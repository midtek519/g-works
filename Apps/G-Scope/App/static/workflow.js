'use strict';
window.GScopeWorkflow=(()=>{
  let C,draftQuestionId=0,dropsBound=false;const W={intake:null,projectId:null,layout:null,layoutVersion:null,field:'name',page:1,rect:null,image:null,zoom:70,hoverField:null,hoverAction:'',boxDragging:false,job:null,drafts:new Map(),boundaryDrafts:new Map(),cleanup:null,bulk:null,intakeLoading:false,uploading:false,savedLayout:null,layoutDirty:false,regionDirty:false,saving:false,focusSelection:false,scanLoadError:false,openScans:new Set(),selectedScans:new Set(),selectedRecords:new Set(),splitSettings:new Set(),scanOffsets:new Map(),scanPreview:null,preparing:false,prepareError:'',prepareProgress:null,scanProgress:null,uploadProgress:null,prepareJob:null,preparedProject:null,showMatching:false,splitStarts:new Map(),sourceVersionDrafts:new Map(),packetVersions:new Map(),openSubmissionPages:new Set(),reviewingScans:false};
  const $=s=>document.querySelector(s),all=s=>[...document.querySelectorAll(s)];
  const ctx=()=>C,escape=v=>C.esc(v),btn=(t,a,e='',p=false)=>C.button(t,'gs-'+a,e,p);
  const bytes=n=>n>1048576?(n/1048576).toFixed(1)+' MB':Math.round((n||0)/1024)+' KB';
  function isIntake(){return !!W.projectId&&C.S.view==='projects'&&!C.S.version;}
  function invalidateLayout(){W.layoutVersion=null;}
  function reset(){W.projectId=null;W.intake=null;W.cleanup=null;W.removingSource=null;W.layoutVersion=null;W.layout=null;W.savedLayout=null;W.layoutDirty=false;W.regionDirty=false;W.field='name';W.page=1;W.rect=null;W.intakeLoading=false;W.drafts.clear();W.boundaryDrafts.clear();W.openScans.clear();W.selectedScans.clear();W.selectedRecords.clear();W.splitSettings.clear();W.scanOffsets.clear();W.scanPreview=null;W.scanLoadError=false;W.preparedProject=null;W.prepareError='';W.prepareProgress=null;W.scanProgress=null;W.uploadProgress=null;W.prepareJob=null;W.showMatching=false;W.lastStage=null;W.splitStarts.clear();W.sourceVersionDrafts.clear();W.packetVersions.clear();W.openSubmissionPages.clear();W.reviewingScans=false;}
  function discard(){W.packetVersions.clear();W.sourceVersionDrafts.clear();W.splitStarts.clear();W.drafts.clear();W.boundaryDrafts.clear();W.regionDirty=false;W.layoutDirty=false;if(W.savedLayout)W.layout=structuredClone(W.savedLayout);if(C.S.version){const saved=getRegion();W.rect=saved?.rect?[...saved.rect]:null;W.page=saved?.page||1;}}

  async function refresh(){if(W.projectId){const pid=W.projectId;try{const [intake,bulk]=await Promise.all([C.api('/api/projects/'+pid+'/intake'),C.api('/api/projects/'+pid+'/batch')]);if(W.projectId!==pid)return;W.intake=intake;W.bulk=bulk;W.scanLoadError=false;const vid=C.S.version?.id;if(vid&&C.S.version.project_id===pid){const version=await C.api('/api/versions/'+vid);if(C.S.version?.id===vid){C.S.version=version;if(!C.S.dirty)C.S.questions=structuredClone(version.questions);}}}catch(error){if(W.projectId===pid)W.scanLoadError=true;throw error;}}}
  const selectedSources=()=>all('[name="intake-source"]:checked').map(x=>x.value);
  function recordValue(row){return {versionId:row.querySelector('[data-record="versionId"]').value,name:row.querySelector('[data-record="name"]').value,netid:row.querySelector('[data-record="netid"]').value};}
  function collect(){for(const row of all('[data-intake-booklet]')){const edited=[...row.querySelectorAll('[data-record][data-edited="true"]')];if(edited.length){const draft={...W.drafts.get(row.dataset.intakeBooklet)};for(const el of edited)draft[el.dataset.record]=el.value;W.drafts.set(row.dataset.intakeBooklet,draft);}}}
  const boundary=f=>({...f.layout,confirmed:false,...W.boundaryDrafts.get(f.id)});
  function input(el){if(window.GScopeMatching?.input?.(el))return;window.GScopeRosters?.input?.(el);if(el.dataset.intakeLayout){const row=el.closest('[data-intake-source]');if(row){const id=row.dataset.intakeSource,p={...W.boundaryDrafts.get(id)};p[el.dataset.intakeLayout]=el.type==='checkbox'?el.checked:Number(el.value);if(el.dataset.intakeLayout!=='confirmed'){p.confirmed=false;const check=row.querySelector('[data-intake-layout="confirmed"]');if(check)check.checked=false;}W.boundaryDrafts.set(id,p);C.S.dirty=true;}return;}if(el.dataset.record&&el.closest('[data-intake-booklet]')){el.dataset.edited='true';C.S.dirty=true;collect();}}
  const B={data:null,loading:false,busy:false,error:'',course:'',term:'',selected:new Set(),preview:null,notice:''};
  const cleanupTerms=()=>[...new Set((B.data?.projects||[]).filter(p=>!B.course||p.course===B.course).map(p=>p.term))].sort();
  const cleanupAssignments=()=>(B.data?.projects||[]).filter(p=>(!B.course||p.course===B.course)&&(!B.term||p.term===B.term));
  async function loadCleanupOptions(){if(B.loading)return;B.loading=true;B.error='';try{B.data=await C.api('/api/scans/cleanup-options');if(!B.data.projects.some(p=>p.course===B.course)){B.course=B.data.projects[0]?.course||'';B.term='';}}catch(error){B.error='The stored-scan list could not be loaded.';}finally{B.loading=false;C.render();}}
  function cleanupSettingsView(){
    const disabled=B.busy?'disabled':'',courses=[...new Set((B.data?.projects||[]).map(p=>p.course))].sort(),assignments=cleanupAssignments(),p=B.preview;
    return `<section class="card gs-bulk-cleanup"><h2>Scan storage cleanup</h2><p class="help">Remove managed exam-scan copies for selected assignments. Choose a course and semester, then select assignments or the entire semester. Original PDFs outside G-Scope, blank exams, rubrics, answer keys, identities and saved grading reviews are retained. Deleted scans cannot be previewed or graded again until restored.</p>${B.error?`<p class="notice warning">${escape(B.error)}</p>${btn('Retry loading assignments','bulk-cleanup-refresh')}`:''}${B.notice?`<p class="notice" role="status">${escape(B.notice)}</p>`:''}${!B.data?`<p>${B.loading?'Loading stored scans…':'Preparing scan storage…'}</p>`:`<div class="row"><label>Course<select id="gs-cleanup-course" ${disabled}>${courses.map(course=>C.option(course,'Math '+course,B.course)).join('')}</select></label><label>Semester<select id="gs-cleanup-term" ${disabled}>${C.option('','All semesters',B.term)}${cleanupTerms().map(term=>C.option(term,C.termLabel?C.termLabel(term):term,B.term)).join('')}</select></label></div><div class="row">${btn(B.term?'Select all assignments this semester':'Select all shown assignments','bulk-cleanup-select',disabled)}${btn('Clear selection','bulk-cleanup-clear',disabled)}<span class="help">${B.selected.size} assignments selected</span></div><div class="gs-cleanup-assignments">${assignments.map(a=>`<label class="check"><input type="checkbox" name="gs-cleanup-assignment" value="${a.id}" ${B.selected.has(a.id)?'checked':''} ${disabled}><span><strong>${escape(a.title)}</strong> · ${escape(C.termLabel?C.termLabel(a.term):a.term)} · ${a.fileCount} stored scan copies</span></label>`).join('')||'<p class="help">No stored scan copies for this selection.</p>'}</div>${btn(B.busy?'Working…':'Preview cleanup','bulk-cleanup-preview',`${disabled} ${B.selected.size?'':'disabled'}`)}${p?`<div class="notice warning"><h3>Review permanent scan deletion</h3><p><strong>${p.fileCount} scan copies · ${bytes(p.totalBytes)}</strong> across ${p.assignments.length} assignments. ${p.affectedRuns} saved runs reference these scans.</p>${p.assignments.map(a=>`<details><summary>Math ${escape(a.course)} · ${escape(C.termLabel?C.termLabel(a.term):a.term)} · ${escape(a.title)} · ${a.preview.fileCount} copies</summary><ul>${a.preview.files.map(f=>`<li>${escape(f.name)} · ${bytes(f.bytes)}${f.available?'':' · already unavailable'}${f.managedPath?`<br><code>${escape(f.managedPath)}</code>`:''}</li>`).join('')}</ul></details>`).join('')}<label class="check"><input type="checkbox" id="gs-bulk-cleanup-confirm" ${disabled}>I want to permanently delete the managed scan copies listed above.</label>${btn('Delete listed scan copies','bulk-cleanup-execute',`${disabled} ${p.fileCount?'':'disabled'}`)}</div>`:''}`}</section>`;
  }
  async function bulkCleanupAction(op){
    if(!op.startsWith('bulk-cleanup-'))return false;if(B.busy)throw Error('Wait for scan cleanup to finish.');
    if(op==='bulk-cleanup-refresh'){B.preview=null;B.selected.clear();await loadCleanupOptions();return true;}
    if(op==='bulk-cleanup-select'){for(const a of cleanupAssignments())B.selected.add(a.id);B.preview=null;C.render();return true;}
    if(op==='bulk-cleanup-clear'){B.selected.clear();B.preview=null;C.render();return true;}
    if(op==='bulk-cleanup-preview'){
      if(!B.selected.size)throw Error('Select assignments to preview.');B.busy=true;B.preview=null;B.notice='';C.render();
      try{B.preview=await C.api('/api/scans/cleanup-preview',{projectIds:[...B.selected]});}finally{B.busy=false;C.render();}return true;
    }
    if(op==='bulk-cleanup-execute'){
      if(!B.preview||!$('#gs-bulk-cleanup-confirm')?.checked)throw Error('Review the preview and check the permanent-deletion confirmation.');
      const p=B.preview;B.busy=true;C.render();
      try{const result=await C.api('/api/scans/cleanup',{projectIds:p.projectIds,previewHash:p.previewHash,confirmed:true});B.notice=result.complete?'Deleted '+result.removedFiles+' managed scan copies. Rubrics, saved reviews and external originals were retained.':result.error||'Cleanup stopped. Preview the remaining copies before retrying.';B.preview=null;B.selected.clear();W.intake=null;W.scanLoadError=false;await loadCleanupOptions();}catch(error){B.preview=null;throw error;}finally{B.busy=false;C.render();}return true;
    }
    return true;
  }
  function cleanupSettingsChange(el){
    if(!['gs-cleanup-course','gs-cleanup-term'].includes(el.id)&&el.name!=='gs-cleanup-assignment')return false;
    if(B.busy)return true;B.preview=null;B.notice='';
    if(el.id==='gs-cleanup-course'){B.course=el.value;B.term='';B.selected.clear();}
    else if(el.id==='gs-cleanup-term'){B.term=el.value;B.selected.clear();}
    else if(el.checked)B.selected.add(el.value);else B.selected.delete(el.value);C.render();return true;
  }

  function view(){
    if(!W.intake)return W.scanLoadError?`<section class="card notice warning"><p>The scan list could not be loaded. Uploaded files are retained.</p>${btn('Retry loading scan list','refresh-inbox')}</section>`:'<section class="card"><p>Loading scans…</p></section>';
    if(W.showMatching&&W.intake.roster?.ready)return window.GScopeMatching?.view?.(W.projectId)||'';
    const I=W.intake,p=C.S.projects.find(p=>p.id===W.projectId);
    if(!I.roster?.ready)return `<section class="card"><h2>Exam roster required</h2><p>Upload and confirm the Gradescope roster before adding scans or matching students.</p>${C.button('Open exam roster','tab','data-tab="roster"',true)}</section>${!W.showMatching?I.sources.map((f,fi)=>scanBatch(f,fi)).join(''):''}${cleanupView()}`;
    return `<div class="toolbar">${btn('← Assignments','close-inbox')}<strong>${escape(p?.course)} · ${escape(C.termLabel?C.termLabel(p?.term):p?.term)} · ${escape(p?.title)} · Exam scans</strong>${!C.S.version?btn('Student matching','show-matching'):''}</div>
    ${window.GScopeAISettings?.readinessView?.()||''}<section class="card gs-intake-upload"><h2>Exam scans</h2><p class="help">${I.pagesPerExam?I.pagesPerExam+' pages per exam · from the blank exam. Uploads split automatically.':'The blank exam sets one page count for this assignment.'}</p>${window.GScopeProgress?.view?.(W.preparing?{message:'Preparing scan splits…'}:W.prepareJob?W.prepareProgress||{message:'Reading printed versions with local OCR…'}:W.scanProgress,{id:'gs-scan-progress'})||''}${W.prepareJob?btn('Stop reading','stop-versions'):''}${W.prepareError?`<p class="notice warning">${escape(W.prepareError)}</p>`:''}<div class="gs-scan-drop" data-gs-scan-drop tabindex="0" role="button" aria-label="Drop scan PDFs here or choose files" aria-busy="${W.uploading}"><strong>Drag and drop scan PDFs here</strong><p class="help">Upload one or more PDFs. A PDF may contain different exam versions.</p><p class="help">Keep each student's complete exam together, with pages in order, including intended blank pages.</p><label>Or choose scan PDFs<input id="gs-intake-upload" type="file" accept="application/pdf,.pdf" multiple ${W.uploading?'disabled':''}></label><p id="gs-upload-status" class="help">Your original files stay unchanged.</p>${W.uploading&&!W.preparing&&!W.prepareJob?(window.GScopeProgress?.view?.(W.uploadProgress,{id:'gs-upload-progress'})||''):''}</div><p class="help">Managed copies: <code>${escape(I.folder)}</code>. Files you upload from another folder stay there unchanged.</p>${W.scanLoadError?`<div class="notice warning">The files were uploaded, but the scan list could not refresh. ${btn('Retry loading scan list','refresh-inbox')}</div>`:''}</section>
    ${scanReviewToolbar()}${I.sources.map((f,fi)=>scanBatch(f,fi)).join('')}
${cleanupView()}${scanPreviewView()}`;
  }
  function stageView(stage){if(W.projectId!==C.S.version?.project_id)return '<section class="card"><p>Loading assignment scans…</p></section>';if(stage==='match'&&!W.intake?.roster?.ready)return view();if(stage==='match')return window.GScopeMatching?.view?.(W.projectId)||'';return `<div class="gs-stage gs-stage-${stage}">${view()}</div>`;}
  const scanAvailable=f=>!f.deleted&&f.available!==false;
  function scanStrip(f,b,key){
    if(!scanAvailable(f))return '<p class="help">Scan bytes unavailable. Saved submission records are retained.</p>';
    const limit=40,total=b.pages,offset=Math.min(W.scanOffsets.get(key)||0,Math.max(0,Math.floor((total-1)/limit)*limit));
    return `<div class="gs-scan-pages" aria-label="Numbered scan pages">${Array.from({length:Math.min(limit,total-offset)},(_,i)=>{const number=offset+i+1,page=b.startPage+number-2;return `<button class="gs-scan-thumb" data-action="gs-scan-zoom" data-source="${f.id}" data-page="${page}" data-start="${b.startPage-1}" data-count="${total}" aria-label="Enlarge submission page ${number}, PDF page ${page+1}" title="Enlarge page ${number} · PDF page ${page+1}"><img src="/api/intake-files/${f.id}/thumbnail/${page}" alt="Scanned page ${number}" loading="lazy" decoding="async" width="100" height="130"><span class="gs-scan-page-number">${number}</span><span class="gs-scan-zoom-icon" aria-hidden="true"><svg viewBox="0 0 20 20"><circle cx="8" cy="8" r="5"></circle><path d="m12 12 5 5M5 8h6M8 5v6"></path></svg></span><span class="gs-scan-thumb-error" hidden>Preview unavailable</span></button>`;}).join('')}</div>${total>limit?`<div class="row gs-scan-page-range"><span class="help">Pages ${offset+1}–${Math.min(offset+limit,total)} of ${total}</span>${btn('Previous pages','scan-pages',`data-key="${key}" data-offset="${Math.max(0,offset-limit)}" ${offset===0?'disabled':''}`)}${btn('Next pages','scan-pages',`data-key="${key}" data-offset="${offset+limit}" ${offset+limit>=total?'disabled':''}`)}</div>`:''}`;
  }
  function evidenceFor(f,b){return (f.versionEvidence?.exams||[]).find(e=>e.startPage===b.startPage);}
  function packetChoice(f,b){
    if(b.assignedBookletId)return b.versionId||'';
    if(W.packetVersions.has(b.id))return W.packetVersions.get(b.id);
    const evidence=evidenceFor(f,b);return evidence?.status==='read'?evidence.versionId||'':'';
  }
  function packetVersionView(f,b){
    const value=packetChoice(f,b),assigned=!!b.assignedBookletId;
    return `<label class="gs-packet-version">Version<select data-packet-version="${b.id}" aria-label="Version for submission starting on PDF page ${b.startPage}" ${assigned||W.reviewingScans?'disabled':''}><option value="">Choose version</option>${W.intake.versions.map(v=>C.option(v.id,v.label,value)).join('')}</select></label>`;
  }
  function sourceReviewPlan(f){
    if(!scanAvailable(f)||!(f.booklets||[]).length)return null;
    const starts=f.booklets.map(b=>b.startPage-1),edited=W.splitStarts.get(f.id);
    if(edited&&JSON.stringify(edited)!==JSON.stringify(starts))return null;
    const regular=f.booklets.every(b=>b.pages===W.intake.pagesPerExam)&&starts[0]===0&&f.booklets.at(-1).startPage-1+f.booklets.at(-1).pages===f.pages;
    if(!f.layout?.confirmed&&!regular)return null;
    const packetVersions=f.booklets.filter(b=>!b.assignedBookletId&&b.pages===W.intake.pagesPerExam&&packetChoice(f,b)).map(b=>({packetId:b.id,versionId:packetChoice(f,b),...(W.packetVersions.has(b.id)?{manual:true}:{})}));
    if(!packetVersions.length&&f.layout?.confirmed)return null;
    return {sourceId:f.id,sourceHash:f.sha256,evidenceHash:f.versionEvidence?.hash||'',starts,packetVersions,confirmSplits:true};
  }
  function reviewPlan(sourceId=null){
    const sources=(W.intake?.sources||[]).filter(f=>!sourceId||f.id===sourceId).map(sourceReviewPlan).filter(Boolean);
    return {sources,packets:sources.reduce((n,s)=>n+s.packetVersions.length,0),splits:sources.filter(s=>!W.intake.sources.find(f=>f.id===s.sourceId).layout?.confirmed).length,manual:sources.reduce((n,s)=>n+s.packetVersions.filter(p=>p.manual).length,0)};
  }
  function scanReviewToolbar(){
    const plan=reviewPlan(),pending=(W.intake?.sources||[]).flatMap(f=>(f.booklets||[]).filter(b=>!b.assignedBookletId));
    if(!W.intake?.sources?.length)return '';
    return `<section class="card gs-scan-review-toolbar"><div><strong>Review scans</strong><span class="help">${plan.packets?plan.packets+' version'+(plan.packets===1?'':'s')+' ready to confirm':pending.length?'Choose a version for the remaining exams.':'All complete exams are confirmed.'}${plan.splits?' · '+plan.splits+' PDF page boundaries to confirm':''}${plan.manual?' · '+plan.manual+' manual version choice'+(plan.manual===1?'':'s'):''}</span></div>${plan.sources.length?btn(W.reviewingScans?'Confirming…':'Confirm ready scans','review-scans',W.reviewingScans||W.prepareJob||W.preparing||W.intake.busy?'disabled':'',true):''}</section>`;
  }
  async function confirmReadyScans(sourceId=null){
    if(W.reviewingScans||W.prepareJob||W.preparing)return true;
    const plan=reviewPlan(sourceId),pid=W.projectId;if(!plan.sources.length)throw Error('Choose versions for complete exams, or review edited page boundaries first.');
    W.reviewingScans=true;C.render();
    try{
      const result=await C.api('/api/projects/'+pid+'/review-scans',{confirmed:true,sources:plan.sources});
      if(W.projectId!==pid)return true;
      for(const source of plan.sources){W.splitStarts.delete(source.sourceId);W.sourceVersionDrafts.delete(source.sourceId);for(const packet of source.packetVersions)W.packetVersions.delete(packet.packetId);}
      C.S.dirty=W.packetVersions.size>0||W.drafts.size>0||W.boundaryDrafts.size>0||W.layoutDirty||W.regionDirty;
      await refresh();window.GScopeMatching?.scansChanged?.(pid);
      const reviewed=result.reviewedPackets??result.assigned??plan.packets;C.message(reviewed?'Confirmed '+reviewed+' exam version'+(reviewed===1?'':'s')+'. Unresolved exams remain for review.':'Page boundaries confirmed. Choose versions for the remaining exams.');
    }finally{W.reviewingScans=false;C.render();}
    return true;
  }
  function splitReviewView(f){
    if(!scanAvailable(f)||!f.splitReview||f.layout?.confirmed)return '';
    const starts=W.splitStarts.get(f.id)||f.splitReview.starts;
    return `<details class="gs-split-review"><summary>Edit page boundaries</summary><div class="notice warning"><h3>Check suggested splits</h3><p>${escape(f.splitReview.reason||'This PDF has an unusual page count or uncertain cover positions.')}</p><p class="help">Each exam normally has ${f.splitReview.expectedPages} pages. Suggested cover pages: ${starts.map(n=>n+1).join(', ')}. Confirming preserves these PDF pages; it does not fill in a missing page.</p>${f.splitReview.coverScores?.length?`<details><summary>Cover comparison details</summary><p class="help">Structural match threshold: ${Math.round((f.splitReview.coverThreshold||.78)*100)}%. ${f.splitReview.coverScores.filter(row=>row.matched||starts.includes(row.page-1)).map(row=>'Page '+row.page+': '+Math.round(row.score*100)+'%').join('; ')}. Comparison uses printed layout; it does not verify every interior page.</p></details>`:''}<label>Cover pages (PDF page numbers, separated by commas)<input data-split-covers="${f.id}" value="${starts.map(n=>n+1).join(', ')}" aria-label="Suggested cover page numbers"></label>${btn('Save edited boundaries','confirm-splits',`data-id="${f.id}"`,true)}</div></details>`;
  }
  async function prepareScans(){
    if(W.preparing||!W.projectId)return;const pid=W.projectId;W.preparing=true;W.preparedProject=pid;W.prepareError='';W.prepareProgress=null;W.scanProgress=null;C.render();
    try{const result=await C.api('/api/projects/'+pid+'/prepare-scans',{});if(W.projectId!==pid)return;W.prepareError=(result.issues||[]).join(' ');if(result.job){W.prepareJob={id:result.job.id,projectId:pid};watchScanPreparation();}else if(W.intake?.sources?.length&&!W.prepareError)W.scanProgress={state:'done',message:'Scan preparation complete · Review detected versions',completed:1,total:1};await refresh();}
    catch(error){if(W.projectId===pid)W.prepareError=error.message;}
    finally{W.preparing=false;C.render();}
  }
  async function watchScanPreparation(){
    const job=W.prepareJob;if(!job)return;
    try{
      const value=await C.api('/api/jobs/'+job.id);if(W.prepareJob!==job)return;
      W.prepareProgress=typeof value.progress==='string'?{message:value.progress}:value.progress||{message:'Reading printed versions locally…'};
      if(['done','error','cancelled'].includes(value.status)&&!value.stopping){
        W.prepareJob=null;
        if(W.projectId===job.projectId){
          const p=W.prepareProgress,total=p.total||1;
          W.scanProgress={...p,state:value.status,message:value.status==='done'?'Scan preparation complete · Review detected versions':value.status==='cancelled'?'Version reading paused. Completed results are saved.':'Version reading stopped. Completed results are saved.',...(value.status==='done'?{completed:total,total}:{})};
          if(value.status==='error')W.prepareError=value.error||'Version identification stopped. Choose versions manually.';
          else if(value.result?.visionUnavailable)W.prepareError='OCR finished. Some markers need review because local vision was unavailable. Clear OCR results are ready to confirm.';
          await refresh();window.GScopeMatching?.scansChanged?.(W.projectId);C.render();
        }return;
      }
      if(W.projectId===job.projectId){await refresh();C.render();}setTimeout(watchScanPreparation,1400);
    }catch(error){W.prepareJob=null;if(W.projectId===job.projectId){W.scanProgress={message:'Version reading stopped. Completed results are saved.'};W.prepareError='Version identification stopped. Choose versions manually.';C.render();}}
  }

  function versionSummary(f){
    const counts=new Map();let unresolved=0;
    for(const b of f.booklets||[]){const label=W.intake.versions.find(v=>v.id===packetChoice(f,b))?.label;if(label)counts.set(label,(counts.get(label)||0)+1);else unresolved++;}
    return `<div class="gs-scan-version-summary" aria-label="Version summary">${[...counts].map(([label,count])=>`<span class="gs-version-count">Version ${escape(label)} · ${count}</span>`).join('')}${unresolved?`<span class="gs-version-count unresolved">${unresolved} need a version</span>`:''}</div>`;
  }
  function sourceVersionView(f){
    if(!scanAvailable(f))return '';
    const value=W.sourceVersionDrafts.get(f.id)||'',saving=W.reviewingScans;
    return `<div class="gs-source-version-panel"><div class="row">${f.removedExams?btn('Restore removed exams ('+f.removedExams+')','source-reimport',`data-id="${f.id}" ${W.prepareJob||W.preparing||saving?'disabled':''}`):''}${btn(W.prepareJob?'Reading versions…':'Read versions again','source-version-check',`data-id="${f.id}" ${!f.booklets?.length||W.prepareJob||W.preparing||saving?'disabled':''}`)}<details class="gs-pdf-version-override"><summary>Set one version for this PDF</summary><div class="row"><label>Version<select data-source-version="${f.id}" ${saving?'disabled':''}><option value="">Choose version</option>${W.intake.versions.map(v=>C.option(v.id,v.label,value)).join('')}</select></label>${btn('Set for unconfirmed exams','source-version',`data-id="${f.id}" ${!value||saving?'disabled':''}`)}</div><p class="help">Sets the individual choices below. Confirm ready scans saves them together.</p></details></div></div>`;
  }
  function splitState(f){
    const packets=f.booklets||[],expected=W.intake.pagesPerExam;
    if(!scanAvailable(f))return {kind:'danger',text:'Scan unavailable',icon:'!'};
    if(!packets.length)return {kind:expected?'review':'pending',text:expected?(f.removedExams?'All exams removed':'Split preparation needed'):'Waiting for blank exam page count',icon:expected?'⚠':''};
    if(expected&&packets.some(b=>b.pages!==expected))return {kind:'danger',text:'Check page count',icon:'!'};
    if(!f.layout?.confirmed)return {kind:'review',text:'Review page boundaries',icon:'⚠'};
    const unassigned=packets.filter(b=>!b.assignedBookletId),unknown=unassigned.filter(b=>!packetChoice(f,b));
    if(unknown.length)return {kind:'review',text:unknown.length+' need a version',icon:'⚠'};
    if(unassigned.length)return {kind:'pending',text:'Ready to confirm',icon:''};
    return {kind:'ready',text:'Confirmed',icon:''};
  }
  function packetRow(f,b,i){
    const evidence=evidenceFor(f,b),name=b.identity?.name||'',netid=b.identity?.netid||'',open=W.openSubmissionPages.has(b.id),complete=!W.intake.pagesPerExam||b.pages===W.intake.pagesPerExam;
    const status=!complete?b.pages+' / '+W.intake.pagesPerExam+' pages':b.assignedBookletId?'Confirmed':W.packetVersions.has(b.id)?'Manual choice':packetChoice(f,b)?'Detected':'Choose version';
    return `<article class="gs-scan-submission" id="scan-submission-${b.id}"><div class="gs-scan-submission-heading"><strong class="gs-submission-number">Exam ${i+1}</strong><div class="gs-submission-student">${name?`<button class="gs-scan-submission-title" data-action="gs-scan-match" data-source="${f.id}" data-id="${b.id}">${escape(name)}</button>${netid?`<span class="help">${escape(netid)}</span>`:''}${!b.identity.reviewed?'<span class="help">Match needs review</span>':''}`:'<span class="help">Not matched to a student</span>'}</div>${packetVersionView(f,b)}<span class="help gs-submission-pages">PDF pages ${b.startPage}–${b.startPage+b.pages-1}</span><span class="gs-scan-status ${b.assignedBookletId?'assigned':!complete?'danger':'unassigned'}">${escape(status)}</span>${btn(open?'Hide pages':'Show pages','submission-pages',`data-id="${b.id}" aria-expanded="${open}" aria-controls="submission-pages-${b.id}"`)}</div>${open?`<div id="submission-pages-${b.id}" class="gs-submission-page-details">${scanStrip(f,b,b.id)}</div>`:''}${!complete?'<p class="help gs-row-warning">Correct missing or extra pages before grading this exam.</p>':''}${(open||!packetChoice(f,b))&&evidence?.reason?`<details class="gs-exam-version-evidence"><summary>Version reading details${evidence.method?' · '+escape(evidence.method):''}</summary><p class="help">${escape(evidence.reason)}${Number.isFinite(evidence.milliseconds)?' ('+Math.round(evidence.milliseconds)+' ms)':''}</p></details>`:''}</article>`;
  }
  function scanBatch(f,index){
    const open=W.openScans.has(f.id),booklets=f.booklets||[],state=splitState(f);
    const date=new Date(f.created),dateText=Number.isNaN(date.getTime())?'':date.toLocaleString();
    return `<section class="card gs-scan-batch split-${state.kind}" data-intake-source="${f.id}"><div class="gs-scan-batch-heading" data-scan-header="${f.id}"><button class="gs-scan-toggle" data-action="gs-scan-toggle" data-id="${f.id}" aria-expanded="${open}" aria-controls="scan-details-${f.id}"><span aria-hidden="true">${open?'▾':'▸'}</span> ${open?'Hide details':'Show details'}</button><strong class="gs-scan-file" title="${escape(f.name)}">PDF ${index+1} · ${escape(f.name)}</strong><span class="help">${booklets.length} exam${booklets.length===1?'':'s'} · ${f.pages} pages · ${bytes(f.bytes)}</span>${state.text?`<span class="gs-split-status ${state.kind}">${state.icon?`<span class="gs-split-symbol" aria-hidden="true">${state.icon}</span> `:''}${state.text}</span>`:''}${btn(W.removingSource===f.id?'Preparing…':'Remove PDF','scan-cleanup',`data-id="${f.id}" ${W.intake.busy||W.removingSource?'disabled':''}`)}</div>${versionSummary(f)}
    ${open?`<div id="scan-details-${f.id}" class="gs-scan-batch-details">${dateText?`<p class="help gs-scan-date">Uploaded ${escape(dateText)}</p>`:''}${sourceVersionView(f)}${splitReviewView(f)}<div class="gs-scan-submissions">${booklets.map((b,i)=>packetRow(f,b,i)).join('')||`<div class="gs-scan-unsplit"><p class="help">Link the blank exam to set this assignment's page count.</p>${scanStrip(f,{startPage:1,pages:f.pages},f.id)}</div>`}</div></div>`:''}</section>`;
  }
  function scanPreviewView(){
    const p=W.scanPreview;if(!p||p.projectId!==W.projectId||!W.intake.sources.some(f=>f.id===p.source&&scanAvailable(f)))return '';
    return `<dialog id="gs-scan-preview" class="gs-scan-preview" aria-labelledby="gs-scan-preview-title"><div class="gs-scan-preview-header"><h2 id="gs-scan-preview-title">Submission page ${p.page-p.start+1} of ${p.count} <span class="help">· PDF page ${p.page+1}</span></h2>${btn('Close','scan-preview-close','aria-label="Close page preview"')}</div><div class="gs-scan-preview-image"><img src="/api/intake-files/${p.source}/page/${p.page}" alt="Enlarged submission page ${p.page-p.start+1}"><p class="gs-scan-preview-error notice warning" hidden>This page could not be opened. Refresh the scan list to check whether the source is still available.</p></div><div class="row gs-scan-preview-navigation">${btn('← Previous page','scan-preview-step',`data-step="-1" ${p.page<=p.start?'disabled':''}`)}${btn('Next page →','scan-preview-step',`data-step="1" ${p.page>=p.start+p.count-1?'disabled':''}`)}<span class="help">Arrow keys change pages. Escape closes.</span></div></dialog>`;
  }
  function closeScanPreview(){const p=W.scanPreview;W.scanPreview=null;$('#gs-scan-preview')?.close?.();collect();C.render();if(p)$(`[data-action="gs-scan-zoom"][data-source="${p.source}"][data-page="${p.page}"]`)?.focus?.();}
  function mountScanPreview(){const dialog=$('#gs-scan-preview');if(!dialog||!W.scanPreview)return;if(!dialog.open){dialog.showModal?.();dialog.querySelector('[data-action="gs-scan-preview-close"]')?.focus?.();}dialog.oncancel=event=>{event.preventDefault();closeScanPreview();};}

  function recordRow(f,b){
    if(b.assignedBookletId)return '';
    const v={...b.proposal,...W.drafts.get(b.id)},needs=b.proposal?.needsReview;
    return `<div class="scan-row" data-intake-booklet="${b.id}" data-source="${f.id}"><label class="check"><input type="checkbox" name="intake-record" value="${b.id}" ${W.selectedRecords.has(b.id)?'checked ':''}${b.proposal&&!needs?'':'disabled'}><span>Pages ${b.startPage}–${b.startPage+b.pages-1} ${b.proposal?needs?'· recognition needs review':'· proposal ready':'· enter manually or recognize'}</span></label>${b.proposal?.reason?`<p class="help">${escape(b.proposal.reason)}</p>`:''}<div class="row"><label>Version<select data-record="versionId"><option value="">Choose version</option>${W.intake.versions.map(x=>C.option(x.id,x.label,v.versionId)).join('')}</select></label><label>Name<input data-record="name" maxlength="160" value="${escape(v.name||'')}"></label><label>NetID<input data-record="netid" maxlength="40" value="${escape(v.netid||'')}"></label></div>${window.GScopeRosters?.checkView?.(b,v)||''}<div class="row">${btn('Preview exam first page','record-preview',`data-id="${b.id}" data-source="${f.id}"`)}${btn('Confirm record & assign version','assign',`data-id="${b.id}" data-source="${f.id}"`,true)}</div><div class="gs-record-preview"></div></div>`;
  }
  function cleanupView(){const p=W.cleanup;if(!p)return '';return `<section class="card notice warning" id="gs-cleanup"><h2>${p.removePdf?'Remove PDF':'Delete managed scan copies'}</h2><p>${p.removePdf?'Remove this PDF and its submissions from the active scan list.':'Select source PDFs above first.'} This removes selected managed sources and their assigned scan copies from G-Scope and frees disk space. Uploaded originals outside G-Scope, handouts, rubrics, identities, proposals and reviews remain. Deleted scans cannot be previewed or processed again.</p>${!p.preview?btn('Preview deletion','cleanup-preview'):''}${p.preview?`<p><strong>${p.preview.fileCount} files · ${bytes(p.preview.totalBytes)}</strong></p><p>${p.preview.affectedRuns?.length||0} saved runs reference these scans. Their proposals and reviews remain.</p><ul>${p.preview.files.map(f=>`<li>${escape(f.name)} · ${bytes(f.bytes)} ${f.available?'':'· already unavailable'}${f.managedPath?`<br><code>${escape(f.managedPath)}</code>`:''}</li>`).join('')}</ul><label class="check"><input type="checkbox" id="gs-cleanup-confirm">I want to permanently delete these managed scan copies.</label>${btn(p.removePdf?'Remove PDF':'Delete these scan copies','cleanup-execute')}`:''}${btn('Cancel','cleanup-close')}</section>`;}
  function templateView(){
    const v=C.S.version,handout=v.files.find(f=>f.kind==='handout');
    if(!handout)return '<section class="card template-document"><h2>Mark the blank exam</h2><p>Choose a blank exam in Exam source first.</p></section>';
    const questions=C.S.questions||v.questions;
    if(W.field.startsWith('q:')&&!questions.some(q=>'q:'+q.id===W.field)){W.field='name';const saved=getRegion();W.rect=saved?.rect||null;W.page=saved?.page||1;}
    return `<section class="card template-document" aria-label="Blank exam and question boxes"><div class="template-toolbar"><div class="template-page-controls">${btn('‹','template-previous',`aria-label="Previous page" title="Previous page" ${W.page<=1?'disabled':''}`)}<label>Page<input id="gs-template-page" type="number" min="1" max="${handout.pages}" value="${W.page}" aria-label="Exam page"></label><span class="help">of ${handout.pages}</span>${btn('›','template-next',`aria-label="Next page" title="Next page" ${W.page>=handout.pages?'disabled':''}`)}${btn('Go','template-page')}</div><div class="template-zoom-controls" aria-label="Exam preview zoom">${btn('−','template-zoom-out','aria-label="Zoom out" title="Zoom out"')}<span id="gs-template-zoom-level" class="help">${W.zoom==='page'?'Fit page':W.zoom+'%'}</span>${btn('+','template-zoom-in','aria-label="Zoom in" title="Zoom in"')}${btn('Fit page','template-zoom-fit','title="Show the whole exam page"')}</div><strong id="gs-active-region">${escape(regionLabel(W.field))}</strong></div><p class="help template-hint">Click a box or its title to select it. Drag the title or interior to move; drag any edge or corner to resize. Draw in an empty area to add the next question; choose a student-detail field to draw that field instead.</p><div class="page-wrap template-page-view" data-layout-version="${escape(v.id)}" data-layout-page="${W.page}"><canvas id="gs-template-canvas" aria-label="Edit name, NetID, version and question boxes on the blank exam"></canvas></div><p id="gs-region-description" class="help template-coordinates"></p></section>`;
  }
  function templateControlsView(){
    const fields=W.layoutVersion===C.S.version?.id?W.layout?.fields||{}:{};
    return `<section class="outline-identity"><h3>Student details</h3><div class="outline-identity-buttons">${[['name','Name'],['netid','NetID'],['version','Exam version']].map(([id,title])=>btn(title+(fields[id]?' · p. '+fields[id].page:' · draw'),'select-region',`data-field="${id}" aria-pressed="${W.field===id}"`)).join('')}</div></section>`;
  }
  function boxSummary(){if(W.layoutVersion!==C.S.version?.id)return null;stashRegion();const pages=(C.S.questions||[]).filter(q=>q.rect).map(q=>q.page).concat(Object.values(W.layout?.fields||{}).filter(Boolean).map(f=>f.page));return {count:pages.length,lastPage:Math.max(0,...pages)};}
  function templateFooterView(){return `<div class="outline-save-actions">${btn('Save outline','template-save','',true)}${btn('Clear selected box','template-clear')}</div>`;}
  function regionLabel(field){if(!field.startsWith('q:'))return {name:'Student name',netid:'NetID',version:'Exam version','new-question':'Draw the next question'}[field]||'Select a box';const q=(C.S.questions||C.S.version.questions).find(q=>'q:'+q.id===field);return q?(window.GScopeOutline?.numberFor?.(q)||String((C.S.questions||C.S.version.questions).indexOf(q)+1))+' · '+q.maxPoints+' points':'Select a question';}
  function getRegion(){if(W.field.startsWith('q:')){const q=(C.S.questions||C.S.version.questions).find(q=>'q:'+q.id===W.field);return q?.rect?{page:q.page,rect:q.rect}:null;}return W.layout?.fields?.[W.field]||null;}
  function stashRegion(){
    if(!W.regionDirty)return;
    if(W.field.startsWith('q:')){const q=(C.S.questions||[]).find(q=>'q:'+q.id===W.field);if(q){q.page=W.page;q.rect=W.rect?[...W.rect]:null;q.checkedFiles=[];}}
    else if(W.layout&&['name','netid','version'].includes(W.field)){W.layout.fields={...W.layout.fields,[W.field]:W.rect?{page:W.page,rect:[...W.rect]}:null};W.layout.approved=false;W.layoutDirty=true;}
    W.regionDirty=false;
  }
  function selectRegion(field,{render=true}={}){
    if(W.layoutVersion!==C.S.version?.id)throw Error('Wait for the blank exam to finish loading.');
    stashRegion();
    if(!['name','netid','version'].includes(field)&&!(C.S.questions||[]).some(q=>q.id&&'q:'+q.id===field))throw Error('Save the outline before selecting a new question box.');
    W.field=field;W.focusSelection=true;const r=getRegion();W.page=r?.page||W.page||1;W.rect=r?.rect?[...r.rect]:null;if(render)C.render();else{W.focusSelection=false;syncRegionSelection();draw();}
  }
  function addQuestion(rect=null){
    stashRegion();const used=new Set(C.S.questions.map(q=>q.key));let n=Math.max(0,...C.S.questions.map(q=>Number(/^\d+/.exec(q.key)?.[0]||0)))+1;while(used.has(String(n)))n++;
    const q={id:'draft-'+(++draftQuestionId),key:String(n),title:'Question '+n,maxPoints:0,selectionMode:'one',items:[],guidance:'',page:W.page,rect:rect?[...rect]:null,checkedFiles:[]};
    C.S.questions.push(q);W.field='q:'+q.id;W.rect=q.rect?[...q.rect]:null;W.regionDirty=false;C.S.dirty=true;C.render();return q;
  }
  function closeBox(row,canvas){const width=canvas.getBoundingClientRect().width||canvas.width,size=18*canvas.width/width;return {x:Math.max(0,row.rect[2]*canvas.width-size),y:Math.max(0,row.rect[1]*canvas.height-size),size};}
  function removeBox(field){
    stashRegion();W.field=field;W.rect=null;W.regionDirty=true;C.S.dirty=true;stashRegion();C.render();
  }
  async function saveTemplateDraft(){
    const vid=C.S.version?.id;if(!vid||W.layoutVersion!==vid)throw Error('Wait for the blank exam to finish loading.');
    if(W.saving)return;if(W.rect&&(W.rect[2]-W.rect[0]<.01||W.rect[3]-W.rect[1]<.01))throw Error('Draw a larger box before saving.');stashRegion();if(!C.S.questions.length&&C.S.version.questions.length)throw Error('Keep at least one question in the outline before saving.');
    const questions=structuredClone(C.S.questions),tree=window.GScopeOutline?.snapshot?.(),fields=structuredClone(W.layout.fields),questionJson=JSON.stringify(questions),fieldsJson=JSON.stringify(fields),needsFields=W.layoutDirty||(!W.layout.approved&&Object.values(fields).some(Boolean));W.saving=true;
    try{
      let value=questions.length?await C.api('/api/versions/'+vid+'/questions',{questions}):await C.api('/api/versions/'+vid);
      if(tree)value=await C.api('/api/versions/'+vid+'/outline-tree',{outline:tree.outline});
      if(needsFields){const layout=await C.api('/api/versions/'+vid+'/identity-layout',{fields,approved:Object.values(fields).some(Boolean)});if(C.S.version?.id===vid){W.savedLayout=structuredClone(layout);if(JSON.stringify(W.layout.fields)===fieldsJson&&!W.regionDirty){W.layout=layout;W.layoutDirty=false;}}}
      if(C.S.version?.id!==vid)return;
      const newer=JSON.stringify(C.S.questions)!==questionJson||W.regionDirty||W.layoutDirty||window.GScopeOutline?.newer?.(tree);
      for(const q of C.S.questions){if(!q.id?.startsWith('draft-'))continue;const saved=value.questions.find(item=>item.key===q.key);if(saved){if(W.field==='q:'+q.id)W.field='q:'+saved.id;q.id=saved.id;}}
      if(!newer)await C.acceptVersion(value);else{C.S.version=value;C.S.dirty=true;C.render();}
      C.message(newer?'Outline saved. Newer edits are still unsaved.':'Outline saved.');
    }finally{W.saving=false;}
  }
  function pageRegions(){
    const rows=[];
    for(const [field,r] of Object.entries(W.layout?.fields||{}))if(r?.page===W.page&&field!==W.field)rows.push({field,rect:r.rect,label:regionLabel(field)});
    for(const q of C.S.questions||[])if(q.rect&&q.page===W.page&&'q:'+q.id!==W.field)rows.push({field:'q:'+q.id,rect:q.rect,label:regionLabel('q:'+q.id)});
    if(W.rect)rows.push({field:W.field,rect:W.rect,label:regionLabel(W.field)});
    return rows;
  }
  function syncRegionSelection(){
    for(const button of all('[data-action="gs-select-region"]')){const active=button.dataset.field===W.field;button.setAttribute('aria-pressed',String(active));button.closest?.('[data-outline-index]')?.classList.toggle('active',active);}
  }
  function labelBox(row,canvas){
    const scale=canvas.width/(canvas.getBoundingClientRect().width||canvas.width),font=12*scale,height=20*scale,c=canvas.getContext('2d');
    c.font='600 '+font+'px Segoe UI, sans-serif';
    const width=Math.min((row.rect[2]-row.rect[0])*canvas.width,((c.measureText?.(row.label)?.width)||row.label.length*font*.6)+14*scale);
    return {x:row.rect[0]*canvas.width,y:Math.max(0,row.rect[1]*canvas.height-height),width,height,font,scale};
  }
  function resizeHit(row,p,canvas){
    const b=canvas.getBoundingClientRect(),[l,t,r,d]=row.rect,x=p[0]*b.width,y=p[1]*b.height,tolerance=8;
    if(x<l*b.width-tolerance||x>r*b.width+tolerance||y<t*b.height-tolerance||y>d*b.height+tolerance)return null;
    const edges=[],left=Math.abs(x-l*b.width),right=Math.abs(x-r*b.width),top=Math.abs(y-t*b.height),bottom=Math.abs(y-d*b.height);
    if(Math.min(left,right)<=tolerance)edges.push(left<=right?'left':'right');
    if(Math.min(top,bottom)<=tolerance)edges.push(top<=bottom?'top':'bottom');
    if(!edges.length)return null;
    const cursor=edges.length===1?(edges[0]==='left'||edges[0]==='right'?'ew-resize':'ns-resize'):(edges.includes('left')===edges.includes('top')?'nwse-resize':'nesw-resize');
    return {edges,cursor};
  }
  function regionHit(p,canvas){
    const rows=pageRegions(),x=p[0]*canvas.width,y=p[1]*canvas.height;
    const contains=b=>x>=b.x&&x<=b.x+(b.width||b.size)&&y>=b.y&&y<b.y+(b.height||b.size);
    const closing=[...rows].reverse().find(row=>contains(closeBox(row,canvas)));
    if(closing)return {row:closing,mode:'delete',cursor:'pointer'};
    const active=rows.find(row=>row.field===W.field),handle=active&&resizeHit(active,p,canvas);
    if(handle)return {row:active,mode:'resize',...handle};
    const title=[...rows].reverse().find(row=>contains(labelBox(row,canvas)));
    if(title)return {row:title,mode:'move',cursor:'grab'};
    const hit=rows.filter(row=>(p[0]>=row.rect[0]&&p[0]<=row.rect[2]&&p[1]>=row.rect[1]&&p[1]<=row.rect[3])||resizeHit(row,p,canvas)).sort((a,b)=>(a.rect[2]-a.rect[0])*(a.rect[3]-a.rect[1])-(b.rect[2]-b.rect[0])*(b.rect[3]-b.rect[1]))[0];
    if(!hit)return null;
    const edge=resizeHit(hit,p,canvas);return edge?{row:hit,mode:'resize',...edge}:{row:hit,mode:'move',cursor:'grab'};
  }
  function resizeIcon(c,canvas,row,color){
    if(!c.beginPath)return;
    const scale=canvas.width/(canvas.getBoundingClientRect().width||canvas.width),x=row.rect[2]*canvas.width-3*scale,y=row.rect[3]*canvas.height-3*scale,n=9*scale,a=3.5*scale;
    c.strokeStyle=color;c.lineWidth=1.4*scale;c.beginPath();c.moveTo(x-n,y-n);c.lineTo(x,y);c.moveTo(x-n+a,y-n);c.lineTo(x-n,y-n);c.lineTo(x-n,y-n+a);c.moveTo(x-a,y);c.lineTo(x,y);c.lineTo(x,y-a);c.stroke();
  }
  function applyTemplateZoom(preserve=false){
    const canvas=$('#gs-template-canvas'),viewport=$('.template-page-view');if(!canvas?.style||!viewport?.clientWidth||!W.image)return;
    const available=Math.max(1,viewport.clientWidth-18),old=canvas.getBoundingClientRect().width||available;
    const width=W.zoom==='page'?Math.min(available,Math.max(1,viewport.clientHeight-18)*canvas.width/canvas.height):available*W.zoom/100;
    canvas.style.width=width+'px';canvas.style.height='auto';
    if(preserve){const ratio=width/old;viewport.scrollTop=Math.max(0,(viewport.scrollTop+viewport.clientHeight/2)*ratio-viewport.clientHeight/2);viewport.scrollLeft=Math.max(0,((viewport.scrollLeft||0)+viewport.clientWidth/2)*ratio-viewport.clientWidth/2);}
    const label=$('#gs-template-zoom-level');if(label)label.textContent=Math.round(width/available*100)+'%';draw();
  }
  function templateZoomPercent(){const canvas=$('#gs-template-canvas'),viewport=$('.template-page-view');return canvas&&viewport?.clientWidth?canvas.getBoundingClientRect().width/Math.max(1,viewport.clientWidth-18)*100:100;}
  function draw(){
    const canvas=$('#gs-template-canvas');if(!canvas||!W.image)return;
    const c=canvas.getContext('2d');c.drawImage(W.image,0,0);
    for(const row of pageRegions()){
      const selected=row.field===W.field,hovered=row.field===W.hoverField,bright=selected||hovered,question=row.field.startsWith('q:')||row.field==='new-question',[x,y,x1,y1]=row.rect;
      const color=question?(bright?'#287b4c':'#9aa69e'):(bright?'#7546b5':'#b0a6bf'),scale=canvas.width/(canvas.getBoundingClientRect().width||canvas.width);
      c.globalAlpha=selected&&W.boxDragging ? .55 : 1;
      c.fillStyle=question?(bright?'#38925b18':'#9aa69e0a'):(bright?'#7546b518':'#b0a6bf0a');c.strokeStyle=color;c.lineWidth=(bright?2:1)*scale;
      c.fillRect(x*canvas.width,y*canvas.height,(x1-x)*canvas.width,(y1-y)*canvas.height);c.strokeRect(x*canvas.width,y*canvas.height,(x1-x)*canvas.width,(y1-y)*canvas.height);
      const label=labelBox(row,canvas);c.font='600 '+label.font+'px Segoe UI, sans-serif';c.fillStyle=bright?color:question?'#e3e9e5':'#e9e4ef';c.fillRect(label.x,label.y,label.width,label.height);c.fillStyle=bright?'white':question?'#526157':'#655b73';c.fillText?.(row.label,label.x+6*scale,label.y+label.font+2*scale,Math.max(1,label.width-10*scale));
      const close=closeBox(row,canvas);c.fillStyle=hovered&&W.hoverAction==='delete'?'#b43d34':bright?color:question?'#e3e9e5':'#e9e4ef';c.fillRect(close.x,close.y,close.size,close.size);c.fillStyle=bright?'white':color;c.font='600 '+Math.round(close.size*.85)+'px Segoe UI, sans-serif';c.fillText?.('×',close.x+close.size*.18,close.y+close.size*.8);
      if(selected){c.fillStyle=color;for(const [a,b] of [[x,y],[x1,y],[x1,y1],[x,y1],[(x+x1)/2,y],[(x+x1)/2,y1],[x,(y+y1)/2],[x1,(y+y1)/2]])c.fillRect(a*canvas.width-3*scale,b*canvas.height-3*scale,6*scale,6*scale);}
      resizeIcon(c,canvas,row,color);c.globalAlpha=1;
    }
    const label=$('#gs-active-region');if(label)label.textContent=regionLabel(W.field);
    const d=$('#gs-region-description');if(d)d.textContent='Page '+W.page;
  }

  async function loadTemplate(){
    const vid=C.S.version?.id;if(!vid)return;
    if(W.layoutVersion!==vid){const layout=await C.api('/api/versions/'+vid+'/identity-layout');if(C.S.version?.id!==vid)return;W.layout=layout;W.savedLayout=structuredClone(layout);W.layoutDirty=false;W.regionDirty=false;W.layoutVersion=vid;const r=getRegion();W.page=r?.page||1;W.rect=r?.rect||null;C.render();return;}
    const canvas=$('#gs-template-canvas'),f=C.S.version.files.find(f=>f.kind==='handout');if(!canvas||!f)return;
    const image=new Image();W.image=null;image.onload=()=>{if($('#gs-template-canvas')!==canvas)return;W.image=image;canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;applyTemplateZoom();draw();window.GScopeOutline?.restorePage?.();if(W.focusSelection&&W.rect){const viewport=$('.template-page-view');if(viewport){const height=canvas.getBoundingClientRect().height,top=W.rect[1]*height,bottom=W.rect[3]*height;if(top<viewport.scrollTop||bottom>viewport.scrollTop+viewport.clientHeight)viewport.scrollTop=Math.max(0,top-30);}W.focusSelection=false;}};image.onerror=()=>C.message('The blank handout page could not be opened.');image.src=`/api/files/${f.id}/page/${W.page-1}`;
    let drag=null;
    const point=e=>{const r=canvas.getBoundingClientRect();return [Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))];};
    const hover=p=>{const hit=regionHit(p,canvas),field=hit?.row.field||null,action=hit?.mode||'';if(canvas.style)canvas.style.cursor=hit?.cursor||'crosshair';canvas.title=hit?(action==='delete'?'Remove ':action==='resize'?'Resize ':'Move ')+hit.row.label:'Draw a box';if(W.hoverField!==field||W.hoverAction!==action){W.hoverField=field;W.hoverAction=action;draw();}return hit;};
    canvas.onpointerdown=e=>{
      if(!W.image||e.button!==undefined&&e.button!==0)return;e.preventDefault?.();const p=point(e),hit=hover(p);
      if(hit?.mode==='delete'){removeBox(hit.row.field);return;}
      if(hit&&hit.row.field!==W.field)selectRegion(hit.row.field,{render:false});
      let mode=hit?.mode||'draw';const r=W.rect,previousField=W.field;
      if(mode==='draw'&&(W.field==='new-question'||(W.field.startsWith('q:')&&r))){stashRegion();mode='new';W.field='new-question';W.rect=null;}
      drag={point:p,rect:r?[...r]:null,mode,edges:hit?.edges||[],cursor:hit?.cursor,previousField,wasDirty:C.S.dirty,regionDirty:W.regionDirty,moved:false};
      if(canvas.style)canvas.style.cursor=mode==='move'?'grabbing':hit?.cursor||'crosshair';canvas.setPointerCapture(e.pointerId);
    };
    canvas.onpointermove=e=>{
      if(!W.image)return;const p=point(e);if(!drag){hover(p);return;}const b=canvas.getBoundingClientRect(),r=drag.rect;
      if(!drag.moved&&Math.max(Math.abs(p[0]-drag.point[0])*b.width,Math.abs(p[1]-drag.point[1])*b.height)<3)return;
      drag.moved=true;W.boxDragging=true;const dx=p[0]-drag.point[0],dy=p[1]-drag.point[1];
      if(drag.mode==='move'){const x=Math.max(-r[0],Math.min(1-r[2],dx)),y=Math.max(-r[1],Math.min(1-r[3],dy));W.rect=[r[0]+x,r[1]+y,r[2]+x,r[3]+y];}
      else if(drag.mode==='resize'){const next=[...r];if(drag.edges.includes('left'))next[0]=Math.max(0,Math.min(1,r[0]+dx));if(drag.edges.includes('right'))next[2]=Math.max(0,Math.min(1,r[2]+dx));if(drag.edges.includes('top'))next[1]=Math.max(0,Math.min(1,r[1]+dy));if(drag.edges.includes('bottom'))next[3]=Math.max(0,Math.min(1,r[3]+dy));W.rect=[Math.min(next[0],next[2]),Math.min(next[1],next[3]),Math.max(next[0],next[2]),Math.max(next[1],next[3])];}
      else W.rect=[Math.min(drag.point[0],p[0]),Math.min(drag.point[1],p[1]),Math.max(drag.point[0],p[0]),Math.max(drag.point[1],p[1])];
      C.S.dirty=true;W.regionDirty=true;draw();
    };
    canvas.onpointerup=e=>{const current=drag;drag=null;W.boxDragging=false;if(current?.mode==='new'){if(W.rect&&W.rect[2]-W.rect[0]>=.01&&W.rect[3]-W.rect[1]>=.01)addQuestion(W.rect);else{W.field=current.previousField;W.rect=getRegion()?.rect||null;W.regionDirty=false;}}else stashRegion();draw();window.GScopeOutline?.updateStatus?.();if(e)hover(point(e));if(e?.pointerId!==undefined)canvas.releasePointerCapture?.(e.pointerId);};
    const cancel=()=>{const current=drag;drag=null;if(!current)return;W.boxDragging=false;if(current.mode==='new'){W.field=current.previousField;W.rect=getRegion()?.rect||null;}else W.rect=current.rect;W.regionDirty=current.regionDirty;C.S.dirty=current.wasDirty;draw();if(canvas.style)canvas.style.cursor='crosshair';};
    canvas.onpointercancel=cancel;canvas.onlostpointercapture=()=>{if(drag)cancel();};
    canvas.onpointerleave=()=>{if(!drag){W.hoverField=null;W.hoverAction='';draw();}};


  }
  const projectPolls=new Set();
  function watchProject(pid){if(!pid||projectPolls.has(pid))return;projectPolls.add(pid);pollProject(pid);}
  async function mount(){
    if(C.S.view==='settings'&&!B.data&&!B.loading&&!B.error)await loadCleanupOptions();
    if(C.S.view==='projects'&&C.S.version&&C.S.tab==='template')await loadTemplate();
    const stage=C.S.view==='projects'?(W.showMatching?'match':C.S.version?C.S.tab:'scans'):'';
    if(C.S.view==='projects'&&C.S.version&&['scans','match'].includes(stage)&&!W.intakeLoading){
      const pid=C.S.version.project_id,entered=W.lastStage!==stage||W.projectId!==pid;
      if(entered||!W.intake&&!W.scanLoadError){W.lastStage=stage;if(W.projectId!==pid)W.scanLoadError=false;W.projectId=pid;W.intakeLoading=true;if(stage==='match')window.GScopeMatching?.scansChanged?.(pid);if(stage==='scans'){W.preparedProject=null;W.prepareError='';}try{await refresh();}finally{W.intakeLoading=false;C.render();}}
    }else if(!['scans','match'].includes(stage))W.lastStage=stage;
    mountScanPreview();
    if(C.S.view==='projects'&&W.projectId&&W.intake){
      if(stage==='match'&&W.intake.roster?.ready){await window.GScopeRosters?.mount?.(W.projectId);await window.GScopeMatching?.mount?.(W.projectId);}
      else if(stage==='scans'&&W.intake.roster?.ready&&!W.preparedProject&&!W.preparing&&!W.uploading&&!W.prepareError)await prepareScans();
    }
  }

  async function uploadScanFiles(supplied){
    if(W.uploading)throw Error('Wait for the current scan upload to finish.');
    const pid=W.projectId,files=[...supplied];if(!pid)throw Error('Open the exam scan inbox first.');if(!files.length)return;
    if(files.some(f=>!f.name?.toLowerCase().endsWith('.pdf')||f.size<=0||f.size>200000000))throw Error('Drop PDF files only, up to 200 MB each. No files were uploaded.');
    W.uploading=true;W.scanProgress=null;W.uploadProgress={message:'Importing PDFs locally…',completed:0,total:files.length};C.render();let imported=0;
    try{
      for(let i=0;i<files.length;i++){
        const f=files[i],text='Importing PDF '+(i+1)+' of '+files.length+' locally…';W.uploadProgress={message:text,completed:imported,total:files.length};C.render();
        const response=await fetch(`/api/projects/${pid}/intake-files?${new URLSearchParams({name:f.name,freshRemoved:'1'})}`,{method:'POST',headers:{'X-App-Token':C.S.boot.token,'Content-Type':'application/pdf'},body:f,credentials:'same-origin',redirect:'error'}),result=await response.json();if(!response.ok)throw Error(result.error||'Scan import failed.');imported++;W.uploadProgress.completed=imported;C.render();
      }
      if(W.projectId===pid){try{W.preparedProject=null;await prepareScans();await refresh();window.GScopeMatching?.scansChanged?.(pid);}catch(error){C.message('Imported '+imported+' PDFs. The scan list could not refresh; use Retry loading scan list.');return;}}C.message('Imported '+imported+' PDF'+(imported===1?'':'s')+' in the supplied order.');
    }catch(error){throw Error('Imported '+imported+' of '+files.length+' PDFs. '+error.message);}
    finally{W.uploading=false;C.render();}
  }
  function bindDrops(){
    if(dropsBound||!document.addEventListener)return;dropsBound=true;
    const fileDrag=event=>[...(event.dataTransfer?.types||[])].includes('Files')||!!event.dataTransfer?.files?.length;
    document.addEventListener('dragover',event=>{if(!fileDrag(event))return;const zone=event.target.closest?.('[data-gs-scan-drop]');if(!zone&&event.target.closest?.('input[type="file"]'))return;event.preventDefault();if(zone){zone.classList.add('dragover');if(event.dataTransfer)event.dataTransfer.dropEffect=W.uploading?'none':'copy';}});
    document.addEventListener('dragleave',event=>{const zone=event.target.closest?.('[data-gs-scan-drop]');if(zone&&!zone.contains(event.relatedTarget))zone.classList.remove('dragover');});
    document.addEventListener('drop',event=>{if(!fileDrag(event))return;const zone=event.target.closest?.('[data-gs-scan-drop]');if(!zone&&event.target.closest?.('input[type="file"]'))return;event.preventDefault();if(!zone){C.message('Drop PDFs in the scan upload area.');return;}zone.classList.remove('dragover');uploadScanFiles(event.dataTransfer.files).catch(error=>C.message(error.message));});
    document.addEventListener('keydown',event=>{if(event.target.matches?.('[data-gs-scan-drop]')&&['Enter',' '].includes(event.key)){event.preventDefault();if(!W.uploading)$('#gs-intake-upload')?.click();}});
    document.addEventListener('click',event=>{
      const header=event.target.closest?.('[data-scan-header]');
      if(!header||event.target.closest?.('button,a,input,select,textarea,label,summary,details,[role="button"]')||window.getSelection?.()?.toString())return;
      action({dataset:{action:'gs-scan-toggle',id:header.dataset.scanHeader}}).catch(error=>C.message(error.message));
    });
    document.addEventListener('click',event=>{const zone=event.target.closest?.('[data-gs-scan-drop]');if(zone&&!event.target.closest?.('input,label,button')&&!W.uploading)$('#gs-intake-upload')?.click();});
    document.addEventListener('keydown',event=>{if(!W.scanPreview||!event.target.closest?.('#gs-scan-preview')||event.altKey||event.ctrlKey||event.metaKey)return;if(['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();action({dataset:{action:'gs-scan-preview-step',step:event.key==='ArrowLeft'?'-1':'1'}}).catch(error=>C.message(error.message));}});
    document.addEventListener('error',event=>{const image=event.target,thumb=image.closest?.('.gs-scan-thumb');if(thumb&&image.tagName==='IMG'){image.hidden=true;const error=thumb.querySelector('.gs-scan-thumb-error');if(error)error.hidden=false;}else if(image.tagName==='IMG'&&image.closest?.('#gs-scan-preview')){image.hidden=true;const error=$('.gs-scan-preview-error');if(error)error.hidden=false;}},true);
  }
  async function change(el){
    if(window.GScopeMatching?.change?.(el))return true;
    if(el.dataset?.splitCovers){const starts=el.value.split(',').map(n=>Number(n.trim())-1);W.splitStarts.set(el.dataset.splitCovers,starts);C.S.dirty=true;return true;}
    if(el.dataset?.sourceVersion){W.sourceVersionDrafts.set(el.dataset.sourceVersion,el.value);C.render();return true;}
    if(el.dataset?.packetVersion){W.packetVersions.set(el.dataset.packetVersion,el.value);C.S.dirty=true;C.render();return true;}
    if(await window.GScopeRosters?.change?.(el))return true;
    if(cleanupSettingsChange(el))return true;
    if(el.name==='intake-source'){if(el.checked)W.selectedScans.add(el.value);else W.selectedScans.delete(el.value);return true;}
    if(el.name==='intake-record'){if(el.checked)W.selectedRecords.add(el.value);else W.selectedRecords.delete(el.value);return true;}
    if(el.id==='gs-intake-upload'){
      await uploadScanFiles(el.files);return true;
    }
    if(el.id==='gs-template-field'){selectRegion(el.value);return true;}
    if(el.dataset.intakeLayout){input(el);return true;}
    if(el.closest('[data-intake-booklet]')){input(el);return true;}return false;
  }
  async function action(el){
    if(await window.GScopeMatching?.action?.(el))return true;
    if(await window.GScopeRosters?.action?.(el))return true;const a=el.dataset.action;if(!a?.startsWith('gs-'))return false;const op=a.slice(3);
    if(await bulkCleanupAction(op))return true;
    if(op==='confirm-splits'){const f=W.intake.sources.find(f=>f.id===el.dataset.id),input=$(`[data-split-covers="${f.id}"]`),starts=input?input.value.split(',').map(n=>Number(n.trim())-1):W.splitStarts.get(f.id)||f.splitReview.starts;await C.api('/api/intake-files/'+f.id+'/confirm-splits',{starts,sourceHash:f.sha256,confirmed:true});W.splitStarts.delete(f.id);W.openScans.add(f.id);W.preparedProject=null;await prepareScans();}
    if(op==='stop-versions'){if(W.prepareJob)await C.api('/api/jobs/'+W.prepareJob.id+'/cancel',{immediate:true});return true;}
    if(op==='review-scans')return confirmReadyScans();
    if(op==='review-versions')return confirmReadyScans(el.dataset.id);
    if(op==='source-reimport'){
      if(W.prepareJob||W.preparing)return true;
      const pid=W.projectId,source=W.intake.sources.find(f=>f.id===el.dataset.id);
      if(!source||!await C.confirm('Restore the removed exams from this PDF for a fresh version check? Saved history stays available.'))return true;
      await C.api('/api/intake-files/'+source.id+'/reimport',{confirmed:true,sourceHash:source.sha256});
      if(W.projectId===pid){W.preparedProject=null;await refresh();await prepareScans();}return true;
    }
    if(op==='source-version-check'){
      if(W.prepareJob||W.preparing)return true;
      const pid=W.projectId,job=await C.api('/api/projects/'+pid+'/recognize',{sourceIds:[el.dataset.id],phase:'versions',force:true});
      if(W.projectId===pid){W.prepareError='';W.prepareProgress=null;W.scanProgress=null;W.prepareJob={id:job.id,projectId:pid};watchScanPreparation();C.render();}
    }
    if(op==='source-version'){
      const f=W.intake.sources.find(f=>f.id===el.dataset.id),value=W.sourceVersionDrafts.get(f.id);
      if(!value)throw Error('Choose a version first.');
      for(const b of f.booklets||[])if(!b.assignedBookletId&&b.pages===W.intake.pagesPerExam)W.packetVersions.set(b.id,value);
      C.S.dirty=true;C.render();C.message('Version choices updated. Review the rows, then Confirm ready scans.');return true;
    }
    if(op==='submission-pages'){const id=el.dataset.id;if(W.openSubmissionPages.has(id))W.openSubmissionPages.delete(id);else W.openSubmissionPages.add(id);C.render();return true;}
    if(op==='show-matching'){W.showMatching=true;C.render();}
    if(op==='roster-use'){const candidate=window.GScopeRosters?.candidate?.(el.dataset.id);if(!candidate)throw Error('Check this name against the roster again.');W.drafts.set(el.dataset.id,{...W.drafts.get(el.dataset.id),name:candidate.name,netid:candidate.netid});C.S.dirty=true;C.render();}
    if(op==='scan-toggle'){collect();const id=el.dataset.id;if(W.openScans.has(id))W.openScans.delete(id);else W.openScans.add(id);C.render();}
    if(op==='scan-split'){collect();const id=el.dataset.id;if(W.splitSettings.has(id))W.splitSettings.delete(id);else W.splitSettings.add(id);C.render();}
    if(op==='scan-pages'){collect();const offset=Number(el.dataset.offset);if(Number.isInteger(offset)&&offset>=0)W.scanOffsets.set(el.dataset.key,offset);C.render();}
    if(op==='scan-match'){collect();if(C.S.version)C.S.tab='match';else W.showMatching=true;W.openScans.add(el.dataset.source);C.render();const row=$('#scan-submission-'+el.dataset.id);row?.scrollIntoView?.({block:'center'});row?.querySelector('[data-record="name"]')?.focus?.();}
    if(op==='scan-cleanup'){
      if(W.removingSource)return true;collect();const pid=W.projectId,id=el.dataset.id;
      if(!W.intake.sources.some(f=>f.id===id))throw Error('Refresh the scan list before removing this PDF.');
      W.removingSource=id;C.render();
      try{const selection={sourceIds:[id],versionFileIds:[],includeDerived:true},preview=await C.api('/api/projects/'+pid+'/cleanup-preview',selection);if(W.projectId!==pid)return true;W.cleanup={...selection,preview,removePdf:true};}
      finally{W.removingSource=null;C.render();}
      $('#gs-cleanup')?.scrollIntoView({block:'center'});
    }
    if(op==='scan-zoom'){
      const f=W.intake?.sources.find(f=>f.id===el.dataset.source),page=Number(el.dataset.page),start=Number(el.dataset.start),count=Number(el.dataset.count);
      if(!f||!scanAvailable(f)||![page,start,count].every(Number.isInteger)||start<0||count<1||start+count>f.pages||page<start||page>=start+count)throw Error('Choose an available page from this PDF.');
      collect();W.scanPreview={projectId:W.projectId,source:f.id,page,start,count};C.render();
    }
    if(op==='scan-preview-close')closeScanPreview();
    if(op==='scan-preview-step'){const p=W.scanPreview,step=Number(el.dataset.step);if(p&&[-1,1].includes(step)&&p.page+step>=p.start&&p.page+step<p.start+p.count){collect();p.page+=step;C.render();}}
    if(op==='open-inbox'){if(!await C.leave())return true;reset();C.S.dirty=false;W.projectId=el.dataset.id;C.S.version=null;C.S.view='projects';await refresh();C.render();C.publish();}
    if(op==='close-inbox'){if(!await C.leave())return true;C.S.dirty=false;reset();C.render();}
    if(op==='refresh-inbox'){collect();try{await refresh();}finally{C.render();}}
    if(op==='intake-layout'){const row=el.closest('[data-intake-source]'),p={};for(const x of row.querySelectorAll('[data-intake-layout]'))p[x.dataset.intakeLayout]=x.type==='checkbox'?x.checked:Number(x.value);await C.api('/api/intake-files/'+el.dataset.id+'/layout',p);W.boundaryDrafts.delete(el.dataset.id);W.splitSettings.delete(el.dataset.id);C.S.dirty=W.drafts.size>0||W.boundaryDrafts.size>0;await refresh();C.render();}
    if(op==='intake-preview'){const row=el.closest('[data-intake-source]'),skip=Number(row.querySelector('[data-intake-layout="skip"]').value),pages=Number(row.querySelector('[data-intake-layout="pages_per_exam"]').value),rotation=Number(row.querySelector('[data-intake-layout="rotation"]').value);row.querySelector('.gs-source-preview').innerHTML=`<div class="grid"><img class="crop-preview" alt="First page of first booklet" src="/api/intake-files/${el.dataset.id}/page/${skip}?rotation=${rotation}"><img class="crop-preview" alt="Last page of first booklet" src="/api/intake-files/${el.dataset.id}/page/${skip+pages-1}?rotation=${rotation}"></div>`;}
    if(op==='record-preview'){const f=W.intake.sources.find(f=>f.id===el.dataset.source),b=f.booklets.find(b=>b.id===el.dataset.id);el.closest('[data-intake-booklet]').querySelector('.gs-record-preview').innerHTML=`<img class="crop-preview" alt="Local exam first page for identity review" src="/api/intake-files/${f.id}/page/${b.startPage-1}">`;}
    if(op==='recognize'){if(W.boundaryDrafts.size)throw Error('Confirm edited PDF boundaries before recognition.');collect();const sourceIds=selectedSources();if(!sourceIds.length)throw Error('Select PDFs with confirmed booklet boundaries first.');const job=await C.api('/api/projects/'+W.projectId+'/recognize',{sourceIds,model:$('#gs-recognition-model').value});W.job={...job,projectId:W.projectId};C.render();C.message('Local recognition started.');pollRecognition();}
    if(op==='cancel-recognition'&&W.job){await C.api('/api/jobs/'+W.job.id+'/cancel',{});C.message('Stopping after the current local request.');}
    if(op==='assign'){
      collect();const f=W.intake.sources.find(f=>f.id===el.dataset.source),b=f.booklets.find(b=>b.id===el.dataset.id),value=recordValue(el.closest('[data-intake-booklet]'));if(!value?.versionId)throw Error('Choose the exam version.');await C.api('/api/intake-booklets/'+b.id+'/assign',{...value,reviewed:true,sourceHash:f.sha256,...(b.recognitionHash?{recognitionHash:b.recognitionHash}:{}),manual:true});W.drafts.delete(b.id);C.S.dirty=W.drafts.size>0||W.boundaryDrafts.size>0;await refresh();C.render();C.message('Record confirmed and exam assigned to its version.');
    }
    if(op==='approve-selected'){
      collect();const ids=all('[name="intake-record"]:checked').map(x=>x.value);if(!ids.length)throw Error('Select proposed records after checking their versions, names and NetIDs.');if(!await C.confirm('Confirm the '+ids.length+' selected identity/version records and assign their exams?'))return true;
      for(const id of ids){const f=W.intake.sources.find(f=>f.booklets.some(b=>b.id===id)),b=f.booklets.find(b=>b.id===id),v={...b.proposal,...W.drafts.get(id)};await C.api('/api/intake-booklets/'+id+'/assign',{versionId:v.versionId,name:v.name,netid:v.netid,reviewed:true,sourceHash:f.sha256,recognitionHash:b.recognitionHash});W.drafts.delete(id);}C.S.dirty=W.drafts.size>0||W.boundaryDrafts.size>0;await refresh();C.render();
    }
    if(op==='cleanup-view'){W.cleanup={sourceIds:selectedSources()};C.render();$('#gs-cleanup')?.scrollIntoView({block:'center'});}
    if(op==='cleanup-close'){W.cleanup=null;C.render();}
    if(op==='cleanup-preview'){const sourceIds=W.cleanup.sourceIds;if(!sourceIds.length)throw Error('Select source PDFs to delete.');const selection={sourceIds,versionFileIds:[],includeDerived:true};W.cleanup={...selection,preview:await C.api('/api/projects/'+W.projectId+'/cleanup-preview',selection)};C.render();$('#gs-cleanup')?.scrollIntoView({block:'center'});}
    if(op==='cleanup-execute'){if(!$('#gs-cleanup-confirm')?.checked)throw Error('Confirm permanent deletion of the listed managed copies.');const p=W.cleanup,result=await C.api('/api/projects/'+W.projectId+'/cleanup',{sourceIds:p.sourceIds,versionFileIds:p.versionFileIds,includeDerived:p.includeDerived,previewHash:p.preview.previewHash,confirmed:true});W.cleanup=null;await refresh();C.render();C.message(result.complete===false?(result.error||'Some scan copies could not be deleted.')+' Remaining copies were retained.':(p.removePdf?'PDF removed.':'Managed scan copies deleted.')+' Saved grading history was retained.');}

    if(op==='process-project'){W.bulk=await C.api('/api/projects/'+W.projectId+'/process',{model:$('#gs-recognition-model').value,useTemplateCrops:true});C.render();watchProject(W.projectId);}
    if(op==='pause-project'){await C.api('/api/projects/'+W.projectId+'/pause',{});C.message('Pausing after the current local request. Completed suggestions remain.');}
    if(op==='select-region'){selectRegion(el.dataset.field);}
    if(op==='template-new'){stashRegion();W.field='new-question';W.rect=null;C.render();}
    if(['template-page','template-previous','template-next'].includes(op)){stashRegion();const handout=C.S.version.files.find(f=>f.kind==='handout'),page=op==='template-previous'?W.page-1:op==='template-next'?W.page+1:Number($('#gs-template-page').value);if(!Number.isInteger(page)||page<1||page>handout.pages)throw Error('Choose a page in the blank exam.');W.page=page;const r=getRegion();W.rect=r?.page===page?[...r.rect]:null;C.render();}
    if(op==='template-clear'){W.rect=null;W.regionDirty=true;C.S.dirty=true;stashRegion();draw();window.GScopeOutline?.updateStatus?.();}
    if(op==='template-save'){await saveTemplateDraft();}
    if(op==='template-approve'){await saveTemplateDraft();}
    if(['template-zoom-out','template-zoom-in','template-zoom-fit'].includes(op)){W.zoom=op==='template-zoom-fit'?'page':Math.max(10,Math.min(300,Math.round(templateZoomPercent()/10)*10+(op==='template-zoom-in'?10:-10)));applyTemplateZoom(true);return true;}
    if(op==='approve-crops'){if(!await C.confirm('Approve every saved question region for all currently imported scans in this version? First inspect sample question crops from each source PDF and check alignment.'))return true;const v=C.S.version;await C.acceptVersion(await C.api('/api/versions/'+v.id+'/approve-all-crops',{approved:true,snapshotHash:v.currentSnapshotHash}));C.message('Question regions approved for the current scan set.');}
    if(op==='share-rubric'){if(C.S.dirty)throw Error('Save and confirm the source rubric first.');if(!await C.confirm('Apply this confirmed rubric to every version of this exam? Existing matching question regions are kept; changed cards require fresh crop checks. Saved runs keep their original snapshots.'))return true;const result=await C.api('/api/projects/'+C.S.version.project_id+'/share-rubric',{sourceVersionId:C.S.version.id,confirmed:true});await C.acceptVersion(await C.api('/api/versions/'+C.S.version.id));C.message('Shared rubric applied to '+result.versions+' versions.');}
    if(op==='delete-version-scans'){const v=C.S.version,selection={sourceIds:[],versionFileIds:v.files.filter(f=>f.kind==='scans').map(f=>f.id),includeDerived:false};const preview=await C.api('/api/projects/'+v.project_id+'/cleanup-preview',selection);if(!await C.confirm('Permanently delete '+preview.fileCount+' managed scan copies ('+bytes(preview.totalBytes)+') for this version? Saved rubric, identity links, proposals and reviews remain; scan previews and reprocessing become unavailable. Uploaded originals elsewhere remain unchanged.'))return true;const result=await C.api('/api/projects/'+v.project_id+'/cleanup',{...selection,previewHash:preview.previewHash,confirmed:true});await C.acceptVersion(await C.api('/api/versions/'+v.id));C.message(result.complete===false?(result.error||'Some scan copies could not be deleted.')+' Remaining copies were retained.':'Managed scan copies deleted.');}
    return true;
  }
  function download(value,name){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  async function pollRecognition(){const job=W.job;if(!job)return;try{const result=await C.api('/api/jobs/'+job.id);if(['done','error','cancelled'].includes(result.status)){W.job=null;if(W.projectId===job.projectId){collect();await refresh();C.render();}C.message(result.status==='done'?'Recognition finished. Review the proposed records.':result.error||'Recognition stopped.');return;}const label=$('#gs-recognition-status');if(label)label.textContent=result.progress?.message||'Local recognition is running…';}catch(e){W.job=null;C.message(e.message);return;}setTimeout(pollRecognition,1400);}
  async function pollProject(pid){try{const result=await C.api('/api/projects/'+pid+'/batch');if(W.projectId===pid){W.bulk=result;const label=$('#gs-project-progress');if(label&&result)label.textContent=result.status+' · '+result.runs.length+' / '+result.versions.length+' versions complete';}if(['queued','running'].includes(result?.status)){setTimeout(()=>pollProject(pid),1500);return;}projectPolls.delete(pid);if(W.projectId===pid){collect();C.render();C.message(result?.status==='complete'?'Assignment suggestions are ready for review and export.':result?.error||'Assignment processing paused.');}}catch(e){projectPolls.delete(pid);C.message(e.message);}}
  return {rosterChanged:pid=>{if(W.projectId===pid){W.intake=null;W.preparedProject=null;W.lastStage=null;}},init:c=>{C=c;bindDrops();},isIntake,reset,discard,view,stageView,cleanupSettingsView,templateView,templateControlsView,templateFooterView,boxSummary,selection:()=>W.field,stashRegion,addQuestion,selectRegion,saveTemplateDraft,refreshOverlay:draw,resizeTemplate:()=>applyTemplateZoom(),invalidateLayout,mount,change,action,input};
})();
