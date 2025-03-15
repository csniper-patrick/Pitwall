#!/bin/bash -x 
cd $(dirname ${0})
python -m pip install -r requirements.txt
apt-get -y update
apt-get -y install ffmpeg 
sleep ${STARTUP_DELAY:-0}
python ${1:?Missing program}