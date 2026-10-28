import { questionScope, checkLayout, validateRect } from './core.js';
import { saveBrowserRubric } from './rubric-downloads.js';
import { gradingContext, validateBatch, bindPage, lookupBatch, bindIdentityScope } from './batch-core.js';
import { configureOrder, orderInfo, beginAcceptance, commitAcceptance, observeNavigation, pauseOrder } from './ordered-core.js';
let batchQueue=Promise.resolve();
function batchSerial(action){const result=batchQueue.then(action);batchQueue=result.catch(()=>{});return result;}

// Student images/results are never written to local/sync storage.
const running = new Map();

chrome.storage.local.setAccessLevel({ accessLevel: 'TRUSTED_CONTEXTS' });

async function tell(tabId, message) {
  try { return await chrome.tabs.sendMessage(tabId, { app: 'g-rater', ...message }); }
  catch { throw new Error('The grading page changed. Invoke G-Rater again.'); }
}
async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab?.id) throw new Error('Select the grading tab first.');
  questionScope(tab.url);
  return tab;
}
async function ensurePanel(tab) {
  questionScope(tab.url);
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['rubric-match.js','page-actions.js','content.js'] });
  const scope = questionScope(tab.url);
  const { profiles = {} } = await chrome.storage.local.get('profiles');
  await tell(tab.id, { type: 'open', profile: profiles[scope] || null, mode: 'batch' });
  await showPrepared(tab);
}

async function showPrepared(tab){
  const {preparedBatch:state}=await chrome.storage.session.get('preparedBatch');
  const context=gradingContext(tab.url),before=await getFrame(tab.id);
  const ordered=state?.batch?.version===2?null:orderInfo(state,context,tab.id),found=lookupBatch(state,context,before.pageIdentity);
  if(ordered?.error){await tell(tab.id,{type:'clear-prepared',text:ordered.error});return;}
  if(found.error){await tell(tab.id,{type:'clear-prepared',text:found.error+' Use Load / link batch.'});return;}
  const scope=questionScope(tab.url),{profiles={}}=await chrome.storage.local.get('profiles');
  if(before.href!==tab.url)return;
  let applicationAllowed=true;try{checkLayout(profiles[scope],before);}catch{applicationAllowed=false;}
  const current=await chrome.tabs.get(tab.id);if(current.url!==tab.url)return;
  if(found.identityMatched){
    const page=before.pageIdentity,key=context.courseId+':'+page.assignmentId+':'+page.assignmentSubmissionId;
    if(state.identityBindings?.[key]!==found.identity.netid)await chrome.storage.session.set({preparedBatch:{...state,identityBindings:{...state.identityBindings,[key]:found.identity.netid}}});
  }
  await tell(tab.id,{type:'result',result:found.result,epoch:before.epoch,applicationAllowed,preparedInfo:{exam:found.exam,questionKey:found.questionKey,questionLabel:found.questionLabel,reviewed:found.reviewed,batchId:found.batchId,entryId:found.entryId,identity:found.identity,selectionMode:state.batch.questions.find(q=>q.key===found.questionKey).selectionMode,ordered}});
}

async function openBatch(tab){
  if(!tab?.id){await chrome.tabs.create({url:chrome.runtime.getURL('batch.html')});return;}
  const identity=(await getFrame(tab.id)).pageIdentity;
  const context={...gradingContext(tab.url),tabId:tab.id,href:tab.url,assignmentTitle:identity?.assignmentTitle||'',assignmentId:identity?.assignmentId||''};
  const {batchContexts={}}=await chrome.storage.session.get('batchContexts');const id=crypto.randomUUID();
  const contexts=Object.fromEntries(Object.entries(batchContexts).slice(-9));contexts[id]=context;
  await chrome.storage.session.set({batchContexts:contexts});await chrome.tabs.create({url:chrome.runtime.getURL('batch.html')+'#'+id});
}

