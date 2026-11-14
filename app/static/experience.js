const activityDetails={row:null,request:0};
function activityWhen(value){
  const date=new Date(value),tomorrow=new Date();tomorrow.setDate(tomorrow.getDate()+1);
  const day=localDate(date)===localDate()?'今天':localDate(date)===localDate(tomorrow)?'明天':date.toLocaleDateString('zh-CN',{month:'numeric',day:'numeric',weekday:'short'});
  return `${day} ${date.toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})}`;
}
function activityCoverMarkup(row){
  const cover=safeActivityImage(row.cover_url);
  return `<div class="activity-cover ${cover?'has-photo':'illustrated'}">${cover?`<img src="${escapeHTML(cover)}" alt="${escapeHTML(row.exercise_type)}活动封面" loading="lazy">`:activityArtwork(row.exercise_type)}<span class="activity-sport">${escapeHTML(row.exercise_type)}</span><span class="activity-cover-label">${cover?'同学上传':'运动主题图'}</span></div>`;
}
function renderExperience(){
  if(!state.user)return;
  $('homeWeekMinutes').textContent=state.review?.weekly_minutes??0;
  $('homeWeekDays').textContent=`${state.review?.active_days??0} 个运动日`;
  if(typeof renderProfileOverview==='function')renderProfileOverview();
}
function resetExperience(){
  activityDetails.request++;activityDetails.row=null;
  if($('activityDetailDialog').open)$('activityDetailDialog').close();
  $('activityDetailContent').replaceChildren();$('activityDetailMsg').textContent='';
  $('homeAccountAvatar').replaceChildren();delete $('homeAccountAvatar').dataset.identity;
  $('homeWeekMinutes').textContent='0';$('homeWeekDays').textContent='0 个运动日';
}
function activityDetailMarkup(row){
  const name=row.display_name||row.username,group=row.capacity>2;
  const count=group?`${row.joined} / ${row.capacity} 人已加入`:'正在寻找一位运动同伴';
  const rating=row.rating==null?'还没有搭子评价':`${Number(row.rating).toFixed(1)} 分 · ${row.rating_count} 人评价`;
  return `${activityCoverMarkup(row)}<div class="detail-content"><span class="detail-level">${escapeHTML(row.level==='不限'?'不限水平':`${row.level}水平`)} · ${escapeHTML(row.school)}</span><h2 id="activityDetailTitle">${escapeHTML(row.exercise_type)}${group?'组局':'一起练'}</h2><dl class="activity-facts"><div><dt>时间</dt><dd>${escapeHTML(buddyTime(row.starts_at))}</dd></div><div><dt>地点</dt><dd>${escapeHTML(row.location)}</dd></div><div><dt>安排</dt><dd>${row.duration} 分钟 · ${count}</dd></div></dl><div class="detail-host">${activityAvatar(row)}<div><strong>${escapeHTML(name)}</strong><p>${rating} · 完成 ${row.completed||0} 次约定</p></div></div><section><h3>这场怎么约</h3><p class="detail-note">${escapeHTML(row.note||'发起人还没有补充说明。参加前可以聊聊集合方式、器材和费用安排。')}</p></section>${row.bio?`<section><h3>认识发起人</h3><p class="detail-note">${escapeHTML(row.bio)}</p></section>`:''}${group?`<section><h3>参加者预览</h3><div class="detail-people">${(row.participants||[]).map(p=>`<span>${activityAvatar(p)}<small>${escapeHTML(p.display_name||p.username)}</small></span>`).join('')}</div><p class="fine">${count} · 仅展示可见成员的部分头像</p></section>`:''}</div>`;
}
async function openActivityDetails(id){
  const epoch=state.epoch,request=++activityDetails.request;
  activityDetails.row=null;$('activityDetailContent').innerHTML='<h2 id="activityDetailTitle" class="detail-loading">正在看看这场运动…</h2>';
  $('activityDetailMsg').textContent='';$('activityDetailAction').disabled=true;$('activityDetailAction').textContent='正在加载…';$('activityDetailReport').classList.add('hidden');
  if(!$('activityDetailDialog').open)$('activityDetailDialog').showModal();
  try{
    const row=await api(`/api/activities/${id}`);
    if(epoch!==state.epoch||request!==activityDetails.request||!$('activityDetailDialog').open)return;
    activityDetails.row=row;$('activityDetailContent').innerHTML=activityDetailMarkup(row);
    $('activityDetailContent').closest('dialog').querySelector('.detail-toolbar>span').textContent=row.school;
    const mine=row.user_id===state.user.id,full=row.capacity>2&&row.joined>=row.capacity;
    $('activityDetailAction').textContent=mine?'管理我的邀请':row.is_member?'查看我的组局':full?'人数已满':row.capacity>2?'参加这场运动':'和搭子聊聊';
    $('activityDetailAction').disabled=!mine&&!row.is_member&&full;
    $('activityDetailReport').classList.toggle('hidden',mine);
    $('activityDetailDialog').scrollTop=0;
  }catch(error){if(epoch===state.epoch&&request===activityDetails.request){$('activityDetailContent').innerHTML='<h2 id="activityDetailTitle" class="detail-loading">暂时无法查看这场运动</h2>';$('activityDetailMsg').textContent=error.message;$('activityDetailAction').textContent='暂不可参加';}}
}
$('closeActivityDetail').addEventListener('click',()=>$('activityDetailDialog').close());
$('activityDetailDialog').addEventListener('close',()=>{activityDetails.request++;activityDetails.row=null;});
$('activityDetailAction').addEventListener('click',()=>busy($('activityDetailAction'),async()=>{
  const row=activityDetails.row,epoch=state.epoch,request=activityDetails.request;if(!row)return;
  let route;
  if(row.user_id===state.user.id)route='buddies/mine';
  else if(row.is_member)route=`buddies/group/${row.meetup_id}`;
  else if(row.capacity>2){const meeting=await withConflict(`/api/activities/${row.id}/join`,{});route=`buddies/group/${meeting.id}`;}
  else{const chat=await api(`/api/buddies/${row.user_id}/chat`,{method:'POST'});route=`messages/${chat.id}`;}
  if(epoch!==state.epoch||request!==activityDetails.request||!$('activityDetailDialog').open)return;
  $('activityDetailDialog').close();navigate(route);
},'activityDetailMsg'));
$('activityDetailReport').addEventListener('click',()=>{
  const row=activityDetails.row;if(!row)return;
  $('activityDetailDialog').close();openReport({target_id:row.user_id,activity_id:row.id},row.display_name||row.username);
});
document.addEventListener('click',event=>{
  const button=event.target.closest('[data-activity-details]');
  if(button)openActivityDetails(Number(button.dataset.activityDetails));
});
