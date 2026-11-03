/** JSON-RPC-over-WebSocket client for the settings backend (/rpc). */

const DEFAULT_TIMEOUT_MS = 8000;
const TOOL_SPACE_TIMEOUT_MS = 60000;

const RPC_URL = `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/rpc`;

class RpcError extends Error {
  constructor(message, reason, data = {}) {
    super(message || reason || "RPC 錯誤");
    // Views branch on error.body.error (the stable reason); keep that contract.
    this.body = { ...data, error: reason };
    this.reason = reason;
  }
}

let socket = null;
let connecting = null;
let rpcCounter = 0;
const pending = new Map(); // id -> { resolve, reject, timer }
const subscribers = new Map(); // method -> Set<cb>

export const retryBackend = () => rpcCall("backend.retry");

/** Open (or reuse) the shared /rpc socket. Resolves once OPEN, rejects on fail. */
function connect() {
  if (socket && socket.readyState === WebSocket.OPEN) return Promise.resolve();
  if (connecting) return connecting;
  connecting = new Promise((resolve, reject) => {
    let opened = false;
    const ws = new WebSocket(RPC_URL);
    socket = ws;
    ws.onopen = () => {
      opened = true;
      connecting = null;
      resolve();
    };
    ws.onmessage = (ev) => handleMessage(JSON.parse(ev.data));
    ws.onclose = () => {
      socket = null;
      connecting = null;
      for (const p of pending.values()) {
        clearTimeout(p.timer);
        p.reject(new RpcError("連線已關閉", "disconnected"));
      }
      pending.clear();
      if (!opened) reject(new RpcError("無法連接 /rpc", "disconnected"));
      // Keep the event stream alive while anyone is listening, across drops and
      // when the page loads before the app has mounted /rpc.
      if (subscribers.size > 0) setTimeout(() => connect().catch(() => {}), 1000);
    };
  });
  return connecting;
}

function handleMessage(msg) {
  if (msg.id != null && ("result" in msg || "error" in msg)) {
    const p = pending.get(msg.id);
    if (!p) return;
    pending.delete(msg.id);
    clearTimeout(p.timer);
    if (msg.error) p.reject(new RpcError(msg.error.message, msg.error.data?.reason, msg.error.data));
    else p.resolve(msg.result);
    return;
  }
  if (typeof msg.method === "string") {
    const cbs = subscribers.get(msg.method);
    if (cbs) for (const cb of cbs) {
      try {
        cb(msg.params || {});
      } catch (e) {
        console.error(`subscribe(${msg.method}) callback threw:`, e);
      }
    }
  }
}

/** Call a JSON-RPC method and await its result. Rejects with RpcError. */
export async function rpcCall(method, params = {}, { timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  await connect();
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    throw new RpcError("尚未連線", "disconnected");
  }
  const id = `ui-${++rpcCounter}`;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new RpcError(`操作逾時：${method}`, "timeout"));
    }, timeoutMs);
    pending.set(id, { resolve, reject, timer });
    socket.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
  });
}

/** Subscribe to a one-way notification (event). Returns an unsubscribe fn. */
export function subscribe(method, cb) {
  let set = subscribers.get(method);
  if (!set) {
    set = new Set();
    subscribers.set(method, set);
  }
  set.add(cb);
  connect().catch(() => {});
  return () => {
    const current = subscribers.get(method);
    current?.delete(cb);
    if (current?.size === 0) subscribers.delete(method);
  };
}

const STARTUP_POLL_MS = 2000;
const STARTUP_DEADLINE_MS = 90000;

/** Retry a request while the backend is still coming up at startup. */
export async function untilReady(requestFn, signal, onRetry) {
  const deadline = Date.now() + STARTUP_DEADLINE_MS;
  let notified = false;
  for (;;) {
    try {
      return await requestFn();
    } catch (error) {
      if (signal.aborted || Date.now() >= deadline) throw error;
      if (!notified) {
        notified = true;
        onRetry?.();
      }
    }
    await new Promise((resolve) => setTimeout(resolve, STARTUP_POLL_MS));
    if (signal.aborted) throw new Error("view unmounted");
  }
}

export const getStatus = () => rpcCall("conversation.status");

export const listPersonalities = () => rpcCall("personalities.list");
export const loadPersonality = (name) => rpcCall("personalities.load", { name });
export const savePersonality = (payload) => rpcCall("personalities.save", payload);
export const applyPersonality = (name, { persist = false, force = false } = {}) =>
  rpcCall("personalities.apply", { name, persist, force });
