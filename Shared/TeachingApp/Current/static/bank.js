/* Shared question-bank workspace. Content stays in the app's in-memory catalogue. */
const QuestionBank=(()=>{
 'use strict';
 const formats={'free-response':'Free response','fill-in':'Math / text fill-in','multiple-select':'MC · select many','multiple-choice':'MC · select one','true-false':'True / false',mixed:'Mixed'};
 let indexSource=null,index=new Map(),matchKey='',matchSource=null,matchCache=[],keyboardBound=false,rowGesturesBound=false;
 const values=v=>Array.isArray(v)?v:v?[v]:[];
 function inBuilder(){return S.section==='handout-builder'&&!!S.assignment;}
 function active(){return S.section==='bank'||inBuilder();}
 function state(){const b=inBuilder()?(S.builderBank??={bankPageSize:S.bankPageSize,bankSort:S.bankSort,bankGroup:S.bankGroup}):S;b.bankSelection??=new Set();b.bankPage??=1;b.bankPageSize??=100;b.bankSort??='topic';b.bankGroup??='none';b.bankTrash??=false;b.bankInspect??=true;b.bankCollapsed??=new Set();if(inBuilder()){const code=S.assignment.course,use=S.assignment.kind==='final'?'exam':S.assignment.kind;if(b.bankCourse?.length!==1||b.bankCourse[0]!==code)b.bankCourse=[code];if(b.bankUse?.length!==1||b.bankUse[0]!==use)b.bankUse=[use];if(b.bankDiscontinued?.length!==1||b.bankDiscontinued[0]!=='no')b.bankDiscontinued=['no'];b.bankTrash=false;b.bankTopic=S.builderBankTopic??=[];}return b;}
 function redraw(){if(inBuilder())capture();render();}

 function records(){if(indexSource!==S.universal){indexSource=S.universal;index=new Map([...(S.universal.questions||[]),...(S.universal.archived_questions||[]),...(S.universal.trashed_questions||[])].map(q=>[q.id,q]));}return index;}
 function format(q){return formats[q.question_format||q.metadata?.type||'free-response']||'Free response';}
 function courses(q){return Object.keys(q.suitability||{}).filter(c=>q.suitability[c]?.length);}
 function topic(q){const selected=values(state().bankCourse).filter(c=>c!=='unassigned'),code=selected.find(c=>q.classifications?.[c])||courses(q)[0],id=q.classifications?.[code]?.topic||q.topics?.[0],t=(S.universal.topics||[]).find(t=>t.id===id);return t?topicLabel(t,code):'Unassigned topic';}
 let topicSource=null,topicIndex=new Map();
 function topicRecord(id){if(topicSource!==S.universal){topicSource=S.universal;topicIndex=new Map((S.universal.topics||[]).map(t=>[t.id,t]));}return topicIndex.get(id);}
 const facets=[
  {id:'course',key:'bankCourse',label:'Course'},
  {id:'semester',key:'bankSemester',label:'Semester',note:'Used in a saved handout or recorded in the source.'},
  {id:'use',key:'bankUse',label:'Suitable for'},
  {id:'format',key:'bankFormat',label:'Response format'},
  {id:'solution',key:'bankSolution',label:'Solution'},
  {id:'discontinued',key:'bankDiscontinued',label:'Discontinued'},
  {id:'topic',key:'bankTopic',label:'Topics'}
 ];
 const facetById=id=>facets.find(f=>f.id===id);
 const includes=(b,f)=>values(b[f.key]??(f.id==='discontinued'?['no']:[]));
 const excludes=(b,f)=>values(b[f.key+'Excluded']);
 function pool(b=state()){return b.bankTrash?(S.universal.trashed_questions||[]):[...(S.universal.questions||[]),...(S.universal.archived_questions||[])];}
 function allowedCourse(code,b){return (!values(b.bankCourse).length||values(b.bankCourse).includes(code))&&!values(b.bankCourseExcluded).includes(code);}
 function questionValues(q,id,b){
  const codes=courses(q);
  if(id==='course')return [...new Set([...codes,...(q.archived?[q.source?.course,...Object.keys(q.archive_classification||{}).filter(c=>/^\d+$/.test(c))].filter(Boolean):[]),...(!codes.length||Object.values(q.classifications||{}).some(c=>c.status==='unassigned')?['unassigned']:[])])];
  if(id==='use')return codes.length?[...new Set(Object.entries(q.suitability||{}).filter(([c])=>allowedCourse(c,b)).flatMap(([,uses])=>uses))]:['none'];
  if(id==='semester'){
   const terms=[...(S.universal.bank_usage?.[q.id]||[]).filter(a=>allowedCourse(a.course,b)).map(a=>a.semester),...(!q.source?.course||allowedCourse(q.source.course,b)?[q.source?.semester,q.provenance?.semester]:[])].filter(t=>/^(fa|sp|su|wi)\d{2}$/.test(t||''));
   return terms.length?[...new Set(terms)]:['__none__'];
  }
  if(id==='topic')return (q.topics||[]).filter(id=>{const labels=topicRecord(id)?.course_labels;return !labels||!Object.keys(labels).length||Object.keys(labels).some(c=>allowedCourse(c,b));});
  if(id==='format')return [q.question_format||q.metadata?.type||'free-response'];
  if(id==='solution')return [!q.solution?.trim()?'none':q.solution_status==='incomplete'?'incomplete':'complete'];
  if(id==='discontinued')return [q.archived?'yes':'no'];
  return [];
 }
 let searchSource=null,searchIndex=new Map();
 function queryMatches(q,query){
  if(!query)return true;if(searchSource!==S.universal){searchSource=S.universal;searchIndex=new Map();}
  if(!searchIndex.has(q.id))searchIndex.set(q.id,[q.id,q.legacy_id,q.question,q.solution,q.archive_category,format(q),...(q.topics||[]).map(id=>{const t=topicRecord(id);return t?[t.label,...Object.values(t.course_labels||{}).flatMap(l=>[l.app_name,l.title,l.section])].join(' '):id;}),...(q.objectives||[]).map(id=>(S.universal.objectives||[]).find(o=>o.id===id)?.description||id)].join(' ').toLocaleLowerCase());
  return searchIndex.get(q.id).includes(query);
 }
 function questionMatches(q,b,skip=''){
  if(!queryMatches(q,String(b.bankQuery||'').trim().toLocaleLowerCase()))return false;
  for(const f of facets){if(f.id===skip||b.bankTrash&&f.id==='discontinued')continue;const yes=includes(b,f),no=excludes(b,f);if(!yes.length&&!no.length)continue;const vals=questionValues(q,f.id,b);if(yes.length&&!yes.some(v=>vals.includes(v))||no.some(v=>vals.includes(v)))return false;}
  return true;
 }
 function matches(){
  const b=state(),key=JSON.stringify([facets.map(f=>[includes(b,f),excludes(b,f)]),b.bankQuery,b.bankTrash,b.bankSort]);if(matchSource===S.universal&&matchKey===key)return matchCache;
  const result=pool(b).filter(q=>questionMatches(q,b));
  const compare=(a,c)=>b.bankSort==='updated'?String(c.updated||c.created||'').localeCompare(String(a.updated||a.created||'')):b.bankSort==='format'?format(a).localeCompare(format(c)):b.bankSort==='id'?0:topic(a).localeCompare(topic(c),undefined,{numeric:true});
  result.sort((a,c)=>compare(a,c)||a.id.localeCompare(c.id,undefined,{numeric:true}));matchSource=S.universal;matchKey=key;matchCache=result;return result;
 }
 function selected(){state();return [...state().bankSelection].map(id=>records().get(id)).filter(Boolean);}
 function page(){const all=matches(),size=state().bankPageSize==='all'?Math.max(1,all.length):[50,100,200].includes(Number(state().bankPageSize))?Number(state().bankPageSize):100,pages=Math.max(1,Math.ceil(all.length/size));state().bankPage=Math.max(1,Math.min(pages,state().bankPage));const start=(state().bankPage-1)*size;return {all,rows:all.slice(start,start+size),start,pages,size};}
 function selectPage(checked){for(const q of page().rows)checked?state().bankSelection.add(q.id):state().bankSelection.delete(q.id);redraw();}
 function pager(){const p=page();return `<div class="bank-pager"><span>${p.all.length?p.start+1:0}–${Math.min(p.start+p.rows.length,p.all.length)} of ${p.all.length}</span><div class="bank-pager-tools"><label class="bank-page-size">Per page<select id="bank-page-size" aria-label="Questions per page">${[[50,'50'],[100,'100'],[200,'200'],['all','All']].map(([value,label])=>option(value,label,state().bankPageSize)).join('')}</select></label><div class="actions"><button type="button" class="quiet small" data-action="bank-page" data-page="${state().bankPage-1}" ${state().bankPage<=1?'disabled':''} aria-label="Previous question page">←</button><span>Page ${state().bankPage} / ${p.pages}</span><button type="button" class="quiet small" data-action="bank-page" data-page="${state().bankPage+1}" ${state().bankPage>=p.pages?'disabled':''} aria-label="Next question page">→</button></div></div></div>`;}

 // A short source-derived label, without invoking the math/PDF renderer.
 function description(q){
  let text=String(q.title||q.metadata?.title||q.question||q.excerpt||'').slice(0,6000)
   .replace(/(?<!\\)%[^\n]*/g,'')
   .replace(/\\TrueFalseExplain\b/g,'For each statement, give a true/false answer and justify it.')
   .replace(/\\CalculateDerivatives\b/g,'Calculate the indicated derivatives without simplifying.')
   .replace(/\\begin\{(tikzpicture|axis|pspicture|cta|ctatikz|blankaxes)\}[\s\S]*?(?:\\end\{\1\}|$)/g,' [diagram] ')
   .replace(/\\begin\{(align\*?|equation\*?|gather\*?|displaymath)\}[\s\S]*?(?:\\end\{\1\}|$)/g,' [expression] ')
   .replace(/\\\([\s\S]*?(?:\\\)|$)|\\\[[\s\S]*?(?:\\\]|$)|(?<!\\)\$\$[\s\S]*?(?:\$\$|$)|(?<!\\)\$[\s\S]*?(?:(?<!\\)\$|$)/g,' [expression] ')
   .replace(/\\vary\b[\s\S]*/g,' [version-dependent content] ')
   .replace(/\\(?:WorkspaceHere|includegraphics|label|input|include|url|phantom)\*?(?:\[[^\]]*\])?\{[^{}]*\}/g,' ')
   .replace(/\\href\{[^{}]*\}/g,'')
   .replace(/\\begin\{(?:multicols|minipage)\}(?:\[[^\]]*\])?\{[^{}]*\}/g,' ')
   .replace(/\\(?:vspace|hspace|rule)\*?(?:\[[^\]]*\])?\{[^{}]*\}(?:\{[^{}]*\})?/g,' ')
   .replace(/\\(?:begin|end)\{[^{}]*\}(?:\[[^\]]*\])?/g,' ');
  const parts=text.split(/\\item\b(?:\[[^\]]*\])?|\n\s*\n/);
  text=parts.map(part=>part.replace(/\\[A-Za-z]+\*?(?:\[[^\]]*\])?/g,' ').replace(/\\([%&#_$])/g,'$1').replace(/[{}~\\]/g,' ').replace(/\s+/g,' ').replace(/\s+([,.;:!?])/g,'$1').trim()).find(part=>part.replace(/\[[^\]]*\]|[^A-Za-z]/g,'').length>3)||'Mathematical question';
  return text.length>180?text.slice(0,177).replace(/\s+\S*$/,'')+'…':text;
 }
 function row(q,position){
  const active=state().question?.id===q.id,chosen=state().bankSelection.has(q.id),usage=S.universal.bank_usage?.[q.id]||[],status=q.bank_trash?'In Trash':q.archived?'Discontinued':q.pending_classification?'Classification pending':q.solution_status==='incomplete'?'Incomplete solution':!q.solution?.trim()?'No solution':'',label=description(q),topicText=topic(q),courseText=courses(q).map(c=>'Math '+c).join(', ');
  return `<article class="bank-library-row ${active?'is-current':''} ${chosen?'is-selected':''}" data-bank-row="${esc(q.id)}"><label class="bank-row-check"><input type="checkbox" data-bank-select="${esc(q.id)}" data-position="${position}" aria-label="Select ${esc(q.id)}" ${chosen?'checked':''}></label><button type="button" class="bank-row-main" data-action="question" data-id="${esc(q.id)}" aria-pressed="${active}" title="${esc(label)}"><span class="bank-row-title">${esc(label)}</span><span class="bank-row-meta"><span class="code" title="${esc(q.legacy_id||q.id)}">${esc(q.id)}</span><span class="bank-row-format">${esc(format(q))}</span><span class="bank-row-topic" title="${esc(courseText+' · '+topicText)}">${esc(topicText)}</span></span>${status||usage.length?`<span class="bank-row-flags">${status?`<span class="bank-row-status">${esc(status)}</span>`:''}${usage.length?`<span>${usage.length} saved handout${usage.length===1?'':'s'}</span>`:''}</span>`:''}</button>${S.assignment&&!q.bank_trash?`<button type="button" class="small bank-add" data-action="add-assignment-question" data-id="${esc(q.id)}" ${!eligible(q,S.assignment.course,S.assignment.kind)||S.assignment.questions.some(x=>x.id===q.id)?'disabled':''}>${S.assignment.questions.some(x=>x.id===q.id)?'Added':'+ Add'}</button>`:''}</article>`;
 }
 function rows(){const p=page();let html='';if(state().bankGroup==='topic'){
  const groups=new Map();p.rows.forEach((q,i)=>{const label=topic(q);if(!groups.has(label))groups.set(label,[]);groups.get(label).push([q,p.start+i]);});html=[...groups].map(([label,qs])=>`<details class="bank-topic-group" data-bank-group="${esc(label)}" ${state().bankCollapsed.has(label)?'':'open'}><summary>${esc(label)}<span>${qs.length}</span></summary>${qs.map(([q,i])=>row(q,i)).join('')}</details>`).join('');
 }else html=p.rows.map((q,i)=>row(q,p.start+i)).join('');return html||`<div class="bank-empty"><h3>${state().bankTrash?'No matching questions in Trash':'No matching questions'}</h3><button type="button" data-action="bank-reset-filters">Reset filters</button></div>`;}
 function selectionBar(){const qs=selected();if(!qs.length)return '';const allowed=qs.length&&!qs.some(q=>q.archived||q.bank_trash||q.pending_classification);return `<div class="bank-selection-bar" id="bank-selection-bar" aria-live="polite"><strong>${qs.length} selected</strong><div class="actions"><button type="button" class="quiet small" data-action="bank-select-all">Select all ${matches().length} matches</button><button type="button" class="quiet small" data-action="bank-clear-selection">Clear</button></div><div class="actions bank-selection-actions">${inBuilder()?'<button type="button" data-action="bank-builder-add-selected">Add selected to handout</button>':state().bankTrash?'<button type="button" data-action="bank-restore">Restore selected</button>':`<button type="button" data-action="workflow-add-selected" ${allowed?'':'disabled'}>${S.assignment?'Add to handout':'Add to new handout'}</button><button type="button" data-action="bank-organize" ${allowed?'':'disabled'}>Organize…</button><button type="button" class="danger quiet" data-action="bank-trash">Move to Trash</button>`}</div></div>`;}

 function displayTools(){const p=page();return `<div class="bank-display-tools"><label>Sort<select id="bank-sort">${[['topic','Topic'],['id','Question ID'],['updated','Recently updated'],['format','Response format']].map(([v,l])=>option(v,l,state().bankSort)).join('')}</select></label><label>Group<select id="bank-grouping">${option('none','No grouping',state().bankGroup)}${option('topic','Topic',state().bankGroup)}</select></label><label class="bank-page-check"><input type="checkbox" data-bank-select-page ${p.rows.length&&p.rows.every(q=>state().bankSelection.has(q.id))?'checked':''} ${p.rows.length?'':'disabled'}>Select page</label></div>`;}
 function view(){state();const p=page(),all=records(),trash=(S.universal.trashed_questions||[]).length;state().bankSelection=new Set([...state().bankSelection].filter(id=>all.has(id)));
  return `<div class="bank-workspace ${state().bankInspect?'':'bank-inspector-hidden'}"><section class="panel bank-browser" aria-label="Question bank"><div class="panel-header bank-main-header"><div class="bank-collection-tabs" aria-label="Bank collection"><button class="${state().bankTrash?'':'active'}" data-action="bank-collection" data-collection="bank">Question Bank</button><button class="${state().bankTrash?'active':''}" data-action="bank-collection" data-collection="trash">${bankIcon('trash')}Trash <span>${trash}</span></button></div><div class="actions">${state().bankTrash?`<button type="button" class="danger" data-action="bank-clear-trash" ${trash?'':'disabled'}>Clear Trash${trash?' ('+trash+')':''}</button>`:''}<button data-action="workflow-import">${bankIcon('import')}Import</button><button data-action="bank-export">${bankIcon('export')}Export TeX</button><button data-action="new-question" class="primary">+ New question</button></div>${expandControl()}</div><div class="bank-filter-tools"><input id="bank-query" type="search" aria-label="Search question bank" value="${esc(state().bankQuery||'')}" placeholder="Search question text, ID, topic, or objective…"><div class="bank-filter-line">${filterControl()}</div>${filterChips()}</div>${displayTools()}${selectionBar()}${state().bankWorking?'<p class="bank-working" role="status">Applying question changes…</p>':''}<div class="bank-results" id="questions" tabindex="-1">${rows()}</div>${pager()}</section><section class="panel bank-inspector" data-bank-inspect="${esc(state().question?.id||'')}" aria-label="Question inspector">${inspector()}</section></div>`;
 }

 function bankIcon(name){
  const paths={trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',import:'<path d="M12 3v12m-4-4 4 4 4-4M4 15v6h16v-6"/>',export:'<path d="M12 16V3m-4 4 4-4 4 4M4 15v6h16v-6"/>',expand:'<path d="M4 12h16m-6-6 6 6-6 6M4 4v16"/>',collapse:'<path d="M20 12H4m6-6-6 6 6 6m10-14v16"/>',filter:'<path d="M3 5h18l-7 8v6l-4 2v-8z"/>'};
  return '<svg class="bank-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+(paths[name]||'')+'</svg>';
 }
 function expandControl(){const open=state().bankInspect;return `<button type="button" class="quiet bank-expand" data-action="bank-toggle-inspector" title="${open?'Expand browser':'Show inspector'}" aria-label="${open?'Expand browser':'Show inspector'}">${bankIcon(open?'expand':'collapse')}</button>`;}
 function filterControl(){const b=state(),count=facets.filter(f=>!inBuilder()||!['course','use','discontinued'].includes(f.id)).reduce((n,f)=>n+includes(b,f).length+excludes(b,f).length,0);return `<button type="button" class="bank-filter-launch" data-action="bank-filters" aria-haspopup="dialog">${bankIcon('filter')}Filters${count?`<span class="bank-filter-badge">${count}</span>`:''}</button>`;}
 function topicFilterRows(b=state()){
  const codes=values(b.bankCourse).filter(c=>c!=='unassigned'),no=values(b.bankCourseExcluded),text=v=>typeof plainLabel==='function'?plainLabel(v):String(v||'').replace(/\\#/g,'#'),rows=[];
  for(const t of S.universal.topics||[]){
   if(t.retired||t.legacy)continue;let codesForTopic=Object.keys(t.course_labels||{}).filter(c=>(!codes.length||codes.includes(c))&&!no.includes(c));if(!codesForTopic.length&&!codes.length&&!Object.keys(t.course_labels||{}).length)codesForTopic=[''];
   for(const course of codesForTopic){const l=t.course_labels?.[course]||{},name=text(t.label||l.title||t.id),details=[l.section?'§ '+text(l.section):'',l.chapter_title&&text(l.chapter_title)!==name?text(l.chapter_title):''].filter(Boolean);rows.push({value:t.id,id:t.id,course,group:course?'Math '+course:'Unassigned course',label:name,detail:details.join(' · '),order:l.chapter_order??9999});}
  }
  const duplicates=new Map();for(const r of rows){const k=[r.course,r.label,r.detail].join('|');duplicates.set(k,(duplicates.get(k)||0)+1);}for(const r of rows)if(duplicates.get([r.course,r.label,r.detail].join('|'))>1)r.detail+=(r.detail?' · ':'')+r.id;
  return rows.sort((a,b)=>a.course.localeCompare(b.course,undefined,{numeric:true})||a.order-b.order||a.label.localeCompare(b.label,undefined,{numeric:true})||a.id.localeCompare(b.id));
 }
 function facetOptions(id,b=state()){
  if(id==='course')return [...S.courses.map(c=>({value:c.code,label:'Math '+c.code})),{value:'unassigned',label:'Unassigned'}];
  if(id==='use')return [{value:'none',label:'None'},...['exam','manual','quiz','worksheet'].map(k=>({value:k,label:handoutKindLabel(k)}))];
  if(id==='topic')return topicFilterRows(b);
  if(id==='format')return Object.entries(formats).map(([value,label])=>({value,label})).sort((a,b)=>a.label.localeCompare(b.label));
  if(id==='solution')return [{value:'complete',label:'Complete'},{value:'incomplete',label:'Incomplete'},{value:'none',label:'None'}];
  if(id==='discontinued')return [{value:'no',label:'No'},{value:'yes',label:'Yes'}];
  if(id==='semester'){
   const terms=new Set(pool(b).flatMap(q=>questionValues(q,id,b)).filter(t=>t!=='__none__'));
   return [...terms].sort((a,b)=>Number(b.slice(2))-Number(a.slice(2))||({wi:0,sp:1,su:2,fa:3}[b.slice(0,2)]??0)-({wi:0,sp:1,su:2,fa:3}[a.slice(0,2)]??0)).map(value=>({value,label:termLabel(value)})).concat({value:'__none__',label:'No semester recorded'});
  }
  return [];
 }
 function filterModel(b=state()){
  return facets.filter(f=>!b.bankTrash||f.id!=='discontinued').map(f=>{
   const context={...b,[f.key]:[],[f.key+'Excluded']:[]},counts=new Map();
   for(const q of pool(b))if(questionMatches(q,context,f.id))for(const v of new Set(questionValues(q,f.id,context)))counts.set(v,(counts.get(v)||0)+1);
   const options=facetOptions(f.id,b),yes=includes(b,f),no=excludes(b,f);
   for(const value of [...yes,...no])if(!options.some(o=>o.value===value))options.push(facetOptions(f.id,{...b,bankCourse:[],bankCourseExcluded:[]}).find(o=>o.value===value)||{value,label:value});
   const locked=inBuilder()&&['course','use','discontinued'].includes(f.id);
   return {...f,locked,options:options.map(o=>({...o,count:counts.get(o.value)||0,mode:yes.includes(o.value)?1:no.includes(o.value)?2:0})).filter(o=>o.count||o.mode)};
  });
 }
 function filterChips(){const b=state(),chips=[];for(const f of facets){if(inBuilder()&&['course','use','discontinued'].includes(f.id)||b.bankTrash&&f.id==='discontinued')continue;const options=facetOptions(f.id,b);for(const [mode,list] of [[1,includes(b,f)],[2,excludes(b,f)]])for(const value of list){const o=options.find(o=>o.value===value)||{label:value},label=f.label+': '+o.label;chips.push(`<button type="button" class="bank-filter-chip" data-filter-state="${mode}" data-action="bank-filter-remove" data-facet="${f.id}" data-value="${esc(value)}" title="Remove ${mode===1?'include':'exclude'} filter: ${esc(label)}">${esc(label)}<span aria-hidden="true">×</span></button>`);}}
  return chips.length?'<div class="bank-filter-chips" aria-label="Active filters">'+chips.join('')+'</div>':'';
 }
 let filterSession=null;
 function validFilterSession(){return !!filterSession&&active()&&state()===filterSession.owner&&S.assignment===filterSession.assignment;}
 function refreshFilterResults(){const b=state();b.bankPage=1;b.bankAnchor=null;if(inBuilder())S.builderBankTopic=values(b.bankTopic);if(b.question&&!matches().some(q=>q.id===b.question.id))b.question=null;redraw();if(filterSession)paintFilters();}
 function setFilterMode(id,value,mode,only=false){
  if(filterSession&&!validFilterSession())throw Error('The question context changed. Reopen Filters.');const f=facetById(id),b=state();if(!f||inBuilder()&&['course','use','discontinued'].includes(id))return false;
  const known=facetOptions(id,{...b,bankCourse:[],bankCourseExcluded:[]});if(!known.some(o=>o.value===value))return false;
  b[f.key]=(only?[]:includes(b,f)).filter(v=>v!==value);b[f.key+'Excluded']=(only?[]:excludes(b,f)).filter(v=>v!==value);if(mode===1)b[f.key].push(value);if(mode===2)b[f.key+'Excluded'].push(value);if(inBuilder()&&id==='topic')S.builderBankTopic=b.bankTopic;refreshFilterResults();return true;
 }
 function cycleFilter(id,value,backwards=false,only=false){const f=facetById(id);if(!f)return false;const b=state(),mode=includes(b,f).includes(value)?1:excludes(b,f).includes(value)?2:0;return setFilterMode(id,value,only?1:(mode+(backwards?2:1))%3,only);}
 function clearFilters(defaults=false){if(filterSession&&!validFilterSession())throw Error('The question context changed. Reopen Filters.');const b=state();for(const f of facets){if(inBuilder()&&['course','use','discontinued'].includes(f.id))continue;b[f.key]=defaults&&f.id==='discontinued'?['no']:[];b[f.key+'Excluded']=[];}if(defaults)b.bankQuery='';if(inBuilder())S.builderBankTopic=b.bankTopic;refreshFilterResults();}
 function filterSections(){
  const query=(filterSession?.search||'').trim().toLocaleLowerCase();return filterModel().map(f=>{
   const options=f.options.filter(o=>!query||[f.label,o.label,o.group,o.detail,o.value].join(' ').toLocaleLowerCase().includes(query));if(!options.length)return '';
   const groups=[...new Set(options.map(o=>o.group||''))];return `<section class="bank-filter-section ${f.id==='topic'?'bank-filter-topics':''}" data-bank-facet="${f.id}"><div class="bank-filter-section-heading"><h3>${f.label}${f.locked?'<small>From handout</small>':''}</h3>${!f.locked?`<button type="button" class="quiet small" data-filter-clear="${f.id}">Clear</button>`:''}</div>${f.note?`<p class="bank-filter-note">${f.note}</p>`:''}${groups.map(group=>`<div class="bank-filter-group">${group?`<h4>${esc(group)}</h4>`:''}<div class="bank-filter-options">${options.filter(o=>(o.group||'')===group).map(o=>`<button type="button" class="bank-filter-pill" data-filter-facet="${f.id}" data-filter-value="${esc(o.value)}" data-filter-state="${o.mode}" aria-pressed="${o.mode!==0}" aria-label="${esc(f.label+': '+o.label+(o.group?' · '+o.group:'')+(o.detail?' · '+o.detail:'')+': '+['any','include','exclude'][o.mode]+', '+o.count+' questions')}" ${f.locked?'disabled':''}><span><strong>${esc(o.label)}</strong>${o.detail?`<small>${esc(o.detail)}</small>`:''}</span><span class="bank-filter-option-count">${o.count}</span></button>`).join('')}</div></div>`).join('')}</section>`;
  }).join('')||'<p class="help">No matching filter choices.</p>';
 }
 function paintFilters(){
  if(!validFilterSession()){if(filterSession)dialog.close();return;}const body=document.getElementById('bank-filter-sections');if(!body)return;
  const top=body.scrollTop,focused=document.activeElement?.dataset,focusFacet=focused?.filterFacet,focusValue=focused?.filterValue;body.innerHTML=filterSections();body.scrollTop=top;
  const count=document.getElementById('bank-filter-count');if(count)count.textContent=matches().length+' matching questions';
  if(focusFacet)[...body.querySelectorAll('[data-filter-value]')].find(el=>el.dataset.filterFacet===focusFacet&&el.dataset.filterValue===focusValue)?.focus({preventScroll:true});
 }
 function openFilters(){
  if(inBuilder())capture();filterSession={owner:state(),assignment:S.assignment,search:''};
  modal('Question filters',`<div class="bank-filter-toolbar"><input id="bank-filter-search" type="search" placeholder="Find a filter or topic…" aria-label="Find a filter or topic"><button type="button" id="bank-filter-clear">Clear all</button><button type="button" id="bank-filter-reset">Reset</button></div><div class="bank-filter-legend"><span class="filter-legend-yes">Include</span><span class="filter-legend-no">Exclude</span><span class="filter-legend-any">Any</span><span class="bank-filter-gesture">Click to cycle · right-click to reverse</span></div><div id="bank-filter-sections" class="bank-filter-sections">${filterSections()}</div><div class="bank-filter-footer"><span id="bank-filter-count" role="status" aria-live="polite">${matches().length} matching questions</span><span class="help">Updates immediately</span><button type="button" class="primary" id="bank-filter-done">Done</button></div>`);
  dialog.classList?.add('bank-filter-dialog');dialog.addEventListener?.('close',()=>{filterSession=null;dialog.classList?.remove('bank-filter-dialog');document.querySelector('[data-action="bank-filters"]')?.focus();},{once:true});
  const body=document.getElementById('bank-filter-sections');
  body?.addEventListener('click',event=>{if(!validFilterSession()){dialog.close();return;}const pill=event.target.closest('[data-filter-value]'),clear=event.target.closest('[data-filter-clear]');if(pill&&!pill.disabled)cycleFilter(pill.dataset.filterFacet,pill.dataset.filterValue,false,event.shiftKey);if(clear){const f=facetById(clear.dataset.filterClear),b=state();b[f.key]=[];b[f.key+'Excluded']=[];if(inBuilder()&&f.id==='topic')S.builderBankTopic=b.bankTopic;refreshFilterResults();}});
  body?.addEventListener('contextmenu',event=>{if(!validFilterSession()){dialog.close();return;}const pill=event.target.closest('[data-filter-value]');if(pill&&!pill.disabled){event.preventDefault();cycleFilter(pill.dataset.filterFacet,pill.dataset.filterValue,true,event.shiftKey);}});
  document.getElementById('bank-filter-search')?.addEventListener('input',event=>{filterSession.search=event.target.value;paintFilters();});
  document.getElementById('bank-filter-clear')?.addEventListener('click',()=>clearFilters());document.getElementById('bank-filter-reset')?.addEventListener('click',()=>clearFilters(true));document.getElementById('bank-filter-done')?.addEventListener('click',()=>dialog.close());document.getElementById('bank-filter-search')?.focus();
 }
 function builderBrowser(){const b=state();b.bankSelection=new Set([...b.bankSelection].filter(id=>{const q=records().get(id);return q&&eligible(q,S.assignment.course,S.assignment.kind);}));return `<section class="panel builder-available bank-browser"><div class="panel-header bank-main-header"><h2>Available questions</h2><div class="actions"><button data-action="new-question" class="primary">+ New question</button><button data-action="workflow-import">${bankIcon('import')}Import</button></div>${expandControl()}</div><div class="bank-filter-tools"><input id="bank-query" type="search" aria-label="Search available questions" value="${esc(b.bankQuery||'')}" placeholder="Find a question…"><div class="bank-filter-line">${filterControl()}</div>${filterChips()}</div>${displayTools()}${selectionBar()}<div class="bank-results" id="questions" tabindex="-1">${rows()}</div>${pager()}</section>`;}
 function builderInspector(){return `<section class="panel bank-inspector builder-question-inspector" data-bank-inspect="${esc(state().question?.id||'')}" aria-label="Question inspector">${inspector()}</section>`;}
 function builderClass(){return 'bank-builder-workspace'+(state().bankInspect?'':' bank-inspector-hidden');}
 function setBuilderTopics(values){capture();S.builderBankTopic=values;const b=state();b.bankPage=1;b.bankAnchor=null;if(b.question&&!matches().some(q=>q.id===b.question.id))b.question=null;redraw();}
 function inspectorActions(q){if(inBuilder()){const i=S.assignment.questions.findIndex(item=>item.id===q.id);return `<div class="actions bank-question-actions"><button data-action="builder-preview-question" data-id="${esc(q.id)}" ${isRunning()?'disabled':''}>Preview</button>${i<0?`<button data-action="add-assignment-question" data-id="${esc(q.id)}" ${eligible(q,S.assignment.course,S.assignment.kind)?'':'disabled'}>+ Add to handout</button>`:`<button class="quiet" data-action="remove-question" data-index="${i}">Remove from handout</button>`}</div>`;}const blocked=q.archived||q.pending_classification||q.bank_trash;return `<div class="actions bank-question-actions">${!q.bank_trash?'<button data-action="preview-question" title="Preview PDF with solution">Preview</button><button data-action="copy-question" title="Copy as a new bank question">Copy as new</button><button data-action="bank-export-one">Export TeX</button>':''}${!blocked?'<button data-action="edit-question">Edit</button><button class="quiet" data-action="bank-organize-one">Organize…</button>':''}${q.bank_trash?'<button data-action="bank-restore-one">Restore question</button>':'<button class="quiet danger" data-action="bank-trash-one">Trash</button>'}</div>`;}
 function inspector(){state();const q=state().question;if(!q)return '<div class="bank-inspector-empty"><h2>Inspect a question</h2><p>Select a question to read it, view its solution, or manage it.</p></div>';
  const result=matches(),position=result.findIndex(item=>item.id===q.id),usage=S.universal.bank_usage?.[q.id]||[],actions=inspectorActions(q),classes=Object.entries(q.classifications||{});
  return `<div class="bank-inspector-nav"><span>${position>=0?position+1+' / '+result.length:'Selected question'}</span><div class="actions"><button class="quiet small" data-action="bank-inspect-prev" ${position<=0?'disabled':''}>← Previous</button><button class="quiet small" data-action="bank-inspect-next" ${position<0||position>=result.length-1?'disabled':''}>Next →</button><button class="quiet small" data-action="bank-toggle-inspector" aria-label="Close question inspector">Close</button></div></div><div class="bank-inspector-heading"><h2 class="code">${esc(q.id)}</h2>${q.legacy_id?`<span>${esc(q.legacy_id)}</span>`:''}<span class="tag">${esc(format(q))}</span>${q.bank_trash?'<span class="tag">In Trash</span>':q.archived?'<span class="tag">Discontinued</span>':''}</div>${actions}${q.pending_classification?'<div class="notice">This question’s classification is awaiting approval. You can copy it as a new question.</div>':''}<div class="bank-question-reading"><h3>Question</h3><div class="question-pretty">${prettyLatex(q.question||q.excerpt||'')}</div><details class="bank-solution"><summary>Solution <span>${esc(q.solution_status||(!q.solution?.trim()?'none':'complete'))}</span></summary><div class="question-pretty">${prettyLatex(q.solution||'No solution recorded.')}</div></details><details class="bank-classifications"><summary>Classification & use</summary>${classes.map(([code,c])=>{const t=(S.universal.topics||[]).find(t=>t.id===c.topic);return `<div><strong>Math ${esc(code)} · ${t?esc(topicLabel(t,code)):'Unassigned topic'}</strong><p>${esc((q.suitability?.[code]||[]).map(handoutKindLabel).join(', '))}</p>${c.objectives?.length?'<ul>'+c.objectives.map(id=>'<li>'+esc((S.universal.objectives||[]).find(o=>o.id===id)?.description||id)+'</li>').join('')+'</ul>':''}</div>`;}).join('')||'<p>Unassigned</p>'}</details><details class="bank-source"><summary>LaTeX source</summary><h4>Question</h4><pre>${esc(q.question||'')}</pre><h4>Solution</h4><pre>${esc(q.solution||'')}</pre></details>${usage.length?`<details class="bank-usage"><summary>Used in ${usage.length} saved handout${usage.length===1?'':'s'}</summary><ul>${usage.map(a=>`<li>Math ${esc(a.course)} · ${esc(termLabel(a.semester))} · ${esc(a.title)}</li>`).join('')}</ul></details>`:''}</div>${actions}`;
 }
 function inspect(id){
  const q=records().get(id);if(!q)return;const wasCurrent=state().question?.id===id,previousPage=state().bankPage;state().question=q;state().bankInspect=true;const p=page(),i=p.all.findIndex(q=>q.id===id);if(i>=0)state().bankPage=Math.floor(i/p.size)+1;
  const workspace=document.querySelector(inBuilder()?'.bank-builder-workspace':'.bank-workspace'),panel=workspace?.querySelector('.bank-inspector');
  // Preserve the row nodes so the second click can produce a native double-click.
  if(workspace&&panel&&previousPage===state().bankPage){
   workspace.classList.remove('bank-inspector-hidden');document.querySelectorAll('[data-bank-row]').forEach(row=>{const active=row.dataset.bankRow===id;row.classList.toggle('is-current',active);row.querySelector('.bank-row-main')?.setAttribute('aria-pressed',String(active));});
   if(!wasCurrent||!panel.querySelector('.bank-question-reading')){panel.dataset.bankInspect=id;panel.innerHTML=inspector();panel.scrollTop=0;}
   const toggle=workspace.querySelector('.bank-main-header [data-action="bank-toggle-inspector"]');if(toggle)toggle.textContent='Expand browser';
  }else redraw();
  document.querySelector('[data-bank-row="'+id+'"]')?.scrollIntoView?.({block:'nearest'});
 }
 function navigate(delta){const result=matches(),i=result.findIndex(q=>q.id===state().question?.id),next=i<0?0:i+delta;if(result[next])inspect(result[next].id);}
 function bind(){if(!active())return;state();const owner=state();
  document.getElementById('bank-query')?.addEventListener('input',e=>{state().bankQuery=e.target.value;state().bankPage=1;state().bankAnchor=null;const start=e.target.selectionStart,end=e.target.selectionEnd;clearTimeout(state().bankQueryTimer);state().bankQueryTimer=setTimeout(()=>{if(!active()||state()!==owner)return;redraw();const input=document.getElementById('bank-query');input?.focus();input?.setSelectionRange?.(start,end);},150);});
  for(const [id,key] of [['bank-sort','bankSort'],['bank-grouping','bankGroup']])document.getElementById(id)?.addEventListener('change',e=>{S[key]=e.target.value;state().bankPage=1;state().bankAnchor=null;redraw();});
  document.getElementById('bank-page-size')?.addEventListener('change',e=>{state().bankPageSize=e.target.value==='all'?'all':Number(e.target.value);if(inBuilder())S.bankPageSize=state().bankPageSize;state().bankPage=1;state().bankAnchor=null;redraw();document.getElementById('questions')?.scrollTo?.(0,0);});
  document.querySelector('[data-bank-select-page]')?.addEventListener('change',e=>selectPage(e.target.checked));
  document.querySelectorAll('[data-bank-select]').forEach(el=>{let shifted=false;el.addEventListener('click',e=>shifted=e.shiftKey);el.addEventListener('change',()=>{const position=Number(el.dataset.position),all=matches();if(shifted&&state().bankAnchor!==null&&state().bankAnchor!==undefined){for(let i=Math.min(state().bankAnchor,position);i<=Math.max(state().bankAnchor,position);i++)if(all[i])el.checked?state().bankSelection.add(all[i].id):state().bankSelection.delete(all[i].id);}else el.checked?state().bankSelection.add(el.dataset.bankSelect):state().bankSelection.delete(el.dataset.bankSelect);state().bankAnchor=position;redraw();});});
  document.querySelectorAll('[data-bank-group]').forEach(el=>el.addEventListener('toggle',()=>el.open?state().bankCollapsed.delete(el.dataset.bankGroup):state().bankCollapsed.add(el.dataset.bankGroup)));
  if(!rowGesturesBound){rowGesturesBound=true;document.addEventListener('dblclick',e=>{if(!active()||dialog.open||state().bankWorking||e.target.closest('input,label,select,textarea,a,button:not(.bank-row-main)'))return;const row=e.target.closest('[data-bank-row]'),id=row?.dataset.bankRow;if(!id||!records().has(id))return;e.preventDefault();state().bankSelection.has(id)?state().bankSelection.delete(id):state().bankSelection.add(id);state().bankAnchor=matches().findIndex(q=>q.id===id);redraw();});}
  if(!keyboardBound){keyboardBound=true;document.addEventListener('keydown',e=>{if(!active()||dialog.open||e.ctrlKey||e.metaKey||e.altKey||e.target.closest('input,textarea,select,[contenteditable="true"]'))return;if(e.key==='j'||e.key==='k'){e.preventDefault();navigate(e.key==='j'?1:-1);}});}
 }
 async function apply(operation,qs,details={}){if(state().bankWorking)throw Error('Let the current question changes finish.');state().bankWorking=true;redraw();
  try{const result=await api('/api/universal/bank',{operation,items:qs.map(q=>({id:q.id,revision:q.revision})),bank_revision:S.universal.bank_revision,confirmed:true,...details});S.universal=result;indexSource=null;state().bankSelection.clear();const current=state().question?.id;state().question=current?(result.questions||[]).concat(result.archived_questions||[],result.trashed_questions||[]).find(q=>q.id===current)||null:null;if(operation==='trash'&&!state().bankTrash||operation==='restore'&&state().bankTrash)state().question=null;dialog.close();toast((operation==='organize'?'Updated ':operation==='restore'?'Restored ':operation==='purge'?'Cleared Trash: ':'Moved to Trash: ')+result.bank_action.count+' question'+(result.bank_action.count===1?'':'s')+'.');}
  finally{state().bankWorking=false;redraw();}
 }
 function confirmTrash(qs){if(!qs.length)return;modal('Move questions to Trash',`<p>Move ${qs.length} question${qs.length===1?'':'s'} to Trash?</p><p class="help">Future manual builds exclude these questions. Saved handouts keep their pinned revisions. You can restore questions from Trash.</p><ul class="bank-confirm-list">${qs.slice(0,8).map(q=>`<li>${esc(q.id)} · ${esc(topic(q))}</li>`).join('')}${qs.length>8?'<li>… and '+(qs.length-8)+' more</li>':''}</ul><button type="button" class="danger" id="bank-confirm-action">Move to Trash</button>`);document.getElementById('bank-confirm-action').addEventListener('click',()=>run(()=>apply('trash',qs)));}
 function organize(qs,course){if(!qs.length)return;if(qs.some(q=>q.archived||q.bank_trash||q.pending_classification))throw Error('Organize active questions with approved classifications.');
  const common=S.courses.map(c=>c.code).filter(code=>qs.every(q=>courses(q).includes(code))),code=course||values(state().bankCourse).find(c=>common.includes(c))||common[0]||values(state().bankCourse).find(c=>S.courses.some(x=>x.code===c))||courses(qs[0])[0]||S.course,topics=orderedTopics(code);
  modal('Organize '+qs.length+' question'+(qs.length===1?'':'s'),`<form id="bank-organize-form">${field('Course',`<select id="bank-organize-course">${S.courses.map(c=>option(c.code,'Math '+c.code,code)).join('')}</select>`)}${field('Primary topic',`<select id="bank-organize-topic">${option('__keep__','Keep current topics','__keep__')}${option('','Unassigned topic','__keep__')}${topics.map(t=>option(t.id,topicLabel(t,code),'__keep__')).join('')}</select>`)}<div id="bank-organize-objectives"></div><fieldset class="bank-organize-uses"><legend>Suitable for</legend>${['exam','manual','quiz','worksheet'].map(use=>{const count=qs.filter(q=>q.suitability?.[code]?.includes(use)).length;return `<label class="check-row"><input type="checkbox" data-bank-purpose="${use}" data-mixed="${count>0&&count<qs.length}" ${count===qs.length?'checked':''}>${esc(handoutKindLabel(use))}${count>0&&count<qs.length?'<span class="help">mixed</span>':''}</label>`;}).join('')}</fieldset><p class="help">Topic changes update this course’s manual placement. Saved handouts keep their current revisions.</p><button type="submit" class="primary" id="bank-organize-apply" disabled>Apply to ${qs.length} question${qs.length===1?'':'s'}</button></form>`);
  document.getElementById('bank-organize-course').addEventListener('change',e=>organize(qs,e.target.value));const updateApply=()=>{const button=document.getElementById('bank-organize-apply');if(button)button.disabled=document.getElementById('bank-organize-topic').value==='__keep__'&&![...document.querySelectorAll('[data-bank-purpose]')].some(el=>el.dataset.changed==='true');};document.querySelectorAll('[data-bank-purpose]').forEach(el=>{el.indeterminate=el.dataset.mixed==='true';const initial=el.checked;el.addEventListener('change',()=>{el.dataset.changed=el.dataset.mixed==='true'||el.checked!==initial?'true':'false';const note=el.closest('label')?.querySelector('.help');if(note)note.hidden=true;updateApply();});});
  document.getElementById('bank-organize-topic').addEventListener('change',e=>{const target=document.getElementById('bank-organize-objectives'),objectives=(S.universal.objectives||[]).filter(o=>!o.retired&&o.topic_ids?.includes(e.target.value));updateApply();target.innerHTML=objectives.length?'<fieldset><legend>Learning objectives</legend>'+objectives.map(o=>`<label class="check-row"><input type="checkbox" data-bank-objective value="${esc(o.id)}">${esc(o.description)}</label>`).join('')+'</fieldset>':'';});
  document.getElementById('bank-organize-form').addEventListener('submit',e=>{e.preventDefault();run(async()=>{const details={course:code,uses_add:[],uses_remove:[]};document.querySelectorAll('[data-bank-purpose][data-changed="true"]').forEach(el=>details[el.checked?'uses_add':'uses_remove'].push(el.dataset.bankPurpose));const choice=document.getElementById('bank-organize-topic').value;if(choice!=='__keep__'){details.topic=choice;details.objectives=[...document.querySelectorAll('[data-bank-objective]:checked')].map(el=>el.value);}await apply('organize',qs,details);});});
 }
 function exportDialog(one=false){
  const chosen=one?[state().question]:selected(),matching=matches(),all=[...(S.universal.questions||[]),...(S.universal.archived_questions||[])];
  const scopes=[...(chosen.length?[['selected',chosen,'Selected questions']]:[]),['matching',matching,'Matching questions'],['all',all,'Entire bank']].filter(([,qs])=>qs.length);
  if(!scopes.length)throw Error('There are no questions to export.');
  modal('Export questions',`<form id="bank-export-form">${field('Questions',`<select id="bank-export-scope">${scopes.map(([id,qs,label],i)=>option(id,label+' ('+qs.length+')',scopes[0][0])).join('')}</select>`)}<label class="check-row"><input id="bank-export-solutions" type="checkbox" checked>Include solutions</label><label class="check-row"><input id="bank-export-keep-copy" type="checkbox" checked>Also keep a copy in the standard export folder</label><p class="help">The TeX file includes embedded figures. Use Import to bring it into another question bank, then review its course and topic.</p><button class="primary">Export TeX</button></form>`);
  const form=document.getElementById('bank-export-form');
  form.onsubmit=event=>{event.preventDefault();run(async()=>{
   const qs=scopes.find(([id])=>id===document.getElementById('bank-export-scope').value)[1],solutions=document.getElementById('bank-export-solutions').checked,keepCopy=document.getElementById('bank-export-keep-copy').checked,submit=form.querySelector?.('button');
   if(submit){submit.disabled=true;submit.textContent='Preparing export…';}
   try{
    const result=await api('/api/universal/export',{ids:qs.map(q=>q.id),solutions,keep_copy:keepCopy});
    if(dialog.open===false)return;
    modal('Question export ready',`<p>${result.count} question${result.count===1?'':'s'}${result.figures?' with '+result.figures+' figure'+(result.figures===1?'':'s'):''}.</p>${result.standard_copy?'<p class="help">A copy is also kept in the standard export folder.</p>':''}<a id="bank-export-download" class="primary button" href="${esc(result.url)}" download="questions.tex">Save TeX…</a>`);
    document.getElementById('bank-export-download')?.click();
   }finally{if(submit){submit.disabled=false;submit.textContent='Export TeX';}}
  });};
 }
 async function action(a,t){if(active()&&a==='question'){inspect(t.dataset.id);return true;}if(!active()||!a.startsWith('bank-'))return false;state();
  if(a==='bank-toggle-inspector'){state().bankInspect=!state().bankInspect;redraw();return true;}
  if(a==='bank-page'){state().bankPage=Number(t.dataset.page);redraw();document.getElementById('questions')?.scrollTo?.(0,0);return true;}
  if(a==='bank-collection'){state().bankTrash=t.dataset.collection==='trash';state().bankPage=1;state().bankSelection.clear();state().bankAnchor=null;state().question=null;redraw();return true;}
  if(a==='bank-select-all'){state().bankSelection=new Set(matches().map(q=>q.id));redraw();return true;}
  if(a==='bank-clear-selection'){state().bankSelection.clear();state().bankAnchor=null;redraw();return true;}
  if(a==='bank-reset-filters'){clearFilters(true);return true;}
  if(a==='bank-inspect-prev'||a==='bank-inspect-next'){navigate(a==='bank-inspect-prev'?-1:1);return true;}
  if(a==='bank-builder-add-selected'&&inBuilder()){const qs=selected().filter(q=>!S.assignment.questions.some(item=>item.id===q.id));if(S.assignment.questions.length+qs.length>150)throw Error('A handout can contain up to 150 questions. Select fewer questions.');if(qs.some(q=>!eligible(q,S.assignment.course,S.assignment.kind)))throw Error('Choose questions suitable for this handout.');for(const q of qs)addQuestion(q.id);state().bankSelection.clear();redraw();return true;}
  if(a==='bank-filters'){openFilters();return true;}
  if(a==='bank-filter-remove'){setFilterMode(t.dataset.facet,t.dataset.value,0);return true;}
  if(inBuilder())return false;
  if(a==='bank-export'||a==='bank-export-one'){exportDialog(a.endsWith('-one'));return true;}
  if(a==='bank-organize'||a==='bank-organize-one'){organize(a.endsWith('-one')?[state().question]:selected());return true;}
  if(a==='bank-clear-trash'){if(inBuilder())return true;const qs=S.universal.trashed_questions||[];if(!qs.length)return true;modal('Clear Question Bank Trash',`<p>Remove all ${qs.length} questions from Trash across all courses?</p><p class="help">These questions will no longer be available to Restore. Saved handouts keep their pinned revisions, and recovery snapshots are retained.</p><button type="button" class="danger" id="bank-purge-confirm">Clear Trash (${qs.length})</button>`);document.getElementById('bank-purge-confirm').addEventListener('click',()=>run(()=>apply('purge',qs)));return true;}
  if(a==='bank-trash'||a==='bank-trash-one'){confirmTrash(a.endsWith('-one')?[state().question]:selected());return true;}
  if(a==='bank-restore'||a==='bank-restore-one'){const qs=a.endsWith('-one')?[state().question]:selected();if(qs.length)await apply('restore',qs);return true;}
  return false;
 }
 return {view,rows,matches,inspector,bind,action,records,page,selected,format,topic,description,builderBrowser,builderInspector,builderClass,setBuilderTopics,topicFilterRows,filterControl,filterChips,filterModel,facetOptions,openFilters,cycleFilter,setFilterMode,clearFilters};
})();

