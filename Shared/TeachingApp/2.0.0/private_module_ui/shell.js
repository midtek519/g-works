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
/* Workspace changes ask the loaded editor before replacing its local server. */
(() => {
  const script=document.querySelector('script[data-gwhiz-module]');if(!script)return;
  window.addEventListener('message',async event=>{
    const data=event.data;
    if(event.source!==window.parent||event.origin!==script.dataset.gwhizParent||data?.source!=='gwhiz-shell'||data.version!==1||data.type!=='workspace-leave-check'||data.module!==script.dataset.gwhizModule||!/^workspace-[a-z0-9.-]+$/.test(data.requestId||''))return;
    let busy=false,dirty=false;
    try{if(typeof state!=='undefined')busy=!!state.importBusy;}catch{}
    try{const check=new Event('beforeunload',{cancelable:true});window.dispatchEvent(check);dirty=check.defaultPrevented;}catch{}
    try{if(typeof S!=='undefined')dirty||=!!S.dirty||!!S.reviewDrafts?.size;}catch{}
    const allowed=!busy&&(!dirty||await window.GWorksDialogs.confirm('Discard unsaved changes and switch workspaces?',{title:'Switch workspace',confirmLabel:'Discard and switch',cancelLabel:'Keep editing'}));
    window.parent.postMessage({source:'gwhiz-module',version:1,type:'workspace-leave-result',requestId:data.requestId,allowed,busy},event.origin);
  });
})();
/* Navigation-only bridge. Never passes records, form contents or API tokens. */
(() => {
  'use strict';
  const script = document.querySelector('script[data-gwhiz-module]');
  if (!script || window.parent === window) return;
  const module = script.dataset.gwhizModule, origin = script.dataset.gwhizParent;
  const views = {
    grades: ['students', 'reports', 'imports', 'review', 'settings'],
    recommendations: ['students', 'letters', 'archive', 'settings'],
    integrity: ['cases', 'templates', 'guidance', 'settings']
  }[module];
  if (!views || !/^http:\/\/127\.0\.0\.1:\d+$/.test(origin)) return;
  document.documentElement.classList.add('gwhiz-native', 'gwhiz-' + module);
  let lastView, queued = false;
  function currentView() {
    if (module !== 'integrity' && (typeof state === 'undefined' || !state.boot)) return;
    if (module === 'integrity' && (typeof S === 'undefined' || !S.boot)) return;
    if (module === 'grades') return document.querySelector('#navigation [data-tab].active')?.dataset.tab;
    if (module === 'recommendations') return typeof state !== 'undefined' ? state.view : undefined;
    return document.querySelector('.app-header [data-view].active')?.dataset.view ||
      (typeof S !== 'undefined' ? S.view : undefined);
  }
  function sharedAISettings(view){
    const inDesktop=window.__gspotFrameGuard||new URL(location.href).searchParams.get('gspot_settings')==='1';
    if(view!=='settings'||!inDesktop)return;
    const container=document.querySelector(module==='grades'?'#app-content':module==='recommendations'?'#main':'#page');
    if(!container||container.querySelector('[data-shared-ai-panel]'))return;
    const panel=document.createElement('section');panel.className='gspot-shared-ai-settings';panel.setAttribute('data-shared-ai-panel','');
    panel.innerHTML='<div><h2>AI connections</h2><p>Configure Private and General AI for all modules.</p></div><button type="button" data-open-shared-ai>Open shared AI settings</button>';container.prepend(panel);
  }
  document.addEventListener('click',event=>{
    const button=event.target.closest?.('[data-open-shared-ai]');if(!button||button.disabled)return;
    event.preventDefault();event.stopImmediatePropagation();
    window.parent.postMessage({source:'gspot-desktop-frame',type:'settings-open',section:'ai'},origin);
  },true);
  function publish(type = 'navigation', requestId) {
    const view = currentView();
    if (!views.includes(view)) return;
    sharedAISettings(view);
    if (lastView === undefined) type = 'ready';
    if (type === 'navigation' && view === lastView && requestId === undefined) return;
    lastView = view;
    window.parent.postMessage({source:'gwhiz-module', version:1, type, module, view, requestId}, origin);
  }
  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; publish(); });
  }
  window.addEventListener('message', event => {
    const data = event.data;
    if (event.source !== window.parent || event.origin !== origin || !data ||
        data.source !== 'gwhiz-shell' || data.version !== 1 || data.type !== 'navigate' ||
        data.module !== module || !views.includes(data.view)) return;
    if (currentView() !== data.view) {
      if (module === 'grades') document.querySelector('#navigation [data-tab="' + data.view + '"]')?.click();
      else if (module === 'recommendations') {
        const button = document.querySelector('body > .sidebar [data-view="' + data.view + '"]');
        if (button) button.click();
        else if (data.view === 'archive' && typeof navigate === 'function') navigate('archive');
      } else {
        const button = document.querySelector('.app-header [data-action="nav"][data-view="' + data.view + '"]');
        if (button) button.click();
        else if (data.view === 'archive' && typeof runAction === 'function')
          runAction({dataset:{action:'nav', view:'archive'}});
      }
    }
    // Existing modules own their save/leave checks. Report the actual selection,
    // including when the user cancels an existing unsaved-draft prompt.
    setTimeout(() => publish('navigation', data.requestId), 0);
  });
  new MutationObserver(schedule).observe(document.body, {childList:true, subtree:true, attributes:true, attributeFilter:['class','aria-current']});
  publish('ready');
  window.addEventListener('load', () => publish('ready'), {once:true});
})();

