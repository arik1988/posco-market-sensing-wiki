(() => {
  const current = document.currentScript;
  const source = new URL("research-agent.js?ui=20260829-3", current?.src || window.location.href);
  const script = document.createElement("script");
  script.src = source.href;
  script.defer = true;
  script.addEventListener("error", () => {
    document.querySelectorAll("[data-research-agent-root]").forEach((root) => {
      const message = root.querySelector(".research-loading-shell p");
      if (message) message.textContent = "조사 관리 화면을 불러오지 못했습니다. wiki_run.bat를 다시 시작해 주세요.";
    });
  });
  document.head.append(script);
})();
