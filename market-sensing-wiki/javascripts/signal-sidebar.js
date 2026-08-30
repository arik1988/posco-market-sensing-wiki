(() => {
  "use strict";

  const navigationRequests = new Map();

  const signalBasePath = () => {
    const pathname = window.location.pathname;
    const marker = pathname.lastIndexOf("/signals/");
    return marker >= 0 ? pathname.slice(0, marker + "/signals/".length) : "";
  };

  const navigationData = (basePath) => {
    const url = `${basePath}navigation.json`;
    if (!navigationRequests.has(url)) {
      navigationRequests.set(
        url,
        fetch(url).then((response) => {
          if (!response.ok) throw new Error(`Signal navigation HTTP ${response.status}`);
          return response.json();
        }),
      );
    }
    return navigationRequests.get(url);
  };

  const ensureSidebar = () => {
    let sidebar = document.querySelector(".md-sidebar--primary");
    if (sidebar) return sidebar;
    const main = document.querySelector(".md-main__inner");
    if (!main) return null;
    sidebar = document.createElement("div");
    sidebar.className = "md-sidebar md-sidebar--primary";
    sidebar.dataset.mdComponent = "sidebar";
    sidebar.innerHTML =
      '<div class="md-sidebar__scrollwrap"><div class="md-sidebar__inner"></div></div>';
    main.prepend(sidebar);
    return sidebar;
  };

  const currentSignalId = () =>
    window.location.pathname.match(/\/signals\/(SIG-[A-Z0-9]+)\/?(?:index\.html)?$/)?.[1] || "";

  const renderNavigation = (sidebar, basePath, payload) => {
    const items = Array.isArray(payload?.items) ? payload.items : [];
    const inner = sidebar.querySelector(".md-sidebar__inner");
    if (!inner) return;

    const nav = document.createElement("nav");
    nav.className = "md-nav md-nav--primary signal-sidebar-nav";
    nav.setAttribute("aria-label", "시그널 목록");

    const heading = document.createElement("div");
    heading.className = "signal-sidebar-heading";
    const title = document.createElement("strong");
    title.textContent = "시그널 목록";
    const count = document.createElement("span");
    count.textContent = `${items.length}건`;
    heading.append(title, count);

    const indexLink = document.createElement("a");
    indexLink.className = "signal-sidebar-index";
    indexLink.href = basePath;
    indexLink.textContent = "전체 시그널 · 필터 검색";

    const list = document.createElement("ul");
    list.className = "md-nav__list signal-sidebar-list";
    const activeSignalId = currentSignalId();
    const fragment = document.createDocumentFragment();
    items.forEach((item) => {
      const signalId = String(item.signal_id || "");
      if (!/^SIG-[A-Z0-9]+$/.test(signalId)) return;
      const listItem = document.createElement("li");
      listItem.className = "md-nav__item";
      const link = document.createElement("a");
      link.className = "md-nav__link";
      link.href = `${basePath}${signalId}/`;
      link.textContent = String(item.title || signalId);
      if (signalId === activeSignalId) {
        listItem.classList.add("md-nav__item--active");
        link.classList.add("md-nav__link--active");
        link.setAttribute("aria-current", "page");
      }
      listItem.append(link);
      fragment.append(listItem);
    });
    list.append(fragment);
    nav.append(heading, indexLink, list);
    inner.replaceChildren(nav);
    sidebar.classList.add("signal-sidebar-ready");
    window.dispatchEvent(new CustomEvent("signal-sidebar-ready"));

    nav.querySelector('[aria-current="page"]')?.scrollIntoView({ block: "center" });
  };

  const enhanceSignalSidebar = () => {
    const basePath = signalBasePath();
    if (!basePath) return;
    const sidebar = ensureSidebar();
    if (!sidebar) return;
    navigationData(basePath)
      .then((payload) => renderNavigation(sidebar, basePath, payload))
      .catch(() => sidebar.classList.remove("signal-sidebar-ready"));
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enhanceSignalSidebar, { once: true });
  } else {
    enhanceSignalSidebar();
  }
  if (typeof document$ !== "undefined") document$.subscribe(enhanceSignalSidebar);
})();
