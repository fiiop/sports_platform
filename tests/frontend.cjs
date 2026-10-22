const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, {classList: {add(){}, remove(){}, toggle(){}}, style: {}, value:'', reset(){}});
  return elements.get(id);
};
const attack = '<img src=x onerror=alert(1)>';
const storage = new Map();
const context = vm.createContext({AbortController,setTimeout,clearTimeout,document: {getElementById: element},
  localStorage: {setItem:(k,v)=>storage.set(k,v),getItem:k=>storage.get(k),removeItem:k=>storage.delete(k)},
  fetch: async url => ({ok:true,json:async()=>url==='/api/plans'?[{id:1,title:attack,target:attack,weekly_minutes:60,start_date:'2026-01-01',end_date:'2026-12-31'}]:[{id:1,exercise_date:'2026-01-01',exercise_type:attack,duration:60,distance:0,intensity:3,feeling:attack,note:attack}]})});
const source=fs.readFileSync('app/static/app.js','utf8');
vm.runInContext(source.slice(0,source.lastIndexOf('bind();check()')),context);
(async()=>{
  await vm.runInContext('loadPlans()',context);
  await vm.runInContext('loadRecords()',context);
  for(const id of ['plans','records']){assert.ok(!element(id).innerHTML.includes('<img'));assert.ok(element(id).innerHTML.includes('&lt;img'));}
  assert.equal(vm.runInContext('localDate(new Date(2026,0,2,0,1))',context),'2026-01-02');
  vm.runInContext('state.user={id:1};saveDraft(true)',context);
  assert.ok(storage.has('campus-move-draft:1'));
  vm.runInContext('state.user={id:2};restoreDraft()',context);
  assert.ok(element('recordMsg').textContent.includes('没有'));
  console.log('PASS: rendered HTML escaping, local date and per-account draft isolation');
})().catch(e=>{console.error(e);process.exitCode=1});
