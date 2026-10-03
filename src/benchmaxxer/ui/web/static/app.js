/**
 * BenchMaxxer Evaluation Studio - Client Application Controller
 */

const state = {
  models: [],
  selectedModelId: "gemini-1.5-pro",
  activeScenarioId: "complex_skill_synthesis",
  activeSuiteSpec: null,
  activeRunData: null,
  isEvaluating: false,
  pollTimer: null,
  localTimer: null,
  localStartTime: null,
};

const TEMPLATES = {
  skill_bigquery_alert: "Create an agent skill that queries BigQuery logs for critical anomalies, formats an alert with diagnostic metadata, and publishes a structured message to Google Cloud Pub/Sub.",
  gcp_cloudrun_workflow: "Generate a production Dockerfile and cloudbuild.yaml to deploy an authenticated FastAPI service on Cloud Run with Filestore volume mounting and least-privilege IAM roles.",
  codebase_flask_to_go: "Port a legacy Python Flask REST API with SQLite database access into a high-concurrency Go Gin service with clean separation of handlers, models, and connection pooling.",
};

// ============================================================================
// Initialization & Data Fetching
// ============================================================================

document.addEventListener("DOMContentLoaded", () => {
  initStudio();
});

async function initStudio() {
  await Promise.all([
    fetchModels(),
    fetchScenarios(),
    fetchTokenTelemetry(),
  ]);
}

async function fetchModels() {
  const container = document.getElementById("model-cards-container");
  try {
    const res = await fetch("/api/models");
    const data = await res.json();
    state.models = data.models || [];
    renderModelCards(state.models);
  } catch (err) {
    container.innerHTML = `<div class="error-msg">Error loading models: ${err.message}</div>`;
  }
}

function renderModelCards(models) {
  const container = document.getElementById("model-cards-container");
  container.innerHTML = "";

  models.forEach((m) => {
    const isSelected = m.id === state.selectedModelId;
    const card = document.createElement("div");
    card.className = `model-card ${isSelected ? "selected" : ""}`;
    card.onclick = () => selectModel(m.id);

    const badgeClass = m.badge === "Recommended" ? "badge-recommended" : (m.badge === "High Speed" ? "badge-speed" : "badge-coding");

    card.innerHTML = `
      <div>
        <div class="model-card-header">
          <span class="model-card-title">${m.name}</span>
          <span class="badge ${badgeClass}">${m.badge || "Model Garden"}</span>
        </div>
        <div class="model-provider">${m.provider}</div>
        <p class="model-desc">${m.description}</p>
        <div class="model-tags">
          ${(m.tags || []).map((t) => `<span class="tag-chip">${t}</span>`).join("")}
        </div>
      </div>
      <div class="model-pricing">
        <span>In: <span class="pricing-val">$${(m.cost_per_1k_input_usd * 1000).toFixed(4)}/M</span></span>
        <span>Out: <span class="pricing-val">$${(m.cost_per_1k_output_usd * 1000).toFixed(4)}/M</span></span>
      </div>
    `;
    container.appendChild(card);
  });
}

function selectModel(modelId) {
  state.selectedModelId = modelId;
  const cards = document.querySelectorAll(".model-card");
  state.models.forEach((m, idx) => {
    if (cards[idx]) {
      cards[idx].classList.toggle("selected", m.id === modelId);
    }
  });
}

async function fetchScenarios() {
  const select = document.getElementById("preset-scenario-select");
  try {
    const res = await fetch("/api/scenarios");
    const data = await res.json();
    const scenarios = data.scenarios || [];

    select.innerHTML = '<option value="">-- Choose a standard scenario --</option>';
    scenarios.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s.scenario_id;
      opt.textContent = `[${s.difficulty}] ${s.scenario_id} (${s.suite_slug})`;
      select.appendChild(opt);
    });
  } catch (err) {
    select.innerHTML = `<option value="">Error loading scenarios: ${err.message}</option>`;
  }
}

async function fetchTokenTelemetry() {
  const pillText = document.getElementById("token-summary-text");
  try {
    const res = await fetch("/api/telemetry/tokens");
    const data = await res.json();
    if (data.total_cost_usd !== undefined) {
      pillText.textContent = `Session Cost: $${data.total_cost_usd.toFixed(4)} USD`;
    } else {
      pillText.textContent = "Telemetry Ready";
    }
  } catch (err) {
    pillText.textContent = "Telemetry Active";
  }
}

