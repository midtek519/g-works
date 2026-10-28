// Untrusted imported JSON is data only. Never evaluate markup, paths or code.
const hex=/^[a-f0-9]{32}$/,sha=/^[a-f0-9]{64}$/;
const text=(v,max,empty=false)=>typeof v==='string'&&v.length<=max&&(empty||!!v.trim());
const keys=(v,allowed)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).every(k=>allowed.includes(k));
export function gradingContext(address){
  const u=new URL(address);
  if(u.protocol!=='https:'||!['gradescope.com','www.gradescope.com'].includes(u.hostname))throw new Error('Use an individual Gradescope grading page.');
  const m=u.pathname.match(/^\/courses\/(\d+)\/questions\/(\d+)\/submissions\/(\d+)\/grade\/?$/);
  if(!m)throw new Error('Use an individual Gradescope grading page.');
  return {courseId:m[1],questionId:m[2],submissionId:m[3],scope:`${m[1]}:${m[2]}`};
}
export function validateBatch(raw){
  if(JSON.stringify(raw).length>3_000_000)throw new Error('Use a suggestions JSON file smaller than 3 MB.');
  if(!keys(raw,['format','version','batchId','created','snapshotHash','exam','model','modelDigest','rubricHash','questions','booklets','entries','complete','mappingRequired','identityMatching'])||raw.format!=='rubric-lens-batch'||![1,2].includes(raw.version)||!hex.test(raw.batchId)||!sha.test(raw.snapshotHash)||!sha.test(raw.rubricHash))throw new Error('Choose a Grader suggestions JSON file (format version 1 or 2).');
  if(!keys(raw.exam,['course','term','exam','version'])||!['course','term','exam','version'].every(k=>text(raw.exam[k],160)))throw new Error('The exam metadata is invalid.');
  if(!Array.isArray(raw.questions)||!raw.questions.length||raw.questions.length>100||raw.questions.some(q=>!keys(q,['key','title','selectionMode','number','versionLabel'])||!text(q.key,raw.version===2?80:40)||!/^[A-Za-z0-9_.()-]+$/.test(q.key)||!text(q.title,240)||!['one','all'].includes(q.selectionMode)))throw new Error('The question list is invalid.');
  if(new Set(raw.questions.map(q=>q.key)).size!==raw.questions.length)throw new Error('Question labels must be distinct.');
  if(!Array.isArray(raw.booklets)||!raw.booklets.length||raw.booklets.length>2000||raw.booklets.some(b=>!keys(b,(raw.version===2?['id','label','sourceHash','startPage','pages','student','versionLabel']:['id','label','sourceHash','startPage','pages']))||!hex.test(b.id)||!text(b.label,160)||!sha.test(b.sourceHash)||!Number.isInteger(b.startPage)||b.startPage<1||!Number.isInteger(b.pages)||b.pages<1||b.pages>200))throw new Error('The source exam list is invalid.');
  const exams=new Set(raw.booklets.map(b=>b.id)),questions=new Map(raw.questions.map(q=>[q.key,q]));
  if(raw.version===1&&raw.identityMatching!==undefined)throw new Error('Identity matching requires batch format 2.');
  if(raw.version===2){
    const policy=raw.identityMatching;
    if(!keys(policy,['required','rosterHash','ambiguousNames'])||policy.required!==true||!sha.test(policy.rosterHash)||!Array.isArray(policy.ambiguousNames)||policy.ambiguousNames.length>10000||policy.ambiguousNames.some(n=>!text(n,320)))throw new Error('The reviewed roster identity policy is missing or invalid.');
    if(raw.questions.some(q=>!text(q.number,40)||(q.versionLabel!==undefined&&!text(q.versionLabel,40))))throw new Error('Printed question numbers are required.');
    if(raw.booklets.some(b=>(b.versionLabel!==undefined&&!text(b.versionLabel,40))||!keys(b.student,['name','netid','section'])||!text(b.student.name,160)||!normalizeStudentName(b.student.name)||!/^([a-z][a-z0-9]{0,30})$/.test(b.student.netid)||!text(b.student.section,30,true)))throw new Error('Every exam needs a reviewed roster name and NetID.');
    if(new Set(raw.booklets.map(b=>b.student.netid)).size!==raw.booklets.length)throw new Error('A roster student appears on more than one source exam. Resolve the duplicate in G-Scope.');
  }
  if(exams.size!==raw.booklets.length||!Array.isArray(raw.entries)||raw.entries.length>5000)throw new Error('The suggestion list is invalid.');
  const pairs=new Set(),ids=new Set();
  const entries=raw.entries.map(entry=>{
    if(!keys(entry,['id','examId','questionKey','reviewed','result'])||!hex.test(entry.id)||ids.has(entry.id)||!exams.has(entry.examId)||!questions.has(entry.questionKey)||typeof entry.reviewed!=='boolean')throw new Error('A suggestion has an invalid exam or question reference.');
    const pair=entry.examId+':'+entry.questionKey;if(pairs.has(pair))throw new Error('Duplicate suggestions for the same exam and question.');pairs.add(pair);ids.add(entry.id);
    const r=entry.result;
    if(!keys(r,['rubricItem','explanation','uncertainty','needsReview','choices'])||!text(r.explanation,2000)||!text(r.uncertainty,1000,true)||typeof r.needsReview!=='boolean'||!Array.isArray(r.choices)||r.choices.length>12||r.choices.some(c=>!keys(c,['label','description','points'])||!text(c.label,160)||!text(c.description,4000)||!Number.isFinite(c.points)))throw new Error('A suggestion contains invalid rubric choices.');
    return {...entry,result:{rubricItem:r.choices.map(c=>c.label).join(' / ')||'Review needed',explanation:r.explanation,uncertainty:r.uncertainty,needsReview:r.needsReview||!r.choices.length||(questions.get(entry.questionKey).selectionMode==='one'&&r.choices.length!==1),choices:r.choices.map(c=>({label:c.label,description:c.description,points:c.points}))}};
  });
  return {format:raw.format,version:raw.version,...(raw.version===2?{identityMatching:structuredClone(raw.identityMatching)}:{}),batchId:raw.batchId,snapshotHash:raw.snapshotHash,rubricHash:raw.rubricHash,exam:{...raw.exam},questions:raw.questions.map(q=>({...q})),booklets:raw.booklets.map(b=>structuredClone(b)),entries,complete:raw.complete===true};
}
export function bindPage(state,context,questionKey,examId,confirmed,reuseSubmission=false){
  if(!state?.batch||!state.batch.questions.some(q=>q.key===questionKey)||!state.batch.booklets.some(b=>b.id===examId)||confirmed!==true)throw new Error('Choose and confirm the matching question and source exam.');
  const key=context.scope+':'+context.submissionId;
  // Within one question, each source exam may belong to only one submission.
  if(Object.entries(state.bindings||{}).some(([k,b])=>k!==key&&b.scope===context.scope&&b.examId===examId))throw new Error('That source exam is linked to another submission for this question. Clear the old link before changing it.');
  return {...state,questionMap:{...state.questionMap,[context.scope]:questionKey},bindings:{...state.bindings,[key]:{scope:context.scope,courseId:context.courseId,submissionId:context.submissionId,examId,reuseSubmission:reuseSubmission===true}}};
}
export function lookupBatch(state,context,pageIdentity){
  if(state?.batch?.version===2)return lookupIdentityBatch(state,context,pageIdentity);
  if(!state?.batch)return {error:'Load the Grader suggestions JSON first.'};
  const questionKey=state.questionMap?.[context.scope];
  if(!questionKey)return {error:'Link this Gradescope question to its question label in the loaded batch.'};
  const binding=state.bindings?.[context.scope+':'+context.submissionId]||Object.values(state.bindings||{}).find(b=>b.reuseSubmission&&b.courseId===context.courseId&&b.submissionId===context.submissionId);
  if(!binding)return {error:'Link this Gradescope submission to the matching source exam first.'};
  const entry=state.batch.entries.find(e=>e.examId===binding.examId&&e.questionKey===questionKey);
  if(!entry)return {error:'No prepared suggestion exists for this exam and question in the loaded batch.'};
  return {result:entry.result,exam:state.batch.booklets.find(b=>b.id===binding.examId)?.label,questionKey,reviewed:entry.reviewed,batchId:state.batch.batchId,entryId:entry.id};
}

