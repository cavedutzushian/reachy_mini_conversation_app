import { geminiCredentialRequest, retryBackend } from "./api.js";
import { confirmDialog } from "./components/confirm-dialog.js";
import { h } from "./ui.js";

/** Check whether this browser location permits local credential controls. */
export function canManageGeminiCredential() {
  try {
    if (location.protocol !== "http:" || !["localhost", "127.0.0.1", "[::1]"].includes(location.hostname)
      || !["/", "/static/index.html"].includes(location.pathname)) return false;
    if (window.top === window) return true;
    const ancestors = Array.from(location.ancestorOrigins || []);
    const allowed = new Set([location.origin, "http://tauri.localhost"]);
    return ancestors.length > 0 && ancestors.every(origin => allowed.has(origin));
  } catch {
    console.warn("無法確認內嵌來源；金鑰管理保持只讀。");
    return false;
  }
}

const errors = Object.freeze({
  authentication_failed: "認證失敗，請檢查金鑰；原設定未被候選值取代。",
  model_not_available: "目前模型的使用資格不足，請確認帳號與模型設定。",
  invalid_gemini_model: "請在上方連線設定選擇可用的 Gemini 模型。",
  invalid_gemini_voice: "請在上方連線設定選擇支援的 Gemini 聲音。",
  quota_exceeded: "額度或請求限制已達上限，請確認可用額度後再操作。",
  service_unavailable: "目前無法連接服務，不代表金鑰無效；請稍後手動重試。",
  validation_timeout: "驗證逾時，不代表金鑰無效；請確認網路後手動重試。",
  storage_unavailable: "無可用的受保護憑證庫；請設定系統憑證服務，或維持既有環境設定。",
  storage_locked: "憑證庫已鎖定，請在作業系統解鎖後重試；若啟動時讀取已失敗，請重新啟動 App 再手動重連。",
  storage_failed: "憑證保存／刪除未完成，請確認系統憑證庫與實例資料夾；修正啟動讀取錯誤後請重新啟動 App，再查詢狀態。",
  storage_busy: "另一個行程正在管理此實例，請關閉重複 App 後再試。",
  result_unknown: "操作結果尚未確認，請重新查詢；不會自動重送。",
  revision_conflict: "設定已被其他操作變更，請查看最新狀態，再明確操作。",
  superseded: "此操作已被較新的設定或清除取代，請查看目前狀態。",
  request_not_allowed: "頁面授權已失效或瀏覽器不支援，請重新載入設定頁。",
  local_access_required: "請在 App 所在電腦以 localhost 或 127.0.0.1 開啟一般設定頁。",
  invalid_input: "請輸入非空白的金鑰；空白提交不會清除既有設定。",
  session_stop_failed: "無法確認原對話已停止，沒有套用候選值；請檢查 App 後重試。",
  cleanup_pending: "新設定已套用，但舊憑證的清理尚未完成；請確認憑證庫後重試清除。",
});
const sources = { settings: "設定頁（受保護保存）", environment: "既有環境設定", none: "未設定", blocked: "已阻擋，需處理錯誤" };
const validations = { unverified: "尚未驗證", validating: "驗證中", validated: "當次驗證通過", failed: "當次操作失敗" };
const storageNames = { available: "可嘗試保存", locked: "已鎖定", unavailable: "不可用", error: "發生錯誤", busy: "其他行程使用中" };
const applyNames = { idle: "無待套用項目", saving: "正在保存", applied: "已套用", clearing: "清除中", failed: "未完成" };
const connections = { connected: "已連線", connecting: "連線中", disconnected: "已斷線", waiting_for_config: "等待設定／手動重連", not_started: "尚未啟動", restart_required: "需重新啟動" };

