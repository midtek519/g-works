(async function () {
  "use strict";
  if (!/^\/courses\/?$/.test(location.pathname) && !document.body.hasAttribute("data-cco-preview")) return;
  if (document.getElementById("cco-organizer")) return;
  const C = globalThis.CanvasOrganizerCore;
  const storageKey = `cco:v1:${location.host}`;
  const preview = document.body.hasAttribute("data-cco-preview");
  const storage = globalThis.chrome?.storage?.local || (preview ? {
    async get(key) { try { return {[key]: JSON.parse(localStorage.getItem(key) || "null")}; } catch { return {}; } },
    async set(obj) { for (const [k, v] of Object.entries(obj)) localStorage.setItem(k, JSON.stringify(v)); }
  } : null);
  if (!storage) return;
  if (!preview && globalThis.chrome?.runtime?.sendMessage) {
    try { await chrome.runtime.sendMessage({type: "g-view-bootstrap"}); } catch { /* Generic installs have no personal defaults. */ }
  }
  let settings;
  try { settings = (await storage.get(storageKey))[storageKey]; } catch (e) { console.warn("Canvas Organizer: storage unavailable", e); return; }
  if (!settings || settings.version !== 1) settings = {version: 1, courses: {}, collapsed: {}};
  settings.courses ||= {}; settings.collapsed ||= {};
  if (preview) {
    try {
      const data = JSON.parse(document.getElementById("cco-preview-defaults")?.textContent || "null");
      if (data?.schema === 1 && data.courses && settings.defaultsRevision !== data.revision) {
        settings.defaults = data.courses; settings.defaultsRevision = data.revision;
      }
    } catch { /* Preview still works without an instructor profile. */ }
  }
  let courses = C.readCourses(document);
  if (!courses.length) {
    await new Promise(resolve => {
      const observer = new MutationObserver(() => { if (C.readCourses(document).length) { observer.disconnect(); clearTimeout(timer); resolve(); } });
      observer.observe(document.body, {childList: true, subtree: true});
      const timer = setTimeout(() => { observer.disconnect(); resolve(); }, 15000);
    });
    courses = C.readCourses(document);
  }
  if (!courses.length) return;
  const firstTable = document.querySelector("#my_courses_table, #past_enrollments_table, #future_enrollments_table, table.course-list-table");
  if (!firstTable) return;
  const originalNodes = [];
  for (const table of document.querySelectorAll("#my_courses_table, #past_enrollments_table, #future_enrollments_table, table.course-list-table")) {
    const wrapper = table.parentElement.classList.contains("table-overflow-container") ? table.parentElement : table;
    originalNodes.push(wrapper);
    let prev = wrapper.previousElementSibling;
    if (prev && /^(Past|Future) Enrollments$/i.test(C.tidy(prev.textContent))) originalNodes.push(prev);
  }
  originalNodes.forEach(n => n.setAttribute("data-cco-original", ""));
  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key === "class") node.className = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else if (value !== null && value !== false) node.setAttribute(key, value === true ? "" : String(value));
    }
    for (const child of children.flat()) if (child !== null && child !== undefined) node.append(child.nodeType ? child : document.createTextNode(String(child)));
    return node;
  }
  const filters = {query: "", term: "", role: "", enrollment: "", published: "", family: "", pinned: false};
  let original = false;
  let saveQueue = Promise.resolve();
  const shell = el("section", {id: "cco-organizer", "aria-label": "Course organizer"});
  const status = el("span", {class: "cco-status", role: "status", "aria-live": "polite"});
  const saveStatus = el("span", {class: "cco-save-status", role: "status"});
  function save() {
    const snapshot = structuredClone(settings);
    saveQueue = saveQueue.catch(() => {}).then(() => storage.set({[storageKey]: snapshot})).then(() => { saveStatus.textContent = ""; }).catch(() => { saveStatus.textContent = "Changes could not be saved. Keep this tab open and try again."; });
    return saveQueue;
  }
  const search = el("input", {type: "search", placeholder: "Search courses, sections, semester…", "aria-label": "Search courses", class: "cco-search", oninput: () => { filters.query = search.value; render(); }});
  const modeButton = el("button", {type: "button", class: "cco-button cco-secondary", onclick: () => {
    original = !original;
    body.hidden = original;
    document.body.classList.toggle("cco-active", !original);
    modeButton.textContent = original ? "Organized view" : "Original Canvas view";
    if (original) status.textContent = "Canvas view · favorites work here";
    else { courses = C.readCourses(document); refreshOptions(); render(); }
  }}, "Original Canvas view");
  const tools = el("details", {class: "cco-tools"}, el("summary", {}, "Backup / help"));
  const backupPanel = el("div", {class: "cco-tools-panel"});
  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify({app: "Canvas Course Organizer", host: location.host, ...settings}, null, 2)], {type: "application/json"}));
    const a = el("a", {href: url, download: "canvas-course-labels.json"}); document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const importInput = el("input", {type: "file", accept: ".json,application/json", hidden: true, onchange: async () => {
    const file = importInput.files[0]; if (!file) return;
    try {
      if (file.size > 2e6) throw new Error("Backup is too large.");
      const data = JSON.parse(await file.text());
      if (data.app !== "Canvas Course Organizer" || data.version !== 1 || !data.courses || typeof data.courses !== "object" || Array.isArray(data.courses)) throw new Error("Choose a Canvas Course Organizer backup.");
      if (data.host !== location.host) throw new Error("This backup belongs to a different Canvas site.");
      const clean = {};
      for (const [key, meta] of Object.entries(data.courses)) {
        if (!/^(course:\d+|unlinked:)/.test(key) || !meta || typeof meta !== "object") continue;
        clean[key] = {label: C.tidy(meta.label).slice(0, 300), term: C.tidy(meta.term).slice(0, 80), category: Object.hasOwn(C.categories, meta.category) || meta.category === "resources" ? meta.category : "", pinned: meta.pinned === true, note: C.tidy(meta.note).slice(0, 500)};
      }
      settings.courses = {...settings.courses, ...clean};
      if (Array.isArray(data.categoryOrder)) settings.categoryOrder = C.categoryOrder(data.categoryOrder);
      if (data.defaults && typeof data.defaults === "object" && !Array.isArray(data.defaults)) {
        const defaults = {};
        for (const [key, meta] of Object.entries(data.defaults)) {
          if (!/^(course:\d+|unlinked:)/.test(key) || !meta || typeof meta !== "object" || !Object.hasOwn(C.categories, meta.category)) continue;
          defaults[key] = {category: meta.category, term: C.tidy(meta.term).slice(0, 80), ownershipSource: C.tidy(meta.ownershipSource).slice(0, 400), ownershipUnverified: meta.ownershipUnverified === true};
        }
        settings.defaults = {...settings.defaults, ...defaults};
      }
      await save(); refreshOptions(); render(); saveStatus.textContent = "Labels imported.";
    } catch (e) { saveStatus.textContent = e.message; }
    importInput.value = "";
  }});
  backupPanel.append(el("button", {type: "button", class: "cco-button", onclick: download}, "Export labels"), el("button", {type: "button", class: "cco-button", onclick: () => importInput.click()}, "Import labels"), importInput,
    el("p", {}, "Use Organize to change a category, rename a row, or correct a semester. Pins and labels stay in this Chrome profile. Canvas favorites are available in Original Canvas view."));
  tools.append(backupPanel);
  shell.append(el("div", {class: "cco-top"}, search, modeButton, tools), saveStatus);
  const body = el("div", {class: "cco-body"});
  const filterBar = el("div", {class: "cco-filters"});
  const selects = {};
  for (const [key, label] of [["term", "Semester"], ["role", "Canvas role"], ["enrollment", "Enrollment"], ["published", "Publication"]]) {
    const select = el("select", {"aria-label": label, onchange: () => { filters[key] = select.value; render(); }});
    selects[key] = select;
    filterBar.append(el("label", {}, el("span", {}, label), select));
  }
  function refreshOptions() {
    const decorated = courses.map(c => C.decorate(c, settings));
    const options = {
      term: [...new Set(decorated.map(c => c.term))].sort((a, b) => C.termValue(b) - C.termValue(a) || a.localeCompare(b)),
      role: [...new Set(courses.flatMap(c => c.roles))].sort(),
      enrollment: ["Current", "Past", "Future"], published: ["Published", "Unpublished", "Unknown"]
    };
    for (const [key, values] of Object.entries(options)) {
      selects[key].replaceChildren(el("option", {value: ""}, "All"), ...values.map(v => el("option", {value: v}, key === "category" ? C.categories[v] : v)));
      if (!values.includes(filters[key])) filters[key] = "";
      selects[key].value = filters[key];
    }
  }
  const pinnedOnly = el("input", {type: "checkbox", onchange: () => { filters.pinned = pinnedOnly.checked; render(); }});
  filterBar.append(el("label", {class: "cco-pinned-filter"}, pinnedOnly, "Pinned only"));
  function reset() { for (const k of Object.keys(filters)) filters[k] = k === "pinned" ? false : ""; search.value = ""; pinnedOnly.checked = false; refreshOptions(); render(); }
  filterBar.append(el("button", {type: "button", class: "cco-link-button", onclick: reset}, "Reset"));
  const legend = el("div", {class: "cco-color-legend", "aria-label": "Course colors"});
  for (const family of C.colorOrder) {
    const group = C.colorGroups[family];
    legend.append(el("button", {type: "button", "data-family": family, "aria-label": `Filter courses: ${group.label}`, "aria-pressed": "false", style: `--cco-course-color:${group.color};--cco-course-pale:${group.pale}`, onclick: () => {
      filters.family = filters.family === family ? "" : family; render();
    }}, group.label));
  }
  const results = el("div", {class: "cco-results"});
  const counts = el("div", {class: "cco-counts"}, status,
    el("button", {type: "button", class: "cco-link-button", onclick: () => setAllGroups(false)}, "Expand all"),
    el("button", {type: "button", class: "cco-link-button", onclick: () => setAllGroups(true)}, "Collapse all"));
  body.append(filterBar, legend, counts, results); shell.append(body);
  (firstTable.parentElement.classList.contains("table-overflow-container") ? firstTable.parentElement : firstTable).before(shell);

  function edit(course, opener) {
    const meta = settings.courses[course.key] || {};
    const dialog = el("dialog", {class: "cco-dialog", "aria-labelledby": "cco-edit-title"});
    const title = el("h2", {id: "cco-edit-title"}, "Organize course");
    const form = el("form", {method: "dialog"});
    const label = el("input", {value: meta.label || "", placeholder: course.nickname || course.title, maxlength: 300});
    const suggested = C.decorate(course, {defaults: settings.defaults});
    const category = el("select", {}, el("option", {value: ""}, `Automatic · ${C.categories[suggested.category]}`), ...Object.entries(C.categories).map(([v, t]) => el("option", {value: v}, t)));
    category.value = C.normalizeCategory(meta.category, course);
    const term = el("input", {value: meta.term || "", placeholder: course.term, maxlength: 80});
    const note = el("input", {value: meta.note || "", placeholder: "e.g. coordinator access", maxlength: 500});
    const field = (text, input) => {
      input.setAttribute("aria-label", text);
      return el("label", {class: "cco-field"}, el("span", {}, text), input);
    };
    const close = () => { dialog.close(); dialog.remove(); opener?.isConnected && opener.focus(); };
    form.append(title, el("p", {class: "cco-source-title"}, course.title), field("Display name", label), field("Category", category), field("Semester", term), field("Note", note),
      el("div", {class: "cco-dialog-actions"}, el("button", {type: "button", class: "cco-button", onclick: close}, "Cancel"), el("button", {type: "submit", class: "cco-button cco-primary"}, "Save")));
    form.addEventListener("submit", e => {
      e.preventDefault();
      settings.courses[course.key] = {...meta, label: label.value.trim(), category: category.value, term: term.value.trim(), note: note.value.trim()};
      save(); close(); refreshOptions(); render();
      results.querySelector(`[data-edit-key="${CSS.escape(course.key)}"]`)?.focus();
    });
    dialog.addEventListener("cancel", e => { e.preventDefault(); close(); });
    dialog.append(form); document.body.append(dialog); dialog.showModal();
  }
  function setAllGroups(collapsed) {
    for (const d of results.querySelectorAll("details")) { d.open = !collapsed; settings.collapsed[d.dataset.group] = collapsed; }
    save();
  }
  let draggingCategory = null;
  function clearDropTargets() {
    for (const node of results.querySelectorAll(".cco-drop-before, .cco-drop-after")) node.classList.remove("cco-drop-before", "cco-drop-after");
  }
  function moveCategory(source, target, after, focusDirection) {
    settings.categoryOrder = C.reorderCategories(settings.categoryOrder, source, target, after);
    save(); render();
    const header = results.querySelector(`[data-group="category:${source}"] > summary`);
    const button = focusDirection && header?.querySelector(`[data-move="${focusDirection}"]`);
    if (button && !button.disabled) button.focus(); else header?.focus();
  }
  function reorderControls(category, outer) {
    const summary = outer.querySelector("summary");
    const order = C.categoryOrder(settings.categoryOrder), index = order.indexOf(category.category);
    const grip = el("span", {class: "cco-drag-handle", draggable: "true", title: "Drag to reorder", "aria-hidden": "true",
      onclick: event => { event.preventDefault(); event.stopPropagation(); },
      ondragstart: event => {
        draggingCategory = category.category;
        if (event.dataTransfer) { event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("application/x-g-view-category", category.category); }
        outer.classList.add("cco-dragging");
      },
      ondragend: () => { draggingCategory = null; outer.classList.remove("cco-dragging"); clearDropTargets(); }
    }, "⠿");
    const controls = el("span", {class: "cco-category-order", role: "group", "aria-label": `Reorder ${category.label}`});
    for (const [direction, delta, symbol] of [["up", -1, "↑"], ["down", 1, "↓"]]) {
      const target = order[index + delta];
      controls.append(el("button", {type: "button", class: "cco-order-button", "data-move": direction, disabled: !target,
        title: `Move ${direction}`, "aria-label": `Move ${category.label} ${direction}`,
        onclick: event => { event.preventDefault(); event.stopPropagation(); if (target) moveCategory(category.category, target, delta > 0, direction); }
      }, symbol));
    }
    summary.prepend(grip); summary.append(controls);
    function after(event) {
      const rect = summary.getBoundingClientRect?.();
      return !!(rect?.height && event.clientY >= rect.top + rect.height / 2);
    }
    outer.addEventListener("dragover", event => {
      if (!draggingCategory || draggingCategory === category.category) return;
      event.preventDefault(); if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
      clearDropTargets(); outer.classList.add(after(event) ? "cco-drop-after" : "cco-drop-before");
    });
    outer.addEventListener("dragleave", event => {
      if (!event.relatedTarget || !outer.contains(event.relatedTarget)) outer.classList.remove("cco-drop-before", "cco-drop-after");
    });
    outer.addEventListener("drop", event => {
      if (!draggingCategory || draggingCategory === category.category) return;
      event.preventDefault(); event.stopPropagation();
      const source = draggingCategory; draggingCategory = null; clearDropTargets();
      moveCategory(source, category.category, after(event));
    });
  }
  function row(course) {
    const pin = el("button", {type: "button", class: "cco-pin", "aria-label": `${course.pinned ? "Unpin" : "Pin"} ${course.label}`, "aria-pressed": course.pinned ? "true" : "false", title: course.pinned ? "Unpin" : "Keep at top", onclick: () => {
      settings.courses[course.key] = {...settings.courses[course.key], pinned: !course.pinned}; save(); render();
      results.querySelector(`[data-pin-key="${CSS.escape(course.key)}"]`)?.focus();
    }, "data-pin-key": course.key}, course.pinned ? "★" : "☆");
    const name = course.url ? el("a", {href: course.url, title: course.title}, course.label) : el("span", {class: "cco-unavailable", title: "Canvas did not provide a course link"}, course.label);
    const info = el("div", {class: "cco-course-info"}, name);
    if (course.label !== course.title) info.append(el("div", {class: "cco-native-name"}, course.title));
    if (course.note) info.append(el("div", {class: "cco-note"}, course.note));
    const badges = el("div", {class: "cco-badges"});
    if (course.favorite) badges.append(el("span", {class: "cco-favorite", title: "Canvas courses menu favorite"}, "Canvas favorite"));
    if (course.published === "Unpublished") badges.append(el("span", {class: "cco-unpublished"}, "Unpublished"));
    if (!course.url) badges.append(el("span", {}, "No course link"));
    if (course.ownershipUnverified) badges.append(el("span", {class: "cco-check-owner"}, "Check instructor"));
    const organize = el("button", {type: "button", class: "cco-link-button", "aria-label": `Organize ${course.label}`, "data-edit-key": course.key, onclick: () => edit(course, organize)}, "Organize");
    return el("li", {class: "cco-course", style: `--cco-course-color:${course.courseInfo.color};--cco-course-pale:${course.courseInfo.pale}`}, pin, info, badges, el("div", {class: "cco-role"}, course.roles.join(" · ")), organize);
  }
  function render() {
    if (original) return;
    const all = courses.map(c => C.decorate(c, settings));
    const visible = all.filter(c => C.matches(c, filters));
    for (const button of legend.querySelectorAll("button")) {
      const active = filters.family === button.dataset.family;
      button.setAttribute("aria-pressed", String(active));
      button.title = active ? "Show all courses" : `Show ${C.colorGroups[button.dataset.family].label} courses`;
    }
    status.textContent = `${visible.length} of ${all.length} courses`;
    const today = new Date();
    const month = today.getMonth();
    const currentTerm = `${month < 1 ? "Winter" : month < 5 ? "Spring" : month < 8 ? "Summer" : "Fall"} ${today.getFullYear()}`;
    const forceOpen = !!(filters.query || filters.term || filters.role || filters.enrollment || filters.published || filters.family || filters.pinned);
    const fragment = document.createDocumentFragment();
    function accordion(className, key, text, count, defaultOpen) {
      const d = el("details", {class: className, "data-group": key});
      d.open = forceOpen && count > 0 || !(settings.collapsed[key] ?? !defaultOpen);
      const summary = el("summary", {}, el("span", {}, text), el("span", {class: "cco-group-count"}, count));
      summary.addEventListener("click", () => setTimeout(() => {
        if (!d.isConnected) return;
        settings.collapsed[key] = !d.open; save();
      }, 0));
      d.append(summary); return d;
    }
    for (const category of C.groupCourses(visible, settings.categoryOrder)) {
      const outer = accordion("cco-category", `category:${category.category}`, category.label, category.count, category.category === "mine");
      reorderControls(category, outer);
      const content = el("div", {class: "cco-category-content"});
      for (const group of category.groups) {
        const newest = group.semesters.find(s => C.termValue(s.term))?.term;
        const hasCurrent = group.semesters.some(s => s.term === currentTerm);
        const courseGroup = accordion("cco-course-group", `course:${category.category}:${group.info.code || "other"}`, group.info.groupLabel, group.count, hasCurrent || category.groups.length === 1);
        courseGroup.style.setProperty("--cco-course-color", group.info.color);
        courseGroup.style.setProperty("--cco-course-pale", group.info.pale);
        const semesters = el("div", {class: "cco-course-content"});
        for (const semester of group.semesters) {
          const d = accordion("cco-semester", `semester:${category.category}:${group.info.code || "other"}:${semester.term}`, semester.term, semester.courses.length, semester.term === currentTerm || !hasCurrent && (semester.term === newest || !newest));
          d.append(el("ul", {class: "cco-course-list"}, semester.courses.map(row)));
          semesters.append(d);
        }
        courseGroup.append(semesters); content.append(courseGroup);
      }
      if (!category.count) content.append(el("p", {class: "cco-empty-category"}, "No matching courses."));
      outer.append(content); fragment.append(outer);
    }
    if (!visible.length) fragment.append(el("div", {class: "cco-empty"}, filters.pinned ? "No pinned courses match these filters." : "No courses match these filters.", el("button", {type: "button", class: "cco-link-button", onclick: reset}, "Show all courses")));
    results.replaceChildren(fragment);
  }
  refreshOptions(); render(); document.body.classList.add("cco-active");
})();
