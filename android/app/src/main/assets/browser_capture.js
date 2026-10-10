(function () {
  if (window.__shiyingCapture) return;
  window.__shiyingCapture = true;
  window.__shiyingPayloads = [];
  const allowed = (raw) => {
    try {
      const u = new URL(raw, location.href);
      const host = (domain) => u.hostname === domain || u.hostname.endsWith('.' + domain);
      return ((host('douyin.com') || host('iesdouyin.com')) && /\/aweme\/.*(?:detail|item)/.test(u.pathname)) ||
        (host('bilibili.com') && /\/(?:playurl|view|detail)(?:\/|$)/.test(u.pathname)) ||
        ((host('kuaishou.com') || host('gifshow.com') || host('kwai.com') || host('chenzhongtech.com')) && /graphql|photo|detail/.test(u.pathname)) ||
        ((host('channels.weixin.qq.com') || host('finder.video.qq.com')) && /feed|object|detail|interaction/.test(u.pathname));
    } catch (e) { return false; }
  };
  const keep = (url, body) => {
    try {
      if (!allowed(url) || typeof body !== 'string' || body.length > 2000000) return;
      window.__shiyingPayloads.push({ requestUrl: url, response: JSON.parse(body) });
      if (window.__shiyingPayloads.length > 12) window.__shiyingPayloads.shift();
    } catch (e) { }
  };
  const nativeFetch = window.fetch;
  if (nativeFetch) window.fetch = function () {
    return nativeFetch.apply(this, arguments).then(r => {
      try { if (allowed(r.url) && (r.headers.get('content-type') || '').includes('json')) r.clone().text().then(t => keep(r.url, t)).catch(() => { }); } catch (e) { }
      return r;
    });
  };
  const nativeOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function () {
    this.addEventListener('load', () => {
      try { keep(this.responseURL, this.responseType === 'json' ? JSON.stringify(this.response) : this.responseText); } catch (e) { }
    });
    return nativeOpen.apply(this, arguments);
  };
  // Re-read a small number of request URLs already produced by this page, with its normal session.
  let replay = 0;
  for (const entry of performance.getEntriesByType('resource')) {
    if (nativeFetch && replay < 4 && allowed(entry.name) && !entry.name.includes('graphql') && !entry.name.includes('/get_feed_info')) {
      replay++;
      nativeFetch(entry.name, { credentials: 'include' }).then(r => r.text().then(t => keep(r.url, t))).catch(() => { });
    }
  }
})();
