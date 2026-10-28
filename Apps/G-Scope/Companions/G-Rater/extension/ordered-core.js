import { gradingContext, bindPage, lookupBatch } from './batch-core.js';

// An order is an instructor-confirmed queue for ONE tab and question, never an
// inferred identity match. Only a short-lived, explicitly accepted transition
// may create the next binding. Unrelated navigation fails closed.
const TTL = 15000;
const same = (a,b) => a.scope===b.scope && a.submissionId===b.submissionId;
const fail = message => { throw new Error(message); };
export function configureOrder(state,context,{tabId,href,examId,questionKey,confirmed}) {
  if(confirmed!==true || !Number.isInteger(tabId) || !same(gradingContext(href),context))fail('Confirm that the batch order matches Gradescope and choose the current starting exam.');
  const found=lookupBatch(state,context),index=state.batch.booklets.findIndex(b=>b.id===examId);
  if(found.error || index<0 || found.questionKey!==questionKey || state.bindings?.[context.scope+':'+context.submissionId]?.examId!==examId)fail('Confirm the starting exam and question before enabling ordered review.');
  return {...state,order:{tabId,scope:context.scope,questionKey,submissionId:context.submissionId,examId,index,href,status:'ready',reason:''}};
}
export function pauseOrder(state,reason='Ordered review paused. Confirm the current exam in Load / link batch.') {
  if(!state?.order)return state;
  return {...state,order:{...state.order,status:'paused',pending:undefined,reason}};
}
export function orderInfo(state,context,tabId) {
  const o=state?.order;
  if(!o || o.tabId!==tabId)return null;
  if(o.status!=='ready' || !same(o,context))return {error:o.reason||'Ordered review is paused. Confirm the current exam in Load / link batch.'};
  return {active:true,index:o.index,count:state.batch.booklets.length,last:o.index===state.batch.booklets.length-1};
}
function requireReady(state,context,tabId,href,entryId) {
  const info=orderInfo(state,context,tabId),o=state?.order,found=lookupBatch(state,context);
  if(!info?.active || o.href!==href || found.error || found.entryId!==entryId || found.questionKey!==o.questionKey)fail(info?.error||'The submission or prepared suggestion changed. Confirm the current exam again.');
  return {o,found,info};
}
export function beginAcceptance(state,context,{tabId,href,entryId,choiceIndices,nextHref,nonce,now=Date.now()}) {
  const {o,found,info}=requireReady(state,context,tabId,href,entryId);
  const question=state.batch.questions.find(q=>q.key===o.questionKey),choices=found.result.choices;
  if(!Array.isArray(choiceIndices)||!choiceIndices.length||new Set(choiceIndices).size!==choiceIndices.length||choiceIndices.some(i=>!Number.isInteger(i)||i<0||i>=choices.length))fail('Choose a valid prepared rubric item.');
  if(question.selectionMode==='one'&&choiceIndices.length!==1)fail('This question permits one choice. Choose one of the suggested alternatives.');
  if(question.selectionMode==='all'&&choiceIndices.length!==choices.length)fail('Review every suggested item before accepting this select-all question.');
  if(typeof nonce!=='string'||nonce.length<16||nonce.length>80)fail('Invalid acceptance request.');
  let nextExamId=null;
  if(!info.last) {
    if(typeof nextHref!=='string')fail('A uniquely identified Next student/submission link is required.');
    const next=gradingContext(nextHref),fromURL=new URL(href),nextURL=new URL(nextHref);
    if(next.scope!==context.scope||next.submissionId===context.submissionId||nextURL.origin!==fromURL.origin||nextURL.username||nextURL.password||nextURL.hash)fail('The Next link does not point to another submission for this question.');
    nextExamId=state.batch.booklets[o.index+1].id;
    const nextEntry=state.batch.entries.find(e=>e.examId===nextExamId&&e.questionKey===o.questionKey);
    if(!nextEntry?.result?.choices?.length)fail('The next exam has no usable suggestion for this question. Ordered review stopped before advancing.');
    const existing=state.bindings?.[next.scope+':'+next.submissionId];
    if(existing&&existing.examId!==nextExamId)fail('The next Gradescope submission is already linked to a different exam. Check the order.');
    if(Object.entries(state.bindings||{}).some(([key,b])=>b.scope===next.scope&&b.examId===nextExamId&&key!==next.scope+':'+next.submissionId))fail('The next source exam is already linked to another submission. Check the order.');
  } else if(nextHref!==null)fail('The last exam must finish without navigating.');
  return {...state,order:{...o,status:'accepting',pending:{nonce,entryId,choiceIndices:[...choiceIndices],phase:'selecting',fromHref:href,nextHref,nextExamId,expires:now+TTL}}};
}
export function commitAcceptance(state,context,{tabId,href,nonce,selectedCount,now=Date.now()}) {
  const o=state?.order,p=o?.pending;
  if(o?.tabId!==tabId||o.status!=='accepting'||!p||p.phase!=='selecting'||p.nonce!==nonce||p.fromHref!==href||!same(o,context)||now>p.expires||selectedCount!==p.choiceIndices.length)fail('Acceptance expired or selection could not be verified. Stay on this submission and confirm it again.');
  const found=lookupBatch(state,context);
  if(found.error||found.entryId!==p.entryId)fail('The loaded suggestion changed during acceptance.');
  if(p.nextHref===null)return {...state,order:{...o,status:'complete',pending:undefined,reason:'Ordered review complete. The last suggestion was accepted; no next student was opened.'}};
  return {...state,order:{...o,pending:{...p,phase:'navigating',expires:now+TTL}}};
}
export function observeNavigation(state,{tabId,href,loading=false,now=Date.now()}) {
  const o=state?.order;if(!o||o.tabId!==tabId)return state;
  if(o.status==='paused'||o.status==='complete')return state;
  const p=o.pending;
  if(p&&now>p.expires)return pauseOrder(state,'The accepted navigation did not finish in time. Confirm the current exam again.');
  if(href===o.href) {
    if(loading&&!p)return pauseOrder(state,'The page reloaded. Confirm the current exam before continuing ordered review.');
    return state;
  }
  if(!p||p.phase!=='navigating'||href!==p.nextHref)return pauseOrder(state,'Navigation changed outside Accept and next. Confirm the current exam and order again.');
  let context;try{context=gradingContext(href);}catch{return pauseOrder(state,'The page is no longer a supported grading page.');}
  if(context.scope!==o.scope)return pauseOrder(state,'The question changed. Confirm the current question and exam again.');
  try {
    const bound=bindPage(state,context,o.questionKey,p.nextExamId,true,false);
    return {...bound,order:{...o,index:o.index+1,examId:p.nextExamId,submissionId:context.submissionId,href,status:'ready',pending:undefined,reason:''}};
  }catch{return pauseOrder(state,'The next submission conflicts with an existing exam link. Check the order.');}
}
