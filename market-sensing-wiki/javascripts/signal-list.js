(() => {
  "use strict";

  const createElement = (tagName, className, text) => {
    const element = document.createElement(tagName);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  };

  const appendContextText = (container, label, value) => {
    if (!value) return;
    const item = createElement("span", "signal-context-item");
    item.append(
      createElement("span", "signal-context-label", label),
      document.createTextNode(` ${value}`),
    );
    container.append(item);
  };

  const createContext = (item, detail = false) => {
    const context = createElement(
      "div",
      detail ? "signal-detail-context" : "signal-row-context",
    );
    const pills = createElement("div", "signal-pills");
    pills.setAttribute("aria-label", "사업축과 변화 유형");

    if (item.business_axis) {
      pills.append(createElement("span", "signal-pill signal-pill-axis", item.business_axis));
    }
    if (item.signal_type) {
      pills.append(createElement("span", "signal-pill signal-pill-type", item.signal_type));
    }
    if (pills.childElementCount) context.append(pills);

    const text = createElement("div", "signal-context-text");
    appendContextText(text, "회사", item.company);
    appendContextText(text, "국가·지역", item.region);
    if (text.childElementCount) context.append(text);
    return context;
  };

  const createScore = (label, value) => {
    if (value === undefined || value === null || value === "") return null;
    const group = createElement("div", "signal-score");
    const term = createElement("dt", "signal-score-label", label);
    const description = createElement("dd", "signal-score-value");
    description.setAttribute("aria-label", `${label} ${value}점, 5점 만점`);
    description.append(
      createElement("strong", "", value),
      createElement("span", "signal-score-total", "/5"),
    );
    group.append(term, description);
    return group;
  };

  const createEvaluation = (item, detail = false) => {
    const evaluation = createElement(
      "div",
      detail ? "signal-detail-evaluation" : "signal-row-evaluation",
    );
    const scores = createElement("dl", "signal-scores");
    scores.setAttribute("aria-label", "시그널 평가");
    const impact = createScore("사업영향도", item.business_impact);
    const urgency = createScore("긴급도", item.urgency);
    if (impact) scores.append(impact);
    if (urgency) scores.append(urgency);
    if (scores.childElementCount) evaluation.append(scores);

    if (item.assessed_at) {
      const date = createElement("div", "signal-assessed-at");
      date.append(
        createElement("span", "signal-context-label", "평가일"),
        document.createTextNode(" "),
      );
      const time = createElement("time", "", item.assessed_at);
      time.dateTime = item.assessed_at;
      date.append(time);
      evaluation.append(date);
    }
    return evaluation;
  };

  const tableHost = (table) =>
    table.closest(".md-typeset__scrollwrap") ||
    table.closest(".md-typeset__table") ||
    table;

  const findIndexTable = (scope) =>
    Array.from(scope.querySelectorAll("table")).find((table) => {
      const headers = Array.from(table.querySelectorAll("thead th"), (cell) =>
        cell.textContent.trim(),
      );
      return (
        headers.some((header) => header.includes("시그널")) &&
        table.querySelector('tbody a[href*="SIG-"]')
      );
    });

  const createIndexRow = (item, sourceRow) => {
    const sourceLink = sourceRow.querySelector('a[href*="SIG-"]');
    if (!sourceLink) return null;

    const row = createElement("article", "signal-index-row");
    row.setAttribute("role", "listitem");
    row.append(createContext(item));

    const copy = createElement("div", "signal-row-copy");
    const titleLink = createElement(
      "a",
      "signal-row-title",
      item.title || sourceLink.textContent.trim(),
    );
    titleLink.href = sourceLink.href;
    copy.append(titleLink);
    if (item.sentence && item.sentence !== titleLink.textContent.trim()) {
      copy.append(createElement("p", "signal-row-sentence", item.sentence));
    }
    row.append(copy, createEvaluation(item));
    return row;
  };

  const enhanceIndex = (script, payload) => {
    const scope = script.closest(".md-content__inner") || document;
    if (scope.querySelector(".signal-index-list")) return true;
    const table = findIndexTable(scope);
    if (!table || !Array.isArray(payload.items)) return false;

    const sourceRows = Array.from(table.tBodies[0]?.rows || []);
    if (!sourceRows.length || sourceRows.length !== payload.items.length) return false;

    const list = createElement("div", "signal-index-list");
    list.setAttribute("role", "list");
    list.setAttribute("aria-label", "마켓 시그널 목록");
    payload.items.forEach((item, index) => {
      const row = createIndexRow(item, sourceRows[index]);
      if (row) list.append(row);
    });
    if (list.childElementCount !== sourceRows.length) return false;
    tableHost(table).replaceWith(list);
    return true;
  };

  const findDetailMetaTable = (scope) =>
    Array.from(scope.querySelectorAll("table")).find((table) => {
      const headers = Array.from(table.querySelectorAll("thead th"), (cell) =>
        cell.textContent.trim(),
      );
      return ["사업축", "사업영향도", "긴급도", "평가일"].every((label) =>
        headers.includes(label),
      );
    });

  const findSignalSentence = (scope) =>
    Array.from(scope.querySelectorAll(".admonition.abstract")).find((admonition) =>
      admonition.querySelector(".admonition-title")?.textContent.includes("한 문장"),
    );

  const enhanceDetail = (script, payload) => {
    const scope = script.closest(".md-content__inner") || document;
    if (scope.querySelector(".signal-detail-context")) return true;
    const item = payload.item;
    const title = scope.querySelector("h1");
    if (!item || !title) return false;

    title.classList.add("signal-detail-title");
    if (item.title) title.textContent = item.title;
    title.before(createContext(item, true));

    const sentence = findSignalSentence(scope);
    if (sentence) {
      sentence.classList.add("signal-detail-lede");
      const sentenceLabel = sentence.querySelector(".admonition-title");
      if (sentenceLabel) sentenceLabel.textContent = "사업 시사점";
      const sentenceBody = sentence.querySelector("p:not(.admonition-title)");
      if (sentenceBody && item.sentence) sentenceBody.textContent = item.sentence;
    }

    const evaluation = createEvaluation(item, true);
    const metaTable = findDetailMetaTable(scope);
    if (metaTable) {
      tableHost(metaTable).replaceWith(evaluation);
    } else if (sentence) {
      sentence.after(evaluation);
    } else {
      title.after(evaluation);
    }
    return true;
  };

  const enhanceSignals = () => {
    document.querySelectorAll("script[data-signal-ui]").forEach((script) => {
      if (script.dataset.signalUiEnhanced === "true") return;
      let payload;
      try {
        payload = JSON.parse(script.textContent);
      } catch (_error) {
        return;
      }
      const enhanced =
        payload.kind === "index"
          ? enhanceIndex(script, payload)
          : payload.kind === "detail"
            ? enhanceDetail(script, payload)
            : false;
      if (enhanced) script.dataset.signalUiEnhanced = "true";
    });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enhanceSignals, { once: true });
  } else {
    enhanceSignals();
  }
  if (typeof document$ !== "undefined") document$.subscribe(enhanceSignals);
})();
