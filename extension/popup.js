async function loadConfig() {
  const result = await chrome.storage.sync.get(["apiBase"]);
  document.getElementById("apiBase").value =
    result.apiBase || "http://localhost:8000";
}

async function saveConfig() {
  const apiBase = document.getElementById("apiBase").value.trim();
  await chrome.storage.sync.set({ apiBase });
  document.getElementById("status").textContent = "Saved.";
}

async function clearCache() {
  await chrome.storage.local.remove(["sentPostIds"]);
  document.getElementById("status").textContent = "Cache cleared successfully.";
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

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById("save").addEventListener("click", saveConfig);
    document.getElementById("collect").addEventListener("click", collectCurrentTab);
    document.getElementById("clearCache").addEventListener("click", clearCache);
    loadConfig();
});
