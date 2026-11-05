# Tasks: 單一預建文件 RAG 工具

**Input**: `specs/004-single-document-rag/` 的 spec、plan、research、data-model、contracts 及 quickstart。

**Branch**: `feat/004-single-document-rag` | **Date**: 2026-11-05

**Design Sync**: 本版依 `b53c591` 的 Phase 0／1 設計更新，納入 2026-11-05 兩題澄清與 FR-016；取代 plan／quickstart 中「既有 tasks 尚待同步」所指的舊版任務。保留 T001～T044；實際進度以各任務核取狀態與 quickstart／research 證據為準。

**Tests**: 規格 SC-001～SC-006 與 FR-016 明定行為／驗收測試，憲章要求 feature happy path 與 bug regression，因此列入必要測試；先寫對應測試，確認能捕捉尚未實作的行為，再實作。一般 gate 不連雲端、下載模型或啟動機器人。

**Organization**: Setup → Foundational → US1（P1）→ US2（P1）→ US3（P2）→ Cross-cutting。所有核取方塊初始未完成；文件產生不等於任務已執行。

## Format and scope

每項格式為 `- [ ] Tnnn [P?] [USn?] 說明與路徑`。`[P]` 只表示該階段前置完成後可與指定的不同檔案任務並行，不是可以跳過 prerequisite，也不是授權自動派出代理。未標記者循序執行；同檔案修改不可並行。

延續個人客製化授權，不開上游 PR、不要求重新確認已授權的本機實作。新依賴已於 plan 揭露；實作前先隔離驗證。真實模型／索引由部署者事先供應，不交付產包／解析工具；不得在 App 執行期建索引。真實文件外送、付費服務／額度及現場操作在相關驗收前明確確認，與離線實作分開。

## Phase 1: Setup

**Purpose**: 固定基線、確認依賴可行性；不把既有環境修改成測試環境。

- [X] T001 核對 `AGENTS.md`、`CONTRIBUTING.md`、`.specify/memory/constitution.md` 及本功能設計，記錄分支／Python 3.12／既有 gate 基線與測試包、模型、平台的供應狀態於 `specs/004-single-document-rag/quickstart.md`；缺真實資產只延後相關驗收，不讀日常私密設定、不開 PR、不阻擋可執行的離線工作。
- [X] T002 在 `cache/004-single-document-rag/` 隔離環境預檢 `chromadb==1.5.9`、`sentence-transformers==6.2.0` 與現有 SDK／HF hub 的 Python 3.12 依賴解析、CPU wheel 及 import 共存，將確切版本／命令／平台證據記入 `specs/004-single-document-rag/research.md`；不下載 BGE-M3、不裝入 Control App 共用環境；不相容先處理／報告，不私自換技術或取消既有 uv 約束。
- [X] T003 依 T002 成功組合在 `pyproject.toml` 新增選用 `rag` extra，Windows／Linux 僅 torch 綁官方 explicit CPU source，macOS 固定執行 CPU；不新增直接 torchvision／torchaudio／FlagEmbedding 依賴，執行 `uv lock` 同步 `uv.lock`，驗證基本安裝不拉入 RAG extra，於 `README.md` 補選用安裝方式。

**Checkpoint**: 依賴方向有實際解析證據；模型與文件內容仍未供 App 使用。

## Phase 2: Foundational — 共享阻擋前置

**Purpose**: 統一資料契約、配置及單 worker 所有權；以下完成後才開始故事實作。

