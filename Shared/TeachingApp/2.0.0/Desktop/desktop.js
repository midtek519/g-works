/* Optional desktop enhancement. Navigation stays in this window's memory. */
(() => {
  'use strict';
  if(window.GSpotDesktop)return;
  const config=__DESKTOP_CONFIG__;
  const utility=!!config.role&&config.role!=='main';
  const native=()=>window.pywebview?.api;
  const history=[],maxHistory=60;
  let index=-1,restoring=false,depth=0,queued=false,ready=false,reportTimer,closing=false,configBaseline=null,configSavedForm=null;
  const checkWaiters=new Map();
  let pageErrors=0;
  window.addEventListener('error',()=>pageErrors++);
  window.addEventListener('unhandledrejection',()=>pageErrors++);
  const fields=['section','tab','course','semester','bankQuery','bankCourse','bankUse','bankTopic','bankTopicExcluded','bankCourseExcluded','bankSemester','bankSemesterExcluded','bankUseExcluded','bankFormat','bankFormatExcluded','bankSolution','bankSolutionExcluded','bankDiscontinuedExcluded','bankDiscontinued','bankPage','bankPageSize','bankSort','bankGroup','bankTrash','bankInspect','bankScope','archiveCategory','archiveUnlocked','manualQuestionId','manualQuestionMode','libraryQuery','libraryKind','libraryDocument','libraryPage','builderQuery','builderTopic','builderCourseChosen','taxonomyCourse','taxonomyQuery','taxonomyKind','expandedModule','materialSection'];
  const scrollSelectors=['#questions','.bank-browser','.bank-view > .editor','#manual-outline','#assignment-questions','#builder-question-list','#support-material-list','main','aside'];
  const css=`
    .desktop-navigation{display:flex;gap:3px;align-items:center;flex:none}
    .desktop-navigation button{width:29px;height:29px;padding:4px;display:grid;place-items:center;border-radius:6px;background:transparent;border-color:transparent}
    .desktop-navigation button:hover:not(:disabled){background:var(--hover);border-color:var(--line)}
    .desktop-navigation svg{width:17px;height:17px}
    .topbar>[data-desktop="menu"]{display:grid;place-items:center;flex:none;width:29px;height:29px;padding:5px}
    .topbar>[data-desktop="menu"] svg{width:18px;height:18px}
    .desktop-navigation button:disabled{opacity:.27}
    .topbar{gap:15px;padding-left:12px;padding-right:16px}
    .desktop-toolbar-menu{position:fixed;z-index:1000;right:16px;top:65px;padding:5px;min-width:220px;border:1px solid var(--line);background:white;border-radius:9px;box-shadow:0 7px 25px #18366024}
    .desktop-toolbar-menu button{display:block;width:100%;text-align:left;border:0;padding:8px 11px}
    .desktop-toolbar-menu small{display:block;padding:6px 11px;color:var(--muted);font-size:11px}
    .topbar .local{display:none!important}
    .main-nav [hidden],.private-section[hidden]{display:none!important}
    .topbar>[data-desktop="menu"]{margin-left:0}
    .topbar>[data-desktop="refresh"]{display:grid;place-items:center;flex:none;margin-left:auto;width:29px;height:29px;padding:5px}
    .topbar>[data-desktop="refresh"] svg{width:18px;height:18px}
    @media(max-width:1100px){.topbar{gap:10px}.brand small{font-size:11px}.desktop-navigation button{width:26px}}
  `;
  const style=document.createElement('style');style.textContent=css;document.head.append(style);
  const arrow=direction=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${direction<0?'m14 5-7 7 7 7M7 12h14':'m10 5 7 7-7 7M17 12H3'}"/></svg>`;
  const more='<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="19" cy="12" r="1.7"/></svg>';
  const originalAction=action,originalRender=render,originalAccept=acceptPrivateNavigation,originalApi=api;
  const originalEnsure=ensurePreviewWindow;
  function label(){return document.querySelector('.header-page-heading h1')?.textContent||'Teaching workspace';}
  function configurationValue(){const f=document.getElementById('configuration-form');return f?JSON.stringify([...f.querySelectorAll('input,select,textarea')].map(el=>[el.id||el.name,el.type==='checkbox'?el.checked:el.value])):null;}
  function configurationDirty(){const now=configurationValue();return now!==null && configBaseline!==null && now!==configBaseline;}
  function configurationBaseline(){
    const form=document.getElementById('configuration-form');
    if(S.section!=='configuration'){configBaseline=null;configSavedForm=null;return;}
    if(configBaseline===null||(configSavedForm&&form!==configSavedForm)){configBaseline=configurationValue();configSavedForm=null;}
  }
  function dirty(){
    try{capture();}catch{}
    return !!(S.questionDirty||S.assignmentDirty||(typeof AuthoringWorkflow!=='undefined'&&AuthoringWorkflow.dirty())||(typeof SB!=='undefined'&&SB.dirty)||supportDirty()||configurationDirty()||window.GSpotSystemSettings?.dirty?.()||document.querySelector('#chapters-form,#taxonomy-form'));
  }
  function snapshot(){
    const state=Object.fromEntries(fields.map(key=>[key,S[key]]));
    state.privateViews={...(S.privateViews||{})};
    state.questionId=S.question?.id||null;state.editorId=S.editor?.id||null;
    // Academic editor state stays in JS memory and is never sent to the native API.
    state.editor=S.editor&&!S.questionDirty?clone(S.editor):null;
    state.assignmentId=S.assignment?.id||null;
    state.label=label();state.x=window.scrollX;state.y=window.scrollY;
    state.scrolls=scrollSelectors.map(selector=>{const el=document.querySelector(selector);return {selector,top:el?.scrollTop||0,left:el?.scrollLeft||0};});
    return state;
  }
  function route(state){return JSON.stringify([state.section,state.section?.startsWith('private-')?state.privateViews[state.section.slice(8)]:null,state.tab,state.course,state.semester,state.section==='bank'?state.questionId:null,state.section==='question-builder'?state.editorId:null,state.section==='handout-builder'?state.assignmentId:null,state.section==='course-library'?state.libraryDocument:null,state.section==='handout-builder'&&state.tab==='manual'?state.manualQuestionId:null]);}
  function updateCurrent(){if(index>=0)history[index]=snapshot();}
  function record(){
    queued=false;if(!ready||restoring||depth)return;
    const state=snapshot();
    if(index>=0 && route(history[index])===route(state))history[index]=state;
    else{history.splice(index+1);history.push(state);if(history.length>maxHistory)history.shift();index=history.length-1;}
    toolbar();report();
  }
  function schedule(){if(queued)return;queued=true;requestAnimationFrame(record);}
  function toolbar(){
    const header=document.querySelector('.topbar');if(!header)return;
    if(utility){
      configurationBaseline();
      return;
    }
    document.querySelectorAll('[data-action="section"][data-section="configuration"],.private-section[data-view="settings"]').forEach(el=>el.hidden=true);
    let nav=header.querySelector('.desktop-navigation');
    if(!nav){nav=document.createElement('nav');nav.className='desktop-navigation';nav.setAttribute('aria-label','Workspace history');nav.innerHTML=`<button type="button" data-desktop="back" title="Back · Alt+Left" aria-label="Back">${arrow(-1)}</button><button type="button" data-desktop="forward" title="Forward · Alt+Right" aria-label="Forward">${arrow(1)}</button>`;header.prepend(nav);}
    const back=nav.querySelector('[data-desktop="back"]'),forward=nav.querySelector('[data-desktop="forward"]');
    back.disabled=index<=0||restoring;forward.disabled=index>=history.length-1||restoring;
    back.title=index>0?'Back to '+history[index-1].label+' · Alt+Left':'Back · Alt+Left';
    forward.title=index<history.length-1?'Forward to '+history[index+1].label+' · Alt+Right':'Forward · Alt+Right';
    if(window.GSpotHeader){window.GSpotHeader.mount();configurationBaseline();return;}
    let menu=header.querySelector('[data-desktop="menu"]');
    if(!menu){menu=document.createElement('button');menu.type='button';menu.className='quiet small';menu.dataset.desktop='menu';menu.title='App options';menu.setAttribute('aria-label','App options');menu.setAttribute('aria-haspopup','menu');menu.innerHTML=more;header.append(menu);}
    if(!header.querySelector('[data-desktop="refresh"]')){const refresh=document.createElement('button');refresh.type='button';refresh.className='quiet small';refresh.dataset.desktop='refresh';refresh.title='Refresh '+config.name+' and loaded modules';refresh.setAttribute('aria-label','Refresh '+config.name);refresh.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 7a8 8 0 1 0 1 8M20 3v5h-5"/></svg>';header.insertBefore(refresh,menu);}
    header.querySelector('.local')?.remove();
    configurationBaseline();
  }
  function report(){
    clearTimeout(reportTimer);reportTimer=setTimeout(()=>native()?.state({dirty:dirty(),busy:!!S.busy,label:label(),canBack:index>0&&!restoring,canForward:index<history.length-1&&!restoring}).catch(()=>{}),200);
  }
  api=async function(path,data){const result=await originalApi(path,data);if(path==='/api/configuration'&&data!==undefined){configBaseline=configurationValue();configSavedForm=document.getElementById('configuration-form');}return result;};
  render=function(...args){const result=originalRender(...args);toolbar();schedule();return result;};
  action=async function(name,target){
    if(!utility && ((name==='section'&&target.dataset.section==='configuration')||(['section','private-section'].includes(name)&&target.dataset.view==='settings'))){
      return native()?.open_settings(target.dataset.section==='configuration'?'materials':target.dataset.section.replace('private-',''));
    }
    if(!restoring && depth===0)updateCurrent();
    if(name==='section' && S.section==='configuration' && target.dataset.section!==S.section && configurationDirty() && !confirm('Leave your unsaved configuration changes?'))return;
    depth++;
    try{return await originalAction(name,target);}
    finally{depth--;if(!restoring)schedule();report();}
  };
  acceptPrivateNavigation=function(...args){const result=originalAccept(...args);schedule();return result;};
  async function move(delta){
    if(utility)return false;
    if(restoring||S.busy)return false;
    const destination=index+delta;
    if(destination<0||destination>=history.length)return false;
    updateCurrent();const target=history[destination],oldSection=S.section;
    if(dialog.open){toast('Finish or close the dialog before navigating.');return false;}
    if(S.assignmentDirty&&S.assignment?.id!==target.assignmentId&&target.section==='handout-builder'&&!leaveDraft())return false;
    if(S.section===target.section&&S.section==='question-builder'&&S.questionDirty&&S.editor?.id!==target.editorId){if(!leaveDraft())return false;S.questionDirty=false;}
    restoring=true;toolbar();
    let completed=false;
    try{
      const view=target.section.startsWith('private-')?target.privateViews[target.section.slice(8)]:undefined;
      await action('section',{dataset:{section:target.section,view}});
      if(S.section!==target.section)return false; // An existing save/leave prompt was cancelled.
      if(view){
        const module=target.section.slice(8),deadline=Date.now()+4000;
        while(Date.now()<deadline){const meta=privateMeta.get(module);if(meta?.ready&&!meta.pending)break;await new Promise(resolve=>setTimeout(resolve,30));}
        const meta=privateMeta.get(module);
        if(!meta?.ready||meta.pending||meta.view!==view)return false;
      }
      if(oldSection===target.section&&target.section==='question-builder'&&S.questionDirty&&S.editor?.id!==target.editorId)return false;
      const previousCourse=S.course,previousSemester=S.semester;
      for(const field of fields){if(field!=='section'&&target[field]!==undefined)S[field]=target[field];}
      if(view)S.privateViews={...(S.privateViews||{}),[target.section.slice(8)]:view};
      if(previousCourse!==S.course||previousSemester!==S.semester)await loadCatalog(S.semester);
      if(target.section==='bank')S.question=qById(target.questionId)||null;
      if(target.section==='question-builder'&&!(S.questionDirty&&S.editor?.id===target.editorId)){
        S.editor=target.editor?clone(target.editor):target.editorId?clone(qById(target.editorId)||blankQuestion()):blankQuestion();
        S.questionDirty=false;S.questionEditUnlocked=false;
      }
      if(target.section==='handout-builder'&&target.assignmentId&&S.assignment?.id!==target.assignmentId){
        S.assignment=await api('/api/universal/assignments/'+target.assignmentId);S.assignmentDirty=false;
      }
      if(target.section==='course-library')await loadLibrary();
      originalRender();index=destination;toolbar();
      completed=true;
      requestAnimationFrame(()=>requestAnimationFrame(()=>{
        for(const item of target.scrolls){const element=document.querySelector(item.selector);if(element){element.scrollTop=item.top;element.scrollLeft=item.left;}}
        window.scrollTo(target.x,target.y);restoring=false;toolbar();report();
      }));
      return true;
    }finally{if(!completed){restoring=false;toolbar();schedule();}}
  }
  function menu(){
    const existing=document.querySelector('.desktop-toolbar-menu');if(existing){existing.remove();return;}
    const el=document.createElement('div');el.className='desktop-toolbar-menu';el.setAttribute('role','menu');
    el.innerHTML='<button type="button" data-desktop="settings" role="menuitem">All settings…</button><button type="button" data-desktop="folders" role="menuitem">Output folders…</button><button type="button" data-desktop="preview" role="menuitem">Show PDF preview</button><button type="button" data-desktop="fullscreen" role="menuitem">Full screen · F11</button><button type="button" data-desktop="help" role="menuitem">About & changelog…</button><button type="button" data-desktop="close" role="menuitem">Close desktop window</button>';
    document.body.append(el);
  }
  function previewProxy(){
    let current=new URL('/preview.html',location.origin),closed=false;
    const loc={get origin(){return current.origin;},get pathname(){return current.pathname;},get search(){return current.search;},get hash(){return current.hash;},set href(value){current=new URL(value,location.origin);native()?.open_preview(current.pathname+current.search+current.hash).catch(()=>toast('The desktop preview could not open.'));}};
    return {get closed(){return closed;},set closed(value){closed=!!value;},get location(){return loc;},set location(value){loc.href=value;},focus(){if(current.hash)native()?.open_preview(current.pathname+current.search+current.hash).catch(()=>{});}};
  }
  ensurePreviewWindow=function(){if(!native())return originalEnsure();if(!previewWindow||previewWindow.closed)previewWindow=previewProxy();return true;};
  function checkFrames(){
    const waits=[];
    for(const [id,frame] of privateFrames){
      const meta=privateMeta.get(id);if(!meta?.ready)continue;
      const request=crypto.randomUUID();
      waits.push(new Promise(resolve=>{
        const timeout=setTimeout(()=>{checkWaiters.delete(request);resolve({dirty:true,uncertain:true});},2000);
        checkWaiters.set(request,{resolve,timeout,frame,origin:meta.origin});
        frame.contentWindow.postMessage({source:'gspot-desktop',type:'close-check',id:request},meta.origin);
      }));
    }
    return Promise.all(waits);
  }
  window.addEventListener('message',event=>{
    if(event.data?.source!=='gspot-desktop-frame')return;
    if(!utility&&event.data.type==='settings-open'&&event.data.section==='ai'){
      const known=[...privateFrames].some(([id,frame])=>event.source===frame.contentWindow&&event.origin===privateMeta.get(id)?.origin);
      if(known)native()?.open_settings('ai');return;
    }
    if(['navigate','close','fullscreen'].includes(event.data.type)){
      const known=[...privateFrames].some(([id,frame])=>event.source===frame.contentWindow&&event.origin===privateMeta.get(id)?.origin);
      if(!known)return;
      if(event.data.type==='close')close();
      else if(event.data.type==='fullscreen')native()?.toggle_fullscreen(!!event.data.leave);
      else if([-1,1].includes(event.data.direction))move(event.data.direction);
      return;
    }
    if(event.data.type==='refresh-ready'){
      const pending=refreshWaiters.get(event.data.id);
      if(!pending||event.origin!==pending.origin||event.source!==pending.frame.contentWindow)return;
      clearTimeout(pending.timeout);refreshWaiters.delete(event.data.id);pending.resolve(true);return;
    }
    if(event.data.type!=='close-check')return;
    const pending=checkWaiters.get(event.data.id);
    if(!pending||event.origin!==pending.origin||event.source!==pending.frame.contentWindow)return;
    clearTimeout(pending.timeout);checkWaiters.delete(event.data.id);pending.resolve({dirty:!!event.data.dirty,uncertain:false});
  });
  async function confirmClose(message,discard,request){
    const api=native();
    if(api?.close_prompt&&!await api.close_prompt(config.nonce,request,true))return false;
    try{
      if(utility&&window.GSpotTools?.confirm)return await window.GSpotTools.confirm('Close Settings?',message,{confirmLabel:discard?'Discard changes & close':'Close window',cancelLabel:'Keep editing'});
      if(!window.GWorksDialogs)throw Error('The confirmation is unavailable. Reopen the app.');
      return await window.GWorksDialogs.confirm(message,{title:'Close '+config.name+'?',confirmLabel:discard?'Discard changes & close':'Close window'});
    }finally{await api?.close_prompt?.(config.nonce,request,false);}
  }
  async function close(request=null){
    if(closing)return false;closing=true;
    let approved=false;
    try{
      request??=await native()?.begin_close?.(config.nonce);
      const frameChecks=await checkFrames();
      if((dirty()||frameChecks.some(x=>x.dirty))&&!await confirmClose(frameChecks.some(x=>x.uncertain)?'A module could not confirm that all changes are saved. Close the desktop window anyway?':'There are unsaved changes. Close the desktop window and discard them?',true,request))return false;
      if((S.busy||isRunning())&&!await confirmClose('Work or a PDF build is still running. Close this window? The local service will continue running.',false,request))return false;
      const api=native();approved=await(api.begin_close?api.approve_close(config.nonce,request):api.approve_close(config.nonce));return approved;
    }finally{closing=false;if(!approved){const api=native();if(api?.begin_close)api.close_cancelled?.(request);else api?.close_cancelled?.();}}
  }
  const refreshWaiters=new Map();
  async function prepareFrameRefresh(){
    return Promise.all([...privateFrames].map(([id,frame])=>{
      const meta=privateMeta.get(id);if(!meta?.ready)return Promise.resolve(true);
      return new Promise(resolve=>{
        const request=crypto.randomUUID(),timeout=setTimeout(()=>{refreshWaiters.delete(request);resolve(false);},2000);
        refreshWaiters.set(request,{frame,origin:meta.origin,resolve,timeout});
        frame.contentWindow.postMessage({source:'gspot-desktop',type:'refresh-approved',id:request},meta.origin);
      });
    }));
  }
  let refreshing=false,refreshApproved=false;
  window.addEventListener('beforeunload',event=>{if(refreshApproved)event.stopImmediatePropagation();},true);
  async function refreshApp(){
    if(refreshing)return false;refreshing=true;
    try{
      const checks=await checkFrames();
      if((dirty()||checks.some(x=>x.dirty))&&!await window.GWorksDialogs.confirm(checks.some(x=>x.uncertain)?'A module could not confirm that all changes are saved. Refresh '+config.name+' anyway?':'Refresh '+config.name+' and discard unsaved changes in the app and its modules?'))return false;
      if((S.busy||isRunning())&&!await window.GWorksDialogs.confirm('A local task is still running. Refresh the interface? Processing will continue in the local service.'))return false;
      try{sessionStorage.setItem('gspot-refresh-navigation',JSON.stringify({section:S.section,course:S.course,semester:S.semester,privateViews:S.privateViews||{}}));}catch{}
      if((await prepareFrameRefresh()).some(ok=>!ok)){toast('A module did not respond to Refresh. Use Close and reopen the app; saved work stays local.');return false;}
      refreshApproved=true;setTimeout(()=>{refreshApproved=false;},5000);location.reload();return true;
    }finally{refreshing=false;}
  }
  document.addEventListener('click',event=>{
    const button=event.target.closest('[data-desktop]');
    if(!button){if(!event.target.closest('.desktop-toolbar-menu'))document.querySelector('.desktop-toolbar-menu')?.remove();return;}
    event.preventDefault();event.stopImmediatePropagation();
    const name=button.dataset.desktop;
    if(name!=='menu')document.querySelector('.desktop-toolbar-menu')?.remove();
    if(name==='back')move(-1);else if(name==='forward')move(1);else if(name==='menu')menu();else if(name==='refresh')refreshApp().catch(error=>toast(error.message));else if(name==='close')close();else if(name==='pin')native()?.toggle_preview_pin();else if(name==='preview')native()?.open_preview('/preview.html');
    else if(name==='settings')native()?.open_settings();else if(name==='folders')native()?.open_folders();else if(name==='help')native()?.open_help();else if(name==='fullscreen')native()?.toggle_fullscreen();
  },true);
  document.addEventListener('keydown',event=>{
    if(event.key==='F11'||event.key==='Escape'){
      if(event.key==='F11')event.preventDefault();
      native()?.toggle_fullscreen(event.key==='Escape');
      return;
    }
    if(event.altKey&&!event.ctrlKey&&!event.metaKey&&['ArrowLeft','ArrowRight'].includes(event.key)){
      event.preventDefault();event.stopImmediatePropagation();move(event.key==='ArrowLeft'?-1:1);
    }
    if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='w'){event.preventDefault();close();}
  },true);
  document.addEventListener('input',report,true);
  document.addEventListener('change',()=>{schedule();report();},true);
  let scrollTimer;window.addEventListener('scroll',()=>{clearTimeout(scrollTimer);scrollTimer=setTimeout(()=>{if(!restoring)updateCurrent();},100);},true);
  window.GSpotDesktop={back:()=>move(-1),forward:()=>move(1),close,refresh:refreshApp,previewClosed(){if(previewWindow)previewWindow.closed=true;},
    status:()=>({ready,index,length:history.length,section:S.section,canBack:index>0,canForward:index<history.length-1,restoring,dirty:dirty(),pageErrors}),
    frameCheck:checkFrames};
  async function start(){
    if(!S.courses.length||!document.querySelector('.header-page-heading h1')){setTimeout(start,60);return;}
    try{
      const raw=sessionStorage.getItem('gspot-refresh-navigation');sessionStorage.removeItem('gspot-refresh-navigation');
      if(raw){
        const saved=JSON.parse(raw),previousCourse=S.course,previousSemester=S.semester;
        if(S.courses.some(c=>c.code===saved.course))S.course=saved.course;
        if(/^(fa|sp|su|wi)\d{2}$/.test(saved.semester||''))S.semester=saved.semester;
        if(previousCourse!==S.course||previousSemester!==S.semester){await loadCatalog(S.semester);await loadUniversal();}
        for(const module of S.privateModules||[]){const value=saved.privateViews?.[module.id];if(['projects','rubrics','review','settings','students','letters','cases','dashboard','reports','imports','archive','templates','guidance'].includes(value)){S.privateViews??={};S.privateViews[module.id]=value;}}
        const allowed=new Set(['handout-builder','question-builder','syllabus-builder','support','bank','metadata','course-library','history','configuration',...(S.privateModules||[]).filter(m=>m.installed).map(m=>'private-'+m.id)]);
        if(allowed.has(saved.section))await originalAction('section',{dataset:{section:saved.section}});
      }
    }catch(error){toast(error.message);}
    ready=true;toolbar();record();
  }
  start();
})();
