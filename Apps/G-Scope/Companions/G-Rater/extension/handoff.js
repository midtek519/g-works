import { handoffPrompt } from './prompt.js';
const $ = id => document.getElementById(id);
let prompt = '', imageBlob = null, expiry;
let loaded = false;
async function clear(clearClipboard = false) {
  clearTimeout(expiry); imageBlob = null; prompt = ''; loaded = false;
  $('work').removeAttribute('src'); $('rubric').removeAttribute('src'); $('prompt').textContent = ''; $('ready').hidden = true;
  $('status').textContent = 'Handoff cleared. Capture again from Gradescope when ready.';
  if (clearClipboard) try { await navigator.clipboard.writeText(''); } catch { /* May require a fresh user gesture. */ }
}
async function buildImage(crops) {
  const decode = async data => {
    const raw = atob(data.split(',')[1]);
    return createImageBitmap(new Blob([Uint8Array.from(raw,c=>c.charCodeAt(0))],{type:'image/png'}));
  };
  const work = await decode(crops.work), rubric = await decode(crops.rubric);
  try {
    const gap = 28, top = 54;
    const canvas = document.createElement('canvas');
    canvas.width = work.width + rubric.width + gap * 3;
    canvas.height = Math.max(work.height, rubric.height) + top + gap;
    const ctx = canvas.getContext('2d'); ctx.fillStyle = '#ffffff'; ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.fillStyle = '#20323b'; ctx.font = 'bold 20px Segoe UI, sans-serif';
    ctx.fillText('STUDENT WORK',gap,32); ctx.fillText('RUBRIC',work.width+gap*2,32);
    ctx.drawImage(work,gap,top); ctx.drawImage(rubric,work.width+gap*2,top);
    return await new Promise(resolve => canvas.toBlob(resolve,'image/png'));
  } finally { work.close(); rubric.close(); }
}
try {
  const bundle = await chrome.runtime.sendMessage({ app:'g-rater', type:'take-handoff', id:location.hash.slice(1) });
  history.replaceState(null,'',location.pathname);
  if (!bundle?.ok) throw new Error(bundle?.error || 'Handoff unavailable. Capture again.');
  $('work').src = bundle.crops.work; $('rubric').src = bundle.crops.rubric;
  prompt = handoffPrompt(bundle.guidance); $('prompt').textContent = prompt;
  imageBlob = await buildImage(bundle.crops); loaded = true; $('ready').hidden = false;
  $('status').textContent = 'Ready. These images have not been sent to Copilot.';
  expiry = setTimeout(clear,300000);
} catch (e) { $('status').textContent = e.message; }
$('copyImage').onclick = async () => {
  if (!loaded) return;
  try { await navigator.clipboard.write([new ClipboardItem({ 'image/png':imageBlob })]); $('status').textContent = 'Images copied. Paste into your Rutgers Copilot chat.'; }
  catch { $('status').textContent = 'Image copy failed. Keep this page focused and try again.'; }
};
$('copyPrompt').onclick = async () => {
  if (!loaded) return;
  try { await navigator.clipboard.writeText(prompt); $('status').textContent = 'Prompt copied. Paste it below the image in Copilot, then send.'; }
  catch { $('status').textContent = 'Prompt copy failed. Keep this page focused and try again.'; }
};
$('openCopilot').onclick = () => chrome.tabs.create({ url:'https://copilot.cloud.microsoft/?auth=2' });
$('clear').onclick = () => clear(true);
window.addEventListener('pagehide', () => { imageBlob = null; prompt = ''; $('work').removeAttribute('src'); $('rubric').removeAttribute('src'); });
