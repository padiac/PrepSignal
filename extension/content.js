function extractPosts() {
  const posts = [];
  const url = location.href;

  if (url.includes('forum-145')) {
    const threads = document.querySelectorAll('tbody[id^="normalthread_"]');
    const threadUrls = [];
    for (const row of threads) {
      if (threadUrls.length >= 5) break; // Limit auto-opening to 5 threads
      const link = row.querySelector('a.s.xst');
      if (link && link.href) {
        threadUrls.push(link.href);
      }
    }
    
    if (threadUrls.length > 0) {
      chrome.runtime.sendMessage({
        type: "OPEN_THREADS",
        payload: threadUrls
      });
      console.log("Sent OPEN_THREADS message to background for urls:", threadUrls);
    }
    return []; // We handle extraction inside the thread page now, no need to ingest list items
  } 
  else if (url.includes('thread-')) {
    const postNodes = document.querySelectorAll('div[id^="post_"]');
    for (const post of postNodes) {
      if (posts.length >= 5) break; 
      
      const contentNode = post.querySelector('td.t_f');
      const dateNode = post.querySelector('em[id^="authorposton"]');
      const id = post.id.replace('post_', '');

      let content = contentNode ? contentNode.innerText.trim() : "";
      const date = dateNode ? dateNode.innerText.replace("发表于 ", "").trim() : null;

      if (!id || !content) continue;

      posts.push({
        source_site: "1point3acres",
        source_post_id: id,
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

  // If this was an automated tab opened by our extension, immediately close it
  if (location.href.includes('auto_scrape=1')) {
    chrome.runtime.sendMessage({ type: "CLOSE_TABS" });
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
