# publisher/utils.py
"""
Utility functions for the publisher services.
"""

import base64
import contextlib
import hashlib
import json
import logging
import os
import re
import secrets
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# --- Formula 1 Account Auth & SignalR Core Constants ---
ACCOUNT_ORIGIN = "https://account.formula1.com"
CONFIG_SCRIPT_URL = f"{ACCOUNT_ORIGIN}/scripts/main.min.js"
IDP_ORIGIN = "https://id.formula1.com"
AUTHORIZE_URL = f"{IDP_ORIGIN}/as/authorize"
TOKEN_URL = f"{IDP_ORIGIN}/as/token"
AUTH_TIMEOUT = (5, 30)
EXPIRY_MARGIN = 300  # Renew tokens 5 minutes before expiry to avoid mid-handshake 401s.
RECORD_SEPARATOR = "\x1e"  # SignalR Core JSON message delimiter.

DEFAULT_AUTH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
PING_SDK_HEADERS = {"X-Requested-With": "ping-sdk"}
_DAVINCI_OBJECT = re.compile(r"\bdavinci:\{([^}]*)\}")


class F1AuthError(Exception):
    """Raised when Formula 1 account authentication fails."""


def updateDictDelta(obj: Dict[str, Any], delta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively updates a dictionary with the values from another dictionary.

    This is used to apply delta updates received from the live timing API to the
    full data structures stored in Redis.

    Args:
        obj: The dictionary to be updated.
        delta: The dictionary containing the new values.

    Returns:
        The updated dictionary.
    """
    for key, value in delta.items():
        if key not in obj:
            obj[key] = value
        elif isinstance(value, dict) and isinstance(obj.get(key), dict):
            obj[key] = updateDictDelta(obj[key], value)
        elif isinstance(value, dict) and isinstance(obj.get(key), list):
            # This handles cases where a list of dictionaries is updated by index.
            tempDict = {str(idx): val for idx, val in enumerate(obj[key])}
            tempDict = updateDictDelta(tempDict, value)
            obj[key] = list(tempDict.values())
        else:
            obj[key] = value
    return obj


def timeStr2msec(timeStr: str) -> float:
    """
    Converts a time string (e.g., "1:23.456") to milliseconds.

    Args:
        timeStr: The time string to convert.

    Returns:
        The time in milliseconds.
    """
    parts = re.split(r"[:.]", timeStr)
    m, s, ms = (parts + ['0'] * 3)[:3] # Pad with zeros if parts are missing
    return (int(m) * 60 + int(s)) * 1000 + int(ms)


def msec2timeStr(msec: int, signed: bool = False) -> str:
    """
    Converts milliseconds to a time string (e.g., "1:23.456").

    Args:
        msec: The time in milliseconds.
        signed: Whether to include a '+' sign for positive values.

    Returns:
        The formatted time string.
    """
    val = abs(int(msec))
    if signed:
        timeStr = "+" if msec >= 0 else "-"
    else:
        timeStr = "" if msec >= 0 else "-"

    minutes = val // 60000
    seconds = (val % 60000) // 1000
    milliseconds = val % 1000

    if minutes > 0:
        return f"{timeStr}{minutes}:{seconds:02}.{milliseconds:03}"
    return f"{timeStr}{seconds}.{milliseconds:03}"


def load_config() -> Tuple[bool, str, bool, str, str, str, float, str, int, str]:
    """
    Loads configuration settings from environment variables.

    This centralizes the configuration for all publisher services.

    Returns:
        A tuple containing the loaded configuration settings.
    """
    log_level = os.getenv("LOG_LEVEL", default="INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # --- General Settings ---
    USE_SSL = os.getenv("USE_SSL", default="True").lower() == "true"
    API_HOST = os.getenv("API_HOST", default="livetiming.formula1.com")
    RETRY = os.getenv("RETRY", default="True").lower() == "true"

    # --- URL Construction ---
    # Build the base URLs for the live timing API.
    base_http_url = f"https://{API_HOST}" if USE_SSL else f"http://{API_HOST}"
    base_ws_url = f"wss://{API_HOST}" if USE_SSL else f"ws://{API_HOST}"

    livetimingUrl = urllib.parse.urljoin(base_http_url, "/signalrcore")
    websocketUrl = urllib.parse.urljoin(base_ws_url, "/signalrcore")
    staticUrl = urllib.parse.urljoin(base_http_url, "/static")

    # --- Redis Configuration ---
    REDIS_HOST = os.getenv("REDIS_HOST", default="redis")
    REDIS_PORT = int(os.getenv("REDIS_PORT", default=6379))
    REDIS_CHANNEL = "RACE_CONTROL" # Note: This is a default and may not be used by all publishers.

    # --- SignalR Client Configuration ---
    clientProtocol = 1.5

    return (
        USE_SSL,
        API_HOST,
        RETRY,
        livetimingUrl,
        websocketUrl,
        staticUrl,
        clientProtocol,
        REDIS_HOST,
        REDIS_PORT,
        REDIS_CHANNEL,
    )


def _decode_jwt_payload(token: str) -> Dict[str, Any]:
    """Decode the payload of a JWT without verifying its signature."""
    # Signature verification is handled by the F1 API server; the client only reads claims.
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid JWT structure")
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        decoded = base64.urlsafe_b64decode(payload_b64 + padding)
        payload = json.loads(decoded.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JWT payload is not a JSON object")
        return payload
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise F1AuthError(f"Failed to decode JWT payload: {exc}") from exc


def _hash_username(username: str) -> str:
    """Return a stable SHA-256 digest for the given username."""
    return hashlib.sha256(username.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SubscriptionToken:
    """F1TV entitlement JWT sent as a Bearer token to F1 live timing APIs."""

    value: str = field(repr=False)
    expires_at: float
    user_hash: str = ""

    @classmethod
    def from_jwt(cls, value: str, user_hash: str = "") -> "SubscriptionToken":
        """Create a SubscriptionToken from a JWT string, reading its exp claim."""
        payload = _decode_jwt_payload(value)
        try:
            expires_at = float(payload["exp"])
        except (KeyError, TypeError, ValueError) as exc:
            raise F1AuthError("Subscription token has no valid expiry.") from exc
        return cls(value=value, expires_at=expires_at, user_hash=user_hash)

    @property
    def authorization_header(self) -> str:
        """Return the HTTP Authorization header value."""
        return f"Bearer {self.value}"

    def is_valid(self) -> bool:
        """Return True if the token has not expired within EXPIRY_MARGIN."""
        return self.expires_at - EXPIRY_MARGIN > time.time()


class TokenManager:
    """Caches and renews the F1 subscription token in memory and on disk."""

    VERSION = 1

    def __init__(self, path: Optional[Path] = None):
        self._custom_path = path
        self._tokens: Dict[str, SubscriptionToken] = {}

    def _token_path_for(self, user_hash: Optional[str] = None) -> Path:
        if self._custom_path is not None:
            return self._custom_path
        if env_path := os.getenv("F1_TOKEN_PATH"):
            return Path(env_path)
        if user_hash:
            return Path(f"/tmp/f1auth_token_{user_hash}.json")
        return Path("/tmp/f1auth_token.json")

    def get(
        self,
        username: str,
        password: str,
        force_renew: bool = False,
    ) -> SubscriptionToken:
        """Return a valid token for username, signing in when necessary."""
        user_hash = _hash_username(username)
        if not force_renew:
            token = self.get_stored(user_hash=user_hash)
            if token is not None and token.is_valid():
                return token

        logger.info("Signing in to Formula 1 account...")
        token = login(username, password)
        self._tokens[user_hash] = token
        logger.info("Sign-in successful.")

        try:
            self.store(token, user_hash=user_hash)
        except OSError as exc:
            logger.warning(f"Failed to store the access token: {exc}")
        return token

    def get_stored(self, user_hash: Optional[str] = None) -> Optional[SubscriptionToken]:
        """Return a stored token from memory or disk if it matches user_hash."""
        if user_hash is not None:
            token = self._tokens.get(user_hash)
            if token is not None:
                return token if token.user_hash == user_hash else None
        elif len(self._tokens) == 1:
            return next(iter(self._tokens.values()))

        path = self._token_path_for(user_hash)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.pop("version", None) != self.VERSION:
                return None
            token = SubscriptionToken(**data)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return None

        # Verify account ownership before caching in memory to prevent cross-user poisoning.
        if user_hash is not None and token.user_hash != user_hash:
            return None

        self._tokens[token.user_hash] = token
        return token

    def store(
        self, token: SubscriptionToken, user_hash: Optional[str] = None
    ) -> None:
        """Persist the token to disk atomically with owner-only permissions."""
        path = self._token_path_for(user_hash or token.user_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        payload = json.dumps({"version": self.VERSION, **asdict(token)})
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.chmod(tmp_path, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                tmp_path.unlink()
            raise
        os.replace(tmp_path, path)

    def clear(self, user_hash: Optional[str] = None) -> None:
        """Remove the stored token for user_hash (or all tokens if omitted)."""
        if user_hash is not None:
            self._tokens.pop(user_hash, None)
            path = self._token_path_for(user_hash)
            # When sharing a custom/env file path, only unlink if it belongs to user_hash.
            if self._custom_path is not None or os.getenv("F1_TOKEN_PATH"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if data.get("user_hash") != user_hash:
                        return
                except (OSError, ValueError, TypeError):
                    pass
            with contextlib.suppress(FileNotFoundError):
                path.unlink()
            return

        known_hashes = list(self._tokens.keys())
        self._tokens.clear()
        for known_hash in known_hashes:
            with contextlib.suppress(FileNotFoundError):
                self._token_path_for(known_hash).unlink()
        with contextlib.suppress(FileNotFoundError):
            self._token_path_for(None).unlink()


_token_manager = TokenManager()


def _fetch_auth_config(session: requests.Session) -> Tuple[str, str]:
    """Scrape the DaVinci OAuth clientId and policyId from account.formula1.com."""
    resp = session.get(CONFIG_SCRIPT_URL, timeout=AUTH_TIMEOUT)
    resp.raise_for_status()

    obj = _DAVINCI_OBJECT.search(resp.text)
    if not obj:
        raise F1AuthError(f"No config object found in {CONFIG_SCRIPT_URL}")

    def field(name: str) -> str:
        match = re.search(rf'\b{name}:"([^"]+)"', obj.group(1))
        if not match:
            raise F1AuthError(f"Config scrape missing required field {name}")
        return match.group(1)

    return field("clientId"), field("acrValues")


def _code_challenge(code_verifier: str) -> str:
    """Compute a PKCE S256 code challenge (RFC 7636)."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _code_from_flow_response(resp: requests.Response, state: str) -> str:
    """Validate the DaVinci response and return the authorization code."""
    try:
        data = resp.json()
    except ValueError:
        resp.raise_for_status()
        raise F1AuthError("Unexpected response from the sign-in.") from None

    if data.get("status") != "COMPLETED":
        raise F1AuthError(
            data.get("message") or f"Sign-in failed (status {resp.status_code})."
        )
    auth_response = data.get("authorizeResponse") or {}
    if auth_response.get("state") != state:
        raise F1AuthError("Sign-in failed: state mismatch in the response.")
    code = auth_response.get("code")
    if not (code and isinstance(code, str)):
        raise F1AuthError("Sign-in failed: no authorization code returned.")
    return code


def login(username: str, password: str) -> SubscriptionToken:
    """Authenticate with Formula 1 using username and password and return a SubscriptionToken."""
    try:
        # Share one Session so PingOne/DaVinci flow cookies persist across all OAuth steps.
        with requests.Session() as session:
            session.headers.update(DEFAULT_AUTH_HEADERS)
            # 1. Discover dynamic DaVinci OAuth client/policy IDs.
            client_id, policy_id = _fetch_auth_config(session)

            code_verifier = secrets.token_urlsafe(64)
            state = secrets.token_urlsafe(24)

            # 2. Request redirectless DaVinci login flow (response_mode=pi.flow).
            resp = session.get(
                AUTHORIZE_URL,
                params={
                    "client_id": client_id,
                    "response_type": "code",
                    "response_mode": "pi.flow",
                    "scope": "openid",
                    "state": state,
                    "nonce": secrets.token_urlsafe(24),
                    "code_challenge": _code_challenge(code_verifier),
                    "code_challenge_method": "S256",
                    "acr_values": policy_id,
                },
                headers=PING_SDK_HEADERS,
                timeout=AUTH_TIMEOUT,
            )
            resp.raise_for_status()
            form = resp.json()

            try:
                submit_url = form["_links"]["next"]["href"]
                interaction_id = form["interactionId"]
                flow_id = form["id"]
                event_name = form["eventName"]
            except (KeyError, TypeError) as exc:
                raise F1AuthError(
                    "Unexpected response when starting the sign-in."
                ) from exc

            # Never post credentials outside the expected Formula 1 IdP origin.
            if not submit_url.startswith(f"{IDP_ORIGIN}/"):
                raise F1AuthError(f"Unexpected sign-in url {submit_url}.")

            # 3. Submit username/password to obtain the authorization code.
            resp = session.post(
                submit_url,
                json={
                    "id": flow_id,
                    "eventName": event_name,
                    "interactionId": interaction_id,
                    "parameters": {
                        "eventType": "submit",
                        "data": {
                            "actionKey": "SIGNIN",
                            "formData": {"username": username, "password": password},
                        },
                    },
                },
                headers={**PING_SDK_HEADERS, "interactionId": interaction_id},
                timeout=AUTH_TIMEOUT,
            )
            code = _code_from_flow_response(resp, state)

            # 4. Exchange authorization code + PKCE verifier for the access token.
            resp = session.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "code": code,
                    "code_verifier": code_verifier,
                },
                timeout=AUTH_TIMEOUT,
            )
            resp.raise_for_status()
            try:
                access_token = resp.json()["access_token"]
            except (ValueError, KeyError, TypeError) as exc:
                raise F1AuthError("No access token in the token response.") from exc
    except requests.RequestException as exc:
        raise F1AuthError(f"Sign-in failed: {exc}") from exc

    claims = _decode_jwt_payload(access_token)
    subscription_jwt = claims.get("subscriptionToken")
    if not subscription_jwt:
        raise F1AuthError(
            "Access token contains no subscription token. "
            "An active F1TV subscription is required."
        )
    return SubscriptionToken.from_jwt(
        subscription_jwt, user_hash=_hash_username(username)
    )


