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

# PulseAudio: cria um dispositivo virtual para que XFCE e Chromium tenham
# uma saída de som mesmo sem placa de áudio física no container.
REMOTE_UID="$(id -u remote)"
export XDG_RUNTIME_DIR="/run/user/$REMOTE_UID"
mkdir -p "$XDG_RUNTIME_DIR"
chown remote:remote "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

gosu remote env XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
  pulseaudio --start --exit-idle-time=-1 --log-target=file:/tmp/pulseaudio.log >/tmp/pulseaudio-start.log 2>&1 || true

PULSE_SERVER="unix:$XDG_RUNTIME_DIR/pulse/native"
AUDIO_READY=0
for attempt in $(seq 1 20); do
  if gosu remote env XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
      PULSE_SERVER="$PULSE_SERVER" pactl info >/dev/null 2>&1; then
    AUDIO_READY=1
    break
  fi
  sleep 1
done

if [ "$AUDIO_READY" -eq 1 ]; then
  if ! gosu remote env XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
      PULSE_SERVER="$PULSE_SERVER" pactl list short sinks | awk '$2 == "remote_output" {found=1} END {exit !found}'; then
    gosu remote env XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" PULSE_SERVER="$PULSE_SERVER" \
      pactl load-module module-null-sink sink_name=remote_output rate=48000 \
      sink_properties=device.description=Remote_Audio >/tmp/pulseaudio-module.log
  fi
  gosu remote env XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" PULSE_SERVER="$PULSE_SERVER" \
    pactl set-default-sink remote_output
  export PULSE_SERVER PULSE_SINK=remote_output
  echo "AUDIO: PulseAudio ativo; saída virtual Remote_Audio configurada."
else
  echo "AUDIO: PulseAudio não iniciou; consulte /tmp/pulseaudio.log."
  if [ -s /tmp/pulseaudio.log ]; then tail -n 30 /tmp/pulseaudio.log; fi
fi

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

websockify --heartbeat=25 --web=/usr/share/novnc 127.0.0.1:6080 localhost:5900 >/tmp/websockify.log 2>&1 &

YOUTUBE_URL="${YOUTUBE_URL:-https://youtu.be/bWO1FNUTIao?is=IHQ1W9LWAd36Sf23}"
YOUTUBE_TAB_COUNT=1
CHROMIUM_URLS=("$YOUTUBE_URL")
CHROMIUM_PROFILE=/home/remote/.config/chromium
mkdir -p "$CHROMIUM_PROFILE" /home/remote/Downloads
chown -R remote:remote "$CHROMIUM_PROFILE" /home/remote/Downloads

# O volume pode reter locks deixados por um container antigo. O Railway
# está configurado sem sobreposição de deployments; portanto, antes de
# iniciar este Chromium, removemos apenas os arquivos de lock, nunca cookies
# ou o restante do perfil.
if pgrep -u remote -f '[c]hromium.*user-data-dir=/home/remote/.config/chromium' >/dev/null; then
  echo "CHROMIUM: já existe um processo usando o perfil; não vou remover os locks."
else
  rm -f "$CHROMIUM_PROFILE/SingletonLock" \
        "$CHROMIUM_PROFILE/SingletonCookie" \
        "$CHROMIUM_PROFILE/SingletonSocket"
  echo "CHROMIUM: locks antigos verificados; perfil persistente preservado."
fi

if [ -s "$CHROMIUM_PROFILE/Default/Cookies" ]; then
  echo "CHROMIUM: banco de cookies existente no volume persistente."
elif [ -s "$CHROMIUM_PROFILE/Default/Network/Cookies" ]; then
  echo "CHROMIUM: banco de cookies existente no volume persistente."
else
  echo "CHROMIUM: banco de cookies ainda não encontrado; faça login uma vez após iniciar."
fi

# Uma única aba reduz o consumo do Chromium; a extensão mantém a recarga
# automática do YouTube a cada 60 segundos e tenta retomar a reprodução.
gosu remote chromium \
  --no-sandbox \
  --disable-dev-shm-usage \
  --disable-gpu \
  --disable-gpu-compositing \
  --disable-features=Vulkan,UseSkiaRenderer \
  --renderer-process-limit=4 \
  --process-per-site \
  --enable-extensions \
  --disable-extensions-except=/opt/auto-refresh \
  --load-extension=/opt/auto-refresh \
  --enable-audio-focus=no-enforce \
  --autoplay-policy=no-user-gesture-required \
  --password-store=basic \
  --disable-background-timer-throttling \
  --disable-renderer-backgrounding \
  --disable-backgrounding-occluded-windows \
  --no-first-run \
  --no-default-browser-check \
  --user-data-dir="$CHROMIUM_PROFILE" \
  --start-maximized \
  "${CHROMIUM_URLS[@]}" >/tmp/chromium.log 2>&1 &
CHROMIUM_PID=$!
sleep 3
if pgrep -u remote -f 'chromium.*user-data-dir=/home/remote/.config/chromium' >/dev/null; then
  echo "CHROMIUM: processo ativo usando o perfil persistente."
else
  echo "CHROMIUM: não iniciou; últimas mensagens:"
  tail -n 40 /tmp/chromium.log || true
fi

echo "YouTube aberto automaticamente em $YOUTUBE_TAB_COUNT aba: $YOUTUBE_URL (autoplay ativo e a aba atualiza a cada 60 segundos)."

python3 /usr/local/bin/remote-api.py &
API_PID=$!
nginx -g 'daemon off;' >/tmp/nginx.log 2>&1 &
NGINX_PID=$!

echo "Desktop remoto, Chromium, áudio PulseAudio, YouTube e API de tarefas iniciados."

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
    for f in /tmp/nginx.log /tmp/xvfb.log /tmp/remote-api.log /tmp/websockify.log /tmp/x11vnc.log /tmp/xfce.log /tmp/chromium.log /tmp/pulseaudio.log; do
      if [ -s "$f" ]; then echo "===== $f ====="; tail -n 40 "$f"; fi
    done
    exit 1
  fi
done
