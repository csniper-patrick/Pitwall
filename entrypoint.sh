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

CMD_PREFIX=()
if [[ -n "$SOCKS_PROXY" ]]; then
	PROXY_HOST="${SOCKS_PROXY%:*}"
	PROXY_PORT="${SOCKS_PROXY##*:}"
	[[ "$PROXY_PORT" == "$SOCKS_PROXY" || -z "$PROXY_PORT" ]] && PROXY_PORT="9050"
	PROXY_IP=$(getent ahostsv4 "$PROXY_HOST" | awk '{print $1; exit}' || true)

	for host in "${REDIS_HOST:-redis}" "${API_HOST:-}"; do
		host="${host%%:*}"
		[[ -z "$host" ]] && continue
		ip=$(getent ahostsv4 "$host" | awk '{print $1; exit}' || true)
		if [[ "$ip" =~ ^(127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.) ]]; then
			grep -qE "[[:space:]]${host}(\$|[[:space:]])" /etc/hosts || echo "$ip $host" >> /etc/hosts
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
		socks5 ${PROXY_IP:?Failed to resolve $PROXY_HOST} $PROXY_PORT
	EOF

	CMD_PREFIX=(proxychains4)
fi

exec "${CMD_PREFIX[@]}" python "${1:?Missing program}" "${@:2}"