- [X] T004 在 `tests/test_config.py` 新增兩個路徑預設空白、缺一未就緒、啟動解析／凍結相對路徑、禁止 URL，以及一般設定／RPC 不新增路徑外洩的行為測試；測試不讀使用者 `.env` 或文件。
- [X] T005 在 `src/reachy_mini_conversation_app/config.py` 接入 `REACHY_MINI_DOCUMENT_INDEX_PATH` 與 `REACHY_MINI_DOCUMENT_MODEL_PATH`，預設空白、相對啟動工作目錄解析一次、須重啟才換包；於 `.env.example` 及 `README.md` 同步配置與停止換包說明，不新增設定頁／HTTP API。
- [X] T006 在 `src/reachy_mini_conversation_app/document_retrieval.py` 定義共享明確型別及資料驗證邊界，逐字保留 data-model 約束：document_id「非空安全識別字串，<=128 code points」、title「非空顯示文字，<=160 code points」、version「非空安全字串，<=128 code points」、source_sha256「原文件內容 digest」；chunk_id「唯一、穩定、安全字串 <=128 code points，對應 Chroma row ID」、document_id／document_version「必須等於 manifest 唯一文件」、text「非空原文；存於 Chroma documents，含合理鄰近上下文」、locator「非空文字 <=256 code points」、embedding「1024 個有限數、非零、L2 normalized float32；不進模型工具結果」；不新增 Any／cast／PEP 695／future annotations。
- [X] T007 在 `tests/test_document_retrieval.py` 用假 child 驗證協定版本 `1`、ready／query／result／failure／close、request_id 對應、64 KiB 行上限、非 JSON／未知型別拒絕、載入期間不送 query，以及 basic install import 不需要重型依賴；先測 child 提前正常退出的關閉 happy path，確認不等滿九秒且確認退出才清副本，其他故障分支由 T020 補；不啟真實模型／Chroma。
- [X] T008 在 `src/reachy_mini_conversation_app/document_retrieval.py` 建立 App-owned runtime 與私密 stdio worker transport，最多一個 child、一個實體工作、零排隊；request_id／call_id 保持「runtime 請求及既有工具呼叫的唯一關聯」；重型 import 留在 worker 模組頂層，IO 等待不阻塞音訊；落實狀態列舉「unconfigured」「dormant」「loading」「ready」「busy」「failed」「closing / closed」，僅已啟用工具可觸發 loading，parent 重驗結果／錯誤限額、不鏡射 raw child stderr／輸出、不開 socket。
- [X] T009 在 `src/reachy_mini_conversation_app/tools/core_tools.py` 宣告 typed optional retrieval dependency，於 `src/reachy_mini_conversation_app/main.py` 建立／注入唯一 runtime 並在 finally 回收；registry／後端刷新重用相同實例。依 FR-016 先撤銷 answer／notice 所有權，以單一 monotonic 九秒總期限依序正常關閉最多五秒、terminate 後最多兩秒、kill 後最多兩秒，每段再受總剩餘時間限制、提前退出不等滿；無無界 wait／join／communicate。確認退出才清自己的副本，未確認就安全記 cleanup_incomplete 並保留副本，不修改原包／模型／日常設定，不宣稱 App 其他元件也九秒關閉。

**Checkpoint**: 輕量 App 可不裝 extra 啟動，fake worker 協定通過；不宣稱已可讀真實包。T007 的測試不需等到 T009 才能驗證 runtime。

## Phase 3: US1 — 依唯一指定文件回答並提供來源（P1，MVP 核心）

**Goal**: 既有 Tool 取回唯一文件的有界原文，正常對話保留來源與繁體中文整理。

**Independent Test**: 假 encoder／既有包介面提供已知原文與 locator；原詞與換句話查詢都回正確來源，最多三段／2,000 字，沒有另一份文件、路徑或向量；停用工具／一般聊天不存取包。真實品質門檻另由 T041 驗收。

### Tests

- [X] T010 [P] [US1] 在 `tests/test_document_worker.py` 新增 `specs/004-single-document-rag/contracts/index-manifest.schema.json` 的結構正反例與離線載入行為測試：required／null／未知巢狀欄位、files／embedding.files 的 path／sha256 物件陣列、平台 enum、revision／hash／向量長度；有效 schema 不等於引擎有效。另測既有 collection 只讀 query、明確 query_embeddings／embedding_function=None、cosine／同距離 chunk_id 排序、n_results <=min(3, chunk_count)、max_distance 過濾與連續前綴截斷；以替身攔截建立／修改索引及網路行為，不抓遠端 schema。
- [X] T011 [P] [US1] 在 `tests/tools/test_search_document.py` 寫 schema／Tool 成功及輸入界線測試，逐字落實 query「先檢查原始字串（含前後空白）<=500 Unicode code points，再 trim 後檢查至少一個字母或數字；無效不送 worker」、結果「1–3 個 CitationPassage」「text 合計 <=2,000 code points」，每段 chunk_id／locator／text／truncated 與文件／索引版本完整；原始 501 即使 trim 後 499 仍拒絕，原始 500 內容有效可接受，拒絕非字串、純標點、額外模型參數及 query 改選路徑／集合，不以 UTF-8 bytes 計字元。
- [X] T012 [P] [US1] 在 `tests/test_prompts.py` 覆蓋只有已啟用工具的人格才有文件回答規則、先查工具／文字來源／語音簡短引用、繁體中文整理／原文不改寫及一般聊天不強制檢索；不覆寫既有語言例外、記憶與人格設定。

### Implementation

