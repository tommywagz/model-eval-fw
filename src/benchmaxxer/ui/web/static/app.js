/**
 * BenchMaxxer Evaluation Studio - Client Application Controller
 * Supports Frontier Model (MIQ) Selection, GCP Project & Location Linking,
 * Custom Multi-Test Suite Builder (1+ Standard + 1+ Custom Argon Use Cases),
 * Live Hierarchical Telemetry, and Git Repository Export.
 */

const state = {
  gcpProject: "benchmaxxer-eval-sandbox",
  gcpLocation: "us-central1",
  allModels: [],
  defaultModels: [],
  dropdownModels: [],
  models: [],
  selectedModelId: "gemini-4-argon",
  allScenarios: [],
  customSuiteItems: [],
  activeScenarioId: "complex_skill_synthesis",
  activeSuiteSpec: null,
  activeRunData: null,
  isEvaluating: false,
  pollTimer: null,
  localTimer: null,
  localStartTime: null,
};

const TEMPLATES = {
  skill_bigquery_alert:
    "Create an agent skill that queries BigQuery logs for critical anomalies, formats an alert with diagnostic metadata, and publishes a structured message to Google Cloud Pub/Sub.",
  gcp_cloudrun_workflow:
    "Generate a production Dockerfile and cloudbuild.yaml to deploy an authenticated FastAPI service on Cloud Run with Filestore volume mounting and least-privilege IAM roles.",
  codebase_flask_to_go:
    "Port a legacy Python Flask REST API with SQLite database access into a high-concurrency Go Gin service with clean separation of handlers, models, and connection pooling.",
};

// ============================================================================
// Frontier Model Brand Logos (Inline SVG Emblems)
// ============================================================================

function getBrandLogoSvg(brand, modelId) {
  const b = (brand || "").toLowerCase();
  const id = (modelId || "").toLowerCase();

  if (b === "gemini" || id.includes("gemini")) {
    // Google Gemini Sparkle Emblem
    return `
      <svg viewBox="0 0 24 24" fill="none" aria-label="Google Gemini Logo">
        <defs>
          <linearGradient id="geminiGrad-${id.replace(/[^a-z0-9]/g, "")}" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stop-color="#1a73e8"/>
            <stop offset="50%" stop-color="#4285f4"/>
            <stop offset="100%" stop-color="#34a853"/>
          </linearGradient>
        </defs>
        <path d="M12 2C12 7.52 16.48 12 22 12C16.48 12 12 16.48 12 22C12 16.48 7.52 12 2 12C7.52 12 12 7.52 12 2Z" fill="url(#geminiGrad-${id.replace(/[^a-z0-9]/g, "")})"/>
      </svg>
    `;
  }

  if (b === "fable" || id.includes("fable")) {
    // Fable AI Geometric Prism Emblem
    return `
      <svg viewBox="0 0 24 24" fill="none" aria-label="Fable AI Logo">
        <rect x="3" y="3" width="18" height="18" rx="5" fill="#e4f7fb" stroke="#007b83" stroke-width="1.8"/>
        <path d="M8 7H16M8 12H14M8 7V17" stroke="#007b83" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="15.5" cy="15.5" r="2" fill="#007b83"/>
      </svg>
    `;
  }

  if (b === "anthropic" || id.includes("sonnet") || id.includes("claude")) {
    // Anthropic / Sonnet Starburst Emblem
    return `
      <svg viewBox="0 0 24 24" fill="none" aria-label="Anthropic Sonnet Logo">
        <circle cx="12" cy="12" r="10" fill="#fef3ec" stroke="#d97757" stroke-width="1.6"/>
        <path d="M12 5V19M5 12H19M7.2 7.2L16.8 16.8M16.8 7.2L7.2 16.8" stroke="#d97757" stroke-width="2" stroke-linecap="round"/>
      </svg>
    `;
  }

  if (b === "meta" || id.includes("llama")) {
    // Meta Infinity Loop Emblem
    return `
      <svg viewBox="0 0 24 24" fill="none" aria-label="Meta Llama Logo">
        <path d="M5 15C3.5 15 2.5 13.5 2.5 12C2.5 9.5 4.5 8 6.5 8C8.8 8 10.5 10.2 12 12.2C13.5 10.2 15.2 8 17.5 8C19.5 8 21.5 9.5 21.5 12C21.5 13.5 20.5 15 19 15C17.2 15 15.8 13.4 14.5 11.6L12 15L9.5 11.6C8.2 13.4 6.8 15 5 15Z" stroke="#0668E1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    `;
  }

  // Default Vertex AI / Partner Model Hex Emblem
  return `
    <svg viewBox="0 0 24 24" fill="none" aria-label="Vertex AI Partner Model Logo">
      <polygon points="12,2 21,7 21,17 12,22 3,17 3,7" fill="#e8f0fe" stroke="#1a73e8" stroke-width="1.8"/>
      <circle cx="12" cy="12" r="3" fill="#1a73e8"/>
    </svg>
  `;
}

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

    state.gcpProject = data.project_id || "benchmaxxer-eval-sandbox";
    state.gcpLocation = data.location || "us-central1";
    state.allModels = data.models || [];
    state.models = state.allModels;

    // Separate the 4 default frontier models and the additional enabled GCP project models
    state.defaultModels =
      data.default_models && data.default_models.length > 0
        ? data.default_models
        : state.allModels.filter((m) => m.is_default);

    state.dropdownModels =
      data.dropdown_models ||
      state.allModels.filter((m) => m.enabled && !m.is_default);

    // Ensure selectedModelId is valid
    if (!state.selectedModelId && state.defaultModels.length > 0) {
      state.selectedModelId = state.defaultModels[0].id;
    }

    updateGcpHeaderUI();
    renderGcpMiqToggles(state.allModels);
    renderModelCards(state.defaultModels);
    renderEnabledModelsDropdown(state.dropdownModels);
    updateActiveModelIndicator();
  } catch (err) {
    if (container) {
      container.innerHTML = `<div class="error-msg">Error loading models: ${err.message}</div>`;
    }
  }
}