export function normalizeStudentName(value){
 return String(value||'').normalize('NFKD').replace(/\p{M}/gu,'').toLocaleLowerCase('en-US').replace(/ß/g,'ss').replace(/ς/g,'σ').match(/\p{L}+/gu)?.sort().join(' ')||'';
}
export function normalizeQuestion(value){
 const key=String(value||'').trim().toLowerCase().replace(/\s+/g,'');
 const part=key.match(/^(\d+)(?:\(([a-z])\)|([a-z]))$/);
 return part?part[1]+'.'+String((part[2]||part[3]).charCodeAt(0)-96):key;
}
function checkedPage(context,page){
 if(!page||page.courseId!==context.courseId||page.questionId!==context.questionId||page.submissionId!==context.submissionId||!page.name||!page.questionNumber||!/^\d+$/.test(page.assignmentId)||!/^\d+$/.test(page.assignmentSubmissionId)||!text(page.token,1200))throw Error('The current student/question data is missing or stale. Refresh Gradescope and show the suggestion again.');
 const actual=gradingContext(page.href);
 if(actual.scope!==context.scope||actual.submissionId!==context.submissionId)throw Error('The grading page changed.');
 return page;
}
export function bindIdentityScope(state,context,page,confirmed){
 if(state?.batch?.version!==2||confirmed!==true)throw Error('Load a roster-linked batch and confirm this Gradescope exam.');
 checkedPage(context,page);
 return {...state,identityScope:{courseId:context.courseId,assignmentId:page.assignmentId},order:undefined};
}
export function lookupIdentityBatch(state,context,page){
 try{
  checkedPage(context,page);
  if(state.identityScope?.courseId!==context.courseId||state.identityScope?.assignmentId!==page.assignmentId)return {error:'Confirm this Gradescope exam in Load / link batch before using roster matches.'};
  const name=normalizeStudentName(page.name);
  if(state.batch.identityMatching.ambiguousNames.some(value=>normalizeStudentName(value)===name))return {error:'This name belongs to multiple roster NetIDs. Resolve the identity in Gradescope/G-Scope before applying a suggestion.'};
  const exams=state.batch.booklets.filter(b=>normalizeStudentName(b.student.name)===name);
  if(exams.length!==1)return {error:exams.length?'More than one source exam matches this student. Resolve the duplicate.':'This student has no exam in the loaded version batch. Load the correct version or review the student match.'};
  const questions=state.batch.questions.filter(q=>(!q.versionLabel||q.versionLabel===exams[0].versionLabel)&&normalizeQuestion(q.number)===normalizeQuestion(page.questionNumber));
  if(questions.length!==1)return {error:'The current question does not uniquely match a printed question number in this batch.'};
  const bound=state.identityBindings?.[context.courseId+':'+page.assignmentId+':'+page.assignmentSubmissionId];
  if(bound&&bound!==exams[0].student.netid)return {error:'The student attached to this Gradescope submission changed. Review the identity before continuing.'};
  const exam=exams[0],question=questions[0],entry=state.batch.entries.find(e=>e.examId===exam.id&&e.questionKey===question.key);
  if(!entry)return {error:'No saved suggestion exists for this student and question.'};
  return {result:entry.result,exam:exam.student.name+' · '+exam.student.netid+(exam.versionLabel?' · Version '+exam.versionLabel:''),questionLabel:question.number,questionKey:question.key,reviewed:entry.reviewed,batchId:state.batch.batchId,entryId:entry.id,identity:{token:page.token,netid:exam.student.netid,name:exam.student.name},identityMatched:true};
 }catch(error){return {error:error.message};}
}
