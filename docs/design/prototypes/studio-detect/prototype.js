(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const state = {
    route: "studio",
    modelSelected: false,
    rootSelected: false,
    runState: "idle",
    runTimers: [],
    scanTimer: null,
    rfAvailable: false,
    result: "cnn",
    destination: "",
  };

  const routeMap = {
    studio: ["studio", null],
    "train-reference": ["train-reference", null],
    review: ["review", null],
    "detect/setup": ["detect", "setup"],
    "detect/recordings": ["detect", "recordings"],
    "detect/run": ["detect", "run"],
    "detect/results": ["detect", "results"],
    "detect/export": ["detect", "export"],
  };

  const demoModel = {
    valid: ["CallNet-v4-demo", "CNN · binary single-label · Demo compatibility", "success"],
    loading: ["Reading Demo Model metadata…", "No real package is being opened", "loading"],
    empty: ["Model package is empty", "No model.json or artifact · Demo error", "error"],
    incompatible: ["Forest-Calls-v2-demo", "Random Forest cannot start recording-wide detection", "error"],
    missing: ["CallNet-v4-demo unavailable", "A declared artifact is missing · Demo error", "warning"],
  };
  const demoRoot = {
    valid: ["Rainforest_2026", "/Volumes/Field/Rainforest_2026 · 42 approved WAVs", "success"],
    loading: ["Scanning Rainforest_2026…", "Demo scan · source remains read-only", "loading"],
    empty: ["No WAV candidates", "/Volumes/Field/Empty_Collection", "warning"],
    invalid: ["Rainforest_2026 has path issues", "Duplicate and outside-root paths require review", "error"],
    changed: ["Rainforest_2026 changed", "One file changed after the frozen scan", "warning"],
    missing: ["Recording root unavailable", "/Volumes/Field/Rainforest_2026 cannot be reached", "error"],
  };

  function setHash(route) {
    const next = `#${route}`;
    if (location.hash === next) {
      navigate(route);
    } else {
      location.hash = next;
    }
  }

  function navigate(route) {
    if (!routeMap[route]) route = "studio";
    state.route = route;
    const [screen, page] = routeMap[route];
    $$("[data-screen]").forEach((node) => { node.hidden = node.dataset.screen !== screen; });
    if (screen === "detect") {
      $$("[data-page]").forEach((node) => { node.hidden = node.dataset.page !== page; });
      $$("[data-nav]").forEach((node) => {
        const active = node.dataset.nav === page;
        node.classList.toggle("active", active);
        if (active) node.setAttribute("aria-current", "page");
        else node.removeAttribute("aria-current");
      });
      $("#detect-main").focus({ preventScroll: true });
      $(".skip-link").setAttribute("href", "#detect-main");
    } else {
      const main = $(`#${screen}-screen main`);
      if (main) main.focus({ preventScroll: true });
      $(".skip-link").setAttribute("href", screen === "studio" ? "#main-content" : screen === "train-reference" ? "#train-main" : "#review-main");
    }
    window.scrollTo(0, 0);
  }

  function showToast(message) {
    const toast = $("#toast");
    toast.textContent = message;
    toast.hidden = false;
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(() => { toast.hidden = true; }, 2800);
  }

  function setAlert(node, intent, title, copy) {
    node.className = `alert ${intent}`;
    $("strong", node).textContent = title;
    $("span", node).textContent = copy;
  }

  function renderSelection(kind) {
    const isModel = kind === "model";
    const selected = isModel ? state.modelSelected : state.rootSelected;
    const select = $(`#${kind}-state`);
    const box = $(`#${kind}-selection`);
    const detail = $(":scope > div > span", box);
    const clear = $(`#clear-${kind}`);
    const record = (isModel ? demoModel : demoRoot)[select.value];
    clear.disabled = !selected;
    box.className = "selection-box";
    if (!selected) {
      $("strong", box).textContent = isModel ? "No Model selected" : "No folder selected";
      detail.textContent = isModel ? "Choose a Train CNN Model package" : "Choose the root containing source WAVs";
    } else {
      $("strong", box).textContent = record[0];
      detail.textContent = record[1];
      if (record[2] !== "success") box.classList.add(record[2]);
    }
    updateReadiness();
  }

  function updateReadiness() {
    const modelState = $("#model-state").value;
    const rootState = $("#root-state").value;
    const threshold = Number($("#threshold-input").value);
    const thresholdValid = Number.isFinite(threshold) && threshold >= 0 && threshold <= 1;
    const modelReady = state.modelSelected && modelState === "valid";
    const rootReady = state.rootSelected && rootState === "valid";
    const ready = modelReady && rootReady && thresholdValid;
    const alert = $("#readiness-alert");
    if (ready) {
      setAlert(alert, "success", "Draft ready for demonstration", "42 approved WAVs · compatible Demo CNN · settings complete.");
    } else if (!thresholdValid) {
      setAlert(alert, "danger", "Check candidate threshold", "Enter a demonstration value from 0 to 1.");
    } else if (state.rootSelected && ["changed", "missing"].includes(rootState)) {
      setAlert(alert, "warning", "Recording root needs review", rootState === "missing" ? "Relink the missing root and compare its inventory before starting." : "Rescan changed source files before starting a new Run.");
    } else if (state.modelSelected && modelState !== "valid") {
      setAlert(alert, modelState === "loading" ? "info" : "danger", "CNN Model not ready", "Resolve the selected Demo Model state before starting.");
    } else if (state.rootSelected && rootState !== "valid") {
      setAlert(alert, rootState === "loading" ? "info" : "warning", "Recording root not ready", "Complete source review before starting.");
    } else {
      setAlert(alert, "neutral", "Draft not ready", "Choose a compatible CNN Model and recording root.");
    }
    $("#start-detect").disabled = !ready;
  }

  function clearRunTimers() {
    state.runTimers.forEach(clearTimeout);
    state.runTimers = [];
  }

  const runViews = {
    idle: { title: "Run not started", stage: "Waiting", percent: 0, intent: "info", alert: "Ready for a demonstration", copy: "Use Start demo detection from Setup or choose a state above.", log: "No simulated activity yet.", stages: [] },
    preparing: { title: "Preparing Demo Run", stage: "Validating frozen metadata", percent: 8, intent: "info", alert: "Preparing", copy: "Demonstrating preflight checks. No Model or WAV is opened.", log: "DEMO · Run draft frozen\nDEMO · Checking metadata declarations\nDEMO · Source access is not performed", stages: ["prepare"] },
    running: { title: "Demonstrating CNN candidate detection", stage: "Dawn_A02.wav · Demo window 812 / 1,640", percent: 54, intent: "warning", alert: "Demonstration running", copy: "Synthetic progress only—this is not scientific processing.", log: "DEMO · Metadata checks complete\nDEMO · Candidate windows 12,440 / 23,120\nDEMO · 17 illustrative intervals staged", stages: ["prepare", "detect"] },
    cancelling: { title: "Stopping Demo Run", stage: "Waiting for simulated work to stop", percent: 54, intent: "warning", alert: "Cancellation requested", copy: "No partial Result will be published.", log: "DEMO · Cancellation requested\nDEMO · Finishing current illustrative step", stages: ["prepare", "detect"] },
    cancelled: { title: "Demo Run cancelled", stage: "No Result published", percent: 54, intent: "warning", alert: "Cancelled safely", copy: "The draft and source inventory remain available for another Run.", log: "DEMO · Work stopped\nDEMO · Staged metadata discarded\nDEMO · Source files untouched", stages: ["prepare"] },
    interrupted: { title: "Demo Run interrupted", stage: "Application restart illustrated", percent: 43, intent: "danger", alert: "Run interrupted", copy: "A native app would preserve diagnostics and require an explicit new Run.", log: "DEMO · Previous process no longer active\nDEMO · No completed Result exists", stages: ["prepare"] },
    failed: { title: "Demo Run failed", stage: "Model compatibility changed", percent: 16, intent: "danger", alert: "Run failed", copy: "The original source and earlier Results remain unchanged.", log: "DEMO · Preflight metadata read\nDEMO · Compatibility failure illustrated\nDEMO · Publication not attempted", stages: ["prepare"] },
    completed: { title: "Demo Run completed", stage: "Metadata-only Result published", percent: 100, intent: "success", alert: "Completed with demonstration data", copy: "18 illustrative intervals across 3 recordings. No inference ran.", log: "DEMO · Candidate progress complete\nDEMO · Result metadata staged\nDEMO · Immutable demonstration Result published", stages: ["prepare", "detect", "publish"] },
    "file-errors": { title: "Demo Run completed with file errors", stage: "Metadata-only Result published", percent: 100, intent: "warning", alert: "Completed · 1 source failed", copy: "The failed recording is reported explicitly, not represented as zero candidates.", log: "DEMO · 41 source files illustrated\nDEMO · Dawn_Broken.wav failed\nDEMO · Result published with per-file outcome", stages: ["prepare", "detect", "publish"] },
  };

  function setRunState(next) {
    state.runState = next;
    $("#run-state").value = next;
    const view = runViews[next];
    $("#run-title").textContent = view.title;
    $("#run-stage").textContent = view.stage;
    $("#run-subtitle").textContent = view.copy;
    $("#run-percent").textContent = `${view.percent}%`;
    $("#run-progress-bar").style.width = `${view.percent}%`;
    $("#run-log").textContent = view.log;
    setAlert($("#run-alert"), view.intent, view.alert, view.copy);
    $$("#stage-list li").forEach((item) => {
      const complete = view.stages.includes(item.dataset.stage);
      const active = next === "preparing" && item.dataset.stage === "prepare" || next === "running" && item.dataset.stage === "detect" || next === "completed" && item.dataset.stage === "publish" || next === "file-errors" && item.dataset.stage === "publish";
      item.classList.toggle("complete", complete && !active);
      item.classList.toggle("active", active);
      $("span", item).textContent = complete ? (active ? "◉" : "✓") : "○";
    });
    const active = ["preparing", "running", "cancelling"].includes(next);
    const retry = ["cancelled", "interrupted", "failed"].includes(next);
    const finished = ["completed", "file-errors"].includes(next);
    $("#cancel-run").disabled = !["preparing", "running"].includes(next);
    $("#retry-run").hidden = !retry;
    $("#open-results").disabled = !finished;
    $("#file-failures").hidden = next !== "file-errors";
    $("#global-run-label").textContent = active ? "Rainforest dawn · Demo" : finished ? "Last Run completed · Demo" : retry ? `Last Run ${next} · Demo` : "No active Run";
    $("#global-run-badge").textContent = active ? (next === "cancelling" ? "Stopping" : "Working") : finished ? "Completed" : retry ? next[0].toUpperCase() + next.slice(1) : "Idle";
    $("#global-run-badge").className = `badge ${active ? "warning" : finished ? "success" : retry ? "danger" : "neutral"}`;
    $("#view-active-run").hidden = !active;
    $("#nav-run-dot").hidden = !active;
  }

  function simulateRun() {
    clearRunTimers();
    setHash("detect/run");
    setRunState("preparing");
    state.runTimers.push(setTimeout(() => setRunState("running"), 700));
    state.runTimers.push(setTimeout(() => setRunState("completed"), 1900));
  }

  const inventoryViews = {
    ready: ["warning", "2 items need a decision", "One duplicate and one invalid WAV are not included."],
    scanning: ["info", "Demo scan in progress", "WAV candidates are being illustrated; source files remain untouched."],
    cancelled: ["warning", "Scan cancelled", "No new inventory was accepted. The previous verified inventory remains unchanged."],
    invalid: ["danger", "Path review required", "A duplicate source identity and an outside-root path block readiness."],
    stale: ["warning", "Source changed after scan", "One WAV fingerprint differs. Rescan before starting a new Run."],
    missing: ["danger", "Recording root unavailable", "Propose a new location, compare inventory facts, then explicitly rebind and rescan."],
  };

  function setInventoryState(next) {
    $("#inventory-state").value = next;
    const [intent, title, copy] = inventoryViews[next];
    setAlert($("#inventory-alert"), intent, title, copy);
    $("#scan-progress").hidden = next !== "scanning";
    $("#relink-card").hidden = !["stale", "missing"].includes(next);
    $("#rescan-button").textContent = next === "missing" ? "Propose rebind" : "Rescan demo";
    $("#nav-issue-count").textContent = next === "ready" ? "2" : next === "scanning" ? "…" : "!";
  }

  function simulateScan() {
    clearTimeout(state.scanTimer);
    setInventoryState("scanning");
    $("#scan-percent").textContent = "46%";
    $("#scan-progress-bar").style.width = "46%";
    $("#scan-count").textContent = "31 / 68 files";
    state.scanTimer = setTimeout(() => {
      $("#scan-percent").textContent = "100%";
      $("#scan-progress-bar").style.width = "100%";
      $("#scan-count").textContent = "68 / 68 files";
      setTimeout(() => {
        state.rootSelected = true;
        $("#root-state").value = "valid";
        renderSelection("root");
        setInventoryState("ready");
      }, 400);
    }, 1100);
  }

  function setFolderDecision(decision) {
    const included = decision === "Included";
    const detail = $("#inventory-detail");
    const values = $$("dd", detail);
    const treeBadge = $("[data-folder='incoming'] .badge");
    $(".overline", detail).textContent = "SELECTED FOLDER";
    $("h2", detail).textContent = "incoming/";
    $(".badge", values[0]).textContent = decision;
    $(".badge", values[0]).className = `badge ${included ? "success" : "neutral"}`;
    values[1].textContent = "1 WAV";
    values[2].textContent = "17 min 42 s";
    values[3].textContent = "Explicit Demo decision";
    treeBadge.textContent = included ? "1 included" : "excluded";
    treeBadge.className = `badge ${included ? "success" : "neutral"}`;
    $("#included-count").textContent = included ? "43" : "42";
    showToast(`Demo decision: incoming/ marked ${decision.toLowerCase()}; source unchanged.`);
  }

  function setResultView(next) {
    $("#result-state").value = next;
    $("#populated-results").hidden = next !== "populated";
    $("#empty-results").hidden = next !== "empty";
    $("#error-results").hidden = next !== "error";
    $("#rf-card").hidden = next !== "populated";
    if (next === "populated") setAlert($("#result-alert"), "info", "Demo Result", "Illustrative candidate times and scores—not output from a Model.");
    if (next === "empty") setAlert($("#result-alert"), "success", "Completed with no Demo candidates", "A zero-interval Result still keeps provenance and per-recording outcomes.");
    if (next === "error") setAlert($("#result-alert"), "danger", "Source navigation unavailable", "Result metadata remains intact while the recording root is missing.");
  }

  function renderResult() {
    const derived = state.result === "rf" && state.rfAvailable;
    $("#result-select").value = derived ? "rf" : "cnn";
    $("#result-name").textContent = derived ? "RF assessment · Demo" : "CNN candidates · Demo";
    $("#lineage-model").textContent = derived ? "CNN Result · cnn-demo-001" : "CNN Model · CallNet-v4-demo";
    $("#lineage-result").textContent = derived ? "Derived Result · rf-demo-001" : "Result · cnn-demo-001";
    $("#parent-value").textContent = derived ? "cnn-demo-001 · preserved unchanged" : "None · first-pass Result";
    $("#provenance-count").textContent = derived ? "18 assessed · 11 accepted · 5 rejected · 2 unscored" : "18 Demo candidates";
    $("#rf-status-heading").hidden = !derived;
    $$(".rf-status").forEach((cell) => { cell.hidden = !derived; });
    $("#export-result-name").textContent = derived ? "RF assessment · Demo" : "CNN candidates · Demo";
  }

  function createRfResult() {
    const button = $("#run-rf");
    button.disabled = true;
    button.textContent = "Creating Demo metadata…";
    setTimeout(() => {
      state.rfAvailable = true;
      state.result = "rf";
      const option = $("#result-select option[value='rf']");
      option.disabled = false;
      option.textContent = "RF assessment · Demo";
      button.textContent = "Derived Demo Result created";
      renderResult();
      showToast("Derived metadata-only Demo Result created; CNN parent preserved.");
    }, 700);
  }

  const exportMessages = {
    ready: ["info", "Ready to demonstrate", "Review the planned mapping, then start. No files will be written."],
    conflict: ["warning", "Destination conflicts", "corpus-demo.wav and 2 snippet names already exist. Choose a new folder or collision policy."],
    stale: ["danger", "Source changed", "Dawn_A01.wav no longer matches the frozen selection. Rescan and create a new Result."],
    cancelled: ["warning", "Export cancelled", "No demonstration output was published. Existing destination files are unchanged."],
    error: ["danger", "Destination write failed", "The demonstration illustrates atomic failure: no partial corpus is published."],
    success: ["success", "Demo export completed", "/Users/researcher/Exports/Rainforest-corpus-demo · nothing was actually written."],
  };

  function updateExportState(next = $("#export-state").value) {
    $("#export-state").value = next;
    const hasDestination = Boolean($("#destination-input").value.trim());
    const alert = $("#export-alert");
    if (!hasDestination && next === "ready") {
      setAlert(alert, "neutral", "Destination required", "Choose a folder to continue.");
    } else {
      const [intent, title, copy] = exportMessages[next];
      setAlert(alert, intent, title, copy);
    }
    $("#start-export").disabled = !hasDestination || next !== "ready";
    $("#show-output").hidden = next !== "success";
  }

  function updateExportFormat(value) {
    const summaries = {
      snippets: ["Individual WAV snippets", "3 WAV", "Provenance manifest"],
      concat: ["Concatenated WAV + Raven TSV", "1 WAV", "Raven TSV + provenance map"],
      both: ["Both", "4 WAV", "Raven TSV + provenance map"],
    };
    const [format, count, companions] = summaries[value];
    $("#format-summary").textContent = format;
    $("#output-count").textContent = count;
    $("#companion-count").textContent = companions;
    $$("#mapping-body tr").forEach((row, index) => {
      const source = ["Dawn_A01__start-0764320ms__end-0765120ms.wav", "Dawn_A01__start-1868540ms__end-1869340ms.wav", "Dawn_A01__start-4930000ms__end-4930800ms.wav"][index];
      const offset = ["00:00.000–00:00.800", "00:00.800–00:01.600", "00:01.600–00:02.400"][index];
      row.cells[1].textContent = value === "concat" ? "corpus-demo.wav + selections-demo.Table.1.selections.txt" : `snippets/${source}${value === "both" ? " + corpus-demo.wav" : ""}`;
      row.cells[2].textContent = value === "snippets" ? "Not applicable" : `concat.wav · ${offset}`;
    });
  }

  function bindEvents() {
    document.addEventListener("click", (event) => {
      const routeButton = event.target.closest("[data-route]");
      if (routeButton) {
        event.preventDefault();
        setHash(routeButton.dataset.route);
      }
    });

    $$(".help-hint").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        const open = !button.classList.contains("popover-open");
        $$(".help-hint.popover-open").forEach((item) => { item.classList.remove("popover-open"); item.setAttribute("aria-expanded", "false"); });
        button.classList.toggle("popover-open", open);
        button.setAttribute("aria-expanded", String(open));
      });
    });
    document.addEventListener("click", () => $$(".help-hint.popover-open").forEach((item) => { item.classList.remove("popover-open"); item.setAttribute("aria-expanded", "false"); }));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        $$(".help-hint.popover-open").forEach((item) => { item.classList.remove("popover-open"); item.setAttribute("aria-expanded", "false"); });
        if ($("#guide-dialog").open) $("#guide-dialog").close();
      }
    });

    $("#choose-model").addEventListener("click", () => { state.modelSelected = true; $("#model-state").value = "valid"; renderSelection("model"); });
    $("#clear-model").addEventListener("click", () => { state.modelSelected = false; renderSelection("model"); });
    $("#model-state").addEventListener("change", () => { state.modelSelected = true; renderSelection("model"); });
    $("#choose-root").addEventListener("click", () => { state.rootSelected = true; $("#root-state").value = "valid"; renderSelection("root"); });
    $("#clear-root").addEventListener("click", () => { state.rootSelected = false; renderSelection("root"); });
    $("#root-state").addEventListener("change", () => { state.rootSelected = true; renderSelection("root"); });
    $("#threshold-input").addEventListener("input", updateReadiness);
    $("#start-detect").addEventListener("click", simulateRun);

    $("#inventory-state").addEventListener("change", (event) => setInventoryState(event.target.value));
    $("#rescan-button").addEventListener("click", () => {
      if ($("#inventory-state").value === "missing") {
        $("#relink-card").hidden = false;
        $("#relink-confirm").focus();
      } else simulateScan();
    });
    $("#cancel-scan").addEventListener("click", () => { clearTimeout(state.scanTimer); setInventoryState("cancelled"); });
    $("#include-folder").addEventListener("click", () => setFolderDecision("Included"));
    $("#exclude-folder").addEventListener("click", () => setFolderDecision("Excluded"));
    $$(".tree-row").forEach((row) => row.addEventListener("click", () => {
      $$(".tree-row").forEach((item) => item.classList.remove("selected"));
      row.classList.add("selected");
      const name = row.dataset.folder ? `${row.dataset.folder}/` : row.dataset.file;
      $("#inventory-detail h2").textContent = name;
      $("#inventory-detail .overline").textContent = row.dataset.folder ? "SELECTED FOLDER" : "SELECTED FILE";
    }));
    $("#relink-confirm").addEventListener("change", (event) => { $("#accept-relink").disabled = !event.target.checked; });
    $("#cancel-relink").addEventListener("click", () => { $("#relink-card").hidden = true; showToast("Proposed Demo rebind cancelled; missing root remains unbound."); });
    $("#accept-relink").addEventListener("click", () => { state.rootSelected = true; $("#root-state").value = "loading"; renderSelection("root"); simulateScan(); showToast("Demo rebind accepted for rescan; one changed file still requires a new inventory."); });

    $("#run-state").addEventListener("change", (event) => { clearRunTimers(); setRunState(event.target.value); });
    $("#cancel-run").addEventListener("click", () => { clearRunTimers(); setRunState("cancelling"); state.runTimers.push(setTimeout(() => setRunState("cancelled"), 650)); });
    $("#retry-run").addEventListener("click", simulateRun);

    $("#result-state").addEventListener("change", (event) => setResultView(event.target.value));
    $("#result-select").addEventListener("change", (event) => { state.result = event.target.value; renderResult(); });
    $$(".recording-row").forEach((row) => row.addEventListener("click", () => { $$(".recording-row").forEach((item) => item.classList.remove("selected")); row.classList.add("selected"); $(".interval-card h2").textContent = $("strong", row).textContent; }));
    $("#show-source").addEventListener("click", () => showToast("Demo only: would reveal Dawn_A01.wav in the source folder."));
    $("#result-relink").addEventListener("click", () => { setInventoryState("missing"); setHash("detect/recordings"); });
    $("#rf-model").addEventListener("change", (event) => {
      const valid = event.target.value === "valid";
      $("#run-rf").disabled = !valid;
      $("#rf-error").hidden = event.target.value !== "invalid";
    });
    $("#run-rf").addEventListener("click", createRfResult);

    $$('input[name="export-format"]').forEach((radio) => radio.addEventListener("change", (event) => updateExportFormat(event.target.value)));
    $("#choose-destination").addEventListener("click", () => { const value = "/Users/researcher/Exports/Rainforest-corpus-demo"; $("#destination-input").value = value; state.destination = value; $("#destination-summary").textContent = value; updateExportState("ready"); });
    $("#destination-input").addEventListener("input", (event) => { state.destination = event.target.value.trim(); $("#destination-summary").textContent = state.destination || "Not selected"; updateExportState(); });
    $("#export-state").addEventListener("change", (event) => {
      if (event.target.value === "success" && !$("#destination-input").value.trim()) {
        const value = "/Users/researcher/Exports/Rainforest-corpus-demo";
        $("#destination-input").value = value;
        state.destination = value;
        $("#destination-summary").textContent = value;
      }
      updateExportState(event.target.value);
    });
    $("#start-export").addEventListener("click", () => {
      const button = $("#start-export");
      button.disabled = true;
      button.textContent = "Demonstrating export…";
      setAlert($("#export-alert"), "info", "Preparing demonstration", "Checking frozen mapping and destination; no audio is written.");
      setTimeout(() => { button.textContent = "Export demonstration"; updateExportState("success"); }, 850);
    });
    $("#show-output").addEventListener("click", () => showToast("Demo only: would open /Users/researcher/Exports/Rainforest-corpus-demo"));

    $("#help-wiki-button").addEventListener("click", () => $("#guide-dialog").showModal());
    $$('[data-close-dialog]').forEach((button) => button.addEventListener("click", () => $("#guide-dialog").close()));
    $("#guide-dialog").addEventListener("click", (event) => { if (event.target === $("#guide-dialog")) $("#guide-dialog").close(); });
    window.addEventListener("hashchange", () => navigate(location.hash.slice(1)));
  }

  function init() {
    bindEvents();
    renderSelection("model");
    renderSelection("root");
    setRunState("idle");
    setInventoryState("ready");
    setResultView("populated");
    renderResult();
    updateExportFormat("both");
    updateExportState("ready");
    navigate(location.hash.slice(1) || "studio");
  }

  window.__studioPrototype = { navigate, setRunState, setInventoryState, setResultView, updateExportState, state };
  init();
})();