async function batchAction(message){
  const saved=await chrome.storage.session.get(['preparedBatch','batchContexts']);let state=saved.preparedBatch;
  const context=saved.batchContexts?.[message.contextId];
  const currentContext=async()=>{if(!context)throw new Error('Open Load / link batch from the Gradescope grading page.');const tab=await chrome.tabs.get(context.tabId);if(tab.url!==context.href)throw new Error('The grading page changed. Reopen Load / link batch on the current submission.');return context;};
  const update=async()=>{if(context){try{const tab=await chrome.tabs.get(context.tabId);if(tab.url===context.href)await ensurePanel(tab);}catch{}}};
  switch(message.type){
    case 'batch-state':return {state:state||null,context:context?{scope:context.scope,courseId:context.courseId,questionId:context.questionId,submissionId:context.submissionId,tabId:context.tabId,assignmentTitle:context.assignmentTitle,assignmentId:context.assignmentId}:null};
    case 'batch-import':{
      const batch=validateBatch(message.batch);state=state?.batch?.batchId===batch.batchId&&state.batch.snapshotHash===batch.snapshotHash?{...state,batch}:{batch,questionMap:{},bindings:{}};
      state=pauseOrder(state,'A batch was imported. Confirm the current exam and order again.');
      await chrome.storage.session.set({preparedBatch:state});await update();return {};
    }
    case 'batch-link-identity':{
      const current=await currentContext(),frame=await getFrame(current.tabId);
      state=bindIdentityScope(state,current,frame.pageIdentity,message.confirmed);
      await chrome.storage.session.set({preparedBatch:state});await update();return {};
    }
    case 'batch-bind':{
      if(state?.batch?.version===2)throw new Error('Roster-linked batches use student/question matching, not scan-order links.');
      const current=await currentContext();state=bindPage(state,current,message.questionKey,message.examId,message.confirmed,message.reuseSubmission);
      if(message.ordered===true)state=configureOrder(state,current,{tabId:current.tabId,href:current.href,examId:message.examId,questionKey:message.questionKey,confirmed:message.orderConfirmed});
      else if(state.order?.tabId===current.tabId)state={...state,order:undefined};
      await chrome.storage.session.set({preparedBatch:state});await update();return {};
    }
    case 'batch-unlink':{
      const current=await currentContext();if(!state)return {};
      state=pauseOrder(state,'An exam link was removed. Confirm the current exam and order again.');
      state={...state,bindings:Object.fromEntries(Object.entries(state.bindings||{}).filter(([k,b])=>message.examId?!(b.scope===current.scope&&b.examId===message.examId):!(b.courseId===current.courseId&&b.submissionId===current.submissionId&&(b.scope===current.scope||b.reuseSubmission))))};
      await chrome.storage.session.set({preparedBatch:state});await update();return {};
    }
    case 'batch-clear':
      await chrome.storage.session.remove(['preparedBatch','batchContexts']);
      for(const tab of await chrome.tabs.query({}))tell(tab.id,{type:'clear-prepared',text:'Loaded batch discarded. Load a suggestions JSON to continue.'}).catch(()=>{});
      return {};
    default:throw new Error('Unknown prepared batch action.');
  }
}

async function updatePreparedNavigation(tabId,href,loading=false){
  const {preparedBatch:state}=await chrome.storage.session.get('preparedBatch');
  const next=observeNavigation(state,{tabId,href,loading});
  if(next!==state)await chrome.storage.session.set({preparedBatch:next});
}

async function orderedAction(message,tab){
  const {preparedBatch:state}=await chrome.storage.session.get('preparedBatch');
  if(message.type==='pause-order'){
    if(state?.order?.tabId===tab.id){const next=pauseOrder(state,'Ordered review paused. Confirm the current exam in Load / link batch.');await chrome.storage.session.set({preparedBatch:next});}
    return {};
  }
  const context=gradingContext(tab.url);
  if(tab.url!==message.href||state?.batch?.batchId!==message.batchId)throw new Error('The submission or loaded batch changed. Confirm the current exam again.');
  let next;
  if(message.type==='prepare-advance'){
    const nonce=crypto.randomUUID();
    next=beginAcceptance(state,context,{tabId:tab.id,href:tab.url,entryId:message.entryId,choiceIndices:message.choiceIndices,nextHref:message.nextHref,nonce});
    await chrome.storage.session.set({preparedBatch:next});return {nonce};
  }
  if(message.type==='commit-advance'){
    next=commitAcceptance(state,context,{tabId:tab.id,href:tab.url,nonce:message.nonce,selectedCount:message.selectedCount});
    await chrome.storage.session.set({preparedBatch:next});return {finished:next.order.status==='complete'};
  }
  throw new Error('Unknown ordered-review action.');
}

async function openRubricExport(tab) {
  // This separate tool checks for Create Rubric before reading any page text.
  // activeTab is sufficient; no persistent Gradescope or Canvas access is added.
  await chrome.scripting.executeScript({target:{tabId:tab.id},files:['rubric-reader.js','rubric-export.js']});
}

async function getFrame(tabId) {
  const frame = await tell(tabId, { type: 'frame' });
  if (!frame?.width) throw new Error('Could not measure the visible page.');
  frame.zoom = await chrome.tabs.getZoom(tabId);
  return frame;
}
async function cancel() {}
async function analyze(tab) { await showPrepared(tab); }

