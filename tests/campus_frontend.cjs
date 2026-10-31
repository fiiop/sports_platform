const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const tick=()=>new Promise(resolve=>setImmediate(resolve));

async function themes(){
  const nodes=new Map(),requests=[],root={dataset:{}},state={epoch:1};
  const element=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',value:'',classList:{toggle(){}}});return nodes.get(id);};
  const context=vm.createContext({state,$:element,document:{documentElement:root,querySelector:()=>({}),querySelectorAll:()=>[]},
    matchMedia:()=>({matches:false}),localStorage:{setItem(){}},
    api:async(url,options)=>new Promise((resolve,reject)=>requests.push({body:JSON.parse(options.body),resolve,reject}))});
  const source=fs.readFileSync('app/static/campus.js','utf8');
  vm.runInContext(source.slice(0,source.indexOf("$('campusProfileForm').addEventListener")),context);
  vm.runInContext("campus.profile={school:'湘潭大学',theme:'forest'};campus.profileReady=Promise.resolve()",context);
  const first=vm.runInContext("saveTheme('ocean')",context);
  const second=vm.runInContext("saveTheme('lilac')",context);
  const school=vm.runInContext("saveProfilePatch({school:'另一所大学'})",context);
  await tick();assert.equal(requests.length,1);assert.equal(root.dataset.theme,'lilac');
  requests[0].resolve(requests[0].body);await first;await tick();
  assert.equal(requests.length,2);assert.equal(requests[1].body.theme,'lilac');
  assert.equal(root.dataset.theme,'lilac');
  requests[1].resolve(requests[1].body);await second;await tick();
  assert.equal(requests[2].body.theme,'lilac');assert.equal(requests[2].body.school,'另一所大学');
  requests[2].resolve(requests[2].body);await school;
  const failed=vm.runInContext("saveTheme('night')",context);await tick();
  requests[3].reject(new Error('offline'));await failed;
  assert.equal(root.dataset.theme,'lilac');assert.equal(element('themeMsg').textContent,'offline');
  const stale=vm.runInContext("saveTheme('forest')",context);state.epoch++;await stale;
  assert.equal(requests.length,4,'a queued save must not run under a different login');
}

async function identity(){
  const requests=[],nodes=new Map(),state={epoch:1,user:{username:'student'}};
  const element=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',classList:{toggle(){},add(){},remove(){}},getAttribute(){return this.src;},removeAttribute(){}});return nodes.get(id);};
  const context=vm.createContext({state,$:element,AbortController,setTimeout,clearTimeout,
    URL:{createObjectURL:()=>`blob:test-${Math.random()}`,revokeObjectURL(){}},Image:class{decode(){return Promise.resolve();}},
    fetch:async()=>({ok:true,headers:{get:()=> 'image/jpeg'},blob:async()=>({size:10})}),
    api:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
  vm.runInContext("let profileQueue=Promise.resolve();const campus={profile:null};let ready;campus.profileReady=new Promise(resolve=>ready=resolve)",context);
  const source=fs.readFileSync('app/static/identity.js','utf8');
  vm.runInContext(source.slice(0,source.indexOf("$('identityForm').addEventListener")),context);
  const name=vm.runInContext("saveIdentityChange('/api/profile/identity',{method:'PUT'})",context);
  const photo=vm.runInContext("saveIdentityChange('/api/profile/avatar',{method:'POST'})",context);
  await tick();assert.equal(requests.length,0,'wait for the initial profile before saving');
  vm.runInContext("campus.profile={school:'湘潭大学'};ready()",context);
  await tick();assert.equal(requests.length,1,'identity and image saves are serialized');
  requests[0].resolve({nickname:'同学',display_name:'同学',bio:'一起打球',avatar_url:null});await name;await tick();
  assert.equal(requests.length,2);assert.equal(element('userArea').textContent,'同学');
  requests[1].resolve({nickname:'同学',display_name:'同学',bio:'一起打球',avatar_url:'/api/users/1/avatar?v=2'});await photo;
  assert.equal(vm.runInContext('campus.profile.avatar_url',context),'/api/users/1/avatar?v=2');
  const failed=vm.runInContext("saveIdentityChange('/api/profile/identity',{method:'PUT'})",context);
  const handled=assert.rejects(failed,/offline/);await tick();requests[2].reject(new Error('offline'));await handled;
  const recover=vm.runInContext("saveIdentityChange('/api/profile/avatar',{method:'DELETE'})",context);
  await tick();assert.equal(requests.length,4);requests[3].resolve({display_name:'同学',avatar_url:null});await recover;
  const stale=vm.runInContext("saveIdentityChange('/api/profile/identity',{method:'PUT'})",context);
  state.epoch++;await stale;assert.equal(requests.length,4,'queued saves cannot run as the next account');
}

async function worker(){
  const listeners={},shown=[],opened=[],navigated=[],focused=[],fetched=[];
  let response={ok:true,show:false},windows=[];
  const context=vm.createContext({URL,URLSearchParams,fetch:async(url,options)=>{fetched.push({url,options});return {ok:response.ok,json:async()=>response};},
    self:{location:{origin:'https://campus.example'},addEventListener:(name,fn)=>listeners[name]=fn,
      registration:{showNotification:async(title,options)=>shown.push({title,options})},
      clients:{matchAll:async()=>windows,openWindow:async url=>opened.push(url)}},caches:{}});
  vm.runInContext(fs.readFileSync('app/static/sw.js','utf8'),context);
  async function emit(type,fields){let result;listeners[type]({...fields,waitUntil:promise=>result=promise});await result;}
  const push=data=>emit('push',{data:{json:()=>data}});
  await push(null);await push({user_id:-1});assert.equal(fetched.length,0);
  await push({user_id:1,notice_id:2});assert.equal(shown.length,0,'read or wrong-account pushes stay hidden');
  response={ok:false};await push({user_id:1,notice_id:2});assert.equal(shown.length,0);
  response={ok:true,show:true,url:'/#messages/3'};
  await push({user_id:1,notice_id:2});assert.equal(shown.length,1);
  assert.equal(fetched.at(-1).options.credentials,'same-origin');assert.equal(shown[0].options.data.url,'/#messages/3');
  const click=url=>emit('notificationclick',{notification:{close(){},data:{url}}});
  await click('https://unrelated.example/');assert.equal(opened.length,0);
  await click('/#messages/3');assert.deepEqual(opened,['https://campus.example/#messages/3']);
  windows=[{url:'https://campus.example/',navigate:async url=>navigated.push(url),focus:async()=>focused.push(true)}];
  await click('/#buddies/group/7');assert.deepEqual(navigated,['https://campus.example/#buddies/group/7']);assert.equal(focused.length,1);
  listeners.fetch({request:{url:'https://campus.example/api/profile',method:'GET'},respondWith(){throw new Error('private API must not be cached');}});
}

(async()=>{await themes();await identity();await worker();console.log('PASS: serialized theme/school/identity saves, upload initialization, failure recovery, login isolation, push validation and notification navigation');})().catch(error=>{console.error(error);process.exitCode=1;});
