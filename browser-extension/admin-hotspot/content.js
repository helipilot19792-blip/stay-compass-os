(function initAdminHotspot() {
  const HOTSPOT_ID = "stay-compass-admin-hotspot";
  const HOTSPOT_SIZE = 28;
  let lastActivationAt = 0;

  if (document.getElementById(HOTSPOT_ID)) {
    return;
  }

  const hotspot = document.createElement("div");
  hotspot.id = HOTSPOT_ID;
  hotspot.setAttribute("aria-hidden", "true");
  hotspot.style.position = "fixed";
  hotspot.style.right = "0";
  hotspot.style.bottom = "0";
  hotspot.style.width = `${HOTSPOT_SIZE}px`;
  hotspot.style.height = `${HOTSPOT_SIZE}px`;
  hotspot.style.background = "transparent";
  hotspot.style.opacity = "0.01";
  hotspot.style.zIndex = "2147483647";
  hotspot.style.pointerEvents = "auto";
  hotspot.style.touchAction = "manipulation";
  hotspot.style.userSelect = "none";
  hotspot.style.webkitUserSelect = "none";

  const activate = (event) => {
    const now = Date.now();
    if (now - lastActivationAt < 1000) {
      return;
    }
    lastActivationAt = now;

    event.preventDefault();
    event.stopPropagation();
    if (typeof event.stopImmediatePropagation === "function") {
      event.stopImmediatePropagation();
    }

    chrome.runtime.sendMessage({ type: "stay-compass-open-admin" }, () => {
      if (chrome.runtime.lastError) {
        console.error("Admin hotspot message failed.", chrome.runtime.lastError.message);
      }
    });
  };

  hotspot.addEventListener("pointerdown", activate, true);
  hotspot.addEventListener("click", activate, true);
  document.documentElement.appendChild(hotspot);
})();
