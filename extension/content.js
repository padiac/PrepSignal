function extractPosts() {
  const posts = [];
  const url = location.href;

  if (url.includes('forum-145')) {
    const threads = document.querySelectorAll('tbody[id^="normalthread_"]');
    const threadInfos = [];
    for (const row of threads) {
      const link = row.querySelector('a.s.xst');
      if (!link?.href) continue;

      const threadIdMatch = link.href.match(/thread-(\d+)/);
      const threadId = threadIdMatch ? threadIdMatch[1] : null;
      if (!threadId) continue;

      let listReplyCount = null;
      const numCell = row.querySelector('td.num');
      if (numCell) {
        const n = parseInt(numCell.textContent.trim(), 10);
        if (!isNaN(n) && n >= 0) listReplyCount = n;
      }

      threadInfos.push({ url: link.href, threadId, listReplyCount });
    }

    if (threadInfos.length > 0) {
      chrome.runtime.sendMessage({ type: "QUEUE_THREADS", payload: threadInfos });
      console.log("Sent QUEUE_THREADS:", threadInfos.length, "threads");
    } else if (!window.__forumRetried) {
      window.__forumRetried = true;
      setTimeout(() => sendPostsToBackground(), 3000);
    }
    return []; // We handle extraction inside the thread page now, no need to ingest list items
  } 
  else if (url.includes('thread-')) {
    const threadIdMatch = url.match(/thread-(\d+)/);
    const threadId = threadIdMatch ? threadIdMatch[1] : null;

    // Thread title, company, job, metadata: from DOM first, fallback to page <title>/<meta>
    // title format: "SIG Phone + Onsite|sig面经|一亩三分地海外面经版"; meta keywords: "海外面经,sig"
    let threadTitle = null;
    let company = null;
    let jobTitle = null;
    let threadMetadata = null;
    const titleEl = document.getElementById('thread_subject');
    if (titleEl) threadTitle = titleEl.textContent.trim();
    const companyEl = document.querySelector('table.plhin font[color="#FF6600"], table.plhin font[color="#ff6600"]');
    const jobEl = document.querySelector('table.plhin font[color="green"]');
    if (companyEl) company = companyEl.textContent.trim();
    if (jobEl) jobTitle = jobEl.textContent.trim();
    const uTag = companyEl?.closest('u');
    if (uTag) threadMetadata = uTag.innerText.trim();
    // Fallback: parse from <title> "ThreadTitle|company面经|..." and meta keywords
    if (!threadTitle || !company) {
      const parts = document.title.split('|');
      if (parts.length >= 1 && !threadTitle) threadTitle = parts[0].trim();
      if (parts.length >= 2 && !company) company = parts[1].replace(/面经$/, '').trim();
      if (!company) {
        const kw = document.querySelector('meta[name="keywords"]')?.getAttribute('content');
        if (kw) company = kw.split(',')[1]?.trim() || null;
      }
    }

    const postNodes = document.querySelectorAll('div[id^="post_"]');
    for (const post of postNodes) {
      // Removed the 5 post limit here so we grab all replies on the current page
      
      const contentNode = post.querySelector('td.t_f');
      const dateNode = post.querySelector('em[id^="authorposton"]');
      const id = post.id.replace('post_', '');

      let content = contentNode ? contentNode.innerText.trim() : "";
      const date = dateNode ? dateNode.innerText.replace("发表于 ", "").trim() : null;

      if (!id || !content) continue;

      posts.push({
        source_site: "1point3acres",
        source_post_id: id,
        source_thread_id: threadId,
        source_url: url.split('?')[0].split('&')[0],
        content: content,
        created_at: date,
        company: company,
        job_title: jobTitle,
        thread_title: threadTitle,
        thread_metadata: threadMetadata
      });
    }
  }

  return posts;
}

async function sendPostsToBackground() {
  const posts = extractPosts();
  if (posts.length > 0) {
    const response = await chrome.runtime.sendMessage({
      type: "COLLECT_POSTS",
      payload: posts
    });
    console.log("collector result:", response);
  }

  // If this was an automated tab opened by our extension, handle closing or pagination
  if (location.href.includes('auto_scrape=1')) {
    // Look for the "Next Page" button inside the thread
    const nextBtn = document.querySelector('a.nxt');
    
    if (nextBtn && nextBtn.href) {
      console.log("Found next page, navigating to:", nextBtn.href);
      // Append our tracking parameter so the next page also triggers the auto scrape delay
      const nextUrl = new URL(nextBtn.href);
      nextUrl.searchParams.set("auto_scrape", "1");
      
      // Simulate human reading time (5 to 12 seconds) before clicking next page
      const paginationDelay = Math.floor(Math.random() * 7000) + 5000;
      console.log(`Waiting ${paginationDelay}ms before going to next page...`);
      setTimeout(() => {
        window.location.href = nextUrl.toString();
      }, paginationDelay);
    } else {
      console.log("No next page found or reached the end. Closing tab.");
      // We reached the last page of the thread, so we close it
      chrome.runtime.sendMessage({ type: "CLOSE_TABS" });
    }
  }
}

(async () => {
  if (location.href.includes('thread-') && location.href.includes('auto_scrape=1')) {
    const { fastMode } = await chrome.storage.local.get(["fastMode"]);
    const readDelay = fastMode ? 2000 : Math.floor(Math.random() * 7000) + 8000;
    setTimeout(sendPostsToBackground, readDelay);
  } else {
    sendPostsToBackground();
  }
})();

chrome.runtime.onMessage.addListener((message) => {
  if (message.type === "MANUAL_COLLECT") {
    sendPostsToBackground();
  }
});
