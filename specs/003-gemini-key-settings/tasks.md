# Tasks: 設定頁管理 Gemini API key

**Input**: `specs/003-gemini-key-settings/` 的 spec.md、plan.md、research.md、data-model.md、contracts/credential-settings.md、quickstart.md。

**Branch**: `feat/003-gemini-key-settings`

**Prerequisites**: Python 3.12；遵守 AGENTS.md、CONTRIBUTING.md 及 `.specify/memory/constitution.md`。

**Tests**: 規格各故事的 Independent Test、SC-001～SC-005 要求行為驗證，憲章另要求新功能 happy-path／回歸測試，因此包含必要測試任務。故事測試先寫、確認因尚未實作的行為失敗，再完成產品實作；不為薄包裝逐行補測試。

**Organization**: 依使用者故事分組。任務全部未完成；此文件不代表程式、OS vault、雲端或實機驗收已通過。

## Format and paths

`- [ ] Tnnn [P?] [USn?] 描述及確切檔案路徑`；`[P]` 只表示該組前置條件完成後，可在不同檔案平行執行，並非授權啟動代理。
所有路徑相對儲存庫根目錄。`gemini_credentials.py` 與其鏡像測試是新增檔案，其餘優先擴充現有檔案。

## Phase 1: Setup

**Purpose**: 確認個人客製化範圍、環境及依賴，不接觸日常秘密或機器人。

- [X] T001 在 specs/003-gemini-key-settings/quickstart.md 記錄本功能隔離預檢：讀取 AGENTS.md、CONTRIBUTING.md 與受影響模組，確認 feat/003-gemini-key-settings、Python 3.12、乾淨基線及既有完整 gate 結果；沿用個人客製化授權，不以缺少上游 Issue 阻擋本機工作、不自動開 PR，不讀 .env／vault、不連雲端或 daemon。
- [X] T002 在 pyproject.toml 加入 plan.md 已告知的唯一直接依賴 keyring>=25.7,<26，執行 uv lock 同步 uv.lock；確認三平台與 Python 3.12 解析，不引入 keyrings.alt、Google SDK、前端框架或新 mypy ignore。
- [X] T003 在 specs/003-gemini-key-settings/quickstart.md 補上可重現的隔離測試環境命令與 fixture scope，指定假環境來源／fake vault／假 socket、阻擋未預期外連，區分離線、瀏覽器、OS vault、live 驗收；未獲當輪同意不得讀日常金鑰或啟動真實測試。

## Phase 2: Foundational — 所有故事的共同前置

**Purpose**: 先建立來源、資料型別、受保護儲存及本機授權邊界；完成後才能實作故事入口。

