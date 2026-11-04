/** Settings view: Hugging Face connection, voice, and runtime status. */

import {
  applyVoice,
  describeError,
  getCurrentVoice,
  getStatus,
  listVoices,
  saveBackendConfig,
  retryBackend,
  saveSpeechConfig,
  untilReady,
} from "../api.js";
import { SHOW_LATENCIES_KEY } from "../constants.js";
import { h } from "../ui.js";
import { mountGeminiCredential } from "../gemini-key.js";

const HF_CONNECTION_MODES = Object.freeze({
  DEPLOYED: "deployed",
  LOCAL: "local",
});

const DEFAULT_HF_HOST = "localhost";
const DEFAULT_HF_PORT = 8765;
const BACKEND_ERRORS = Object.freeze({
  missing_gemini_key: "請在下方 Gemini 金鑰區輸入 API key；既有 GEMINI_API_KEY 環境設定仍可使用。",
  invalid_gemini_voice: "請在連線設定選擇支援的 Gemini 聲音。",
  invalid_gemini_model: "請選擇 Gemini Developer API 帳號可使用的 Live 模型。",
  authentication_failed: "請修正所選服務的憑證，重新啟動應用程式後再重試。",
  access_unavailable: "請確認所選帳號的模型存取權與服務使用資格。",
  quota_exceeded: "重試前請確認計費設定與可用額度。",
  tool_schema_unsupported: "已啟用的工具含有不支援的定義。請更新其結構描述或停用該工具。",
  connection_lost: "連線中斷，正在自動重試所選服務。",
  setup_timeout: "連線建立逾時，正在自動重試。",
  send_timeout: "音訊或訊息傳送逾時，正在自動重新連線。",
  resume_unavailable: "無法續接先前對話，正在開始新對話。",
});

const HF_MODE_HINTS = Object.freeze({
  [HF_CONNECTION_MODES.DEPLOYED]: "使用託管的 Hugging Face 後端，無須 API 金鑰。",
  [HF_CONNECTION_MODES.LOCAL]: "直接連接下方的主機與連接埠。",
});

export async function mountSettingsView({ outlet, signal }) {
  const connectionSection = buildConnectionSection({
    onSaved: () =>
      Promise.all([
        refreshStatus({ statusSection, connectionSection, speechSection, signal }),
        refreshVoices({ voiceSection, signal }),
      ]),
  });
  const voiceSection = buildVoiceSection();
  const statusSection = buildStatusSection();
  const speechSection = buildSpeechSection();
  const developerSection = buildDeveloperSection();

  const view = h(
    "section",
    { class: "view view--settings" },
    h(
      "header",
      { class: "view-header" },
      h("h1", { class: "view-title" }, "設定"),
      h("p", { class: "view-subtitle" }, "設定 Reachy Mini 的連線、聲音、語音行為與執行狀態。")
    ),
    connectionSection.element,
    voiceSection.element,
    speechSection.element,
    statusSection.element,
    developerSection
  );
  outlet.replaceChildren(view);
  mountGeminiCredential({ outlet: connectionSection.credentialOutlet, signal });

  await Promise.all([
    refreshStatus({ statusSection, connectionSection, speechSection, signal }),
    refreshVoices({ voiceSection, signal }),
  ]);
  const statusTimer = setInterval(async () => {
    if (signal.aborted) return;
    try { statusSection.render(await getStatus()); }
    catch (error) { statusSection.renderUnavailable(error); }
  }, 2000);
  signal.addEventListener("abort", () => clearInterval(statusTimer), { once: true });
}

