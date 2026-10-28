/* Pin local Materials sources; only explicitly reviewed question excerpts become guidance. */
(() => {
  'use strict';
  let C,sourceClicksBound=false;
  const M={projectFiles:null,lastTab:null,buildVersions:new Map(),sourceOption:'',answerOption:'tex',buildId:'',vid:null,catalog:null,references:[],loading:false,error:'',kind:'handout',externalRole:'',externalFile:null,versionNames:{},setupWarning:'',setupStatus:'',setupUnknown:false,solutionVersion:'A',sourceId:'',source:null,sourceLoading:false,preview:null,previewLoading:false,confirmed:false,questionKey:'',text:'',baseline:'',busy:false,epoch:0,sourceRequest:0,previewRequest:0};
  const dirty=()=>M.text!==M.baseline||M.confirmed||!!M.externalFile||Object.keys(M.versionNames).length>0||!!window.GScopeAnswerKeys?.dirty?.();
  const target=()=>M.catalog?.version||String(C.S.version?.label||'').replace(/^version\s+/i,'').toUpperCase();
  const owns=(vid,epoch)=>M.vid===vid&&M.epoch===epoch;
  const same=(vid,epoch)=>C.S.version?.id===vid&&owns(vid,epoch);
  const repaint=()=>{if(C.S.view==='projects'&&['materials','rubric'].includes(C.S.tab)&&C.S.version?.id===M.vid){if(C.S.dirty)C.collectQuestions?.();C.render();}};
  const btn=(text,action,extra='',primary=false)=>C.button(text,'materials-'+action,extra,primary);
  const ref=role=>M.references.find(x=>x.role===role);
  const question=()=>C.S.version?.questions.find(q=>q.key===M.questionKey);
  function savedText(q) {return q?.guidance?.match(/\[G-Scope reviewed solution; version [A-Z]\]\n([\s\S]*?)\n\[\/G-Scope reviewed solution\]/)?.[1]||'';}
  function resetDraft() {M.text=savedText(question());M.baseline=M.text;}
  function resetVersion(vid) {
    if(M.vid===vid)return;
    Object.assign(M,{projectFiles:null,lastTab:null,sourceOption:'',buildId:'',vid,catalog:null,references:[],loading:false,error:'',kind:'handout',externalRole:'',externalFile:null,versionNames:{},setupWarning:'',setupStatus:'',setupUnknown:false,solutionVersion:'A',sourceId:'',source:null,sourceLoading:false,preview:null,previewLoading:false,confirmed:false,questionKey:C.S.version.questions[0]?.key||'',text:'',baseline:'',busy:false,epoch:M.epoch+1,sourceRequest:M.sourceRequest+1,previewRequest:M.previewRequest+1});
    resetDraft();
  }
  function discard() {resetDraft();M.confirmed=false;M.externalFile=null;M.externalRole='';M.versionNames={};window.GScopeAnswerKeys?.discard?.();}
  function sources() {return (M.catalog?.sources||[]);}
  function sourceTargetView(){return `<label>Target version<select data-materials-target-version>${(C.S.projects?.find(p=>p.id===C.S.version.project_id)?.versions||[{id:C.S.version.id,label:target()}]).map(v=>C.option(v.id,v.label,C.S.version.id)).join('')}</select></label>`;}
  function sourcePreview(item){return item.format==='pdf'?`<a class="button" href="/api/versions/${encodeURIComponent(M.vid)}/materials/source/${encodeURIComponent(item.id)}/pdf" target="gscope-exam-pdf" rel="noopener" data-materials-pdf>Preview PDF ↗</a>`:'';}
  const sourceKeys=['build','folder','upload'];
  function sourceCard(key,title){const selected=M.sourceOption===key;return `<section class="card materials-source-option ${selected?'is-selected':M.sourceOption?'is-muted':''}" data-materials-option="${key}"><h2><button type="button" class="materials-option-choice" data-action="materials-select-source" data-option="${key}" aria-pressed="${selected}"><span>${title}</span><span class="materials-option-state">${selected?'✓ Selected':'Choose option'}</span></button></h2>`;}
  function chooseSource(key){
    if(!sourceKeys.includes(key))return;M.sourceOption=key;
    // Update appearance in place. Replacing a card on a select/file-input click
    // would destroy the focused control before its native picker can open.
    for(const card of document.querySelectorAll?.('[data-materials-option]')||[]){const active=card.dataset.materialsOption===key;card.classList.toggle('is-selected',active);card.classList.toggle('is-muted',!active);const button=card.querySelector('[data-action="materials-select-source"]');button?.setAttribute('aria-pressed',String(active));const label=card.querySelector('.materials-option-state');if(label)label.textContent=active?'✓ Selected':'Choose option';}
  }
  function bindSourceClicks(){if(sourceClicksBound||!document.addEventListener)return;sourceClicksBound=true;document.addEventListener('click',event=>{const pdf=event.target.closest?.('[data-materials-pdf]');if(pdf){event.preventDefault();window.open(pdf.href,'gscope-exam-pdf','popup=yes,width=1000,height=850,resizable=yes,scrollbars=yes');return;}const card=event.target.closest?.('[data-materials-option]');if(card)chooseSource(card.dataset.materialsOption);});}
  function questionLabel(q){const key=String(q.key).trim(),title=String(q.title||'').trim(),bare=s=>s.toLowerCase().replace(/^question\s*|^q\s*(?=\d)/,'').replace(/[\s().]/g,'');return 'Question '+key+(title&&bare(title)!==bare(key)?' · '+title:'');}
  function texAvailabilityView(){
    const data=window.GScopeAnswerKeys?.availability?.(),e=C.esc;if(!data)return '<span class="materials-tex-status">Checking linked TeX…</span>';
    const available=data.versions.filter(v=>v.available),sources=[...new Set(available.map(v=>v.sourceVersion).filter(Boolean))];
    const current=data.versions.find(v=>v.version===target()),title=data.versions.map(v=>'Version '+v.version+': '+(v.available?'uses solutions for '+v.sourceVersion:v.reason||'No TeX solutions linked')).join('\n');
    const label=data.currentAvailable?'Available: Version'+(sources.length===1?' ':'s ')+sources.join(', ')+(current?.available&&current.sourceVersion!==target()?' · adapt for '+target():''):current?.sourceVersion?'Version '+current.sourceVersion+' solutions linked · TeX unavailable':'No TeX solutions linked';
    return '<span class="materials-tex-status '+(data.currentAvailable?'is-available':'is-unavailable')+'" title="'+e(title)+'">'+e(label)+'</span>'+(!data.currentAvailable&&current?.reason?'<span class="help">'+e(current.reason)+'</span>':'');
  }
  function answerOptionsView(){return `<section class="card materials-answer-options"><h2>Choose an answer-key source</h2><p class="help">Three alternatives. Use one approach, then review each answer for its exact version.</p><div class="materials-answer-choices" role="group" aria-label="Answer key source alternatives">${[['tex','Use TeX solutions','Use linked TeX; AI adapts Version A to other versions’ questions.'],['ai','Generate with AI','Solve directly from the blank question without supplied solutions.'],['manual','Enter manually','Write or paste your solution.']].map(([key,title,help])=>`<button type="button" class="materials-answer-choice ${M.answerOption===key?'is-selected':'is-muted'}" data-action="materials-select-answer" data-option="${key}" aria-pressed="${M.answerOption===key}"><strong>${title}</strong><span class="help">${help}</span>${key==='tex'?texAvailabilityView():''}<span class="materials-option-state">${M.answerOption===key?'✓ Selected':'Choose option'}</span></button>`).join('')}</div></section>`;}
  function answerSetupView(){
    if(!C?.S.version)return '';resetVersion(C.S.version.id);const e=C.esc,allQuestions=C.S.version.questions,keys=window.GScopeAnswerKeys?.selectedKeys?.()||allQuestions.map(q=>q.key),questions=allQuestions.filter(q=>keys.includes(q.key));
    if(!questions.some(q=>q.key===M.questionKey)&&M.text===M.baseline){M.questionKey=questions[0]?.key||'';resetDraft();}
    return `${answerOptionsView()}${window.GScopeAnswerKeys?.selectionView?.({manual:M.answerOption==='manual'})||''}${M.answerOption!=='manual'?(window.GScopeAnswerKeys?.view?.({mode:M.answerOption==='tex'?'tex':'solve'})||''):`<section class="card"><h2>Enter a reviewed answer key · Version ${e(target())}</h2>${!questions.length?'<p>Select a question above to enter its answer key.</p>':`<label>Question<select data-materials-field="questionKey">${questions.map(q=>C.option(q.key,questionLabel(q),M.questionKey)).join('')}</select></label>${!keys.includes(M.questionKey)?'<p class="notice warning">Reselect this question to save your edited answer key.</p>':''}${savedText(question())?`<p class="notice warning">Saving will replace the saved solution for ${e(questionLabel(question()))} on Version ${e(target())}.</p>`:''}<label for="materials-answer-tex">Solution (TeX)</label><p class="help" id="materials-answer-help">Omit <code>\\documentclass</code> and the <code>document</code> environment. <code>\\begin{solution}…\\end{solution}</code> is optional.</p><div class="gs-solution-layout"><div class="gs-solution-source"><textarea id="materials-answer-tex" data-gscope-tex aria-describedby="materials-answer-help" data-answer-question="${e(M.questionKey)}" data-materials-field="text" rows="7" maxlength="8000" spellcheck="false">${e(M.text)}</textarea></div><section class="gs-solution-preview" aria-label="Solution preview"><h4>Preview</h4><div data-solution-preview></div><p class="help" data-solution-preview-status role="status"></p></section></div><div class="row">${btn(savedText(question())?'Replace saved answer key':'Save reviewed answer key','save-solution',M.busy||!keys.includes(M.questionKey)?'disabled':'',true)}${btn('Discard answer edits','discard')}</div><p class="help">Updated solutions apply to future grading runs. Existing results stay unchanged.</p>`}</section>`}`;
  }
  function sourceLabel(r){return ({build:'Handout Build','build-source':'Handout Build','course-source':'Handout Build','output-folder':'Output folder','external-upload':'External upload'})[r.origin]||'Materials';}
  function linkedFilesView(){
    const e=C.esc,versions=M.projectFiles?.versions||[{id:C.S.version.id,label:target(),references:M.references}];
    const rows=versions.flatMap(v=>[...(v.references.some(r=>r.role==='handout')?[]:[{role:'missing'}]),...v.references].map(r=>({...r,versionId:v.id,versionLabel:v.label})));
    return `<section class="card materials-linked-files"><div class="spread materials-linked-heading"><h2>Linked exam files</h2>${C.button('+ Add version','add-version',`data-id="${e(C.S.version.project_id)}"`)}</div><div class="materials-linked-table-wrap"><table class="materials-linked-table" aria-label="Linked exam files by version"><colgroup><col class="materials-file-label-col"><col><col class="materials-file-actions-col"></colgroup><thead><tr><th>File</th><th>Source</th><th><span class="materials-visually-hidden">File actions</span></th></tr></thead><tbody>${rows.map(r=>{
      if(r.role==='missing')return `<tr><th scope="row">Version ${e(r.versionLabel)} · Blank exam</th><td colspan="2" class="help materials-missing-blank">No blank exam linked</td></tr>`;
      const label=`Version ${r.versionLabel} · ${r.role==='handout'?'Blank exam':'Solutions'}`,attrs=`data-id="${e(r.id)}" data-version="${e(r.versionId)}"`,canPreview=r.format==='pdf'||!!r.buildId;
      return `<tr><th scope="row">${e(label)}</th><td>${sourceLabel(r)}</td><td><div class="materials-linked-actions">${canPreview?`<a class="button" href="/api/versions/${encodeURIComponent(r.versionId)}/materials/reference/${encodeURIComponent(r.id)}/pdf" target="gscope-exam-pdf" rel="noopener" data-materials-pdf>Preview PDF ↗</a>`:''}${btn('Replace file','replace-reference',`${attrs} ${M.busy?'disabled':''}`)}${btn('Remove file','remove-reference',`${attrs} ${M.busy?'disabled':''}`)}<input hidden type="file" id="materials-replace-${e(r.id)}" accept="${r.role==='handout'?'.pdf,application/pdf':'.pdf,.tex,application/pdf,text/x-tex'}" data-materials-upload="replacement" ${attrs}></div></td></tr>`;
    }).join('')}</tbody></table></div><details class="materials-version-names"><summary>Rename versions</summary><div class="materials-version-name-fields">${versions.map(v=>`<label>Version ${e(v.label)}<input data-materials-version-label="${e(v.id)}" value="${e(M.versionNames[v.id]??v.label)}" maxlength="1" pattern="[A-Za-z]" aria-label="New letter for Version ${e(v.label)}"></label>`).join('')}</div>${btn('Save version names','rename-versions',!Object.keys(M.versionNames).length||M.busy?'disabled':'')}</details></section>`;
  }
  function linkedReference(vid,id){return (M.projectFiles?.versions?.find(v=>v.id===vid)?.references||M.references).find(r=>r.id===id);}
  async function refreshLinkedFiles(vid,epoch){
    if(!same(vid,epoch))return;
    const [version,projectFiles]=await Promise.all([C.api('/api/versions/'+vid),C.api('/api/projects/'+C.S.version.project_id+'/exam-sources')]);
    if(same(vid,epoch)){applyVersion(version,vid,epoch);M.projectFiles=projectFiles;M.references=projectFiles.versions.find(v=>v.id===vid)?.references||[];M.preview=null;if(M.text===M.baseline)resetDraft();window.GScopeAnswerKeys?.invalidate?.();}
  }
  let setupJob=null,setupStarting=false;
  function buildLetters(build){return Array.from({length:build?.versions||0},(_,i)=>String.fromCharCode(65+i));}
  function buildSelection(build){const key=C.S.version.project_id+':'+build.id,expected=new Set((M.projectFiles?.versions||C.S.projects?.find(p=>p.id===C.S.version.project_id)?.versions||[{label:target()}]).map(v=>v.label));return M.buildVersions.get(key)||buildLetters(build).filter(letter=>expected.has(letter));}
  function buildCheckboxes(build){if(!build)return '';const selected=buildSelection(build);return `<fieldset class="materials-build-versions"><legend>Versions to set up</legend>${buildLetters(build).map(letter=>`<label><input type="checkbox" data-materials-build-version="${letter}" data-build="${build.id}" ${selected.includes(letter)?'checked':''}> ${letter}</label>`).join('')}</fieldset>`;}
  function buildSetupView(){const builds=M.catalog?.handoutBuilds||[],chosen=builds.find(b=>b.id===M.buildId)||builds[0];return `${sourceCard('build','Use a Handout Build')}<p>Choose a saved G-Whiz handout to prepare the selected blank exam versions.</p>${builds.length?`<label>Handout Build<select id="materials-handout-build" data-materials-field="buildId">${builds.map(b=>C.option(b.id,b.title+' · Versions '+Array.from({length:b.versions},(_,i)=>String.fromCharCode(65+i)).join(', '),M.buildId||builds[0]?.id)).join('')}</select></label>${buildCheckboxes(chosen)}${btn(setupJob||setupStarting?'Setting up versions…':'Set up selected versions','setup-build',setupJob||setupStarting?'disabled':'',true)}`:'<p class="help">No saved Handout Build matches this course, semester and exam title. Save one in Materials, then refresh the catalog.</p>'}<p class="help" id="materials-build-progress" role="status">${eSetupStatus()}</p>${M.setupUnknown?btn('Check setup status','check-setup',setupJob?.polling?'disabled':''): ''}</section>`;}
  const eSetupStatus=()=>C.esc(M.setupStatus||(setupJob?'Compilation and linking continue locally.':''));
  function setupStatus(text,vid,epoch){if(same(vid,epoch)){M.setupStatus=text;const label=document.querySelector('#materials-build-progress');if(label)label.textContent=text;}}
  async function pollSetup(job,vid,epoch){
    if(setupJob!==job||job.polling)return;job.polling=true;
    let state;
    try{state=await C.api('/api/jobs/'+job.id);}
    catch(error){job.polling=false;if(same(vid,epoch)){M.setupUnknown=true;setupStatus('Could not check setup: '+error.message+' Setup may still be running; check its status before starting again.',vid,epoch);repaint();}return;}
    finally{job.polling=false;}
    if(setupJob!==job)return;
    if(same(vid,epoch))M.setupUnknown=false;
    if(['queued','running'].includes(state.status)){setupStatus((state.progress?.message||'Preparing exam versions…')+(Number.isFinite(state.progress?.elapsedSeconds)?' · '+Math.floor(state.progress.elapsedSeconds)+'s elapsed':''),vid,epoch);setTimeout(()=>pollSetup(job,vid,epoch),1200);return;}
    if(state.status!=='done'){setupJob=null;const text=state.error||'Build setup stopped. Check the handout build in Materials before retrying.';setupStatus(text,vid,epoch);C.message(text);repaint();return;}
    try{
      if(same(vid,epoch)){
        const version=await C.api('/api/versions/'+state.result.versionId),projects=await C.api('/api/projects');
        if(same(vid,epoch)){M.catalog=null;M.error='';M.setupWarning=(state.result.warnings||[]).join(' ');applyVersion(version,vid,epoch);C.S.projects=projects.projects;M.setupStatus='Selected versions are ready.';}
      }else C.S.projects=(await C.api('/api/projects')).projects;
      setupJob=null;repaint();C.message('Blank exam versions '+state.result.versions.join(', ')+' are ready. '+(state.result.solutionsVersion?'Version A solutions are linked. ':'No solutions were found. ')+'Review the exam outline for each version.');
    }catch(error){if(same(vid,epoch)){M.setupUnknown=true;setupStatus('Setup finished, but its files could not be refreshed: '+error.message+' Check setup status to retry the refresh.',vid,epoch);repaint();}}
  }
  function view() {
    if(!C?.S.version)return '';
    resetVersion(C.S.version.id);
    const e=C.esc;
    if(!M.catalog)return `<section class="card" id="materials-panel"><h2>Exam source &amp; solutions</h2><p>${M.error?e(M.error):'Loading local Materials sources…'}</p>${M.error?btn('Retry','refresh'):''}</section>`;
    const list=sources(),questions=C.S.version.questions;
    if(!questions.some(q=>q.key===M.questionKey)&&M.text===M.baseline){M.questionKey=questions[0]?.key||'';resetDraft();}
    return `<div id="materials-panel"><section class="card materials-source-header"><h2>Exam source &amp; solutions</h2><p class="help">Select a source option below. Switch options whenever you need to add another file.</p></section>
    <h3 class="materials-options-title" id="materials-source-options-title">Source options</h3><div class="grid materials-setup-options" role="group" aria-labelledby="materials-source-options-title">${buildSetupView()}${sourceCard('folder','Choose an output-folder PDF')}<p>Choose a PDF from this course’s semester output folder.</p>${M.setupWarning?`<p class="notice warning">${e(M.setupWarning)}</p>`:''}<div class="materials-source-fields">${sourceTargetView()}<label>Available source<select data-materials-field="sourceId"><option value="">Choose a source</option>${list.map(s=>C.option(s.id,`${s.relativePath||s.filename||s.title}`,M.sourceId)).join('')}</select></label><div class="materials-source-preview">${M.source?sourcePreview(M.source):''}</div>${M.catalog.outputFolder?`<p class="help materials-source-folder"><code>${e(M.catalog.outputFolder)}</code></p>`:''}</div>${!list.length?'<p>No matching files were found in this semester’s output folder. Use a Handout Build or upload an external PDF instead.</p>':''}${M.sourceLoading?'<p>Reading source…</p>':''}${M.source?`<p>Detected role: <strong>${e(M.source.role==='handout'?'blank handout':'solutions')}</strong> for <strong>Version ${e(target())}</strong>.</p>${btn('Link source','link',M.busy?'disabled':'',true)}`:''}</section>${sourceCard('upload','Upload an external PDF')}<p>Use an exam supplied by a coordinator or saved outside the output folder.</p><div class="materials-source-fields">${sourceTargetView()}<label>This PDF contains<select data-materials-field="externalRole"><option value="" ${!M.externalRole?'selected':''}>—</option>${C.option('handout','Blank exam',M.externalRole)}${C.option('solutions','Solutions',M.externalRole)}</select></label></div><div class="row materials-external-upload">${btn('Choose PDF','choose-external',M.busy?'disabled':'')}<span class="help" data-materials-external-name>${e(M.externalFile?.name||'No file chosen')}</span><input hidden id="materials-external-file" type="file" accept="application/pdf,.pdf" data-materials-upload="external" ${M.busy?'disabled':''}></div>${btn(M.busy?'Uploading…':'Upload','upload-external',!M.externalRole||!M.externalFile||M.busy?'disabled':'',true)}</section></div>
    ${linkedFilesView()}
    </div>`;
  }

  async function mount() {
    bindSourceClicks();
    if(!C?.S.version||!['materials','rubric'].includes(C.S.tab))return;
    resetVersion(C.S.version.id);const entered=M.lastTab!==C.S.tab;M.lastTab=C.S.tab;if(entered&&C.S.tab==='materials'&&!M.loading){M.catalog=null;M.error='';}
    if(!M.catalog&&!M.loading&&!M.error) {
      const vid=M.vid,epoch=M.epoch;M.loading=true;
      try {
        const [catalog,references,projectFiles]=await Promise.all([C.api(`/api/versions/${vid}/materials/catalog`),C.api(`/api/versions/${vid}/materials`),C.api('/api/projects/'+C.S.version.project_id+'/exam-sources')]);
        if(same(vid,epoch)){M.catalog=catalog;M.references=references.references;M.projectFiles=projectFiles;M.solutionVersion=catalog.defaultSolutionsVersion||'A';}
      } catch(error){if(same(vid,epoch))M.error=error.message;}
      finally {if(owns(vid,epoch)){M.loading=false;repaint();}}
    }
    await window.GScopeAnswerKeys?.mount?.();
  }
  function input(el) {
    if(el.dataset.materialsVersionLabel){const id=el.dataset.materialsVersionLabel,original=M.projectFiles?.versions.find(v=>v.id===id)?.label;if(el.value.toUpperCase()===original)delete M.versionNames[id];else M.versionNames[id]=el.value.toUpperCase();const save=document.querySelector('[data-action="materials-rename-versions"]');if(save)save.disabled=!Object.keys(M.versionNames).length||M.busy;return true;}
    if(el.dataset.materialsField!=='text')return false;
    M.text=el.value;
    return true;
  }
  function syncUploadControls(){
    const upload=document.querySelector('[data-action="materials-upload-external"]');if(upload)upload.disabled=!['handout','solutions'].includes(M.externalRole)||!M.externalFile||M.busy;
    const name=document.querySelector('[data-materials-external-name]');if(name)name.textContent=M.externalFile?.name||'No file chosen';
  }
  async function loadSource(id) {
    chooseSource('folder');
    const vid=M.vid,epoch=M.epoch,request=++M.sourceRequest;
    M.sourceId=id;M.source=null;M.confirmed=false;M.sourceLoading=!!id;repaint();
    if(!id)return;
    try {const source=await C.api(`/api/versions/${vid}/materials/source/${id}`);if(same(vid,epoch)&&request===M.sourceRequest)M.source=source;}
    finally {if(owns(vid,epoch)&&request===M.sourceRequest){M.sourceLoading=false;repaint();}}
  }
  async function change(el) {
    if(el.dataset.materialsUpload==='replacement'){
      const file=el.files?.[0];if(!file)return true;
      const vid=M.vid,epoch=M.epoch,targetVid=el.dataset.version||vid,reference=linkedReference(targetVid,el.dataset.id);if(!reference)throw Error('Reload and choose the current linked file.');
      if(M.busy)throw Error('Wait for the current file action to finish.');
      if(file.size>200000000||!(reference.role==='handout'?/\.pdf$/i:/\.(pdf|tex)$/i).test(file.name))throw Error(reference.role==='handout'?'Choose a blank-exam PDF.':'Choose a solutions PDF or TeX file.');
      if(!await C.confirm('Replace this '+(reference.role==='handout'?'blank exam? Check its exam outline and answers again afterward.':'solutions file? Its reviewed answers will need checking again.')+' Earlier grading records are kept.')){el.value='';return true;}
      if(dirty())throw Error('Save or discard your answer edits before replacing a file.');
      M.busy=true;repaint();
      try{const response=await fetch(`/api/versions/${targetVid}/materials/reference/${reference.id}/replace?name=${encodeURIComponent(file.name)}&sha256=${reference.sha256}`,{method:'POST',headers:{'X-App-Token':C.S.boot.token,'Content-Type':'application/octet-stream'},body:file,credentials:'same-origin',redirect:'error'});const result=await response.json();if(!response.ok)throw Error(result.error||'The replacement could not finish.');await refreshLinkedFiles(vid,epoch);C.message('File replaced. '+(reference.role==='handout'?'Check this version’s exam outline and answer keys.':'Review this version’s answer keys.'));}
      finally{if(owns(vid,epoch)){M.busy=false;repaint();}}return true;
    }
    if(el.hasAttribute?.('data-materials-target-version')){await C.openVersion?.(el.value,{keepStep:true});return true;}
    if(el.dataset.materialsBuildVersion){const build=M.catalog.handoutBuilds.find(b=>b.id===el.dataset.build);if(build){const set=new Set(buildSelection(build));el.checked?set.add(el.dataset.materialsBuildVersion):set.delete(el.dataset.materialsBuildVersion);M.buildVersions.set(C.S.version.project_id+':'+build.id,buildLetters(build).filter(x=>set.has(x)));chooseSource('build');}return true;}
    if(el.dataset.materialsUpload==='external') {
      chooseSource('upload');const file=el.files?.[0]||null;
      if(file&&(!/\.pdf$/i.test(file.name)||file.size>200000000)){el.value='';M.externalFile=null;syncUploadControls();throw Error('Choose a PDF up to 200 MB.');}
      M.externalFile=file;syncUploadControls();return true;
    }
    const field=el.dataset.materialsField;if(!field)return false;
    if(field==='buildId'){M.buildId=el.value;chooseSource('build');repaint();return true;}
    if(field==='externalRole'){chooseSource('upload');M.externalRole=el.value;syncUploadControls();return true;}
    if(input(el))return true;
    if(field==='confirmed'){M[field]=el.checked;return true;}
    if(field==='questionKey') {
      if(M.text!==M.baseline&&!await C.confirm('Discard the unsaved solution excerpt and select another question?')){el.value=M.questionKey;return true;}
      M.questionKey=el.value;resetDraft();repaint();return true;
    }
    if(field==='kind'||field==='solutionVersion') {M[field]=el.value;await loadSource('');return true;}
    if(field==='sourceId'){await loadSource(el.value);return true;}
    return true;
  }
  function applyVersion(value,vid,epoch) {
    if(!same(vid,epoch)){if(owns(vid,epoch))M.catalog=null;return;}
    C.S.version=value;
    // An API response must not overwrite newer rubric edits made on another tab.
    if(!C.S.dirty)C.S.questions=structuredClone(value.questions);
    C.S.consistencyReport=null;
    if(C.S.run?.version_id===vid)C.S.run.current=false;
  }
  async function action(el) {
    const name=el.dataset.action||'';if(!name.startsWith('materials-'))return false;
    const action=name.slice(10),vid=M.vid,epoch=M.epoch;
    if(action==='rename-versions'){
      if(M.busy)return true;const versions=M.projectFiles?.versions;if(!versions)throw Error('Wait for the assignment files to load.');
      const names=versions.map(v=>({id:v.id,label:M.versionNames[v.id]??v.label,previousLabel:v.label})),submitted=JSON.stringify(M.versionNames);
      M.busy=true;try{await C.api('/api/projects/'+C.S.version.project_id+'/rename-versions',{versions:names});if(same(vid,epoch)){if(JSON.stringify(M.versionNames)===submitted)M.versionNames={};await refreshLinkedFiles(vid,epoch);C.S.projects=(await C.api('/api/projects')).projects;M.catalog=null;}C.message(Object.keys(M.versionNames).length?'Version names saved. Newer edits are still unsaved.':'Version names saved.');}finally{if(owns(vid,epoch)){M.busy=false;repaint();}}return true;
    }
    if(action==='choose-external'){if(!M.busy)document.querySelector('#materials-external-file')?.click();return true;}
    if(action==='upload-external'){
      if(M.busy)return true;const file=M.externalFile;if(!file)throw Error('Choose a PDF to upload.');
      const vid=M.vid,epoch=M.epoch,role=M.externalRole;
      if(!['handout','solutions'].includes(role))throw Error('Choose whether this PDF is a blank exam or solutions.');
      if(!/\.pdf$/i.test(file.name)||file.size>200000000)throw Error('Choose a PDF up to 200 MB.');
      if(M.busy)throw Error('Wait for the current source action to finish.');
      if(M.text!==M.baseline&&!await C.confirm('Discard the unsaved solution excerpt before changing exam files?'))return true;
      if(role==='solutions'&&ref('solutions')&&!await C.confirm('Replace this version’s solutions file and clear its reviewed answer excerpts?'))return true;
      resetDraft();M.busy=true;repaint();
      try {
        const response=await fetch(`/api/versions/${vid}/materials/upload?${new URLSearchParams({name:file.name,role})}`,{method:'POST',headers:{'Content-Type':'application/pdf','X-App-Token':C.S.boot.token},body:file,credentials:'same-origin',redirect:'error'});
        const value=await response.json();if(!response.ok)throw Error(value.error||'The PDF could not be uploaded.');
        if(same(vid,epoch)){M.references=value.references;M.projectFiles=await C.api('/api/projects/'+C.S.version.project_id+'/exam-sources');M.preview=null;M.externalRole='';M.externalFile=null;}
        applyVersion(value.version,vid,epoch);C.message(role==='handout'?'Blank exam added. Continue to Exam outline.':'Solutions added to this version.');
      } finally {if(owns(vid,epoch)){M.busy=false;repaint();}}
      return true;
    }
    if(action==='select-source'){chooseSource(el.dataset.option);return true;}
    if(action==='select-answer'){if(['tex','ai','manual'].includes(el.dataset.option)){M.answerOption=el.dataset.option;repaint();}return true;}
    if(action==='check-setup'){if(setupJob)await pollSetup(setupJob,setupJob.versionId,setupJob.epoch);return true;}
    if(action==='setup-build') {
      if(setupStarting||setupJob)return true;
      if(M.busy)throw Error('Wait for the current file action to finish.');
      if(C.S.dirty)throw Error('Save or discard your exam outline and rubric edits before setting up versions.');
      chooseSource('build');
      const id=document.querySelector('#materials-handout-build')?.value||M.buildId||M.catalog?.handoutBuilds?.[0]?.id,build=M.catalog?.handoutBuilds?.find(b=>b.id===id);
      if(!build)throw Error('Choose a Handout Build.');
      const selected=[...buildSelection(build)];if(!selected.length)throw Error('Select at least one version to set up.');
      setupStarting=true;el.disabled=true;
      try{
        const text=(dirty()?'Discard unsaved Materials edits and compile':'Compile')+' the saved build and set up Versions '+selected.join(', ')+' for this assignment? This creates private copies in G-Scope and does not publish files.';
        if(!await C.confirm(text,{title:'Set up selected versions?',confirmLabel:'Set up versions'}))return true;
        if(!same(vid,epoch))throw Error('The selected exam changed. Choose its build again.');
        discard();M.setupUnknown=false;setupStatus('Preparing Versions '+selected.join(', ')+(selected.includes('A')?' and Version A solutions':'')+'…',vid,epoch);repaint();
        const job=await C.api(`/api/versions/${vid}/setup-handout-build`,{assignmentId:build.id,revision:build.revision,versionLabels:selected,confirmed:true});
        setupJob={...job,versionId:vid,epoch};pollSetup(setupJob,vid,epoch);
      }catch(error){setupStatus(error.message,vid,epoch);throw error;}
      finally{setupStarting=false;el.disabled=false;repaint();}
      return true;
    }
    if(action==='refresh') {
      if(dirty()&&!await C.confirm('Discard unsaved Materials edits and refresh?'))return true;
      discard();Object.assign(M,{catalog:null,error:'',sourceId:'',source:null,preview:null,sourceRequest:M.sourceRequest+1,previewRequest:M.previewRequest+1,sourceLoading:false,previewLoading:false});repaint();return true;
    }
    if(action==='paired') {
      const source=M.catalog.sources.find(s=>s.id===el.dataset.id);if(!source)throw new Error('Refresh the catalog and select a current source.');
      M.kind=source.role;M.solutionVersion=source.version||'A';await loadSource(source.id);return true;
    }
    if(action==='replace-reference') {document.querySelector('#materials-replace-'+el.dataset.id)?.click();return true;}
    if(action==='remove-reference') {
      const targetVid=el.dataset.version||vid,reference=linkedReference(targetVid,el.dataset.id);if(!reference)throw Error('Reload and choose the current linked file.');
      if(M.busy)return true;if(dirty())throw Error('Save or discard your answer edits before removing a file.');
      if(!await C.confirm('Remove this '+(reference.role==='handout'?'blank exam from this version? Its outline and answers will need checking when another blank is linked.':'solutions file? Its reviewed answers will be cleared.')+' Earlier grading records are kept.'))return true;
      M.busy=true;repaint();try{await C.api(`/api/versions/${targetVid}/materials/reference/${reference.id}/remove`,{confirmed:true,sha256:reference.sha256});await refreshLinkedFiles(vid,epoch);C.message('File removed from this version. Earlier grading records are kept.');}
      finally{if(owns(vid,epoch)){M.busy=false;repaint();}}return true;
    }
    if(action==='discard'){if(M.text===M.baseline||await C.confirm('Discard the unsaved solution excerpt?')){resetDraft();repaint();}return true;}
    if(M.busy)return true;
    if(action==='link') {
      if(!M.source)throw new Error('Choose a source to link.');
      if(M.text!==M.baseline&&!await C.confirm('Discard the unsaved solution excerpt before changing the pinned source?'))return true;
      const source=M.source;
      if(source.role==='solutions'&&ref('solutions')&&!await C.confirm('Replace this version’s solutions source? Previously reviewed solution excerpts will be cleared; saved runs and reviews are retained.'))return true;
      resetDraft();M.busy=true;repaint();
      try {
        const references=await C.api(`/api/versions/${vid}/materials/link`,{sourceId:source.id,sha256:source.sha256,role:source.role,targetVersion:target(),versionConfirmed:true});
        if(source.role==='handout'&&source.format==='pdf'){
          const saved=references.references.find(r=>r.role==='handout');
          await C.api(`/api/versions/${vid}/materials/use-handout`,{referenceId:saved.id,sha256:saved.sha256,confirmed:true});
        }
        if(same(vid,epoch)){M.references=references.references;M.projectFiles=await C.api('/api/projects/'+C.S.version.project_id+'/exam-sources');if(M.sourceId===source.id)M.confirmed=false;M.preview=null;M.previewLoading=false;M.previewRequest++;}
        const version=await C.api(`/api/versions/${vid}`);applyVersion(version,vid,epoch);
        if(same(vid,epoch)&&M.text===M.baseline)resetDraft();
        C.message('Exam file linked to this version. Continue to Exam outline, or add a solutions file.');
      } finally {if(owns(vid,epoch)){M.busy=false;repaint();}}
      return true;
    }
    if(action==='use-handout') {
      const targetVid=el.dataset.version||vid,source=(M.projectFiles?.versions?.find(v=>v.id===targetVid)?.references||M.references).find(r=>r.id===el.dataset.id);if(!source)throw new Error('Reload and choose the current saved handout.');
      if(!await C.confirm('Use this pinned PDF as this version’s blank exam template? Existing different templates cannot be replaced.'))return true;
      M.busy=true;repaint();
      try {const result=await C.api(`/api/versions/${targetVid}/materials/use-handout`,{referenceId:source.id,sha256:source.sha256,confirmed:true});if(targetVid===vid)applyVersion(result,vid,epoch);M.projectFiles=await C.api('/api/projects/'+C.S.version.project_id+'/exam-sources');C.message('Blank template is ready. Use Exam outline to mark fields and questions.');}
      finally {if(owns(vid,epoch)){M.busy=false;repaint();}}
      return true;
    }
    if(action==='save-solution') {
      const q=question(),text=M.text;if(!q)throw Error('Choose a saved question first.');
      if(C.S.dirty)throw Error('Save question and rubric edits before applying an answer.');
      if(window.GScopeAnswerKeys?.selectedKeys&&!window.GScopeAnswerKeys.selectedKeys().includes(q.key))throw Error('Select this question before saving its answer key.');
      if(!text.trim())throw Error('Enter the reviewed solution.');M.busy=true;repaint();
      try{const result=await C.api(`/api/versions/${vid}/answer-keys/manual`,{questionKey:q.key,text,reviewed:true});applyVersion(result.version,vid,epoch);if(same(vid,epoch)&&M.questionKey===q.key){M.baseline=savedText(result.version.questions.find(x=>x.key===q.key));if(M.text===text)M.text=M.baseline;}window.GScopeAnswerKeys?.invalidate?.();C.message('Reviewed answer saved for this question and version.');}
      finally{if(owns(vid,epoch)){M.busy=false;repaint();}}return true;
    }
    return true;
  }
  window.GScopeMaterials={init:context=>{C=context;},view,answerView:answerSetupView,editAnswer:key=>{window.GScopeAnswerKeys?.selectQuestion?.(key);M.answerOption='manual';M.questionKey=key;resetDraft();},mount,input,change,action,dirty,discard,refreshAnswers:()=>{if(M.text===M.baseline)resetDraft();}};
})();
