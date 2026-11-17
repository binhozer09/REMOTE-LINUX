// Recupera automaticamente a reprodução do YouTube e atualiza cada aba a cada 60s.
(() => {
  if (window.__remotePlaybackGuardInstalled) return;
  window.__remotePlaybackGuardInstalled = true;

  const host = location.hostname.toLowerCase();
  const isYouTube =
    host === 'youtube.com' ||
    host.endsWith('.youtube.com') ||
    host === 'youtube-nocookie.com' ||
    host.endsWith('.youtube-nocookie.com') ||
    host === 'youtu.be';

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
      // Pode ser bloqueio de autoplay do próprio navegador/YouTube.
      console.debug('[Remote YouTube Autoplay] Reprodução não autorizada:', error);
    } finally {
      playAttemptInProgress = false;
    }
  };

  // Verifica pausas e player carregado depois da navegação interna do YouTube.
  window.setInterval(tryPlay, 2000);
  document.addEventListener('yt-navigate-finish', () => {
    window.setTimeout(tryPlay, 1000);
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', tryPlay, { once: true });
  } else {
    window.setTimeout(tryPlay, 1000);
  }

  // Mantém o comportamento solicitado: recarrega esta aba a cada minuto.
  window.setInterval(() => window.location.reload(), 60000);
})();