function buildConnectionSection({ onSaved } = {}) {
  const providerSelect = h("select", { class: "settings-select", name: "backend" },
    h("option", { value: "huggingface" }, "Hugging Face"),
    h("option", { value: "gemini" }, "Gemini"));
  const modelInput = h("input", { class: "settings-input", name: "gemini_model", value: "gemini-3.8-live" });
  const geminiVoice = h("select", { class: "settings-select", name: "gemini_voice" },
    ...["Aoede", "Charon", "Fenrir", "Kore", "Puck"].map(voice => h("option", { value: voice }, voice)));
  const geminiFields = h("div", { class: "settings-form" },
    h("label", { class: "settings-field" }, "模型", modelInput),
    h("label", { class: "settings-field" }, "Gemini 聲音", geminiVoice),
    h("p", { class: "settings-hint" }, "可直接在下方 Gemini 金鑰區設定；既有 GEMINI_API_KEY 環境入口仍可使用，並需啟用 Gemini Developer API 存取權；服務可能收費。音訊、依請求拍攝的照片及已啟用的共用記憶會傳送至所選服務。切換後會開始新對話，已儲存的記憶仍共用。"));
  const hfModeSelect = h(
    "select",
    { class: "settings-select", name: "hf_mode" },
    h("option", { value: HF_CONNECTION_MODES.DEPLOYED }, "託管"),
    h("option", { value: HF_CONNECTION_MODES.LOCAL }, "本機")
  );
  const hfHostInput = h("input", {
    type: "text",
    name: "hf_host",
    autocomplete: "off",
    placeholder: DEFAULT_HF_HOST,
    value: DEFAULT_HF_HOST,
    class: "settings-input",
  });
  const hfPortInput = h("input", {
    type: "number",
    name: "hf_port",
    min: "1",
    max: "65535",
    step: "1",
    inputmode: "numeric",
    value: String(DEFAULT_HF_PORT),
    class: "settings-input",
  });
  const hfLocalFields = h(
    "div",
    { class: "settings-field-row", "data-role": "hf-local-fields" },
    h(
      "label",
      { class: "settings-field" },
      h("span", { class: "settings-label" }, "主機／IP"),
      hfHostInput
    ),
    h(
      "label",
      { class: "settings-field" },
      h("span", { class: "settings-label" }, "連接埠"),
      hfPortInput
    )
  );
  const hint = h("p", { class: "settings-hint" }, "");
  const status = h("p", { class: "settings-status", role: "status", "aria-live": "polite" });
  const submitButton = h("button", { type: "submit", class: "btn btn--primary" }, "儲存連線");

  const form = h(
    "form",
    { class: "settings-form" },
    h("label", { class: "settings-field" }, "對話服務供應商", providerSelect),
    geminiFields,
    h(
      "label",
      { class: "settings-field" },
      h("span", { class: "settings-label" }, "Hugging Face 連線"),
      hfModeSelect
    ),
    hfLocalFields,
    hint,
    h("div", { class: "settings-actions" }, submitButton),
    status
  );

  const credentialOutlet = h("div", { class: "credential-controls" });
  const credentialSummary = h("p", { class: "settings-hint", role: "status" }, "Gemini 金鑰狀態尚未確認。");
  const credentialEntry = h("div", { class: "settings-form" },
    h("h3", {}, "Gemini 金鑰"),
    credentialSummary,
    credentialOutlet);
  const element = h(
    "section",
    { class: "settings-section" },
    h("h2", { class: "settings-section-title" }, "連線"),
    form,
    credentialEntry
  );

  function syncLocalFields() {
    const isGemini = providerSelect.value === "gemini";
    geminiFields.hidden = !isGemini;
    hfModeSelect.parentElement.hidden = isGemini;
    const isLocal = !isGemini && hfModeSelect.value === HF_CONNECTION_MODES.LOCAL;
    hfLocalFields.style.display = isLocal ? "" : "none";
    hfHostInput.disabled = !isLocal;
    hfPortInput.disabled = !isLocal;
    hfHostInput.required = isLocal;
    hfPortInput.required = isLocal;
    hint.textContent = isGemini ? "可在下方 Gemini 金鑰區修正憑證；若連線已停止，請明確按重試。" : HF_MODE_HINTS[hfModeSelect.value] || "";
  }

  providerSelect.addEventListener("change", syncLocalFields);
  hfModeSelect.addEventListener("change", syncLocalFields);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitButton.disabled) return;
    submitButton.disabled = true;
    hfModeSelect.disabled = true;
    hfHostInput.disabled = true;
    hfPortInput.disabled = true;
    form.setAttribute("aria-busy", "true");
    status.classList.remove("is-error");
    status.textContent = "儲存中…";
    try {
      const isGemini = providerSelect.value === "gemini";
      const payload = isGemini
        ? { backend: "gemini", gemini_model: modelInput.value.trim(), gemini_voice: geminiVoice.value }
        : { backend: "huggingface", hf_mode: hfModeSelect.value };
      if (!isGemini && hfModeSelect.value === HF_CONNECTION_MODES.LOCAL) {
        payload.hf_host = hfHostInput.value.trim();
        if (hfPortInput.value) {
          payload.hf_port = Number.parseInt(hfPortInput.value, 10);
        }
      }
      const result = await saveBackendConfig(payload);
      status.textContent =
        result?.message || (result?.requires_restart ? "已儲存，請重新啟動應用程式以套用。" : "已儲存。");
      await onSaved?.();
    } catch (error) {
      status.textContent = `儲存失敗：${describeError(error)}`;
      status.classList.add("is-error");
    } finally {
      submitButton.disabled = false;
      hfModeSelect.disabled = false;
      syncLocalFields();
      form.removeAttribute("aria-busy");
    }
  });

  syncLocalFields();

  return {
    element,
    credentialOutlet,
    syncFromStatus(payload) {
      const credential = payload?.gemini_credential;
      const sourceLabels = { settings: "設定頁（受保護保存）", environment: "既有環境設定", none: "未設定", blocked: "已阻擋，請處理憑證錯誤" };
      credentialSummary.textContent = credential
        ? `Gemini 金鑰來源：${sourceLabels[credential.source] || "未知"}。${credential.manual_reconnect_required ? "等待手動重連。" : ""}保存不代表已驗證或已連線。`
        : "Gemini 金鑰管理尚未初始化；請確認 App 已更新並重新啟動。";
      providerSelect.value = payload?.backend || "huggingface";
      modelInput.value = payload?.gemini_model || "gemini-3.8-live";
      geminiVoice.value = payload?.gemini_voice || "Kore";
      if (Object.values(HF_CONNECTION_MODES).includes(payload?.hf_connection_mode)) {
        hfModeSelect.value = payload.hf_connection_mode;
      }
      if (payload?.hf_direct_host) {
        hfHostInput.value = payload.hf_direct_host;
      }
      if (payload?.hf_direct_port != null) {
        hfPortInput.value = String(payload.hf_direct_port);
      }
      syncLocalFields();
    },
  };
}

