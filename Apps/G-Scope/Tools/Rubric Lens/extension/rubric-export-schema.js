// Bounded rubric-only schema. Old text exports remain valid.
const fail=()=>{throw Error('Choose a complete G-Rater rubric export with valid questions, groups and outline.');};
const exact=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join(',')===keys.slice().sort().join(',');
const string=(v,max,empty=false)=>typeof v==='string'&&v.length<=max&&(empty||!!v.trim());
const num=v=>typeof v==='number'&&Number.isFinite(v)&&Math.abs(v)<=1000000;
const key=v=>string(v,40)&&/^[a-z0-9][a-z0-9._-]*$/i.test(v);
const path=v=>string(v,40)&&/^\d+(?:\.\d+)*$/.test(v);
const same=(a,b)=>{
 if(a===b)return true;if(typeof a!==typeof b||!a||!b)return false;
 if(Array.isArray(a))return Array.isArray(b)&&a.length===b.length&&a.every((v,i)=>same(v,b[i]));
 if(typeof a==='object'){const keys=Object.keys(a);return keys.length===Object.keys(b).length&&keys.every(k=>Object.hasOwn(b,k)&&same(a[k],b[k]));}return false;
};
export function validateRubric(value){
 const base=['format','version','title','text'];
 if(!exact(value,value?.version===2?[...base,'outline','questions']:base)||value.format!=='rubric-lens-rubric-export'||![1,2].includes(value.version))fail();
 if(!string(value.title,160,true)||!string(value.text,200000))fail();
 if(value.version===1)return {...value,title:value.title.trim()||'Untitled rubric',text:value.text.trim()};
 const {outline,questions}=value;
 if(!Array.isArray(outline)||!outline.length||outline.length>200||!Array.isArray(questions)||!questions.length||questions.length>100)fail();
 const numbers=new Map(),graded=new Map(),keys=new Set();
 for(const row of outline){
  if(!exact(row,['number','key','title','maxPoints','parentNumber','graded'])||!path(row.number)||!key(row.key)||!string(row.title,240)||!num(row.maxPoints)||row.maxPoints<0||typeof row.graded!=='boolean'||numbers.has(row.number)||keys.has(row.key))fail();
  if(row.parentNumber!==null&&(!path(row.parentNumber)||!numbers.has(row.parentNumber)||!row.number.startsWith(row.parentNumber+'.')||numbers.get(row.parentNumber).graded))fail();
  numbers.set(row.number,row);keys.add(row.key);if(row.graded)graded.set(row.key,row);
 }
 const seen=new Set();
 for(const q of questions){
  if(!exact(q,['key','title','maxPoints','groups'])||!key(q.key)||!string(q.title,240)||!num(q.maxPoints)||q.maxPoints<0||seen.has(q.key)||!graded.has(q.key)||graded.get(q.key).maxPoints!==q.maxPoints||graded.get(q.key).title!==q.title)fail();
  seen.add(q.key);if(!Array.isArray(q.groups)||!q.groups.length||q.groups.length>50)fail();
  for(const g of q.groups){
   if(!exact(g,['description','selectionMode','items'])||!string(g.description,4000,true)||!['one','all'].includes(g.selectionMode)||!Array.isArray(g.items)||!g.items.length||g.items.length>50)fail();
   for(const i of g.items)if(!exact(i,['label','description','points'])||!string(i.label,160)||!string(i.description,4000)||!num(i.points))fail();
  }
 }
 if(seen.size!==graded.size)fail();
 let parsed;try{parsed=JSON.parse(value.text);}catch{fail();}
 if(!same(parsed,{outline,questions}))fail();
 return {...value,title:value.title.trim()||'Untitled rubric',text:value.text.trim()};
}
