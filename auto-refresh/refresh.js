// Mantém cada aba do YouTube reproduzindo: se o vídeo pausar ou terminar,
// tenta iniciar novamente. Também recarrega a aba a cada 60 segundos.
(() => {
  if (window.__remotePlaybackGuardInstalled) return;
  window.__remotePlaybackGuardInstalled = true;

  const isYouTube = /(^|\\.)youtube\\.com$|(^|\\.)youtube-nocookie\\.com$/.test(location.hostname);
  if (!isYouTube) return;

  let playAttemptInProgress = false;

  const findVideo = () =>
    document.querySelector('video.html5-main-video') ||
    document.querySelector('video');

  const tryPlay = async () => {
    const video = findVideo();
    if (!video || (!video.paused && !video.ended)) return;
    if (playAttemptInProgress) return;
    if (video.readyState < 2 && !video.ended) return;

    playAttemptInProgress = true;
    try {
      if (video.ended) video.currentTime = 0;
      await video.play();
    } catch (error) {
      console.debug('[Remote YouTube Autoplay] Reprodução bloqueada:', error);
    } finally {
      playAttemptInProgress = false;
    }
  };

  // Detecta pausas e também navegação interna do YouTube.
  window.setInterval(tryPlay, 2000);
  document.addEventListener('yt-navigate-finish', () => {
    window.setTimeout(tryPlay, 1000);
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', tryPlay, { once: true });
  } else {
    window.setTimeout(tryPlay, 1000);
  }

  // Cada aba recarrega a página automaticamente a cada 60 segundos.
  window.setInterval(() => window.location.reload(), 60000);
})();