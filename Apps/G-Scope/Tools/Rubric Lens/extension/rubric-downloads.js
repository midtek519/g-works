import { validateRubric } from './rubric-export-schema.js';

async function completeDownload(downloads,id,timeoutMs=60000){
  return new Promise((resolve,reject)=>{
    let settled=false;
    const finish=(error,item)=>{if(settled)return;settled=true;clearTimeout(timer);downloads.onChanged.removeListener(changed);error?reject(error):resolve(item);};
    async function inspect(){try{const [item]=await downloads.search({id});if(!item)return finish(Error('Chrome could not find this rubric save. Try again.'));if(item.state==='complete'&&item.exists!==false)return finish(null,item);if(item.state==='interrupted'||item.exists===false)finish(Error('The rubric save was cancelled or interrupted. Try confirming the save again.'));}catch(e){finish(e);}}
    const changed=delta=>{if(delta.id===id&&(delta.state||delta.error||delta.exists))inspect();};
    const timer=setTimeout(()=>finish(Error('The rubric save has not finished. Check Chrome’s downloads panel, then refresh saved rubrics in G-Scope once it completes.')),timeoutMs);
    downloads.onChanged.addListener(changed);inspect();
  });
}
export function rubricFilename(title){
  let stem=String(title).normalize('NFKC').replace(/\.json$/i,'').replace(/\s+/g,'').replace(/[^\p{L}\p{N}._-]/gu,'-').replace(/[-_.]{2,}/g,'-').replace(/^[-_.]+|[-_.]+$/g,'');
  stem=Array.from(stem).slice(0,120).join('').replace(/[. ]+$/g,'')||'Rubric';
  if(/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(stem))stem='Rubric-'+stem;
  return 'G-Rater/Rubrics/'+stem+'.json';
}
export async function saveBrowserRubric(payload,downloads=chrome.downloads){
  if(!downloads?.download||!downloads?.search||!downloads?.onChanged)throw Error('Reload G-Rater in chrome://extensions and approve its Downloads permission, then refresh Gradescope.');
  const value=validateRubric(payload),bytes=new TextEncoder().encode((value.version===2?'rubric-v2\n':'')+value.text);
  const digest=await crypto.subtle.digest('SHA-256',bytes),rid=[...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('');
  const filename=rubricFilename(value.title);
  const id=await downloads.download({url:'data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify(value,null,2)+'\n'),filename,conflictAction:'uniquify',saveAs:false});
  if(!Number.isInteger(id))throw Error('Chrome could not start the rubric save.');
  await completeDownload(downloads,id);
  return {saved:true,rubric:{id:rid,title:value.title},folder:'G-Rater/Rubrics'};
}