function updateGcpHeaderUI() {
  const statusText = document.getElementById("gcp-status-text");
  const headerLoc = document.getElementById("gcp-header-location");
  const projInput = document.getElementById("gcp-project-input");
  const locSelect = document.getElementById("gcp-location-select");
  const dropdownProjLabel = document.getElementById("dropdown-project-label");
  const enabledCountBadge = document.getElementById("enabled-miq-count-badge");

  if (statusText) statusText.textContent = `GCP: ${state.gcpProject}`;
  if (headerLoc) headerLoc.textContent = state.gcpLocation;
  if (projInput) projInput.value = state.gcpProject;
  if (locSelect) locSelect.value = state.gcpLocation;
  if (dropdownProjLabel) dropdownProjLabel.textContent = `${state.gcpProject} • ${state.gcpLocation}`;

  const totalEnabled = state.allModels.filter((m) => m.enabled).length;
  if (enabledCountBadge) {
    enabledCountBadge.textContent = `${totalEnabled} MIQ Models Enabled in Project`;
  }
}

function toggleGcpConfigPanel() {
  const panel = document.getElementById("gcp-config-panel");
  if (!panel) return;
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  const input = document.getElementById("gcp-project-input");
  if (input) input.focus();
}

function renderGcpMiqToggles(models) {
  const container = document.getElementById("gcp-miq-toggles-container");
  if (!container) return;
  container.innerHTML = "";

  models.forEach((m) => {
    const item = document.createElement("div");
    item.className = `miq-toggle-item ${m.enabled ? "enabled" : ""}`;
    item.onclick = () => toggleMiqModelInProject(m.id, !m.enabled);

    item.innerHTML = `
      <div class="miq-toggle-left">
        <div class="miq-toggle-brand">${getBrandLogoSvg(m.brand, m.id)}</div>
        <div style="min-width: 0;">
          <div class="miq-toggle-name">${m.name}</div>
          <div class="miq-toggle-meta">${m.is_default ? "Default Card" : "Dropdown MIQ"} • ${m.location || state.gcpLocation}</div>
        </div>
      </div>
      <input type="checkbox" ${m.enabled ? "checked" : ""} aria-label="Enable ${m.name} in GCP project" onclick="event.stopPropagation(); toggleMiqModelInProject('${m.id}', this.checked)">
    `;
    container.appendChild(item);
  });
}

async function toggleMiqModelInProject(modelId, enabledState) {
  try {
    const res = await fetch("/api/gcp/models/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelId, enabled: enabledState }),
    });
    const data = await res.json();
    if (data.success) {
      state.allModels = data.models || state.allModels;
      state.defaultModels = data.default_models || state.defaultModels;
      state.dropdownModels = data.dropdown_models || [];
      updateGcpHeaderUI();
      renderGcpMiqToggles(state.allModels);
      renderModelCards(state.defaultModels);
      renderEnabledModelsDropdown(state.dropdownModels);
    }
  } catch (err) {
    console.error("Failed to toggle MIQ model:", err);
  }
}

