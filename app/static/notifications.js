const notifications={cursor:null,noticeCursor:null,checking:false,enabled:false,route:'messages',count:0,privateCount:0};
function resetNotifications(){Object.assign(notifications,{cursor:null,noticeCursor:null,checking:false,enabled:false,count:0,privateCount:0});$('messageBanner').classList.add('hidden');document.title='循动 · 找到搭子，让运动成为日常';if('serviceWorker' in navigator)navigator.serviceWorker.getRegistration().then(r=>r?.getNotifications()).then(rows=>rows?.forEach(n=>n.close())).catch(()=>{});}
function showMessageBanner(title,body,route){if(!state.user||document.hidden)return;notifications.route=route;$('messageBannerTitle').textContent=title;$('messageBannerBody').textContent=body;$('messageBanner').classList.remove('hidden');}
function renderUnread(){const count=notifications.privateCount+notifications.count;for(const id of ['buddyUnread','buddyTabUnread']){$(id).textContent=count>99?'99+':String(count);$(id).classList.toggle('hidden',!count);$(id).setAttribute('aria-label',`${count} 条未读消息与通知`);}document.title=count?`(${count}) 循动 · 有新消息`:'循动 · 找到搭子，让运动成为日常';}
async function checkNotifications(){
  if(notifications.checking||!state.user)return;notifications.checking=true;const epoch=state.epoch;
  try{const [incoming,notices]=await Promise.all([api(`/api/buddy-notifications${notifications.cursor==null?'':`?after=${notifications.cursor}`}`),api('/api/notices')]);if(epoch!==state.epoch)return;
    const fresh=incoming.items.filter(n=>!(buddy.active&&buddy.tab==='messages'&&buddy.chatId===n.chat_id));
    if(notifications.cursor!=null&&fresh.length){const n=fresh.at(-1);showMessageBanner(`${n.username} 发来新消息`,'轻点进入聊天',`messages/${n.chat_id}`);}
    notifications.cursor=incoming.cursor;
    const newNotices=notices.items.filter(n=>!n.is_read&&n.id>(notifications.noticeCursor??Infinity));
    if(newNotices.length){const n=newNotices[0];if(!(campus.meeting?.id===n.meetup_id&&buddy.tab==='group'))showMessageBanner(n.title,n.body,n.meetup_id?`buddies/group/${n.meetup_id}`:'profile');}
    notifications.noticeCursor=Math.max(notifications.noticeCursor||0,...notices.items.map(n=>n.id));notifications.count=notices.count;
    $('noticeCount').textContent=String(notices.count);$('noticeList').innerHTML=notices.items.map(n=>`<button type="button" class="notice-item ${n.is_read?'read':''}" data-notice="${n.id}" data-meeting="${n.meetup_id||''}"><strong>${escapeHTML(n.title)}</strong><span>${escapeHTML(n.body)}</span><small>${escapeHTML(buddyTime(n.created_at))}</small></button>`).join('')||'<p class="fine">邀请、改约和赴约提醒会出现在这里。</p>';renderUnread();
  }finally{if(epoch===state.epoch)notifications.checking=false;}
}
function pushSupported(){return window.isSecureContext&&'Notification' in window&&'serviceWorker' in navigator&&'PushManager' in window;}
function updatePushStatus(message){
  let text=message||'站内提示已开启。开启系统通知后，离开页面也能收到提醒。';
  if(!pushSupported())text='当前浏览器不支持系统推送。iPhone 请用 Safari 添加到主屏幕后打开；其他手机可尝试支持推送的浏览器。';
  else if(Notification.permission==='denied')text='通知权限已被关闭。请在浏览器或手机的网站设置中允许通知，再回来开启。';
  else if(notifications.enabled&&!message)text='本设备系统通知已开启。退出账号或登录过期后停止推送。';
  $('pushStatus').textContent=text;$('pushToggle').textContent=notifications.enabled?'关闭通知':'开启通知';
}
function applicationKey(text){const binary=atob(text.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-text.length%4)%4));return Uint8Array.from(binary,c=>c.charCodeAt(0));}
async function pushRegistration(){return await Promise.race([navigator.serviceWorker.ready,new Promise((_,reject)=>setTimeout(()=>reject(new Error('通知服务尚未就绪，请刷新后重试。')),12000))]);}
async function syncPush(){
  if(!pushSupported())return;const epoch=state.epoch;
  let opted=false;try{opted=localStorage.getItem('campus-push-enabled')==='yes';}catch{}
  if(!opted||Notification.permission!=='granted')return;
  const reg=await pushRegistration(),sub=await reg.pushManager.getSubscription();if(epoch!==state.epoch||!sub)return;
  await api('/api/push/subscriptions',{method:'PUT',body:JSON.stringify(sub.toJSON())});if(epoch===state.epoch)notifications.enabled=true;
}
async function initNotifications(){await checkNotifications();try{await syncPush();updatePushStatus();}catch(e){updatePushStatus(`站内提醒正常；系统通知暂未连接：${e.message}`);}}
async function togglePush(){await busy($('pushToggle'),async()=>{
  if(!pushSupported()){updatePushStatus();return;}
  const epoch=state.epoch;
  if(!notifications.enabled){
    // Permission must be requested directly from this user gesture, before network work.
    const permission=Notification.permission==='granted'?'granted':await Notification.requestPermission();
    if(permission!=='granted'){updatePushStatus('尚未开启系统通知，站内提示仍然可用。');return;}
    const reg=await pushRegistration(),key=await api('/api/push/public-key');if(epoch!==state.epoch)return;
    let sub=await reg.pushManager.getSubscription();
    if(sub?.options.applicationServerKey){const old=new Uint8Array(sub.options.applicationServerKey),fresh=applicationKey(key.public_key);if(old.length!==fresh.length||old.some((x,i)=>x!==fresh[i])){await sub.unsubscribe();sub=null;}}
    sub=sub||await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:applicationKey(key.public_key)});
    if(epoch!==state.epoch){await sub.unsubscribe();return;}
    await api('/api/push/subscriptions',{method:'PUT',body:JSON.stringify(sub.toJSON())});
    if(epoch!==state.epoch)return;notifications.enabled=true;try{localStorage.setItem('campus-push-enabled','yes');}catch{}
  }else{
    const reg=await pushRegistration(),sub=await reg.pushManager.getSubscription();
    if(sub){await api('/api/push/subscriptions',{method:'DELETE',body:JSON.stringify(sub.toJSON())});await sub.unsubscribe();}
    if(epoch!==state.epoch)return;notifications.enabled=false;try{localStorage.removeItem('campus-push-enabled');}catch{}
  }
  updatePushStatus();
},'pushStatus');}
$('pushToggle').addEventListener('click',togglePush);
$('openMessageBanner').addEventListener('click',()=>{$('messageBanner').classList.add('hidden');navigate(notifications.route);});
$('dismissMessageBanner').addEventListener('click',()=>$('messageBanner').classList.add('hidden'));
$('noticeList').addEventListener('click',e=>{const b=e.target.closest('[data-notice]');if(b)busy(b,async()=>{await api(`/api/notices/${b.dataset.notice}/read`,{method:'POST'});navigate(b.dataset.meeting?`buddies/group/${b.dataset.meeting}`:'profile');await checkNotifications();});});
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&state.user){refreshBuddyDates();pollBuddyChat();}});
if('serviceWorker' in navigator)navigator.serviceWorker.addEventListener('message',e=>{if(e.data?.type==='campus-push'&&state.user)pollBuddyChat();});
