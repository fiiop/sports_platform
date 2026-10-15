const buddy = {map:null, layer:null, pin:null, point:null, rows:[], chats:[], chatId:null, after:0, timer:null, active:false, loading:false, listRequest:0, messageLoading:false};
const buddyTime = value => new Date(value).toLocaleString('zh-CN',{month:'long',day:'numeric',weekday:'short',hour:'2-digit',minute:'2-digit'});
function resetBuddies(){
  clearInterval(buddy.timer);buddy.active=false;buddy.chatId=null;buddy.after=0;buddy.rows=[];buddy.chats=[];buddy.point=null;buddy.listRequest++;
  if(buddy.layer)buddy.layer.clearLayers();if(buddy.pin){buddy.pin.remove();buddy.pin=null;}
  for(const id of ['buddyList','buddyChats','buddyMessages'])$(id).replaceChildren();
  $('buddyForm').reset();$('buddyFilterForm').reset();$('buddyMessageForm').reset();$('buddyMessageForm').classList.add('hidden');
  $('buddyChatTitle').textContent='选择一位搭子，打个招呼';
  for(const id of ['buddyChatTopic','buddyChatMsg','buddyFormMsg','buddyMapMsg'])$(id).textContent='';
  if(buddy.map)buddy.map.setView([35,105],4);
}
function buddyNavigate(page){
  clearInterval(buddy.timer);buddy.active=page==='buddies';if(!buddy.active)return;
  initBuddyMap();if(buddy.map)setTimeout(()=>buddy.map.invalidateSize(),0);
  loadBuddyPage().catch(e=>$('buddyMapMsg').textContent=e.message);
  buddy.timer=setInterval(()=>{if(!document.hidden && buddy.active && state.user)pollBuddyChat();},4000);
}
function initBuddyMap(){
  if(buddy.map)return;
  if(!window.L){$('buddyMapMsg').textContent='地图组件未加载，请刷新页面。';return;}
  buddy.map=L.map('buddyMap').setView([35,105],4);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors'}).on('tileerror',()=>{$('buddyMapMsg').textContent='地图底图暂时无法加载，请检查网络；已有状态仍可在下方查看和聊天。';}).addTo(buddy.map);
  buddy.layer=L.layerGroup().addTo(buddy.map);
  buddy.map.on('click',e=>{setBuddyPoint(e.latlng.lat,e.latlng.lng);$('buddyEditor').open=true;});
}
function setBuddyPoint(lat,lng){
  buddy.point={latitude:lat,longitude:((lng+180)%360+360)%360-180};
  $('buddyPoint').value='已选择地图地点，可点击地图重新选择';
  if(buddy.map){if(buddy.pin)buddy.pin.remove();buddy.pin=L.circleMarker([lat,buddy.point.longitude],{radius:12,color:'#b76b28',fillOpacity:.3}).addTo(buddy.map).bindTooltip('你选择的运动地点');}
}
async function loadBuddyPage(){
  const epoch=state.epoch;
  const own=await api('/api/buddies/me');if(epoch!==state.epoch)return;
  if(own){
    $('buddySport').value=own.exercise_type;$('buddyPlace').value=own.location;$('buddyNote').value=own.note;
    const d=new Date(own.starts_at);$('buddyTime').value=`${localDate(d)}T${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
    setBuddyPoint(own.latitude,own.longitude);buddy.map?.setView([own.latitude,own.longitude],14);
    $('buddyFormMsg').textContent=new Date(own.starts_at)<=new Date()?'之前的状态已过期，更新运动时间后可重新发布。':'你的状态已公开，可以修改后重新发布。';
  }
  await Promise.all([loadBuddyStatuses(),loadBuddyChats()]);
}
function buddyCard(row){
  const mine=row.user_id===state.user?.id;
  return `<article class="buddy-status"><div class="record-main"><h3>${escapeHTML(row.username)} <span class="pill">想${escapeHTML(row.exercise_type)}</span></h3>${mine?'<span class="fine">我</span>':''}</div><p class="record-detail">${escapeHTML(buddyTime(row.starts_at))} · ${escapeHTML(row.location)}</p><p class="record-detail">${escapeHTML(row.note)}</p>${mine?'':`<button type="button" class="ghost" data-buddy-user="${row.user_id}">加为聊天搭子 ↗</button>`}</article>`;
}
function renderBuddyStatuses(){
  $('buddyList').innerHTML=buddy.rows.map(buddyCard).join('')||'<div class="empty"><b>这里还没有运动状态</b>在地图上选个地点，发布你的第一条状态吧。</div>';
  if(buddy.layer){buddy.layer.clearLayers();for(const row of buddy.rows){L.circleMarker([row.latitude,row.longitude],{radius:10,color:row.user_id===state.user?.id?'#b76b28':'#185c45',fillOpacity:.8}).addTo(buddy.layer).bindPopup(buddyCard(row));}}
}
async function loadBuddyStatuses(append=false){
  const epoch=state.epoch,request=++buddy.listRequest;
  const rows=await api(`/api/buddies?exercise_type=${encodeURIComponent($('buddyFilter').value.trim())}&offset=${append?buddy.rows.length:0}`);
  if(epoch!==state.epoch||request!==buddy.listRequest)return;
  buddy.rows=append?[...buddy.rows,...rows]:rows;renderBuddyStatuses();$('buddyMore').classList.toggle('hidden',rows.length<100);
  if(!append && buddy.rows.length && buddy.map)buddy.map.fitBounds(buddy.rows.map(r=>[r.latitude,r.longitude]),{maxZoom:15,padding:[30,30]});
}
async function publishBuddy(){
  if(!$('buddyForm').reportValidity())return;
  await busy($('buddyPublish'),async()=>{
    if(!buddy.point)throw new Error('请先在地图上点击选择运动地点。');
    if(buddy.point.latitude < -85 || buddy.point.latitude >85)throw new Error('请选择有效的运动地点。');
    const epoch=state.epoch;
    await api('/api/buddies/me',{method:'PUT',body:JSON.stringify({exercise_type:$('buddySport').value,starts_at:new Date($('buddyTime').value).toISOString(),location:$('buddyPlace').value,note:$('buddyNote').value,...buddy.point})});
    if(epoch!==state.epoch)return;
    $('buddyFormMsg').textContent='状态已公开，其他人可以从地图上找你聊天。';$('buddyFilter').value='';await loadBuddyStatuses();
  },'buddyFormMsg');
}
async function removeBuddy(){
  await busy($('buddyRemove'),async()=>{
    const epoch=state.epoch;await api('/api/buddies/me',{method:'DELETE'});if(epoch!==state.epoch)return;
    $('buddyFormMsg').textContent='状态已撤下，已有聊天保留。';await loadBuddyStatuses();
  },'buddyFormMsg');
}
function renderBuddyChats(){
  $('buddyChats').innerHTML=buddy.chats.map(c=>`<button type="button" class="buddy-chat-choice ${buddy.chatId===c.id?'selected':''}" data-buddy-chat="${c.id}"><strong>${escapeHTML(c.username)}</strong><small>${escapeHTML(c.last_message)}</small></button>`).join('')||'<p class="fine">还没有聊天。点击地图上的搭子，打个招呼。</p>';
}
async function loadBuddyChats(append=false){
  const epoch=state.epoch;const rows=await api(`/api/buddy-chats?offset=${append?buddy.chats.length:0}`);if(epoch!==state.epoch)return;
  buddy.chats=append?[...buddy.chats,...rows]:rows;renderBuddyChats();$('buddyChatsMore').classList.toggle('hidden',rows.length<100);
}
async function openBuddyChat(id){
  buddy.chatId=id;buddy.after=0;$('buddyMessages').replaceChildren();$('buddyMessage').value='';$('buddyChatMsg').textContent='';
  const chat=buddy.chats.find(c=>c.id===id);$('buddyChatTitle').textContent=chat?`和 ${chat.username} 聊聊`:'搭子聊天';$('buddyChatTopic').textContent=chat?.topic||'';
  $('buddyMessageForm').classList.remove('hidden');renderBuddyChats();await loadBuddyMessages();$('buddyConversation').scrollIntoView({block:'nearest'});
}
async function loadBuddyMessages(){
  const epoch=state.epoch,id=buddy.chatId;if(!id)return;
  let more=true;
  while(more){
    const rows=await api(`/api/buddy-chats/${id}/messages?after=${buddy.after}`);if(epoch!==state.epoch||id!==buddy.chatId)return;
    const box=$('buddyMessages'),atBottom=box.scrollHeight-box.scrollTop-box.clientHeight<60;
    for(const row of rows){
      if(row.id<=buddy.after)continue;
      const item=document.createElement('div');item.className=`buddy-message ${row.sender_id===state.user.id?'mine':''}`;
      const body=document.createElement('p');body.textContent=row.body;const time=document.createElement('small');time.textContent=buddyTime(row.created_at);item.append(body,time);box.append(item);buddy.after=row.id;
    }
    if(atBottom)box.scrollTop=box.scrollHeight;
    more=rows.length===100;
  }
}
async function pollBuddyChat(){
  if(buddy.loading)return;buddy.loading=true;
  try{await loadBuddyChats();await loadBuddyMessages();$('buddyChatMsg').textContent='';}
  catch(e){if(state.user)$('buddyChatMsg').textContent=e.message;}
  finally{buddy.loading=false;}
}
async function sendBuddyMessage(){
  if(!$('buddyMessageForm').reportValidity()||!buddy.chatId)return;
  await busy($('buddySend'),async()=>{
    const epoch=state.epoch,id=buddy.chatId,body=$('buddyMessage').value;
    await api(`/api/buddy-chats/${id}/messages`,{method:'POST',body:JSON.stringify({body})});
    if(epoch!==state.epoch||id!==buddy.chatId)return;
    if($('buddyMessage').value===body)$('buddyMessage').value='';$('buddyChatMsg').textContent='';await loadBuddyMessages();await loadBuddyChats();
  },'buddyChatMsg');
}
$('buddyForm').addEventListener('submit',e=>{e.preventDefault();publishBuddy();});
$('buddyFilterForm').addEventListener('submit',e=>{e.preventDefault();busy(e.currentTarget.querySelector('button'),()=>loadBuddyStatuses(),'buddyMapMsg');});
$('buddyRemove').addEventListener('click',removeBuddy);
$('buddyMore').addEventListener('click',()=>busy($('buddyMore'),()=>loadBuddyStatuses(true),'buddyMapMsg'));
$('buddyChatsMore').addEventListener('click',()=>busy($('buddyChatsMore'),()=>loadBuddyChats(true),'buddyChatMsg'));
$('buddyMessageForm').addEventListener('submit',e=>{e.preventDefault();sendBuddyMessage();});
$('buddyChatRefresh').addEventListener('click',()=>pollBuddyChat());
$('page-buddies').addEventListener('click',e=>{
  const b=e.target.closest('button');if(!b)return;
  if(b.dataset.buddyUser)busy(b,async()=>{const epoch=state.epoch;const chat=await api(`/api/buddies/${b.dataset.buddyUser}/chat`,{method:'POST'});if(epoch!==state.epoch)return;await loadBuddyChats();await openBuddyChat(chat.id);},'buddyChatMsg');
  if(b.dataset.buddyChat)busy(b,()=>openBuddyChat(Number(b.dataset.buddyChat)),'buddyChatMsg');
});
$('buddyLocate').addEventListener('click',()=>{
  if(!navigator.geolocation){$('buddyMapMsg').textContent='浏览器不支持定位，请拖动地图选择地点。';return;}
  const epoch=state.epoch;$('buddyMapMsg').textContent='正在定位，只移动地图视野，不会自动公开位置。';
  navigator.geolocation.getCurrentPosition(p=>{if(epoch!==state.epoch)return;buddy.map?.setView([p.coords.latitude,p.coords.longitude],15);$('buddyMapMsg').textContent='已移动到附近，请点击地图选择约定的运动地点。';},()=>{if(epoch===state.epoch)$('buddyMapMsg').textContent='无法获取位置，请允许定位权限，或拖动和缩放地图选点。';},{timeout:10000,maximumAge:60000});
});
