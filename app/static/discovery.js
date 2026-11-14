// Campus discovery uses real activities; illustration cards are only visual fallbacks.
const discovery={rows:[],request:0,filters:null,filterApplied:false};
const buddyCover={file:null,objectURL:null,url:null,remove:false};
const filterFields=['buddyTimeFilter','buddyPeriodFilter','buddyScope','buddySort','buddyLevelFilter','buddyPlaceFilter'];
function safeActivityImage(url){return typeof url==='string'&&/^\/api\/(users|activities)\/\d+\/(avatar|cover)(\?v=[\w-]+)?$/.test(url)?url:'';}
function activityAvatar(person,extra=''){
  const name=person.display_name||person.username||'同学';
  return `<span class="activity-avatar ${extra}" title="${escapeHTML(name)}"><span aria-hidden="true">${escapeHTML(Array.from(name)[0]||'同')}</span>${avatarPhotoMarkup(person)}</span>`;
}
function activityArtwork(sport){
  if(/篮球/.test(sport))return '<svg viewBox="0 0 420 150" aria-hidden="true"><path class="court-line" d="M24 18h372v114H24zm186 0v114M24 52h62v46H24m372-46h-62v46h62"/><circle class="sport-ball" cx="276" cy="75" r="53"/><path class="ball-line" d="M223 75h106M276 22v106m-40-87q75 33 80 67m0-66q-75 34-80 67"/><path class="motion-line" d="M138 60h52m-69 20h63m-38 20h36"/></svg>';
  if(/羽毛|乒乓|网球/.test(sport))return '<svg viewBox="0 0 420 150" aria-hidden="true"><path class="court-line" d="M22 22h376v106H22zm188 0v106M22 75h376M82 22v106m256-106v106"/><g transform="translate(260 74) rotate(35)"><ellipse class="racket" cx="0" cy="-20" rx="30" ry="41"/><path class="racket-line" d="M-19-49v58m12-68v78M6-59v78m13-68v58M-28-35h56m-58 15h60M-28-5h56M0 21v47"/><path class="racket-grip" d="M0 51v24"/></g><path class="shuttle" d="m134 49 36-25 17 42-37 8Z"/><path class="shuttle-line" d="m143 52 29-20m-24 26 28-14m-22 20 26-9"/><circle class="shuttle" cx="147" cy="72" r="9"/></svg>';
  return '<svg viewBox="0 0 420 150" aria-hidden="true"><path class="track-line" d="M0 116h160c60 0 60-84 120-84h140M0 135h163c69 0 69-84 124-84h133M0 97h154c53 0 54-84 119-84h147"/><circle class="runner-head" cx="231" cy="35" r="11"/><path class="runner-body" d="m220 57-20 27 28 17-15 30m-13-47-30 26h-30m80-52 24 16 22-14m-46-2-26 3-17 21"/><path class="motion-line" d="M105 50h49m-65 17h57"/></svg>';
}
function campusActivityCard(row,home=false){
  const mine=row.user_id===state.user?.id,group=row.capacity>2,name=row.display_name||row.username;
  const full=group&&row.joined>=row.capacity,remaining=Math.max(0,row.capacity-row.joined);
  const label=group?(full?'人数已满':`还缺 ${remaining} 人`):'找一位同伴';
  const rating=row.rating==null?'暂无评价':`★ ${Number(row.rating).toFixed(1)} · ${row.rating_count} 人评价`;
  const people=(row.participants||[]).slice(0,3);
  return `<article class="buddy-status campus-activity ${home?'home-pick':''}" data-activity-card="${row.id}">${activityCoverMarkup(row)}<div class="activity-content"><div class="activity-title"><h3>${escapeHTML(row.exercise_type)}${group?'组局':''}</h3><span class="activity-seats ${full?'full':''}">${label}</span></div><p class="activity-when" title="${escapeHTML(buddyTime(row.starts_at))}">${escapeHTML(activityWhen(row.starts_at))}<span> · ${row.duration||60} 分钟</span></p><p class="activity-place">⌖ ${escapeHTML(row.location)}</p><div class="activity-tags"><span>${escapeHTML(row.level==='不限'?'不限水平':`${row.level}水平`)}</span>${row.school===campus.profile?.school?'<span>同校</span>':''}</div><div class="activity-host">${activityAvatar(row)}<div><strong>${escapeHTML(name)}${mine?' · 我':''}</strong><span>${rating}</span></div>${group?`<span class="participant-faces">${people.slice(1).map(p=>activityAvatar(p,'participant-avatar')).join('')}</span>`:''}<button type="button" data-activity-details="${row.id}">查看详情 ↗</button></div></div></article>`;
}
async function loadHomeActivities(){
  if(!state.user)return;const epoch=state.epoch,request=++discovery.request;
  $('homeDiscoveryMsg').textContent='正在看看校园里的运动邀请…';$('homeActivityList').setAttribute('aria-busy','true');
  try{
    const rows=await api('/api/activities?scope=school&sort=time&limit=3');
    if(epoch!==state.epoch||request!==discovery.request)return;
    discovery.rows=rows;$('homeCampusLabel').textContent=`${campus.profile?.school||rows[0]?.school||'我的校园'} · 一起运动`;
    $('homeActivityList').innerHTML=rows.map(row=>campusActivityCard(row,true)).join('')||'<div class="campus-empty"><div class="campus-empty-art activity-cover illustrated">'+activityArtwork('羽毛球')+'</div><h3>第一场，从你开始</h3><p>还没有同校活动。发出邀请，约同学一起动一动。</p><button type="button" data-home-create="羽毛球">发起一场羽毛球局 ↗</button><button type="button" class="text-button" data-home-own>选择其他运动</button></div>';
    $('homeDiscoveryMsg').textContent='';
  }catch(e){if(epoch===state.epoch&&request===discovery.request)$('homeDiscoveryMsg').textContent=e.message;}
  finally{if(request===discovery.request)$('homeActivityList').removeAttribute('aria-busy');}
}
function homeDiscoveryRefresh(){return loadHomeActivities();}
function resetDiscovery(){discovery.request++;discovery.rows=[];$('homeActivityList').replaceChildren();$('homeDiscoveryMsg').textContent='';discovery.filters=null;if($('buddyFilterDialog').open)$('buddyFilterDialog').close();resetDiscoveryFilters();resetBuddyCover();}
function currentDiscoveryFilters(){return Object.fromEntries(filterFields.map(id=>[id,$(id).value]));}
function assignDiscoveryFilters(values){for(const id of filterFields)$(id).value=values[id]??'';refreshBuddyDates();syncPeriodButtons();}
function resetDiscoveryFilters(){assignDiscoveryFilters({buddyScope:'school',buddySort:'rating'});updateDiscoveryFilterSummary();}
function updateDiscoveryFilterSummary(){
  const f=currentDiscoveryFilters(),parts=[f.buddyScope==='all'?'全部学校':'同校',f.buddySort==='time'?'时间最近':'评分优先'];
  if(f.buddyTimeFilter)parts.push(f.buddyTimeFilter.slice(5).replace('-','/'));if(f.buddyPeriodFilter)parts.push({morning:'上午',afternoon:'下午',evening:'晚上'}[f.buddyPeriodFilter]);if(f.buddyLevelFilter)parts.push(f.buddyLevelFilter);if(f.buddyPlaceFilter.trim())parts.push(f.buddyPlaceFilter.trim());
  const count=Number(!!f.buddyTimeFilter)+Number(!!f.buddyPeriodFilter)+Number(f.buddyScope!=='school')+Number(f.buddySort!=='rating')+Number(!!f.buddyLevelFilter)+Number(!!f.buddyPlaceFilter.trim());
  $('buddyFilterSummary').textContent=parts.join(' · ');$('buddyFilterCount').textContent=String(count);$('buddyFilterCount').classList.toggle('hidden',!count);
}
function openDiscoveryFilters(){refreshBuddyDates();clearTimeout(buddy.searchTimer);discovery.filters=currentDiscoveryFilters();discovery.filterApplied=false;$('buddyFilterDialog').showModal();}
function closeDiscoveryFilters(){if(discovery.filters&&!discovery.filterApplied)assignDiscoveryFilters(discovery.filters);discovery.filters=null;$('buddyFilterDialog').close();updateDiscoveryFilterSummary();}
function resetBuddyCover(){if(buddyCover.objectURL)URL.revokeObjectURL(buddyCover.objectURL);Object.assign(buddyCover,{file:null,objectURL:null,url:null,remove:false});$('buddyCoverFile').value='';$('buddyCoverMsg').textContent='JPEG、PNG 或 WebP，最多 5 MB；未选择照片时显示运动主题图。';renderBuddyCover();}
function setBuddyCover(row){resetBuddyCover();buddyCover.url=safeActivityImage(row?.cover_url)||null;renderBuddyCover();}
function renderBuddyCover(){const url=buddyCover.objectURL||(!buddyCover.remove&&buddyCover.url);$('buddyCoverPreview').classList.toggle('hidden',!url);if(url)$('buddyCoverPreview').src=url;else $('buddyCoverPreview').removeAttribute('src');$('buddyCoverPlaceholder').classList.toggle('hidden',!!url);$('buddyCoverRemove').classList.toggle('hidden',!url);}
function selectBuddyCover(){const file=$('buddyCoverFile').files[0];if(!file)return;if(file.size>5*1024*1024||!['image/jpeg','image/png','image/webp'].includes(file.type)){$('buddyCoverMsg').textContent='请选择不超过 5 MB 的 JPEG、PNG 或 WebP 图片。';$('buddyCoverFile').value='';return;}if(buddyCover.objectURL)URL.revokeObjectURL(buddyCover.objectURL);buddyCover.file=file;buddyCover.objectURL=URL.createObjectURL(file);buddyCover.remove=false;renderBuddyCover();$('buddyCoverMsg').textContent='封面已选好，确认发布时上传。图片不会存入本地草稿。';saveBuddyDraft();}
async function saveBuddyCover(activityId){const epoch=state.epoch;if(buddyCover.file){const data=new FormData();data.append('file',buddyCover.file);const result=await api(`/api/activities/${activityId}/cover`,{method:'POST',body:data});if(epoch===state.epoch)buddyCover.url=result.cover_url;}else if(buddyCover.remove&&buddyCover.url)await api(`/api/activities/${activityId}/cover`,{method:'DELETE'});}
$('openBuddyFilters').addEventListener('click',openDiscoveryFilters);
$('closeBuddyFilters').addEventListener('click',closeDiscoveryFilters);
$('buddyFilterDialog').addEventListener('cancel',event=>{event.preventDefault();closeDiscoveryFilters();});
$('buddyFilterDialog').addEventListener('close',()=>{if(discovery.filters&&!discovery.filterApplied)assignDiscoveryFilters(discovery.filters);discovery.filters=null;updateDiscoveryFilterSummary();});
$('resetBuddyFilters').addEventListener('click',()=>assignDiscoveryFilters({buddyScope:'school',buddySort:'rating'}));
$('applyBuddyFilters').addEventListener('click',()=>{discovery.filterApplied=true;$('buddyFilterDialog').close();updateDiscoveryFilterSummary();loadBuddyStatuses();});
$('buddyCoverFile').addEventListener('change',selectBuddyCover);
$('buddyCoverRemove').addEventListener('click',()=>{if(buddyCover.objectURL)URL.revokeObjectURL(buddyCover.objectURL);buddyCover.objectURL=null;buddyCover.file=null;buddyCover.remove=true;$('buddyCoverFile').value='';renderBuddyCover();$('buddyCoverMsg').textContent=buddyCover.url?'确认保存后移除封面。':'已取消选择封面。';saveBuddyDraft();});
$('refreshHomeActivities').addEventListener('click',()=>busy($('refreshHomeActivities'),loadHomeActivities,'homeDiscoveryMsg'));
$('homeDiscovery').addEventListener('click',event=>{
  const b=event.target.closest('button');if(!b)return;
  if('homeChat' in b.dataset)busy(b,async()=>{const epoch=state.epoch,chat=await api(`/api/buddies/${b.dataset.homeChat}/chat`,{method:'POST'});if(epoch===state.epoch)navigate(`messages/${chat.id}`);},'homeDiscoveryMsg');
  if('homeJoin' in b.dataset)busy(b,async()=>{const epoch=state.epoch,m=await withConflict(`/api/activities/${b.dataset.homeJoin}/join`,{});if(epoch===state.epoch)navigate(`buddies/group/${m.id}`);},'homeDiscoveryMsg');
  if('homeOwn' in b.dataset)navigate('buddies/mine');
  if('homeSport' in b.dataset){$('buddyFilter').value=b.dataset.homeSport;resetDiscoveryFilters();navigate('buddies');}
  if('homeCreate' in b.dataset){navigate('buddies/mine');newActivity();$('buddySport').value=b.dataset.homeCreate;saveBuddyDraft();}
});
document.addEventListener('error',event=>{const image=event.target;if(image.tagName!=='IMG')return;const cover=image.closest('.activity-cover');if(cover){cover.classList.remove('has-photo');cover.classList.add('illustrated');image.replaceWith(document.createRange().createContextualFragment(activityArtwork(cover.closest('article')?.querySelector('h3')?.textContent||'')));const label=cover.querySelector('.activity-cover-label');if(label)label.textContent='运动主题图';}},true);
