'use strict';
document.querySelector('#print-form').addEventListener('click',()=>window.print());
document.querySelector('#interview-kind').addEventListener('change',event=>{
  const kind=event.target.value;
  document.querySelectorAll('[data-student]').forEach(element=>element.textContent=element.dataset[kind]);
});