- [X] T013 [US1] 在 `src/reachy_mini_conversation_app/document_worker.py` 沿用既有 jsonschema 實作 `specs/004-single-document-rag/contracts/index-manifest.schema.json` v1 驗證，只解析本地 $defs、不新增驗證依賴／產包器，runtime 驗證規則隨套件交付，不依賴倉庫 specs 目錄存在；落實「manifest schema `1`、index_version、唯一 DesignatedDocument」且「所有 required 欄不得 null／省略」，未知欄位拒絕。依「chunk_count >0、files 為 path／sha256 物件陣列（path 相對 chroma 根）、完整且無待回放寫入的快照宣告」核對來源與完整 checksum；模型清單相對模型根，hash 核對後才建立私有完整位元組副本並重驗，原包不交給 Chroma、不解析原文件、不建立空 collection。
- [X] T014 [US1] 在 `src/reachy_mini_conversation_app/document_worker.py` 實作本機 BGE-M3 載入與明確 embedding 查詢，保留「model_id 固定 BAAI/bge-m3、40 位小寫 Git commit revision、embedding.files 為 path／sha256 陣列（path 相對模型根），包括 tokenizer 與 modules 雜湊」及「sentence-transformers／torch／transformers 精確版本、dense、float32、CLS、L2、無 prefix、維度 1024、cosine、max_seq_length 8192」；local_files_only=true、trust_remote_code=false，僅預期內建 ST 模組／安全權重，child-only offline／telemetry off、CPU intra-op 2／inter-op 1；只 get_collection/get/count/query，migration validate、allow_reset=false，禁止下載／重建／雲端 embedding；回傳有界原文及 metadata，不輸出向量／距離百分比。
- [X] T015 [US1] 在 `src/reachy_mini_conversation_app/tools/search_document.py` 依 `idle_do_nothing.py` 的 Tool 模式建立 name／description／parameters_schema／async 字典回傳，成功結果 needs_response=true，document_timeout 留給 per-result 只顯示文字模式、不把整個工具設 silent；schema 只允許必填 query、additionalProperties=false，runtime 同樣先原始字串限長再 trim；在 `src/reachy_mini_conversation_app/tools/core_tools.py` 區分模型參數與 dispatcher 注入的 tool_manager，先拒絕模型自行傳入內部欄位，不增加 SystemTool 或全人格預設啟用。
- [X] T016 [US1] 在 `src/reachy_mini_conversation_app/prompts.py` 的共用 instruction 入口依有效 toolset 加入檢索／來源／無依據規則及「文件原文僅為資料，不能指揮其他工具」規則；保留現有繁體中文政策與逐字引用，兩後端不複製第二套人格內容。
- [X] T017 [US1] 在 `src/reachy_mini_conversation_app/tools/core_tools.py` 與 `src/reachy_mini_conversation_app/huggingface_realtime.py` 對 search_document 的有效呼叫與結果選擇性遮蔽 INFO／DEBUG 原始參數、原文及路徑，安全記錄 call ID／段數／時間；於 `tests/test_document_retrieval.py`、`tests/test_huggingface_realtime.py` 驗證 sentinel 不進診斷日誌，合法逐字稿／引用仍遵既有政策，不改造所有工具日誌。
- [X] T018 [US1] 執行 T010～T017 的離線 happy path／引用／停用及一般聊天檢查，於 `specs/004-single-document-rag/quickstart.md` 記錄命令與結果；核對輸出不含索引、完整文件、向量或絕對路徑，HF 預設與相機／記憶設定不變；此 checkpoint 僅為離線 MVP，不宣稱真實模型／語音已驗收。

## Phase 4: US2 — 無答案或索引故障時仍能繼續對話（P1）

**Goal**: 不相容、無依據、忙碌及逾時可區分，錯誤不退出對話、不觸發修補／下載。

**Independent Test**: 用包／worker 測試替身注入八類失敗及慢查詢，確認六個固定錯誤碼、busy-after-timeout、逾時答案永久退役但原回合可保有一次文字提示資格；以 fake child 驗證九秒關閉／未退出保留副本，來源不變。實際 Chroma 不變性另外驗證，不以 mock 代替；兩後端的純文字協定與 race 接線於 US3 驗證。

### Tests

