# Tasks: RAG 雙模型準備與單文件 v2 離線產包

**Input**: 本目錄 [spec](spec.md)、[plan](plan.md)、[research](research.md)、[data-model](data-model.md)、[CLI契約](contracts/preparation-cli.md)、[receipt契約](contracts/model-receipt.md)、[章節契約](contracts/chapter-source-v1.md) 與 [quickstart](quickstart.md)；包格式以 [004 v2契約](../004-single-document-rag/contracts/index-package.md) 為唯一準據。

**Branch**: `feat/005-prepare-rag-assets` | **Date**: 2026-11-09。

**Design Sync**: 固定雙模型與bge-base-final-selection-20261109，兩次模型準備再一次離線產包；不將舊版已完成或實驗數字當作v2實作證據。

**Tests**: SC-001～SC-007及驗收情境要求模型／包／發布／重現／隱私測試，憲章要求happy path與regression；依故事先寫能捕捉缺失的測試，再實作，不為薄函式製作鏡像測試。

## Format and execution scope

- 本輪活動任務僅T043～T082；40項全部完成；T058／T069／T080依使用者2026-11-10最新明確授權完成Windows真實驗收，T082已以需求對照及最終完整gate結案。T001～T042完整原文及39已完成／3未完成狀態保留在文末四反引號歷史區塊；實作時忽略該存檔的checkbox，不能按舊單模型／已校準門檻／source-window-v1執行。
- ID延續、不重編號／倒填歷史完成率。`[P]`只允許前置完成後不同檔案工作並行，不授權派代理；同檔修改及跨004／005的共享支援須協調一次完成。
- 任務產生階段未執行下載／產包／gate；目前離線實作與執行結果見quickstart.md。一般gate與離線假資料不下載模型、不讀.env／日常憑證／私人快取、不連HF／Gemini／daemon或啟動App。實際下載／本機重型驗收採明確opt-in及信任來源，不將當時授權當作每輪自動重跑授權。
- 所有文件向量、BM25 TF／DF／長度／avgdl、章節／別名與索引由005離線預建；004只消費包、算query／重排。兩模型獨立發布，不引入一命令雙目的地彙總、另一提供者、充分性規則／模型或雲端審核。
- Python3.12／Windows本機驗收；Linux／macOS依既有要求略過、不可記pass。程式仍採可攜API、SDK公開介面、既有lock與CI。保留發布前舊素材保護與發布後清理exit8，無憲章豁免或自動提交。

## Phase 1: Setup — 固定新版基線與004責任

- [X] T043 核對 `AGENTS.md`、`CONTRIBUTING.md`、`.specify/memory/constitution.md`、本功能設計與既有lock，於 `specs/005-prepare-rag-assets/quickstart.md` 記錄Python3.12／Windows／分支／既有gate及可用資產狀態；保留舊revision缺安全權重、傳輸失敗與200題曝光紀錄，不讀私密快取、不因缺真模型阻擋無關離線工作。
- [X] T044 對照 `specs/004-single-document-rag/tasks.md` 的T046／T050／T055～T063與本功能v2契約，在 `specs/005-prepare-rag-assets/quickstart.md` 記共享document_model／document_assets／manifest schema的實作責任及交接。沿用 `pyproject.toml`、`uv.lock` 的Chroma1.5.9／ST6.2.0／CPU torch與標準庫，不新增框架；004 reader可先用合成v2資料開發，005 receipt基礎先到位，實際發布再依reader驗證，不要求任一功能先整體結案。

## Phase 2: Foundational — 雙角色receipt、路徑與工作程序

**Goal**: 在故事前保護既有資料並固定v2身分／程序邊界；新功能無素材時仍可做離線驗證。

- [X] T045 [P] 在 `tests/test_document_assets.py` 為 `specs/005-prepare-rag-assets/contracts/model-receipt.schema.json` 建v2兩角色正反例：role／ID／固定SHA一致、resolved_revision相等、payload各10／6檔且每path恰一次、size_bytes>=1／SHA256小寫64hex、未知欄位／null／重複key／NaN／Infinity／BOM／超16MiB拒絕；v1／角色互冒／不合safe weights拒絕，不遠端載schema，fixture不是實際可用模型。
- [X] T046 [P] 在 `tests/test_build_document_package.py` 為雙模型／來源／別名／output路徑與基礎發布寫測試：三個checkout預設與CWD無關、wheel無checkout必填明確路徑，根目錄／link／junction／Windows別名／重疊拒絕；兩模型規範路徑排序取鎖後取output、busy立即失敗並釋放本次鎖，不按PID／時間破鎖。發布前保護舊版、發布後清理exit8的基本行為先測，不延到US3才處理。
- [X] T047 在 `src/reachy_mini_conversation_app/document_assets.py` 與 `src/reachy_mini_conversation_app/document_model_receipt.schema.json` 同步v2 typed要求／receipt驗證，逐字落實「role必填embedding／reranker；repo_id分別固定BAAI/bge-m3／BAAI/bge-reranker-base；revision必填且須等於方案固定SHA」、「replace 為明確布林；預設 false」。固定SHA分別50f9396f75618b3389c1fd1068a1ff58dc7b5b26／2cfc18c9415c912f9d8155881c133215df768a70，schema_version2、所有required／精確檔案清單與實際完整runtime檢查；模型根「實際檔案集合須等於 payload＋receipt」，inventory不含自己，包內各模型清單另含receipt hash。v1不就地改寫／冒充already_ready。
- [X] T048 在 `src/reachy_mini_conversation_app/document_assets.py` 依T046擴充獨立重排預設external_content/bge-reranker-base-model/，保留嵌入／索引位置；checkout標記辨識、wheel不寫site-packages。共用鎖／stage／backup保留「operation_id：隨機 UUID；kind=model／package；本次 owner PID 僅診斷，不能用來自動授權清理」及「destination_name、stage_name、backup_name：已核對父目錄內的 basename，不接受 `..`／絕對路徑／link」；排他、不可時間過期，先確認原路徑與祖先安全再操作。
- [X] T049 在 `tests/test_document_prepare_worker.py` 及 `src/reachy_mini_conversation_app/document_assets.py`、`src/reachy_mini_conversation_app/document_prepare_worker.py` 擴充typed內部operation／角色／雙模型／scheme／aliases已驗證路徑scalar協定；先測IPC拒絕全文／chunks／vectors（含reference）／pickle，再接線。父CLI持鎖、worker只寫candidate，producer／fresh verifier不同程序；專用空HF_HOME／offline／telemetry off／SKIP_DOTENV並清除憑證／自訂endpoint，重型import僅工作模組頂層，確認退出才發布或清理，無socket／SDK／dotenv。
- [X] T050 明確選用執行 `tests/test_document_prepare_worker.py` 的真實鎖定Chroma合成小包回歸，覆蓋1／2／3／奇數／多batch餘一段；沿既有batch_size2／sync_threshold2／num_threads2、最後真實row相同內容公開update／close／退出方法，在 `specs/005-prepare-rag-assets/quickstart.md` 記原包hash／全rows／vectors／count及副本全部持久HNSW不變性。只用合成向量，不載BGE／原文件；若新包無法合規封存即阻擋producer真實交付，不用假段落／私有API／刪journal／改reader過關。缺extra只記未執行，不能當pass。

**Checkpoint**: Foundation離線邊界完成，真實引擎回歸有證據後才宣告新producer可交付；舊gate不代表新流程通過。

## Phase 3: US1 — 分角色準備可離線使用的兩模型（P1，MVP）

**Independent Test**: fake Hub／role驗證worker經公開CLI準備兩個獨立模型目的地，重複同完整角色／版本零metadata／零下載；真實safe模型另opt-in，不需文件／服務／機器人。

### Tests

- [X] T051 [P] [US1] 在 `tests/test_download_document_model.py` 測--role embedding|reranker及--revision必填／固定40hex，拒絕main／tag／其他ID／URL／endpoint／版本不合；角色預設目的地、明確--output／--replace、三路徑設定建議與中文exit碼。每次只處理一角色，另一角色失敗不動已就緒者，單一成功不宣告整套ready。
- [X] T052 [P] [US1] 在 `tests/test_document_model.py` 測兩角色safe-only／CPU float32／local-only／無remote code／hash／完整runtime與reference／raw logit；嵌入1024維finite／非零／L2 norm<=1e-4、reference cosine差<=1e-5，重排固定非敏感query／passage／有限Identity logit／pair512／batch4，不設品質分數門檻。每工作程序只設定一次threads intra2／inter1，攔截GPU／pickle／網路、角色互冒及重複inter-op設定；與004共享模型回歸。

### Implementation and evidence

