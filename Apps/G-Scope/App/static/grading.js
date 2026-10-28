/* Question-scoped grading controls. Saved student identities never enter model requests. */
window.GScopeGrading=(()=>{
 'use strict';
 let C,current=null;const states=new Map(),pausing=new Set();
 const e=v=>C.esc(v),button=(text,op,extra='',primary=false)=>C.button(text,'grading-'+op,extra,primary);
 function state(v){if(!states.has(v.id))states.set(v.id,{id:v.id,data:null,selected:new Set(v.questions.map(q=>q.id)),thinking:false,loading:false,busy:false,error:'',request:0,abandon:null});return states.get(v.id);}
 const formatName=t=>({free_response:'Free response',single_choice:'Single choice',multiple_choice:'Select all',fill_in:'Fill-in'}[t||'free_response']);
 const duration=s=>{s=Math.max(0,Math.round(Number(s)||0));return s>=3600?Math.floor(s/3600)+'h'+Math.floor(s%3600/60)+'m'+s%60+'s':s>=60?Math.floor(s/60)+'m'+s%60+'s':s+'s';};
 function summary(r){
  if(pausing.has(r.id)&&['queued','running'].includes(r.status))return 'Pausing after current submission…';
  const n=r.completedSubmissions??0,total=r.totalSubmissions??0,multiple=(r.questions||[]).length>1;
  const verb=r.status==='complete'?'Graded':r.status==='saved'?'Saved partial results for':r.status==='paused'?'Paused at':r.status==='discarded'?'Discarded results for':r.status==='error'?'Stopped at':'Grading';
  return verb+' '+n+'/'+total+' submissions'+(multiple?' · '+r.completed+'/'+r.total+' question assessments':'')+' in '+duration(r.elapsed_seconds)+(r.elapsed_seconds>r.session_seconds+1?' · this session '+duration(r.session_seconds):'');
 }
 function invalidate(vid){const g=states.get(vid);if(g){g.data=null;g.request++;g.loading=false;}}
 async function load(g){
  if(g.loading)return;g.loading=true;g.error='';const request=++g.request;
  try{const data=await C.api('/api/versions/'+g.id+'/grading-status?thinking='+(g.thinking?'1':'0'));if(g.request!==request)return;g.data=data;}
  catch(err){if(g.request===request)g.error=err.message;}
  finally{if(g.request===request){g.loading=false;if(!C.S.dirty&&C.S.version?.id===g.id&&((C.S.view==='projects'&&['process','reviewgrades'].includes(C.S.tab))||C.S.view==='review')){if(C.S.view==='review'&&C.S.reviewDrafts?.size){const el=document.querySelector('#gs-export-current');if(el)el.innerHTML=exportControl(C.S.version);}else C.render();}}}
 }
 async function mount(){
  const v=C.S.version;if(!v||!((C.S.view==='projects'&&['process','reviewgrades'].includes(C.S.tab))||C.S.view==='review'))return;
  const g=state(v);current=g;if(!g.data&&!g.loading&&!g.error)await load(g);
 }
 function exportControl(v){
  const g=state(v);
  return g.data?.exportReady?'<a class="button" href="/api/projects/'+v.project_id+'/export" download>Export all grading suggestions</a>':'<button disabled title="'+e(g.data?.exportReason||'Checking current results and confirmed student matches')+'">Export all grading suggestions</button><span class="help">'+e(g.data?.exportReason||'Checking export readiness…')+'</span>';
 }
 function abandonView(g){
  if(!g.abandon)return '';
  return '<section class="notice warning gs-abandon-dialog" role="dialog" aria-label="Abandon paused grading run"><strong>Abandon this run?</strong><p>Keep completed assessments for review and reuse, or discard this run’s assessments and reviews. Other runs and exam setup stay intact.</p><div class="row">'+button('Save partial results','abandon-save','data-id="'+g.abandon+'" '+(g.busy?'disabled':''),true)+button('Discard results','abandon-discard','data-id="'+g.abandon+'" '+(g.busy?'disabled':''))+button('Cancel','abandon-cancel',g.busy?'disabled':'')+'</div></section>';
 }
 function view(v){if(window.GScopeGradeWorkspace)return window.GScopeGradeWorkspace.view(v,state(v));
  const g=state(v);current=g;const d=g.data,qs=d?.questions||v.questions.map(q=>({...q,responseType:q.response?.type||'free_response',current:0,outdated:0,total:v.booklets.length,issues:[]}));
  const selected=qs.filter(q=>g.selected.has(q.id)),issues=[...(d?.issues||[]),...selected.flatMap(q=>q.issues)];
  if(!selected.length)issues.push('Select one or more questions.');
  const pending=selected.reduce((n,q)=>n+q.total-q.current,0),history=selected.some(q=>q.current||q.outdated);
  const ready=!!d&&!g.loading&&!g.busy&&!d.activeRun&&issues.length===0;
  const rows=v.runs||[];
  return '<section class="card gs-grading-controls"><div class="spread"><h2>Grade &amp; review</h2>'+C.button('Inspect question crops (optional)','tab','data-tab="crops"')+'</div><p>'+v.booklets.length+' submissions · '+selected.length+' selected questions · <strong>'+v.booklets.length*selected.length+' question assessments</strong></p><div class="gs-grading-questions" role="group" aria-label="Questions to grade">'+qs.map(q=>button('<strong>Question '+e(q.key)+'</strong><small>'+formatName(q.responseType)+' · '+q.current+'/'+q.total+' current'+(q.outdated?' · '+q.outdated+' outdated':'')+'</small>','select','data-id="'+q.id+'" aria-pressed="'+g.selected.has(q.id)+'"')).join('')+'</div><div class="row gs-grade-selection">'+button('Select all','all')+button('Clear selection','none')+'<label class="check"><input type="checkbox" id="gs-grade-thinking" '+(g.thinking?'checked':'')+' '+(g.busy?'disabled':'')+'>Extended reasoning for free response</label><span class="help">'+e(C.modelLabel?.(d?.model||C.S.boot?.defaultModel)||'Configured local model')+'</span></div>'+(g.loading?'<p role="status">Checking grading readiness…</p>':'')+(g.error?'<p class="notice warning">'+e(g.error)+'</p>':'')+(issues.length?'<div class="notice warning"><strong>Before grading</strong><ul>'+[...new Set(issues)].map(i=>'<li>'+e(i)+'</li>').join('')+'</ul></div>':'')+'<div class="row">'+button(g.busy?'Preparing grading…':'Grade selected questions','start',ready&&pending?'':'disabled',true)+button('Regrade selected questions','redo',ready&&history?'':'disabled')+button('Refresh readiness','refresh',g.busy?'disabled':'')+'</div><p class="help">'+(d?.activeRun?'A grading run is active. Review or pause it before starting another.':d&&!pending&&selected.length?'Selected questions already have current results. Regrade starts fresh and keeps older runs as history.':pending+' assessments need current results. Grading skips compatible retained results; regrading processes every selected question again.')+'</p><p class="help">Choice and fill-in questions use response recognition followed by code-based comparison. Free response uses the saved grading specification. Extended reasoning applies only to free response.</p></section><section class="card"><h2>Export for G-Rater</h2><p class="help">One export combines current results from all versions and retained question runs.</p><div id="gs-export-current" class="row">'+exportControl(v)+'</div></section>'+abandonView(g)+'<section class="card"><h2>Saved runs for Version '+e(v.label)+'</h2>'+rows.map(r=>'<div class="scan-row"><div class="spread"><strong>'+e(r.status)+' · '+e(new Date(r.created).toLocaleString())+'</strong><span class="help">'+duration(r.elapsed_seconds)+' total'+(r.thinking?' · Extended reasoning':' · Standard grading')+'</span></div><p class="help">Questions '+e((r.questionKeys||[]).join(', ')||'All')+' · '+e(C.modelLabel?.(r.model)||r.model)+'</p><div class="row">'+button('Review / progress','open','data-id="'+r.id+'"')+(['paused','error'].includes(r.status)?button('Resume','resume','data-id="'+r.id+'" '+(g.busy||d?.activeRun?'disabled':''))+button('Abandon…','abandon','data-id="'+r.id+'" '+(g.busy?'disabled':'')):'')+'</div></div>').join('')+(rows.length?'':'<p>No grading runs yet.</p>')+'</section>';
 }
 function reviewNav(r){
  return '<div class="gs-review-question-buttons" role="group" aria-label="Review question">'+button('All questions','review-question','data-id="" aria-pressed="'+!C.S.reviewQuestion+'"')+r.questions.map(q=>button('Question '+e(q.key),'review-question','data-id="'+q.id+'" aria-pressed="'+(C.S.reviewQuestion===q.id)+'"')).join('')+'</div>';
 }
 function reviewItems(r){return r.proposals.filter(p=>!C.S.reviewQuestion||p.question_id===C.S.reviewQuestion);}
 async function cropChange(field,value){
  const S=C.S,q=S.version.questions[S.cropQuestion]||S.version.questions[0],page=Number(document.querySelector('#crop-page')?.value||S.cropPage);
  if((JSON.stringify(S.rect)!==JSON.stringify(q.rect)||page!==q.page)&&!await C.confirm('Discard the unsaved crop adjustment and switch the displayed question or exam?'))return false;
  if(field==='question')S.cropQuestion=Number(value);
  if(field==='file'){S.cropFile=value;S.cropBooklet=null;}
  if(field==='booklet')S.cropBooklet=value;
  C.render();return true;
 }
 async function action(el){
  if(!el.dataset.action?.startsWith('grading-'))return false;
  const op=el.dataset.action.slice(8),v=C.S.version,g=state(v);current=g;
  if(op==='crop-step'){
   const field=el.dataset.field,offset=Number(el.dataset.offset),values=field==='question'?v.questions.map((q,i)=>String(i)):field==='file'?v.files.filter(f=>f.kind==='scans').map(f=>f.id):v.booklets.filter(b=>b.file_id===C.S.cropFile).map(b=>b.id);
   const old=field==='question'?String(C.S.cropQuestion):field==='file'?C.S.cropFile:C.S.cropBooklet,index=values.indexOf(old),next=values[index+offset];
   if(next!==undefined)await cropChange(field,next);return true;
  }
  if(op==='back'){g.data=null;C.S.view='projects';C.S.tab='process';C.render();return true;}
  if(op==='review-question'){C.S.reviewQuestion=el.dataset.id;const first=reviewItems(C.S.run)[0];C.S.selected=first?.id;C.render();return true;}
  if(op==='select'){g.selected.has(el.dataset.id)?g.selected.delete(el.dataset.id):g.selected.add(el.dataset.id);C.render();return true;}
  if(op==='all'){g.selected=new Set(v.questions.map(q=>q.id));C.render();return true;}
  if(op==='none'){g.selected.clear();C.render();return true;}
  if(op==='refresh'){g.error='';g.data=null;await load(g);return true;}
  if(op==='open'){C.S.reviewQuestion='';await C.openRun(el.dataset.id);return true;}
  if(op==='abandon'){g.abandon=el.dataset.id;C.render();return true;}
  if(op==='abandon-cancel'){g.abandon=null;C.render();return true;}
  if(g.busy)return true;
  if(op==='resume'&&v.runs.find(r=>r.id===el.dataset.id)?.provider==='chatgpt'){
   if(!await C.leave())return true;const r=await C.api('/api/runs/'+el.dataset.id),q=v.questions.find(q=>r.questions.some(item=>item.id===q.id));
   if(!q)throw Error('Choose the saved free-response question first.');await window.GScopeOnline.open(C,v,q);return true;
  }
  if(op==='start'||op==='redo'||op==='resume'){
   if(op!=='resume'&&!g.selected.size)throw Error('Select one or more questions.');
   if(op==='redo'&&!await C.confirm('Regrade the selected questions using the current rubric and guidance? Older results and reviews remain in history.'))return true;
   g.busy=true;g.error='';C.render();
   try{
    const payload=op==='resume'?{resume:el.dataset.id,model:v.runs.find(r=>r.id===el.dataset.id)?.model}:{questionIds:[...g.selected],thinking:g.thinking,redo:op==='redo',useTemplateCrops:true};
    const result=await C.api('/api/versions/'+v.id+'/runs',payload);g.data=null;C.S.version=await C.api('/api/versions/'+v.id);C.S.reviewQuestion='';if(el.dataset.stay==='question'){C.S.run=await C.api('/api/runs/'+result.id);C.S.view='projects';C.S.tab='process';window.GScopeGradeWorkspace?.invalidate?.(v.id);}else await C.openRun(result.id);
   }catch(err){g.error=err.message;throw err;}finally{g.busy=false;C.render();}return true;
  }
  if(op==='abandon-save'||op==='abandon-discard'){
   if(op==='abandon-discard'&&!await C.confirm('Discard this run’s completed assessments and instructor reviews? Other runs and the exam setup are preserved.'))return true;
   g.busy=true;C.render();
   try{await C.api('/api/runs/'+el.dataset.id+'/abandon',{choice:op==='abandon-save'?'save':'discard',confirmed:true});g.abandon=null;g.data=null;C.S.view='projects';C.S.tab='process';C.S.run=null;await C.acceptVersion(await C.api('/api/versions/'+v.id));}finally{g.busy=false;C.render();}return true;
  }
  return true;
 }
 async function change(el){
  if(el.id!=='gs-grade-thinking')return false;const g=state(C.S.version);if(g.busy)return true;
  g.thinking=el.checked;invalidate(g.id);g.error='';await load(g);return true;
 }
 async function startQuestion(id,{thinking=false,redo=false}={}){const g=state(C.S.version);g.selected=new Set([id]);g.thinking=thinking;invalidate(g.id);return action({dataset:{action:redo?'grading-redo':'grading-start',stay:'question'}});}
 return {setPausing:(id,value)=>value?pausing.add(id):pausing.delete(id),startQuestion,init:c=>C=c,mount,view,reviewSummary:v=>window.GScopeGradeWorkspace.reviewView(v,state(v)),action,change,invalidate,duration,summary,reviewNav,reviewItems,exportControl,cropChange,abandonView:()=>current?abandonView(current):''};
})();



