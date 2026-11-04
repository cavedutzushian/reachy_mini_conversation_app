# Tasks: 同頁管理 Gemini API key

**Input**: spec.md、plan.md、research.md、data-model.md、contracts/credential-settings.md、quickstart.md。
**Branch**: feat/003-gemini-key-settings；Python 3.12；遵守 AGENTS.md、CONTRIBUTING.md 與憲章。
**Scope**: 原設定頁 Gemini 區直接輸入／更新／清除，不另開頁面；重用既有 vault、journal、驗證與 session owner，無新依賴、環境變數、SDK patch 或登入系統。
**Tests**: spec 的 Independent Test、SC-001～SC-005 與憲章要求必要 happy-path／回歸，故包含測試。先寫會揭露缺少同頁行為的測試，再實作；既有後端測試直接重用，不為不變程式重寫鏡像測試。
**Organization**: 下列 29 項為同頁差異工作，依實際完成與驗收結果勾選。依故事分組；[P] 僅代表所列前置完成後，可在不同檔案平行處理，不授權啟動代理。

## 基線、編號與驗收範圍

- T001～T044 的原清單保留於 Git commit 1a39c87 的同一路徑；當時 40 項完成、T040 依平台豁免結束追蹤，合計 41／44 已處理。此處從 T045 續編，不重用 ID、不把舊勾選當同頁完成。
- 原 T037 的原生入口／遠端驗收由 T071 接續；原 T041 的同頁實際服務／對話矩陣由 T072 接續；原 T044 結案由 T073 接續。舊外開連結實測無反應，不記為通過。
- 原 Windows vault、Linux 不可用及雲端最小 setup 的結果依 quickstart.md 保留；使用者 2026-11-03 已豁免 macOS／Linux 剩餘實測，不重開該平台任務、不記為通過。
- 同頁新任務與人工／native／live 結果分開追蹤。未獲當輪授權不啟動 App／robot、不讀真實 key；人工待驗不阻擋必要離線實作／gate，完整結案仍需完成或使用者明確範圍決定。

## Phase 1: Setup

**Purpose**: 核對基線、工具與隔離範圍，不重新建置已存在後端。

- [X] T045 在 specs/003-gemini-key-settings/quickstart.md 記錄同頁實作預檢：讀取設計、AGENTS.md／CONTRIBUTING.md、受影響模組，確認分支、Python 3.12 與工作目錄狀態；保留既有個人客製化與平台豁免，不因缺上游 Issue 阻擋本機工作、不開 PR，不讀 .env／vault 或連雲端／daemon。
- [X] T046 在 specs/003-gemini-key-settings/quickstart.md 記錄現有測試環境與可用 Chrome／Puppeteer 工具位置、後端回歸基線及精確重現命令；確認 src/reachy_mini_conversation_app/gemini_credentials.py 的 persisted metadata／來源／鎖與 pyproject.toml／uv.lock 不需改動，不搬移 key 或新增依賴。工具缺失列待驗而非成功，工作區路徑不得硬編進交付測試。

## Phase 2: Foundational — 共用隔離與 eligibility

**Purpose**: 所有故事前先建立可重現測試與預設只讀的入口判定。

- [X] T047 在 tests/fixtures/gemini_key_settings.py 建立可重用的同頁 fake 設定伺服器，沿用既有 FakeVault／假 validator／假 handler 及暫存 scope，提供測試所需四種來源、HF／Gemini 連線與延遲／失敗情境；啟動前禁止 dotenv／日常憑證與未預期外連，不建立 robot／audio／相機／記憶。新增 tests/static/js/gemini-key.browser.mjs 的隔離瀏覽器 runner：以命令參數指定既有 Chrome／Puppeteer 與 fixture URL，無新框架／產品 mock 開關；結束關閉自己建立的 browser／server／scope。將可重現命令寫入 specs/003-gemini-key-settings/quickstart.md，不能僅依賴 ignored cache。
- [X] T048 在 tests/static/js/gemini-key.browser.mjs 先加入 eligibility 行為回歸：本機頂層、可信完整鏈允許；惡意 parent／grandparent、null／未知／空項、API 缺失／讀取錯誤、內嵌空鏈、非 loopback／非 HTTP／錯誤 pathname、dev origin／scheme／suffix／任意 port 變體拒絕；本階段測公開 eligibility 判定的輸出，模組匯入不得建立 password DOM、token bootstrap 或 mutation；完整 UI 拒絕斷言交 T050／T062。真實瀏覽器驗鏈，能力缺失另以隔離注入模擬，確認現況會失敗。
- [X] T049 在 src/reachy_mini_conversation_app/static/js/gemini-key.js 實作 controller 可重複呼叫的公開 eligibility 判定，將現有全域初始化延後到掛載以免匯入副作用；本項先完成判定及無副作用匯入，完整 controller 接線交 T052：自身 HTTP、hostname 精確 localhost／127.0.0.1／[::1]、pathname 精確 / 或 /static/index.html；頂層用 window.top===window，frame 的原生 location.ancestorOrigins 必須可讀、非空且每項完整 origin 精確屬於 {location.origin, "http://tauri.localhost"}。eligibility 遵循「readonly / eligible；依 plan.md 的自身位置與原生完整祖先鏈，每次掛載／bootstrap／mutation 重算，非可寫設定或 server 認證」；未知／缺失一律只讀，不採 query／referrer／UA／postMessage／RPC／自報 header。通過 T048，不建立第二認證系統。