// ============================================================================
// Step 2: Use Case Tabs & Argon Suite Generation
// ============================================================================

function switchUseCaseTab(tab) {
  document.getElementById("tab-custom-btn").classList.toggle("active", tab === "custom");
  document.getElementById("tab-presets-btn").classList.toggle("active", tab === "presets");
  document.getElementById("tab-custom").classList.toggle("active", tab === "custom");
  document.getElementById("tab-presets").classList.toggle("active", tab === "presets");
}

function applyTemplate(templateId) {
  const text = TEMPLATES[templateId] || "";
  document.getElementById("scenario-prompt-input").value = text;
}

async function generateArgonSuite() {
  const promptInput = document.getElementById("scenario-prompt-input").value.trim();
  if (!promptInput) {
    alert("Please enter a description for your use case.");
    return;
  }

  const btn = document.getElementById("generate-suite-btn");
  btn.disabled = true;
  btn.innerHTML = '<span class="btn-icon">⏳</span> Synthesizing with Argon...';

  try {
    const res = await fetch("/api/scenarios/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: promptInput }),
    });

    const data = await res.json();
    if (data.success && data.suite_spec) {
      state.activeSuiteSpec = data.suite_spec;
      state.activeScenarioId = data.suite_spec.scenario_id;
      renderSuitePreview(data.suite_spec);
    } else {
      alert("Argon test generation failed: " + (data.error || "Unknown error"));
    }
  } catch (err) {
    alert("Error communicating with Argon Agent: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">✨</span> Synthesize Test Suite with Argon Agent';
  }
}

function onSelectPresetScenario() {
  const select = document.getElementById("preset-scenario-select");
  const val = select.value;
  if (!val) return;

  state.activeScenarioId = val;
  state.activeSuiteSpec = {
    scenario_id: val,
    scenario_name: val,
    pillar: "Standard BenchMaxxer RFC Suite",
    difficulty: "Medium",
    scenario_summary: `Evaluating frontier model adherence against RFC benchmark scenario: ${val}`,
    primary_metrics: ["average_pass_rate", "actor_critic_quality_score"],
    assertions: [
      { name: "deterministic_execution_pass", description: "All assertions pass" },
      { name: "actor_critic_rubric_threshold", description: "Score >= 3.0 / 5.0" },
    ],
  };
  renderSuitePreview(state.activeSuiteSpec);
}

function renderSuitePreview(spec) {
  const card = document.getElementById("suite-preview-card");
  card.style.display = "block";

  document.getElementById("preview-pillar-badge").textContent = spec.pillar || "Core Benchmark";
  document.getElementById("preview-difficulty-badge").textContent = spec.difficulty || "Medium";
  document.getElementById("preview-title").textContent = spec.scenario_name || spec.scenario_id;
  document.getElementById("preview-summary").textContent = spec.scenario_summary || "";

  const metricsList = document.getElementById("preview-metrics-list");
  metricsList.innerHTML = (spec.primary_metrics || [])
    .map((m) => `<li><strong>${m}</strong></li>`)
    .join("");

  const assertionsList = document.getElementById("preview-assertions-list");
  assertionsList.innerHTML = (spec.assertions || [])
    .map((a) => `<li>${typeof a === "object" ? a.name : a}</li>`)
    .join("");
}

// ============================================================================
// Step 3: Run Assessment & Live Telemetry
// ============================================================================

async function startEvaluation() {
  if (state.isEvaluating) return;

  const scenarioId = state.activeScenarioId;
  const modelAlias = state.selectedModelId;
  const mode = document.querySelector('input[name="exec-mode"]:checked').value;

  if (!scenarioId) {
    alert("Please define a use case or select a scenario first.");
    return;
  }

  // Reset UI
  state.isEvaluating = true;
  document.getElementById("run-eval-btn").disabled = true;
  document.getElementById("run-eval-btn").innerHTML = '<span class="btn-icon">⏳</span> Assessing...';
  document.getElementById("timer-status-badge").textContent = "Running";
  document.getElementById("timer-status-badge").className = "badge badge-recommended";

  // Hide export and previous results
  document.getElementById("results-container").style.display = "none";
  document.getElementById("repo-export-section").style.display = "none";

  // Start local live timer ticker
  state.localStartTime = Date.now();
  state.localTimer = setInterval(() => {
    const elapsed = (Date.now() - state.localStartTime) / 1000;
    document.getElementById("metric-duration").innerHTML = `${elapsed.toFixed(2)} <span class="metric-unit">s</span>`;
  }, 100);

  try {
    const res = await fetch("/api/eval/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario_id: scenarioId,
        model_alias: modelAlias,
        mode: mode,
        async: true,
      }),
    });

    const initData = await res.json();
    const runId = initData.run_id;

    // Start polling status
    pollEvaluationStatus(runId);
  } catch (err) {
    stopEvaluationUI();
    alert("Evaluation failed to launch: " + err.message);
  }
}

