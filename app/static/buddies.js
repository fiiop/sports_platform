const buddy = {map:null,layer:null,pin:null,point:null,pickerPoint:null,tiles:null,tileTimer:null,mapObserver:null,proxyTiles:false,
  rows:[],chats:[],chatId:null,after:0,before:0,own:null,dirty:false,initialized:false,active:false,tab:'discover',picker:false,
  timer:null,loading:false,listRequest:0,chatRequest:0,messageLoading:false,readAfter:0,preview:null,mine:[],editId:null,searchTimer:null};
const buddyTime = value => new Date(value).toLocaleString('zh-CN',{month:'long',day:'numeric',weekday:'short',hour:'2-digit',minute:'2-digit'});
const buddyKey = suffix => `campus-buddy:${state.user?.id}:${suffix}`;
function buddyStore(suffix,value){try{localStorage.setItem(buddyKey(suffix),JSON.stringify(value));return true;}catch{return false;}}
function buddyRead(suffix){try{return JSON.parse(localStorage.getItem(buddyKey(suffix))||'null');}catch{return null;}}
function buddyDrop(suffix){try{localStorage.removeItem(buddyKey(suffix));}catch{}}
function clearBuddyDrafts(){try{const prefix=buddyKey('');Object.keys(localStorage).filter(k=>k.startsWith(prefix)).forEach(k=>localStorage.removeItem(k));}catch{}}
function resetBuddies(){
  if(typeof resetBuddyCover==='function')resetBuddyCover();
  clearInterval(buddy.timer);clearTimeout(buddy.searchTimer);document.body.classList.remove('in-conversation','chat-typing','in-messages','in-message-list','in-publish');clearTimeout(buddy.tileTimer);buddy.mapObserver?.disconnect();buddy.map?.remove();
  Object.assign(buddy,{map:null,layer:null,pin:null,tiles:null,point:null,own:null,dirty:false,initialized:false,chatId:null,rows:[],chats:[],active:false,timer:null,picker:false,loading:false,messageLoading:false,mine:[],editId:null,savedPreview:null});
  buddy.listRequest++;buddy.chatRequest++;
  for(const id of ['buddyList','buddyChats','buddyMessages','buddyOwnStatus','buddyBlocks'])$(id).replaceChildren();
  $('buddyChatAvatar').replaceChildren();delete $('buddyChatAvatar').dataset.identity;$('buddyChatTitle').textContent='搭子聊天';$('buddyChatTopic').textContent='';
  $('messageSelfAvatar').replaceChildren();delete $('messageSelfAvatar').dataset.identity;delete $('buddyChats').dataset.signature;$('messageConversationCount').textContent='';$('buddyChatMenu').open=false;
  for(const id of ['buddyUnread','buddyTabUnread'])$(id).classList.add('hidden');
  for(const id of ['buddyPreviewDialog','buddyMapDialog','buddyRatingDialog','buddyFilterDialog'])if($(id).open)$(id).close();
  $('buddyForm').reset();$('buddyMoreDetails').open=false;$('buddyReusePlace').classList.add('hidden');$('buddyReuseHint').classList.add('hidden');$('buddyFilterForm').reset();$('buddyMessageForm').reset();$('buddyMessage').style.height='44px';
  $('buddyMapHost').append($('buddyMapWrap'));$('buddyPoint').textContent='未添加地图位置，可直接填写场地发布。';
  for(const id of ['buddyFormMsg','buddyChatMsg','buddyChatsMsg','buddyDraftMsg','buddyBlocksMsg'])$(id).textContent='';
}
function buddyRoute(tab,id){navigate(`${tab==='messages'?'messages':`buddies/${tab}`}${id?`/${id}`:''}`);}
function buddyNavigate(page,route=''){
  buddy.active=page==='buddies';document.body.classList.remove('in-conversation','in-messages','in-message-list','in-publish');$('buddyChatMenu').open=false;
  if(!state.user)return;
  if(!buddy.timer)buddy.timer=setInterval(()=>{if(!document.hidden&&state.user)pollBuddyChat();},4000);
  if(!buddy.initialized){buddy.initialized=true;loadOwnBuddy().catch(e=>{$('buddyFormMsg').textContent=e.message;buddy.initialized=false;});updateBuddyUnread().catch(()=>{});}
  if(!buddy.active){buddy.chatId=null;return;}
  const [requested,id]=route.split('/');buddy.tab=['discover','messages','mine','appointments','group'].includes(requested)?requested:'discover';
  document.body.classList.toggle('in-publish',buddy.tab==='mine');
  const messaging=buddy.tab==='messages'||buddy.tab==='group';
  document.querySelector('.buddy-tabs').classList.toggle('hidden',messaging);
  $('buddyPageTitle').textContent=messaging?'每一次约定，都有回应':'找到你的运动同频';
  $('buddyPageIntro').textContent=messaging?'和同伴聊聊，把时间和地点约清楚。':'今天想动一动？同校的伙伴在这里。';
  document.querySelectorAll('[data-buddy-tab]').forEach(b=>{const active=b.dataset.buddyTab===buddy.tab;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
  for(const [tab,panel] of [['discover','buddyDiscoverPanel'],['messages','buddyMessagesPanel'],['mine','buddyMinePanel'],['appointments','buddyAppointmentsPanel'],['group','buddyGroupPanel']])$(panel).classList.toggle('hidden',tab!==buddy.tab);
  if(buddy.tab!=='messages')buddy.chatId=null;
  if(buddy.tab==='discover'){refreshBuddyDates();loadBuddyStatuses().catch(e=>$('buddyListMsg').textContent=e.message);if(buddy.map)setTimeout(()=>buddy.map?.invalidateSize(),0);}
  if(buddy.tab==='appointments')loadMeetups().catch(e=>$('meetupsMsg').textContent=e.message);
  if(buddy.tab==='group')loadMeetup(Number(id)).catch(e=>$('meetupMsg').textContent=e.message);
  if(buddy.tab==='messages'){
    const chatId=/^\d+$/.test(id||'')?Number(id):null;
    document.body.classList.add('in-messages');document.body.classList.toggle('in-message-list',!chatId);renderMessageSelf();
    if(chatId&&buddy.chatId!==chatId){$('buddyMessage').disabled=true;$('buddySend').disabled=true;}
    document.body.classList.toggle('in-conversation',!!chatId);
    $('buddyChatListPanel').classList.toggle('hidden',!!chatId);$('buddyConversation').classList.toggle('hidden',!chatId);
    if(!chatId)buddy.chatId=null;
    loadBuddyChats().then(()=>{if(buddy.active&&buddy.tab==='messages'&&chatId)return openBuddyChat(chatId);}).catch(e=>{(chatId?$('buddyChatMsg'):$('buddyChatsMsg')).textContent=e.message;});
    loadMeetups().catch(()=>{});
  }
}
function ownFields(){return {exercise_type:$('buddySport').value,time:$('buddyTime').value,location:$('buddyPlace').value,note:$('buddyNote').value,point:buddy.point,duration:Number($('buddyDuration').value),capacity:Number($('buddyCapacity').value),level:$('buddyLevel').value,edit_id:buddy.editId};}
function setBuddyDuration(value){const duration=Number(value),select=$('buddyDuration');if(!Number.isInteger(duration)||duration<15||duration>360)return;const text=String(duration);if(!Array.from(select.options).some(option=>option.value===text))select.add(new Option(`${duration} 分钟`,text));select.value=text;}
function updatePublishSummary(){
  const sport=$('buddySport').value.trim(),capacity=Number($('buddyCapacity').value),duration=Number($('buddyDuration').value);
  const people=Number.isInteger(capacity)&&capacity>=2&&capacity<=20?(capacity>2?`${capacity} 人组局`:'找一位同伴'):'请填写人数';
  $('buddyPublishSummary').textContent=sport?`${sport} · ${duration} 分钟 · ${people}`:'准备好，就邀请同学一起';
  document.querySelectorAll('[data-buddy-sport]').forEach(button=>{const selected=button.dataset.buddySport===sport;button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));});
}
function lastPublishedPlace(){return buddy.mine.filter(row=>row.user_id===state.user?.id&&row.location?.trim()&&row.id!==buddy.editId).sort((a,b)=>b.id-a.id)[0]||null;}
function renderReusePlace(){const row=lastPublishedPlace();$('buddyReusePlace').classList.toggle('hidden',!row);$('buddyReusePlace').title=row?`沿用 ${row.location} 和 ${row.duration} 分钟`:'';}
function reuseLastPlace(){const row=lastPublishedPlace();if(!row)return;$('buddyPlace').value=row.location;setBuddyDuration(row.duration);setBuddyPoint(row.latitude==null?null:{latitude:row.latitude,longitude:row.longitude});$('buddyReuseHint').textContent=`已沿用：${row.location} · ${row.duration} 分钟，仍可修改。`;$('buddyReuseHint').classList.remove('hidden');saveBuddyDraft();}
function applyOwnFields(d){$('buddySport').value=d.exercise_type||'羽毛球';$('buddyTime').value=d.time||'';$('buddyPlace').value=d.location||'';$('buddyNote').value=d.note||'';setBuddyPoint(d.point);setBuddyDuration(d.duration||60);$('buddyCapacity').value=String(d.capacity||2);$('buddyLevel').value=d.level||'不限';buddy.editId=d.edit_id||null;$('buddyCapacity').disabled=!!buddy.editId;updatePublishSummary();}
function saveBuddyDraft(){
  if(!state.user)return;buddy.dirty=true;updatePublishSummary();const ok=buddyStore('status',ownFields());
  $('buddyDraftMsg').textContent=ok?'编辑内容已暂存到此浏览器，尚未公开。':'浏览器无法暂存，请保留当前页面。';$('buddyDiscardDraft').classList.remove('hidden');
}
async function loadOwnBuddy(){
  const epoch=state.epoch,rows=await api('/api/activities/mine');if(epoch!==state.epoch)return;buddy.mine=rows;buddy.own=rows.find(r=>new Date(r.starts_at)>new Date())||null;renderOwnBuddy();
  if(buddy.dirty)return;
  const draft=buddyRead('status');if(draft){applyOwnFields(draft);if(typeof setBuddyCover==='function')setBuddyCover(rows.find(r=>r.id===buddy.editId));buddy.dirty=true;$('buddyDraftMsg').textContent='已恢复本地草稿，请核对后发布；未上传的图片需重新选择。';$('buddyDiscardDraft').classList.remove('hidden');renderOwnBuddy();}
}
function renderOwnBuddy(){
  $('buddyOwnStatus').innerHTML=buddy.mine.map(row=>`<div class="own-activity"><div><span class="pill">${new Date(row.starts_at)>new Date()?'已公开':'已开始'}</span><h3>${escapeHTML(row.exercise_type)}${row.capacity>2?` · ${row.joined}/${row.capacity} 人组局`:''}</h3><p class="fine">${escapeHTML(buddyTime(row.starts_at))} · ${escapeHTML(row.location)}</p></div><div class="actions">${new Date(row.starts_at)>new Date()?`<button type="button" class="text-button" data-edit-activity="${row.id}">编辑</button>`:''}${row.meetup_id?`<button type="button" class="text-button" data-open-meetup="${row.meetup_id}">查看组局</button>`:''}<button type="button" class="text-button" data-remove-activity="${row.id}">撤下</button></div></div>`).join('')||'<strong>发布第一次运动邀请</strong><p class="fine">可以同时发布最多三条未来状态。</p>';
  $('buddyFormTitle').textContent=buddy.editId?'调整这场运动':'发起一场运动';$('buddyPublish').firstChild.textContent=buddy.editId?'预览修改 ':'预览邀请 ';$('buddyRemove').classList.add('hidden');$('buddyPublishedCount').textContent=String(buddy.mine.length);$('buddyPublishedPanel').classList.toggle('hidden',!buddy.mine.length&&!buddy.editId);renderReusePlace();updatePublishSummary();
  const own=buddy.own;$('homeBuddyStatus').textContent=own?`${own.exercise_type} · ${buddyTime(own.starts_at)} · ${own.location}`:'下一次想什么时候运动？发布状态，邀请同伴一起出发。';
}
function editActivity(id){const row=buddy.mine.find(r=>r.id===id);if(!row)return;const d=new Date(row.starts_at);applyOwnFields({...row,edit_id:id,time:`${localDate(d)}T${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`,point:row.latitude==null?null:{latitude:row.latitude,longitude:row.longitude}});buddy.savedPreview=null;if(typeof setBuddyCover==='function')setBuddyCover(row);$('buddyMoreDetails').open=!!(row.cover_url||row.note||row.level!=='不限');$('buddyReuseHint').classList.add('hidden');buddy.dirty=true;renderOwnBuddy();$('buddyFormTitle').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth',block:'start'});}
function newActivity(){buddy.editId=null;buddy.savedPreview=null;buddy.dirty=false;buddyDrop('status');$('buddyForm').reset();$('buddyMoreDetails').open=false;$('buddyReuseHint').classList.add('hidden');$('buddyCapacity').disabled=false;setBuddyPoint(null);if(typeof resetBuddyCover==='function')resetBuddyCover();$('buddyDraftMsg').textContent='';$('buddyDiscardDraft').classList.add('hidden');renderOwnBuddy();}
async function withdrawActivity(id){if(!confirm('撤下这条状态？已有约定和聊天记录会保留。'))return;await api(`/api/activities/${id}`,{method:'DELETE'});if(buddy.editId===id)newActivity();await loadOwnBuddy();}

function setBuddyPoint(point){buddy.point=point;$('buddyPoint').textContent=point?`已选地图位置：${point.latitude.toFixed(4)}, ${point.longitude.toFixed(4)}`:'未添加地图位置，可直接填写场地发布。';$('buddyClearPoint').classList.toggle('hidden',!point);}
function buddyCard(row){
  return campusActivityCard(row);
}
function renderBuddyStatuses(){
  if(typeof updateDiscoveryFilterSummary==='function')updateDiscoveryFilterSummary();
  const filtered=$('buddyFilter').value||$('buddyTimeFilter').value||$('buddyPeriodFilter').value||$('buddyLevelFilter').value||$('buddyPlaceFilter').value;
  $('buddyList').innerHTML=buddy.rows.map(buddyCard).join('')||`<div class="empty"><svg class="empty-runners" aria-hidden="true"><use href="#icon-buddies"/></svg><b>${filtered?'暂时没有符合条件的搭子':'还没有运动状态'}</b>${filtered?'换个项目或时间试试。':'发出第一份邀请，让同伴找到你。'}<div class="actions empty-actions"><button type="button" class="ghost" ${filtered?'data-clear-filters':'data-buddy-tab="mine"'}>${filtered?'清除筛选':'发布我的状态'}</button></div></div>`;
  if(buddy.layer){buddy.layer.clearLayers();for(const row of buddy.rows){if(row.latitude==null||row.longitude==null)continue;L.circleMarker([row.latitude,row.longitude],{radius:9,color:row.user_id===state.user?.id?'#b76b28':'#185c45',fillOpacity:.8}).addTo(buddy.layer).bindPopup(buddyCard(row));}}
  document.querySelectorAll('[data-filter-sport]').forEach(b=>{b.classList.toggle('selected',b.dataset.filterSport===$('buddyFilter').value.trim());b.setAttribute('aria-pressed',String(b.dataset.filterSport===$('buddyFilter').value.trim()));});
}
async function loadBuddyStatuses(append=false){
  clearTimeout(buddy.searchTimer);const epoch=state.epoch,request=++buddy.listRequest;
  const query=new URLSearchParams({keyword:$('buddyFilter').value.trim(),sort:$('buddySort').value,offset:append?buddy.rows.length:0,scope:$('buddyScope').value,place:$('buddyPlaceFilter').value.trim(),level:$('buddyLevelFilter').value,period:$('buddyPeriodFilter').value,utc_offset:-new Date().getTimezoneOffset()});
  if($('buddyTimeFilter').value)query.set('on_date',$('buddyTimeFilter').value);
  $('buddyListMsg').textContent='正在寻找运动搭子…';$('buddyList').setAttribute('aria-busy','true');
  try{const rows=await api(`/api/activities?${query}`);if(epoch!==state.epoch||request!==buddy.listRequest)return;
    buddy.rows=append?[...buddy.rows,...rows]:rows;renderBuddyStatuses();$('buddyMore').classList.toggle('hidden',rows.length<30);$('buddyListMsg').textContent=`${buddy.rows.length} 条状态 · ${$('buddySort').value==='rating'?'评分优先':'时间最近'}${$('buddyPeriodFilter').value&&!$('buddyTimeFilter').value?' · 今天起五天':''}`;
  }catch(e){if(epoch===state.epoch&&request===buddy.listRequest)$('buddyListMsg').textContent=e.message;}
  finally{if(request===buddy.listRequest)$('buddyList').removeAttribute('aria-busy');}
}
function previewBuddy(){
  if(!$('buddyForm').reportValidity())return;
  const date=new Date($('buddyTime').value);if(!Number.isFinite(date.getTime())||date<=new Date()){$('buddyFormMsg').textContent='请选择未来的运动时间。';return;}
  buddy.preview={exercise_type:$('buddySport').value.trim(),location:$('buddyPlace').value.trim(),starts_at:date.toISOString(),note:$('buddyNote').value.trim(),latitude:buddy.point?.latitude??null,longitude:buddy.point?.longitude??null,duration:Number($('buddyDuration').value),capacity:Number($('buddyCapacity').value),level:$('buddyLevel').value};
  if(!buddy.preview.exercise_type||!buddy.preview.location){$('buddyFormMsg').textContent='请填写运动项目和场地。';return;}
  $('buddyPreview').innerHTML=`<span class="pill">${buddy.preview.capacity>2?`${buddy.preview.capacity} 人组局`:'找一位同伴'}</span><h3>${escapeHTML(buddy.preview.exercise_type)}</h3><p>${escapeHTML(buddyTime(buddy.preview.starts_at))} · ${buddy.preview.duration} 分钟</p><p>⌖ ${escapeHTML(buddy.preview.location)}</p><p class="fine">水平：${escapeHTML(buddy.preview.level)}</p>${buddy.preview.note?`<p class="preview-note">${escapeHTML(buddy.preview.note)}</p>`:''}<p class="fine">${buddy.point?'已附地图位置':'按上方文字地点集合'}</p>`;
  const cover=typeof buddyCover!=='undefined'?(buddyCover.objectURL||(!buddyCover.remove&&buddyCover.url)):null;if(cover){const img=document.createElement('img');img.className='preview-cover';img.src=cover;img.alt='待发布的活动封面';$('buddyPreview').prepend(img);}
  $('buddyPreviewMsg').textContent='';$('buddyPreviewDialog').showModal();
}
async function publishBuddy(){await busy($('buddyConfirmPublish'),async()=>{
  const epoch=state.epoch,payload=JSON.stringify(buddy.preview);
  if(!buddy.editId||buddy.savedPreview!==payload){const row=await api(buddy.editId?`/api/activities/${buddy.editId}`:'/api/activities',{method:buddy.editId?'PUT':'POST',body:payload});if(epoch!==state.epoch)return;buddy.editId=row.id;buddy.savedPreview=payload;$('buddyCapacity').disabled=true;buddyStore('status',ownFields());}
  // Keep the selected file and saved activity id intact while a cover upload is pending.
  buddy.dirty=true;
  try{if(typeof saveBuddyCover==='function')await saveBuddyCover(buddy.editId);}catch(e){if(epoch===state.epoch){await loadOwnBuddy().catch(()=>{});if(epoch!==state.epoch)return;$('buddyDraftMsg').textContent='状态已经公开，封面尚未保存；保留此页面可重试上传。';throw new Error(`状态已发布，但图片未保存：${e.message} 再次点击确认发布可重试，不会重复创建活动。`);}return;}
  if(epoch!==state.epoch)return;
  newActivity();await loadOwnBuddy();$('buddyPreviewDialog').close();$('buddyFormMsg').textContent='状态已公开，等一个一起出发的同伴。';celebrate($('buddyOwnStatus'));notify('运动邀请已发布');
  if(typeof homeDiscoveryRefresh==='function')homeDiscoveryRefresh();
},'buddyPreviewMsg');}
async function removeBuddy(){if(buddy.editId)await withdrawActivity(buddy.editId);}

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

async function updateBuddyUnread(){const epoch=state.epoch,d=await api('/api/buddy-chats/unread');if(epoch!==state.epoch)return;if(typeof notifications!=='undefined'){notifications.privateCount=d.count;renderUnread();}}
function renderBuddyChats(){
  renderMessageSelf();$('messageConversationCount').textContent=buddy.chats.length?`${buddy.chats.length} 个会话`:'';
  const signature=JSON.stringify(buddy.chats);if($('buddyChats').dataset.signature===signature)return;$('buddyChats').dataset.signature=signature;
  $('buddyChats').innerHTML=buddy.chats.map(c=>`<button type="button" class="buddy-chat-choice chat-list-row ${c.unread_count?'has-unread':''}" data-buddy-chat="${c.id}"><span class="chat-list-avatar">${chatAvatar(c)}${c.unread_count?`<span class="unread-badge">${c.unread_count>99?'99+':c.unread_count}</span>`:''}</span><span class="chat-list-content"><span class="chat-meta"><strong>${escapeHTML(chatName(c))}</strong><small>${c.last_at?escapeHTML(chatListTime(c.last_at)):''}</small></span><small class="chat-preview">${c.blocked?'当前不可互动 · ':''}${escapeHTML(c.last_message||'打个招呼，一起约运动吧')}</small></span></button>`).join('')||'<div class="empty message-empty"><span aria-hidden="true">☏</span><b>下一场运动，从一句问候开始</b><p>找到合拍的同学，一起聊聊想玩的运动。</p><button type="button" class="ghost" data-go="buddies">去认识运动搭子 →</button></div>';
}
function renderMessageSelf(){if(!state.user)return;const person={...state.user,...(campus.profile||{})},signature=JSON.stringify([chatName(person),person.avatar_url]);if($('messageSelfAvatar').dataset.identity===signature)return;$('messageSelfAvatar').innerHTML=chatAvatar(person);$('messageSelfAvatar').dataset.identity=signature;}
function chatName(person){return person?.display_name||person?.username||'运动伙伴';}
function chatListTime(value){const d=new Date(value);return localDate(d)===localDate()?d.toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}):d.toLocaleDateString('zh-CN',{month:'numeric',day:'numeric'});}
function chatAvatar(person){const name=chatName(person);return `<span class="chat-avatar" title="${escapeHTML(name)}"><span class="chat-avatar-fallback" aria-hidden="true">${escapeHTML(Array.from(name)[0]||'同')}</span>${avatarPhotoMarkup(person,true)}</span>`;}
function updateChatHeading(person){const signature=JSON.stringify([chatName(person),person?.avatar_url,person?.identity_hidden]);if($('buddyChatAvatar').dataset.identity!==signature){$('buddyChatAvatar').innerHTML=chatAvatar(person);$('buddyChatAvatar').dataset.identity=signature;}$('buddyChatTitle').textContent=chatName(person);$('buddyChatTopic').textContent=person?.topic||'聊聊时间和集合地点';}
function updateMessageIdentity(box,person,userId){if(!person)return;for(const row of box.querySelectorAll(`[data-sender="${userId}"]`)){const signature=JSON.stringify([chatName(person),person.avatar_url,person.identity_hidden]);if(row.dataset.identity===signature)continue;row.querySelector('.chat-avatar')?.remove();row.insertAdjacentHTML('afterbegin',chatAvatar(person));row.dataset.identity=signature;const label=row.querySelector('.message-sender');if(label)label.textContent=chatName(person);}}
async function loadBuddyChats(append=false){
  const epoch=state.epoch,rows=await api(`/api/buddy-chats?offset=${append?buddy.chats.length:0}`);if(epoch!==state.epoch)return;
  const byId=new Map(buddy.chats.map(c=>[c.id,c]));for(const row of rows)byId.set(row.id,row);buddy.chats=[...byId.values()].sort((a,b)=>b.last_id-a.last_id||b.id-a.id);renderBuddyChats();
  if(append||buddy.chats.length<=100)$('buddyChatsMore').classList.toggle('hidden',rows.length<100);
  const selected=buddy.chats.find(c=>c.id===buddy.chatId);if(selected){$('buddySend').disabled=selected.blocked||$('buddyMessage').disabled;updateChatHeading(selected);updateMessageIdentity($('buddyMessages'),selected,selected.user_id);}
}
async function openBuddyChat(id){
  if(!buddy.active||buddy.tab!=='messages')return;
  if(buddy.chatId===id)return;loadPinnedMeetup(id).catch(()=>{});
  const epoch=state.epoch,request=++buddy.chatRequest;buddy.chatId=id;buddy.after=0;buddy.before=0;buddy.readAfter=0;
  $('buddyMessages').replaceChildren();$('buddyMessage').value=buddyRead(`chat:${id}`)||'';resizeBuddyComposer();$('buddyChatMsg').textContent='正在加载消息…';$('buddyNewMessages').classList.add('hidden');
  const c=buddy.chats.find(c=>c.id===id);updateChatHeading(c);$('buddySend').disabled=!!c?.blocked;
  const rows=await api(`/api/buddy-chats/${id}/messages?latest=true&limit=50`);if(epoch!==state.epoch||request!==buddy.chatRequest||id!==buddy.chatId)return;
  $('buddyMessage').disabled=!!c?.blocked;$('buddySend').disabled=!!c?.blocked;
  appendBuddyMessages(rows);$('buddyOlder').classList.toggle('hidden',rows.length<50);$('buddyMessages').scrollTop=$('buddyMessages').scrollHeight;$('buddyChatMsg').textContent=c?.blocked?'当前无法互动，可在“我的”中管理黑名单。':'';await markBuddyRead();
}
function messageNode(row,group=false){const mine=row.sender_id===state.user.id,item=document.createElement('div');item.className=`buddy-message ${mine?'mine':''}`;item.dataset.message=String(row.id);item.dataset.sender=String(row.sender_id);item.dataset.identity=JSON.stringify([chatName(row),row.avatar_url,row.identity_hidden]);item.innerHTML=chatAvatar(row);const body=document.createElement('div');body.className='message-body';if(group&&!mine){const name=document.createElement('strong');name.className='message-sender';name.textContent=chatName(row);body.append(name);}const bubble=document.createElement('div');bubble.className='message-bubble';const p=document.createElement('p');p.textContent=row.body;bubble.append(p);const t=document.createElement('small');t.className='message-time';t.textContent=chatListTime(row.created_at);t.title=buddyTime(row.created_at);body.append(bubble,t);item.append(body);return item;}
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
  try{await updateBuddyUnread();if(typeof checkNotifications==='function')await checkNotifications();if(buddy.active&&buddy.tab==='messages'){await loadBuddyChats();if(buddy.chatId){await loadBuddyMessages();await loadPinnedMeetup(buddy.chatId);}else await loadMeetups();}if(buddy.own)renderOwnBuddy();if(buddy.active&&buddy.tab==='group')await pollGroup();}
  catch(e){if(state.user&&buddy.active)$('buddyChatsMsg').textContent=e.message;}
  finally{if(epoch===state.epoch)buddy.loading=false;}
}
async function sendBuddyMessage(){if(!$('buddyMessageForm').reportValidity()||!buddy.chatId)return;await busy($('buddySend'),async()=>{
  const epoch=state.epoch,id=buddy.chatId,body=$('buddyMessage').value;await api(`/api/buddy-chats/${id}/messages`,{method:'POST',body:JSON.stringify({body})});if(epoch!==state.epoch)return;
  if(buddyRead(`chat:${id}`)===body)buddyDrop(`chat:${id}`);
  if(id===buddy.chatId){if($('buddyMessage').value===body)$('buddyMessage').value='';resizeBuddyComposer();$('buddyChatMsg').textContent='';$('buddyMessages').scrollTop=$('buddyMessages').scrollHeight;await loadBuddyMessages();}await loadBuddyChats();
},'buddyChatMsg');}
function selectedBuddy(){return buddy.chats.find(c=>c.id===buddy.chatId);}
async function openRating(){const c=selectedBuddy();if(!c)return;await busy($('buddyRate'),async()=>{const epoch=state.epoch,d=await api(`/api/buddies/${c.user_id}/rating`);if(epoch!==state.epoch)return;$('buddyRatingDialog').dataset.user=String(c.user_id);$('buddyScore').value=String(d.my_score||5);$('buddySaveRating').disabled=!d.can_rate;$('buddyRatingSummary').textContent=d.rating==null?'这位搭子还没有评分。':`当前 ${d.rating.toFixed(1)} 分 · ${d.rating_count} 人评价`;$('buddyRatingMsg').textContent=d.can_rate?'': '双方确认完成同一次运动后才可评分，黑名单状态下不可评分。';$('buddyRatingDialog').showModal();},'buddyChatMsg');}
async function saveRating(){await busy($('buddySaveRating'),async()=>{const epoch=state.epoch;await api(`/api/buddies/${$('buddyRatingDialog').dataset.user}/rating`,{method:'PUT',body:JSON.stringify({score:Number($('buddyScore').value)})});if(epoch!==state.epoch)return;$('buddyRatingDialog').close();notify('评分已保存，谢谢你的反馈');},'buddyRatingMsg');}
async function blockBuddy(){const c=selectedBuddy();if(!c||!confirm(`将 ${c.username} 加入黑名单？双方将无法继续发消息。`))return;await busy($('buddyBlock'),async()=>{const epoch=state.epoch;await api(`/api/buddy-blocks/${c.user_id}`,{method:'PUT'});if(epoch!==state.epoch)return;await loadBuddyChats();$('buddyChatMsg').textContent='已加入黑名单，可在“我的”中解除。';},'buddyChatMsg');}
async function loadBlocks(){const epoch=state.epoch,rows=await api('/api/buddy-blocks');if(epoch!==state.epoch)return;$('buddyBlocks').innerHTML=rows.map(r=>`<div class="record-main record-item"><strong>${escapeHTML(r.username)}</strong><button type="button" class="ghost" data-unblock="${r.user_id}">解除拉黑</button></div>`).join('')||'<p class="fine">你的黑名单为空。</p>';}
function celebrate(el){el.classList.remove('success-pop');void el.offsetWidth;el.classList.add('success-pop');}

