# Validation Guide: 模型下載與單文件離線產包

**階段**：2026-11-10 使用者已重新明確授權雙固定模型下載與Windows真實驗收；T058／T069／T080通過，T082完成需求對照與最終完整gate，005活動任務40／40結案。歷史保存進度及延後決定如下保留。

**前輪階段（已由本輪授權取代）**：2026-11-10 離線實作完成、真實模型驗收延後。兩角色下載、chapter-source-v1／別名、預建BM25、v2包與fresh reader已有離線證據；尚未取得本輪真實BGE兩模型／三步交接證據，不代表整體結案。下列命令為後續明確opt-in驗收入口，不因保存進度而自動執行。

## 真實驗收接續（2026-11-10，40／40，Windows素材準備結案）

使用者最新授權：「授權下載兩個固定版本模型，繼續 Windows 真實驗收。」本輪僅匿名公開下載、工作區cache、CPU合成文件驗收；不啟動App、不讀私人模型快取、不用雲端對話、不處理example.md、不自動提交。Linux／macOS維持未測。

- T058：`RUN_DOCUMENT_MODEL_ACCEPTANCE=1` 執行 `tests/test_download_document_model.py::test_approved_snapshot_loads_offline_and_reuses_without_network`，兩角色 **2 passed／1 warning，221.55秒**。匿名Hub提示保留，未改用token；pytest的1項warning為.pytest_cache/nodeids寫入遭WinError5，並非模型驗證失敗。下載明確設HF_HUB_DISABLE_XET=1。原始記錄 `cache/005-prepare-rag-assets/20261110-real-models-network.log`；`--basetemp cache/005-prepare-rag-assets/20261110-real-models-network`。
- embedding：`test_approved_snapshot_loads_o0/model`，固定SHA `50f9396f75618b3389c1fd1068a1ff58dc7b5b26`，10 payload檔、2,293,234,427 bytes；v2 receipt SHA256 `2375c8937bbffdd61ac74a547baa5f9439a02d62a6fca6aa0c262abf3d05206a`。
- reranker：`test_approved_snapshot_loads_o1/model`，固定SHA `2cfc18c9415c912f9d8155881c133215df768a70`，6 payload檔、1,134,374,819 bytes；v2 receipt SHA256 `9fe3492a56dfe469d1af01ce4779cc90446a5a6b806384bdf085bf985963e44b`。
- 兩角色均實際safe-only CPU載入／前後hash核對後發布，第二次同版本以HfApi拒絕spy證明零metadata與下載且inventory不變。實際runtime：ST6.2.0／torch2.15.0+cpu／transformers5.21.0，Windows Python3.12.12。完整路徑／角色摘要保存在 `cache/005-prepare-rag-assets/20261110-real-model-summary.json`，不是私人快取。
- 首次一般沙箱連線失敗：`20261110-real-models-optin.log` 2 failed，ConnectError／download_unavailable／exit5，兩角色未發布。自動核准第一次誤引用前輪延後而拒絕，附上本輪最新明確授權再送審後通過；未繞過拒絕或更換來源，所有失敗保留。
- T069已擴充八份固定合成案例、每份兩次產包、原文／aliases／兩模型hash與chunks／BM25重現比較；新增無標題TXT、重複ATX、空與合法別名。準備時離線回歸38 passed／8 skipped。實際驗收啟動獨立sitecustomize audit，攔截socket.connect／getaddrinfo／sendto；無網路紀錄檔才可記零嘗試，HF／transformers亦設offline。結果待下方補記。
- T069：`RUN_DOCUMENT_PACKAGE_ACCEPTANCE=1`、兩個DOCUMENT_*_PATH明確指向本輪模型，執行 `tests/test_build_document_package.py::test_real_local_model_builds_five_source_packages_without_network`，**8 passed／1 warning，1632.67秒（27分12秒）**；原始 `20261110-real-packages.log`，`--basetemp cache/005-prepare-rag-assets/20261110-real-packages`。八份固定來源（中文／英文／否定／表格／程式碼連結／TXT混合行尾及空別名／章節合法別名／同名ATX及fence），各兩次，共16包；每次獨立producer／fresh verifier，來源及aliases bytes／兩模型inventory不變，兩次chunks.jsonl／bm25.json逐bytes相同；全rows／metadata／vectors／count及原包／副本持久HNSW不變由真正v2 verifier執行，不是mock。
- 來源／aliases／manifest／完整包inventory及其SHA256摘要：`cache/005-prepare-rag-assets/20261110-real-package-summary.json`（16包）；兩角色receipt摘要見上。所有package.schema_version=2，實際Windows目標寫入manifest；不宣告Linux／macOS可用。sitecustomize audit確實隨PYTHONPATH提供父CLI與所有worker，攔截connect／DNS／sendto，network-attempts.log未建立：零嘗試。此成功只代表素材完整性／重現／整合，不是新文件品質或004查詢時限通過。
- T069的1項warning同樣是pytest無權寫入既有.pytest_cache/nodeids；原始警告保留，模型／包本身成功。未為此修改權限或重跑模型。
- T080：`RUN_DOCUMENT_PACKAGE_ACCEPTANCE=1`及同一雙模型／offline audit，執行 `tests/test_build_document_package.py::test_real_package_replacement_busy_and_cancelled_worker_preserve_materials`，**1 passed／1 warning，316.75秒（5分16秒）**，原始 `20261110-real-lifecycle.log`、`--basetemp cache/005-prepare-rag-assets/20261110-real-lifecycle`。真實包初次發布0；未授權覆寫4；獨立Python程序持有真正目的地鎖時busy4；實際worker啟動後受控KeyboardInterrupt取消130；舊包inventory逐bytes保持，鎖清除後明確重試--replace成功0，重新產包的chunks／BM25保持相同，兩模型inventory不變。此取消發生於worker啟動後、推論前；不宣稱OS硬當機／斷電實測。故障邊界／硬中斷殘留／未確認退出與exit8仍由既有跨程序及故障注入回歸支援。
- T080最終包與來源摘要：`20261110-real-lifecycle-summary.json`，包inventory SHA256 `f18653c54be2a8e6f2e8262139d33aaa9aeed3e30682c449ee37084ae89e597d`。本輪共保留17個已發布v2包（T069的16個加T080最終1個）；T080替換前的初始包另由測試比對，沒有冒稱保留其實體目錄。network-attempts.log仍未建立；1項warning是pytest快取權限問題，原始記錄保留。
- 本輪完整離線gate：Ruff check／format（139檔）、strict mypy（64 source files）、uv lock --check（183 packages）通過；`20261110-actual-acceptance-gate.log` **1003 passed／31 skipped，188.93秒**。31 skipped包含需獨立opt-in的真模型／Chroma等案例，不能視為已通過。後續新增或細化的真實交接測試仍須另外執行；工程gate不開App、不下載。

