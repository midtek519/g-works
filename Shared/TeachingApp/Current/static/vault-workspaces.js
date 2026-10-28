/* Local library controls. Only a Boolean leave result crosses module frames. */
(() => {
  let model, pending;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function ready() {
    if (!model) {
      pending ||= api('/api/vault-workspaces').then(value => model = value).finally(() => pending = null);
      await pending;
    }
    const bar = document.querySelector('[data-vault-toolbar]');
    if (bar) bar.innerHTML = controls(currentPrivateModule());
    return model;
  }
  function controls(module) {
    if (!module || !model) return '';
    if (module.id !== 'grades') return `<button type="button" data-vault-action="library" data-module="${esc(module.id)}">Choose library…</button>`;
    return `<label>Course database <select data-vault-course aria-label="Course database"><option value="" ${model.active_course?'':'selected'} disabled>Choose a course</option>${model.courses.map(row => `<option value="${esc(row.id)}" ${row.id===model.active_course?'selected':''}>${esc(row.name)}${row.available?'':' (unavailable)'}</option>`).join('')}</select></label> <button type="button" data-vault-action="create">New course…</button> <button type="button" data-vault-action="register">Open database…</button>`;
  }
  function toolbar(module) {
    return `<div data-vault-toolbar style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px">${controls(module)}</div>`;
  }
  async function canLeave(module) {
    const frame = privateFrames.get(module), meta = privateMeta.get(module);
    if (!frame || !meta) return true;
    const requestId = 'workspace-' + Date.now() + '-' + Math.random().toString(36).slice(2);
    return new Promise((resolve, reject) => {
      const finish = value => {clearTimeout(timeout);window.removeEventListener('message', receive);resolve(value);};
      const receive = event => {
        if (event.source === frame.contentWindow && event.origin === meta.origin && event.data?.source === 'gwhiz-module' && event.data.type === 'workspace-leave-result' && event.data.requestId === requestId) finish(event.data.allowed === true);
      };
      const timeout = setTimeout(() => {window.removeEventListener('message', receive);reject(Error('The module is still opening. Finish or save its work, then try again.'));}, 60000);
      window.addEventListener('message', receive);
      frame.contentWindow.postMessage({source:'gwhiz-shell',version:1,type:'workspace-leave-check',module,requestId}, meta.origin);
    });
  }
  async function change(payload, module='grades', approved=false) {
    if (!approved && !await canLeave(module)) return false;
    model = await api('/api/vault-workspaces', payload);
    privateFrames.get(module)?.remove(); privateFrames.delete(module); privateMeta.delete(module); privateStarts.delete(module);
    render(); return true;
  }
  function openCourse(action) {
    const opening = action === 'register';
    modal(opening?'Open a course database':'New course database', `<form data-vault-form="${action}"><p>${opening?'Open an existing G-Vault database. Its records stay in the selected file.':'Start with empty records. Add semesters, sections, grading policies, and imports within this course.'}</p><label>Math course number<input name="code" pattern="[0-9]{3}" maxlength="3" required placeholder="151"></label><label>Course name<input name="name" maxlength="120" placeholder="Math 151"></label>${opening?'<label>Database file<input name="path" required placeholder="C:\\…\\grades.sqlite"></label>':''}<div class="actions"><button type="submit" class="primary">${opening?'Open database':'Create course'}</button></div><p data-vault-error class="error" role="status"></p></form>`);
  }
  function openLibrary(module) {
    modal(module==='recommendations'?'Letters library':'Integrity library', `<form data-vault-form="library" data-module="${module}"><p>Letters and integrity records have separate libraries, independent of course grade databases.</p><label>Library folder<input name="path" required value="${esc(model.libraries[module])}"></label><label><input type="checkbox" name="create"> Create a new library in an empty folder</label><div class="actions"><button type="submit" class="primary">Use library</button></div><p data-vault-error class="error" role="status"></p></form>`);
  }
  document.addEventListener('click', async event => {
    const button = event.target.closest('[data-vault-action]');
    if (!button) return;
    event.preventDefault();
    try {
      const module=button.dataset.vaultAction==='library'?button.dataset.module:'grades';
      if(!await canLeave(module))return;
      if (button.dataset.vaultAction === 'library') openLibrary(button.dataset.module);
      else openCourse(button.dataset.vaultAction);
    } catch(error) {toast(error.message);}
  });
  document.addEventListener('change', async event => {
    if (!event.target.matches('[data-vault-course]')) return;
    try {if (!await change({action:'select',id:event.target.value})) event.target.value=model.active_course;}
    catch(error){event.target.value=model.active_course;toast(error.message);}
  });
  document.addEventListener('submit', async event => {
    const form=event.target.closest('[data-vault-form]'); if(!form)return;
    event.preventDefault();const button=form.querySelector('[type=submit]');button.disabled=true;
    const data=Object.fromEntries(new FormData(form));data.action=form.dataset.vaultForm;data.module=form.dataset.module;data.create=data.create==='on';
    try {if(await change(data,data.action==='library'?data.module:'grades',true))dialog.close();}
    catch(error){form.querySelector('[data-vault-error]').textContent=error.message;}
    finally{button.disabled=false;}
  });
  window.VaultWorkspaces={ready,toolbar};
})();