- [X] T053 [US1] 在 `src/reachy_mini_conversation_app/download_document_model.py` 接入角色／固定SHA與獨立output解析；先驗路徑／鎖／已有完整v2 receipt，全部相符才already_ready並零網路。缺role／非法SHA或未授權替換先拒絕；v1不默改ready，需明確重新準備且替換須--replace。保持CLI輕量不import config／registry／inference；一命令不連帶另一角色。
- [X] T054 [US1] 在 `src/reachy_mini_conversation_app/document_prepare_worker.py` 重用 `src/reachy_mini_conversation_app/document_model.py` 的004雙角色typed支援（對應004 T056，共享檔只實作一次）進行候選離線驗證；embedding CLS／Normalize／1024／8192模型上限與本方案512輸入不混用，reranker CrossEncoder Identity raw logit／CPU float32。verification嵌入固定query＋normalized reference，重排固定query「這份文件主要說明什麼？」／passage「這是一份提供文件查詢的示範說明。」＋有限原始logit，寫candidate receipt而非IPC向量；前後hash／程序退出確認才可發布。
- [X] T055 [US1] 在 `src/reachy_mini_conversation_app/download_document_model.py` 依角色精確10／6檔allowlist作匿名Hub預檢／下載，固定公開endpoint／token=False／本次專用cache、resolved SHA相同、必要小型配置／safetensors存在後才取大檔；上游LFS／Git blob識別及本機hash驗證，拒絕bin／pt／Python／link／下載metadata。不得自選PR、轉換權重、換模型／版本、讀日常token／HF_ENDPOINT／快取，provider body不進診斷；只發布乾淨payload＋receipt。
- [X] T056 [US1] 在 `src/reachy_mini_conversation_app/download_document_model.py` 串接離線模型驗證、共用安全發布與結果，落實「status 為 completed／already_ready／failed／busy／recovery_required」「published 為必填布林」「ready（bool 或 null）」：completed=true/true、already_ready=false/true、發布前失敗／busy=false/null、發布後清理不全true/true且exit8。清理不全保留新版與人工指引，不重試／rollback，不寫.env或操作App。
- [X] T057 [US1] 執行 `tests/test_download_document_model.py`、`tests/test_document_model.py`、`tests/test_document_prepare_worker.py` 的兩角色fake完整下載、離線驗證、失敗保護與same-role/revision重用；spy確認零metadata／零下載與另一目的地不被動到。於 `specs/005-prepare-rag-assets/quickstart.md` 記實際命令／角色／snapshot／結果，不用fake或reference聲稱文件品質／時限通過。
- [X] T058 [US1] 在 `tests/test_download_document_model.py` 擴充明確opt-in的兩固定安全模型實際準備／離線載入／前後hash／同版本零網路重用驗收，於 `specs/005-prepare-rag-assets/quickstart.md` 分角色記v2 receipt／payload摘要與實際runtime。只對本次明確授權的公開來源與隔離目的地執行；既有BGE-M3 v1證據及rerank實驗快取不冒充v2通過，不掃私人快取或自動下載。缺授權／資產保持未完成，可繼續離線US2／US3。

**Checkpoint**: MVP為兩角色分開準備／安全發布；真實US1只有T058有對應證據才可宣告完成，不代表索引／對話可用。

## Phase 4: US2 — 單文件章節／別名／BM25的完整v2包（P1）

**Independent Test**: 假encoder／reranker＋真實Chroma（明確opt-in），至少五份固定無敏感TXT／Markdown，驗原文／定位／BM25／兩次重現及新reader完整流程；真實雙模型另驗收。不依賴US1網路，可信外部v2角色模型亦可。

### Tests

- [X] T059 [P] [US2] 在 `tests/test_build_document_package.py` 測必填--scheme bge-base-final-selection-20261109、缺／錯scheme／--max-distance覆寫拒絕、單一--input／重複input／額外參數拒絕，--model／--reranker-model／--aliases及三checkout預設；文件識別「004 安全 identifier」「title 為既有 160 code point 限制」。以chapter-source-v1正式常數建golden fixtures：ATX／fence／前言／無標題TXT／重複標題／CRLF／單CR／EOF／長段／零offset／非單調回退，300／30與512限制不靠縮參數測。
- [X] T060 [P] [US2] 在 `tests/test_document_prepare_worker.py` 測producer同來源快照／合法與無效人工別名、v2 manifest／全量BM25及fresh verifier，IPC無原文／vectors，socket／DNS spy保證產包零外連；來源或別名中途修改／替換拒絕發布。reader未支援v2／語意不符／操作失敗不能發布，正常no_evidence與故障分開，假encoder＋真實Chroma結果不當模型品質證據。

### Implementation and evidence

- [X] T061 [US2] 在 `src/reachy_mini_conversation_app/build_document_package.py` 接入明確--scheme及獨立--reranker-model／可選--aliases；不默認scheme、不要求逐項參數或品質合格校準證明、不接受--max-distance覆寫。輸入「唯一 .txt／.md／.markdown 常規檔，case-insensitive；不可為 link／junction／URL／glob」，UTF-8／BOM合法，其他編碼與無有效字母數字拒絕；兩模型缺失／不合v2 receipt即失敗，不抓模型。父CLI只讀scalar／路徑，不讀全文切段或載tokenizer／inference。
- [X] T062 [US2] 在 `src/reachy_mini_conversation_app/build_document_package.py` 實作worker呼叫的typed純chapter-source-v1切段，沿 `specs/005-prepare-rag-assets/contracts/chapter-source-v1.md` 明確ATX／fence／階層範圍、前言／純空白／純標題覆蓋、TXT單範圍；target300／overlap30／heading64／alias48／完整embedding512含special tokens。offset合法且不切CRLF、段落後半空行優先、逐合法字元非單調回退、長段續切與嚴格前進／有限終止，無decode重寫／省略；舊400／50只存檔，不作v2 fallback。
- [X] T063 [US2] 在 `src/reachy_mini_conversation_app/build_document_package.py` 與 `src/reachy_mini_conversation_app/document_prepare_worker.py` 依章節契約驗證人工aliases JSON：schema1、document_id／version／source_sha256完全對應，text恰等於evidence原文、scope為真實章節子樹或單範圍；無檔等同明示空清單，不擷取／生成同義詞。固定context末3層／64tokens、alias48tokens與model_text模板及digest，別名不作引文；stable ID canonical keys含source／policy／configuration／aliases／model_text摘要與start/end。逐字落實「0 <= start < end <= len(text)」「恰為 source.text[start:end]；不能從 token decode 重建」及locator「L<first>-L<last>; chars[<start>,<end>)」，行號1-based inclusive／字元0-based end-exclusive，不虛構頁碼。
- [X] T064 [US2] 在 `src/reachy_mini_conversation_app/document_prepare_worker.py` 從完整model_text離線預建ascii-cjk23-v1 BM25資料，生成retrieval/chunks.jsonl與bm25.json固定欄位；TF／DF只列正整數、df<=N、length=sum(tf)、avgdl為平均、N由chunk_ids長度取得，空token段length0／全空avgdl0合法且lexical0分。保留chunks／Chroma ID全集與順序、model_text digest／raw來源映射，不用pickle／額外套件，不把建統計搬進App。
- [X] T065 [US2] 在 `src/reachy_mini_conversation_app/document_prepare_worker.py` producer一次讀來源及可選別名bytes，來源「UTF-8 解碼前 bytes（含原 BOM）hash」、initial_identity／initial_stat讀前後一致；hash／解碼／切段／embedding同緩衝區，不正規化Unicode／行尾。重用共用BGE-M3 encoder與T050公開Chroma封存，row id=chunk_id／documents=text／metadata document_id／version／locator，與chunks一對一；模型／來源不修改，完成public close且退出才列inventory，不加假段落／私有API／刪journal。
- [X] T066 [US2] 在 `src/reachy_mini_conversation_app/document_prepare_worker.py` 與 `src/reachy_mini_conversation_app/document_assets.py` 組成004唯一v2 manifest：schema_version2、單文件／版本／集合、精確runtime／平台、完整chroma及retrieval inventory、兩模型payload＋receipt hash、非敏感reference、strategy／chunking／BM25／retrieval／reranking／provenance。將固定scheme參數、final-scheme.json／report.md digest與限制隨程式交付，不依賴cache或遠端schema；quality_gate_passed=false、200題曝光／84/100正例／2/100負例誤放行／127/131支持及歷史來源摘要與實際文件摘要分開，288段與實驗別名不硬編碼。0.58只為重排／預算後父cosine上限，不稱新文件已校準。
- [X] T067 [US2] 在 `src/reachy_mini_conversation_app/document_prepare_worker.py` fresh verifier以004 v2 DocumentIndex及兩模型，在完整副本執行exact dense10／BM25正分10／等權RRF60完整5候選、Identity logit最低3.486859679222107／drop4／3段及2000code points，再父cosine0.58；top1超限整次無依據，extras超限只刪不補／重排。核對原包全hash、全rows／metadata／vectors／count、BM25／chunks及副本持久HNSW不變，允許必要SQLite記帳而非replay／migration／重建；操作失敗或reader未支援不得發布。發布前串流來源／別名hash及身分／stat核對，變更即拒絕，不重新decode／tokenize建資料。
- [X] T068 [US2] 執行 `tests/test_build_document_package.py`、`tests/test_document_prepare_worker.py` 的至少五份合成單文件：中文／英文／否定／表格／程式碼連結，另含無標題TXT／重複ATX／fence／前言／空與合法別名；錯版本／證據／scope必拒絕。重建至少兩次核對text／ID／順序／locator／model_text／BM25一致，原文／兩模型hash不變、零外連，結果記 `specs/005-prepare-rag-assets/quickstart.md`；不要求Chroma二進位相同，不稱新切段或ID必然等同舊288段／歷史品質。
- [X] T069 [US2] 在 `tests/test_build_document_package.py` 擴充真實本機雙角色v2安全模型＋至少五份無敏感文件opt-in產包驗收，使用新版fresh reader驗全部原文／來源／BM25／向量／HNSW不變性與零網路，於 `specs/005-prepare-rag-assets/quickstart.md` 記來源／別名／receipt／包digest、runtime及原始命令／失敗。可使用可信外部同等v2模型，不強制先網路下載；缺素材或004 reader未就緒保持未完成，不放寬素材驗證或用fake代替。