### T082逐項結案與限制

最終完整gate（最後一次測試修改後）：`cache/005-prepare-rag-assets/20261110-final-handoff-gate.log` **1003 passed／31 skipped，127.73秒**；Ruff check／format（139檔）、strict mypy（64 source files）、uv lock --check（183 packages）通過。一般gate的opt-in略過未計入通過；實際雙模型2項、八份文件8項、交接1項各自以以上獨立原始紀錄為證。程式未新增依賴，未修改CI、日常.env或憑證庫，未啟動App／daemon／機器人；沒有自動提交或PR。

| 要求 | 完成證據與界線 |
|---|---|
| FR-001 | 同一CLI分角色執行兩次模型準備，再手動呼叫單文件產包；T058／T069／T080三步交接，無App自動觸發。 |
| FR-002 | T058兩個固定ID／40hex與上游metadata實際核對；非法角色／SHA／浮動來源由離線拒絕測試涵蓋。 |
| FR-003 | T058精確10／6檔safe payload、CPU實際載入、hash／v2 role receipt及零metadata重用；不是品質證明。 |
| FR-004 | T046／T071既有測試驗三checkout預設／跨CWD／wheel明確路徑；本輪三路徑與實際cache目的地在CLI和摘要，不寫設定。 |
| FR-005 | T069八份單文件TXT／Markdown實測；UTF-8 BOM及其他編碼／格式／多輸入拒絕由離線回歸涵蓋；不執行程式碼或連結。 |
| FR-006 | 必填scheme、文件ID／title／版本與來源bytes摘要，缺值／覆寫拒絕測試通過；本輪明確選定完整方案，不附品質合格宣告。 |
| FR-007 | 八份各兩次chunks逐bytes相同，含原文／ID／順序／locator／model_text；TXT混合行尾、重複ATX／fence、空／合法別名實測；錯別名證據／版本／scope拒絕測試通過。 |
| FR-008 | T069／T080雙角色本機safe CPU、全文件向量及BM25離線預建；socket audit零嘗試，無下載／雲端審核／文件外送。 |
| FR-009 | 17個保留包均為v2、真實runtime／Windows目標／完整inventory與方案資訊；schema與004契約／wheel一致；v1拒絕回歸通過。 |
| FR-010 | 每次發布前不同producer／verifier程序，實際DocumentIndex混合／重排query；全rows／vectors／count／metadata、原包hash及副本持久HNSW不變，無命中與操作失敗區分。 |
| FR-011 | T080未授權覆寫4／跨程序busy4／worker啟動取消130均保舊包，明確重試替換0；發布前故障、發布後保新版exit8及硬中斷殘留由既有故障注入／跨程序回歸涵蓋。 |
| FR-012 | 根目錄／link／junction／來源與雙模型重疊拒絕回歸；T069／T080來源／兩模型hash不變，不操作App。 |
| FR-013 | 本輪實際CLI中文結果／路徑／固定碼；sentinel診斷負向測試通過；不讀dotenv／日常憑證／私人模型快取。 |
| FR-014 | root README、env example、架構圖及wheel已同步；既有依賴／lock和SDK公開邊界不變，未改HF預設或相機／記憶權限。 |
| FR-015 | 真實fresh reader沿固定dense10／BM25正分10／RRF60／五候選、raw logit／drop4／三段2000及最後0.58流程；分數界線、截斷、top1拒絕／extras不補段由專用回歸驗證。 |
| FR-016 | 包內provenance及bundled scheme保留final-scheme／report摘要、曝光200題／84/100／2/100／127/131與quality_gate_passed=false；0.58非獨立信心或新文件已校準。 |
| SC-001 | 兩個真實模型各自準備／發布／重用，再單文件產包，無搬檔／改包／改私密設定；CLI三步全通過。 |
| SC-002 | 八份固定有效單文件，各兩次實測16／16發布驗證；涵蓋要求類型及別名，錯配拒絕另有離線測試，僅素材驗收比例。 |
| SC-003 | 至少八類發布前故障及發布後exit8回歸均通過，T080實際拒絕／取消舊包不變；真實OS硬當機／斷電與下載途中斷網未額外實測，不冒稱現場證據。 |
| SC-004 | 本輪父CLI及所有worker繼承離線audit，connect／DNS／sendto零嘗試；T058同版本重用零metadata／下載／覆寫，未啟動App或runtime indexing。 |
| SC-005 | 每個已發布包均通過實際v2 reader與全量／持久索引不變性驗證；只宣告Windows；v1拒絕由回歸證明。 |
| SC-006 | 八份各兩次chunks／BM25全等、來源及alias bytes／兩模型inventory不變；sentinel回歸沒有原文／向量／憑證進產品診斷。 |
| SC-007 | 來源／包／receipt摘要及固定設定可追溯；舊失敗與原分母保留，未以素材成功改寫品質、五秒比例或004生命周期驗收。 |

