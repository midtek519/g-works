/* Pure outline ordering/grouping. Graded leaves remain separate from summaries. */
window.GScopeOutlineTree=(()=>{
  const clone=value=>structuredClone(value);
  function internal(rows){const keys=new Map(rows.map(n=>[n.number,n.key]));return rows.map(n=>({...clone(n),parentKey:Object.hasOwn(n,'parentKey')?n.parentKey:(keys.get(n.parentNumber)||null)}));}
  function descendant(node,parent,map){let key=node.parentKey,seen=new Set();while(key&&!seen.has(key)){if(key===parent)return true;seen.add(key);key=map.get(key)?.parentKey;}return false;}
  function pack(input){
    let rows=internal(input);const map=new Map(rows.map(n=>[n.key,n]));
    for(const n of rows)if(n.parentKey&&!map.has(n.parentKey))n.parentKey=null;
    let changed=true;while(changed){changed=false;const parents=new Set(rows.map(n=>n.parentKey));rows=rows.filter(n=>{if(!n.graded&&!parents.has(n.key)){changed=true;return false;}return true;});}
    for(const n of rows)if(n.parentKey){const parent=map.get(n.parentKey);if(!n.graded||parent.graded||parent.parentKey)throw Error('Only one level of subquestions is allowed. Ungroup the question first.');}
    const result=[],visiting=new Set();
    function children(parent,prefix){let i=0;for(const n of rows.filter(n=>n.parentKey===parent)){if(visiting.has(n.key))throw Error('An outline group cannot contain itself.');visiting.add(n.key);n.number=prefix?prefix+'.'+(++i):String(++i);n.parentNumber=prefix||null;result.push(n);children(n.key,n.number);visiting.delete(n.key);}}
    children(null,'');if(result.length!==rows.length)throw Error('Check the outline hierarchy for a cycle.');
    for(const n of [...result].reverse())if(!n.graded)n.maxPoints=result.filter(c=>c.parentKey===n.key).reduce((sum,c)=>sum+(Number(c.maxPoints)||0),0);
    return result;
  }
  function sync(rows,questions){
    const byKey=new Map(questions.map(q=>[q.key,q])),next=internal(rows).filter(n=>!n.graded||byKey.has(n.key)),known=new Set(next.filter(n=>n.graded).map(n=>n.key));
    for(const n of next)if(n.graded){const q=byKey.get(n.key);n.title=q.title;n.maxPoints=q.maxPoints;}
    for(const q of questions)if(!known.has(q.key))next.push({key:q.key,title:q.title,maxPoints:q.maxPoints,graded:true,parentKey:null});
    // Older nested outlines open as one group with all graded parts retained.
    const map=new Map(next.map(n=>[n.key,n]));
    for(const n of next){let parent=map.get(n.parentKey),seen=new Set([n.key]);while(parent?.parentKey){if(seen.has(parent.key))throw Error('Check the outline hierarchy for a cycle.');seen.add(parent.key);parent=map.get(parent.parentKey);}if(n.parentKey)n.parentKey=parent?.key||null;}
    return pack(next.filter(n=>n.graded||!n.parentKey));
  }
  function move(input,sourceKey,targetKey,operation){
    const rows=pack(input),map=new Map(rows.map(n=>[n.key,n])),source=map.get(sourceKey),target=map.get(targetKey);
    if(!source||source===target)return rows;
    if(target&&descendant(target,source.key,map))throw Error('A group cannot be moved into one of its own parts.');
    const block=rows.filter(n=>n===source||descendant(n,source.key,map));let rest=rows.filter(n=>!block.includes(n));
    const endOf=node=>{const indices=rest.map((n,i)=>n===node||descendant(n,node.key,new Map(rest.map(n=>[n.key,n])))?i:-1);return Math.max(...indices)+1;};
    if(operation==='outdent'){
      const parent=map.get(source.parentKey);if(!parent)return rows;source.parentKey=parent.parentKey;rest.splice(endOf(parent),0,...block);
    }else if(operation==='indent'){
      if(!target)return rows;
      if(!source.graded)throw Error('Only one level of subquestions is allowed. Move the whole group up or down instead.');
      if(target.parentKey){source.parentKey=target.parentKey;rest.splice(endOf(target),0,...block);}
      else if(target.graded){
        const a=/^(\d+)[a-z]+$/i.exec(target.key),b=/^(\d+)[a-z]+$/i.exec(source.key);let key=a&&b&&a[1]===b[1]&&!map.has(a[1])?a[1]:null;
        if(!key){let i=1;while(map.has('section-'+i))i++;key='section-'+i;}
        const parent={key,title:a&&b&&a[1]===b[1]?a[1]:'Question group',graded:false,maxPoints:0,parentKey:target.parentKey};
        rest.splice(rest.indexOf(target),0,parent);target.parentKey=key;source.parentKey=key;rest.splice(rest.indexOf(target)+1,0,...block);
      }else{source.parentKey=target.key;rest.splice(endOf(target),0,...block);}
    }else if(target){const anchor=!source.graded&&target.parentKey?map.get(target.parentKey):target;source.parentKey=anchor.parentKey;rest.splice(operation==='before'?rest.indexOf(anchor):endOf(anchor),0,...block);}
    else return rows;
    return pack(rest);
  }
  function ungroup(input,key){const rows=pack(input),parent=rows.find(n=>n.key===key);if(!parent||parent.graded)return rows;for(const n of rows)if(n.parentKey===key)n.parentKey=parent.parentKey;return pack(rows.filter(n=>n!==parent));}
  function serialize(rows){return pack(rows).map(({number,key,title,maxPoints,parentNumber,graded})=>({number,key,title,maxPoints,parentNumber,graded}));}
  return Object.freeze({sync,move,ungroup,serialize});
})();