function buildVoiceSection() {
  const select = h(
    "select",
    { class: "settings-select", name: "voice", disabled: "disabled" },
    h("option", { value: "" }, "正在載入聲音…")
  );
  const status = h("p", { class: "settings-status", role: "status", "aria-live": "polite" });
  const submitButton = h(
    "button",
    { type: "submit", class: "btn btn--primary", disabled: "disabled" },
    "套用聲音"
  );
  const form = h(
    "form",
    { class: "settings-form" },
    h("label", { class: "settings-field" }, h("span", { class: "settings-label" }, "聲音"), select),
    h("div", { class: "settings-actions" }, submitButton),
    status
  );

  const element = h(
    "section",
    { class: "settings-section" },
    h("h2", { class: "settings-section-title" }, "聲音"),
    form
  );

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitButton.disabled || !select.value) return;
    submitButton.disabled = true;
    select.disabled = true;
    form.setAttribute("aria-busy", "true");
    status.classList.remove("is-error");
    status.textContent = "套用中…";
    try {
      const result = await applyVoice(select.value);
      status.textContent = result?.status || "聲音已套用。";
    } catch (error) {
      status.textContent = `套用失敗：${describeError(error)}`;
      status.classList.add("is-error");
    } finally {
      submitButton.disabled = !select.value;
      select.disabled = !select.value;
      form.removeAttribute("aria-busy");
    }
  });

  return {
    element,
    setOptions(voices, current) {
      select.replaceChildren();
      if (!voices.length) {
        select.appendChild(h("option", { value: "" }, "沒有可用的聲音"));
        select.disabled = true;
        submitButton.disabled = true;
        status.textContent = "目前無法取得聲音列表。";
        return;
      }
      for (const v of voices) {
        const opt = h("option", { value: v }, v);
        if (v === current) opt.selected = true;
        select.appendChild(opt);
      }
      select.disabled = false;
      submitButton.disabled = false;
      status.textContent = "";
    },
  };
}