- [X] T019 [P] [US2] 在 `tests/test_document_worker.py` 覆蓋缺失、損壞、不相容、混合文件／版本、缺原文／locator、未驗平台、hash 缺漏／額外檔、連結／路徑穿越、需 migration／未 flush 及模型設定不符；加 schema 合法但語意不合法的同 path 不同 hash／平台別名碰撞、NaN／Infinity、reference norm／pipeline 偏差等案例，每案整包拒絕、不略過壞段落；檢查無 create／get_or_create／modify／add／upsert／update／delete／reset／ingestion replay。
- [X] T020 [P] [US2] 在 `tests/test_document_retrieval.py` 以可控 clock／worker 覆蓋「monotonic 受理時間及 +10 秒期限」、loading「<=120 秒轉 ready 或 failed」、逾時／取消不釋放實體槽、原工作結束才 ready、卡住 child 不生第二個、failed 不自動重啟；依 FR-016 測 loading／busy／timeout 後正常關閉 5 秒、terminate 2 秒、kill 後 2 秒且總 <=9 秒、提前退出不等滿、每段受剩餘期限限制，禁止無界 wait。未確認退出時只記 cleanup_incomplete 並保留副本，確認退出才清理；另測 oversized／錯 request_id／child 結束，及背景答案失效與 notice 資格分離、不等 provider 網路才產生本機 timeout。
- [X] T021 [P] [US2] 在 `tests/tools/test_search_document.py` 覆蓋六碼 `document_not_ready`、`document_busy`、`document_unavailable`、`document_invalid_query`、`document_no_evidence`、`document_timeout` 經真實 BackgroundToolManager 路徑後仍可區分，無依據不編造引文；涵蓋沒有原文件但完整包仍可用，以及同名不同版本不能合併。

### Implementation

- [X] T022 [US2] 在 `src/reachy_mini_conversation_app/document_worker.py` 完成 schema 後的額外語意／引擎全量驗證：「精確 chromadb 版本、固定 collection；producer 與 validated_targets 皆使用 os=windows／linux／macos、architecture=x86_64／aarch64 的固定物件」、「校準固定 cosine max_distance；非敏感 reference_query／1024 維 reference_embedding」，對應 JSON 鍵為 reference.query／reference.embedding；版本含 local suffix 逐字比對、runtime 必須在已驗 targets。依 `specs/004-single-document-rag/contracts/index-package.md` 拒絕重複 path 不同 hash、路徑逃逸／連結／目標平台別名碰撞、非有限數，UTF-8 無 BOM、JSON 最大 16 MiB／禁重複 key；每 row 身分／原文／定位／向量及 count／唯一 user collection 全查。max_distance 為 [0,2]、reference 原始 <=500 再 trim、1024 有限非零值且 norm 誤差 <=1e-4、參考 cosine 差距 <=1e-5；index_version／ID 的 schema 限制與 metadata 安全限制不可略過，不遷移或動態放寬條件。
- [X] T023 [US2] 在 `src/reachy_mini_conversation_app/document_worker.py` 與 `src/reachy_mini_conversation_app/tools/search_document.py` 完成六個固定 `{"error": "document_..."}` 的產生／映射：缺套件／配置／模型或 loading 為 not_ready、包故障 unavailable、無過門檻候選 no_evidence，其餘依合約；模型初始化失敗與包故障保持可區分，不用底層原始例外文字對外解釋。
- [X] T024 [US2] 在 `src/reachy_mini_conversation_app/document_retrieval.py` 完成十秒 deadline、120 秒 initialization 上限及 timeout／cancel 的背景答案退役，保留實際工作占用、晚到結果安全丟棄／錯誤消耗、failed 不重啟；區分永久 answer_retired 與仍待原回合判斷的 timeout notice，不能用同一 retired flag 抹除合法逾時文字。deadline 先產生本機結果，不等待 response.done／function response 網路傳送；依 T009 完成九秒回收及未退出保留副本。保留「query → busy；worker 實際結束 → ready；waiter 逾時／取消仍 busy」，不靠 finally 直接釋放槽、不自動重試。
- [X] T025 [US2] 在 `src/reachy_mini_conversation_app/tools/core_tools.py`、`src/reachy_mini_conversation_app/huggingface_realtime.py`、`src/reachy_mini_conversation_app/document_retrieval.py` 及 `src/reachy_mini_conversation_app/document_worker.py` 完成 malformed JSON／invalid-input／意外例外的 RAG 專用安全日誌與錯誤邊界；於 `tests/test_document_retrieval.py`、`tests/test_huggingface_realtime.py` 放 query／段落／路徑／底層例外 sentinel，確認 INFO／DEBUG 不洩漏原始內容或 traceback，操作失敗仍以固定碼／安全類別記錄，不沉默。
- [ ] T026 [US2] 在 `tests/test_document_worker.py` 建立明確 opt-in 的真實 Chroma 預建包整合測試，資產只由 `cache/004-single-document-rag/` 事先提供、不在 App 路徑建置；測合法／失敗／重啟前後原包 hashes、工作副本 documents／metadata／embeddings／count 與持久 HNSW hash 不變，區分允許記帳與索引寫入；禁止 migration／ingestion replay，未提供資產記未執行，若必須重建則阻擋交付並在 `specs/004-single-document-rag/quickstart.md` 留證。
- [X] T027 [US2] 執行八類故障後一般對話、文件注入不增動作權限，以及「停止 App → 換完整包 → 重啟」只引用新版本的離線整合情境，於 `tests/test_document_retrieval.py`、`tests/test_prompts.py` 補必要行為回歸並在 `specs/004-single-document-rag/quickstart.md` 記結果；不新增熱更新、文件選擇或 memory／camera 寫入。

