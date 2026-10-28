/* Approved common-mistake decisions. All requests stay on the local module. */
(() => {
  'use strict';
  let C;
  const D = {versionId:null,data:null,loading:false,error:'',questionKey:'',draft:null,baseline:'',approved:false,busy:false,history:[],pending:null,request:0};
  const drafts=new Map(),versions=new Map();
  const key=()=>D.versionId+'|'+D.questionKey;
  const blank = () => ({applyToAll:true,scoreMode:'cap',condition:'',reason:'',items:[],message:'',ruleId:null,expectedRevision:null,source:'manual'});
  const encode = value => JSON.stringify(value);
  const dirty = () => (!!D.draft&&encode(D.draft)!==D.baseline)||[...drafts].some(([k,v])=>k!==key()&&encode(v.draft)!==v.baseline);
  const question = () => D.data?.questions.find(q=>q.key===D.questionKey);
  function resetDraft(value=blank()) {D.draft=value;D.baseline=encode(value);D.approved=false;}
  function stash(){
    if(D.versionId&&D.draft)drafts.set(key(),{draft:structuredClone(D.draft),baseline:D.baseline,history:structuredClone(D.history),pending:D.pending,busy:D.busy,request:D.request});
    if(D.versionId)versions.set(D.versionId,{data:D.data,questionKey:D.questionKey});
  }
  function restore(){
    const saved=drafts.get(key());
    if(saved){D.draft=structuredClone(saved.draft);D.baseline=saved.baseline;D.history=structuredClone(saved.history);D.pending=saved.pending;D.busy=saved.busy;D.request=saved.request;}
    else{resetDraft();D.history=[];D.pending=null;D.busy=false;D.request++;}
  }
  function resetVersion(id){
    if(D.versionId===id)return;stash();const prior=versions.get(id);
    Object.assign(D,{versionId:id,data:prior?.data||null,loading:false,error:'',questionKey:prior?.questionKey||'',busy:false,history:[],pending:null,request:D.request+1});restore();
  }
  const math=text=>window.GScopeSolutionPreview?.render?.(text).html||C.esc(text);
  function field(name,label,limit,rows){
    const id='guidance-'+D.versionId+'-'+D.questionKey+'-'+name;
    return `<div class="gs-solution-layout gs-guidance-editor"><label for="${C.esc(id)}">${label}<textarea id="${C.esc(id)}" data-gscope-tex data-consistency-field="${name}" maxlength="${limit}" rows="${rows}" aria-label="${label}">${C.esc(D.draft[name])}</textarea></label><div class="gs-guidance-preview"><small class="help">Math preview</small><div data-solution-preview></div></div></div>`;
  }
  function repaint() {if(C.S.version?.id===D.versionId&&C.S.tab==='decisions')C.render();}
  const btn=(text,action,extra='',primary=false)=>C.button(text,'consistency-'+action,extra,primary);
  const selectedText=(q,ids)=>q.items.filter(i=>ids.includes(i.id)).map(i=>`${i.label} (${i.points>0?'+':''}${i.points})`).join(' / ');
  function invalidateCachedLists(){for(const saved of versions.values())saved.data=null;}
  function invalidateRun() {
    C.S.consistencyReport=null;
    const project=C.S.projects?.find(p=>p.id===D.data?.projectId);
    if(C.S.run&&project?.versions.some(v=>v.id===C.S.run.version_id))C.S.run.current=false;
  }
  function ruleCard(q,rule) {
    const e=C.esc;
    return `<div class="scan-row"><div class="spread"><strong>${e(selectedText(q,rule.items))}</strong><span class="pill">${rule.active?'Approved':'Inactive'} · ${rule.scoreMode==='cap'?'Score cap':'Exact score'} · ${rule.applyToAll?'All compatible versions':'This version'} · revision ${rule.revision}</span></div><p>${math(rule.condition)}</p><p class="help">${math(rule.reason)}</p><div class="row">${btn(rule.active?'Edit decision':'Revise and reactivate','edit',`data-rule="${e(rule.id)}"`)}${rule.active?btn('Deactivate','deactivate',`data-rule="${e(rule.id)}"`):''}</div><details><summary class="help">Revision history</summary>${rule.history.map(h=>`<p class="help"><strong>Revision ${h.revision}${h.active?'':' · inactive'}</strong> · ${e(selectedText(q,h.items))}<br>${math(h.condition)}<br>${math(h.reason)}</p>`).join('')}</details></div>`;
  }
  function view() {
    if(!C?.S.version)return '';
    resetVersion(C.S.version.id);
    const e=C.esc,q=question();
    if(!D.data)return `<section class="card" id="consistency-panel"><h2>Grading guidance · Optional</h2><p>${D.error?e(D.error):'Loading approved decisions…'}</p>${D.error?btn('Retry','refresh'):''}</section>`;
    if(!D.data.questions.length)return '<section class="card"><h2>Grading guidance · Optional</h2><p>Save question cards in the Rubric tab first.</p></section>';
    if(!q){D.questionKey=D.data.questions[0].key;restore();return view();}
    const d=D.draft;
    return `<div id="consistency-panel"><section class="card"><h2>Grading guidance · Optional</h2><p class="help">Save a reviewed decision for this question. Choose a score cap when other mistakes may also reduce credit.</p><div class="row"><div class="gs-guidance-questions" role="group" aria-label="Guidance question">${D.data.questions.map(x=>btn('Question '+e(x.key),'question',`data-key="${e(x.key)}" aria-pressed="${x.key===D.questionKey}"`)).join('')}</div>${btn('Refresh decisions','refresh')}</div></section>
    <div class="grid"><section class="card"><h2>Discuss a common mistake</h2><p class="help">Describe the mathematical pattern without student names. The local model proposes a decision using this question’s existing rubric.</p>${D.history.map(h=>`<div class="notice ${h.role==='user'?'':'warning'}"><strong>${h.role==='user'?'You':'Local model'}</strong><p style="white-space:pre-wrap">${math(h.text)}</p></div>`).join('')}${field('message','Mathematical question or follow-up',4000,4)}<label>Installed local model<select data-consistency-model>${C.modelOptions()}</select></label>${btn(D.busy?'Thinking locally…':'Discuss with local model','discuss',D.busy?'disabled':'',true)}${D.pending?`<div class="notice"><strong>Editable proposal ready</strong><p>${math(D.pending.draft.condition)}</p><p><strong>${D.pending.draft.scoreMode==='cap'?'Maximum score':'Exact score'}</strong>: ${e(selectedText(q,D.pending.draft.items))}</p><p>${math(D.pending.draft.reason)}</p>${D.pending.draft.caution?`<p class="help">${e(D.pending.draft.caution)}</p>`:''}${btn('Load proposed decision','load-proposal')}</div>`:''}</section>
    <section class="card"><h2>${d.ruleId?'Revise approved decision':'Approve a reusable decision'}</h2>${field('condition','Apply when this condition is visible',800,5)}<p class="help">Include exceptions or required supporting work in the condition. Maximum 800 characters.</p><p><strong>Use ${q.selectionMode==='one'?'one rubric item':'the applicable combination'}:</strong></p>${q.items.map(i=>`<label class="check"><input type="${q.selectionMode==='one'?'radio':'checkbox'}" name="consistency-choice" data-consistency-choice="${e(i.id)}" ${d.items.includes(i.id)?'checked':''}><span><strong>${e(i.label)} · ${i.points>0?'+':''}${e(i.points)}</strong> ${math(i.description)}</span></label>`).join('')}${field('reason','Short reason',320,3)}<label>Scoring behavior<select data-consistency-field="scoreMode">${C.option('cap','Maximum score - other errors may lower it',d.scoreMode)}${C.option('exact','Exact score - only when everything else meets the condition',d.scoreMode)}</select></label><label class="check"><input type="checkbox" data-consistency-scope ${d.applyToAll?'checked':''}>Apply to all versions</label><p class="help">${d.applyToAll?'Compatible versions: '+e((q.compatibleVersions||[]).map(v=>v.label).join(', ')||C.S.version.label)+'. Different rubrics are excluded.':'Applies to Version '+e(C.S.version.label)+' only.'}</p><div class="row">${btn('Approve decision','approve','',true)}${btn('Clear editor','clear')}</div><p class="help">Approving or deactivating a decision requires a new grading run. Prior proposals, reviews, and decision revisions remain available.</p></section></div>
    <section class="card"><h2>Saved decisions for question ${e(q.key)}</h2>${q.rules.map(rule=>ruleCard(q,rule)).join('')||'<p>No approved decisions yet. You can write one manually or discuss it with the local model.</p>'}</section></div>`;
  }
  async function mount() {
    if(!C?.S.version||C.S.tab!=='decisions')return;
    resetVersion(C.S.version.id);
    if(!D.data&&!D.loading&&!D.error) {
      const id=D.versionId;D.loading=true;
      try {const data=await C.api(`/api/versions/${id}/decisions`);if(D.versionId===id)D.data=data;}
      catch(error){if(D.versionId===id)D.error=error.message;}
      finally {if(D.versionId===id){D.loading=false;repaint();}}
      return;
    }
    const panel=document.querySelector('#consistency-panel');
    if(!panel||panel.dataset.bound)return;
    panel.dataset.bound='true';
    panel.addEventListener('input',event=>changed(event.target));
    panel.addEventListener('change',event=>changed(event.target));
  }
  async function changed(el) {
    if(!D.draft)return false;
    if(el.hasAttribute('data-consistency-question')) {
      if(el.value===D.questionKey)return true;
      if(dirty()&&!await C.confirm('Discard the unsaved common-mistake decision?')){el.value=D.questionKey;return true;}
      D.questionKey=el.value;resetDraft();D.history=[];D.pending=null;repaint();return true;
    }
    if(el.hasAttribute('data-consistency-scope')){D.draft.applyToAll=el.checked;repaint();return true;}
    if(el.hasAttribute('data-consistency-approved')){D.approved=el.checked;return true;}
    const field=el.dataset.consistencyField;
    if(field){D.draft[field]=el.value;D.approved=false;}
    else if(el.hasAttribute('data-consistency-choice')) {
      D.draft.items=[...document.querySelectorAll('[data-consistency-choice]:checked')].map(x=>x.dataset.consistencyChoice);D.approved=false;
    } else return false;
    const approval=document.querySelector('[data-consistency-approved]');if(approval)approval.checked=false;
    return true;
  }
  async function action(el) {
    const name=el.dataset.action||'';
    if(!name.startsWith('consistency-'))return false;
    const action=name.slice('consistency-'.length),q=question(),vid=D.versionId;
    if(action==='question'){
      if(el.dataset.key!==D.questionKey){stash();D.questionKey=el.dataset.key;restore();repaint();}return true;
    }
    if(action==='refresh') {
      if(dirty()&&!await C.confirm('Discard the unsaved decision and refresh?'))return true;
      resetDraft();D.data=null;D.error='';repaint();return true;
    }
    if(!q)throw new Error('Choose a saved question first.');
    if(action==='clear') {if(!dirty()||await C.confirm('Clear the unsaved decision?')){resetDraft();repaint();}return true;}
    if(action==='edit') {
      if(dirty()&&!await C.confirm('Discard the unsaved decision and edit this one?'))return true;
      const rule=q.rules.find(r=>r.id===el.dataset.rule);if(!rule)throw new Error('Refresh the decision list.');
      resetDraft({...blank(),applyToAll:rule.applyToAll!==false,scoreMode:rule.scoreMode||'exact',condition:rule.condition,reason:rule.reason,items:rule.items.slice(),ruleId:rule.id,expectedRevision:rule.revision,source:rule.source});repaint();return true;
    }
    if(action==='deactivate') {
      const rule=q.rules.find(r=>r.id===el.dataset.rule);if(!rule)throw new Error('Refresh the decision list.');
      if(!await C.confirm('Deactivate this decision for every version sharing this rubric? Existing proposals and reviews are retained; a new grading run is required.'))return true;
      const data=await C.api(`/api/versions/${vid}/decisions/${rule.id}/deactivate`,{questionKey:q.key,rubricFingerprint:q.fingerprint,expectedRevision:rule.revision,confirmed:true});
      invalidateCachedLists();if(D.versionId===vid){D.data=data;invalidateRun();repaint();}
      C.message('Decision deactivated. Start a new run to use the current policy.');return true;
    }
    if(action==='approve') {
      const before=encode(D.draft);
      const data=await C.api(`/api/versions/${vid}/decisions`,{questionKey:q.key,rubricFingerprint:q.fingerprint,condition:D.draft.condition,reason:D.draft.reason,items:D.draft.items,ruleId:D.draft.ruleId,expectedRevision:D.draft.expectedRevision,source:D.draft.source,applyToAll:D.draft.applyToAll,scoreMode:D.draft.scoreMode,approved:true});
      invalidateCachedLists();if(D.versionId===vid){D.data=data;invalidateRun();if(D.questionKey===q.key&&encode(D.draft)===before){resetDraft();D.pending=null;}repaint();}
      C.message('Guidance saved for the selected version scope. Start a new grading run to apply it.');return true;
    }
    if(action==='load-proposal') {
      const p=D.pending;
      if(!p||p.versionId!==vid||p.questionKey!==q.key||p.rubricFingerprint!==q.fingerprint)throw new Error('This proposal belongs to an older question or rubric. Discuss it again.');
      if(dirty()&&(D.draft.condition||D.draft.reason||D.draft.items.length)&&!await C.confirm('Replace the current unsaved editor with this proposed decision?'))return true;
      D.draft={...D.draft,condition:p.draft.condition,reason:p.draft.reason,items:p.draft.items.slice(),scoreMode:p.draft.scoreMode||'exact',source:'local-discussion'};D.approved=false;repaint();return true;
    }
    if(action==='discuss') {
      if(D.busy)return true;
      const message=D.draft.message.trim();if(!message)throw new Error('Describe the mathematical mistake or follow-up question.');
      const model=document.querySelector('[data-consistency-model]')?.value;
      const request=++D.request,discussionKey=key();D.busy=true;D.pending=null;
      try {
        const job=await C.api(`/api/versions/${vid}/decisions/discuss`,{questionKey:q.key,rubricFingerprint:q.fingerprint,message,history:D.history.slice(-8),...(model?{model}:{})});
        repaint();
        let answer;
        for(let attempt=0;attempt<2400;attempt++) {
          await new Promise(resolve=>setTimeout(resolve,300));
          const status=await C.api(`/api/jobs/${job.id}`);
          if(status.status==='done'){answer=status.result;break;}
          if(['error','cancelled'].includes(status.status))throw new Error(status.error||'The local discussion stopped.');
        }
        if(!answer)throw new Error('The local discussion timed out.');
        if(D.versionId!==vid||D.questionKey!==q.key||D.request!==request){
          const saved=drafts.get(discussionKey);
          if(saved&&saved.request===request){saved.pending=answer;saved.busy=false;saved.history.push({role:'user',text:message},{role:'assistant',text:answer.draft.condition+'\\n'+answer.draft.reason});saved.history=saved.history.slice(-8);if(saved.draft.message===message)saved.draft.message='';}
          return true;
        }
        D.pending=answer;
        const draft=answer.draft;
        D.history.push({role:'user',text:message},{role:'assistant',text:`Condition: ${draft.condition}\nChoice: ${selectedText(q,draft.items)}\nReason: ${draft.reason}${draft.caution?'\nCaution: '+draft.caution:''}`});
        D.history=D.history.slice(-8);
        if(D.draft.message===message)D.draft.message='';
        C.message('Proposal ready. Load, edit and explicitly approve it before it affects grading.');
      } finally {const saved=drafts.get(discussionKey);if(saved&&saved.request===request)saved.busy=false;if(D.versionId===vid&&D.questionKey===q.key&&D.request===request){D.busy=false;repaint();}}
      return true;
    }
    return true;
  }
  function reportView(report) {
    const e=C.esc;
    return `<section class="card"><h2>Consistency review</h2><p class="help">Counts describe recognized patterns in this run. Unrecognized or misread patterns still require review. ${report.current?'':'The current rubric, sources or policy differ from this run.'}</p>${report.groups.map(g=>`<div class="scan-row"><strong>Question ${e(g.questionKey)} · decision revision ${g.revision}</strong><p>${e(g.condition)}</p><p>${g.matched} matched · ${g.reviewed} reviewed · ${g.humanOverrides} instructor overrides · ${g.modelDisagreements} model disagreements · ${g.flagged} flagged</p></div>`).join('')||'<p>No approved common-mistake decisions were included in this run.</p>'}<p class="help">${report.withoutMatchedRule} suggestions have no matched decision.</p>${report.exceptions.length?`<h3>Review exceptions</h3>${report.exceptions.map(x=>`<p>Exam ${x.examNumber} · ${e(x.questionKey)}: ${e(x.reasons.join('; '))}${x.reviewed?' · reviewed':''}</p>`).join('')}`:''}</section>`;
  }
  window.GScopeConsistency={init:context=>{C=context;},view,mount,action,change:changed,dirty,discard:()=>{drafts.clear();versions.clear();resetDraft();D.pending=null;D.history=[];},reportView};
})();
