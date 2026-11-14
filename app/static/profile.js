function closeProfileDialogs(){document.querySelectorAll('.profile-dialog[open]').forEach(dialog=>dialog.close());}
function openProfileDialog(id){
  const dialog=$(id);if(!state.user||!dialog?.classList.contains('profile-dialog'))return;
  closeProfileDialogs();syncProfileEditor();dialog.showModal();
}
function syncProfileEditor(){
  const source=$('profileAvatarPreview'),target=$('identityEditorPhoto'),url=source.getAttribute('src');
  if(url){if(target.getAttribute('src')!==url)target.src=url;}else target.removeAttribute('src');
  target.classList.toggle('hidden',source.classList.contains('hidden'));
  $('identityEditorFallback').classList.toggle('hidden',$('profileAvatarFallback').classList.contains('hidden'));
  $('identityEditorFallback').textContent=$('profileAvatarFallback').textContent;
  $('identityAvatarStatus').textContent=$('avatarMsg').textContent;
  document.querySelector('.profile-avatar-status').classList.toggle('hidden',!$('avatarMsg').textContent||$('avatarMsg').textContent===avatarHelp);
}
function renderProfileOverview(){
  if(!state.user)return;
  const profile=campus.profile,review=state.review;
  $('profileSchoolLabel').textContent=profile?.school||'我的校园';
  $('profileWeekMinutes').textContent=review?.weekly_minutes??0;
  $('profileWeekDays').textContent=review?.active_days??0;
  $('profileCompleted').textContent=profile?.completed??0;
  $('profilePeriod').textContent=review?`${review.period_start} — ${review.period_end} · 每一次运动都算数`:'记录一次运动，从今天开始。';
  const records=state.records,counts=new Map();
  for(const row of records)counts.set(row.exercise_type,(counts.get(row.exercise_type)||0)+1);
  $('profileSportsScope').textContent=records.length?`根据最近已加载的 ${records.length} 条记录整理`:'记录运动，慢慢找到自己的喜好';
  $('profileSports').innerHTML=[...counts].sort((a,b)=>b[1]-a[1]).slice(0,4).map(([name,count])=>`<span>${escapeHTML(name)}<small>${count} 次</small></span>`).join('')||'<p class="fine">还没有常玩项目，先从喜欢的开始。</p>';
  $('profileRecentRecords').innerHTML=records.slice(0,3).map(row=>`<article class="profile-recent-record"><span class="profile-record-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><use href="#icon-record"/></svg></span><div><strong>${escapeHTML(row.exercise_type)}</strong><small>${escapeHTML(row.exercise_date)} · ${escapeHTML(row.feeling)}</small></div><span><strong>${row.duration}</strong><small>分钟</small></span></article>`).join('')||'<div class="profile-record-empty"><p>你的下一次出发，值得被记住。</p><button type="button" class="ghost" data-go="records">记录第一次运动</button></div>';
  const signature=JSON.stringify([state.epoch,profile?.display_name,profile?.avatar_url]);
  if($('homeAccountAvatar').dataset.identity!==signature){
    $('homeAccountAvatar').dataset.identity=signature;
    $('homeAccountAvatar').innerHTML=chatAvatar({...profile,user_id:state.user.id,username:state.user.username});
  }
}
function resetProfileOverview(){
  closeProfileDialogs();
  for(const id of ['profileWeekMinutes','profileWeekDays','profileCompleted'])$(id).textContent='0';
  $('profileSports').replaceChildren();$('profileRecentRecords').replaceChildren();
  $('profileSchoolLabel').textContent='我的校园';$('profilePeriod').textContent='';$('profileSportsScope').textContent='';
  $('homeAccountAvatar').replaceChildren();delete $('homeAccountAvatar').dataset.identity;
  $('identityEditorPhoto').removeAttribute('src');$('identityEditorPhoto').classList.add('hidden');
  $('identityEditorFallback').textContent='动';$('identityEditorFallback').classList.remove('hidden');
  for(const id of ['profileMsg','themeMsg','reportListMsg','adminMsg','buddyBlocksMsg'])$(id).textContent='';
  $('completedCount').textContent='已完成 0 次约定';
}
document.addEventListener('click',event=>{
  const open=event.target.closest('[data-profile-open]');
  if(open)openProfileDialog(open.dataset.profileOpen);
  if(event.target.closest('[data-profile-close]'))event.target.closest('dialog')?.close();
});
const profilePreviewObserver=new MutationObserver(syncProfileEditor);
for(const id of ['profileAvatarPreview','profileAvatarFallback','avatarMsg'])profilePreviewObserver.observe($(id),{attributes:true,childList:true,subtree:true,characterData:true});
