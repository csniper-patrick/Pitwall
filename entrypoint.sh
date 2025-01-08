#!/bin/bash -x 
cd $(dirname ${0})
python -m pip install -r requirements.txt
sleep 10
python ${1:?Missing program}