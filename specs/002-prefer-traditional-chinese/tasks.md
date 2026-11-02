# Tasks: 優先使用繁體中文

**Input**: `specs/002-prefer-traditional-chinese/` 的設計文件。

**Prerequisites**: [plan.md](plan.md)、[spec.md](spec.md)、[research.md](research.md)、[data-model.md](data-model.md)、[介面契約](contracts/language-and-display.md)、[驗收指南](quickstart.md) 與 `.specify/memory/constitution.md`。

**Tests**: 依專案必要行為測試要求及計畫的明確測試設計納入。改變行為的測試先於實作，確認預期失敗；原文與相容性保護可能在修改前即通過，須維持通過，不為製造紅燈而破壞它們。離線測試不得呼叫雲端或硬體，不新增逐句譯文快照、DOM 測試框架或依賴。

**Organization**: 先設定與共同保護，再依 US1／US2／US3 交付獨立可驗證成果，最後整體驗收。所有任務初始均未完成，僅在實際完成並有證據後勾選。

## Format: `[ID] [P?] [Story] Description`

- ID 依執行順序連號；故事階段使用 `[US1]`、`[US2]`、`[US3]`。
- `[P]` 表示在所列前置完成後，與同組不同檔案任務可平行；不表示可跳過測試、品質檢查或故事驗收。
- 同一檔案的任務一律序列執行；本清單不自行授權啟動其他代理。

## Path Conventions

沿用 `src/reachy_mini_conversation_app/` 與鏡像 `tests/`，不建新服務、儲存或翻譯平台。證據寫入本功能 `quickstart.md`，不新增 docs/ Markdown 或其他 README。

## Phase 1: Setup

**Purpose**: 確認個人客製化範圍與可重現基線。

- [X] T001 依 `specs/002-prefer-traditional-chinese/quickstart.md` 的明確隔離步驟準備忽略的 `cache/traditional-chinese-trial.py` 及獨立測試目錄，在任何實際服務連線前驗證傳入 `main.run` 的絕對 instance_path 與關閉的相機／記憶設定；不複製日常 `.env`、記憶、歷史或人格，不執行舊資料遷移，缺少私密行程憑證時保留未完成。記錄個人客製化、零付費範圍與釐清決定；不改既有 Gemini 結案，也不沿用舊豁免。
- [X] T002 執行根 `AGENTS.md` 要求的完整基線 gate，包含 Ruff、format、strict mypy、pytest 與 uv lock 檢查，對照 `pyproject.toml`、`uv.lock`，在 `specs/002-prefer-traditional-chinese/quickstart.md` 記錄實際版本、平台、結果與阻礙；不以歷史 690-test 結果當本輪實作結果，不調降檢查或修改 CI。

## Phase 2: Foundational

**Purpose**: 在翻譯與提示調整前固定文案／資料邊界。

- [X] T003 [P] 依 `specs/002-prefer-traditional-chinese/research.md` 的完整前端盤點，於 `specs/002-prefer-traditional-chinese/quickstart.md` 建立六類畫面的文案／例外／驗收表；包含固定標題、載入、空狀態、錯誤、確認／取消、tooltip、無障礙標籤及自有診斷頁，區分自有文案、第三方資料與使用者原文。
- [X] T004 [P] 在 `tests/test_language_vision_routes.py`、`tests/test_settings_store.py` 補齊既有資料契約保護：全域語言「既有兩字母／auto／未存值」、「未存值沿用環境與既有預設，不改成 zh」、「有效的人格值優先於全域值」；保留 `profile`／`all` 語意、設定 version 1 與全域設定清除人格覆寫行為，不接受新地區代碼，不新增 locale 欄位、環境變數或遷移。

**Checkpoint**: T001–T004 完成後才開始故事任務；固定介面可以翻譯，但所有服務文字與機器可讀值仍是受保護資料。

