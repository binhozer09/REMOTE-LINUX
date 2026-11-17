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

# noVNC/websockify e a API de tarefas ficam atrás do Nginx.
websockify --web=/usr/share/novnc 127.0.0.1:6080 localhost:5900 >/tmp/websockify.log 2>&1 &
WEB_PID=$!
python3 /usr/local/bin/remote-api.py >/tmp/remote-api.log 2>&1 &
API_PID=$!
nginx -g 'daemon off;' >/tmp/nginx.log 2>&1 &
NGINX_PID=$!

sleep 5
gosu remote env DISPLAY=:1 HOME=/home/remote chromium \
  --no-sandbox --disable-gpu --disable-dev-shm-usage --no-first-run \
  --no-default-browser-check --disable-features=Translate \
  --load-extension=/opt/auto-refresh \
  --user-data-dir=/home/remote/.config/chromium \
  --new-window https://www.youtube.com/ \
  >/tmp/chromium.log 2>&1 &
CHROME_PID=$!
echo "Desktop, navegador e API de tarefas iniciados."

(
  set +e
  wait "$CHROME_PID"
  CHROME_EXIT=$?
  echo "Chromium encerrou com código $CHROME_EXIT; abrindo Firefox."
  gosu remote env DISPLAY=:1 HOME=/home/remote firefox-esr --new-window https://www.youtube.com/ >/tmp/firefox.log 2>&1 &
) &

while kill -0 "$NGINX_PID" 2>/dev/null && kill -0 "$XVFB_PID" 2>/dev/null; do
  sleep 5
done
echo "Servidor gráfico ou Nginx encerrou; finalizando serviço."
exit 1