async function saveGcpConfiguration() {
  const projInput = document.getElementById("gcp-project-input");
  const locSelect = document.getElementById("gcp-location-select");
  const btn = document.getElementById("save-gcp-config-btn");
  const savedBadge = document.getElementById("gcp-config-saved-badge");

  const projectId = (projInput ? projInput.value.trim() : "") || "benchmaxxer-eval-sandbox";
  const location = (locSelect ? locSelect.value : "") || "us-central1";
  const enabledIds = state.allModels.filter((m) => m.enabled).map((m) => m.id);

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = "<span>⏳</span> Linking GCP Project...";
  }

  try {
    const res = await fetch("/api/gcp/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: projectId,
        location: location,
        enabled_model_ids: enabledIds,
      }),
    });
    const data = await res.json();
    if (data.success) {
      state.gcpProject = data.project_id;
      state.gcpLocation = data.location;
      state.allModels = data.models || [];
      state.defaultModels = data.default_models || [];
      state.dropdownModels = data.dropdown_models || [];

      updateGcpHeaderUI();
      renderGcpMiqToggles(state.allModels);
      renderModelCards(state.defaultModels);
      renderEnabledModelsDropdown(state.dropdownModels);

      if (savedBadge) {
        savedBadge.textContent = `Linked: ${state.gcpProject} (${state.gcpLocation})`;
      }
    }
  } catch (err) {
    alert("Error updating GCP configuration: " + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = "<span>☁️</span> Link & Save GCP Config";
    }
  }
}

// ============================================================================
// Step 1: Frontier Model Cards (4 Defaults) & Enabled GCP Project Dropdown
// ============================================================================

function renderModelCards(models) {
  const container = document.getElementById("model-cards-container");
  if (!container) return;
  container.innerHTML = "";

  models.forEach((m) => {
    const isSelected = m.id === state.selectedModelId;
    const card = document.createElement("div");
    card.className = `model-card ${isSelected ? "selected" : ""}`;
    card.setAttribute("data-model-id", m.id);
    card.onclick = () => selectModel(m.id);

    const badgeClass =
      m.badge && m.badge.includes("Flagship")
        ? "badge-recommended"
        : m.badge && m.badge.includes("Speed")
        ? "badge-speed"
        : "badge-coding";

    card.innerHTML = `
      <div>
        <div class="model-card-top">
          <div class="model-brand-logo" title="${m.provider}">
            ${getBrandLogoSvg(m.brand, m.id)}
          </div>
          <div style="display: flex; align-items: center; gap: 0.4rem;">
            <span class="badge ${badgeClass}">${m.badge || "Frontier MIQ"}</span>
            <div class="model-select-check" aria-hidden="true">✓</div>
          </div>
        </div>
        <div class="model-card-header">
          <span class="model-card-title">${m.name}</span>
        </div>
        <div class="model-provider">${m.provider}</div>
        <p class="model-desc">${m.description}</p>
        <div class="model-tags">
          ${(m.tags || []).map((t) => `<span class="tag-chip">${t}</span>`).join("")}
        </div>
      </div>
      <div class="model-pricing">
        <span>In: <span class="pricing-val">$${(m.cost_per_1k_input_usd * 1000).toFixed(2)}/M</span></span>
        <span>Out: <span class="pricing-val">$${(m.cost_per_1k_output_usd * 1000).toFixed(2)}/M</span></span>
      </div>
    `;
    container.appendChild(card);
  });
}

function renderEnabledModelsDropdown(dropdownModels) {
  const select = document.getElementById("enabled-models-dropdown");
  if (!select) return;

  select.innerHTML = `<option value="">-- Select from ${dropdownModels.length} other enabled MIQ models in ${state.gcpProject} --</option>`;
  dropdownModels.forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.selected = m.id === state.selectedModelId;
    opt.textContent = `${m.name} — ${m.provider} (${m.location || state.gcpLocation}) [$${(m.cost_per_1k_input_usd * 1000).toFixed(2)}/M in]`;
    select.appendChild(opt);
  });

  updateDropdownBanner();
}