$('buddyForm').addEventListener('submit',e=>{e.preventDefault();previewBuddy();});
$('buddyForm').addEventListener('input',saveBuddyDraft);
$('buddyPlace').addEventListener('input',()=>{setBuddyPoint(null);$('buddyReuseHint').classList.add('hidden');});
$('buddyFilterForm').addEventListener('submit',e=>{e.preventDefault();busy($('buddyFilterApply'),()=>loadBuddyStatuses(),'buddyListMsg');});
$('buddyMessageForm').addEventListener('submit',e=>{e.preventDefault();sendBuddyMessage();});
function resizeBuddyComposer(){const input=$('buddyMessage'),box=$('buddyMessages'),bottom=box.scrollHeight-box.scrollTop-box.clientHeight<50;input.style.height='44px';input.style.height=`${Math.min(112,Math.max(44,input.scrollHeight))}px`;if(bottom)box.scrollTop=box.scrollHeight;}
$('buddyMessage').addEventListener('input',()=>{if(buddy.chatId)buddyStore(`chat:${buddy.chatId}`,$('buddyMessage').value);resizeBuddyComposer();});
$('buddyMessages').addEventListener('scroll',()=>markBuddyRead().catch(()=>{}));
$('buddyRatingForm').addEventListener('submit',e=>{e.preventDefault();saveRating();});
const buddyActions={buddyConfirmPublish:publishBuddy,buddyCancelPreview:()=>$('buddyPreviewDialog').close(),buddyRemove:removeBuddy,
  buddyDiscardDraft:()=>{if(confirm('放弃尚未公开的修改？'))newActivity();},buddyNewStatus:()=>{newActivity();$('buddyFormTitle').scrollIntoView({block:'start'});},buddyReusePlace:reuseLastPlace,
  buddyListView:()=>showBuddyMap(false),buddyMapView:()=>showBuddyMap(true),buddyMapRetry:()=>useBuddyTiles(true),buddyPickPoint:openPointPicker,
  buddyClearPoint:()=>{setBuddyPoint(null);saveBuddyDraft();},buddyCancelPoint:()=>$('buddyMapDialog').close(),buddyConfirmPoint:()=>{setBuddyPoint(buddy.pickerPoint);saveBuddyDraft();$('buddyMapDialog').close();},
  buddyMore:()=>busy($('buddyMore'),()=>loadBuddyStatuses(true),'buddyListMsg'),buddyChatsMore:()=>busy($('buddyChatsMore'),()=>loadBuddyChats(true),'buddyChatsMsg'),
  buddyChatBack:()=>buddyRoute('messages'),buddyChatRefresh:pollBuddyChat,buddyOlder:loadOlderMessages,
  buddyNewMessages:()=>{$('buddyMessages').scrollTop=$('buddyMessages').scrollHeight;markBuddyRead().catch(()=>{});},
  buddyRate:openRating,buddyBlock:blockBuddy,buddyCloseRating:()=>$('buddyRatingDialog').close(),loadBlocks:()=>busy($('loadBlocks'),loadBlocks,'buddyBlocksMsg')};
