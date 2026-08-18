(() => {
  "use strict";

  const MINIMUM_CONTRAST = 4.5;
  const LABEL_SELECTOR = ".label, .nodeLabel, text, tspan";
  const SHAPE_SELECTOR = "rect, circle, ellipse, polygon, path";

  function rgb(color) {
    const match = color.match(
      /^rgba?\(\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)/
    );
    return match ? match.slice(1, 4).map(Number) : null;
  }

  function luminance(channels) {
    const linear = channels.map((channel) => {
      const value = channel / 255;
      return value <= 0.04045
        ? value / 12.92
        : ((value + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
  }

  function contrast(first, second) {
    const lighter = Math.max(luminance(first), luminance(second));
    const darker = Math.min(luminance(first), luminance(second));
    return (lighter + 0.05) / (darker + 0.05);
  }

  function ensureNodeContrast(node) {
    const shape = node.querySelector(SHAPE_SELECTOR);
    const labels = [...node.querySelectorAll(LABEL_SELECTOR)];
    const background = shape && rgb(getComputedStyle(shape).fill);
    if (!background || labels.length === 0) return;

    const current = rgb(getComputedStyle(labels[0]).color);
    if (current && contrast(background, current) >= MINIMUM_CONTRAST) return;

    const white = [255, 255, 255];
    const black = [0, 0, 0];
    const labelColor =
      contrast(background, white) >= contrast(background, black)
        ? "#ffffff"
        : "#000000";

    for (const label of labels) {
      label.style.setProperty("color", labelColor, "important");
      label.style.setProperty("fill", labelColor, "important");
    }
  }

  function ensureMermaidContrast(root = document) {
    for (const node of root.querySelectorAll(".mermaid svg g.node")) {
      ensureNodeContrast(node);
    }
  }

  let pending = false;
  function scheduleContrastCheck() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      ensureMermaidContrast();
    });
  }

  new MutationObserver(scheduleContrastCheck).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
  document.addEventListener("DOMContentLoaded", scheduleContrastCheck);
  window.addEventListener("load", scheduleContrastCheck);
})();
