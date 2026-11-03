import { geminiCredentialRequest, retryBackend } from "./api.js";
import { confirmDialog } from "./components/confirm-dialog.js";

const input = document.querySelector("#credential-input");
const form = document.querySelector("#credential-form");
const applyButton = document.querySelector("#credential-apply");
const clearButton = document.querySelector("#credential-clear");
const retryButton = document.querySelector("#credential-retry");
const result = document.querySelector("#credential-result");
const summary = document.querySelector("#credential-state");
const impact = document.querySelector("#credential-impact");
const errors = Object.freeze({
  authentication_failed: "認證失敗，請檢查金鑰；原設定未被候選值取代。",
  model_not_available: "目前模型的使用資格不足，請確認帳號與模型設定。",
  invalid_gemini_model: "請回一般設定選擇可用的 Gemini 模型。",
  invalid_gemini_voice: "請回一般設定選擇支援的 Gemini 聲音。",
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
  request_not_allowed: "頁面授權已失效或瀏覽器不支援，請用本機瀏覽器重新開啟此頁。",
  local_access_required: "請在 App 所在電腦以 localhost 或 127.0.0.1 開啟本機金鑰設定頁。",
  invalid_input: "請輸入非空白的金鑰；空白提交不會清除既有設定。",
  session_stop_failed: "無法確認原對話已停止，沒有套用候選值；請檢查 App 後重試。",
  cleanup_pending: "新設定已套用，但舊憑證的清理尚未完成；請確認憑證庫後重試清除。",
});
const sources = { settings: "設定頁（受保護保存）", environment: "既有環境設定", none: "未設定", blocked: "已阻擋，需處理錯誤" };
const validations = { unverified: "尚未驗證", validating: "驗證中", validated: "當次驗證通過", failed: "當次操作失敗" };
const storageNames = { available: "可嘗試保存", locked: "已鎖定", unavailable: "不可用", error: "發生錯誤", busy: "其他行程使用中" };
const applyNames = { idle: "無待套用項目", saving: "正在保存", applied: "已套用", clearing: "清除中", failed: "未完成" };
const connections = { connected: "已連線", connecting: "連線中", disconnected: "已斷線", waiting_for_config: "等待設定／手動重連", not_started: "尚未啟動", restart_required: "需重新啟動" };
let current = null;
let csrfToken = "";
let submitting = false;
let intent = 0;
let refreshing = false;

function render(status) {
  if (current && status.owner_epoch === current.owner_epoch && status.revision < current.revision) return;
  if (current && status.owner_epoch !== current.owner_epoch && !status.csrf_token) return;
  current = status;
  if (status.csrf_token) csrfToken = status.csrf_token;
  summary.textContent = `來源：${sources[status.source] || "未知"}；${validations[status.validation] || "尚未驗證"}；${applyNames[status.apply] || "未知"}；儲存：${storageNames[status.storage] || "未知"}；連線：${connections[status.connection] || "未知"}。`;
  if (status.reason && errors[status.reason]) summary.textContent += ` ${errors[status.reason]}`;
  if (status.manual_reconnect_required) summary.textContent += " Gemini 等待你手動重新連線。";
  impact.textContent = status.backend === "gemini"
    ? "按下驗證並套用會停止目前 Gemini 對話；成功後開始新對話，不保證保留前文。失敗時保留原設定，需手動恢復。"
    : "目前使用 Hugging Face；管理 Gemini 金鑰不會切換供應商或中斷 HF 對話。";
  const pending = submitting || status.validation === "validating" || status.apply === "saving";
  applyButton.disabled = !csrfToken || pending || status.apply === "clearing" || status.source === "blocked";
  clearButton.disabled = !csrfToken || status.apply === "clearing" || status.storage === "busy";
  retryButton.disabled = status.backend !== "gemini" || !status.configured || pending || status.apply === "clearing" || status.source === "blocked";
  form.setAttribute("aria-busy", String(pending));
}

async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
    render(await geminiCredentialRequest());
  } catch (error) {
    summary.textContent = errors[error.reason] || "無法查詢金鑰狀態，請稍後重試。";
    csrfToken = "";
    applyButton.disabled = clearButton.disabled = retryButton.disabled = true;
  } finally {
    refreshing = false;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (applyButton.disabled) return;
  let candidate = input.value.trim();
  input.value = "";
  if (!candidate) {
    result.textContent = errors.invalid_input;
    input.focus();
    return;
  }
  const operation = ++intent;
  submitting = true;
  result.textContent = "正在驗證並保存…";
  render(current);
  try {
    const status = await geminiCredentialRequest("POST", { candidate, expected_revision: current.revision }, csrfToken);
    if (operation === intent) {
      render(status);
      result.textContent = errors[status.reason] || "已驗證並套用；請依目前連線狀態繼續。";
    }
  } catch (error) {
    if (operation === intent) result.textContent = errors[error.reason] || "操作未完成，請重新查詢狀態。";
  } finally {
    candidate = "";
    submitting = false;
    await refresh();
    input.focus();
  }
});

clearButton.addEventListener("click", async () => {
  input.value = "";
  const confirmed = await confirmDialog({
    title: "清除設定頁金鑰？",
    message: "將停止 Gemini 對話並刪除本功能管理的金鑰。既有環境金鑰仍可能可用，但需手動重連。這不會撤銷供應商帳號中的金鑰。",
    confirmLabel: "確認清除", danger: true,
  });
  if (!confirmed) return;
  const operation = ++intent;
  result.textContent = "正在停止 Gemini 並清除…";
  clearButton.disabled = true;
  try {
    const status = await geminiCredentialRequest("DELETE", { expected_revision: current.revision, confirm: true }, csrfToken);
    if (operation === intent) {
      render(status);
      result.textContent = `設定頁金鑰已移除。${status.environment_available ? "既有環境來源仍可使用。" : "目前沒有可用金鑰。"}Gemini 已停止；需手動重新連線。`;
    }
  } catch (error) {
    if (operation === intent) result.textContent = `清除未完成／未確認。${errors[error.reason] || "請重新查詢狀態。"}`;
  } finally {
    await refresh();
  }
});

retryButton.addEventListener("click", async () => {
  try {
    await retryBackend();
    result.textContent = "已要求手動重新連線，請查看連線狀態。";
  } catch {
    result.textContent = "尚未能重新連線，請先確認金鑰與 App 狀態。";
  }
  await refresh();
});
document.querySelector("#credential-cancel").addEventListener("click", () => {
  input.value = "";
  result.textContent = submitting ? "輸入已清空；進行中的操作仍以目前狀態為準。" : "已取消編輯，生效設定不變。";
  input.focus();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") input.value = "";
});
document.querySelector("#credential-refresh").addEventListener("click", refresh);
const timer = setInterval(refresh, 1000);
window.addEventListener("pagehide", () => { input.value = ""; csrfToken = ""; clearInterval(timer); });
window.addEventListener("pageshow", () => { input.value = ""; refresh(); });
refresh();