- [X] T004 在 src/reachy_mini_conversation_app/gemini_credentials.py 建立嚴格、有型別且不洩密的 metadata／operation／public status 模型；逐字遵循 data-model.md：version「固定整數 1；未知版本阻擋 managed 使用」、revision「單調非負整數；同實例 lifetime lock 及提交鎖保護」、state「active、preparing、clearing、cleared；清除失敗保留 clearing」、active_revision「opaque 隨機槽 ID 或 null；不是 key hash」、pending_revision「尚未提交槽 ID 或 null」、retired_revisions「待刪除槽 ID 集合；包含已提交更新的舊槽」、manual_reconnect_required「bool；clear／受影響失敗後跨重啟保留，不以 env 存在解除」；operation 使用 opaque ID、expected_revision、model/voice 與 generation 快照，phase「validating/saving/clearing/done/failed/superseded」；候選值不進 repr、序列化、例外或事件。
- [X] T005 在 src/reachy_mini_conversation_app/gemini_credentials.py 實作穩定 scope、namespace 與 lifetime OS file lock：SDK instance_path 優先，CLI 採既有 REACHY_MINI_INSTANCE_PATH／platformdirs；正規化路徑雜湊且 label 不含原始路徑／秘密；Windows msvcrt、Linux/macOS fcntl，頂層條件匯入；同 scope 第二行程 fail closed，不把鎖檔存在誤判成持鎖。於 src/reachy_mini_conversation_app/main.py 初始化及釋放此 scope，不搬移 .env 或改變一般 CLI 設定持久化。
- [X] T006 在 src/reachy_mini_conversation_app/gemini_credentials.py 實作可注入的受保護儲存：只明確建立 Windows WinVaultKeyring（persist="local machine"）、macOS Keyring、Linux SecretService.Keyring；拒絕自動 discovery／chainer／null／fail／自訂明文 backend，錯誤安全分類，OS 呼叫離開 event loop；service「App 固定前綴 + scope digest + 隨機槽 ID」、account「固定 gemini」，不列出其他實例條目、不收集解鎖密碼。
- [X] T007 在 src/reachy_mini_conversation_app/gemini_credentials.py 實作獨立 gemini-credential.json 嚴格讀取／原子寫入及來源 resolver，於 src/reachy_mini_conversation_app/config.py 分離環境 snapshot 與正式生效來源：先判斷 clearing／壞檔／無法確認／持鎖衝突為 blocked，即使 active_revision 存在也不得繞過；其後 preparing 有舊 active 則只讀此槽、失敗 blocked，無舊 managed 則保留原環境 snapshot/none、不讀候選；active 槽缺失不當作 null。只有無 managed 或完成 cleared 才回環境。保留原 dotenv 優先規則，refresh 不覆寫 managed，不寫候選到 os.environ/.env 或一般 AppSettings。
- [X] T008 在 src/reachy_mini_conversation_app/console.py 建立專用 HTTP 存取檢查及安全錯誤回應：實際 loopback peer、精確 Host/port、拒絕轉送標頭、同源 Origin/Fetch Metadata、記憶體 CSRF 與 no-store；無寬鬆 CORS，不把 SDK RPC／本機代理轉送當授權，無法辨別代理來源則該入口拒絕秘密操作；獨立 GET /settings/gemini-key 頁限定直接本機頂層導覽，frame-ancestors none／X-Frame-Options DENY，不允許任何 parent；templates/gemini-key.html 不經 static 公開。此頁導覽不要求 API 的 CSRF／same-origin fetch header，頁面內 API 仍嚴格檢查。一般根設定頁保留既有 frame／遠端操作，不新增本機限制。保留一般 RPC，backend.config 仍拒絕 key。
- [X] T009 在 src/reachy_mini_conversation_app/console.py 加入唯一 LocalStream owner 的 Gemini manual-reconnect gate 與 operation revision fencing，重用 src/reachy_mini_conversation_app/huggingface_realtime.py 的 session generation／停止音訊與舊工具結果機制；HF 不 restart、不 flush、不換 provider；Gemini 受影響失敗／clear 後待明確 backend.retry 或重新選用，不因 env 有值自動重連；停止失敗回 session_stop_failed，不繼續套用。
- [X] T010 在 tests/test_gemini_credentials.py 與 tests/test_console.py 建立 tmp_path、fake vault、假 socket／owner 的隔離測試，覆蓋型別與 journal 壞檔、backend allowlist、env-only 無 vault、兩 scope 隔離／同 scope 真正第二行程鎖、前置 HTTP 拒絕及 HF 不受 gate 影響；確認 fixtures 不讀日常設定／真實憑證且無外連，通過後才進入故事實作。

**Checkpoint**: 所有公開入口預設拒絕不具權限的秘密請求；來源及 lock 故障不會被當成缺失；尚無供使用者提交的半成品入口。

## Phase 3: User Story 1 — 從設定頁提供 Gemini 金鑰 (P1, MVP)

**Goal**: 首次輸入、最小 Live setup 驗證、受保護保存、狀態與重啟可用，不需編輯 .env。

**Independent Test**: 在無環境金鑰的隔離實例，經本機設定頁提交假金鑰並模擬 setupComplete；查詢／重載欄位空白，重啟解析同一受保護值。locked／不可用時不保存、不套用，HF 使用中不被改變。

### Tests first

