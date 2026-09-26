let chart;
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function localDate(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}

async function api(url, options={}) {
  const r = await fetch(url, {headers: {'Content-Type':'application/json'}, ...options});
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    if (r.status === 401) showAuth();
    const detail = Array.isArray(d.detail)
      ? d.detail.map(item => `${item.loc?.slice(1).join('.') || '输入'}: ${item.msg}`).join('；')
      : d.detail;
    throw new Error(detail || `请求失败（${r.status}）`);
  }
  return d;
}
async function check(){const m=await api('/api/me'); if(m.logged_in) showApp(m.username); else showAuth();}
function showAuth(){ $('authPanel').classList.remove('hidden'); $('appPanel').classList.add('hidden'); $('userArea').textContent=''; $('aiAdvice').textContent='点击“生成建议”'; }
function showApp(name){ $('authPanel').classList.add('hidden'); $('appPanel').classList.remove('hidden'); $('userArea').textContent=`当前用户：${name}`; $('recordDate').value=localDate(); const now=new Date();$('planStart').value=localDate(now); $('planEnd').value=localDate(new Date(now.getFullYear(), now.getMonth(), now.getDate()+30)); refresh(); }
async function login(){try{const d=await api('/api/login',{method:'POST',body:JSON.stringify({username:$('username').value,password:$('password').value})});$('authMsg').textContent=d.message;await check()}catch(e){$('authMsg').textContent=e.message}}
async function registerUser(){try{const d=await api('/api/register',{method:'POST',body:JSON.stringify({username:$('username').value,password:$('password').value})});$('authMsg').textContent=d.message}catch(e){$('authMsg').textContent=e.message}}
async function logout(){try{await api('/api/logout',{method:'POST'});showAuth()}catch(e){$('recordMsg').textContent=e.message}}
async function createPlan(){try{await api('/api/plans',{method:'POST',body:JSON.stringify({title:$('planTitle').value,target:$('planTarget').value,weekly_minutes:Number($('weeklyMinutes').value),start_date:$('planStart').value,end_date:$('planEnd').value})});$('planMsg').textContent='计划已保存';await refresh()}catch(e){$('planMsg').textContent=e.message}}
async function loadPlans(){const ps=await api('/api/plans');$('plans').innerHTML=ps.map(p=>`<div class="review-box" style="margin-top:10px"><b>${escapeHTML(p.title)}</b><br>${escapeHTML(p.target||'暂无具体目标')}<br>每周 ${p.weekly_minutes} 分钟｜${p.start_date} ～ ${p.end_date}</div>`).join('')||'<p class="muted">还没有计划。</p>'}
async function addRecord(){try{await api('/api/records',{method:'POST',body:JSON.stringify({exercise_date:$('recordDate').value,exercise_type:$('exerciseType').value,duration:Number($('duration').value),distance:Number($('distance').value||0),intensity:Number($('intensity').value),calories:Number($('calories').value||0),feeling:$('feeling').value,note:$('note').value})});$('recordMsg').textContent='记录成功';$('duration').value='';$('distance').value='';$('calories').value='';$('note').value='';refresh()}catch(e){$('recordMsg').textContent=e.message}}
async function loadRecords(){const rs=await api('/api/records');$('records').innerHTML=rs.map(r=>`<tr><td>${r.exercise_date}</td><td>${escapeHTML(r.exercise_type)}</td><td>${r.duration} 分</td><td>${r.distance} km</td><td>${r.intensity}</td><td>${escapeHTML(r.feeling)}</td><td>${escapeHTML(r.note||'')}</td><td><button class="ghost" onclick="delRecord(${r.id})">删</button></td></tr>`).join('')||'<tr><td colspan="8">暂无记录</td></tr>'}
async function delRecord(id){if(!confirm('确定删除这条记录吗？'))return;try{await api(`/api/records/${id}`,{method:'DELETE'});await refresh()}catch(e){$('recordMsg').textContent=e.message}}
async function refresh(){try{const d=await api('/api/dashboard');$('mMinutes').textContent=d.summary.total_minutes;$('mDays').textContent=d.summary.active_days;$('mCalories').textContent=d.summary.total_calories;$('reviewStatus').textContent=d.review.status;$('reviewText').textContent=`近7天 ${d.review.weekly_minutes} 分钟 / 目标 ${d.review.target} 分钟。${d.review.advice}`;$('progressBar').style.width=Math.min(d.review.completion,100)+'%';if(chart)chart.destroy();if(typeof Chart !== 'undefined') chart=new Chart($('chart'),{type:'line',data:{labels:d.chart.labels,datasets:[{label:'分钟',data:d.chart.minutes,tension:.35}]},options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true}}}});await loadPlans();await loadRecords();}catch(e){$('recordMsg').textContent=e.message;}}
async function getAIAdvice(){ $('aiAdvice').textContent='生成中...';try{const d=await api('/api/ai-advice',{method:'POST'});$('aiAdvice').textContent=d.advice}catch(e){$('aiAdvice').textContent=e.message}}
check().catch(e => {$('authMsg').textContent=e.message;});
