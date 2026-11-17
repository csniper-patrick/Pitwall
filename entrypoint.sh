#!/bin/bash -x 
set -eo pipefail
cd $(dirname ${0})

if [[ "$1" == "--tor" ]]; then
	shift
	command -v tor >/dev/null || (apt-get -y update && apt-get -y install tor)
	exec tor --SocksPort 0.0.0.0:9050 "$@"
fi

[[ -f package_install_done ]] || (
	python -m pip install -r requirements.txt
	apt-get -y update
	apt-get -y install ffmpeg proxychains4
)

sleep ${STARTUP_DELAY:-0}

is_ipv4() {
	[[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
}

resolve_ipv4() {
	if is_ipv4 "$1"; then
		echo "$1"
		return 0
	fi
	local ip=""
	local retries="${RESOLVE_RETRIES:-5}"
	for ((i = 1; i <= retries; i++)); do
		ip=$(getent ahostsv4 "$1" | awk '{print $1; exit}')
		if [[ -n "$ip" ]]; then
			echo "$ip"
			return 0
		fi
		if ((i < retries)); then
			sleep 1
		fi
	done
	return 1
}

wait_for_tcp() {
	local host="$1"
	local port="$2"
	local retries="${PROXY_READY_RETRIES:-30}"
	for ((i = 1; i <= retries; i++)); do
		if timeout 2 bash -c '</dev/tcp/"$1"/"$2"' _ "$host" "$port" 2>/dev/null; then
			return 0
		fi
		if ((i < retries)); then
			sleep 2
		fi
	done
	return 1
}

update_hosts_entry() {
	local ip="$1"
	local host="$2"
	if awk -v ip="$ip" -v h="$host" '
		$1 !~ /^#/ && $1 == ip {
			for (i = 2; i <= NF; i++) if ($i == h) found = 1
		}
		END { exit !found }
	' /etc/hosts; then
		return 0
	fi
	local content
	content=$(awk -v h="$host" '
		$1 ~ /^#/ { print; next }
		{
			out = $1; kept = 0
			for (i = 2; i <= NF; i++) {
				if ($i != h) { out = out " " $i; kept = 1 }
			}
			if (kept) print out
		}
	' /etc/hosts)
	printf "%s\n%s %s\n" "$content" "$ip" "$host" > /etc/hosts
}

CMD_PREFIX=()
if [[ -n "$SOCKS_PROXY" ]]; then
	PROXY_SPEC="${SOCKS_PROXY#socks5://}"
	PROXY_SPEC="${PROXY_SPEC#socks5h://}"
	if [[ "$PROXY_SPEC" == *":"* ]]; then
		PROXY_HOST="${PROXY_SPEC%:*}"
		PROXY_PORT="${PROXY_SPEC##*:}"
		[[ -z "$PROXY_PORT" ]] && PROXY_PORT="9050"
	else
		PROXY_HOST="$PROXY_SPEC"
		PROXY_PORT="9050"
	fi

	if [[ -z "$PROXY_HOST" || ! "$PROXY_PORT" =~ ^[0-9]+$ ]]; then
		echo "Error: invalid SOCKS_PROXY '$SOCKS_PROXY'" >&2
		exit 1
	fi

	if ! PROXY_IP=$(resolve_ipv4 "$PROXY_HOST"); then
		echo "Error: failed to resolve SOCKS_PROXY host '$PROXY_HOST'" >&2
		exit 1
	fi

	if ! wait_for_tcp "$PROXY_IP" "$PROXY_PORT"; then
		echo "Error: SOCKS_PROXY '$PROXY_IP:$PROXY_PORT' is not reachable" >&2
		exit 1
	fi

	for raw_host in "${REDIS_HOST:-redis}" "${API_HOST:-}"; do
		local_host="${raw_host%%:*}"
		if [[ -n "$local_host" ]] && ! is_ipv4 "$local_host"; then
			if ! HOST_IP=$(resolve_ipv4 "$local_host"); then
				if [[ "$local_host" != *"."* ]]; then
					echo "Error: failed to resolve host '$local_host'" >&2
					exit 1
				fi
				echo "Warning: could not pre-resolve '$local_host'; deferring to proxy_dns" >&2
				continue
			fi
			if [[ "$HOST_IP" =~ ^(127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.) ]]; then
				update_hosts_entry "$HOST_IP" "$local_host"
			fi
		fi
	done

	cat <<-EOF > /etc/proxychains4.conf
		strict_chain
		proxy_dns
		remote_dns_subnet 224
		tcp_read_time_out 15000
		tcp_connect_time_out 8000
		localnet 127.0.0.0/255.0.0.0
		localnet 10.0.0.0/255.0.0.0
		localnet 172.16.0.0/255.240.0.0
		localnet 192.168.0.0/255.255.0.0

		[ProxyList]
		socks5 $PROXY_IP $PROXY_PORT
	EOF

	CMD_PREFIX=(proxychains4)
fi

exec "${CMD_PREFIX[@]}" python "${1:?Missing program}" "${@:2}"
