#!/bin/bash -x 
cd $(dirname ${0})
[[ -f package_install_done ]] || (
	python -m pip install -r requirements.txt
	apt-get -y update
	apt-get -y install ffmpeg tor
)

if [[ "$1" == "--tor" ]]; then
	shift
	exec tor --SocksPort 0.0.0.0:${SOCKS_PORT:-9050} "$@"
fi

sleep ${STARTUP_DELAY:-0}
python ${1:?Missing program} "${@:2}"