- [X] T011 [P] [US1] 在 tests/test_gemini_realtime.py 加入獨立候選驗證行為測試：明確候選／model/voice 快照、x-goog-api-key header、有效 setupComplete、setup/close deadline、auth／model／quota／network 分類；斷言不載入人格／記憶／逐字稿／resumption／tools、不送 user turn、不初始化 robot/audio/VAD、不播放聲音。
- [X] T012 [P] [US1] 在 tests/test_console.py 先寫 GET/POST /api/gemini-credential 契約測試：無既存值回填、JSON 宣告欄位、revision、CSRF、16 KiB 上限、空白拒絕、固定錯誤、框架驗證錯誤不帶 input/body，HF active 不換 backend；確認未實作行為會使測試失敗。
- [X] T013 [P] [US1] 在 tests/test_gemini_credentials.py 先寫首次保存／readback／active commit、保存各點故障與重啟測試；pending 不升級；clearing 與 active ID 共存時先 blocked，preparing 無舊 managed 時保留原 env snapshot/none；vault 或 journal 失敗不套用候選，重啟 validation 回到 unverified，讀取已知槽失敗不 fallback。

### Implementation

- [X] T014 [US1] 在 src/reachy_mini_conversation_app/gemini_realtime.py 實作 T011 的獨立 typed async validator，重用 Live URL／setup/close timeout 與安全分類；只送 model、必要 AUDIO/speechConfig 並等 setupComplete 後關閉，不呼叫正常 start_up、不變更 global key、不隱藏重試、不記錄 headers 或 remote exception 原文。
- [X] T015 [US1] 在 src/reachy_mini_conversation_app/gemini_credentials.py 實作驗證後的版本化提交：記 pending → 新 vault 槽 write/readback → 原子 active commit，失敗保留舊 active；replace 結果不明先重讀、無法確認則 blocked/result_unknown，不宣稱成功；開始前／每個 await 後／提交前檢查 revision，不將取消 to_thread 當取消 vault 寫入。
- [X] T016 [US1] 在 src/reachy_mini_conversation_app/console.py 掛載 GET/POST /api/gemini-credential，接上 T008、T009、T014、T015；GET 需 X-Credential-Request:1 與 Sec-Fetch-Site same-origin（有 Origin 時亦同源）；POST 需 JSON、合法 expected_revision 與 X-Credential-CSRF，trim 後空白報 invalid_input，未知欄位／超量請求安全拒絕，不以 key 前綴或長度宣稱有效，瀏覽器斷線不自動重送。
- [X] T017 [US1] 在 src/reachy_mini_conversation_app/console.py 與 src/reachy_mini_conversation_app/gemini_realtime.py 接上正式 handler 的生效憑證快照；成功保存且當前仍選 Gemini／model 快照有效才經既有 owner 建 fresh session、清除舊 resumption，失敗如實顯示停止及手動恢復，HF 不動；發布 Public status：configured「bool」、managed_presence「absent/present/unknown」、environment_available「bool」、source「settings/environment/none/blocked」、storage「available/locked/unavailable/error/busy」、validation「unverified/validating/validated/failed」、apply「idle/saving/applied/clearing/failed」，connection 沿用既有狀態，保留 gemini_key_configured 的安全 bool 相容欄位。
- [X] T018 [US1] 在 src/reachy_mini_conversation_app/static/js/api.js 增加專用同源 HTTP credential transport，token 僅留頁面記憶體、重啟重新 bootstrap；不走通用 RPC、不在 URL／瀏覽器儲存／錯誤中保留候選，失敗僅重新查詢安全狀態，不自動重送秘密；API 需涵蓋後續 clear 契約但本階段不開放未完成按鈕。
- [X] T019 [US1] 在 src/reachy_mini_conversation_app/static/js/views/settings.js 只加入安全狀態及「開啟本機金鑰設定」按鈕；以 noopener/noreferrer 另開 /settings/gemini-key。在 src/reachy_mini_conversation_app/templates/gemini-key.html 及 src/reachy_mini_conversation_app/static/js/gemini-key.js 新增獨立頁 password、label、autocomplete=off、spellcheck=false、「驗證並套用」與取消；於 console.py 受保護路由送出 HTML，確認 pyproject.toml 的 wheel 包含 template 且不存在公開 static alias。HF 選中亦可管理；來源／保存／驗證／連線分開顯示，事先告知 Gemini 新對話／失敗恢復，提交／取消／離開／重載清空、不 reveal，Tab/Enter/Esc、aria-live 可用；一般 Control App iframe／遠端頁保留原一般操作，remote/relay 只提示在 App 所在電腦操作，不導向另一台 localhost。
- [X] T020 [US1] 依 specs/003-gemini-key-settings/quickstart.md 建立 cache/003-gemini-key-settings/settings_trial.py 隔離 fake 設定頁入口（確認 fake dependencies、暫存 scope 且阻擋外連），補精確啟動命令並以自動 fixture 驗證首次提交、取消、空白、失敗、reload/restart、HF active 不變、一般頁不新增 frame 限制、獨立頁的本機／frame 限制與 template 打包，記錄結果於同檔；本任務只以 US1 程式及必要離線自動測試通過為完成條件，人工畫面／操作次數驗收移交 T036/T037，未通過人工驗收不等於已結案，也不阻擋 US2 開發。

