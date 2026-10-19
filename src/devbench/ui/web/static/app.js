/**
 * devbench Evaluation Studio - Client Application Controller
 * Supports Frontier Model (MIQ) Selection, GCP Project & Location Linking,
 * Custom Multi-Test Suite Builder (1+ Standard + 1+ Custom Argon Use Cases),
 * Live Hierarchical Telemetry, and Git Repository Export.
 */

const state = {
  gcpProject: "",
  gcpLocation: "us-central1",
  assessmentMode: "gcp", // "gcp" | "curl" | "api"
  miqPage: 1,
  miqPageSize: 12,
  miqCollapsed: false,
  apiKeysConfigured: {},
  linkStatus: {},
  allModels: [],
  defaultModels: [],
  dropdownModels: [],
  models: [],
  selectedModelId: "gemini-3.5-flash",
  allHarnesses: [],
  defaultHarnesses: [],
  dropdownHarnesses: [],
  selectedHarnessId: "agy",
  internalGooglePermissions: null,
  allScenarios: [],
  customSuiteItems: [],
  activeScenarioId: "storage_operations",
  activeSuiteSpec: null,
  activeRunData: null,
  isEvaluating: false,
  pollTimer: null,
  localTimer: null,
  localStartTime: null,
};

const ICONS = {
  spinner: '<svg class="spinner" width="14" height="14" viewBox="0 0 24 24" fill="none" style="vertical-align: middle;"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" stroke-dasharray="32" stroke-linecap="round" fill="none"/></svg>',
  check: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" style="vertical-align: middle;"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z" fill="currentColor"/></svg>',
  play: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" style="vertical-align: middle;"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>',
  sparkle: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" style="vertical-align: middle;"><path d="M12 2L13.8 8.2L20 10L13.8 11.8L12 18L10.2 11.8L4 10L10.2 8.2L12 2Z" fill="currentColor"/></svg>',
  package: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" style="vertical-align: middle;"><path d="M21 16.5C21 16.88 20.79 17.21 20.47 17.38L12.57 21.82C12.41 21.91 12.21 21.96 12.01 21.96C11.81 21.96 11.61 21.91 11.45 21.82L3.55 17.38C3.21 17.21 3 16.88 3 16.5V7.5C3 7.12 3.21 6.79 3.55 6.62L11.45 2.18C11.79 2 12.21 2 12.55 2.18L20.45 6.62C20.79 6.79 21 7.12 21 7.5V16.5ZM12 4.15L5.04 8.05L12 11.96L18.96 8.05L12 4.15ZM5 9.91V15.59L11 18.96V13.27L5 9.91ZM13 18.96L19 15.59V9.91L13 13.27V18.96Z" fill="currentColor"/></svg>',
  commit: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" style="vertical-align: middle;"><path d="M16.9 11C16.43 8.72 14.42 7 12 7C9.58 7 7.57 8.72 7.1 11H2V13H7.1C7.57 15.28 9.58 17 12 17C14.42 17 16.43 15.28 16.9 13H22V11H16.9ZM12 15C10.34 15 9 13.66 9 12C9 10.34 10.34 9 12 9C13.66 9 15 10.34 15 12C15 13.66 13.66 15 12 15Z" fill="currentColor"/></svg>',
  refresh: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" style="vertical-align: middle;"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" fill="currentColor"/></svg>',
  visibility: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" style="vertical-align: middle;"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z" fill="currentColor"/></svg>',
  visibilityOff: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" style="vertical-align: middle;"><path d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.44-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z" fill="currentColor"/></svg>',
  warning: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" style="vertical-align: middle;"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" fill="#f9ab00"/></svg>',
  cloud: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M19.35 10.04C18.67 6.59 15.64 4 12 4C9.11 4 6.6 5.64 5.35 8.04C2.34 8.36 0 10.91 0 14C0 17.31 2.69 20 6 20H19C21.76 20 24 17.76 24 15C24 12.36 21.95 10.22 19.35 10.04Z" fill="#1a73e8"/></svg>',
  brain: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z" fill="#1a73e8"/></svg>',
  codeTransform: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z" fill="#1e8e3e"/></svg>'
};

