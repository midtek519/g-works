/* The locally bundled CodeMirror editor synchronizes the existing answer controls. */
window.GScopeTexEditors=(()=>{
  function beforeRender(){window.GScopeSolutionPreview?.beforeRender?.();window.GWhizLatexEditors?.beforeRender?.();}
  function mount(version){
    window.GScopeSolutionPreview?.mount?.();
    if(!version||!window.GWhizLatexEditors)return;
    for(const area of document.querySelectorAll('textarea[data-gscope-tex]')){
      if(area.closest('[hidden]'))continue;
      window.GWhizLatexEditors.mount({querySelectorAll:()=>[area]},{scope:'gscope:'+version+':'+(area.dataset.answerQuestion||area.id)});
      // Keep keyboard guidance ahead of the visible editor, including remounts.
      const next=area.nextElementSibling,host=next?.classList.contains('latex-editor-help')?next.nextElementSibling:next;
      if(host?.classList.contains('latex-editor-host')){
        const help=next?.classList.contains('latex-editor-help')?next:host.nextElementSibling;
        if(help?.classList.contains('latex-editor-help')){const layout=area.closest('.gs-solution-layout');if(layout)layout.before(help);else host.before(help);}
        const description=area.getAttribute('aria-describedby');
        if(description)host.querySelector('.cm-content')?.setAttribute('aria-describedby',description);
      }
    }
  }
  return {beforeRender,mount,sync:()=>window.GWhizLatexEditors?.sync?.()};
})();
