const buddy = {map:null,layer:null,pin:null,point:null,pickerPoint:null,tiles:null,tileTimer:null,mapObserver:null,proxyTiles:false,
  rows:[],chats:[],chatId:null,after:0,before:0,own:null,dirty:false,initialized:false,active:false,tab:'discover',picker:false,
  timer:null,loading:false,listRequest:0,chatRequest:0,messageLoading:false,readAfter:0,preview:null};
const buddyTime = value => new Date(value).toLocaleString('zh-CN',{month:'long',day:'numeric',weekday:'short',hour:'2-digit',minute:'2-digit'});
const buddyKey = suffix => `campus-buddy:${state.user?.id}:${suffix}`;
function buddyStore(suffix,value){try{localStorage.setItem(buddyKey(suffix),JSON.stringify(value));return true;}catch{return false;}}
function buddyRead(suffix){try{return JSON.parse(localStorage.getItem(buddyKey(suffix))||'null');}catch{return null;}}
function buddyDrop(suffix){try{localStorage.removeItem(buddyKey(suffix));}catch{}}
function clearBuddyDrafts(){try{const prefix=buddyKey('');Object.keys(localStorage).filter(k=>k.startsWith(prefix)).forEach(k=>localStorage.removeItem(k));}catch{}}
function resetBuddies(){
  clearInterval(buddy.timer);clearTimeout(buddy.tileTimer);buddy.mapObserver?.disconnect();buddy.map?.remove();
  Object.assign(buddy,{map:null,layer:null,pin:null,tiles:null,point:null,own:null,dirty:false,initialized:false,chatId:null,rows:[],chats:[],active:false,timer:null,picker:false,loading:false,messageLoading:false});
  buddy.listRequest++;buddy.chatRequest++;
  for(const id of ['buddyList','buddyChats','buddyMessages','buddyOwnStatus','buddyBlocks'])$(id).replaceChildren();
  for(const id of ['buddyUnread','buddyTabUnread'])$(id).classList.add('hidden');
  for(const id of ['buddyPreviewDialog','buddyMapDialog','buddyRatingDialog'])if($(id).open)$(id).close();
  $('buddyForm').reset();$('buddyFilterForm').reset();$('buddyMessageForm').reset();
  $('buddyMapHost').append($('buddyMapWrap'));$('buddyPoint').textContent='未添加地图位置，可直接填写场地发布。';
  for(const id of ['buddyFormMsg','buddyChatMsg','buddyChatsMsg','buddyDraftMsg','buddyBlocksMsg'])$(id).textContent='';
}
function buddyRoute(tab,id){navigate(`buddies/${tab}${id?`/${id}`:''}`);}
function buddyNavigate(page,route=''){
  buddy.active=page==='buddies';
  if(!state.user)return;
  if(!buddy.timer)buddy.timer=setInterval(()=>{if(!document.hidden&&state.user)pollBuddyChat();},4000);
  if(!buddy.initialized){buddy.initialized=true;loadOwnBuddy().catch(e=>{$('buddyFormMsg').textContent=e.message;buddy.initialized=false;});updateBuddyUnread().catch(()=>{});}
  if(!buddy.active){buddy.chatId=null;return;}
  const [requested,id]=route.split('/');buddy.tab=['discover','messages','mine'].includes(requested)?requested:'discover';
  document.querySelectorAll('[data-buddy-tab]').forEach(b=>{const active=b.dataset.buddyTab===buddy.tab;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
  for(const [tab,panel] of [['discover','buddyDiscoverPanel'],['messages','buddyMessagesPanel'],['mine','buddyMinePanel']])$(panel).classList.toggle('hidden',tab!==buddy.tab);
  if(buddy.tab==='discover'){buddy.chatId=null;loadBuddyStatuses().catch(e=>$('buddyListMsg').textContent=e.message);if(buddy.map)setTimeout(()=>buddy.map?.invalidateSize(),0);}
  if(buddy.tab==='mine')buddy.chatId=null;
  if(buddy.tab==='messages'){
    const chatId=/^\d+$/.test(id||'')?Number(id):null;
    $('buddyChatListPanel').classList.toggle('hidden',!!chatId);$('buddyConversation').classList.toggle('hidden',!chatId);
    if(!chatId)buddy.chatId=null;
    loadBuddyChats().then(()=>{if(buddy.active&&buddy.tab==='messages'&&chatId)return openBuddyChat(chatId);}).catch(e=>$('buddyChatsMsg').textContent=e.message);
  }
}
function ownFields(){return {exercise_type:$('buddySport').value,time:$('buddyTime').value,location:$('buddyPlace').value,note:$('buddyNote').value,point:buddy.point};}
function applyOwnFields(d){$('buddySport').value=d.exercise_type||'羽毛球';$('buddyTime').value=d.time||'';$('buddyPlace').value=d.location||'';$('buddyNote').value=d.note||'';setBuddyPoint(d.point);}
function saveBuddyDraft(){
  if(!state.user)return;buddy.dirty=true;const ok=buddyStore('status',ownFields());
  $('buddyDraftMsg').textContent=ok?'编辑内容已暂存到此浏览器，尚未公开。':'浏览器无法暂存，请保留当前页面。';$('buddyDiscardDraft').classList.remove('hidden');
}
async function loadOwnBuddy(){
  const epoch=state.epoch,own=await api('/api/buddies/me');if(epoch!==state.epoch)return;buddy.own=own;renderOwnBuddy();
  if(buddy.dirty)return;
  const draft=buddyRead('status');
  if(draft){applyOwnFields(draft);buddy.dirty=true;$('buddyDraftMsg').textContent='已恢复尚未发布的本地草稿。';$('buddyDiscardDraft').classList.remove('hidden');return;}
  if(own){const d=new Date(own.starts_at);applyOwnFields({...own,time:`${localDate(d)}T${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`,point:own.latitude==null?null:{latitude:own.latitude,longitude:own.longitude}});}
}
function renderOwnBuddy(){
  const own=buddy.own,live=own&&new Date(own.starts_at)>new Date();
  $('buddyOwnStatus').innerHTML=own?`<span class="pill">${live?'已公开':'已到期'}</span><h3>${escapeHTML(own.exercise_type)} · ${escapeHTML(own.location)}</h3><p class="fine">${escapeHTML(buddyTime(own.starts_at))}${live?'':' · 更新运动时间后可再次发布'}</p>`:'<strong>还没有公开状态</strong><p class="fine">写下想做的运动，邀请同伴一起出发。</p>';
  $('buddyFormTitle').textContent=live?'修改运动状态':'发布运动状态';$('buddyRemove').classList.toggle('hidden',!own);
  $('homeBuddyStatus').textContent=live?`${own.exercise_type} · ${buddyTime(own.starts_at)} · ${own.location}`:'下一次想什么时候运动？发布状态，邀请同伴一起出发。';
}
function setBuddyPoint(point){buddy.point=point;$('buddyPoint').textContent=point?`已选地图位置：${point.latitude.toFixed(4)}, ${point.longitude.toFixed(4)}`:'未添加地图位置，可直接填写场地发布。';$('buddyClearPoint').classList.toggle('hidden',!point);}
function buddyCard(row){
  const mine=row.user_id===state.user?.id;
  const rating=row.rating==null?'暂无评分':`★ ${row.rating.toFixed(1)} · ${row.rating_count} 人评价`;
  return `<article class="buddy-status"><div class="record-main"><h3>${escapeHTML(row.exercise_type)}</h3><span class="rating-pill">${rating}</span></div><p class="buddy-date">${escapeHTML(buddyTime(row.starts_at))}</p><p class="record-detail">${escapeHTML(row.location)}${row.latitude==null?' · 文字地点':''}</p>${row.note?`<p class="record-detail">${escapeHTML(row.note)}</p>`:''}<div class="record-main"><span class="fine">${escapeHTML(row.username)}${mine?' · 我':''}</span>${mine?'<button type="button" class="ghost" data-buddy-tab="mine">修改状态</button>':`<button type="button" class="ghost" data-buddy-user="${row.user_id}">聊一聊 ↗</button>`}</div></article>`;
}
function renderBuddyStatuses(){
  const filtered=$('buddyFilter').value||$('buddyTimeFilter').value;
  $('buddyList').innerHTML=buddy.rows.map(buddyCard).join('')||`<div class="empty"><svg class="empty-runners" aria-hidden="true"><use href="#icon-buddies"/></svg><b>${filtered?'暂时没有符合条件的搭子':'还没有运动状态'}</b>${filtered?'换个项目或时间试试。':'发出第一份邀请，让同伴找到你。'}<div class="actions empty-actions"><button type="button" class="ghost" ${filtered?'data-clear-filters':'data-buddy-tab="mine"'}>${filtered?'清除筛选':'发布我的状态'}</button></div></div>`;
  if(buddy.layer){buddy.layer.clearLayers();for(const row of buddy.rows){if(row.latitude==null||row.longitude==null)continue;L.circleMarker([row.latitude,row.longitude],{radius:9,color:row.user_id===state.user?.id?'#b76b28':'#185c45',fillOpacity:.8}).addTo(buddy.layer).bindPopup(buddyCard(row));}}
  document.querySelectorAll('[data-filter-sport]').forEach(b=>{b.classList.toggle('selected',b.dataset.filterSport===$('buddyFilter').value.trim());b.setAttribute('aria-pressed',String(b.dataset.filterSport===$('buddyFilter').value.trim()));});
}
async function loadBuddyStatuses(append=false){
  const epoch=state.epoch,request=++buddy.listRequest;
  const query=new URLSearchParams({exercise_type:$('buddyFilter').value.trim(),sort:$('buddySort').value,offset:append?buddy.rows.length:0});
  const windowType=$('buddyTimeFilter').value;
  if(windowType){const start=new Date();start.setHours(0,0,0,0);if(windowType==='tomorrow')start.setDate(start.getDate()+1);const end=new Date(start);end.setDate(end.getDate()+(windowType==='week'?7:1));query.set('starts_after',start.toISOString());query.set('starts_before',end.toISOString());}
  $('buddyListMsg').textContent='正在寻找运动搭子…';
  const rows=await api(`/api/buddies?${query}`);if(epoch!==state.epoch||request!==buddy.listRequest)return;
  buddy.rows=append?[...buddy.rows,...rows]:rows;renderBuddyStatuses();$('buddyMore').classList.toggle('hidden',rows.length<100);$('buddyListMsg').textContent=`${buddy.rows.length} 条状态 · ${$('buddySort').value==='rating'?'评分优先；同分时优先评价人数较多的搭子':'按运动开始时间排序'}`;
}
function previewBuddy(){
  if(!$('buddyForm').reportValidity())return;
  const date=new Date($('buddyTime').value);if(!Number.isFinite(date.getTime())||date<=new Date()){$('buddyFormMsg').textContent='请选择未来的运动时间。';return;}
  buddy.preview={exercise_type:$('buddySport').value.trim(),location:$('buddyPlace').value.trim(),starts_at:date.toISOString(),note:$('buddyNote').value.trim(),latitude:buddy.point?.latitude??null,longitude:buddy.point?.longitude??null};
  if(!buddy.preview.exercise_type||!buddy.preview.location){$('buddyFormMsg').textContent='请填写运动项目和场地。';return;}
  $('buddyPreview').innerHTML=`<h3>${escapeHTML(buddy.preview.exercise_type)}</h3><p>${escapeHTML(buddyTime(buddy.preview.starts_at))}</p><p>${escapeHTML(buddy.preview.location)}</p><p class="fine">${escapeHTML(buddy.preview.note)}</p><p class="fine">${buddy.point?'含地图位置':'仅公开文字地点，也能在列表中被找到'}</p>`;
  $('buddyPreviewMsg').textContent='';$('buddyPreviewDialog').showModal();
}
async function publishBuddy(){await busy($('buddyConfirmPublish'),async()=>{
  const epoch=state.epoch,own=await api('/api/buddies/me',{method:'PUT',body:JSON.stringify(buddy.preview)});if(epoch!==state.epoch)return;
  buddy.own=own;buddy.dirty=false;buddyDrop('status');$('buddyDraftMsg').textContent='';$('buddyDiscardDraft').classList.add('hidden');renderOwnBuddy();$('buddyPreviewDialog').close();$('buddyFormMsg').textContent='状态已公开，等一个一起出发的同伴。';celebrate($('buddyOwnStatus'));notify('运动邀请已发布');
},'buddyPreviewMsg');}
async function removeBuddy(){if(!confirm('撤下这条公开状态？已有聊天会保留。'))return;await busy($('buddyRemove'),async()=>{const epoch=state.epoch;await api('/api/buddies/me',{method:'DELETE'});if(epoch!==state.epoch)return;buddy.own=null;renderOwnBuddy();$('buddyFormMsg').textContent='状态已撤下，已有聊天保留。';},'buddyFormMsg');}

function initBuddyMap(){
  if(buddy.map)return;
  if(!window.L){$('buddyMapMsg').textContent='地图组件无法加载，仍可填写文字地点发布。';return;}
  buddy.map=L.map('buddyMap').setView([35,105],4);buddy.layer=L.layerGroup().addTo(buddy.map);useBuddyTiles(false);
  buddy.map.on('click',e=>{if(!buddy.picker)return;buddy.pickerPoint={latitude:e.latlng.lat,longitude:((e.latlng.lng+180)%360+360)%360-180};renderPickerPoint();$('buddyConfirmPoint').disabled=false;});
  if(window.ResizeObserver){buddy.mapObserver=new ResizeObserver(()=>buddy.map?.invalidateSize());buddy.mapObserver.observe($('buddyMap'));}
  renderBuddyStatuses();
}
function renderPickerPoint(){buddy.pin?.remove();buddy.pin=null;if(buddy.pickerPoint&&buddy.map)buddy.pin=L.circleMarker([buddy.pickerPoint.latitude,buddy.pickerPoint.longitude],{radius:12,color:'#b76b28',fillOpacity:.4}).addTo(buddy.map);}
function useBuddyTiles(proxy){
  if(!buddy.map)return;clearTimeout(buddy.tileTimer);
  if(buddy.tiles){buddy.tiles.off('loading tileerror load');buddy.map.removeLayer(buddy.tiles);}
  buddy.proxyTiles=proxy;$('buddyMapRetry').classList.add('hidden');$('buddyMapMsg').textContent=proxy?'正在通过备用通道加载地图…':'正在加载地图…';
  const layer=L.tileLayer(proxy?'/api/map-tiles/{z}/{x}/{y}.png':'https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors'});
  buddy.tiles=layer;let errors=0,switching=false;
  function failed(){if(buddy.tiles!==layer)return;if(!proxy){if(switching)return;switching=true;setTimeout(()=>{if(buddy.tiles===layer)useBuddyTiles(true);},0);}else{$('buddyMapMsg').textContent='底图暂时无法加载，可重试或使用文字地点；列表与聊天仍可使用。';$('buddyMapRetry').classList.remove('hidden');}}
  layer.on('loading',()=>{errors=0;clearTimeout(buddy.tileTimer);buddy.tileTimer=setTimeout(failed,proxy?20000:8000);});
  layer.on('tileerror',()=>{errors++;failed();});layer.on('load',()=>{if(buddy.tiles!==layer)return;clearTimeout(buddy.tileTimer);if(errors){failed();return;}$('buddyMapMsg').textContent='';$('buddyMapRetry').classList.add('hidden');});layer.addTo(buddy.map);
}
function showBuddyMap(show){$('buddyMapHost').classList.toggle('hidden',!show);$('buddyMapView').classList.toggle('active',show);$('buddyListView').classList.toggle('active',!show);$('buddyMapView').setAttribute('aria-pressed',String(show));$('buddyListView').setAttribute('aria-pressed',String(!show));if(show){const first=!buddy.map;initBuddyMap();setTimeout(()=>{buddy.map?.invalidateSize();const points=buddy.rows.filter(r=>r.latitude!=null).map(r=>[r.latitude,r.longitude]);if(first&&points.length)buddy.map?.fitBounds(points,{maxZoom:15,padding:[24,24]});},0);}}
function openPointPicker(){buddy.picker=true;buddy.pickerPoint=buddy.point?{...buddy.point}:null;$('buddyPickerHost').append($('buddyMapWrap'));$('buddyMapDialog').showModal();initBuddyMap();renderPickerPoint();$('buddyConfirmPoint').disabled=!buddy.pickerPoint;setTimeout(()=>{buddy.map?.invalidateSize();if(buddy.point)buddy.map?.setView([buddy.point.latitude,buddy.point.longitude],15);},0);}
function closePointPicker(){buddy.picker=false;buddy.pin?.remove();buddy.pin=null;$('buddyMapHost').append($('buddyMapWrap'));setTimeout(()=>buddy.map?.invalidateSize(),0);}

async function updateBuddyUnread(){const epoch=state.epoch,d=await api('/api/buddy-chats/unread');if(epoch!==state.epoch)return;for(const id of ['buddyUnread','buddyTabUnread']){$(id).textContent=d.count>99?'99+':String(d.count);$(id).classList.toggle('hidden',!d.count);$(id).setAttribute('aria-label',`${d.count} 条未读消息`);}}
function renderBuddyChats(){
  $('buddyChats').innerHTML=buddy.chats.map(c=>`<button type="button" class="buddy-chat-choice" data-buddy-chat="${c.id}"><span class="chat-meta"><strong>${escapeHTML(c.username)}</strong>${c.unread_count?`<span class="unread-badge">${c.unread_count>99?'99+':c.unread_count}</span>`:''}<small>${c.last_at?escapeHTML(buddyTime(c.last_at)):''}</small></span><small>${c.blocked?'当前不可互动 · ':''}${escapeHTML(c.last_message)}</small></button>`).join('')||'<div class="empty"><b>从一句问候开始</b>在发现页找到合适的搭子，点「聊一聊」。</div>';
}
async function loadBuddyChats(append=false){
  const epoch=state.epoch,rows=await api(`/api/buddy-chats?offset=${append?buddy.chats.length:0}`);if(epoch!==state.epoch)return;
  const byId=new Map(buddy.chats.map(c=>[c.id,c]));for(const row of rows)byId.set(row.id,row);buddy.chats=[...byId.values()].sort((a,b)=>b.last_id-a.last_id||b.id-a.id);renderBuddyChats();
  if(append||buddy.chats.length<=100)$('buddyChatsMore').classList.toggle('hidden',rows.length<100);
  const selected=buddy.chats.find(c=>c.id===buddy.chatId);if(selected)$('buddySend').disabled=selected.blocked;
}
async function openBuddyChat(id){
  if(!buddy.active||buddy.tab!=='messages')return;
  if(buddy.chatId===id)return;
  const epoch=state.epoch,request=++buddy.chatRequest;buddy.chatId=id;buddy.after=0;buddy.before=0;buddy.readAfter=0;
  $('buddyMessages').replaceChildren();$('buddyMessage').value=buddyRead(`chat:${id}`)||'';$('buddyChatMsg').textContent='正在加载消息…';$('buddyNewMessages').classList.add('hidden');
  const c=buddy.chats.find(c=>c.id===id);$('buddyChatTitle').textContent=c?`和 ${c.username} 聊聊`:'搭子聊天';$('buddyChatTopic').textContent=c?.topic||'';$('buddySend').disabled=!!c?.blocked;
  const rows=await api(`/api/buddy-chats/${id}/messages?latest=true&limit=50`);if(epoch!==state.epoch||request!==buddy.chatRequest||id!==buddy.chatId)return;
  appendBuddyMessages(rows);$('buddyOlder').classList.toggle('hidden',rows.length<50);$('buddyMessages').scrollTop=$('buddyMessages').scrollHeight;$('buddyChatMsg').textContent=c?.blocked?'当前无法互动，可在“我的”中管理黑名单。':'';await markBuddyRead();
}
function messageNode(row){const item=document.createElement('div');item.className=`buddy-message ${row.sender_id===state.user.id?'mine':''}`;item.dataset.message=String(row.id);const p=document.createElement('p');p.textContent=row.body;const t=document.createElement('small');t.textContent=buddyTime(row.created_at);item.append(p,t);return item;}
function appendBuddyMessages(rows,older=false){
  const box=$('buddyMessages'),fragment=document.createDocumentFragment();
  for(const row of rows){if(box.querySelector(`[data-message="${row.id}"]`))continue;fragment.append(messageNode(row));buddy.after=Math.max(buddy.after,row.id);buddy.before=buddy.before?Math.min(buddy.before,row.id):row.id;}
  if(older)box.prepend(fragment);else box.append(fragment);
}
async function loadOlderMessages(){await busy($('buddyOlder'),async()=>{const epoch=state.epoch,id=buddy.chatId,rows=await api(`/api/buddy-chats/${id}/messages?before=${buddy.before}&limit=50`);if(epoch!==state.epoch||id!==buddy.chatId)return;const box=$('buddyMessages'),height=box.scrollHeight;appendBuddyMessages(rows,true);box.scrollTop+=box.scrollHeight-height;$('buddyOlder').classList.toggle('hidden',rows.length<50);},'buddyChatMsg');}
async function markBuddyRead(){
  const box=$('buddyMessages');if(!buddy.active||buddy.tab!=='messages'||!buddy.chatId||!buddy.after||document.hidden||box.scrollHeight-box.scrollTop-box.clientHeight>50||buddy.readAfter>=buddy.after)return;
  const epoch=state.epoch,id=buddy.chatId,after=buddy.after;await api(`/api/buddy-chats/${id}/read`,{method:'POST',body:JSON.stringify({message_id:after})});if(epoch!==state.epoch||id!==buddy.chatId)return;buddy.readAfter=Math.max(buddy.readAfter,after);$('buddyNewMessages').classList.add('hidden');await updateBuddyUnread();
}
async function loadBuddyMessages(){
  if(!buddy.chatId||buddy.messageLoading)return;buddy.messageLoading=true;
  const epoch=state.epoch,id=buddy.chatId;
  try{const rows=await api(`/api/buddy-chats/${id}/messages?after=${buddy.after}&limit=100`);if(epoch!==state.epoch||id!==buddy.chatId)return;const box=$('buddyMessages'),atBottom=box.scrollHeight-box.scrollTop-box.clientHeight<50;appendBuddyMessages(rows);if(atBottom)box.scrollTop=box.scrollHeight;else if(rows.length)$('buddyNewMessages').classList.remove('hidden');await markBuddyRead();}
  finally{if(epoch===state.epoch)buddy.messageLoading=false;}
}
async function pollBuddyChat(){
  if(buddy.loading||!state.user)return;buddy.loading=true;const epoch=state.epoch;
  try{await updateBuddyUnread();if(buddy.active&&buddy.tab==='messages'){await loadBuddyChats();if(buddy.chatId)await loadBuddyMessages();}if(buddy.own)renderOwnBuddy();}
  catch(e){if(state.user&&buddy.active)$('buddyChatsMsg').textContent=e.message;}
  finally{if(epoch===state.epoch)buddy.loading=false;}
}
async function sendBuddyMessage(){if(!$('buddyMessageForm').reportValidity()||!buddy.chatId)return;await busy($('buddySend'),async()=>{
  const epoch=state.epoch,id=buddy.chatId,body=$('buddyMessage').value;await api(`/api/buddy-chats/${id}/messages`,{method:'POST',body:JSON.stringify({body})});if(epoch!==state.epoch)return;
  if(buddyRead(`chat:${id}`)===body)buddyDrop(`chat:${id}`);
  if(id===buddy.chatId){if($('buddyMessage').value===body)$('buddyMessage').value='';$('buddyChatMsg').textContent='';$('buddyMessages').scrollTop=$('buddyMessages').scrollHeight;await loadBuddyMessages();}await loadBuddyChats();
},'buddyChatMsg');}
function selectedBuddy(){return buddy.chats.find(c=>c.id===buddy.chatId);}
async function openRating(){const c=selectedBuddy();if(!c)return;await busy($('buddyRate'),async()=>{const epoch=state.epoch,d=await api(`/api/buddies/${c.user_id}/rating`);if(epoch!==state.epoch)return;$('buddyRatingDialog').dataset.user=String(c.user_id);$('buddyScore').value=String(d.my_score||5);$('buddySaveRating').disabled=!d.can_rate;$('buddyRatingSummary').textContent=d.rating==null?'这位搭子还没有评分。':`当前 ${d.rating.toFixed(1)} 分 · ${d.rating_count} 人评价`;$('buddyRatingMsg').textContent=d.can_rate?'': '双方交流过消息后才可评分，黑名单状态下不可评分。';$('buddyRatingDialog').showModal();},'buddyChatMsg');}
async function saveRating(){await busy($('buddySaveRating'),async()=>{const epoch=state.epoch;await api(`/api/buddies/${$('buddyRatingDialog').dataset.user}/rating`,{method:'PUT',body:JSON.stringify({score:Number($('buddyScore').value)})});if(epoch!==state.epoch)return;$('buddyRatingDialog').close();notify('评分已保存，谢谢你的反馈');},'buddyRatingMsg');}
async function blockBuddy(){const c=selectedBuddy();if(!c||!confirm(`将 ${c.username} 加入黑名单？双方将无法继续发消息。`))return;await busy($('buddyBlock'),async()=>{const epoch=state.epoch;await api(`/api/buddy-blocks/${c.user_id}`,{method:'PUT'});if(epoch!==state.epoch)return;await loadBuddyChats();$('buddyChatMsg').textContent='已加入黑名单，可在“我的”中解除。';},'buddyChatMsg');}
async function loadBlocks(){const epoch=state.epoch,rows=await api('/api/buddy-blocks');if(epoch!==state.epoch)return;$('buddyBlocks').innerHTML=rows.map(r=>`<div class="record-main record-item"><strong>${escapeHTML(r.username)}</strong><button type="button" class="ghost" data-unblock="${r.user_id}">解除拉黑</button></div>`).join('')||'<p class="fine">你的黑名单为空。</p>';}
function celebrate(el){el.classList.remove('success-pop');void el.offsetWidth;el.classList.add('success-pop');}

$('buddyForm').addEventListener('submit',e=>{e.preventDefault();previewBuddy();});
$('buddyForm').addEventListener('input',saveBuddyDraft);
$('buddyFilterForm').addEventListener('submit',e=>{e.preventDefault();busy(e.currentTarget.querySelector('button'),()=>loadBuddyStatuses(),'buddyListMsg');});
$('buddyMessageForm').addEventListener('submit',e=>{e.preventDefault();sendBuddyMessage();});
$('buddyMessage').addEventListener('input',()=>{if(buddy.chatId)buddyStore(`chat:${buddy.chatId}`,$('buddyMessage').value);});
$('buddyMessages').addEventListener('scroll',()=>markBuddyRead().catch(()=>{}));
$('buddyRatingForm').addEventListener('submit',e=>{e.preventDefault();saveRating();});
const buddyActions={buddyConfirmPublish:publishBuddy,buddyCancelPreview:()=>$('buddyPreviewDialog').close(),buddyRemove:removeBuddy,
  buddyDiscardDraft:()=>{if(!confirm('放弃尚未公开的修改？'))return;buddy.dirty=false;buddyDrop('status');$('buddyForm').reset();setBuddyPoint(null);$('buddyDraftMsg').textContent='';$('buddyDiscardDraft').classList.add('hidden');loadOwnBuddy().catch(e=>notify(e.message));},
  buddyListView:()=>showBuddyMap(false),buddyMapView:()=>showBuddyMap(true),buddyMapRetry:()=>useBuddyTiles(true),buddyPickPoint:openPointPicker,
  buddyClearPoint:()=>{setBuddyPoint(null);saveBuddyDraft();},buddyCancelPoint:()=>$('buddyMapDialog').close(),buddyConfirmPoint:()=>{setBuddyPoint(buddy.pickerPoint);saveBuddyDraft();$('buddyMapDialog').close();},
  buddyMore:()=>busy($('buddyMore'),()=>loadBuddyStatuses(true),'buddyListMsg'),buddyChatsMore:()=>busy($('buddyChatsMore'),()=>loadBuddyChats(true),'buddyChatsMsg'),
  buddyChatBack:()=>buddyRoute('messages'),buddyChatRefresh:pollBuddyChat,buddyOlder:loadOlderMessages,
  buddyNewMessages:()=>{$('buddyMessages').scrollTop=$('buddyMessages').scrollHeight;markBuddyRead().catch(()=>{});},
  buddyRate:openRating,buddyBlock:blockBuddy,buddyCloseRating:()=>$('buddyRatingDialog').close(),loadBlocks:()=>busy($('loadBlocks'),loadBlocks,'buddyBlocksMsg')};
for(const [id,fn] of Object.entries(buddyActions))$(id).addEventListener('click',fn);
$('buddyMapDialog').addEventListener('close',closePointPicker);
$('buddyOtherSport').addEventListener('click',()=>{$('buddyCustomFilter').classList.remove('hidden');$('buddyFilterApply').classList.remove('hidden');$('buddyFilter').focus();});
for(const id of ['buddyTimeFilter','buddySort'])$(id).addEventListener('change',()=>loadBuddyStatuses().catch(e=>$('buddyListMsg').textContent=e.message));
$('page-buddies').addEventListener('click',e=>{
  const b=e.target.closest('button');if(!b)return;
  if(b.dataset.buddyTab)buddyRoute(b.dataset.buddyTab);
  if(b.dataset.buddyChat)buddyRoute('messages',Number(b.dataset.buddyChat));
  if(b.dataset.buddyUser)busy(b,async()=>{const epoch=state.epoch,c=await api(`/api/buddies/${b.dataset.buddyUser}/chat`,{method:'POST'});if(epoch===state.epoch)buddyRoute('messages',c.id);},'buddyListMsg');
  if('filterSport' in b.dataset){$('buddyFilter').value=b.dataset.filterSport;busy(b,()=>loadBuddyStatuses(),'buddyListMsg');}
  if('clearFilters' in b.dataset){$('buddyFilterForm').reset();busy(b,()=>loadBuddyStatuses(),'buddyListMsg');}
  if(b.dataset.buddySport){$('buddySport').value=b.dataset.buddySport;saveBuddyDraft();}
  if(b.dataset.buddyPlace){$('buddyPlace').value=b.dataset.buddyPlace;setBuddyPoint(null);saveBuddyDraft();}
  if('buddyDay' in b.dataset){const date=new Date();if(b.dataset.buddyDay==='weekend')date.setDate(date.getDate()+((6-date.getDay()+7)%7));else date.setDate(date.getDate()+Number(b.dataset.buddyDay));const existing=$('buddyTime').value.slice(11)||'18:00';$('buddyTime').value=`${localDate(date)}T${existing}`;saveBuddyDraft();}
});
$('buddyBlocks').addEventListener('click',e=>{const b=e.target.closest('[data-unblock]');if(b)busy(b,async()=>{const epoch=state.epoch;await api(`/api/buddy-blocks/${b.dataset.unblock}`,{method:'DELETE'});if(epoch!==state.epoch)return;await loadBlocks();notify('已移出黑名单');},'buddyBlocksMsg');});
$('buddyLocate').addEventListener('click',()=>{if(!navigator.geolocation){$('buddyMapMsg').textContent='浏览器不支持定位，可手动拖动地图。';return;}const epoch=state.epoch;$('buddyMapMsg').textContent='正在定位，仅移动视野，不公开当前位置。';navigator.geolocation.getCurrentPosition(p=>{if(epoch!==state.epoch)return;buddy.map?.setView([p.coords.latitude,p.coords.longitude],15);$('buddyMapMsg').textContent='已移动视野，点击地图选点或返回使用文字地点。';},()=>{if(epoch===state.epoch)$('buddyMapMsg').textContent='定位不可用，可手动选点，或使用文字地点发布。';},{timeout:10000,maximumAge:60000});});

$('buddyMessage').addEventListener('focus',()=>document.body.classList.add('chat-typing'));
$('buddyMessage').addEventListener('blur',()=>setTimeout(()=>{if(document.activeElement!==$('buddyMessage'))document.body.classList.remove('chat-typing');},180));