## Phase 3: User Story 1 — 閱讀繁體介面與原始對話文字 (P1, MVP)

**Goal**: 自有介面使用繁體，逐字稿原文不變，錯誤與互動仍可用。

**Independent Test**: 不依賴模型繁體生成，使用模擬事件與實際瀏覽器驗證六類畫面、已知／未知錯誤，以及十二組原文的即時／完成／歷史呈現。

### Tests

- [X] T005 [US1] 在 `tests/test_console.py` 擴充頁面／RPC 行為測試，依 `specs/002-prefer-traditional-chinese/contracts/language-and-display.md` 固定十二組原文與預期文字，檢查部分、完成、歷史文字、保留 `role`／`text`／`final` 與序列資訊且不新增 converted_text；使用同一資料提供實際前端可連線的既有測試 app／RPC fixture，在 `specs/002-prefer-traditional-chinese/quickstart.md` 記錄啟動、事件發送與頁面網址，禁止連雲端或執行工具。另測已知提示、穩定錯誤身份及未知原文，不以逐句譯文快照代替行為測試。

### Implementation

- [X] T006 [P] [US1] 翻譯 `src/reachy_mini_conversation_app/static/index.html`、`src/reachy_mini_conversation_app/static/vad-monitor.html`、`src/reachy_mini_conversation_app/static/js/main.js`、`src/reachy_mini_conversation_app/static/js/router.js`、`src/reachy_mini_conversation_app/static/js/orb.js` 的自有殼層、導覽與狀態文案，頁面語言使用 `zh-Hant`；保留路由、selector、事件值與診斷資料。
- [X] T007 [P] [US1] 翻譯 `src/reachy_mini_conversation_app/static/js/views/settings.js`、`src/reachy_mini_conversation_app/static/js/components/language-picker.js` 的設定、後端原因映射與語言範圍文案；zh 可顯示「中文（繁體優先）」、auto 顯示「自動判斷」，保留 `zh`／`auto`／`profile`／`all` 及選擇語意，不把自動模式當成預設中文。
- [X] T008 [P] [US1] 翻譯 `src/reachy_mini_conversation_app/static/js/views/home.js`、`src/reachy_mini_conversation_app/static/js/views/talk.js`、`src/reachy_mini_conversation_app/static/js/components/conversation-panel.js` 的固定標題、角色、空狀態、部分／完成／中斷與延遲標籤；保留 `textContent` 的原文字串及既有事件組裝，不能引入繁簡轉換、翻譯、正規化或等整段才顯示的步驟。
- [X] T009 [P] [US1] 翻譯 `src/reachy_mini_conversation_app/static/js/views/tools.js`、`src/reachy_mini_conversation_app/static/js/components/profile-tools.js`、`src/reachy_mini_conversation_app/static/js/components/profile-modal.js`、`src/reachy_mini_conversation_app/static/js/components/confirm-dialog.js` 的固定文案與無障礙名稱；自有工具顯示名稱／說明只在畫面層對照，保留人格／聲音名稱、工具 ID、模型工具宣告、參數與第三方描述。
- [X] T010 [P] [US1] 翻譯 `src/reachy_mini_conversation_app/static/js/api.js` 的既有錯誤顯示映射及自有用戶提示，保留 RPC 方法、參數、原因碼與 timeout 行為；未知第三方錯誤維持原文 fallback，不建通用 i18n 或轉換呼叫層。
- [X] T011 [US1] 盤點並翻譯 `src/reachy_mini_conversation_app/console.py`、`src/reachy_mini_conversation_app/language_routes.py`、`src/reachy_mini_conversation_app/personality_routes.py`、`src/reachy_mini_conversation_app/memory_routes.py`、`src/reachy_mini_conversation_app/vision_routes.py`、`src/reachy_mini_conversation_app/tool_space_routes.py`、`src/reachy_mini_conversation_app/profile_tool_routes.py` 中實際供使用者閱讀的固定 `message`／已知錯誤說明，包含 `conversation.context.message`；保留機器原因碼、列舉、錯誤結構與原始服務文字，不翻譯 logger 或為 UI 更動工具行為。
- [ ] T012 [US1] 在 `specs/002-prefer-traditional-chinese/quickstart.md` 記錄 T005–T011 的離線結果與六類畫面盤點，並透過 T005 fixture 對全部十二組固定原文逐項比較實際 DOM 的部分／完成／歷史文字；記錄輸入、預期、RPC 結果、畫面實際文字及比對結果，不適用階段註明原因，不以 RPC 通過、截圖或檔案存在代替畫面驗收。另檢查鍵盤確認／取消、tooltip、無障礙名稱、窄畫面、長中文換行，以及 `src/reachy_mini_conversation_app/static/js/ui.js`、`src/reachy_mini_conversation_app/static/js/constants.js`、`src/reachy_mini_conversation_app/static/js/personality-badge.js`、`src/reachy_mini_conversation_app/static/js/pending-apply.js` 的遺漏文案；保留身份資料，可用時做既有 Node 語法檢查，不新增依賴或把未檢查寫成通過。

