/* Local filter UI. Draft choices are committed only by Apply. No network calls. */
window.Math135Filters = (() => {
  const fields=[['semester','Semester'],['lecturer','Lecturer'],['recitation','Recitation Instructor'],['unit','School / Unit'],['class','Class Year'],['curric','Major / Curriculum']];
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fresh=()=>({version:1,join:'and',groups:{}});
  const emptyGroup=()=>({yes:[],no:[],yes_mode:'or',no_mode:'or',combine:'and'});
  const clone=value=>JSON.parse(JSON.stringify(value));
  const logicOptions=value=>[['or','Any (OR)'],['and','All (AND)'],['xor','Exactly one (XOR)']].map(([v,label])=>`<option value="${v}"${v===value?' selected':''}>${label}</option>`).join('');
  const funnel='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 4h18l-7 8v7l-4 2v-9Z"/></svg>';
  function create({state,getOptions,termLabel,onApply}) {
    let draft=null,modal=null,opener=null;
    function normalize(){
      state.filterRules ||= fresh();
      for(const [key] of fields)state.filterRules.groups[key]={...emptyGroup(),...state.filterRules.groups[key]};
    }
    function scopeTerms(rules=state.filterRules){
      const group=rules?.groups.semester||emptyGroup();
      return (state.boot?.semesters||[]).map(item=>item.semester).filter(term=>(!group.yes.length||group.yes.includes(term))&&!group.no.includes(term));
    }
    function scopeLabel(rules=state.filterRules){
      const group=rules?.groups.semester||emptyGroup(),terms=scopeTerms(rules),all=state.boot?.semesters||[];
      if(!group.yes.length&&!group.no.length)return 'All semesters';
      if(terms.length===1)return termLabel(terms[0]);
      if(!terms.length)return 'No semesters';
      for(const [prefix,label] of [['Fa','Fall'],['Sp','Spring']]){
        const season=all.filter(item=>item.semester.startsWith(prefix));
        if(season.length===terms.length&&season.every(item=>terms.includes(item.semester)))return `All ${label.toLowerCase()}s (${terms.length})`;
      }
      return `${terms.length} semesters`;
    }
    function setSemesters(terms){normalize();state.filterRules.groups.semester={...emptyGroup(),yes:[...terms]};}
    const selected=rules=>fields.reduce((total,[key])=>total+(rules.groups[key]?.yes.length||0)+(rules.groups[key]?.no.length||0),0);
    function options(key,rules){
      const source=key==='semester'?(state.boot?.semesters||[]).map(item=>({value:item.semester,label:item.label+(item.status==='current'?' · Current':'')})):getOptions(key,rules);
      const rows=new Map(source.map(item=>[String(item.value),{...item,value:String(item.value)}]));
      for(const value of [...rules.groups[key].yes,...rules.groups[key].no])if(!rows.has(value)){
        const known=state.boot?.filters?.[key]?.find(item=>String(item.value)===value);
        rows.set(value,{value,label:known?.label||value,full_label:known?.full_label||known?.label||value,count:0});
      }
      return [...rows.values()];
    }
    const labelFor=(key,value)=>key==='semester'?termLabel(value):state.boot?.filters?.[key]?.find(item=>String(item.value)===value)?.label||value;
    function renderToolbar(actions=''){
      normalize();const count=selected(state.filterRules);
      const chips=fields.filter(([key])=>key!=='semester'&&(state.filterRules.groups[key].yes.length||state.filterRules.groups[key].no.length)).map(([key,label])=>{
        const group=state.filterRules.groups[key],text=[group.yes.length?`Yes ${group.yes.length}`:'',group.no.length?`No ${group.no.length}`:''].filter(Boolean).join(' · ');
        return `<button type="button" class="record-filter-chip" data-record-open="${key}" title="Edit ${label}">${label}: ${text}</button>`;
      }).join('');
      return `<section class="record-filterbar" aria-label="Filter records"><div class="record-semester"><label id="semester-filter-label">Semester</label><button type="button" id="semester-filter" data-record-open="semester" aria-haspopup="dialog" aria-labelledby="semester-filter-label semester-filter"><span>${escape(scopeLabel())}</span><span aria-hidden="true">⌄</span></button></div><button type="button" class="button record-filter-open" data-record-open="" aria-haspopup="dialog">${funnel}Filters${count?` <span class="record-filter-count">${count}</span>`:''}</button>${count?'<button type="button" class="button link" data-action="clear-filters">Clear filters</button>':''}${chips?`<div class="record-filter-chips" aria-label="Active filters">${chips}</div>`:''}${actions?`<div class="record-filter-actions">${actions}</div>`:''}</section>`;
    }
    function queryValue(){normalize();return selected(state.filterRules)?JSON.stringify(state.filterRules):'';}
    function describe(){
      normalize();const pieces=[scopeLabel()];
      if(selected(state.filterRules))pieces.push('Combine filters: '+state.filterRules.join.toUpperCase());
      for(const [key,label] of fields){
        const group=state.filterRules.groups[key];
        for(const kind of ['yes','no'])if(group[kind].length)pieces.push(`${label} ${kind==='yes'?'Yes':'No'} (${group[kind+'_mode'].toUpperCase()}): ${group[kind].map(value=>labelFor(key,value)).join(', ')}`);
        if(key!=='semester'&&state.filterRules.join==='custom'&&(group.yes.length||group.no.length))pieces.push(label+' combines as '+group.combine.toUpperCase());
      }
      return pieces.join(' · ');
    }
    function choice(key,value){return draft.groups[key].yes.includes(value)?'yes':draft.groups[key].no.includes(value)?'no':'any';}
    function pill(key,item){
      const mode=choice(key,item.value),label=item.full_label||item.label;
      return `<button type="button" class="record-filter-option" data-record-group="${key}" data-record-value="${escape(item.value)}" data-record-state="${mode}" data-record-search="${escape((item.label+' '+label).toLocaleLowerCase())}" aria-pressed="${mode!=='any'}" aria-label="${escape(label)}: ${mode}" title="${escape(label)}"><span class="record-option-state">${mode==='yes'?'Yes':mode==='no'?'No':'Any'}</span><span>${escape(item.label)}</span>${item.count===undefined?'':`<span class="record-option-count">${Number(item.count||0).toLocaleString()}</span>`}</button>`;
    }
    function renderDialog(){
      modal.innerHTML=`<div class="record-filter-dialog-header"><h2 id="record-filter-title">Filters</h2><button type="button" class="quiet record-filter-close" data-record-cancel aria-label="Close filters">×</button></div><div class="record-filter-tools"><input type="search" id="record-filter-search" placeholder="Find a filter or option…" aria-label="Find a filter or option"><label>Combine other filters<select data-record-join><option value="and"${draft.join==='and'?' selected':''}>All (AND)</option><option value="or"${draft.join==='or'?' selected':''}>Any (OR)</option><option value="custom"${draft.join==='custom'?' selected':''}>Custom</option></select></label><button type="button" data-record-clear>Clear choices</button></div><p class="record-filter-help">Click a tag to cycle <strong>Any → Yes → No</strong>. Right-click reverses; Shift-click includes only that tag in its group. Semester choices always limit the other filters. Counts reflect the selected semesters.</p><p class="record-custom-help"${draft.join==='custom'?'':' hidden'}>Custom: every AND group must match, plus at least one active OR group, within the selected semesters.</p><div class="record-filter-scroll">${fields.map(([key,label])=>{
        const group=draft.groups[key],items=options(key,draft);
        const logic=key==='semester'?`<span class="record-semester-help">Match any Yes term; exclude every No term.</span>`:`<label class="record-custom-control"${draft.join==='custom'?'':' hidden'}>Group combines as<select data-record-logic="combine" data-record-key="${key}"><option value="and"${group.combine==='and'?' selected':''}>AND</option><option value="or"${group.combine==='or'?' selected':''}>OR</option></select></label><label>Yes matches<select data-record-logic="yes_mode" data-record-key="${key}">${logicOptions(group.yes_mode)}</select></label><label>No excludes<select data-record-logic="no_mode" data-record-key="${key}">${logicOptions(group.no_mode)}</select></label>`;
        const shortcuts=key==='semester'?`<div class="record-semester-shortcuts">${[['all','All semesters'],['fall','All falls'],['spring','All springs'],['current','Current']].map(([value,text])=>`<button type="button" data-record-semesters="${value}">${text}</button>`).join('')}</div>`:'';
        return `<section class="record-filter-group" data-record-section="${key}" data-record-section-search="${label.toLocaleLowerCase()}"><div class="record-filter-group-header"><h3>${label}</h3><span class="record-group-total" data-record-total="${key}"></span>${logic}</div>${shortcuts}<div class="record-filter-options">${items.map(item=>pill(key,item)).join('')||'<p class="record-no-options">No values recorded for these semesters.</p>'}</div></section>`;
      }).join('')}<p id="record-filter-no-results" hidden>No matching filters or options.</p></div><div class="record-filter-footer"><span data-record-scope>${escape(scopeLabel(draft))}</span><button type="button" data-record-cancel>Cancel</button><button type="button" class="primary" data-record-apply>Apply filters</button></div>`;
      updateCounts();
    }
    function updateCounts(){for(const [key] of fields){const group=draft.groups[key];modal.querySelector(`[data-record-total="${key}"]`).textContent=group.yes.length||group.no.length?`${group.yes.length} Yes · ${group.no.length} No`:'';}}
    function refreshPills(){
      for(const button of modal.querySelectorAll('[data-record-value]')){
        const mode=choice(button.dataset.recordGroup,button.dataset.recordValue);button.dataset.recordState=mode;
        button.setAttribute('aria-pressed',String(mode!=='any'));button.setAttribute('aria-label',button.title+': '+mode);
        button.querySelector('.record-option-state').textContent=mode==='yes'?'Yes':mode==='no'?'No':'Any';
      }
      updateCounts();
    }
    function refreshScopeOptions(){
      for(const [key] of fields)if(key!=='semester')modal.querySelector(`[data-record-section="${key}"] .record-filter-options`).innerHTML=options(key,draft).map(item=>pill(key,item)).join('')||'<p class="record-no-options">No values recorded for these semesters.</p>';
      modal.querySelector('[data-record-scope]').textContent=scopeLabel(draft);search();
    }
    function changeChoice(button,reverse=false,solo=false){
      const key=button.dataset.recordGroup,value=button.dataset.recordValue,group=draft.groups[key];
      let next=solo?'yes':['any','yes','no'][(['any','yes','no'].indexOf(choice(key,value))+(reverse?2:1))%3];
      if(solo){group.yes=[];group.no=[];}
      group.yes=group.yes.filter(item=>item!==value);group.no=group.no.filter(item=>item!==value);
      if(next!=='any')group[next].push(value);refreshPills();if(key==='semester')refreshScopeOptions();
    }
    function search(){
      const query=modal.querySelector('#record-filter-search').value.trim().toLocaleLowerCase();let visible=0;
      for(const section of modal.querySelectorAll('[data-record-section]')){
        let matches=0;const category=section.dataset.recordSectionSearch.includes(query);
        for(const pill of section.querySelectorAll('[data-record-value]')){pill.hidden=!category&&!pill.dataset.recordSearch.includes(query);if(!pill.hidden)matches++;}
        section.hidden=!!query&&!category&&!matches;if(!section.hidden)visible++;
      }
      modal.querySelector('#record-filter-no-results').hidden=!!visible;
    }
    function ensureDialog(){
      if(modal)return;
      modal=document.createElement('dialog');modal.id='record-filter-dialog';modal.setAttribute('aria-labelledby','record-filter-title');document.body.append(modal);
      modal.addEventListener('close',()=>{draft=null;const target=opener?.isConnected?opener:document.querySelector('[data-record-open]');target?.focus({preventScroll:true});});
      modal.addEventListener('click',async event=>{
        if(event.target===modal){const r=modal.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)modal.close();return;}
        const target=event.target.closest('button');if(!target)return;
        if(target.hasAttribute('data-record-cancel')){modal.close();return;}
        if(target.hasAttribute('data-record-semesters')){
          const kind=target.dataset.recordSemesters,terms=state.boot?.semesters||[];
          draft.groups.semester={...emptyGroup(),yes:kind==='all'?[]:terms.filter(item=>kind==='current'?item.status==='current':item.semester.startsWith(kind==='fall'?'Fa':'Sp')).map(item=>item.semester)};
          refreshPills();refreshScopeOptions();return;
        }
        if(target.hasAttribute('data-record-clear')){const join=draft.join;draft=fresh();draft.join=join;for(const [key] of fields)draft.groups[key]=emptyGroup();renderDialog();return;}
        if(target.hasAttribute('data-record-apply')){state.filterRules=clone(draft);modal.close();await onApply();document.querySelector('[data-record-open]')?.focus({preventScroll:true});return;}
        if(target.hasAttribute('data-record-value'))changeChoice(target,false,event.shiftKey);
      });
      modal.addEventListener('contextmenu',event=>{const target=event.target.closest('[data-record-value]');if(target){event.preventDefault();changeChoice(target,true,event.shiftKey);}});
      modal.addEventListener('input',event=>{if(event.target.id==='record-filter-search')search();});
      modal.addEventListener('change',event=>{
        const target=event.target;
        if(target.hasAttribute('data-record-join')){draft.join=target.value;for(const el of modal.querySelectorAll('.record-custom-control,.record-custom-help'))el.hidden=draft.join!=='custom';}
        if(target.dataset.recordLogic)draft.groups[target.dataset.recordKey][target.dataset.recordLogic]=target.value;
      });
    }
    function open(key='',target){
      normalize();ensureDialog();opener=target||document.activeElement;draft=clone(state.filterRules);renderDialog();modal.showModal();
      if(key)modal.querySelector(`[data-record-section="${key}"]`)?.scrollIntoView({block:'start'});
      modal.querySelector('#record-filter-search').focus({preventScroll:true});
    }
    document.addEventListener('click',event=>{const target=event.target.closest('[data-record-open]');if(target){event.preventDefault();open(target.dataset.recordOpen,target);}});
    return {normalize,renderToolbar,queryValue,describe,scopeTerms,scopeLabel,setSemesters,clear:()=>{state.filterRules=fresh();normalize();},cancel:()=>{if(modal?.open)modal.close();},open};
  }
  return {create};
})();
