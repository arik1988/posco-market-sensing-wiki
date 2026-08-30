(() => {
  const API = "http://127.0.0.1:8201";
  const companies = [
    ["POSCO", "포스코", "철강"],
    ["POSCO Holdings", "포스코홀딩스", "리튬·전략광물"],
    ["POSCO International", "포스코인터내셔널", "에너지·식량·팜"],
    ["POSCO E&C", "포스코이앤씨", "건설·인프라"],
    ["POSCO Future M", "포스코퓨처엠", "이차전지소재"],
    ["POSCO Flow", "포스코플로우", "철강·원료 물류"],
    ["POSCO Mobility Solution", "포스코모빌리티솔루션", "구동모터코아·강건재가공"],
    ["POSCO Steeleon", "포스코스틸리온", "도금·컬러강판"],
  ];
  const weekdayLabels = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"];
  const codexModelLabels = {
    "gpt-5.6-sol": "GPT-5.6-Sol",
    "gpt-5.6-terra": "GPT-5.6-Terra",
    "gpt-5.6-luna": "GPT-5.6-Luna",
  };
  const codexEffortLabels = { light: "Light", medium: "Medium", high: "High" };

  const el = (tag, attrs = {}, children = []) => {
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([key, value]) => {
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else if (key === "checked") node.checked = Boolean(value);
      else if (key === "disabled") node.disabled = Boolean(value);
      else if (key === "hidden") node.hidden = Boolean(value);
      else if (key === "value") node.value = value;
      else node.setAttribute(key, value);
    });
    (Array.isArray(children) ? children : [children]).forEach((child) => {
      if (child) node.append(child);
    });
    return node;
  };

  const input = (attrs) => el("input", attrs);
  const localDate = (value = new Date()) => {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  };
  const daysAgo = (days) => {
    const value = new Date();
    value.setDate(value.getDate() - days);
    return localDate(value);
  };
  const option = (value, label) => el("option", { value, text: label });

  function providerCard(id, title, purpose, description, checked) {
    const radio = input({ type: "radio", name: "provider", value: id, checked });
    return el("label", { class: "research-provider-card" }, [
      radio,
      el("span", { class: "research-provider-copy" }, [
        el("strong", { text: title }),
        el("span", { class: "research-provider-purpose", text: purpose }),
        el("small", { text: description }),
        el("span", { class: "research-provider-readiness", "data-provider-state": id, text: "상태 확인 중" }),
      ]),
    ]);
  }

  function requestPayload(root, controls) {
    const companyAxes = [...root.querySelectorAll(".research-company-option")]
      .filter((card) => card.querySelector('input[name="company-scope"]')?.checked)
      .map((card) => ({
        company: card.querySelector('input[name="company-name"]')?.value.trim() || "",
        business_axis: card.querySelector('input[name="business-axis"]')?.value.trim() || "",
      }));
    return {
      topic: controls.topic.value.trim(),
      topic_company: controls.topicCompany.value.trim(),
      company_axes: companyAxes,
      companies: companyAxes.map((item) => item.company),
      date_from: controls.start.value,
      date_to: controls.end.value,
      provider: root.querySelector('input[name="provider"]:checked')?.value || "pgpt",
      codex_model: controls.codexModel.value,
      codex_effort: controls.codexEffort.value,
      publish: controls.publish.checked,
    };
  }

  function responseMessage(data, fallback) {
    return data?.message || data?.error?.message || (typeof data?.error === "string" ? data.error : "") || fallback;
  }

  function setStatus(target, title, message, state = "idle") {
    target.dataset.state = state;
    target.querySelector("strong").textContent = title;
    target.querySelector("p").textContent = message;
  }

  function scheduleSummary(schedule) {
    if (schedule.frequency === "daily") return `매일 ${schedule.run_time}`;
    if (schedule.frequency === "weekly") return `매주 ${weekdayLabels[schedule.weekday]} ${schedule.run_time}`;
    return `매월 ${schedule.day_of_month}일 ${schedule.run_time}`;
  }

  function dateTimeLabel(value) {
    if (!value) return "예정 없음";
    return new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul", dateStyle: "medium", timeStyle: "short",
    }).format(new Date(value));
  }

  async function api(path, options = {}) {
    const response = await fetch(`${API}${path}`, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(responseMessage(data, "요청을 처리하지 못했습니다."));
    return data;
  }

  async function refreshSchedules(list, empty) {
    try {
      const data = await api("/api/research/schedules");
      list.replaceChildren();
      empty.textContent = "저장된 반복 일정이 없습니다.";
      empty.hidden = data.schedules.length > 0;
      empty.dataset.state = "";
      data.schedules.forEach((schedule) => {
        const toggle = input({ type: "checkbox", checked: schedule.enabled });
        toggle.setAttribute("aria-label", `${schedule.name} 활성화`);
        toggle.addEventListener("change", async () => {
          toggle.disabled = true;
          try {
            await api(`/api/research/schedules/${schedule.schedule_id}`, {
              method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: toggle.checked }),
            });
          } catch (error) {
            toggle.checked = !toggle.checked;
            window.alert(error.message);
          } finally {
            toggle.disabled = false;
          }
        });
        const remove = el("button", { type: "button", class: "research-icon-button", text: "삭제", "aria-label": `${schedule.name} 일정 삭제` });
        remove.addEventListener("click", async () => {
          remove.disabled = true;
          try {
            await api(`/api/research/schedules/${schedule.schedule_id}`, { method: "DELETE" });
            await refreshSchedules(list, empty);
          } catch (error) {
            window.alert(error.message);
            remove.disabled = false;
          }
        });
        list.append(el("article", { class: "research-schedule-card" }, [
          el("div", { class: "research-schedule-heading" }, [toggle, el("strong", { text: schedule.name }), remove]),
          el("p", { text: schedule.topic }),
          el("div", { class: "research-schedule-meta" }, [
            el("span", { text: `${schedule.topic_company || schedule.companies[0]} 중심` }),
            el("span", { text: scheduleSummary(schedule) }),
            el("span", { text: `최근 ${schedule.lookback_days}일 재탐색` }),
            el("span", { text: `${(schedule.company_axes || schedule.companies).length}개 회사·사업축` }),
            ...(schedule.provider === "codex" ? [
              el("span", { text: codexModelLabels[schedule.codex_model] || schedule.codex_model }),
              el("span", { text: `${codexEffortLabels[schedule.codex_effort] || schedule.codex_effort} effort` }),
            ] : []),
            el("span", { text: schedule.publish ? "SQLite 발행" : "읽기 전용" }),
          ]),
          el("small", { text: `다음 실행 ${dateTimeLabel(schedule.next_run_at)}` }),
        ]));
      });
    } catch (error) {
      list.replaceChildren();
      empty.hidden = false;
      empty.textContent = `일정 API를 사용할 수 없습니다. 조사 서버를 다시 시작해 주세요. (${error.message})`;
      empty.dataset.state = "failed";
    }
  }

  function mount(root) {
    if (root.dataset.mounted === "true") return;
    root.dataset.mounted = "true";
    const article = root.closest("article");
    if (article) article.classList.add("research-agent-page");

    const topic = el("textarea", {
      id: "research-topic", rows: "4", required: "required",
      "aria-label": "조사 주제 직접 입력",
      placeholder: "예: 최근 2주간 철강 수입규제와 원료 가격 변화가 POSCO 사업 판단에 미치는 영향",
    });
    const topicCompany = input({
      type: "text", id: "research-topic-company", required: "required", maxlength: "120",
      list: "research-company-suggestions", "aria-label": "조사 주제 대상 회사 직접 입력",
      placeholder: "예: POSCO",
    });
    const companySuggestions = el("datalist", { id: "research-company-suggestions" },
      companies.map(([name, label]) => el("option", { value: name, label }))
    );
    const companyGrid = el("div", { class: "research-company-grid" });
    const selectionCount = el("span", { class: "research-selection-count" });
    const updateSelectionCount = () => {
      const total = companyGrid.querySelectorAll(".research-company-option").length;
      const count = companyGrid.querySelectorAll('input[name="company-scope"]:checked').length;
      selectionCount.textContent = `${count}/${total}개 범위 사용`;
    };

    const addCompanyScope = (name = "", label = "직접 추가한 범위", axis = "", checked = true) => {
      const checkbox = input({ type: "checkbox", name: "company-scope", checked, "aria-label": `${label} 조사 범위 사용` });
      checkbox.addEventListener("change", updateSelectionCount);
      const companyName = input({ type: "text", name: "company-name", value: name, maxlength: "120", placeholder: "예: POSCO 또는 포스코" });
      const businessAxis = input({ type: "text", name: "business-axis", value: axis, maxlength: "160", placeholder: "예: 철강·원료" });
      const remove = el("button", { type: "button", class: "research-icon-button", text: "삭제", "aria-label": `${label} 조사 범위 삭제` });
      const card = el("article", { class: "research-company-option" }, [
        el("div", { class: "research-company-option-heading" }, [
          el("label", {}, [checkbox, el("strong", { text: label })]), remove,
        ]),
        el("div", { class: "research-company-edit-grid" }, [
          el("label", { class: "research-field" }, [el("span", { text: "회사명" }), companyName]),
          el("label", { class: "research-field" }, [el("span", { text: "조사 사업축·주제" }), businessAxis]),
        ]),
      ]);
      remove.addEventListener("click", () => { card.remove(); updateSelectionCount(); });
      companyGrid.append(card);
      updateSelectionCount();
      if (!name) companyName.focus();
    };
    companies.forEach(([name, label, axis]) => addCompanyScope(name, label, axis));
    updateSelectionCount();
    const allCompanies = el("button", { type: "button", class: "research-text-button", text: "전체 선택" });
    const clearCompanies = el("button", { type: "button", class: "research-text-button", text: "전체 해제" });
    const addCompany = el("button", { type: "button", class: "research-add-scope-button", text: "+ 회사·조사 주제 추가" });
    allCompanies.addEventListener("click", () => {
      companyGrid.querySelectorAll('input[name="company-scope"]').forEach((node) => { node.checked = true; }); updateSelectionCount();
    });
    clearCompanies.addEventListener("click", () => {
      companyGrid.querySelectorAll('input[name="company-scope"]').forEach((node) => { node.checked = false; }); updateSelectionCount();
    });
    addCompany.addEventListener("click", () => addCompanyScope());

    const start = input({ type: "date", id: "research-date-from", value: daysAgo(13) });
    const end = input({ type: "date", id: "research-date-to", value: localDate() });
    const publish = input({ type: "checkbox", id: "research-publish", checked: true });
    const codexModel = el("select", { id: "research-codex-model", "aria-label": "Codex 모델" }, [
      option("gpt-5.6-sol", "GPT-5.6-Sol"),
      option("gpt-5.6-terra", "GPT-5.6-Terra"),
      option("gpt-5.6-luna", "GPT-5.6-Luna"),
    ]);
    codexModel.value = "gpt-5.6-luna";
    const codexEffort = el("select", { id: "research-codex-effort", "aria-label": "Codex effort" }, [
      option("light", "Light"), option("medium", "Medium"), option("high", "High"),
    ]);
    codexEffort.value = "medium";
    const codexOptions = el("div", { class: "research-codex-options" }, [
      el("label", { class: "research-field" }, [el("span", { text: "모델" }), codexModel]),
      el("label", { class: "research-field" }, [el("span", { text: "Effort" }), codexEffort]),
      el("small", { text: "Codex OAuth를 선택했을 때 적용됩니다." }),
    ]);
    const updateCodexOptions = () => {
      const enabled = root.querySelector('input[name="provider"]:checked')?.value === "codex";
      codexOptions.dataset.enabled = enabled ? "true" : "false";
      codexModel.disabled = !enabled;
      codexEffort.disabled = !enabled;
    };
    const runButton = el("button", { type: "submit", class: "research-submit", text: "지금 조사 시작" });
    const status = el("section", { class: "research-status", "aria-live": "polite" }, [
      el("strong", { text: "실행 대기" }), el("p", { text: "범위를 설정한 뒤 지금 조사하거나 반복 일정을 저장해 주세요." }),
    ]);
    const output = el("pre", { class: "research-output", hidden: true });
    const serverState = el("div", { class: "research-server-state", "aria-live": "polite" }, [
      el("span", { class: "research-state-dot" }), el("strong", { text: "조사 서버 확인 중" }), el("span", { text: "설정 UI는 서버 상태와 관계없이 사용할 수 있습니다." }),
    ]);

    const frequency = el("select", { id: "research-frequency" }, [option("daily", "매일"), option("weekly", "매주"), option("monthly", "매월")]);
    const runTime = input({ type: "time", id: "research-run-time", value: "09:00" });
    const weekday = el("select", { id: "research-weekday" }, weekdayLabels.map((label, index) => option(String(index), label)));
    const dayOfMonth = el("select", { id: "research-day-of-month" }, Array.from({ length: 28 }, (_, index) => option(String(index + 1), `${index + 1}일`)));
    const lookbackDays = input({ type: "number", id: "research-lookback-days", value: "14", min: "1", max: "366" });
    const weekdayField = el("label", { class: "research-field", hidden: true }, [el("span", { text: "실행 요일" }), weekday]);
    const monthlyField = el("label", { class: "research-field", hidden: true }, [el("span", { text: "실행일" }), dayOfMonth]);
    const updateFrequency = () => {
      weekdayField.hidden = frequency.value !== "weekly";
      monthlyField.hidden = frequency.value !== "monthly";
    };
    frequency.addEventListener("change", updateFrequency);
    updateFrequency();

    const scheduleList = el("div", { class: "research-schedule-list" });
    const scheduleEmpty = el("p", { class: "research-schedule-empty", text: "저장된 반복 일정이 없습니다." });
    const saveSchedule = el("button", { type: "button", class: "research-secondary-button", text: "반복 조사 저장" });

    const form = el("form", { class: "research-form" }, [
      el("section", { class: "research-panel research-panel-lead" }, [
        el("div", { class: "research-eyebrow", text: "MARKET RESEARCH CONTROL" }),
        el("h2", { text: "조사 범위를 정하고 바로 실행합니다" }),
        el("p", { text: "회사·사업축과 조사 주제를 직접 정해 즉시 조사하거나, 같은 범위를 정기적으로 다시 확인하도록 예약할 수 있습니다." }),
      ]),
      serverState,
      el("section", { class: "research-panel" }, [
        el("div", { class: "research-section-heading" }, [
          el("div", {}, [el("h3", { text: "1. 대상 회사와 조사 주제" }), el("p", { class: "research-help", text: "이번 주제가 어느 회사를 위한 조사인지 회사와 외부 변화·사업 판단을 함께 입력해 주세요." })]),
          el("span", { class: "research-required", text: "필수" }),
        ]),
        el("div", { class: "research-topic-scope-grid" }, [
          el("label", { class: "research-topic-field" }, [el("span", { text: "대상 회사 직접 입력" }), topicCompany, companySuggestions]),
          el("label", { class: "research-topic-field" }, [el("span", { text: "조사 주제 직접 입력" }), topic]),
        ]),
      ]),
      el("section", { class: "research-panel" }, [
        el("div", { class: "research-section-heading" }, [
          el("div", {}, [el("h3", { text: "2. 추가 조사 범위" }), el("p", { class: "research-help", text: "1번 대상 회사를 포함해 함께 조사할 회사와 사업축을 선택·수정하거나 새로 추가할 수 있습니다." })]),
          el("div", { class: "research-company-actions" }, [selectionCount, allCompanies, clearCompanies]),
        ]), companyGrid, addCompany,
      ]),
      el("section", { class: "research-panel research-grid-two" }, [
        el("div", {}, [el("h3", { text: "3. 조사 기간" }), el("p", { class: "research-help", text: "즉시 실행에서 확인할 발표·사건 기간입니다." }), el("div", { class: "research-date-row" }, [start, el("span", { text: "—" }), end])]),
        el("div", {}, [el("h3", { text: "4. 저장 방식" }), el("p", { class: "research-help", text: "기본값은 검증된 결과를 단일 SQLite에 발행합니다." }), el("label", { class: "research-publish-option" }, [publish, el("span", {}, [el("strong", { text: "SQLite까지 완전 발행" }), el("small", { text: "Source → Claim → Signal → Insight와 감사를 완료합니다." })])])]),
      ]),
      el("section", { class: "research-panel" }, [
        el("h3", { text: "5. 실행 Provider" }), el("p", { class: "research-help", text: "검색과 SQLite 계약은 같고, 판단 모델의 연결 방식만 다릅니다." }),
        el("div", { class: "research-provider-grid" }, [providerCard("pgpt", "P-GPT", "실제 운영", "회사 API를 사용하는 기본 Provider", true), providerCard("codex", "Codex OAuth", "개발 검증", "로컬 ChatGPT OAuth로 기능 검증", false)]),
        codexOptions,
      ]),
      el("section", { class: "research-panel" }, [
        el("div", { class: "research-section-heading" }, [
          el("div", {}, [el("h3", { text: "6. 반복 조사 주기" }), el("p", { class: "research-help", text: "저장한 일정은 이 PC에서 조사 서버가 실행 중일 때 자동으로 시작됩니다. 기준 시간대는 Asia/Seoul입니다." })]),
          el("span", { class: "research-optional", text: "선택" }),
        ]),
        el("div", { class: "research-schedule-fields" }, [
          el("label", { class: "research-field" }, [el("span", { text: "실행 주기" }), frequency]), weekdayField, monthlyField,
          el("label", { class: "research-field" }, [el("span", { text: "실행 시각" }), runTime]),
          el("label", { class: "research-field" }, [el("span", { text: "매번 확인할 최근 기간" }), el("span", { class: "research-input-suffix" }, [lookbackDays, el("span", { text: "일" })])]),
        ]),
      ]),
      el("div", { class: "research-action-row" }, [runButton, saveSchedule, el("span", { text: "동시에 요청된 조사는 SQLite 충돌을 막기 위해 순서대로 실행됩니다." })]),
    ]);
    form.querySelectorAll('input[name="provider"]').forEach((radio) => radio.addEventListener("change", updateCodexOptions));
    updateCodexOptions();

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = requestPayload(root, { topic, topicCompany, start, end, publish, codexModel, codexEffort });
      if (!payload.topic || !payload.topic_company || payload.company_axes.length === 0 || payload.company_axes.some((item) => !item.company || !item.business_axis)) {
        setStatus(status, "입력 확인 필요", "대상 회사, 조사 주제와 사용할 회사·사업축을 빠짐없이 입력해 주세요.", "failed"); return;
      }
      if (!payload.company_axes.some((item) => item.company === payload.topic_company)) {
        setStatus(status, "입력 확인 필요", "1번 대상 회사를 2번 추가 조사 범위에도 포함해 주세요.", "failed"); return;
      }
      runButton.disabled = true;
      setStatus(status, "조사 요청 중", "Deep Agent 실행을 준비하고 있습니다.", "running"); output.hidden = true;
      try {
        const job = await api("/api/research/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        await poll(job.run_id, status, output);
      } catch (error) {
        setStatus(status, "조사를 시작하지 못했습니다", error.message, "failed");
      } finally { runButton.disabled = false; }
    });

    saveSchedule.addEventListener("click", async () => {
      const payload = requestPayload(root, { topic, topicCompany, start, end, publish, codexModel, codexEffort });
      if (!payload.topic || !payload.topic_company || payload.company_axes.length === 0 || payload.company_axes.some((item) => !item.company || !item.business_axis)) {
        setStatus(status, "입력 확인 필요", "반복 일정에도 대상 회사, 조사 주제와 사용할 회사·사업축이 필요합니다.", "failed"); return;
      }
      if (!payload.company_axes.some((item) => item.company === payload.topic_company)) {
        setStatus(status, "입력 확인 필요", "1번 대상 회사를 2번 추가 조사 범위에도 포함해 주세요.", "failed"); return;
      }
      const range = Math.round((new Date(payload.date_to) - new Date(payload.date_from)) / 86400000) + 1;
      Object.assign(payload, { frequency: frequency.value, run_time: runTime.value, weekday: Number(weekday.value), day_of_month: Number(dayOfMonth.value), lookback_days: Math.max(1, range) });
      saveSchedule.disabled = true;
      try {
        const schedule = await api("/api/research/schedules", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        setStatus(status, "반복 조사 저장 완료", `${scheduleSummary(schedule)} 일정으로 저장했습니다.`, "completed");
        await refreshSchedules(scheduleList, scheduleEmpty);
      } catch (error) {
        setStatus(status, "일정을 저장하지 못했습니다", error.message, "failed");
      } finally { saveSchedule.disabled = false; }
    });

    root.replaceChildren(form, status, output, el("section", { class: "research-panel research-saved-panel" }, [
      el("div", { class: "research-section-heading" }, [
        el("div", {}, [el("h2", { text: "저장된 반복 조사" }), el("p", { class: "research-help", text: "활성화된 일정만 자동 실행되며, 필요하면 일시정지하거나 삭제할 수 있습니다." })]),
        el("button", { type: "button", class: "research-text-button", text: "새로고침", onclick: () => refreshSchedules(scheduleList, scheduleEmpty) }),
      ]), scheduleEmpty, scheduleList,
    ]));
    refreshProviders(root, serverState);
    refreshSchedules(scheduleList, scheduleEmpty);
  }

  async function poll(runId, status, output) {
    for (;;) {
      const job = await api(`/api/research/runs/${runId}`);
      if (job.status === "completed") {
        setStatus(status, "조사 완료", job.publish ? "SQLite 발행과 분석을 완료했습니다." : "읽기 전용 분석을 완료했습니다.", "completed");
        output.textContent = job.result?.answer || "완료 결과가 없습니다."; output.hidden = false; return;
      }
      if (job.status === "failed") throw new Error(responseMessage(job, "조사 실행 중 오류가 발생했습니다."));
      setStatus(status, job.status === "queued" ? "실행 대기" : "웹 조사 중", "공개 원문 확인과 사업 영향 분석을 진행하고 있습니다.", "running");
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
  }

  async function refreshProviders(root, serverState) {
    try {
      const data = await api("/api/research/providers");
      serverState.dataset.state = "ready";
      serverState.querySelector("strong").textContent = "조사 서버 연결됨";
      serverState.lastElementChild.textContent = "즉시 실행을 사용할 수 있습니다. 반복 일정 API 상태는 아래에서 확인합니다.";
      data.providers.forEach((provider) => {
        const target = root.querySelector(`[data-provider-state="${provider.id}"]`);
        if (!target) return;
        target.textContent = provider.message; target.dataset.ready = provider.configured ? "true" : "false";
      });
    } catch {
      serverState.dataset.state = "failed";
      serverState.querySelector("strong").textContent = "조사 서버 연결 안 됨";
      serverState.lastElementChild.textContent = "설정은 확인할 수 있지만 실행과 일정 저장에는 wiki_run.bat 재시작이 필요합니다.";
      root.querySelectorAll("[data-provider-state]").forEach((target) => { target.textContent = "로컬 조사 서버에 연결되지 않았습니다."; target.dataset.ready = "false"; });
    }
  }

  const boot = () => document.querySelectorAll("[data-research-agent-root]").forEach(mount);
  window.__poscoResearchAgentBoot = boot;
  // The agent bundle is loaded dynamically. It can arrive after MkDocs has
  // already emitted its first document$ event, so always mount the current
  // document before subscribing to later instant-navigation updates.
  boot();
  if (typeof document$ !== "undefined") document$.subscribe(boot);
  else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
})();
