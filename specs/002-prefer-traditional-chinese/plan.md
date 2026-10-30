# Implementation Plan: 優先使用繁體中文

**Branch**: `feat/002-prefer-traditional-chinese` | **Date**: 2026-10-30 | **Spec**: [spec.md](spec.md)

**Input**: `specs/002-prefer-traditional-chinese/spec.md`，包含 A／C／B 三項使用者釐清。

## Summary

沿用現有 HTML、原生 JavaScript 模組與共用提示組裝，翻譯應用程式自有介面文案，並要求模型在回覆中文時優先使用繁體。服務回覆與逐字稿原文不改寫；自動語言、非中文設定、人格、聲音及工具行為不變。不新增字形轉換、翻譯服務、多語言平台或依賴。

## Technical Context

**Language/Version**: Python >=3.12；既有瀏覽器 JavaScript ES modules、HTML/CSS。

**Primary Dependencies**: 既有 Reachy Mini SDK、FastAPI、HF/OpenAI 相容連線與 Gemini WebSocket；無新套件或版本調整。

**Storage**: 沿用 `settings.json` version 1 的 `language`、`profile_languages`；不新增欄位、環境變數或資料遷移。記憶、歷史及人格檔案不改寫。

**Testing**: 既有 pytest、strict mypy、Ruff；補上共用提示、兩後端設定、RPC 與原文保留測試。現有專案沒有 DOM 測試執行環境，畫面與無障礙檢查採實際瀏覽器驗收。

**Target Platform**: 既有 Linux、macOS、Windows 與 Reachy 部署；不改 SDK 內部。

**Project Type**: 既有單一機器人對話應用程式與本機設定介面。

**Performance Goals**: 每後端十次中文問答至少九次符合繁體偏好；十二組原文保留案例全過。沒有新增網路翻譯、額外生成、逐字處理或等待整段輸出的步驟，不新增回覆延遲門檻。

**Constraints**: `zh`、`auto` 及現有語言代碼不變；自動模式不強制中文。明確的當次語言／原文要求可優先於預設提示，但不改存檔或辨識／語音協定設定。不保證模型或辨識服務永遠使用繁體。

**Scale/Scope**: 兩個既有後端、全部自有可見介面與提示；不翻譯第三方資料、使用者輸入、開發者日誌或整個專案文件。

## Constitution Check

| 原則 | 設計前檢查 | 設計後檢查 |
|---|---|---|
| SDK 與既有架構 | 沿用公開介面與共用提示 | 通過；不改 SDK、傳輸或對話生命週期 |
| 最小可維護差異 | 就地翻譯固定文案，重用錯誤映射 | 通過；不新增 i18n 框架、轉換器或平行設定 |
| 錯誤與日誌 | 翻譯自有提示，保留錯誤碼及原始資訊 | 通過；不隱藏失敗、不翻譯 logger 文案 |
| 行為測試與品質 | 先測語言選擇、提示優先順序及原文保留 | 通過設計；實作時仍須完整品質檢查，未宣稱新功能測試已跑 |
| 人工審閱與範圍 | 延續已授權個人客製化 | 通過；不建立 PR，未來上游貢獻仍依 Issue／人工審閱流程 |
| 相容與文件 | Python 3.12、現有儲存與 RPC 契約 | 通過；更新根 README，不改受保護文件／CI，不新增 docs/ Markdown |

沒有憲章例外，也沒有尚待釐清的技術選擇。研究依據見 [research.md](research.md)。

## Project Structure

### Documentation (this feature)

```text
specs/002-prefer-traditional-chinese/
  spec.md
  plan.md
  research.md
  data-model.md
  contracts/language-and-display.md
  quickstart.md
  checklists/requirements.md
```

`tasks.md` 由下一階段 `$speckit-tasks` 產生。

### Source Code (repository root)

```text
src/reachy_mini_conversation_app/
  prompts.py
  console.py
  language_routes.py
  personality_routes.py, memory_routes.py, vision_routes.py
  tool_space_routes.py, profile_tool_routes.py
  static/index.html, static/vad-monitor.html
  static/js/api.js, main.js, router.js, orb.js
  static/js/views/{home,talk,settings,tools}.js
  static/js/components/{confirm-dialog,conversation-panel,language-picker,profile-modal,profile-tools}.js
tests/
  test_huggingface_realtime.py
  test_gemini_realtime.py
  test_console.py
  test_language_vision_routes.py
  test_settings_store.py
  test_startup_settings.py
```

