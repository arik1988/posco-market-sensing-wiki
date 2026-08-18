(() => {
  "use strict";

  const STORAGE_KEY = "market-sensing-wiki:linked-context";
  const TARGET_CLASS = "linked-context-target";
  const MAX_AGE_MS = 30_000;

  function normalizeText(value) {
    return String(value || "")
      .replace(/\s+/g, " ")
      .replace(/\s+[·\-–—]\s+(?:현재|연구·실증|계획·투자).*$/u, "")
      .replace(/\s+(?:기술|기업)\s+현황$/u, "")
      .trim();
  }

  function normalizePath(pathname) {
    const decoded = decodeURIComponent(pathname).replace(/\/index\.html$/u, "/");
    return decoded.length > 1 ? decoded.replace(/\/+$/u, "") : decoded;
  }

  function uniqueCandidates(values) {
    const seen = new Set();
    const result = [];
    for (const value of values) {
      const text = normalizeText(value);
      const key = text.toLocaleLowerCase("ko-KR");
      if (text.length < 2 || seen.has(key)) continue;
      seen.add(key);
      result.push(text);
    }
    return result;
  }

  function navigationCandidates(link) {
    const currentTitle = document.querySelector(".md-content h1")?.textContent;
    const row = link.closest("tr");
    const firstCell = row?.querySelector("th:first-child, td:first-child");
    const firstCellText = firstCell?.textContent;
    const clickedFirstCell = Boolean(firstCell?.contains(link));
    const nearbyHeading = link.closest("h2, h3, h4, h5, h6")?.textContent;

    return uniqueCandidates(
      clickedFirstCell
        ? [currentTitle, nearbyHeading, link.textContent, firstCellText]
        : [firstCellText, currentTitle, nearbyHeading, link.textContent],
    );
  }

  function rememberContext(event) {
    if (event.defaultPrevented || event.button !== 0) return;
    if (!(event.target instanceof Element)) return;
    const link = event.target.closest(".md-content a[href]");
    if (!link || link.hasAttribute("download")) return;

    const target = new URL(link.href, window.location.href);
    if (
      target.origin !== window.location.origin ||
      target.hash ||
      normalizePath(target.pathname) === normalizePath(window.location.pathname)
    ) {
      return;
    }

    const candidates = navigationCandidates(link);
    if (!candidates.length) return;

    try {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          targetPath: normalizePath(target.pathname),
          candidates,
          createdAt: Date.now(),
        }),
      );
    } catch {
      // Navigation must keep working when session storage is unavailable.
    }
  }

  function readContext() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      const context = JSON.parse(raw);
      const expired = Date.now() - Number(context.createdAt) > MAX_AGE_MS;
      const wrongPage =
        normalizePath(context.targetPath) !==
        normalizePath(window.location.pathname);
      if (expired || wrongPage || !Array.isArray(context.candidates)) {
        return null;
      }
      return context;
    } catch {
      return null;
    }
  }

  function clearContext() {
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // Nothing else is required when session storage is unavailable.
    }
  }

  function matchScore(element, candidate) {
    const text = normalizeText(element.textContent).toLocaleLowerCase("ko-KR");
    const query = normalizeText(candidate).toLocaleLowerCase("ko-KR");
    if (!text || !query) return Number.POSITIVE_INFINITY;
    if (text === query) return 0;
    if (text.startsWith(`${query} `) || text.startsWith(`${query} ·`)) return 1;
    if (text.includes(query)) return 2;
    return Number.POSITIVE_INFINITY;
  }

  function findTarget(candidates) {
    const content = document.querySelector(".md-content__inner");
    if (!content) return null;

    const landmarks = Array.from(
      content.querySelectorAll(
        [
          "h2",
          "h3",
          "h4",
          "h5",
          "h6",
          "details > summary",
          ".admonition-title",
          "tbody > tr > td:first-child",
        ].join(", "),
      ),
    );

    for (const candidate of candidates) {
      let best = null;
      let bestScore = Number.POSITIVE_INFINITY;
      for (const landmark of landmarks) {
        const score = matchScore(landmark, candidate);
        if (score < bestScore) {
          best = landmark;
          bestScore = score;
        }
      }
      if (best) {
        return best.closest("tr, details, .admonition") || best;
      }
    }
    return null;
  }

  function revealLinkedContext() {
    if (window.location.hash) return;
    const context = readContext();
    if (!context) return;
    clearContext();

    window.setTimeout(() => {
      requestAnimationFrame(() => {
        const target = findTarget(context.candidates);
        if (!target) return;

        document
          .querySelectorAll(`.${TARGET_CLASS}`)
          .forEach((element) => element.classList.remove(TARGET_CLASS));
        target.classList.add(TARGET_CLASS);
        const targetNeedsCentering = () => {
          const scrollingElement =
            document.scrollingElement || document.documentElement;
          if (scrollingElement.scrollHeight <= window.innerHeight + 1) {
            return false;
          }
          const box = target.getBoundingClientRect();
          return box.top < 72 || box.bottom > window.innerHeight - 24;
        };
        const centerTarget = () => {
          if (!targetNeedsCentering()) return;
          const box = target.getBoundingClientRect();
          const scrollingElement =
            document.scrollingElement || document.documentElement;
          const desiredTop =
            box.top + window.scrollY - (window.innerHeight - box.height) / 2;
          const maximumTop = Math.max(
            0,
            scrollingElement.scrollHeight - window.innerHeight,
          );
          const top = Math.min(maximumTop, Math.max(0, desiredTop));
          if (Math.abs(window.scrollY - top) < 1) return;
          const root = document.documentElement;
          const previousScrollBehavior = root.style.scrollBehavior;
          root.style.scrollBehavior = "auto";
          window.scrollTo(0, top);
          requestAnimationFrame(() => {
            root.style.scrollBehavior = previousScrollBehavior;
          });
        };

        centerTarget();
        window.setTimeout(() => {
          if (!target.isConnected) return;
          centerTarget();
        }, 650);
        window.setTimeout(() => target.classList.remove(TARGET_CLASS), 3200);
      });
    }, 120);
  }

  if (!window.__steelContextualNavigationInstalled) {
    window.__steelContextualNavigationInstalled = true;
    document.addEventListener("click", rememberContext, true);
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(revealLinkedContext);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", revealLinkedContext);
  } else {
    revealLinkedContext();
  }
})();