function buildSpeechSection() {
  const localVad = h("input", { type: "checkbox", name: "local_vad_enabled", disabled: "disabled" });
  const localBargeIn = h("input", { type: "checkbox", name: "local_barge_in_enabled", disabled: "disabled" });
  const status = h("p", { class: "settings-status", role: "status", "aria-live": "polite" });
  const submitButton = h("button", { type: "submit", class: "btn btn--primary", disabled: "disabled" }, "儲存語音設定");
  const form = h("form", { class: "settings-form" },
    h("label", { class: "settings-toggle" }, localVad,
      h("span", {}, h("strong", {}, "本機語音偵測"),
        h("span", { class: "settings-hint" }, "在機器人端偵測語音，以更快暫停天線與待機動作。"))),
    h("label", { class: "settings-toggle" }, localBargeIn,
      h("span", {}, h("strong", {}, "本機插話"),
        h("span", { class: "settings-hint" }, "你說話時更快停止機器人的語音。需要啟用本機語音偵測。"))),
    h("p", { class: "settings-hint" }, "儲存變更後會重新連接對話以套用。"),
    h("div", { class: "settings-actions" }, submitButton), status);
  const element = h("section", { class: "settings-section" },
    h("h2", { class: "settings-section-title" }, "語音行為"), form);

  localVad.addEventListener("change", () => { localBargeIn.disabled = !localVad.checked; });

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (submitButton.disabled) return;
    submitButton.disabled = true;
    localVad.disabled = true;
    localBargeIn.disabled = true;
    form.setAttribute("aria-busy", "true");
    status.classList.remove("is-error");
    status.textContent = "儲存中…";
    try {
      const result = await saveSpeechConfig({ local_vad_enabled: localVad.checked, local_barge_in_enabled: localBargeIn.checked });
      localVad.checked = result.local_vad_enabled;
      localBargeIn.checked = result.local_barge_in_enabled;
      status.textContent = result.message || "已儲存。";
    } catch (error) {
      status.textContent = `儲存失敗：${describeError(error)}`;
      status.classList.add("is-error");
    } finally {
      submitButton.disabled = false;
      localVad.disabled = false;
      localBargeIn.disabled = !localVad.checked;
      form.removeAttribute("aria-busy");
    }
  });
  return {
    element,
    syncFromStatus(payload) {
      localVad.checked = payload.local_vad_enabled;
      localBargeIn.checked = payload.local_barge_in_enabled;
      localVad.disabled = false;
      localBargeIn.disabled = !localVad.checked;
      submitButton.disabled = false;
    },
  };
}

function buildDeveloperSection() {
  const showLatencies = h("input", {
    type: "checkbox",
    name: "show_latencies",
    checked: localStorage.getItem(SHOW_LATENCIES_KEY) === "1",
    onChange: (event) => localStorage.setItem(SHOW_LATENCIES_KEY, event.target.checked ? "1" : "0"),
  });
  return h(
    "details",
    { class: "settings-section settings-developer" },
    h("summary", { class: "settings-section-title" }, "開發者選項"),
    h(
      "div",
      { class: "settings-form" },
      h(
        "label",
        { class: "settings-toggle" },
        showLatencies,
        h(
          "span",
          {},
          h("strong", {}, "顯示回覆延遲"),
          h("span", { class: "settings-hint" }, "在對話面板的各則回覆下顯示後端各階段耗時。")
        )
      )
    )
  );
}