**Checkpoint**: T068完成離線US2，T069才是實際模型產包證據。包只驗素材與整合，不代表004 CPU／語音驗收。

## Phase 5: US3 — 安全發布、清理與交接（P2）

**Independent Test**: 以受控子程序與自有假素材測跨腳本鎖、發布前後失敗／取消／硬中斷；完整中文結果與設定建議，不需下載或App。

- [X] T070 [P] [US3] 在 `tests/test_document_assets.py` 擴充雙角色／v2包發布矩陣：階段「locked → preparing → validating → validated → backed_up（僅替換）→ published → cleaning」，stage→destination成功即發布，之前失敗恢復舊payload bytes；之後backup／stage／lock／記錄失敗保留新版、cleanup_incomplete／published=true／ready=true／exit8，禁止rollback／重跑。測記錄落後phase／硬中斷與發布前取消130／恢復失敗8(false)、發布後取消8(true)，來源及別名檔全情境零修改。
- [X] T071 [P] [US3] 在 `tests/test_download_document_model.py`、`tests/test_build_document_package.py` 建真實跨程序fake CLI測試：兩模型依規範路徑排序後取包鎖、busy failfast／釋放自有鎖、拒絕共享／重疊模型目錄、不同CWD／wheel明確路徑、三次呼叫／各目的地獨立結果；stdout／INFO／DEBUG放sentinel驗無原文／vectors／token／provider body。完成顯示三設定值但不改.env／一般設定／憑證，不啟動App或其他程序。
- [X] T072 [US3] 在 `src/reachy_mini_conversation_app/build_document_package.py`、`src/reachy_mini_conversation_app/document_assets.py` 完成兩模型解析／平台規範排序取讀鎖，再取output鎖；拒絕兩模型彼此或原文／aliases／output危險重疊、link／junction／根目錄／Windows別名／未忽略repo輸出，操作與發布前重驗。busy立即釋放本次鎖、無佇列／PID超時破鎖，005不提供App行程鎖，部署者自行先停止App。
- [X] T073 [US3] 在 `src/reachy_mini_conversation_app/document_assets.py` 依T070維持old→backup／validated stage→destination發布界線；普通發布前失敗還原舊版，Windows不假設非空目錄原子replace或目的地路徑全程存在。發布後記錄／清理失敗保留新版並明示「已發布，清理未完成」、recovery_required／cleanup_incomplete／true/true／exit8，保留自有殘留／hash／人工指引，不自動rollback／下載／產包／重試；只清本次已核對目錄，不刪無關內容。
- [X] T074 [US3] 在 `src/reachy_mini_conversation_app/download_document_model.py`、`src/reachy_mini_conversation_app/build_document_package.py`、`src/reachy_mini_conversation_app/document_prepare_worker.py` 接續雙角色／v2的中斷傳遞與退出確認，未確認子程序退出不發布／清檔；發布前可復原取消130、無法復原exit8／published=false，發布後取消清理exit8／published=true／ready=true。硬中斷保留操作記錄與backup，人工先確認無準備行程再核對實際hash恢復，不自動recover或只刪lock；不讓第三方traceback／內容外洩。
- [X] T075 [US3] 執行 `tests/test_document_assets.py`、`tests/test_download_document_model.py`、`tests/test_build_document_package.py` 至少八類SC-003故障／並行／替換／中斷矩陣；發布前舊資料保護與發布後保留新版分開驗證，全部來源／別名／兩模型不被產包修改。已完成單角色不被另一角色失敗改動，不以published=true／ready=true混成exit0；結果寫 `specs/005-prepare-rag-assets/quickstart.md`，不停止無關程序或操作日常Control App。
- [X] T076 [US3] 在 `specs/005-prepare-rag-assets/quickstart.md` 記US3獨立結果、人工恢復／exit對照、三個實際設定值REACHY_MINI_DOCUMENT_MODEL_PATH／REACHY_MINI_DOCUMENT_RERANKER_PATH／REACHY_MINI_DOCUMENT_INDEX_PATH；標記各目的地狀態及實際Windows目標，未測Linux／macOS不算pass。交給004事先建妥的v2包，無App啟動／模型搜尋／設定寫入／runtime indexing；005成功不勾004語音／CPU／插話任務。

## Phase 6: Polish & Cross-Cutting Validation

- [X] T077 [P] 更新 `README.md` 的兩CLI三步／角色與固定revision、必填--scheme／可選--aliases、章節／TXT／原文定位、預建BM25／v2-only／v1重產、三預設及明確路徑、雙模型safe receipt、發布前保護／發布後exit8與人工恢復；同步補新重排目的地及sibling忽略測試涉及的 `.gitignore` 狹窄規則與 `tests/test_document_assets.py` 回歸。不修改日常.env或多建README／docs Markdown，不稱0.58品質合格。
- [X] T078 [P] 依實作更新 `docs/scheme.mmd`，用既有流程重生 `docs/assets/conversation_app_arch.svg` 並視覺檢查；呈現兩角色下載／單文件章節別名及BM25離線產包／新版004讀取資料流，不手改SVG、不改CI。此任務不編輯README，以免與T077衝突。
- [X] T079 在 `tests/test_profile_paths.py` 驗證wheel包含兩CLI、model／prepare worker、雙角色receipt schema／004 v2 manifest及固定scheme來源digest／必要資料；schema與004／005契約一致、無source specs／cache／遠端ref依賴。普通安裝／help不import inference／config／SDK，不裝rag仍可讀help，無checkout明確給model／reranker-model／output，不寫site-packages；模型loader／004 Tool生命週期回歸不退化。
- [X] T080 在取得本次明確opt-in範圍及T058／T069實際證據後，依 `specs/005-prepare-rag-assets/quickstart.md` 驗三步完整Windows交接：兩固定模型各自驗證／發布／同版本零網路重用，再唯一文件產包／新reader全量查詢不變性，至少五份文件及兩次重現、替換／並行／中斷恢復皆留來源／aliases／receipt／包digest。可信外部模型可滿足T069但不能冒稱下載步驟通過；0.58無須品質合格證明、素材缺項不宣告完成，Linux／macOS不補測或記pass。
- [X] T081 自審 `src/reachy_mini_conversation_app/`、`tests/`、`README.md`、`.gitignore` 與架構diff，依 `AGENTS.md` 執行Ruff check／format、strict mypy、完整 `pytest tests/ -v` 及 `uv lock --check`，在 `specs/005-prepare-rag-assets/quickstart.md` 記實際結果／skips。typed公共API／頂層imports／SDK公開API／無新Any或ignore／現有依賴lock／CPU與跨平台路徑均檢查；一般gate不下載／連雲端／啟動機器人，舊939項與fake不作新版pass，必要回歸失敗先修。
- [X] T082 在 `specs/005-prepare-rag-assets/tasks.md` 及 `specs/005-prepare-rag-assets/quickstart.md` 對FR-001～FR-016／SC-001～SC-007逐項結案，只勾充分證據；保留歷史缺權重／Xet失敗、200題曝光／84/100／2/100／127/131及原分母。品質／五秒比例非選用門檻，但素材完整性／不變性／故障安全／必要量測與工程gate仍不可免除；缺T058／T069／T080只記部分交付。舊T029／T039／T042存檔不倒填，004 CPU／雙後端／現場另驗，不改requirements checklist或代開PR。

