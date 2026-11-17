// Autoplay persistente do YouTube + reinício da faixa a cada 60 segundos.
(() => {
  if (window.__remotePlaybackGuardInstalled) return;
  window.__remotePlaybackGuardInstalled = true;

  const host = location.hostname.toLowerCase();
  const isYouTube =
    host === "youtube.com" || host.endsWith(".youtube.com") ||
    host === "youtu.be" ||
    host === "youtube-nocookie.com" || host.endsWith(".youtube-nocookie.com");
  if (!isYouTube) return;

  const RELOAD_MS = 60000;
  const RETRY_MS = 1200;
  let attempting = false;
  let lastAttempt = 0;

  const getPlayer = () => document.getElementById("movie_player");
  const getVideo = () =>
    document.querySelector("video.html5-main-video") ||
    document.querySelector("#movie_player video") ||
    document.querySelector("video");

  const startPlayback = async (reason = "retry") => {
    const video = getVideo();
    const player = getPlayer();
    if (!video || attempting) return;

    // Garante que o elemento de mídia não fique configurado para autoplay mudo.
    video.autoplay = true;
    video.setAttribute("autoplay", "");
    video.playsInline = true;
    video.muted = false;
    if (video.volume === 0) video.volume = 1;

    const playerState = (() => {
      try { return typeof player?.getPlayerState === "function" ? player.getPlayerState() : null; }
      catch (_) { return null; }
    })();

    if (!video.paused && !video.ended && playerState !== 2 && playerState !== 0) return;
    if (video.readyState < 2 && !video.ended) return;

    const now = Date.now();
    if (now - lastAttempt < 800) return;
    lastAttempt = now;
    attempting = true;

    try {
      if (video.ended || playerState === 0) {
        try { video.currentTime = 0; } catch (_) {}
        try { player?.seekTo?.(0, true); } catch (_) {}
      }

      // Usa primeiro a API do player do YouTube e depois a API HTMLMediaElement.
      try { player?.playVideo?.(); } catch (_) {}
      await video.play();
      console.info("[REMOTE AUTOPLAY] Reprodução iniciada/retomada:", reason);
    } catch (error) {
      console.debug("[REMOTE AUTOPLAY] Tentativa aguardando permissão do Chromium:", String(error));
    } finally {
      attempting = false;
    }
  };

  const schedulePlayback = (reason, delay = 250) => {
    window.setTimeout(() => startPlayback(reason), delay);
  };

  // Tenta no carregamento e repete enquanto a aba estiver aberta.
  schedulePlayback("page-load", 1200);
  window.setInterval(() => startPlayback("watchdog"), RETRY_MS);

  // Reage quando o YouTube cria/substitui o player ou carrega os dados do vídeo.
  ["yt-navigate-finish", "yt-page-data-updated"].forEach(eventName => {
    document.addEventListener(eventName, () => schedulePlayback(eventName, 700));
  });

  document.addEventListener("canplay", () => schedulePlayback("canplay", 100), true);
  document.addEventListener("loadeddata", () => schedulePlayback("loadeddata", 150), true);
  document.addEventListener("pause", event => {
    if (event.target instanceof HTMLVideoElement) schedulePlayback("pause-detected", 300);
  }, true);
  document.addEventListener("ended", event => {
    if (event.target instanceof HTMLVideoElement) schedulePlayback("video-ended", 300);
  }, true);

  // O requisito do usuário: recarregar a página para a música recomeçar do início.
  window.setInterval(() => window.location.reload(), RELOAD_MS);
  console.info("[REMOTE AUTOPLAY] Proteção ativa; atualização programada para 60 segundos.");
})();
