# Research: 優先使用繁體中文

研究日期：2026-10-30。依據使用者 A／C／B 釐清與本機原始碼；研究代理只讀盤點前端，未修改檔案。沒有需要外部套件選型或網路研究的未知項目。

## 1. 不新增字形轉換

**Decision**: 只翻譯自有固定文案與附加模型回覆偏好，服務文字原樣顯示。

**Rationale**: 使用者明確選 C。現有 `static/js/components/conversation-panel.js` 以 `textContent` 呈現逐字稿，維持該邊界可保留引用、名稱及簡體輸入。

**Alternatives considered**: 即時轉換、完成後轉換、外部翻譯服務皆不符合已確認範圍；OpenCC 類依賴不需加入或研究。

## 2. 沿用設定與語言代碼

**Decision**: 保留 `language`、`profile_languages`、`zh`、`auto` 及既有預設；不新增地區碼／locale 設定。

**Rationale**: `language_routes.py` 接受兩字母或 auto，`console._set_language()` 已處理全域與人格範圍及存檔，`prompts.get_session_language()` 已實作人格優先。使用者選 B 保留自動判斷。

**Alternatives considered**: 新增 `zh-TW` 回覆代碼、遷移 auto 到 zh 或建立第二份語言儲存都會改變現有契約且沒有需求。

## 3. 在共用提示處表達偏好

**Decision**: 修改 `prompts.get_session_instructions()` 的暫時性語言規則，保留人格與記憶，明確區分預設語言、中文時繁體及當次要求。

**Rationale**: HF 的初始／更新設定與 Gemini 的 setup 都使用同一函式。現有 `Speak only ...` 太絕對，與當次語言例外不一致；auto 不應收到無條件中文指令。

**Alternatives considered**: 在兩個傳輸各自補政策易漂移；修改人格檔或儲存內容違反 FR-010；不以額外模型呼叫糾正字形。

## 4. 就地翻譯介面

**Decision**: 直接翻譯既有自有 HTML／JS 文案，包括輔助標籤；只在已有映射或真實重複處共用顯示文字。

**Rationale**: 前端是原生 ES modules，已有 `api.js` 錯誤映射與設定頁後端原因映射，沒有多語言框架。這次 UI 固定繁體，不需語系切換平台。

**Alternatives considered**: 頁面文字全域取代會誤改服務／使用者內容；新增完整 i18n 平台會擴大單一語言文案需求。

## 5. 分開自有文案與協定資料

**Decision**: 翻譯已知顯示說明，保持 RPC 方法、參數、錯誤碼、列舉、selector、路由與識別碼。未知第三方文字退回原文。

**Rationale**: `api.describeError()` 已支援穩定原因映射及 raw fallback；`conversation.context.message` 目前直接顯示自有伺服器英文，因此也須盤點來源。

**Alternatives considered**: 翻譯所有 RPC 字串、工具 schema 或第三方描述會改變行為或誤把資料當文案。

## 6. 使用現有測試與人工畫面驗收

**Decision**: 延伸 pytest 的提示、設定及 WebSocket 行為測試；十二組原文案例涵蓋部分／完成／歷史文字。瀏覽器實測固定文案、互動與無障礙。環境若已有 Node，可另做 ES module 語法檢查，但不新增執行需求。

**Rationale**: `tests/test_console.py` 已有頁面與 RPC 測試，未建 DOM runner。將每句譯文做 snapshot 不能取代互動驗收；前端測試亦不能證明模型繁體一致性。

**Alternatives considered**: 新增瀏覽器測試框架或只測字串常數都不適合本次最小範圍。

## 7. 明確保留生成限制

**Decision**: 每後端十次代表性中文問答至少九次符合；例外須事先列入案例，不事後將失敗改成引用例外。提示不代表辨識／語音合成語言能力改變。

**Rationale**: 使用者要求「盡量」且禁止事後轉換；原始回覆可讓不遵守偏好的情況被看見。FR-006 不要求改寫服務協定或新增口音能力。

**Alternatives considered**: 保證 100% 生成繁體或失敗時自動重試不符合規格，也可能重複工具副作用。

## 前端盤點

位於 `src/reachy_mini_conversation_app/`：

- `static/index.html`、`static/vad-monitor.html`：頁面語言、固定標題、導覽、提示與無障礙文字。
- `static/js/main.js`、`router.js`、`orb.js`：殼層、狀態與操作提示。
- `static/js/api.js`：錯誤顯示映射與原文 fallback，方法與錯誤原因不變。
- `static/js/views/home.js`、`talk.js`、`settings.js`、`tools.js`：可見狀態、表單、空畫面、確認與錯誤。
- `static/js/components/confirm-dialog.js`、`conversation-panel.js`、`language-picker.js`、`profile-modal.js`、`profile-tools.js`：固定文案、角色／範圍標籤及 dialog 輔助名稱。
- `static/js/ui.js`、`constants.js`、`personality-badge.js`、`pending-apply.js`：檢查但不為翻譯改動穩定 ID、名稱資料或流程。

盤點不表示要翻譯人格名稱、使用者內容、第三方描述或模型工具宣告；完整邊界見 [契約](contracts/language-and-display.md)。所有研究問題已決定，無待釐清項目。