## Dependencies & Execution Order

```text
T043 → T044 → T045/T046 → T047 → T048 → T049 → T050
  → US1: T051/T052 → T053 → T054 → T055 → T056 → T057 → T058(opt-in)
  → US2: T059/T060 → T061 → T062 → T063 → T064 → T065 → T066 → T067 → T068 → T069(opt-in)
  → US3: T070/T071 → T072 → T073 → T074 → T075 → T076
  → T077/T078 → T079 → T080 → T081 → T082
```

- 所有故事依Foundation；T050是新版producer交付前真實Chroma回歸，無BGE需求。可先寫不依真實引擎的測試，但未取得封存／不變性證據不能把producer標成可交付。
- 005 T047 receipt／基礎驗證先供004共用；004 T056與005 T054共享model支援只實作一次，後者專注準備worker／receipt檢查。004 T055～T063可用合成包先完成reader，005 T067再重用它fresh verify；005不要求004先整體結案，004真實T069則等005包備妥，無循環依賴。跨功能同檔修改循序合併。
- US2使用可信外部v2雙角色模型即可獨立開發，不依US1下載連線；T058未獲本次授權可先繼續T059～T068／US3／文件。T067需要004新版reader實作，未到位先完成producer候選與離線測試、不得發布；不改用舊reader、mock或僅schema代替真實驗證。
- T058及T069是各自真實驗收，可等待資產／授權而繼續不依賴的離線工作；T080必須兩者與US3完成，不能用時間經過、歷史receipt或已曝光實驗當成完成。不同模型目的地失敗不自動重跑另一目的地。
- US3矩陣依兩CLI離線成功T057／T068，不依賴實際下載；基本路徑／發布保護在T046／T048就須到位，不能先讓US1／US2破壞舊素材再等US3修。T070／T071先測新版擴充，T072～T074作必要最小修正。
- T077／T078在介面穩定後不同檔案可並行；T079與004包裝工作協調一次。T081是最終gate，實作過程先跑必要回歸，缺真模型仍可做離線gate／記部分交付；T082不得免除必要真實素材驗證或以舊勾選代表新版。

### Parallel examples per story

| 群組／共同前置 | 不同檔案可並行工作 | 合併點 |
|---|---|---|
| Foundation／T044 | T045 assets receipt測試、T046 builder路徑測試 | T047～T050 |
| US1／Foundation | T051 download CLI測試、T052 model測試 | T053～T057 |
| US2／Foundation | T059 builder切段／輸入測試、T060 prepare worker測試 | T061～T068 |
| US3／T057及T068 | T070 assets故障、T071兩CLI跨程序測試 | T072～T076 |
| Polish／T076 | T077 README／ignore／測試、T078 Mermaid／SVG | T079之後 |

## Requirement and Evidence Coverage

| 規格 | 新版任務 |
|---|---|
| FR-001 手動三步／不動App | T044、T049、T051、T053／T056、T061、T071、T076、T080 |
| FR-002 固定兩角色版本／下載 | T045、T047、T051～T055、T058 |
| FR-003 安全模型／receipt／重用 | T045、T047、T052～T058、T079 |
| FR-004 三路徑／設定交接 | T046／T048、T051／T053、T059／T061、T071／T072、T076、T079 |
| FR-005 單文件UTF-8／不展開 | T059～T063、T065、T068／T069 |
| FR-006 明確scheme／識別／來源 | T059、T061、T063、T065／T066、T068 |
| FR-007 原文／章節／別名／定位 | T059／T060、T062／T063、T065、T068／T069 |
| FR-008 雙模型本機／零外連 | T049、T052／T054、T060、T064～T069、T080 |
| FR-009 v2完整包／v1拒絕 | T044／T047、T060、T064～T067、T069、T079 |
| FR-010 發布前全流程／不變性 | T050、T060、T065～T069、T080 |
| FR-011 發布界線／清理exit8 | T046／T048、T056、T070～T076、T080 |
| FR-012 路徑／鎖／不控App | T046／T048／T049、T059／T061、T070～T076 |
| FR-013 中文／固定碼／隱私 | T049、T051、T055～T057、T060／T061、T065、T071、T074～T076 |
| FR-014 README／既有架構依賴 | T043／T044、T076～T079、T081 |
| FR-015 完整固定檢索／重排設定 | T044、T059／T061、T064、T066／T067、T069、T079 |
| FR-016 曝光／選值／原失敗 | T043、T057、T066、T068、T076／T077、T080～T082 |
| SC-001 三步完整素材 | T057／T058、T068／T069、T071、T080 |
| SC-002 五份文件／TXT／別名 | T059／T060、T062／T063、T068／T069、T080 |
| SC-003 八類故障／分界保護 | T045／T046、T050、T051／T052、T059／T060、T070～T075、T080 |
| SC-004 零外連／重用／App零建索引 | T049、T051～T058、T060、T064～T069、T076、T080 |
| SC-005 新reader／不變性／平台 | T044、T050、T060、T065～T069、T076、T079／T080 |
| SC-006 兩次重現／無診斷洩漏 | T059／T060、T062～T065、T068／T069、T071／T075、T080 |
| SC-007 追溯／限制／安全保留 | T043／T044、T052、T058、T066～T069、T076～T082；004 runtime安全仍由004任務驗 |

### Historical pending-task handoff

| 舊未完成項（只存檔、不再按舊定義執行） | 新版接替 |
|---|---|
| T029 真實單模型產包 | T069，改雙角色／完整v2方案 |
| T039 真實兩步交接 | T080，改三步且保留發布保護 |
| T042 舊版結案 | T082 |

## Implementation Strategy and Task Summary

1. MVP為Foundation與US1（T043～T057離線），角色逐一準備與安全發布；只有T058實測可宣告真模型準備成功，尚不能宣告文件查詢交付。
2. 加US2完整章節／別名／BM25產包及004 fresh reader驗證，再US3跨程序／中斷／交接。保留基本發布保護早於故事實作，不以新功能延後安全。
3. 文件／wheel／真實三步證據與最後gate依序；缺資產／授權不重複停下無關離線工作，但真實驗收保持未完成。品質比例不阻擋選案，不免除素材、生命週期、隱私或工程要求。
4. 新版40項：Setup2、Foundation6、US1 8、US2 11、US3 7、Polish6；10項[P]限不同檔案群，全部含ID／路徑，只有故事階段加US標籤。本輪36/40完成；歷史42項39已完成／3未完成不計新版完成率。
5. 本次離線實作與完整gate已執行，證據見quickstart.md。使用者選擇保存進度、真實驗收延後；下次接續T058／T069／T080，再依實際證據結案T082。不下載、啟動App或自動提交，不將舊receipt／fake結果冒充真模型通過。

## 歷史任務與證據（2026-11-06，唯讀存檔）

以下完整原文只代表當時snapshot，保留舊門檻、素材狀態及核取方塊。它不是本輪活動任務，不能把舊source-window-v1／校準阻擋或成功數套到新版。

````markdown
# Tasks: RAG 模型下載與單文件離線產包

**Input**: `specs/005-prepare-rag-assets/` 的 spec、plan、research、data-model、contracts 與 quickstart。
**Branch**: `feat/005-prepare-rag-assets` | **Date**: 2026-11-06
**Prerequisites**: 依 2026-11-06 最新 plan／data-model／CLI 與 [source-window-v1](contracts/source-window-v1.md) 重新同步；004 v1 包與 reader 拒絕條件不變。
**Tests**: 依 spec 的驗收情境／SC、plan 的明確驗證要求及專案憲章產生必要測試；先驗失敗再實作，不為每個薄函式另寫鏡像測試。
**Organization**: Setup → Foundation → US1(P1) → US2(P1) → US3(P2) → Cross-cutting。依 quickstart.md 的實際證據更新；39／42 完成，真實素材與整體結案仍待驗，核取方塊不代表規格品質審查結果。

## Format and paths

每項為 `- [ ] Tnnn [P?] [USn?] 說明及檔案路徑`。`[P]` 僅表示在所屬階段前置完成後，可處理不同檔案的工作；不是跳過前置或授權啟動代理。相同模組的實作依序進行，現有檔案只作必要修改。

## Phase 1: Setup

**Purpose**: 確認既有環境、資產範圍與隔離位置，不下載權重或建立日常文件索引。