/** Mount ephemeral credential controls and return their disposer. */
export function mountGeminiCredential({ outlet, signal }) {
  let generation = 0;
  let disposed = false;
  let requests = null;
  let timer = null;
  let controls = null;
  let current = null;
  let csrfToken = "";
  let intent = 0;
  let completedMutation = 0;
  let submitting = false;
  let clearing = false;
  let refreshing = false;

  function suspend() {
    generation++;
    requests?.abort();
    requests = null;
    clearInterval(timer);
    timer = null;
    if (controls) controls.input.value = "";
    controls = null;
    csrfToken = "";
    current = null;
    submitting = clearing = refreshing = false;
    outlet.replaceChildren();
  }
  function active(epoch) {
    if (disposed || signal?.aborted || generation !== epoch) return false;
    if (canManageGeminiCredential()) return true;
    suspend();
    outlet.append(h("p", { class: "settings-hint" }, "此入口只能檢視金鑰狀態，無法確認本機管理權限。"));
    return false;
  }
  function render(status) {
    if (current && status.owner_epoch === current.owner_epoch && status.revision < current.revision) return;
    if (current && status.owner_epoch !== current.owner_epoch && !status.csrf_token) return;
    current = status;
    if (status.csrf_token) csrfToken = status.csrf_token;
    if (!controls) return;
    controls.summary.textContent = `來源：${sources[status.source] || "未知"}；${validations[status.validation] || "尚未驗證"}；${applyNames[status.apply] || "未知"}；儲存：${storageNames[status.storage] || "未知"}；連線：${connections[status.connection] || "未知"}。`;
    if (status.reason && errors[status.reason]) controls.summary.textContent += ` ${errors[status.reason]}`;
    if (status.manual_reconnect_required) controls.summary.textContent += " Gemini 等待你手動重新連線。";
    controls.impact.textContent = status.backend === "gemini"
      ? "驗證並套用會停止目前 Gemini 對話；成功後開始新對話，不保證保留前文。失敗時原設定保留，需手動恢復。"
      : "目前使用 Hugging Face；管理 Gemini 金鑰不會切換供應商或中斷 HF 對話。";
    const pending = submitting || status.validation === "validating" || status.apply === "saving";
    controls.apply.disabled = !csrfToken || pending || clearing || status.apply === "clearing" || status.source === "blocked";
    controls.clear.disabled = !csrfToken || clearing || status.apply === "clearing" || status.storage === "busy";
    controls.retry.disabled = status.backend !== "gemini" || !status.configured || pending || clearing || status.apply === "clearing" || status.source === "blocked";
    controls.form.setAttribute("aria-busy", String(pending || clearing));
  }
  async function refresh(epoch) {
    if (!active(epoch) || refreshing) return;
    const operation = intent;
    const completion = completedMutation;
    refreshing = true;
    try {
      const status = await geminiCredentialRequest("GET", null, "", requests.signal);
      if (active(epoch) && operation === intent && completion === completedMutation) render(status);
    } catch (error) {
      if (active(epoch) && operation === intent && completion === completedMutation) {
        suspend();
        showUnavailable(errors[error.reason] || "無法查詢金鑰狀態，請稍後重試。");
      }
    } finally {
      if (generation === epoch) refreshing = false;
    }
  }
  function showUnavailable(message) {
    outlet.replaceChildren(h("p", { class: "settings-hint", role: "status" }, message),
      h("button", { class: "btn btn--ghost", type: "button", onclick: start }, "重新查詢金鑰狀態"));
  }
  async function start() {
    if (disposed || signal?.aborted) return;
    suspend();
    const epoch = generation;
    if (!active(epoch)) return;
    requests = new AbortController();
    outlet.append(h("p", { class: "settings-hint", role: "status" }, "正在確認金鑰設定…"));
    try {
      const status = await geminiCredentialRequest("GET", null, "", requests.signal);
      if (!active(epoch)) return;
      if (!status.csrf_token) throw new Error("Missing credential authorization");
      render(status);
      const input = h("input", { id: "credential-input", class: "settings-input", type: "password", autocomplete: "off", spellcheck: "false", autocapitalize: "none", "aria-describedby": "credential-privacy" });
      const apply = h("button", { id: "credential-apply", class: "btn btn--primary", type: "submit" }, "驗證並套用");
      const cancel = h("button", { id: "credential-cancel", class: "btn btn--ghost", type: "button" }, "取消編輯");
      const clear = h("button", { id: "credential-clear", class: "btn btn--danger", type: "button" }, "清除設定頁金鑰");
      const retry = h("button", { id: "credential-retry", class: "btn btn--ghost", type: "button" }, "手動重新連線 Gemini");
      const reload = h("button", { id: "credential-refresh", class: "btn btn--ghost", type: "button" }, "重新查詢狀態");
      const summary = h("p", { id: "credential-state", class: "settings-hint", role: "status", "aria-live": "polite" });
      const impact = h("p", { id: "credential-impact", class: "settings-hint" });
      const result = h("p", { id: "credential-result", class: "settings-status", role: "status", "aria-live": "polite" });
      const form = h("form", { id: "credential-form", class: "settings-form" },
        h("label", { class: "settings-field", for: "credential-input" }, "新的 Gemini API key", input),
        h("p", { id: "credential-privacy", class: "settings-hint" }, "金鑰跨重啟保存在系統憑證庫，不會顯示既存值。驗證只檢查所選模型連線資格，不傳送對話、人格、音訊或工具；服務可能計入額度。"),
        h("div", { class: "settings-actions credential-actions" }, apply, cancel, clear));
      controls = { input, form, apply, clear, retry, summary, impact, result };
      outlet.replaceChildren(summary, impact, form, result, h("div", { class: "settings-actions credential-actions" }, reload, retry));
      const events = { signal: requests.signal };

      form.addEventListener("submit", async event => {
        event.preventDefault();
        if (!active(epoch) || apply.disabled) return;
        let candidate = input.value.trim();
        input.value = "";
        if (!candidate) { result.textContent = errors.invalid_input; input.focus(); return; }
        const operation = ++intent;
        submitting = true;
        result.textContent = "正在驗證並保存…";
        render(current);
        try {
          const status = await geminiCredentialRequest("POST", { candidate, expected_revision: current.revision }, csrfToken, requests.signal);
          if (active(epoch) && operation === intent) {
            completedMutation++;
            render(status);
            result.textContent = errors[status.reason] || "已驗證並套用；請依目前連線狀態繼續。";
          }
        } catch (error) {
          if (active(epoch) && operation === intent) result.textContent = errors[error.reason] || "操作未完成，請重新查詢狀態。";
        } finally {
          candidate = "";
          if (active(epoch) && operation === intent) submitting = false;
          await refresh(epoch);
          if (active(epoch)) input.focus();
        }
      }, events);
      clear.addEventListener("click", async () => {
        if (!active(epoch) || clear.disabled) return;
        input.value = "";
        const confirmed = await confirmDialog({ title: "清除設定頁金鑰？", message: "將停止 Gemini 並刪除本功能管理的金鑰。既有環境來源仍可能可用，但需手動重連；這不會撤銷供應商帳號中的金鑰。", confirmLabel: "確認清除", danger: true, signal: requests.signal });
        if (!confirmed || !active(epoch)) return;
        const operation = ++intent;
        submitting = false;
        clearing = true;
        result.textContent = "正在停止 Gemini 並清除…";
        render(current);
        try {
          const latest = await geminiCredentialRequest("GET", null, "", requests.signal);
          if (!active(epoch) || operation !== intent) return;
          render(latest);
          const status = await geminiCredentialRequest("DELETE", { expected_revision: current.revision, confirm: true }, csrfToken, requests.signal);
          if (active(epoch) && operation === intent) {
            completedMutation++;
            render(status);
            result.textContent = `設定頁金鑰已移除。${status.environment_available ? "既有環境來源仍可使用。" : "目前沒有可用金鑰。"}Gemini 已停止；需手動重新連線。`;
          }
        } catch (error) {
          if (active(epoch) && operation === intent) result.textContent = `清除未完成／未確認。${errors[error.reason] || "請重新查詢狀態。"}`;
        } finally {
          if (active(epoch) && operation === intent) clearing = false;
          await refresh(epoch);
        }
      }, events);
      retry.addEventListener("click", async () => {
        if (!active(epoch) || retry.disabled) return;
        try {
          await retryBackend();
          if (active(epoch)) result.textContent = "已要求手動重新連線，請查看連線狀態。";
        } catch {
          if (active(epoch)) result.textContent = "尚未能重新連線，請確認金鑰與 App 狀態。";
        }
        await refresh(epoch);
      }, events);
      cancel.addEventListener("click", () => {
        input.value = "";
        result.textContent = submitting ? "輸入已清空；進行中的操作仍以目前狀態為準。" : "已取消編輯，生效設定不變。";
        input.focus();
      }, events);
      window.addEventListener("keydown", event => { if (event.key === "Escape") input.value = ""; }, events);
      reload.addEventListener("click", () => refresh(epoch), events);
      render(status);
      timer = setInterval(() => refresh(epoch), 1000);
    } catch (error) {
      if (active(epoch)) {
        suspend();
        showUnavailable(errors[error.reason] || "無法確認金鑰設定權限，請稍後重試。");
      }
    }
  }
  function dispose() {
    disposed = true;
    suspend();
    window.removeEventListener("pagehide", suspend);
    window.removeEventListener("pageshow", start);
    signal?.removeEventListener("abort", dispose);
  }
  if (signal?.aborted) {
    dispose();
    return dispose;
  }
  window.addEventListener("pagehide", suspend);
  window.addEventListener("pageshow", start);
  signal?.addEventListener("abort", dispose, { once: true });
  start();
  return dispose;
}
