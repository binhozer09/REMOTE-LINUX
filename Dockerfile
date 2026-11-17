FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:1
ENV PORT=8080
ENV HOME=/home/remote

RUN apt-get update && apt-get install -y --no-install-recommends \
    xfce4 xfce4-terminal dbus-x11 xvfb x11vnc novnc websockify \
    firefox-esr chromium fonts-liberation fonts-noto-core \
    gosu ca-certificates curl wget procps xterm \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash remote \
    && mkdir -p /home/remote/.vnc \
    && chown -R remote:remote /home/remote

COPY start.sh /usr/local/bin/start-remote
RUN chmod +x /usr/local/bin/start-remote

EXPOSE 8080
CMD ["/usr/local/bin/start-remote"]