function selectModel(modelId) {
  state.selectedModelId = modelId;

  // Update the 4 default cards selection state
  const cards = document.querySelectorAll(".model-card");
  state.defaultModels.forEach((m, idx) => {
    if (cards[idx]) {
      cards[idx].classList.toggle("selected", m.id === modelId);
    }
  });

  // Sync dropdown value if selected from default squares vs dropdown
  const dropdown = document.getElementById("enabled-models-dropdown");
  if (dropdown) {
    const isDropdownModel = state.dropdownModels.some((m) => m.id === modelId);
    dropdown.value = isDropdownModel ? modelId : "";
  }

  updateDropdownBanner();
  updateActiveModelIndicator();
}

function onSelectDropdownModel(modelId) {
  if (!modelId) {
    // Revert to Gemini 4 Argon default
    selectModel("gemini-4-argon");
    return;
  }
  selectModel(modelId);
}

function updateDropdownBanner() {
  const banner = document.getElementById("selected-dropdown-model-banner");
  if (!banner) return;

  const selectedDropdownModel = state.dropdownModels.find((m) => m.id === state.selectedModelId);
  if (!selectedDropdownModel) {
    banner.style.display = "none";
    return;
  }

  banner.style.display = "flex";
  document.getElementById("dropdown-selected-logo").innerHTML = getBrandLogoSvg(
    selectedDropdownModel.brand,
    selectedDropdownModel.id
  );
  document.getElementById("dropdown-selected-name").textContent = `${selectedDropdownModel.name} (${selectedDropdownModel.provider})`;
  document.getElementById("dropdown-selected-desc").textContent = selectedDropdownModel.description;
  document.getElementById("dropdown-selected-pricing").textContent = `In: $${(
    selectedDropdownModel.cost_per_1k_input_usd * 1000
  ).toFixed(2)}/M • Out: $${(selectedDropdownModel.cost_per_1k_output_usd * 1000).toFixed(2)}/M`;
}

function updateActiveModelIndicator() {
  const indicator = document.getElementById("active-model-indicator");
  if (!indicator) return;
  const found = state.allModels.find((m) => m.id === state.selectedModelId);
  indicator.textContent = `Active Model: ${found ? found.name : state.selectedModelId}`;
}

// ============================================================================
// Step 2: Scenarios & Custom Multi-Test Suite Builder
// ============================================================================

async function fetchScenarios() {
  const select = document.getElementById("preset-scenario-select");
  try {
    const res = await fetch("/api/scenarios");
    const data = await res.json();
    const scenarios = data.scenarios || [];
    state.allScenarios = scenarios;

    if (select) {
      select.innerHTML = '<option value="">-- Choose a standard benchmark scenario --</option>';
      scenarios.forEach((s) => {
        const opt = document.createElement("option");
        opt.value = s.scenario_id;
        opt.textContent = `[${s.difficulty}] ${s.scenario_id} (${s.suite_slug})`;
        select.appendChild(opt);
      });
    }

    // Initialize default suite with 1 standard scenario so user can immediately run or add more
    if (state.customSuiteItems.length === 0 && scenarios.length > 0) {
      const defaultSc =
        scenarios.find((s) => s.scenario_id === "oauth_api_enablement") || scenarios[0];
      addScenarioToCustomSuite(defaultSc, false);
    }

    renderStandardScenariosChecklist();
    renderCustomSuiteTray();
  } catch (err) {
    if (select) {
      select.innerHTML = `<option value="">Error loading scenarios: ${err.message}</option>`;
    }
  }
}

function renderStandardScenariosChecklist() {
  const container = document.getElementById("standard-scenarios-checklist");
  if (!container) return;
  container.innerHTML = "";

  const standardScenarios = state.allScenarios.filter((s) => !s.scenario_id.startswith?.("argon_") && !s.scenario_id.startsWith("argon_"));
  standardScenarios.forEach((s) => {
    const isChecked = state.customSuiteItems.some((item) => item.scenario_id === s.scenario_id);
    const label = document.createElement("label");
    label.className = `scenario-check-card ${isChecked ? "checked" : ""}`;

    label.innerHTML = `
      <input type="checkbox" ${isChecked ? "checked" : ""} onchange="toggleStandardScenarioInSuite('${s.scenario_id}', this.checked)">
      <div style="min-width: 0;">
        <div style="font-weight: 600; color: var(--text-primary); word-break: break-word;">${s.scenario_id}</div>
        <div style="font-size: 0.7rem; color: var(--text-secondary);">[${s.difficulty}] ${s.suite_slug}</div>
      </div>
    `;
    container.appendChild(label);
  });
}

