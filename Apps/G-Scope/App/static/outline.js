/* Outline editing precedes rubric creation. Suggestions are editable drafts. */
window.GScopeOutline=(()=>{
  let C,pending=null,busy=false,D=null,dragState=null,pendingKeys=new Map(),floatingOptions=null,optionsBound=false,boxCopy=null;
  const button=(t,a,e='',p=false)=>C.button(t,'outline-'+a,e,p);
  const scrolls=new Map();
  function capture(){
    closeOptions();
    const list=document.querySelector('.outline-question-list');if(list)scrolls.set('outline:'+list.dataset.outlineVersion,list.scrollTop);
    const page=document.querySelector('.template-page-view');if(page)scrolls.set('page:'+page.dataset.layoutVersion+':'+page.dataset.layoutPage,page.scrollTop);
  }
  function restorePage(){const page=document.querySelector('.template-page-view');if(page)page.scrollTop=scrolls.get('page:'+page.dataset.layoutVersion+':'+page.dataset.layoutPage)||0;}
  function sizeWorkspace(){const workspace=document.querySelector('.exam-outline-workspace');if(!workspace||!window.innerHeight)return;workspace.style.height='';const nav=document.querySelector('nav[aria-label="Exam project steps"]'),top=(nav?.getBoundingClientRect().height||0)+10;workspace.style.setProperty?.('--outline-sticky-top',top+'px');workspace.style.setProperty?.('--outline-document-height',Math.max(360,window.innerHeight-Math.max(top,workspace.getBoundingClientRect().top)-18)+'px');window.GScopeWorkflow?.resizeTemplate?.();positionOptions();}
  function closeOptions(){const active=floatingOptions;floatingOptions=null;if(!active)return;active.owner.open=false;active.owner.appendChild(active.menu);active.menu.removeAttribute('data-floating-options');active.menu.style.cssText='';}
  function positionOptions(){
    if(!floatingOptions)return;const {owner,menu}=floatingOptions,anchor=owner.querySelector('summary').getBoundingClientRect(),height=window.innerHeight,width=window.innerWidth;
    if(!owner.isConnected||anchor.bottom<0||anchor.top>height){closeOptions();return;}
    const margin=8,below=height-anchor.bottom-margin,above=anchor.top-margin;menu.style.maxHeight=Math.max(80,Math.max(below,above)-6)+'px';menu.style.maxWidth=Math.max(120,width-margin*2)+'px';
    const rect=menu.getBoundingClientRect(),up=rect.height>below&&above>below;
    menu.style.left=Math.max(margin,Math.min(width-rect.width-margin,anchor.right-rect.width))+'px';menu.style.top=Math.max(margin,up?anchor.top-rect.height-6:Math.min(height-rect.height-margin,anchor.bottom+6))+'px';
  }
  function bindOptions(){
    if(!optionsBound&&document.addEventListener){optionsBound=true;document.addEventListener('pointerdown',event=>{if(floatingOptions&&!floatingOptions.owner.contains(event.target)&&!floatingOptions.menu.contains(event.target))closeOptions();},true);document.addEventListener('keydown',event=>{if(event.key==='Escape'&&floatingOptions){const summary=floatingOptions.owner.querySelector('summary');closeOptions();summary.focus?.();event.preventDefault();}});window.addEventListener?.('scroll',positionOptions,true);}
    for(const owner of document.querySelectorAll('.outline-row-details'))owner.ontoggle=()=>{
      if(!owner.open){if(floatingOptions?.owner===owner)closeOptions();return;}
      if(floatingOptions?.owner===owner)return;closeOptions();const menu=owner.querySelector('.outline-question-options');if(!menu)return;
      menu.dataset.outlineIndex=owner.closest('[data-outline-index]').dataset.outlineIndex;menu.setAttribute('data-floating-options','');menu.style.position='fixed';menu.style.zIndex='1002';menu.style.right='auto';menu.style.bottom='auto';menu.style.overflowY='auto';document.body.appendChild(menu);floatingOptions={owner,menu};positionOptions();
    };
  }
  function mount(){const dialog=document.querySelector('#outline-copy-dialog');if(dialog&&boxCopy){if(!dialog.open)dialog.showModal?.();dialog.oncancel=event=>{if(boxCopy?.busy)event.preventDefault();else{boxCopy=null;C.render();}};}sizeWorkspace();bindOptions();const list=document.querySelector('.outline-question-list');bindDrag(list);}
  const T=()=>window.GScopeOutlineTree;
  function tree(){const v=C.S.version,base=JSON.stringify(v.rubricOutline||[]);if(!D||D.vid!==v.id||(!D.dirty&&D.base!==base))D={vid:v.id,base,rows:[],rev:0,dirty:false};D.rows=T().sync(D.rows.length?D.rows:v.rubricOutline||[],C.S.questions);return D.rows;}
  function discard(){closeOptions();D=null;dragState=null;pendingKeys.clear();if(!boxCopy?.busy)boxCopy=null;}
  function outlineNode(q){return tree().find(n=>n.key===q.key);}
  function outlineNumber(q){return outlineNode(q)?.number||q.key;}
  function parentPoints(number){return tree().find(n=>n.number===number)?.maxPoints||0;}
  function snapshot(){if(!C.S.questions.length)return null;if(pendingKeys.size)throw Error('Use a valid, unique question label before saving the outline.');const rows=T().serialize(tree());if(rows.some(n=>!n.title.trim()||!Number.isFinite(n.maxPoints)||n.maxPoints<0))throw Error('Give each question/group a title and a nonnegative point value.');return {versionId:C.S.version.id,outline:rows,rev:D.rev};}
  function newer(saved){return !!saved&&D?.vid===saved.versionId&&D.rev!==saved.rev;}
  function setRows(rows){window.GScopeWorkflow.stashRegion();const byKey=new Map(C.S.questions.map(q=>[q.key,q]));D.rows=rows;D.rev++;D.dirty=true;C.S.questions=rows.filter(n=>n.graded).map(n=>byKey.get(n.key)).filter(Boolean);C.S.dirty=true;C.render();}
  function move(key,target,op){tree();setRows(T().move(D.rows,key,target,op));}
  function bindDrag(list){if(!list)return;
    const clear=()=>{for(const row of list.querySelectorAll('[data-tree-key]'))row.classList.remove('outline-drop-target');};
    list.ondragstart=event=>{const handle=event.target.closest('[data-drag-key]');if(!handle)return;dragState={key:handle.dataset.dragKey,x:event.clientX};event.dataTransfer?.setData('text/plain',dragState.key);if(event.dataTransfer)event.dataTransfer.effectAllowed='move';};
    list.ondragover=event=>{const row=event.target.closest('[data-tree-key]');if(!dragState||!row)return;event.preventDefault();clear();row.classList.add('outline-drop-target');if(event.dataTransfer)event.dataTransfer.dropEffect='move';};
    list.ondrop=event=>{const row=event.target.closest('[data-tree-key]'),drag=dragState;dragState=null;clear();if(!drag||!row)return;event.preventDefault();const dx=event.clientX-drag.x,r=row.getBoundingClientRect(),op=dx>32?'indent':dx< -32?'outdent':event.clientY<r.top+r.height/2?'before':'after';try{move(drag.key,row.dataset.treeKey,op);}catch(e){C.message(e.message);}};
    list.ondragend=()=>{dragState=null;clear();};
  }
  function rowActions(node,index){
    const e=C.esc,siblings=tree().filter(n=>n.parentKey===node.parentKey),position=siblings.findIndex(n=>n.key===node.key),attrs=`data-key="${e(node.key)}"`;
    return `<div class="outline-row-actions">${button('↑','up',`${attrs} title="Move up" aria-label="Move ${e(node.number)} up" ${position===0?'disabled':''}`)}${button('↓','down',`${attrs} title="Move down" aria-label="Move ${e(node.number)} down" ${position===siblings.length-1?'disabled':''}`)}${node.graded?button('×','remove',`data-index="${index}" data-outline-remove title="Remove question" aria-label="Remove question ${e(node.number)}"`):button('Ungroup','ungroup',`${attrs} title="Ungroup; keep every question" aria-label="Ungroup ${e(node.number)}"`)}</div>`;
  }
  function questionRow(q,index,selected){
    const e=C.esc,node=outlineNode(q),siblings=tree().filter(n=>n.parentKey===node.parentKey),previous=siblings[siblings.findIndex(n=>n.key===node.key)-1];
    return `<div class="outline-question ${node.parentNumber?'outline-subquestion':''} ${q.id&&selected==='q:'+q.id?'active':''}" data-outline-index="${index}" data-tree-key="${e(q.key)}"><button draggable="true" data-drag-key="${e(q.key)}" class="outline-select" data-action="gs-select-region" data-field="q:${e(q.id||'')}" ${q.id?'':'disabled'} title="${q.id?'Show question '+e(node.number)+' and its box':'Save the outline to draw this question box'}" aria-label="Show question ${e(node.number)}" aria-pressed="${!!q.id&&selected==='q:'+q.id}">${e(node.number)}</button><label class="outline-title"><span class="sr-only">Question ${e(node.number)} title</span><input data-outline-field="title" value="${e(q.title)}" aria-label="Question ${e(node.number)} title"></label><label class="outline-points"><span class="sr-only">Question ${e(node.number)} points</span><input type="number" min="0" step="any" data-outline-field="maxPoints" value="${q.maxPoints}" aria-label="Question ${e(node.number)} points"></label><div class="outline-row-tools">${rowActions(node,index)}<details class="outline-row-details"><summary title="Question options" aria-label="Question ${e(node.number)} options">⋯</summary><div class="outline-question-options"><p class="help"><span class="outline-box-status">${q.rect?'Box on page '+q.page:'No box yet'}</span> · ${q.items?.length||0} rubric items${q.id?'':' · Save the outline before drawing this question’s box.'}</p><div class="outline-move-actions">${node.parentKey?button('Ungroup','ungroup',`data-key="${e(q.key)}"`):button('Group with previous','group',`data-key="${e(q.key)}" ${previous?'':'disabled'}`)}</div></div></details></div></div>`;
  }
  function renderRows(row){
    const byKey=new Map(C.S.questions.map((q,i)=>[q.key,{q,i}]));
    return tree().map(node=>node.graded?row(byKey.get(node.key).q,byKey.get(node.key).i):`<div class="outline-parent-row" data-tree-key="${C.esc(node.key)}"><button draggable="true" class="outline-drag" data-drag-key="${C.esc(node.key)}" title="Drag group" aria-label="Move group ${C.esc(node.number)}">${C.esc(node.number)}</button><label><input data-outline-parent="${C.esc(node.key)}" value="${C.esc(node.title)}" aria-label="Group ${C.esc(node.number)} title"></label><strong data-parent-points="${C.esc(node.number)}">${node.maxPoints}</strong>${rowActions(node)}</div>`).join('');
  }
  function total(){return (C.S.questions||[]).reduce((sum,q)=>sum+(Number.isFinite(q.maxPoints)?q.maxPoints:0),0);}
  function updateStatus(){
    const label=document.querySelector('#outline-total');if(label)label.textContent=total()+' points total';
    for(const row of document.querySelectorAll('[data-outline-index]')){const q=C.S.questions[Number(row.dataset.outlineIndex)];if(!q)continue;const select=row.querySelector('.outline-select'),status=row.querySelector('.outline-box-status');if(select)select.textContent=outlineNumber(q);if(status)status.textContent=q.rect?'Box on page '+q.page:'No box yet';}
    for(const parent of document.querySelectorAll('[data-parent-points]'))parent.textContent=parentPoints(parent.dataset.parentPoints);
    window.GScopeWorkflow?.refreshOverlay?.();
  }
  function copyBoxesView(){
    if(!boxCopy||boxCopy.vid!==C.S.version.id)return '';const e=C.esc,data=boxCopy.options;
    return `<dialog id="outline-copy-dialog" class="outline-copy-dialog" aria-labelledby="outline-copy-title"><header><h2 id="outline-copy-title">Copy outline from Version ${e(C.S.version.label)}</h2>${button('×','copy-close',`aria-label="Close copy outline" ${boxCopy.busy?'disabled':''}`)}</header>${boxCopy.loading?'<p>Loading versions…</p>':boxCopy.report?`<div class="outline-copy-results">${boxCopy.report.results.map(r=>`<p><strong>Version ${e(r.label)}</strong> · ${r.questionBoxes} question boxes · ${r.studentFields} student fields</p>${r.warnings.map(w=>`<p class="help warning">${e(w)}</p>`).join('')}${r.skipped.length?`<p class="help">Skipped: ${r.skipped.map(s=>e(s.kind==='question'?'Question '+s.key:s.key)+' (p. '+s.page+')').join(', ')}.</p>`:''}`).join('')}</div>${button('Done','copy-close')}`:data?`<p class="help">Copy question and student-detail boxes. Each version stays editable.</p><div class="outline-copy-targets">${data.targets.map(v=>`<label class="check"><input type="checkbox" data-outline-copy-target="${e(v.id)}" ${boxCopy.selected.has(v.id)?'checked':''} ${!v.pages||boxCopy.busy?'disabled':''}><span>Version ${e(v.label)}${v.pages?' · '+v.pages+' pages'+(v.boxes?' · replaces '+v.boxes+' existing boxes':''):' · Add a blank exam first'}${v.pages&&v.pages<data.lastBoxPage?`<span class="help outline-copy-page-warning">Boxes after page ${v.pages} will be skipped.</span>`:''}</span></label>`).join('')||'<p>Add another version to this assignment first.</p>'}</div><div class="row">${button(boxCopy.busy?'Copying…':C.S.dirty?'Save & copy outline':'Copy outline','copy-apply',`id="outline-copy-apply" ${boxCopy.busy||!boxCopy.selected.size?'disabled':''}`,true)}${button('Cancel','copy-close',boxCopy.busy?'disabled':'')}</div>`:''}${boxCopy.error?`<p class="notice warning" role="alert">${e(boxCopy.error)}</p>`:''}</dialog>`;
  }
  function view(){const v=C.S.version,e=C.esc,selected=window.GScopeWorkflow?.selection?.();
    return `<aside class="card outline-sidebar" aria-label="Question outline and student fields"><header class="outline-heading"><div><h2>Exam outline</h2><span class="help" id="outline-total">${total()} points total</span></div><div class="outline-top-actions">${button('Suggest boxes','suggest',busy?'disabled':'')}${button('+','add','aria-label="Add question" title="Add question"')}</div></header><details class="outline-help" ${pending?.versionId===v.id?'open':''}><summary>${pending?.versionId===v.id?pending.questions.length+' suggested boxes ready':'Setup & suggestions'}</summary><p class="help">Select a question to edit its box. Drag its number to reorder; drag right onto another row to group, or left to ungroup. Use the row arrows to move and × to remove. The three dots contain grouping options. Groups allow one level of subquestions. Group totals summarize their parts and are not graded twice.</p><p class="help">Suggested boxes use printed labels on the blank exam. You can move and resize boxes manually for any PDF. Save outline also approves the current student-detail boxes.</p>${busy?'<p class="help">Reading the blank exam locally…</p>':''}${pending?.versionId===v.id?`<div class="notice"><ul>${pending.warnings.map(w=>`<li>${e(w)}</li>`).join('')}</ul>${button('Use suggested outline','apply')}${button('Discard suggestions','discard')}</div>`:''}</details>${window.GScopeWorkflow.templateControlsView()}<div class="outline-column-labels" aria-hidden="true"><span>#</span><span>Question title</span><span>Points</span><span></span></div><div class="outline-question-list" data-outline-version="${e(v.id)}">${renderRows((q,index)=>questionRow(q,index,selected))||'<p class="help">Add questions or suggest boxes from the blank exam.</p>'}</div><footer class="outline-footer">${window.GScopeWorkflow.templateFooterView()}</footer></aside>${copyBoxesView()}`;
  }
  function input(el){
    if(el.dataset.outlineCopyTarget!==undefined){if(boxCopy&&!boxCopy.busy){el.checked?boxCopy.selected.add(el.dataset.outlineCopyTarget):boxCopy.selected.delete(el.dataset.outlineCopyTarget);const apply=document.querySelector('#outline-copy-apply');if(apply)apply.disabled=!boxCopy.selected.size;}return true;}
    if(el.dataset.outlineParent!==undefined){const node=tree().find(n=>n.key===el.dataset.outlineParent);if(node){node.title=el.value;D.rev++;D.dirty=true;C.S.dirty=true;}return true;}
    const field=el.dataset.outlineField;if(!field)return false;const row=el.closest('[data-outline-index]'),q=C.S.questions[Number(row.dataset.outlineIndex)],node=outlineNode(q);
    if(field==='key'){
      const valid=/^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$/.test(el.value)&&!D.rows.some(n=>n.key===el.value&&n.key!==q.key);
      if(!valid){pendingKeys.set(q.id,el.value);C.S.dirty=true;return true;}pendingKeys.delete(q.id);
    }
    q[field]=field==='maxPoints'?Number(el.value):el.value;if(node&&field==='key')node.key=el.value;D.rev++;D.dirty=true;C.S.dirty=true;updateStatus();return true;
  }
  async function action(el){const name=el.dataset.action||'';if(!name.startsWith('outline-'))return false;
    const op=name.slice(8),v=C.S.version;
    if(op==='copy-close'){if(!boxCopy?.busy){boxCopy=null;C.render();}return true;}
    if(op==='copy-open'){
      if(boxCopy?.busy)return true;const summary=window.GScopeWorkflow.boxSummary?.(),draft=boxCopy={vid:v.id,loading:true,busy:false,options:null,selected:new Set(),report:null,error:''};C.render();
      try{const options=await C.api('/api/versions/'+v.id+'/box-copy-options');if(boxCopy===draft&&C.S.version?.id===v.id){draft.options=summary?{...options,lastBoxPage:summary.lastPage,sourceBoxes:summary.count}:options;draft.selected=new Set(options.targets.filter(t=>t.pages&&!t.boxes).map(t=>t.id));}}
      catch(error){if(boxCopy===draft)draft.error=error.message;}finally{if(boxCopy===draft){draft.loading=false;C.render();}}return true;
    }
    if(op==='copy-apply'){
      const draft=boxCopy;if(!draft||draft.busy||!draft.selected.size)return true;const targets=Array.from(draft.selected),targetHashes=Object.fromEntries(draft.options.targets.filter(t=>draft.selected.has(t.id)).map(t=>[t.id,t.stateHash]));draft.busy=true;draft.error='';C.render();
      try{if(C.S.dirty)await window.GScopeWorkflow.saveTemplateDraft();if(C.S.version?.id!==v.id)throw Error('The source version changed. Reopen Copy outline.');if(C.S.dirty)throw Error('Newer outline edits are still unsaved. Finish saving them before copying.');const current=await C.api('/api/versions/'+v.id+'/box-copy-options');const result=await C.api('/api/versions/'+v.id+'/copy-boxes',{targetVersionIds:targets,sourceHash:current.sourceHash,targetHashes});if(boxCopy===draft)draft.report=result;C.message('Outline copied. Each version can be edited independently.');}
      catch(error){if(boxCopy===draft)draft.error=error.message;}finally{if(boxCopy===draft){draft.busy=false;C.render();}}return true;
    }
    if(['up','down','group','outdent','ungroup'].includes(op)){
      const rows=tree(),node=rows.find(n=>n.key===el.dataset.key);if(!node)return true;
      if(op==='ungroup'){if(node.graded)move(node.key,null,'outdent');else setRows(T().ungroup(rows,node.key));}
      else if(op==='outdent')move(node.key,null,'outdent');
      else{const siblings=rows.filter(n=>n.parentKey===node.parentKey),index=siblings.indexOf(node),target=siblings[index+(op==='down'?1:-1)];if(target)move(node.key,target.key,op==='group'?'indent':op==='down'?'after':'before');}
      return true;
    }
    if(op==='add'){window.GScopeWorkflow.addQuestion();}
    if(op==='remove'){window.GScopeWorkflow.stashRegion();const q=C.S.questions[Number(el.dataset.index)];if((q.rect||q.items.length)&&!await C.confirm('Remove question '+q.key+' from this outline and its current rubric? Saved grading runs retain their snapshots.'))return true;C.S.questions.splice(Number(el.dataset.index),1);C.S.dirty=true;C.render();}
    if(op==='save'){await window.GScopeWorkflow.saveTemplateDraft();}
    if(op==='discard'){pending=null;C.render();}
    if(op==='suggest'){
      if(busy)return true;if(C.S.dirty)throw Error('Save the outline edits before requesting suggested boxes.');
      busy=true;C.render();try{const result=await C.api('/api/versions/'+v.id+'/outline-suggestions',{});if(C.S.version?.id===v.id)pending=result;}finally{busy=false;C.render();}
    }
    if(op==='apply'){
      if(!pending||pending.versionId!==v.id)throw Error('Request suggestions for this version first.');
      if(C.S.dirty)throw Error('Save or discard outline edits before using the suggested boxes.');
      if(v.files.find(f=>f.kind==='handout')?.sha256!==pending.handoutHash)throw Error('The blank exam changed. Request new suggestions.');
      if(v.questions.length&&!await C.confirm('Merge suggested questions into this outline? Matching questions keep existing rubric items, point values and saved boxes. Unmatched questions are kept.'))return true;
      const prior=new Map(v.questions.map(q=>[q.key,q]));const questions=pending.questions.map(q=>{const old=prior.get(q.key);return old?{...q,...old,page:old.rect?old.page:q.page,rect:old.rect||q.rect}:q;});
      const keys=new Set(questions.map(q=>q.key));for(const q of v.questions)if(!keys.has(q.key))questions.push(q);
      if(!questions.length)throw Error('No question boxes were detected. Add questions and draw boxes manually.');
      const before=JSON.stringify(C.S.questions);const layout=await C.api('/api/versions/'+v.id+'/identity-layout');
      const fields={...layout.fields};for(const key of ['name','netid','version'])if(!fields[key]&&pending.fields[key])fields[key]=pending.fields[key];
      await C.api('/api/versions/'+v.id+'/identity-layout',{fields,approved:false});
      const value=await C.api('/api/versions/'+v.id+'/questions',{questions});
      if(C.S.version?.id===v.id){pending=null;C.workflowInvalidate?.();if(JSON.stringify(C.S.questions)===before)await C.acceptVersion(value);else{C.S.version=value;C.S.dirty=true;C.render();}}
      C.message('Draft outline saved. Check and resize every box and review all point values.');
    }
    return true;
  }
  return {init:c=>{C=c;window.addEventListener?.('resize',sizeWorkspace);},view,input,action,capture,mount,restorePage,updateStatus,snapshot,newer,discard,numberFor:outlineNumber,acceptVersion:discard};
})();
