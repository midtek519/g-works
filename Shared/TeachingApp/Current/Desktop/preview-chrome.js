/* The preview owns its Keep on top control; the main workspace stays unpinned. */
(() => {
 if(window.GWorksPreviewChrome)return;
 const toolbar=document.querySelector('.viewer-toolbar,.topbar');if(!toolbar)return;
 const button=document.createElement('button');button.type='button';button.textContent='Keep on top';button.id='desktop-preview-pin';button.setAttribute('aria-pressed','false');button.title='Keep this PDF preview above other windows';toolbar.append(button);
 const style=document.createElement('style');style.textContent='.viewer-toolbar{align-items:center}.viewer-toolbar>label{margin:0;align-self:center}.viewer-toolbar>button,.viewer-toolbar>select{min-height:38px;height:38px;margin-top:0;margin-bottom:0;align-self:center}#desktop-preview-pin{margin-left:auto;font:12px/1.4 "Segoe UI",system-ui,sans-serif}#desktop-preview-pin[aria-pressed=true]{background:var(--accent,#2465ab);color:white;border-color:var(--accent,#2465ab)}';document.head.append(style);
 function state(pinned){button.setAttribute('aria-pressed',String(!!pinned));}
 button.addEventListener('click',async()=>{button.disabled=true;try{state(await window.pywebview.api.preview_pin());}catch{button.title='Could not change Keep on top. Try again.';}finally{button.disabled=false;}});
 window.GWorksPreviewChrome={state};
})();
