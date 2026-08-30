(() => {
  "use strict";

  const KIND_LABELS = {
    verified: "확인값",
    derived: "공개자료 역산",
  };

  function visibleKindLabel(variable) {
    if (variable.kind === "assumption") return "";
    return KIND_LABELS[variable.kind] || "";
  }
  const CONFIDENCE_LABELS = {
    high: "높음",
    medium: "중간",
    low: "낮음",
  };

  function element(tagName, className, text) {
    const node = document.createElement(tagName);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function evaluate(expression, values) {
    if (typeof expression === "number") return expression;
    if (!expression || typeof expression !== "object") {
      throw new Error("잘못된 계산식입니다.");
    }
    if (typeof expression.var === "string") {
      const value = Number(values[expression.var]);
      if (!Number.isFinite(value)) throw new Error("입력값을 확인해 주세요.");
      return value;
    }
    const args = (expression.args || []).map((item) => evaluate(item, values));
    switch (expression.op) {
      case "add":
        return args.reduce((total, value) => total + value, 0);
      case "subtract":
        return args[0] - args[1];
      case "multiply":
        return args.reduce((total, value) => total * value, 1);
      case "divide":
        if (args[1] === 0) throw new Error("0으로 나눌 수 없습니다.");
        return args[0] / args[1];
      case "negate":
        return -args[0];
      default:
        throw new Error("지원하지 않는 계산식입니다.");
    }
  }

  function formatNumber(value, decimals = 0, showSign = false) {
    const options = {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    };
    const absolute = Math.abs(value).toLocaleString("ko-KR", options);
    if (!showSign || value === 0) return value < 0 ? `−${absolute}` : absolute;
    return `${value > 0 ? "+" : "−"}${absolute}`;
  }

  function clamp(value, variable) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return Number(variable.default);
    return Math.min(Number(variable.max), Math.max(Number(variable.min), numeric));
  }

  function primaryOutput(model) {
    return model.outputs.find((output) => output.primary) || model.outputs[0];
  }

  function dominantVariable(model, values) {
    const primary = primaryOutput(model);
    const base = evaluate(primary.expression, values);
    let dominant = null;
    let maximumDelta = -1;
    for (const variable of model.variables) {
      const span = Number(variable.max) - Number(variable.min);
      const nextValue = Math.min(Number(variable.max), Number(values[variable.id]) + span * 0.1);
      if (nextValue === Number(values[variable.id])) continue;
      const changed = { ...values, [variable.id]: nextValue };
      const delta = Math.abs(evaluate(primary.expression, changed) - base);
      if (delta > maximumDelta) {
        maximumDelta = delta;
        dominant = variable;
      }
    }
    return dominant;
  }

  function buildSimulator(model) {
    const values = Object.fromEntries(
      model.variables.map((variable) => [variable.id, Number(variable.default)]),
    );
    const controls = new Map();
    const outputValues = new Map();
    const card = element("section", "impact-simulator-card");
    card.dataset.enhanced = "true";

    const header = element("header", "impact-simulator-header");
    const headingWrap = element("div", "impact-simulator-heading");
    headingWrap.append(
      element("span", "impact-simulator-eyebrow", "WHAT-IF · AI 예비 추정"),
      element("h3", "impact-simulator-title", model.title),
      element("p", "impact-simulator-description", model.description),
    );
    const meta = element("div", "impact-simulator-meta");
    meta.append(
      element(
        "span",
        `impact-confidence is-${model.confidence}`,
        `신뢰도 ${CONFIDENCE_LABELS[model.confidence] || model.confidence}`,
      ),
      element("span", "impact-as-of", `기준 ${model.as_of}`),
    );
    header.append(headingWrap, meta);

    const results = element("div", "impact-results");
    for (const output of model.outputs) {
      const item = element(
        "div",
        `impact-result${output.primary ? " is-primary" : ""}`,
      );
      const label = element("span", "impact-result-label", output.label);
      const value = element("strong", "impact-result-value");
      const unit = element("span", "impact-result-unit", output.unit);
      item.append(label, value, unit);
      results.append(item);
      outputValues.set(output.id, value);
    }
    const presetComparison = element("section", "impact-preset-comparison");
    presetComparison.setAttribute("aria-label", "프리셋 결과 비교");
    presetComparison.append(
      element("span", "impact-preset-comparison-title", "프리셋 결과"),
    );
    const presetComparisonGrid = element("div", "impact-preset-comparison-grid");
    const primary = primaryOutput(model);
    for (const preset of model.presets) {
      const presetValues = {
        ...Object.fromEntries(
          model.variables.map((variable) => [variable.id, Number(variable.default)]),
        ),
        ...preset.values,
      };
      const item = element("div", "impact-preset-result");
      const label = element("span", "impact-preset-result-label", preset.label);
      const value = element(
        "strong",
        "impact-preset-result-value",
        formatNumber(
          evaluate(primary.expression, presetValues),
          Number(primary.decimals || 0),
          Boolean(primary.show_sign),
        ),
      );
      item.append(label, value, element("span", "impact-preset-result-unit", primary.unit));
      presetComparisonGrid.append(item);
    }
    presetComparison.append(presetComparisonGrid);
    const driver = element("p", "impact-dominant-driver");

    const toolbar = element("div", "impact-toolbar");
    const presetGroup = element("div", "impact-presets");
    presetGroup.setAttribute("aria-label", "시나리오 선택");
    for (const preset of model.presets) {
      const shortLabel = String(preset.label).replace(/\s*시나리오$/u, "");
      const button = element("button", "impact-preset", shortLabel);
      button.type = "button";
      button.setAttribute("aria-label", preset.label);
      button.title = preset.label;
      button.addEventListener("click", () => {
        Object.assign(values, preset.values);
        for (const variable of model.variables) {
          const control = controls.get(variable.id);
          control.range.value = String(values[variable.id]);
          control.number.value = String(values[variable.id]);
        }
        presetGroup.querySelectorAll("button").forEach((item) => {
          item.classList.toggle("is-active", item === button);
        });
        update();
      });
      presetGroup.append(button);
    }
    const reset = element("button", "impact-reset", "초기화");
    reset.type = "button";
    reset.setAttribute("aria-label", "기본값으로 초기화");
    reset.addEventListener("click", () => {
      for (const variable of model.variables) {
        values[variable.id] = Number(variable.default);
        const control = controls.get(variable.id);
        control.range.value = String(values[variable.id]);
        control.number.value = String(values[variable.id]);
      }
      presetGroup.querySelectorAll("button").forEach((item) => item.classList.remove("is-active"));
      update();
    });
    toolbar.append(presetGroup, reset);
    const controlStrip = element("div", "impact-control-strip");
    controlStrip.append(driver, toolbar);

    const inputGrid = element("div", "impact-input-grid");
    for (const variable of model.variables) {
      const field = element("div", "impact-input");
      const labelRow = element("div", "impact-input-label-row");
      const label = element("label", "impact-input-label", variable.label);
      const inputId = `impact-${Math.random().toString(36).slice(2)}-${variable.id}`;
      label.htmlFor = inputId;
      labelRow.append(label);
      const kindLabel = visibleKindLabel(variable);
      if (kindLabel) {
        labelRow.append(
          element(
            "span",
            `impact-input-kind is-${variable.kind}`,
            kindLabel,
          ),
        );
      }

      const controlRow = element("div", "impact-input-control");
      const range = document.createElement("input");
      range.type = "range";
      range.id = inputId;
      range.min = String(variable.min);
      range.max = String(variable.max);
      range.step = String(variable.step);
      range.value = String(variable.default);
      range.setAttribute("aria-label", `${variable.label} 슬라이더`);
      const numberWrap = element("div", "impact-number-wrap");
      const number = document.createElement("input");
      number.type = "number";
      number.min = String(variable.min);
      number.max = String(variable.max);
      number.step = String(variable.step);
      number.value = String(variable.default);
      number.setAttribute("aria-label", `${variable.label} 직접 입력`);
      numberWrap.append(number, element("span", "impact-input-unit", variable.unit));
      const sync = (rawValue) => {
        values[variable.id] = clamp(rawValue, variable);
        range.value = String(values[variable.id]);
        number.value = String(values[variable.id]);
        presetGroup.querySelectorAll("button").forEach((item) => item.classList.remove("is-active"));
        update();
      };
      range.addEventListener("input", () => sync(range.value));
      number.addEventListener("input", () => {
        if (number.value !== "") sync(number.value);
      });
      number.addEventListener("change", () => sync(number.value));
      controlRow.append(range, numberWrap);
      field.append(
        labelRow,
        controlRow,
        element("p", "impact-input-basis", variable.basis),
      );
      inputGrid.append(field);
      controls.set(variable.id, { range, number });
    }

    const details = element("details", "impact-method");
    const summary = element("summary", "", "산식·입력 근거 보기");
    const formula = element("div", "impact-formula");
    formula.append(
      element("strong", "", "계산식"),
      element("code", "", model.formula_display),
      element("p", "", model.notice),
    );
    details.append(summary, formula);

    const error = element("p", "impact-error");
    error.hidden = true;
    card.append(header, results, presetComparison, controlStrip, inputGrid, details, error);

    function update() {
      try {
        for (const output of model.outputs) {
          const result = evaluate(output.expression, values);
          outputValues.get(output.id).textContent = formatNumber(
            result,
            Number(output.decimals || 0),
            Boolean(output.show_sign),
          );
        }
        const dominant = dominantVariable(model, values);
        driver.textContent = dominant
          ? `현재 결과를 가장 크게 좌우하는 변수: ${dominant.label}`
          : "현재 조건에서 단일 지배변수를 식별할 수 없습니다.";
        error.hidden = true;
      } catch (caught) {
        error.textContent = caught instanceof Error ? caught.message : "계산할 수 없습니다.";
        error.hidden = false;
      }
    }

    update();
    return card;
  }

  function enhanceImpactSimulators() {
    document.querySelectorAll(".impact-simulator-data").forEach((container) => {
      if (container.dataset.impactProcessed === "true") return;
      container.dataset.impactProcessed = "true";
      try {
        const model = JSON.parse(container.textContent || "{}");
        container.replaceWith(buildSimulator(model));
      } catch (caught) {
        container.classList.add("impact-simulator-failed");
        container.setAttribute("role", "alert");
        container.textContent = "영향 시뮬레이터 데이터를 읽지 못했습니다.";
      }
    });
  }

  let enhancementScheduled = false;

  function scheduleImpactEnhancement() {
    if (enhancementScheduled) return;
    enhancementScheduled = true;
    requestAnimationFrame(() => {
      enhancementScheduled = false;
      enhanceImpactSimulators();
    });
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(scheduleImpactEnhancement);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scheduleImpactEnhancement);
  } else {
    scheduleImpactEnhancement();
  }

  new MutationObserver(scheduleImpactEnhancement).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
})();
