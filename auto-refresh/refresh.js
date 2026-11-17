// Atualiza a aba atual a cada 60 segundos.
(() => {
  if (window.__remoteAutoRefreshInstalled) return;
  window.__remoteAutoRefreshInstalled = true;
  window.setInterval(() => {
    window.location.reload();
  }, 60000);
})();