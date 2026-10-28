/* Runs inside each private module, never in the parent navigation bridge. */
(() => {
  'use strict';
  window.LocalDrafting={open};
  async function open(options){
    const endpoint=options.endpoint==='/api/local-rationale'?options.endpoint:'/api/local-ai';
    const dialog=document.createElement('dialog');dialog.className='local-ai-dialog';
    dialog.innerHTML=`<div class="local-ai-wrap"><h2></h2><p class="local-ai-intro"></p><p class="local-ai-status" role="status">Opening the approved brief…</p><label class="local-ai-model-label">Installed local model<select class="local-ai-model"></select></label><label>Approved brief / redacted prompt<textarea class="local-ai-brief" rows="11"></textarea></label><label class="local-ai-draft-label" hidden>Editable draft<textarea class="local-ai-draft" rows="14"></textarea></label><div class="local-ai-actions"><button class="local-ai-close">Close</button><button class="local-ai-copy" hidden>Copy redacted prompt</button><a class="local-ai-copilot" hidden href="https://copilot.cloud.microsoft/?auth=2" target="_blank" rel="noopener noreferrer">Open Rutgers Copilot ↗</a><button class="local-ai-generate primary">Draft with local Ollama</button><button class="local-ai-use primary" hidden>Use draft</button></div></div>`;
    document.body.append(dialog);dialog.showModal();
    const $=selector=>dialog.querySelector('.local-ai-'+selector);let job=null,closed=false,poll=null,draftUnsaved=false;
    const unload=event=>{if(draftUnsaved){event.preventDefault();event.returnValue='';}};
    window.addEventListener('beforeunload',unload);
    const online=options.mode==='online',general=options.mode==='general'&&endpoint==='/api/local-ai';let connection=null;
    $('wrap').querySelector('h2').textContent=online?'Reviewed online handoff':general?'Draft with General AI':'Draft with Private AI';
    $('intro').textContent=options.intro||(online?'Review this redacted prompt before copying it. Attachments are excluded. You choose the approved online service and send it yourself.':general?'Only the approved redacted text brief goes to your General AI connection. Review indirect identifying details first. Attachments and original records are excluded.':'Only the reviewed input goes to the model running on this computer. The result remains an editable draft for your review.');
    if(general)$('generate').textContent='Draft with General AI';
    if(options.copyOnly)$('use').textContent='Copy draft';
    $('draft').addEventListener('input',()=>{draftUnsaved=true;});
    $('model-label').hidden=online||general;$('generate').hidden=online;$('copy').hidden=!online;$('copilot').hidden=!online;
    const status=text=>{$('status').textContent=text;};
    async function api(path,body){
      const response=await fetch(endpoint+path,{method:body===undefined?'GET':'POST',headers:{'X-App-Token':options.token,...(body===undefined?{}:{'Content-Type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)}),credentials:'same-origin',redirect:'error',cache:'no-store'});
      const result=await response.json();if(!response.ok)throw new Error(result.error||'The local drafting action could not finish.');return result;
    }
    function close(){closed=true;window.removeEventListener('beforeunload',unload);clearTimeout(poll);if(job)api('/jobs/'+job+'/cancel',{}).catch(()=>{});dialog.close();dialog.remove();}
    $('close').onclick=close;dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
    $('copy').onclick=async()=>{try{await navigator.clipboard.writeText($('brief').value);status('Reviewed prompt copied. Nothing was uploaded or sent.');}catch{status('Select the prompt and press Ctrl+C to copy it.');}};
    async function check(){
      try{
        const result=await api('/jobs/'+job);
        if(closed)return;
        if(result.status==='done'){
          $('draft-label').hidden=false;$('draft').value=result.result.body;$('use').hidden=false;$('generate').disabled=false;
          draftUnsaved=true;
          status(options.copyOnly?'Draft ready. Verify the evidence observations and wording, then copy the draft for review. No finding or sanction has changed.':'Draft ready. Review its facts and wording, edit it here, then choose Use draft. It has not been signed or sent.');return;
        }
        if(result.status==='error' || result.status==='cancelled'){status(result.error||'Draft request cancelled.');$('generate').disabled=false;return;}
        status(result.progress||(result.status==='queued'?'Waiting for the model…':general?'General AI is drafting. You may close this window to discard the request.':'Private AI is drafting on this computer. You may close this window to discard the request.'));poll=setTimeout(check,1000);
      }catch(error){if(!closed){status(error.message);$('generate').disabled=false;}}
    }
    $('generate').onclick=async()=>{
      try{
        if(job)await api('/jobs/'+job+'/cancel',{});
        $('generate').disabled=true;$('use').hidden=true;$('draft-label').hidden=true;status(general?'Starting General AI…':'Starting Private AI…');
        const result=await api('/jobs',{brief:options.brief,target:options.target,...(general?{connection:'general'}:{model:$('model').value})});job=result.id;if(!closed)check();
      }catch(error){if(!closed){status(error.message);$('generate').disabled=false;}}
    };
    $('use').onclick=async()=>{
      try{
        if(options.copyOnly){await navigator.clipboard.writeText($('draft').value);draftUnsaved=false;status('Draft copied. Review it before pasting into a communication. No finding, sanction, signature or sending status changed.');return;}
        $('use').disabled=true;await api('/apply',{jobId:job,body:$('draft').value,useDraft:true});job=null;draftUnsaved=false;
        close();if(options.onApplied)await options.onApplied();
      }catch(error){if(!closed){status(error.message);$('use').disabled=false;}}
    };
    try{
      const brief=await api('/brief',{brief:options.brief,target:options.target});if(closed)return;
      $('brief').value=brief.text;$('brief').readOnly=!online;
      if(general){connection=await api('/connection');if(connection.provider==='chatgpt'&&(!connection.connected||!connection.model))throw new Error('Connect ChatGPT and choose a General AI model in Settings → AI.');}
      else if(!online){const result=await api('/models');if(closed)return;for(const model of result.models){const option=document.createElement('option');option.value=model.name;option.textContent=model.name;$('model').append(option);}const preferred='rubric-lens-qwen35:27b-20261022';if([...$('model').options].some(o=>o.value===preferred))$('model').value=preferred;if(!$('model').value)throw new Error('No installed local model is available. Open AI settings and check the private connection.');}
      status(online?'Review identities and indirect identifying details before copying. The current redacted export remains available.':general?connection.label+' · '+connection.model+'. Approved brief verified.':'Approved input verified. Choose Draft with Private AI to begin.');
    }catch(error){if(!closed){status(error.message);$('generate').disabled=true;$('copy').disabled=true;}}
  }
})();
