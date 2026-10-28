/* Desktop-only settings and help window, using the existing local forms/APIs. */
(() => {
  'use strict';
  if(window.GSpotTools)return;
  const initial=__TOOLS_INITIAL__,family=initial[0],native=()=>window.pywebview.api;
  const edition=__TOOLS_CONFIG__;
  const helpSections=new Set(['about','changelog','technical']);
  const modules={appearance:['Appearance','Desktop themes & app styling'],ai:['AI','Local & General AI connections'],temporary:['Temporary files','Disposable previews & caches'],...(edition.private_modules?{...(edition.materials!==false?{materials:['Materials','Publish destinations']}:{}),grades:['Grades','Semester policies & instructor assignments'],recommendations:['Recommendations','Writing preferences, letterhead & signature'],integrity:['Integrity','Letterhead & signature']}:{materials:['Materials','Publish destinations']}),about:['About '+edition.name,''],changelog:['Changelog',''],technical:['Technical Details','']};
  const saveActions={ai:[['ai','Save AI settings']],materials:[['materials','Save']],grades:[['policy','Save policy'],['assignments','Save assignments']],recommendations:[['preferences','Save preferences'],['letterhead','Save letterhead']],integrity:[['letterhead','Save letterhead']]};
  let page={mode:family,section:initial[1]},pending=false,info=null,folderList=[],folderError='',saving=false,saveStatus='';
  const saveWaiters=new Map();
  let signatureBusy=false;
  let temporaryBusy=false,temporaryMessage='',confirmation=null;
  const originalRender=render,originalContent=content,originalApi=api,originalAccept=acceptPrivateNavigation;
  const style=document.createElement('style');
  document.documentElement.classList.add('gspot-dialog','gspot-dialog-'+family);
  style.textContent=`
    html.gspot-dialog{--ink:#202020;--muted:#626262;--accent:#0f6cbd;--line:#d8d8d8;--paper:#fafafa;--hover:#edf3f9;font:13px 'Segoe UI',system-ui,sans-serif}
    .gspot-dialog body{margin:0;background:#fafafa;font:13px/1.45 'Segoe UI',system-ui,sans-serif;height:100vh;overflow:hidden;color:var(--ink)}
    .gspot-dialog #app{height:calc(100vh - 52px);display:flex;flex-direction:column;overflow:hidden}
    .gspot-dialog .topbar{display:none!important}
    .gspot-dialog .layout{display:grid;grid-template-columns:155px minmax(0,1fr);min-height:0;flex:1;overflow:hidden}
    .gspot-dialog .layout>aside{padding:12px 8px;overflow:auto;background:#f3f3f3;border-right:1px solid var(--line)}
    .gspot-dialog .layout>main{padding:16px 18px;overflow:auto;min-width:0;min-height:0;max-width:none;background:#fafafa}
    .gspot-dialog:not(.gspot-dialog-settings) .layout{grid-template-columns:minmax(0,1fr)}
    .gspot-dialog:not(.gspot-dialog-settings) .layout>main{display:flex;flex-direction:column}
    .gspot-dialog #content{min-width:0;min-height:0}
    .gspot-dialog-help #content{flex:1;display:flex;flex-direction:column}
    .gspot-dialog h1,.gspot-dialog h2,.gspot-dialog h3{font-family:'Segoe UI',system-ui,sans-serif;letter-spacing:normal;line-height:1.4;color:var(--ink)}
    .gspot-dialog h1{font-size:17px;font-weight:600;margin:0}.gspot-dialog h2{font-size:14px;font-weight:600;margin:0 0 8px}.gspot-dialog h3{font-size:13px;font-weight:600}
    .dialog-heading{margin-bottom:14px}.dialog-heading p{font-size:12px;color:var(--muted);margin:4px 0 0}
    .gspot-dialog p,.gspot-dialog .help{font-size:12px;line-height:1.5}.gspot-dialog label{font-size:12px}
    .gspot-dialog button,.gspot-dialog input,.gspot-dialog select,.gspot-dialog textarea{font:12px/1.4 'Segoe UI',system-ui,sans-serif;border-radius:4px}
    .gspot-dialog button,.gspot-dialog select,.gspot-dialog input:not([type=checkbox]){min-height:30px;padding:5px 9px}
    .gspot-dialog button{box-shadow:none}.gspot-dialog .panel{padding:0;margin:0;border:0;border-radius:0;box-shadow:none;background:transparent}
    .gspot-dialog .tools-nav button{display:block;width:100%;text-align:left;margin:3px 0;padding:8px 10px;border:1px solid transparent;background:transparent;font-size:13px}
    .gspot-dialog .tools-nav button[aria-current=page]{background:#e6edf5;border-color:#c7d6e7;color:#0f4c81}
    .configuration-panel>h2{display:none}.gspot-dialog .configuration-panel>p.help{margin-top:0}
    .gspot-dialog .publish-placeholders{padding:7px 9px;margin:10px 0;border-radius:4px;background:#f3f3f3}
    .gspot-dialog .configuration-panel .publish-course{padding:9px 0;margin:0}
    .gspot-dialog .publish-location-row{grid-template-columns:120px minmax(0,1fr) auto;gap:4px 9px;margin:8px 0;align-items:center}
    .gspot-dialog .publish-location-row>label{grid-column:auto;margin:0}.gspot-dialog .publish-location-row>.publish-example{grid-column:2/-1;margin:0;font-size:10px}
    .gspot-dialog .publish-location-row>.actions{flex-wrap:nowrap;gap:4px}.gspot-dialog .publish-location-row input{width:100%}
    .gspot-dialog .publish-base-row{padding-bottom:8px}.gspot-dialog .configuration-temp{margin-top:14px;padding-top:12px;gap:12px}
    .gspot-dialog .configuration-save>button{display:none}
    .gspot-dialog .tools-ai-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start}
    .gspot-dialog .tools-ai-card{padding:16px!important;border:1px solid var(--line)!important;border-radius:9px!important;background:var(--signature-surface,var(--white,#fff));min-width:0}
    html.gspot-dialog .tools-ai-card.tools-ai-private{border-top:4px solid #15817e!important}html.gspot-dialog .tools-ai-card.tools-ai-general{border-top:4px solid #416bc0!important}
    html.gspot-dialog .tools-ai-private .tools-ai-card-heading h2{color:#146b67!important}html.gspot-dialog .tools-ai-general .tools-ai-card-heading h2{color:#3456a5!important}
    html.gspot-dialog[data-gspot-theme=midnight] .tools-ai-private .tools-ai-card-heading h2{color:#74d6cb!important}html.gspot-dialog[data-gspot-theme=midnight] .tools-ai-general .tools-ai-card-heading h2{color:#a9c3ff!important}
    .gspot-dialog .tools-ai-card h2{font-size:18px;font-weight:650;margin:0 0 4px;line-height:1.3}.gspot-dialog .tools-ai-card .tools-ai-purpose{font-size:12px;line-height:1.5;margin:0 0 15px;color:var(--muted)}
    .tools-ai-card-heading{display:flex;justify-content:space-between;align-items:start;gap:10px}.tools-ai-badge{display:inline-block;white-space:nowrap;font-size:10px;font-weight:650;letter-spacing:.04em;text-transform:uppercase;padding:3px 7px;border-radius:4px;background:#dcefeb;color:#135f5c}.tools-ai-general .tools-ai-badge{background:#e4ebfa;color:#294d92}
    .gspot-dialog .tools-ai-card .field{margin:0 0 12px}.gspot-dialog .tools-ai-card .actions{gap:6px;margin:8px 0 12px;flex-wrap:wrap}.gspot-dialog .tools-ai-card p[role=status]{margin:5px 0 9px;font-size:12px}
    .gspot-dialog .tools-ai-card .tools-ai-model-row{display:grid;grid-template-columns:minmax(0,1fr) 140px;gap:10px}.gspot-dialog .tools-ai-card .tools-ai-local-row{display:grid;grid-template-columns:125px minmax(0,1fr);gap:10px}
    .tools-ai-overview{margin:0 0 14px}.tools-ai-route-details{margin-top:16px;border:1px solid var(--line);border-radius:8px;padding:12px 14px}.tools-ai-route-details summary{font-weight:650;cursor:pointer}.tools-ai-route-details>.help{margin:10px 0}
    .tools-ai-table-wrap{overflow-x:auto;margin:12px 0}.tools-ai-routes{border-collapse:collapse;width:100%;font-size:12px;line-height:1.5}.tools-ai-routes th,.tools-ai-routes td{text-align:left;padding:9px 11px;border:1px solid var(--line);vertical-align:top}.tools-ai-routes th{font-weight:650;background:var(--paper,#f3f6fc)}.tools-ai-routes th:first-child{width:23%}.tools-ai-routes th:last-child{width:100px}
    .gspot-dialog .tools-temp-panel{padding:15px!important;max-width:700px}.tools-temp-panel [role=status]{margin:12px 0 0}.gspot-dialog #dialog .tools-confirm-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:20px}.gspot-dialog #dialog{width:min(460px,calc(100vw - 40px));padding:20px;border-radius:10px;border:1px solid var(--line);color:var(--ink);background:var(--signature-surface,var(--paper,#fff))}.gspot-dialog #dialog::backdrop{background:#102d4a66}.gspot-dialog #dialog .panel-header{gap:16px}.gspot-dialog #dialog h2{font-size:17px}.gspot-dialog #dialog p{font-size:13px;margin-top:16px}
    @media(max-width:900px){.gspot-dialog .tools-ai-grid{grid-template-columns:minmax(0,1fr)}}
    @media(max-width:520px){.gspot-dialog .tools-ai-card .tools-ai-model-row,.gspot-dialog .tools-ai-card .tools-ai-local-row{grid-template-columns:minmax(0,1fr)}}
    .gspot-dialog .tools-ai-fields{display:grid;grid-template-columns:180px minmax(0,1fr);gap:12px}.gspot-dialog [data-system-ai]:not([type=checkbox]){width:100%}
    .gspot-dialog .tools-output-controls{display:flex;align-items:end;flex-wrap:wrap;gap:9px;margin:10px 0 12px}.gspot-dialog .tools-output-controls .field{width:160px;margin:0}.gspot-dialog .tools-output-controls select{width:100%}
    .gspot-dialog .tools-output-controls select,.gspot-dialog .tools-output-controls>[data-tools-refresh]{height:32px}
    .gspot-dialog .tools-folder-row{display:flex;gap:12px;justify-content:space-between;align-items:center;padding:9px 0;border-top:1px solid var(--line)}.gspot-dialog .tools-folder-row p{margin:3px 0 0;overflow-wrap:anywhere;font-size:11px;color:var(--muted)}
    .tools-folder-row strong{font-size:12px;font-weight:600}.tools-folder-row>button{flex:none}
    .gspot-dialog .tools-other-folders{margin-top:18px}
    .gspot-dialog .tools-help{height:100%;min-height:0;max-width:none;display:flex;flex-direction:column}.tools-help p{margin:0 0 12px}
    .tools-about h1{font-size:22px;margin:0 0 5px}.gspot-dialog .tools-about dl{display:grid;grid-template-columns:95px minmax(0,1fr);gap:7px 12px;font-size:12px;margin:15px 0}.tools-about dd{overflow-wrap:anywhere;margin:0}.tools-about dt{color:var(--muted)}
    .tools-history{overflow:auto;min-height:0}.tools-history article+article{border-top:1px solid var(--line);padding-top:12px;margin-top:15px}.tools-history h2{font-size:13px;margin:0 0 6px}.tools-history ul{padding-left:19px;margin:0}.tools-history li{margin:5px 0;font-size:12px}
    .gspot-dialog .tools-technical pre{white-space:pre-wrap;font:11px/1.5 Consolas,monospace;margin:0;background:white;border:1px solid var(--line);border-radius:4px;padding:10px;flex:1;min-height:0;overflow:auto}
    .dialog-footer{position:fixed;bottom:0;left:0;right:0;height:52px;display:flex;gap:8px;align-items:center;justify-content:flex-end;padding:9px 16px;border-top:1px solid var(--line);background:#f3f3f3;z-index:500}
    .dialog-footer button{min-width:82px}.dialog-footer [role=status]{margin-right:auto;min-width:0;font-size:11px;color:var(--muted)}
    .gspot-dialog #toast{bottom:62px}.gspot-dialog #private-module-host{position:fixed;border-radius:0}
    .gspot-dialog #private-module-host{visibility:hidden}
    /* The Settings window shares one compact visual system across its sections. */
    html.gspot-dialog-settings{--settings-surface:var(--signature-surface,#fff);--settings-tint:#f0f5fc;--settings-section:#285b98}
    html.gspot-dialog-settings[data-gspot-theme=midnight]{--settings-surface:#252e3e;--settings-tint:#29374b;--settings-section:#b5d0ff}
    .gspot-dialog-settings .layout>main{padding:18px 22px}
    .gspot-dialog-settings .dialog-heading{margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--line)}
    .gspot-dialog-settings .dialog-heading h1{font-size:20px;font-weight:650;line-height:1.3}
    html.gspot-dialog-settings #content>.panel:not(.tools-ai-card),html.gspot-dialog-settings .configuration-panel{padding:16px!important;border:1px solid var(--line)!important;border-radius:9px!important;background:var(--settings-surface)!important;box-shadow:none!important}
    .gspot-dialog-settings .configuration-panel>p.help{max-width:850px;margin:0 0 12px}
    .gspot-dialog-settings .configuration-panel .publish-placeholders{padding:9px 11px;margin:0 0 14px;background:var(--settings-tint);border:1px solid var(--line);border-radius:7px;font-size:12px}
    .gspot-dialog-settings .publish-placeholders summary{font-weight:600;cursor:pointer}
    .gspot-dialog-settings .configuration-panel .publish-course{padding:0;margin:0 0 9px;border:1px solid var(--line);border-radius:8px;overflow:hidden}
    .gspot-dialog-settings .publish-course>summary{padding:11px 13px;cursor:pointer;font-size:14px;font-weight:650;line-height:1.4;background:var(--settings-tint);color:var(--settings-section)}
    .gspot-dialog-settings .publish-course[open]>summary{border-bottom:1px solid var(--line)}
    .gspot-dialog-settings .publish-location-row{grid-template-columns:125px minmax(0,1fr) auto;gap:4px 10px;align-items:center;margin:0;padding:9px 13px;border:0}
    .gspot-dialog-settings .publish-location-row>label{font-size:12px;font-weight:600;color:var(--ink)}
    .gspot-dialog-settings .publish-location-row input{min-width:0;min-height:32px;border-radius:6px}
    .gspot-dialog-settings .publish-location-row>.publish-example{font-size:11px;line-height:1.35;overflow-wrap:anywhere;color:var(--muted)}
    .gspot-dialog-settings .publish-location-row>.actions{margin:0;gap:5px;display:flex}
    .gspot-dialog-settings .publish-location-row>.actions button{height:32px;border-radius:6px;white-space:nowrap}
    .gspot-dialog-settings .publish-base-row{padding-top:13px;padding-bottom:11px;border-bottom:1px solid var(--line)}
    .gspot-dialog-settings .publish-example-note{margin:0;padding:9px 13px 0;font-size:11px;color:var(--muted)}
    .gspot-dialog-settings .configuration-save{margin:0;min-height:0}
    .gspot-dialog-settings .desktop-theme-choices{gap:12px;margin:12px 0 0}
    .gspot-dialog-settings .desktop-theme-choice strong{font-size:14px;font-weight:650}
    .gspot-dialog-settings .dialog-footer{border-radius:0!important;box-shadow:none!important}
    .gspot-dialog-settings input:focus-visible,.gspot-dialog-settings select:focus-visible,.gspot-dialog-settings button:focus-visible,.gspot-dialog-settings summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
    @media(max-width:720px){.gspot-dialog-settings .layout>main{padding:14px}.gspot-dialog-settings .publish-location-row{grid-template-columns:minmax(0,1fr) auto}.gspot-dialog-settings .publish-location-row>label{grid-column:1/-1}.gspot-dialog-settings .publish-location-row>.publish-example{grid-column:1/-1}}

  `;document.head.append(style);
  function chrome(){
    const aside=document.querySelector('.layout>aside');document.querySelector('.topbar')?.remove();
    if(aside){if(family==='settings')aside.innerHTML='<nav class="tools-nav" aria-label="App settings">'+Object.entries(modules).map(([id,[label]])=>(id==='about'?'<p class="help" style="margin:18px 10px 6px">Help</p>':'')+`<button type="button" data-tools-mode="settings" data-tools-section="${id}"${page.section===id?' aria-current="page"':''}>${label}</button>`).join('')+'</nav>';else{aside.remove();document.querySelector('.layout').style.gridTemplateColumns='minmax(0,1fr)';}}
    const main=document.querySelector('.layout>main');
    if(main){let heading=main.querySelector('.dialog-heading');if(!heading){heading=document.createElement('header');heading.className='dialog-heading';main.prepend(heading);}
      if(family==='settings'&&!helpSections.has(page.section))heading.innerHTML='<h1>'+modules[page.section][0]+'</h1><p>'+modules[page.section][1]+'</p>';
      else if(family==='settings')heading.remove();
      else if(family==='folders')heading.innerHTML='<h1>Output Folders</h1>';else heading.remove();}
    footer();syncFrame();
  }
  function footer(){
    let element=document.querySelector('.dialog-footer');if(!element){element=document.createElement('footer');element.className='dialog-footer';document.body.append(element);}
    const ai=page.section==='ai'?window.GSpotSystemSettings?.status():null;
    element.innerHTML='<span role="status">'+esc(ai?.message||saveStatus)+'</span>'+(family==='settings'?(saveActions[page.section]||[]).map(([id,label],i)=>`<button type="button" data-tools-save="${id}"${i===0?' class="primary"':''}${saving||pending||ai?.busy||(ai&&!ai.ready)?' disabled':''}>${label}</button>`).join(''):'')+'<button type="button" data-tools-close>Close</button>';
  }
  positionPrivateModule=function(){
    const slot=document.getElementById('private-module-slot');if(!privateHost||!slot)return;
    const r=slot.getBoundingClientRect(),bottom=document.querySelector('.dialog-footer')?.getBoundingClientRect().top||innerHeight-52;
    const height=Math.max(160,bottom-r.top-12);slot.style.height=height+'px';
    Object.assign(privateHost.style,{left:r.left+'px',top:r.top+'px',width:r.width+'px',height:height+'px'});
  };
  function syncFrame(){
    if(!privateHost)return;
    const id=S.section.replace('private-',''),meta=privateMeta.get(id);
    privateHost.style.visibility=page.mode==='settings'&&meta?.ready&&meta.view==='settings'&&!meta.pending?'visible':'hidden';
    positionPrivateModule();
    if(page.mode==='settings'&&['recommendations','integrity'].includes(page.section))refreshSignatureFrames(page.section);
  }
  // Only fixed navigation and boolean dirty status cross the module boundary.
  api=async function(path,data){
    let result;try{result=await originalApi(path,data);}catch(error){if(path==='/api/configuration'&&data!==undefined){saving=false;saveStatus='Could not save. Check the fields in this section.';footer();}throw error;}
    if(path==='/api/private-modules/open'){
      const url=new URL(result.url);url.hash='settings';url.searchParams.set('gspot_settings','1');return {...result,url:url.href};
    }
    if(path==='/api/configuration'&&data!==undefined){saving=false;saveStatus='Saved';footer();}
    return result;
  };
  acceptPrivateNavigation=function(...args){const result=originalAccept(...args);chrome();return result;};
  render=function(...args){const result=originalRender(...args);chrome();return result;};
  content=function(){
    if(page.mode==='settings'&&page.section==='ai')return window.GSpotSystemSettings?.aiView()||'<p>Reopen Settings to load AI controls.</p>';
    if(page.mode==='settings'&&page.section==='temporary')return desktopTemporaryFilesView();
    if(page.mode==='settings'&&page.section==='materials')return originalContent().replace(/<div class="configuration-temp">[\s\S]*$/,'</section>');
    if(page.mode==='settings'&&!helpSections.has(page.section))return page.section==='appearance'?(window.GSpotAppearance?.view()||'<p class="help" role="status">Close and reopen '+esc(edition.name)+' to load the updated desktop theme controls.</p>'):originalContent();
    if(page.mode==='folders')return foldersView();
    if(!info)return '<p class="help">Loading version information…</p>';
    if(page.section==='about')return `<section class="tools-help tools-about"><h1>${esc(edition.name)}</h1><p class="help">${edition.private_modules?'Your teaching workspace':'Your teaching materials, in one place'}</p><dl><dt>Application</dt><dd>${esc(info.app_version)}</dd><dt>Desktop</dt><dd>${esc(info.desktop_version)}</dd><dt>Runtime</dt><dd>${esc(info.runtime)}</dd></dl><p>Uses your existing local files and settings.</p><p class="help">F11: full screen · Esc: leave full screen<br>Alt+Left / Right: workspace history · Ctrl+W: close window</p></section>`;
    if(page.section==='changelog')return changelogView(info.changelog||'');
    return `<section class="tools-help tools-technical"><h1>Technical Details</h1><p class="help">${edition.private_modules?'Synchronization log for maintaining the instructor edition.':'Local desktop and engine information.'} The Changelog describes changes in plain language.</p><pre aria-label="Technical information">${esc(info.app_history||'No additional technical history is available.')}</pre></section>`;
  };
  function desktopTemporaryFilesView(){
    const blocked=!S.tempInfo||S.tempInfo.active||isRunning()||temporaryBusy;
    return '<section class="panel tools-temp-panel"><p class="help">Remove generated PDF previews, build logs and cached pages. Saved content and scans are kept.</p><p class="help">'+(S.tempInfo?esc((S.tempInfo.bytes/1048576).toFixed(1))+' MB · '+esc(S.tempInfo.files)+' files':'Loading temporary files…')+'</p><button type="button" data-tools-clear-temp'+(blocked?' disabled':'')+'>'+(temporaryBusy?'Clearing…':'Clear temporary files')+'</button><p role="status">'+esc(temporaryMessage)+'</p></section>';
  }
  async function clearTemporaryFiles(){
    if(temporaryBusy)return false;
    if(S.busy){temporaryMessage='An app action is still running. Try again when it finishes.';render();return false;}
    temporaryBusy=true;temporaryMessage='';render();
    try{
      const cleared=await action('clear-temp',{dataset:{action:'clear-temp'}});
      if(cleared)temporaryMessage='Cleared '+S.tempInfo.cleared_files+' files.'+(S.tempInfo.skipped_entries?' Items still in use were kept.':'')+(Object.keys(S.tempInfo.protected_caches||{}).length?' Older linked TeX solutions still use the Drafts cache; it was kept.':'');
      return !!cleared;
    }catch(error){temporaryMessage=error.message||'Temporary files could not be cleared.';return false;}
    finally{temporaryBusy=false;render();}
  }
  function confirmAction(title,message,{confirmLabel='Continue',cancelLabel='Cancel'}={}){
    if(dialog.open||confirmation)return Promise.resolve(false);
    return new Promise(resolve=>{
      const finish=value=>{if(!confirmation)return;confirmation=null;dialog.removeEventListener('close',closed);if(dialog.open)dialog.close();resolve(!!value);};
      const closed=()=>finish(false);confirmation=finish;dialog.addEventListener('close',closed);
      modal(esc(title),'<p>'+esc(message)+'</p><div class="tools-confirm-actions"><button type="button" data-tools-confirm="cancel">'+esc(cancelLabel)+'</button><button type="button" class="primary" data-tools-confirm="accept">'+esc(confirmLabel)+'</button></div>');
      dialog.querySelector('[data-tools-confirm="cancel"]')?.focus();
    });
  }
  function changelogView(text){
    const groups=[];let group=null;
    for(const line of text.split('\n')){if(/^\d+\.\d+\.\d+/.test(line)){group={title:line.trim(),items:[]};groups.push(group);}else if(group&&line.startsWith('- '))group.items.push(line.slice(2).trim());else if(group&&line.trim()&&group.items.length)group.items[group.items.length-1]+=' '+line.trim();}
    return '<section class="tools-help"><h1>Changelog</h1><div class="tools-history">'+groups.map(g=>'<article><h2>'+esc(g.title)+'</h2><ul>'+g.items.map(t=>'<li>'+esc(t)+'</li>').join('')+'</ul></article>').join('')+'</div></section>';
  }
  function foldersView(){const html=allFoldersView();return edition.private_modules?html:html.split('<section class="panel tools-other-folders">')[0];}
  function allFoldersView(){
    return `<section class="panel"><h2>Materials</h2><p class="help">Select a course and semester to open its configured destinations. Settings control these folders.</p><div class="tools-output-controls">${field('Course',`<select data-tools-course>${S.courses.map(c=>option(c.code,'Math '+c.code,S.course)).join('')}</select>`)}${field('Semester',`<select data-tools-semester>${terms().map(t=>option(t.value,t.label,S.semester)).join('')}</select>`)}<button type="button" data-tools-refresh>Refresh folders</button></div><p class="help" role="status">${esc(folderError)}</p>${folderList.map((f,i)=>`<div class="tools-folder-row"><div><strong>${esc(f.kinds.join(', '))}</strong><p>${esc(f.path)}</p>${f.exists?'':'<p class="help">Not created yet. Publish a document first.</p>'}</div><button type="button" data-tools-folder="${i}"${f.exists?'':' disabled'}>Open folder</button></div>`).join('')}</section><section class="panel tools-other-folders"><h2>Other modules</h2>${[['recommendations','Recommendation letters','Published letters in the local Letters library.'],['integrity','Integrity case files','Each case keeps its evidence and correspondence together.']].map(([id,title,description])=>`<div class="tools-folder-row"><div><strong>${title}</strong><p class="help">${description}</p></div><button type="button" data-tools-local="${id}">Open folder</button></div>`).join('')}</section>`;
  }
  async function loadFolders(){
    folderError='';folderList=[];
    try{
      const scopes=['handouts','manual','syllabus','support'];
      const results=await Promise.all(scopes.map(scope=>api('/api/output-folders',{course:S.course,semester:S.semester,scope})));
      const merged=new Map();results.forEach((result,index)=>{for(const f of result.folders){if(merged.has(f.path)){const prior=merged.get(f.path);prior.kinds=[...new Set([...prior.kinds,...f.kinds])];}else merged.set(f.path,{...f,scope:scopes[index]});}});
      folderList=[...merged.values()];
    }catch(error){folderError=error.message;}
    if(page.mode==='folders')render();
  }
  async function show(mode='settings',section='materials'){
    if(mode!==family){if(mode==='settings')return native().open_settings(section);if(mode==='folders')return native().open_folders();return native().open_help(section);}
    if(pending||saving||temporaryBusy)return false;
    if(mode==='settings'&&!modules[section])return false;
    if(!['settings','folders','help'].includes(mode))return false;
    if(dialog.open){toast('Close the current dialog before switching settings.');return false;}
    if(page.section==='ai'&&section!=='ai'&&window.GSpotSystemSettings?.dirty()){if(!await confirmAction('Discard AI settings changes?','Leave your unsaved AI settings?',{confirmLabel:'Discard changes',cancelLabel:'Keep editing'}))return false;window.GSpotSystemSettings.discard();}
    const old=page,target=mode==='settings'?(['appearance','ai','temporary'].includes(section)?'desktop-'+section:helpSections.has(section)?'desktop-help':section==='materials'?'configuration':'private-'+section):'history';
    pending=true;page={mode,section};saveStatus='';if(helpSections.has(section))info=null;
    try{
      await action('section',{dataset:{section:target,view:mode==='settings'&&section!=='materials'?'settings':undefined}});
      if(S.section!==target){page=old;chrome();return false;}
      if(mode==='folders')await loadFolders();
      if(mode==='settings'&&section==='temporary'){S.tempInfo=await api('/api/temp-files');render();}
      if(mode==='settings'&&section==='ai'){await window.GSpotSystemSettings.loadAI();render();}
      if(mode==='help'||helpSections.has(section)){info=await native().tool_info(section);render();}
      chrome();return true;
    }catch(error){page=old;chrome();toast(error.message);return false;}
    finally{pending=false;footer();}
  }
  function save(action){
    if(saving||pending)return;
    if(page.section==='ai'){window.GSpotSystemSettings?.saveAI();return;}
    if(page.section==='materials'){
      const form=document.querySelector('#configuration-form');if(!form||!form.reportValidity())return;
      saving=true;saveStatus='Saving…';footer();form.requestSubmit();return;
    }
    const module=page.section,frame=privateFrames.get(module),meta=privateMeta.get(module);
    if(!frame||!meta?.ready||meta.view!=='settings'){saveStatus='This section is still opening.';footer();return;}
    const id=crypto.randomUUID();saving=true;saveStatus='Saving…';footer();
    const timeout=setTimeout(()=>{saveWaiters.delete(id);saving=false;saveStatus='Check the fields and messages in this section.';footer();},6000);
    saveWaiters.set(id,{frame,origin:meta.origin,timeout});
    frame.contentWindow.postMessage({source:'gspot-desktop',type:'settings-save',id,module,action},meta.origin);
  }
  // Only the explicitly shared signature path crosses this settings-only bridge.
  let signatureRefreshing=false;
  async function refreshSignatureFrames(selected){
    if(signatureRefreshing||!edition.private_modules||typeof native()?.signature_info!=='function')return;
    signatureRefreshing=true;
    try{
      const result=await native().signature_info();if(result.error||typeof result.path!=='string')return;
      for(const module of selected?[selected]:['recommendations','integrity']){
        const frame=privateFrames.get(module),meta=privateMeta.get(module);if(!frame||!meta?.ready||meta.view!=='settings')continue;
        frame.contentWindow.postMessage({source:'gspot-desktop',type:'signature-current',id:crypto.randomUUID(),module,path:result.path},meta.origin);
      }
    }catch{}finally{signatureRefreshing=false;}
  }
  function signatureRequest(event){
    const data=event.data;
    if(data?.source!=='gspot-desktop-frame'||data.type!=='signature-browse')return false;
    const module=page.section,frame=privateFrames.get(module),meta=privateMeta.get(module);
    if(!['recommendations','integrity'].includes(module)||page.mode!=='settings'||!frame||meta?.view!=='settings'||!meta.ready||event.source!==frame.contentWindow||event.origin!==meta.origin||!/^[a-z0-9-]{1,100}$/i.test(data.id||'')||signatureBusy)return true;
    signatureBusy=true;
    (async()=>{
      let result;try{result=await native().browse_signature();}catch{result={error:'The signature browser could not open. You can still type the path.'};}
      frame.contentWindow.postMessage({source:'gspot-desktop',type:'signature-picked',id:data.id,module,...result},meta.origin);
    })().finally(()=>signatureBusy=false);
    return true;
  }

  window.addEventListener('message',event=>{
    if(signatureRequest(event))return;
    if(event.data?.source==='gspot-desktop-frame'&&event.data.type==='settings-open'&&event.data.section==='ai'&&edition.private_modules){const known=[...privateFrames].some(([id,frame])=>frame.contentWindow===event.source&&privateMeta.get(id)?.origin===event.origin);if(known)show('settings','ai');return;}
    if(event.data?.source!=='gspot-desktop-frame'||event.data.type!=='settings-save-result')return;
    const request=saveWaiters.get(event.data.id);if(!request||event.source!==request.frame.contentWindow||event.origin!==request.origin)return;
    clearTimeout(request.timeout);saveWaiters.delete(event.data.id);saving=false;
    if(event.data.ok)refreshSignatureFrames();
    saveStatus=event.data.ok?'Saved':'Could not save. Check the fields and messages in this section.';footer();
  });
  document.addEventListener('click',event=>{
    const target=event.target.closest('[data-tools-mode],[data-tools-refresh],[data-tools-folder],[data-tools-local],[data-tools-save],[data-tools-close],[data-tools-ai-check],[data-tools-clear-temp],[data-tools-confirm]');if(!target)return;
    event.preventDefault();
    if(target.disabled)return;
    if(target.dataset.toolsConfirm){confirmation?.(target.dataset.toolsConfirm==='accept');return;}
    (async()=>{
      if(target.hasAttribute('data-tools-close'))return window.GSpotDesktop.close();
      if(target.hasAttribute('data-tools-clear-temp'))return clearTemporaryFiles();
      if(target.hasAttribute('data-tools-ai-check'))return window.GSpotSystemSettings?.checkAI();
      if(target.dataset.toolsSave)return save(target.dataset.toolsSave);
      if(target.dataset.toolsMode)return show(target.dataset.toolsMode,target.dataset.toolsSection);
      if(target.hasAttribute('data-tools-refresh'))return loadFolders();
      if(target.dataset.toolsLocal){const result=await native().open_folder(target.dataset.toolsLocal);if(!result.opened)toast(result.error);return;}
      const f=folderList[Number(target.dataset.toolsFolder)];if(!f)return;
      const kind=f.kinds[0],scope=f.scope;
      await api('/api/output-folders',{course:S.course,semester:S.semester,scope,open_kind:kind});
    })().catch(error=>toast(error.message));
  },true);
  document.addEventListener('change',event=>{
    if(event.target.hasAttribute('data-tools-course')){
      S.course=event.target.value;loadCatalog().then(loadFolders).catch(error=>toast(error.message));
    }else if(event.target.hasAttribute('data-tools-semester')){S.semester=event.target.value;loadFolders();}
  });
  window.GSpotTools={show,confirm:confirmAction,updateFooter:footer,status:()=>({ready:!pending,mode:page.mode,section:page.section,folders:folderList.length,saving,clearing:temporaryBusy})};
  window.addEventListener('gspot-appearance-ready',()=>{if(page.mode==='settings'&&page.section==='appearance')render();});
  function start(){if(!(family==='settings'&&(['appearance','ai','temporary'].includes(page.section)||helpSections.has(page.section)))&&!S.courses.length){setTimeout(start,50);return;}show(...initial);}
  start();
})();