- [X] T001 讀 `AGENTS.md`、`CONTRIBUTING.md`、`.specify/memory/constitution.md` 及本功能全部設計；核對 Python 3.12、產品 lock 與基線 gate，把環境、個人客製化範圍及既有結果記入 `specs/005-prepare-rag-assets/quickstart.md`；不代開上游 PR、不改 requirements checklist 標記。
- [X] T002 在 `specs/005-prepare-rag-assets/quickstart.md` 記錄隔離測試策略：所有合成素材放 `cache/005-prepare-rag-assets/`，沿用既有 rag／dev 環境與鎖檔；不讀日常 `.env`、私人 HF cache／憑證或啟動 App。真實下載須部署者提供信任的安全 revision 及明確測試範圍；未供應只阻擋真實素材驗收，不阻擋離線實作；Linux／macOS 不安排實測。
- [X] T003 在 `.gitignore` 補兩個預設目的地的狹窄 sibling stage／backup／lock 忽略規則，保留既有正式素材忽略項；於 `tests/test_document_assets.py` 驗證預設殘留被忽略，不新增會隱藏產品原始碼的廣泛規則。

## Phase 2: Foundational — 阻擋故事實作的共用邊界

**Purpose**: 先證明真實引擎可行性，再建共用來源驗證、CPU encoder、路徑與發布邊界。

- [X] T004 在 `tests/test_document_prepare_worker.py` 建立明確選用、只需真實鎖定 Chroma 及合成 normalized 1024 維向量的獨立程序探針，覆蓋 1／2／3／奇數／超過 API batch／最後餘一段；公開建集合／add／close 後新程序驗原包 hash、所有 row 邏輯／向量／count 與副本所有持久 HNSW hash；fixture 不使用 BGE 或文件，不寫日常路徑。
- [X] T005 執行 T004，在 `specs/005-prepare-rag-assets/quickstart.md` 留真實結果與可用公開操作順序；候選 `batch_size=2`、`sync_threshold=2`、`num_threads=2`、cosine，不能設 1。必要時實測一次相同真實 row 的公開 update 能否完成尾批；不得假段落、刪 journal、私有 API／表或改 reader。任何合法小包無法封存就停止後續實作並回報，不把猜測或 skip 算通過。
- [X] T006 [P] 在 `tests/test_document_assets.py` 先寫 receipt／預設根／路徑／排他鎖／基本發布測試：不同 CWD 預設一致、wheel 無 checkout 要明確路徑、根目錄／重疊／祖先 link／junction／Windows 別名拒絕，既有 output 未授權不覆寫、發布前普通 rename 失敗保留或恢復舊版。先覆蓋 stage→destination 成功後清理失敗保留新版、exit 8 的基本行為，完整矩陣留 T030；測 schema 與額外語意規則，不靠私有 helper 名稱斷言。
- [X] T007 [P] 在 `tests/test_document_model.py` 及 `tests/test_document_worker.py` 寫模型共用抽取回歸：CPU／安全權重／local-only／無 remote code、模組與版本／hash／reference 不符拒絕、encoder 輸出與 reader 一致，且一般 App／light runtime import 不載入 torch／Chroma／ST。
- [X] T008 在 `src/reachy_mini_conversation_app/document_assets.py` 建 typed 模型要求／receipt／輸入驗證與路徑解析，並新增隨包 `src/reachy_mini_conversation_app/document_model_receipt.schema.json`，與 `contracts/model-receipt.schema.json` 相同。逐項落實「repo_id 固定 BAAI/bge-m3；revision 為 40 位小寫 hex，無預設」、「replace 為明確布林；預設 false」、resolved_revision 相等、schema_version=1、files 路徑唯一／size_bytes >=1／SHA-256 64 小寫 hex、UTF-8 無 BOM／重複 key／NaN／Infinity 且 <=16 MiB、未知欄位拒絕；payload 精確十檔為 config.json、config_sentence_transformers.json、modules.json、sentence_bert_config.json、1_Pooling/config.json、sentencepiece.bpe.model、special_tokens_map.json、tokenizer.json、tokenizer_config.json、model.safetensors。receipt inventory 排除自己，實際根只能 payload＋receipt，不接受額外檔案或連結；schema 只解析內嵌 $defs。
- [X] T009 將 `src/reachy_mini_conversation_app/document_worker.py` 的重複模型驗證／load／encode 抽至 `src/reachy_mini_conversation_app/document_model.py` 並重用，保留 CPU float32、dense 1024 維 finite／非零／L2 norm 誤差 <=1e-4、CLS／Normalize、threads 2／1、空前綴、8192 上限及 reference cosine 差距 <=1e-5；實際 ST／torch／transformers 完整版號含 local suffix 比對。在同一模型模組提供 worker 使用的 typed tokenizer adapter，回傳未截斷／不含特殊 tokens 的 offsets 及實際含特殊 tokens 的 count；不讓輕量 CLI 載入 tokenizer。頂層重型 imports 只在受控模組，不能放寬 004 合約或新增 Any／cast／ignore；跑 T007 與既有 worker 回歸。
- [X] T010 在 `src/reachy_mini_conversation_app/document_assets.py` 實作共用路徑與基本發布：checkout 標記辨識、明確相對參數按 CWD 解析；同父目錄排他 mkdir lock、stage／backup，「operation_id：隨機 UUID；kind=model／package；本次 owner PID 僅診斷，不能用來自動授權清理」，「destination_name、stage_name、backup_name：已核對父目錄內的 basename，不接受 `..`／絕對路徑／link」。落實「locked → preparing → validating → validated → backed_up（僅替換）→ published → cleaning」；stage→destination rename 成功即發布界線，之前普通失敗恢復 backup／舊 payload bytes 不變，之後清理失敗保留新版並回 exit 8，不自動回復或重跑。Windows 不保證目的地路徑全程存在；不以 os.replace 假定非空目錄原子替換，不按 PID／時間破鎖。預設根不落 site-packages／任意 CWD，自訂 repo 內未忽略輸出拒絕。
- [X] T011 在 `src/reachy_mini_conversation_app/document_prepare_worker.py` 與 `src/reachy_mini_conversation_app/document_assets.py` 建 typed 私有子程序邊界：request 僅模型驗證／producer／fresh verifier operation、已驗證 source／model／stage／副本路徑及 scalar metadata；result 僅固定狀態／錯誤碼、來源／檔案 digest、count、安全結果。IPC 禁止全文／chunks／向量（含 reference embedding）／model／tokenizer／pickle；worker 寫 candidate receipt／manifest／collection，父 CLI 只核對摘要／路徑並持鎖發布。全部 inference／tokenizer 僅在 worker，模型驗證與 fresh verifier 可各自載入，不開 socket／dotenv／SDK。啟動前專用 HF_HOME／cache、offline／telemetry off／SKIP_DOTENV，確認子程序退出才發布／清理。「status 為 completed／already_ready／failed／busy／recovery_required」、「published 為必填布林」、「ready（bool 或 null）」：completed 為 published=true／ready=true，already_ready 為 published=false／ready=true，發布前失敗／busy 為 published=false／ready=null；發布後清理不全 published=true／ready=true、status=recovery_required、code=cleanup_incomplete、exit=8，附自有殘留／人工指引，不能當 completed 或自動重跑。

**Checkpoint**: T005 必須有真實合成索引證據，T006～T011 通過相關離線回歸。Foundation 後才進入故事實作；缺使用者模型不應阻擋本階段。

## Phase 3: US1 — 下載一次即可離線使用指定模型 (P1 / MVP)

**Goal**: 一次手動下載供應正確模型，重跑同完整版本零網路，無索引也能獨立驗證。
**Independent Test**: fake Hub／encoder 走完整公開 CLI；真實安全 revision 明確 opt-in 後再做斷網 load／encode，不需文件、provider 或機器人。

### Tests

- [X] T012 [P] [US1] 在 `tests/test_download_document_model.py` 寫 CLI／Hub 合約測試：revision 必填且 40 小寫 hex、拒絕 main／tag／model／URL／endpoint，checkout／明確 output／replace 行為、中文輸出與 exit codes；固定公開 endpoint、token=False、精確十檔 allowlist、獨立 cache、先小配置後大檔，缺 safetensors／resolved SHA 不同即拒絕，無 PR fallback／bin 轉換／私人 cache／dotenv 讀取。
- [X] T013 [P] [US1] 在 `tests/test_document_prepare_worker.py` 補模型角色的離線檢查：載入前後檔案 hash 不變、必要檔缺失／safe weights／模組／runtime／reference 壞值拒絕、子程序不外連／不讀私密設定，權重釋放後才可發布。以程序與 IPC spy 確認只有 worker 載入模型／tokenizer、receipt／reference 向量寫 candidate 而非回傳父 CLI；例外內容 sentinel 不洩漏。

