// Local page guards and explicit rubric application. Identity reads use only the grading payload.
globalThis.__gRaterActions = (() => {
  const context = href => {
    const url=new URL(href),m=url.pathname.match(/^\/courses\/(\d+)\/questions\/(\d+)\/submissions\/(\d+)\/grade\/?$/);
    if(url.protocol!=='https:'||!['gradescope.com','www.gradescope.com'].includes(url.hostname)||url.username||url.password||url.hash||!m)throw Error('Unsupported grading route.');
    return {url,scope:m[1]+':'+m[2],submission:m[3]};
  };
  function findNext(href) {
    const current=context(href),candidates=[];
    for(const element of document.querySelectorAll('a[href]')) {
      if(element.closest('[hidden],[aria-hidden="true"],[inert]')||element.getAttribute('aria-disabled')==='true'||element.disabled)continue;
      const label=['aria-label','title','data-tooltip'].map(k=>element.getAttribute(k)||'').concat(element.innerText||'').join(' ').replace(/\s+/g,' ').trim();
      if(!/\bnext\s+(?:student|submission)\b/i.test(label)||/\b(?:previous|question|ungraded|unanswered|group)\b/i.test(label))continue;
      const r=element.getBoundingClientRect(),style=getComputedStyle(element);
      if(r.width<3||r.height<3||r.left<0||r.top<0||r.right>innerWidth||r.bottom>innerHeight||style.visibility!=='visible'||Number(style.opacity)===0)continue;
      let next;try{next=context(new URL(element.getAttribute('href'),href).href);}catch{continue;}
      if(next.url.origin!==current.url.origin||next.scope!==current.scope||next.submission===current.submission)continue;
      candidates.push({element,href:next.url.href});
    }
    if(candidates.length!==1)throw Error('Could not uniquely identify a visible Next student/submission link. Stay here and use Gradescope navigation manually, then confirm the next exam in Load / link batch.');
    return candidates[0];
  }
  function matching(region,choice,expected) {
    const match=globalThis.__gRaterFindRubric?.(region,choice.description,choice.points);
    if(!expected?.element||!match?.element||!match.element.isConnected||match.element!==expected.element||match.descriptionElement!==expected.descriptionElement)throw Error('The rubric changed. Selection and navigation stopped.');
    return match;
  }
  function verifyChoices(region,choices,expected,isCurrent) {
    if(!isCurrent())throw Error('The submission or layout changed. Selection and navigation stopped.');
    if(choices.length!==expected.length||!choices.length)throw Error('No verified rubric selection.');
    if(new Set(expected.map(m=>m?.element)).size!==expected.length)throw Error('Suggested choices do not identify distinct rubric buttons.');
    for(let i=0;i<choices.length;i++)if(!matching(region,choices[i],expected[i]).selected)throw Error('Gradescope has not confirmed the suggested selection. No next student was opened.');
    return choices.length;
  }
  async function applyChoices({region,choices,expected,isCurrent,wait=ms=>new Promise(resolve=>setTimeout(resolve,ms)),attempts=25}) {
    if(choices.length!==expected.length||!choices.length||new Set(expected.map(m=>m?.element)).size!==expected.length)throw Error('Suggested choices must identify distinct rubric buttons.');
    // Validate all targets before the first mutation. Never toggle an already
    // selected item off, and never substitute the editable description.
    const initial=choices.map((choice,i)=>matching(region,choice,expected[i]));
    for(let i=0;i<choices.length;i++) {
      if(!isCurrent())throw Error('The submission or layout changed. Selection and navigation stopped.');
      const target=matching(region,choices[i],initial[i]);
      if(!target.selected)target.element.click();
      let stable=0;
      for(let attempt=0;attempt<attempts;attempt++) {
        await wait(120);
        if(!isCurrent())throw Error('The submission or layout changed. Selection and navigation stopped.');
        if(matching(region,choices[i],initial[i]).selected){if(++stable>=3)break;}else stable=0;
      }
      if(stable<3)throw Error('Gradescope did not confirm the rubric selection. No next student was opened.');
    }
    return verifyChoices(region,choices,initial,isCurrent);
  }
  function clickNext(next,currentHref) {
    if(location.href!==currentHref)throw Error('The submission changed before navigation.');
    const current=findNext(currentHref);
    if(current.element!==next.element||current.href!==next.href||!current.element.isConnected)throw Error('The Next link changed. Navigation stopped.');
    current.element.click();
  }

  function readIdentity(href){
    const current=context(href);
    if(location.href!==href)throw Error('The grading page changed.');
    const found=[];
    for(const node of document.querySelectorAll('[data-react-props]')){
      const raw=node.getAttribute('data-react-props');
      if(!raw||raw.length>2000000)continue;
      let value;try{value=JSON.parse(raw);}catch{continue;}
      if(!value?.question||!value?.submission||!value?.assignment_submission||!value?.course||!value?.assignment)continue;
      const q=value.question,sub=value.submission,assignment=value.assignment;
      if(String(value.course.id)!==current.scope.split(':')[0]||String(q.id)!==current.scope.split(':')[1]||String(sub.id)!==current.submission)continue;
      if(String(sub.question_id)!==String(q.id)||String(sub.assignment_submission_id)!==String(value.assignment_submission.id)||String(q.assignment_id)!==String(assignment.id))continue;
      let nav;try{nav=context(new URL(value.navigation_urls?.current,href).href);}catch{continue;}
      if(nav.scope!==current.scope||nav.submission!==current.submission)continue;
      if(assignment.settings?.submissions_anonymized||assignment.group_submission)throw Error('Named single-student grading is required for roster matching.');
      const name=typeof sub.owner_names==='string'?sub.owner_names.trim():'',number=String(q.full_index||'').trim();
      if(!name||name.length>160||!number||number.length>40)throw Error('The current student name or question number is unavailable.');
      const labels=[...document.querySelectorAll('#actionBar .actionBar--label abbr[aria-label]')].map(n=>(n.getAttribute('aria-label')||'').trim()).filter(Boolean).map(value=>value.match(/^Currently grading submission \d+ of \d+ by (.+)$/i)?.[1]||value);
      const normalized=v=>v.normalize('NFKD').replace(/\p{M}/gu,'').toLocaleLowerCase('en-US').replace(/\s+/g,' ').trim();
      if(labels.length&&(labels.length!==1||normalized(labels[0])!==normalized(name)))throw Error('The visible student and embedded grading data disagree. Refresh Gradescope before continuing.');
      const identity={href,courseId:String(value.course.id),questionId:String(q.id),submissionId:String(sub.id),assignmentId:String(assignment.id),assignmentSubmissionId:String(value.assignment_submission.id),name,questionNumber:number,assignmentTitle:String(assignment.title||'').slice(0,240)};
      identity.token=JSON.stringify([identity.courseId,identity.questionId,identity.submissionId,identity.assignmentId,identity.assignmentSubmissionId,name,number]);
      found.push(identity);
    }
    if(found.length!==1)throw Error('The current Gradescope student/question data is missing, ambiguous or stale. Refresh the page.');
    return found[0];
  }
  return {findNext,applyChoices,verifyChoices,clickNext,readIdentity};
})();
