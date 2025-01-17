FROM docker.io/library/python:3.12-alpine

WORKDIR /opt/
COPY  ./entrypoint.sh ./requirements.txt /opt/
COPY ./publisher/ /opt/publisher/
COPY ./discord/ /opt/discord/
COPY ./data/ /opt/data/
RUN python -m pip install -r requirements.txt

ENTRYPOINT [ "/opt/entrypoint.sh" ]
