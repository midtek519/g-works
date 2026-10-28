/* This function is injected only after the user chooses a file and clicks Fill form. */
function fillMaxient(report, schema, overwrite) {
  'use strict';
  const url = new URL(location.href);
  if (url.origin !== 'https://cm.maxient.com' || url.pathname !== '/reportingform.php' ||
      !url.searchParams.has('RutgersUniv') || url.searchParams.get('layout_id') !== '38') {
    throw new Error('Open the Rutgers FINAL reporting form (layout 38) first.');
  }
  for (const id of ['reporters_title','person_0','aq[17][answer]']) {
    if (!document.getElementById(id)) throw new Error('The expected form is not present. Sign in and open the final reporting form.');
  }
  const allowed = schema.fields.filter(f => f.visible && f.type !== 'file');
  const norm = value => String(value || '').normalize('NFKC').replace(/[\u2010-\u2015\u2212]/g,'-').replace(/\s+/g,' ').trim();
  const choiceNorm = value => norm(value).toLowerCase().replace(/\s*-\s*/g,' - ');
  const placeholder = option => !option || !norm(option.value) || option.disabled || /^please\s+(?:choose|select)\b/i.test(norm(option.label || option.text || option.textContent || option.value));
  const result = { filled: [], unchanged: [], skipped: [] };
  const actions = [];
  for (const [key, value] of Object.entries(report.fields)) {
    const rules = allowed.filter(f => (f.id || f.name) === key);
    if (!rules.length) throw new Error('The file contains an unsupported field. Re-export it from Casebook.');
    const rule = rules[0];
    if (value === null || value === '') continue;
    if (typeof value !== 'string' && typeof value !== 'boolean') throw new Error('Invalid field value.');
    let element;
    if (rule.type === 'radio') {
      element = Array.from(document.getElementsByName(rule.name)).find(el => el.type === 'radio' && el.getAttribute('value') === value);
    } else element = document.getElementById(rule.id);
    const label = rule.group_legend || rule.label || key;
    if (!element || element.disabled || !element.getClientRects().length) { result.skipped.push(label + ': missing, hidden, or disabled'); continue; }
    if (element.tagName.toLowerCase() !== rule.tag || (rule.tag === 'input' && element.type !== rule.type)) throw new Error('The form structure changed; no fields were filled.');
    if (rule.type === 'radio') {
      const current = Array.from(document.getElementsByName(rule.name)).find(el => el.checked);
      if (current === element) { result.unchanged.push(label); continue; }
      if (current && !overwrite) { result.skipped.push(label + ': different answer already selected'); continue; }
      actions.push({element, property:'checked',value:true,label});
    } else if (rule.type === 'checkbox') {
      if (typeof value !== 'boolean') throw new Error('Invalid checkbox choice.');
      if (element.checked === value) { result.unchanged.push(label); continue; }
      if (element.checked && !overwrite) { result.skipped.push(label + ': different answer already selected'); continue; }
      actions.push({element,property:'checked',value,label});
    } else {
      if (typeof value !== 'string') throw new Error('Invalid text answer.');
      if (rule.max_length && value.length > Number(rule.max_length)) { result.skipped.push(label + ': answer exceeds the field length'); continue; }
      let answer = value;
      let currentPlaceholder = false;
      if (rule.type === 'select') {
        const options = Array.from(element.options);
        const exact = options.filter(option => !option.disabled && option.value === value);
        const matches = exact.length ? exact : options.filter(option => !option.disabled && !placeholder(option) && [option.value,option.label,option.text,option.textContent].some(text => text != null && choiceNorm(text) === choiceNorm(value)));
        if (matches.length !== 1) { result.skipped.push(label + ': option is unavailable or ambiguous'); continue; }
        answer = matches[0].value;
        currentPlaceholder = placeholder(options.find(option => option.value === element.value));
      }
      if (rule.type === 'date' && !/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('Invalid incident date.');
      if (norm(element.value) === norm(answer)) { result.unchanged.push(label); continue; }
      if (element.value && !currentPlaceholder && !overwrite) { result.skipped.push(label + ': different answer already entered'); continue; }
      actions.push({element,property:'value',value:answer,label});
    }
  }
  // All structural checks complete before any controls are changed.
  for (const action of actions) {
    const element = action.element;
    const prototype = element.tagName === 'SELECT' ? HTMLSelectElement.prototype : element.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, action.property).set.call(element, action.value);
    element.dispatchEvent(new Event('input',{bubbles:true}));
    element.dispatchEvent(new Event('change',{bubbles:true}));
    if (element[action.property] === action.value) result.filled.push(action.label);
    else result.skipped.push(action.label + ': the form did not retain the selected answer');
  }
  return result;
}
function attachMaxientPdf(attachment) {
  const url=new URL(location.href);
  if(url.origin!=='https://cm.maxient.com'||url.pathname!=='/reportingform.php'||!url.searchParams.has('RutgersUniv')||url.searchParams.get('layout_id')!=='38')throw new Error('Open the Rutgers final reporting form first.');
  const input=document.getElementById('filer_input');
  if(!input||input.type!=='file'||input.name!=='uploadedFiles[]'||input.disabled||!input.getClientRects().length)throw new Error('The expected attachment control is unavailable. Attach the PDF manually.');
  const bytes=Uint8Array.from(atob(attachment.base64),c=>c.charCodeAt(0));
  if(!attachment.name.endsWith('.pdf')||bytes.length>25*1024*1024||String.fromCharCode(...bytes.slice(0,5))!=='%PDF-')throw new Error('Invalid outcome PDF.');
  const existing=Array.from(input.files||[]);
  if(existing.some(f=>f.name===attachment.name&&f.size===bytes.length))return {attached:true,alreadyPresent:true,name:attachment.name};
  if(existing.length&&!input.multiple)throw new Error('An attachment is already selected. Keep it and attach the outcome manually.');
  const transfer=new DataTransfer();
  for(const file of existing)transfer.items.add(file);
  transfer.items.add(new File([bytes],attachment.name,{type:'application/pdf'}));
  input.files=transfer.files;
  input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
  if(!Array.from(input.files).some(f=>f.name===attachment.name&&f.size===bytes.length))throw new Error('The form did not retain the PDF. Attach it manually.');
  return {attached:true,name:attachment.name};
}
if (typeof module !== 'undefined') module.exports = { fillMaxient,attachMaxientPdf };