005活動T043～T082共40／40完成；封存T001～T042原文與checkbox不改，舊T029／T039／T042不倒填。requirements checklist仍為唯讀16／16，未用它表示實作完成。

保留限制：Linux／macOS未實測；受控實際取消在worker啟動後、推論前，非OS硬當機／斷電證據；故障矩陣包含模擬注入。產包與CPU模型實測不是新盲測、文件回答充分性或查詢延遲合格證明。004的舊包專用本機提示排程、50題CPU量測、雙後端／現場／插話與剩餘生命周期驗收仍依004任務執行，未自動勾選。所有本輪模型與素材保留於隔離cache，未搬入正式external_content、未配置或啟動App；後續使用者須明確選定部署素材與三路徑。可選before／after implement Git提交hook依既有不自動提交要求略過，無mandatory hook。

## 增量實作進度（2026-11-10，36／40，真實驗收延後）

使用者明確選擇「本輪保存進度，真實驗收延後」。T058／T069／T080與結案T082保留未完成；不下載、不讀私人模型快取、不啟動App、不用雲端對話或處理example.md。不把下面的假模型證據當作實際BGE驗收。Linux／macOS仍未實測，CI與工程要求未放寬。

### 已完成與交接

- T046／T048／T049／T050：三個checkout預設、wheel明確路徑、雙模型規範排序取鎖再鎖包、busy釋放自有鎖、危險重疊／來源別名保護；scalar私密IPC與獨立producer／verifier、隔離cache／offline環境，以及真實Chroma小包封存回歸已通過。
- T051～T057：角色／固定SHA／safe payload／CPU float32／Identity logits與reference、v2 receipt完整性及runtime、匿名fake Hub完整流程、同版本零metadata／下載重用、清理狀態及相對路徑／中文診斷已通過。T058只完成實際測試入口，未執行。
- T059～T068：單文件與明確scheme、300／30章節切段、64／48脈絡、512完整嵌入輸入、ATX／fence／前言／TXT、原文／CRLF與真實行號、人工別名證據與scope、穩定ID、BM25預建、v2 manifest與完整fresh reader驗證已接通。所有source bytes／別名snapshot在發布前重驗；兩次產包只要求原文／ID／model_text／BM25一致，不要求Chroma二進位相同。T069真模型驗收未執行。
- 共用004讀取部分：v2-only、精確dense10／BM25正分10／RRF60／最多五個完整候選、BGE-base原始logit最低3.486859679222107／drop4／最多3段及2000字元，之後父cosine0.58。query保留、只回傳實際評分的原文前綴；top1超限整次無依據、extras刪除不補段／重排。重排路徑與既有兩路徑在啟動時固定，缺一不啟動worker。004專用舊包提示排程、CPU50題、雙後端／現場與其餘任務仍須依004驗收；本輪未自動勾004任務。
- T070～T079：至少八類故障／並行／替換／取消、發布前保護與發布後exit8、worker未確認退出時連兩模型鎖都保留、中文固定結果／sentinel診斷、README／.env.example與新scheme隨wheel交付已驗。架構圖由既有本機Mermaid CLI重新生成SVG，另以PNG目視確認無遮擋／裁切，未手改SVG、未修改CI／依賴或日常設定。
- 已選定方案封裝為產品document_scheme.json，保存final-scheme.json與report.md的SHA-256及原選案限制；執行時不依賴cache路徑。200題曝光、84/100正例、2/100負例誤放行與127/131支持保留；0.58仍是實務上限，沒有新盲測、品質門檻通過或新文件校準宣告。

### 驗證證據

| 範圍 | 結果與原始記錄 |
|---|---|
| v2 worker／模型／設定與runtime | 81 passed／2 skipped；cache/005-prepare-rag-assets/20261110-v2-runtime.log |
| 五候選／raw-logit／後置距離／可見原文與切段回歸 | 77 passed／2 skipped；20261110-selection.log；後續新增界線案例含於最後完整gate |
| 發布／雙模型保護 | 74 passed／3 skipped；20261110-publication.log |
| 中斷／預設路徑最後回歸 | 76 passed／1 skipped；20261110-shutdown-final.log；包括terminate／kill／wait失敗及第二次Ctrl+C保留所有權 |
| 真實Chroma／假模型額外opt-in | **18 passed（156.12秒）**；20261110-v2-engine-final.log。10種小包／尾批及8份文件含TXT、重複章節、人工別名；每份fresh process、兩次原文／ID／model_text／BM25重現、來源或別名變更拒絕；原包hash／全部rows／向量／count與工作副本持久HNSW不變。使用合成向量與假模型，非BGE實測。 |
| wheel | 先前v1／v2 schema差距已修復；20261110-wheel.log：1 passed，最後完整gate亦含新版manifest／receipt／固定scheme封裝檢查 |
| 第一輪完整gate | **988 passed／20 skipped（77.05秒）**；20261110-full-gate.log |
| 最後發布／邊界完整gate | **1003 passed／23 skipped（85.39秒）**；20261110-release-gate.log。Ruff check／format、strict mypy（64 source files）及uv lock --check通過；使用工作區UV_CACHE_DIR、既有venv、UV_NO_BUILD_ISOLATION=1／UV_OFFLINE=1／REACHY_MINI_SKIP_DOTENV=1。 |

