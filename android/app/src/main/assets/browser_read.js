(function () {
  const out = { page: location.href, title: document.title, ua: navigator.userAgent, payloads: [] };
  const add = value => { try { if (value) { const json = typeof value === 'string' ? value : JSON.stringify(value); if (json.length <= 2000000) out.payloads.push(json); } } catch (e) { } };
  for (const value of [window._ROUTER_DATA, window._SSR_DATA, window.__INITIAL_STATE__, window.__INITIAL_SSR_STATE__, window.__APOLLO_STATE__, window.INIT_STATE, window.__INITIAL_DATA__, window.__NEXT_DATA__]) add(value);
  for (const script of document.querySelectorAll('script')) if (/RENDER_DATA|__NEXT_DATA__|SIGI_STATE/.test(script.id) || script.type === 'application/json') add(script.textContent);
  for (const value of (window.__shiyingPayloads || [])) add(value);
  if (location.hostname === 'channels.weixin.qq.com' && location.pathname === '/finder-preview/pages/sph') {
    let feed = null;
    const app = document.querySelector('#app');
    const vue = app && app.__vue_app__;
    const pinia = vue && vue.config && vue.config.globalProperties.$pinia;
    const store = pinia && pinia.state && pinia.state.value && pinia.state.value.feed;
    if (store && store.feed) { feed = store.feed; add({ previewPage: location.href, feedInfo: feed, authorInfo: store.finderAcct }); }
    for (const item of (window.__shiyingPayloads || [])) {
      const response = item.response;
      if (item.requestUrl.includes('/finder-preview/api/feed/get_feed_info') && response && response.errCode === 0 && response.data) feed = response.data.feedInfo;
    }
    if (feed && !(feed.picInfo && feed.picInfo.length) && !feed.videoUrl && !(feed.h264VideoInfo && feed.h264VideoInfo.videoUrl) && !(feed.h265VideoInfo && feed.h265VideoInfo.videoUrl))
      out.platformMessage = '这个视频号分享网页只提供封面和介绍，没有提供可下载的视频地址。需要在微信中观看；当前无法从此链接保存视频。';
    else if (!feed && !document.querySelector('video') && /可(?:扫码)?前往微信观看此内容/.test(document.body.textContent))
      out.platformMessage = '这个视频号分享网页只提供封面和介绍，没有提供可下载的视频地址。需要在微信中观看；当前无法从此链接保存视频。';
  }
  if (location.hostname === 'bilibili.com' || location.hostname.endsWith('.bilibili.com')) {
    if (/\/read\/cv\d+/.test(location.pathname)) { const article = document.querySelector('.article-holder'); if (article) add({ articleHtml: article.outerHTML.slice(0, 2000000), articleTitle: document.title }); }
    let metadata = window.__INITIAL_STATE__;
    if (!metadata) for (const item of (window.__shiyingPayloads || [])) if (item.response && item.response.data && item.response.data.bvid && item.response.data.title) metadata = item.response.data;
    if (metadata) {
      if (window.__playinfo__) add({ biliPage: location.href, metadata, playInfo: window.__playinfo__ });
      for (const item of (window.__shiyingPayloads || [])) if (item.requestUrl.includes('/playurl')) add({ biliPage: location.href, metadata, playInfo: item.response, requestUrl: item.requestUrl });
    }
  }
  const videos = [...document.querySelectorAll('video')].filter(v => v.getBoundingClientRect().width > 0);
  videos.sort((a, b) => b.getBoundingClientRect().width * b.getBoundingClientRect().height - a.getBoundingClientRect().width * a.getBoundingClientRect().height);
  const video = videos[0];
  if (video) Object.assign(out, { url: video.currentSrc || video.src, width: video.videoWidth, height: video.videoHeight, duration: Number.isFinite(video.duration) ? video.duration : 0, poster: video.poster });
  // Some clients keep the active post in component props instead of a global JSON object.
  // Read only media-shaped objects from the visible player, never account/login form state.
  if (video) {
    let element = video;
    const seen = new WeakSet();
    for (let level = 0; element && level < 5; level++, element = element.parentElement) {
      const key = Object.keys(element).find(k => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$'));
      let fiber = key && element[key];
      for (let parent = 0; fiber && parent < 4; parent++, fiber = fiber.return) {
        const queue = [fiber.memoizedProps]; let visited = 0;
        while (queue.length && visited++ < 1500) {
          const item = queue.shift();
          if (!item || typeof item !== 'object' || seen.has(item)) continue;
          seen.add(item);
          if ((item.objectDesc && Array.isArray(item.objectDesc.media)) ||
            ((item.photoId || item.photo_id) && (item.playUrl || item.videoResource || item.atlas)) ||
            (item.aweme_id && (item.video || item.images)) || (item.noteId && (item.imageList || item.video))) { add(item); continue; }
          for (const name of Object.keys(item)) {
            if (['_owner', 'return', 'alternate', 'stateNode', 'auth', 'account', 'login'].includes(name)) continue;
            const child = item[name]; if (child && typeof child === 'object' && !(child instanceof Node)) queue.push(child);
          }
        }
      }
    }
  }
  return JSON.stringify(out);
})();
