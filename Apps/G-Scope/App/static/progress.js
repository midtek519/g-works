/* Shared measured/indeterminate task progress for scan intake and matching. */
window.GScopeProgress=(()=>{
 'use strict';
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function view(value,{id=''}={}){
  if(!value)return '';
  const p=typeof value==='string'?{message:value}:value;
  const total=Number(p.total),completed=Number(p.completed),measured=Number.isFinite(total)&&total>0&&Number.isFinite(completed);
  const done=measured?Math.max(0,Math.min(completed,total)):0;
  const count=measured?done+' / '+total:'',message=p.message||'Working…';
  return '<div '+(id?'id="'+esc(id)+'" ':'')+'class="gs-task-progress '+(p.state==='done'?'complete':'')+'" role="status" aria-live="polite"><div class="gs-task-progress-label"><span>'+esc(message)+'</span>'+(count&&p.state!=='done'?'<small>'+count+'</small>':'')+'</div>'+(p.state==='done'?'':'<progress aria-label="'+esc(message)+'" '+(measured?'max="'+total+'" value="'+done+'"':'')+'>'+esc(count||message)+'</progress>')+'</div>';
 }
 return {view};
})();