function escapeHtml(value) {
  return String(value === undefined || value === null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function fmtUsd(v, digits = 5) {
  return `$${Number(v || 0).toFixed(digits)}`;
}

function fmtInt(v) {
  return Number(v || 0).toLocaleString();
}

async function readJsonResponse(res) {
  let data = {};
  try {
    data = await res.json();
  } catch (e) {
    data = {};
  }
  if (!res.ok) {
    const err = new Error(data.error || `HTTP ${res.status}`);
    err.data = data;
    throw err;
  }
  return data;
}

const TEMPLATES = {
  skill_bigquery_alert:
    "Create an agent skill that queries BigQuery logs for critical anomalies, formats an alert with diagnostic metadata, and publishes a structured message to Google Cloud Pub/Sub.",
  gcp_cloudrun_workflow:
    "Generate a production Dockerfile and cloudbuild.yaml to deploy an authenticated FastAPI service on Cloud Run with Filestore volume mounting and least-privilege IAM roles.",
  codebase_flask_to_go:
    "Port a legacy Python Flask REST API with SQLite database access into a high-concurrency Go Gin service with clean separation of handlers, models, and connection pooling.",
};

// ============================================================================
// Frontier Model & Agent Harness Brand Logos (Inline SVG Emblems)
// ============================================================================

function getHarnessLogoSvg(harnessId, brand) {
  const id = (harnessId || "").toLowerCase();
  const b = (brand || "").toLowerCase();

  if (id === "agy" || id === "jetski" || b === "google") {
    return `
      <svg viewBox="0 0 24 24" fill="none" aria-label="Google Agent Harness Logo">
        <rect x="2.5" y="2.5" width="19" height="19" rx="5" fill="#e8f0fe" stroke="#1a73e8" stroke-width="1.8"/>
        <path d="M12 6L17 12L12 18L7 12L12 6Z" fill="#1a73e8"/>
        <circle cx="12" cy="12" r="2.2" fill="#ffffff"/>
      </svg>
    `;
  }
  if (id === "claude-code" || b === "anthropic") {
    return getBrandLogoSvg("anthropic", id);
  }
  if (id === "opencode" || b === "opencode") {
    return `
      <svg viewBox="0 0 24 24" fill="none" aria-label="OpenCode Harness Logo">
        <rect x="2.5" y="4" width="19" height="16" rx="3.5" fill="#e6f4ea" stroke="#1e8e3e" stroke-width="1.8"/>
        <path d="M7 9.5L10.5 12L7 14.5M12 14.5H16.5" stroke="#1e8e3e" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    `;
  }
  if (id === "codex" || b === "openai") {
    return `
      <svg viewBox="0 0 24 24" fill="none" aria-label="Codex CLI Harness Logo">
        <circle cx="12" cy="12" r="9.5" fill="#f3e8fd" stroke="#8430ce" stroke-width="1.8"/>
        <path d="M9.5 9L6.5 12L9.5 15M14.5 9L17.5 12L14.5 15" stroke="#8430ce" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    `;
  }
  return getBrandLogoSvg(brand, harnessId);
}

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

  if (b === "mistral" || id.includes("mistral")) {
    // Mistral AI Stepped Block 'M' Emblem
    return `
      <svg viewBox="0 0 24 24" fill="none" aria-label="Mistral AI Logo">
        <rect x="3" y="4" width="4" height="4" fill="#FFD800"/>
        <rect x="17" y="4" width="4" height="4" fill="#FFD800"/>
        <rect x="3" y="8" width="8" height="4" fill="#FFAF00"/>
        <rect x="13" y="8" width="8" height="4" fill="#FFAF00"/>
        <rect x="3" y="12" width="18" height="4" fill="#FF8205"/>
        <rect x="3" y="16" width="4" height="4" fill="#FA500F"/>
        <rect x="10" y="16" width="4" height="4" fill="#FA500F"/>
        <rect x="17" y="16" width="4" height="4" fill="#FA500F"/>
      </svg>
    `;
  }

  if (b === "anthropic" || id.includes("opus") || id.includes("sonnet") || id.includes("claude")) {
    // Anthropic Claude Starburst Emblem
    return `
      <svg viewBox="0 0 24 24" fill="none" aria-label="Anthropic Claude Logo">
        <circle cx="12" cy="12" r="10" fill="#fef3ec" stroke="#d97757" stroke-width="1.6"/>
        <path d="M12 5V19M5 12H19M7.2 7.2L16.8 16.8M16.8 7.2L7.2 16.8" stroke="#d97757" stroke-width="2" stroke-linecap="round"/>
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

  if (b === "meta" || id.includes("llama")) {
    // Meta Infinity Loop Emblem
    return `
      <svg viewBox="0 0 24 24" fill="none" aria-label="Meta Llama Logo">
        <path d="M5 15C3.5 15 2.5 13.5 2.5 12C2.5 9.5 4.5 8 6.5 8C8.8 8 10.5 10.2 12 12.2C13.5 10.2 15.2 8 17.5 8C19.5 8 21.5 9.5 21.5 12C21.5 13.5 20.5 15 19 15C17.2 15 15.8 13.4 14.5 11.6L12 15L9.5 11.6C8.2 13.4 6.8 15 5 15Z" stroke="#0668E1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    `;
  }

  // Default Agent Platform / Partner Model Hex Emblem
  return `
    <svg viewBox="0 0 24 24" fill="none" aria-label="Agent Platform Partner Model Logo">
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
  initQuickNavScrollSpy();
  await Promise.all([
    fetchModels(),
    fetchHarnesses(),
    fetchScenarios(),
    fetchTokenTelemetry(),
    loadAuthStatus(),
  ]);
}

async function fetchHarnesses() {
  const container = document.getElementById("harness-cards-container");
  try {
    const res = await fetch("/api/harnesses");
    const data = await readJsonResponse(res);
    const previousSelection = state.allHarnesses.length ? state.selectedHarnessId : null;
    state.allHarnesses = data.harnesses || [];
    state.selectedHarnessId = previousSelection || data.default_harness || "agy";
    state.internalGooglePermissions = data.internal_google_default_permissions || null;

    state.defaultHarnesses = state.allHarnesses.filter((h) => h.is_default !== false);
    state.dropdownHarnesses = state.allHarnesses.filter((h) => h.is_default === false);

    renderHarnessCards(state.defaultHarnesses);
    renderAdditionalHarnessesDropdown(state.dropdownHarnesses);
    updateActiveHarnessIndicator();
    updateInternalPermissionsBar();
    updateHarnessWarning();
  } catch (err) {
    if (container) {
      container.innerHTML = `<div class="error-msg">Error loading agent harnesses: ${escapeHtml(err.message)}</div>`;
    }
  }
}

function harnessInstallChip(h) {
  if (h.builtin) return `<span class="tag-chip install-chip installed">Built-in</span>`;
  return h.installed
    ? `<span class="tag-chip install-chip installed" title="${escapeHtml(h.install_status)}">✓ Installed</span>`
    : `<span class="tag-chip install-chip missing" title="${escapeHtml(h.install_status)}">Not installed</span>`;
}

function renderHarnessCards(harnesses) {
  const container = document.getElementById("harness-cards-container");
  if (!container) return;
  container.innerHTML = "";

  harnesses.forEach((h) => {
    const isSelected = h.id === state.selectedHarnessId;
    const card = document.createElement("div");
    card.className = `model-card harness-card ${isSelected ? "selected" : ""} ${h.installed ? "" : "not-installed"}`;
    card.setAttribute("data-harness-id", h.id);
    card.onclick = () => selectHarness(h.id);

    card.innerHTML = `
      <div>
        <div class="model-card-top">
          <div class="model-brand-logo" title="${escapeHtml(h.provider)}">
            ${getHarnessLogoSvg(h.id, h.brand)}
          </div>
          <div style="display: flex; align-items: center; gap: 0.4rem;">
            <span class="badge badge-recommended">${escapeHtml(h.badge || "Harbor Harness")}</span>
            <div class="model-select-check" aria-hidden="true">✓</div>
          </div>
        </div>
        <div class="model-card-header">
          <span class="model-card-title">${escapeHtml(h.name)}</span>
        </div>
        <div class="model-provider">${escapeHtml(h.provider)} • <code>${escapeHtml(h.cli_binary || h.id)}</code></div>
        <p class="model-desc">${escapeHtml(h.description)}</p>
        <div class="model-tags">
          ${harnessInstallChip(h)}
          ${h.harbor_agent_name ? `<span class="tag-chip">Harbor: ${escapeHtml(h.harbor_agent_name)}</span>` : `<span class="tag-chip">Harbor bridge agent</span>`}
        </div>
      </div>
      <div class="model-pricing">
        <span title="${escapeHtml(h.install_status || "")}">${h.binary_path ? `<code>${escapeHtml(h.binary_path)}</code>` : escapeHtml(h.install_status || "")}</span>
      </div>
    `;
    container.appendChild(card);
  });
}

function renderAdditionalHarnessesDropdown(dropdownHarnesses) {
  const select = document.getElementById("additional-harnesses-dropdown");
  if (!select) return;

  select.innerHTML = `<option value="">-- Additional Harnesses (${dropdownHarnesses.length}) --</option>`;
  dropdownHarnesses.forEach((h) => {
    const opt = document.createElement("option");
    opt.value = h.id;
    opt.selected = h.id === state.selectedHarnessId;
    opt.textContent = `${h.name} (${h.id}) — ${h.installed ? "installed" : "not installed"}`;
    select.appendChild(opt);
  });
}

function selectHarness(harnessId) {
  state.selectedHarnessId = harnessId;

  document.querySelectorAll(".harness-card").forEach((card) => {
    card.classList.toggle("selected", card.getAttribute("data-harness-id") === harnessId);
  });

  const dropdown = document.getElementById("additional-harnesses-dropdown");
  if (dropdown) {
    const isDropdown = state.dropdownHarnesses.some((h) => h.id === harnessId);
    dropdown.value = isDropdown ? harnessId : "";
  }

  updateActiveHarnessIndicator();
  updateHarnessWarning();
}

function onSelectDropdownHarness(harnessId) {
  if (!harnessId) {
    selectHarness("agy");
    return;
  }
  selectHarness(harnessId);
}

function updateActiveHarnessIndicator() {
  const indicator = document.getElementById("active-harness-indicator");
  if (!indicator) return;
  const found = state.allHarnesses.find((h) => h.id === state.selectedHarnessId);
  indicator.textContent = `Active Harness: ${found ? found.name : state.selectedHarnessId}`;
}

function updateHarnessWarning() {
  const box = document.getElementById("harness-warning");
  if (!box) return;
  const h = state.allHarnesses.find((x) => x.id === state.selectedHarnessId);
  const model = state.allModels.find((m) => m.id === state.selectedModelId);
  const messages = [];
  if (h && !h.installed) {
    messages.push(
      `<strong>${escapeHtml(h.name)}</strong> is not installed on this machine (${escapeHtml(h.install_status)}). ` +
        `Install it and click "Re-detect" to use it for live runs; mock runs simulate it.`
    );
  }
  if (h && model && Array.isArray(h.supported_brands) && h.supported_brands.length > 0 &&
      !h.supported_brands.includes(String(model.brand || "").toLowerCase())) {
    messages.push(
      `<strong>${escapeHtml(h.name)}</strong> can only host ${escapeHtml(h.supported_brands.join(", "))} models; ` +
        `the selected MIQ <strong>${escapeHtml(model.name)}</strong> is a ${escapeHtml(model.brand)} model.`
    );
  }
  box.style.display = messages.length ? "block" : "none";
  box.innerHTML = messages.map((m) => `<div style="display:flex;align-items:center;gap:6px;margin:2px 0;">${ICONS.warning} <span>${m}</span></div>`).join("");
}

async function registerCustomHarness() {
  const name = document.getElementById("custom-harness-name").value.trim();
  const binary = document.getElementById("custom-harness-binary").value.trim();
  const command = document.getElementById("custom-harness-command").value.trim();
  if (!name || !binary) {
    alert("Please provide both a harness name and the CLI binary.");
    return;
  }
  try {
    const res = await fetch("/api/harnesses/custom", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, cli_binary: binary, headless_command: command || null }),
    });
    const data = await readJsonResponse(res);
    await fetchHarnesses();
    selectHarness(data.harness.id);
    if (!data.harness.installed) {
      alert(`Registered '${data.harness.name}', but '${binary}' was not found on this machine.`);
    }
  } catch (err) {
    alert("Could not register harness: " + err.message);
  }
}

function updateInternalPermissionsBar() {
  const saLabel = document.getElementById("sandbox-sa-label");
  if (saLabel) {
    const sa = state.internalGooglePermissions && state.internalGooglePermissions.service_account;
    saLabel.textContent = sa || `devbench-sa@${state.gcpProject}.iam.gserviceaccount.com`;
  }
}

function sortModelsByProviderAndRelease(models) {
  if (!Array.isArray(models)) return [];

  function getSortKey(m) {
    const mid = String(m.id || m.model_id || "").toLowerCase();
    const name = String(m.name || "").toLowerCase();
    const pub = String(m.publisher || "").toLowerCase();
    const brand = String(m.brand || "").toLowerCase();
    const prov = String(m.provider || "").toLowerCase();
    const text = `${mid} ${name}`;

    // 1. Provider ranking: Google -> Anthropic -> xAI / Grok -> Mistral -> Meta -> DeepSeek -> Qwen -> ElevenLabs -> Others
    let pRank = 99;
    if (pub === "google" || brand === "gemini" || text.includes("gemini") || text.includes("muse") || text.includes("gemma") || prov.includes("google")) {
      pRank = 0;
    } else if (pub === "anthropic" || brand === "anthropic" || text.includes("claude") || prov.includes("anthropic")) {
      pRank = 1;
    } else if (pub === "xai" || brand === "xai" || text.includes("grok") || prov.includes("xai")) {
      pRank = 2;
    } else if (pub === "mistral" || pub === "mistralai" || brand === "mistral" || text.includes("mistral") || text.includes("codestral") || prov.includes("mistral")) {
      pRank = 3;
    } else if (pub === "meta" || brand === "meta" || text.includes("llama") || prov.includes("meta") || prov.includes("llama")) {
      pRank = 4;
    } else if (pub === "deepseek" || brand === "deepseek" || text.includes("deepseek") || prov.includes("deepseek")) {
      pRank = 5;
    } else if (pub === "qwen" || pub === "alibaba" || brand === "qwen" || text.includes("qwen") || prov.includes("qwen")) {
      pRank = 6;
    } else if (pub === "elevenlabs" || brand === "elevenlabs" || text.includes("eleven") || prov.includes("elevenlabs")) {
      pRank = 7;
    }

    // 2. Extract version (reverse release order: latest first)
    const cleanMid = mid.replace(/[-_](?:[0-9]+b|[0-9]+m)\b/g, "");
    const cleanName = name.replace(/\b(?:[0-9]+b|[0-9]+m)\b/g, "");
    const combined = `${cleanMid} ${cleanName}`;

    let major = 0.0, minor = 0.0;
    const verMatch = combined.match(/(?:gemini|claude|grok|llama|mistral|qwen|deepseek|r|v)[-_ ]?([0-9]+(?:[\.\-][0-9]+)?)/) || cleanMid.match(/([0-9]+(?:[\.\-][0-9]+)?)/);
    if (verMatch) {
      const parts = verMatch[1].replace("-", ".").split(".");
      major = parseFloat(parts[0]) || 0.0;
      minor = parts.length > 1 ? (parseFloat(parts[1]) || 0.0) : 0.0;
    }

    // 3. Tier ranking within same version
    let tierRank = 0;
    if (text.includes("argon")) tierRank = 10;
    else if (text.includes("opus") || text.includes("reasoning") || text.includes("large")) tierRank = 8;
    else if (text.includes("pro") || text.includes("sonnet") || text.includes("medium")) tierRank = 6;
    else if (text.includes("flash") || text.includes("haiku") || text.includes("small") || text.includes("codestral")) tierRank = 4;
    else if (text.includes("mini") || text.includes("turbo") || text.includes("lite")) tierRank = 2;

    return { pRank, major, minor, tierRank, mid };
  }

  return [...models].sort((a, b) => {
    const ka = getSortKey(a);
    const kb = getSortKey(b);
    if (ka.pRank !== kb.pRank) return ka.pRank - kb.pRank;
    if (ka.major !== kb.major) return kb.major - ka.major; // descending
    if (ka.minor !== kb.minor) return kb.minor - ka.minor; // descending
    if (ka.tierRank !== kb.tierRank) return kb.tierRank - ka.tierRank; // descending
    return ka.mid.localeCompare(kb.mid);
  });
}

function applyModelsSnapshot(data) {
  state.gcpProject = data.project_id || state.gcpProject;
  state.gcpLocation = data.location || state.gcpLocation;
  state.linkStatus = data.link_status || {};
  state.allModels = sortModelsByProviderAndRelease(data.models || []);
  state.models = state.allModels;
  state.defaultModels = sortModelsByProviderAndRelease(data.default_models || state.allModels.filter((m) => m.is_default && m.enabled));
  state.dropdownModels = sortModelsByProviderAndRelease(data.dropdown_models || state.allModels.filter((m) => m.enabled && !m.is_default));

  // Keep the selected MIQ valid: it must be enabled in the linked project.
  const enabled = state.allModels.filter((m) => m.enabled);
  if (!enabled.some((m) => m.id === state.selectedModelId)) {
    state.selectedModelId = (state.defaultModels[0] || enabled[0] || {}).id || "";
  }

  updateGcpHeaderUI();
  updateInternalPermissionsBar();
  renderGcpMiqToggles(state.allModels);
  renderModelCards(state.defaultModels);
  renderEnabledModelsDropdown(state.dropdownModels);
  updateActiveModelIndicator();
  updateHarnessWarning();
  updateMiqTogglesSelection(state.selectedModelId);
}

async function fetchModels() {
  const container = document.getElementById("model-cards-container");
  try {
    const res = await fetch("/api/models");
    const data = await readJsonResponse(res);
    applyModelsSnapshot(data);
  } catch (err) {
    if (container) {
      container.innerHTML = `<div class="error-msg">Error loading models: ${escapeHtml(err.message)}</div>`;
    }
  }
}

function isDiscoveredProject() {
  return state.linkStatus && state.linkStatus.source === "discovered";
}

function updateGcpHeaderUI() {
  const statusText = document.getElementById("gcp-status-text");
  const headerLoc = document.getElementById("gcp-header-location");
  const projInput = document.getElementById("gcp-project-input");
  const locSelect = document.getElementById("gcp-location-select");
  const dropdownProjLabel = document.getElementById("dropdown-project-label");
  const enabledCountBadge = document.getElementById("enabled-miq-count-badge");
  const savedBadge = document.getElementById("gcp-config-saved-badge");
  const statusBox = document.getElementById("gcp-link-status");

  const discovered = isDiscoveredProject();
  if (statusText) statusText.textContent = discovered ? `GCP: ${state.gcpProject}` : `GCP: ${state.gcpProject} (not linked)`;
  if (headerLoc) headerLoc.textContent = state.gcpLocation;
  if (projInput && document.activeElement !== projInput) projInput.value = state.gcpProject;
  if (locSelect) {
    if (![...locSelect.options].some((o) => o.value === state.gcpLocation)) {
      const opt = document.createElement("option");
      opt.value = state.gcpLocation;
      opt.textContent = state.gcpLocation;
      locSelect.appendChild(opt);
    }
    locSelect.value = state.gcpLocation;
  }
  if (dropdownProjLabel) dropdownProjLabel.textContent = `${state.gcpProject} • ${state.gcpLocation}`;

  const sidebarProj = document.getElementById("sidebar-gcp-project");
  const sidebarLoc = document.getElementById("sidebar-gcp-location");
  if (sidebarProj) sidebarProj.value = state.gcpProject;
  if (sidebarLoc) sidebarLoc.value = state.gcpLocation;
  const curlQuotaHeader = document.getElementById("curl-quota-project-header");
  if (curlQuotaHeader) curlQuotaHeader.textContent = `-H "x-goog-user-project: ${state.gcpProject || 'gemini-api-505408'}"`;
  updateCurlPreview();

  const totalEnabled = state.allModels.filter((m) => m.enabled).length;
  if (enabledCountBadge) {
    enabledCountBadge.textContent = `${totalEnabled} of ${state.allModels.length} Models Enabled`;
  }
  if (savedBadge) {
    savedBadge.textContent = discovered ? `Linked: ${state.gcpProject} (${state.gcpLocation})` : "Not linked (offline demo catalog)";
    savedBadge.className = `badge ${discovered ? "badge-speed" : "badge-coding"}`;
  }
  if (statusBox) {
    const ls = state.linkStatus || {};
    const errors = (ls.errors || []).filter(Boolean);
    statusBox.setAttribute("data-state", discovered ? "linked" : errors.length ? "error" : "offline");
    let html = escapeHtml(ls.message || "Offline demo catalog — link a GCP project to discover the models enabled in it.");
    if (ls.credential_source) html += ` <span class="muted">• Credentials: ${escapeHtml(ls.credential_source)}</span>`;
    if (ls.discovered_at) html += ` <span class="muted">• Discovered ${escapeHtml(ls.discovered_at)}</span>`;
    if (errors.length) {
      html += `<ul>${errors.slice(0, 6).map((e) => `<li>${escapeHtml(e)}</li>`).join("")}</ul>`;
    }
    statusBox.innerHTML = html;
  }
}

function selectAssessmentMode(mode) {
  state.assessmentMode = mode;

  // Update mode selector cards
  document.querySelectorAll(".mode-select-card").forEach((card) => {
    const isTarget = card.getAttribute("data-mode") === mode;
    card.classList.toggle("active", isTarget);
    card.setAttribute("aria-checked", isTarget ? "true" : "false");
  });

  // Toggle dynamic authorization panels in sidebar
  const gcpPanel = document.getElementById("auth-panel-gcp");
  const curlPanel = document.getElementById("auth-panel-curl");
  const apiPanel = document.getElementById("auth-panel-api");
  if (gcpPanel) gcpPanel.style.display = mode === "gcp" ? "flex" : "none";
  if (curlPanel) curlPanel.style.display = mode === "curl" ? "flex" : "none";
  if (apiPanel) apiPanel.style.display = mode === "api" ? "flex" : "none";

  // Synchronize execution mode radio in Step 3
  if (mode === "curl") {
    const mockRadio = document.querySelector('input[name="exec-mode"][value="mock"]');
    if (mockRadio) mockRadio.checked = true;
  } else if (mode === "gcp") {
    const liveRadio = document.querySelector('input[name="exec-mode"][value="live"]');
    if (liveRadio) liveRadio.checked = true;
  }

  // Update curl sample preview endpoint
  updateCurlPreview();

  // Notify server of mode selection
  fetch("/api/auth/mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  }).catch(() => {});
}

function updateCurlPreview() {
  const preview = document.getElementById("curl-endpoint-preview");
  if (preview) {
    const model = state.selectedModelId || "gemini-3.5-flash";
    const proj = state.gcpProject || "gemini-api-505408";
    const loc = state.gcpLocation || "global";
    preview.textContent = `https://aiplatform.googleapis.com/v1/projects/${proj}/locations/${loc}/publishers/google/models/${model}:generateContent`;
  }
}

