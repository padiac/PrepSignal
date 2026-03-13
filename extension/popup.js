async function loadConfig() {
  const [sync, local] = await Promise.all([
    chrome.storage.sync.get(["apiBase"]),
    chrome.storage.local.get(["fastMode", "scrapeQueue", "sentPostIds"])
  ]);
  document.getElementById("apiBase").value = sync.apiBase || "http://localhost:8000";
  document.getElementById("fastMode").checked = !!local.fastMode;

  const q = local.scrapeQueue || [];
  const sent = local.sentPostIds || [];
  document.getElementById("queueStatus").textContent =
    `Queue: ${q.length} threads | Sent: ${sent.length} posts`;

  const apiBase = (sync.apiBase || "http://localhost:8000").trim().replace(/\/$/, "");
  try {
    const r = await fetch(`${apiBase}/`, { method: "GET" });
    document.getElementById("apiStatus").textContent =
      r.ok ? `API: OK (${apiBase})` : `API: ${r.status}`;
  } catch (e) {
    document.getElementById("apiStatus").textContent = `API: unreachable (${apiBase})`;
  }

}

async function saveConfig() {
  const apiBase = document.getElementById("apiBase").value.trim();
  await chrome.storage.sync.set({ apiBase });
  document.getElementById("status").textContent = "Saved.";
}

async function collectCurrentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab) {
    try {
      await chrome.tabs.sendMessage(tab.id, { type: "MANUAL_COLLECT" });
      document.getElementById("status").textContent =
        "Triggered collection on current tab.";
    } catch (e) {
      document.getElementById("status").textContent = 
        "Error: Could not trigger collection. Make sure you are on a supported page and the page is fully loaded.";
    }
  }
}

document.getElementById("fastMode").addEventListener("change", async (e) => {
  const checked = e.target.checked;
  await chrome.storage.local.set({ fastMode: checked });
  try {
    const r = await chrome.runtime.sendMessage({ type: "KICKSTART" });
    document.getElementById("status").textContent =
      checked ? `Fast mode ON — queue: ${r?.queueSize ?? '?'}` : `Normal mode — started`;
    setTimeout(loadConfig, 2000);
  } catch (err) {
    document.getElementById("status").textContent = "Error: " + (err.message || "failed");
  }
});

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById("save").addEventListener("click", saveConfig);
  document.getElementById("collect").addEventListener("click", collectCurrentTab);
  loadConfig();
});
