// Photos are kept only in this document. Failed requests must remain recoverable.
const avatarRecovery = {failed:new Map(), serial:0};
const avatarRetryDelays = [800, 2500, 8000];

function avatarPhotoURL(person){
  if(person?.identity_hidden)return '';
  const url=safeActivityImage(person?.avatar_url);
  const owner=person?.user_id??person?.sender_id??person?.id;
  const mine=state.user&&(owner===state.user.id||url.startsWith(`/api/users/${state.user.id}/avatar?`));
  return mine&&campus.profile&&Object.hasOwn(campus.profile,'avatar_url')
    ?safeActivityImage(campus.profile.avatar_url):url;
}
function avatarPhotoSource(url){
  return identityState.source===url&&identityState.image?identityState.image:url;
}
function avatarPhotoMarkup(person,chat=false){
  const url=avatarPhotoURL(person);if(!url)return '';
  const name=person.display_name||person.username||'同学';
  return `<img data-avatar-photo ${chat?'data-chat-photo':''} data-avatar-source="${escapeHTML(url)}" data-avatar-epoch="${state.epoch}" src="${escapeHTML(avatarPhotoSource(url))}" alt="${escapeHTML(name)}的头像" loading="lazy">`;
}
function forgetAvatarFailure(image){
  const failure=avatarRecovery.failed.get(image);
  if(failure)clearTimeout(failure.timer);
  avatarRecovery.failed.delete(image);
}
function currentAvatarImage(image){
  return !!state.user&&image.isConnected&&Number(image.dataset.avatarEpoch)===state.epoch
    &&!!safeActivityImage(image.dataset.avatarSource);
}
function retryAvatarImage(image,failure){
  if(avatarRecovery.failed.get(image)!==failure)return;
  if(!currentAvatarImage(image)||failure.source!==image.dataset.avatarSource){forgetAvatarFailure(image);return;}
  clearTimeout(failure.timer);failure.timer=null;
  if(document.hidden||navigator.onLine===false)return;
  failure.attempts++;
  // Keep the canonical URL separately; retries must not append to old retry URLs.
  const source=avatarPhotoSource(failure.source);
  image.loading='eager';
  image.src=source.startsWith('blob:')?source:`${source}${source.includes('?')?'&':'?'}retry=${++avatarRecovery.serial}`;
}
function failedAvatarImage(image){
  if(!currentAvatarImage(image))return;
  image.classList.add('hidden');
  image.parentElement.title='头像暂时加载失败，网络恢复后会自动重试';
  let failure=avatarRecovery.failed.get(image);
  if(!failure||failure.source!==image.dataset.avatarSource){
    forgetAvatarFailure(image);
    failure={source:image.dataset.avatarSource,attempts:0,timer:null};
    avatarRecovery.failed.set(image,failure);
  }
  clearTimeout(failure.timer);
  if(failure.attempts<avatarRetryDelays.length){
    failure.timer=setTimeout(()=>retryAvatarImage(image,failure),avatarRetryDelays[failure.attempts]);
  }
}
function retryAvatarPhotos(){
  if(!state.user||document.hidden||navigator.onLine===false)return;
  for(const [image,failure] of avatarRecovery.failed){
    if(!currentAvatarImage(image)){forgetAvatarFailure(image);continue;}
    // An online/resume event starts one bounded recovery cycle, never an interval.
    if(failure.timer)continue;
    failure.attempts=0;retryAvatarImage(image,failure);
  }
  if(!$('retryProfileAvatar').classList.contains('hidden')&&!identityState.uploading&&!identityState.loading){
    loadIdentityImage(campus.profile?.avatar_url,{force:true,saved:!!identityState.preview});
  }
}
function syncOwnAvatarPhotos(){
  if(!state.user||!campus.profile)return;
  const prefix=`/api/users/${state.user.id}/avatar`,url=safeActivityImage(campus.profile.avatar_url);
  for(const image of document.querySelectorAll('img[data-avatar-photo]')){
    if(image.dataset.avatarSource.split('?')[0]!==prefix)continue;
    if(!url){forgetAvatarFailure(image);image.parentElement.title=image.alt.replace(/的头像$/,'');image.remove();continue;}
    image.dataset.avatarSource=url;
    const source=avatarPhotoSource(url);
    image.loading='eager';
    if(image.getAttribute('src')!==source){forgetAvatarFailure(image);image.src=source;}
    if(image.complete&&image.naturalWidth){forgetAvatarFailure(image);image.classList.remove('hidden');}
  }
  if(typeof renderMessageSelf==='function')renderMessageSelf();
  if(typeof updateMessageIdentity==='function'){
    const person={...state.user,...campus.profile};
    for(const id of ['buddyMessages','groupMessages'])updateMessageIdentity($(id),person,state.user.id);
  }
}
function resetAvatarPhotos(){
  for(const image of avatarRecovery.failed.keys())forgetAvatarFailure(image);
  // Also discard pending old-account images outside the message page.
  document.querySelectorAll('img[data-avatar-photo]').forEach(image=>image.remove());
}
document.addEventListener('error',event=>{
  if(event.target.matches?.('img[data-avatar-photo]'))failedAvatarImage(event.target);
},true);
document.addEventListener('load',event=>{
  const image=event.target;
  if(!image.matches?.('img[data-avatar-photo]')||!currentAvatarImage(image))return;
  forgetAvatarFailure(image);image.classList.remove('hidden');
  image.parentElement.title=image.alt.replace(/的头像$/,'');
},true);
window.addEventListener('online',retryAvatarPhotos);
window.addEventListener('pageshow',retryAvatarPhotos);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)retryAvatarPhotos();});