function buildStatusSection() {
  const retry = h("button", { type: "button", class: "btn" }, "重試連線");
  retry.addEventListener("click", async () => {
    retry.disabled = true;
    try { await retryBackend(); }
    finally { retry.disabled = false; }
  });
  const list = h(
    "dl",
    { class: "settings-status-grid" },
    statusRow("後端", "載入中…")
  );
  const element = h(
    "section",
    { class: "settings-section" },
    h("h2", { class: "settings-section-title" }, "目前狀態"),
    list,
    retry
  );

  return {
    element,
    render(payload) {
      list.replaceChildren();
      list.appendChild(statusRow("供應商", payload.backend === "gemini" ? "Gemini" : "Hugging Face"));
      list.appendChild(statusRow("對話上下文", payload.backend_context_state === "resumed" ? "已續接" : "新對話"));
      if (payload.backend_retry_delay_seconds != null) {
        list.appendChild(statusRow("恢復狀態", `${payload.backend_retry_delay_seconds} 秒後進行第 ${payload.backend_retry_attempt} 次自動重試`));
      }
      if (payload.backend === "huggingface") {
      list.appendChild(statusRow("HF connection", formatHfMode(payload.hf_connection_mode)));
      if (payload.hf_connection_mode === HF_CONNECTION_MODES.LOCAL) {
        list.appendChild(statusRow("HF target", formatHfTarget(payload)));
      }
      }
      list.appendChild(
        statusRow(
          "設定",
          payload.can_proceed ? "就緒" : "尚未設定",
          payload.can_proceed ? "ok" : "warn"
        )
      );
      const backendState = payload.backend_connected
        ? "connected"
        : payload.backend_connection_state || "not_started";
      const backendLabels = {
        connected: "已連線",
        connecting: "連線中…",
        disconnected: "已斷線",
        not_started: "尚未啟動",
        restart_required: "需要重新啟動",
        waiting_for_config: "等待設定",
      };
      list.appendChild(
        statusRow(
          "後端",
          backendLabels[backendState] || "無法使用",
          backendState === "connected" ? "ok" : backendState === "not_started" ? undefined : "warn"
        )
      );
      if (payload.backend_error) {
        list.appendChild(statusRow("後端錯誤", BACKEND_ERRORS[payload.backend_error_reason] || payload.backend_error, "warn"));
      }
      if (payload.requires_restart) {
        list.appendChild(statusRow("重新啟動", "需要重新啟動以套用變更", "warn"));
      }
    },
    renderUnavailable(error) {
      list.replaceChildren(statusRow("後端", `無法使用：${describeError(error)}`, "warn"));
    },
  };
}

function statusRow(label, value, tone) {
  return h(
    "div",
    { class: ["settings-status-row", tone && `is-${tone}`] },
    h("dt", { class: "settings-status-label" }, label),
    h("dd", { class: "settings-status-value" }, value)
  );
}

function formatHfMode(mode) {
  if (mode === HF_CONNECTION_MODES.LOCAL) return "本機";
  if (mode === HF_CONNECTION_MODES.DEPLOYED) return "託管";
  return "-";
}

function formatHfTarget(payload) {
  const host = payload?.hf_direct_host;
  const port = payload?.hf_direct_port;
  if (!host) return "-";
  return `${host}:${port || DEFAULT_HF_PORT}`;
}

async function refreshStatus({ statusSection, connectionSection, speechSection, signal }) {
  try {
    const payload = await untilReady(getStatus, signal);
    if (signal.aborted) return;
    statusSection.render(payload);
    connectionSection.syncFromStatus(payload);
    speechSection.syncFromStatus(payload);
  } catch (error) {
    if (signal.aborted) return;
    statusSection.renderUnavailable(error);
  }
}

async function refreshVoices({ voiceSection, signal }) {
  let voices = [];
  let current = "";
  try {
    voices = await untilReady(listVoices, signal);
  } catch {
    voices = [];
  }
  if (signal.aborted) return;
  try {
    const data = await getCurrentVoice();
    current = data?.voice || "";
  } catch {
    current = "";
  }
  if (signal.aborted) return;
  voiceSection.setOptions(voices, current);
}