**Checkpoint**: US1 可獨立交付繁體介面與不改字的逐字稿；尚不宣稱模型繁體一致性已通過。

## Phase 4: User Story 2 — 兩後端優先繁體回覆 (P1)

**Goal**: 在既有共用提示中表達繁體偏好，保留 auto、非中文與設定優先順序。

**Independent Test**: 模擬兩後端設定與替換 handler，驗證相同政策；準備每後端十次觀察樣本。最終實際觀察在 T020 定稿後由 T021 執行，不設繁體比例門檻，也不使用轉字改善結果。

### Tests

- [X] T013 [P] [US2] 在 `tests/test_huggingface_realtime.py` 補上 zh／auto／非中文、人格優先與既有辨識／合成欄位的回歸；以行為檢查取代對舊 `Speak only ...` 句子的依賴，確認 auto 沒有無條件中文要求，原語言與聲音代碼不變。
- [X] T014 [P] [US2] 在 `tests/test_gemini_realtime.py` 測試 setup 與後續指示使用相同的共用語言政策，覆蓋中文繁體優先、auto 條件式中文及非中文預設；保留模型、聲音及傳輸設定，不增加地區辨識碼、不為修正字形重連或重新生成。
- [X] T015 [US2] 在 `tests/test_console.py`、`tests/test_startup_settings.py` 補上後端切換、同供應商重連、重啟及人格語言覆寫的政策重建案例；驗證未存值與 auto 不被寫成 zh，原始人格、記憶／歷史、聲音、工具權限與相機／記憶開關不因語言偏好而變動。

### Implementation

- [X] T016 [US2] 在 `src/reachy_mini_conversation_app/prompts.py` 的 `get_session_instructions()` 沿用現有解析順序與人格／記憶組裝，將絕對語言命令改為預設語言規則，並加入「中文時優先繁體」的共用指示；保留「與後端、聲音及人格分開理解」及「不是新持久化欄位」的限制。auto 不強制中文，未設定沿用預設；不修改人格檔、設定格式、ASR／TTS 協定，不新增單次轉發包裝或後端專用中文政策。
- [X] T017 [US2] 在 `specs/002-prefer-traditional-chinese/quickstart.md` 預先固定每後端十次中文觀察樣本與紀錄欄位，涵蓋開場、一般問題、簡體輸入、無副作用工具結果與重選／重連後回覆；記錄完成助理原文／逐字稿、語音語言、字形效果、無效或無法判斷結果與限制，不設 9/10 門檻。此任務只準備樣本，例外另列，最終觀察必須等 T020 完成並於 T021 執行，不以修改前的結果作結案證據。