### Implementation

- [X] T014 [US1] 在 `src/reachy_mini_conversation_app/download_document_model.py` 實作真正的模組 CLI（不加薄 wrapper／console entry point），沿用 `contracts/preparation-cli.md` 參數；--help 不需 rag／模型。先路徑安全與模型鎖，再核對現有同版本 receipt／payload；已完整則 already_ready，零 metadata 查詢／下載／覆寫；不同或損壞目的地未 replace 即拒絕。
- [X] T015 [US1] 在 `src/reachy_mini_conversation_app/download_document_model.py` 實作匿名固定 revision metadata／小配置預檢及 payload 下載；尊重呼叫者明確的 offline 禁令，核對可取得的 LFS／Git 檔案識別及本機 hash。專用傳輸 cache 與乾淨 stage 分開，只複製十檔正常 bytes，不攜帶 .cache/huggingface／symlink／bin／pt／Python，不製造來源未提供的 2_Normalize 配置。
- [X] T016 [US1] 在 `src/reachy_mini_conversation_app/document_prepare_worker.py` 實作共享 encoder 的模型驗證，固定 reference「這份文件主要說明什麼？」及「1024 維 normalized finite embedding」；由該 worker 呼叫 `src/reachy_mini_conversation_app/document_assets.py` 寫 candidate model-receipt.json，reference 向量不經 IPC。payload 清單不含 receipt，自有 runtime 使用實際完整版本；模型驗證與前後 hash 核對後正常退出，不以欄位宣告替代真實檢查。
- [X] T017 [US1] 在 `src/reachy_mini_conversation_app/download_document_model.py` 串接完整下載→離線驗證→程序退出→共用發布與結果處理；依 CLI 合約處理 0／2／3／4／5／6／7／8／130 及固定錯誤碼，中文 CLI 可顯示指定路徑／revision，診斷不含 provider body／token／私密例外。不改 .env／App 設定或自行安裝依賴。
- [X] T018 [US1] 跑 T012～T017 的正常／重用／中斷／缺檔／寫入失敗回歸，於 `specs/005-prepare-rag-assets/quickstart.md` 記 fake 驗證與限制，確認不需要索引或 US2 即可單獨展示 US1；不得宣稱已下載真實安全模型。
- [X] T019 [US1] 在 `tests/test_download_document_model.py` 建立明確 opt-in 真實指定安全 revision 驗收並依授權執行：下載、離線載入、receipt 與模型完整性、同完整版本重跑零下載；於 `specs/005-prepare-rag-assets/quickstart.md` 記 revision／主機／runtime／digest／原始結果。未提供信任 revision 或下載範圍保持未完成，不自選未合併 PR；不阻擋其他故事的離線工作。

**Checkpoint**: T018 是離線 MVP，T019 才是實際模型證據；兩者分開，不以 fake 代替下載成功。

## Phase 4: US2 — 將唯一文字文件產成完整包 (P1)

**Goal**: 只用既有本機模型，取得可核對原文／定位、符合 004 的完整包。
**Independent Test**: 可用可信 receipt／受控 encoder fixture 單獨開發，不依賴下載網路；實際交付仍需明確提供的真實模型。

### Tests

- [X] T020 [P] [US2] 在 `tests/test_build_document_package.py` 寫輸入與 `specs/005-prepare-rag-assets/contracts/source-window-v1.md` golden 測試：唯一常規 txt／md／markdown case-insensitive、UTF-8／BOM、CRLF／LF／CR 保留，拒絕無有效字母／數字、目錄／glob／link／URL／多輸入及重複 --input；原始 bytes 含 BOM hash 不變，安全 identifier <=128、「title 為既有 160 code point 限制」、「max_distance 有限 [0,2]，必須明確提供」。用正式常數驗 ABCDEFGH→[0,4)／[3,7)／[6,8)、CRLF→[0,3)／[2,6)／[5,8)、600 字元零 offset→[0,510)／[510,600)；驗非單調 514→600→10 必須逐點後退。另驗映射筆數／範圍／單調性錯誤、n<=50、零寬 overlap、CRLF overlap 到 end、最短片仍超限、EOF 空白、超長單行、原文完整覆蓋與兩次原文／ID／順序／locator 一致；語法／連結／指令不執行，假 tokenizer 不當真實 BGE 證據。
- [X] T021 [P] [US2] 在 `tests/test_document_prepare_worker.py` 寫 producer／fresh verifier 合約測試：公開索引寫入只在 producer、embedding_function=None／cosine／單一 collection／來源；拒絕缺檔／journal／混合來源／hash／向量不符／replay 或 HNSW 改變，區分 SQLite 必要記帳與邏輯變更，不改 manifest 掩蓋。驗 producer 一次 bytes 讀取衍生 hash／text／chunks／vectors、初次讀取前後身分／stat 一致；來源修改／替換於 fresh verifier 最後串流檢查拒絕，不重 decode／tokenize。以 IPC／程序 spy 驗父 CLI 不讀全文切段／不載 inference、管道無內容或向量、worker 寫 candidate。測來源／模型及原包不變、所有 rows（非抽樣）及未知必要索引檔也受保護。

### Implementation

- [X] T022 [US2] 在 `src/reachy_mini_conversation_app/build_document_package.py` 實作模組 CLI 與輸入 metadata 驗證；預設 model／output 按 checkout，無 checkout 須兩者明確給出；相對明確參數按 CWD。先鎖模型再鎖包，任一 busy 釋放本次鎖退出；不 import config／main／core_tools、不讀日常設定，不自動抓模型或啟用 App。
- [X] T023 [US2] 在 `src/reachy_mini_conversation_app/build_document_package.py` 實作由 producer 呼叫的純切段函式及 TextSource／SourceChunk typed 邊界；只接受原字串與 typed tokenizer 介面，不 import inference 或建立 tokenizer。逐條實作 `specs/005-prepare-rag-assets/contracts/source-window-v1.md`：candidate_content_tokens=400、overlap_content_tokens=50、max_encoded_tokens=512、zero_offset_window_chars=512；剩餘 <=400 取 EOF，否則前 400 非零寬 offset 最大 end，無可前進 end 才用 512 字元 fallback。每片實際含特殊 tokens <=512、禁止截斷；逐個合法字元點後退，不假定 token 數單調，CRLF end 向左修正。重疊取 n−50 token 原文起點；零寬／n<=50／不前進／CRLF 向右修正後 >=end 則 next_start=end，不另造 fallback。落實「0 <= start < end <= len(text)」、「text：恰為 source.text[start:end]；不能從 token decode 重建」、ordinal 順序、全覆蓋／有限終止／EOF 不重複。ID 用確切 keys document_id／document_version／source_sha256／policy／start／end，sort_keys=true、ensure_ascii=false、separators=(',', ':') 的 UTF-8 JSON SHA-256，`c-`＋64 小寫 hex；locator 為「`L<first>-L<last>; chars[<start>,<end>)`；行號 1-based inclusive，字元範圍 0-based end-exclusive」，換行歸其結束的行，CRLF 合算一行，不解析章節／生成頁碼。
- [X] T024 [US2] 在 `src/reachy_mini_conversation_app/document_prepare_worker.py` 實作 producer：唯一負責初次來源 bytes 讀取、身分／stat、同緩衝區 raw hash／UTF-8-sig decode／切段／locator／文件向量，呼叫 T023 純函式與 worker 內 tokenizer adapter；不正規化 Unicode／行尾。使用 T005 已證明的公開 Chroma 操作及共用模型；row「id=chunk_id、documents=text、metadatas 僅 document_id／document_version／locator」，禁止假段落或其他文件。public close／程序退出後才取 inventory，原文／模型不改動；只回摘要，全文／vectors 不經 IPC。
- [X] T025 [US2] 由 `src/reachy_mini_conversation_app/document_prepare_worker.py` 呼叫 `src/reachy_mini_conversation_app/document_assets.py` 在 candidate 生成既有 004 v1 manifest：單文件／版本／集合、實際完整 engine／embedding runtime、source hash、完整 chroma files、model payload＋receipt 的 embedding.files／hash、非敏感 reference 及使用者門檻；receipt／manifest／collection（含 reference 向量）不透過 IPC 傳回父 CLI。重新枚舉 embedding.files，不直接採 receipt.files、不加未知欄位／自我 hash，不改 `src/reachy_mini_conversation_app/document_manifest.schema.json`。policy 只入準備操作記錄，不入 004 manifest。
- [X] T026 [US2] 在 `src/reachy_mini_conversation_app/document_prepare_worker.py` 實作獨立 fresh verifier：在完整副本以 migrations=validate／現有 DocumentIndex 全量開啟、query、public close／退出後驗所有 row documents／metadata／embedding／count、原包全 hash 及副本所有持久索引 hash；原檔 journal 或任何重建／replay 差異拒絕。最後串流重算來源 hash、比對 initial_identity／initial_stat，修改／替換拒絕發布，不再次 decode／tokenize，不宣稱阻止外部寫入。candidate 暫列本機 target／snapshot_complete 不等於發布；只發布相同已驗證 bytes，target 取本機 runtime_target，不能複製其他主機；父 CLI 確認 verifier 退出／摘要成功後才發布。
- [X] T027 [US2] 在 `src/reachy_mini_conversation_app/build_document_package.py` 串接 metadata／receipt 核對、獨立 producer／verifier 與共用發布；父 CLI 只協調路徑／scalar metadata／安全摘要，不讀全文切段、不載模型或 tokenizer，也不接收 chunks／vectors。全程 offline／專用 cache／telemetry off，父程序持鎖、子程序不能搬正式輸出；缺素材明確失敗，依 CLI 合約顯示中文結果、published／ready／exit codes，不校準或換模型，只顯示設定建議、不改 .env。
- [X] T028 [US2] 在 `tests/test_build_document_package.py`、`tests/test_document_prepare_worker.py` 執行至少五份合成文件（中文、英文、否定、表格、程式碼／連結）及兩次重現、來源 sentinel／zero-network 回歸，於 `specs/005-prepare-rag-assets/quickstart.md` 記 SC-002／SC-004／SC-006 證據；區分 fake encoder 與真實 Chroma，不宣稱模型／語意品質已通過。
- [ ] T029 [US2] 在 `tests/test_build_document_package.py` 建 opt-in 的真實本機安全模型＋五份固定無敏感文件產包／既有 reader 驗收，確認完整素材、原文／位置／不變性及零外連，於 `specs/005-prepare-rag-assets/quickstart.md` 記來源／receipt／包 digest、主機及原始結果。可用已驗證外部同等模型，不強制先做 T019 網路下載；缺素材保持未完成，不降低 004 驗證。