function copySampleCurlCommand(btn) {
  const model = state.selectedModelId || "gemini-3.5-flash";
  const proj = state.gcpProject || "gemini-api-505408";
  const loc = state.gcpLocation || "global";
  const cmd = `curl -X POST "https://aiplatform.googleapis.com/v1/projects/${proj}/locations/${loc}/publishers/google/models/${model}:generateContent" \\
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \\
  -H "x-goog-user-project: ${proj}" \\
  -H "Content-Type: application/json" \\
  -d '{"contents": [{"role": "user", "parts": [{"text": "Hello devbench"}]}]}'`;

  navigator.clipboard.writeText(cmd).then(() => {
    if (btn) {
      const orig = btn.innerHTML;
      btn.innerHTML = `<span style="display:inline-flex;align-items:center;gap:4px;">${ICONS.check} <span>Copied cURL Command!</span></span>`;
      setTimeout(() => { btn.innerHTML = orig; }, 2000);
    }
  });
}

function toggleKeyMask(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;
  if (input.type === "password") {
    input.type = "text";
    btn.innerHTML = ICONS.visibilityOff;
  } else {
    input.type = "password";
    btn.innerHTML = ICONS.visibility;
  }
}

async function saveDirectApiKeys() {
  const gemini = (document.getElementById("key-input-gemini")?.value || "").trim();
  const anthropic = (document.getElementById("key-input-anthropic")?.value || "").trim();
  const openai = (document.getElementById("key-input-openai")?.value || "").trim();
  const fb = document.getElementById("api-keys-feedback");
  const btn = document.getElementById("save-api-keys-btn");

  if (btn) btn.disabled = true;
  try {
    const res = await fetch("/api/auth/keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        gemini_api_key: gemini,
        anthropic_api_key: anthropic,
        openai_api_key: openai,
      }),
    });
    const data = await readJsonResponse(res);
    updateKeyTags(data.keys_configured);
    if (fb) {
      fb.style.display = "block";
      fb.style.color = "var(--google-green)";
      fb.innerHTML = `<span style="display:inline-flex;align-items:center;gap:4px;">${ICONS.check} <span>Direct API Keys updated successfully.</span></span>`;
      setTimeout(() => { fb.style.display = "none"; }, 3500);
    }
  } catch (err) {
    if (fb) {
      fb.style.display = "block";
      fb.style.color = "var(--google-red)";
      fb.textContent = `Error saving keys: ${err.message}`;
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

function updateKeyTags(keys = {}) {
  state.apiKeysConfigured = keys;
  const tagGemini = document.getElementById("tag-key-gemini");
  const tagAnthropic = document.getElementById("tag-key-anthropic");
  const tagOpenai = document.getElementById("tag-key-openai");
  if (tagGemini) {
    tagGemini.textContent = keys.gemini ? "Configured ✓" : "Not set";
    tagGemini.className = `key-status-tag ${keys.gemini ? "configured" : ""}`;
  }
  if (tagAnthropic) {
    tagAnthropic.textContent = keys.anthropic ? "Configured ✓" : "Not set";
    tagAnthropic.className = `key-status-tag ${keys.anthropic ? "configured" : ""}`;
  }
  if (tagOpenai) {
    tagOpenai.textContent = keys.openai ? "Configured ✓" : "Not set";
    tagOpenai.className = `key-status-tag ${keys.openai ? "configured" : ""}`;
  }
}

async function loadAuthStatus() {
  try {
    const res = await fetch("/api/auth/status");
    const data = await readJsonResponse(res);
    if (data.mode) {
      selectAssessmentMode(data.mode);
    }
    if (data.keys_configured) {
      updateKeyTags(data.keys_configured);
    }
  } catch (err) {
    // Non-critical background fetch
  }
}

function toggleGcpConfigPanel() {
  const panel = document.getElementById("gcp-config-panel");
  if (!panel) return;
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  const input = document.getElementById("gcp-project-input");
  if (input) input.focus();
}

function enablementChip(m) {
  const map = {
    enabled: ["installed", "Enabled"],
    unverified: ["unverified", "Unverified"],
    not_enabled: ["missing", "Not enabled"],
    not_available: ["missing", "Not in region"],
    error: ["missing", "Check failed"],
    catalog: ["unverified", "Demo catalog"],
  };
  const [cls, label] = map[m.enablement] || (m.enabled ? ["installed", "Enabled"] : ["missing", "Disabled"]);
  return `<span class="tag-chip install-chip ${cls}" title="${escapeHtml(m.status_detail || "")}">${label}</span>`;
}

function changeMiqPage(newPage) {
  state.miqPage = newPage;
  renderGcpMiqToggles(state.allModels);
}

function changeMiqPageSize(newSize) {
  state.miqPageSize = parseInt(newSize, 10) || 12;
  state.miqPage = 1;
  renderGcpMiqToggles(state.allModels);
}

function toggleMiqSectionCollapse() {
  state.miqCollapsed = !state.miqCollapsed;
  const body = document.getElementById("miq-collapsible-body");
  const summary = document.getElementById("miq-collapsed-summary");
  const icon = document.getElementById("miq-collapse-icon");
  const text = document.getElementById("miq-collapse-text");
  const summaryText = document.getElementById("miq-collapsed-text");

  if (body) {
    if (state.miqCollapsed) {
      body.classList.add("collapsed");
    } else {
      body.classList.remove("collapsed");
    }
  }
  if (summary) {
    summary.style.display = state.miqCollapsed ? "flex" : "none";
  }
  if (icon) {
    icon.innerHTML = state.miqCollapsed
      ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M8.59 16.59L13.17 12L8.59 7.41L10 6L16 12L10 18L8.59 16.59Z"/></svg>`
      : `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M7.41 8.59L12 13.17L16.59 8.59L18 10L12 16L6 10L7.41 8.59Z"/></svg>`;
  }
  if (text) {
    text.textContent = state.miqCollapsed ? "Expand Models" : "Collapse Models";
  }
  if (summaryText) {
    const totalEnabled = state.allModels.filter((m) => m.enabled).length;
    summaryText.textContent = `${state.allModels.length} Models Discovered (${totalEnabled} Enabled in Project) — Section collapsed to proceed quickly to Step 1 & 2. Click to expand.`;
  }
}

function renderGcpMiqToggles(models) {
  const container = document.getElementById("gcp-miq-toggles-container");
  if (!container) return;
  container.innerHTML = "";
  const discovered = isDiscoveredProject();

  if (models.length === 0) {
    container.innerHTML = `<div class="loading-placeholder">No models discovered yet.</div>`;
    const pageInfoTop = document.getElementById("miq-page-info");
    const pageInfoBottom = document.getElementById("miq-page-info-bottom");
    if (pageInfoTop) pageInfoTop.textContent = "0 Models available";
    if (pageInfoBottom) pageInfoBottom.textContent = "0 Models";
    return;
  }

  // Sort provider by provider in reverse release order (latest first)
  const sorted = sortModelsByProviderAndRelease(models);

  // Pagination Math (Supports 9 or 12 models per page)
  const pageSize = state.miqPageSize || 12;
  const totalModels = sorted.length;
  const totalPages = Math.max(1, Math.ceil(totalModels / pageSize));
  if (state.miqPage > totalPages) state.miqPage = totalPages;
  if (state.miqPage < 1) state.miqPage = 1;
  const curPage = state.miqPage;

  const startIdx = (curPage - 1) * pageSize;
  const endIdx = Math.min(startIdx + pageSize, totalModels);
  const pagedModels = sorted.slice(startIdx, endIdx);

  // Sync Page Size Selector
  const sizeSelect = document.getElementById("miq-page-size-select");
  if (sizeSelect && sizeSelect.value !== String(pageSize)) {
    sizeSelect.value = String(pageSize);
  }

  // Update Page Info labels
  const pageInfoTop = document.getElementById("miq-page-info");
  const pageInfoBottom = document.getElementById("miq-page-info-bottom");
  const infoText = `Showing ${startIdx + 1}–${endIdx} of ${totalModels} Models (Page ${curPage} of ${totalPages})`;
  if (pageInfoTop) pageInfoTop.textContent = infoText;
  if (pageInfoBottom) pageInfoBottom.textContent = `Page ${curPage} of ${totalPages} • ${totalModels} Total Discovered Models`;

  // Render Page Navigation Buttons (Top & Bottom)
  const renderNavButtons = (containerId) => {
    const nav = document.getElementById(containerId);
    if (!nav) return;
    nav.innerHTML = "";
    if (totalPages <= 1) return;

    // Previous Button
    const prevBtn = document.createElement("button");
    prevBtn.type = "button";
    prevBtn.className = "page-pill-btn";
    prevBtn.innerHTML = "&lsaquo; Prev";
    prevBtn.disabled = curPage === 1;
    prevBtn.title = "Previous Page";
    prevBtn.onclick = () => changeMiqPage(curPage - 1);
    nav.appendChild(prevBtn);

    // Numbered Page Pills
    for (let p = 1; p <= totalPages; p++) {
      const pageBtn = document.createElement("button");
      pageBtn.type = "button";
      pageBtn.className = `page-pill-btn ${p === curPage ? "active" : ""}`;
      pageBtn.textContent = String(p);
      pageBtn.title = `Page ${p}`;
      pageBtn.onclick = () => changeMiqPage(p);
      nav.appendChild(pageBtn);
    }

    // Next Button
    const nextBtn = document.createElement("button");
    nextBtn.type = "button";
    nextBtn.className = "page-pill-btn";
    nextBtn.innerHTML = "Next &rsaquo;";
    nextBtn.disabled = curPage === totalPages;
    nextBtn.title = "Next Page";
    nextBtn.onclick = () => changeMiqPage(curPage + 1);
    nav.appendChild(nextBtn);
  };

  renderNavButtons("miq-page-nav-top");
  renderNavButtons("miq-page-nav-bottom");

  // Render Each Model in the +80% Larger Box (Whole title readable, attributes, verification & select)
  pagedModels.forEach((m) => {
    const isSelected = m.id === state.selectedModelId;
    const item = document.createElement("div");
    item.className = `miq-toggle-item ${m.enabled ? "enabled" : ""} ${isSelected ? "selected-miq" : ""}`;
    item.setAttribute("data-model-id", m.id);
    const publisherName = m.publisher || m.brand || "Google Cloud";
    const locTag = m.location || state.gcpLocation || "global";
    const launchStage = m.launch_stage || (m.category === "dedicated_endpoint" ? "Dedicated Endpoint" : "MaaS Serverless");
    const pricing = pricingLabel(m);

    let verifyControl = "";
    if (discovered && m.discovered) {
      const canVerify = m.publisher && m.publisher !== "endpoint";
      verifyControl = `
        <div style="display: flex; align-items: center; gap: 0.35rem;">
          ${enablementChip(m)}
          ${canVerify ? `<button type="button" class="chip-btn" onclick="event.stopPropagation(); verifyModelAccess('${escapeHtml(m.id)}', this)">Verify in Model Garden</button>` : ""}
        </div>
      `;
    } else {
      verifyControl = `
        <div style="display: flex; align-items: center; gap: 0.35rem;">
          ${enablementChip(m)}
          <button type="button" class="chip-btn" onclick="event.stopPropagation(); verifyModelAccess('${escapeHtml(m.id)}', this)">Verify</button>
        </div>
      `;
    }

    item.innerHTML = `
      <div>
        <div class="miq-item-top">
          <div class="miq-item-left">
            <div class="miq-toggle-brand" title="${escapeHtml(m.provider || publisherName)}">
              ${getBrandLogoSvg(m.brand, m.id)}
            </div>
            <div class="miq-item-title-block">
              <div class="miq-toggle-name" title="${escapeHtml(m.name)}">${escapeHtml(m.name)}</div>
              <div class="miq-toggle-meta">${escapeHtml(m.id)} • ${escapeHtml(publisherName)}</div>
            </div>
          </div>
          <div class="miq-toggle-check" onclick="event.stopPropagation()">
            <input type="checkbox" id="chk-miq-${escapeHtml(m.id)}" ${m.enabled ? "checked" : ""} aria-label="Enable ${escapeHtml(m.name)}" onchange="toggleMiqModelInProject('${escapeHtml(m.id)}', this.checked)">
          </div>
        </div>

        <div class="miq-item-attrs" style="margin-top: 0.5rem;">
          <span class="miq-attr-chip location">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" style="vertical-align: -1px; margin-right: 2px;">
              <path d="M12 2C8.13 2 5 5.13 5 9C5 14.25 12 22 12 22C12 22 19 14.25 19 9C19 5.13 15.87 2 12 2ZM12 11.5C10.62 11.5 9.5 10.38 9.5 9C9.5 7.62 10.62 6.5 12 6.5C13.38 6.5 14.5 7.62 14.5 9C14.5 10.38 13.38 11.5 12 11.5Z" fill="#1a73e8"/>
            </svg>
            ${escapeHtml(locTag)}
          </span>
          <span class="miq-attr-chip">${escapeHtml(launchStage)}</span>
          <span class="miq-attr-chip pricing">${pricing}</span>
        </div>
      </div>

      <div class="miq-item-bottom">
        ${verifyControl}
        <button type="button" class="chip-btn miq-select-btn ${isSelected ? 'btn-selected' : ''}" style="${isSelected ? 'background: var(--google-blue, #1a73e8); color: #fff; font-weight: 600;' : ''}" onclick="event.stopPropagation(); selectModel('${escapeHtml(m.id)}')">
          ${isSelected ? '✓ Active MIQ' : 'Select as MIQ'}
        </button>
      </div>
    `;

    item.onclick = () => {
      selectModel(m.id);
    };

    container.appendChild(item);
  });
}

let currentModelForAccessVerify = null;

function showModelAccessModal(info = {}) {
  const modal = document.getElementById("model-access-modal");
  if (!modal) return;

  const modelId = info.model_id || state.selectedModelId || "unknown-model";
  currentModelForAccessVerify = modelId;
  const projectId = info.project_id || state.gcpProject || "not-specified";
  const location = info.location || state.gcpLocation || "us-central1";
  const errorMsg = info.message || info.detail || info.error || "Agent Platform Model Garden access denied or model terms not accepted.";
  const statusBadge = info.error_status || "PERMISSION_DENIED";

  const modelIdEl = document.getElementById("modal-model-id");
  if (modelIdEl) modelIdEl.textContent = modelId;

  const projIdEl = document.getElementById("modal-project-id");
  if (projIdEl) projIdEl.textContent = projectId;

  const locEl = document.getElementById("modal-location");
  if (locEl) locEl.textContent = location;

  const badgeEl = document.getElementById("modal-status-badge");
  if (badgeEl) badgeEl.textContent = statusBadge;

  const errorTextEl = document.getElementById("modal-error-text");
  if (errorTextEl) errorTextEl.textContent = errorMsg;

  const mgLink = document.getElementById("modal-model-garden-link");
  if (mgLink) {
    mgLink.href = info.model_garden_url || `https://console.cloud.google.com/vertex-ai/model-garden?project=${encodeURIComponent(projectId)}`;
  }

  modal.style.display = "flex";
}

function closeModelAccessModal() {
  const modal = document.getElementById("model-access-modal");
  if (modal) modal.style.display = "none";
}

function handleModalBackdropClick(e) {
  if (e.target && e.target.id === "model-access-modal") {
    closeModelAccessModal();
  }
}

function copyAdcLoginCommand(btn) {
  const cmd = "gcloud auth application-default login";
  navigator.clipboard.writeText(cmd).then(() => {
    if (btn) {
      const orig = btn.textContent;
      btn.textContent = "Copied!";
      setTimeout(() => { btn.textContent = orig; }, 1500);
    }
  }).catch(() => {
    prompt("Copy command:", cmd);
  });
}

function copyModalAdcCommand(btn) {
  copyAdcLoginCommand(btn);
}

async function retryModelVerificationFromModal() {
  if (!currentModelForAccessVerify) {
    closeModelAccessModal();
    return;
  }
  const btn = document.getElementById("modal-reverify-btn");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span style="display:inline-flex;align-items:center;gap:4px;">${ICONS.spinner} <span>Checking…</span></span>`;
  }
  try {
    await verifyModelAccess(currentModelForAccessVerify);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<span style="display:inline-flex;align-items:center;gap:4px;">${ICONS.refresh} <span>Re-Verify Model Access</span></span>`;
    }
  }
}

