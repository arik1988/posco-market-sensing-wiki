(() => {
  "use strict";

  const MIN_SCALE = 0.05;
  const MAX_SCALE = 8;
  let closeActiveViewer = null;

  function clamp(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, value));
  }

  function diagramSize(svg) {
    const viewBox = svg.viewBox && svg.viewBox.baseVal;
    if (viewBox && viewBox.width > 0 && viewBox.height > 0) {
      return { width: viewBox.width, height: viewBox.height };
    }
    const bounds = svg.getBoundingClientRect();
    return {
      width: Math.max(1, bounds.width),
      height: Math.max(1, bounds.height),
    };
  }

  function openViewer(source) {
    const svg = source.querySelector("svg");
    if (!svg) return;
    if (closeActiveViewer) closeActiveViewer();

    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    const placeholder = document.createComment("mermaid-viewer-placeholder");
    const size = diagramSize(svg);
    const viewer = document.createElement("div");
    viewer.className = "mermaid-viewer";
    viewer.setAttribute("role", "dialog");
    viewer.setAttribute("aria-modal", "true");
    viewer.setAttribute("aria-label", "Mermaid 차트 전체보기");
    viewer.innerHTML = `
      <div class="mermaid-viewer-panel">
        <div class="mermaid-viewer-toolbar">
          <strong>Mermaid</strong>
          <div class="mermaid-viewer-actions">
            <button type="button" data-action="zoom-out" aria-label="축소" title="축소">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M5 12h14"></path>
              </svg>
            </button>
            <output class="mermaid-viewer-zoom-value">100%</output>
            <button type="button" data-action="zoom-in" aria-label="확대" title="확대">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M12 5v14M5 12h14"></path>
              </svg>
            </button>
            <button type="button" data-action="fit" aria-label="배율 초기화" title="배율 초기화">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M4 12a8 8 0 1 0 2.35-5.65L4 8.7M4 4v4.7h4.7"></path>
              </svg>
            </button>
            <button type="button" data-action="close" aria-label="전체보기 닫기" title="닫기">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M5 5l14 14M19 5L5 19"></path>
              </svg>
            </button>
          </div>
        </div>
        <div class="mermaid-viewer-canvas">
          <div class="mermaid-viewer-stage"></div>
        </div>
      </div>
    `;

    const canvas = viewer.querySelector(".mermaid-viewer-canvas");
    const stage = viewer.querySelector(".mermaid-viewer-stage");
    const closeButton = viewer.querySelector('[data-action="close"]');
    const fitButton = viewer.querySelector('[data-action="fit"]');
    const zoomOutButton = viewer.querySelector('[data-action="zoom-out"]');
    const zoomInButton = viewer.querySelector('[data-action="zoom-in"]');
    const zoomValue = viewer.querySelector(".mermaid-viewer-zoom-value");
    const originalParent = svg.parentNode;
    originalParent.insertBefore(placeholder, svg);
    stage.appendChild(svg);
    document.body.appendChild(viewer);
    document.body.style.overflow = "hidden";

    let scale = 1;
    let panX = 0;
    let panY = 0;
    let pointerId = null;
    let previousX = 0;
    let previousY = 0;

    function renderTransform() {
      const scaledWidth = size.width * scale;
      const scaledHeight = size.height * scale;
      stage.style.width = `${scaledWidth}px`;
      stage.style.height = `${scaledHeight}px`;
      stage.style.marginLeft = `${scaledWidth / -2}px`;
      stage.style.marginTop = `${scaledHeight / -2}px`;
      stage.style.transform = `translate(${panX}px, ${panY}px)`;
      zoomValue.textContent = `${Math.round(scale * 100)}%`;
      zoomOutButton.disabled = scale <= MIN_SCALE;
      zoomInButton.disabled = scale >= MAX_SCALE;
    }

    function changeScale(nextScale) {
      nextScale = clamp(nextScale, MIN_SCALE, MAX_SCALE);
      const ratio = nextScale / scale;
      panX *= ratio;
      panY *= ratio;
      scale = nextScale;
      renderTransform();
    }

    function fitDiagram() {
      const padding = 48;
      scale = clamp(
        Math.min(
          (canvas.clientWidth - padding) / size.width,
          (canvas.clientHeight - padding) / size.height
        ),
        MIN_SCALE,
        MAX_SCALE
      );
      panX = 0;
      panY = 0;
      renderTransform();
    }

    function onWheel(event) {
      event.preventDefault();
      const bounds = canvas.getBoundingClientRect();
      const cursorX = event.clientX - bounds.left - bounds.width / 2;
      const cursorY = event.clientY - bounds.top - bounds.height / 2;
      const nextScale = clamp(
        scale * Math.exp(-event.deltaY * 0.0015),
        MIN_SCALE,
        MAX_SCALE
      );
      const ratio = nextScale / scale;
      panX = cursorX - (cursorX - panX) * ratio;
      panY = cursorY - (cursorY - panY) * ratio;
      scale = nextScale;
      renderTransform();
    }

    function onPointerDown(event) {
      if (event.button !== 0) return;
      pointerId = event.pointerId;
      previousX = event.clientX;
      previousY = event.clientY;
      canvas.classList.add("is-panning");
      canvas.setPointerCapture(pointerId);
      event.preventDefault();
    }

    function onPointerMove(event) {
      if (event.pointerId !== pointerId) return;
      panX += event.clientX - previousX;
      panY += event.clientY - previousY;
      previousX = event.clientX;
      previousY = event.clientY;
      renderTransform();
    }

    function onPointerUp(event) {
      if (event.pointerId !== pointerId) return;
      pointerId = null;
      canvas.classList.remove("is-panning");
    }

    function onKeyDown(event) {
      if (event.key === "Escape") closeViewer();
    }

    function closeViewer() {
      canvas.removeEventListener("wheel", onWheel);
      window.removeEventListener("resize", fitDiagram);
      document.removeEventListener("keydown", onKeyDown);
      if (placeholder.parentNode) {
        placeholder.parentNode.replaceChild(svg, placeholder);
      }
      viewer.remove();
      document.body.style.overflow = previousOverflow;
      closeActiveViewer = null;
      if (previousFocus instanceof HTMLElement) previousFocus.focus();
    }

    closeActiveViewer = closeViewer;
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointercancel", onPointerUp);
    fitButton.addEventListener("click", fitDiagram);
    zoomOutButton.addEventListener("click", () => changeScale(scale - 0.2));
    zoomInButton.addEventListener("click", () => changeScale(scale + 0.2));
    closeButton.addEventListener("click", closeViewer);
    viewer.addEventListener("click", (event) => {
      if (event.target === viewer) closeViewer();
    });
    window.addEventListener("resize", fitDiagram);
    document.addEventListener("keydown", onKeyDown);
    fitDiagram();
    closeButton.focus();
  }

  function installViewerButtons(root = document) {
    for (const diagram of root.querySelectorAll(".mermaid")) {
      if (!diagram.querySelector("svg")) continue;
      diagram.classList.add("mermaid-with-viewer");
      if (diagram.querySelector(":scope > .mermaid-viewer-open")) continue;

      const button = document.createElement("button");
      button.type = "button";
      button.className = "mermaid-viewer-open";
      button.setAttribute("aria-label", "Mermaid 차트 전체보기");
      button.setAttribute("title", "전체보기");
      button.innerHTML = `
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9 3H3v6M15 3h6v6M9 21H3v-6M15 21h6v-6"></path>
        </svg>
      `;
      button.addEventListener("click", () => openViewer(diagram));
      diagram.appendChild(button);
    }
  }

  let pending = false;
  function scheduleViewerSetup() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      installViewerButtons();
    });
  }

  new MutationObserver(scheduleViewerSetup).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
  document.addEventListener("DOMContentLoaded", scheduleViewerSetup);
  window.addEventListener("load", scheduleViewerSetup);
})();
