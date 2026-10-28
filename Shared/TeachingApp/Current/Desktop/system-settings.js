/* Function-based AI settings. Credentials remain in the local backend. */
(() => {
 if(window.GWorksSystemSettings)return;
 let data=null,general=null,account=null,baseline='',generalBaseline='',busy=false,message='',error='',poll=null;
 const dirty=()=>!!data&&(JSON.stringify(data)!==baseline||JSON.stringify(general)!==generalBaseline);
 const refresh=()=>{if(window.GWorksTools)render();};
 const routes=[['G-Scope','Student scans, identity matching, grading & decisions from student work','Private'],['G-Scope','Solutions & rubric drafts from the blank exam','General'],['Recommendations & Integrity','Approved redacted drafting brief / AI handoff','General'],['Private record tools','Evidence or attachments processed directly on this computer','Private']];
 let loading=null;
 async function loadAI(){
  if(loading)return loading;
  if(busy)return false;
  busy=true;refresh();
  loading=(async()=>{try{
   if(!data){const [local,result]=await Promise.all([api('/api/local-ai/settings'),api('/api/general-ai/settings')]);data=local;general=result.configuration;account=result.account;baseline=JSON.stringify(data);generalBaseline=JSON.stringify(general);}
   else account=await api('/api/general-ai/account');
   error='';
   if(general.provider==='chatgpt'&&account?.connected&&account.sharing&&!(account.models||[]).length){busy=true;refresh();try{account=await api('/api/general-ai/account/models',{});}finally{busy=false;}}
   schedule();
  }catch(e){error=e.message;}finally{loading=null;busy=false;refresh();}})();return loading;
 }

 function effortsFor(model){
  if(!model)return [];
  if(model.efforts?.length)return model.efforts;
  // Supported GPT families: documented low-through-max range when the plan
  // catalog omits effort metadata. Unrecognized models retain their default.
  return /^gpt-(?:6(?:\.1)?|5\.6)-/.test(model.id)?['low','medium','high','xhigh','max']:[];
 }
 const aiButton=(action,label,disabled=false)=>`<button type="button" data-ai-account="${action}"${disabled?' disabled':''}>${label}</button>`;
 function generalControls(inactive){
  if(general.provider==='local')return '<p class="help">General tasks use the Private AI engine locally. Choose ChatGPT to use your plan for eligible tasks.</p>';
  const models=account?.models||[],model=models.find(m=>m.id===general.model),levels=effortsFor(model),connected=account?.connected&&account.sharing;
  const state=busy?'Updating connection…':account?.message||(account?.connected&&!account.sharing?'Reconnect and allow ChatGPT plan usage.':connected?'ChatGPT connected.':'No ChatGPT account connected.');
  const status=!connected?'Connect ChatGPT to load models.':!models.length?'No models loaded. Refresh models to try again.':!model?'Select a model.':!levels.length?'This model uses its default thinking level.':'';
  return `${account?.profiles?.length?field('ChatGPT account',`<select data-account-profile${inactive}>${account.profiles.map(p=>option(p.id,p.label+(p.connected?'':' · signed out'),account.active)).join('')}</select>`):''}<p role="status">${esc(state)}</p>
  <div class="actions">${aiButton('start',account?.connected?'Reconnect ChatGPT':'Continue with ChatGPT',busy||account?.pending)}${account?.pending?aiButton('cancel','Cancel sign-in'):''}${account?.profiles?.length?aiButton('add','Add account',busy):''}${account?.connected?aiButton('signout','Sign out',busy):''}${aiButton('usage','Manage usage ↗',busy)}</div>
  <div class="tools-ai-model-row">${field('Model',`<select data-general-ai="model"${busy||!connected||!models.length?' disabled':''}>${option('','—',general.model)}${models.map(m=>option(m.id,m.label,general.model)).join('')}${general.model&&!model?option(general.model,general.model+' · unavailable',general.model):''}</select>`)}${field('Thinking',`<select data-general-ai="effort"${busy||!model||!levels.length?' disabled':''}>${option('default','Model default',general.effort)}${[...new Set([...levels,...(general.effort!=='default'&&model?[general.effort]:[])])].map(level=>option(level,level[0].toUpperCase()+level.slice(1),general.effort)).join('')}</select>`)}</div>
  <div class="actions">${aiButton('models','Refresh models',busy||!connected)}<span class="help">${esc(status)}</span></div><p class="help">Student scans and original private evidence stay local. ChatGPT receives only eligible input.</p>`;
 }
 function aiView(){
  if(!data)return '<p class="help" role="status">'+esc(error||'Loading AI settings…')+'</p>';
  const inactive=busy?' disabled':'';
  return `<p class="help tools-ai-overview">Each feature chooses the connection that fits its input. A module can use both.</p><div class="tools-ai-grid">
  <section class="panel tools-ai-card tools-ai-private"><div class="tools-ai-card-heading"><h2>Private AI</h2><span class="tools-ai-badge">Local only</span></div><p class="tools-ai-purpose">For protected student records. Runs only on this computer.</p><div class="tools-ai-local-row">${field('Engine',`<select data-system-ai="provider"${inactive}>${option('ollama','Ollama',data.provider)}${option('openai-local','Compatible local server',data.provider)}</select>`)}${field('Local server address',`<input data-system-ai="url" value="${esc(data.url)}"${inactive}>`)}</div>${field('Model',`<input data-system-ai="model" value="${esc(data.model)}"${inactive}>`)}${data.provider==='openai-local'?field('Model revision or fingerprint',`<input data-system-ai="revision" value="${esc(data.revision)}"${inactive}>`)+`<label class="check"><input type="checkbox" data-system-ai="vision" ${data.vision?'checked':''}${inactive}>Supports images</label>`:''}<button type="button" data-tools-ai-check${inactive}>Check local connection</button><p class="help">Used for student scans, grading, identity matching and direct evidence processing.</p></section>
  <section class="panel tools-ai-card tools-ai-general"><div class="tools-ai-card-heading"><h2>General AI</h2><span class="tools-ai-badge">${general.provider==='chatgpt'?'ChatGPT':'Local'}</span></div><p class="tools-ai-purpose">For blank teaching materials and approved, redacted drafting briefs.</p>${field('Connection',`<select data-general-ai="provider"${inactive}>${option('local','Use the local connection',general.provider)}${option('chatgpt','ChatGPT account',general.provider)}</select>`)}${generalControls(inactive)}</section></div>
  <details class="tools-ai-route-details"><summary>Which features use each connection?</summary><div class="tools-ai-table-wrap"><table class="tools-ai-routes"><thead><tr><th>Module</th><th>Feature / input</th><th>Connection</th></tr></thead><tbody>${routes.map(([module,feature,connection])=>`<tr><td>${esc(module)}</td><td>${esc(feature)}</td><td><strong>${esc(connection)}</strong></td></tr>`).join('')}</tbody></table></div><p class="help"><strong>Private AI</strong> helps prevent unintended FERPA disclosures. Protected student records stay local; any AI processing uses the local model. <strong>General AI</strong> receives blank academic content or text you have reviewed and redacted for sharing. Review indirect identifying details too. These names describe data handling, not a FERPA certification.</p><a href="/privacy/ferpa.html" target="_blank" rel="noopener">FERPA & privacy reference ↗</a></details>${error?'<p class="error" role="alert">'+esc(error)+'</p>':''}`;
 }

 async function submit(save){
  if(busy||!data)return false;busy=true;message='';error='';refresh();
  try{
   if(save){
    if(JSON.stringify(data)!==baseline){const result=await api('/api/local-ai/settings',{...data});data=result.configuration;baseline=JSON.stringify(data);}
    if(JSON.stringify(general)!==generalBaseline){const result=await api('/api/general-ai/settings',{...general});general=result.configuration;generalBaseline=JSON.stringify(general);}
    message='AI settings saved.';
   }else{const result=await api('/api/local-ai/check',{...data});message=result.vision?'Local connection ready. Image support available.':'Local connection ready. Text-only model.';}
   return true;
  }catch(e){error=e.message;return false;}finally{busy=false;refresh();}
 }
 async function accountAction(command,profile){
  if(busy&&command!=='cancel')return false;busy=true;message='';error='';refresh();
  try{
   if(command==='add'){command='start';profile='';}
   const payload=command==='start'?{profile:profile??account?.active??''}:command==='select'?{profile}:{};
   const result=await api('/api/general-ai/account/'+command,payload);
   if(command!=='usage')account=result;
   if(command==='select'&&account.connected&&account.sharing&&!(account.models||[]).length)account=await api('/api/general-ai/account/models',{});
   if(['models','select'].includes(command)&&general.model&&!(account.models||[]).some(m=>m.id===general.model)){general.model='';general.effort='default';}
   schedule();return true;
  }catch(e){error=e.message;return false;}finally{busy=false;refresh();}
 }
 function schedule(){clearTimeout(poll);if(account?.pending)poll=setTimeout(pollAccount,1000);}
 async function pollAccount(){
  try{
   account=await api('/api/general-ai/account');
   if(account.welcome){alert('You’re using your ChatGPT plan. Eligible General AI requests use this plan. Manage this connection’s usage in ChatGPT Settings → Usage.');account=await api('/api/general-ai/account/welcome',{});}
   if(!account.pending&&account.connected&&account.sharing){try{account=await api('/api/general-ai/account/models',{});}catch(e){error=e.message;}}
   refresh();schedule();
  }catch(e){error=e.message;refresh();}
 }
 document.addEventListener('input',event=>{const key=event.target.dataset?.systemAi;if(!data||busy||!['provider','url','model','revision','vision'].includes(key))return;data[key]=event.target.type==='checkbox'?event.target.checked:event.target.value;message='';error='';window.GWorksTools?.updateFooter?.();});
 document.addEventListener('change',event=>{
  if(event.target.dataset?.systemAi==='provider'){data.provider=event.target.value;refresh();}
  const key=event.target.dataset?.generalAi;if(general&&!busy&&['provider','model','effort'].includes(key)){general[key]=event.target.value;if(key==='provider'){general.model='';general.effort='default';}if(key==='model')general.effort='default';message='';error='';refresh();if(key==='provider'&&general.provider==='chatgpt')loadAI();}
  if(event.target.matches?.('[data-account-profile]'))accountAction('select',event.target.value);
 });
 document.addEventListener('click',event=>{const button=event.target.closest?.('[data-ai-account]');if(button&&!button.disabled){event.preventDefault();accountAction(button.dataset.aiAccount);}});
 window.GWorksSystemSettings={loadAI,aiView,dirty,discard(){if(baseline){data=JSON.parse(baseline);general=JSON.parse(generalBaseline);}},saveAI:()=>submit(true),checkAI:()=>submit(false),accountAction,status:()=>({busy,ready:!!data,message:error||message})};
})();
