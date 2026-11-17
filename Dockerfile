FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:1
ENV PORT=8080
ENV HOME=/home/remote

RUN apt-get update && apt-get install -y --no-install-recommends \
    xfce4 xfce4-terminal xfce4-pulseaudio-plugin dbus-x11 xvfb x11vnc novnc websockify nginx \
    firefox-esr chromium chromium-driver python3-selenium ffmpeg libavcodec-extra \
    pulseaudio pulseaudio-utils pavucontrol alsa-utils libasound2-plugins \
    gstreamer1.0-libav gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
    fonts-liberation fonts-noto-core fonts-noto-color-emoji \
    gosu ca-certificates curl wget procps xterm python3 \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash remote \
    && mkdir -p /home/remote/.vnc /home/remote/Desktop \
    && chown -R remote:remote /home/remote

COPY auto-refresh/ /opt/auto-refresh/
COPY nginx.conf /etc/nginx/sites-available/default
COPY remote_api.py /usr/local/bin/remote-api.py
COPY start.sh /usr/local/bin/start-remote
RUN chmod +x /usr/local/bin/start-remote /usr/local/bin/remote-api.py

EXPOSE 8080
CMD ["/usr/local/bin/start-remote"]
