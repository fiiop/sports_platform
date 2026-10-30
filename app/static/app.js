const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {user:null, records:[], plans:[], review:null, recordId:null, planId:null, more:false, epoch:0};
const routeScroll = new Map();
let currentRoute = '', reflectionWeek = '', reflectionDirty = false;
let installPrompt, toastTimer;
function localDate(date=new Date()) {return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;}
function notify(message) { $('toast').textContent=message; $('toast').classList.remove('hidden'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').classList.add('hidden'),4500); }
async function api(url, options={}) {
  let r;const requestEpoch=state.epoch;
  const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),30000);
  const multipart=typeof FormData!=='undefined'&&options.body instanceof FormData;
  try {r=await fetch(url,{...options,signal:controller.signal,headers:{...(multipart?{}:{'Content-Type':'application/json'}),...options.headers},cache:'no-store'});}
  catch {throw new Error('网络连接失败或请求超时，请检查网络后重试。');}
  finally {clearTimeout(timeout);}
  const data=await r.json().catch(()=>({}));
  if(!r.ok){
    if(r.status===401 && state.user && requestEpoch===state.epoch) showAuth();
    const message=Array.isArray(data.detail)?data.detail.map(x=>x.msg.replace('Value error, ','')).join('；'):typeof data.detail==='object'?data.detail?.message:data.detail;
    const error=new Error(message || `请求失败（${r.status}）`);error.detail=data.detail;error.status=r.status;throw error;
  }
  return data;
}
async function busy(button, action, messageId) {
  if(button.disabled)return;button.disabled=true;button.setAttribute('aria-busy','true');
  try {await action();} catch(e) {if(messageId) $(messageId).textContent=e.message; else notify(e.message);}
  finally {button.disabled=false;button.removeAttribute('aria-busy');}
}
function navigate(route, fromHistory=false){
  let [page,...parts]=route.replace(/^#/,'').split('/');
  if(page==='messages'){page='buddies';parts=['messages',...parts];}
  const navPage=page==='buddies'&&['messages','group','appointments'].includes(parts[0])?'messages':page;
  if(!['home','records','plans','buddies','profile'].includes(page)) return;
  if(currentRoute)routeScroll.set(currentRoute,window.scrollY);
  if(!fromHistory && location.hash!==`#${route}`)history.pushState(null,'',`#${route}`);
  currentRoute=route;
  document.querySelectorAll('.page').forEach(p=>p.classList.toggle('hidden',p.id!==`page-${page}`));
  document.querySelectorAll('[data-page]').forEach(b=>{b.classList.toggle('active',b.dataset.page===navPage);if(b.dataset.page===navPage)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
  if(typeof buddyNavigate==='function') buddyNavigate(page,parts.join('/'));
  if(page==='profile'&&typeof refreshCampusStats==='function')refreshCampusStats().catch(e=>{$('profileMsg').textContent=e.message;});
  if(page==='home'&&state.user&&typeof loadHomeActivities==='function'){
    loadHomeActivities().catch(e=>{$('homeDiscoveryMsg').textContent=e.message;});
    if(typeof loadMeetups==='function')loadMeetups().catch(()=>{});
  }
  const heading=$(`page-${page}`).querySelector('h1');heading?.setAttribute('tabindex','-1');heading?.focus({preventScroll:true});
  window.scrollTo({top:fromHistory?(routeScroll.get(route)||0):0,behavior:'instant'});
}
function showAuth(){
  if(typeof resetIdentity==='function')resetIdentity();
  if(typeof resetDiscovery==='function')resetDiscovery();
  if(typeof resetBuddies==='function') resetBuddies();
  if(typeof resetCampus==='function') resetCampus();
  if(typeof resetNotifications==='function') resetNotifications();
  state.epoch++; state.user=null; state.records=[]; state.plans=[]; state.review=null;reflectionDirty=false;reflectionWeek='';
  $('authPanel').classList.remove('hidden');$('appPanel').classList.add('hidden');
  $('records').replaceChildren();$('plans').replaceChildren();$('userArea').textContent='';
  $('recordForm').reset();$('planForm').reset();$('reflectionForm').reset();
  state.recordId=null;state.planId=null;
  $('aiAdvice').textContent='记录几次运动，再来看看建议吧。';
  for(const id of ['mMinutes','mDays','mCalories'])$(id).textContent='0';
  for(const id of ['recordMsg','planMsg','reflectionMsg','comparison','reviewPeriod','completionLabel','chartCaption','reviewText'])$(id).textContent='';
  $('chart').replaceChildren();$('progressBar').style.width='0%';
  $('reflectionHistory').replaceChildren();$('reflectionHistory').classList.add('hidden');
  for(const id of ['recordDraftStatus','planDraftStatus','reflectionDraftStatus','homeBuddyStatus'])$(id).textContent='';
}
async function check(){const user=await api('/api/me');if(user.logged_in) await showApp(user);else showAuth();}
async function showApp(user){
  state.user=user;state.epoch++;
  $('authPanel').classList.add('hidden');$('appPanel').classList.remove('hidden');
  $('userArea').textContent=user.username;$('greetingName').textContent=user.username;
  $('todayLabel').textContent=new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'});
  $('password').value='';resetRecord();resetPlan();navigate(location.hash.slice(1)||'home',true);updateDraftHints();
  await Promise.all([refresh(),loadReflection(),typeof loadCampus==='function'?loadCampus():Promise.resolve()]);
  if(typeof initNotifications==='function')initNotifications().catch(()=>{});
}
async function login(){if(!$('authForm').reportValidity())return; await busy($('authForm').querySelector('[type=submit]'),async()=>{await api('/api/login',{method:'POST',body:JSON.stringify({username:$('username').value,password:$('password').value})});await check();},'authMsg');}
async function registerUser(){if(!$('authForm').reportValidity())return;await busy($('registerButton'),async()=>{await api('/api/register',{method:'POST',body:JSON.stringify({username:$('username').value,password:$('password').value})});$('authMsg').textContent='注册成功，请点击登录。';},'authMsg');}
async function logout(){await busy($('logoutButton'),async()=>{await api('/api/logout',{method:'POST'});try{for(const key of [draftKey(),extraDraftKey('plan'),extraDraftKey('reflection')])localStorage.removeItem(key);}catch{}if(typeof clearBuddyDrafts==='function')clearBuddyDrafts();showAuth();history.replaceState(null,'','#home');$('authMsg').textContent='已退出登录。';});}
function resetRecord(){state.recordId=null;$('recordForm').reset();$('recordDate').value=localDate();$('recordFormTitle').textContent='今天，你怎么动的？';$('recordSubmit').textContent='保存记录';$('cancelRecord').classList.add('hidden');}
function resetPlan(){state.planId=null;$('planForm').reset();const now=new Date();$('planStart').value=localDate(now);$('planEnd').value=localDate(new Date(now.getFullYear(),now.getMonth(),now.getDate()+27));$('planFormTitle').textContent='制定运动计划';$('planSubmit').textContent='保存计划';$('cancelPlan').classList.add('hidden');}
const recordFields={exercise_date:'recordDate',exercise_type:'exerciseType',duration:'duration',distance:'distance',intensity:'intensity',calories:'calories',feeling:'feeling',note:'note'};
function recordPayload(){return Object.fromEntries(Object.entries(recordFields).map(([key,id])=>[key,['duration','distance','intensity','calories'].includes(key)?Number($(id).value||0):$(id).value]));}
function fillRecord(row){for(const [key,id] of Object.entries(recordFields)) $(id).value=row[key]??'';}
function editRecord(id){const row=state.records.find(r=>r.id===id);if(!row)return;state.recordId=id;fillRecord(row);$('recordFormTitle').textContent='编辑训练记录';$('recordSubmit').textContent='保存修改';$('cancelRecord').classList.remove('hidden');navigate('records');$('recordDetails').open=true;$('recordForm').scrollIntoView({block:'start'});}
function draftKey(){return `campus-move-draft:${state.user?.id}`;}
function saveDraft(silent=false){
  if(!state.user) return;
  try {localStorage.setItem(draftKey(),JSON.stringify({row:recordPayload(),id:state.recordId,savedAt:Date.now()}));$('recordDraftStatus').textContent='已暂存到此浏览器，尚未提交。';$('restoreDraft').classList.remove('hidden');if(!silent)$('recordMsg').textContent='草稿已暂存到当前浏览器，联网后请恢复并手动提交。';}
  catch {if(!silent)$('recordMsg').textContent='浏览器无法保存草稿，请保留当前页面。';}
}
function restoreDraft(){
  try {const raw=localStorage.getItem(draftKey());if(!raw){$('recordMsg').textContent='当前账号没有暂存草稿。';return;}
    const draft=JSON.parse(raw);resetRecord();fillRecord(draft.row);state.recordId=draft.id;
    if(state.recordId){$('recordFormTitle').textContent='编辑训练记录（草稿）';$('recordSubmit').textContent='保存修改';$('cancelRecord').classList.remove('hidden');}
    $('recordMsg').textContent='已恢复草稿，请核对后提交。';
  } catch {$('recordMsg').textContent='草稿无法读取，请重新填写。';}
}
async function addRecord(){
  if(!$('recordForm').reportValidity())return;
  saveDraft(true);
  await busy($('recordSubmit'),async()=>{
    const editing=state.recordId;
    const epoch=state.epoch;
    try{await api(editing?`/api/records/${editing}`:'/api/records',{method:editing?'PUT':'POST',body:JSON.stringify(recordPayload())});}
    catch(e){if(e.detail?.record_id){$('recordMsg').textContent=e.message+' ';const b=document.createElement('button');b.type='button';b.className='text-button';b.textContent='编辑已有记录';b.addEventListener('click',()=>busy(b,async()=>{const row=await api(`/api/records/${e.detail.record_id}`);if(epoch!==state.epoch)return;if(!state.records.some(r=>r.id===row.id))state.records.push(row);editRecord(row.id);},'recordMsg'));$('recordMsg').append(b);return;}throw e;}
    if(epoch!==state.epoch)return;
    try{localStorage.removeItem(draftKey());}catch{}
    resetRecord();updateDraftHints();$('recordMsg').textContent='记录已保存，可在首页查看进度。';notify('又记录了一次努力！');await refresh();
  },'recordMsg');
}
async function delRecord(id){if(!confirm('删除这条训练记录？删除后无法恢复。'))return;try{await api(`/api/records/${id}`,{method:'DELETE'});if(state.recordId===id)resetRecord();await refresh();notify('记录已删除');}catch(e){notify(e.message);}}
function renderRecords(){
  $('records').innerHTML=state.records.map(r=>`<article class="record-item"><div class="record-main"><div><h3>${escapeHTML(r.exercise_type)} <span class="pill">${r.duration} 分钟</span></h3><span class="record-date">${escapeHTML(r.exercise_date)}</span></div><div class="record-actions"><button type="button" class="ghost" data-edit-record="${r.id}">编辑</button><button type="button" class="text-button" data-delete-record="${r.id}">删除</button></div></div><p class="record-detail">${r.distance ? `${r.distance} km · ` : ''}强度 ${r.intensity}/5 · ${escapeHTML(r.feeling)}</p>${r.note?`<p class="record-detail">${escapeHTML(r.note)}</p>`:''}</article>`).join('')||'<div class="empty"><b>第一条记录，从今天开始</b>填好上面的训练日记，把这一次努力留住。</div>';
  $('loadMore').classList.toggle('hidden',!state.more);
}
async function loadRecords(append=false){const epoch=state.epoch;const rows=await api(`/api/records?offset=${append?state.records.length:0}&limit=20`);if(epoch!==state.epoch)return;state.records=append?[...state.records,...rows]:rows;state.more=rows.length===20;renderRecords();}
function editPlan(id){const p=state.plans.find(p=>p.id===id);if(!p)return;state.planId=id;$('planTitle').value=p.title;$('planTarget').value=p.target;$('weeklyMinutes').value=p.weekly_minutes;$('planStart').value=p.start_date;$('planEnd').value=p.end_date;$('planFormTitle').textContent='调整运动计划';$('planSubmit').textContent='保存修改';$('cancelPlan').classList.remove('hidden');navigate('plans');$('planForm').scrollIntoView({block:'start'});}
async function createPlan(){if(!$('planForm').reportValidity())return;await busy($('planSubmit'),async()=>{
  const payload={title:$('planTitle').value,target:$('planTarget').value,weekly_minutes:Number($('weeklyMinutes').value),start_date:$('planStart').value,end_date:$('planEnd').value};
  if(payload.end_date<payload.start_date)throw new Error('结束日期不能早于开始日期。');
  await api(state.planId?`/api/plans/${state.planId}`:'/api/plans',{method:state.planId?'PUT':'POST',body:JSON.stringify(payload)});
  try{localStorage.removeItem(extraDraftKey('plan'));}catch{}resetPlan();updateDraftHints();$('planMsg').textContent='计划已保存，首页目标已更新。';await refresh();notify('计划已更新');
},'planMsg');}
async function delPlan(id){if(!confirm('删除这个计划？已有训练记录会保留。'))return;try{await api(`/api/plans/${id}`,{method:'DELETE'});if(state.planId===id)resetPlan();await refresh();notify('计划已删除');}catch(e){notify(e.message);}}
async function loadPlans(){const epoch=state.epoch;const plans=await api('/api/plans');if(epoch!==state.epoch)return;state.plans=plans;const today=localDate();$('plans').innerHTML=plans.map(p=>`<article class="plan-item"><div class="record-main"><h3>${escapeHTML(p.title)}</h3><span class="pill">${p.is_current?'当前用于统计':p.start_date>today?'未开始':p.end_date<today?'已结束':'进行中'}</span></div><p class="record-detail">${escapeHTML(p.target||'保持运动，持续记录')}</p><p class="record-detail">每周 ${p.weekly_minutes} 分钟 · ${escapeHTML(p.start_date)} ～ ${escapeHTML(p.end_date)}</p><div class="record-actions"><button type="button" class="ghost" data-edit-plan="${p.id}">调整计划</button><button type="button" class="text-button" data-delete-plan="${p.id}">删除</button></div></article>`).join('')||'<div class="empty"><b>给自己一个小目标</b>先从一个容易坚持的计划开始。</div>';}
function renderChart(data){const max=Math.max(1,...data.minutes);$('chart').innerHTML=data.labels.map((day,i)=>`<div class="bar-column" role="button" tabindex="0" data-chart="${day}：${data.minutes[i]} 分钟" aria-label="${day}：${data.minutes[i]} 分钟" title="${day}：${data.minutes[i]} 分钟"><div class="bar-track"><div class="bar-fill" style="height:${data.minutes[i]/max*100}%"></div></div><small>${day.slice(8)}</small></div>`).join('');const total=data.minutes.reduce((a,b)=>a+b,0);$('chart').setAttribute('aria-label',data.labels.map((d,i)=>`${d}：${data.minutes[i]} 分钟`).join('；'));$('chartCaption').textContent=total?`${data.labels[0]} ～ ${data.labels.at(-1)} · 共 ${total} 分钟，${data.minutes.filter(x=>x>0).length} 个运动日。`:'还没有运动数据，保存第一条记录后，就能看到自己的节奏。';}
async function refresh(){
  const epoch=state.epoch;
  try {const d=await api('/api/dashboard');if(epoch!==state.epoch)return;state.review=d.review;
    $('mMinutes').textContent=d.summary.total_minutes;$('mDays').textContent=d.summary.active_days;$('mCalories').textContent=d.summary.total_calories;
    $('reviewStatus').textContent=d.review.status;$('reviewText').textContent=`${d.review.period_start} ～ ${d.review.period_end} · 已记录 ${d.review.weekly_minutes} / ${d.review.target} 分钟。`;
    $('progressBar').style.width=Math.min(d.review.completion,100)+'%';$('completionLabel').textContent=`${d.review.plan_id?d.review.plan_title:'默认参考目标（可在计划页设置）'} · 完成 ${d.review.completion}%`;
    $('comparison').textContent=`比前 7 天${d.review.delta_minutes>=0?'多':'少'} ${Math.abs(d.review.delta_minutes)} 分钟 · 运动 ${d.review.active_days} 天`;
    $('reviewPeriod').textContent=`统计区间 ${d.review.period_start} ～ ${d.review.period_end}；对比紧邻的前 7 天。`;
    renderChart(d.chart);await Promise.all([loadPlans(),loadRecords()]);
  }catch(e){notify(e.message);}
}
async function loadReflection(){const epoch=state.epoch;try{const r=await api('/api/reflection');if(epoch!==state.epoch)return;reflectionWeek=r.week_start;if(!reflectionDirty){$('reflection').value=r.reflection;$('nextAction').value=r.next_action;}$('reflectionMsg').textContent=`当前周笔记：${r.week_start} 起，每周一开始新笔记。`;}catch(e){notify(e.message);}}
async function saveReflection(){await busy($('reflectionForm').querySelector('[type=submit]'),async()=>{await api('/api/reflection',{method:'PUT',body:JSON.stringify({reflection:$('reflection').value,next_action:$('nextAction').value})});reflectionDirty=false;try{localStorage.removeItem(extraDraftKey('reflection'));}catch{}updateDraftHints();$('reflectionMsg').textContent='本周复盘已保存。下次登录可以继续查看和调整。';},'reflectionMsg');}
async function getAIAdvice(){const epoch=state.epoch;await busy($('adviceButton'),async()=>{const d=await api('/api/ai-advice',{method:'POST'});if(epoch===state.epoch){$('adviceDetails').open=true;$('aiAdvice').textContent=d.advice;$('adviceSource').textContent=d.source==='model'?'AI 生成建议':'规则建议';}});}
async function exportRecords(){await busy($('exportButton'),async()=>{let all=[],offset=0;while(true){const rows=await api(`/api/records?offset=${offset}&limit=100`);all.push(...rows);if(rows.length<100)break;offset+=rows.length;}const blob=new Blob([JSON.stringify({exported_at:new Date().toISOString(),records:all},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`campus-move-${localDate()}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notify('训练记录已导出');});}
function openInstall(){$('nativeInstall').classList.toggle('hidden',!installPrompt);$('installDialog').showModal();}
function networkState(){$('networkBanner').classList.toggle('hidden',navigator.onLine);}
function extraDraftKey(kind){return `campus-move-${kind}-draft:${state.user?.id}`;}
function updateDraftHints(){
  for(const [key,button,status] of [[draftKey(),'restoreDraft','recordDraftStatus'],[extraDraftKey('plan'),'restorePlanDraft','planDraftStatus'],[extraDraftKey('reflection'),'restoreReflectionDraft','reflectionDraftStatus']]){
    try{const exists=!!localStorage.getItem(key);$(button).classList.toggle('hidden',!exists);$(status).textContent=exists?'有本地草稿，可恢复后继续填写。':'';}catch{}
  }
}
function saveExtraDraft(kind){
  if(!state.user)return;
  const row=kind==='plan'?{title:$('planTitle').value,target:$('planTarget').value,weekly_minutes:$('weeklyMinutes').value,start_date:$('planStart').value,end_date:$('planEnd').value}:{reflection:$('reflection').value,next_action:$('nextAction').value};
  try{localStorage.setItem(extraDraftKey(kind),JSON.stringify({row,id:state.planId,week:reflectionWeek,savedAt:Date.now()}));$(`${kind}DraftStatus`).textContent='已暂存到此浏览器，尚未提交。';$(kind==='plan'?'restorePlanDraft':'restoreReflectionDraft').classList.remove('hidden');}catch{$(`${kind}DraftStatus`).textContent='浏览器无法暂存，请保留此页面。';}
}
function restoreExtraDraft(kind){
  try{
    const d=JSON.parse(localStorage.getItem(extraDraftKey(kind))||'null');if(!d)return;
    if(kind==='plan'){
      state.planId=d.id||null;
      for(const [key,id] of Object.entries({title:'planTitle',target:'planTarget',weekly_minutes:'weeklyMinutes',start_date:'planStart',end_date:'planEnd'}))$(id).value=d.row[key]??'';
      $('planFormTitle').textContent=state.planId?'调整运动计划（草稿）':'制定运动计划（草稿）';$('cancelPlan').classList.toggle('hidden',!state.planId);
    }else{if(d.week && reflectionWeek && d.week!==reflectionWeek && !confirm('这份草稿来自其他周，要复制到本周笔记吗？'))return;$('reflection').value=d.row.reflection;$('nextAction').value=d.row.next_action;reflectionDirty=true;$('reflectionDetails').open=true;}
    $(`${kind}DraftStatus`).textContent='草稿已恢复，请核对后提交。';
  }catch{notify('草稿无法读取，请重新填写。');}
}
async function reflectionHistory(){await busy($('reflectionHistoryButton'),async()=>{
  const epoch=state.epoch,rows=await api('/api/reflections');if(epoch!==state.epoch)return;
  $('reflectionHistory').classList.remove('hidden');$('reflectionHistory').innerHTML=rows.map(r=>`<article class="record-item"><h3>${escapeHTML(r.week_start)} 起的一周</h3><p class="record-detail">${escapeHTML(r.reflection||'未填写感受')}</p><p class="record-detail">下一步：${escapeHTML(r.next_action||'未填写')}</p></article>`).join('')||'<p class="fine">保存第一份周笔记后，就能在这里回顾。</p>';
});}
function bindExperience(){
  window.addEventListener('hashchange',()=>{if(state.user)navigate(location.hash.slice(1)||'home',true);});
  $('recordForm').addEventListener('input',()=>saveDraft(true));
  $('planForm').addEventListener('input',()=>saveExtraDraft('plan'));
  $('reflectionForm').addEventListener('input',()=>{reflectionDirty=true;saveExtraDraft('reflection');});
  $('restorePlanDraft').addEventListener('click',()=>restoreExtraDraft('plan'));
  $('restoreReflectionDraft').addEventListener('click',()=>restoreExtraDraft('reflection'));
  $('reflectionHistoryButton').addEventListener('click',reflectionHistory);
  document.querySelectorAll('[data-duration],[data-sport]').forEach(b=>b.addEventListener('click',()=>{if(b.dataset.duration)$('duration').value=b.dataset.duration;if(b.dataset.sport)$('exerciseType').value=b.dataset.sport;saveDraft(true);}));
  $('chart').addEventListener('click',e=>{const bar=e.target.closest('[data-chart]');if(bar)$('chartSelection').textContent=bar.dataset.chart;});
  $('chart').addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.dataset.chart){e.preventDefault();$('chartSelection').textContent=e.target.dataset.chart;}});
}
function bind(){
  bindExperience();
  for(const [id,fn] of [['authForm',login],['recordForm',addRecord],['planForm',createPlan],['reflectionForm',saveReflection]])$(id).addEventListener('submit',e=>{e.preventDefault();fn();});
  for(const [id,fn] of Object.entries({registerButton:registerUser,logoutButton:logout,cancelRecord:resetRecord,cancelPlan:resetPlan,saveDraft:()=>saveDraft(),restoreDraft,adviceButton:getAIAdvice,exportButton:exportRecords,installButton:openInstall,profileInstall:openInstall,closeInstall:()=>$('installDialog').close(),loadMore:()=>busy($('loadMore'),()=>loadRecords(true)),reloadRecords:()=>busy($('reloadRecords'),()=>loadRecords()),adjustPlan:()=>state.review?.plan_id?editPlan(state.review.plan_id):navigate('plans')}))$(id).addEventListener('click',fn);
  $('navigation').addEventListener('click',e=>{const b=e.target.closest('[data-page]');if(b)navigate(b.dataset.page);});
  document.addEventListener('click',e=>{const b=e.target.closest('[data-go]');if(b)navigate(b.dataset.go);});
  $('records').addEventListener('click',e=>{const b=e.target.closest('button');if(b?.dataset.editRecord)editRecord(Number(b.dataset.editRecord));if(b?.dataset.deleteRecord)delRecord(Number(b.dataset.deleteRecord));});
  $('plans').addEventListener('click',e=>{const b=e.target.closest('button');if(b?.dataset.editPlan)editPlan(Number(b.dataset.editPlan));if(b?.dataset.deletePlan)delPlan(Number(b.dataset.deletePlan));});
  window.addEventListener('offline',networkState);window.addEventListener('online',()=>{networkState();notify('已恢复联网，可手动提交暂存的草稿。');});networkState();
  window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();installPrompt=e;$('nativeInstall').classList.remove('hidden');});
  $('nativeInstall').addEventListener('click',async()=>{if(!installPrompt)return;await installPrompt.prompt();await installPrompt.userChoice;installPrompt=null;$('nativeInstall').classList.add('hidden');$('installDialog').close();});
  if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
}
bind();check().catch(e=>{$('authMsg').textContent=e.message;});
