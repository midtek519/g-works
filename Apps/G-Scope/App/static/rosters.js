'use strict';
window.GScopeRosters=(()=>{
 let C;const R={pid:null,data:null,preview:null,loading:false,busy:false,error:'',request:0,includeGuests:null,sources:[],reuseSource:'',query:'',section:'',page:0,editing:null,edit:null,editDirty:false};
 const e=v=>C.esc(v),button=(t,a,x='',primary=false)=>C.button(t,'roster-'+a,x,primary);
 function confirmedList(data){
  if(!data?.students?.length)return '';
  const filtered=data.students.filter(s=>(!R.section||(s.sections||[s.section]).includes(R.section))&&(!R.query||(s.name+' '+s.netid+' '+(s.emails||[]).join(' ')).toLowerCase().includes(R.query.toLowerCase())));
  const size=30,pages=Math.max(1,Math.ceil(filtered.length/size));R.page=Math.min(R.page,pages-1);
  const rows=filtered.slice(R.page*size,(R.page+1)*size);
  return `<section class="gs-confirmed-roster"><div class="gs-roster-tools"><label>Find student<input id="gs-roster-search" value="${e(R.query)}" placeholder="Name or NetID"></label><label>Section<select id="gs-roster-section"><option value="">All sections</option>${(data.sections||[]).map(s=>`<option value="${e(s)}" ${R.section===s?'selected':''}>${e(s)}</option>`).join('')}</select></label><span class="help">${filtered.length} of ${data.count} students</span></div><div class="gs-roster-table-wrap"><table class="gs-roster-table"><thead><tr><th>Name</th><th>NetID</th><th>Section</th><th>Details</th><th></th></tr></thead><tbody>${rows.map(s=>`<tr><td>${e(s.name)}</td><td>${e(s.netid)}</td><td>${e((s.sections||[s.section]).join(', '))}</td><td>${s.emails?.length?`<details><summary>${s.emails.length} email${s.emails.length===1?'':'s'}</summary>${s.emails.map(x=>`<div>${e(x)}</div>`).join('')}</details>`:'—'}</td><td>${button('Edit','student-edit',`data-id="${s.id}" ${R.busy?'disabled':''}`)} ${button('Remove','student-remove',`data-id="${s.id}" ${R.busy?'disabled':''}`)}</td></tr>`).join('')||'<tr><td colspan="5">No students match.</td></tr>'}</tbody></table></div><div class="gs-roster-pages">${button('Previous','page',`data-page="${R.page-1}" ${R.page===0?'disabled':''}`)}<span>Page ${R.page+1} of ${pages}</span>${button('Next','page',`data-page="${R.page+1}" ${R.page+1>=pages?'disabled':''}`)}</div>${R.editing?`<div class="gs-roster-edit"><label>Name<input data-roster-edit="name" maxlength="160" value="${e(R.edit.name)}"></label><label>NetID<input data-roster-edit="netid" maxlength="31" value="${e(R.edit.netid)}"></label><label>Section<input data-roster-edit="section" maxlength="30" value="${e(R.edit.section)}"></label><div>${button('Save student','student-save',R.busy?'disabled':'',true)} ${button('Cancel','student-cancel',R.busy?'disabled':'')}</div><p class="help">Changing a name or NetID requires reviewing that student's existing exam match again.</p></div>`:''}</section>`;
 }
 function view(pid){
  const data=R.pid===pid?R.data:null,p=R.pid===pid?R.preview:null,disabled=R.loading||R.busy?'disabled':'';
  return `<section class="card gs-roster-panel"><h2>Exam roster <span class="help">Required</span></h2><p class="help">Upload a Gradescope CSV or reuse a roster from this course and semester. First Name and Last Name identify the student; SID supplies the NetID.</p>${data?.ready?`<p class="notice" role="status">${data.count} students confirmed · sections ${e((data.sections||[]).join(', '))}.</p>`:'<p class="notice warning">Confirm a Gradescope roster before uploading exam scans.</p>'}${R.error?`<p class="notice warning">${e(R.error)}</p>${button('Retry roster','retry')}`:''}<label>Gradescope roster CSV<input type="file" id="gs-roster-file" accept=".csv,.tsv,.txt" ${disabled}></label>${R.sources.length?`<div class="row gs-roster-reuse"><label>Reuse a previous exam roster<select id="gs-roster-reuse" ${disabled}><option value="">Choose exam</option>${R.sources.map(s=>C.option(s.id,s.title+' - '+s.count+' students',R.reuseSource)).join('')}</select></label>${button('Preview roster','reuse',disabled+(!R.reuseSource?' disabled':''))}</div>`:'<p class="help">No other confirmed roster is available for this course and semester.</p>'}${R.loading?'<p role="status">Loading roster…</p>':''}
  ${p?`<div class="notice"><h3>Review roster import</h3><p><strong>${p.count} unique students</strong> · ${e(p.course)} · ${e(C.termLabel?C.termLabel(p.term):p.term)}</p><p class="help">Sections: ${e(p.sections.join(', '))}</p>${p.reusedFrom?`<p class="help">Copied from ${e(p.reusedFrom)}. Confirming creates an independent roster for this exam.</p><details><summary>Student preview (first ${p.studentPreview?.length||0})</summary>${(p.studentPreview||[]).map(s=>`<p class="help">${e(s.name)} - ${e(s.netid)} - ${e(s.section)}</p>`).join('')}</details>`:''}${p.mergedRows?`<p class="help">${p.mergedRows} repeated SID row(s) consolidated; email aliases retained.</p>`:''}${p.excludedStaff?`<p class="help">${p.excludedStaff} staff row(s) excluded.</p>`:''}${p.duplicateNames?'<p class="notice warning">Different NetIDs share a name. Review those matches; Lens will stop on ambiguous names.</p>':''}${p.skippedRows?`<p class="notice warning">${p.skippedRows} invalid student row(s), CSV lines ${e((p.skippedLines||[]).join(', '))}. Correct the CSV before confirming.</p>`:''}${p.guestStudents?`<div class="notice warning"><strong>Review ${p.guestStudents} Guest/unmapped students</strong><ul>${(p.guestPreview||[]).map(row=>`<li>${e(row.name)} · ${e(row.netid)} · ${e(row.section)}</li>`).join('')}</ul><label>Include these students in this exam?<select id="gs-roster-guests" ${disabled}><option value="" ${R.includeGuests===null?'selected':''}>Choose after reviewing</option><option value="include" ${R.includeGuests===true?'selected':''}>Include Guest/unmapped students</option><option value="exclude" ${R.includeGuests===false?'selected':''}>Exclude Guest/unmapped students</option></select></label></div>`:''}<div class="row">${button(R.busy?'Saving…':'Confirm exam roster','apply',disabled+(p.skippedRows||(p.guestStudents&&R.includeGuests===null)?' disabled':''),true)}${button('Cancel import','cancel',disabled)}</div></div>`:''}
  ${confirmedList(data)}<p class="help">Student identities stay local and are excluded from AI grading prompts. Replacing the roster requires checking existing student matches again.</p><div class="row">${C.button('Continue to exam scans →','tab','data-tab="scans" '+(data?.ready?'':'disabled'),true)}</div></section>`;
 }
 async function mount(pid){
  if(!pid||R.loading||(R.pid===pid&&(R.data||R.error)))return;
  if(R.pid!==pid){R.pid=pid;R.data=null;R.preview=null;R.error='';R.query='';R.section='';R.page=0;R.editing=null;R.edit=null;R.editDirty=false;R.sources=[];R.reuseSource='';R.request++;}
  const request=R.request;R.loading=true;
  try{const [value,sources]=await Promise.all([C.api('/api/projects/'+pid+'/roster'),C.api('/api/projects/'+pid+'/roster-sources')]);R.sources=sources?.items||[];if(R.pid===pid&&R.request===request){R.data=value;if(C.S.version?.project_id===pid)C.S.version.roster=value;}}
  catch(error){if(R.pid===pid)R.error='The roster could not be loaded. Reopen Exam roster to retry.';}
  finally{R.loading=false;C.render();}
 }
 async function action(el){
  if(!el.dataset.action?.startsWith('roster-'))return false;
  if(R.busy)throw Error('Wait for the roster import to finish.');
  const op=el.dataset.action.slice(7),pid=R.pid;
  if(op==='page'){R.page=Math.max(0,Number(el.dataset.page)||0);C.render();return true;}
  if(op==='student-edit'){
   if(R.preview)throw Error('Finish or cancel the roster import first.');
   if(R.editDirty&&!await C.confirm('Discard the unsaved student edit?'))return true;
   const student=R.data.students.find(s=>s.id===el.dataset.id);if(!student)throw Error('Refresh the roster first.');
   R.editing=student.id;R.edit={name:student.name,netid:student.netid,section:student.section};R.editDirty=false;C.render();return true;
  }
  if(op==='student-cancel'){R.editing=null;R.edit=null;R.editDirty=false;C.render();return true;}
  if(op==='student-save'||op==='student-remove'){
   if(R.preview)throw Error('Finish or cancel the roster import first.');
   if(op==='student-save'&&!R.editing)throw Error('Select a student first.');
   const id=op==='student-save'?R.editing:el.dataset.id,student=R.data.students.find(s=>s.id===id);
   if(!student)throw Error('Refresh the roster first.');
   if(op==='student-remove'&&!await C.confirm('Remove '+student.name+' ('+student.netid+') from this exam roster?'+(student.matchedExams?' Their existing exam match will need review.':'')))return true;
   R.busy=true;R.error='';C.render();
   try{
    const value=await C.api('/api/projects/'+pid+'/roster/student'+(op==='student-remove'?'/remove':''),{studentId:id,rosterHash:R.data.rosterHash,confirmed:true,...(op==='student-save'?{student:R.edit}:{})});
    if(R.pid!==pid)return true;
    R.data=value;R.editing=null;R.edit=null;R.editDirty=false;
    if(C.S.version?.project_id===pid)C.S.version.roster=value;
    window.GScopeMatching?.rosterChanged?.(pid);window.GScopeWorkflow?.rosterChanged?.(pid);
    C.message(op==='student-remove'?'Student removed from this exam roster.':'Student saved.'+(value.affectedMatches?' Review the affected exam match.':''));
   }catch(error){if(R.pid===pid)R.error=error.message;throw error;}finally{R.busy=false;C.render();}
   return true;
  }
  if(op==='reuse'){
   if(R.editDirty)throw Error('Save or cancel the student edit first.');
   const source=R.sources.find(s=>s.id===R.reuseSource);if(!source)throw Error('Choose a previous exam.');
   R.busy=true;R.error='';C.render();
   try{R.preview=await C.api('/api/projects/'+pid+'/roster-reuse',{sourceProjectId:source.id,sourceRosterHash:source.rosterHash});R.includeGuests=null;}
   finally{R.busy=false;C.render();}return true;
  }
  if(op==='retry'){R.error='';R.data=null;await mount(pid);return true;}
  if(op==='cancel'){R.preview=null;R.error='';C.render();return true;}
  if(op==='apply'){
   if(!R.preview||R.preview.skippedRows)throw Error('Preview a valid Gradescope roster first.');
   if(R.preview.guestStudents&&R.includeGuests===null)throw Error('Choose whether Guest/unmapped students belong to this exam.');
   R.busy=true;R.error='';C.render();
   try{
    const value=await C.api('/api/projects/'+pid+'/roster/apply',{previewId:R.preview.id,confirmed:true,includeGuests:R.preview.guestStudents?R.includeGuests:false});
    if(R.pid===pid){R.data=value;R.preview=null;if(C.S.version?.project_id===pid)C.S.version.roster=value;window.GScopeMatching?.rosterChanged?.(pid);window.GScopeWorkflow?.rosterChanged?.(pid);}
    C.message('Exam roster confirmed: '+value.count+' students.');
   }catch(error){if(R.pid===pid)R.error=error.message;throw error;}finally{R.busy=false;C.render();}
  }
  return true;
 }
 async function change(el){
  if(el.id==='gs-roster-reuse'){R.reuseSource=el.value;C.render();return true;}
  if(el.id==='gs-roster-search'||el.id==='gs-roster-section'){const search=el.id==='gs-roster-search',position=el.selectionStart;R[search?'query':'section']=el.value;R.page=0;C.render();if(search){const input=typeof document.querySelector==='function'?document.querySelector('#gs-roster-search'):null;input?.focus?.();if(Number.isInteger(position))input?.setSelectionRange?.(position,position);}return true;}
  if(el.dataset?.rosterEdit&&R.edit){R.edit[el.dataset.rosterEdit]=el.value;R.editDirty=true;return true;}
  if(el.id==='gs-roster-guests'){R.includeGuests=el.value==='include'?true:el.value==='exclude'?false:null;C.render();return true;}
  if(el.id!=='gs-roster-file')return false;
  const file=el.files?.[0];if(!file)return true;
  if(file.size>20000000)throw Error('Choose a Gradescope CSV up to 20 MB.');
  if(R.editDirty)throw Error('Save or cancel the student edit before importing a roster.');
  if(R.busy)throw Error('Wait for the current roster import.');
  const pid=R.pid,request=++R.request;R.busy=true;R.error='';R.preview=null;C.render();
  try{
   const response=await fetch('/api/projects/'+pid+'/roster-upload?'+new URLSearchParams({name:file.name}),{method:'POST',headers:{'X-App-Token':C.S.boot.token,'Content-Type':'application/octet-stream'},body:file,credentials:'same-origin',redirect:'error'});
   const value=await response.json();if(!response.ok)throw Error(value.error||'The Gradescope CSV could not be read.');
   if(R.pid===pid&&R.request===request){R.preview=value;R.includeGuests=null;}
  }catch(error){if(R.pid===pid&&R.request===request)R.error=error.message;throw error;}finally{R.busy=false;C.render();}
  return true;
 }
 return {init:c=>C=c,view,mount,action,change,input:el=>{if(el.id==='gs-roster-search'){change(el);return true;}if(el.dataset?.rosterEdit&&R.edit){R.edit[el.dataset.rosterEdit]=el.value;R.editDirty=true;return true;}return false;},checkView:()=>'',candidate:()=>null,dirty:()=>!!R.preview||R.busy||R.editDirty,discard:()=>{R.preview=null;R.error='';R.editing=null;R.edit=null;R.editDirty=false;R.request++;}};
})();