最後一次自審將原文行號邏輯共用，並對chunks.jsonl採16MiB有界逐行讀取及共用finite／重複key檢查；其後完整gate仍為 **1003 passed／23 skipped（72.49秒）**，記錄20261110-reviewed-gate.log，Ruff／format／strict mypy亦通過。PowerShell重導向原始log保留UTF-16 BOM，讀取時依BOM解碼。所有暫存／模型／索引只在工作區cache；未建立正式external_content素材。舊v1、缺權重、Xet失敗與前次gate失敗紀錄保留，不改寫通過。

### 待後續明確opt-in

1. T058：兩個固定安全revision的匿名下載／離線CPU載入、v2角色receipt、前後hash及同版本零網路重用；可在當次Windows測試環境明確設HF_HUB_DISABLE_XET=1使用已知HTTP傳輸方式。沒有本輪授權就不執行。
2. T069：以已驗證的兩個v2模型路徑，執行至少五份非敏感合成文件的真實產包、完整新reader與不變性驗收；不要求已校準門檻，不使用私人文件或舊receipt冒充。
3. T080：按實際兩模型與產包證據完成三步交接／重用／替換／恢復；不因此啟動App或勾004語音／CPU任務。
4. T082：逐項依真實證據結案。目前只交付離線實作，不以36項已完成或品質限制接受取代上述證據。未自動提交或代開PR。

## 增量實作進度（2026-11-09，未結案）

- Windows／Python 3.12.12，分支 `feat/005-prepare-rag-assets`。已讀 AGENTS／CONTRIBUTING／憲章；沿用 lock 中 Chroma 1.5.9、ST 6.2.0、torch 2.15.0+cpu、transformers 5.21.0，未新增或安裝依賴。既有 v1 模型與重排實驗快取只作歷史紀錄，本次未讀取或重新驗證，不以舊 receipt 當 v2 成功。
- T043／T044：005 先供應角色固定值、v2 receipt schema／完整性與實際 runtime 核對；004 T050／T055～T063 負責 v2 包 schema、讀取及完整檢索。`document_model.py` 的 CPU 安全模型載入由兩功能共用，只實作一次；本次已加入基本 raw-logit 載入與將 threads2／1移至程序入口，但004的query保留／原文可見範圍與完整流程尚未驗收，不勾004任務。005 T067 必須重用真正 v2 reader，不得以 mock／schema-only 代替後發布。
- T045／T047：兩角色 v2 receipt 正反例及產品 schema／驗證器已同步。固定 revision、精確10／6檔、bytes／hash、角色互冒／v1／未知欄位／null／重複key／非有限數／BOM／16MiB限制與實際 runtime 不合皆有拒絕測試。假 payload 只驗證邊界，未載模型。
- 其餘部分實作：下載器新增必填 --role，兩角色 fake Hub 下載／離線驗證／零網路重用測試；重排目錄與 siblings 忽略規則；基本 CrossEncoder CPU／safe-only／Identity logits；父／子程序 scalar IPC 檢查。尚不宣告 T046／T048～T058 或 Foundation 整體完成；雙模型 builder 鎖與新版 producer／fresh reader 仍待接線。
- 修改前聚焦基線：42 passed／17 skipped。預設系統 pytest 暫存目錄先遇 WinError5，改用本工作區 cache 的獨立 --basetemp 後執行；此環境失敗未改寫通過。
- 新版聚焦回歸：`tests/test_document_assets.py tests/test_download_document_model.py tests/test_document_model.py tests/test_document_worker.py`：80 passed／2 skipped（真實模型 opt-in）；Ruff／format、strict mypy（64 source files）、`uv lock --check --offline --cache-dir cache/uv` 通過。最後完整 gate 結果另列下方，這些局部成功不代表完整 gate 通過。
- 合成引擎探針：僅設定 RUN_DOCUMENT_CHROMA_PROBE=1，執行 `tests/test_document_prepare_worker.py::test_real_chroma_snapshot_is_sealed`：10 passed（40.54秒）。1／2／3／5／跨批次、公開update／close、fresh process及原包／副本HNSW不變性含負向對照；只用合成向量，未載 BGE、未讀 example.md、未建立正式 App 索引。這不是包含 BM25／章節的新包驗收，因此 T050 保留未完成。
- 完整 pytest 第一輪：957 passed／19 skipped／1 failed（52.37秒）。wheel 初次因日常 uv cache lock 權限失敗；改用工作區cache、既有venv／no-build-isolation／offline後 wheel 可建立，確定失敗在產品 `document_manifest.schema.json` 仍v1、004契約已v2（`tests/test_profile_paths.py:336`）。未放寬測試或只複製schema造成舊reader冒充v2；原始結果留 `cache/005-prepare-rag-assets/implementation-full-gate.log` 與 `implementation-wheel-local.log`。
- 舊產包回歸：`RUN_DOCUMENT_CHROMA_PROBE=1` 的 `test_real_package_producer_and_fresh_reader_preserve_source` **5 passed（58.01秒）**，以假encoder／真實Chroma確認receipt更新未破壞既有v1原文與fresh reader流程；這不是新版章節／BM25／重排包成功證據。記錄 `cache/005-prepare-rag-assets/implementation-legacy-package-regression.log`。
- 最後完整 gate：使用工作區 UV_CACHE_DIR、既有 .venv、UV_NO_BUILD_ISOLATION=1及UV_OFFLINE=1，`pytest tests/ -v` 得 **958 passed／19 skipped／1 failed（46.23秒）**，唯一失敗仍為 wheel 的 v1／v2 manifest schema 比對；記錄 `cache/005-prepare-rag-assets/implementation-final-gate.log`。沒有略過該測試或放寬契約。
- 完成順序：先續T046／T048～T050的005基礎，再協同004 T050／T055～T063與005兩角色worker／producer／T067。v2 reader未備妥前不得發布新版包；缺實際模型驗收仍可做無關離線工作。工程 gate 未綠，不送審、不結案。README 已標示轉換進度；架構圖待 T078 依正式資料流編輯 Mermaid 再生成，不手改 SVG。
- 本次沒有模型下載、App／daemon／雲端連線、私密快取／.env／憑證讀取、正式索引發布或自動提交。Linux／macOS未測；舊失敗、200題曝光及原分母全部保留。