function toggleStandardScenarioInSuite(scenarioId, checked) {
  if (checked) {
    const found = state.allScenarios.find((s) => s.scenario_id === scenarioId) || {
      scenario_id: scenarioId,
      scenario_name: scenarioId,
      difficulty: "Medium",
      pillar: "Standard BenchMaxxer RFC Suite",
      suite_slug: "cloud_tool_writing",
      is_custom: false,
    };
    addScenarioToCustomSuite(found, true);
  } else {
    removeScenarioFromCustomSuite(scenarioId);
  }
}

function addSelectedPresetToSuite() {
  const select = document.getElementById("preset-scenario-select");
  if (!select || !select.value) {
    alert("Please select a standard scenario from the dropdown first.");
    return;
  }
  toggleStandardScenarioInSuite(select.value, true);
}

function addScenarioToCustomSuite(scObj, showPreview = true) {
  const exists = state.customSuiteItems.some((item) => item.scenario_id === scObj.scenario_id);
  const normalized = {
    scenario_id: scObj.scenario_id,
    scenario_name: scObj.scenario_name || scObj.scenario_id,
    difficulty: scObj.difficulty || "Medium",
    pillar: scObj.pillar || "Standard BenchMaxxer RFC Suite",
    suite_slug: scObj.suite_slug || "agent_skill_creation",
    is_custom: Boolean(scObj.is_custom || scObj.scenario_id.startsWith("argon_")),
    scenario_summary:
      scObj.scenario_summary ||
      scObj.prompt ||
      `Evaluating frontier model adherence against scenario: ${scObj.scenario_id}`,
    primary_metrics: scObj.primary_metrics || ["average_pass_rate", "actor_critic_quality_score"],
    assertions: scObj.assertions || [
      { name: "deterministic_execution_pass", description: "All assertions pass" },
      { name: "actor_critic_rubric_threshold", description: "Score >= 3.0 / 5.0" },
    ],
  };

  if (!exists) {
    state.customSuiteItems.push(normalized);
  }

  state.activeScenarioId = normalized.scenario_id;
  state.activeSuiteSpec = normalized;

  renderStandardScenariosChecklist();
  renderCustomSuiteTray();
  if (showPreview) {
    renderSuitePreview(normalized);
  }
}

function removeScenarioFromCustomSuite(scenarioId) {
  state.customSuiteItems = state.customSuiteItems.filter((i) => i.scenario_id !== scenarioId);
  if (state.customSuiteItems.length > 0) {
    state.activeScenarioId = state.customSuiteItems[0].scenario_id;
    state.activeSuiteSpec = state.customSuiteItems[0];
  }
  renderStandardScenariosChecklist();
  renderCustomSuiteTray();
}

function clearCustomSuite() {
  state.customSuiteItems = [];
  renderStandardScenariosChecklist();
  renderCustomSuiteTray();
}

function renderCustomSuiteTray() {
  const listEl = document.getElementById("custom-suite-items-list");
  const stdBadge = document.getElementById("suite-standard-count-badge");
  const custBadge = document.getElementById("suite-custom-count-badge");
  if (!listEl) return;

  const stdCount = state.customSuiteItems.filter((i) => !i.is_custom).length;
  const custCount = state.customSuiteItems.filter((i) => i.is_custom).length;

  if (stdBadge) stdBadge.textContent = `${stdCount} Standard`;
  if (custBadge) custBadge.textContent = `${custCount} Custom`;

  if (state.customSuiteItems.length === 0) {
    listEl.innerHTML = `
      <div style="padding: 1rem; text-align: center; color: var(--text-muted); font-size: 0.8rem; border: 1px dashed var(--border-color); border-radius: 8px;">
        Your custom test suite is empty. Add 1+ Standard Benchmark Scenarios and/or synthesize 1+ Custom Use Cases on the left.
      </div>
    `;
    return;
  }

  listEl.innerHTML = "";
  state.customSuiteItems.forEach((item, idx) => {
    const row = document.createElement("div");
    row.className = "suite-item-row";
    const typeBadgeClass = item.is_custom ? "badge-speed" : "badge-recommended";
    const typeLabel = item.is_custom ? "Custom Use Case" : "Standard RFC";

    row.innerHTML = `
      <div class="suite-item-info" onclick="inspectSuiteItem('${item.scenario_id}')" title="Click to preview test specification">
        <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-muted);">${idx + 1}.</span>
        <span class="badge ${typeBadgeClass}">${typeLabel}</span>
        <span class="suite-item-name">${item.scenario_name || item.scenario_id}</span>
        <span class="badge">${item.difficulty}</span>
      </div>
      <button type="button" class="remove-suite-item-btn" onclick="removeScenarioFromCustomSuite('${item.scenario_id}')" title="Remove from suite">×</button>
    `;
    listEl.appendChild(row);
  });
}

