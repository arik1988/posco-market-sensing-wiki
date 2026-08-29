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

  let scoreRationaleId = 0;

  const createScore = (label, assessment) => {
    const value = assessment?.score;
    const rationale = String(assessment?.rationale || "").trim();
    if (value === undefined || value === null || value === "") return null;
    const group = createElement("div", "signal-score");
    const term = createElement("dt", "signal-score-label", label);
    const description = createElement("dd", "signal-score-value");
    description.setAttribute("aria-label", `${label} ${value}점, 10점 만점`);
    description.append(
      createElement("strong", "", value),
      createElement("span", "signal-score-total", "/10"),
    );
    group.append(term, description);
    if (rationale) {
      const tooltip = createElement("span", "signal-score-rationale", rationale);
      tooltip.id = `signal-score-rationale-${++scoreRationaleId}`;
      tooltip.setAttribute("role", "tooltip");
      group.classList.add("signal-score-with-rationale");
      group.tabIndex = 0;
      group.setAttribute("aria-describedby", tooltip.id);
      group.append(tooltip);
    }
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

    const dates = createElement("div", "signal-row-dates");
    [
      ["감지일", item.detected_at],
      ["평가일", item.assessed_at],
    ].forEach(([label, value]) => {
      if (!value) return;
      const date = createElement("div", "signal-assessed-at");
      date.append(
        createElement("span", "signal-context-label", label),
        document.createTextNode(" "),
      );
      const time = createElement("time", "", value);
      time.dateTime = value;
      date.append(time);
      dates.append(date);
    });
    if (dates.childElementCount) evaluation.append(dates);
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

  const createIndexSection = (title, description, entries) => {
    if (!entries.length) return null;

    const section = createElement("section", "signal-index-section");
    const heading = createElement("h2", "signal-index-section-title", title);
    section.append(heading);
    if (description) {
      section.append(
        createElement("p", "signal-index-section-description", description),
      );
    }

    const list = createElement("div", "signal-index-list");
    list.setAttribute("role", "list");
    list.setAttribute("aria-label", `${title} 목록`);
    entries.forEach(({ item, sourceRow }) => {
      const row = createIndexRow(item, sourceRow);
      if (row) list.append(row);
    });
    if (list.childElementCount !== entries.length) return null;
    section.append(list);
    return section;
  };

  const localIsoDate = (date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  };

  const createDateFilter = (onChange) => {
    const toolbar = createElement("section", "signal-index-toolbar");
    toolbar.setAttribute("aria-label", "감지일 필터");

    const filter = createElement("div", "signal-date-filter");
    filter.append(createElement("strong", "signal-date-filter-title", "감지일"));

    const createDateField = (labelText, ariaLabel) => {
      const label = createElement("label", "signal-date-field");
      label.append(createElement("span", "", labelText));
      const input = createElement("input");
      input.type = "date";
      input.setAttribute("aria-label", ariaLabel);
      label.append(input);
      return { label, input };
    };
    const from = createDateField("시작", "감지일 시작");
    const to = createDateField("종료", "감지일 종료");
    const separator = createElement("span", "signal-date-separator", "~");
    filter.append(from.label, separator, to.label);

    const presets = createElement("div", "signal-date-presets");
    presets.setAttribute("aria-label", "감지일 빠른 선택");
    const presetButtons = [];
    [
      ["최근 1일", 1],
      ["최근 1주일", 7],
      ["최근 1개월", 30],
    ].forEach(([label, days]) => {
      const button = createElement("button", "signal-date-preset", label);
      button.type = "button";
      button.setAttribute("aria-pressed", "false");
      button.addEventListener("click", () => {
        const end = new Date();
        const start = new Date(end.getFullYear(), end.getMonth(), end.getDate());
        start.setDate(start.getDate() - (days - 1));
        from.input.value = localIsoDate(start);
        to.input.value = localIsoDate(end);
        presetButtons.forEach((candidate) => {
          candidate.setAttribute("aria-pressed", String(candidate === button));
        });
        onChange(from.input.value, to.input.value);
      });
      presetButtons.push(button);
      presets.append(button);
    });
    const reset = createElement("button", "signal-date-reset", "전체");
    reset.type = "button";
    reset.addEventListener("click", () => {
      from.input.value = "";
      to.input.value = "";
      presetButtons.forEach((button) => button.setAttribute("aria-pressed", "false"));
      onChange("", "");
    });
    presets.append(reset);
    filter.append(presets);

    const status = createElement("div", "signal-filter-status");
    const summary = createElement("span", "signal-filter-summary");
    summary.setAttribute("aria-live", "polite");
    const error = createElement("span", "signal-filter-error");
    error.setAttribute("role", "alert");
    status.append(summary, error);
    toolbar.append(filter, status);

    const manualChange = () => {
      presetButtons.forEach((button) => button.setAttribute("aria-pressed", "false"));
      onChange(from.input.value, to.input.value);
    };
    from.input.addEventListener("change", manualChange);
    to.input.addEventListener("change", manualChange);

    return { toolbar, summary, error };
  };

  const enhanceIndex = (script, payload) => {
    const scope = script.closest(".md-content__inner") || document;
    if (scope.querySelector(".signal-index-groups")) return true;
    const table = findIndexTable(scope);
    if (!table || !Array.isArray(payload.items)) return false;

    const sourceRows = Array.from(table.tBodies[0]?.rows || []);
    if (!sourceRows.length || sourceRows.length !== payload.items.length) return false;

    const entries = payload.items.map((item, index) => ({
      item,
      sourceRow: sourceRows[index],
    }));
    const wrapper = createElement("div", "signal-index-explorer");
    const container = createElement("div", "signal-index-groups");

    const render = (from, to) => {
      container.replaceChildren();
      filter.error.textContent = "";
      const invalidRange = from && to && from > to;
      const visible = invalidRange
        ? []
        : entries.filter(({ item }) => {
            const detectedAt = item.detected_at || item.assessed_at || "";
            if (!detectedAt) return !from && !to;
            return (!from || detectedAt >= from) && (!to || detectedAt <= to);
          });
      if (invalidRange) {
        filter.error.textContent = "시작일은 종료일보다 늦을 수 없습니다.";
      }
      filter.summary.textContent = `전체 ${entries.length}건 중 ${visible.length}건`;

      const groups = { core: [], execution: [] };
      visible.forEach((entry) => {
        if (entry.item.signal_role === "execution_context") {
          groups.execution.push(entry);
        } else {
          groups.core.push(entry);
        }
      });
      const coreSection = createIndexSection("핵심 시장신호", "", groups.core);
      const executionSection = createIndexSection(
        "실행·노출 확인",
        "회사 발표·실적을 외부 시장신호의 노출과 실행 상태를 확인하는 근거로 모았습니다.",
        groups.execution,
      );
      [coreSection, executionSection].filter(Boolean).forEach((section) => {
        container.append(section);
      });
      if (!container.childElementCount && !invalidRange) {
        container.append(
          createElement(
            "p",
            "signal-index-empty",
            "선택한 감지일 범위에 해당하는 Signal이 없습니다.",
          ),
        );
      }
    };
    const filter = createDateFilter(render);
    wrapper.append(filter.toolbar, container);
    render("", "");
    if (container.querySelectorAll(".signal-index-row").length !== sourceRows.length) {
      return false;
    }
    tableHost(table).replaceWith(wrapper);
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
    document.querySelectorAll("template[data-signal-ui]").forEach((container) => {
      if (container.dataset.signalUiEnhanced === "true") return;
      let payload;
      try {
        payload = JSON.parse(container.content.textContent);
      } catch (_error) {
        return;
      }
      const enhanced =
        payload.kind === "index"
          ? enhanceIndex(container, payload)
          : payload.kind === "detail"
            ? enhanceDetail(container, payload)
            : false;
      if (enhanced) container.dataset.signalUiEnhanced = "true";
    });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enhanceSignals, { once: true });
  } else {
    enhanceSignals();
  }
  if (typeof document$ !== "undefined") document$.subscribe(enhanceSignals);
})();
