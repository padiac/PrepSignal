const DEFAULT_API_BASE = "http://localhost:8000";

async function getConfig() {
  const result = await chrome.storage.sync.get(["apiBase"]);
  return {
    apiBase: result.apiBase || DEFAULT_API_BASE
  };
}

async function getSentIds() {
  const result = await chrome.storage.local.get(["sentPostIds"]);
  return new Set(result.sentPostIds || []);
}

async function saveSentIds(setObj) {
  await chrome.storage.local.set({
    sentPostIds: Array.from(setObj)
  });
}

async function postToApi(post, apiBase) {
  const resp = await fetch(`${apiBase}/posts`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(post)
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`API error ${resp.status}: ${text}`);
  }

  return resp.json();
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "OPEN_THREADS") {
    (async () => {
      for (let i = 0; i < message.payload.length; i++) {
        const url = message.payload[i];
        const targetUrl = new URL(url);
        targetUrl.searchParams.set("auto_scrape", "1");
        chrome.tabs.create({ url: targetUrl.toString(), active: false });
        // wait a random amount of time (3 to 7 seconds) before opening the next tab
        const randomDelay = Math.floor(Math.random() * 4000) + 3000;
        await new Promise(r => setTimeout(r, randomDelay));
      }
    })();
    sendResponse({ ok: true });
    return true;
  }

  if (message.type === "CLOSE_TABS") {
    if (sender.tab && sender.tab.id) {
      // Small delay to ensure the background script finishes ingesting
      setTimeout(() => {
        chrome.tabs.remove(sender.tab.id);
      }, 1000);
    }
    sendResponse({ ok: true });
    return true;
  }

  if (message.type !== "COLLECT_POSTS") return;

  (async () => {
    const { apiBase } = await getConfig();
    const sentIds = await getSentIds();

    let inserted = 0;
    let skipped = 0;
    let failed = 0;

    for (const post of message.payload) {
      const dedupeKey = `${post.source_site}:${post.source_post_id}`;
      if (sentIds.has(dedupeKey)) {
        skipped += 1;
        continue;
      }

      try {
        await postToApi(post, apiBase);
        sentIds.add(dedupeKey);
        inserted += 1;
      } catch (err) {
        console.error("Failed to send post:", err);
        failed += 1;
      }
    }

    await saveSentIds(sentIds);

    sendResponse({ ok: true, inserted, skipped, failed });
  })();

  return true;
});