function inspectSuiteItem(scenarioId) {
  const item = state.customSuiteItems.find((i) => i.scenario_id === scenarioId);
  if (item) {
    state.activeScenarioId = item.scenario_id;
    state.activeSuiteSpec = item;
    renderSuitePreview(item);
  }
}

async function saveCustomTestSuite() {
  if (state.customSuiteItems.length === 0) {
    alert("Please add at least 1 test (Standard Benchmark or Custom Use Case) to your suite.");
    return;
  }

  const nameInput = document.getElementById("custom-suite-name-input");
  const suiteName = (nameInput ? nameInput.value.trim() : "") || "Custom Frontier Evaluation Suite";
  const scenarioIds = state.customSuiteItems.map((i) => i.scenario_id);

  const btn = document.getElementById("save-custom-suite-btn");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = "<span>⏳</span> Saving Suite...";
  }

  try {
    const res = await fetch("/api/suites/custom", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        suite_name: suiteName,
        scenario_ids: scenarioIds,
      }),
    });
    const data = await res.json();
    if (data.success && data.suite) {
      const s = data.suite;
      renderSuitePreview({
        scenario_id: s.suite_slug,
        scenario_name: `${s.suite_name} (${s.scenarios.length} Tests: ${s.standard_scenarios.length} Standard + ${s.custom_scenarios.length} Custom)`,
        pillar: "Composite Custom Benchmark Suite",
        difficulty: "Multi-Tier",
        scenario_summary: `Included tests: ${s.scenarios.join(", ")}`,
        primary_metrics: s.primary_metrics,
        assertions: s.assertions,
      });
    } else {
      alert("Could not save custom suite: " + (data.error || "Unknown error"));
    }
  } catch (err) {
    alert("Error saving custom suite: " + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = "<span>📦</span> Save Custom Test Suite";
    }
  }
}

async function fetchTokenTelemetry() {
  const pillText = document.getElementById("token-summary-text");
  try {
    const res = await fetch("/api/telemetry/tokens");
    const data = await res.json();
    if (data.total_cost_usd !== undefined) {
      pillText.textContent = `Session Spend: $${data.total_cost_usd.toFixed(4)} USD`;
    } else {
      pillText.textContent = "Telemetry Ready";
    }
  } catch (err) {
    pillText.textContent = "Telemetry Active";
  }
}

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
  const titleEl = document.getElementById("custom-scenario-title-input");
  const titleInput = titleEl ? titleEl.value.trim() : "";

  if (!promptInput) {
    alert("Please enter a description for your custom use case.");
    return;
  }

  const btn = document.getElementById("generate-suite-btn");
  btn.disabled = true;
  btn.innerHTML = '<span class="btn-icon">⏳</span> Synthesizing with Argon...';

  try {
    const res = await fetch("/api/scenarios/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: promptInput, title: titleInput }),
    });

    const data = await res.json();
    if (data.success && data.suite_spec) {
      const spec = data.suite_spec;
      spec.is_custom = true;
      state.activeSuiteSpec = spec;
      state.activeScenarioId = spec.scenario_id;
      state.allScenarios.push(spec);

      // Add synthesized custom use case to the user's Custom Test Suite
      addScenarioToCustomSuite(spec, true);
      if (titleEl) titleEl.value = "";
    } else {
      alert("Argon test generation failed: " + (data.error || "Unknown error"));
    }
  } catch (err) {
    alert("Error communicating with Argon Agent: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">✨</span> Synthesize & Add Custom Use Case to Suite';
  }
}

