"use strict";
(() => {
  const LM = { open: false, frame: null };
  function ensureShell() {
    let root = document.getElementById("living-map-shell");
    if (root) {
      LM.frame = root.querySelector("#living-map-frame");
      return root;
    }
    root = document.createElement("section");
    root.id = "living-map-shell";
    root.className = "living-map-shell";
    root.hidden = true;
    root.setAttribute("aria-label", "Living world map");
    root.innerHTML = `<iframe id="living-map-frame" class="living-map-frame" src="/living-map/index.html?v=3.57.2" title="Worldwalker Living Map"></iframe>`;
    document.body.appendChild(root);
    LM.frame = root.querySelector("#living-map-frame");
    return root;
  }
  function showMainView(view) {
    close();
    if (typeof setMobileView === "function" && typeof isMobileLayout === "function" && isMobileLayout()) setMobileView(view || "chronicle");
  }
  window.addEventListener("message", (event) => {
    if (!LM.frame || event.source !== LM.frame.contentWindow || !event.data) return;
    const message = event.data;
    if (message.type === "worldwalker-map-close") { showMainView(message.view); return; }
    if (message.type === "worldwalker-map-action") {
      close();
      const input = document.getElementById("action-input");
      if (input && message.action) {
        input.value = String(message.action);
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.focus();
      }
      if (typeof setMobileView === "function" && typeof isMobileLayout === "function" && isMobileLayout()) setMobileView("actions");
      return;
    }
    if (message.type === "worldwalker-map-advance") {
      close();
      document.getElementById(typeof isMobileLayout === "function" && isMobileLayout() ? "btn-mobile-advance" : "btn-advance")?.click();
    }
  });
  function open() {
    const root = ensureShell();
    root.hidden = false;
    LM.open = true;
    document.body.classList.add("living-map-open");
    if (typeof isMobileLayout === "function" && isMobileLayout()) {
      document.body.setAttribute("data-mobile-view", "map");
      const dock = document.getElementById("mobile-advance-dock");
      if (dock) dock.style.setProperty("display", "none", "important");
    }
    LM.frame?.contentWindow?.postMessage({ type: "worldwalker-map-refresh" }, location.origin);
  }
  function close() {
    const root = ensureShell();
    root.hidden = true;
    LM.open = false;
    document.body.classList.remove("living-map-open");
    const dock = document.getElementById("mobile-advance-dock");
    if (dock) dock.style.removeProperty("display");
  }
  window.WorldwalkerLivingMap = { open, close, refresh: open, state: LM };
})();
