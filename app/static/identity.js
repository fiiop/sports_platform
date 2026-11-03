const identityState={uploading:false,preview:null,image:null,source:null,request:null,loading:null,controller:null,generation:0};
const avatarHelp='照片选填，支持 JPEG、PNG、WebP，最多 5 MB。';
function showIdentityImage(url){
  const image=$('profileAvatarPreview');
  if(url){if(image.getAttribute('src')!==url)image.src=url;}else image.removeAttribute('src');
  image.classList.toggle('hidden',!url);$('profileAvatarFallback').classList.toggle('hidden',!!url);
}
function releaseIdentityImage(key){if(identityState[key])URL.revokeObjectURL(identityState[key]);identityState[key]=null;}
function cancelIdentityImage(){identityState.generation++;identityState.controller?.abort();identityState.controller=null;identityState.loading=null;identityState.request=null;}
async function decodedAvatar(url,signal){
  const response=await fetch(url,{credentials:'same-origin',cache:'no-store',signal});
  if(!response.ok){const error=new Error('头像暂时无法读取');error.status=response.status;throw error;}
  if(!(response.headers.get('content-type')||'').startsWith('image/'))throw new Error('头像图片无法读取');
  const blob=await response.blob();if(blob.size>5*1024*1024)throw new Error('头像图片过大');
  const objectURL=URL.createObjectURL(blob),image=new Image();
  try{image.src=objectURL;await image.decode();return objectURL;}
  catch(error){URL.revokeObjectURL(objectURL);throw error;}
}
function loadIdentityImage(source,{force=false,saved=false}={}){
  if(!source){cancelIdentityImage();releaseIdentityImage('preview');releaseIdentityImage('image');identityState.source=null;showIdentityImage(null);$('retryProfileAvatar').classList.add('hidden');return Promise.resolve(false);}
  if(!force&&identityState.source===source&&identityState.image){showIdentityImage(identityState.image);return Promise.resolve(true);}
  if(!force&&identityState.request===source&&identityState.loading)return identityState.loading;
  cancelIdentityImage();const generation=identityState.generation,epoch=state.epoch,controller=new AbortController();
  identityState.controller=controller;identityState.request=source;
  $('retryProfileAvatar').classList.add('hidden');$('avatarMsg').textContent=saved?'头像已保存，正在加载图片…':'正在加载头像…';
  const current=()=>generation===identityState.generation&&epoch===state.epoch;
  const timeout=setTimeout(()=>controller.abort(),20000);
  identityState.loading=(async()=>{
    try{
      let objectURL;
      for(let attempt=0;attempt<2;attempt++){
        try{objectURL=await decodedAvatar(source,controller.signal);break;}
        catch(error){if(!current()||controller.signal.aborted||attempt===1||(error.status&&error.status<500))throw error;}
      }
      if(!current()){URL.revokeObjectURL(objectURL);return false;}
      const old=identityState.image;identityState.image=objectURL;identityState.source=source;showIdentityImage(objectURL);
      if(typeof syncOwnAvatarPhotos==='function')syncOwnAvatarPhotos();
      if(old)URL.revokeObjectURL(old);releaseIdentityImage('preview');
      $('avatarMsg').textContent=saved?'头像已保存，下次登录仍会保留。':avatarHelp;
      $('retryProfileAvatar').classList.add('hidden');return true;
    }catch(error){
      if(current()){
        // A failed download must not discard the selected photo or claim it was removed.
        showIdentityImage(identityState.preview||identityState.image);
        $('avatarMsg').textContent=saved?'头像已保存，但图片暂时加载失败，请重试。':'头像暂时加载失败，请重试。';
        $('retryProfileAvatar').classList.remove('hidden');
      }
      return false;
    }finally{clearTimeout(timeout);if(current()){identityState.loading=null;identityState.controller=null;identityState.request=null;}}
  })();
  return identityState.loading;
}
function renderIdentity(profile,fill=false){
  if(!state.user)return;
  const name=profile.display_name||state.user.username;
  $('userArea').textContent=name;$('greetingName').textContent=name;
  $('profileBioText').textContent=profile.bio||'写一句介绍，让同伴更了解你。';
  $('profileAccountLabel').textContent=`账号 @${state.user.username}`;
  $('profileAvatarFallback').textContent=Array.from(name)[0]||'动';
  $('removeProfileAvatar').classList.toggle('hidden',!profile.avatar_url);
  if(!identityState.uploading)loadIdentityImage(profile.avatar_url);
  if(typeof syncOwnAvatarPhotos==='function')syncOwnAvatarPhotos();
  else if(typeof renderMessageSelf==='function')renderMessageSelf();
  if(fill){$('profileNickname').value=profile.nickname||'';$('profileBio').value=profile.bio||'';}
}
function resetIdentity(){
  if(typeof resetAvatarPhotos==='function')resetAvatarPhotos();
  cancelIdentityImage();releaseIdentityImage('preview');releaseIdentityImage('image');
  identityState.source=null;identityState.uploading=false;
  $('identityForm').reset();$('profileAvatarFile').value='';$('profileAvatarFile').disabled=false;
  $('profileAvatarPreview').removeAttribute('src');$('profileAvatarPreview').classList.add('hidden');
  $('profileAvatarFallback').classList.remove('hidden');$('profileAvatarFallback').textContent='动';
  $('removeProfileAvatar').classList.add('hidden');$('removeProfileAvatar').disabled=false;$('identitySave').disabled=false;$('retryProfileAvatar').classList.add('hidden');$('identityMsg').textContent='';$('avatarMsg').textContent=avatarHelp;
  $('profileBioText').textContent='写一句介绍，让同伴更了解你。';$('profileAccountLabel').textContent='';
}
function acceptIdentity(data,fill=false){Object.assign(campus.profile,data);renderIdentity(campus.profile,fill);}
function saveIdentityChange(url,options){
  const epoch=state.epoch;
  const task=profileQueue.catch(()=>{}).then(async()=>{
    await campus.profileReady;
    if(epoch!==state.epoch)return null;
    if(!campus.profile)throw new Error('个人资料尚未加载，请刷新页面后重试。');
    const result=await api(url,options);
    if(epoch!==state.epoch)return null;
    acceptIdentity(result);return result;
  });
  profileQueue=task;return task;
}
async function uploadAvatar(){
  const input=$('profileAvatarFile'),file=input.files?.[0];if(!file||identityState.uploading)return;
  if(file.size>5*1024*1024){$('avatarMsg').textContent='图片不能超过 5 MB，请选择较小的照片。';input.value='';return;}
  const epoch=state.epoch;identityState.uploading=true;input.disabled=true;$('removeProfileAvatar').disabled=true;
  cancelIdentityImage();releaseIdentityImage('preview');$('retryProfileAvatar').classList.add('hidden');
  const preview=URL.createObjectURL(file);identityState.preview=preview;
  showIdentityImage(preview);
  $('avatarMsg').textContent='正在保存头像…';
  try{
    const form=new FormData();form.append('file',file);
    await saveIdentityChange('/api/profile/avatar',{method:'POST',body:form});
    if(epoch!==state.epoch)return;
    await loadIdentityImage(campus.profile.avatar_url,{force:true,saved:true});
    if(epoch!==state.epoch)return;
    if(typeof homeDiscoveryRefresh==='function')homeDiscoveryRefresh();
  }catch(error){if(epoch===state.epoch){releaseIdentityImage('preview');showIdentityImage(identityState.image);$('avatarMsg').textContent=error.message;}}
  finally{if(epoch===state.epoch){identityState.uploading=false;input.disabled=false;input.value='';$('removeProfileAvatar').disabled=false;}}
}
$('identityForm').addEventListener('submit',event=>{
  event.preventDefault();if(!$('identityForm').reportValidity())return;
  busy($('identitySave'),async()=>{
    const epoch=state.epoch;
    await saveIdentityChange('/api/profile/identity',{method:'PUT',body:JSON.stringify({nickname:$('profileNickname').value.trim(),bio:$('profileBio').value.trim()})});
    if(epoch!==state.epoch)return;$('identityMsg').textContent='资料已保存，同伴会看到你的新介绍。';
    if(typeof homeDiscoveryRefresh==='function')homeDiscoveryRefresh();
  },'identityMsg');
});
$('profileAvatarFile').addEventListener('change',uploadAvatar);
$('removeProfileAvatar').addEventListener('click',()=>busy($('removeProfileAvatar'),async()=>{
  const epoch=state.epoch;await saveIdentityChange('/api/profile/avatar',{method:'DELETE'});
  if(epoch!==state.epoch)return;$('avatarMsg').textContent='头像已移除，已恢复默认头像。';
  if(typeof homeDiscoveryRefresh==='function')homeDiscoveryRefresh();
},'avatarMsg'));
$('retryProfileAvatar').addEventListener('click',()=>busy($('retryProfileAvatar'),()=>loadIdentityImage(campus.profile?.avatar_url,{force:true,saved:!!identityState.preview}),'avatarMsg'));
