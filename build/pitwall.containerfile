FROM docker.io/library/python:3.13

WORKDIR /opt/
COPY  ./entrypoint.sh ./requirements.txt /opt/
COPY ./publisher/ /opt/publisher/
COPY ./discord/ /opt/discord/
COPY ./data/ /opt/data/
RUN apt-get -y update && apt-get -y install ffmpeg && python -m pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu && touch package_install_done

ENTRYPOINT [ "/opt/entrypoint.sh" ]
