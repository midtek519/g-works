/* G-WORKS SHARED DIALOGS: GENERATED FROM App/Desktop/dialogs.js */
/* Local dialogs for every desktop document and embedded module. No bridge/data export. */
(() => {
  if(window.GWorksDialogs)return;
  let pending=null;
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function styles(){
    if(!document.head)return;
    const style=document.createElement('style');style.textContent=`
      dialog.gworks-confirmation{box-sizing:border-box;width:min(520px,calc(100vw - 32px));max-height:calc(100vh - 32px);overflow:auto;padding:20px!important;border:1px solid var(--line,#c7d4e7)!important;border-radius:10px;background:var(--paper,#f4f7fc)!important;color:var(--ink,#20334d)!important;font:13px/1.5 'Segoe UI',system-ui,sans-serif;box-shadow:0 18px 60px #10233c40}
      .gworks-confirmation::backdrop{background:#10233c66}.gworks-confirmation h2{margin:0 0 12px;font:600 18px/1.4 'Segoe UI',sans-serif;color:inherit!important}.gworks-confirmation p{white-space:pre-line;margin:0 0 20px;overflow-wrap:anywhere}.gworks-confirmation label{display:block;font-size:12px;font-weight:600;margin-bottom:16px}.gworks-confirmation input{display:block;box-sizing:border-box;width:100%;margin-top:5px;padding:8px;border:1px solid var(--line,#c7d4e7);border-radius:5px;background:var(--paper,#fff);color:inherit;font:inherit}.gworks-confirmation-actions{display:flex;justify-content:flex-end;gap:8px}.gworks-confirmation button{padding:7px 14px;border:1px solid var(--line,#c7d4e7);border-radius:5px;background:var(--paper,#fff);color:inherit;font:inherit;cursor:pointer}.gworks-confirmation button.primary{background:var(--accent,#2465ab)!important;color:white!important;border-color:var(--accent,#2465ab)!important}
    `;document.head.append(style);
  }
  if(document.head)styles();else document.addEventListener('DOMContentLoaded',styles,{once:true});
  function open({title='Confirm action',text,confirmLabel='Continue',cancelLabel='Cancel',input=false,defaultValue='',maxLength=160}){
    if(pending)return Promise.resolve(input?null:false);
    return new Promise((resolve,reject)=>{
      const previous=document.activeElement,dialog=document.createElement('dialog');let settled=false;
      dialog.className='gworks-confirmation';dialog.setAttribute('data-gworks-dialog','');dialog.setAttribute('aria-labelledby','gworks-dialog-title');
      const finish=accepted=>{
        if(settled)return;settled=true;
        const value=input?(accepted?dialog.querySelector('[data-dialog-input]').value:null):!!accepted;
        pending=null;dialog.remove();if(previous?.isConnected)previous.focus?.();resolve(value);
      };
      maxLength=Number.isInteger(maxLength)?Math.max(1,Math.min(1000,maxLength)):160;
      dialog.innerHTML='<h2 id="gworks-dialog-title">'+escape(title)+'</h2><p>'+escape(text)+'</p>'+(input?'<label>'+escape(title)+'<input data-dialog-input maxlength="'+maxLength+'" autocomplete="off" value="'+escape(defaultValue)+'"></label>':'')+'<div class="gworks-confirmation-actions"><button type="button" data-project-confirm="cancel">'+escape(cancelLabel)+'</button><button type="button" class="primary" data-project-confirm="accept">'+escape(confirmLabel)+'</button></div>';
      dialog.addEventListener('click',event=>{const button=event.target.closest?.('[data-project-confirm]');if(button){event.preventDefault();event.stopPropagation?.();finish(button.dataset.projectConfirm==='accept');}});
      dialog.addEventListener('cancel',event=>{event.preventDefault();finish(false);});dialog.addEventListener('close',()=>finish(false));
      dialog.addEventListener('keydown',event=>{if(input&&event.key==='Enter'&&!event.isComposing){event.preventDefault();finish(true);}});
      pending={dialog,finish};
      try{document.body.append(dialog);dialog.showModal();const focus=dialog.querySelector(input?'[data-dialog-input]':'[data-project-confirm="cancel"]');focus?.focus();if(input)focus?.select?.();}
      catch{pending=null;dialog.remove();reject(Error('The confirmation could not open. Save your work and reload the app.'));}
    });
  }
  // Parent navigation uses synthetic module clicks. Keep them from bypassing an open prompt.
  document.addEventListener('click',event=>{if(pending&&!event.target.closest?.('[data-gworks-dialog]')){event.preventDefault();event.stopImmediatePropagation?.();}},true);
  document.addEventListener('keydown',event=>{if(pending&&event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation?.();pending.finish(false);}},true);
  window.addEventListener('pagehide',()=>pending?.finish(false));
  window.GWorksDialogs={confirm:(text,options={})=>open({text,...options}),prompt:(title,defaultValue='',options={})=>open({title,text:'Enter a value, then save.',confirmLabel:'Save',input:true,defaultValue,...options}),get busy(){return !!pending;}};
})();

