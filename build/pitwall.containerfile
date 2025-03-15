FROM docker.io/library/python:3.12

WORKDIR /opt/
COPY  ./entrypoint.sh ./requirements.txt /opt/
COPY ./publisher/ /opt/publisher/
COPY ./discord/ /opt/discord/
COPY ./data/ /opt/data/
RUN apt-get -y update && apt-get -y install ffmpeg
RUN python -m pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

ENTRYPOINT [ "/opt/entrypoint.sh" ]
