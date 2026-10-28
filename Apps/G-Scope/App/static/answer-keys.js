/* Blank-exam answer proposals. Drafts are never grading guidance until explicitly reviewed. */
window.GScopeAnswerKeys=(()=>{
  let C,epoch=0,job=null;const polls=new Set();
  const K={vid:null,data:null,loading:false,error:'',request:0,mode:'solve',scope:'current',useSolutions:true,selected:null,selectionTouched:false,edits:new Map(),saving:new Set(),discarding:new Set(),starting:false,notice:null};
  const dirty=()=>[...K.edits.values()].some(e=>e.text!==e.baseline);
  const discard=()=>{K.edits.clear();};
  function reset(){const vid=C.S.version?.id;if(K.vid===vid)return;epoch++;Object.assign(K,{vid,data:null,loading:false,error:'',notice:null,selected:null,selectionTouched:false});discard();K.saving.clear();}
  const same=(vid,e)=>K.vid===vid&&C.S.version?.id===vid&&epoch===e;
  const repaint=()=>{if(C.S.view==='projects'&&C.S.tab==='rubric'){if(C.S.dirty)C.collectQuestions?.();C.render();}};
  const savedSolution=q=>!!q?.guidance?.match(/\[G-Scope reviewed solution; version [A-Z]\]\n[\s\S]*?\n\[\/G-Scope reviewed solution\]/);
  const displayNumber=key=>C.S.version?.rubricOutline?.find(n=>n.graded&&n.key===key)?.number||key;
  const btn=(text,action,extra='',primary=false)=>C.button(text,'answer-'+action,extra,primary);
  function missingKey(q){const item=K.data?.items?.find(i=>i.questionKey===q.key);return item?!item.current:!savedSolution(q);}
  function selectedKeys(){reset();if(!K.selected)K.selected=new Set((C.S.version?.questions||[]).map(q=>q.key));return (C.S.version?.questions||[]).filter(q=>K.selected.has(q.key)).map(q=>q.key);}
  function selectionView({manual=false}={}){
    if(!C?.S.version)return '';reset();const e=C.esc,v=C.S.version,selected=new Set(selectedKeys()),busy=K.starting||job||K.saving.size||K.discarding.size;
    return `<section class="card answer-key-selection"><div class="spread"><h2>Choose questions for answer keys</h2><span class="help">${selected.size} selected · Version ${e(v.label)}</span></div>${!v.questions.length?'<p>Create an outline in Exam outline first. Copy outline saves each destination automatically.</p>':`<div class="row">${btn('Select missing','select-missing',busy?'disabled':'')}${btn('Select all','select-all',busy?'disabled':'')}${btn('Clear selection','select-none',busy?'disabled':'')}${manual?'':`<label>Draft for<select data-answer-field="scope" ${busy?'disabled':''}>${C.option('current','This version ('+v.label+')',K.scope)}${C.option('all','All assignment versions',K.scope)}</select></label>`}</div><div class="answer-key-question-options">${v.questions.map(q=>{const item=K.data?.items?.find(i=>i.questionKey===q.key),status=item&&!item.current?'Changed since draft':item?.status==='draft'?'Draft saved':savedSolution(q)?'Key saved':'Missing key';return `<label class="answer-key-question-option"><input type="checkbox" data-answer-question-select="${e(q.key)}" ${selected.has(q.key)?'checked':''} ${busy?'disabled':''}><span>Question ${e(displayNumber(q.key))}<small>${status}</small></span></label>`;}).join('')}</div><p class="help">${!manual&&K.scope==='all'?'Selected question numbers will be drafted in every assignment version. Status and Select missing refer to Version '+e(v.label)+'. ':''}A new draft replaces the selected question’s previous draft. Saving a reviewed answer key replaces its saved key. Unselected questions stay unchanged.</p>${C.S.dirty?'<p class="notice warning">Save your outline or rubric edits before drafting. Copied outlines are already saved in each destination version.</p>':''}`}</section>`;
  }
  function uncertaintyView(item){
    const text=String(item.uncertainty||'').trim(),match=text.match(/^(none|low|medium|high)\b/i),level=match?match[1].toLowerCase():'unknown',label=level==='unknown'?'Unknown / not provided':level[0].toUpperCase()+level.slice(1),detail=match?text.slice(match[0].length).replace(/^[\s:.;-]+/,''):text;
    return `<p class="answer-uncertainty uncertainty-${level}"><strong>Model uncertainty: ${label}</strong>${detail?' · '+C.esc(detail):''}<small>Model-reported; review the answer key.</small></p>`;
  }
  function report(message,warnings=[]){
    const unique=[...new Set(warnings.map(w=>String(w).replace(/Version ([A-Z]), question [^:]+: draft not saved\. /,'Version $1: ')))];
    K.notice={message,warnings:unique};C.message(message);repaint();
  }
  function reportView(){if(!K.notice)return '';const e=C.esc;return '<section class="answer-draft-report" role="status"><p>'+e(K.notice.message)+'</p>'+(K.notice.warnings.length?'<details><summary>Details ('+K.notice.warnings.length+')</summary><ul>'+K.notice.warnings.map(w=>'<li>'+e(w)+'</li>').join('')+'</ul></details>':'')+'</section>';}
  function view({mode='solve'}={}){
    K.mode=mode;
    if(!C?.S.version)return '';reset();const e=C.esc,v=C.S.version,items=(K.data?.items||[]).filter(i=>selectedKeys().includes(i.questionKey)),drafts=items.filter(i=>i.status==='draft'),replacements=drafts.filter(i=>savedSolution(v.questions.find(q=>q.key===i.questionKey))).length;
    return `<section class="card answer-key-panel"><h2>${K.mode==='tex'?'Draft from TeX solutions':'Generate answer-key drafts'}</h2>${reportView()}<p class="help">${K.mode==='tex'?'Uses this version’s linked TeX when available. Otherwise, AI adapts Version A’s solution to the actual target-version question.':'Solves the actual blank questions without linked solutions.'} Review every draft before use. No student scans are used.</p>
    <p class="help">${e(C.S.boot?.generalAI?.label||'General AI · configured in Settings → AI')}${C.S.boot?.generalAI?.model?' · '+e(C.S.boot.generalAI.model):''}</p>
    <div class="row">${btn(K.starting?'Starting…':K.scope==='all'?'Draft selected keys · all versions':'Draft selected answer keys','generate',!selectedKeys().length||K.starting||job||K.discarding.size||K.saving.size||(K.mode==='tex'&&K.data?.texSolutions&&(K.scope==='all'?!K.data.texSolutions.anyAvailable:!K.data.texSolutions.currentAvailable))?'disabled':'',true)}${K.data?.canUseAllDrafts?btn('Save selected reviewed keys','approve-all',`title="Save the selected reviewed answer-key drafts in this version" ${!drafts.length||drafts.some(i=>!i.current)||job||K.starting||K.discarding.size||K.saving.size?'disabled':''}`,true):''}${btn('Refresh drafts','refresh','title="Reload saved drafts without generating new solutions"')}${K.data?.canDiscardDrafts?btn('Discard selected drafts','discard-all',job||K.starting||K.discarding.size||K.saving.size||!items.some(i=>i.status==='draft')?'disabled':''):''}${job?btn(job.stopping?'Stopping…':K.data?.canStopImmediately?'Stop now':'Stop after current question','cancel',job.stopping?'disabled':''):''}</div><p id="answer-key-progress" class="help">${e(job?.message||K.error||(K.loading?'Loading saved answer drafts…':''))}</p>
    <p class="help">Review each draft, then save the answer key for grading. Exact-version TeX can be used directly; questions needing an image require their outline boxes.</p>${replacements?`<p class="notice warning">Saving selected drafts will replace ${replacements} saved answer key${replacements===1?'':'s'} in Version ${e(v.label)}.</p>`:''}
    ${items.map(item=>{const edit=K.edits.get(item.id),text=edit?.text??item.text,q=v.questions.find(q=>q.key===item.questionKey),stale=!item.current;return `<article class="answer-key-draft"><details class="answer-key-solution" ${item.status!=='approved'||edit?.text!==undefined&&edit.text!==item.text?'open':''}><summary><h3>Question ${e(displayNumber(item.questionKey))} · Version ${e(v.label)} · ${item.status==='approved'?'Reviewed answer key':'Unapproved answer-key draft'}</h3></summary>${stale?'<p class="notice warning">The question or linked sources changed. Generate a fresh draft before applying this answer.</p>':''}${q?.id&&q.rect?`<details><summary>Show blank question</summary><img class="answer-key-crop" src="/api/questions/${encodeURIComponent(q.id)}/template-crop" loading="lazy" alt="Blank question ${e(item.questionKey)}"></details>`:''}${savedSolution(q)?`<p class="notice warning">Saving will replace the saved answer key for Question ${e(displayNumber(item.questionKey))} on Version ${e(v.label)}.</p>`:''}<label for="answer-tex-${e(item.id)}">Solution (TeX)</label><p class="help" id="answer-help-${e(item.id)}">Omit <code>\\documentclass</code> and the <code>document</code> environment. <code>\\begin{solution}…\\end{solution}</code> is optional.</p><div class="gs-solution-layout"><div class="gs-solution-source"><textarea id="answer-tex-${e(item.id)}" data-gscope-tex aria-describedby="answer-help-${e(item.id)}" data-answer-question="${e(item.questionKey)}" rows="6" maxlength="8000" data-answer-input="${e(item.id)}" ${K.discarding.has(item.id)?'disabled':''}>${e(text)}</textarea></div><section class="gs-solution-preview" aria-label="Solution preview"><h4>Preview</h4><div data-solution-preview></div><p class="help" data-solution-preview-status role="status"></p></section></div>${uncertaintyView(item)}<p class="help">${item.linkedExcerptUsed?'Draft used a matching-version linked solution excerpt.':'Draft solved the blank question without a linked excerpt.'}</p>${btn(savedSolution(q)?'Replace saved answer key':'Save reviewed answer key','approve',`data-id="${e(item.id)}" ${stale||K.saving.size||K.discarding.size?'disabled':''}`,true)}${item.status==='draft'&&K.data?.canDiscardDrafts?btn('Discard draft','discard',`data-id="${e(item.id)}" ${job||K.starting||K.discarding.size||K.saving.size?'disabled':''}`):''}</details></article>`;}).join('')||(!K.loading?'<p>No saved answer-key drafts for the selected questions.</p>':'')}</section>`;
  }
  async function load(){
    reset();const vid=K.vid,e=epoch,request=++K.request;K.loading=true;K.error='';
    try{const data=await C.api('/api/versions/'+vid+'/answer-keys');if(same(vid,e)&&request===K.request){K.data=data;if(!K.selectionTouched)K.selected=new Set((C.S.version.questions||[]).map(q=>q.key));if(data.activeJob){job={id:data.activeJob.id,projectId:C.S.version.project_id,message:data.activeJob.stopping?'Stopping…':data.activeJob.progress?.message,stopping:!!data.activeJob.stopping};watch(job);}}}
    catch(error){if(same(vid,e)&&request===K.request)K.error=error.message;}
    finally{if(same(vid,e)&&request===K.request){K.loading=false;repaint();}}
  }
  async function mount(){if(!C?.S.version||C.S.tab!=='rubric')return;reset();if(!K.data&&!K.loading&&!K.error)await load();}
  function input(el){const id=el.dataset.answerInput;if(!id)return false;const item=K.data?.items.find(i=>i.id===id);if(!item)return true;K.edits.set(id,{text:el.value,baseline:item.text});const button=document.querySelector(`[data-action="answer-approve"][data-id="${id}"]`);if(button)button.disabled=!item.current||K.saving.has(id);return true;}
  async function change(el){
    const key=el.dataset.answerQuestionSelect;if(key!==undefined){if(!C.S.version.questions.some(q=>q.key===key))return true;selectedKeys();K.selectionTouched=true;if(el.checked)K.selected.add(key);else K.selected.delete(key);repaint();return true;}
    const field=el.dataset.answerField;if(!field)return false;
    if(field==='scope'){if(['current','all'].includes(el.value))K.scope=el.value;}repaint();return true;
  }
  function watch(value){if(polls.has(value.id))return;polls.add(value.id);poll(value);}
  async function poll(value){
    try{const state=await C.api('/api/jobs/'+value.id);if(['queued','running'].includes(state.status)||state.stopping){value.message=value.stopping||state.stopping?'Stopping…':state.progress?.message||'Drafting answers with General AI…';if(state.stopping)value.stopping=true;const node=document.querySelector('#answer-key-progress');if(node&&C.S.version?.project_id===value.projectId)node.textContent=value.message;setTimeout(()=>poll(value),1400);return;}
      polls.delete(value.id);if(job?.id===value.id)job=null;
      if(C.S.version?.project_id===value.projectId){K.data=null;await load();}
      const result=state.result;report(state.status==='done'?(result.created?'Drafted '+result.created+' answer keys. Review each before use.':'No answer keys were drafted. See details below.'):state.error||'Answer-key drafting stopped. Completed drafts were kept.',result?.warnings||[]);repaint();
    }catch(error){polls.delete(value.id);if(job?.id===value.id)job=null;C.message(error.message);repaint();}
  }
  async function action(el){
    const name=el.dataset.action||'';if(!name.startsWith('answer-'))return false;reset();
    if(['answer-select-missing','answer-select-all','answer-select-none'].includes(name)){K.selectionTouched=true;K.selected=new Set(name==='answer-select-none'?[]:C.S.version.questions.filter(q=>name==='answer-select-all'||missingKey(q)).map(q=>q.key));repaint();return true;}
    if(name==='answer-refresh'){await load();return true;}
    if(name==='answer-cancel'){
      if(!job||job.stopping)return true;const value=job,immediate=!!K.data?.canStopImmediately;value.stopping=true;value.message='Stopping…';repaint();
      try{await C.api('/api/jobs/'+value.id+'/cancel',immediate?{immediate:true}:{});C.message(immediate?'Stopping now. The unfinished solution is discarded; completed drafts are kept.':'Stopping after the current local request. Completed answer drafts are kept.');}
      catch(error){value.stopping=false;value.message='';throw error;}finally{repaint();}return true;
    }
    if(name==='answer-discard'||name==='answer-discard-all'){
      if(!K.data?.canDiscardDrafts)return true;if(job||K.starting)throw Error('Stop drafting before discarding saved drafts.');if(K.discarding.size||K.saving.size)return true;
      const items=(K.data?.items||[]).filter(i=>i.status==='draft'&&(name==='answer-discard-all'?selectedKeys().includes(i.questionKey):i.id===el.dataset.id));if(!items.length)return true;
      const ids=items.map(i=>i.id),vid=K.vid,e=epoch;ids.forEach(id=>K.discarding.add(id));K.request++;K.loading=false;repaint();
      try{const result=await C.api('/api/versions/'+vid+'/answer-keys/discard',{draftIds:ids});if(same(vid,e)){K.request++;K.loading=false;K.data=result.answerKeys;ids.forEach(id=>K.edits.delete(id));}C.message(result.discarded+' unapproved draft'+(result.discarded===1?'':'s')+' discarded. Reviewed solutions were kept.');}
      finally{ids.forEach(id=>K.discarding.delete(id));if(same(vid,e))repaint();}return true;
    }
    if(name==='answer-generate'){
      if(K.starting||job||K.discarding.size||K.saving.size)return true;if(C.S.dirty)throw Error('Save your question and rubric edits before drafting answer keys.');if(dirty())throw Error('Apply or discard your edited answer text before redrafting.');
      const keys=selectedKeys();if(!keys.length)throw Error('Select the questions that need answer keys first.');const vid=K.vid,e=epoch;K.starting=true;repaint();
      try{const result=await C.api('/api/versions/'+vid+'/answer-keys/draft',{scope:K.scope,useLinkedSolutions:K.mode==='tex',adaptFromA:K.mode==='tex',skipExisting:false,questionKeys:keys});if(result.generalAI)C.S.boot.generalAI=result.generalAI;if(result.noWork){report(result.message,result.warnings||[]);return true;}job={id:result.id,projectId:result.projectId,message:'Drafting '+result.questions+' question answers…'};watch(job);if(result.warnings?.length)report('Some selected answer keys could not be drafted. See details below.',result.warnings);}
      finally{K.starting=false;if(same(vid,e))repaint();}return true;
    }
    if(name==='answer-approve-all'){
      if(!K.data?.canUseAllDrafts||K.saving.size||K.discarding.size)return true;if(job||K.starting)throw Error('Stop drafting before using all drafts.');if(C.S.dirty)throw Error('Save your question and rubric edits before applying solutions.');
      const items=(K.data.items||[]).filter(i=>i.status==='draft'&&selectedKeys().includes(i.questionKey));if(!items.length)return true;if(items.some(i=>!i.current))throw Error('Regenerate stale drafts before using all drafts.');
      const vid=K.vid,e=epoch,drafts=items.map(i=>({id:i.id,text:K.edits.get(i.id)?.text??i.text}));drafts.forEach(i=>K.saving.add(i.id));repaint();
      try{const result=await C.api('/api/versions/'+vid+'/answer-keys/approve-all',{reviewed:true,drafts});if(same(vid,e)){K.request++;K.loading=false;K.data=result.answerKeys;for(const draft of drafts)if(K.edits.get(draft.id)?.text===draft.text)K.edits.delete(draft.id);C.S.version=result.version;if(!C.S.dirty)C.S.questions=structuredClone(result.version.questions);C.S.consistencyReport=null;window.GScopeMaterials?.refreshAnswers?.();}C.message(result.approved+' reviewed solutions saved for this version.');}
      finally{drafts.forEach(i=>K.saving.delete(i.id));if(same(vid,e))repaint();}return true;
    }
    if(name==='answer-approve'){
      if(C.S.dirty)throw Error('Save your question and rubric edits before applying an answer.');const item=K.data?.items.find(i=>i.id===el.dataset.id);if(!item||!item.current)throw Error('Choose a current answer draft.');if(!selectedKeys().includes(item.questionKey))throw Error('Select this question before saving its answer key.');if(K.saving.size||K.discarding.size)return true;
      const vid=K.vid,e=epoch,text=K.edits.get(item.id)?.text??item.text;K.saving.add(item.id);repaint();
      try{const result=await C.api('/api/versions/'+vid+'/answer-keys/'+item.id+'/approve',{reviewed:true,text});if(same(vid,e)){K.request++;K.loading=false;K.data=result.answerKeys;if((K.edits.get(item.id)?.text??item.text)===text)K.edits.delete(item.id);C.S.version=result.version;if(!C.S.dirty)C.S.questions=structuredClone(result.version.questions);C.S.consistencyReport=null;window.GScopeMaterials?.refreshAnswers?.();}C.message('Reviewed answer saved for this question and version. Confirm the complete rubric again if prompted before grading.');}
      finally{K.saving.delete(item.id);if(same(vid,e))repaint();}return true;
    }
    return true;
  }
  return {init:context=>C=context,availability:()=>K.data?.texSolutions,selectionView,selectedKeys,selectQuestion:key=>{selectedKeys();K.selected.add(key);K.selectionTouched=true;},view,mount,input,change,action,dirty,discard,invalidate:()=>{K.data=null;K.error='';}};
})();
