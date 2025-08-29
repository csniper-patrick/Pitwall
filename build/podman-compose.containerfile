FROM quay.io/podman/stable:latest
RUN dnf -y install wget \
    && wget https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m) -O /usr/local/bin/docker-compose \
    && chmod +x /usr/local/bin/docker-compose