**Checkpoint**: 可示範首次設定及跨重啟保存，包含基本授權及不洩密；尚未宣告可交付完整更新／清除功能。

## Phase 4: User Story 2 — 更新與清除金鑰，理解對話影響 (P1)

**Goal**: 安全替換與明確刪除，涵蓋舊值保留、清理失敗、競態及手動恢復。

**Independent Test**: 以兩個 sentinel、驗證／儲存故障及 clear，在 Gemini active、disconnected、HF active 三種情境交叉測試；確認 session 與來源政策、無舊音訊或工具重播。

### Tests first

- [X] T021 [P] [US2] 在 tests/test_gemini_credentials.py 先寫更新／clear 交易測試：保留舊 active、提交後 retired 清理失敗、刪除全部已知 active/pending/retired 槽、clearing/cleared crash 點、delete/metadata 結果不明、失敗清除不報成功，慢 write 完成後不得逃過新 clear。
- [X] T022 [P] [US2] 在 tests/test_console.py 先寫 DELETE 契約與三種連線狀態的 update/clear/fail 矩陣；覆蓋慢驗證後 clear、多分頁舊 revision、驗證中換 model/provider、重複提交、owner 停止失敗，斷言不等雲端 timeout 才停止、無雙回覆／舊工具結果、無自動 source/provider 切換。

### Implementation

