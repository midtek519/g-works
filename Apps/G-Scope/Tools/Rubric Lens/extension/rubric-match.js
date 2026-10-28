// Runs only after a requested analysis. Inspect rendered rubric text locally,
// only for elements whose bounds fit inside the approved rubric rectangle.
globalThis.__rubricLensFindRubric = function(region, description, points) {
  if (!region || !description || !Number.isFinite(points)) return null;
  const normalize = s => String(s).normalize('NFKC').replace(/\u2212/g,'-').replace(/\s+/g,' ').trim().toLowerCase();
  const withoutLabel = s => normalize(s).replace(/^[+-]?\s*\d+(?:\.\d+)?\s*(?:points?|pts?)\s*/,'').replace(/^[a-z]\s*[:.)-]\s*/,'');
  const target = withoutLabel(description);
  if (!target || target.length < 8) return null;
  const inside = r => r.width>3 && r.height>3 && r.left>=region.x-1 && r.top>=region.y-1 && r.right<=region.x+region.width+1 && r.bottom<=region.y+region.height+1;
  // Gradescope's description opens its editor. Only the small, visible
  // shortcut badge (Q/W/E/etc.) selects the grade. Never fall back to the text.
  const findShortcut = (row, descriptionEl) => {
    const candidates = new Set();
    for (const el of row.querySelectorAll('*')) {
      if (descriptionEl.contains(el) || el.contains(descriptionEl) || el.closest('textarea,input,select,[contenteditable="true"],[hidden],[aria-hidden="true"]')) continue;
      const key = String(el.innerText || '').trim();
      if (!/^[A-Z1-9]$/.test(key)) continue;
      const rect = el.getBoundingClientRect();
      if (!inside(rect) || rect.width>56 || rect.height>48) continue;
      const style = getComputedStyle(el);
      if (style.visibility!=='visible' || Number(style.opacity)===0) continue;
      const button = el.closest('button,[role="button"]');
      const clickable = button && row.contains(button) && String(button.innerText || '').trim()===key ? button : el;
      if (clickable.disabled || clickable.getAttribute('aria-disabled')==='true') continue;
      const meta = `${clickable.getAttribute('title') || ''} ${clickable.getAttribute('aria-label') || ''}`;
      if (/\b(?:edit|delete|remove|search|drag)\b/i.test(meta)) continue;
      const framed = parseFloat(style.borderTopWidth)>0 && style.borderTopStyle!=='none' && parseFloat(style.borderLeftWidth)>0 && style.borderLeftStyle!=='none';
      if (!button && el.tagName!=='KBD' && !/key|shortcut/i.test(el.className || '') && !framed) continue;
      if (!inside(clickable.getBoundingClientRect())) continue;
      candidates.add(clickable);
    }
    // Collapse a span inside the same shortcut badge to a single click target.
    const distinct = [...candidates].filter(el => ![...candidates].some(other => other!==el && other.contains(el) && String(other.innerText || '').trim()===String(el.innerText || '').trim()));
    return distinct.length===1 ? distinct[0] : null;
  };
  // Structured exports keep KaTeX's source TeX instead of duplicated visual
  // and MathML text. Compare that representation only within the approved
  // rubric rectangle; legacy rendered-text matching remains available.
  function rubricText(node) {
    if(node.nodeType===3)return node.nodeValue||'';
    if(node.nodeType!==1)return '';
    if(node.classList?.contains('katex')){
      const source=node.querySelector('annotation[encoding="application/x-tex"]');
      if(source)return '\\('+source.textContent+'\\)';
    }
    if(['SCRIPT','STYLE','INPUT','TEXTAREA','SELECT','BUTTON','SVG','ANNOTATION'].includes(node.tagName)||node.classList?.contains('sr-only')||node.getAttribute('aria-hidden')==='true')return '';
    if(node.tagName==='BR')return '\n';
    const value=[...node.childNodes].map(rubricText).join('');
    return ['P','DIV','LI'].includes(node.tagName)?value+'\n':value;
  }
  const candidates = new Set();
  const xPositions = [region.x+6,region.x+region.width*.25,region.x+region.width*.5,region.x+region.width*.75,region.x+region.width-6];
  for(let y=region.y+4;y<region.y+region.height;y+=12) {
    for(const x of xPositions) for(const el of document.elementsFromPoint(x,y)) {
      if (inside(el.getBoundingClientRect())) candidates.add(el);
    }
  }
  const exact = [...candidates].filter(el => {
    const text=el.innerText;
    return typeof text==='string' && text.length<=4000 && (withoutLabel(text)===target || (el.querySelector('annotation[encoding="application/x-tex"]') && withoutLabel(rubricText(el))===target));
  });
  const distinct = exact.filter(el => !exact.some(other=>other!==el && el.contains(other)));
  if(distinct.length!==1) return null;
  const descriptionEl = distinct[0];
  let row = descriptionEl;
  let match = null;
  while(row && inside(row.getBoundingClientRect())) {
    const text=normalize(row.innerText || '');
    const values=[...text.matchAll(/([+-]?\s*\d+(?:\.\d+)?)\s*(?:points?|pts?)\b/g)].map(m=>Number(m[1].replace(/\s/g,'')));
    if(values.length===1 && Math.abs(values[0]-points)<1e-8) {
      const bounds=row.getBoundingClientRect();
      const selected=row.getAttribute('aria-checked')==='true' || row.getAttribute('aria-selected')==='true' || row.getAttribute('data-selected')==='true' ||
        /(?:^|\s)(?:rubricitem--selected|rubric-item-selected|selected|is-selected|checked|is-checked)(?:\s|$)/i.test(row.className || '') ||
        !!row.querySelector('input[type="radio"]:checked,input[type="checkbox"]:checked,[aria-checked="true"],[aria-selected="true"]');
      const element=findShortcut(row,descriptionEl);
      match={ element, descriptionElement:descriptionEl, row, selected, bounds:{x:bounds.x,y:bounds.y,width:bounds.width,height:bounds.height} };
      if(element) return match;
    }
    row=row.parentElement;
  }
  return match;
};
