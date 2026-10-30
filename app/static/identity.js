const identityState={uploading:false,preview:null};
function renderIdentity(profile,fill=false){
  if(!state.user)return;
  const name=profile.display_name||state.user.username;
  $('userArea').textContent=name;$('greetingName').textContent=name;
  $('profileBioText').textContent=profile.bio||'写一句介绍，让同伴更了解你。';
  $('profileAccountLabel').textContent=`账号 @${state.user.username}`;
  $('profileAvatarFallback').textContent=Array.from(name)[0]||'动';
  const image=$('profileAvatarPreview'),hasAvatar=!!profile.avatar_url;
  if(hasAvatar)image.src=profile.avatar_url;else image.removeAttribute('src');
  image.classList.toggle('hidden',!hasAvatar);$('profileAvatarFallback').classList.toggle('hidden',hasAvatar);
  $('removeProfileAvatar').classList.toggle('hidden',!hasAvatar);
  if(fill){$('profileNickname').value=profile.nickname||'';$('profileBio').value=profile.bio||'';}
}
function resetIdentity(){
  if(identityState.preview)URL.revokeObjectURL(identityState.preview);
  identityState.preview=null;identityState.uploading=false;
  $('identityForm').reset();$('profileAvatarFile').value='';$('profileAvatarFile').disabled=false;
  $('profileAvatarPreview').removeAttribute('src');$('profileAvatarPreview').classList.add('hidden');
  $('profileAvatarFallback').classList.remove('hidden');$('profileAvatarFallback').textContent='动';
  $('removeProfileAvatar').classList.add('hidden');$('removeProfileAvatar').disabled=false;$('identitySave').disabled=false;$('identityMsg').textContent='';$('avatarMsg').textContent='照片选填，支持 JPEG、PNG、WebP，最多 5 MB。';
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
  const preview=URL.createObjectURL(file);identityState.preview=preview;
  $('profileAvatarPreview').src=preview;$('profileAvatarPreview').classList.remove('hidden');$('profileAvatarFallback').classList.add('hidden');
  $('avatarMsg').textContent='正在保存头像…';
  try{
    const form=new FormData();form.append('file',file);
    await saveIdentityChange('/api/profile/avatar',{method:'POST',body:form});
    if(epoch!==state.epoch)return;$('avatarMsg').textContent='头像已保存，下次登录仍会保留。';
    if(typeof homeDiscoveryRefresh==='function')homeDiscoveryRefresh();
  }catch(error){if(epoch===state.epoch){renderIdentity(campus.profile||{});$('avatarMsg').textContent=error.message;}}
  finally{URL.revokeObjectURL(preview);if(epoch===state.epoch){identityState.uploading=false;identityState.preview=null;input.disabled=false;input.value='';$('removeProfileAvatar').disabled=false;}}
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
$('profileAvatarPreview').addEventListener('error',()=>{$('profileAvatarPreview').classList.add('hidden');$('profileAvatarFallback').classList.remove('hidden');});