- [X] T023 [US2] 在 src/reachy_mini_conversation_app/gemini_credentials.py 完成替換後 retired 槽清理及重啟復原：成功 active 不因清理失敗回滾，回 cleanup_pending 並保留待清理 ID；pending 永不自動升級，重啟清理未提交槽但不解除 manual gate，不建立可讀取憑證歷史。
- [X] T024 [US2] 在 src/reachy_mini_conversation_app/gemini_credentials.py 實作 clear：先持久化 clearing，再刪所有已知槽、確認不存在，最後原子 cleared commit；成功才允許環境 fallback，保留 manual_reconnect_required；刪除／metadata 失敗顯示未完成或未知，不回退、不誤稱已刪、不刪其他實例；無法保存 clear 意圖時明示不能保證重啟記得該次失敗，提示重試。
- [X] T025 [US2] 在 src/reachy_mini_conversation_app/console.py 完成 DELETE /api/gemini-credential（expected_revision、confirm=true）及 update/clear 協調：clear 意圖立即增加 operation revision、gate/fence 停止 Gemini，再處理短儲存提交區段；後到結果只清理，不 commit／覆蓋狀態／restart。保存／發布／重啟前重檢 provider/model/session 快照，多分頁衝突回 409 並由使用者重試。
- [X] T026 [US2] 在 src/reachy_mini_conversation_app/console.py 完成受影響驗證失敗／clear 的持久化 manual gate、backend.retry 與明確重選 Gemini 恢復；成功 update 只在快照仍有效時明確解除 gate 建新 session，不能沿用舊 resumption；雲端關閉逾時仍退休 owner，HF 使用中不改 session、動作或 provider。
- [X] T027 [US2] 在 src/reachy_mini_conversation_app/static/js/api.js 完成 DELETE、revision_conflict／superseded／result_unknown 及失去回應後重新查詢；不以 UI cancel 假裝取消伺服器操作，token 只留記憶體、不將候選寫入 retry queue，clear 能在驗證期間送出新意圖。
- [X] T028 [US2] 在 src/reachy_mini_conversation_app/static/js/gemini-key.js 與 src/reachy_mini_conversation_app/templates/gemini-key.html 加明確清除與確認對話框、更新／失敗／cleanup_pending 狀態、環境來源與停止後手動恢復提示；輸入更新前不改生效值，空白不是刪除；clear 不等於 provider 撤銷，失敗不宣稱已刪；從一般設定頁起計算開啟獨立頁＋清除＋確認共三次，pending 禁止重複套用但允許 clear，所有退出路徑清空 draft。
- [X] T029 [US2] 在 tests/test_huggingface_realtime.py 擴充必要 shared session 回歸：舊 generation 的音訊／工具完成在 credential retirement 後不播放／重播；驗證 HF active 的 Gemini 管理不 flush HF，不建立第二個 retry owner；僅對本功能觸及的共用行為增加測試。
- [X] T030 [US2] 依 specs/003-gemini-key-settings/quickstart.md 執行隔離更新／clear／fail 矩陣及多分頁、慢驗證競態，以自動 fixture 核對新對話／原設定保留／待手動重連與安全 UI 狀態 payload；本任務完成條件只含 US2 程式及必要離線自動測試，人工畫面／操作次數驗收移交 T036/T037，live 移交 T041，結果分開追蹤，不阻擋 US3 開發、不宣稱人工已通過。

**Checkpoint**: 首次設定、更新及清除形成完整安全閉環；舊 operation、來源 fallback 與 owner retry 都不得繞過使用者意圖。

## Phase 5: User Story 3 — 保留既有環境設定與機密邊界 (P2)

**Goal**: 證明 `.env` 相容性、四種來源政策、六類操作零洩漏與本機權限邊界，補齊跨層回歸。

**Independent Test**: 無真實 key，交叉 env-only/UI-only/both/neither 的 reload/clear/restart；以 sentinel 檢查輸出／持久儲存；跨站、LAN、relay 不能取得 token、改值或刪值。

### Tests first

- [X] T031 [P] [US3] 在 tests/test_gemini_credentials.py 加完整四種來源 × reload/clear/restart、locked/read failure、第二行程與 env refresh 矩陣，斷言 dotenv 原優先規則不變、已知 managed 失敗不 fallback、成功 clear 才轉環境且 gate 保留，沒有 vault 的 env-only 仍可運作。
- [X] T032 [P] [US3] 在 tests/test_console.py 加安全負向與 sentinel 洩漏測試：惡意／缺 Origin、Host rebinding、LAN peer、轉送標頭、缺或過期 token、Fetch Metadata、超量／錯型別／未知欄位、generic RPC key、獨立頁所有 frame 拒絕／直接本機導覽允許／無 static alias，以及一般頁原 frame 行為保留；涵蓋 input/update/clear/failure/reload/restart 與 DEBUG logs、request validation repr、狀態／錯誤／逐字稿／歷史，禁止完整或可辨識片段，不只驗 happy path。
- [X] T033 [P] [US3] 在 tests/test_settings_store.py 與 tests/test_main.py 加整合回歸：一般 settings.json／journal 無秘密、候選不改 os.environ/.env，CLI scope 穩定不搬移 legacy 設定；profile/voice/language、記憶原文與 tool permissions 保持，初始化／停止不開相機或記憶、不連真實 daemon。

### Implementation and verification

