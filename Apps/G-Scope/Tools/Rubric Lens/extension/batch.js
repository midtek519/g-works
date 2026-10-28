const $=id=>document.getElementById(id);const contextId=location.hash.slice(1);let state,context;
const status=(text,error=false)=>{$('status').textContent=text;$('status').classList.toggle('error',error);};
async function send(type,data={}){const r=await chrome.runtime.sendMessage({app:'rubric-lens',type,contextId,...data});if(!r?.ok)throw new Error(r?.error||'This action could not finish.');return r;}
function options(el,items,label){el.replaceChildren();for(const item of items){const opt=document.createElement('option');opt.value=item.id||item.key;opt.textContent=label(item);el.append(opt);}}
async function refresh(){
  const r=await send('batch-state');state=r.state;context=r.context;
  $('summary').textContent=state?.batch?`${state.batch.exam.course} · ${state.batch.exam.term} · ${state.batch.exam.exam} · Version ${state.batch.exam.version}: ${state.batch.entries.length} suggestions, ${state.batch.booklets.length} exams.${state.batch.complete?'':' This is a partial run.'}`:'No batch loaded.';
  $('link-section').hidden=!(state?.batch&&context)||state.batch.version===2;
  $('identity-section').hidden=!(state?.batch?.version===2&&context);
  if(state?.batch?.version===2&&context){$('identity-context').textContent='Gradescope assignment: '+(context.assignmentTitle||'Open a current named grading page')+'. Loaded batch: '+state.batch.exam.exam+' · Version '+state.batch.exam.version+'.';}

  if(state?.batch&&context&&state.batch.version===1){
    $('context').textContent='This link is for the grading page that opened this window. Confirm the source exam below.';
    options($('question'),state.batch.questions,q=>q.key+' · '+q.title);options($('exam'),state.batch.booklets,b=>b.label);
    const mapped=state.questionMap?.[context.scope];if(mapped)$('question').value=mapped;
    const binding=state.bindings?.[context.scope+':'+context.submissionId];if(binding){$('exam').value=binding.examId;$('reuse').checked=binding.reuseSubmission===true;}
    const order=state.order?.tabId===context.tabId?state.order:null;$('ordered').checked=!!order;$('orderConfirmed').checked=false;$('order-confirmation').hidden=!order;$('order-status').textContent=order?`Ordered review: ${order.status}. ${order.reason||'Each acceptance advances only one exam.'}`:'';
    source();
  }
}
function source(){const b=state?.batch.booklets.find(b=>b.id===$('exam').value);$('source').textContent=b?`Source PDF hash ${b.sourceHash.slice(0,12)}… · pages ${b.startPage}–${b.startPage+b.pages-1}. Compare this exam in G-Scope before linking.`:'';}
$('exam').onchange=()=>{source();$('confirmed').checked=false;$('orderConfirmed').checked=false;};
$('question').onchange=()=>{$('confirmed').checked=false;$('orderConfirmed').checked=false;};
$('ordered').onchange=()=>{$('order-confirmation').hidden=!$('ordered').checked;$('orderConfirmed').checked=false;};
$('file').onchange=async()=>{try{const f=$('file').files[0];if(!f||f.size>3_000_000)throw new Error('Choose a suggestions JSON file smaller than 3 MB.');await send('batch-import',{batch:JSON.parse(await f.text())});await refresh();status('Batch loaded for this browser session. Return to Gradescope; confirm its exam once before using roster-matched suggestions.');}catch(e){status(e.message,true);}};
$('save').onclick=async()=>{try{await send('batch-bind',{questionKey:$('question').value,examId:$('exam').value,confirmed:$('confirmed').checked,reuseSubmission:$('reuse').checked,ordered:$('ordered').checked,orderConfirmed:$('orderConfirmed').checked});status($('ordered').checked?'Ordered review confirmed. Return to Gradescope and review each suggestion before choosing Accept and next.':'Link saved. Return to Gradescope. Its prepared suggestion will appear without a model request.');}catch(e){status(e.message,true);}};
$('unlink').onclick=async()=>{try{await send('batch-unlink');await refresh();status('This page’s link removed.');}catch(e){status(e.message,true);}};
$('unlink-exam').onclick=async()=>{try{await send('batch-unlink',{examId:$('exam').value});await refresh();status('Conflicting links for this source exam and question removed. Check the match and save the correct link.');}catch(e){status(e.message,true);}};
$('clear').onclick=async()=>{try{await send('batch-clear');await refresh();status('Loaded suggestions and links discarded from this browser session.');}catch(e){status(e.message,true);}};
refresh().catch(e=>status(e.message,true));

$('identity-link').onclick=async()=>{try{await send('batch-link-identity',{confirmed:true});status('Exam confirmed. Return to Gradescope; Lens matches the current student and question automatically.');}catch(error){status(error.message,true);}};
