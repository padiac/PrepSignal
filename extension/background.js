const DEFAULT_API_BASE = "http://localhost:8000";
const FORUM_145_URL = "https://www.1point3acres.com/bbs/forum-145-1.html";

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

async function scheduleNextScrape(delayInMinutes) {
  let delay = delayInMinutes;
  const { fastMode } = await chrome.storage.local.get(["fastMode"]);

  if (fastMode) {
    delay = 0.5;  // Chrome MV3 minimum is 30 sec
  } else if (typeof delay === "undefined") {
    const rand = Math.random();
    if (rand < 0.50) {
      delay = Math.random() * 2 + 1;        // 50% peak: 1–3 min
    } else if (rand < 0.80) {
      delay = Math.random() * 30 + 20;     // 30% mid: 20–50 min
    } else if (rand < 0.95) {
      delay = Math.random() * 180 + 120;   // 15% long: 2–5 h
    } else {
      delay = Math.random() * 360 + 360;    // 5% very long: 6–12 h
    }
  }

  chrome.alarms.create("scrapeTick", { delayInMinutes: delay });
  console.log(`Scheduled next scrape in ${delay.toFixed(2)} minutes.`);
}

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === "scrapeTick") {
    await processNextInQueue();
  } else if (alarm.name === "forumRefresh") {
    try {
      const tab = await chrome.tabs.create({ url: FORUM_145_URL, active: false });
      setTimeout(() => {
        if (tab?.id) chrome.tabs.remove(tab.id).catch(() => {});
      }, 45000);
    } catch (_) {}
    const { fastMode } = await chrome.storage.local.get(["fastMode"]);
    const forumDelay = fastMode ? 0.5 : Math.random() * 120 + 240;  // 30 sec vs 4–6 hr
    chrome.alarms.create("forumRefresh", { delayInMinutes: forumDelay });
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

async function processNextInQueue() {
  const queue = await getQueue();
  if (queue.length === 0) return false;
  const url = queue.shift();
  await saveQueue(queue);
  const targetUrl = new URL(url);
  targetUrl.searchParams.set("auto_scrape", "1");
  try {
    await chrome.tabs.create({ url: targetUrl.toString(), active: false });
  } catch (e) {
    queue.unshift(url);
    await saveQueue(queue);
    if (queue.length > 0) await scheduleNextScrape();
    return false;
  }
  if (queue.length > 0) {
    await scheduleNextScrape();
  }
  return true;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "KICKSTART") {
    (async () => {
      try {
        const queue = await getQueue();
        if (queue.length > 0) {
          await processNextInQueue();
        }
        await chrome.tabs.create({ url: FORUM_145_URL, active: false });
        chrome.alarms.clear("forumRefresh");
        const { fastMode } = await chrome.storage.local.get(["fastMode"]);
        const forumDelay = fastMode ? 0.5 : Math.random() * 120 + 240;
        chrome.alarms.create("forumRefresh", { delayInMinutes: forumDelay });
        sendResponse({ ok: true, queueSize: queue.length });
      } catch (e) {
        sendResponse({ ok: false, error: e.message });
      }
    })();
    return true;
  }

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

      const { fastMode } = await chrome.storage.local.get(["fastMode"]);
      for (const info of threadInfos) {
        const url = info?.url;
        const threadId = info?.threadId;
        const listReplyCount = info?.listReplyCount;
        if (!url || !threadId || queueUrls.has(url)) continue;

        const dbCount = dbCounts[threadId] ?? 0;
        let hasNewContent =
          listReplyCount == null ||
          dbCount === 0 ||
          listReplyCount + 1 > dbCount;
        if (fastMode && added < 5) {
          hasNewContent = true;
        }

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
          scheduleNextScrape(fastMode ? 0.5 : 5 + Math.random() * 10);
        }
      }
      sendResponse({ ok: true, added });
    })();
    return true;
  }

  if (message.type === "CLOSE_TABS") {
    if (sender.tab && sender.tab.id) {
      const tabId = sender.tab.id;
      setTimeout(() => {
        chrome.tabs.remove(tabId).catch(() => {});
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
      const alreadySent = sentIds.has(dedupeKey);
      try {
        await postToApi(post, apiBase);
        sentIds.add(dedupeKey);
        if (alreadySent) skipped += 1; else inserted += 1;
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

async function ensureForumRefreshAlarm() {
  const alarm = await chrome.alarms.get("forumRefresh");
  if (!alarm) {
    const { fastMode } = await chrome.storage.local.get(["fastMode"]);
    const delay = fastMode ? 0.5 : Math.random() * 60 + 60;  // 30 sec vs 1–2 hr
    chrome.alarms.create("forumRefresh", { delayInMinutes: delay });
  }
}

async function maybeResumeQueue() {
  const queue = await getQueue();
  if (queue.length === 0) return;
  const alarm = await chrome.alarms.get("scrapeTick");
  if (alarm) return;
  await processNextInQueue();
}

chrome.runtime.onStartup.addListener(() => {
  maybeResumeQueue();
  ensureForumRefreshAlarm();
});

maybeResumeQueue();
ensureForumRefreshAlarm();