## Phase 5: US3 — 跨後端使用並結束過期查詢（P2）

**Goal**: HF／Gemini 共用工具與單一 runtime，插話／取消／換回合後沒有遲到結果或動作。

**Independent Test**: 各 adapter 接入同一可控慢 worker，分別測插話、取消、停用、換供應商、新對話及 duplicate ID；模型／UI／follow-up 均無過期投遞。有效回合的 timeout 只顯示一次本機文字且不觸發語音，不等 provider response.done／網路才顯示；成功查詢及下一輪一般對話仍有正常語音，沒有新 worker 或隱性重試。

### Tests

- [X] T028 [P] [US3] 在 `tests/test_huggingface_realtime.py` 新增 RAG generation／response epoch、接受插話、取消／停用／換後端／新對話、跨 await／queue 消費 race 及 duplicate ID 測試。timeout 有效回合只顯示一次「文件查詢已逾時，請稍後再試。」、完成安全 function_call_output 但不因 error 強制 response.create／語音，notice 不等 response.done／網路；失效回合無 notice，late success 丟棄。測 mixed-tool batch 仍保留其他工具合法 follow-up、成功／下一輪語音正常，in-flight／batch 不被舊呼叫卡住；另驗原始 501 字即使 trim 後合法仍拒絕、原始 500 有效可接受，與 Tool 順序一致。
- [X] T029 [P] [US3] 在 `tests/test_gemini_realtime.py` 新增相同退役、toolCallCancellation、ToolInvocation.response_epoch、跨 await／queue 消費及 duplicate ID 測試；檢查 RAG declaration 為 NON_BLOCKING、成功 function response scheduling=WHEN_IDLE、timeout=SILENT，六個固定 error 不退化成通用失敗；有效回合文字恰一次／無 timeout 語音、失效回合無 notice、重複協定完成仍 silent、不重查／重播，下一輪語音正常。所選模型不支援時明示 RAG 能力不相容，不自動換模型／provider 或重連；另驗原始 501 字先拒絕及 500 字再 trim 的處理與 HF／Tool 一致。
- [X] T030 [P] [US3] 在 `tests/test_document_retrieval.py` 驗證 main 注入的 runtime 經 registry／人格／HF-Gemini 切換仍只有一個 worker，停用不讀包／不送工作、取消後仍 busy；確認 `accepted → running → completed／failed，或 retired`，永久退役不可恢復。逐字落實 answer_retired「bool，初始 false；timeout／取消／回合失效即 true，永久撤銷背景答案」、timeout_notice_sent「bool，初始 false；只在仍擁有原回合時顯示一次本機文字後設 true」，與 generation／response epoch 回合有效性分別判斷，duplicate／晚到 worker 不復活答案／重複 notice，CPU 完成不等於回合重新有效。

### Implementation

