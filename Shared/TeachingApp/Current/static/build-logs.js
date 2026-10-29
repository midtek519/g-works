/* Compiler reports do not depend on a PDF, preview window, or native bridge. */
(() => {
 'use strict';
 const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function url(id,index=null,download=false){
  if(!/^[a-f0-9]{16}$/.test(id)||index!==null&&(!Number.isInteger(index)||index<0))throw Error('Choose a saved build log.');
  return '/api/builds/'+id+(index===null?'':'/'+index)+'/log'+(download?'?download=1':'');
 }
 function saveLink(id,index=null){return '<a class="save-compile-log" href="'+url(id,index,true)+'" download="Compile-log-'+id+(index===null?'':'-'+(index+1))+'.txt">Save log</a>';}
 function diagnostic(message){
  const text=String(message||''),missing=/File\s+[`'“"]([^`'”"\r\n]+)[`'”"]\s+not found/i.exec(text);
  if(missing){const file=missing[1],packageFile=/\.(?:sty|cls|tfm|fd)$/i.test(file);return {title:(packageFile?'Missing TeX package: ':'Missing file: ')+file,help:packageFile?'Install the required packages in TeX settings, then compile again.':'Check that this file is available to the document, then compile again.',settings:packageFile};}
  if(/(?:no .*TeX installation|shared TeX|compiler.*(?:not found|unavailable)|pdflatex.*unavailable)/i.test(text))return {title:'The TeX compiler is unavailable.',help:'Choose a working installation in TeX settings, then compile again.',settings:true};
  if(/(?:timed out|timeout|exceeded.*(?:minutes|seconds))/i.test(text))return {title:'Compilation took too long.',help:'Open the compiler log to see where it stopped.',settings:false};
  const lines=text.split(/\r?\n/).map(x=>x.trim()).filter(x=>x&&!/Fatal error occurred|no output PDF|^\S+\.(?:cls|sty|tex):\d+:\s*==>/.test(x));
  const first=lines.find(x=>/^!|(?:LaTeX|Package .*?) Error:/.test(x))||lines[0]||'The PDF could not be compiled.';
  return {title:first.replace(/^!\s*/,'').replace(/^LaTeX Error:\s*/,''),help:'Open the compiler log for details.',settings:false};
 }
 function context(batch,job){const name=job?.name||(batch.jobs?.length===1?batch.jobs[0].name:batch.title);return [batch.course?'Math '+batch.course:'',name].filter(Boolean).join(' · ');}
 function view(batch,{index=null,expanded=false,heading=true}={}){
  if(!batch||index===null&&['queued','running'].includes(batch.status))return '';
  const job=index===null?null:batch.jobs[index],state=job?.status||batch.status,failed=state==='failed',ready=state==='ready',running=['queued','running'].includes(state),message=job?.message||batch.message||'',issue=diagnostic(message);
  const title=failed?'Compilation failed':ready?'Compilation succeeded':running?'Compilation in progress':'Build needs review';
  return '<section class="compile-report '+(failed?'compile-report-failed':'')+'" data-build-report="'+batch.id+'" aria-label="Compiler report">'+(heading?'<div class="compile-report-heading"><span class="compile-result-icon" aria-hidden="true">'+(failed?'!':ready?'✓':'…')+'</span><div><h3>'+title+'</h3><p class="compile-report-context">'+esc(context(batch,job))+'</p></div></div>':'<p class="compile-report-context">'+esc(context(batch,job))+'</p>')+(failed?'<div class="compile-diagnostic"><strong>'+esc(issue.title)+'</strong><p>'+esc(issue.help)+'</p></div>':'')+'<div class="compile-report-actions">'+(failed&&issue.settings?'<button type="button" class="primary" data-action="tex-settings">TeX settings</button>':'')+saveLink(batch.id,index)+'</div><details data-compile-log="'+batch.id+'" '+(index===null?'':'data-log-index="'+index+'" ')+(expanded?'open':'')+'><summary>Compiler log</summary><pre data-compile-log-text>Open to read the compiler log.</pre></details></section>';
 }
 function preview(batch,{job:jobIndex=0,page=1}={}){
  const jobs=batch.jobs||[],index=jobs[jobIndex]?jobIndex:0,job=jobs[index],running=['queued','running'].includes(batch.status),completed=jobs.filter(j=>!['queued','running'].includes(j.status)).length;
  const header=running?'<div class="compile-progress"><strong>Compiling</strong><p class="compile-report-context">'+esc(context(batch,job))+'</p><div class="progress"><span style="width:'+Math.max(5,completed/Math.max(1,jobs.length)*100)+'%"></span></div><p class="help">'+completed+' of '+jobs.length+' PDFs complete</p></div>':view(batch);
  const list=jobs.length>1?'<div class="outputs compile-output-list" aria-label="Build files">'+jobs.map((j,i)=>'<div class="output"><span class="output-name">'+esc(j.name)+'<span class="compile-output-state">'+esc(j.status==='ready'?'Ready':j.status==='failed'?'Failed':j.status==='running'?'Compiling':'Queued')+'</span></span><div class="actions">'+(j.status==='ready'?'<button data-action="preview-job" data-index="'+i+'" '+(index===i?'disabled':'')+'>Preview</button>':'')+(j.status!=='queued'?'<button class="quiet" data-action="log" data-index="'+i+'">Compiler log</button>':'')+'</div></div>').join('')+'</div>':'';
  const pdf=job?.status==='ready'?'<div class="preview-controls"><div class="actions"><button data-action="page-prev" aria-label="Previous page" '+(page<=1?'disabled':'')+'>←</button><span class="small">Page '+page+' / '+job.pages+'</span><button data-action="page-next" aria-label="Next page" '+(page>=job.pages?'disabled':'')+'>→</button></div><a target="_blank" rel="noopener" href="/api/builds/'+batch.id+'/'+index+'/pdf">Open PDF ↗</a></div><div class="preview-image"><img alt="'+esc(job.name)+', page '+page+'" src="/api/builds/'+batch.id+'/'+index+'/page/'+page+'"></div>':'';
  const publish=batch.status==='ready'&&!jobs.some(j=>j.preview_only)?'<div class="actions top-gap"><button class="primary" data-action="publish" '+(batch.published?'disabled':'')+'>'+(batch.published?'Saved to course folder':'Publish to course folder')+'</button></div>':'';
  return '<div class="compile-preview" data-build-report="'+batch.id+'">'+header+list+pdf+publish+'</div>';
 }
 async function openSettings(request){const result=await request('/api/tex/settings',{});if(!result.opened)throw Error('Open TeX distribution from the launcher Settings.');return result;}
 async function load(details){
  if(!details.open||details.dataset.logLoaded)return;
  const area=details.querySelector('[data-compile-log-text]');details.dataset.logLoaded='loading';area.textContent='Loading compiler log…';
  try{
   const index=details.dataset.logIndex===undefined?null:Number(details.dataset.logIndex),response=await fetch(url(details.dataset.compileLog,index),{credentials:'same-origin',cache:'no-store',redirect:'error'});
   if(!response.ok)throw Error('The compiler log could not be loaded. Close and reopen this line to retry.');
   const text=await response.text();area.textContent=text.length>200000?'Showing the last part of the log. Save log includes the complete report.\n\n'+text.slice(-200000):text;details.dataset.logLoaded='ready';
  }catch(error){delete details.dataset.logLoaded;area.textContent=error.message;}
 }
 document.addEventListener('toggle',event=>{if(event.target.matches?.('details[data-compile-log]'))void load(event.target);},true);
 function mount(root=document){root.querySelectorAll('details[data-compile-log][open]').forEach(load);}
 window.GWorksBuildLogs={view,preview,diagnostic,openSettings,saveLink,url,mount,load};
})();