chrome.action.onClicked.addListener(async tab => {
  try {
    let gradingPage=false;try{questionScope(tab.url);gradingPage=true;}catch{}
    if(gradingPage) await batchSerial(()=>ensurePanel(tab)); else await openRubricExport(tab);
  }
  catch (error) { console.warn('G-Rater could not open:', error.message); await chrome.runtime.openOptionsPage(); }
});
chrome.commands.onCommand.addListener(async command => {
  if (!['analyze-current', 'preview-current'].includes(command)) return;
  try { const tab = await activeTab(); await batchSerial(()=>ensurePanel(tab)); await batchSerial(()=>analyze(tab, command === 'preview-current')); }
  catch (e) {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (tab?.id) await tell(tab.id, { type: 'error', text: e.message }).catch(() => {});
  }
});
chrome.tabs.onRemoved.addListener(tabId => cancel(tabId));
chrome.tabs.onActivated.addListener(() => { for (const id of running.keys()) cancel(id); });
chrome.tabs.onUpdated.addListener((tabId,info,tab)=>{
  if(info.url||info.status==='loading'){
    cancel(tabId);tell(tabId,{type:'clear-prepared',text:'Page changed. Checking the current submission…'}).catch(()=>{});
    batchSerial(()=>updatePreparedNavigation(tabId,info.url||tab.url,info.status==='loading')).catch(()=>{});
  }
  if(info.status==='complete')batchSerial(async()=>{
    const {preparedBatch}=await chrome.storage.session.get('preparedBatch');
    if(preparedBatch){await updatePreparedNavigation(tabId,tab.url);try{await ensurePanel(await chrome.tabs.get(tabId));}catch{}}
  }).catch(()=>{});
});
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message?.app !== 'g-rater') return;
  (async () => {
    if(message.type?.startsWith('batch-')&&sender.url?.split(/[?#]/)[0]===chrome.runtime.getURL('batch.html'))return batchSerial(()=>batchAction(message));
    if (!sender.tab?.id || sender.frameId !== 0) throw new Error('Use the grading page controls.');
    const tab = await chrome.tabs.get(sender.tab.id);
    if(message.type==='batch-open'){await openBatch(tab);return {};}
    if(message.type==='rubric-export') {await openRubricExport(tab);return {};}
    if(message.type==='rubric-save'){
      const address=new URL(tab.url);
      if(address.protocol!=='https:'||!['gradescope.com','www.gradescope.com'].includes(address.hostname)||!/^\/courses\/[^/]+\/assignments\/[^/]+\/rubric(?:\/edit)?\/?$/.test(address.pathname))throw new Error('Use Save to G-Scope only on the Create Rubric page.');
      return await saveBrowserRubric(message.rubric);
    }
    const scope = questionScope(tab.url);
    if(['prepare-advance','commit-advance','pause-order'].includes(message.type))return batchSerial(()=>orderedAction(message,tab));
    switch (message.type) {
      case 'validate-prepared':{
        const {preparedBatch}=await chrome.storage.session.get('preparedBatch');
        const frame=await getFrame(tab.id),found=lookupBatch(preparedBatch,gradingContext(tab.url),frame.pageIdentity);
        if(found.error||found.batchId!==message.batchId||found.entryId!==message.entryId||!found.result.choices.some(c=>c.description===message.description&&c.points===message.points))throw new Error('The prepared batch or page link changed. Show its current suggestion again.');
        return {};
      }
      case 'save-profile': {
        const frame = await getFrame(tab.id);
        validateRect(message.work, frame); validateRect(message.rubric, frame);
        const { profiles = {} } = await chrome.storage.local.get('profiles');
        const profile = { work: message.work, rubric: message.rubric, frame: { width:frame.width,height:frame.height,dpr:frame.dpr,scrollX:frame.scrollX,scrollY:frame.scrollY,zoom:frame.zoom }, guidance: String(message.guidance || '').slice(0, 12000) };
        profiles[scope] = profile;
        await chrome.storage.local.set({ profiles });
        return { profile };
      }
      case 'save-guidance': {
        const { profiles = {} } = await chrome.storage.local.get('profiles');
        if (!profiles[scope]) throw new Error('Set regions first, then save guidance.');
        profiles[scope].guidance = String(message.guidance || '').slice(0, 12000);
        await chrome.storage.local.set({ profiles });
        return {};
      }
      case 'analyze': await batchSerial(()=>analyze(tab, !!message.preview)); return {};
      case 'cancel': await cancel(tab.id); return {};
      case 'settings': await chrome.runtime.openOptionsPage(); return {};
      case 'refresh': await batchSerial(async()=>{await updatePreparedNavigation(tab.id,tab.url);await ensurePanel(tab);}); return {};
      case 'forget-profile': {
        await cancel(tab.id);
        const { profiles = {} } = await chrome.storage.local.get('profiles');
        delete profiles[scope]; await chrome.storage.local.set({ profiles });
        return {};
      }
      default: throw new Error('Unknown action.');
    }
  })().then(data => reply({ ok: true, ...data }), e => reply({ ok: false, error: e.message }));
  return true;
});