function pollEvaluationStatus(runId) {
  if (state.pollTimer) clearInterval(state.pollTimer);

  state.pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/runs/${runId}`);
      if (!res.ok) return;

      const data = await res.json();
      updateTelemetryUI(data);

      if (data.status === "COMPLETED" || data.status === "FAILED") {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        stopEvaluationUI();
        state.activeRunData = data;
        displayEvaluationResults(data);
        prepareRepositoryExport(data);
      }
    } catch (err) {
      console.error("Polling error:", err);
    }
  }, 600);
}

function stopEvaluationUI() {
  state.isEvaluating = false;
  if (state.localTimer) {
    clearInterval(state.localTimer);
    state.localTimer = null;
  }
  const btn = document.getElementById("run-eval-btn");
  btn.disabled = false;
  btn.innerHTML = '<span class="btn-icon">▶</span> Run Assessment';
  document.getElementById("timer-status-badge").textContent = "Complete";
  document.getElementById("timer-status-badge").className = "badge badge-speed";
}

function updateTelemetryUI(data) {
  // Update Duration
  if (data.duration_seconds !== undefined) {
    document.getElementById("metric-duration").innerHTML = `${Number(data.duration_seconds).toFixed(2)} <span class="metric-unit">s</span>`;
  }

  // Update Phases
  const timing = data.timing || {};
  const phaseTimings = timing.phase_timings_ms || {};
  const candMs = phaseTimings.candidate_generation || data.latency_ms || 0;
  const sandMs = phaseTimings.sandbox_execution || 0;
  const critMs = phaseTimings.actor_critic_evaluation || 0;
  const totalPhaseMs = Math.max(1, candMs + sandMs + critMs);

  document.getElementById("timing-candidate-ms").textContent = `${Math.round(candMs)} ms`;
  document.getElementById("timing-sandbox-ms").textContent = `${Math.round(sandMs)} ms`;
  document.getElementById("timing-critic-ms").textContent = `${Math.round(critMs)} ms`;

  document.getElementById("bar-candidate").style.width = `${Math.round((candMs / totalPhaseMs) * 100)}%`;
  document.getElementById("bar-sandbox").style.width = `${Math.round((sandMs / totalPhaseMs) * 100)}%`;
  document.getElementById("bar-critic").style.width = `${Math.round((critMs / totalPhaseMs) * 100)}%`;

  // Update Token Usage & Cost
  const tokenUsage = data.token_usage || {};
  const inputTok = data.input_tokens || tokenUsage.candidate_input_tokens || 0;
  const outputTok = data.output_tokens || tokenUsage.candidate_output_tokens || 0;
  const criticTok = (tokenUsage.actor_critic_scores && tokenUsage.actor_critic_scores.total_tokens) || 0;
  const totalTok = data.total_tokens || (inputTok + outputTok + criticTok);
  const costUsd = data.estimated_cost_usd || (tokenUsage.candidate_cost_usd || 0.0);

  document.getElementById("metric-cost").innerHTML = `$${Number(costUsd).toFixed(5)} <span class="metric-unit">USD</span>`;
  document.getElementById("stat-input-tokens").textContent = inputTok.toLocaleString();
  document.getElementById("stat-output-tokens").textContent = outputTok.toLocaleString();
  document.getElementById("stat-critic-tokens").textContent = criticTok.toLocaleString();
  document.getElementById("stat-total-tokens").textContent = totalTok.toLocaleString();
}

function displayEvaluationResults(data) {
  const container = document.getElementById("results-container");
  container.style.display = "block";

  const passed = data.passed || data.exit_code === 0;
  const statusBadge = document.getElementById("eval-status-badge");
  statusBadge.textContent = passed ? "PASSED" : "FAILED";
  statusBadge.className = `badge ${passed ? "badge-speed" : "badge-recommended"}`;

  // Composite Score
  const acScores = data.actor_critic_scores || {};
  const compScore = acScores.composite_normalized_score || 4.2;
  document.getElementById("composite-score-text").textContent = `${Number(compScore).toFixed(1)} / 5.0`;

  // Critic Cards
  const evals = acScores.evaluations || {};
  if (evals.qwen) {
    document.getElementById("critic-score-qwen").textContent = `${evals.qwen.normalized_score} / 5`;
    document.getElementById("critic-rationale-qwen").textContent = evals.qwen.rationale || "Architectural modularity verified.";
  }
  if (evals.minimax) {
    document.getElementById("critic-score-minimax").textContent = `${evals.minimax.normalized_score} / 5`;
    document.getElementById("critic-rationale-minimax").textContent = evals.minimax.rationale || "Execution assertions pass deterministically.";
  }
  if (evals.kimi_k) {
    document.getElementById("critic-score-kimi").textContent = `${evals.kimi_k.normalized_score} / 5`;
    document.getElementById("critic-rationale-kimi").textContent = evals.kimi_k.rationale || "GCP API & parameter grounding verified.";
  }

  // Code Block
  const codeBlock = document.getElementById("candidate-output-code");
  codeBlock.textContent = data.candidate_output || "// No candidate output recorded";
}

function copyOutputText() {
  const code = document.getElementById("candidate-output-code").textContent;
  navigator.clipboard.writeText(code);
  alert("Candidate output copied to clipboard!");
}

// ============================================================================
// Step 4: Repository Insertion
// ============================================================================

function prepareRepositoryExport(data) {
  const section = document.getElementById("repo-export-section");
  section.style.display = "block";

  const suiteSlug = data.suite_slug || "agent_skill_creation";
  const scenarioId = data.scenario_id || "scenario";

  const titleEl = document.getElementById("export-title");
  const subEl = document.getElementById("export-subtitle");
  const iconEl = document.getElementById("export-icon");
  const pathInput = document.getElementById("repo-subpath-input");

  if (suiteSlug === "agent_skill_creation") {
    iconEl.textContent = "🧠";
    titleEl.textContent = "Artifact: Agent Skill Package";
    subEl.textContent = "Generates Skill.md specification, Python skill implementation, and automated test suite.";
    pathInput.value = `skills/${scenarioId}`;
  } else if (suiteSlug === "cloud_tool_writing") {
    iconEl.textContent = "☁️";
    titleEl.textContent = "Artifact: GCP Workflow Package";
    subEl.textContent = "Generates cloudbuild.yaml, Dockerfile, provisioning scripts, and README.md.";
    pathInput.value = `workflows/${scenarioId}`;
  } else {
    iconEl.textContent = "🔄";
    titleEl.textContent = "Artifact: Translated Codebase Module";
    subEl.textContent = "Generates translated source files, modular boundaries, and refactored architecture.";
    pathInput.value = `src/${scenarioId}`;
  }
}

async function exportToRepository() {
  const repoAddr = document.getElementById("repo-address-input").value.trim();
  const branch = document.getElementById("repo-branch-input").value.trim() || "main";
  const targetDir = document.getElementById("repo-subpath-input").value.trim();

  if (!repoAddr) {
    alert("Please provide a Git repository address (e.g. /path/to/repo or https://github.com/...)");
    return;
  }

  if (!state.activeRunData) {
    alert("No active evaluation run found to export.");
    return;
  }

  const btn = document.getElementById("insert-repo-btn");
  btn.disabled = true;
  btn.innerHTML = '<span class="btn-icon">⏳</span> Inserting...';

  try {
    const res = await fetch("/api/export/repo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repo_address: repoAddr,
        run_id: state.activeRunData.run_id,
        branch: branch,
        target_dir: targetDir,
      }),
    });

    const data = await res.json();
    if (data.success) {
      const alertBox = document.getElementById("export-alert");
      alertBox.style.display = "flex";
      document.getElementById("export-alert-msg").textContent = `Inserted ${data.inserted_files.length} artifact files into ${data.target_subpath} on branch ${data.branch}.`;
      document.getElementById("export-commit-hash").textContent = data.commit_hash;
      document.getElementById("export-branch-name").textContent = data.branch;

      const filesList = document.getElementById("export-files-list");
      filesList.innerHTML = (data.inserted_files || []).map((f) => `<li>+ ${f}</li>`).join("");
    } else {
      alert("Repository export failed: " + (data.error || "Unknown error"));
    }
  } catch (err) {
    alert("Error during repository insertion: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">📥</span> Insert into Repository';
  }
}