**Checkpoint**: foundation 測試可重現、拒絕情境 fail closed；才進入同頁控制故事。

## Phase 3: US1 — 從原設定頁提供金鑰（P1，MVP）

**Goal**: 同頁提供遮蔽輸入及獨立提交，無 popup，保留狀態及不回填。
**Independent Test**: 無 env 的 fake scope，在原設定頁一次提交、驗證／保存成功；重整／重掛載／模擬重啟只顯示狀態且欄位空白，HF 不變，拒絕入口不取得 token。

### Tests first

- [X] T050 [P] [US1] 在 tests/static/js/gemini-key.browser.mjs 加入同頁首次輸入、空白、取消、提交清空、reload／重掛載／fake owner 重啟、一般設定儲存不夾帶 key、HF 不變、無 popup／外開連結的行為測試；bootstrap 未完成或失敗不得有可輸入 DOM，eligibility 拒絕時無 password DOM、token fetch 或 mutation，保存不可用不宣稱成功，確認新行為在舊 UI 失敗。
- [X] T051 [P] [US1] 在 tests/test_console.py 重用並執行既有 GET／POST 憑證契約與最小驗證測試，核對 JSON／expected_revision、16 KiB、600 秒記憶體 CSRF、Origin／Fetch Metadata／Host／peer、no-store、錯誤不帶 input/body；一般 RPC 不發 token、backend.config 拒絕 key。只有發現同頁接線缺口才加必要回歸，不複製已有覆蓋。

### Implementation and verification

- [X] T052 [US1] 在 src/reachy_mini_conversation_app/static/js/gemini-key.js 將 document 全域初始化整理為有掛載／卸載生命週期的 controller，沿用既有操作與固定錯誤；phase 遵循「readonly / bootstrapping / ready / pending / error / disposed；只有 eligible 且 bootstrap 成功才建立輸入控制」，draft 遵循「僅當次輸入記憶體；不回填、不序列化或記錄，提交／取消／清除／離開／卸載清空」，csrf_token 遵循「同頁 bootstrap 取得，僅留本次 controller；卸載／pagehide 釋放，不傳 parent／RPC／browser storage」。先判定／bootstrap 再建立 controls；不留 stub 或第二份全域初始化，不改後端保存交易。
- [X] T053 [US1] 在 src/reachy_mini_conversation_app/static/js/views/settings.js 的原 Gemini 區掛載 controller，移除開啟獨立頁按鈕，不與一般 settings form 合併；顯示 password、label、autocomplete=off、spellcheck=false、繁體狀態、「驗證並套用」、取消及既有清除／重連控制。一般設定／HF 原路徑保留；bootstrap 拒絕只顯示安全狀態，切頁連動卸載。
- [X] T054 [US1] 在 src/reachy_mini_conversation_app/static/style.css 重用既有 field／actions／hint 樣式整理同頁佈局，確認 label、aria-live、焦點、Tab／Enter／Esc、窄視窗繁體換行及錯誤提示；不顯示舊 key、不新增 reveal 或前端框架，不改全域 iframe 權限。
- [X] T055 [US1] 依 specs/003-gemini-key-settings/quickstart.md 執行 T048／T050／T051 與同頁 fake fixture 首次提交矩陣，記錄空白、取消、保存失敗、reload／重掛載／模擬 owner 重啟、HF 不變及無 popup；命令指定 tests/fixtures/gemini_key_settings.py 與 tests/static/js/gemini-key.browser.mjs。此項只含程式／自動離線證據，人工畫面移交 T070，不冒充原生或 vault 已驗。