- [X] T031 [US3] 在 `src/reachy_mini_conversation_app/huggingface_realtime.py` 的共享 RealtimeConversationHandler 實作 RAG call ID／generation／response epoch、answer_retired、timeout_notice_sent 與對應退役規則，引用 data-model「由既有 handler 擷取，對話端檢查，不送文件包或作為使用者參數」；接受插話、取消、停用、換後端、新對話及結束撤銷 answer／notice。timeout 先永久撤銷背景答案，原回合仍有效才經既有 AdditionalOutputs 顯示一次固定文字；不經模型生成／第二條 transcript append、不等 provider 清理，queue 消費前重驗資格，保留其他工具語意。
- [X] T032 [US3] 在 `src/reachy_mini_conversation_app/huggingface_realtime.py` 接入共享所有權，RAG 結果／UI／follow-up 投遞前與 await 後重驗。timeout 仍對有效原 call 送安全 function_call_output，但跳過既有「任何 error 強制 follow-up」分支，不貢獻 `_tool_batch_needs_response`／`_safe_response_create()`；本機文字不等 response.done 或網路傳送。移除該 call in-flight／batch 狀態，保留其他非 timeout 工具本來應有的 batch 回覆；失效回合不向新 session 補送，不重連／重播，成功與下一輪語音正常。
- [X] T033 [US3] 在 `src/reachy_mini_conversation_app/gemini_realtime.py` 使用共享所有權與 response epoch 處理取消／晚到結果；僅 RAG declaration 設 NON_BLOCKING，與 needs_response=true 分開，依單次結果成功用 WHEN_IDLE、document_timeout 用 SILENT，保留六個固定 error、不沿用整工具 _silent_tools 讓成功也消音。有效 call 的協定完成與本機 notice 分開，duplicate timeout 仍 silent 且不重查／重複文字，失效 call 不送入新 session；所選模型排程不相容明示 RAG 能力失敗，禁止自動換模型／provider，保留其他工具既有行為與 HF 預設。
- [X] T034 [US3] 在 `src/reachy_mini_conversation_app/main.py`、`src/reachy_mini_conversation_app/tools/core_tools.py` 與共享 `src/reachy_mini_conversation_app/huggingface_realtime.py` 完成 toolset 刷新／人格停用時拒絕新查詢與退役舊 call 的接線；先前模型可保留至 App 停止，但無權限不得執行新檢索，不因刷新 registry 重建 worker。
- [X] T035 [US3] 跑 `tests/test_huggingface_realtime.py`、`tests/test_gemini_realtime.py` 及 `tests/test_document_retrieval.py` 的慢查詢／所有權／純文字 timeout 矩陣，確認同份結果可共用、六碼可區分、有效回合 notice 恰一次／零 timeout 語音、取消／切換與 notice 顯示交錯無舊輸出、duplicate 不重複、晚到答案永久丟棄；取消後 busy、完成後可明確重問，成功／下一輪語音與其他動作工具不退化。
- [X] T036 [US3] 將 US3 離線生命週期與純文字 timeout 結果、命令及尚未實測的模型 scheduling／語音項目記入 `specs/004-single-document-rag/quickstart.md`；核對切換不增加來源服務帳號、不改 HF 預設或相機／記憶／語言／人格設定，整理 T042 的插話／notice／重複 call 操作順序，不先啟動真實服務，也不以 fake 的 SILENT wire 結果代替服務驗收。

## Phase 6: Polish & Cross-Cutting Validation

**Purpose**: 完成文件、包裝、真實資產／CPU／服務驗收及最後 gate。需要外部資產／現場配合者保持未完成，不能以離線測試勾選。

- [X] T037 更新根 `README.md`、`.env.example` 與 `specs/004-single-document-rag/quickstart.md` 的實際安裝／測試命令、既有人格啟用方式、唯一預建包 Schema／額外語意條件、本機模型供應、snippets 外送／日誌限制、原始字串 500 限制、純文字 timeout、5／2／2 回收及未退出保留副本、48／50 成功門檻與停止換包；不新增 README 或 docs Markdown，不宣稱未測效能／平台／索引可攜性。
- [X] T038 [P] 依最終實作更新 `docs/scheme.mmd`，用既有產生方式重新輸出 `docs/assets/conversation_app_arch.svg` 並檢查 README 嵌入；圖中顯示 shared Tool → 本機 CPU worker → 唯一預建包與有界結果流，禁止手工改 SVG，不改 CI。
- [ ] T039 在 `tests/test_document_retrieval.py`、`tests/test_document_worker.py` 與 `tests/test_profile_paths.py` 的既有 wheel 測試補基本安裝／rag extra／worker module 打包驗證，確保安裝後的 runtime Schema 驗證不依賴 source checkout／specs 目錄或遠端 $ref，結構規則符合 `specs/004-single-document-rag/contracts/index-manifest.schema.json`；在 `specs/004-single-document-rag/quickstart.md` 記 Python 3.12 與三平台可取得證據，確認缺套件不退出普通 App、重型 import 隔離、CPU 套件來源、原包相容矩陣，未測平台未完成，不繼承舊功能跳過授權。
- [ ] T040 在 `tests/test_document_retrieval.py` 建立明確 opt-in 的 CPU 量測入口（不需新產品 CLI），接收事先供應的包／模型／固定 50 題路徑，記錄逐題時間／成功段落數／固定錯誤及摘要，先用合成 50 筆結果驗證 47 題成功不過、48 題成功可過且快速錯誤不算成功；於 `specs/004-single-document-rag/quickstart.md` 補實際命令並固定 CPU／RAM／OS／架構／model revision／依賴／threads／包 digest。執行 50 次 <=200 字有效問題（<=1,000 段、每段 <=512 tokens），至少 48／50 題五秒內成功取得段落，全部十秒內完成或明確失敗；error／no_evidence／busy／not_ready／timeout 即使很快也不計成功，不刪失敗題縮小分母。另記冷載入、p50／p95 的分母與取法、parent／worker RAM 峰值及音訊可用性；不下載／建索引／調低精度，缺資產或未達門檻保持未完成（SC-003）。
- [ ] T041 在確認文件段落外送與既有額度授權後，依 `specs/004-single-document-rag/quickstart.md` 使用事先標註並凍結的 20 題可答（>=10 換句話）、10 題無依據及 5 題要求其他文件測 HF／Gemini；檢索 >=18/20 有支持原文、各後端 >=18/20 正確、全部文件答案可核對來源、15 題負向全數不捏造／不存取其他來源，含數字／否定／表格／注入題，逐題留結果與失敗，不用重測改寫原比例（SC-001／SC-002／SC-006）。
- [ ] T042 在現場配合與雲端使用範圍確認後，依 `specs/004-single-document-rag/quickstart.md` 對 HF／Gemini 各做十次查詢，涵蓋各五次插話與五次取消／換後端／新對話，無退出、遲到語音／文字／動作或舊工具重播。另各用可控慢 worker 測有效回合 timeout 只有一次固定文字、無該錯誤觸發語音，取消／切換與顯示交錯無 notice，late success／duplicate 不重播，成功／下一輪語音正常；實際驗 Gemini 排程支援、不用 fake 代替。再測故障後中文對話、停止換包及 FR-016 九秒回收／未退出保留副本，記相機／記憶關閉、不自動換模型／provider（SC-004／SC-005）。
- [X] T043 完成實作 diff 自審，依 `AGENTS.md` 執行 Ruff check／format、strict mypy、完整 `pytest tests/ -v` 及 `uv lock --check`，核對新公共型別／模組頂層 imports／SDK 公開 API／跨平台路徑／無新 ignore，將實際 gate 與包裝結果記入 `specs/004-single-document-rag/quickstart.md`；新失敗先修復，不把 skips 或缺模型驗收寫成 pass。
- [ ] T044 在 `specs/004-single-document-rag/tasks.md` 與 `specs/004-single-document-rag/quickstart.md` 對照下列 FR／SC 覆蓋完成結案審查，只勾有證據的項目，保留原始失敗與未驗平台／效能／現場限制；確認未新增產包器、OCR、熱更新、雲端 embedding、更多供應商或自動切換，不修改 `checklists/requirements.md` 來假造規格通過，不建立上游 PR。