**Checkpoint**: US2 的政策套用可獨立離線驗證；最終服務觀察尚待 T020／T021。服務逐字稿仍可能是簡體，不能宣稱固定辨識字形或口音。

## Phase 5: User Story 3 — 原文與其他語言例外 (P2)

**Goal**: 尊重當次要求並保持可讀原文，不修改存檔或因字形不符重做動作。

**Independent Test**: 明確的簡體引用、技術文字、其他語言與模型未遵守偏好案例均正確；同一對話回到原預設語言，儲存與工具呼叫次數不變。

### Tests

- [X] T018 [P] [US3] 在 `tests/test_settings_store.py`、`tests/test_startup_settings.py` 擴充當次引用／其他語言要求不永久改設定的回歸，保持「不建立新例外資料庫、不解析後改寫工具參數，也不永久改變回覆語言」；覆蓋 profile／all 範圍、人格原始文字與相機／記憶權限不變。
- [X] T019 [P] [US3] 在 `tests/test_huggingface_realtime.py`、`tests/test_gemini_realtime.py` 測試明確原文／其他語言要求可優先於預設生成語言，保留網址、程式碼、路徑、名稱與識別碼；對模型回傳簡體、未知服務錯誤與失敗後下一回合，確認沒有新增生成請求、工具重播或文字替代。

### Implementation

- [X] T020 [US3] 在 `src/reachy_mini_conversation_app/prompts.py` 補齊當次簡體原文、引用、翻譯及其他語言要求的例外優先順序，並要求保留技術文字與指定名稱；例外只影響當次生成，不寫入設定、不改服務文字或工具參數。依 T018／T019 的結果只修正必要政策，不加字形偵測／轉換、例外儲存、額外模型呼叫或自動重試。
- [ ] T021 [US3] 等 T020 提示與例外規則定稿、相關離線測試通過後，在 `specs/002-prefer-traditional-chinese/quickstart.md` 記錄當時程式版本／差異摘要，依 T001 隔離啟動流程執行 T017 的每後端十次最終觀察及原文／其他語言例外；auto 各三組中文與非中文、未設定及明確非中文案例保留原規則，記錄服務限制與未遵守偏好情況。無繁體比例門檻，但仍須證明偏好正確套用、原文保留、對話可繼續且無重複工具；未執行項目維持未完成。之後相關提示或語言選擇語意改變時重做受影響觀察。

**Checkpoint**: 三個故事均可驗證，例外處理沒有引入第二套語言狀態或文字處理管線。

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T022 更新根 `README.md` 的語言與介面行為說明：UI 固定繁體、模型中文繁體偏好、服務回覆／逐字稿不轉換、auto 不變及原文例外；不翻譯整份專案文件，不新增 README、環境變數或 docs/ Markdown。
- [X] T023 對 `pyproject.toml`、`uv.lock`、`src/`、`tests/` 執行完整 Ruff／format／strict mypy／pytest／uv lock／diff 檢查，在 `specs/002-prefer-traditional-chinese/quickstart.md` 記錄本次實際結果及平台；未跑的平台與瀏覽器／Node 檢查明列未完成或不可用，不改 CI，不沿用舊 gate 當新結果。
- [ ] T024 依 `specs/002-prefer-traditional-chinese/spec.md` 的 SC-001–SC-006，在 `specs/002-prefer-traditional-chinese/quickstart.md` 整理六類介面、每後端十次效果觀察、十二組 RPC／實際 DOM 原文比對、設定保留、例外與 auto 矩陣；確認 T021 對應最終交付的提示與語言選擇語意，若之後相關行為改變就重做受影響觀察，純文件／無語意格式變更不要求重跑。分開真實結果與限制，不恢復已取消的比例門檻，也不自行豁免其他必要驗收。
- [ ] T025 對照 `AGENTS.md`、`.specify/memory/constitution.md`、`specs/002-prefer-traditional-chinese/plan.md` 自審最終差異，在 `specs/002-prefer-traditional-chinese/quickstart.md` 記錄沒有憑證、原文改寫、依賴／協定新增或無關異動；若架構實際擴大則標記 `docs/scheme.mmd` 的後續更新，不手改生成 SVG，不改受保護文件，不自動建立 PR。

