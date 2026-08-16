#!/bin/bash -x 
cd $(dirname ${0})
[[ -f package_install_done ]] || (
	python -m pip install -r requirements.txt
	apt-get -y update
	apt-get -y install ffmpeg tor torsocks
)

if [[ "$1" == "--tor" ]]; then
	shift
	exec tor --SocksPort 0.0.0.0:${SOCKS_PORT:-9050} "$@"
fi

CMD_PREFIX=""
if [[ -n "$SOCKS_PROXY" ]]; then
	TOR_ADDR="0.0.0.0"
	TOR_PORT="9050"

	if [[ "$SOCKS_PROXY" =~ ^[0-9]+$ ]]; then
		TOR_PORT="$SOCKS_PROXY"
	elif [[ "$SOCKS_PROXY" == *":"* ]]; then
		TOR_ADDR="${SOCKS_PROXY%:*}"
		TOR_PORT="${SOCKS_PROXY##*:}"
	elif [[ "$SOCKS_PROXY" != "true" && "$SOCKS_PROXY" != "1" && "$SOCKS_PROXY" != "yes" ]]; then
		TOR_ADDR="$SOCKS_PROXY"
		TOR_PORT="${SOCKS_PORT:-9050}"
	fi

	export TORSOCKS_TOR_ADDRESS="$TOR_ADDR"
	export TORSOCKS_TOR_PORT="$TOR_PORT"
	export TORSOCKS_ALLOW_OUTBOUND_LOCALHOST=1

	mkdir -p /etc/tor
	cat <<-EOF > /etc/tor/torsocks.conf
		TorAddress $TOR_ADDR
		TorPort $TOR_PORT
		AllowOutboundLocalhost 1
	EOF

	CMD_PREFIX="torsocks"
fi

sleep ${STARTUP_DELAY:-0}
${CMD_PREFIX} python ${1:?Missing program} "${@:2}"