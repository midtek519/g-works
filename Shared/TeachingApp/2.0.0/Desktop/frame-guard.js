/* Desktop close checks pass booleans only; records and forms stay in the frame. */
(() => {
  if (window.parent === window || window.__gspotFrameGuard) return;
  window.__gspotFrameGuard = true;
  let policyBaseline = null,instructorBaseline=null,pendingSave=null;
  const settingsContext=new URL(location.href).searchParams.get('gspot_settings')==='1';
  const policyForm = () => document.querySelector('#policy-form,form[data-form="policy"]');
  const values=elements=>JSON.stringify([...elements].map(el=>[el.id||el.name,el.type==='checkbox'?el.checked:el.value]));
  const policyValue = () => {const form=policyForm();return form?values(form.querySelectorAll('input,select,textarea')):null;};
  const instructorValue=()=>document.querySelector('#instructor-rows')?values(document.querySelectorAll('#instructor-semester,#instructor-rows')):null;
  let seenForm=null;
  new MutationObserver(()=>{const form=policyForm();if(form!==seenForm){seenForm=form;policyBaseline=policyValue();instructorBaseline=instructorValue();}}).observe(document,{childList:true,subtree:true});
  document.addEventListener('focusin', () => {if(policyBaseline===null)policyBaseline=policyValue();},true);
  const originalFetch=window.fetch;
  function saveResult(ok){
    const request=pendingSave,script=document.querySelector('script[data-gwhiz-parent]');if(!request||!script)return;
    clearTimeout(request.timeout);pendingSave=null;
    window.parent.postMessage({source:'gspot-desktop-frame',type:'settings-save-result',id:request.id,ok:!!ok},script.dataset.gwhizParent);
  }
  window.fetch=async (...args)=>{
    const path=String(args[0]),post=String(args[1]?.method||'GET').toUpperCase()==='POST';
    try{
      const response=await originalFetch(...args);
      if(response.ok&&post&&/\/api\/policy/.test(path))setTimeout(()=>policyBaseline=policyValue(),0);
      if(response.ok&&post&&/\/api\/instructors/.test(path))setTimeout(()=>instructorBaseline=instructorValue(),0);
      if(post&&pendingSave&&path.includes(pendingSave.path))setTimeout(()=>saveResult(response.ok),100);
      return response;
    }catch(error){if(post&&pendingSave&&path.includes(pendingSave.path))saveResult(false);throw error;}
  };
  if(settingsContext){
    document.addEventListener('DOMContentLoaded',()=>{
      document.documentElement.classList.add('gspot-module-settings');
      const style=document.createElement('style');style.textContent=`
        html.gspot-module-settings{--settings-surface:var(--signature-surface,#fff);--settings-tint:#f0f5fc;--settings-section:#285b98;--settings-ai-bg:#edf7f1;--settings-ai-line:#b3d6c0;--settings-ai-ink:#174e35}
        html.gspot-module-settings[data-gspot-theme=midnight]{--settings-surface:#252e3e;--settings-tint:#29374b;--settings-section:#b5d0ff;--settings-ai-bg:#203a32;--settings-ai-line:#456e5d;--settings-ai-ink:#c8edda}
        .gspot-module-settings body{background:var(--paper,#f4f7fc);font:13px/1.45 'Segoe UI',system-ui,sans-serif;color:var(--ink)}
        .gspot-module-settings h1,.gspot-module-settings h2,.gspot-module-settings h3{font-family:'Segoe UI',system-ui,sans-serif!important;letter-spacing:normal;line-height:1.35}
        .gspot-module-settings h2,.gspot-module-settings .panel>h3{font-size:17px!important;font-weight:650;margin:0 0 12px;color:var(--settings-section)!important}
        .gspot-module-settings h3{font-size:14px!important;font-weight:600}
        html.gspot-module-settings .panel,html.gspot-module-settings .card{box-shadow:none!important;border:1px solid var(--line)!important;border-radius:9px!important;background:var(--settings-surface)!important;margin:0 0 14px;min-width:0}
        html.gspot-module-settings .panel,html.gspot-module-settings .card:not(:has(>.card-header)){padding:16px}
        .gspot-module-settings .card:has(>.card-header){padding:0}
        .gspot-module-settings .card-header{padding:13px 16px;background:var(--settings-tint);border-bottom:1px solid var(--line);border-radius:8px 8px 0 0}
        .gspot-module-settings .card-header h2{margin:0}
        .gspot-module-settings .card-header p{font-size:12px;line-height:1.45;margin:5px 0 0}
        .gspot-module-settings .card-body{padding:16px}
        .gspot-module-settings p,.gspot-module-settings .help,.gspot-module-settings .field-help,.gspot-module-settings .tiny,.gspot-module-settings .small-text{font-size:12px;line-height:1.5}
        .gspot-module-settings p{margin:0 0 12px}
        .gspot-module-settings label{font-size:12px;font-weight:600;line-height:1.4;margin-bottom:5px}
        .gspot-module-settings button,.gspot-module-settings input,.gspot-module-settings select,.gspot-module-settings textarea{font:12px/1.4 'Segoe UI',system-ui,sans-serif!important;border-radius:6px}
        .gspot-module-settings button,.gspot-module-settings input:not([type=checkbox]):not([type=radio]),.gspot-module-settings select{min-height:32px;padding:6px 9px}
        .gspot-module-settings input:not([type=checkbox]):not([type=radio]),.gspot-module-settings select,.gspot-module-settings textarea{max-width:100%;min-width:0;width:100%}
        .gspot-module-settings textarea{padding:9px 10px;resize:vertical;line-height:1.6}
        .gspot-module-settings input[type=checkbox],.gspot-module-settings input[type=radio]{min-height:0;width:15px;height:15px;margin:0}
        .gspot-module-settings .settings-grid{display:grid;grid-template-columns:minmax(250px,.8fr) minmax(400px,1.2fr);gap:14px;align-items:start}
        .gspot-module-settings .settings-grid>.panel{margin:0}
        .gspot-module-settings .settings-identity-row,.gspot-module-settings .settings-letterhead-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
        .gspot-module-settings .settings-identity-row>.field{min-width:0;margin:0 0 12px}
        .gspot-module-settings .settings-letterhead-grid>.span-all{grid-column:1/-1}
        .gspot-module-settings #profile-form>.field,.gspot-module-settings .settings-signature-field{margin-bottom:12px}
        .gspot-module-settings .settings-path-row{display:flex;align-items:start;gap:7px;min-width:0}
        .gspot-module-settings .settings-path-row>input{flex:1;min-width:0;margin:0}
        .gspot-module-settings .settings-path-row>button{flex:none;white-space:nowrap}
        .gspot-module-settings [data-browse-signature]{display:inline-flex!important;align-items:center}
        .gspot-module-settings .settings-signature-field>.field-help{display:block;margin-top:5px}
        .gspot-module-settings [data-signature-status]:empty{display:none}
        .gspot-module-settings #style-guide{min-height:220px!important;height:260px;margin:0 0 12px}
        .gspot-module-settings .notice{font-size:12px;padding:10px 12px;line-height:1.5}
        .gspot-module-settings .settings-wrap{max-width:none;width:100%}
        /* The parent Settings window supplies the inset and page heading. */
        html.gspot-module-settings body{padding:0!important;margin:0!important}
        html.gspot-module-settings :is(.shell,.main-shell,.app-shell){padding:0!important;margin:0!important;width:100%!important;min-height:0!important}
        html.gspot-module-settings :is(#app-content,#main,#page,main#app){box-sizing:border-box;padding:0!important;margin:0!important;width:100%!important;max-width:none!important;min-height:0!important}
        html.gspot-module-settings :is(.shell>.topbar,.main-shell>.topbar,.app-header,body>header,.page-heading){display:none!important}
        html.gspot-module-settings .gspot-shared-ai-settings{box-sizing:border-box;display:flex;align-items:center;justify-content:space-between;gap:14px;width:100%;min-width:0;padding:12px 15px;margin:0 0 14px;border:1px solid var(--settings-ai-line)!important;border-top:3px solid #31825a!important;border-radius:9px!important;background:var(--settings-ai-bg)!important;color:var(--settings-ai-ink)!important;box-shadow:none!important}
        html.gspot-module-settings .gspot-shared-ai-settings>div{flex:1;min-width:0}
        html.gspot-module-settings .gspot-shared-ai-settings h2{font:650 14px/1.4 'Segoe UI',system-ui,sans-serif!important;letter-spacing:normal;margin:0!important;color:var(--settings-ai-ink)!important}
        html.gspot-module-settings .gspot-shared-ai-settings p{font:400 12px/1.4 'Segoe UI',system-ui,sans-serif;margin:3px 0 0!important;color:inherit!important}
        html.gspot-module-settings .gspot-shared-ai-settings>button{box-sizing:border-box;flex:0 0 auto;align-self:center;min-height:32px;margin:0;padding:6px 10px;font:500 12px/1.4 'Segoe UI',system-ui,sans-serif!important;white-space:nowrap;color:#24568a!important;background:#fff!important;border:1px solid #b8cee9!important;border-radius:6px;box-shadow:none!important}
        html.gspot-module-settings .gspot-shared-ai-settings>button:hover:not(:disabled){background:#e6f0fa!important;border-color:#8faecd!important}
        html.gspot-module-settings .gspot-shared-ai-settings>button:focus-visible{outline:2px solid #31825a;outline-offset:2px}
        html.gspot-module-settings[data-gspot-theme=midnight] .gspot-shared-ai-settings>button{color:#deebfc!important;background:#2a394e!important;border-color:#66819d!important}
        html.gspot-module-settings[data-gspot-theme=midnight] .gspot-shared-ai-settings>button:hover:not(:disabled){background:#344b62!important;border-color:#93b0cb!important}
        .gspot-module-settings [data-action=save-policy],.gspot-module-settings [data-action=save-instructors],.gspot-module-settings [data-action=save-style],.gspot-module-settings [data-action=save-profile],.gspot-module-settings form[data-form=settings] button[type=submit]{display:none!important}
        .gspot-module-settings .policy-term-grid{grid-template-columns:155px minmax(0,1fr);gap:18px}
        .gspot-module-settings .policy-choice{padding:8px 10px;text-align:left}
        .gspot-module-settings .weight-row{grid-template-columns:minmax(145px,1fr) 85px 95px;gap:9px;padding:6px 0}
        .gspot-module-settings .policy-cutoffs{gap:9px}
        .gspot-module-settings .policy-cutoffs label{display:block}
        .gspot-module-settings .form-grid,.gspot-module-settings .row{gap:12px}
        @media(max-width:1050px){.gspot-module-settings .settings-grid{grid-template-columns:minmax(0,1fr)}}
        @media(max-width:640px){.gspot-module-settings .settings-identity-row,.gspot-module-settings .settings-letterhead-grid{grid-template-columns:minmax(0,1fr)}.gspot-module-settings .policy-term-grid{grid-template-columns:minmax(0,1fr)}.gspot-module-settings .policy-list{display:flex;flex-wrap:wrap;gap:6px}}
        @media(max-width:580px){html.gspot-module-settings .gspot-shared-ai-settings{align-items:start;flex-direction:column}html.gspot-module-settings .gspot-shared-ai-settings>button{align-self:flex-start}}
      `;document.head.append(style);
    },{once:true});
  }
  let signatureRequestId=null;
  const signatureInput=()=>document.querySelector('#signature-file,input[name="signature_file"]');
  function signatureMessage(data){
    if(!['signature-current','signature-picked'].includes(data.type))return false;
    const script=document.querySelector('script[data-gwhiz-parent]');
    if(!settingsContext||!script||data.module!==script.dataset.gwhizModule||!['recommendations','integrity'].includes(data.module))return true;
    const input=signatureInput();if(!input)return true;
    const status=document.querySelector('[data-signature-status]'),button=document.querySelector('[data-browse-signature]');
    if(data.type==='signature-picked'){
      if(data.id!==signatureRequestId)return true;signatureRequestId=null;if(button)button.disabled=false;
      if(data.error){if(status)status.textContent=data.error;return true;}
      if(data.cancelled){if(status)status.textContent='Selection cancelled.';return true;}
      if(typeof data.path!=='string'||data.path.length>2000)return true;
      input.value=data.path;input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
      if(status)status.textContent='Save letterhead to apply to both modules.';return true;
    }
    if(typeof data.path!=='string'||data.path.length>2000)return true;
    if(data.module==='recommendations'&&typeof state!=='undefined'){
      if(state.settingsDraft?._signatureDirty)return true;
      state.boot.profile.signature_file=data.path;if(state.settingsDraft)state.settingsDraft.profile.signature_file=data.path;
    }else if(data.module==='integrity'&&typeof S!=='undefined'){
      if(input.value!==(S.boot.settings?.signature_file||''))return true;
      S.boot.settings.signature_file=data.path;
    }
    input.value=data.path;return true;
  }
  if(settingsContext)document.addEventListener('click',event=>{
    const button=event.target.closest?.('[data-browse-signature]'),script=document.querySelector('script[data-gwhiz-parent]');
    if(!button||button.disabled||!script||!['recommendations','integrity'].includes(script.dataset.gwhizModule)||signatureRequestId)return;
    event.preventDefault();event.stopImmediatePropagation();button.disabled=true;signatureRequestId=crypto.randomUUID();
    const status=document.querySelector('[data-signature-status]');if(status)status.textContent='Choose a local signature PNG…';
    window.parent.postMessage({source:'gspot-desktop-frame',type:'signature-browse',id:signatureRequestId},script.dataset.gwhizParent);
  },true);

  document.addEventListener('keydown',event=>{
    const script=document.querySelector('script[data-gwhiz-parent]');if(!script)return;
    if(event.key==='F11'||event.key==='Escape'){
      if(event.key==='F11')event.preventDefault();
      window.parent.postMessage({source:'gspot-desktop-frame',type:'fullscreen',leave:event.key==='Escape'},script.dataset.gwhizParent);
    }else if(event.altKey&&!event.ctrlKey&&!event.metaKey&&['ArrowLeft','ArrowRight'].includes(event.key)){
      event.preventDefault();event.stopImmediatePropagation();
      window.parent.postMessage({source:'gspot-desktop-frame',type:'navigate',direction:event.key==='ArrowLeft'?-1:1},script.dataset.gwhizParent);
    }else if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='w'){
      event.preventDefault();window.parent.postMessage({source:'gspot-desktop-frame',type:'close'},script.dataset.gwhizParent);
    }
  },true);
  window.addEventListener('message', event => {
    const data=event.data,script=document.querySelector('script[data-gwhiz-parent]');
    if(event.source!==window.parent || !script || event.origin!==script.dataset.gwhizParent || data?.source!=='gspot-desktop' || !/^[a-z0-9-]{1,100}$/i.test(data.id||''))return;
    if(signatureMessage(data))return;
    if(data.type==='settings-save'){
      if(!settingsContext||data.module!==script.dataset.gwhizModule||pendingSave)return;
      const selected={grades:{policy:['[data-action=save-policy]','/api/policy'],assignments:['[data-action=save-instructors]','/api/instructors']},recommendations:{preferences:['[data-action=save-style]','/api/style-guide'],letterhead:['[data-action=save-profile]','/api/profile']},integrity:{letterhead:['form[data-form=settings] button[type=submit]','/api/settings']}}[data.module]?.[data.action];
      pendingSave={id:data.id,path:selected?.[1]||'',timeout:setTimeout(()=>saveResult(false),4000)};
      const button=selected&&document.querySelector(selected[0]);if(!button||button.disabled){saveResult(false);return;}
      button.click();return;
    }
    if(data.type==='refresh-approved'){const suppress=event=>event.stopImmediatePropagation();window.addEventListener('beforeunload',suppress,true);setTimeout(()=>window.removeEventListener('beforeunload',suppress,true),5000);window.parent.postMessage({source:'gspot-desktop-frame',type:'refresh-ready',id:data.id},event.origin);return;}
    if(data.type!=='close-check')return;
    let dirty=false;
    try {const e=new Event('beforeunload',{cancelable:true});window.dispatchEvent(e);dirty=e.defaultPrevented;}catch{}
    try {if(typeof S!=='undefined')dirty ||= !!S.dirty||!!S.reviewDrafts?.size;}catch{}
    try {dirty ||= !!window.GScopeConsistency?.dirty?.();}catch{}
    try {dirty ||= !!window.GScopeMaterials?.dirty?.();}catch{}
    try {if(typeof state!=='undefined')dirty ||= [...(state.studentDrafts?.values()||[]),...(state.letterDrafts?.values()||[])].some(d=>d._dirty)||!!state.settingsDraft?._dirty||!!state.wizard?._dirty;}catch{}
    if(policyBaseline!==null && policyValue()!==null)dirty ||= policyValue()!==policyBaseline;
    if(instructorBaseline!==null && instructorValue()!==null)dirty ||= instructorValue()!==instructorBaseline;
    window.parent.postMessage({source:'gspot-desktop-frame',type:'close-check',id:data.id,dirty:!!dirty},event.origin);
  });
})();