def get_token(
    force_renew: bool = False,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> SubscriptionToken:
    """Return a valid F1 subscription token using explicit or env credentials."""
    resolved_user = username if username is not None else os.getenv("F1_USERNAME")
    resolved_pass = password if password is not None else os.getenv("F1_PASSWORD")
    if not resolved_user or not resolved_pass:
        raise F1AuthError(
            "No F1 account credentials available. Set F1_USERNAME and F1_PASSWORD."
        )
    return _token_manager.get(
        resolved_user, resolved_pass, force_renew=force_renew
    )


def clear_token(username: Optional[str] = None) -> None:
    """Remove the cached F1 subscription token for username (or all if omitted)."""
    resolved_user = username if username is not None else os.getenv("F1_USERNAME")
    user_hash = _hash_username(resolved_user) if resolved_user else None
    _token_manager.clear(user_hash=user_hash)


def _try_get_token(
    force_renew: bool = False,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Optional[SubscriptionToken]:
    """Obtain an F1 token, logging a warning and returning None on failure."""
    try:
        return get_token(
            force_renew=force_renew, username=username, password=password
        )
    except F1AuthError as exc:
        logger.warning(
            f"Failed to authenticate with Formula 1 account, "
            f"continuing without authentication: {exc}"
        )
        return None


def negotiate_signalr(
    livetiming_url: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Any, Optional[str], Optional[Dict[str, str]]]:
    """
    Negotiate an authenticated SignalR Core connection with the live timing server.

    Returns:
        A tuple containing negotiation JSON, response headers, encoded URL query
        parameters, and extra headers (Cookie and Authorization) for WebSocket connect.
    """
    token = _try_get_token(username=username, password=password)
    negotiate_url = f"{livetiming_url}/negotiate"

    try:
        with requests.Session() as session:
            session.headers.update(
                {
                    "User-Agent": "BestHTTP",
                    "Accept-Encoding": "gzip,identity",
                }
            )
            if token is not None:
                session.headers["Authorization"] = token.authorization_header

            # Pre-negotiate to obtain AWSALBCORS sticky cookie (returned even on HTTP 405).
            session.options(negotiate_url, timeout=AUTH_TIMEOUT)

            res = session.post(
                negotiate_url,
                headers={"Content-Type": "application/json"},
                timeout=AUTH_TIMEOUT,
            )

            # Retry once with a fresh token in case the cached JWT was revoked before exp.
            if res.status_code == 401 and token is not None:
                clear_token(username=username)
                token = _try_get_token(
                    force_renew=True, username=username, password=password
                )
                if token is not None:
                    session.headers["Authorization"] = token.authorization_header
                else:
                    session.headers.pop("Authorization", None)
                res = session.post(
                    negotiate_url,
                    headers={"Content-Type": "application/json"},
                    timeout=AUTH_TIMEOUT,
                )

            res.raise_for_status()
            data = res.json()

            connection_id = data.get("connectionId")
            if not connection_id:
                raise requests.exceptions.RequestException(
                    "Negotiate response missing connectionId"
                )

            params = urllib.parse.urlencode({"id": connection_id})
            extra_headers: Dict[str, str] = {
                "User-Agent": "BestHTTP",
                "Accept-Encoding": "gzip,identity",
            }
            if session.cookies:
                extra_headers["Cookie"] = "; ".join(
                    f"{name}={value}" for name, value in session.cookies.items()
                )
            if token is not None:
                extra_headers["Authorization"] = token.authorization_header

            return data, res.headers, params, extra_headers

    except requests.exceptions.RequestException as error:
        logger.error(f"Negotiation failed: {error}")
        return None, None, None, None


def parse_signalr_messages(raw_message: str) -> List[Dict[str, Any]]:
    """
    Parse a raw SignalR Core WebSocket frame into normalized message dicts.

    SignalR Core frames are delimited by ASCII record separator (0x1e).
    Normalizes Completion (type 3) into {"R": ...} and 'feed' Invocation (type 1)
    into {"M": [{"H": "Streaming", "M": "feed", "A": [...]}]}.
    """
    parsed: List[Dict[str, Any]] = []
    for record in raw_message.split(RECORD_SEPARATOR):
        if not record:
            continue
        msg = json.loads(record)
        if not isinstance(msg, dict):
            continue

        if "type" not in msg:
            parsed.append(msg)
            continue

        msg_type = msg.get("type")
        if msg_type == 6:  # PingMessage (keepalive; nothing to publish)
            continue
        if msg_type == 7:  # CloseMessage (raise to trigger reconnect loop)
            raise ConnectionError(
                msg.get("error") or "SignalR connection closed by server"
            )
        if msg_type == 3:  # CompletionMessage (initial topic snapshots)
            if msg.get("error"):
                raise ConnectionError(f"SignalR invocation error: {msg['error']}")
            result = msg.get("result")
            if isinstance(result, dict):
                parsed.append({"R": result})
        elif msg_type == 1:  # InvocationMessage (incremental stream updates)
            if str(msg.get("target", "")).lower() == "feed":
                args = msg.get("arguments") or []
                parsed.append(
                    {"M": [{"H": "Streaming", "M": "feed", "A": args}]}
                )

    return parsed


async def subscribe_signalr(
    sock: Any, topics: List[str], invocation_id: str = "1"
) -> List[Dict[str, Any]]:
    """
    Perform the SignalR Core JSON handshake and subscribe to the requested topics.

    Returns any trailing SignalR messages bundled with the handshake response.
    """
    await sock.send(
        json.dumps({"protocol": "json", "version": 1}) + RECORD_SEPARATOR
    )
    handshake_raw = await sock.recv()
    records = [r for r in handshake_raw.split(RECORD_SEPARATOR) if r]
    if not records:
        raise ConnectionError("Empty SignalR handshake response")

    handshake_resp = json.loads(records[0])
    if handshake_resp.get("error"):
        raise ConnectionError(
            f"SignalR handshake failed: {handshake_resp['error']}"
        )

    await sock.send(
        json.dumps(
            {
                "type": 1,
                "invocationId": invocation_id,
                "target": "Subscribe",
                "arguments": [topics],
            }
        )
        + RECORD_SEPARATOR
    )

    # Forward any messages piggybacked in the same WebSocket frame as the handshake.
    if len(records) > 1:
        return parse_signalr_messages(RECORD_SEPARATOR.join(records[1:]))
    return []


async def iter_signalr_messages(
    sock: Any, initial_messages: Optional[List[Dict[str, Any]]] = None
) -> AsyncIterator[Dict[str, Any]]:
    """Yield parsed SignalR messages from initial handshake leftovers and the socket."""
    for msg in initial_messages or ():
        yield msg
    while True:
        raw_frame = await sock.recv()
        for msg in parse_signalr_messages(raw_frame):
            yield msg
