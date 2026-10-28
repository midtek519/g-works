/* Integrated desktop header. Fixed commands only; no forms or editor text. */
(() => {
 'use strict';
 if(window.GSpotHeader)return;
 const config=__HEADER_CONFIG__,native=()=>window.pywebview.api;
 const esc=value=>String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
 const icons={
  folders:'<path d="M3 7h7l2 2h9v11H3zM3 7V4h7l2 3"/>',
  preview:'<path d="M5 3h9l5 5v13H5zM14 3v6h5M8 13h8M8 17h5"/>',
  pin:'<path d="m8 3 8 0-1 6 4 4H5l4-4zM12 13v8"/>',
  fullscreen:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
  settings:'<path d="m10 3 4 0 .7 3 2 .9 2.8-1 2 3.5-2.2 2.1v2.3l2.2 2.1-2 3.5-2.8-1-2 .9-.7 3h-4l-.7-3-2-.9-2.8 1-2-3.5L4.7 13v-2.3L2.5 8.6l2-3.5 2.8 1 2-.9z"/><circle cx="12" cy="12" r="3"/>',
  refresh:'<path d="M20 7a8 8 0 1 0 1 8M20 3v5h-5"/>',
  menu:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  minimize:'<path d="M5 12h14"/>',maximize:'<rect x="5" y="5" width="14" height="14" rx="1"/>',
  restore:'<path d="M8 5V3h13v13h-2M3 8h13v13H3z"/>',close:'<path d="m6 6 12 12M18 6 6 18"/>'};
 const svg=id=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[id]}</svg>`;
 const button=(id,label,icon,attributes='')=>`<button type="button" data-shell="${id}" title="${esc(label)}" aria-label="${esc(label)}" ${attributes}>${svg(icon)}</button>`;
 async function windowCommand(action){
  try{const api=native();if(typeof api.window_action!=='function')throw Error('Desktop host needs reopening');const ok=await api.window_action(action);if(ok===false&&!action.startsWith('resize-')&&action!=='drag')throw Error('Native window command failed');return ok;}
  catch{if(typeof toast==='function')toast('The window control could not finish. Reopen the desktop app to load its updated controls.');return false;}
 }
 const style=document.createElement('style');style.textContent=`
  html[data-shell-native-header=true] .topbar{display:none!important}
  html[data-shell-native-header=true] .layout{min-height:100vh}
  html[data-shell-native-header=true] .layout>aside{top:0;height:100dvh}
  html[data-shell-native-header=true] .shell-menu{max-height:calc(100vh - 24px)}
  html.gspot-integrated .topbar{min-height:66px;padding:8px 10px 8px 14px;gap:14px;position:relative;font:13px/1.35 'Segoe UI',system-ui,sans-serif;user-select:none}
  html.gspot-integrated .topbar .brand{gap:9px;flex:none}html.gspot-integrated .topbar .brand-logo{width:37px;height:37px}html.gspot-integrated .topbar .brand strong{font:650 17px 'Segoe UI',system-ui,sans-serif;letter-spacing:.01em}html.gspot-integrated .topbar .brand small{display:none}
  html.gspot-integrated .topbar .header-page-heading{flex:1;min-width:80px;max-width:none;padding-right:8px}html.gspot-integrated .header-page-heading h1{font:600 20px/1.2 'Segoe UI',system-ui,sans-serif;margin:0;white-space:nowrap;text-overflow:ellipsis;overflow:hidden}html.gspot-integrated .header-page-heading p{font:12px/1.3 'Segoe UI',system-ui,sans-serif;margin:4px 0 0;opacity:.8;white-space:nowrap;text-overflow:ellipsis;overflow:hidden}
  .shell-actions,.shell-window-controls{display:flex;align-items:center;gap:3px;flex:none}.shell-actions{margin-left:auto}.shell-window-controls{margin-left:9px;padding-left:10px;border-left:1px solid color-mix(in srgb,currentColor 20%,transparent)}
  .topbar .shell-actions button,.topbar .shell-window-controls button{display:grid;place-items:center;width:32px;height:32px;padding:6px;border:1px solid transparent;border-radius:6px;background:transparent;box-shadow:none;min-height:0;min-width:0}
  .shell-actions svg,.shell-window-controls svg{width:19px;height:19px}.shell-actions button:disabled{opacity:.3}.shell-actions button[aria-pressed=true]{box-shadow:inset 0 -2px var(--signature-secondary,#169b9d)!important}.topbar .shell-window-controls [data-shell=close]:hover{background:#c63352!important;color:white!important}
  .shell-actions button:focus-visible,.shell-window-controls button:focus-visible{outline:2px solid currentColor;outline-offset:1px}
  .shell-menu{position:fixed;right:14px;top:68px;z-index:1400;width:min(450px,calc(100vw - 28px));max-height:calc(100vh - 85px);overflow:auto;padding:6px;display:grid;grid-template-columns:1fr;gap:2px;background:var(--paper,#fff);color:var(--ink,#20334d);border:1px solid var(--line,#cbd6e6);border-radius:8px;box-shadow:0 10px 35px #16335030;font:13px 'Segoe UI',system-ui,sans-serif}
  .shell-menu .shell-folder-divider{width:auto;border:0;border-top:1px solid var(--line,#cbd6e6);margin:5px 6px}
  .shell-menu details{min-width:0}.shell-menu summary{cursor:pointer;font-weight:650;padding:7px 8px;border-radius:4px}.shell-menu button{width:100%;text-align:left;display:block;font:12px/1.4 'Segoe UI',system-ui,sans-serif;padding:7px 9px;border:0;border-radius:4px;background:transparent;color:inherit;white-space:pre-wrap}.shell-menu button:hover,.shell-menu summary:hover{background:var(--hover,#e3edf7)}.shell-menu [role=group]{padding-left:9px}.shell-menu p{font-size:11px;color:var(--muted,#586b85);margin:7px 9px 3px}.shell-menu button:disabled{opacity:.4;cursor:default}
  .shell-resize{position:fixed;z-index:2000;user-select:none;touch-action:none}.shell-resize[data-edge=n],.shell-resize[data-edge=s]{height:5px;left:9px;right:9px;cursor:ns-resize}.shell-resize[data-edge=e],.shell-resize[data-edge=w]{width:5px;top:9px;bottom:9px;cursor:ew-resize}.shell-resize[data-edge=n]{top:0}.shell-resize[data-edge=s]{bottom:0}.shell-resize[data-edge=e]{right:0}.shell-resize[data-edge=w]{left:0}.shell-resize[data-edge=nw],.shell-resize[data-edge=ne],.shell-resize[data-edge=sw],.shell-resize[data-edge=se]{width:9px;height:9px}.shell-resize[data-edge=nw],.shell-resize[data-edge=se]{cursor:nwse-resize}.shell-resize[data-edge=ne],.shell-resize[data-edge=sw]{cursor:nesw-resize}.shell-resize[data-edge=nw]{top:0;left:0}.shell-resize[data-edge=ne]{top:0;right:0}.shell-resize[data-edge=sw]{bottom:0;left:0}.shell-resize[data-edge=se]{bottom:0;right:0}html[data-shell-maximized=true] .shell-resize,html[data-shell-fullscreen=true] .shell-resize{display:none}
  @media(max-width:1150px){html.gspot-integrated .header-page-heading p{display:none}html.gspot-integrated .topbar{gap:8px}.shell-actions,.shell-window-controls{gap:1px}.shell-window-controls{margin-left:3px;padding-left:4px}}
   .shell-menu .shell-folder-context{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);align-items:end;gap:10px;padding:8px}
  .shell-menu .shell-folder-context>label{display:block;min-width:0;width:auto;margin:0;font-size:11px;line-height:1.35}
  .shell-menu .shell-folder-context select{display:block;box-sizing:border-box;width:100%;min-width:0;margin:4px 0 0;height:38px;padding:7px 10px;border:1px solid var(--line);border-radius:6px;font:12px 'Segoe UI',system-ui,sans-serif;color:inherit;background:var(--white,#fff)}
  .shell-menu .shell-folder-results button{font-weight:400;line-height:1.45}
`;document.head.append(style);document.documentElement.classList.add('gspot-integrated');
 let current={maximized:false,fullscreen:false},outputChoices=[];
 function state(value){current={...current,...value};document.documentElement.dataset.shellMaximized=String(current.maximized);document.documentElement.dataset.shellFullscreen=String(current.fullscreen);sync();}
 function sync(){
  const maximize=document.querySelector('[data-shell=maximize]');if(maximize){maximize.innerHTML=svg(current.maximized?'restore':'maximize');maximize.title=current.maximized?'Restore window':'Maximize window';maximize.setAttribute('aria-label',maximize.title);maximize.disabled=current.fullscreen;}
 }
 function mount(){
  let header=document.querySelector('.topbar');
  if(!header){const app=document.getElementById?.('app');if(!app)return;header=document.createElement('header');header.className='topbar';header.innerHTML='<div class="brand"><img class="brand-logo" src="/g-whiz.svg" alt=""><div><strong>'+esc(config.name)+'</strong></div></div><div class="header-page-heading"><h1>'+esc(config.name)+'</h1><p>Opening your workspace…</p></div>';app.prepend(header);}
  header.querySelector('[data-desktop=menu]')?.remove();header.querySelector('[data-desktop=refresh]')?.remove();
  if(!header.querySelector('.shell-actions')){
   const actions=document.createElement('nav');actions.className='shell-actions';actions.setAttribute('aria-label','App actions');
   actions.innerHTML=button('folders','Open output folders','folders','aria-haspopup="true" aria-expanded="false"')+button('preview','Show PDF preview','preview')+button('settings','Settings','settings')+(window.GSpotDesktop?.refresh?button('refresh','Reload '+config.name,'refresh'):'');header.append(actions);
  }
  if(!config.system_frame&&!header.querySelector('.shell-window-controls')){
   const controls=document.createElement('div');controls.className='shell-window-controls';controls.innerHTML=button('minimize','Minimize window','minimize')+button('maximize','Maximize window','maximize')+button('close','Close '+config.name,'close');header.append(controls);
  }
  if(!config.system_frame&&!document.querySelector('.shell-resize'))for(const edge of ['n','ne','e','se','s','sw','w','nw']){const handle=document.createElement('div');handle.className='shell-resize';handle.dataset.edge=edge;handle.setAttribute('aria-hidden','true');document.body.append(handle);}
  sync();
 }
 function closeMenu(restore=false){const menu=document.querySelector('.shell-menu');if(!menu)return;menu.remove();const opener=document.querySelector('[data-shell=folders]');opener?.setAttribute('aria-expanded','false');if(restore)opener?.focus();}
 function menu(nativeInset){
  if(document.querySelector('.shell-menu')){closeMenu(true);return;}
  const entries=items=>items.map(item=>`<button type="button" data-shell-command="${item.action}">${esc(item.label)}</button>`).join('');
  const isCourseFolder=item=>['folders','folder-output'].includes(item.action),universal=config.folders.filter(item=>!isCourseFolder(item)&&item.action!=='folder-downloads');
  const panel=document.createElement('div');panel.className='shell-menu';panel.setAttribute('aria-label','Open output folders');document.body.append(panel);const opener=document.querySelector('[data-shell=folders]');opener?.setAttribute('aria-expanded','true');const bounds=opener?.getBoundingClientRect?.();if(bounds){panel.style.right=Math.max(14,innerWidth-bounds.right)+'px';panel.style.top=(bounds.bottom+10)+'px';}if(config.native_header){panel.style.right=(Number.isFinite(nativeInset)?Math.max(10,nativeInset):164)+'px';panel.style.top='10px';}
  if(!config.folders.some(item=>item.action==='folders')||typeof api!=='function'||typeof S==='undefined'||!S.courses?.length){panel.innerHTML=entries(config.folders.filter(item=>item.action!=='folder-downloads'));panel.querySelector('button')?.focus();return;}
  const context={course:S.course||S.courses[0].code,semester:S.semester||S.courses[0].default_semester},scopes=['handouts','manual','syllabus','support'];let semesters=S.catalog?.semesters||[],request=0,message='',loading=false;
  const label=tag=>typeof termLabel==='function'?termLabel(tag):tag;
  function draw(){if(document.querySelector('.shell-menu')!==panel)return;const tags=[...new Map([{value:context.semester,label:label(context.semester)},...semesters].filter(t=>t.value).map(t=>[t.value,t])).values()];panel.innerHTML=`<div class="shell-folder-context"><label>Course<select data-shell-folder-course>${S.courses.map(c=>`<option value="${esc(c.code)}"${c.code===context.course?' selected':''}>Math ${esc(c.code)}</option>`).join('')}</select></label><label>Semester<select data-shell-folder-semester>${tags.map(t=>`<option value="${esc(t.value)}"${t.value===context.semester?' selected':''}>${esc(t.label||label(t.value))}</option>`).join('')}</select></label></div><div class="shell-folder-results" aria-live="polite">${loading?'<p>Loading folders…</p>':message?`<p>${esc(message)}</p><button data-shell-folder-retry>Retry</button>`:outputChoices.map((folder,index)=>`<button type="button" data-shell-output="${index}" title="${esc(folder.path)}"${folder.exists?'':' disabled'}><span>${esc(folder.kinds.join(', '))}${folder.exists?'':' (not created)'}</span></button>`).join('')||'<p>No configured folders.</p>'}</div>${universal.length?'<hr class="shell-folder-divider" role="separator">'+entries(universal):''}`;}
  async function loadFolders(loadTerms=false){const id=++request,chosen={...context};loading=true;message='';outputChoices=[];draw();try{if(loadTerms){const catalog=await api('/api/catalog?course='+encodeURIComponent(chosen.course)+'&semester='+encodeURIComponent(chosen.semester),undefined,{timeoutMs:15000});if(id!==request)return;semesters=catalog.semesters;context.semester=chosen.semester=catalog.semester;}const results=await Promise.all(scopes.map(scope=>api('/api/output-folders',{...chosen,scope}, {timeoutMs:15000})));if(id!==request||document.querySelector('.shell-menu')!==panel)return;const merged=new Map();results.forEach((result,index)=>{for(const folder of result.folders){const key=folder.path.split(String.fromCharCode(92)).join('/').replace(/[/]+$/,'').toLocaleLowerCase(),prior=merged.get(key);if(prior)prior.kinds=[...new Set([...prior.kinds,...folder.kinds])];else merged.set(key,{...folder,scope:scopes[index],context:{...chosen}});}});outputChoices=[...merged.values()];}catch(e){if(id!==request)return;message=e.name==='TimeoutError'?'Folders took too long to load. Please retry.':e.message||'Folders could not load.';}finally{if(id===request){loading=false;draw();}}}
  panel.addEventListener('change',event=>{if(event.target.matches('[data-shell-folder-course]')){context.course=event.target.value;context.semester=S.courses.find(c=>c.code===context.course)?.default_semester||context.semester;semesters=[];loadFolders(true);}else if(event.target.matches('[data-shell-folder-semester]')){context.semester=event.target.value;loadFolders();}});
  panel.addEventListener('click',event=>{if(event.target.closest('[data-shell-folder-retry]'))loadFolders(true);});
  loadFolders();
 }
 let dragStart=null;
 document.documentElement.dataset.shellSystemFrame=String(!!config.system_frame);
 document.documentElement.dataset.shellNativeHeader=String(!!config.native_header);
 document.addEventListener('mousedown',event=>{
  if(event.button!==0)return;
  const edge=event.target.closest('.shell-resize');if(edge){event.preventDefault();windowCommand('resize-'+edge.dataset.edge);return;}
  if(config.system_frame)return;
  if(event.detail>1)return;
  if(event.target.closest('.topbar')&&!event.target.closest('button,a,input,select,textarea,summary,[role=button]')){event.preventDefault();dragStart={x:event.screenX,y:event.screenY};}
 },true);
 document.addEventListener('mouseup',()=>{dragStart=null;},true);
 window.addEventListener('blur',()=>{dragStart=null;});
 document.addEventListener('mousemove',event=>{if(!dragStart)return;if(!(event.buttons&1)){dragStart=null;return;}if(Math.hypot(event.screenX-dragStart.x,event.screenY-dragStart.y)<4)return;dragStart=null;windowCommand('drag');},true);
 document.addEventListener('dblclick',event=>{if(!config.system_frame&&event.target.closest('.topbar')&&!event.target.closest('button,a,input,select,textarea,summary,[role=button]')){dragStart=null;event.preventDefault();windowCommand('maximize');}},true);
 document.addEventListener('click',event=>{
  const target=event.target.closest('[data-shell],[data-shell-command],[data-shell-output]');if(!target){if(!event.target.closest('.shell-menu'))closeMenu();return;}
  event.preventDefault();event.stopImmediatePropagation();
  if(target.disabled)return;
  if(target.dataset.shellOutput!==undefined){const folder=outputChoices[Number(target.dataset.shellOutput)];closeMenu();if(folder?.exists)api('/api/output-folders',{...folder.context,scope:folder.scope,open_kind:folder.kinds[0]}).catch(()=>{if(typeof toast==='function')toast('The output folder could not open.');});return;}
  const action=target.dataset.shellCommand||target.dataset.shell;
  if(action==='folders'){menu();return;}closeMenu();
  let result;if(action==='refresh')result=window.GSpotDesktop.refresh();else if(['minimize','maximize'].includes(action))result=windowCommand(action);else if(action==='close')result=window.GSpotDesktop.close();else if(action==='settings')result=native().open_settings();else result=native().menu_action(action);
  Promise.resolve(result).catch(()=>{if(typeof toast==='function')toast('The desktop action could not finish.');});
 },true);
 window.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.querySelector('.shell-menu')){event.preventDefault();event.stopImmediatePropagation();closeMenu(true);}},true);
 const originalRender=render;render=function(...args){closeMenu();const result=originalRender(...args);mount();return result;};
 window.GSpotHeader={mount,state,folders:menu};mount();
 // Some startup and module code replaces the header without calling render.
 // Repair missing actions/controls independently, without reacting to our SVG
 // state updates or creating a MutationObserver loop.
 const app=document.getElementById?.('app');if(app&&typeof MutationObserver!=='undefined')new MutationObserver(()=>{
  const header=document.querySelector('.topbar');
  if(!header||!header.querySelector('.shell-actions')||(!config.system_frame&&!header.querySelector('.shell-window-controls')))mount();
 }).observe(app,{childList:true,subtree:true});
})();