- [X] T034 [US3] 在 src/reachy_mini_conversation_app/config.py、src/reachy_mini_conversation_app/main.py 與 src/reachy_mini_conversation_app/gemini_credentials.py 完成 T031/T033 揭露的來源 refresh／startup/shutdown 邊界整合；確認正式 handler 取明確生效快照，managed 憑證不被一般設定載入覆寫，既有 env-only 部署與正常啟動保持相容，不擴充無關設定範圍。
- [X] T035 [US3] 在 src/reachy_mini_conversation_app/console.py 與 src/reachy_mini_conversation_app/gemini_realtime.py 完成 T032 揭露的錯誤／輸出邊界：只傳固定安全 reason 與 operation ID，auth/model/quota/network/storage 分開且有下一步；不得記錄 body/header/token/remote exception 原文，transport debug 不洩密，仍以 logger 記錄安全失敗分類，不吞錯誤。
- [X] T036 [US3] 在 specs/003-gemini-key-settings/quickstart.md 補齊並實際驗證 cache/003-gemini-key-settings/settings_trial.py 隔離瀏覽器入口的精確啟動命令（沿用 T020 harness，不新增產品 mock 開關）；以 fake dependencies、暫存 scope、拒絕外連開啟既有 settings_app，承接 T020/T030 的人工驗收：確認一般頁按鈕另開獨立本機頁、Tab/Enter/Esc／焦點／aria-live／繁體換行、HF 不變及首次／更新／清除／失敗提示；從一般 Gemini 區計算開頁＋套用兩次、開頁＋清除＋確認三次，記錄六類操作的 Network／URL／History／Local/Session Storage 檢查與跨站拒絕，禁止含秘密 HAR／截圖輸出。
- [ ] T037 [US3] 在 specs/003-gemini-key-settings/quickstart.md 記錄 Control App 本機 iframe、直接 loopback 瀏覽器、remote/relay-only／不支援 Fetch Metadata 的實際 UI 結果：一般設定在本機 Control App iframe／既有遠端入口仍能使用，本機按鈕另開頂層憑證頁、remote/relay 只提示須在 App 所在電腦操作；獨立頁對所有 frame 與遠端導覽都拒絕，無 parent allowlist／static alias，一般 RPC 不受影響；未執行環境保持待驗，不阻擋 T038/T039/T042。

**Checkpoint**: T035 後可繼續文件及本機 gate；T036/T037 的人工畫面結果獨立追蹤，未完成不宣稱 SC-002、SC-003、SC-005 的人工部分通過。不能用 UI 顯示「已保存」冒充 vault 或真實服務已通過。

## Phase 6: Polish and cross-cutting validation

- [X] T038 [P] 在 README.md 更新根文件：本機設定入口與限制、OS vault 前提／Linux 無 Secret Service、跨重啟 scope、UI 優先與 clear 回環境但手動重連、失敗保留／未知狀態、清除非 provider 撤銷；保留 GEMINI_API_KEY 相容說明，不新增 README 或 docs/ Markdown，不新增環境變數，若確需變數先檢視範圍並同步 .env.example。
- [X] T039 [P] 在 docs/scheme.mmd 補憑證保存／驗證及設定資料流，依既有生成方式重新產生 docs/assets/conversation_app_arch.svg 並視覺檢查；不手改 SVG，在 specs/003-gemini-key-settings/quickstart.md 記錄架構圖更新狀態。
- [X] T040 在 specs/003-gemini-key-settings/quickstart.md 記錄當輪同意後的獨立 namespace OS vault 驗收：以非真實 sentinel 做各可用平台跨行程保存／讀回／刪除、鎖定與不可用、scope 隔離，僅刪測試槽並清理 fixture；Windows、macOS、Linux 分別標示實測或待驗，未做平台不得勾為通過或以 fake backend 代替。2026-11-03 依使用者「略過macOS與Linux測試」決定結束本任務追蹤；Windows 與 Linux 已有結果保留，macOS／Linux 剩餘實測明確豁免，勾選不代表三平台實測通過。
- [ ] T041 在 specs/003-gemini-key-settings/quickstart.md 記錄另行授權後的真實 Gemini 最小 setup 與 HF/Gemini 對話矩陣：獨立 scope、使用者由 UI 輸入 key、既有免費額度／費用範圍先確認，相機／記憶關閉，確認單獨驗證無媒體／工具，update 新 session、clear 待手動重連、fail 保留與無雙回覆；完成後清除測試憑證並恢復原狀，未授權則保持未完成，不索取聊天中的 key。
- [X] T042 在 specs/003-gemini-key-settings/quickstart.md 記錄完整 gate 實際結果：ruff check . --fix、ruff format .、mypy --pretty --show-error-codes、pytest tests/ -v、uv lock --check；修正本功能引起的失敗，保留 Python／OS／測試數與限制，不降規則或新增 ignore，前次功能 gate 不算本次證據。
- [X] T043 在 specs/003-gemini-key-settings/quickstart.md 依 FR-001～FR-014／SC-001～SC-005 自審需求覆蓋、程式 diff、文件／lock／生成 SVG 與零秘密；確認無 SDK 私有修改、新 retry owner、額外 provider、受保護貢獻／CI 檔案變更；列出未實測平台／服務，不因服務失敗重測後抹去原紀錄。
- [ ] T044 在 specs/003-gemini-key-settings/tasks.md 與 specs/003-gemini-key-settings/quickstart.md 更新實際完成狀態及結案證據：只有實作與必要驗證完成才勾選；人工／平台／live 未完成保持未完成，範圍豁免須有明確使用者決定，不自動視為通過；執行既有 after_implement hook 保存進度，不建立上游 PR。

