FROM quay.io/podman/stable:latest
RUN dnf -y install podman docker-compose
ENV DOCKER_HOST=unix:///run/podman/podman.sock