/* END G-WORKS SHARED DIALOGS */
/* General AI account controls. Backend returns metadata, never credentials. */
window.GScopeGeneralAI=(()=>{
 'use strict';let C,data=null,account=null,baseline='',loading=false,busy=false,error='',status='',poll=null,visible=false;
 const dirty=()=>!!data&&JSON.stringify(data)!==baseline;
 const render=()=>{if(C.S.view==='settings')C.render();};
 const button=(label,action,disabled=false)=>C.button(label,'general-ai-'+action,disabled?'disabled':'');
 const option=(id,label,current)=>C.option(id,label,current),esc=x=>C.esc(x);
 function discard(){if(baseline)data=JSON.parse(baseline);}
 function view(){
  if(!data)return '<section class="card"><h2>General AI</h2><p role="status">'+esc(error||'Loading connection settings…')+'</p>'+(error?button('Retry','reload'):'')+'</section>';
  const connected=account?.connected&&account.sharing,models=account?.models||[],model=models.find(x=>x.id===data.model),levels=model?.efforts||[],inactive=busy?' disabled':'';
  return '<section class="card g2-general-ai"><h2>General AI</h2><p class="help">Blank exam solution and rubric drafts. Reviewed free-response crops can use online AI through the explicit grading review.</p><label>Connection<select data-general-ai="provider"'+inactive+'>'+option('local','Use the local AI connection',data.provider)+option('chatgpt','ChatGPT account',data.provider)+'</select></label>'+(data.provider==='chatgpt'?
   (account?.profiles?.length?'<label>Account<select data-general-account'+inactive+'>'+account.profiles.map(p=>option(p.id,p.label+(p.connected?'':' · signed out'),account.active)).join('')+'</select></label>':'')+
   '<p role="status">'+esc(account?.message||(connected?'ChatGPT connected.':account?.connected?'Reconnect and allow ChatGPT plan usage.':'No ChatGPT account connected.'))+'</p><div class="row">'+button(account?.connected?'Reconnect ChatGPT':'Continue with ChatGPT','start',busy||account?.pending)+(account?.pending?button('Cancel sign-in','cancel'):account?.profiles?.length?button('Add account','add',busy):'')+(account?.connected?button('Sign out','signout',busy):'')+'</div><div class="row"><label>Model<select data-general-ai="model"'+(busy||!connected||!models.length?' disabled':'')+'>'+option('','Choose a model',data.model)+models.map(m=>option(m.id,m.label||m.id,data.model)).join('')+(data.model&&!model?option(data.model,data.model+' · unavailable',data.model):'')+'</select></label><label>Thinking<select data-general-ai="effort"'+(busy||!model||!levels.length?' disabled':'')+'>'+option('default','Model default',data.effort)+levels.map(level=>option(level,level[0].toUpperCase()+level.slice(1),data.effort)).join('')+'</select></label></div><div class="row">'+button('Refresh models','models',busy||!connected)+'</div>':'')+
   '<div class="g2-save-row">'+button('Save General AI settings','save',busy||data.provider==='chatgpt'&&(!connected||!model))+'<span class="help" role="status">'+esc(error||status)+'</span></div></section>';
 }
 function schedule(){clearTimeout(poll);poll=null;if(account?.pending&&C.S.view==='settings')poll=setTimeout(pollAccount,1500);}
 async function pollAccount(){
  try{const wasPending=account?.pending;account=await C.api('/api/general-ai/account');if(wasPending&&!account.pending&&account.connected&&account.sharing){account=await C.api('/api/general-ai/account/models',{});status='ChatGPT connected. Choose a model and save.';}if(account.welcome){C.message('Eligible General AI requests can now use your ChatGPT plan.');account=await C.api('/api/general-ai/account/welcome',{});}error='';schedule();}
  catch(e){error=e.message;}finally{render();}
 }
 async function mount(){
  if(C.S.view!=='settings'){visible=false;clearTimeout(poll);poll=null;return;}
  if(loading||busy)return;const entered=!visible;visible=true;if(data&&!entered)return;if(error&&!data)return;
  loading=true;
  try{if(!data){const result=await C.api('/api/general-ai/settings');data=result.configuration;account=result.account;baseline=JSON.stringify(data);}else account=await C.api('/api/general-ai/account');error='';schedule();}
  catch(e){error=e.message;}finally{loading=false;render();}
 }
 async function change(el){
  if(el.dataset.generalAccount!==undefined){await action({dataset:{action:'general-ai-select',profile:el.value}});return true;}
  const key=el.dataset.generalAi;if(!key||!data||busy)return false;if(!['provider','model','effort'].includes(key))return false;
  data[key]=el.value;if(key==='provider'){data.model='';data.effort='default';}if(key==='model')data.effort='default';error='';status='';render();return true;
 }
 async function action(el){
  const value=el.dataset.action||'';if(!value.startsWith('general-ai-'))return false;let command=value.slice(11);
  if(command==='reload'){error='';visible=false;await mount();return true;}
  if(busy||!data)return true;if(!['save','start','add','select','cancel','signout','models'].includes(command))return true;
  busy=true;error='';status='';render();
  try{
   if(command==='save'){const result=await C.api('/api/general-ai/settings',{provider:data.provider,model:data.model,effort:data.effort});data=result.configuration;account=result.account||account;baseline=JSON.stringify(data);if(C.S.boot)C.S.boot.generalAI=result.connection||result.configuration;status='Shared General AI settings saved.';}
   else{const add=command==='add';if(add)command='start';const payload=command==='start'?{profile:add?'':account?.active||''}:command==='select'?{profile:el.dataset.profile}:{};account=await C.api('/api/general-ai/account/'+command,payload);if(command==='select'&&account.connected&&account.sharing&&!account.models?.length)account=await C.api('/api/general-ai/account/models',{});if(['models','select'].includes(command)&&data.model&&!account.models?.some(m=>m.id===data.model)){data.model='';data.effort='default';}schedule();}
  }catch(e){error=e.message;}finally{busy=false;render();}return true;
 }
 return {init:c=>C=c,view,mount,change,action,dirty,discard};
})();