## 前置條件

- Windows／Python 3.12 與本儲存庫；依現有 README 安裝，以 `uv sync --frozen --extra rag --group dev` 取得既有鎖定環境。本輪不重新解析／安裝依賴。
- 兩模型依已選案固定版本：BAAI/bge-m3@50f9396f75618b3389c1fd1068a1ff58dc7b5b26與BAAI/bge-reranker-base@2cfc18c9415c912f9d8155881c133215df768a70，具角色對應安全權重與v2 receipt；不使用main／tag／其他版本或自選PR。
- 一份無敏感資料的 UTF-8 TXT／Markdown，以及文件識別資訊；有額外別名才另提供可核對同文件／版本／digest／scope的人工清單。明確選用版本化完整方案，不要求品質合格校準證明，也不宣稱0.58對新文件可靠校準。
- App 保持停止，相機／記憶不變；兩腳本不啟動機器人、不讀日常 .env／憑證。真實模型下載只有部署者明確執行下載腳本才開始。
- 沿用原嵌入／索引目的地並增加獨立重排目錄；實作須核對新目的地及其sibling stage／backup／lock狹窄忽略規則。自訂輸出放 repo 外或事先自行管理忽略。

## 三個正常準備步驟（新版實作後）

在儲存庫根及已安裝環境，將--input範例改為已授權的唯一文件；以下是未來驗收命令，不是本輪執行授權。三次呼叫各有獨立結果，不以第一個模型成功宣告整套就緒：

```powershell
python -m reachy_mini_conversation_app.download_document_model --role embedding --revision 50f9396f75618b3389c1fd1068a1ff58dc7b5b26
python -m reachy_mini_conversation_app.download_document_model --role reranker --revision 2cfc18c9415c912f9d8155881c133215df768a70
python -m reachy_mini_conversation_app.build_document_package --input example.md --document-id manual --title "測試手冊" --document-version v1 --index-version build-2 --scheme bge-base-final-selection-20261109
```

預期：各模型經角色驗證後分別發布external_content/bge-m3-model/與external_content/bge-reranker-base-model/，含v2 receipt；第三步零網路產external_content/document-package/manifest.json、完整chroma/及retrieval/chunks.jsonl、bm25.json，新程序完整混合／重排驗證成功才發布。三者正常exit0，清理不全exit8仍要處理殘留，不自動重跑。

既有目的地預設拒絕覆寫；只有使用者明確要替換才加--replace，先保護／核對原素材。舊v1 receipt不能直接宣告新版already_ready，舊v1包不能改版本欄冒充v2。--scheme必填，缺少即停止；無--max-distance或個別參數覆寫。需要人工別名時以--aliases指定符合 [chapter-source-v1](contracts/chapter-source-v1.md) 的JSON；不提供即空清單，不自動複製實驗別名。

從不同CWD呼叫仍指source checkout預設目錄；明確相對參數依呼叫CWD解析。wheel無checkout時下載傳--output，builder明確傳--model、--reranker-model及--output。完成只顯示REACHY_MINI_DOCUMENT_MODEL_PATH、REACHY_MINI_DOCUMENT_RERANKER_PATH、REACHY_MINI_DOCUMENT_INDEX_PATH及其值，不改.env；全名與流程以 [CLI契約](contracts/preparation-cli.md) 為準。後續啟用App依實作後根README，不能在本輪啟動。


## 故障與保護

1. 同一完整 revision 再執行下載：already_ready，零網路／零覆寫。
2. 缺 safetensors／不相容配置的完整 revision：大型下載前拒絕，不採另一 SHA／PR、不轉換 bin。
3. 改 model payload 或 receipt hash、移除 tokenizer：明確失敗；無replace不寫目的地，有 replace 的新下載驗證失敗仍保留舊模型。
4. builder 使用已準備模型，於使用者提供的斷網／禁止外連測試環境執行：成功；缺模型時失敗，不代為連網。腳本不自行修改電腦網路。
5. `.txt`、`.MD`、UTF-8 BOM、CRLF／LF／單 CR、中文／英文／否定／表格／程式碼／連結並加入無標題TXT、重複章節／前言／fence及空／合法／不合法人工別名，共至少五份fixture：原文 slice、定位、上限與只讀來源皆正確；不抓連結或執行內容。
6. 無效編碼／空白／PDF／目錄／glob／URL／多輸入、無效識別欄位、缺少／未知scheme、非法aliases或嘗試--max-distance覆寫：明確錯誤，無可用半成品。
7. 兩model／input／aliases／output重疊、根目錄、link／junction、專案受保護目錄或未忽略 repo 內自訂輸出：拒絕，不影響來源。
8. 並行兩命令處理相同模型／目的地：一方持鎖，另一方 busy 立即失敗，沒有互刪；不要用時間或 PID 自動破鎖。
9. 發布前保護：既有目的地無 replace：拒絕。明確 `--replace` 時，注入新包驗證失敗／第二個 rename 失敗：舊資料保持或復原，沒有虛假 completed。
10. 在 preparing／validating／backed_up／published／cleaning 各階段中止子／父程序：不把半成品當完成；顯示可辨識 stage／backup／lock 狀態。先人工確認無準備程序，再核對 operation 記錄及 hashes 恢復完整舊版或已驗證新版；不可直接刪 lock、刪整個輸出或停止無關程序。

