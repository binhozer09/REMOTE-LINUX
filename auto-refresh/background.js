const YOUTUBE_URL = "https://youtu.be/bWO1FNUTIao?is=IHQ1W9LWAd36Sf23";
const ALARM_NAME = "remote-youtube-recovery";

function isYouTubeUrl(url = "") {
  try {
    const host = new URL(url).hostname.toLowerCase();
    return host === "youtube.com" ||
      host.endsWith(".youtube.com") ||
      host === "youtu.be" ||
      host === "youtube-nocookie.com" ||
      host.endsWith(".youtube-nocookie.com");
  } catch (_) {
    return false;
  }
}

function isBrowserErrorOrBlank(url = "") {
  return url.startsWith("chrome-error://") ||
    url.startsWith("chrome://network-error") ||
    url.startsWith("chrome://newtab") ||
    url === "about:blank" ||
    url === "data:,";
}

function scheduleRecovery() {
  chrome.alarms.create(ALARM_NAME, {
    delayInMinutes: 1,
    periodInMinutes: 1
  });
}

chrome.runtime.onInstalled.addListener(scheduleRecovery);
chrome.runtime.onStartup.addListener(scheduleRecovery);
scheduleRecovery();

async function recoverYouTubeTab() {
  const tabs = await chrome.tabs.query({});

  if (!tabs.length) {
    await chrome.tabs.create({ url: YOUTUBE_URL, active: true });
    console.info("[REMOTE WATCHDOG] Nenhuma aba encontrada; YouTube aberto novamente.");
    return;
  }

  const youtubeTab = tabs.find(tab => isYouTubeUrl(tab.url));
  if (youtubeTab && youtubeTab.id !== undefined) {
    await chrome.tabs.reload(youtubeTab.id, { bypassCache: true });
    console.info("[REMOTE WATCHDOG] Aba do YouTube atualizada pelo alarme de 60 segundos.");
    return;
  }

  const errorTab = tabs.find(tab => isBrowserErrorOrBlank(tab.url));
  if (errorTab && errorTab.id !== undefined) {
    await chrome.tabs.update(errorTab.id, { url: YOUTUBE_URL, active: true });
    console.info("[REMOTE WATCHDOG] Tela de erro/aba vazia detectada; YouTube restaurado.");
    return;
  }

  console.info("[REMOTE WATCHDOG] Nenhuma aba do YouTube ou tela interna de erro encontrada; nenhuma aba foi alterada.");
}

chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name !== ALARM_NAME) return;
  recoverYouTubeTab().catch(error => {
    console.error("[REMOTE WATCHDOG] Falha ao recuperar a aba:", String(error));
  });
});