保留現有結構；上述路徑為檢查／可能修改範圍，不代表每個檔案均必須改動。`ui.js`、`constants.js`、`personality-badge.js`、`pending-apply.js` 亦需盤點，但不得為翻譯而更動穩定名稱與識別值。

## Design

### 回覆偏好

在 `prompts.get_session_instructions()` 組裝暫時性指示，不改寫人格或記憶原文。語言優先順序維持人格專屬設定高於全域設定，再沿用既有預設。

- `zh`：預設中文、繁體優先；保留當次原文、翻譯及其他語言要求。
- `auto`：保持原有語言判斷，只附加「若回答中文，優先繁體」的條件，不加入預設中文或固定辨識語言指令。
- 其他語言：保留原語言預設；若使用者明確要求當次中文，該中文回覆仍優先繁體。
- 明確要求簡體原文、引用、程式碼、網址、名稱與識別碼時，提示要求保留原樣；不做文字偵測、重試或事後改寫。

目前無條件的 `Speak only ...` 提示須調整為預設語言規則與明確例外，相關既有測試需改驗行為而非保留舊句子。兩個後端沿用相同指示；不另寫 Gemini 專用中文政策，不增加服務不接受的地區語言代碼。辨識與語音合成能力仍由既有後端控制，不將文字提示解讀為能力保證。

### 介面與錯誤

就地翻譯自有 HTML／JS 文案，包括載入、空白、確認／取消、重連、延遲標籤、`title` 與無障礙名稱；頁面語言標記為 `zh-Hant`。重複顯示文案沿用既有映射，不建通用翻譯呼叫層。

`api.js` 的 `ERROR_MESSAGES`、設定頁的既有後端原因映射維持穩定 key，僅翻譯顯示值。未知第三方錯誤保留原文，必要時加固定繁體說明。`console.py` 的 `conversation.context.message`、設定操作回傳的自有 `message` 及其他路由的人類可讀固定提示也須盤點，不能僅翻譯前端按鈕。機器可讀錯誤碼與結構不變。

工具的呼叫名稱、參數、狀態與模型宣告不為 UI 翻譯而更動。自有工具如需繁體顯示名稱／固定說明，使用既有工具畫面的顯示對照；第三方說明與使用者內容保留原樣。

### 原文與儲存邊界

`conversation.transcript`、完成事件、歷史內容及前端 `textContent` 路徑不新增字形處理。只翻譯周圍角色／狀態標籤，不改 `text`。模型回傳簡體是可見的模型偏好未遵守案例，不以轉換、隱藏或重新生成掩蓋。

沿用既有設定儲存與重啟／重連流程，自有 UI 固定繁體並非新的回覆語言設定。無資料遷移、新 locale 欄位、新帳號或付費服務。實際協定與行為矩陣見 [契約](contracts/language-and-display.md)。

### 驗證與需求覆蓋

| 需求 | 設計與驗證 |
|---|---|
| FR-001、FR-008 | 固定文案盤點、已知錯誤映射、自有伺服器提示、六類畫面與無障礙驗收 |
| FR-002、FR-003、FR-006 | 共用提示優先順序、兩後端指示、auto／非中文／當次例外測試 |
| FR-004、FR-005、FR-009 | 十二組服務原文的即時／完成／歷史事件測試，不轉換、不自動重試 |
| FR-007、FR-010 | 既有設定與權限回歸、切換／重連／重啟、人格／記憶原始檔不變 |

先做離線回歸，再做畫面與每後端十次實際問答。實際服務未可用時記錄未完成，不沿用前一功能的計時豁免。完整指令與驗收矩陣見 [quickstart.md](quickstart.md)。

## Complexity Tracking

無需例外或新增架構。這是既有邊界內的文案與提示變更，預期不改架構圖；若實作擴大架構範圍，須重新評估並依規則標記圖表更新需求。
