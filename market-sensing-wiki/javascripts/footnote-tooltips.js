(() => {
  "use strict";

  const TOOLTIP_ATTRIBUTE = "data-footnote-tooltip";
  const TOOLTIP_ID = "footnote-source-tooltip";

  function originalSourceLink(definition) {
    return Array.from(definition.querySelectorAll("a[href]")).find((link) => {
      const label = link.textContent.replace(/\s+/g, " ").trim();
      return (
        (label === "원문" || label === "원문 보기") &&
        /^https?:\/\//i.test(link.href)
      );
    });
  }

  function footnoteText(definition, originalLink) {
    const copy = definition.cloneNode(true);
    copy.querySelectorAll("a.footnote-backref").forEach((link) => link.remove());
    copy.querySelectorAll("a").forEach((link) => {
      link.replaceWith(link.textContent);
    });
    const text = copy.textContent
      .replace(/\s+/g, " ")
      .replace(/\s*[·|]\s*$/, "")
      .trim();
    if (!originalLink) return text;

    const hostname = new URL(originalLink.href).hostname.replace(/^www\./, "");
    return `${text} · 원본 사이트: ${hostname}`;
  }

  function tooltipElement() {
    let tooltip = document.getElementById(TOOLTIP_ID);
    if (tooltip) return tooltip;

    tooltip = document.createElement("div");
    tooltip.id = TOOLTIP_ID;
    tooltip.className = "footnote-source-tooltip";
    tooltip.setAttribute("role", "tooltip");
    tooltip.hidden = true;
    document.body.appendChild(tooltip);
    return tooltip;
  }

  function hideTooltip() {
    const tooltip = document.getElementById(TOOLTIP_ID);
    if (tooltip) tooltip.hidden = true;
  }

  function showTooltip(reference) {
    const tooltip = tooltipElement();
    tooltip.textContent = reference.getAttribute(TOOLTIP_ATTRIBUTE);
    tooltip.hidden = false;

    const referenceBox = reference.getBoundingClientRect();
    const tooltipBox = tooltip.getBoundingClientRect();
    const viewportPadding = 12;
    const gap = 10;
    const centeredLeft =
      referenceBox.left + referenceBox.width / 2 - tooltipBox.width / 2;
    const left = Math.min(
      Math.max(centeredLeft, viewportPadding),
      window.innerWidth - tooltipBox.width - viewportPadding,
    );
    const above = referenceBox.top - tooltipBox.height - gap;
    const top =
      above >= viewportPadding ? above : referenceBox.bottom + gap;

    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  }

  function bindTooltip(reference) {
    if (reference.dataset.footnoteTooltipBound === "true") return;
    reference.dataset.footnoteTooltipBound = "true";
    reference.addEventListener("mouseenter", () => showTooltip(reference));
    reference.addEventListener("focus", () => showTooltip(reference));
    reference.addEventListener("mouseleave", hideTooltip);
    reference.addEventListener("blur", hideTooltip);
    reference.addEventListener("keydown", (event) => {
      if (event.key === "Escape") hideTooltip();
    });
  }

  function installFootnoteTooltips(root = document) {
    for (const reference of root.querySelectorAll("a.footnote-ref[href^='#fn']")) {
      if (reference.hasAttribute(TOOLTIP_ATTRIBUTE)) continue;

      const targetId = reference.hash.slice(1);
      const definition = document.getElementById(targetId);
      if (!definition) continue;

      const originalLink = originalSourceLink(definition);
      const text = footnoteText(definition, originalLink);
      if (!text) continue;

      reference.setAttribute(TOOLTIP_ATTRIBUTE, text);
      reference.setAttribute("aria-describedby", TOOLTIP_ID);
      bindTooltip(reference);

      if (originalLink) {
        reference.setAttribute("href", originalLink.href);
        reference.setAttribute("target", "_blank");
        reference.setAttribute("rel", "noopener noreferrer");
        reference.setAttribute(
          "aria-label",
          `출처: ${text} (원본 사이트 새 탭에서 열기)`,
        );
      } else {
        reference.setAttribute("aria-label", `각주: ${text}`);
      }
    }
  }

  let pending = false;
  function scheduleSetup() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      installFootnoteTooltips();
    });
  }

  new MutationObserver(scheduleSetup).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
  document.addEventListener("DOMContentLoaded", scheduleSetup);
  window.addEventListener("load", scheduleSetup);
  window.addEventListener("scroll", hideTooltip, true);
  window.addEventListener("resize", hideTooltip);
})();