async function verifyModelAccess(modelId, btn) {
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span style="display:inline-flex;align-items:center;gap:4px;">${ICONS.spinner} <span>Checking…</span></span>`;
  }
  try {
    const res = await fetch("/api/gcp/models/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelId }),
    });
    const data = await readJsonResponse(res);
    applyModelsSnapshot(data);
    const v = data.verification || {};
    if (!v.enabled) {
      showModelAccessModal({
        model_id: modelId,
        model_name: v.model_name || modelId,
        project_id: data.project_id || v.project_id,
        location: data.location || v.location,
        message: v.detail || v.message || "Model is not enabled in this GCP project",
        error_status: v.enablement || "NOT_ENABLED",
        model_garden_url: v.model_garden_url,
      });
    } else {
      closeModelAccessModal();
    }
  } catch (err) {
    if (err.data && (err.data.error_type === "MODEL_ACCESS_DENIED" || err.data.model_id)) {
      showModelAccessModal(err.data);
    } else {
      alert("Verification failed: " + err.message);
    }
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Verify";
    }
  }
}

async function toggleMiqModelInProject(modelId, enabledState) {
  try {
    const res = await fetch("/api/gcp/models/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelId, enabled: enabledState }),
    });
    const data = await readJsonResponse(res);
    if (data.success) applyModelsSnapshot(data);
  } catch (err) {
    console.error("Failed to toggle MIQ model:", err);
  }
}

async function saveGcpConfiguration() {
  const projInput = document.getElementById("gcp-project-input");
  const locSelect = document.getElementById("gcp-location-select");
  const verifyToggle = document.getElementById("gcp-verify-partner-toggle");
  const btn = document.getElementById("save-gcp-config-btn");

  const projectId = projInput ? projInput.value.trim() : "";
  const location = (locSelect ? locSelect.value : "") || "us-central1";
  if (!projectId) {
    alert("Enter the ID of the GCP project you want to link.");
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span style="display:inline-flex;align-items:center;gap:4px;">${ICONS.spinner} <span>Verifying project &amp; discovering models...</span></span>`;
  }

  try {
    const res = await fetch("/api/gcp/link", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: projectId,
        location: location,
        verify_partner_access: Boolean(verifyToggle && verifyToggle.checked),
      }),
    });
    const data = await readJsonResponse(res);
    applyModelsSnapshot(data);
    if (!data.success) {
      const lr = data.link_result || {};
      alert(`Could not link ${projectId}: ${lr.message || "see details in the GCP panel"}`);
    }
  } catch (err) {
    alert("Error linking GCP project: " + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true" style="vertical-align: middle; margin-right: 4px;"><path d="M19.35 10.04C18.67 6.59 15.64 4 12 4C9.11 4 6.6 5.64 5.35 8.04C2.34 8.36 0 10.91 0 14C0 17.31 2.69 20 6 20H19C21.76 20 24 17.76 24 15C24 12.36 21.95 10.22 19.35 10.04ZM15.5 13H13V16C13 16.55 12.55 17 12 17C11.45 17 11 16.55 11 16V13H8.5C8.05 13 7.83 12.46 8.15 12.15L11.65 8.65C11.85 8.45 12.16 8.45 12.36 8.65L15.86 12.15C16.17 12.46 15.95 13 15.5 13Z" fill="currentColor"/></svg><span>Link &amp; Discover Models</span>`;
    }
  }
}