## Dependencies & Execution Order

### Phase graph

```text
T001 → T002 → T003
  → T004 → T005 → T006 → T007 → T008 → T009
  → US1: T010/T011/T012 → T013 → T014 → T015 → T016 → T017 → T018
  → US2: T019/T020/T021 → T022 → T023 → T024 → T025 → T026 → T027
  → US3: T028/T029/T030 → T031 → T032 → T033 → T034 → T035 → T036
  → T037/T038 → T039 → T040 → T041 → T042 → T043 → T044
```

所有 story 都依賴 Foundation。US2 hardening 延伸 US1 的包／query 成功路徑；US3 延伸 US1 工具與 US2 實體工作槽／取消，故本功能**不宣稱三個故事可無相依並行實作**。每個故事仍有自己的測試與 checkpoint；測試替身可隔離未到場的實體／服務資源。

T010／T011／T012、T019／T020／T021、T028／T029／T030 各組是在其前置階段完成後的不同檔案測試工作。T037 與 T038 為最終產品行為固定後的不同文件工作。除此之外，特別是 `document_worker.py`、`document_retrieval.py`、`core_tools.py`、`huggingface_realtime.py` 上的修改循序進行。

T026 需要實際鎖定 Chroma 及外部預建測試包；可先完成其 opt-in 測試實作，再繼續不依賴真實資產的離線任務，但 T026 未取得不變性證據就不能宣告可對真實包交付。T039 平台不可取得、T040 模型／CPU 樣本未供應、T041／T042 尚未授權或無現場配合時，相關驗收保持未完成；繼續可執行的文件／離線 gate，不能重複要求同一已授權範圍，也不能用等待時間代替授權。

T040 開始前必須完成 T026 的該目標平台不變性驗證；T041／T042 需要 T040 結果及外送／現場範圍確認。T043 是最後 gate，前面遇到回歸時先做相關測試／必要 gate，不延到結案才發現。未滿足真實驗收時，T044 只能記錄部分交付，不能勾選整體完成。

### Parallel examples per story

| 故事 | 可並行工作（僅在該故事前置完成後） | 後續合併點 |
|---|---|---|
| US1 | T010 worker 成功合約測試；T011 Tool schema 測試；T012 prompt 行為測試 | T013～T017 依序實作，T018 核對 |
| US2 | T019 包故障測試；T020 runtime timeout 測試；T021 Tool 錯誤碼測試 | T022～T025 依序實作，T026／T027 驗證 |
| US3 | T028 HF 退役測試；T029 Gemini 退役測試；T030 runtime 所有權測試 | T031～T034 依序接線，T035／T036 驗證 |

## Requirement and Evidence Coverage