11. 新版 rename 已成功後注入 backup／stage／lock／操作記錄清理失敗或取消：新版維持可用且不回復，顯示「已發布，清理未完成」、exit 8、published=true／ready=true，保留可核對殘留；確認沒有自動下載、產包或重試。與第 9 項發布前普通失敗／第 10 項硬中斷分開判定，來源 bytes 在全部案例均不變。

依 [chapter-source-v1](contracts/chapter-source-v1.md) 驗證 golden fixtures、原文完整覆蓋、CRLF、末片、零 offset 與非單調計數；兩次重建的段落／ID／定位／model_text／BM25資料必須一致。假 tokenizer fixtures 只證明演算法，不取代真實 BGE-M3 驗收。另以程序／IPC spy 確認父 CLI 不載 tokenizer／模型、不讀全文切段；worker 產出 candidate 檔案，管道無原文／向量；來源或別名檔中途修改／替換須在發布前拒絕。

以上錯誤碼、CLI 輸出與狀態依 [CLI 合約](contracts/preparation-cli.md)；不將 provider body、原文、向量、token 或私密例外內容加入診斷。

## 新版回歸 gate：真實 Chroma 小包

不需 BGE 模型，先用明確合成 normalized 1024 維向量，獨立 producer 建立 1／2／3／奇數／多 batch fixture；只在 cache 建置，不從 App 路徑建索引。

沿用既有batch_size／sync_threshold=2、相同最後真實row公開update後public close的歷史方法，新版仍需實測回歸。每種案例都要經 fresh process 檢查完整 inventory、原包hash、全部row邏輯／向量／count、chunks／BM25資產、副本持久HNSW hash 及 query／close 後不變性。封存候選存在待回放journal／重建／replay需求或文件索引差異就拒絕；reader工作副本的必要SQLite記帳依004合約分開檢查，不藉此容許索引變更。

若任何合法小文件情境不能以公開 API 產出合規包，**停止交付並回報**。不加假段落、不修改 Chroma 私有表或 004 schema、不刪 journal 掩蓋，不把目前研究當成功證據。

## 自動化驗證命令

```text
python -m pytest tests/test_document_assets.py tests/test_document_model.py tests/test_download_document_model.py tests/test_build_document_package.py tests/test_document_prepare_worker.py -v
python -m pytest tests/test_document_worker.py tests/test_document_retrieval.py tests/test_huggingface_realtime.py tests/test_gemini_realtime.py tests/test_profile_paths.py -v
ruff check . --fix
ruff format .
mypy --pretty --show-error-codes
python -m pytest tests/ -v
uv lock --check
```

一般 gate 不抓模型、不連 provider、不啟動 daemon。fake Hub 驗證 endpoint／token=False／allowlist／專用 cache，spy 驗證 builder 零外連與已就緒分支零下載。模型／索引真正整合採明確 opt-in，未提供核准安全 snapshot 記未執行，不能自選研究候選或把 fake 當真實模型通過。

wheel 測試要涵蓋兩CLI help、雙角色receipt與004 v2 manifest schema 與本功能 schema 相同、不依賴 source specs／遠端 ref、普通 App 不 import optional stack。004雙模型支援的原有安全拒絕、編碼／reference／CPU 與回合回歸仍須通過。

## 證據與交接

記錄 OS／架構、Python／lock、指定 revision、receipt／來源／包 digest、固定 fixture、命令與原始結果；不發布私密原文。每個已發布 target 有 fresh reader 證據，至少五份文件可核對原文，八類故障、兩次切段重現與日誌 sentinel 皆有結果。

本輪 Windows 設計不等於 Windows 實測通過；Linux／macOS 明確未測。模型下載成功也不代表 004 真實 CPU 50 題、兩後端來源品質／插話／文字 timeout 已驗收。完成這兩腳本後才用實際素材續做 004 的待辦，不能在此提前結案。



## 新版完整方案與驗收界線

產包後以新版reader核對：exact dense10／BM25正分10／等權RRF60、最多五個完整候選、BGE-base Identity logit>=3.486859679222107與附加drop<=4、三段／2000字元預算後才套cosine0.58。top1超限全無依據、附加超限刪除不補位／重排；同分ID、候選不足、無token、pair裁切及實際可見原文都須有邊界測試。

正常no_evidence是完整流程的合法結果，不是品質通過；操作失敗不得發布。reader未支援v2或兩模型未就緒時停止，不退回dense-only。模擬與真實測試分開；新模型receipt兩角色正反例、五份文件／人工別名、零網路、發布失敗／清理exit8、wheel／基礎import及完整gate都要留實際證據。

0.58選值來源、模型／策略版本、選案紀錄digest與限制隨版本化方案交付；不依賴工作區cache。曝光200題的84/100正例、2/100負例誤放行與127/131段落支持保留，不稱盲測或原門檻通過。288段只屬原example實驗，通用切段與新資料須另記差異；不新增充分性規則／模型／雲端審核。

004固定CPU主機50題量測與雙後端引用／語音／插話／文字逾時仍另行驗收；五秒／品質比例不阻擋選案，不免除故障安全／禁止捏造／隱私／工程gate。兩功能tasks本輪未改，須增量同步後analyze。

## 歷史紀錄界線

