(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  const state = {
    route: "studio",
    modelSelected: false,
    rootSelected: false,
    inventoryState: "ready",
    selectedInventory: { kind: "folder", key: "recordings" },
    folderDecisions: {
      recordings: "included",
      incoming: "undecided",
      positives: "excluded",
      alpaca: "excluded",
    },
    runState: "idle",
    runTimers: [],
    scanTimers: [],
    rfAvailable: false,
    result: "cnn",
    resultView: "populated",
    selectedRecording: "Dawn_A01.wav",
    selections: {
      cnn: new Set(["a01-1", "a01-2", "a01-4"]),
      rf: new Set(),
    },
    exportSnapshot: { result: "cnn", intervals: [] },
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

  const modelScenarios = {
    valid: ["CallNet v4", "Compatible · CNN · binary single-label", "success"],
    loading: ["Reading model information…", "Compatibility check in progress", "loading"],
    empty: ["Model package is empty", "No model manifest or artifact", "error"],
    incompatible: ["Forest Calls v2", "This model can refine intervals but cannot start detection", "error"],
    missing: ["CallNet v4 unavailable", "A declared model file is missing", "warning"],
  };

  const rootScenarios = {
    valid: ["Rainforest_2026", "/Volumes/Field/Rainforest_2026 · 42 included WAVs", "success"],
    loading: ["Scanning Rainforest_2026…", "Reading WAV file information", "loading"],
    empty: ["No WAV recordings", "/Volumes/Field/Empty_Collection", "warning"],
    invalid: ["Rainforest_2026 has path errors", "Duplicate and outside-folder paths require review", "error"],
    changed: ["Rainforest_2026 changed", "One recording changed after the last scan", "warning"],
    missing: ["Recordings folder unavailable", "/Volumes/Field/Rainforest_2026 cannot be reached", "error"],
  };

  const folderData = {
    recordings: { label: "recordings/", count: 42, duration: "31 h 08 min", rule: "Recognized recordings folder" },
    incoming: { label: "incoming/", count: 1, duration: "17 min 42 s", rule: "Explicit inclusion decision" },
    positives: { label: "positives/", count: 12, duration: "9 min 31 s", rule: "Train snippets are excluded" },
    alpaca: { label: ".alpaca/", count: 11, duration: "24 min 18 s", rule: "Derived audio is excluded" },
  };

  const fileData = {
    "Dawn_A01.wav": { decision: "Included", count: "1 WAV", duration: "01 h 38 min", rule: "Parent folder decision", intent: "success" },
    "Dawn_A02.wav": { decision: "Included", count: "1 WAV", duration: "54 min 09 s", rule: "Parent folder decision", intent: "success" },
    "Dawn_A02-copy.wav": { decision: "Excluded", count: "1 WAV", duration: "54 min 09 s", rule: "Duplicate recording", intent: "neutral" },
    "broken.wav": { decision: "Invalid · skipped", count: "1 WAV", duration: "Unavailable", rule: "Unreadable WAV header", intent: "danger" },
  };

  const recordings = [
    {
      name: "Dawn_A01.wav",
      duration: "01:38:14",
      intervals: [
        { id: "a01-1", start: "00:12:44.320", end: "00:12:45.120", startMs: 764320, endMs: 765120, score: 0.91, refinement: "accepted" },
        { id: "a01-2", start: "00:31:08.540", end: "00:31:09.340", startMs: 1868540, endMs: 1869340, score: 0.84, refinement: "rejected" },
        { id: "a01-3", start: "01:04:27.100", end: "01:04:27.900", startMs: 3867100, endMs: 3867900, score: 0.77, refinement: "unscored" },
        { id: "a01-4", start: "01:22:10.000", end: "01:22:10.800", startMs: 4930000, endMs: 4930800, score: 0.73, refinement: "accepted" },
      ],
    },
    {
      name: "Dawn_A02.wav",
      duration: "00:54:09",
      intervals: [
        { id: "a02-1", start: "00:03:11.600", end: "00:03:12.400", startMs: 191600, endMs: 192400, score: 0.94, refinement: "accepted" },
        { id: "a02-2", start: "00:07:42.080", end: "00:07:42.880", startMs: 462080, endMs: 462880, score: 0.88, refinement: "accepted" },
        { id: "a02-3", start: "00:11:09.210", end: "00:11:10.010", startMs: 669210, endMs: 670010, score: 0.86, refinement: "rejected" },
        { id: "a02-4", start: "00:18:25.000", end: "00:18:25.800", startMs: 1105000, endMs: 1105800, score: 0.83, refinement: "accepted" },
        { id: "a02-5", start: "00:25:36.440", end: "00:25:37.240", startMs: 1536440, endMs: 1537240, score: 0.81, refinement: "unscored" },
        { id: "a02-6", start: "00:32:12.180", end: "00:32:12.980", startMs: 1932180, endMs: 1932980, score: 0.79, refinement: "accepted" },
        { id: "a02-7", start: "00:39:51.720", end: "00:39:52.520", startMs: 2391720, endMs: 2392520, score: 0.77, refinement: "rejected" },
        { id: "a02-8", start: "00:46:05.100", end: "00:46:05.900", startMs: 2765100, endMs: 2765900, score: 0.75, refinement: "accepted" },
        { id: "a02-9", start: "00:51:33.030", end: "00:51:33.830", startMs: 3093030, endMs: 3093830, score: 0.72, refinement: "rejected" },
      ],
    },
    {
      name: "Dusk_C17.wav",
      duration: "02:11:42",
      intervals: [
        { id: "c17-1", start: "00:08:14.250", end: "00:08:15.050", startMs: 494250, endMs: 495050, score: 0.92, refinement: "accepted" },
        { id: "c17-2", start: "00:37:41.900", end: "00:37:42.700", startMs: 2261900, endMs: 2262700, score: 0.87, refinement: "accepted" },
        { id: "c17-3", start: "01:02:18.400", end: "01:02:19.200", startMs: 3738400, endMs: 3739200, score: 0.82, refinement: "rejected" },
        { id: "c17-4", start: "01:48:06.720", end: "01:48:07.520", startMs: 6486720, endMs: 6487520, score: 0.76, refinement: "accepted" },
        { id: "c17-5", start: "02:04:55.000", end: "02:04:55.800", startMs: 7495000, endMs: 7495800, score: 0.74, refinement: "accepted" },
      ],
    },
    { name: "Dawn_Broken.wav", duration: "!", intervals: [], error: "Source read failed" },
  ];

  function setHash(route) {
    const next = `#${route}`;
    if (location.hash === next) navigate(route);
    else location.hash = next;
  }

  function navigate(route) {
    if (!routeMap[route]) route = "studio";
    state.route = route;
    const [screen, page] = routeMap[route];
    $$('[data-screen]').forEach((node) => { node.hidden = node.dataset.screen !== screen; });
    if (screen === "detect") {
      $$('[data-page]').forEach((node) => { node.hidden = node.dataset.page !== page; });
      $$('[data-nav]').forEach((node) => {
        const active = node.dataset.nav === page;
        node.classList.toggle("active", active);
        if (active) node.setAttribute("aria-current", "page");
        else node.removeAttribute("aria-current");
      });
      if (page === "results") renderResult();
      if (page === "export") {
        freezeExportSelection();
        renderExport();
      }
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
    const record = (isModel ? modelScenarios : rootScenarios)[select.value];
    clear.disabled = !selected;
    box.className = "selection-box";
    if (!selected) {
      $("strong", box).textContent = isModel ? "No model selected" : "No folder selected";
      detail.textContent = isModel ? "Choose a trained detection model" : "Choose the folder containing your WAV recordings";
    } else {
      $("strong", box).textContent = record[0];
      detail.textContent = record[1];
      if (record[2] !== "success") box.classList.add(record[2]);
    }
    updateReadiness();
  }

  function inventoryCounts() {
    const counts = { included: 0, undecided: 0, excluded: 1, invalid: 1 };
    Object.entries(folderData).forEach(([key, folder]) => {
      counts[state.folderDecisions[key]] += folder.count;
    });
    return counts;
  }

  function updateReadiness() {
    const modelState = $("#model-state").value;
    const rootState = $("#root-state").value;
    const threshold = Number($("#threshold-input").value);
    const thresholdValid = Number.isFinite(threshold) && threshold >= 0 && threshold <= 1;
    const modelReady = state.modelSelected && modelState === "valid";
    const rootReady = state.rootSelected && rootState === "valid";
    const inventoryReady = state.inventoryState === "ready" && inventoryCounts().included > 0;
    const ready = modelReady && rootReady && inventoryReady && thresholdValid;
    const alert = $("#readiness-alert");

    if (ready) {
      const count = inventoryCounts().included;
      setAlert(alert, "success", "Ready to start", `${count} included WAVs · compatible detection model · settings complete.`);
    } else if (!thresholdValid) {
      setAlert(alert, "danger", "Check minimum detection score", "Enter a value from 0 to 1.");
    } else if (state.rootSelected && ["changed", "missing"].includes(rootState)) {
      setAlert(alert, "warning", "Recordings folder needs review", rootState === "missing" ? "Relink the missing folder and compare its inventory before starting." : "Rescan changed recordings before starting a new Run.");
    } else if (state.modelSelected && modelState !== "valid") {
      setAlert(alert, modelState === "loading" ? "info" : "danger", "Detection model not ready", "Resolve the selected model before starting.");
    } else if (state.rootSelected && rootState !== "valid") {
      setAlert(alert, rootState === "loading" ? "info" : "warning", "Recordings folder not ready", "Complete the folder review before starting.");
    } else if (state.rootSelected && state.inventoryState === "invalid") {
      setAlert(alert, "danger", "Resolve invalid included recordings", "Exclude or repair invalid included recordings before starting.");
    } else if (state.rootSelected && state.inventoryState !== "ready") {
      setAlert(alert, "warning", "Recording review not ready", "Complete or resolve the current inventory state before starting.");
    } else if (state.rootSelected && inventoryCounts().included === 0) {
      setAlert(alert, "warning", "No recordings included", "Include at least one valid recording before starting.");
    } else {
      setAlert(alert, "neutral", "Not ready", "Choose a compatible detection model and recordings folder.");
    }
    $("#start-detect").disabled = !ready;
  }

  function clearRunTimers() {
    state.runTimers.forEach(clearTimeout);
    state.runTimers = [];
  }

  const runViews = {
    idle: { title: "Run not started", stage: "Waiting", percent: 0, intent: "info", alert: "Ready to start", copy: "Review setup, then start detection.", log: "No activity yet.", stages: [] },
    preparing: { title: "Preparing Run", stage: "Validating frozen inputs", percent: 8, intent: "info", alert: "Preparing", copy: "Checking the model, inventory, and settings.", log: "Run draft frozen\nChecking model information\nChecking recording inventory", stages: ["prepare"] },
    running: { title: "Finding candidate calls", stage: "Dawn_A02.wav · window 812 / 1,640", percent: 54, intent: "warning", alert: "Detection running", copy: "17 candidate intervals found so far.", log: "Input checks complete\nCandidate windows 12,440 / 23,120\n17 intervals staged", stages: ["prepare", "detect"] },
    cancelling: { title: "Stopping Run", stage: "Waiting for current work to stop", percent: 54, intent: "warning", alert: "Cancellation requested", copy: "No partial Result will be published.", log: "Cancellation requested\nFinishing the current work item", stages: ["prepare", "detect"] },
    cancelled: { title: "Run cancelled", stage: "No Result published", percent: 54, intent: "warning", alert: "Cancelled safely", copy: "The setup and recording inventory remain available for another Run.", log: "Work stopped\nStaged metadata discarded\nSource recordings unchanged", stages: ["prepare"] },
    interrupted: { title: "Run interrupted", stage: "Previous process is no longer active", percent: 43, intent: "danger", alert: "Run interrupted", copy: "Review diagnostics, then start a new Run.", log: "Previous process no longer active\nNo completed Result exists", stages: ["prepare"] },
    failed: { title: "Run failed", stage: "Model compatibility changed", percent: 16, intent: "danger", alert: "Run failed", copy: "The source recordings and earlier Results remain unchanged.", log: "Input metadata checked\nModel compatibility failed\nNo Result published", stages: ["prepare"] },
    completed: { title: "Run completed", stage: "Metadata-only Result published", percent: 100, intent: "success", alert: "Completed", copy: "18 candidate intervals across 3 recordings.", log: "Candidate search complete\nResult metadata staged\nResult published", stages: ["prepare", "detect", "publish"] },
    "file-errors": { title: "Run completed with file errors", stage: "Metadata-only Result published", percent: 100, intent: "warning", alert: "Completed · 1 recording failed", copy: "The failed recording is reported separately from recordings with zero candidates.", log: "41 recordings analyzed\nDawn_Broken.wav failed\nResult published with per-file outcomes", stages: ["prepare", "detect", "publish"] },
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
      const active = (next === "preparing" && item.dataset.stage === "prepare") || (next === "running" && item.dataset.stage === "detect") || (["completed", "file-errors"].includes(next) && item.dataset.stage === "publish");
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
    $("#global-run-label").textContent = active ? "Rainforest dawn" : finished ? "Last Run completed" : retry ? `Last Run ${next}` : "No active Run";
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
    ready: ["warning", "2 recordings skipped", "One duplicate and one invalid WAV are not included."],
    scanning: ["info", "Scan in progress", "Reading recording names and WAV headers."],
    cancelled: ["warning", "Scan cancelled", "No new inventory was accepted. The previous verified inventory remains unchanged."],
    invalid: ["danger", "Invalid included recording", "broken.wav is included but unreadable. Exclude it or repair the recording before starting."],
    stale: ["warning", "Source changed after scan", "One WAV fingerprint differs. Rescan before starting a new Run."],
    missing: ["danger", "Recordings folder unavailable", "Propose a new location, compare the inventory, then explicitly rebind and rescan."],
  };

  function renderInventoryCounts() {
    const counts = inventoryCounts();
    $("#included-count").textContent = counts.included;
    $("#undecided-count").textContent = counts.undecided;
    $("#excluded-count").textContent = counts.excluded;
    $("#invalid-count").textContent = counts.invalid;
    $("#invalid-count").nextElementSibling.textContent = state.inventoryState === "invalid" ? "included · resolve" : "not included";
    Object.entries(folderData).forEach(([key, folder]) => {
      const badge = $(`[data-folder='${key}'] .badge`);
      const decision = state.folderDecisions[key];
      badge.textContent = `${folder.count} ${decision}`;
      badge.className = `badge ${decision === "included" ? "success" : decision === "undecided" ? "warning" : "neutral"}`;
    });
  }

  function renderInventoryDetail() {
    const { kind, key } = state.selectedInventory;
    const detail = $("#inventory-detail");
    $$(".tree-row").forEach((item) => item.classList.toggle("selected", item.dataset[kind] === key));
    $(".overline", detail).textContent = kind === "folder" ? "SELECTED FOLDER" : "SELECTED FILE";
    $("h2", detail).textContent = kind === "folder" ? folderData[key].label : key;
    const values = $$("dd", detail);
    const record = kind === "folder" ? {
      decision: state.folderDecisions[key][0].toUpperCase() + state.folderDecisions[key].slice(1),
      count: `${folderData[key].count} WAV${folderData[key].count === 1 ? "" : "s"}`,
      duration: folderData[key].duration,
      rule: folderData[key].rule,
      intent: state.folderDecisions[key] === "included" ? "success" : state.folderDecisions[key] === "undecided" ? "warning" : "neutral",
    } : fileData[key];
    $(".badge", values[0]).textContent = record.decision;
    $(".badge", values[0]).className = `badge ${record.intent}`;
    values[1].textContent = record.count;
    values[2].textContent = record.duration;
    values[3].textContent = record.rule;
    $("#include-folder").disabled = kind !== "folder" || state.folderDecisions[key] === "included";
    $("#exclude-folder").disabled = kind !== "folder" || state.folderDecisions[key] === "excluded";
  }

  function setInventoryState(next) {
    state.inventoryState = next;
    $("#inventory-state").value = next;
    const [intent, title, copy] = inventoryViews[next];
    setAlert($("#inventory-alert"), intent, title, copy);
    $("#scan-progress").hidden = next !== "scanning";
    $("#relink-card").hidden = !["stale", "missing"].includes(next);
    $("#rescan-button").textContent = next === "missing" ? "Propose rebind" : "Rescan";
    $("#nav-issue-count").textContent = next === "ready" ? "2" : next === "scanning" ? "…" : "!";
    renderInventoryCounts();
    updateReadiness();
  }

  function clearScanTimers() {
    state.scanTimers.forEach(clearTimeout);
    state.scanTimers = [];
  }

  function simulateScan() {
    clearScanTimers();
    setInventoryState("scanning");
    $("#scan-percent").textContent = "46%";
    $("#scan-progress-bar").style.width = "46%";
    $("#scan-count").textContent = "31 / 68 files";
    state.scanTimers.push(setTimeout(() => {
      $("#scan-percent").textContent = "100%";
      $("#scan-progress-bar").style.width = "100%";
      $("#scan-count").textContent = "68 / 68 files";
      state.scanTimers.push(setTimeout(() => {
        state.rootSelected = true;
        $("#root-state").value = "valid";
        renderSelection("root");
        setInventoryState("ready");
      }, 400));
    }, 1100));
  }

  function setFolderDecision(decision) {
    const selected = state.selectedInventory;
    if (selected.kind !== "folder") return;
    state.folderDecisions[selected.key] = decision.toLowerCase();
    renderInventoryCounts();
    renderInventoryDetail();
    updateReadiness();
    showToast(`${folderData[selected.key].label} marked ${decision.toLowerCase()}.`);
  }

  function currentRecording() {
    return recordings.find((recording) => recording.name === state.selectedRecording) || recordings[0];
  }

  function renderRecordingList() {
    const list = $("#recording-list");
    $$(".recording-row", list).forEach((node) => node.remove());
    recordings.forEach((recording) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = `recording-row${recording.name === state.selectedRecording ? " selected" : ""}${recording.error ? " warning-row" : ""}`;
      row.dataset.recording = recording.name;
      const description = recording.error || `${recording.intervals.length} ${state.result === "rf" && state.rfAvailable ? "assessed intervals" : "candidates"}`;
      row.innerHTML = `<span><strong>${recording.name}</strong><small>${description}</small></span><span>${recording.duration}</span>`;
      row.addEventListener("click", () => {
        state.selectedRecording = recording.name;
        renderRecordingList();
        renderIntervals();
      });
      list.append(row);
    });
  }

  function renderIntervals() {
    const recording = currentRecording();
    const derived = state.result === "rf" && state.rfAvailable;
    const selected = state.selections[derived ? "rf" : "cnn"];
    $(".interval-card h2").textContent = recording.name;
    $("#show-source").disabled = Boolean(recording.error);
    $("#rf-status-heading").hidden = !derived;
    const body = $("#interval-body");
    body.replaceChildren();
    if (recording.error) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = derived ? 5 : 4;
      cell.textContent = "Source read failed. The recording outcome remains available in Result metadata.";
      row.append(cell);
      body.append(row);
      return;
    }
    recording.intervals.forEach((interval) => {
      const row = document.createElement("tr");
      const statusIntent = interval.refinement === "accepted" ? "success" : interval.refinement === "rejected" ? "danger" : "warning";
      row.innerHTML = `<td><input type="checkbox" data-interval="${interval.id}" aria-label="Select ${recording.name} interval at ${interval.start}"${selected.has(interval.id) ? " checked" : ""}></td><td>${interval.start}</td><td>${interval.end}</td><td>${interval.score.toFixed(2)}</td>${derived ? `<td><span class="badge ${statusIntent}">${interval.refinement}</span></td>` : ""}`;
      body.append(row);
    });
  }

  function setResultView(next) {
    state.resultView = next;
    $("#result-state").value = next;
    $("#populated-results").hidden = next !== "populated";
    $("#empty-results").hidden = next !== "empty";
    $("#error-results").hidden = next !== "error";
    $("#rf-card").hidden = next !== "populated";
    if (next === "populated") setAlert($("#result-alert"), "info", state.result === "rf" ? "Refined Result" : "Original Result", "18 candidate intervals retain their source recording times.");
    if (next === "empty") setAlert($("#result-alert"), "success", "Completed with no candidates", "A zero-interval Result still keeps provenance and per-recording outcomes.");
    if (next === "error") setAlert($("#result-alert"), "danger", "Source navigation unavailable", "Result metadata remains intact while the recordings folder is unavailable.");
    renderResult();
  }

  function renderResult() {
    const derived = state.result === "rf" && state.rfAvailable;
    $("#result-select").value = derived ? "rf" : "cnn";
    $("#result-name").textContent = derived ? "Refined Result" : "Original candidate Result";
    $("#lineage-model").textContent = derived ? "Parent Result · result-original-001" : "Detection Model · CallNet v4 (CNN)";
    $("#lineage-result").textContent = derived ? "Refined Result · result-refined-001" : "Result · result-original-001";
    $("#parent-value").textContent = derived ? "result-original-001 · preserved unchanged" : "None · original Result";
    $("#provenance-count").textContent = state.resultView === "empty" ? "0 candidates" : derived ? "18 assessed · 11 accepted · 5 rejected · 2 unscored" : "18 candidates";
    if (state.resultView === "populated") setAlert($("#result-alert"), "info", derived ? "Refined Result" : "Original Result", derived ? "Refinement decisions are stored separately from the original candidate intervals." : "18 candidate intervals retain their source recording times.");
    renderRecordingList();
    renderIntervals();
  }

  function createRfResult() {
    const button = $("#run-rf");
    button.disabled = true;
    button.textContent = "Creating refined Result…";
    setTimeout(() => {
      state.rfAvailable = true;
      state.selections.rf = new Set(state.selections.cnn);
      state.result = "rf";
      const option = $("#result-select option[value='rf']");
      option.disabled = false;
      option.textContent = "Refined Result";
      button.textContent = "Refined Result created";
      renderResult();
      showToast("Refined Result created. The original Result remains unchanged.");
    }, 700);
  }

  function allIntervals() {
    return recordings.flatMap((recording) => recording.intervals.map((interval) => ({ ...interval, recording: recording.name })));
  }

  function freezeExportSelection() {
    const artifact = state.result === "rf" && state.rfAvailable ? "rf" : "cnn";
    const selected = state.selections[artifact];
    state.exportSnapshot = {
      result: artifact,
      intervals: state.resultView === "empty" ? [] : allIntervals().filter((interval) => selected.has(interval.id)),
    };
  }

  function offsetTime(milliseconds) {
    const minutes = Math.floor(milliseconds / 60000);
    const seconds = Math.floor((milliseconds % 60000) / 1000);
    const ms = milliseconds % 1000;
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(ms).padStart(3, "0")}`;
  }

  function selectedFormat() {
    return $('input[name="export-format"]:checked').value;
  }

  function renderExportMapping() {
    const body = $("#mapping-body");
    body.replaceChildren();
    const format = selectedFormat();
    let offset = 0;
    if (state.exportSnapshot.intervals.length === 0) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 3;
      cell.textContent = "No intervals selected. Return to Results to choose intervals.";
      row.append(cell);
      body.append(row);
      return;
    }
    state.exportSnapshot.intervals.forEach((interval) => {
      const row = document.createElement("tr");
      const base = interval.recording.replace(/\.wav$/i, "");
      const snippet = `snippets/${base}__start-${String(interval.startMs).padStart(7, "0")}ms__end-${String(interval.endMs).padStart(7, "0")}ms.wav`;
      const duration = interval.endMs - interval.startMs;
      const output = format === "concat" ? "corpus.wav + selections.Table.1.selections.txt" : format === "both" ? `${snippet} + corpus.wav` : snippet;
      const exportOffset = format === "snippets" ? "Not applicable" : `corpus.wav · ${offsetTime(offset)}–${offsetTime(offset + duration)}`;
      row.innerHTML = `<td>${interval.recording} · ${interval.start}–${interval.end}</td><td>${output}</td><td>${exportOffset}</td>`;
      body.append(row);
      offset += duration;
    });
  }

  function updateExportFormat(value = selectedFormat()) {
    const count = state.exportSnapshot.intervals.length;
    const summaries = {
      snippets: ["Individual WAV snippets", `${count} WAV`, "Provenance manifest"],
      concat: ["Concatenated WAV + Raven TSV", count ? "1 WAV" : "0 WAV", "Raven TSV + provenance map"],
      both: ["Both", `${count ? count + 1 : 0} WAV`, "Raven TSV + provenance map"],
    };
    const [format, outputCount, companions] = summaries[value];
    $("#format-summary").textContent = format;
    $("#output-count").textContent = outputCount;
    $("#companion-count").textContent = companions;
    renderExportMapping();
    updateExportState();
  }

  function renderExport() {
    const count = state.exportSnapshot.intervals.length;
    const recordingCount = new Set(state.exportSnapshot.intervals.map((interval) => interval.recording)).size;
    $("#export-result-name").textContent = state.exportSnapshot.result === "rf" ? "Refined Result" : "Original candidate Result";
    $("#export-selection-count").textContent = `${count} interval${count === 1 ? "" : "s"}`;
    $("#export-selection-count").className = `badge ${count ? "success" : "warning"}`;
    $("#export-selection-summary").textContent = count ? `${count} interval${count === 1 ? "" : "s"} from ${recordingCount} recording${recordingCount === 1 ? "" : "s"}` : "No intervals selected";
    updateExportFormat();
  }

  function exportMessage(next) {
    const destination = state.destination || "/Users/researcher/Exports/Rainforest-corpus";
    const messages = {
      ready: ["info", "Ready to export", "Review the frozen selection and planned mapping, then start."],
      conflict: ["warning", "Destination conflicts", "corpus.wav and two snippet names already exist. Choose a new folder or resolve the conflicts."],
      stale: ["danger", "Source changed", "Dawn_A01.wav no longer matches the frozen selection. Rescan and create a new Result."],
      cancelled: ["warning", "Export cancelled", "No new output was published. Existing destination files are unchanged."],
      error: ["danger", "Destination write failed", "No partial corpus was published."],
      success: ["success", "Export completed", destination],
    };
    return messages[next];
  }

  function updateExportState(next = $("#export-state").value) {
    $("#export-state").value = next;
    const hasDestination = Boolean($("#destination-input").value.trim());
    const hasSelection = state.exportSnapshot.intervals.length > 0;
    const alert = $("#export-alert");
    if (!hasSelection && next === "ready") setAlert(alert, "warning", "Selection required", "Return to Results and select at least one interval.");
    else if (!hasDestination && next === "ready") setAlert(alert, "neutral", "Destination required", "Choose a folder to continue.");
    else {
      const [intent, title, copy] = exportMessage(next);
      setAlert(alert, intent, title, copy);
    }
    $("#start-export").disabled = !hasDestination || !hasSelection || next !== "ready";
    $("#show-output").hidden = next !== "success";
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
    $("#choose-root").addEventListener("click", () => { state.rootSelected = true; $("#root-state").value = "valid"; setInventoryState("ready"); renderSelection("root"); });
    $("#clear-root").addEventListener("click", () => { state.rootSelected = false; renderSelection("root"); });
    $("#root-state").addEventListener("change", () => { state.rootSelected = true; renderSelection("root"); });
    $("#threshold-input").addEventListener("input", updateReadiness);
    $("#start-detect").addEventListener("click", simulateRun);

    $("#inventory-state").addEventListener("change", (event) => setInventoryState(event.target.value));
    $("#rescan-button").addEventListener("click", () => {
      if (state.inventoryState === "missing") {
        $("#relink-card").hidden = false;
        $("#relink-confirm").focus();
      } else simulateScan();
    });
    $("#cancel-scan").addEventListener("click", () => { clearScanTimers(); setInventoryState("cancelled"); });
    $("#include-folder").addEventListener("click", () => setFolderDecision("Included"));
    $("#exclude-folder").addEventListener("click", () => setFolderDecision("Excluded"));
    $$(".tree-row").forEach((row) => row.addEventListener("click", () => {
      state.selectedInventory = row.dataset.folder ? { kind: "folder", key: row.dataset.folder } : { kind: "file", key: row.dataset.file };
      renderInventoryDetail();
    }));
    $("#relink-confirm").addEventListener("change", (event) => { $("#accept-relink").disabled = !event.target.checked; });
    $("#cancel-relink").addEventListener("click", () => { $("#relink-card").hidden = true; showToast("Proposed rebind cancelled. The missing folder remains unbound."); });
    $("#accept-relink").addEventListener("click", () => { state.rootSelected = true; $("#root-state").value = "loading"; renderSelection("root"); simulateScan(); showToast("New folder accepted for inventory comparison and rescan."); });

    $("#run-state").addEventListener("change", (event) => { clearRunTimers(); setRunState(event.target.value); });
    $("#cancel-run").addEventListener("click", () => { clearRunTimers(); setRunState("cancelling"); state.runTimers.push(setTimeout(() => setRunState("cancelled"), 650)); });
    $("#retry-run").addEventListener("click", simulateRun);

    $("#result-state").addEventListener("change", (event) => setResultView(event.target.value));
    $("#result-select").addEventListener("change", (event) => { state.result = event.target.value; renderResult(); });
    $("#interval-body").addEventListener("change", (event) => {
      if (!event.target.matches("input[data-interval]")) return;
      const artifact = state.result === "rf" && state.rfAvailable ? "rf" : "cnn";
      if (event.target.checked) state.selections[artifact].add(event.target.dataset.interval);
      else state.selections[artifact].delete(event.target.dataset.interval);
    });
    $("#show-source").addEventListener("click", () => showToast(`Source: /Volumes/Field/Rainforest_2026/recordings/${state.selectedRecording}`));
    $("#result-relink").addEventListener("click", () => { setInventoryState("missing"); setHash("detect/recordings"); });
    $("#rf-model").addEventListener("change", (event) => {
      const valid = event.target.value === "valid";
      $("#run-rf").disabled = !valid;
      $("#rf-error").hidden = event.target.value !== "invalid";
    });
    $("#run-rf").addEventListener("click", createRfResult);

    $$("input[name='export-format']").forEach((radio) => radio.addEventListener("change", (event) => updateExportFormat(event.target.value)));
    $("#choose-destination").addEventListener("click", () => {
      const value = "/Users/researcher/Exports/Rainforest-corpus";
      $("#destination-input").value = value;
      state.destination = value;
      $("#destination-summary").textContent = value;
      updateExportState("ready");
    });
    $("#destination-input").addEventListener("input", (event) => {
      state.destination = event.target.value.trim();
      $("#destination-summary").textContent = state.destination || "Not selected";
      updateExportState();
    });
    $("#export-state").addEventListener("change", (event) => {
      if (event.target.value === "success" && !$("#destination-input").value.trim()) {
        const value = "/Users/researcher/Exports/Rainforest-corpus";
        $("#destination-input").value = value;
        state.destination = value;
        $("#destination-summary").textContent = value;
      }
      updateExportState(event.target.value);
    });
    $("#start-export").addEventListener("click", () => {
      const button = $("#start-export");
      button.disabled = true;
      button.textContent = "Exporting…";
      setAlert($("#export-alert"), "info", "Preparing export", "Checking the frozen mapping and destination.");
      setTimeout(() => { button.textContent = "Export corpus"; updateExportState("success"); }, 850);
    });
    $("#show-output").addEventListener("click", () => showToast(`Export folder: ${state.destination}`));

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
    renderInventoryDetail();
    setResultView("populated");
    renderResult();
    freezeExportSelection();
    renderExport();
    navigate(location.hash.slice(1) || "studio");
  }

  window.__studioPrototype = {
    navigate,
    setRunState,
    setInventoryState,
    setResultView,
    renderResult,
    freezeExportSelection,
    updateExportState,
    state,
  };
  init();
})();