## Dependencies and execution order

```text
T001 → T002 → T003
                  ↓
              T004 → T005 → T006 → T007 → T008 → T009 → T010
                                                                ↓
              US1: T011 / T012 / T013 → T014 → T015 → T016 → T017 → T018 → T019 → T020
                                                                                              ↓
              US2: T021 / T022 → T023 → T024 → T025 → T026 → T027 → T028 → T029 → T030
                                                                                              ↓
              US3: T031 / T032 / T033 → T034 → T035（實作／自動測試完成）
                                                                        ↓
              T035 → T038 / T039 → T042 → T043 → T044
              T035 → T036 → T037（人工待驗分支，不阻擋文件／gate）
              另行授權後：T040（OS）／T041（live）→ T043 驗收證據；未做則保留待驗
```

- Setup 完成後 Foundation 才開始，全部 Foundation 完成才進 US1；安全邊界不得為 MVP 延後。
- US2 依賴 US1 的 POST、儲存及 UI，US3 依賴前兩故事的完整六類流程。本功能共享同一設定頁／owner／來源，故故事按順序交付，不能假稱互不依賴。
- 每個故事的程式與必要離線自動測試可透過自己的 fake fixture 驗證；T020/T030 不含人工完成條件，因此後續開發不依賴前一故事的人工結果、真實 key 或 robot。T036/T037/T040/T041 分開追蹤人工／平台／live 待驗，完整結案仍須完成或取得明確範圍決定。
- T011/T012/T013 皆在 T010 後；T021/T022 在 T020 後；T031/T032/T033 在 T030 後。同組各檔案不同，無組內依賴。
- T038/T039 可在 T035 後平行，不等待 T036/T037 人工驗收，但 T039 完成圖形寫入後才把結果合併進 quickstart，避免同檔並寫。
- T040 OS 實測及 T041 live 需要當輪同意，不阻擋先完成可獨立執行的 T042 本機 gate。T043/T044 必須誠實列出尚未完成的驗收，不靠等待時間推定授權。
- 編輯同檔的任務依序執行；只有 [P] 組可以同時工作。新測試預期失敗屬開發中 checkpoint，最終 gate 必須綠燈。

## Parallel examples per story

- **US1**：T010 完成後，同時準備 T011（tests/test_gemini_realtime.py）、T012（tests/test_console.py）、T013（tests/test_gemini_credentials.py）；三組測試均確定缺失行為後再執行 T014。
- **US2**：T020 完成後，同時準備 T021（tests/test_gemini_credentials.py）與 T022（tests/test_console.py）；T023 以後維持順序，不能一邊改 vault 交易一邊改同檔 clear。
- **US3**：T030 完成後，同時準備 T031（tests/test_gemini_credentials.py）、T032（tests/test_console.py）、T033（tests/test_settings_store.py、tests/test_main.py）；跨層修正依 T034/T035 順序整合。