for(const [id,fn] of Object.entries(buddyActions))$(id).addEventListener('click',fn);
$('buddyMapDialog').addEventListener('close',closePointPicker);
$('buddyChatMenu').addEventListener('click',event=>{if(event.target.closest('button'))$('buddyChatMenu').open=false;});
document.addEventListener('click',event=>{if(!$('buddyChatMenu').contains(event.target))$('buddyChatMenu').open=false;});
$('buddyOtherSport').addEventListener('click',()=>{$('buddyCustomFilter').classList.remove('hidden');$('buddyFilterApply').classList.remove('hidden');$('buddyFilter').focus();});
for(const id of ['buddyTimeFilter','buddySort','buddyScope','buddyLevelFilter'])$(id).addEventListener('change',()=>{if(!$('buddyFilterDialog').open)loadBuddyStatuses().catch(e=>$('buddyListMsg').textContent=e.message);});
$('page-buddies').addEventListener('click',e=>{
  const b=e.target.closest('button');if(!b)return;
  if(b.dataset.buddyTab)buddyRoute(b.dataset.buddyTab);
  if(b.dataset.buddyChat)buddyRoute('messages',Number(b.dataset.buddyChat));
  if(b.dataset.buddyUser)busy(b,async()=>{const epoch=state.epoch,c=await api(`/api/buddies/${b.dataset.buddyUser}/chat`,{method:'POST'});if(epoch===state.epoch)buddyRoute('messages',c.id);},'buddyListMsg');
  if('filterSport' in b.dataset){$('buddyFilter').value=b.dataset.filterSport;busy(b,()=>loadBuddyStatuses(),'buddyListMsg');}
  if('clearFilters' in b.dataset){$('buddyFilterForm').reset();resetDiscoveryFilters();busy(b,()=>loadBuddyStatuses(),'buddyListMsg');}
  if(b.dataset.buddySport){$('buddySport').value=b.dataset.buddySport;saveBuddyDraft();}
  if(b.dataset.buddyPlace){$('buddyPlace').value=b.dataset.buddyPlace;setBuddyPoint(null);saveBuddyDraft();}
  if('buddyDay' in b.dataset){const date=new Date();if(b.dataset.buddyDay==='weekend')date.setDate(date.getDate()+((6-date.getDay()+7)%7));else date.setDate(date.getDate()+Number(b.dataset.buddyDay));const existing=$('buddyTime').value.slice(11)||'18:00';$('buddyTime').value=`${localDate(date)}T${existing}`;saveBuddyDraft();}
});
$('buddyBlocks').addEventListener('click',e=>{const b=e.target.closest('[data-unblock]');if(b)busy(b,async()=>{const epoch=state.epoch;await api(`/api/buddy-blocks/${b.dataset.unblock}`,{method:'DELETE'});if(epoch!==state.epoch)return;await loadBlocks();notify('已移出黑名单');},'buddyBlocksMsg');});
$('buddyLocate').addEventListener('click',()=>{if(!navigator.geolocation){$('buddyMapMsg').textContent='浏览器不支持定位，可手动拖动地图。';return;}const epoch=state.epoch;$('buddyMapMsg').textContent='正在定位，仅移动视野，不公开当前位置。';navigator.geolocation.getCurrentPosition(p=>{if(epoch!==state.epoch)return;buddy.map?.setView([p.coords.latitude,p.coords.longitude],15);$('buddyMapMsg').textContent='已移动视野，点击地图选点或返回使用文字地点。';},()=>{if(epoch===state.epoch)$('buddyMapMsg').textContent='定位不可用，可手动选点，或使用文字地点发布。';},{timeout:10000,maximumAge:60000});});

$('buddyMessage').addEventListener('focus',()=>document.body.classList.add('chat-typing'));
$('buddyMessage').addEventListener('blur',()=>setTimeout(()=>{if(document.activeElement!==$('buddyMessage'))document.body.classList.remove('chat-typing');},180));
