/* Question formats are instructor-reviewed. Suggestions never change scoring by themselves. */
window.GScopeResponses=(()=>{
 'use strict';let C;const hints=new Map();let busy=false;
 const names={manual:'Manual / blank workspace',free_response:'Free response with AI',single_choice:'Multiple choice - select one',multiple_choice:'Multiple choice - select all that apply',fill_in:'Fill-in answer'};
 const e=x=>C.esc(x),btn=(s,a,extra='')=>C.button(s,'response-'+a,extra),options=(items,value)=>items.map(([v,t])=>C.option(v,t,value)).join('');
 const split=x=>String(x||'').split(/[\s,;]+/).filter(Boolean).map(x=>x.toUpperCase());
 const list=(q,value)=>'<option value="">Choose rubric item</option>'+q.items.map(i=>C.option(i.label,i.label+' ('+i.points+' points): '+i.description.slice(0,100),value)).join('');
 function view(q,index){
  const r=q.response||{type:'free_response'},t=r.type||'free_response',choice=['single_choice','multiple_choice'].includes(t),keyInfo=q.responseKey,correct=r.correctOrigin!=='manual'&&keyInfo&&keyInfo.status!=='manual'?keyInfo.correct:(r.correct||[]),hint=hints.get(C.S.version.id)?.suggestions?.[q.id];
  let html='<div class="gs-response-editor'+(choice?' gs-response-choice':'')+'" aria-label="Answer key for Version '+e(C.S.version.label)+'"><div class="row gs-response-format-row"><label>Response format<select data-response="type">'+options(Object.entries(names),t)+'</select></label>'+btn(busy?'Checking formats...':'Suggest format','suggest','data-question="'+index+'" '+(busy?'disabled':''))+'</div>';
  if(hint)html+='<p class="help">'+(hint.type?'<strong>Suggested: '+e(names[hint.type])+'</strong>. ':'')+e(hint.reason)+(hint.type&&hint.type!==t?' '+btn('Use suggestion','apply','data-question="'+index+'"'):'')+'</p>';
  if(t==='manual'){html+='<p class="help">Grade each answer yourself, or form and review answer groups. No AI assessment is required.</p>';}else if(t==='free_response'){
   html+='<details><summary>Grading specification</summary><p class="help">Uses this version\'s reviewed answer key, rubric and approved guidance for every submission. Add expected steps or valid alternative methods when useful.</p><label>Expected work / alternative methods (optional)<textarea data-response="expectedWork" rows="3" maxlength="4000">'+e(r.expectedWork||'')+'</textarea></label></details>';
  }else{
   if(t==='single_choice'||t==='multiple_choice'){
    html+='<div class="row gs-response-choice-key"><label>Option labels<input data-response="options" value="'+e((r.options||['A','B','C','D','E']).join(', '))+'" placeholder="A, B, C, D, E"></label><label>'+ (t==='single_choice'?'Correct option':'Correct options')+'<input data-response="correct" value="'+e(correct.join(', '))+'" title="'+e(keyInfo?.message||'')+'" placeholder="Enter reviewed option'+(t==='single_choice'?'':'s')+'"></label></div>';
    if(keyInfo){if(['conflict','ambiguous'].includes(keyInfo.status)||keyInfo.warning)html+='<p class="notice warning">'+e(keyInfo.message||'')+(['conflict','ambiguous'].includes(keyInfo.status)&&keyInfo.candidates?.length?' '+e(keyInfo.candidates.map(c=>c.sources.join(' / ')+': '+c.correct.join(', ')).join('; ')):'')+(keyInfo.warning?' '+e(keyInfo.warning):'')+'</p>';if(keyInfo.status==='manual')html+=btn('Use reviewed sources','use-source','data-question="'+index+'"');}
   }else{
    html+='<label>Accepted answers (one per line; include equivalent forms)<textarea data-response="accepted" rows="3" maxlength="25000">'+e((r.accepted||[]).join('\n'))+'</textarea></label><div class="row"><label>Comparison<select data-response="comparison">'+options([['math','Mathematical expressions'],['exact','Text answers'],['numeric','Numeric values with tolerance']],r.comparison||'exact')+'</select></label>'+(r.comparison==='numeric'?'<label>Absolute tolerance<input data-response="tolerance" type="number" min="0" step="any" value="'+e(r.tolerance||0)+'"></label>':'')+'</div><p class="help">Equivalent mathematical expressions can be grouped together. Review uncertain recognition and group membership before assigning a grade.</p>';
   }
   if((['single_choice','multiple_choice'].includes(t)&&!correct.length)||(t==='fill_in'&&!(r.accepted||[]).length))html+='<p class="notice warning">Choose the correct answer for this version before grading. The format can be saved and shared now.</p>';
   html+='<div class="row"><label>Correct response<select data-response="correctLabel">'+list(q,r.correctLabel)+'</select></label><label>Incorrect / blank response<select data-response="incorrectLabel">'+list(q,r.incorrectLabel)+'</select></label></div>';
   if(t==='multiple_choice'){
    html+='<label>Scoring<select data-response="scoring">'+options([['all_or_nothing','All-or-nothing: exact selected set'],['partial_counts','Partial credit: explicit selection counts']],r.scoring||'all_or_nothing')+'</select></label>';
    if(r.scoring==='partial_counts')html+='<p class="help">A perfect set uses Correct response. Blank responses and combinations without a rule use Incorrect / blank response.</p><div class="gs-partial-rules">'+(r.partialRules||[]).map((p,j)=>'<div class="row" data-response-rule="'+j+'"><label>Correct options selected<input type="number" min="0" max="26" data-rule="right" value="'+p.right+'"></label><label>Incorrect options selected<input type="number" min="0" max="26" data-rule="wrong" value="'+p.wrong+'"></label><label>Rubric item<select data-rule="label">'+list(q,p.label)+'</select></label>'+btn('Remove','remove-rule','data-question="'+index+'" data-rule-index="'+j+'"')+'</div>').join('')+'</div>'+btn('Add partial-credit rule','add-rule','data-question="'+index+'"');
   }
  }
  return html+'</div>';
 }
 function collect(section,q){
  const fields=[...section.querySelectorAll('[data-response]')];if(!fields.length)return;
  // Do not create a setting on untouched legacy free-response questions.
  const form=Object.fromEntries(fields.map(x=>[x.dataset.response,x.value]));
  if(!q.response&&form.type==='free_response'&&!form.expectedWork)return;
  const r={...q.response,type:form.type};
  for(const [key,value] of Object.entries(form))r[key]=['options','correct'].includes(key)?split(value):key==='accepted'?value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean):key==='tolerance'?Number(value):value;
  if(r.type==='multiple_choice'&&r.scoring==='partial_counts')r.partialRules=[...section.querySelectorAll('[data-response-rule]')].map(row=>Object.fromEntries([...row.querySelectorAll('[data-rule]')].map(x=>[x.dataset.rule,x.dataset.rule==='label'?x.value:Number(x.value)])));
  if(['single_choice','multiple_choice'].includes(r.type)&&!r.correctOrigin&&q.responseKey?.status==='resolved'&&JSON.stringify(r.correct)===JSON.stringify(q.responseKey.correct))r.correctOrigin='source';
  q.response=r;
 }
 function input(el){
  if(el.dataset.response!=='correct')return;
  const section=el.closest('.question'),q=C.S.questions[Number(section?.dataset.index)];if(!q?.response)return;
  q.response.correctOrigin='manual';delete q.responseKey;
 }
 async function resolveKey(q){
  if(!q.id||!['single_choice','multiple_choice'].includes(q.response?.type))return;
  const vid=C.S.version.id,previous=JSON.stringify(q.response);
  const result=await C.api('/api/versions/'+vid+'/response-keys',{questions:[{id:q.id,response:q.response,items:q.items,guidance:q.guidance||''}]});
  if(C.S.version.id!==vid||JSON.stringify(q.response)!==previous)return;
  const value=result.questions?.[q.id];if(value){q.response=value.response;q.responseKey=value.responseKey;}
 }
 async function change(el){
  if(!el.dataset.response)return false;
  C.collectQuestions();C.S.dirty=true;
  if(['type','comparison','scoring'].includes(el.dataset.response)){
   const q=C.S.questions[Number(el.closest('.question').dataset.index)];
   if(el.dataset.response==='type')q.response={type:el.value,grouping:q.response?.grouping||'individual',...(['single_choice','multiple_choice'].includes(el.value)?{options:['A','B','C','D','E'],correct:[],scoring:'all_or_nothing',partialRules:[]}:el.value==='fill_in'?{accepted:[],comparison:'math',tolerance:0}:{expectedWork:''})};
   if(el.dataset.response==='type'){delete q.responseKey;await resolveKey(q);}
   C.render();
  }
  return true;
 }
 async function action(el){
  if(!el.dataset.action?.startsWith('response-'))return false;
  C.collectQuestions();const q=C.S.questions[Number(el.dataset.question)],op=el.dataset.action.slice(9),v=C.S.version;
  if(op==='suggest'){
   if(busy)return true;busy=true;C.render();
   try{const result=await C.api('/api/versions/'+v.id+'/response-suggestions',{questions:C.S.questions.map(x=>({id:x.id,items:x.items}))});hints.set(v.id,result);if(result.notice)C.message(result.notice);}
   finally{busy=false;C.render();}return true;
  }
  if(op==='apply'){
   const hint=hints.get(v.id)?.suggestions?.[q.id];if(!hint?.type)return true;
   q.response={type:hint.type,grouping:q.response?.grouping||'individual',...(['single_choice','multiple_choice'].includes(hint.type)?{options:['A','B','C','D','E'],correct:[],scoring:'all_or_nothing',partialRules:[]}:hint.type==='fill_in'?{accepted:[],comparison:'math',tolerance:0}:{expectedWork:''})};
  }
  if(op==='apply'){delete q.responseKey;await resolveKey(q);}
  if(op==='use-source'){q.response.correctOrigin='source';q.response.correct=[];delete q.responseKey;await resolveKey(q);}
  if(op==='add-rule'){q.response.partialRules||=[];q.response.partialRules.push({right:0,wrong:1,label:''});}
  if(op==='remove-rule')q.response.partialRules.splice(Number(el.dataset.ruleIndex),1);
  C.S.dirty=true;C.render();return true;
 }
 return {init:c=>C=c,view,collect,change,action,input};
})();