這些是執行機會說明，不要求代理分工；同一開發者亦可循序完成。

## Requirement and entity mapping

| 規格／模型 | 任務 |
|---|---|
| FR-001、FR-002、FR-007；SC-001；空白／草稿行為 | T012、T016、T018～T020、T027、T028、T030 |
| FR-003；Public status、operation revision | T004、T009、T013、T015～T017、T021、T022、T025～T028 |
| FR-004、FR-012；SC-002；秘密／transport 邊界 | T006、T008、T011、T012、T014、T016、T018、T019、T032、T033、T035～T037 |
| FR-005、FR-006；SC-003；metadata、protected entry、source | T004～T007、T013、T015、T023、T024、T031、T033、T034、T040 |
| FR-008、FR-009、FR-011；SC-004；session／clear gate | T009、T012、T017、T021～T030、T041 |
| FR-010；SC-005；安全失敗分類 | T006、T011～T017、T021～T028、T032、T035 |
| FR-013、FR-014；silent setup 與既有設定保留 | T011、T014、T017、T029、T033～T035、T041 |
| 根文件、架構、完整 gate、自審 | T038、T039、T042～T044 |

## Implementation strategy

**MVP**: T001～T020（Setup + Foundation + US1）。以 fake scope 驗證首次輸入、受保護保存與重啟；
包含本機權限限制及保密，不對外宣告完整 key 管理功能已完成，也不部署未具 clear 的完整產品入口。

**Incremental delivery**: 先驗證 US1，再加入 US2 更新／清除閉環，接著 US3 相容與安全矩陣，最後文件、
各環境實際驗收與完整 gate。缺少 OS 或 live 授權時繼續不受影響的本機工作，保留待驗任務。

**Counts**: 共 44 項；Setup 3、Foundation 7、US1 10、US2 10、US3 7、Polish 7。
10 項 [P] 分成四組：US1 三項、US2 兩項、US3 三項、文件／架構兩項；不包含同檔序列任務。

## 本輪進度 — 2026-11-03

**同頁修訂待規劃落地**：以下 41／44 只追蹤原獨立頁基線。使用者最新要求改為原設定頁直接輸入、不額外開頁；spec.md 與 plan.md 已記錄新目標及可信內嵌研究閘門。現有 UI 任務／驗收不能直接作為同頁完成證據；下一輪通過閘門後須重整差異任務並分析，不據此宣告功能結案。

41／44 項已處理（40 項完成，T040 依平台測試豁免結束追蹤）；其餘保留未完成，詳見 quickstart.md 的驗收表：

- T037：直接本機 Chrome、跨來源 fetch／iframe 已驗。本輪使用者授權安裝本機客製版並啟動；Control App 另開金鑰頁的按鈕實測無反應，不能通過。使用者隨後改要求同頁整合，已停止 App 並還原未變更的暫時相機／記憶設定；待新方案驗收，真正遠端／WebRTC relay 仍未驗。
- T040：Windows 原生假值保存、跨行程讀回、實例隔離及刪除通過；Ubuntu 24.04 原生 backend 服務不可用測試通過，安全拒絕保存、保留環境來源且無明文 fallback，跨行程確認並清理 scope。2026-11-03 使用者明確要求略過 macOS 與 Linux 測試，剩餘實測列為已豁免，結束 T040 追蹤；不宣稱三平台均通過，不變更跨平台產品支援或既有 CI。
- T041：已授權免費額度下的最小 Live setup 成功、使用者確認、隔離真實憑證已刪除；實際 HF/Gemini 語音對話／切換矩陣未授權，保留待驗。
- T044：本輪已記錄進度並執行 after_implement 保存；完整結案仍等待上述必要驗收或明確範圍決定，不自動豁免。

共用 HTTP 異動入口的 clear 交易與回歸測試在 UI 開放前一併整合，避免暴露未實作的刪除入口；US2 測試缺少 clear 時先確認失敗，再補上實作。
