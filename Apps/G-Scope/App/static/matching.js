/* Private student matching: fixed roster identities, explicit human confirmation. */
window.GScopeMatching=(()=>{
 'use strict';
 let C;const M={pid:null,data:null,loading:false,job:null,filter:'all',query:'',hideFields:false,showMissing:false,editing:null,edits:new Map(),error:'',watching:false,progress:null,starting:false,confirming:false,request:0,index:-1};
 const e=v=>C.esc(v),button=(t,a,x='',p=false)=>C.button(t,'match-'+a,x,p);
 const active=()=>C.S.tab==='match'&&(!C.S.view||C.S.view==='projects'),section=v=>/^\d+$/.test(v||'')?String(Number(v)).padStart(2,'0'):v||'—';
 const fold=v=>String(v||'').normalize('NFKD').toLowerCase().replace(/[^a-z0-9]/g,'');
 const idFold=v=>fold(v).replace(/[1il]/g,'l').replace(/[0o]/g,'o');
 function options(r){
  const edit=M.edits.get(r.id)||{query:''},q=(edit.query||'').toLowerCase().trim();
  const used=new Set((M.data.items||[]).filter(x=>x.id!==r.id&&['auto','manual'].includes(x.status)).map(x=>x.studentId));
  let available=M.data.roster.filter(s=>!used.has(s.id));
  const score=s=>(r.proposal?.netid&&fold(s.netid)===fold(r.proposal.netid)?100:0)+(r.proposal?.name&&fold(s.name)===fold(r.proposal.name)?80:0)+(r.proposal?.netid&&idFold(s.netid)===idFold(r.proposal.netid)?30:0);
  if(q){
   const direct=available.filter(s=>[s.name,s.netid,...(s.emails||[])].some(v=>(v||'').toLowerCase().includes(q)));
   available=direct.length?direct:available.filter(s=>/\d/.test(q)&&idFold(s.netid)===idFold(q));
  }
  return available.sort((a,b)=>score(b)-score(a)||a.name.localeCompare(b.name)).slice(0,50);
 }
 function highlight(value,q){
  value=String(value||'');q=String(q||'').trim();if(!q)return e(value);
  const i=value.toLowerCase().indexOf(q.toLowerCase());return i<0?e(value):e(value.slice(0,i))+'<mark>'+e(value.slice(i,i+q.length))+'</mark>'+e(value.slice(i+q.length));
 }
 function editor(r){
  const edit=M.edits.get(r.id)||{query:''},choices=options(r),list='gs-students-'+r.id;
  return '<div class="gs-student-editor" data-match-row="'+r.id+'"><label class="gs-picker-label">Choose student to assign<input data-match-field="query" value="'+e(edit.query||'')+'" placeholder="Search name, NetID or email" role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls="'+list+'" autocomplete="off"></label><div id="'+list+'" role="listbox" class="gs-student-options">'+choices.map((s,i)=>'<button type="button" role="option" aria-selected="'+(M.index===i)+'" data-action="match-pick" data-id="'+r.id+'" data-student="'+s.id+'"><strong>'+highlight(s.name,edit.query)+'</strong><span>'+highlight(s.netid,edit.query)+' · '+e(section(s.section))+'</span>'+(s.emails?.[0]?'<small>'+highlight(s.emails[0],edit.query)+'</small>':'')+'</button>').join('')+(choices.length?'':'<p class="help">No available roster students match.</p>')+'</div>'+(r.status!=='unmatched'?button('Clear assignment','clear','data-id="'+r.id+'"'):'')+button('Cancel','cancel','data-id="'+r.id+'"')+'</div>';
 }

 const state=r=>r.studentId&&r.identityReviewed&&r.status!=='unmatched'?'confirmed':r.studentId&&r.status!=='unmatched'?'high':r.suggestion?'suggestion':'none';
 const candidate=r=>r.status==='unmatched'?r.suggestion:{id:r.studentId,name:r.name,netid:r.netid,section:r.section};
 function rows(){return (M.data?.items||[]).filter(r=>(M.filter==='all'||state(r)===M.filter)&&[r.name,r.netid,r.suggestion?.name,r.suggestion?.netid,r.number].join(' ').toLowerCase().includes(M.query.toLowerCase()));}
 function progressView(id='gs-match-progress'){if(M.progress?.state==='done')return '';return window.GScopeProgress?.view?.(M.progress,{id})||'';}
 function finishProgress(status){
  const p=typeof M.progress==='object'&&M.progress?M.progress:{},total=p.total||M.data?.items?.length||0;
  M.progress={...p,state:status,message:status==='done'?'Matching complete':status==='cancelled'?'Matching paused. Completed results are saved.':'Matching stopped. Completed results are saved.',...(status==='done'&&total?{total,completed:total}:{})};
 }
 function rowView(r){
  const kind=state(r),s=candidate(r),status={high:'Match · Awaiting confirmation',suggestion:'Suggestion · Check carefully',none:'No suggestion',confirmed:'✓ Confirmed'}[kind];
  const previews=r.available&&r.versionId?r.previewFields.map(f=>'<img class="gs-identity-'+f+'" src="/api/intake-booklets/'+r.id+'/identity/'+f+'" alt="Exam '+r.number+' '+(f==='name'?'name':'NetID')+' field" loading="lazy" decoding="async">').join(''):'<span class="help">Choose exam version first.</span>';
  const reading=r.proposal?.name||r.proposal?.netid;
  const details=r.reason||reading?'<details><summary>Details</summary>'+(reading?'<p class="help">Read as: '+e(r.proposal.name||'—')+' · '+e(r.proposal.netid||'—')+'</p>':'')+(r.reason?'<p class="help">'+e(r.reason)+'</p>':'')+'</details>':'';
  const canConfirm=s&&kind!=='confirmed'&&r.available&&r.versionId;
  return '<tr><td class="gs-match-fields" '+(M.hideFields?'hidden':'')+'><div class="gs-identity-previews">'+previews+'</div></td><td><div class="gs-match-heading"><strong>Exam '+r.number+'</strong><span class="gs-match-status '+kind+'">'+status+'</span></div><div class="gs-match-identity">'+e(s?.name||'Choose a roster student')+(s?.netid?' <code>'+e(s.netid)+'</code>':'')+'</div>'+(M.editing===r.id?editor(r):'<div class="gs-match-row-actions">'+(canConfirm?button('Confirm','confirm-one','data-id="'+r.id+'" data-student="'+e(s.id)+'" '+(M.confirming?'disabled':''),true):'')+button(s?'Change':'Choose student','edit','data-id="'+r.id+'" '+(!r.versionId?'disabled':''))+details+'</div>')+'</td><td>'+e(section(s?.section||r.section))+'</td><td>'+e(r.versionLabel||'Not assigned')+'<br><small class="help">Pages '+r.startPage+'–'+(r.startPage+r.pages-1)+'</small></td></tr>';
 }
 function view(pid){
  if(M.pid!==pid||!M.data)return '<section class="card"><h2>Student matching</h2><p>'+(M.error?e(M.error):'Loading students…')+'</p></section>';
  const d=M.data,counts={high:0,suggestion:0,none:0,confirmed:0};for(const r of d.items)counts[state(r)]++;
  const running=M.job||M.starting;
  return '<section class="card gs-matching"><div class="gs-matching-header"><div><h2>Student matching <small>'+d.items.length+' exams</small></h2><p class="help">Check the handwriting, then confirm the roster student.</p></div><div class="row">'+button(running?'Matching…':d.items.some(r=>r.attempted)?'Match again':'Match students','start',running?'disabled':'',true)+button('Confirm all high-confidence matches','confirm',counts.high&&!M.confirming?'':'disabled')+button('Confirm all suggestions ('+counts.suggestion+')','confirm-suggestions',counts.suggestion&&!M.confirming?'':'disabled')+(M.job?button('Pause','stop'):'')+button('Continue to grading →','continue')+'</div></div>'+(M.error?'<p class="notice warning">'+e(M.error)+'</p>':'')+progressView()+'<div class="gs-match-tools"><div class="gs-match-filters">'+[['all','All'],['high',counts.high+' Matches'],['suggestion',counts.suggestion+' Suggestions'],['none',counts.none+' No suggestion'],['confirmed',counts.confirmed+' Confirmed']].map(([id,label])=>button(label,'filter','data-filter="'+id+'" class="gs-filter-'+id+'" aria-pressed="'+(M.filter===id)+'"')).join('')+'</div><div class="row"><input id="gs-match-search" aria-label="Search submissions" value="'+e(M.query)+'" placeholder="Search submissions">'+button(M.hideFields?'Show fields':'Hide fields','fields')+'</div></div><div class="gs-match-roster-summary">'+button(d.unmatchedStudents.length+' roster students not yet matched','missing')+'</div>'+(M.showMissing?'<details open class="notice"><summary>Roster students not yet matched</summary><ul>'+d.roster.filter(s=>d.unmatchedStudents.includes(s.id)).map(s=>'<li>'+e(s.name)+' · '+e(s.netid)+'</li>').join('')+'</ul></details>':'')+'<div class="gs-match-table-wrap"><table class="gs-match-table"><thead><tr><th '+(M.hideFields?'hidden':'')+'>Name &amp; NetID</th><th>Student</th><th>Section</th><th>Version / pages</th></tr></thead><tbody>'+rows().map(rowView).join('')+'</tbody></table></div></section>';
 }
 function progressOnly(){
  const n=document.querySelector('#gs-match-background-text');
  if(n)n.innerHTML=progressView('gs-match-background-progress');
  const b=document.querySelector('[data-action="match-stop"]');if(b&&!M.job)b.hidden=true;
 }
 async function load(pid){
  const request=++M.request;M.loading=true;
  try{const d=await C.api('/api/projects/'+pid+'/matching');if(M.pid!==pid||request!==M.request)return;M.data=d;M.error='';if(!M.job&&!d.items.some(r=>r.attempted))M.progress=null;if(d.job&&['queued','running'].includes(d.job.status)){M.job=d.job.id;watch();}else if(d.job&&d.items.some(r=>r.attempted)&&['done','error','cancelled'].includes(d.job.status)&&!M.job)finishProgress(d.job.status);}
  catch(error){if(M.pid===pid)M.error=error.message;}
  finally{if(M.pid===pid&&request===M.request){M.loading=false;if(active())C.render();else progressOnly();}}
 }
 async function start(){
  if(M.job||M.starting)return;M.starting=true;M.progress={message:'Preparing student matching…'};if(active())C.render();
  try{const job=await C.api('/api/projects/'+M.pid+'/match-students',{});if(!job.noWork){M.job=job.id;watch();}else M.progress={message:'No exams need another reading.'};M.error='';}
  catch(error){M.error=error.message;M.progress=null;}finally{M.starting=false;if(active())C.render();}
 }
 async function mount(pid){if(M.pid!==pid){M.pid=pid;M.request++;M.data=null;M.job=null;M.edits.clear();M.editing=null;M.error='';M.progress=null;}if(!M.loading&&!M.data)await load(pid);}
 async function watch(){
  if(M.watching||!M.job)return;M.watching=true;const pid=M.pid,id=M.job;
  try{const j=await C.api('/api/jobs/'+id);if(M.pid!==pid||M.job!==id)return;M.progress=typeof j.progress==='string'?{message:j.progress}:j.progress||{message:'Matching students…'};if(['done','error','cancelled'].includes(j.status)&&!j.stopping){M.job=null;finishProgress(j.status);await load(pid);if(j.status==='error')M.error=j.error||'Matching stopped; completed results are saved.';if(active())C.render();else progressOnly();return;}await load(pid);setTimeout(()=>watch(),1400);}
  catch(error){if(M.pid===pid){M.job=null;M.error=error.message;if(active())C.render();}}
  finally{M.watching=false;}
 }
 async function pause(){
  const id=M.job;if(!id)return;M.progress={...(typeof M.progress==='object'?M.progress:{}),message:'Pausing matching…'};if(active())C.render();
  await C.api('/api/jobs/'+id+'/cancel',{immediate:true});
  for(let i=0;i<40;i++){const job=await C.api('/api/jobs/'+id);if(!job.stopping)break;await new Promise(resolve=>setTimeout(resolve,250));}
  if(M.job===id)M.job=null;finishProgress('cancelled');await load(M.pid);
 }
 async function beforeNavigate(tab){if(tab!=='template'||!M.job)return true;if(!await C.confirm('Pause student matching to edit the name/NetID boxes? Completed readings stay saved.'))return false;await pause();return true;}
 function input(el){
  if(el.id==='gs-match-search'){M.query=el.value;const pos=el.selectionStart;C.render();const n=document.querySelector('#gs-match-search');n?.focus?.();n?.setSelectionRange?.(pos,pos);return true;}
  const row=el.closest?.('[data-match-row]');if(!row||!el.dataset.matchField)return false;
  const value=M.edits.get(row.dataset.matchRow)||{query:''};value[el.dataset.matchField]=el.value;M.edits.set(row.dataset.matchRow,value);M.index=-1;
  if(active()){const pos=el.selectionStart;C.render();const n=document.querySelector('[data-match-row="'+row.dataset.matchRow+'"] [data-match-field="query"]');n?.focus?.();n?.setSelectionRange?.(pos,pos);}return true;
 }
 async function confirming(action){
  if(M.confirming)return;M.confirming=true;if(active())C.render();
  try{return await action();}finally{M.confirming=false;if(active())C.render();}
 }
 async function action(el){
  if(!el.dataset.action?.startsWith('match-'))return false;const op=el.dataset.action.slice(6);
  if(op==='filter')M.filter=el.dataset.filter;
  if(op==='fields')M.hideFields=!M.hideFields;
  if(op==='missing')M.showMissing=!M.showMissing;
  if(op==='edit'){M.editing=el.dataset.id;M.index=-1;}
  if(op==='cancel'){M.editing=null;M.edits.delete(el.dataset.id);}
  if(op==='refresh')await load(M.pid);
  if(op==='start')await start();
  if(op==='stop')await pause();
  if(op==='continue'){C.S.tab='process';C.render();return true;}
  if(op==='pick'||op==='assign'){
   const id=el.dataset.id,edit=M.edits.get(id)||{},studentId=el.dataset.student||edit.studentId;
   if(!studentId)throw Error('Choose a roster student.');await C.api('/api/intake-booklets/'+id+'/student',{studentId,reviewed:true});M.editing=null;M.edits.delete(id);await load(M.pid);
  }
  if(op==='clear'){
   if(await C.confirm('Clear this student assignment? The student becomes available again and saved grading stays intact.')){
    await C.api('/api/intake-booklets/'+el.dataset.id+'/student/clear',{reviewed:true,rosterHash:M.data.rosterHash});M.editing=null;M.edits.delete(el.dataset.id);await load(M.pid);
   }
  }
  if(op==='confirm-one')await confirming(async()=>{
   const row=M.data.items.find(r=>r.id===el.dataset.id),s=row&&candidate(row);
   if(!s||s.id!==el.dataset.student)throw Error('This suggestion changed. Check the displayed student again.');
   if(row.status==='unmatched')await C.api('/api/intake-booklets/'+row.id+'/student',{studentId:s.id,reviewed:true});
   else await C.api('/api/projects/'+M.pid+'/review-student-matches',{packetIds:[row.id],rosterHash:M.data.rosterHash,reviewed:true});
   await load(M.pid);
  });
  if(op==='confirm-suggestions')await confirming(async()=>{
   const suggestions=M.data.items.filter(r=>r.status==='unmatched'&&r.suggestion).map(r=>({packetId:r.id,studentId:r.suggestion.id}));
   if(!suggestions.length)throw Error('No suggestions remain.');
   if(await C.confirm('Confirm all '+suggestions.length+' suggested roster students after checking the handwriting? High-confidence matches and exams with no suggestion are unchanged.')){
    await C.api('/api/projects/'+M.pid+'/review-student-suggestions',{suggestions,rosterHash:M.data.rosterHash,reviewed:true});await load(M.pid);
   }
  });
  if(op==='confirm')await confirming(async()=>{
   const ids=M.data.items.filter(r=>r.status==='auto'&&!r.identityReviewed).map(r=>r.id);
   if(!ids.length)throw Error('No unconfirmed matches remain.');
   if(await C.confirm('Confirm all '+ids.length+' high-confidence matches after checking the handwriting? Gold suggestions and exams with no suggestion will remain unconfirmed.')){await C.api('/api/projects/'+M.pid+'/review-student-matches',{packetIds:ids,rosterHash:M.data.rosterHash,reviewed:true});await load(M.pid);}
  });
  if(active())C.render();return true;
 }
 function init(c){C=c;document.addEventListener?.('keydown',event=>{
  const el=event.target;if(el.dataset?.matchField!=='query'||!M.editing)return;
  if(event.key==='Escape'){event.preventDefault();M.editing=null;C.render();return;}
  if(event.key==='Enter'&&M.index>=0){event.preventDefault();const r=M.data.items.find(x=>x.id===M.editing),s=options(r)[M.index];if(s)action({dataset:{action:'match-pick',id:r.id,student:s.id}}).catch(error=>C.message(error.message));return;}
  if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();const r=M.data.items.find(x=>x.id===M.editing);M.index=Math.max(0,Math.min(options(r).length-1,M.index+(event.key==='ArrowDown'?1:-1)));const pos=el.selectionStart;C.render();const n=document.querySelector('[data-match-field="query"]');n?.focus?.();n?.setSelectionRange?.(pos,pos);}
 });}
 function rosterChanged(pid){if(M.pid===pid){M.request++;M.data=null;M.loading=false;}}
 return {init,view,mount,input,change:el=>el.dataset?.matchField==='query'||el.id==='gs-match-search'?true:input(el),action,beforeNavigate,rosterChanged,scansChanged:rosterChanged,dirty:()=>false,discard:()=>{M.edits.clear();M.editing=null;},backgroundView:()=>M.job&&!active()?'<aside class="gs-matching-background"><div id="gs-match-background-text">'+progressView('gs-match-background-progress')+'</div>'+button('Pause','stop')+'</aside>':''};
})();
