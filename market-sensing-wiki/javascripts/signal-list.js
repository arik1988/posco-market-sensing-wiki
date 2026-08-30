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
    pills.setAttribute("aria-label", "회사, 사업축과 변화 유형");

    if (item.company) {
      pills.append(createElement("span", "signal-pill signal-pill-company", item.company));
    }
    if (item.business_axis) {
      pills.append(createElement("span", "signal-pill signal-pill-axis", item.business_axis));
    }
    if (item.signal_type) {
      pills.append(createElement("span", "signal-pill signal-pill-type", item.signal_type));
    }
    if (pills.childElementCount) context.append(pills);

    const text = createElement("div", "signal-context-text");
    appendContextText(text, "국가·지역", item.region);
    if (text.childElementCount) context.append(text);
    return context;
  };

  let scoreRationaleId = 0;

  let activeScoreRationale = null;

  const hideScoreRationale = (tooltip = activeScoreRationale) => {
    if (!tooltip) return;
    tooltip.hidden = true;
    if (activeScoreRationale === tooltip) activeScoreRationale = null;
  };

  const showScoreRationale = (group, tooltip) => {
    if (activeScoreRationale && activeScoreRationale !== tooltip) {
      hideScoreRationale(activeScoreRationale);
    }
    tooltip.hidden = false;

    const anchor = group.getBoundingClientRect();
    const tooltipBox = tooltip.getBoundingClientRect();
    const viewportPadding = 12;
    const gap = 8;
    const leftAligned = anchor.left;
    const rightAligned = anchor.right - tooltipBox.width;
    const left = Math.min(
      Math.max(
        leftAligned + tooltipBox.width <= window.innerWidth - viewportPadding
          ? leftAligned
          : rightAligned,
        viewportPadding,
      ),
      window.innerWidth - tooltipBox.width - viewportPadding,
    );
    const below = anchor.bottom + gap;
    const above = anchor.top - tooltipBox.height - gap;
    const top =
      below + tooltipBox.height <= window.innerHeight - viewportPadding
        ? below
        : Math.max(above, viewportPadding);

    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
    activeScoreRationale = tooltip;
  };

  const bindScoreRationale = (group, tooltip) => {
    group.addEventListener("mouseenter", () => showScoreRationale(group, tooltip));
    group.addEventListener("focus", () => showScoreRationale(group, tooltip));
    group.addEventListener("mouseleave", () => hideScoreRationale(tooltip));
    group.addEventListener("blur", () => hideScoreRationale(tooltip));
    group.addEventListener("keydown", (event) => {
      if (event.key === "Escape") hideScoreRationale(tooltip);
    });
  };

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
      tooltip.hidden = true;
      document.body.append(tooltip);
      bindScoreRationale(group, tooltip);
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

  const itemCompanies = (item) => {
    if (Array.isArray(item.companies)) {
      return item.companies.map((value) => String(value).trim()).filter(Boolean);
    }
    return item.company ? [String(item.company).trim()] : [];
  };

  const sortedUnique = (values) =>
    Array.from(new Set(values.filter(Boolean))).sort((left, right) =>
      left.localeCompare(right, "ko"),
    );

  const signalIdFromHref = (href) => {
    try {
      const path = new URL(href, document.baseURI).pathname;
      return path.match(/\/signals\/(SIG-[A-Z0-9]+)\/?$/)?.[1] || "";
    } catch (_error) {
      return "";
    }
  };

  const updateSidebarSignalNavigation = (visibleEntries = null) => {
    const visibleSignalIds =
      visibleEntries === null
        ? null
        : new Set(
            visibleEntries
              .map(({ sourceRow }) =>
                signalIdFromHref(
                  sourceRow.querySelector('a[href*="SIG-"]')?.href || "",
                ),
              )
              .filter(Boolean),
          );

    document
      .querySelectorAll('.md-sidebar--primary a[href*="signals/SIG-"]')
      .forEach((link) => {
        const signalId = signalIdFromHref(link.href);
        const item = link.closest(".md-nav__item");
        if (!signalId || !item) return;
        item.hidden = visibleSignalIds !== null && !visibleSignalIds.has(signalId);
      });
  };

  const createSignalFilter = (entries, onChange) => {
    const toolbar = createElement("section", "signal-index-toolbar");
    toolbar.setAttribute("aria-label", "마켓 시그널 필터");

    const controls = createElement("div", "signal-filter-controls");
    const classification = createElement("div", "signal-classification-filter");

    const createSelectField = (labelText, ariaLabel, allLabel) => {
      const label = createElement("label", "signal-select-field");
      label.append(createElement("span", "", labelText));
      const select = createElement("select");
      select.setAttribute("aria-label", ariaLabel);
      select.append(new Option(allLabel, ""));
      label.append(select);
      return { label, select, allLabel };
    };
    const company = createSelectField("회사", "회사 필터", "전체 회사");
    const axis = createSelectField("사업축", "사업축 필터", "전체 사업축");
    sortedUnique(entries.flatMap(({ item }) => itemCompanies(item))).forEach((value) => {
      company.select.append(new Option(value, value));
    });
    const updateAxisOptions = () => {
      const previous = axis.select.value;
      const available = sortedUnique(
        entries
          .filter(({ item }) =>
            !company.select.value || itemCompanies(item).includes(company.select.value),
          )
          .map(({ item }) => String(item.business_axis || "").trim()),
      );
      axis.select.replaceChildren(new Option(axis.allLabel, ""));
      available.forEach((value) => axis.select.append(new Option(value, value)));
      axis.select.value = available.includes(previous) ? previous : "";
    };
    updateAxisOptions();
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
    const detectedDates = sortedUnique(
      entries.map(({ item }) => String(item.detected_at || "").trim()),
    );
    if (detectedDates.length) {
      [from.input, to.input].forEach((input) => {
        input.min = detectedDates[0];
        input.max = detectedDates[detectedDates.length - 1];
      });
    }
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
        dateReset.setAttribute("aria-pressed", "false");
        onChange({
          company: company.select.value,
          businessAxis: axis.select.value,
          from: from.input.value,
          to: to.input.value,
        });
      });
      presetButtons.push(button);
      presets.append(button);
    });
    const dateReset = createElement("button", "signal-date-reset", "날짜 전체");
    dateReset.type = "button";
    dateReset.setAttribute("aria-pressed", "true");
    dateReset.addEventListener("click", () => {
      from.input.value = "";
      to.input.value = "";
      presetButtons.forEach((button) => button.setAttribute("aria-pressed", "false"));
      dateReset.setAttribute("aria-pressed", "true");
      onChange({
        company: company.select.value,
        businessAxis: axis.select.value,
        from: "",
        to: "",
      });
    });
    presets.append(dateReset);
    filter.append(presets);

    const resetAll = createElement("button", "signal-filter-reset", "필터 초기화");
    resetAll.type = "button";
    resetAll.addEventListener("click", () => {
      company.select.value = "";
      updateAxisOptions();
      from.input.value = "";
      to.input.value = "";
      presetButtons.forEach((button) => button.setAttribute("aria-pressed", "false"));
      dateReset.setAttribute("aria-pressed", "true");
      onChange({ company: "", businessAxis: "", from: "", to: "" });
    });
    classification.append(company.label, axis.label, resetAll);

    const status = createElement("div", "signal-filter-status");
    const summary = createElement("span", "signal-filter-summary");
    summary.setAttribute("aria-live", "polite");
    const error = createElement("span", "signal-filter-error");
    error.setAttribute("role", "alert");
    status.append(summary, error);
    controls.append(classification, filter);
    toolbar.append(controls, status);

    const notify = () => {
      onChange({
        company: company.select.value,
        businessAxis: axis.select.value,
        from: from.input.value,
        to: to.input.value,
      });
    };
    const manualDateChange = () => {
      presetButtons.forEach((button) => button.setAttribute("aria-pressed", "false"));
      dateReset.setAttribute("aria-pressed", "false");
      notify();
    };
    ["input", "change"].forEach((eventName) => {
      from.input.addEventListener(eventName, manualDateChange);
      to.input.addEventListener(eventName, manualDateChange);
    });
    company.select.addEventListener("change", () => {
      updateAxisOptions();
      notify();
    });
    axis.select.addEventListener("change", notify);

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

    const render = ({ company = "", businessAxis = "", from = "", to = "" }) => {
      container.replaceChildren();
      filter.error.textContent = "";
      const invalidRange = from && to && from > to;
      const visible = invalidRange
        ? []
        : entries.filter(({ item }) => {
            if (company && !itemCompanies(item).includes(company)) return false;
            if (businessAxis && item.business_axis !== businessAxis) return false;
            const detectedAt = item.detected_at || "";
            if (!detectedAt) return !from && !to;
            return (!from || detectedAt >= from) && (!to || detectedAt <= to);
          });
      if (invalidRange) {
        filter.error.textContent = "시작일은 종료일보다 늦을 수 없습니다.";
      }
      filter.summary.textContent = `전체 ${entries.length}건 중 ${visible.length}건`;
      updateSidebarSignalNavigation(visible);

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
            "선택한 필터 조건에 해당하는 Signal이 없습니다.",
          ),
        );
      }
    };
    const filter = createSignalFilter(entries, render);
    wrapper.append(filter.toolbar, container);
    render({});
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
      return ["사업영향도", "긴급도", "평가일"].every((label) =>
        headers.includes(label),
      );
    });

  const findSignalSentence = (scope) =>
    Array.from(scope.querySelectorAll(".admonition.abstract")).find((admonition) =>
      admonition.querySelector(".admonition-title")?.textContent.includes("한 문장"),
    );

  const enhanceDetail = (script, payload) => {
    updateSidebarSignalNavigation();
    const scope = script.closest(".md-content__inner") || document;
    if (scope.querySelector(".signal-detail-context")) return true;
    const item = payload.item;
    const title = scope.querySelector("h1");
    if (!item || !title) return false;

    title.classList.add("signal-detail-title");
    if (item.title) title.textContent = item.title;
    if (!scope.querySelector(".signal-static-pills")) {
      title.before(createContext(item, true));
    }

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
  window.addEventListener("scroll", () => hideScoreRationale(), true);
  window.addEventListener("resize", () => hideScoreRationale());
})();
