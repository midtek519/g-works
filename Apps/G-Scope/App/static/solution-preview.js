/* Offline, read-only TeX preview. Never compiles TeX or loads remote resources. */
window.GScopeSolutionPreview=(()=>{
  const timers=new Map(),escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function render(value){
    const source=String(value||'').slice(0,8000).replace(/\\(?:begin|end)\s*\{solution\}/g,'');let errors=0;
    const math=(tex,display=false)=>{
      if(!window.katex)return '<code>'+escape(tex)+'</code>';
      try{return window.katex.renderToString(tex,{displayMode:display,throwOnError:true,trust:false,strict:'ignore',maxExpand:500,maxSize:10,macros:{'\\R':'\\mathbb{R}','\\N':'\\mathbb{N}','\\Z':'\\mathbb{Z}','\\ds':'\\displaystyle'}});}
      catch{errors++;return '<code class="solution-tex-error">'+escape(tex)+'</code>';}
    };
    // Older drafts sometimes omitted math delimiters. Recognize bounded runs of
    // mathematical tokens while keeping words and punctuation as escaped prose.
    function prose(text){
      let out='',i=0;
      while(i<text.length){
        const word=text.slice(i).match(/^[A-Za-z]{2,}/);
        if(word){out+=escape(word[0]);i+=word[0].length;continue;}
        let end=i,depth=0,command=false,operator=false;
        while(end<text.length){
          const token=text.slice(end).match(/^(?:\\[A-Za-z]+|[A-Za-z](?![A-Za-z])|\d+(?:\.\d+)?|[\s{}()[\]^_+*/=<>|,'\-])/);
          if(!token)break;const t=token[0];
          if(t.startsWith('\\'))command=true;if(/[\^_=<>+*/]/.test(t))operator=true;
          if(t==='{')depth++;if(t==='}')depth--;if(depth<0)break;
          end+=t.length;
          // A braced command argument may contain normal text.
          if(t==='{'&&command){let p=end,d=1;while(p<text.length&&d){if(text[p]==='\\'){p+=2;continue;}if(text[p]==='{')d++;if(text[p]==='}')d--;p++;}if(d)break;end=p;depth--;}
        }
        let run=text.slice(i,end).trimEnd().replace(/[,']$/,'');
        if(run&&(command||operator)&&depth===0){out+=math(run);i+=run.length;}
        else{out+=escape(text[i]);i++;}
      }
      return out.replace(/\n/g,'<br>');
    }
    let html='',pos=0;const marker=/(?<!\\)(\$\$|\$|\\\(|\\\[|\\begin\{(?:align\*?|equation\*?|gather\*?)\})/g;
    for(let match;(match=marker.exec(source));){
      html+=prose(source.slice(pos,match.index));const open=match[0],env=open.match(/\\begin\{(.*?)\}/)?.[1];const close=env?'\\end{'+env+'}':({'$$':'$$','$':'$','\\(':'\\)','\\[':'\\]'})[open];
      let end=source.indexOf(close,marker.lastIndex);while(end>0&&source[end-1]==='\\')end=source.indexOf(close,end+close.length);
      if(end<0){html+=escape(open);pos=marker.lastIndex;continue;}
      let tex=source.slice(marker.lastIndex,end);if(env?.startsWith('align'))tex='\\begin{aligned}'+tex+'\\end{aligned}';if(env?.startsWith('gather'))tex='\\begin{gathered}'+tex+'\\end{gathered}';html+=math(tex,!!env||open==='$$'||open==='\\[');pos=end+close.length;marker.lastIndex=pos;
    }
    html+=prose(source.slice(pos));return {html:html||'<span class="help">The formatted solution will appear here.</span>',errors};
  }
  function update(area){
    const panel=area?.closest?.('.gs-solution-layout')?.querySelector('[data-solution-preview]');if(!panel)return;
    const result=render(area.value);panel.innerHTML=result.html;const status=area.closest('.gs-solution-layout').querySelector('[data-solution-preview-status]');if(status)status.textContent=result.errors?'Some TeX could not be rendered; its source is shown.':'';
  }
  function input(area){if(!area?.hasAttribute?.('data-gscope-tex'))return;clearTimeout(timers.get(area));timers.set(area,setTimeout(()=>{timers.delete(area);if(area.isConnected!==false)update(area);},120));}
  function beforeRender(){for(const timer of timers.values())clearTimeout(timer);timers.clear();}
  function mount(){for(const area of document.querySelectorAll('textarea[data-gscope-tex]'))update(area);}
  return {render,mount,input,beforeRender};
})();
