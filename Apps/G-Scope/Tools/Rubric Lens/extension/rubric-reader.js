/* Rubric-definition DOM only. Reads selection-radio state on demand; only settings gears may be clicked. */
(() => {
  if(globalThis.RubricLensExport)return;
  const all=(root,selector)=>[...root.querySelectorAll(selector)];
  const one=(root,selector)=>root.querySelector(selector);
  const has=(node,name)=>node?.classList?.contains(name);
  const settingSources=new WeakMap();
  function text(node){
    if(!node)return '';
    if(node.nodeType===3)return node.nodeValue||'';
    if(node.nodeType!==1)return '';
    if(has(node,'katex')){
      const latex=one(node,'annotation[encoding="application/x-tex"]');
      return latex?'\\('+latex.textContent+'\\)':walk(node);
    }
    if(['SCRIPT','STYLE','INPUT','TEXTAREA','SELECT','BUTTON','SVG','ANNOTATION'].includes(node.tagName)||has(node,'sr-only')||node.getAttribute('aria-hidden')==='true')return '';
    if(node.tagName==='BR')return '\n';
    const result=walk(node);
    return ['P','DIV','LI'].includes(node.tagName)?result+'\n':result;
  }
  const walk=node=>[...node.childNodes].map(text).join('');
  const clean=node=>text(node).replace(/\u00a0/g,' ').replace(/[ \t]+/g,' ').replace(/ *\n */g,'\n').replace(/\n{3,}/g,'\n\n').trim();
  const scalar=node=>(node?.textContent||'').replace(/\u00a0/g,' ').replace(/\s+/g,' ').trim();
  const number=node=>{const m=/^([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:points?|pts?)?$/i.exec(scalar(node));return m&&Number.isFinite(Number(m[1]))?Number(m[1]):null;};
  const description=root=>clean(one(root,'.markdownText')||one(root,'.rubricField-description'));
  const item=(root,points,index)=>{const value=description(root);return {label:/^([^\s:]{1,24}):/.exec(value)?.[1]||String(index+1),description:value,points};};
  function selection(root){
    const controls=one(root,'.rubricItemGroup--controls');
    if(!controls)return 'unknown';
    const modes=all(controls,'button').flatMap(b=>[scalar(b),b.getAttribute('aria-label')||'']).map(v=>/^Select\s+(one|many)$/i.exec(v)?.[1]?.toLowerCase()).filter(Boolean);
    const unique=[...new Set(modes)];return unique.length===1?(unique[0]==='many'?'all':'one'):'unknown';
  }
  function groups(question,problems,key){
    const matrices=all(question,'.gradingPopout--matrix');
    if(matrices.length){
      if(all(question,'.rubricItem').length||all(question,'.rubricItemGroup').length)problems.push('Question '+key+': mixed grid/list groups need manual review; they cannot be silently combined.');
      return matrices.flatMap(table=>{
        const headers=all(one(table,'thead')||table,'.gradingPopout--columnHeader').filter(h=>!has(h,'gradingPopout--columnHeader-rowHeader'));
        const points=headers.map(h=>number(one(h,'[name="rubricPointsButton"]')));
        return all(one(table,'tbody')||table,'.gradingPopout--row-tableContent').map(row=>{
          const cells=all(row,'.gradingPopout--cell');
          if(cells.length!==points.length)problems.push('Question '+key+': grid columns and loaded cells do not match.');
          const header=one(row,'.gradingPopout--rowHeader')||row;
          const group={description:description(header),selectionMode:radioSelection(header),items:cells.map((cell,i)=>item(cell,points[i]??null,i))};
          settingSources.set(group,{root:header,button:one(header,'button.submissionGraderSidebar--rubricSettings')});
          return group;
        });
      });
    }
    const bundles=all(question,'.rubricItemGroup');
    const result=bundles.map(group=>{
      const bundle=group.closest('.rubricEntryGroupBundle');
      if(bundle&&all(bundle,'.rubricItemGroup').length!==1)problems.push('Question '+key+': nested group structure needs manual review.');
      return {description:description(one(group,'.rubricItemGroup--row')||group),selectionMode:selection(group),items:all(bundle||group,'.rubricItem').map((el,i)=>item(el,number(one(el,'[name="rubricPointsButton"]')),i))};
    });
    const loose=all(question,'.rubricItem').filter(el=>!el.closest('.rubricItemGroup')&&!el.closest('.rubricEntryGroupBundle'));
    if(loose.length)result.push({description:'Ungrouped rubric items',selectionMode:'unknown',items:loose.map((el,i)=>item(el,number(one(el,'[name="rubricPointsButton"]')),i))});
    return result;
  }
  function read(section){
    const nodes=all(section,'.assignmentRubricQuestion');
    if(!nodes.length)throw Error('This layout has no recognized rubric questions. Use Read selected text for a text-only export.');
    const problems=[];
    const outline=nodes.map((el,index)=>{
      const heading=one(el,'.assignmentRubricQuestion--heading')||el;
      const n=scalar(one(heading,'.assignmentRubricQuestion--number')).replace(/^Q\s*/i,'');
      const title=scalar(one(heading,'.assignmentRubricQuestion--title'));
      const candidate=title.replace(/^Q\s*/i,'').replace(/\(([a-z])\)$/i,'$1');
      const key=/^\d+(?:[.:-]\d+)*(?:[a-z])?$/i.test(candidate)?candidate:n;
      if(!key)problems.push('A question label is missing near outline row '+(index+1)+'.');
      return {number:n,key,title:title||key,maxPoints:number(one(heading,'.assignmentRubricQuestion--points')),parentNumber:null,graded:has(el,'assignmentRubricQuestion-leaf')};
    });
    const numbers=new Set(outline.map(o=>o.number));
    if(numbers.size!==outline.length||new Set(outline.map(o=>o.key)).size!==outline.length)problems.push('Outline numbers or question labels are repeated. Check the question hierarchy.');
    for(const node of outline){let parent=node.number;while(parent.includes('.')){parent=parent.slice(0,parent.lastIndexOf('.'));if(numbers.has(parent)){node.parentNumber=parent;break;}}}
    const keys=new Set();
    const questions=nodes.flatMap((el,i)=>{
      const info=outline[i];if(!info.graded)return [];
      if(keys.has(info.key))problems.push('Repeated graded question label: '+info.key+'.');keys.add(info.key);
      return [{key:info.key,title:info.title,maxPoints:info.maxPoints,groups:groups(el,problems,info.key)}];
    });
    return {outline,questions,problems};
  }
  // Only the two selection-style enums are read. Live checked state takes
  // precedence over the initial HTML attribute, which React may leave stale.
  function radioSelection(root){
    const options=all(root,'.rubricItemGroupSettingsPopover input[type="radio"]').filter(el=>['select_one','select_many'].includes(el.getAttribute('value')));
    const names=new Set(options.map(el=>el.getAttribute('name')));
    if(options.length!==2||names.size!==1||!names.values().next().value)return 'unknown';
    if(new Set(options.map(el=>el.getAttribute('value'))).size!==2)return 'unknown';
    const checked=options.filter(el=>el.checked===true);
    return checked.length===1?(checked[0].getAttribute('value')==='select_many'?'all':'one'):'unknown';
  }
  const visibleMenus=doc=>all(doc,'.rubricItemGroupSettingsPopover').filter(el=>el.closest('.jBox-wrapper')?.getAttribute('aria-hidden')==='false');
  async function waitFor(probe,guard){
    for(let i=0;i<26;i++){guard();const value=probe();if(value)return value;if(i<25)await new Promise(resolve=>setTimeout(resolve,20));}
    return null;
  }
  const structure=draft=>JSON.stringify({outline:draft.outline,questions:draft.questions.map(q=>({...q,groups:q.groups.map(g=>({...g,selectionMode:null}))}))});
  async function readWithSettings(section,guard=()=>{},progress=()=>{}){
    guard();const draft=read(section),initial=structure(draft),doc=section.ownerDocument;
    if(!doc)return draft;
    const sources=draft.questions.flatMap(q=>q.groups.map(g=>({group:g,...settingSources.get(g)}))).filter(s=>s.button&&s.group.items.length);
    if(sources.length>200)throw Error('Too many rubric groups to read settings safely. Export a smaller assignment.');
    const initiallyOpen=sources.filter(s=>s.button.getAttribute('aria-expanded')==='true');
    // An unassociated open menu is never assigned by position or guessed labels.
    if(visibleMenus(doc).length&&initiallyOpen.length!==1)return draft;
    const restore=initiallyOpen.length===1?initiallyOpen[0].button:null;
    let opened=null;
    async function closeOpened(){
      if(!opened)return;
      guard();const button=opened;opened=null;
      if(button.getAttribute('aria-expanded')==='true'){
        button.click();await waitFor(()=>button.getAttribute('aria-expanded')!=='true'&&!visibleMenus(doc).length,guard);
      }
    }
    try{
      for(let i=0;i<sources.length;i++){
        guard();const source=sources[i];progress(i+1,sources.length);
        if(source.group.selectionMode!=='unknown')continue;
        if(!section.contains(source.button))throw Error('The rubric changed. Read it again before exporting.');
        if(source.button.getAttribute('aria-expanded')!=='true'){
          // Close an initially open settings menu before inspecting another group.
          const active=sources.filter(s=>s.button.getAttribute('aria-expanded')==='true');
          if(active.length>1)continue;
          if(active.length){active[0].button.click();if(!await waitFor(()=>!visibleMenus(doc).length,guard))continue;}
          if(visibleMenus(doc).length)continue;
          guard();source.button.click();opened=source.button;
        }
        const menu=await waitFor(()=>{
          if(source.button.getAttribute('aria-expanded')!=='true')return null;
          const menus=visibleMenus(doc);return menus.length===1?menus[0].parentElement:null;
        },guard);
        guard();if(menu)source.group.selectionMode=radioSelection(menu);
        await closeOpened();
      }
      guard();if(structure(read(section))!==initial)throw Error('The rubric changed while its settings were read. Read the page again.');
      return draft;
    }finally{
      // Never operate stale controls after navigation or cancellation.
      try{guard();await closeOpened();if(restore&&section.contains(restore)&&restore.getAttribute('aria-expanded')!=='true'&&!visibleMenus(doc).length)restore.click();}catch{}
    }
  }
  function suggestedTitle(doc){
    const courseLabel=clean(one(doc,'.sidebar--subtitle-withBackToCourse a'));
    const assignmentLabel=clean(one(doc,'.sidebar--title'));
    if(!courseLabel||!assignmentLabel)return '';
    const full=/\b(Spring|Summer|Fall|Winter)\s+(20\d{2})\b/i.exec(assignmentLabel+' '+courseLabel);
    const short=/\b(FA|SP|SU|WI)(\d{2})\b/i.exec(courseLabel);
    const semester=full?full[1][0].toUpperCase()+full[1].slice(1).toLowerCase()+' '+full[2]:short?({FA:'Fall',SP:'Spring',SU:'Summer',WI:'Winter'}[short[1].toUpperCase()]+' 20'+short[2]):'';
    const course=courseLabel.replace(/\b(?:FA|SP|SU|WI)\d{2}\b.*$/i,'').replace(/\b(?:Spring|Summer|Fall|Winter)\s+20\d{2}\b.*$/i,'').replace(/\bSections?\b.*$/i,'').replace(/[\s·:–—-]+$/,'').trim();
    const assignment=assignmentLabel.replace(/\b(?:Spring|Summer|Fall|Winter)\s+20\d{2}\b/ig,'').replace(/\(?\bVersion\s+[A-Z0-9]+\)?/ig,'').replace(/\s+/g,' ').replace(/^[\s·:–—-]+|[\s·:–—-]+$/g,'').trim();
    return course&&assignment&&semester?[course,assignment,semester].join(' - ').slice(0,160):'';
  }
  function issues(draft){
    const result=[...draft.problems];
    if(!draft.questions.length)result.push('No graded questions were found.');
    if(draft.questions.length>100||draft.outline.length>200||JSON.stringify({outline:draft.outline,questions:draft.questions},null,2).length>200000)result.push('This rubric is too large for one export. Export a smaller assignment.');
    for(const q of draft.questions){
      if(!Number.isFinite(q.maxPoints)||q.maxPoints<0)result.push('Question '+q.key+': maximum points could not be read.');
      if(!q.groups.length)result.push('Question '+q.key+': no loaded rubric items. Expand its groups or use Grid View and read again.');
      q.groups.forEach((g,i)=>{
        if(!['one','all'].includes(g.selectionMode))result.push('Question '+q.key+', group '+(i+1)+': confirm Select one or Select many below.');
        if(!g.items.length)result.push('Question '+q.key+', group '+(i+1)+': rubric is collapsed, empty or not loaded. Expand it or use Grid View and read again.');
        if(g.items.some(item=>!item.description||!Number.isFinite(item.points)))result.push('Question '+q.key+', group '+(i+1)+': a description or point value is missing.');
        if(g.items.length>50||g.description.length>4000||g.items.some(item=>item.description.length>4000||item.label.length>160))result.push('Question '+q.key+', group '+(i+1)+': rubric content exceeds the supported field limits.');
      });
    }
    return result;
  }
  function exportData(draft,title){
    const errors=issues(draft);if(errors.length)throw Error(errors[0]);
    const data={outline:draft.outline,questions:draft.questions};
    return {format:'rubric-lens-rubric-export',version:2,title:title.trim(),text:JSON.stringify(data,null,2),...data};
  }
  globalThis.RubricLensExport=Object.freeze({read,readWithSettings,suggestedTitle,issues,exportData});
})();
