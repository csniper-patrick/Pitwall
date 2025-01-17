#!/bin/bash -x 
cd $(dirname ${0})
python -m pip install -r requirements.txt
sleep ${STARTUP_DELAY:-0}
python ${1:?Missing program}