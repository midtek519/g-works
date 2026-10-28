"use strict";
// This is a private extension page, opened by the local launcher. It has no
// externally-connectable API, web-accessible resources or extra permissions.
(function () {
  const params = new URLSearchParams(location.search);
  const manifest = chrome.runtime.getManifest();
  const name = manifest.name;
  const status = document.getElementById("status");
  const reload = document.getElementById("reload");
  document.getElementById("name").textContent = name;
  document.title = name + " · Extension setup";
  const target = params.get("extension");
  const managerUrl = "chrome://extensions/" +
    (target && /^[a-p]{32}$/.test(target) ? "?id=" + target : "");
  function manager() {
    chrome.tabs.create({url: managerUrl}, () => {
      if (chrome.runtime.lastError) {
        status.textContent = "Enter chrome://extensions/ in Chrome’s address bar.";
        return;
      }
      status.textContent = "Chrome extensions opened. You can close this setup tab.";
    });
  }
  function requestReload() {
    reload.disabled = true;
    status.textContent = "Reload requested. Chrome is refreshing " + name + ".";
    // Chrome may reload or close this view along with the extension. A fragment
    // marks the resulting view so it never issues another automatic reload.
    history.replaceState(null, "", location.pathname + "?action=reload#requested");
    try { chrome.runtime.reload(); }
    catch {
      status.textContent = "Chrome could not reload the extension. Use Chrome extensions below.";
      reload.disabled = false;
    }
  }
  reload.addEventListener("click", requestReload);
  document.getElementById("manager").addEventListener("click", manager);
  if (params.get("action") === "reload") {
    reload.hidden = false;
    if (location.hash === "#requested") {
      status.textContent = name + " is running · version " + (manifest.version_name || manifest.version) + ".";
    } else requestReload();
  } else manager();
})();
