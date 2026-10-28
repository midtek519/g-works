(() => {
  if (globalThis.__gRaterInstalled) return;
  globalThis.__gRaterInstalled = true;
  const host = document.createElement('div');
  host.id = 'g-rater-host';
  host.style.cssText = 'all:initial;position:fixed;inset:0;z-index:2147483647;pointer-events:none;';
  const root = host.attachShadow({ mode: 'closed' });
  // This HTML is static extension UI, never page content or model output.
  root.innerHTML = `<style>
    :host { font-family:'Segoe UI',system-ui,sans-serif; color:#20334d; color-scheme:light; }
    * { box-sizing:border-box; } [hidden] { display:none!important; }
    .panel { pointer-events:auto; position:absolute; left:18px; top:18px; width:340px; max-height:calc(100vh - 36px); overflow:auto; border:1px solid #d4deed; border-radius:14px; background:#ffffff; box-shadow:0 10px 40px #20334d30; padding:18px; font:14px/1.5 'Segoe UI',system-ui,sans-serif; }
    .eyebrow { font-size:10px; letter-spacing:.16em; font-weight:750; color:#275fbd; margin:0 0 4px; } h2 { font-size:21px; letter-spacing:-.02em; margin:0; }
    .head { display:flex; align-items:start; justify-content:space-between; gap:10px; cursor:move; touch-action:none; } button { font:inherit; cursor:pointer; border:1px solid #d4deed; border-radius:6px; padding:7px 10px; background:white; color:#20334d; }
    button:hover { background:#e7effc; } button:disabled { cursor:wait; opacity:.55; } button:focus-visible,textarea:focus-visible { outline:3px solid #9db6df; outline-offset:2px; }
    .primary { background:#275fbd; color:white; border-color:#275fbd; font-weight:650; } .primary:hover { background:#1d4d9e; }
    .row { display:flex; flex-wrap:wrap; gap:7px; margin:12px 0; } .icon { padding:1px 7px; font-size:20px; line-height:1.4; }
    .state { display:inline-block; background:#e7effc; border-radius:20px; padding:3px 9px; font-size:11px; margin:12px 0 4px; color:#20334d; }
    .status { margin:8px 0; color:#586b85; } .status.error { color:#a13e31; } .mode { font-size:12px; color:#586b85; }
    label { display:block; font-size:12px; margin:12px 0 6px; font-weight:650; } textarea { width:100%; resize:vertical; min-height:80px; border:1px solid #d4deed; border-radius:6px; padding:8px; font:13px/1.5 inherit; color:#20334d; background:white; }
    details { border-top:1px solid #d4deed; padding-top:10px; margin-top:12px; } summary { cursor:pointer; font-size:12px; }
    .note { font-size:11px; color:#586b85; } .result { border-left:3px solid #275fbd; background:#e7effc; padding:12px; margin-top:12px; white-space:pre-wrap; overflow-wrap:anywhere; }
    .result h3 { font-size:15px; margin:0 0 8px; } .result p { margin:7px 0; } .result small { color:#586b85; }
    .preview img { display:block; width:100%; height:auto; border:1px solid #d4deed; margin-top:5px; background:white; } .preview p { font-size:11px; margin:10px 0 0; }
    .select { pointer-events:auto; position:absolute; inset:0; cursor:crosshair; background:#071b292b; touch-action:none; }
    .selection { position:absolute; pointer-events:none; border:2px solid #275fbd; background:#e7effc44; box-shadow:0 0 0 1px #20334d; }
    .banner { position:absolute; left:50%; top:12px; transform:translateX(-50%); width:max-content; max-width:90vw; padding:12px 18px; background:#20334d; color:white; border-radius:9px; font:14px/1.5 'Segoe UI',sans-serif; text-align:center; }
    .outline { position:absolute; border:2px solid #275fbd; pointer-events:none; } .outline span { position:absolute; top:-23px; left:-2px; font:12px/19px 'Segoe UI',sans-serif; background:#275fbd; color:white; padding:1px 6px; white-space:nowrap; }
    .suggested-choice { position:absolute; pointer-events:none; border:3px solid #8951d0; background:#8951d025; border-radius:6px; box-shadow:0 0 0 1px #fff9; }
    .suggested-choice span { position:absolute; right:2px; top:2px; border-radius:4px; background:#713ab8; color:white; font:700 11px/18px 'Segoe UI',sans-serif; padding:0 5px; }
    .choice { border-top:1px solid #d4deed; padding-top:9px; margin-top:9px; } .choice button { border-color:#8951d0; color:#63349c; background:white; }
  </style><section class="panel" aria-label="G-Rater" role="region">
    <div class="head"><div><p class="eyebrow">G-SCOPE SUGGESTION REVIEW</p><h2>G-Rater</h2></div><button class="icon" id="close" aria-label="Close panel">×</button></div>
    <span id="state" class="state">Ready for review</span><p id="mode" class="mode"></p>
    <p id="status" class="status" role="status" aria-live="polite">Load the G-Scope suggestions JSON and link this submission. Set regions to align the rubric overlay.</p>
    <div class="row"><button id="analyze" class="primary">Show saved suggestion</button><button id="cancel" hidden>Cancel</button><button id="preview">Check regions</button></div>
    <div class="row"><button id="calibrate">Set regions</button><button id="outlines">Show regions</button></div>
    <div class="row"><button id="exportRubric">Export rubric page</button><button id="batch">Load / link batch</button></div>
    <div id="result" class="result" hidden></div><div id="previewBox" class="preview" hidden></div>
    <textarea id="guidance" hidden></textarea><button id="saveGuidance" hidden>Save guidance</button>
    <details><summary>Overlay setup</summary><p class="note">G-Scope grades locally before you open these suggestions. Lens reads rubric choices inside the saved region to position the overlay and applies them only when you accept. No AI connection, screenshots or pairing are used.</p><button id="forget">Forget this question’s setup</button></details>
    <p class="note">Purple marks are suggestions. A choice is selected only when you click its Use button.</p>
  </section><div id="selector" class="select" hidden><div id="selection" class="selection" hidden></div><div id="banner" class="banner"></div></div>`;
  document.documentElement.append(host);
  const $ = id => root.getElementById(id);
  const panel = root.querySelector('.panel');
  let profile = null, epoch = 0, dirty = false, lastHref = location.href, selecting = false, busy = false, savedRegions = [], suggestionMarks = [], start = null, draft = [], accepting = false;
  const send = async data => {
    const response = await chrome.runtime.sendMessage({ app:'g-rater', ...data });
    if (!response?.ok) throw new Error(response?.error || 'The extension could not complete the action.');
    return response;
  };
  function status(text, error = false) { $('status').textContent = text; $('status').classList.toggle('error', error); }
  function clearOutput() {
    for(const node of suggestionMarks) node.remove(); suggestionMarks=[];
    $('result').replaceChildren(); $('result').hidden = true;
    $('previewBox').replaceChildren(); $('previewBox').hidden = true;
  }
  function invalidate(reason, layout = false) {
    if(accepting)send({type:'pause-order'}).catch(()=>{});
    epoch++; if (layout) dirty = true;
    clearOutput();
    for (const node of savedRegions) node.remove(); savedRegions = [];
    if (busy) send({ type:'cancel' }).catch(() => {});
    status(reason);
  }
  function setBusy(value) {
    busy = value; $('state').textContent = value ? 'Loading saved suggestion' : 'Ready for review';
    for (const id of ['analyze','preview','calibrate','outlines']) $(id).disabled = value;
    $('cancel').hidden = !value;
  }
  function setMode(mode) {
    $('mode').textContent = 'Prepared G-Scope suggestions · no AI connection';
    $('analyze').textContent=mode==='batch'?'Show saved suggestion':'Show saved suggestion';
  }
  function pageIdentity(){try{return globalThis.__gRaterActions.readIdentity(location.href);}catch{return null;}}
  function frame() { return { width:innerWidth, height:innerHeight, dpr:devicePixelRatio, scrollX, scrollY, href:location.href, epoch, dirty, pageIdentity:pageIdentity() }; }
  function beginSelection() {
    invalidate('Choose the work region, then the rubric.'); selecting = true; draft = []; start = null;
    panel.hidden = true; $('selector').hidden = false; $('selection').hidden = true;
    $('banner').textContent = '1 of 2 · Drag around the question and student work. Exclude names. Esc cancels.';
  }
  function finishSelection() { selecting = false; $('selector').hidden = true; panel.hidden = false; }
  const selector = $('selector');
  selector.addEventListener('pointerdown', e => {
    if (e.button !== 0 || !selecting) return;
    start = { x:e.clientX, y:e.clientY }; selector.setPointerCapture(e.pointerId);
    $('selection').hidden = false;
  });
  selector.addEventListener('pointermove', e => {
    if (!start) return;
    const x = Math.min(start.x, e.clientX), y = Math.min(start.y, e.clientY);
    Object.assign($('selection').style, { left:`${x}px`, top:`${y}px`, width:`${Math.abs(e.clientX-start.x)}px`, height:`${Math.abs(e.clientY-start.y)}px` });
  });
  selector.addEventListener('pointerup', async e => {
    if (!start) return;
    const endX = Math.max(0, Math.min(innerWidth, e.clientX)), endY = Math.max(0, Math.min(innerHeight, e.clientY));
    const rect = { x:Math.min(start.x,endX), y:Math.min(start.y,endY), width:Math.abs(endX-start.x), height:Math.abs(endY-start.y) };
    start = null; $('selection').hidden = true;
    if (rect.width < 40 || rect.height < 40) { $('banner').textContent = 'That region is too small. Drag a larger rectangle. Esc cancels.'; return; }
    draft.push(rect);
    if (draft.length === 1) { $('banner').textContent = '2 of 2 · Drag around the rubric choices and point values. Esc cancels.'; return; }
    finishSelection(); dirty = false;
    try {
      const response = await send({ type:'save-profile', work:draft[0], rubric:draft[1], guidance:$('guidance').value });
      profile = response.profile;
      status('Regions saved for this question. Use Check regions to verify the overlay alignment.');
      showOutlines();
    } catch (error) { status(error.message, true); }
  });
  document.addEventListener('keydown', e => {
    if (selecting && e.key === 'Escape') { finishSelection(); status('Region selection cancelled. Previous setup retained.'); }
    else if (!e.composedPath().includes(host) && !['Control','Shift','Alt','Meta'].includes(e.key)) invalidate('Page interaction detected. Show the saved suggestion again.');
  }, true);
  function showOutlines() {
    for (const node of savedRegions) node.remove(); savedRegions = [];
    if (!profile) return status('Set regions first.', true);
    for (const key of ['work','rubric']) {
      const r = profile[key], box = document.createElement('div'), label = document.createElement('span');
      box.className = 'outline'; Object.assign(box.style, { left:`${r.x}px`, top:`${r.y}px`, width:`${r.width}px`, height:`${r.height}px` });
      label.textContent = key === 'work' ? 'Student work' : 'Rubric'; box.append(label); root.append(box); savedRegions.push(box);
    }
  }
  const safeAction = action => async () => { try { await action(); } catch (error) { status(error.message, true); } };
  $('calibrate').onclick = beginSelection;
  // Move the assistant out of the way without changing the capture geometry.
  const head = root.querySelector('.head'); let drag = null;
  head.addEventListener('pointerdown', e => {
    if (e.target.closest('button')) return;
    const r = panel.getBoundingClientRect(); drag = { x:e.clientX-r.left,y:e.clientY-r.top };
    head.setPointerCapture(e.pointerId); e.preventDefault();
  });
  head.addEventListener('pointermove', e => {
    if (!drag) return;
    panel.style.left = `${Math.max(0,Math.min(innerWidth-panel.offsetWidth,e.clientX-drag.x))}px`;
    panel.style.top = `${Math.max(0,Math.min(innerHeight-60,e.clientY-drag.y))}px`;
  });
  head.addEventListener('pointerup', () => { drag = null; });
  $('outlines').onclick = showOutlines;
  $('exportRubric').onclick = safeAction(() => send({ type:'rubric-export' }));
  $('batch').onclick = safeAction(() => send({ type:'batch-open' }));
  $('preview').onclick = safeAction(() => {showOutlines();status('Check the region alignment. No screenshot or AI request is made.');});
  $('analyze').onclick = safeAction(() => send({ type:'analyze' }));
  $('cancel').onclick = safeAction(async () => { invalidate('Request cancelled.'); await send({ type:'cancel' }); });
  $('saveGuidance').onclick = safeAction(async () => { await send({ type:'save-guidance', guidance:$('guidance').value }); status('Grading guidance saved for this question.'); });
  $('close').onclick = () => { invalidate('Panel closed.'); panel.hidden = true; };
  $('forget').onclick = safeAction(async () => { await send({ type:'forget-profile' }); profile = null; $('guidance').value = ''; invalidate('Question setup removed. Set regions to begin again.'); });
  // Observe only navigation/viewport interaction, never submission HTML or text.
  document.addEventListener('scroll', e => { if (!e.composedPath().includes(host)) invalidate('The page scrolled. Set regions again.', true); }, true);
  window.addEventListener('resize', () => { if (selecting) finishSelection(); invalidate('Window size or scaling changed. Set regions again.', true); });
  document.addEventListener('wheel', e => { if (!e.composedPath().includes(host)) invalidate('The document may have moved or zoomed. Set regions again.', true); }, { capture:true, passive:true });
  let pointer = null;
  document.addEventListener('pointerdown', e => {
    if (!e.composedPath().includes(host)) { pointer = { x:e.clientX, y:e.clientY }; invalidate('Page interaction detected. Show the saved suggestion again.'); }
  }, true);
  document.addEventListener('pointerup', e => {
    if (pointer && Math.hypot(e.clientX-pointer.x,e.clientY-pointer.y)>8) invalidate('The document may have been panned. Set regions again.', true);
    pointer = null;
  }, true);
  const checkNavigation=()=>{
    if (location.href !== lastHref) {
      lastHref = location.href; invalidate('Submission changed. Wait for it to load, then capture.');
      send({ type:'refresh' }).catch(() => { profile = null; panel.hidden = true; });
    }
  };
  setInterval(checkNavigation,100);
  window.addEventListener('popstate',checkNavigation);
  window.addEventListener('hashchange',checkNavigation);
  // Clear before a browser navigation; the worker validates the resulting URL.
  globalThis.navigation?.addEventListener('navigate',()=>{clearOutput();});

  chrome.runtime.onMessage.addListener((message, sender, reply) => {
    if (message?.app !== 'g-rater' || sender.id !== chrome.runtime.id) return;
    if (message.type === 'frame') { reply(frame()); return; }
    if (message.type === 'hide-for-capture') {
      host.style.visibility = 'hidden';
      requestAnimationFrame(() => requestAnimationFrame(() => reply({ ok:true })));
      return true;
    }
    switch (message.type) {
      case 'open':
        profile = message.profile; panel.hidden = false;
        $('guidance').value = profile?.guidance || '';
        setMode(message.mode);
        break;
      case 'set-mode': setMode(message.mode); invalidate('Prepared suggestions updated. Show the saved suggestion when ready.'); break;
      case 'restore-after-capture': host.style.visibility = ''; break;
      case 'busy':
        clearOutput(); for (const node of savedRegions) node.remove(); savedRegions = [];
        setBusy(true); status(message.text); break;
      case 'idle': setBusy(false); break;
      case 'notice': status(message.text); break;
      case 'clear-prepared': invalidate(message.text);break;
      case 'error': clearOutput(); status(message.text, true); setBusy(false); break;
      case 'preview':
        clearOutput(); status(message.text); $('previewBox').hidden = false;
        for (const key of ['work','rubric']) {
          const label = document.createElement('p'), img = document.createElement('img');
          label.textContent = key === 'work' ? 'Student work · selected pixels only' : 'Rubric · selected pixels only';
          img.alt = key === 'work' ? 'Cropped student work' : 'Cropped rubric'; img.src = message.crops[key];
          $('previewBox').append(label,img);
        }
        break;
      case 'result': {
        if (message.epoch !== epoch) break;
        clearOutput(); $('result').hidden = false;
        const r = message.result;
        if(message.preparedInfo){const p=document.createElement('p');p.textContent=`Prepared batch · ${message.preparedInfo.exam} · ${message.preparedInfo.questionLabel||message.preparedInfo.questionKey}${message.preparedInfo.reviewed?' · reviewed in G-Scope':''}`;$('result').append(p);}
        const title = document.createElement('h3'); title.textContent = r.needsReview ? 'Review needed' : `Suggested: ${r.rubricItem}`;
        $('result').append(title);
        for (const [label,value] of [['Rubric item',r.rubricItem],['Reason',r.explanation],['Uncertainty',r.uncertainty]]) {
          const p = document.createElement('p'); p.textContent = `${label}: ${value}`; $('result').append(p);
        }
        const note = document.createElement('small'); note.textContent = 'AI suggestion. Confirm the work and apply the grade yourself.'; $('result').append(note);
        const choices = Array.isArray(r.choices) ? r.choices : [];
        const resultEpoch=epoch,resultHref=location.href,prepared=message.preparedInfo,order=prepared?.ordered;
        const matches=choices.map(choice=>globalThis.__gRaterFindRubric?.(profile?.rubric,choice.description,choice.points));
        const acceptanceButtons=[];
        const isCurrent=()=>epoch===resultEpoch&&!dirty&&location.href===resultHref&&location.href===lastHref&&(!prepared?.identity||pageIdentity()?.token===prepared.identity.token);
        const accept=indices=>safeAction(async()=>{
          if(accepting)return;
          accepting=true;for(const button of $('result').querySelectorAll('button'))button.disabled=true;
          let committed=false;
          try {
            if(!isCurrent())throw new Error('The submission or layout changed. Show its suggestion again.');
            const actions=globalThis.__gRaterActions;
            if(!actions||!order?.active)throw new Error('Confirm ordered review in Load / link batch first.');
            const next=order.last?null:actions.findNext(resultHref);
            const ticket=await send({type:'prepare-advance',batchId:prepared.batchId,entryId:prepared.entryId,href:resultHref,choiceIndices:indices,nextHref:next?.href??null});
            const selected=indices.map(i=>choices[i]),expected=indices.map(i=>matches[i]);
            status('Applying the reviewed choice and checking Gradescope selection…');
            const selectedCount=await actions.applyChoices({region:profile?.rubric,choices:selected,expected,isCurrent});
            const done=await send({type:'commit-advance',batchId:prepared.batchId,href:resultHref,nonce:ticket.nonce,selectedCount});
            actions.verifyChoices(profile?.rubric,selected,expected,isCurrent);
            clearOutput();
            if(done.finished){committed=true;status('Ordered review complete. The last suggestion was accepted.');return;}
            actions.clickNext(next,resultHref);committed=true;status('Accepted. Loading the next exam in the confirmed order…');
            setTimeout(()=>{if(location.href===resultHref){send({type:'pause-order'}).catch(()=>{});clearOutput();status('The next submission did not open. Confirm the current exam again.',true);}},10000);
          } catch(error) {
            await send({type:'pause-order'}).catch(()=>{});clearOutput();throw error;
          } finally {accepting=false;if(!committed)for(const button of acceptanceButtons)button.disabled=true;}
        });
        if(order?.active){const p=document.createElement('p');p.textContent=`Ordered review · exam ${order.index+1} of ${order.count}. ${prepared.selectionMode==='one'&&choices.length>1?'Choose one alternative before advancing.':''}`;$('result').append(p);}
        for(const [index,choice] of choices.entries()) {
          const match=matches[index];
          const container=document.createElement('div');container.className='choice';
          const label=document.createElement('p');label.textContent=`${index+1}. ${choice.label}`;container.append(label);
          const button=document.createElement('button');button.id=`use-choice-${index}`;button.textContent=choices.length===1?'Use suggestion':'Use this choice';
          button.disabled=message.applicationAllowed===false || !match?.element || match.selected;
          if(match?.selected) button.textContent='Already selected';
          if(match && message.applicationAllowed!==false) {
            const mark=document.createElement('div');mark.className='suggested-choice';
            Object.assign(mark.style,{left:`${match.bounds.x}px`,top:`${match.bounds.y}px`,width:`${match.bounds.width}px`,height:`${match.bounds.height}px`});
            const badge=document.createElement('span');badge.textContent=`Suggestion ${index+1}`;mark.append(badge);root.append(mark);suggestionMarks.push(mark);
            if(!match.element) {
              const why=document.createElement('small');why.textContent='Matched this rubric item, but could not uniquely identify its letter button. Click that letter in Gradescope.';container.append(why);
            }
          } else {
            const why=document.createElement('small');why.textContent=message.applicationAllowed===false?'Set and check the regions for this question before applying a saved suggestion.':'Could not uniquely match this description and points on screen. Select it manually.';container.append(why);
          }
          button.onclick=safeAction(async()=>{
            if(accepting)return;
            if(epoch!==resultEpoch || dirty || location.href!==lastHref) { invalidate('The submission changed. Capture again.');return; }
            if(message.preparedInfo) {
              await send({type:'validate-prepared',batchId:message.preparedInfo.batchId,entryId:message.preparedInfo.entryId,description:choice.description,points:choice.points});
              if(epoch!==resultEpoch || dirty || location.href!==lastHref) { invalidate('The submission changed. Show its suggestion again.');return; }
            }
            if(!isCurrent()){invalidate('The student or question changed. Show the current suggestion again.');return;}
            const fresh=globalThis.__gRaterFindRubric?.(profile?.rubric,choice.description,choice.points);
            if(!fresh?.element || fresh.element!==match.element || fresh.descriptionElement!==match.descriptionElement || !fresh.element.isConnected) { invalidate('The rubric changed. Capture again.');return; }
            if(fresh.selected) { clearOutput();status('The suggested rubric choice is already selected.');return; }
            fresh.element.click();
            clearOutput();status('Clicked the suggested rubric choice. Confirm its selection and score in Gradescope.');
          });
          if(!(prepared?.identity&&prepared.selectionMode==='all'))container.append(button);
          if(order?.active&&prepared.selectionMode==='one'){
            const advance=document.createElement('button');advance.id=`accept-next-${index}`;advance.textContent=order.last?(choices.length===1?'Accept and finish':'Accept this choice and finish'):(choices.length===1?'Accept and next':'Accept this choice and next');
            advance.disabled=message.applicationAllowed===false||!match?.element;
            advance.onclick=accept([index]);acceptanceButtons.push(advance);container.append(advance);
          }
          $('result').append(container);
        }
        if(prepared?.identity&&prepared.selectionMode==='all'&&choices.length){
          const useAll=document.createElement('button');useAll.textContent='Use suggested items';
          useAll.disabled=message.applicationAllowed===false||matches.some(match=>!match?.element);
          useAll.onclick=safeAction(async()=>{
            if(accepting)return;accepting=true;
            try{
              if(!isCurrent())throw Error('The student or question changed. Show its current suggestion.');
              for(const choice of choices)await send({type:'validate-prepared',batchId:prepared.batchId,entryId:prepared.entryId,description:choice.description,points:choice.points});
              await globalThis.__gRaterActions.applyChoices({region:profile?.rubric,choices,expected:matches,isCurrent});
              clearOutput();status('Selected the suggested items. Confirm their score in Gradescope.');
            }finally{accepting=false;}
          });
          $('result').append(useAll);
        }
        if(order?.active&&prepared.selectionMode==='all'&&choices.length){
          const advance=document.createElement('button');advance.id='accept-all-next';advance.textContent=order.last?'Accept all suggested items and finish':'Accept all suggested items and next';
          advance.disabled=message.applicationAllowed===false||matches.some(m=>!m?.element);
          advance.onclick=accept(choices.map((_,i)=>i));acceptanceButtons.push(advance);$('result').append(advance);
        }
        status(order?.active?'Review the work, then explicitly accept to advance.':'Suggestion is for this capture only.'); break;
      }
    }
    reply({ ok:true });
  });
})();