**Checkpoint**: T028 完成離線故事；T029 完成實際產包證據。US2 可用已準備模型單獨執行，不需要 US1 在線運作。

## Phase 5: US3 — 安全發布素材並交接給 App (P2)

**Goal**: 驗證完整跨腳本生命週期，已完成／未完成狀態清楚，發布前失敗保留舊版，發布後清理失敗保留新版並明確回報。
**Independent Test**: 使用受控子程序與自有 fixture 目錄測替換／中斷／鎖；不必下載權重或啟動 App。

### Tests

- [X] T030 [P] [US3] 在 `tests/test_document_assets.py` 增加分界故障矩陣：preparing／validating／validated／backed_up 前普通失敗恢復舊 payload bytes 與目的地；stage→destination 成功後，在 backup／stage／lock／operation record 清理或階段記錄注入失敗，必須保留新版、顯示「已發布，清理未完成」、status=recovery_required、code=cleanup_incomplete、published=true、ready=true、exit 8，且沒有 rollback／下載／產包／自動重試。分別測 hard interruption、記錄仍停舊 phase、發布前取消 exit 130／恢復失敗 exit 8 published=false、發布後取消清理 exit 8 published=true。驗 UUID、kind=model／package、basename 範圍、不依 PID／時間破鎖，原文件全部情境零修改；不要求 Windows 目的地 namespace 全程不變。
- [X] T031 [P] [US3] 在 `tests/test_download_document_model.py` 與 `tests/test_build_document_package.py` 增加真正跨程序 CLI 測試：不同 CWD／wheel explicit paths、同目的地競爭、模型發布對 builder 的鎖順序、輸出含既有路徑設定值而不寫 `.env`／一般設定／憑證；以 safe sentinel 檢查 stdout／診斷不含原文／向量／token／provider body，正常操作僅兩次手動啟動。

### Implementation

- [X] T032 [US3] 在 `src/reachy_mini_conversation_app/document_assets.py` 完成 T030 的發布／恢復／清理矩陣：old→backup、validated stage→destination 成功即發布，第二步前普通失敗復原舊版，恢復失敗留 recovery_required／published=false／exit 8。發布後階段記錄或清理失敗仍保留新版，status=recovery_required／code=cleanup_incomplete／published=true／ready=true／exit 8，禁止自動回復、下載、產包或重試。只清本次記錄與已核對父目錄內自有資料，保留精確殘留／hash 及人工指引；硬中斷時核對實際目錄而非僅信 phase，不加自動 recovery、不先刪舊版／盲刪 lock。
- [X] T033 [US3] 在 `src/reachy_mini_conversation_app/download_document_model.py`、`src/reachy_mini_conversation_app/build_document_package.py` 及 `src/reachy_mini_conversation_app/document_prepare_worker.py` 完成中斷傳遞／退出確認：未確認子程序釋放資源就保留狀態、不刪檔／發布；發布前 cancelled 且可安全恢復回 130，無法恢復回 8／published=false；發布後取消清理回 8／published=true／ready=true，保留新版與人工清理資訊，不假裝未發布或自動重試。不記原始 traceback／私密內容。
- [X] T034 [US3] 執行 `tests/test_document_assets.py`、`tests/test_download_document_model.py`、`tests/test_build_document_package.py` 的競爭／危險路徑／分界故障矩陣：至少八類 SC-003 發布前可處理失敗，原檔與既有 payload bytes 變更為零；另測發布後清理失敗保留新版、exit 8、不自動回復／重跑，不把「舊版零變更」誤套到已發布新版。所有情境來源文件零修改；Windows 自有檔案鎖／rename 失敗不停止其他程序，不操作日常 App。
- [X] T035 [US3] 在 `specs/005-prepare-rag-assets/quickstart.md` 留 US3 獨立驗證結果與人工恢復步驟、中文 exit 對照及未驗證限制；確認沒有 App 行程控制、runtime indexing、相機／記憶或供應商設定變更，不將 005 結果當成 004 整體結案。

## Phase 6: Polish & Cross-Cutting Validation

**Purpose**: 文件、包裝、實際證據與必要 gate；未完成素材驗收如實保留。

- [X] T036 [P] 更新根 `README.md` 的兩個實際模組命令、rag 前置、信任且含 safetensors 的固定 revision／main 不支援、已校準門檻、預設／明確路徑、固定切段／定位行為、替換前停止 App、恢復與錯誤碼。清楚區分發布前失敗／發布後保留新版但待清理 exit 8，後者不得自動重跑；不新增 README／docs Markdown，不自動改 `.env`。
- [X] T037 [P] 依兩支離線準備腳本的資料流更新 `docs/scheme.mmd` 並用既有 Mermaid 工具重新生成 `docs/assets/conversation_app_arch.svg`，視覺檢查下載／本機產包／既有 reader 的邊界；不手改 SVG、不改 CI。
- [X] T038 在 `tests/test_profile_paths.py` 的既有 wheel 驗證補兩 CLI 模組／worker／共用模型及 receipt schema 打包，核對 `src/reachy_mini_conversation_app/document_model_receipt.schema.json` 與本功能 schema 相同、安裝後不依 source specs／遠端 $ref、普通安裝與 --help 無 optional stack／dotenv／機器人初始化；無 checkout 時要求明確路徑、不寫 site-packages。
- [ ] T039 依 T019／T029 可取得的真實安全模型與 Windows 檔案操作證據，在 `specs/005-prepare-rag-assets/quickstart.md` 記完整兩步流程、至少五份文件、讀取／query／close 後不變性、已就緒重用、offline／並行／替換／中斷恢復結果及來源／模型／包 digest；未提供信任 revision 或實際素材，保留未完成。Linux／macOS 只列未測，不把 fake 或其他功能授權代替實際驗收。
- [X] T040 在 `specs/005-prepare-rag-assets/quickstart.md` 整理每項 FR／SC 的已取得證據、未完成／失敗／平台限制與實際命令，將「尚未實作」設計指引更新成實際行為但不虛構 pass；保留首次失敗，004 的實際 CPU／雙後端／現場驗收仍由原任務獨立處理。
- [X] T041 自審相關 `src/reachy_mini_conversation_app/`、`tests/`、`README.md`、`.gitignore` 與架構 diff，依 AGENTS 跑完整 Ruff check／format、strict mypy、`pytest tests/ -v`、`uv lock --check`，於 `specs/005-prepare-rag-assets/quickstart.md` 留結果；檢查 typed 公開 API／頂層 imports／SDK 公開 API／無新 ignore／未變 CI／沒有新依賴，尤其確認 004 模型抽取回歸。真實 Chroma 探針不可用缺 extra skip 冒充通過。
- [ ] T042 在 `specs/005-prepare-rag-assets/tasks.md` 與 `specs/005-prepare-rag-assets/quickstart.md` 逐項結案：只勾實際完成證據充分的任務；T019／T029／T039 或可行性 gate 未完成就保留整體未結案。不得修改 requirements checklist 來表示實作完成、不自動勾 004 待辦、不代開 PR。