function onCustomModelTypeChange(type) {
  const label = document.getElementById("custom-endpoint-id-label");
  const input = document.getElementById("custom-endpoint-id-input");
  if (!label || !input) return;
  if (type === "dedicated_endpoint") {
    label.textContent = "Endpoint ID (or resource name)";
    input.placeholder = "e.g. 728193049102 or projects/.../endpoints/728193049102";
  } else {
    label.textContent = "Publisher Name or Model ID";
    input.placeholder = "e.g. publishers/google/models/gemini-3.1-pro or gemini-3-flash";
  }
}

async function submitCustomGcpModel() {
  const typeSelect = document.getElementById("custom-model-type-select");
  const endpointInput = document.getElementById("custom-endpoint-id-input");
  const nameInput = document.getElementById("custom-model-name-input");
  const projInput = document.getElementById("gcp-project-input");
  const locSelect = document.getElementById("gcp-location-select");
  const feedback = document.getElementById("custom-model-feedback");
  const btn = document.getElementById("add-custom-model-btn");

  const modelType = typeSelect ? typeSelect.value : "managed";
  const endpointIdOrName = endpointInput ? endpointInput.value.trim() : "";
  const displayName = nameInput ? nameInput.value.trim() : "";
  const projectId = projInput ? projInput.value.trim() : "";
  const location = locSelect ? locSelect.value : "us-central1";

  if (!endpointIdOrName) {
    if (feedback) {
      feedback.style.display = "block";
      feedback.style.color = "var(--google-red, #ea4335)";
      feedback.textContent = "Please enter an Endpoint ID or Publisher Model Name.";
    }
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span style="display:inline-flex;align-items:center;gap:4px;">${ICONS.spinner} <span>Adding...</span></span>`;
  }

  try {
    const res = await fetch("/api/gcp/models/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model_type: modelType,
        endpoint_id_or_name: endpointIdOrName,
        display_name: displayName,
        project_id: projectId,
        region: location,
      }),
    });
    const data = await readJsonResponse(res);
    if (data.success) {
      applyModelsSnapshot(data);
      if (feedback) {
        feedback.style.display = "block";
        feedback.style.color = "var(--google-green, #34a853)";
        feedback.textContent = `Successfully added and enabled "${data.model.name}"!`;
        setTimeout(() => { feedback.style.display = "none"; }, 4000);
      }
      if (endpointInput) endpointInput.value = "";
      if (nameInput) nameInput.value = "";
    } else {
      if (feedback) {
        feedback.style.display = "block";
        feedback.style.color = "var(--google-red, #ea4335)";
        feedback.textContent = data.error || "Failed to register custom model.";
      }
    }
  } catch (err) {
    if (feedback) {
      feedback.style.display = "block";
      feedback.style.color = "var(--google-red, #ea4335)";
      feedback.textContent = `Error: ${err.message}`;
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<span style="display:inline-flex;align-items:center;gap:4px;"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 2C6.48 2 2 6.48 2 12C2 17.52 6.48 22 12 22C17.52 22 22 17.52 22 12C22 6.48 17.52 2 12 2ZM17 13H13V17H11V13H7V11H11V7H13V11H17V13Z" fill="currentColor"/></svg><span>Add Model</span></span>`;
    }
  }
}


