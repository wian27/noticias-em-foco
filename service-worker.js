const CACHE_NAME='em-foco-pwa-v1';
const BASE_URL=new URL('./',self.location.href);
const SHELL=[
  BASE_URL.href,
  new URL('index.html',BASE_URL).href,
  new URL('article.html',BASE_URL).href,
  new URL('manifest.webmanifest',BASE_URL).href,
  new URL('icons/icon-192.svg',BASE_URL).href,
  new URL('icons/icon-512.svg',BASE_URL).href
];
self.addEventListener('install',event=>{
  event.waitUntil(caches.open(CACHE_NAME).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting()));
});
self.addEventListener('activate',event=>{
  event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE_NAME).map(key=>caches.delete(key)))).then(()=>self.clients.claim()));
});
self.addEventListener('fetch',event=>{
  const request=event.request;
  if(request.method!=='GET'||new URL(request.url).origin!==self.location.origin)return;
  event.respondWith(fetch(request).then(response=>{
    if(response&&response.ok)caches.open(CACHE_NAME).then(cache=>cache.put(request,response.clone()));
    return response;
  }).catch(async()=>{
    const cached=await caches.match(request);
    if(cached)return cached;
    if(request.mode==='navigate')return caches.match(new URL('index.html',BASE_URL).href);
    return Response.error();
  }));
});