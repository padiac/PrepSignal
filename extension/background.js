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

async function getQueue() {
  const result = await chrome.storage.local.get(["scrapeQueue"]);
  return result.scrapeQueue || [];
}

async function saveQueue(queueArray) {
  await chrome.storage.local.set({ scrapeQueue: queueArray });
}

function scheduleNextScrape(delayInMinutes) {
  let delay = delayInMinutes;

  if (typeof delay === "undefined") {
    // 💡 Human behavior simulation algorithm 💡
    const rand = Math.random();

    if (rand < 0.6) {
      // 60% chance: "Bursty reading session".
      // Just like a human opening a few tabs in a row and reading them.
      // Wait between 1 minute to 4 minutes.
      delay = Math.random() * 3 + 1;
    } else if (rand < 0.9) {
      // 30% chance: "Took a short break".
      // Wait between 15 minutes to 45 minutes.
      delay = Math.random() * 30 + 15;
    } else {
      // 10% chance: "Long break / Working session / Sleeping".
      // Wait between 60 minutes to 180 minutes (1 to 3 hours).
      delay = Math.random() * 120 + 60;
    }
  }

  chrome.alarms.create("scrapeTick", { delayInMinutes: delay });
  console.log(`Scheduled next scrape in ${delay.toFixed(2)} minutes.`);
}

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === "scrapeTick") {
    const queue = await getQueue();
    if (queue.length > 0) {
      const url = queue.shift();
      await saveQueue(queue);
      
      const targetUrl = new URL(url);
      targetUrl.searchParams.set("auto_scrape", "1");
      chrome.tabs.create({ url: targetUrl.toString(), active: false });

      if (queue.length > 0) {
        scheduleNextScrape();
      }
    }
  }
});


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

async function fetchThreadPostCounts(threadIds, apiBase) {
  if (threadIds.length === 0) return {};
  try {
    const resp = await fetch(`${apiBase}/threads/post_counts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ thread_ids: threadIds })
    });
    if (!resp.ok) return {};
    return await resp.json();
  } catch {
    return {};
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "QUEUE_THREADS") {
    (async () => {
      const queue = await getQueue();
      const { apiBase } = await getConfig();
      const threadInfos = message.payload;
      if (!Array.isArray(threadInfos) || threadInfos.length === 0) {
        sendResponse({ ok: true });
        return;
      }

      const threadIds = threadInfos.map((t) => t?.threadId).filter(Boolean);
      const dbCounts = await fetchThreadPostCounts(threadIds, apiBase);

      let added = 0;
      const queueUrls = new Set(queue);

      for (const info of threadInfos) {
        const url = info?.url;
        const threadId = info?.threadId;
        const listReplyCount = info?.listReplyCount;
        if (!url || !threadId || queueUrls.has(url)) continue;

        const dbCount = dbCounts[threadId] ?? 0;
        // listReplyCount = replies excluding OP; total posts = listReplyCount + 1
        const hasNewContent =
          listReplyCount == null ||
          dbCount === 0 ||
          listReplyCount + 1 > dbCount;

        if (hasNewContent) {
          queue.push(url);
          queueUrls.add(url);
          added += 1;
        }
      }

      if (added > 0) {
        await saveQueue(queue);
        const alarm = await chrome.alarms.get("scrapeTick");
        if (!alarm) {
          scheduleNextScrape(0.1);
        }
      }
      sendResponse({ ok: true, added });
    })();
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