**Checkpoint**: US1 可獨立離線示範；尚不宣告完整交付，更新／清除與卸載競態需 US2 複驗。

## Phase 4: US2 — 更新、清除與對話影響（P1）

**Goal**: 同頁重用完整更新／清除閉環，離開／返回不重送或污染新狀態。
**Independent Test**: 兩個假 key、驗證／保存／刪除故障，於 active HF／active Gemini／disconnected 三種情境交叉 update／clear／failure；確認 fresh session 或手動恢復、舊設定保留，切頁／BFCache／遲到回覆不重播。

### Tests first

- [X] T056 [P] [US2] 在 tests/static/js/gemini-key.browser.mjs 加入更新、清除確認／Esc、空白不清除、驗證失敗保留、cleanup_pending／result_unknown、切頁／返回／pagehide／pageshow／BFCache、bootstrap 中卸載、舊掛載遲到結果與重複掛載回歸；驗證 pending 可 clear、無秘密自動重送、無多重 poll／listeners，先確認缺失行為會失敗。
- [X] T057 [P] [US2] 在 tests/test_console.py 重用既有 HF／Gemini／disconnected 更新／清除／失敗與慢驗證／多分頁 revision／provider-model 變更矩陣，確認唯一 owner、停止失敗、HF 不 flush、Gemini fresh session、clear manual gate 及舊音訊／工具結果退休；只為新暴露缺口新增必要行為回歸，不改 SDK 或重寫已測交易。

### Implementation and verification

- [X] T058 [US2] 在 src/reachy_mini_conversation_app/static/js/api.js 為專用 geminiCredentialRequest 接上 controller 可釋放的前端 request wait（需要時以 AbortSignal），保持既有 JSON／CSRF 及安全錯誤；取消等待不回報 server 已取消，不重送候選、不放入 retry queue，不將祖先宣稱當 header 授權。
- [X] T059 [US2] 在 src/reachy_mini_conversation_app/static/js/gemini-key.js 完成生命週期與競態：mount_generation 遵循「每次掛載或恢復增加，用於丟棄已卸載控制的遲到回覆，不取代 server revision／owner_epoch」；listeners / poll / request wait 遵循「controller 唯一擁有；卸載全部停止或解除，前端停止等待不代表 server 操作取消」。每個 await 後核對有效掛載與 owner_epoch／revision；pagehide／卸載清 draft/token，pageshow 重新判定與 bootstrap，eligibility 失效即卸載，不恢復草稿或自動重送；明確 UI 取消不能假稱後端取消。
- [X] T060 [US2] 在 src/reachy_mini_conversation_app/static/js/gemini-key.js 接回更新／clear／失敗／重連提示與確認對話框：提交一次、清除加確認兩次，pending 禁重複套用但允許 clear；Gemini 事前中斷／成功新對話／失敗保留與手動恢復、env fallback／非供應商撤銷均說清楚，HF 不受影響。處理 auth/model/quota/network/storage、revision_conflict／superseded／result_unknown／cleanup_pending，不顯示候選或上游錯誤原文。
- [X] T061 [US2] 在 specs/003-gemini-key-settings/quickstart.md 記錄 tests/static/js/gemini-key.browser.mjs、tests/test_console.py 的三種連線狀態 × update／clear／failure 及生命週期矩陣結果；核對舊設定保留、Gemini fresh／manual gate、HF 不動、無重送／雙回覆／舊工具重播。全部用 fake 依賴，人工及 live 另交 T070／T072，不阻擋 US3 離線開發。

## Phase 5: US3 — 來源相容與機密邊界（P2）

**Goal**: 移除舊秘密入口，證明完整來源鏈與 API 防護分工、環境相容及六類操作零洩漏。
**Independent Test**: 四種來源 × reload／clear／restart，以 fake sentinel 檢查同頁、一般設定與記錄；惡意全鏈／跨站／遠端不能得到 token、輸入或變更，舊頁 404、一般 iframe／RPC 保留。

### Tests first