/* Decorative navigation icons only. Labels and event handlers remain intact. */
(() => {
 const script=document.querySelector('script[data-gwhiz-module]');if(!script)return;
 const module=script.dataset.gwhizModule,paths={"conversation":"<path d=\"M2 3h15v10H8l-5 4v-4H2ZM18 7h4v12h-3v3l-4-3h-5v-3\"/>","transcript":"<path d=\"M5 2h14v20l-3-2-4 2-4-2-3 2ZM8 6h8M8 10h8M8 14h5\"/>","letters":"<rect x=\"2\" y=\"5\" width=\"20\" height=\"15\" rx=\"2\"/><path d=\"m3 6 9 7 9-7M3 19l6-6M21 19l-6-6\"/>","person-card":"<rect x=\"2\" y=\"4\" width=\"20\" height=\"16\" rx=\"2\"/><circle cx=\"8\" cy=\"10\" r=\"2\"/><path d=\"M4 17a4 4 0 0 1 8 0M15 9h4M15 13h4M15 17h3\"/>","overview":"<rect x=\"2\" y=\"3\" width=\"8\" height=\"8\" rx=\"1\"/><rect x=\"14\" y=\"3\" width=\"8\" height=\"4\" rx=\"1\"/><rect x=\"2\" y=\"15\" width=\"8\" height=\"6\" rx=\"1\"/><rect x=\"14\" y=\"11\" width=\"8\" height=\"10\" rx=\"1\"/>","evidence":"<circle cx=\"10\" cy=\"10\" r=\"7\"/><path d=\"m15 15 7 7M7 10h6M10 7v6\"/>","meeting":"<circle cx=\"7\" cy=\"6\" r=\"3\"/><circle cx=\"17\" cy=\"6\" r=\"3\"/><path d=\"M2 21v-6a5 5 0 0 1 10 0v6M12 21v-6a5 5 0 0 1 10 0v6M9 15h6M12 12l3 3-3 3\"/>","activity":"<path d=\"M6 2v3M6 9v6M6 19v3M11 6h11M11 17h11\"/><circle cx=\"6\" cy=\"6\" r=\"3\"/><circle cx=\"6\" cy=\"17\" r=\"3\"/>","review-files":"<path d=\"m5 3-3 12v6h20v-6L19 3ZM2 15h6l2 3h4l2-3h6M8 7h8M8 10h8\"/>"};
 function add(button,id){if(!button||button.querySelector('.gspot-subtool-icon')||!paths[id])return;const span=document.createElement('span');span.className='gspot-subtool-icon';span.setAttribute('aria-hidden','true');span.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'+paths[id]+'</svg>';button.prepend(span);}
 let pending=false;
 function update(){pending=false;if(module==='recommendations'){document.querySelectorAll('[data-action="student-tab"]').forEach(b=>add(b,{notes:'conversation',grades:'transcript',letters:'letters',details:'person-card'}[b.dataset.tab]));document.querySelectorAll('[data-action="open-library"]').forEach(b=>add(b,'letters'));document.querySelectorAll('[data-action="files-review"]').forEach(b=>add(b,'review-files'));}else if(module==='integrity'){document.querySelectorAll('.tabs [data-action="tab"]').forEach(b=>add(b,{overview:'overview',evidence:'evidence',letters:'letters',meeting:'meeting',activity:'activity'}[b.dataset.tab]));}}
 function schedule(){if(pending)return;pending=true;requestAnimationFrame(update);}
 if(['recommendations','integrity'].includes(module)){new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true});update();}
})();