以下2026-11-06素材、舊命令／測試變數、門檻未備妥與passed數字均是當時v1證據，原文保留。新決策已不要求已通過品質驗收的門檻；舊模型payload與receipt可留存；v2的實作及新驗證狀態以上方最新日期紀錄為準，不以歷史任務勾選宣告新版完成。

## 已取得證據（2026-11-06）

範圍為個人客製化、Windows 11 x86_64／Python 3.12.12。使用既有鎖檔，以 `uv sync --frozen --extra rag --group dev --offline --cache-dir cache/uv` 從工作區快取補齊依賴，未改 pyproject.toml／uv.lock、未新增依賴。實際版本：Chroma 1.5.9、Sentence Transformers 6.2.0、torch 2.15.0+cpu、transformers 5.21.0。所有合成資料在 `cache/005-prepare-rag-assets/`；未讀日常 .env／憑證或私人 HF cache，未啟動 App／provider 對話／機器人。

| 驗證 | 結果與範圍 |
|---|---|
| T004／T005 Chroma gate | 10 個真實 Chroma 案例通過，另含忽略規則測試共 11 項。1／2／3／5／超過 API batch 且最後餘一段；原包 hash、全部 rows／向量／count、副本所有持久 HNSW hash 與 query／close 後不變性核對。 |
| 封存方法 | 1 段資料只 close 的負向對照確實改寫 data_level0.bin／length.bin；正式流程 batch_size=2、sync_threshold=2、num_threads=2，最後對最後一筆真實 row 做一次相同內容的公開 update，再 close／退出。未使用假段落、私有 API、刪 journal 或修改 loader 合約。 |
| 五份離線文件 | 中文、英文、否定、表格、程式碼／連結：假 encoder＋真實 Chroma、獨立 producer／verifier 共 5 項通過。audit hook 禁止 socket.connect／getaddrinfo；全量邏輯摘要、原包與持久索引不變。這不是 BGE-M3 語意品質證據。 |
| CLI 串接／來源失敗 | 同一合成中文文件再經實際 builder CLI、隔離私有管道及新工作程序完成驗證／發布，與第一次文件識別／段落數一致；來源修改拒絕發布；無效 UTF-8 回 invalid_document／exit 2，不留可用目的地。最終針對新增無效編碼分支的複驗 1 passed。 |
| 切段 | 正式常數的原文／ID／CRLF／零 offset／非單調計數 golden fixtures、非法映射與重建一致性通過，不比較 Chroma 二進位重現。 |
| 發布／IPC | 發布前各階段取消保留舊版、第二個 rename 失敗復原、發布後清理／記錄失敗及取消維持新版並回 exit 8；跨程序 busy、硬中斷殘留、無法確認 worker 退出時保留素材均通過。私有管道不接受內容型結果，測試 sentinel 不進診斷；模型環境清除憑證並使用獨立 cache／offline。 |
| 下載 | fake Hub／worker 完整準備與同版本重用通過，重用不呼叫 metadata。公開 endpoint、token=False、精確十檔 allowlist、LFS／Git blob hash、傳輸失敗保留舊資料及 provider body 遮蔽均有檢查。 |
| Wheel／文件 | 兩 CLI／共用模型／worker／runtime receipt schema 進 wheel，schema 與合約相同；從 wheel import 輕量入口不載 inference／config。root README 已同步；scheme.mmd 重新產生 SVG，另渲染 PNG 視覺檢查，未手改 SVG。 |
| 完整 gate | Ruff check／format 通過；strict mypy：64 source files 無錯誤；pytest：939 passed、19 skipped；uv lock --check --offline 通過。 |

19 項略過包含 15 項需明確啟用的 Chroma／合成產包測試、2 項真實模型／產包 opt-in，以及 2 項既有 opt-in。前 15 項已另外明確執行，其中 Chroma gate 與五份合成文件的原始 XML／log 留在工作區快取；不把一般 gate 的 skip 算成實際通過。

主要結果檔：`cache/005-prepare-rag-assets/probe-confirmed.xml`、`package-close-and-mutation.xml`、`package-cli-final.xml`、`cli-invalid-encoding-final.xml`、`verified-final-gate.xml`（及對應 log）。測試程序使用自有工作區 basetemp，uv 使用工作區 cache，不修改電腦網路或系統服務。

### 保留的首次失敗與修正

- 初次基線使用系統 tmp 產生環境錯誤；改工作區 basetemp 後基線為 896 passed／2 skipped，唯一 wheel 失敗是工作區外 uv cache 權限；改工作區離線 cache 單獨複驗通過。
- 初次忽略規則測試受 Windows CRLF stdin 影響，改 Git 的 NUL 分隔介面；一段 close-only 的 HNSW 不變性失敗保留為負向對照，正式 producer 依已證明的 public update 方法封存。
- 初次合成產包把 atime 納入來源 stat 比較而誤拒絕；改核對 dev／ino／size／mtime_ns 與最終串流 hash。來源變更測試仍明確拒絕。
- 一輪完整 gate 為 916 passed／17 skipped，wheel 測試以 CP950 讀含中文 receipt schema 失敗；測試明定 UTF-8 後單獨複驗及最終完整 gate 通過，產品原有 UTF-8 讀取未放寬。

### 真實素材待驗

使用者指定 revision：`5617a9f61b028005a4858fdac845db406aefb181`。匿名公開 metadata 回同一 SHA，列出 pytorch_model.bin，但沒有 model.safetensors；實際下載 CLI 回 unsupported_revision，在權重下載前拒絕，隔離目的地未發布。沒有轉換、選用 PR／另一個 commit 或下載不被接受的權重。此舊 revision 的成功驗收未完成；其後使用者另提供的合規 revision 已通過 T019，詳見下節。

