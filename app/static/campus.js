const campus={profile:null,meetings:[],meeting:null,request:0,groupAfter:0,groupBefore:0,groupLoading:false,formMeeting:null,repeatMeeting:null,repeatRequest:null,cancelMeeting:null,report:null,adminId:null,adminRows:[],boatSeen:{}};
const meetingLabels={pending:'待回应',confirmed:'已约好',completed:'已完成',cancelled:'已取消',declined:'未接受',expired:'已过期'};
function resetCampus(){campus.request++;delete $('groupChats').dataset.signature;Object.assign(campus,{profile:null,meetings:[],meeting:null,groupAfter:0,groupBefore:0,groupLoading:false,formMeeting:null,repeatMeeting:null,repeatRequest:null,cancelMeeting:null,report:null,adminRows:[],boatSeen:{}});for(const id of ['meetupList','meetupDetail','groupMessages','pinnedMeetup','groupChats','noticeList','adminReports','myReports'])$(id).replaceChildren();for(const id of ['meetupFormDialog','repeatMeetupDialog','cancelMeetupDialog','reportDialog','adminDialog'])if($(id).open)$(id).close();$('adminPanel').classList.add('hidden');$('profileSchool').value='湘潭大学';}
function applyTheme(choice){const actual=choice==='system'?(matchMedia('(prefers-color-scheme:dark)').matches?'night':'forest'):choice;document.documentElement.dataset.theme=actual;document.querySelector('meta[name="theme-color"]').content={forest:'#185c45',ocean:'#245f9b',lilac:'#70529a',night:'#132322'}[actual]||'#185c45';try{localStorage.setItem('campus-theme',choice);}catch{}document.querySelectorAll('[data-theme-choice]').forEach(b=>{const active=b.dataset.themeChoice===choice;b.classList.toggle('selected',active);b.setAttribute('aria-pressed',String(active));});}
let profileQueue=Promise.resolve(),themeIntent=0;
async function loadCampus(){const epoch=state.epoch;campus.profileReady=api('/api/profile');const profile=await campus.profileReady;if(epoch!==state.epoch)return;campus.profile=profile;$('profileSchool').value=profile.school;$('campusLabel').textContent=`${profile.school} · 一起运动`;$('completedCount').textContent=`已完成 ${profile.completed} 次约定`;$('adminPanel').classList.toggle('hidden',!profile.is_admin);applyTheme(profile.theme);if(typeof renderIdentity==='function')renderIdentity(profile,true);await loadMeetups();}
function saveProfilePatch(patch){
  const epoch=state.epoch;
  const task=profileQueue.catch(()=>{}).then(async()=>{
    await campus.profileReady;
    if(epoch!==state.epoch)return null;
    const saved=await api('/api/profile',{method:'PUT',body:JSON.stringify({school:campus.profile.school,theme:campus.profile.theme,...patch})});
    if(epoch!==state.epoch)return null;
    Object.assign(campus.profile,saved);if(typeof renderProfileOverview==='function')renderProfileOverview();return saved;
  });
  profileQueue=task;return task;
}
async function saveTheme(choice){const epoch=state.epoch,intent=++themeIntent;applyTheme(choice);$('themeMsg').textContent='正在保存主题…';try{await saveProfilePatch({theme:choice});if(epoch===state.epoch&&intent===themeIntent)$('themeMsg').textContent='主题已保存。';}catch(e){if(epoch===state.epoch&&intent===themeIntent){applyTheme(campus.profile?.theme||'forest');$('themeMsg').textContent=e.message;}}}
async function refreshCampusStats(){const epoch=state.epoch,p=await api('/api/profile');if(epoch!==state.epoch)return;$('completedCount').textContent=`已完成 ${p.completed} 次约定`;$('adminPanel').classList.toggle('hidden',!p.is_admin);if(campus.profile)Object.assign(campus.profile,{completed:p.completed,is_admin:p.is_admin});if(typeof renderProfileOverview==='function')renderProfileOverview();}
function refreshBuddyDates(){const today=new Date(),options=[{value:'',name:'不限',date:'日期'}];for(let i=0;i<5;i++){const d=new Date(today);d.setDate(d.getDate()+i);options.push({value:localDate(d),name:i===0?'今天':i===1?'明天':d.toLocaleDateString('zh-CN',{weekday:'short'}),date:`${d.getMonth()+1}.${d.getDate()}`});}if(!options.some(o=>o.value===$('buddyTimeFilter').value))$('buddyTimeFilter').value='';$('buddyDates').innerHTML=options.map(o=>`<button type="button" data-filter-date="${o.value}" aria-pressed="${o.value===$('buddyTimeFilter').value}" class="${o.value===$('buddyTimeFilter').value?'selected':''}"><strong>${o.name}</strong><small>${o.date}</small></button>`).join('');}
function syncPeriodButtons(){document.querySelectorAll('[data-period]').forEach(b=>{const active=b.dataset.period===$('buddyPeriodFilter').value;b.classList.toggle('selected',active);b.setAttribute('aria-pressed',String(active));});}
function scheduleSearch(){if($('buddyFilterDialog')?.open)return;clearTimeout(buddy.searchTimer);buddy.listRequest++;$('buddyListMsg').textContent='正在匹配项目…';buddy.searchTimer=setTimeout(()=>loadBuddyStatuses(),280);}
function meetupSportIcon(sport){
  const name=String(sport||'').toLowerCase();
  if(name.includes('羽毛球'))return '🏸';
  if(name.includes('篮球'))return '🏀';
  if(name.includes('足球'))return '⚽';
  if(name.includes('乒乓'))return '🏓';
  if(name.includes('网球'))return '🎾';
  if(name.includes('排球'))return '🏐';
  if(name.includes('游泳'))return '🏊';
  if(name.includes('跑步'))return '🏃';
  if(name.includes('骑行'))return '🚴';
  if(name.includes('健身'))return '🏋️';
  if(name.includes('瑜伽'))return '🧘';
  return '🏅';
}
function meetupProgress(m,active){
  if(m.kind!=='group')return '';
  const capacity=Math.max(1,Number(m.capacity)||1);
  const joined=Math.min(capacity,active.length);
  const percent=Math.round(joined/capacity*100);
  const remaining=Math.max(0,capacity-joined);
  return `<div class="meetup-progress" aria-label="组队进度 ${joined}/${capacity} 人">
    <div class="meetup-progress-track">
      <span class="meetup-progress-fill" style="width:${percent}%"></span>
      <span class="meetup-progress-icon" style="left:${percent}%" aria-hidden="true">${meetupSportIcon(m.exercise_type)}</span>
    </div>
    <div class="meetup-progress-caption"><span>已加入 ${joined}/${capacity} 人</span><span>${remaining===0?'组队已满':`还差 ${remaining} 人`}</span></div>
  </div>`;
}
function meetingCard(m,detail=false){
  const mine=m.members.find(p=>p.user_id===state.user?.id),others=m.members.filter(p=>p.user_id!==state.user?.id),active=m.members.filter(p=>p.status==='accepted'),future=new Date(m.starts_at)>new Date(),ended=new Date(m.ends_at)<=new Date();
  let buttons='';
  if(['pending','confirmed'].includes(m.state)&&mine?.status==='pending'&&future)buttons=`<button type="button" data-meetup-action="accept" data-meeting-id="${m.id}">接受邀请</button><button type="button" class="ghost" data-meetup-action="decline" data-meeting-id="${m.id}">暂不参加</button>`;
  if(m.state==='confirmed'&&mine?.status==='accepted'&&future)buttons+=`<button type="button" class="ghost" data-change-meetup="${m.id}">提出改约</button>`;
  if(m.state==='confirmed'&&mine?.status==='accepted'&&ended&&!mine.attended)buttons+=`<button type="button" data-meetup-action="attend" data-meeting-id="${m.id}">确认我已参加</button>`;
  if(['pending','confirmed'].includes(m.state)&&['pending','accepted'].includes(mine?.status)&&!(m.kind==='group'&&mine?.status==='pending')&&!ended)buttons+=`<button type="button" class="text-button" data-cancel-meetup="${m.id}">${m.kind==='group'&&m.owner_id!==state.user.id?'退出组局':'取消约定'}</button>`;
  if(canRepeatMeeting(m))buttons+=`<button type="button" data-repeat-meetup="${m.id}">再约一场</button>`;
  let proposal='';if(m.proposal){proposal=`<div class="change-proposal"><strong>待确认的改约</strong><p>${escapeHTML(buddyTime(m.proposal.starts_at))} · ${m.proposal.duration} 分钟<br>${escapeHTML(m.proposal.location)}</p><small>原约定继续有效，所有参与者同意后变更。</small>${mine?.status==='accepted'&&!mine.voted?`<div class="actions"><button type="button" data-meetup-action="accept_change" data-meeting-id="${m.id}">同意改约</button><button type="button" class="ghost" data-meetup-action="reject_change" data-meeting-id="${m.id}">保留原安排</button></div>`:'<p class="fine">你已同意，等待其他参与者确认。</p>'}</div>`;}
  const cancelled=m.cancel_reason?`<p class="cancel-note">${m.late_cancel?'临时取消':'提前取消'}：${escapeHTML(m.cancel_reason)}</p>`:'';
  return `<article class="card meetup-card"><div class="section-head"><span class="pill ${m.state==='completed'?'completed':''}">${meetingLabels[m.state]||m.state}${m.kind==='group'?` · ${active.length}/${m.capacity} 人`:''}</span>${!detail?`<button type="button" class="text-button" data-open-meetup="${m.id}">详情 ↗</button>`:''}</div><h2>${escapeHTML(m.exercise_type)}</h2>${meetupProgress(m,active)}<p class="buddy-date">${escapeHTML(buddyTime(m.starts_at))} · ${m.duration} 分钟</p><p class="record-detail">⌖ ${escapeHTML(m.location)}</p><p class="fine">${m.kind==='group'?'组局伙伴':'一起运动'}：${escapeHTML(active.map(p=>chatName(p)).join('、'))}${m.members.some(p=>p.status==='pending')&&future?` · 等待 ${escapeHTML(m.members.filter(p=>p.status==='pending').map(p=>chatName(p)).join('、'))} 回应`:''}</p>${m.state==='confirmed'&&ended?`<p class="confirmation-note">${mine?.attended?'你已确认参加，等待同伴确认。':'运动时间已结束，请按实际情况确认参加。'} ${active.filter(p=>p.attended).length}/${active.length} 人已确认</p>`:''}${cancelled}${proposal}<div class="actions">${buttons}</div>${detail?`<details class="member-details"><summary>参与者与记录</summary>${m.members.map(p=>`<div class="member-row"><div><strong>${escapeHTML(chatName(p))}${p.user_id===state.user.id?' · 我':''}</strong><p class="fine">${p.status==='cancelled'?`${p.late_cancel?'临时':'提前'}退出：${escapeHTML(p.cancel_reason)}`:p.attended?'已确认参加':p.status==='pending'?'待回应':p.status==='declined'?'未接受邀请':'尚未确认参加'}</p></div>${p.user_id!==state.user.id?`<div class="actions">${m.state==='completed'&&p.attended?`<button type="button" class="text-button" data-rate-user="${p.user_id}">评价</button>`:''}<button type="button" class="text-button" data-report-member="${p.user_id}" data-meeting-id="${m.id}">举报</button></div>`:''}</div>`).join('')}</details>`:''}</article>`;
}
async function loadMeetups(append=false){const epoch=state.epoch,rows=await api(`/api/meetups?offset=${append?campus.meetings.length:0}`);if(epoch!==state.epoch)return;campus.meetings=append?[...campus.meetings,...rows]:rows;renderMeetups();$('moreMeetups').classList.toggle('hidden',rows.length<30);}
function renderMeetups(){
  const sorted=[...campus.meetings].sort((a,b)=>{const active=m=>['pending','confirmed'].includes(m.state)&&new Date(m.ends_at)>new Date();return Number(active(b))-Number(active(a))||(active(a)?new Date(a.starts_at)-new Date(b.starts_at):new Date(b.starts_at)-new Date(a.starts_at));});
  $('meetupList').innerHTML=sorted.map(m=>meetingCard(m)).join('')||'<div class="card empty"><b>还没有运动约定</b>从搭子聊天中发出邀请，或加入一个多人组局。<button type="button" class="ghost" data-go="buddies">去找搭子 →</button></div>';
  const next=sorted.find(m=>m.state==='confirmed'&&new Date(m.starts_at)>new Date()&&m.members.some(p=>p.user_id===state.user.id&&p.status==='accepted'));
  $('nextMeetupCard').classList.toggle('hidden',!next);
  $('nextMeetup').innerHTML=next?`<div class="next-meetup-body"><div><h2>${escapeHTML(next.exercise_type)}</h2><p>${escapeHTML(buddyTime(next.starts_at))}</p><p class="fine">${escapeHTML(next.location)}</p></div><button type="button" data-open-meetup="${next.id}">查看约定 ↗</button></div>`:'';
  const groups=sorted.filter(m=>m.kind==='group'),groupSignature=JSON.stringify(groups);
  if($('groupChats').dataset.signature!==groupSignature){$('groupChats').dataset.signature=groupSignature;$('groupChats').innerHTML=groups.map(m=>`<button type="button" class="buddy-chat-choice group-chat-choice chat-list-row" data-open-meetup="${m.id}"><span class="chat-group-avatar" aria-hidden="true">${m.members.filter(p=>p.status==='accepted').slice(0,4).map(p=>chatAvatar(p)).join('')||'<span>群</span>'}</span><span class="chat-list-content"><span class="chat-meta"><strong>${escapeHTML(m.exercise_type)}组局</strong><span class="chat-group-label">群聊</span></span><small class="chat-preview">${escapeHTML(m.location)} · ${meetingLabels[m.state]}</small></span></button>`).join('');
  }
  $('messageGroupHeading').classList.toggle('hidden',!groups.length);
  if(typeof renderProfileOverview==='function')renderProfileOverview();
}
async function loadPinnedMeetup(chatId){const epoch=state.epoch,rows=await api(`/api/meetups?chat_id=${chatId}`);if(epoch!==state.epoch||buddy.chatId!==chatId)return;for(const m of rows){const i=campus.meetings.findIndex(x=>x.id===m.id);if(i<0)campus.meetings.push(m);else campus.meetings[i]=m;}const m=[...rows].sort((a,b)=>new Date(a.starts_at)-new Date(b.starts_at)).find(m=>['pending','confirmed'].includes(m.state))||rows[0];$('pinnedMeetup').innerHTML=m?`<button type="button" data-open-meetup="${m.id}"><span class="pill">${meetingLabels[m.state]}</span><span><strong>${escapeHTML(m.exercise_type)}</strong><small>${escapeHTML(buddyTime(m.starts_at))} · ${escapeHTML(m.location)}</small></span><span>›</span></button>${canRepeatMeeting(m)?`<button type="button" class="text-button" data-repeat-meetup="${m.id}">和这位搭子再约一场 →</button>`:''}`:'';}
async function loadMeetup(id){
  const epoch=state.epoch,request=++campus.request;campus.meeting=null;campus.groupAfter=0;campus.groupBefore=0;$('groupMessages').replaceChildren();$('meetupDetail').replaceChildren();$('meetupMsg').textContent='正在读取约定…';$('groupChatPanel').classList.add('hidden');
  const m=await api(`/api/meetups/${id}`);if(epoch!==state.epoch||request!==campus.request||buddy.tab!=='group')return;campus.meeting=m;$('meetupDetail').innerHTML=meetingCard(m,true);$('meetupMsg').textContent='';const group=m.kind==='group'&&m.members.some(p=>p.user_id===state.user.id&&['accepted','cancelled'].includes(p.status));$('groupChatPanel').classList.toggle('hidden',!group);$('groupMessage').value=buddyRead(`group:${id}`)||'';
  if(group){const rows=await api(`/api/meetups/${id}/messages`);if(epoch!==state.epoch||request!==campus.request)return;appendGroupMessages(rows);$('groupOlder').classList.toggle('hidden',rows.length<50);$('groupMessages').scrollTop=$('groupMessages').scrollHeight;updateGroupComposer();}
  if(!document.hidden)await api(`/api/meetups/${id}/read`,{method:'POST'});if(typeof checkNotifications==='function')await checkNotifications();
}
function updateGroupComposer(){const m=campus.meeting,mine=m?.members.find(p=>p.user_id===state.user?.id);$('groupSend').disabled=mine?.status!=='accepted'||['cancelled','declined'].includes(m?.state);$('groupMessage').disabled=$('groupSend').disabled;$('groupMessageMsg').textContent=$('groupSend').disabled?'当前不能发言，已有聊天记录保留。':'';}
function appendGroupMessages(rows,older=false){const box=$('groupMessages'),fragment=document.createDocumentFragment();for(const row of rows){if(box.querySelector(`[data-message="${row.id}"]`))continue;fragment.append(messageNode(row,true));campus.groupAfter=Math.max(campus.groupAfter,row.id);campus.groupBefore=campus.groupBefore?Math.min(campus.groupBefore,row.id):row.id;}if(older)box.prepend(fragment);else box.append(fragment);}
async function pollGroup(){if(campus.groupLoading||!campus.meeting||buddy.tab!=='group')return;campus.groupLoading=true;const epoch=state.epoch,id=campus.meeting.id,request=campus.request;try{const m=await api(`/api/meetups/${id}`);if(epoch!==state.epoch||request!==campus.request)return;const newcomers=newBoatMembers(m);if(newcomers.length)showBoatJoinAnimation(m,newcomers);if(JSON.stringify(m)!==JSON.stringify(campus.meeting)){campus.meeting=m;$('meetupDetail').innerHTML=meetingCard(m,true);}const canRead=m.kind==='group'&&m.members.some(p=>p.user_id===state.user.id&&['accepted','cancelled'].includes(p.status));$('groupChatPanel').classList.toggle('hidden',!canRead);if(canRead){for(const member of m.members)updateMessageIdentity($('groupMessages'),member,member.user_id);const rows=await api(`/api/meetups/${id}/messages?after=${campus.groupAfter}`);if(epoch!==state.epoch||request!==campus.request)return;const box=$('groupMessages'),atBottom=box.scrollHeight-box.scrollTop-box.clientHeight<50;appendGroupMessages(rows);if(atBottom){box.scrollTop=box.scrollHeight;await api(`/api/meetups/${id}/read`,{method:'POST'});}updateGroupComposer();}}finally{if(epoch===state.epoch)campus.groupLoading=false;}}
function findMeeting(id){return campus.meeting?.id===id?campus.meeting:campus.meetings.find(m=>m.id===id);}
function canRepeatMeeting(m){
  const mine=m?.members.find(p=>p.user_id===state.user?.id);
  return m?.state==='completed'&&new Date(m.ends_at)<=new Date()&&mine?.status==='accepted'&&mine.attended
    &&m.members.filter(p=>p.status==='accepted'&&p.attended).length>1;
}
async function openRepeatMeeting(id){
  const epoch=state.epoch,m=await api(`/api/meetups/${id}`);
  if(epoch!==state.epoch)return;
  if(!canRepeatMeeting(m)){notify('完成约定并确认参加后，才能再约一场');return;}
  campus.repeatMeeting=m;
  campus.repeatRequest=Array.from(crypto.getRandomValues(new Uint8Array(16)),n=>n.toString(16).padStart(2,'0')).join('');
  $('repeatMeetupForm').reset();$('repeatSport').textContent=m.exercise_type;
  const d=new Date();d.setDate(d.getDate()+1);const old=new Date(m.starts_at);d.setHours(old.getHours(),old.getMinutes(),0,0);
  $('repeatTime').value=`${localDate(d)}T${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
  $('repeatDuration').value=String(m.duration);$('repeatPlace').value=m.location;
  const people=m.members.filter(p=>p.status==='accepted'&&p.attended&&p.user_id!==state.user.id);
  $('repeatParticipants').innerHTML=people.map(p=>`<span class="repeat-person">${chatAvatar(p)}<span>${escapeHTML(chatName(p))}</span></span>`).join('');
  $('repeatNotice').textContent=m.kind==='group'?'邀请只发给上次实际参加的同伴，每个人需要重新确认。':'沿用这位搭子与运动项目，确认新的时间和地点后发送邀请。';
  $('repeatMsg').textContent='';$('repeatMeetupDialog').showModal();
}
async function submitRepeatMeeting(){
  if(!$('repeatMeetupForm').reportValidity()||!campus.repeatMeeting)return;
  await busy($('repeatSubmit'),async()=>{
    const epoch=state.epoch,m=campus.repeatMeeting,date=new Date($('repeatTime').value);
    if(!Number.isFinite(date.getTime())||date<=new Date())throw new Error('请选择未来的运动时间。');
    const payload={starts_at:date.toISOString(),duration:Number($('repeatDuration').value),location:$('repeatPlace').value.trim(),request_id:campus.repeatRequest};
    const result=await withConflict(`/api/meetups/${m.id}/repeat`,payload);
    if(epoch!==state.epoch)return;
    $('repeatMeetupDialog').close();campus.repeatMeeting=null;campus.repeatRequest=null;
    await refreshMeetingResult(result);
    navigate(result.kind==='pair'?`messages/${result.chat_id}`:`buddies/group/${result.id}`);
    notify('新邀请已发出，等待同伴确认');
  },'repeatMsg');
}
async function withConflict(url,payload){try{return await api(url,{method:'POST',body:JSON.stringify(payload)});}catch(e){if(e.detail?.conflicts&&confirm(e.detail.message))return api(url,{method:'POST',body:JSON.stringify({...payload,allow_conflict:true})});throw e;}}
async function refreshMeetingResult(m){if(campus.meeting?.id===m.id){campus.meeting=m;$('meetupDetail').innerHTML=meetingCard(m,true);const canRead=m.kind==='group'&&m.members.some(p=>p.user_id===state.user.id&&['accepted','cancelled'].includes(p.status));$('groupChatPanel').classList.toggle('hidden',!canRead);updateGroupComposer();}await loadMeetups();if(buddy.chatId)await loadPinnedMeetup(buddy.chatId);if(m.state==='completed'){const epoch=state.epoch,p=await api('/api/profile');if(epoch===state.epoch){if(campus.profile)Object.assign(campus.profile,{completed:p.completed,is_admin:p.is_admin});$('completedCount').textContent=`已完成 ${p.completed} 次约定`;}}}
function boatAcceptedMembers(meeting){
  return (Array.isArray(meeting?.members)?meeting.members:[])
    .filter(p=>p.status==='accepted'&&p.user_id!=null)
    .map(p=>({id:p.user_id,name:chatName(p)}));
}
function rememberBoatRoster(meeting){
  if(!meeting)return;
  campus.boatSeen[meeting.id]=boatAcceptedMembers(meeting).map(p=>p.id);
}
// 轮询时调用：返回本次真正“新上船”的成员 id，首次看到该队伍不播放动画。
function newBoatMembers(meeting){
  const roster=boatAcceptedMembers(meeting),ids=roster.map(p=>p.id);
  const seen=campus.boatSeen[meeting.id];
  campus.boatSeen[meeting.id]=ids;
  if(!seen)return [];
  return ids.filter(id=>!seen.includes(id));
}
function showBoatJoinAnimation(meeting,newcomers=[]){
  // 只使用服务端返回的最新成员状态，人数 = 当前已接受邀请的人数。
  const roster=boatAcceptedMembers(meeting);
  if(!roster.length)return;
  const count=roster.length;
  const extra=new Set(Array.isArray(newcomers)?newcomers:[]);
  const old=document.getElementById('boatJoinOverlay');
  if(old)old.remove();
  const overlay=document.createElement('div');
  overlay.id='boatJoinOverlay';
  overlay.className='boat-join-overlay';
  overlay.style.cssText='position:fixed!important;inset:0!important;width:100%!important;height:100%!important;min-height:100vh!important;min-height:100dvh!important;z-index:2147483647!important;display:grid!important;place-items:center!important;box-sizing:border-box!important;padding:16px!important;background:rgba(20,39,32,.68)!important;visibility:visible!important;opacity:1!important;pointer-events:auto!important';
  // 船与人物的尺寸随人数变化，CSS 只读取这些变量，不再用 !important 互相覆盖。
  const look=count<=2?{w:'94%',h:'132px',p:'40px',ph:'58px',b:'42px'}
    :count<=4?{w:'110%',h:'146px',p:'36px',ph:'54px',b:'47px'}
    :count<=6?{w:'124%',h:'158px',p:'32px',ph:'50px',b:'51px'}
    :{w:'136%',h:'166px',p:'28px',ph:'46px',b:'54px'};
  overlay.style.setProperty('--boat-width',look.w);
  overlay.style.setProperty('--boat-height',look.h);
  overlay.style.setProperty('--person-size',look.p);
  overlay.style.setProperty('--person-height',look.ph);
  overlay.style.setProperty('--people-bottom',look.b);
  overlay.setAttribute('role','dialog');
  overlay.setAttribute('aria-modal','true');
  overlay.setAttribute('aria-label','加入运动小船');
  const shown=roster.slice(0,10);
  const people=shown.map((p,index)=>`<span class="boat-passenger ${extra.has(p.id)?'boat-new-passenger':''}" style="--person-index:${index}" title="${escapeHTML(p.name)}">🧑</span>`).join('')
    +(count>shown.length?`<span class="boat-more">+${count-shown.length}</span>`:'');
  overlay.innerHTML=`<div class="boat-join-dialog">
    <button type="button" class="boat-close" aria-label="关闭">×</button>
    <div class="boat-join-kicker">LET'S GO TOGETHER</div>
    <h2>上船成功！</h2>
    <p class="boat-join-subtitle">已有 ${count} 位伙伴同舟，一起出发吧</p>
    <div class="boat-scene">
      <div class="boat-sun"></div>
      <div class="boat-passengers">${people}</div>
      <svg class="boat-svg" viewBox="0 0 360 150" role="img" aria-label="载着 ${count} 位运动伙伴的小船">
        <path class="boat-sail" d="M177 18 L177 104 L116 104 Z"/><path class="boat-sail boat-sail-two" d="M190 35 L190 104 L247 104 Z"/>
        <path class="boat-mast" d="M182 13 L182 112"/>
        <path class="boat-hull" d="M48 105 Q180 132 312 105 L282 137 Q180 151 78 137 Z"/>
        <path class="boat-hull-line" d="M78 119 Q180 140 282 119"/>
      </svg>
      <div class="boat-wave boat-wave-one"></div><div class="boat-wave boat-wave-two"></div>
    </div>
    <div class="boat-join-count">⛵ ${count} 位伙伴同舟，准备出发</div>
    <p class="boat-join-names">${roster.slice(0,5).map(p=>escapeHTML(p.name)).join(' · ')}</p>
    <button type="button" class="boat-confirm">太棒了</button>
  </div>`;
  document.body.appendChild(overlay);
  let closed=false;
  const close=()=>{if(closed)return;closed=true;overlay.classList.add('boat-leaving');document.removeEventListener('keydown',onKey);setTimeout(()=>overlay.remove(),240);};
  const onKey=e=>{if(e.key==='Escape')close();};
  overlay.querySelector('.boat-close').addEventListener('click',close);
  overlay.querySelector('.boat-confirm').addEventListener('click',close);
  overlay.addEventListener('click',e=>{if(e.target===overlay)close();});
  document.addEventListener('keydown',onKey);
  setTimeout(close,6500);
}
async function decideMeeting(id,action,reason=''){
  const m=findMeeting(id);
  if(!m)throw new Error('请刷新约定后重试。');
  const epoch=state.epoch;
  const result=await withConflict(`/api/meetups/${id}/decision`,{action,revision:m.revision,reason});
  if(epoch!==state.epoch)return;
  if(action==='accept'){showBoatJoinAnimation(result,[state.user.id]);rememberBoatRoster(result);}
  await refreshMeetingResult(result);
  notify(action==='attend'?'已记录你的参加确认':action==='accept'?'邀请已接受':'约定已更新');
}
function openInvite(meeting=null){const selected=selectedBuddy();if(!meeting&&!selected){notify('请先打开一位搭子的聊天');return;}campus.formMeeting=meeting;$('meetupForm').reset();$('inviteSport').value=meeting?.exercise_type||selected?.topic.split(' · ')[0]||'羽毛球';$('inviteSport').disabled=!!meeting;const d=meeting?new Date(meeting.starts_at):new Date(Date.now()+86400000);$('inviteTime').value=`${localDate(d)}T${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;$('inviteDuration').value=String(meeting?.duration||60);$('invitePlace').value=meeting?.location||selected?.topic.split(' · ').slice(1).join(' · ')||'';$('meetupFormTitle').textContent=meeting?'提出新的时间和地点':'发出运动邀请';$('inviteSubmit').textContent=meeting?'发送改约提议':'发送邀请';$('inviteMsg').textContent='';$('meetupFormDialog').showModal();}
async function submitInvite(){await busy($('inviteSubmit'),async()=>{const epoch=state.epoch,m=campus.formMeeting,payload={starts_at:new Date($('inviteTime').value).toISOString(),duration:Number($('inviteDuration').value),location:$('invitePlace').value.trim()};if(m)payload.revision=m.revision;else Object.assign(payload,{chat_id:buddy.chatId,exercise_type:$('inviteSport').value.trim()});const result=await withConflict(m?`/api/meetups/${m.id}/change`:'/api/meetups',payload);if(epoch!==state.epoch)return;$('meetupFormDialog').close();await refreshMeetingResult(result);notify(m?'改约提议已发出，等待同伴确认':'运动邀请已发出');},'inviteMsg');}
function openReport(data,name){campus.report=data;$('reportForm').reset();$('reportTarget').textContent=`举报对象：${name}`;$('reportMsg').textContent='';$('reportDialog').showModal();}
async function rateUser(id){const epoch=state.epoch,d=await api(`/api/buddies/${id}/rating`);if(epoch!==state.epoch)return;$('buddyRatingDialog').dataset.user=String(id);$('buddyScore').value=String(d.my_score||5);$('buddySaveRating').disabled=!d.can_rate;$('buddyRatingSummary').textContent=d.rating==null?'暂无评分':`${d.rating.toFixed(1)} 分 · ${d.rating_count} 人评价`;$('buddyRatingMsg').textContent=d.can_rate?'':'双方确认完成运动后才可评分。';$('buddyRatingDialog').showModal();}
async function loadMyReports(){const epoch=state.epoch,rows=await api('/api/reports/mine');if(epoch!==state.epoch)return;$('myReports').innerHTML=rows.map(r=>`<article class="report-row"><strong>#${r.id} · ${escapeHTML(r.target)} · ${r.state==='pending'?'待处理':'已处理'}</strong><p>${escapeHTML(r.reason)}</p>${r.resolution?`<p class="resolution">处理说明：${escapeHTML(r.resolution)}</p>`:''}</article>`).join('')||'<p class="fine">暂时没有提交的举报。</p>';}
async function loadAdminReports(append=false){const epoch=state.epoch,rows=await api(`/api/admin/reports?offset=${append?campus.adminRows.length:0}`);if(epoch!==state.epoch)return;campus.adminRows=append?[...campus.adminRows,...rows]:rows;$('adminReports').innerHTML=campus.adminRows.map(r=>`<article class="report-row"><span class="pill">${r.state==='pending'?'待处理':'已处理'}</span><h3>#${r.id} · ${escapeHTML(r.target)}</h3><p class="fine">举报者：${escapeHTML(r.reporter)} · ${escapeHTML(buddyTime(r.created_at))}</p><p>${escapeHTML(r.reason)}</p>${r.resolution?`<p class="resolution">${escapeHTML(r.resolution)}</p>`:''}<button type="button" class="ghost" data-resolve-report="${r.id}">查看并处理</button></article>`).join('')||'<p class="fine">没有待处理举报。</p>';$('moreAdminReports').classList.toggle('hidden',rows.length<30);}
$('campusProfileForm').addEventListener('submit',e=>{e.preventDefault();busy(e.submitter,async()=>{const epoch=state.epoch,d=await saveProfilePatch({school:$('profileSchool').value.trim()});if(epoch!==state.epoch||!d)return;$('campusLabel').textContent=`${d.school} · 一起运动`;$('profileMsg').textContent='学校已更新，首页和发现页会按新学校筛选。';if(typeof homeDiscoveryRefresh==='function')await homeDiscoveryRefresh();},'profileMsg');});
$('buddyFilter').addEventListener('input',scheduleSearch);$('buddyPlaceFilter').addEventListener('input',scheduleSearch);
$('buddyMoreFilters').addEventListener('click',()=>{$('buddyExtraFilters').classList.toggle('hidden');$('buddyMoreFilters').setAttribute('aria-expanded',String(!$('buddyExtraFilters').classList.contains('hidden')));});
$('buddyInvite').addEventListener('click',()=>openInvite());$('meetupForm').addEventListener('submit',e=>{e.preventDefault();submitInvite();});
$('repeatMeetupForm').addEventListener('submit',e=>{e.preventDefault();submitRepeatMeeting();});
$('cancelMeetupForm').addEventListener('submit',e=>{e.preventDefault();busy($('cancelMeetupSubmit'),async()=>{await decideMeeting(campus.cancelMeeting,'cancel',$('cancelReason').value.trim());$('cancelMeetupDialog').close();},'cancelMeetupMsg');});
$('buddyReport').addEventListener('click',()=>{const c=selectedBuddy();if(c)openReport({target_id:c.user_id,chat_id:c.id},c.username);});
$('reportForm').addEventListener('submit',e=>{e.preventDefault();busy($('reportSubmit'),async()=>{const epoch=state.epoch;await api('/api/reports',{method:'POST',body:JSON.stringify({...campus.report,reason:$('reportReason').value.trim()})});if(epoch!==state.epoch)return;$('reportDialog').close();notify('举报已提交，可在“我的举报”查看进度');},'reportMsg');});
$('groupMessage').addEventListener('input',()=>{if(campus.meeting)buddyStore(`group:${campus.meeting.id}`,$('groupMessage').value);});
$('groupMessageForm').addEventListener('submit',e=>{e.preventDefault();busy($('groupSend'),async()=>{const epoch=state.epoch,id=campus.meeting.id,body=$('groupMessage').value;await api(`/api/meetups/${id}/messages`,{method:'POST',body:JSON.stringify({body})});if(epoch!==state.epoch)return;if(buddyRead(`group:${id}`)===body)buddyDrop(`group:${id}`);if(campus.meeting?.id===id){if($('groupMessage').value===body)$('groupMessage').value='';$('groupMessages').scrollTop=$('groupMessages').scrollHeight;await pollGroup();}},'groupMessageMsg');});
$('groupOlder').addEventListener('click',()=>busy($('groupOlder'),async()=>{const epoch=state.epoch,id=campus.meeting.id,rows=await api(`/api/meetups/${id}/messages?before=${campus.groupBefore}`);if(epoch!==state.epoch||id!==campus.meeting?.id)return;const box=$('groupMessages'),height=box.scrollHeight;appendGroupMessages(rows,true);box.scrollTop+=box.scrollHeight-height;$('groupOlder').classList.toggle('hidden',rows.length<50);},'groupMessageMsg'));
$('refreshMeetups').addEventListener('click',()=>busy($('refreshMeetups'),()=>loadMeetups(),'meetupsMsg'));$('moreMeetups').addEventListener('click',()=>busy($('moreMeetups'),()=>loadMeetups(true),'meetupsMsg'));
$('loadReports').addEventListener('click',()=>busy($('loadReports'),loadMyReports,'reportListMsg'));
$('loadAdminReports').addEventListener('click',()=>busy($('loadAdminReports'),()=>loadAdminReports(),'adminMsg'));$('moreAdminReports').addEventListener('click',()=>busy($('moreAdminReports'),()=>loadAdminReports(true),'adminMsg'));
$('adminForm').addEventListener('submit',e=>{e.preventDefault();busy($('adminSubmit'),async()=>{const epoch=state.epoch;await api(`/api/admin/reports/${campus.adminId}`,{method:'POST',body:JSON.stringify({action:$('adminAction').value,resolution:$('adminResolution').value.trim()})});if(epoch!==state.epoch)return;$('adminDialog').close();await loadAdminReports();},'adminDialogMsg');});
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
  if(b.dataset.closeDialog)$(b.dataset.closeDialog).close();
  if(b.dataset.themeChoice)busy(b,()=>saveTheme(b.dataset.themeChoice),'themeMsg');
  if('filterDate' in b.dataset){$('buddyTimeFilter').value=b.dataset.filterDate;refreshBuddyDates();if(!$('buddyFilterDialog')?.open)loadBuddyStatuses();}
  if('period' in b.dataset){$('buddyPeriodFilter').value=b.dataset.period;syncPeriodButtons();if(!$('buddyFilterDialog')?.open)loadBuddyStatuses();}
  if(b.dataset.openMeetup)navigate(`buddies/group/${b.dataset.openMeetup}`);
  if(b.dataset.editActivity)editActivity(Number(b.dataset.editActivity));
  if(b.dataset.removeActivity)busy(b,()=>withdrawActivity(Number(b.dataset.removeActivity)),'buddyFormMsg');
  if(b.dataset.joinActivity)busy(b,async()=>{const epoch=state.epoch,m=await withConflict(`/api/activities/${b.dataset.joinActivity}/join`,{});if(epoch!==state.epoch)return;showBoatJoinAnimation(m,[state.user.id]);rememberBoatRoster(m);navigate(`buddies/group/${m.id}`);},'buddyListMsg');
  if(b.dataset.meetupAction)busy(b,()=>decideMeeting(Number(b.dataset.meetingId),b.dataset.meetupAction),buddy.tab==='appointments'?'meetupsMsg':'meetupMsg');
  if(b.dataset.repeatMeetup)busy(b,()=>openRepeatMeeting(Number(b.dataset.repeatMeetup)));
  if(b.dataset.changeMeetup){const m=findMeeting(Number(b.dataset.changeMeetup));if(m)openInvite(m);}
  if(b.dataset.cancelMeetup){campus.cancelMeeting=Number(b.dataset.cancelMeetup);$('cancelReason').value='';$('cancelMeetupMsg').textContent='';$('cancelMeetupDialog').showModal();}
  if(b.dataset.reportActivity){const row=buddy.rows.find(r=>r.id===Number(b.dataset.reportActivity));if(row)openReport({target_id:row.user_id,activity_id:row.id},row.username);}
  if(b.dataset.reportMember){const m=findMeeting(Number(b.dataset.meetingId)),p=m?.members.find(p=>p.user_id===Number(b.dataset.reportMember));if(p)openReport({target_id:p.user_id,meetup_id:m.id},p.username);}
  if(b.dataset.rateUser)busy(b,()=>rateUser(Number(b.dataset.rateUser)),'meetupMsg');
  if(b.dataset.resolveReport){const r=campus.adminRows.find(r=>r.id===Number(b.dataset.resolveReport));if(!r)return;campus.adminId=r.id;$('adminForm').reset();$('adminResolution').value=r.resolution||'';$('adminDialogMsg').textContent='';$('adminDialogTitle').textContent=`处理举报 #${r.id}`;$('adminDialog').showModal();}
});
matchMedia('(prefers-color-scheme:dark)').addEventListener('change',()=>{if(campus.profile?.theme==='system')applyTheme('system');});
if(window.visualViewport){const resize=()=>document.documentElement.style.setProperty('--chat-height',`${window.visualViewport.height}px`);window.visualViewport.addEventListener('resize',resize);resize();}
