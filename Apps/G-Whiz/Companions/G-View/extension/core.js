(function (root) {
  "use strict";
  const tidy = value => String(value || "").replace(/\s+/g, " ").trim();
  const categories = {
    sections: "Other instructors’ course pages", mine: "My course pages",
    instructors: "Instructor sites", all: "All-Sections sites", other: "Other"
  };
  const colorGroups = {
    "135": {label: "135", color: "#ad2948", pale: "#fbedf1"},
    calculus: {label: "151 / 152 / 251", color: "#2768a7", pale: "#edf4fc"},
    "130": {label: "130", color: "#13756e", pale: "#eaf6f3"},
    "250": {label: "250", color: "#7550a6", pale: "#f3eefb"},
    other: {label: "Other", color: "#62707e", pale: "#f0f3f5"}
  };
  const colorOrder = ["130", "135", "calculus", "250", "other"];
  function categoryOrder(saved) {
    const valid = Array.isArray(saved) ? saved.filter(id => typeof id === "string" && Object.hasOwn(categories, id)) : [];
    return [...new Set([...valid, ...Object.keys(categories)])];
  }
  function reorderCategories(saved, source, target, after = false) {
    const order = categoryOrder(saved);
    if (source === target || !order.includes(source) || !order.includes(target)) return order;
    const next = order.filter(id => id !== source);
    next.splice(next.indexOf(target) + (after ? 1 : 0), 0, source);
    return next;
  }
  function courseInfo(title) {
    const text = tidy(title);
    const match = text.match(/(?:01:)?640:\s*(\d{3})\b/i) || text.match(/\b(?:math|calc(?:ulus)?)\s*[-:]?\s*(\d{3})\b/i) || text.match(/\b(103|111|112|115|130|135|136|151|152|250|251|477)\b/);
    const code = match?.[1] || "";
    const tail = match ? text.slice(match.index + match[0].length) : "";
    const marker = tail.match(/\b(?:sections?|sec\.?)\s*[:.]?\s*/i);
    const sectionText = marker ? tail.slice(marker.index + marker[0].length) : tail.replace(/^[\s:()\-]+/, "");
    const sections = parseSections(sectionText);
    const family = code === "135" ? "135" : ["151", "152", "251"].includes(code) ? "calculus" : ["130", "250"].includes(code) ? code : "other";
    return {code, sections, family, label: code ? `Math ${code}` : "Other sites", ...colorGroups[family], groupLabel: code ? `Math ${code}` : "Other sites"};
  }
  function parseSections(text) {
    const token = "[A-Z]?\\d{1,2}(?!\\d)";
    const range = `${token}(?:\\s*[-–]\\s*${token})?`;
    const match = tidy(text).toUpperCase().match(new RegExp(`^(${range}(?:\\s*(?:,|/|&|AND)\\s*${range})*)`));
    if (!match) return [];
    const result = [];
    for (const part of match[1].split(/\s*(?:,|\/|&|AND)\s*/)) {
      const m = part.match(/^([A-Z]?)(\d{1,2})(?:\s*[-–]\s*([A-Z]?)(\d{1,2}))?$/);
      if (!m) continue;
      const prefix = m[1], endPrefix = m[3] || prefix;
      const start = Number(m[2]), end = m[4] ? Number(m[4]) : start;
      if (prefix !== endPrefix || end < start || end - start > 98) continue;
      for (let n = start; n <= end; n++) result.push(prefix + String(n).padStart(prefix ? 1 : 2, "0"));
    }
    return [...new Set(result)];
  }
  function inferTerm(term, title) {
    term = tidy(term);
    if (term && !/^default term$/i.test(term)) return term;
    const s = tidy(title);
    let m = s.match(/\b(Spring|Summer|Fall|Winter)\s*['’]?(20\d{2}|\d{2})\b/i);
    const season = s => ({sp: "Spring", s: "Spring", su: "Summer", fa: "Fall", f: "Fall", wi: "Winter", w: "Winter"})[s.toLowerCase()];
    if (m) return `${m[1][0].toUpperCase()}${m[1].slice(1).toLowerCase()} ${m[2].length === 2 ? "20" : ""}${m[2]}`;
    m = s.match(/\b(20\d{2})(SP|SU|FA|WI)\b/i);
    if (m) return `${season(m[2])} ${m[1]}`;
    m = s.match(/\b(SP|SU|FA|WI|S|F|W)(\d{2})\b/i);
    if (m) return `${season(m[1])} 20${m[2]}`;
    return "Ongoing / no semester";
  }
  function termValue(term) {
    const m = term.match(/\b(Winter|Spring|Summer|Fall)\s+(\d{4})\b/i);
    return m ? Number(m[2]) * 10 + ({winter: 1, spring: 2, summer: 3, fall: 4})[m[1].toLowerCase()] : 0;
  }
  function autoCategory(course) {
    const s = course.title;
    if (/\ball\s+sections\b/i.test(s)) return "all";
    if (/\binstructors?\b.*\b(site|resources?|canvas)\b|\bresources?\b.*\binstructors?\b|\bmath\s+(?:department\s+)?teaching\b/i.test(s)) return "instructors";
    if (/training|workshop|sandbox|template|blueprint|test(?:ing)?\s+(?:course|for)|blank site|study groups/i.test(s)) return "other";
    if (courseInfo(s).code) return "sections";
    return "other";
  }
  function normalizeCategory(value, course) {
    if (value === "resources") return autoCategory(course) === "instructors" ? "instructors" : "other";
    return Object.hasOwn(categories, value) ? value : "";
  }
  function readCourses(doc) {
    const result = [];
    const seen = new Map();
    const expectedOrigin = doc.body?.hasAttribute("data-cco-preview") ? "https://rutgers.instructure.com" : new URL(doc.baseURI).origin;
    for (const table of doc.querySelectorAll("#my_courses_table, #past_enrollments_table, #future_enrollments_table, table.course-list-table")) {
      const enrollment = /past/.test(table.id) ? "Past" : /future/.test(table.id) ? "Future" : "Current";
      const headers = [...table.querySelectorAll("thead th")].map(h => tidy(h.textContent).toLowerCase());
      for (const row of table.querySelectorAll("tbody > tr")) {
        const cells = [...row.cells];
        const cell = (cls, heading) => row.querySelector(`.${cls}`) || cells[headers.indexOf(heading)];
        const nameCell = cell("course-list-course-title-column", "course");
        if (!nameCell) continue;
        const anchor = [...nameCell.querySelectorAll("a[href]")].find(a => {
          try { const u = new URL(a.getAttribute("href"), doc.baseURI); return u.origin === expectedOrigin && /^\/courses\/\d+\/?$/.test(u.pathname); } catch { return false; }
        });
        const favoriteEl = row.querySelector("[data-course-id]");
        const url = anchor ? new URL(anchor.getAttribute("href"), doc.baseURI) : null;
        const title = tidy(nameCell.querySelector(".name")?.textContent || anchor?.textContent || nameCell.textContent);
        if (!title) continue;
        const nativeTerm = tidy(cell("course-list-term-column", "term")?.textContent);
        const id = url?.pathname.match(/\d+/)?.[0] || favoriteEl?.getAttribute("data-course-id");
        // An unlinked course may have no Canvas ID. Use a stable local metadata key; never invent a link.
        const key = id ? `course:${id}` : `unlinked:${JSON.stringify([title, nativeTerm, enrollment])}`;
        const role = tidy(cell("course-list-enrolled-as-column", "enrolled as")?.textContent);
        const publishedText = tidy(cell("course-list-published-column", "published")?.textContent);
        const published = /^yes\b|^yesThis/i.test(publishedText) ? "Published" : /^no\b|^noThis/i.test(publishedText) ? "Unpublished" : "Unknown";
        const favorite = !!row.querySelector(".course-list-favorite-course");
        if (seen.has(key)) {
          const old = seen.get(key);
          if (role && !old.roles.includes(role)) old.roles.push(role);
          if (!old.enrollments.includes(enrollment)) old.enrollments.push(enrollment);
          old.favorite ||= favorite;
          continue;
        }
        const course = {key, id: id || null, title, url: url?.href || null,
          nickname: tidy(cell("course-list-nickname-column", "nickname")?.textContent),
          nativeTerm, term: inferTerm(nativeTerm, title), roles: role ? [role] : [],
          enrollments: [enrollment], published, favorite};
        result.push(course); seen.set(key, course);
      }
    }
    return result;
  }
  function decorate(course, settings) {
    const meta = settings?.courses?.[course.key] || {};
    const defaults = settings?.defaults?.[course.key] || {};
    return {...course, label: tidy(meta.label) || course.nickname || course.title,
      category: normalizeCategory(meta.category, course) || normalizeCategory(defaults.category, course) || autoCategory(course),
      term: tidy(meta.term) || tidy(defaults.term) || course.term, pinned: meta.pinned === true, note: tidy(meta.note),
      courseInfo: courseInfo(course.title), ownershipSource: tidy(defaults.ownershipSource), ownershipUnverified: defaults.ownershipUnverified === true};
  }
  function matches(course, filters) {
    if (filters.view === "pinned" && !course.pinned) return false;
    if (Object.hasOwn(categories, filters.view) && course.category !== filters.view) return false;
    if (filters.view === "coordinator" && !course.roles.some(r => /coordinator/i.test(r))) return false;
    if (filters.term && course.term !== filters.term) return false;
    if (filters.category && course.category !== filters.category) return false;
    if (filters.role && !course.roles.includes(filters.role)) return false;
    if (filters.enrollment && !course.enrollments.includes(filters.enrollment)) return false;
    if (filters.published && course.published !== filters.published) return false;
    if (filters.pinned && !course.pinned) return false;
    if (filters.family && (course.courseInfo || courseInfo(course.title)).family !== filters.family) return false;
    const haystack = [course.title, course.label, course.nickname, course.term, course.nativeTerm, ...course.roles, categories[course.category], course.note].join(" ").toLocaleLowerCase();
    return tidy(filters.query).toLocaleLowerCase().split(" ").filter(Boolean).every(word => haystack.includes(word));
  }
  function groupCourses(courses, savedOrder) {
    return categoryOrder(savedOrder).map(category => {
      const label = categories[category];
      const selected = courses.filter(c => c.category === category);
      const codes = [...new Set(selected.map(c => (c.courseInfo || courseInfo(c.title)).code))].sort((a, b) => (Number(a) || 9999) - (Number(b) || 9999));
      const groups = codes.map(code => {
        const items = selected.filter(c => (c.courseInfo || courseInfo(c.title)).code === code);
        const terms = [...new Set(items.map(c => c.term))].sort((a, b) => termValue(b) - termValue(a) || a.localeCompare(b));
        const semesters = terms.map(term => ({term, courses: items.filter(c => c.term === term).sort((a, b) => Number(b.pinned) - Number(a.pinned) || a.label.localeCompare(b.label, undefined, {numeric: true}))}));
        return {info: items[0].courseInfo || courseInfo(items[0].title), count: items.length, semesters};
      });
      return {category, label, count: selected.length, groups};
    });
  }
  const api = {tidy, categories, colorGroups, colorOrder, categoryOrder, reorderCategories, courseInfo, parseSections, normalizeCategory, inferTerm, termValue, autoCategory, readCourses, decorate, matches, groupCourses};
  root.GViewCore = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
