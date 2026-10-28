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