/* One shared local AI connection, edited only in Settings. */
window.GScopeAISettings=(()=>{
 let C,data=null,baseline='',loading=false,busy=false,error='',status='',models=[],readyState=null,probeBusy=false,probed=false;
 const dirty=()=>window.GScopeGeneralAI.dirty()||!!data&&JSON.stringify(data)!==baseline;
 const inSystem=()=>window.parent!==window&&typeof location!=='undefined'&&new URLSearchParams(location.search).get('gspot_settings')==='1';
 function discard(){if(baseline)data=JSON.parse(baseline);window.GScopeGeneralAI.discard();}
 function view(){if(inSystem())return '<section class="gspot-shared-ai-settings" data-shared-ai-panel><div><h2>AI connections</h2><p>Configure Private and General AI for all modules.</p></div>'+C.button('Open shared AI settings','ai-settings-open-system')+'</section>';if(!data)return `<section class="card"><h2>Private AI · local connection</h2><p>${C.esc(error||'Loading connection settings…')}</p></section>`;return `<section class="card"><h2>Private AI · local connection</h2><p class="help">Identity matching and local grading use this connection.</p><div class="row"><label>Engine<select data-ai-setting="provider">${C.option('ollama','Ollama',data.provider)}${C.option('openai-local','Compatible local server',data.provider)}</select></label><label>Local server address<input data-ai-setting="url" value="${C.esc(data.url)}"></label></div><label>Model<input data-ai-setting="model" list="local-ai-models" value="${C.esc(data.model)}"><datalist id="local-ai-models">${models.map(m=>`<option value="${C.esc(m)}">`).join('')}</datalist></label>${data.provider==='openai-local'?`<div class="row"><label>Model revision or fingerprint<input data-ai-setting="revision" value="${C.esc(data.revision)}"></label><label class="check"><input type="checkbox" data-ai-setting="vision" ${data.vision?'checked':''}>This local model supports images</label></div><p class="help">Uses the local server’s /v1 API. Update the revision when replacing its model weights.</p>`:''}<div class="row">${C.button(busy?'Checking…':'Check connection','ai-settings-check',busy?'disabled':'')}${C.button('Save local AI settings','ai-settings-save',busy?'disabled':'',true)}</div><p class="help" role="status">${C.esc(error||status)}</p></section>`+window.GScopeGeneralAI.view();}
 async function probe(start=false){
  if(probeBusy)return;probeBusy=true;probed=true;C.render();
  try{readyState=await C.api(start?'/api/local-ai/start-engine':'/api/local-ai/readiness',start?{confirmed:true}:undefined);}
  catch{readyState={state:'checking_failed',message:'Local AI readiness could not be checked. Recheck or open Settings.'};}
  finally{probeBusy=false;C.render();}
 }
 function readinessView(){
  return `<section class="card"><div class="row" role="status"><strong>OCR first</strong><span class="help">Vision fallback:</span><span>${C.esc(probeBusy?'Checking local AI...':readyState?.message||'Checking local AI...')}</span>${C.button('Recheck','ai-engine-recheck',probeBusy?'disabled':'')}${readyState?.canStart?C.button('Start Ollama','ai-engine-start',probeBusy?'disabled':''):''}</div></section>`;
 }
 async function mount(){if(!inSystem())await window.GScopeGeneralAI.mount();if(C.S.view==='projects'&&C.S.version&&['scans','match'].includes(C.S.tab)&&!probed&&!probeBusy)await probe();if(inSystem()||C.S.view!=='settings'||data||loading||error)return;loading=true;try{data=await C.api('/api/local-ai/settings');baseline=JSON.stringify(data);error='';}catch(e){error=e.message;}finally{loading=false;C.render();}}
 function input(el){const key=el.dataset.aiSetting;if(!key||!data)return false;data[key]=el.type==='checkbox'?el.checked:el.value;error='';status='';return true;}
 async function change(el){if(await window.GScopeGeneralAI.change(el))return true;if(!input(el))return false;if(el.dataset.aiSetting==='provider')C.render();return true;}
 async function action(el){if(await window.GScopeGeneralAI.action(el))return true;const action=el.dataset.action;if(['ai-engine-recheck','ai-engine-start'].includes(action)){await probe(action==='ai-engine-start');return true;}if(action==='ai-settings-open-system'&&inSystem()){window.parent.postMessage({source:'gspot-desktop-frame',type:'settings-open',section:'ai'},C.S.boot.parentOrigin);return true;}if(!['ai-settings-check','ai-settings-save'].includes(action))return false;if(busy)return true;busy=true;error='';status='';C.render();try{const result=await C.api(action==='ai-settings-save'?'/api/local-ai/settings':'/api/local-ai/check',data);models=result.models;status=action==='ai-settings-save'?'Shared local AI connection saved.':'Connected. '+(result.vision?'Vision support available.':'Text-only model.');if(action==='ai-settings-save'){probed=false;readyState=null;data=result.configuration;baseline=JSON.stringify(data);C.S.boot.defaultModel=data.model;C.S.models=null;}}catch(e){error=e.message;}finally{busy=false;C.render();}return true;}
 return {init:c=>{C=c;window.GScopeGeneralAI.init(c);},view,mount,input,change,action,dirty,discard,readinessView};
})();
