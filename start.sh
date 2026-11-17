#!/usr/bin/env bash
set -Eeuo pipefail

: "${VNC_PASSWORD:?Defina VNC_PASSWORD nas variáveis do Railway antes de iniciar o serviço}"
: "${REMOTE_CONTROL_TOKEN:?REMOTE_CONTROL_TOKEN ausente}"
if [ "${#VNC_PASSWORD}" -lt 8 ]; then
  echo "VNC_PASSWORD precisa ter pelo menos 8 caracteres." >&2
  exit 1
fi

mkdir -p /home/remote/.vnc /home/remote/.config/autostart /home/remote/Desktop
x11vnc -storepasswd "$VNC_PASSWORD" /home/remote/.vnc/passwd >/dev/null
chown -R remote:remote /home/remote/.vnc /home/remote/.config /home/remote/Desktop
chmod 600 /home/remote/.vnc/passwd

export DISPLAY=:1 HOME=/home/remote USER=remote

gosu remote Xvfb :1 -screen 0 "${SCREEN_SIZE:-1280x800x24}" -ac +extension GLX +render -noreset >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!
cleanup() {
  kill "$XVFB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sleep 2
gosu remote dbus-launch --exit-with-session startxfce4 >/tmp/xfce.log 2>&1 &
XFCE_PID=$!

sleep 3
gosu remote x11vnc -display :1 -rfbauth /home/remote/.vnc/passwd \
  -forever -shared -localhost -rfbport 5900 -xkb -noxrecord -noxfixes -noxdamage >/tmp/x11vnc.log 2>&1 &
VNC_PID=$!

websockify --web=/usr/share/novnc 127.0.0.1:6080 localhost:5900 >/tmp/websockify.log 2>&1 &
WEB_PID=$!
python3 /usr/local/bin/remote-api.py >/tmp/remote-api.log 2>&1 &
API_PID=$!
nginx -g 'daemon off;' >/tmp/nginx.log 2>&1 &
NGINX_PID=$!

echo "Desktop remoto e API de tarefas iniciados; navegador aguardando abertura manual."

while true; do
  sleep 5
  FAILED=""
  for item in "nginx:$NGINX_PID" "xvfb:$XVFB_PID" "api:$API_PID" "websockify:$WEB_PID" "x11vnc:$VNC_PID"; do
    name="${item%%:*}"
    pid="${item##*:}"
    if ! kill -0 "$pid" 2>/dev/null; then FAILED="$FAILED $name"; fi
  done
  if [ -n "$FAILED" ]; then
    echo "Processos encerrados:$FAILED"
    for f in /tmp/nginx.log /tmp/xvfb.log /tmp/remote-api.log /tmp/websockify.log /tmp/x11vnc.log /tmp/xfce.log; do
      if [ -s "$f" ]; then echo "===== $f ====="; tail -n 40 "$f"; fi
    done
    exit 1
  fi
done
