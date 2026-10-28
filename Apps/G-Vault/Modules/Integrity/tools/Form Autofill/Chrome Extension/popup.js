'use strict';
let report = null;
const $ = id => document.getElementById(id);
const status = text => { $('status').textContent = text; };
const update = () => { $('fill').disabled = !report || !$('confirm').checked; };
$('confirm').addEventListener('change', update);
$('attach').addEventListener('change',async()=>{
 if(!$('attach').checked)return;
 const granted=await chrome.permissions.request({origins:['http://127.0.0.1/*']});
 if(!granted){$('attach').checked=false;status('Local PDF access was not granted. You can attach the PDF manually.');}
});
async function linkedPdf(data){
 const attachment=data.attachments?.find(a=>a.role==='outcome-letter');
 if(!attachment?.local_url||!['signed','historical'].includes(data.letter_status))throw new Error('Export a fresh JSON linked to your signed final first.');
 const url=new URL(attachment.local_url);
 const prefix='/api/report-attachment/'+data.case_id+'/'+data.communication_id+'/';
 if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||!url.port||url.username||url.password||url.search||url.hash||!url.pathname.startsWith(prefix)||!/^Report-[a-f0-9]+\/[A-Za-z0-9_-]{40,}$/.test(url.pathname.slice(prefix.length)))throw new Error('Invalid local PDF link. Re-export from Casebook.');
 const response=await fetch(url.href,{credentials:'omit',cache:'no-store',redirect:'error'});
 if(!response.ok)throw new Error('The linked PDF is unavailable or changed. Export a fresh signed-letter JSON with Casebook open.');
 if(Number(response.headers.get('Content-Length'))>25*1024*1024)throw new Error('This PDF exceeds the helper’s 25 MB limit. Attach it manually.');
 const bytes=new Uint8Array(await response.arrayBuffer());
 if(bytes.length>25*1024*1024||String.fromCharCode(...bytes.slice(0,5))!=='%PDF-')throw new Error('The linked file is not a supported PDF.');
 const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
 if(digest!==attachment.sha256)throw new Error('PDF verification failed. Export a fresh JSON.');
 let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
 return {base64:btoa(binary),name:attachment.filename||data.case_id+'-outcome.pdf'};
}

$('file').addEventListener('change', async () => {
  report = null; $('attach').checked=false; $('attach').disabled=true; $('summary').hidden = true; $('confirm').checked = false; update();
  try {
    const file = $('file').files[0]; if (!file) return;
    if (file.size > 5 * 1024 * 1024) throw new Error('Choose a Casebook reporting JSON smaller than 5 MB.');
    const data = JSON.parse(await file.text());
    if (data.schema_version !== 1 || data.document_type !== 'rutgers-final-integrity-report' || !data.fields || typeof data.fields !== 'object' || Array.isArray(data.fields) || !data.student?.name || !data.case_id || !Array.isArray(data.missing_fields)) throw new Error('This is not a Casebook reporting export.');
    const schema = await (await fetch('form-schema.json')).json();
    const keys = new Set(schema.fields.filter(f=>f.visible&&f.type!=='file').map(f=>f.id||f.name));
    if (Object.keys(data.fields).some(key=>!keys.has(key))) throw new Error('Unsupported fields in this export.');
    report = data;
    $('student').textContent = data.student.name;
    $('case').textContent = data.case_id + ' / ' + data.communication_id;
    $('letter').textContent = data.letter_status === 'signed' ? 'Export linked to a signed PDF.' : data.letter_status === 'historical' ? 'Export linked to a preserved historical letter.' : 'Draft export: use a signed-letter export for the final submission.';
    $('warnings').replaceChildren();
    for (const message of [...data.missing_fields.map(x=>'Missing: '+x), ...(data.warnings || []), 'Review all attachments before submitting. Add any other supporting documents manually.']) {
      const item = document.createElement('li'); item.textContent = message; $('warnings').append(item);
    }
    const canAttach=['signed','historical'].includes(data.letter_status)&&data.attachments?.some(a=>a.role==='outcome-letter'&&a.local_url);
    $('attach').disabled=!canAttach;
    $('attachment-help').textContent=canAttach?'Keep Casebook open. Checking this allows the helper to read only the PDF linked to this export and attach it when you click Fill form.':'Create the signed final, then export a fresh JSON to enable automatic PDF attachment.';
    $('summary').hidden = false; status('Review the student and confirm before filling.');
  } catch(error) { status(error.message); }
});
$('fill').addEventListener('click',async()=>{
  if (!report || !$('confirm').checked) return;
  $('fill').disabled = true;
  try {
    const [tab] = await chrome.tabs.query({active:true,currentWindow:true});
    if (!tab?.id) throw new Error('Select the reporting-form tab.');
    const schema = await (await fetch('form-schema.json')).json();
    const pdf=$('attach').checked?await linkedPdf(report):null;
    const [result] = await chrome.scripting.executeScript({target:{tabId:tab.id},func:fillMaxient,args:[report,schema,$('overwrite').checked]});
    if (!result?.result) throw new Error('The form could not be filled.');
    const value=result.result;
    let attachmentMessage='Attach the outcome PDF manually.';
    if(pdf){
      const [attached]=await chrome.scripting.executeScript({target:{tabId:tab.id},func:attachMaxientPdf,args:[pdf]});
      if(!attached?.result?.attached)throw new Error('Fields were filled, but the attachment was not confirmed. Attach the PDF manually.');
      attachmentMessage='PDF attached: '+attached.result.name+'. Check that it appears in Supporting Documentation.';
    }
    status('Filled '+value.filled.length+' fields; '+value.unchanged.length+' already matched.\n'+(value.skipped.length?'Needs attention:\n'+value.skipped.join('\n')+'\n':'')+attachmentMessage+'\nReview all answers and attachments, then submit yourself.');
  } catch(error) { status(error.message); }
  finally { update(); }
});