- [X] T062 [P] [US3] 在 tests/static/js/gemini-key.browser.mjs 擴充惡意 parent／可信 parent 外的惡意 grandparent、referrer policy 遮蔽、opaque／未知／缺失鏈、遠端／relay、錯誤 scheme／port／suffix／dev origin、postMessage／RPC／query 自稱可信的負向測試；input/update/clear/failure/reload/restart 六類 sentinel 檢查狀態／錯誤／URL／browser storage／歷史零洩漏，拒絕時無 token fetch／password DOM，普通設定仍可用。
- [X] T063 [P] [US3] 在 tests/test_console.py 與 tests/test_profile_paths.py 先更新舊入口及 wheel 回歸：GET /settings/gemini-key 為 404、無 redirect／static alias，wheel 不含舊 template；根設定頁仍 200 可內嵌，一般 RPC 不受限制，專用 API peer／Host／Origin／Fetch Metadata／CSRF／body limit／no-store 與框架錯誤去密完整保留。確認舊實作因仍提供獨立頁而失敗，不靠刪掉保護測試過關。

### Integration and verification

- [X] T064 [US3] 在 src/reachy_mini_conversation_app/console.py 移除舊獨立頁 handler／route 與不再使用的匯入，刪除 src/reachy_mini_conversation_app/templates/gemini-key.html，確認沒有 static alias／另一個秘密輸入入口。維持 GET／POST／DELETE /api/gemini-credential 與根頁／RPC 的既有契約，不把 frame 判斷當 server 認證、不對根頁新增全面 frame 禁止；通過 T063。
- [X] T065 [US3] 在 tests/fixtures/gemini_key_settings.py 與 tests/static/js/gemini-key.browser.mjs 接齊 env-only／UI-only／both／neither 的同頁 reload／clear／fake owner restart 場景，重用 tests/test_gemini_credentials.py、tests/test_settings_store.py 的來源與持久化回歸，核對 clearing／blocked 優先、preparing 無舊 managed 保留原 env／none、active 讀失敗不 fallback、clear gate 跨重啟；後端模型／schema 不變，只為新增 UI 整合缺口補測試。
- [X] T066 [US3] 依 specs/003-gemini-key-settings/quickstart.md 執行 T062／T063／T065 及 tests/test_gemini_realtime.py 最小無媒體 validator 回歸，記錄六類 sentinel、四種來源、完整祖先鏈／API 負向與打包結果；檢查 DEBUG／validation repr、一般 settings／journal／.env 未被寫秘密，profile／voice／language／記憶原文／tool permissions 不變，不啟動相機或記憶。未知入口仍只讀，不擴充 allowlist。

## Phase 6: Polish、實際驗收與結案

- [X] T067 [P] 在 README.md 更新原頁輸入／更新／清除、獨立提交、可信來源／只讀限制、來源優先與受保護保存、失敗及手動恢復說明；移除獨立頁操作描述，不新增 README／docs Markdown／環境變數，不將 Tauri origin 說成 Reachy 程序身分。
- [X] T068 [P] 核對 docs/scheme.mmd 的同頁憑證資料流，必要時修改來源並重新產生 docs/assets/conversation_app_arch.svg，視覺確認無舊獨立輸入節點；不得手改 SVG。僅圖形已正確時記錄無需變更，不改 SDK 架構。
- [X] T069 在 specs/003-gemini-key-settings/quickstart.md 記錄完整 Ruff check／format、strict mypy、pytest tests/ -v、uv lock --check --offline、持久化 browser 回歸及 wheel 結果；遵守 Python 3.12、無新 ignore／依賴／硬編路徑，保留原始失敗及修正後複驗，不將沙箱／工具缺失報成功，自審產品與文件差異。
- [ ] T070 依 specs/003-gemini-key-settings/quickstart.md 進行人工同頁 fake 畫面驗收：提交一次、清除加確認兩次、無 popup，Tab／Enter／Esc／焦點／aria-live／繁體窄視窗、更新失敗／返回欄位空白、一般設定正常。只輸入明示假值，不連雲端／robot；未獲使用者結果保留待驗，不拿自動 browser 取代人工結果。
- [ ] T071 在 specs/003-gemini-key-settings/quickstart.md 記錄當輪同意後的 Windows Control App 原生入口及實際 remote／relay 驗收：原設定頁直接控制、完整實際祖先鏈／ancestorOrigins 能力、Origin／Fetch Metadata、無開窗、相機／記憶關閉；不符精確 allowlist 或不支援時確認只讀、無 token／mutation、一般設定可用。源碼推論／Chrome 模擬不算原生成功；未有環境的 remote／relay 部分保持待驗或等待明確範圍決定，不為通過而放寬來源，不修改 SDK。測後只清理自己的暫時設定／行程並還原。
- [ ] T072 在 specs/003-gemini-key-settings/quickstart.md 記錄另行授權後的同頁真實 Gemini 最小 setup 與 HF active／Gemini active／disconnected 更新／清除／失敗矩陣：獨立 scope、受保護測試 namespace、使用者從已允許的同頁輸入 key、先確認免費額度／費用範圍，相機／記憶關閉；單獨驗證無媒體，fresh session／manual gate／保留／HF 不動及無重播均核對，最後清理測試憑證及設定。未授權保持待驗，不讀既有 .env／日常 key、不索取聊天中的 key，不重開已豁免 macOS／Linux 測試。
- [ ] T073 在 specs/003-gemini-key-settings/tasks.md 與 specs/003-gemini-key-settings/quickstart.md 更新同頁完成狀態、歷史基線／新結果及剩餘限制；只有實作／必要驗證完成才勾選，T070～T072 的未做部分需完成或使用者明確範圍決定才能結案。保留平台豁免但不宣稱實測通過，執行既有 after_implement hook 保存，不建立上游 PR。