指定來源 `example.md`：62213 bytes、UTF-8-sig 解碼 25453 code points，SHA-256 `d1696eed28fa4043645b256ac587f63a7cd1d722e40d13eb6144aef4effb3c07`。僅做指定檔案編碼／摘要檢查；未複製或建立真實索引，來源與模型／索引不入 Git。使用者明確回覆「尚未校準」，因此沒有代填 max-distance。

合規本機模型已依下節補驗備妥；T029／T039 尚缺已校準門檻，T042 保留整體未結案。真實驗收入口已建立，需部署者明確選用：下載使用 RUN_DOCUMENT_MODEL_ACCEPTANCE=1 與 DOCUMENT_MODEL_REVISION；本機產包使用 RUN_DOCUMENT_PACKAGE_ACCEPTANCE=1、DOCUMENT_MODEL_PATH、DOCUMENT_MAX_DISTANCE。這些是測試行程變數，不是 App 設定；未提供有效素材不得勾完成。Linux／macOS 未測，004 真實 CPU／雙後端／語音／品質任務未更動。

| 需求 | 證據／尚缺項目 |
|---|---|
| FR-001～004 | 兩 CLI、固定 revision／allowlist、receipt／hash、CWD／wheel 路徑與零網路重用；真實安全模型下載已依下節 T019 補驗通過。 |
| FR-005～008 | 單文件格式／識別／門檻拒絕、原文 golden fixtures、離線 producer／來源一致性；真實模型編碼待 T029。 |
| FR-009～010 | 真實 Chroma 小包 gate、五份合成文件與既有 reader 全量／關閉後不變性；未擴增平台，真實 BGE-M3 待 T029。 |
| FR-011～013 | 分界取消／rollback／cleanup／hard-crash、跨程序排他、危險路徑與 IPC／日誌 sentinel；來源不修改、沒有 App 行程控制。 |
| FR-014 | README／Mermaid／wheel／全 gate／lock，無新依賴，既有 HF／Tool／相機／記憶設定不變。 |
| SC-001 | fake 下載與合成 CLI 產包分別通過；真實下載已通過；完整交接待 T029／T039。 |
| SC-002 | 五份合成文件通過原文／位置／格式；真實模型同組文件待 T029。 |
| SC-003 | 編碼、格式、revision、完整性、傳輸、未授權覆寫、危險路徑、發布前驗證與發布後清理／中斷有分界保護證據。 |
| SC-004 | fake Hub 同版本零 metadata／下載；五份合成產包禁止網路；真實模型同版本零網路重用已依下節通過。 |
| SC-005 | 真實 Chroma＋假 encoder fresh reader／全量邏輯／HNSW 不變，僅 Windows；真實模型包待 T029。 |
| SC-006 | 純原文切段重建一致、兩次 producer／CLI 文件識別與段落數一致、sentinel／IPC 保護；真實模型完整重現待 T029／T039。 |

## T019 補驗通過（2026-11-06）

- 使用者明確指定的新 revision：`50f9396f75618b3389c1fd1068a1ff58dc7b5b26`。匿名 metadata 解析至同一 SHA，十個必要安全 payload 齊全；舊 revision 的缺檔結果仍保留。
- 第一次實際下載在 hf_xet 原生傳輸階段發生 Windows access violation，沒有發布可用模型。原始 log：`cache/005-prepare-rag-assets/approved-model-50f9396f.log`；沒有依此失敗自動換版本、模型或格式。當時的操作殘留位於同名隔離測試根，未自動破鎖或清除。
- 使用套件支援的當次行程設定 `HF_HUB_DISABLE_XET=1`，在新隔離目錄以一般匿名 HTTP 下載同一 snapshot。此設定不修改 .env、依賴或模型，不是自動模型替代。
- 實際執行 `RUN_DOCUMENT_MODEL_ACCEPTANCE=1`、`DOCUMENT_MODEL_REVISION=<上述 SHA>` 的 `tests/test_download_document_model.py::test_approved_snapshot_loads_offline_and_reuses_without_network`，結果 **1 passed，152.23 秒**；另有 1 個 pytest cache 權限警告，沒有模型驗證錯誤。模型通過離線 CPU 載入、1024 維 normalized finite reference、前後 hash 一致性、receipt 及第二次呼叫零 metadata／下載／覆寫檢查。
- Payload 共 10 檔、2,293,234,427 bytes；根目錄精確 11 檔（含 receipt）。receipt SHA-256：`841e6563d296d012d5be146a11df8084980db4e25d99844c38630522a08fd2d7`；實際 runtime 為 ST 6.2.0／torch 2.15.0+cpu／transformers 5.21.0。
- 已保留模型位置：`cache/005-prepare-rag-assets/approved-model-http-50f9396f/test_approved_snapshot_loads_o0/model/`。這是隔離驗收目錄，不是 App 已啟用的設定；後續可明確以此作為 --model。沒有自動搬移模型或改 App 設定，素材仍不入 Git。
- 原始結果：`approved-model-http-50f9396f.log`／`.xml`；不含向量的本機摘要：`approved-model-http-summary.json`，皆在同一工作區 cache 根。

本次僅更新驗收證據與傳輸方式說明，沒有程式或依賴變更；前輪完整 gate 939 passed／19 skipped 仍保留，這次另外明確執行的真實模型測試補足其中一項 opt-in。不能將本次 reference 向量驗證當成文件檢索品質、CPU 50 題或語音驗收通過。使用者仍明確表示門檻尚未準備，T029／T039／T042 保持未完成，進度 39／42；example.md 未產包、未修改或外送。