export const deletePersonality = (name) => rpcCall("personalities.delete", { name });

export const getConversationHistory = () => rpcCall("conversation.history");
export const getMicState = () => rpcCall("conversation.mic", {});
export const setMicMuted = (muted) => rpcCall("conversation.mic", { muted });

export const listVoices = () => rpcCall("voices.list");
export const getCurrentVoice = () => rpcCall("voices.current");
export const applyVoice = (voice) => rpcCall("voices.apply", { voice });

export const getLanguage = () => rpcCall("language.get");
/** scope: "profile" saves for the active personality only, "all" for every personality. */
export const setLanguage = (language, scope) => rpcCall("language.set", { language, scope });

export const saveBackendConfig = (payload) => rpcCall("backend.config", payload);
export const saveSpeechConfig = (payload) => rpcCall("speech.config", payload);

export const listToolSpaces = () => rpcCall("tool_spaces.list");
export const addToolSpace = (slug) =>
  rpcCall("tool_spaces.add", { slug }, { timeoutMs: TOOL_SPACE_TIMEOUT_MS });
export const removeToolSpace = (slug) =>
  rpcCall("tool_spaces.remove", { slug }, { timeoutMs: TOOL_SPACE_TIMEOUT_MS });

export const getProfileTools = (profile) =>
  rpcCall("profile_tools.get", profile ? { profile } : {});
export const saveProfileTools = (profile, enabledTools) =>
  rpcCall("profile_tools.save", { profile, enabled_tools: enabledTools });
export const resetProfileTools = (profile) =>
  rpcCall("profile_tools.reset", { profile });

/** Backend error codes that need friendlier copy than the raw code. */
const ERROR_MESSAGES = Object.freeze({
  invalid_language: "請選擇自動判斷或既有的兩字母語言代碼。",
  invalid_params: "輸入參數不正確，請檢查後重試。",
  camera_forced_off: "相機已透過 --no-camera 停用。",
  disconnected: "連線已中斷，請確認應用程式正在執行後重試。",
  timeout: "操作逾時，請檢查連線後重試。",
  not_running: "對話尚未連線，請先完成連線設定。",
  invalid_backend: "所選後端不明。",
  empty_key: "此後端需要 API 金鑰。",
  empty_hf_host: "請輸入 Hugging Face 主機。",
  invalid_hf_host: "Hugging Face 主機格式不正確。",
  invalid_hf_port: "Hugging Face 連接埠格式不正確。",
  invalid_hf_mode: "Hugging Face 模式不明。",
  missing_hf_session_url: "無法連接 Hugging Face Space，請確認它正在執行。",
  invalid_name: "請輸入有效的人格名稱。",
  invalid_instructions: "請輸入人格指示。",
  profile_exists: "已存在同名人格。",
  invalid_tool_space_slug: "請以 owner/name 格式輸入 Space。",
  invalid_tool_selection: "部分所選工具已無法使用。",
  unknown_profile: "此人格已無法使用。",
  missing_voice: "請先選擇聲音。",
  profile_locked: "管理員已鎖定人格切換。",
  profile_in_use: "此人格正在使用中或已設為啟動預設，請先切換為其他人格。",
  not_deletable: "無法刪除此人格。",
  loop_unavailable: "Reachy 仍在啟動中，請稍後重試。",
  tool_space_not_installed: "此 Tool Space 已不再安裝。",
});

/** Map a thrown error to user-facing copy, falling back to its raw message. */
export function describeError(error) {
  const code = error?.body?.error;
  return ERROR_MESSAGES[code] || error?.body?.detail || error?.message || String(error);
}


export async function geminiCredentialRequest(method = "GET", payload = null, csrfToken = "") {
  const headers = { "X-Credential-Request": "1" };
  if (method !== "GET") {
    headers["Content-Type"] = "application/json";
    headers["X-Credential-CSRF"] = csrfToken;
  }
  let response;
  let status;
  try {
    response = await fetch("/api/gemini-credential", {
      method, headers, cache: "no-store", credentials: "same-origin",
      ...(payload === null ? {} : { body: JSON.stringify(payload) }),
    });
    status = await response.json();
  } catch {
    throw new RpcError("無法確認操作結果，請重新查詢狀態；不會自動重送。", "result_unknown");
  }
  if (!response.ok) throw new RpcError("金鑰設定操作未完成。", status.reason || "service_unavailable", status);
  return status;
}
