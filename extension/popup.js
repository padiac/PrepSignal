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

  try {
    await chrome.runtime.sendMessage({ type: "ENSURE_RESUME" });
  } catch (_) {}
}

async function saveConfig() {
  const apiBase = document.getElementById("apiBase").value.trim();
  await chrome.storage.sync.set({ apiBase });
  document.getElementById("status").textContent = "Saved.";
}

async function clearCache() {
  await chrome.storage.local.remove(["sentPostIds", "scrapeQueue"]);
  document.getElementById("status").textContent = "Cache cleared (sentPostIds + scrapeQueue).";
}

async function refreshForumNow() {
  const tab = await chrome.tabs.create({ url: "https://www.1point3acres.com/bbs/forum-145-1.html", active: true });
  document.getElementById("status").textContent = "Opened forum-145. Keep tab visible ~10s for threads to load.";
}

async function resumeQueue() {
  try {
    await chrome.runtime.sendMessage({ type: "ENSURE_RESUME" });
    document.getElementById("status").textContent = "Resume check done. If queue has items, scrape scheduled.";
    loadConfig();
  } catch (e) {
    document.getElementById("status").textContent = "Error: " + (e.message || "failed");
  }
}

async function processNextNow() {
  try {
    const r = await chrome.runtime.sendMessage({ type: "TRIGGER_NEXT_SCRAPE" });
    await loadConfig();
    if (r?.triggered) {
      document.getElementById("status").textContent = `Opened next thread. ${r.queueAfter || 0} left in queue.`;
    } else if (r?.queueBefore !== undefined) {
      document.getElementById("status").textContent = r.queueBefore === 0
        ? "Queue is empty. Click Refresh Forum Now first."
        : `Queue had ${r.queueBefore} but failed to open. Try Resume Queue.`;
    } else {
      document.getElementById("status").textContent = "Queue is empty. Click Refresh Forum Now first.";
    }
  } catch (e) {
    document.getElementById("status").textContent = "Error: " + (e.message || "failed");
    loadConfig();
  }
}

async function enableBackfill() {
  await chrome.storage.local.set({ backfillMode: true });
  document.getElementById("status").textContent =
    "Backfill enabled. Open forum-145 (海外面经) now; all threads on the page will be re-queued to update metadata.";
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

document.getElementById("refreshForum").addEventListener("click", refreshForumNow);
document.getElementById("processNext").addEventListener("click", processNextNow);
document.getElementById("resumeQueue").addEventListener("click", resumeQueue);

document.getElementById("fastMode").addEventListener("change", async (e) => {
  await chrome.storage.local.set({ fastMode: e.target.checked });
  document.getElementById("status").textContent = e.target.checked ? "Fast mode ON" : "Fast mode OFF";
});

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById("save").addEventListener("click", saveConfig);
    document.getElementById("collect").addEventListener("click", collectCurrentTab);
    document.getElementById("backfill").addEventListener("click", enableBackfill);
    document.getElementById("clearCache").addEventListener("click", clearCache);
    loadConfig();
});
