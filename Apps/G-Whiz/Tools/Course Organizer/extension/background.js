"use strict";

// A user click opens the course directory. No tab-reading permission is needed.
chrome.action.onClicked.addListener(() => {
  chrome.tabs.create({url: "https://rutgers.instructure.com/courses"});
});

// Optional, local-only setup data. This file is explicitly excluded from the
// distributable extension package; the G-Whiz helper stages it from app Data.
let bootstrapPromise;
async function seedLocalDefaults() {
  if (bootstrapPromise) return bootstrapPromise;
  bootstrapPromise = (async () => {
    try {
      const response = await fetch(chrome.runtime.getURL("local-defaults.json"));
      if (!response.ok) return false;
      const data = await response.json();
      if (data.app !== "G-View local defaults" || data.schema !== 1 || data.host !== "rutgers.instructure.com" || !data.courses || Array.isArray(data.courses)) return false;
      const key = `cco:v1:${data.host}`;
      const stored = (await chrome.storage.local.get(key))[key];
      const settings = stored?.version === 1 ? stored : {version: 1, courses: {}, collapsed: {}};
      if (settings.defaultsRevision === data.revision) return true;
      const defaults = {};
      for (const [id, value] of Object.entries(data.courses)) {
        if (!/^(course:\d+|unlinked:)/.test(id) || !value || typeof value !== "object") continue;
        if (!["sections", "mine", "instructors", "all", "other"].includes(value.category)) continue;
        defaults[id] = {category: value.category, term: typeof value.term === "string" ? value.term.slice(0, 80) : "", ownershipSource: typeof value.ownershipSource === "string" ? value.ownershipSource.slice(0, 400) : "", ownershipUnverified: value.ownershipUnverified === true};
      }
      await chrome.storage.local.set({[key]: {...settings, defaults, defaultsRevision: data.revision}});
      return true;
    } catch { return false; }
  })();
  try { return await bootstrapPromise; } finally { bootstrapPromise = null; }
}
chrome.runtime.onInstalled.addListener(() => { seedLocalDefaults(); });
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message?.type !== "g-view-bootstrap") return;
  if (sender.url && new URL(sender.url).hostname !== "rutgers.instructure.com") { respond(false); return; }
  seedLocalDefaults().then(respond); return true;
});