// ============================================================================
// Step 1: Frontier Model Cards (4 Defaults) & Enabled GCP Project Dropdown
// ============================================================================

function pricingLabel(m) {
  const src = m.pricing_source && m.pricing_source !== "catalog" ? ` (${m.pricing_source.replace(/_/g, " ")})` : "";
  return `In: <span class="pricing-val">$${(Number(m.cost_per_1k_input_usd || 0) * 1000).toFixed(2)}/M</span> • Out: <span class="pricing-val">$${(Number(m.cost_per_1k_output_usd || 0) * 1000).toFixed(2)}/M</span><span class="muted">${escapeHtml(src)}</span>`;
}

function renderModelCards(models) {
  const container = document.getElementById("model-cards-container");
  if (!container) return;
  container.innerHTML = "";

  if (models.length === 0) {
    container.innerHTML = `<div class="loading-placeholder">No enabled models in ${escapeHtml(state.gcpProject)} (${escapeHtml(state.gcpLocation)}). Link a project above, or enable/verify models in Agent Platform Model Garden.</div>`;
    return;
  }

  models.forEach((m) => {
    const isSelected = m.id === state.selectedModelId;
    const card = document.createElement("div");
    card.className = `model-card miq-card ${isSelected ? "selected" : ""}`;
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
          <div class="model-brand-logo" title="${escapeHtml(m.provider)}">
            ${getBrandLogoSvg(m.brand, m.id)}
          </div>
          <div style="display: flex; align-items: center; gap: 0.4rem;">
            <span class="badge ${badgeClass}">${escapeHtml(m.badge || "Frontier MIQ")}</span>
            <div class="model-select-check" aria-hidden="true">✓</div>
          </div>
        </div>
        <div class="model-card-header">
          <span class="model-card-title">${escapeHtml(m.name)}</span>
        </div>
        <div class="model-provider">${escapeHtml(m.provider)}</div>
        <p class="model-desc">${escapeHtml(m.description)}</p>
        <div class="model-tags">
          ${(m.tags || []).map((t) => `<span class="tag-chip">${escapeHtml(t)}</span>`).join("")}
        </div>
      </div>
      <div class="model-pricing">
        <span>${pricingLabel(m)}</span>
      </div>
    `;
    container.appendChild(card);
  });
}

function renderEnabledModelsDropdown(dropdownModels) {
  const select = document.getElementById("enabled-models-dropdown");
  if (!select) return;

  select.innerHTML = `<option value="">-- Select from ${dropdownModels.length} other enabled models in ${escapeHtml(state.gcpProject)} --</option>`;
  dropdownModels.forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.selected = m.id === state.selectedModelId;
    opt.textContent = `${m.name} — ${m.provider} (${m.location || state.gcpLocation}) [$${(Number(m.cost_per_1k_input_usd || 0) * 1000).toFixed(2)}/M in]`;
    select.appendChild(opt);
  });

  updateDropdownBanner();
}

function selectModel(modelId) {
  if (!modelId) return;
  state.selectedModelId = modelId;

  // 1. Locate the model object across all models collections
  const targetModel =
    (state.allModels && state.allModels.find((m) => m.id === modelId)) ||
    (state.dropdownModels && state.dropdownModels.find((m) => m.id === modelId)) ||
    (state.defaultModels && state.defaultModels.find((m) => m.id === modelId));

  // 2. If model is currently disabled, enable it so it can be evaluated
  if (targetModel && !targetModel.enabled) {
    targetModel.enabled = true;
    const chk = document.getElementById(`chk-miq-${modelId}`);
    if (chk) chk.checked = true;
    toggleMiqModelInProject(modelId, true);
  }

  // 3. Check if it is one of the default cards in Section 1
  const isDefaultCard = state.defaultModels && state.defaultModels.some((m) => m.id === modelId);

  // Sync Section 1 default cards
  document.querySelectorAll(".miq-card").forEach((card) => {
    card.classList.toggle("selected", card.getAttribute("data-model-id") === modelId);
  });

  // 4. Sync Section 1 dropdown
  const dropdown = document.getElementById("enabled-models-dropdown");
  if (dropdown) {
    if (isDefaultCard) {
      dropdown.value = "";
    } else {
      // If it's a dropdown / non-default model, ensure it is in state.dropdownModels
      if (targetModel && !state.dropdownModels.some((m) => m.id === modelId)) {
        state.dropdownModels.push(targetModel);
        state.dropdownModels = sortModelsByProviderAndRelease(state.dropdownModels);
        renderEnabledModelsDropdown(state.dropdownModels);
      } else {
        let opt = Array.from(dropdown.options).find((o) => o.value === modelId);
        if (!opt && targetModel) {
          opt = document.createElement("option");
          opt.value = targetModel.id;
          opt.textContent = `${targetModel.name} — ${targetModel.provider} (${targetModel.location || state.gcpLocation}) [$${(Number(targetModel.cost_per_1k_input_usd || 0) * 1000).toFixed(2)}/M in]`;
          dropdown.appendChild(opt);
        }
      }
      dropdown.value = modelId;
    }
  }

  // 5. Update dropdown banner (same banner as when selected via Section 1 dropdown)
  updateDropdownBanner();

  // 6. Update Active MIQ indicator, warning, and curl preview
  updateActiveModelIndicator();
  updateHarnessWarning();
  updateCurlPreview();

  // 7. Update Available Models cards button and highlighting
  updateMiqTogglesSelection(modelId);
}

function updateMiqTogglesSelection(modelId) {
  const items = document.querySelectorAll(".miq-toggle-item");
  items.forEach((item) => {
    const itemModelId = item.getAttribute("data-model-id");
    const isSelected = itemModelId === modelId;
    item.classList.toggle("selected-miq", isSelected);

    const btn = item.querySelector(".miq-select-btn");
    if (btn) {
      if (isSelected) {
        btn.classList.add("btn-selected");
        btn.style.background = "var(--google-blue, #1a73e8)";
        btn.style.color = "#ffffff";
        btn.style.fontWeight = "600";
        btn.textContent = "✓ Active MIQ";
      } else {
        btn.classList.remove("btn-selected");
        btn.style.background = "";
        btn.style.color = "";
        btn.style.fontWeight = "";
        btn.textContent = "Select as MIQ";
      }
    }
  });
}

function onSelectDropdownModel(modelId) {
  if (!modelId) {
    const fallback = state.defaultModels[0] || state.allModels.find((m) => m.enabled);
    selectModel(fallback ? fallback.id : "");
    return;
  }
  selectModel(modelId);
}

function updateDropdownBanner() {
  const banner = document.getElementById("selected-dropdown-model-banner");
  if (!banner) return;

  const isDefault = state.defaultModels && state.defaultModels.some((m) => m.id === state.selectedModelId);
  if (isDefault || !state.selectedModelId) {
    banner.style.display = "none";
    return;
  }

  const selectedDropdownModel =
    (state.dropdownModels && state.dropdownModels.find((m) => m.id === state.selectedModelId)) ||
    (state.allModels && state.allModels.find((m) => m.id === state.selectedModelId));

  if (!selectedDropdownModel) {
    banner.style.display = "none";
    return;
  }

  banner.style.display = "flex";
  const logoEl = document.getElementById("dropdown-selected-logo");
  if (logoEl) {
    logoEl.innerHTML = getBrandLogoSvg(
      selectedDropdownModel.brand,
      selectedDropdownModel.id
    );
  }
  const nameEl = document.getElementById("dropdown-selected-name");
  if (nameEl) {
    nameEl.textContent = `${selectedDropdownModel.name} (${selectedDropdownModel.provider || selectedDropdownModel.publisher || "Google Cloud"})`;
  }
  const descEl = document.getElementById("dropdown-selected-desc");
  if (descEl) {
    descEl.textContent = selectedDropdownModel.description || "Frontier Model discovered in project";
  }
  const pricingEl = document.getElementById("dropdown-selected-pricing");
  if (pricingEl) {
    pricingEl.textContent = `In: $${(
      Number(selectedDropdownModel.cost_per_1k_input_usd || 0) * 1000
    ).toFixed(2)}/M • Out: $${(Number(selectedDropdownModel.cost_per_1k_output_usd || 0) * 1000).toFixed(2)}/M`;
  }
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

// Currently implemented & runnable standard benchmark scenarios
const IMPLEMENTED_STANDARD_SCENARIO_IDS = new Set([
  "easy_deployment",
  "model_training",
  "oauth_api_enablement",
  "storage_operations",
]);

function isImplementedScenario(scenarioId) {
  if (!scenarioId) return false;
  return (
    IMPLEMENTED_STANDARD_SCENARIO_IDS.has(scenarioId) ||
    scenarioId === "oauth" ||
    scenarioId.startsWith("argon_")
  );
}

async function fetchScenarios() {
  const select = document.getElementById("preset-scenario-select");
  try {
    const res = await fetch("/api/scenarios");
    const data = await res.json();
    const scenarios = data.scenarios || [];
    state.allScenarios = scenarios;

    const standardScenarios = getStandardScenarios();

    if (select) {
      select.innerHTML = '<option value="">-- Choose a standard benchmark scenario --</option>';
      standardScenarios.forEach((s) => {
        const opt = document.createElement("option");
        opt.value = s.scenario_id;
        opt.textContent = `[${s.difficulty}] ${s.scenario_id} (${s.suite_slug})`;
        if (s.scenario_id === "storage_operations") {
          opt.selected = true;
        }
        select.appendChild(opt);
      });
      select.value = "storage_operations";
    }

    // Initialize default suite with storage_operations as the preset test
    if (state.customSuiteItems.length === 0 && standardScenarios.length > 0) {
      const defaultSc =
        standardScenarios.find((s) => s.scenario_id === "storage_operations") || standardScenarios[0];
      addScenarioToCustomSuite(defaultSc, true);
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

  const standardScenarios = getStandardScenarios();
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

function getStandardScenarios() {
  return state.allScenarios.filter(
    (s) =>
      !s.is_custom &&
      !s.scenario_id.startsWith("argon_") &&
      (IMPLEMENTED_STANDARD_SCENARIO_IDS.has(s.scenario_id) || s.scenario_id === "oauth")
  );
}

function selectAllStandardScenarios() {
  getStandardScenarios().forEach((s) => {
    if (!state.customSuiteItems.some((i) => i.scenario_id === s.scenario_id)) {
      addScenarioToCustomSuite(s, false);
    }
  });
  renderStandardScenariosChecklist();
  renderCustomSuiteTray();
}

function clearStandardScenarios() {
  state.customSuiteItems = state.customSuiteItems.filter((i) => i.is_custom);
  if (state.customSuiteItems.length > 0) {
    state.activeScenarioId = state.customSuiteItems[0].scenario_id;
    state.activeSuiteSpec = state.customSuiteItems[0];
  }
  renderStandardScenariosChecklist();
  renderCustomSuiteTray();
}

function toggleStandardScenarioInSuite(scenarioId, checked) {
  if (checked) {
    const found = state.allScenarios.find((s) => s.scenario_id === scenarioId) || {
      scenario_id: scenarioId,
      scenario_name: scenarioId,
      difficulty: "Medium",
      pillar: "Standard devbench RFC Suite",
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
    pillar: scObj.pillar || "Standard devbench RFC Suite",
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
        Your test suite is empty. Check any number of pre-configured standard tests and/or add your own test scenarios on the left (at least one test is required to run).
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
    btn.innerHTML = `<span style="display:inline-flex;align-items:center;gap:4px;">${ICONS.spinner} <span>Saving Suite...</span></span>`;
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
      btn.innerHTML = `<span style="display:inline-flex;align-items:center;gap:4px;">${ICONS.package} <span>Save Custom Test Suite</span></span>`;
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
  btn.innerHTML = `<span class="btn-icon">${ICONS.spinner}</span> Synthesizing with Argon...`;

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
    btn.innerHTML = `<span class="btn-icon">${ICONS.sparkle}</span> Synthesize & Add Custom Use Case to Suite`;
  }
}

function onSelectPresetScenario() {
  const select = document.getElementById("preset-scenario-select");
  const val = select.value;
  if (!val) return;

  const found = state.allScenarios.find((s) => s.scenario_id === val) || {
    scenario_id: val,
    scenario_name: val,
    pillar: "Standard devbench RFC Suite",
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

  // The suite is exactly what the user composed: any mix of standard + custom tests (>= 1 total).
  const scenarioIds = state.customSuiteItems.map((i) => i.scenario_id);
  if (scenarioIds.length === 0) {
    alert("Your test suite is empty. Add at least one pre-configured standard test or one of your own test scenarios.");
    return;
  }
  if (!state.selectedModelId) {
    alert("Select a Model in Question (MIQ) enabled in your linked GCP project first.");
    return;
  }

  const modelAlias = state.selectedModelId;
  const agentHarness = state.selectedHarnessId || "agy";
  const harborToggle = document.getElementById("harbor-sandbox-toggle");
  const useHarbor = harborToggle ? Boolean(harborToggle.checked) : true;
  const harborEnvSelect = document.getElementById("harbor-env-select");
  const environmentType = harborEnvSelect ? harborEnvSelect.value : "podman";
  const mode = document.querySelector('input[name="exec-mode"]:checked').value;
  const nameInput = document.getElementById("custom-suite-name-input");
  const suiteName = nameInput ? nameInput.value.trim() : "Custom Frontier Evaluation Suite";

  // Reset UI
  state.isEvaluating = true;
  state.activeRunData = null;
  document.getElementById("run-eval-btn").disabled = true;
  document.getElementById("run-eval-btn").innerHTML = `<span class="btn-icon">${ICONS.spinner}</span> Assessing via ${escapeHtml(agentHarness)} (${scenarioIds.length} Test${scenarioIds.length > 1 ? "s" : ""})...`;
  document.getElementById("timer-status-badge").textContent = `Running (${agentHarness})`;
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
        scenario_id: scenarioIds[0],
        scenario_ids: scenarioIds,
        suite_name: suiteName,
        model_alias: modelAlias,
        agent_type: agentHarness,
        harness: agentHarness,
        harbor: useHarbor,
        environment_type: environmentType,
        mode: mode,
        auth_mode: state.assessmentMode || "gcp",
        async: true,
      }),
    });

    const initData = await readJsonResponse(res);
    renderReport({
      status: "RUNNING",
      model_alias: modelAlias,
      agent_harness: agentHarness,
      scenario_ids: scenarioIds,
      warnings: initData.warnings || [],
      test_results: [],
      completed_tests: 0,
      total_tests: scenarioIds.length,
    });
    pollEvaluationStatus(initData.run_id);
  } catch (err) {
    stopEvaluationUI("Error");
    if (err.data && (err.data.error_type === "MODEL_ACCESS_DENIED" || err.data.model_id)) {
      showModelAccessModal(err.data);
    } else {
      alert("Evaluation could not start: " + err.message);
    }
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
      renderReport(data);

      if (data.status === "COMPLETED" || data.status === "FAILED") {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        stopEvaluationUI(data.status === "COMPLETED" ? "Complete" : "Failed");
        state.activeRunData = data;
        displayEvaluationResults(data);
        if (data.model_access_error) {
          showModelAccessModal(data.model_access_error);
        }
        if (data.status === "COMPLETED") prepareRepositoryExport(data);
        fetchTokenTelemetry();
        const reportSection = document.getElementById("eval-report-section");
        if (reportSection) reportSection.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (err) {
      console.error("Polling error:", err);
    }
  }, 600);
}

function stopEvaluationUI(label = "Complete") {
  state.isEvaluating = false;
  if (state.localTimer) {
    clearInterval(state.localTimer);
    state.localTimer = null;
  }
  const btn = document.getElementById("run-eval-btn");
  btn.disabled = false;
  btn.innerHTML = `<span class="btn-icon">${ICONS.play}</span> Run Assessment`;
  document.getElementById("timer-status-badge").textContent = label;
  document.getElementById("timer-status-badge").className = `badge ${label === "Complete" ? "badge-speed" : "badge-danger"}`;
}

// ============================================================================
// Evaluation Report (bottom of the page): metrics, token cost & time per test
// ============================================================================

function renderReport(data) {
  const section = document.getElementById("eval-report-section");
  if (!section) return;
  section.style.display = "block";

  const rows = Array.isArray(data.test_results) ? data.test_results : [];
  const report = data.report || {};
  const total = data.total_tests || (data.scenario_ids || []).length || rows.length;
  const done = data.completed_tests !== undefined ? data.completed_tests : rows.length;

  const badge = document.getElementById("eval-report-status-badge");
  if (badge) {
    if (data.status === "RUNNING") {
      badge.textContent = `RUNNING ${done}/${total}`;
      badge.className = "badge badge-recommended";
    } else {
      const allPassed = rows.length > 0 && rows.every((r) => r.status === "PASSED");
      badge.textContent = data.status === "FAILED" ? "FAILED" : allPassed ? "ALL PASSED" : "COMPLETED WITH FAILURES";
      badge.className = `badge ${allPassed && data.status !== "FAILED" ? "badge-speed" : "badge-danger"}`;
    }
  }

  const subtitle = document.getElementById("eval-report-subtitle");
  if (subtitle) {
    const modelName = report.model_name || data.model_alias || state.selectedModelId;
    const harnessName = report.harness_name || data.agent_harness || state.selectedHarnessId;
    const where = report.gcp_project_id || data.gcp_project_id || state.gcpProject;
    subtitle.innerHTML = `MIQ <strong>${escapeHtml(modelName)}</strong> hosted by <strong>${escapeHtml(harnessName)}</strong> • Project <code>${escapeHtml(where)}</code> • ${escapeHtml(report.execution_mode || data.execution_mode || "")} mode${report.harbor || data.harbor ? " • Harbor " + escapeHtml(report.environment_type || data.environment_type || "") : ""}`;
  }

  const warningsBox = document.getElementById("eval-report-warnings");
  const warnings = (report.warnings || data.warnings || []).filter(Boolean);
  if (warningsBox) {
    const errorLine = data.status === "FAILED" && data.error ? [`Run failed: ${data.error}`] : [];
    const all = [...warnings, ...errorLine];
    warningsBox.style.display = all.length ? "block" : "none";
    warningsBox.innerHTML = all.map((w) => `<div style="display:flex;align-items:center;gap:6px;margin:2px 0;">${ICONS.warning} <span>${escapeHtml(w)}</span></div>`).join("");
  }

  const sum = (key) => rows.reduce((acc, r) => acc + Number(r[key] || 0), 0);
  const passedCount = rows.filter((r) => r.status === "PASSED").length;
  const scored = rows.filter((r) => r.status !== "ERROR");
  const avgScore = scored.length ? scored.reduce((a, r) => a + Number(r.composite_score || 0), 0) / scored.length : 0;
  const summary = document.getElementById("eval-report-summary");
  if (summary) {
    const cards = [
      ["Tests", `${done}/${total}`, `${rows.filter((r) => !r.is_custom).length} standard • ${rows.filter((r) => r.is_custom).length} custom`],
      ["Pass Rate", `${rows.length ? ((100 * passedCount) / rows.length).toFixed(0) : 0}%`, `${passedCount} passed • ${rows.length - passedCount} failed/error`],
      ["Avg Critic Score", `${avgScore.toFixed(2)} / 5`, "Actor-critic composite"],
      ["Total Time", `${sum("wall_seconds").toFixed(2)} s`, `avg ${(rows.length ? sum("wall_seconds") / rows.length : 0).toFixed(2)} s / test`],
      ["Total Tokens", fmtInt(sum("total_tokens")), `${fmtInt(sum("input_tokens"))} in • ${fmtInt(sum("output_tokens"))} out • ${fmtInt(sum("critic_tokens"))} critic`],
      ["Total Cost", fmtUsd(sum("estimated_cost_usd")), `MIQ ${fmtUsd(sum("candidate_cost_usd"))} • critics ${fmtUsd(sum("critic_cost_usd"))}`],
    ];
    summary.innerHTML = cards
      .map(
        ([label, value, sub]) => `
        <div class="report-summary-card">
          <div class="report-summary-label">${escapeHtml(label)}</div>
          <div class="report-summary-value">${escapeHtml(value)}</div>
          <div class="report-summary-sub">${escapeHtml(sub)}</div>
        </div>`
      )
      .join("");
  }

  const tbody = document.getElementById("eval-report-tbody");
  const tfoot = document.getElementById("eval-report-tfoot");
  if (tbody) {
    const pending = (data.scenario_ids || []).slice(rows.length);
    tbody.innerHTML =
      rows
        .map((r, idx) => {
          const statusCls = r.status === "PASSED" ? "badge-speed" : "badge-danger";
          const harborCell =
            r.harbor_tasks_total !== undefined && r.harbor_tasks_total !== null
              ? `${r.harbor_tasks_passed}/${r.harbor_tasks_total}`
              : "—";
          return `
          <tr>
            <td>${idx + 1}</td>
            <td><strong>${escapeHtml(r.scenario_name || r.scenario_id)}</strong><div class="muted mono">${escapeHtml(r.scenario_id)}</div>${r.error ? `<div class="report-error">${escapeHtml(r.error)}</div>` : ""}</td>
            <td><span class="badge ${r.is_custom ? "badge-coding" : "badge-recommended"}">${r.is_custom ? "Custom" : "Standard"}</span></td>
            <td><span class="badge ${statusCls}">${escapeHtml(r.status)}</span></td>
            <td class="mono">${Number(r.rubric_score || 0).toFixed(1)} / ${Number(r.composite_score || 0).toFixed(2)}</td>
            <td class="mono">${harborCell}</td>
            <td class="mono">${Number(r.wall_seconds || 0).toFixed(2)} s</td>
            <td class="mono">${fmtInt(r.input_tokens)}</td>
            <td class="mono">${fmtInt(r.output_tokens)}</td>
            <td class="mono">${fmtInt(r.critic_tokens)}</td>
            <td class="mono" title="Token source: ${escapeHtml(r.token_source || "")}">${fmtUsd(r.candidate_cost_usd)}</td>
            <td class="mono"><strong>${fmtUsd(r.estimated_cost_usd)}</strong></td>
          </tr>`;
        })
        .join("") +
      pending
        .map(
          (sid, i) => `
          <tr class="pending-row">
            <td>${rows.length + i + 1}</td>
            <td><strong>${escapeHtml(sid)}</strong></td>
            <td colspan="10" class="muted">${i === 0 && data.status === "RUNNING" ? `<span style="display:inline-flex;align-items:center;gap:4px;">${ICONS.spinner} <span>Running…</span></span>` : "Queued"}</td>
          </tr>`
        )
        .join("");
  }
  if (tfoot) {
    tfoot.innerHTML = rows.length
      ? `
      <tr>
        <td></td>
        <td colspan="3"><strong>Total (${rows.length} test${rows.length > 1 ? "s" : ""})</strong></td>
        <td class="mono">avg ${avgScore.toFixed(2)}</td>
        <td></td>
        <td class="mono"><strong>${sum("wall_seconds").toFixed(2)} s</strong></td>
        <td class="mono">${fmtInt(sum("input_tokens"))}</td>
        <td class="mono">${fmtInt(sum("output_tokens"))}</td>
        <td class="mono">${fmtInt(sum("critic_tokens"))}</td>
        <td class="mono">${fmtUsd(sum("candidate_cost_usd"))}</td>
        <td class="mono"><strong>${fmtUsd(sum("estimated_cost_usd"))}</strong></td>
      </tr>`
      : "";
  }
  state.lastReportData = data;
}

function _downloadBlob(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function downloadReportJson() {
  const data = state.lastReportData;
  if (!data) return;
  _downloadBlob(
    `devbench-report-${data.run_id || "run"}.json`,
    JSON.stringify({ report: data.report || {}, test_results: data.test_results || [] }, null, 2),
    "application/json"
  );
}

function downloadReportCsv() {
  const data = state.lastReportData;
  if (!data || !Array.isArray(data.test_results)) return;
  const cols = [
    "scenario_id", "scenario_name", "is_custom", "status", "rubric_score", "composite_score",
    "harbor_tasks_passed", "harbor_tasks_total", "wall_seconds", "duration_seconds",
    "input_tokens", "output_tokens", "critic_tokens", "total_tokens",
    "candidate_cost_usd", "critic_cost_usd", "estimated_cost_usd", "token_source", "error",
  ];
  const esc = (v) => {
    const s = v === undefined || v === null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [cols.join(",")].concat(data.test_results.map((r) => cols.map((c) => esc(r[c])).join(",")));
  _downloadBlob(`devbench-report-${data.run_id || "run"}.csv`, lines.join("\n"), "text/csv");
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
    const harnessLabel = data.agent_harness || data.harness || state.selectedHarnessId || "agy";
    titleEl.textContent =
      testCount > 1
        ? `Assessment Results — ${data.model_alias} • Harness: ${harnessLabel} (${testCount} Suite Tests)`
        : `Assessment Results — ${data.model_alias} • Harness: ${harnessLabel}`;
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
            <span class="badge ${tr.passed ? "badge-speed" : "badge-danger"}">${tr.status === "ERROR" ? "ERROR" : tr.passed ? "PASS" : "FAIL"}</span>
            <span class="badge ${tr.is_custom ? "badge-coding" : "badge-recommended"}">${
          tr.is_custom ? "Custom Use Case" : "Standard Benchmark"
        }</span>
            <strong>${escapeHtml(tr.scenario_name || tr.scenario_id)}</strong>
          </div>
          <div style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-secondary);">
            Score: ${Number(tr.rubric_score || 0).toFixed(1)}/5 • ${Number(tr.wall_seconds || tr.duration_seconds || 0).toFixed(2)}s • ${
          fmtInt(tr.total_tokens)
        } tok • ${fmtUsd(tr.estimated_cost_usd)}
          </div>
        </div>
      `
      )
      .join("");
  }

  const acScores = data.actor_critic_scores || {};
  const compScore = acScores.composite_normalized_score || 0;
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
    iconEl.innerHTML = ICONS.brain;
    titleEl.textContent = "Artifact: Agent Skill Package";
    subEl.textContent = "Generates Skill.md specification, Python skill implementation, and automated test suite.";
    pathInput.value = `skills/${scenarioId}`;
  } else if (suiteSlug === "cloud_tool_writing") {
    iconEl.innerHTML = ICONS.cloud;
    titleEl.textContent = "Artifact: GCP Workflow Package";
    subEl.textContent = "Generates cloudbuild.yaml, Dockerfile, provisioning scripts, and README.md.";
    pathInput.value = `workflows/${scenarioId}`;
  } else {
    iconEl.innerHTML = ICONS.codeTransform;
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
  btn.innerHTML = `<span class="btn-icon">${ICONS.spinner}</span> Inserting...`;

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
    btn.innerHTML = `<span class="btn-icon">${ICONS.commit}</span> Insert into Repository`;
  }
}

