#!/usr/bin/env bash
set -Eeuo pipefail

: "${VNC_PASSWORD:?Defina VNC_PASSWORD nas variáveis do Railway antes de iniciar o serviço}"
if [ "${#VNC_PASSWORD}" -lt 8 ]; then
  echo "VNC_PASSWORD precisa ter pelo menos 8 caracteres." >&2
  exit 1
fi

mkdir -p /home/remote/.vnc /home/remote/.config/autostart /home/remote/Desktop
x11vnc -storepasswd "$VNC_PASSWORD" /home/remote/.vnc/passwd >/dev/null
chown -R remote:remote /home/remote/.vnc /home/remote/.config /home/remote/Desktop
chmod 600 /home/remote/.vnc/passwd

export DISPLAY=:1
export HOME=/home/remote
export USER=remote

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

echo "Desktop Linux iniciado; noVNC escutando na porta ${PORT:-8080}."
websockify --web=/usr/share/novnc --heartbeat=30 "${PORT:-8080}" localhost:5900 >/tmp/websockify.log 2>&1 &
WEB_PID=$!

# Aguarda o XFCE criar a sessão X antes de abrir o navegador.
sleep 5
gosu remote env DISPLAY=:1 HOME=/home/remote chromium \
  --no-sandbox --disable-gpu --disable-dev-shm-usage --no-first-run \
  --no-default-browser-check --disable-features=Translate \
  --user-data-dir=/home/remote/.config/chromium \
  --new-window https://www.youtube.com/ \
  >/tmp/chromium.log 2>&1 &
CHROME_PID=$!
echo "Chromium iniciado para abrir o YouTube (PID $CHROME_PID)."

# Mantém o serviço vivo enquanto a sessão gráfica e o acesso remoto estiverem ativos.
wait -n "$XVFB_PID" "$XFCE_PID" "$VNC_PID" "$WEB_PID"
