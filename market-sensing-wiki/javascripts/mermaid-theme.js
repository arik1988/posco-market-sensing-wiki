(() => {
  "use strict";

  if (!window.mermaid) return;

  window.mermaid.initialize({
    startOnLoad: false,
    theme: "base",
    themeVariables: {
      background: "transparent",
      primaryColor: "#edf2fb",
      primaryTextColor: "#20242c",
      primaryBorderColor: "#3f66c9",
      secondaryColor: "#f5f6f7",
      secondaryTextColor: "#20242c",
      tertiaryColor: "#ffffff",
      tertiaryTextColor: "#20242c",
      lineColor: "#6c737e",
      textColor: "#20242c",
      noteBkgColor: "#edf2fb",
      noteTextColor: "#20242c",
      actorBkg: "#ffffff",
      actorBorder: "#d4d8de",
      actorTextColor: "#20242c",
      clusterBkg: "#f5f6f7",
      clusterBorder: "#d4d8de",
    },
  });

  let rendering = Promise.resolve();
  let scheduled = false;

  function pendingDiagrams(root = document) {
    return [
      ...root.querySelectorAll('.mermaid:not([data-processed="true"])'),
    ].filter((diagram) => !diagram.querySelector("svg"));
  }

  function renderPendingDiagrams(root = document) {
    rendering = rendering
      .then(async () => {
        for (const diagram of pendingDiagrams(root)) {
          try {
            await window.mermaid.run({ nodes: [diagram] });
          } catch (error) {
            console.error("Mermaid diagram rendering failed.", error);
          }
        }
      })
      .catch((error) => {
        console.error("Mermaid rendering queue failed.", error);
      });
    return rendering;
  }

  function scheduleMermaidRendering(root = document) {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      renderPendingDiagrams(root);
    });
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(() => scheduleMermaidRendering());
  }
  document.addEventListener("DOMContentLoaded", () => scheduleMermaidRendering());
  window.addEventListener("load", () => scheduleMermaidRendering());
})();