| 規格 | 主要實作／驗證任務 |
|---|---|
| FR-001 工具共用／權限 | T009、T015、T016、T028～T036 |
| FR-002 唯一文件／版本 | T006、T013、T019、T022、T027、T041 |
| FR-003 原文／定位 | T006、T010、T013～T015、T022、T041 |
| FR-004 Schema／語意／引擎相容 | T002、T003、T010、T013、T014、T019、T022、T026、T039 |
| FR-005 無索引寫入 | T010、T013、T014、T019、T022、T026、T027 |
| FR-006 原始輸入限長／CPU／無下載 | T007、T011、T014、T015、T020、T028／T029、T040 |
| FR-007 回傳上限／版本 | T006、T010、T011、T014、T015、T041 |
| FR-008 回答／引用／繁體中文 | T012、T016、T018、T041、T042 |
| FR-009 無依據不捏造 | T010、T016、T021、T023、T027、T041 |
| FR-010 固定可區分錯誤 | T019～T025、T029、T033、T035、T042 |
| FR-011 deadline／busy／純文字逾時 | T007～T009、T020、T024、T028～T033、T035、T040、T042 |
| FR-012 過期結果退役 | T020、T024、T028～T036、T042 |
| FR-013 無其他副作用 | T012、T016、T018、T027、T034、T036、T041／T042 |
| FR-014 本機資料流／日誌 | T007、T010、T014、T017、T025、T037、T041 |
| FR-015 配置／停止換包 | T004、T005、T009、T027、T037、T042 |
| FR-016 九秒回收／未退出保留副本 | T009、T020、T024、T037、T042 |
| SC-001／SC-002 品質／拒答 | T040 固定樣本先備妥，T041 雙後端逐題結果 |
| SC-003 CPU 成功門檻 | T014 thread／模型策略、T020 deadline、T040 opt-in 量測：48／50 成功、快速失敗不計成功 |
| SC-004 現場生命週期 | T028～T036 離線回歸、T042 現場矩陣 |
| SC-005 八類故障／無寫入 | T019～T027、T026 真實包、T042 後續對話 |
| SC-006 輸出／日誌限額 | T010／T011、T017、T025、T041 |

## Implementation Strategy

1. 先完成 Setup／Foundation，再做 US1 離線成功路徑。**建議 MVP 核心是 US1**，但尚未具備 US2／US3 的錯誤與取消防護前，只能做隔離離線展示，不應開始真實即時對話交付。
2. 依序完成 US2 故障與資源界線、US3 兩後端退役，避免把單工具 happy path 當完整語音功能。
3. 凍結人工標註題與版本後才校準／驗收，先真實包不變性、再 CPU、再雲端品質與現場操作；沒有 API key／模型／預建包時不自動取日常資料，也不新增資產建置器。
4. 每個 checkpoint 記錄實際命令與結果；只勾完成證據充分的 task。全部驗收、必要文件、架構圖及最後 gate 完成後才結案。

## Task Summary

44 項：Setup 3、Foundational 6、US1 9、US2 9、US3 9、Cross-cutting 8。10 項標記 `[P]`，限上述不同檔案工作群。所有任務含序號、核取方塊及實際目標路徑；user story 階段均有 `[USn]`，共用階段無 story 標籤。


## 本輪執行狀態（2026-11-05）

已完成 38／44 項：T001～T025、T027～T038、T043。實作及離線驗證已完成，但功能尚未結案。詳細命令、套件及限制見 quickstart 的續作紀錄；requirements checklist 保持原有 16／16，不修改其標記。

- T026：已提供明確 opt-in 真實 Chroma 不變性測試；使用者回覆索引／模型「尚未準備」，未執行，不以 fake HNSW 證據替代。
- T039：Windows Python 3.12 普通／rag 安裝、CPU import、wheel／隨包 schema／checkout 外 import 已驗證；Linux／macOS 尚未執行，整項保留未完成。
- T040：已建立真實 CPU 50 題 opt-in 測試入口及 47／50 失敗、48／50 通過的固定分母回歸；尚無真實模型、索引、固定題組及主機量測，未完成。
- T041、T042：等待同一份實際素材及本次文件段落外送／雲端額度／語音與機器人驗收範圍確認。前次金鑰功能授權不作為 RAG 授權；本輪不連雲端、不啟動機器人。
- T043：Ruff check／format、strict mypy（59 source files）、完整 pytest 897 passed／2 skipped、uv lock --check 已通過。兩個 skip 僅為未提供素材的 opt-in 完整性與 CPU 測試；不是實際驗收通過。其他初期失敗與每輪測試紀錄保留於 ignored cache。
- T044：待上述實際證據與平台缺項完成後，才做最終全 feature 結案；目前僅記錄已完成部分。
