const VERSION = '__ASSET_VERSION__';
const CACHE = `campus-move-public-${VERSION}`;
const PATHS = ['/static/style.css', '/static/identity.css', '/static/discovery.css', '/static/app.js', '/static/buddies.js', '/static/campus.js', '/static/identity.js', '/static/discovery.js', '/static/notifications.js', '/static/vendor/leaflet/leaflet.js', '/static/vendor/leaflet/leaflet.css', '/static/offline.html', '/static/manifest.webmanifest', '/static/icon-192.png', '/static/icon-512.png'];
const PUBLIC = PATHS.map(path => `${path}?v=${VERSION}`);
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(PUBLIC)));
});
self.addEventListener('push', event => {
  event.waitUntil((async()=>{
    let data;try{data=event.data.json();}catch{return;}
    if(!data||!Number.isSafeInteger(data.user_id)||data.user_id<=0)return;
    if(data.notice_id){if(!Number.isSafeInteger(data.notice_id)||data.notice_id<=0)return;}
    else if(!Number.isSafeInteger(data.chat_id)||data.chat_id<=0||!Number.isSafeInteger(data.id)||data.id<=0)return;
    const query=new URLSearchParams({user_id:data.user_id});
    if(data.notice_id)query.set('notice_id',data.notice_id);
    else{query.set('chat_id',data.chat_id);query.set('message_id',data.id);}
    // Check the active account, read state and membership before showing anything.
    let result;try{const response=await fetch(`/api/push/check?${query}`,{cache:'no-store',credentials:'same-origin'});if(!response.ok)return;result=await response.json();}catch{return;}
    if(!result.show)return;
    await self.registration.showNotification(result.title||'循动 · 有新消息',{
      body:result.body||'轻点查看，与同伴确认运动安排。',icon:'/static/icon-192.png',
      tag:data.notice_id?`notice-${data.notice_id}`:`chat-${data.chat_id}`,data:{url:result.url||'/#messages'},
    });
    const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});
    for(const client of windows)client.postMessage({type:'campus-push'});
  })());
});
self.addEventListener('notificationclick',event=>{
  event.notification.close();event.waitUntil((async()=>{
    const path=event.notification.data?.url||'/#messages';
    let target;try{target=new URL(path,self.location.origin);}catch{return;}if(target.origin!==self.location.origin)return;
    const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});
    const client=windows.find(c=>new URL(c.url).origin===self.location.origin);
    if(client){await client.navigate(target.href);await client.focus();}else await self.clients.openWindow(target.href);
  })());
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('campus-move-public-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  // Never cache APIs, authenticated HTML or mutations.
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).catch(() => caches.match(`/static/offline.html?v=${VERSION}`)));
    return;
  }
  if (PATHS.includes(url.pathname)) {
    event.respondWith(fetch(event.request).then(response => {
      if (response.ok) {const copy = response.clone();event.waitUntil(caches.open(CACHE).then(cache => cache.put(event.request, copy)));}
      return response;
    }).catch(() => caches.match(event.request)));
  }
});
