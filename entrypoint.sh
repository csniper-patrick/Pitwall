#!/bin/bash -x 
cd $(dirname ${0})
[[ -f package_install_done ]] || (
	python -m pip install -r requirements.txt
	apt-get -y update
	apt-get -y install ffmpeg tor proxychains4
)

if [[ "$1" == "--tor" ]]; then
	shift
	exec tor --SocksPort 0.0.0.0:${SOCKS_PORT:-9050} "$@"
fi

CMD_PREFIX=""
if [[ -n "$SOCKS_PROXY" ]]; then
	TOR_ADDR="127.0.0.1"
	TOR_PORT="${SOCKS_PORT:-9050}"

	if [[ "$SOCKS_PROXY" =~ ^[0-9]+$ ]]; then
		TOR_PORT="$SOCKS_PROXY"
	elif [[ "$SOCKS_PROXY" == *":"* ]]; then
		TOR_ADDR="${SOCKS_PROXY%:*}"
		TOR_PORT="${SOCKS_PROXY##*:}"
	elif [[ "$SOCKS_PROXY" != "true" && "$SOCKS_PROXY" != "1" && "$SOCKS_PROXY" != "yes" ]]; then
		TOR_ADDR="$SOCKS_PROXY"
	fi

	if [[ ! "$TOR_ADDR" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
		RESOLVED_ADDR=$(getent ahostsv4 "$TOR_ADDR" | awk '{print $1; exit}')
		if [[ -n "$RESOLVED_ADDR" ]]; then
			TOR_ADDR="$RESOLVED_ADDR"
		fi
	fi

	for local_host in "${REDIS_HOST:-redis}" "${API_HOST:-}"; do
		if [[ -n "$local_host" && ! "$local_host" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
			HOST_IP=$(getent ahostsv4 "$local_host" | awk '{print $1; exit}')
			if [[ "$HOST_IP" =~ ^(127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.) ]]; then
				grep -qE "[[:space:]]${local_host}(\$|[[:space:]])" /etc/hosts || echo "$HOST_IP $local_host" >> /etc/hosts
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
		socks5 $TOR_ADDR $TOR_PORT
	EOF

	CMD_PREFIX="proxychains4"
fi

sleep ${STARTUP_DELAY:-0}
exec ${CMD_PREFIX} python ${1:?Missing program} "${@:2}"