// ============================================================================
// Quick Right-Side Navigation Dock Controllers
// ============================================================================

function quickNavigateTo(sectionId) {
  const el = document.getElementById(sectionId);
  if (!el) return;

  // If target is gcp-config-panel and it is currently hidden, open it
  if (sectionId === "gcp-config-panel" && el.style.display === "none") {
    toggleGcpConfigPanel();
  }

  // Smooth scroll to section with offset for top header
  const headerHeight = document.querySelector(".app-header")?.offsetHeight || 60;
  const targetPos = el.getBoundingClientRect().top + window.pageYOffset - headerHeight - 16;
  window.scrollTo({ top: Math.max(0, targetPos), behavior: "smooth" });

  // Add brief flash highlight
  el.classList.add("section-flash-highlight");
  setTimeout(() => el.classList.remove("section-flash-highlight"), 1600);

  // Update active item in quick nav dock
  updateActiveQuickNavItem(sectionId);
}

function quickNavigateToTop() {
  window.scrollTo({ top: 0, behavior: "smooth" });
  updateActiveQuickNavItem("gcp-config-panel");
}

function toggleQuickNavDock() {
  const dock = document.getElementById("quick-nav-dock");
  if (dock) {
    dock.classList.toggle("collapsed");
  }
}

function updateActiveQuickNavItem(sectionId) {
  const items = document.querySelectorAll(".quick-nav-item");
  items.forEach((item) => {
    const target = item.getAttribute("data-target");
    item.classList.toggle("active", target === sectionId);
  });
}

function initQuickNavScrollSpy() {
  const sectionIds = [
    "gcp-config-panel",
    "section-select-models",
    "section-select-harness",
    "section-use-case-suite",
    "section-run-eval",
    "eval-report-section",
  ];

  let scrollTimeout = null;
  window.addEventListener(
    "scroll",
    () => {
      if (scrollTimeout) return;
      scrollTimeout = setTimeout(() => {
        scrollTimeout = null;
        const scrollPos = window.pageYOffset + 200;
        let currentId = null;

        for (let i = sectionIds.length - 1; i >= 0; i--) {
          const el = document.getElementById(sectionIds[i]);
          if (el && el.style.display !== "none" && el.offsetTop <= scrollPos) {
            currentId = sectionIds[i];
            break;
          }
        }
        if (currentId) {
          updateActiveQuickNavItem(currentId);
        }
      }, 80);
    },
    { passive: true }
  );
}
