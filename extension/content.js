function extractPosts() {
  const posts = [];
  const url = location.href;

  if (url.includes('forum-145')) {
    const threads = document.querySelectorAll('tbody[id^="normalthread_"]');
    const threadUrls = [];
    for (const row of threads) {
      // We no longer limit to 5! We collect all unvisited threads on this page to build out our backlog queue.
      const link = row.querySelector('a.s.xst');
      if (link && link.href) {
        threadUrls.push(link.href);
      }
    }
    
    if (threadUrls.length > 0) {
      chrome.runtime.sendMessage({
        type: "QUEUE_THREADS",
        payload: threadUrls
      });
      console.log("Sent QUEUE_THREADS message to background for urls:", threadUrls);
    }
    return []; // We handle extraction inside the thread page now, no need to ingest list items
  } 
  else if (url.includes('thread-')) {
    // Extract the main thread ID from the URL, e.g. thread-1168182-1-1.html -> 1168182
    const threadIdMatch = url.match(/thread-(\d+)/);
    const threadId = threadIdMatch ? threadIdMatch[1] : null;

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
        source_url: url.split('?')[0].split('&')[0], // clean tracking params
        content: content,
        created_at: date
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

// Add a slight random delay (3 to 6 seconds) for thread pages to ensure the content fully loads and simulates human reading
if (location.href.includes('thread-') && location.href.includes('auto_scrape=1')) {
  const readDelay = Math.floor(Math.random() * 3000) + 3000;
  setTimeout(sendPostsToBackground, readDelay);
} else {
  sendPostsToBackground();
}

chrome.runtime.onMessage.addListener((message) => {
  if (message.type === "MANUAL_COLLECT") {
    sendPostsToBackground();
  }
});