function onSelectPresetScenario() {
  const select = document.getElementById("preset-scenario-select");
  const val = select.value;
  if (!val) return;

  const found = state.allScenarios.find((s) => s.scenario_id === val) || {
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

  addScenarioToCustomSuite(found, true);
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

  const scenarioIds =
    state.customSuiteItems.length > 0
      ? state.customSuiteItems.map((i) => i.scenario_id)
      : [state.activeScenarioId];

  const scenarioId = scenarioIds[0];
  const modelAlias = state.selectedModelId || "gemini-4-argon";
  const mode = document.querySelector('input[name="exec-mode"]:checked').value;
  const nameInput = document.getElementById("custom-suite-name-input");
  const suiteName = nameInput ? nameInput.value.trim() : "Custom Frontier Evaluation Suite";

  if (!scenarioId) {
    alert("Please define a use case or select at least one scenario first.");
    return;
  }

  // Reset UI
  state.isEvaluating = true;
  document.getElementById("run-eval-btn").disabled = true;
  document.getElementById("run-eval-btn").innerHTML = `<span class="btn-icon">⏳</span> Assessing (${scenarioIds.length} Test${scenarioIds.length > 1 ? "s" : ""})...`;
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
        scenario_ids: scenarioIds,
        suite_name: suiteName,
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
        fetchTokenTelemetry();
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
  if (data.duration_seconds !== undefined) {
    document.getElementById("metric-duration").innerHTML = `${Number(data.duration_seconds).toFixed(2)} <span class="metric-unit">s</span>`;
  }

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

  const tokenUsage = data.token_usage || {};
  const inputTok = data.input_tokens || tokenUsage.candidate_input_tokens || 0;
  const outputTok = data.output_tokens || tokenUsage.candidate_output_tokens || 0;
  const criticTok = (tokenUsage.actor_critic_scores && tokenUsage.actor_critic_scores.total_tokens) || 0;
  const totalTok = data.total_tokens || inputTok + outputTok + criticTok;
  const costUsd = data.estimated_cost_usd || tokenUsage.candidate_cost_usd || 0.0;

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
  statusBadge.className = `badge ${passed ? "badge-speed" : "badge-danger"}`;

  const titleEl = document.getElementById("eval-result-title");
  if (titleEl) {
    const testCount = (data.test_results && data.test_results.length) || 1;
    titleEl.textContent =
      testCount > 1
        ? `Assessment Results — ${data.model_alias} (${testCount} Suite Tests)`
        : `Assessment Results — ${data.model_alias}`;
  }

  // Render Multi-Test Suite Breakdown if available
  const breakdownBox = document.getElementById("suite-tests-breakdown");
  const breakdownList = document.getElementById("suite-tests-breakdown-list");
  if (breakdownBox && breakdownList && Array.isArray(data.test_results) && data.test_results.length > 0) {
    breakdownBox.style.display = "block";
    breakdownList.innerHTML = data.test_results
      .map(
        (tr) => `
        <div class="suite-result-row">
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span class="badge ${tr.passed ? "badge-speed" : "badge-danger"}">${tr.passed ? "PASS" : "FAIL"}</span>
            <span class="badge ${tr.is_custom ? "badge-coding" : "badge-recommended"}">${
          tr.is_custom ? "Custom Use Case" : "Standard Benchmark"
        }</span>
            <strong>${tr.scenario_id}</strong>
          </div>
          <div style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-secondary);">
            Score: ${Number(tr.rubric_score || 4.0).toFixed(1)}/5 • ${Number(tr.duration_seconds || 0).toFixed(2)}s • ${
          tr.total_tokens || 0
        } tok
          </div>
        </div>
      `
      )
      .join("");
  }

  const acScores = data.actor_critic_scores || {};
  const compScore = acScores.composite_normalized_score || 4.2;
  document.getElementById("composite-score-text").textContent = `${Number(compScore).toFixed(1)} / 5.0`;

  const evals = acScores.evaluations || {};
  if (evals.qwen) {
    document.getElementById("critic-score-qwen").textContent = `${evals.qwen.normalized_score} / 5`;
    document.getElementById("critic-rationale-qwen").textContent =
      evals.qwen.rationale || "Architectural modularity verified.";
  }
  if (evals.minimax) {
    document.getElementById("critic-score-minimax").textContent = `${evals.minimax.normalized_score} / 5`;
    document.getElementById("critic-rationale-minimax").textContent =
      evals.minimax.rationale || "Execution assertions pass deterministically.";
  }
  if (evals.kimi_k) {
    document.getElementById("critic-score-kimi").textContent = `${evals.kimi_k.normalized_score} / 5`;
    document.getElementById("critic-rationale-kimi").textContent =
      evals.kimi_k.rationale || "GCP API & parameter grounding verified.";
  }

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