## Dependencies and execution order

```text
T045 → T046 → T047 → T048 → T049
                         foundation ready
          → [T050 || T051] → T052 → T053 → T054 → T055 (US1)
          → [T056 || T057] → T058 → T059 → T060 → T061 (US2)
          → [T062 || T063] → T064 → T065 → T066 (US3)
          → [T067 || T068] → T069
          → T070 → T071 / T072 (各自取得必要授權) → T073
```

- 所有故事依 foundation。US2 重用 US1 controller，US3 核對完成後同頁及舊頁移除，因此依上圖優先順序實作；不同故事不能同時修改同一 controller／browser 測試檔。各 Independent Test 使用自己的 fake scope，無需前一故事的人工或 live 成功。
- T050/T051、T056/T057、T062/T063 可在各自 phase 前置完成後平行：browser 與 Python 測試檔不同。T067/T068 在 T066 後平行：README 與圖形檔不同。其餘同檔任務序列處理，避免合併衝突。
- T055/T061/T066 為必要離線驗證 checkpoint；T070～T072 為額外人工／native／live 分支，不阻擋先完成離線程式、文件與 T069。T072 不依賴 native T071 成功，可使用已允許的直接本機瀏覽器同頁，但兩者都需各自當輪授權；完整結案 T073 不自動豁免待驗。

## Parallel examples by story

| 故事 | 可同時進行（各 phase 前置已完成後） | 必須序列 |
|---|---|---|
| US1 | T050 browser 首次輸入／T051 Python HTTP 契約 | T052 controller → T053 掛載 → T054 樣式 → T055 |
| US2 | T056 browser 生命週期／T057 Python owner 矩陣 | T058 transport → T059 lifecycle → T060 提示 → T061 |
| US3 | T062 browser 來源／洩漏／T063 HTTP 舊路由／wheel | T064 移除舊頁 → T065 來源整合 → T066 |

## Requirement and model coverage

| 規格／模型 | 任務 |
|---|---|
| FR-001/002/007；SC-001；draft、phase | T050、T052～T056、T059、T060、T070 |
| FR-003/010/011；SC-005；安全來源／錯誤顯示 | T051～T053、T056～T061、T065 |
| FR-004/012；SC-002；eligibility、csrf_token | T047～T053、T058、T062～T066、T071 |
| FR-005/006；SC-003；既有 metadata／vault 不變 | T046、T050、T055、T065、T066、T072 |
| FR-008/009；SC-004；唯一 owner／operation 不變 | T051、T055～T061、T072 |
| FR-013/014；人格／語言／工具不變、最小 setup | T047、T057、T066、T072 |
| mount_generation、listeners / poll / request wait | T056、T058、T059、T061 |
| 文件／架構／gate／實際結果 | T067～T073 |

## Implementation strategy and completion status

**MVP**: T045～T055（Setup 2、Foundation 3、US1 6），只作安全隔離的同頁示範。實際產品完整交付仍須 US2／US3 及相應驗收，不能以 MVP 掩蓋更新／清除或來源限制的缺口。

**Incremental delivery**: US1 首次設定 → US2 更新／清除與生命週期 → US3 相容／邊界及移除舊頁 → 文件與 gate → 明確授權的實際驗收 → 結案。不因缺少真實 key 或現場操作停止可獨立完成的離線工作。

**Counts**: 共 29 項（T045～T073），Setup 2、Foundation 3、US1 6、US2 6、US3 5、Polish 7；8 項 [P]。25／29 項完成（T045～T069）；T070 待窄版修正人工複驗，T071／T072 待當輪授權與實際驗收，T073 保持未結案。
