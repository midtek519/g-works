/* Explicit online grading review. No roster/identity fields enter transport. */
window.GScopeOnline=(()=>{
 'use strict';
 const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 async function open(C,v,q){
  if(document.querySelector('.online-grading-review'))return;
  const dialog=document.createElement('dialog');dialog.className='online-grading-review';
  const style=document.createElement('style');style.textContent='.online-grading-review{width:min(1250px,96vw);max-height:94vh;padding:20px;border:1px solid #cbb986;border-radius:12px;background:#faf8f2;color:#54401b}.online-grading-review::backdrop{background:#17253877}.og-columns{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(280px,1fr);gap:18px}.og-image{width:100%;height:auto;border:1px solid #cfbf99;touch-action:none;cursor:crosshair}.og-context{width:100%;height:340px;resize:vertical;font:12px Consolas,monospace}.og-list{display:flex;gap:5px;flex-wrap:wrap;margin:12px 0}.og-list button{padding:3px 8px}.og-list .reviewed{border-color:#348457;background:#edf6ef}.og-list .current{outline:2px solid #a27110}.og-actions{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-top:14px}.og-columns label{margin-bottom:8px}.og-message{min-height:22px;font-size:12px}@media(max-width:850px){.og-columns{grid-template-columns:1fr}}';dialog.append(style);
  const body=document.createElement('div');dialog.append(body);document.body.append(dialog);
  let packet=null,index=0,provider='chatgpt',busy=false,reviewed=new Set(),redactions={},image=null,start=null,dirtyBoxes=false;
  const current=()=>packet?.answers[index];
  const payload=()=>({previewId:packet.id,hash:packet.hash,approved:true,reviewedAnswers:[...reviewed],context:packet.context});
  function message(text){const p=body.querySelector('.og-message');if(p)p.textContent=text;}
  function render(){
   body.innerHTML='<div class="spread"><h2>Review online grading · Question '+escape(q.key)+' · Version '+escape(v.label)+'</h2><button data-og="close">Close</button></div><p class="help">Only the displayed answer crops and grading context are shared. Names, NetIDs, rosters, full PDFs and local file details stay out of the request. Check for identifying handwriting and draw over it to redact.</p><label>Service<select data-og-provider><option value="chatgpt" '+(provider==='chatgpt'?'selected':'')+'>Online ChatGPT</option></select></label>'+(packet?'<p class="help">'+escape(packet.model)+' · Each request contains one reviewed crop. Older grading results remain in history.'+'</p><div class="og-columns"><section><div class="spread"><strong>'+escape(current()?.label||'No answers')+'</strong><span>'+reviewed.size+' / '+packet.answers.length+' reviewed</span></div><canvas class="og-image" aria-label="Answer crop. Drag to cover identifying text."></canvas><div class="og-actions"><button data-og="previous" '+(index?'':'disabled')+'>← Previous</button><button data-og="review" '+(busy||dirtyBoxes?'disabled':'')+'>Reviewed & next →</button><button data-og="clear">Clear redactions</button><button data-og="apply" '+(dirtyBoxes&&!busy?'':'disabled')+'>Apply redactions</button></div><div class="og-list">'+packet.answers.map((a,i)=>'<button data-og-index="'+i+'" class="'+(i===index?'current ':'')+(reviewed.has(a.bookletId)?'reviewed':'')+'">'+(i+1)+(reviewed.has(a.bookletId)?' ✓':'')+'</button>').join('')+'</div></section><section><h3>Exact grading context</h3><textarea class="og-context" readonly>'+escape(packet.system+'\n\n'+packet.context)+'</textarea><p class="help">This uses the saved rubric, reference and approved guidance. Change those in the assignment if the context needs correcting. Cropping and automated text checks do not certify de-identification; review every image.</p></section></div><div class="og-actions"><button class="primary" data-og="send" '+(!busy&&!dirtyBoxes&&reviewed.size===packet.answers.length&&packet.answers.length?'':'disabled')+'>'+(busy?'Preparing…':'Approve & grade with ChatGPT')+'</button>'+'</div>':'<p>Preparing the exact outbound preview…</p>')+'<p class="og-message" role="status"></p>';
   const canvas=body.querySelector('canvas');if(!canvas||!current())return;
   image=new Image();image.onload=()=>{canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;draw();};image.src='data:image/png;base64,'+current().png;
   const point=e=>{const r=canvas.getBoundingClientRect();return [Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))];};
   function draw(){const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);ctx.fillStyle='#000';for(const r of redactions[current().bookletId]||[])ctx.fillRect(r[0]*canvas.width,r[1]*canvas.height,(r[2]-r[0])*canvas.width,(r[3]-r[1])*canvas.height);}
   canvas.onpointerdown=e=>{start=point(e);canvas.setPointerCapture(e.pointerId);};
   canvas.onpointerup=e=>{if(!start)return;const end=point(e),r=[Math.min(start[0],end[0]),Math.min(start[1],end[1]),Math.max(start[0],end[0]),Math.max(start[1],end[1])];start=null;if(r[2]-r[0]<.003||r[3]-r[1]<.003)return;(redactions[current().bookletId]??=[]).push(r);reviewed.delete(current().bookletId);dirtyBoxes=true;draw();body.querySelector('[data-og=apply]').disabled=false;body.querySelector('[data-og=send]').disabled=true;body.querySelector('[data-og=review]').disabled=true;};
  }
  async function prepare(){busy=true;const previous=packet;render();try{packet=await C.api('/api/versions/'+v.id+'/online-preview',{questionId:q.id,provider,redactions});reviewed=new Set(packet.answers.filter(a=>reviewed.has(a.bookletId)&&previous?.answers.some(old=>old.bookletId===a.bookletId&&old.sha256===a.sha256)).map(a=>a.bookletId));index=Math.min(index,packet.answers.length-1);dirtyBoxes=false;}catch(e){message(e.message);throw e;}finally{busy=false;render();}}
  body.addEventListener('change',async e=>{if(!e.target.matches('[data-og-provider]')||busy)return;provider=e.target.value;packet=null;reviewed.clear();redactions={};index=0;try{await prepare();}catch(err){message(err.message);}});
  body.addEventListener('click',async e=>{
   const b=e.target.closest('button');if(!b)return;
   try{
    if(b.dataset.og==='close'){if(!busy){dialog.close();dialog.remove();}return;}
    if(busy||!packet)return;
    if(b.dataset.ogIndex!==undefined){if(dirtyBoxes)throw Error('Apply redactions before switching answers.');index=Number(b.dataset.ogIndex);render();return;}
    const action=b.dataset.og;
    if(action==='review'){reviewed.add(current().bookletId);index=Math.min(packet.answers.length-1,index+1);render();}
    if(action==='previous'&&index){if(dirtyBoxes)throw Error('Apply redactions first.');index--;render();}
    if(action==='clear'){redactions[current().bookletId]=[];reviewed.delete(current().bookletId);dirtyBoxes=true;render();}
    if(action==='apply')await prepare();
    if(action==='send'){
     if(reviewed.size!==packet.answers.length||dirtyBoxes)return;
     busy=true;render();
      const result=await C.api('/api/versions/'+v.id+'/online-start',payload());
      C.S.run=await C.api('/api/runs/'+result.id);C.S.version=await C.api('/api/versions/'+v.id);window.GScopeGrading.invalidate(v.id);window.GScopeGradeWorkspace.invalidate(v.id);dialog.close();dialog.remove();C.render();C.message('Online grading started with your reviewed crops.');

    }
   }catch(err){busy=false;render();message(err.message);}
  });
  dialog.addEventListener('cancel',e=>{if(busy)e.preventDefault();else dialog.remove();});dialog.showModal();render();try{await prepare();}catch(e){message(e.message);}
 }
 return {open};
})();