## Dependencies & Execution Order

### Phase Dependencies

```text
T001 -> T002 -> (T003 || T004)
                    |
                    v
US1: T005 -> (T006 || T007 || T008 || T009 || T010) -> T011 -> T012
US2: (T013 || T014) -> T015 -> T016 -> T017
US3: (T018 || T019) -> T020 -> T021 (包含 T017 的最終服務觀察)
Polish: T022 -> T023 -> T024 -> T025
```

- 所有故事都依賴 T001–T004。預設依 US1、US2、US3 順序執行，最後才進 Polish。
- US1 與 US2 的功能可獨立測試；若調整執行排程，T015 必須等 T005 完成並避開 T011，因共用 `tests/test_console.py`／`console.py`。T016 的程式修改不依賴 UI 翻譯，但不得跳過自身測試前置。
- US3 使用 US2 的政策組裝結果：T018 等 T015、T019 等 T013／T014、T020 等 T016 及 T018／T019；T020 與 T016 修改同一檔案，不可平行。
- T017 僅準備資料；最終觀察明確依賴 T017 與 T020，由 T021 執行。不得在 T020 改提示後沿用先前服務觀察結案；T024 再檢查證據與交付行為版本一致。
- T017、T021、T012、T024 共享驗收證據檔案且含互動工作，不平行進行。完整結果缺少實機／畫面證據時不得僅因程式完成而勾選。
- Polish 依三故事完成；T023 在最後程式修改後執行，只有新增變更或失敗才需要重跑已通過檢查。

### Parallel Opportunities

- 基礎：T003 文案盤點與 T004 既有設定保護，檔案互不重疊。
- US1：T005 後，T006–T010 五組 HTML／JS 檔案互不重疊；T011 與整合驗收序列完成。
- US2：T013 HF 與 T014 Gemini 測試檔互不重疊；完成後再做共同生命週期測試與提示實作。
- US3：T018 儲存保護與 T019 兩後端例外測試互不重疊；完成後再修改共用提示。

## Parallel Examples per User Story

| 故事 | 可同時處理的任務 | 必須等待 |
|---|---|---|
| US1 | T006 殼層、T007 設定、T008 對話、T009 工具／人格、T010 API 顯示 | T005 完成；不更動對方的檔案 |
| US2 | T013 HF 測試、T014 Gemini 測試 | Foundation 完成，之後再做 T015／T016 |
| US3 | T018 設定保護、T019 後端例外 | 對應 US2 前置完成；之後再做 T020 |

## Implementation Strategy

### MVP First

完成 Setup／Foundation 與 US1（T001–T012），即可交付繁體操作介面與原文逐字稿。MVP 不宣稱已完成最終模型效果觀察，也不引入轉換器來暫時補足。

### Incremental Delivery

US2 加入共用模型偏好並準備觀察樣本；US3 補齊原文／其他語言例外後，才做最終的每後端十次效果觀察與設定不變驗證。最後完成 README、完整 gate、SC 矩陣與自審。保留真實失敗與限制，不將前一功能的個人結案視為本功能通過。

## Requirement Coverage

| 需求／標準 | 任務 |
|---|---|
| FR-001、FR-008、SC-001 | T003、T005–T012 |
| FR-002、FR-003、SC-002 | T004、T013–T017、T020–T021、T024 |
| FR-004、FR-005、SC-003 | T005、T008、T012、T019 |
| FR-006、FR-009、SC-005 | T018–T021 |
| FR-007、FR-010、SC-004 | T004、T015、T018、T021 |
| SC-006 | T004、T013–T016、T021 |
| 文件／品質／交付 | T022–T025 |