## Dependencies & Execution Order

### Phase graph

```text
T001 → T002 → T003
  → T004 → T005（真實 Chroma 可行性，失敗即停止）
  → T006 / T007 → T008 → T009 → T010 → T011
  → US1: T012 / T013 → T014 → T015 → T016 → T017 → T018 → T019(opt-in)
  → US2: T020 / T021 → T022 → T023 → T024 → T025 → T026 → T027 → T028 → T029(opt-in)
  → US3: T030 / T031 → T032 → T033 → T034 → T035
  → T036 / T037 → T038 → T039 → T040 → T041 → T042
```

### Required ordering and exceptions

- T004／T005 是實作第一道 gate，不需要 BGE；新引擎探針不得改產品 lock 或 reader 來過關。T005 通過才開共用／故事實作，並在 T024 重用已證明的操作，不重新猜測 flush。
- T006／T007 皆依 T005，可在不同測試檔並行；共用模型與 worker 抽取、document_assets 的 schema／路徑／發布依序修改。
- 所有故事依 Foundation。建議按 US1→US2→US3 逐階段驗證；US2 若有可信外部同等模型，可在 Foundation 後獨立開發／測試，不依賴 US1 網路。因共享 worker／assets，不能兩故事同時修改這些檔案。
- T019 沒有核准 revision，仍可做 T020～T038 的離線實作；T029 缺真實模型，也可做不依賴素材的 US3／文件／wheel／gate。但這兩項保持未完成，不宣稱真實故事驗收通過。T039 需要完整 T019＋T029，才能驗證下載與產包的真實兩步交接。
- T030／T031 依兩 CLI 離線整合 T018／T028，不依真實模型；hard-crash 狀態與 ordinary rollback 的基礎行為不得拖到此時才開始保護舊資料，T010 已需具基本保護。
- T036／T037 依介面穩定 T035，僅不同文件可並行；T038 需要前面程式完成。T040／T041 遇真實素材缺項時仍可記錄部分結果、執行可做的 gate，不可跳過有新回歸的必要檢查。T042 只能記錄部分交付，不能在缺項時勾整體完成。
- T020 的假 tokenizer golden fixtures 先於 T023；T021 先於 T024～T027，來源最後核對與 IPC 邊界不可留待結案補上。T006／T010 已含發布界線基本保護，T030～T034 再擴充矩陣；不得到 US3 才修正已發布後 rollback。每個故事的測試先於對應實作。新 regression 先跑相關測試再必要 gate；沒有新改動或疑慮時不重複同一全套測試。測試啟動／素材處理須符合 T002 範圍。

### Parallel examples per story

| 階段 | 前置 | 可並行的不同檔案 | 後續接點 |
|---|---|---|---|
| Foundation | T005 | T006 assets 測試／T007 model＋reader 測試 | T008～T011 依序 |
| US1 | Foundation | T012 download CLI 測試／T013 worker 模型測試 | T014～T018 |
| US2 | Foundation，建議 T018 | T020 builder 輸入／切段測試／T021 worker 產包測試 | T022～T028 |
| US3 | T018、T028 | T030 assets 中斷測試／T031 兩 CLI 整合測試 | T032～T035 |
| Polish | T035 | T036 README／T037 Mermaid＋SVG | T038 之後 |

## Requirement and Evidence Coverage

| 規格 | 對應任務 |
|---|---|
| FR-001 手動兩入口／不動 App | T011、T014、T022、T031、T035、T038 |
| FR-002 固定安全 revision／匿名下載 | T002、T012、T015、T019 |
| FR-003 完整安全模型／receipt／已就緒 | T007～T009、T013、T016～T019 |
| FR-004 路徑／不寫設定 | T006、T010、T014、T022、T031、T038 |
| FR-005 單文件／UTF-8／不展開 | T020、T022、T023、T028 |
| FR-006 識別資訊／門檻／來源 hash | T020、T022、T023、T025、T028 |
| FR-007 原文切段／可重現定位 | T020、T023、T028、T029 |
| FR-008 本機編碼／零外連 | T009、T011、T016、T021、T024、T027～T029 |
| FR-009 既有 v1／完整包 | T008、T021、T025～T029、T038 |
| FR-010 真實封存／不變性／平台 | T004、T005、T021、T024～T026、T029、T039 |
| FR-011 替換／中斷／舊版保護 | T006、T010、T017、T027、T030～T035 |
| FR-012 危險路徑／不控 App | T006、T010、T020、T022、T031～T035 |
| FR-013 中文／固定碼／日誌 | T011～T018、T022、T027、T028、T031、T033 |
| FR-014 README／既有依賴與設定 | T001～T003、T035～T038、T041 |
| SC-001 兩步完整素材 | T019、T029、T031、T039 |
| SC-002 五份原文／定位核對 | T020、T023、T028、T029、T039 |
| SC-003 發布前八類保護／發布後待清理／來源不變 | T006、T012、T013、T020、T021、T030～T034、T039 |
| SC-004 零外連／零重下載 | T012、T015～T019、T027～T029、T039 |
| SC-005 真實 reader／索引不變 | T004、T005、T021、T026、T029、T039 |
| SC-006 兩次重現／日誌零洩漏 | T020、T023、T028、T029、T031、T039 |

## Implementation Strategy

1. 先確認 T005 真實引擎可行性，避免寫完才發現小文件無法滿足 004。probe 只用合成向量，不自行取模型／日常文件。
2. **MVP 為 US1**：共用基礎＋T012～T018 的下載／驗證／安全發布。fake 展示與 T019 真實模型驗收分開，不能把 fake 稱為可交付模型。
3. 加入 US2，使用既有模型獨立測試；原文與來源優先，不靠清理文字、放寬距離或換模型改善表面結果。US3 再完成跨腳本中斷／交接矩陣，不延後基本保護。
4. 最後文件／wheel／gate 與真實範圍逐項留證。安全 revision 未供應、真實包／模型或 Windows 驗收未完成就保持未結案；Linux／macOS 不要求重啟測試，不自動外送段落或控制機器人。

## Task Summary

共 42 項：Setup 3、Foundation 8、US1 8、US2 10、US3 6、Cross-cutting 7。已同步發布前／後失敗界線、published／ready／取消結果、worker／IPC 歸屬、來源最後核對與固定切段 golden fixtures。10 項 `[P]` 僅涵蓋不同檔案工作群。所有任務含連續 ID、checkbox 與具體路徑；只有故事階段標記 `[USn]`。本輪離線實作與 gate 已通過，證據見 quickstart.md；T029／T039／T042 保持未完成，T019 真實安全模型下載已補驗通過；不宣稱真實 BGE-M3 文件產包或整體結案。

## 實作進度（2026-11-06）

首次離線交付為 38／42；以下保留舊 revision 的狀態，現行 T019 見文末補驗。T019 的測試入口已建立，但使用者指定的 `5617a9f61b028005a4858fdac845db406aefb181` 缺 `model.safetensors`，公開 metadata 與實際 CLI 均確認在權重下載前拒絕；未轉換 bin 或另選 revision。T029 的實際驗收入口亦已建立，但沒有合規本機模型，使用者確認尚未校準門檻；`example.md` 只確認 UTF-8／摘要，沒有產包。T039 因此未完成，T042 保留整體未結案。

requirements.md 維持原有 16／16；004 任務未更動；未啟動 App、雲端對話、相機、記憶或機器人。完整 gate 939 passed／19 skipped，另行明確執行的真實 Chroma 合成向量與假 encoder 產包結果不能當成真實 BGE-M3 證據。

### T019 真實模型補驗（2026-11-06）

使用者另提供並信任 `50f9396f75618b3389c1fd1068a1ff58dc7b5b26`，公開預檢十檔齊全。首次 Xet 原生傳輸於 Windows 存取違例；保留原始紀錄。以當次行程 `HF_HUB_DISABLE_XET=1`、同一 revision 及一般匿名 HTTP 重新驗收，1 passed／1 個 pytest cache 權限警告；完整下載、離線 CPU 載入／reference／前後完整性與同版本零網路重用均通過，T019 已勾選。沒有變更版本／依賴或放寬安全格式。模型位置與 receipt 摘要見 quickstart.md。

目前僅 T029／T039／T042 未完成；合規模型已備妥，使用者仍回覆門檻尚未準備，因此未產生 example.md 索引、未進行真實五份文件產包或整體結案。

````
