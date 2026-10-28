(() => {
  const id='rubric-lens-export-host';if(document.getElementById(id))return;
  const host=document.createElement('div');host.id=id;
  host.style.cssText='all:initial;position:fixed;z-index:2147483647;top:16px;right:16px;width:min(560px,calc(100vw - 32px));';
  const root=host.attachShadow({mode:'closed'});
  root.innerHTML=`<style>
  :host{font:14px/1.5 'Segoe UI',sans-serif;color:#20334d;color-scheme:light}*{box-sizing:border-box}section{font:14px/1.5 'Segoe UI',sans-serif;color:#20334d;padding:18px;border:1px solid #cdb9e9;border-radius:12px;background:white;box-shadow:0 8px 38px #1233;max-height:calc(100vh - 32px);overflow:auto}h2{font-size:20px;margin:0 0 8px}h3{font-size:14px;margin:0 0 5px}p{margin:8px 0}.note{font-size:12px;color:#586b85}label{display:block;margin:9px 0 4px}input,select{width:100%;padding:7px;border:1px solid #cdb9e9;border-radius:5px;font:13px/1.5 'Segoe UI',sans-serif;background:white;color:#20334d}button{padding:7px 11px;border:1px solid #cdb9e9;border-radius:5px;background:white;color:#7546b5;font:inherit;cursor:pointer}button:disabled{opacity:.5;cursor:default}.primary{background:#7546b5;color:white;border-color:#7546b5}.close{float:right;padding:0 7px;font-size:20px}.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.error{color:#a24738}[hidden]{display:none!important}.question{padding:10px 0;border-top:1px solid #e0d9ea}.criteria{font-size:12px;padding-left:20px;white-space:pre-wrap}#warnings{font-size:12px;color:#a24738;padding-left:19px}details{margin-top:10px}summary{cursor:pointer;font-size:12px}#rule-controls{padding:9px;background:#f0eafa;border-radius:5px}.actions{position:sticky;top:-18px;z-index:1;background:white;padding:6px 0 12px;border-top:1px solid #e0d9ea;margin-top:12px}#status{font-size:13px;overflow-wrap:anywhere}
  </style><section aria-label="Rubric export"><button id="close" class="close" aria-label="Close rubric export">×</button><h2>Save rubric to G-Scope</h2>
  <p class="note">On Create Rubric, choose Grid View and scroll through every question so its items load. Extract rubric reads the current page and selection settings. Review the preview, then confirm the save. No AI or pairing is used.</p>
  <label for="title">Rubric title</label><input id="title" maxlength="160"><p class="note">Leave blank to use the suggested course - assignment - semester title.</p>
  <div class="actions"><div class="row"><button id="save-library" class="primary">Extract rubric</button><button id="clear">Clear</button></div><p id="status" role="status" aria-live="polite">Ready to extract the current rubric.</p></div>
  <p id="saved-location" class="note">Saved files go to G-Rater/Rubrics inside Chrome’s download folder. In G-Scope, refresh Saved G-Rater exports to pick them up. If you use a custom download location, upload that saved file instead.</p>
  <details id="preview" hidden><summary>Rubric preview</summary><p id="summary" class="note"></p><ul id="warnings" hidden></ul>
  <div id="rule-controls" hidden><p class="note">Some selection settings could not be read. Confirm them below before saving.</p><label>Set unresolved rules<select id="default-rule"><option value="">Choose a rule</option><option value="one">Select one</option><option value="all">Select many</option></select></label></div>
  <div id="review"></div></details></section>`;
  document.documentElement.append(host);
  const $=name=>root.getElementById(name),esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let draft=null,generation=0,busy=false,manualRules=new Map(),previewSignature=null;
  const allowed=location.protocol==='https:'&&['gradescope.com','www.gradescope.com'].includes(location.hostname);
  const fingerprint=(q,g)=>JSON.stringify([q.key,g.description,g.items]);
  function message(text,error=false){$('status').textContent=text;$('status').classList.toggle('error',error);$('status').scrollIntoView?.({block:'nearest'});}
  function update(){$('save-library').disabled=busy||!allowed;$('clear').disabled=busy;$('title').disabled=busy;$('save-library').textContent=busy?'Reading…':previewSignature?'Confirm and save':'Extract rubric';}
  function checkPage(){
    if(!allowed)throw Error('Open Create Rubric directly at gradescope.com, outside Canvas.');
    if(/(?:^|\/)submissions(?:\/|$)/i.test(location.pathname))throw Error('Use Create Rubric. This exporter does not read student grading pages.');
    if(![...document.querySelectorAll('h1,h2,h3')].some(el=>/^Create\s+Rubric$/i.test(el.textContent.trim())))throw Error('Open the assignment’s Create Rubric page first.');
  }
  function review(){
    const errors=draft?RubricLensExport.issues(draft):[];
    $('warnings').hidden=!errors.length;$('warnings').innerHTML=errors.map(e=>'<li>'+esc(e)+'</li>').join('');
    $('rule-controls').hidden=!draft?.questions.some(q=>q.groups.some(g=>g.selectionMode==='unknown'));
    $('preview').hidden=!draft;$('preview').open=!!draft;
    if(!draft){$('summary').textContent='';$('review').innerHTML='';return;}
    const count=draft.questions.reduce((n,q)=>n+q.groups.reduce((s,g)=>s+g.items.length,0),0);
    $('summary').textContent=draft.questions.length+' graded parts · '+count+' rubric items · '+draft.questions.reduce((n,q)=>n+(q.maxPoints||0),0)+' points';
    $('review').innerHTML=draft.questions.map((q,qi)=>'<div class="question"><h3>'+esc(q.key)+' · '+esc(q.title)+' · '+esc(q.maxPoints??'?')+' points</h3>'+q.groups.map((g,gi)=>'<label>Group '+(gi+1)+' selection rule<select data-question="'+qi+'" data-group="'+gi+'">'+[['unknown','Confirm rule…'],['one','Select one'],['all','Select many']].map(([v,t])=>'<option value="'+v+'" '+(v===g.selectionMode?'selected':'')+'>'+t+'</option>').join('')+'</select></label><p class="note">'+esc(g.description)+'</p><ul class="criteria">'+g.items.map(i=>'<li>'+esc(i.points??'?')+' points · '+esc(i.description)+'</li>').join('')+'</ul>').join('')+'</div>').join('');
  }
  function suggest(){const value=RubricLensExport.suggestedTitle(document);$('title').placeholder=value||'Course - Assignment - Semester';return value;}
  function clear(){generation++;draft=null;previewSignature=null;manualRules.clear();$('title').value='';$('default-rule').value='';review();suggest();update();message('Cleared. Extract rubric will read the current page again.');}
  $('clear').onclick=clear;$('close').onclick=()=>{generation++;host.remove();};
  $('review').onchange=event=>{const el=event.target,q=draft?.questions[Number(el.dataset.question)],g=q?.groups[Number(el.dataset.group)];if(!g||!['one','all'].includes(el.value))return;manualRules.set(fingerprint(q,g),el.value);g.selectionMode=el.value;previewSignature=JSON.stringify([location.pathname,draft]);review();update();};
  $('default-rule').onchange=()=>{const value=$('default-rule').value;if(!draft||!['one','all'].includes(value))return;for(const q of draft.questions)for(const g of q.groups)if(g.selectionMode==='unknown'){manualRules.set(fingerprint(q,g),value);g.selectionMode=value;}previewSignature=JSON.stringify([location.pathname,draft]);review();update();};
  $('save-library').onclick=async()=>{
    if(busy)return;const currentGeneration=generation,path=location.pathname,reviewed=previewSignature;busy=true;update();
    try{
      checkPage();const editors=[...document.querySelectorAll('.rubricEditor')];if(editors.length!==1)throw Error('Could not isolate the rubric editor. Use Grid View on Create Rubric.');
      const section=editors[0],guard=()=>{checkPage();if(currentGeneration!==generation||path!==location.pathname||document.querySelectorAll('.rubricEditor').length!==1||document.querySelectorAll('.rubricEditor')[0]!==section)throw Error('The page changed. Extract the rubric again.');};
      message('Reading the current rubric…');
      const value=await RubricLensExport.readWithSettings(section,guard,(i,n)=>message('Reading selection settings: '+i+' of '+n+'…'));
      guard();draft=value;
      for(const q of draft.questions)for(const g of q.groups)if(g.selectionMode==='unknown'&&manualRules.has(fingerprint(q,g)))g.selectionMode=manualRules.get(fingerprint(q,g));
      review();const issues=RubricLensExport.issues(draft);if(issues.length){previewSignature=null;throw Error('Not saved. '+issues[0]);}
      const title=$('title').value.trim()||suggest();if(!title)throw Error('Enter a rubric title; the page does not expose a complete course, assignment and semester.');
      const signature=JSON.stringify([path,draft]);
      if(!reviewed||reviewed!==signature){
        previewSignature=signature;
        message(reviewed?'The rubric changed. Review the updated preview below, then Confirm and save. Nothing has been saved yet.':'Review the rubric preview below, then click Confirm and save. Nothing has been saved yet.');
        $('preview').scrollIntoView?.({block:'nearest'});return;
      }
      const rubric=RubricLensExport.exportData(draft,title);guard();$('save-library').textContent='Saving…';message('Saving locally for G-Scope…');
      const result=await chrome.runtime.sendMessage({app:'rubric-lens',type:'rubric-save',rubric});
      if(!result?.ok||result.saved!==true)throw Error(result?.error||'Chrome did not confirm the rubric save.');
      if(currentGeneration===generation){previewSignature=null;message('Saved “'+result.rubric.title+'”. In G-Scope → Rubrics → Saved G-Rater export, click Refresh.');}
    }catch(e){if(currentGeneration===generation)message(e.message,true);}finally{busy=false;update();}
  };
  try{checkPage();suggest();}catch(e){message(e.message,true);}update();
})();
