# Tasks: 單一預建文件 RAG v2 增量實作

**Input**: 本目錄 [spec](spec.md)、[plan](plan.md)、[research](research.md)、[data-model](data-model.md)、[包契約](contracts/index-package.md)、[工具契約](contracts/search-document.md) 、[CPU人工核對契約](contracts/cpu-evaluation.md) 及 [驗收指南](quickstart.md)。

**Target**: `004-single-document-rag` | **Date**: 2026-11-09 | **Current Git Branch**: `feat/005-prepare-rag-assets`（依指定FEATURE_DIRECTORY定位，未切換分支）。

**Design Sync**: 採004／005本輪設計與bge-base-final-selection-20261109，已增量同步U1固定證據／人工核對與U2舊包本機提示。spec／plan前階段「任務待同步」狀態由本版完成同步紀錄接替；只更新任務，不代表v2已實作、舊失敗通過或取得任何新模型／服務驗收。

**Tests**: SC-001～SC-008明定測試／量測，故列必要行為測試。先建立能捕捉缺失的測試，再實作；不因品質比例取消而省略故障／生命週期／隱私回歸或完整工程gate。

## Format and execution scope

- 新版可執行清單僅T045～T084，37／40完成；T069已完成。T080原始50題及人工核對（21支持／1不支持／28無證據）、音訊補充與所有舊失敗保留。依使用者採用建議已新增20組FAQ、離線重產330段v2包，正式reader預設20／20完整。新35題矩陣HF取回20／20、逐字稿14／20完整；Gemini取回及逐字稿19／20完整，另Q37 provider窗逾時保留。名稱／引用及服務限制未解，T081仍未結案。原Gemini對話連續性修正已取消，數值及拆句實驗未導入；正式參數未改。T082及總結案T084未完成，最新證據見quickstart。ID接續舊T044，不重新編號或變更舊完成狀態。
- 文末四反引號區塊是原T001～T044完整歷史存檔，39項已完成／5項未完成；它不是待執行清單。舊dense-only、48／50、品質門檻與當時素材狀態均只代表舊snapshot。實作工具必須忽略存檔內核取方塊，只處理本節新版待辦。
- `[P]`只表示列明前置完成後不同檔案的工作可並行，不是啟動代理或服務的授權；同檔修改循序。
- 004消費唯一已預建v2包；所有下載、原文件／別名解析、文件向量與BM25／索引建置屬005離線流程，不搬進App。本輪與一般gate不下載、不啟動App／雲端／機器人。
- 保留已有個人客製化授權。本次真實文件段落外送、免費／付費額度、語音及實機操作須依實際資料範圍確認；不讀日常.env／私密快取，不將舊功能同意擴張為新資料授權。Linux／macOS依既有指示略過、不記pass，跨平台程式及CI仍保留。

## Phase 1: Setup — 新版基線與跨功能協調

**Goal**: 明確區分歷史證據、新版設計與005責任，沿用既有依賴。

- [X] T045 在 `specs/004-single-document-rag/quickstart.md` 記錄v2開發基線、Git分支／Python3.12／既有lock、可用的已授權資產與原始失敗；核對 `AGENTS.md`、`CONTRIBUTING.md`、`.specify/memory/constitution.md`，缺真實資產只延後相關驗收，不重做已授權確認、不讀日常私密設定或開PR。
- [X] T046 核對 `specs/005-prepare-rag-assets/tasks.md` 已同步雙角色v2 receipt、chapter-source-v1／可選人工別名、預建BM25與明確scheme；在 `specs/004-single-document-rag/quickstart.md` 記交接狀態及004reader供005fresh verifier重用的邊界。唯讀檢查 `pyproject.toml`、`uv.lock` 與既有離線實驗，確認ST CrossEncoder及標準庫BM25可沿用；不新增依賴、任意換版本或把005任務視為已完成。

## Phase 2: Foundational — v2配置與共用資料邊界

**Goal**: 固定三路徑、v2 schema與型別；不讓未啟用RAG的App載入模型。

- [X] T047 [P] 在 `tests/test_document_worker.py` 為 `specs/004-single-document-rag/contracts/index-manifest.schema.json` 建v2正反例：「manifest schema `2`、index_version、唯一 DesignatedDocument」、required／null／未知欄位、精確版本含local suffix、固定雙模型SHA、strategy／chunking／assets／BM25／reranking／provenance、file inventory／平台／reference；v1拒絕並留原包不變，無遠端schema。包含偽造quality_gate_passed、錯選值來源及用0.58冒充dense-only的反例。 補U2標頭辨識正反例：有界UTF-8／JSON與重複key檢查後，只有頂層整數schema_version=1才標legacy_package，bool／未知版本／壞JSON不得冒稱v1；驗開Chroma前拒絕且只發私密failure，不改包schema／公開六碼。
- [X] T048 [P] 在 `tests/test_config.py` 測新增REACHY_MINI_DOCUMENT_RERANKER_PATH與保留INDEX_PATH／MODEL_PATH：三欄預設空白、缺一not_ready、禁止URL、相對啟動CWD解析一次／凍結至重啟、一般設定／RPC不新增路徑外洩；測試不讀.env或載入模型。
- [X] T049 在 `src/reachy_mini_conversation_app/config.py`、`src/reachy_mini_conversation_app/document_retrieval.py`、`src/reachy_mini_conversation_app/main.py` 串接獨立REACHY_MINI_DOCUMENT_RERANKER_PATH至唯一runtime與child啟動環境，保留ToolDependencies介面、HF預設、既有嵌入／索引位置；任一缺漏not_ready、未啟用不讀包，無設定頁／模型搜尋／下載。依T048驗證。
- [X] T050 將v2契約同步至 `src/reachy_mini_conversation_app/document_manifest.schema.json` 並於 `src/reachy_mini_conversation_app/document_assets.py` 沿用本地jsonschema／安全檔案驗證。型別邊界在 `src/reachy_mini_conversation_app/document_retrieval.py` 保留「非空安全識別字串，<=128 code points」「非空顯示文字，<=160 code points」「非空安全字串，<=128 code points」「非空文字 <=256 code points」，文件／段落版本相符、source_sha256「原文件內容 digest」。只讀本地$defs、拒絕未知欄位／null／重複key／NaN／Infinity，無新忽略或Any／cast。
- [X] T051 在 `tests/test_document_retrieval.py` 擴充三路徑啟動／輕量import／唯一worker協定回歸，引用資料模型「runtime 請求及既有工具呼叫的唯一關聯」「monotonic 受理時間及 +10 秒期限」；私密pipe版本1、request_id、64KiB與載入120秒邊界不因包版本2改變；runtime凍結三路徑、缺套件不使普通App退出。執行T047／T048相關回歸並在 `specs/004-single-document-rag/quickstart.md` 記結果。 依 `specs/004-single-document-rag/contracts/search-document.md` 測私密協定1可選reason：只允許failure＋document_unavailable＋legacy_package，省略合法、null／未知值／其他error組合拒絕，不鏡射原始訊息；先以假worker寫上述協定／快取失敗測試，再於 `src/reachy_mini_conversation_app/document_retrieval.py` 實作strict reason解析及宣告的typed唯讀unavailable_reason，受鎖保護、初始化／關閉清除，不進query結果／設定回應。測首問not_ready後載入失敗僅快取原因，不能直接從thread發UI或復活首問，下一有效query回unavailable。

**Checkpoint**: 三路徑與v2資料邊界通過離線測試；雙模型／真實包尚未驗收。

## Phase 3: US1 — 唯一文件的混合檢索／重排與來源（P1，MVP）

**Independent Test**: 合成v2包與假encoder／reranker固定候選及分數，驗exact dense／BM25／RRF／完整五候選／後置距離順序、可見原文／定位與三段限額；不用005實際下載或雲端服務。

### Tests

- [X] T052 [P] [US1] 在 `tests/test_document_worker.py` 建候選／排序邊界：exact dense前10、BM25正分前10、等權RRF k60取最多5個不同完整parent，正分／去重／不足5不湊數／同分ID穩定；Identity logit最低3.486859679222107、附加drop最多4、最多3段／2000code points後才套cosine0.58；等於門檻保留、top1超限整次no_evidence、附加超限刪除無補位／重排／重新分預算。以假資料明確區分錯誤的ANN、距離預篩及sigmoid。
- [X] T053 [P] [US1] 在 `tests/test_document_model.py` 建兩固定角色／SHA、安全權重／receipt／精確runtime、CPU float32／Identity raw logits、pair512／batch4測試；query保留、來源prefix offset／CRLF／中文與實際可見原文對照，無可見原文或query已超pair預算不靜默裁query。攔截GPU／pickle／remote code／網路及第二次inter-op設定；不啟真實模型。
- [X] T054 [P] [US1] 在 `tests/tools/test_search_document.py`、`tests/test_prompts.py` 覆蓋既有Tool／prompt接收v2結果，逐字保留query「先檢查原始字串（含前後空白）<=500 Unicode code points，再 trim 後檢查至少一個字母或數字；無效不送 worker」，拒絕額外路徑／集合參數；成功為「1–3 個 CitationPassage」「text 合計 <=2,000 code points」。只有明確文件問題先檢索、繁體中文整理／原文不改寫；無支持不捏造、標題／別名不當引文，不新增充分性規則／模型／雲端審核。

### Implementation and integration

- [X] T055 [US1] 在 `src/reachy_mini_conversation_app/document_worker.py` 接入T050 v2 schema／全部檔案與語意preflight，核對exact inventory／hash／平台矩陣／唯一集合及全部rows；逐字落實「chunk_count >0」「所有 required 欄不得 null／省略」「清單不得同 path 不同 hash」，manifest UTF-8無BOM且<=16MiB；拒絕未列檔／link／junction／穿越／平台別名碰撞。原包不交Chroma，驗後完整副本再驗hash，只get_collection embedding_function=None，不建／遷移／寫索引；v1直接unavailable並以安全提示要求離線重產。 U2新增受限標頭識別：確認schema_version為整數1後，在開引擎前拒絕，以私密failure附reason=legacy_package；v1公開仍document_unavailable，不回公開reason／message／新error碼。一般格式故障／其他版本不推測legacy，提示排程由US3共享handler處理，worker不直接顯示文字。
- [X] T056 [US1] 在 `src/reachy_mini_conversation_app/document_model.py` 擴充共用角色安全載入：BAAI/bge-m3@50f9396f75618b3389c1fd1068a1ff58dc7b5b26與BAAI/bge-reranker-base@2cfc18c9415c912f9d8155881c133215df768a70，使用005 v2 receipt與manifest各角色payload＋receipt hash；CPU float32、local_files_only／trust_remote_code=False／safetensors。嵌入保持「dense、float32、CLS、L2、無 prefix、維度 1024、cosine、max_seq_length 8192」，reference norm誤差<=1e-4／cosine差<=1e-5；重排CrossEncoder原始Identity logit／pair512／batch4，不新增依賴。threads intra2／inter1移至 `src/reachy_mini_conversation_app/document_worker.py` 程序入口只設一次。
- [X] T057 [US1] 在 `src/reachy_mini_conversation_app/document_worker.py` 驗證預建retrieval/chunks.jsonl與bm25.json：chunk_id「唯一、穩定、安全字串 <=128 code points，對應 Chroma row ID」、document_id／document_version「必須等於 manifest 唯一文件」、text「非空原文；存於 Chroma documents，與 retrieval/chunks.jsonl 的相同 ID／原文字串一致」、embedding「1024 個有限數、非零、L2 normalized float32；不進模型工具結果」。核對chapter-source-v1「target_tokens=300、overlap_tokens=30、embedding_input_max_tokens=512、heading_context_max_tokens=64、alias_context_max_tokens=48、heading_levels=3」及固定model_text模板；核對start／end非負半開區間、end-start=len(text)、真實行號／重疊內容、標題／人工別名證據與scope／model_text digest；空別名合法，無標題TXT不造章節。BM25「已列TF／DF為正整數，df<=N、每段長度等於tf總和、N等於chunk_count、avgdl等於總長度/N」，ID全集／順序一致、空詞avgdl0合法。不得解析原文件、重tokenize語料建統計、修補或忽略壞資料。
- [X] T058 [US1] 在 `src/reachy_mini_conversation_app/document_worker.py` 從全部已核對Chroma row保留既有normalized父向量矩陣，精確1-dot算cosine top10（非ANN／新索引）；query以ascii-cjk23-v1的casefold ASCII [a-z0-9]+／CJK U+3400..U+9FFF二三字組去重，只讀預建TF／DF／dl／avgdl計BM25（k1=1.2、b=.75、positive log1p IDF），正分top10。等權1/(60+rank)融合取最多5個不同完整parent，同分ID；lexical-only也用既有父向量算cosine，資源不足明確失敗，不換策略。
- [X] T059 [US1] 在 `src/reachy_mini_conversation_app/document_model.py` 實作完整parent model_text與query的BGE-base評分，保留query／來源右側prefix，透過tokenizer offset映回實際可見原文，禁止拆短窗取最高分。章節／人工別名僅模型脈絡；原文未進pair不可回傳，兩類裁切都truncated並保留真實定位。query自身超pair512則no_evidence、無可見原文候選不回傳且不補新候選，所有logit有限。
- [X] T060 [US1] 在 `src/reachy_mini_conversation_app/document_worker.py` 實作T052固定選段：logit降序／ID、第一名與附加段均>=3.486859679222107、附加相對第一名drop<=4，最多3段／2000code points連續前綴；不限同父章節、group margin停用。最後才用父cosine<=0.58，top1超限整次no_evidence，附加超限只刪除、不換第一名／補段／重排／重分字元預算；空結果no_evidence。不接受query覆寫方案，不將0.58說成機率／通用dense門檻。
- [X] T061 [US1] 在 `src/reachy_mini_conversation_app/tools/search_document.py`、`src/reachy_mini_conversation_app/prompts.py` 保留一般Tool／既有toolset與needs_response=True，依v2成功／無依據提供真實來源與繁體中文整理，後端只按實際原文作答，不把成功工具結果當充分保證；停用／一般聊天不強制檢索，無新動作權限／充分性判斷器／雲端審核。依T054測試作必要最小修改，保留既有語言例外。
- [X] T062 [US1] 在 `src/reachy_mini_conversation_app/document_retrieval.py` 對新版worker結果再驗唯一DocumentIdentity、index_version及各段chunk_id／locator／text／truncated與「text 合計 <=2,000 code points」；維持成功／六碼錯誤形狀及私密協定1，不將vectors／raw logits／距離百分比／路徑傳模型。保留typed依賴與一份runtime，不重寫其他工具介面。
- [X] T063 [US1] 執行 `tests/test_document_worker.py`、`tests/test_document_model.py`、`tests/tools/test_search_document.py`、`tests/test_prompts.py` 的v2成功路徑及已曝光選案回放一致性；在 `specs/004-single-document-rag/quickstart.md` 記原候選／排序／原文可見範圍差異與失敗。provenance完整引用固定scheme／兩來源digest、200題曝光／84/100正例／2/100負例誤放行／127/131支持；288段及實驗別名不硬編碼，不稱新盲測或原門檻通過，保留所有舊紀錄。

**Checkpoint**: US1可做隔離離線MVP。未完成US2／US3回歸及實際資產驗證前，不交付真實即時對話。

## Phase 4: US2 — 無依據／故障可恢復與不變性（P1）

**Independent Test**: 假包／模型覆蓋八類故障與無依據，後續一般聊天正常、原包與預建資料無修改；真實Chroma不變性獨立opt-in。

- [X] T064 [P] [US2] 在 `tests/test_document_worker.py` 擴充v1、缺／壞BM25、錯脈絡／別名scope／來源版本、混合文件／版本、錯兩模型receipt／hash／runtime、錯平台／需migration等失敗矩陣；空別名與無標題TXT合法、只壞一段仍全包unavailable。攔截任何create／add／upsert／update／delete／reset／ingestion replay／重建／網路；不以dense-only fallback掩蓋缺資料。 補私密legacy_package只來自已確認整數v1的failure測試，其他故障／未知版本／bool不帶舊包原因，無額外模型結果欄位；壞結果經parent驗證合成unavailable也不得誤提示。
- [X] T065 [P] [US2] 在 `tests/test_document_retrieval.py` 擴充雙模型載入／失敗與慢worker：單child／單工作／零排隊、初始化<=120秒、受理+10秒deadline；取消／逾時後直到CPU實際完成仍busy，不另開worker。測loading／busy／timeout後關閉，單monotonic總9秒分5／2／2，提前退出不等滿、未確認退出保留副本／cleanup_incomplete，無無界wait。
- [X] T066 [US2] 在 `src/reachy_mini_conversation_app/document_worker.py`、`src/reachy_mini_conversation_app/tools/core_tools.py` 依T064維持document_not_ready／busy／unavailable／invalid_query／no_evidence／timeout六固定碼：缺模型／配置與包故障分開，v1有安全離線重產提示；日誌僅固定碼／例外類別、時間與數量，無raw args／原文／向量／路徑／traceback，操作失敗不沉默，不影響普通對話。 依U2保留六公開碼及固定結果形狀，legacy_package僅在已驗證的初始化私密failure傳遞，不送模型／一般設定或靠例外字串推斷；通用unavailable不可一律宣稱v1。專用本機提示由T074排程，不把它誤用timeout SILENT或從worker／dispatcher直接觸發TTS。
- [X] T067 [US2] 在 `src/reachy_mini_conversation_app/document_retrieval.py` 依T065維持runtime狀態「unconfigured」「dormant」「loading」「ready」「busy」「failed」「closing / closed」，失敗不自動重啟、配置需App重啟；tool停用不讀包，CPU未完成不釋放槽。finally先撤銷投遞資格，僅確認worker退出才清工作副本，9秒未確認則保留並安全報清理不全，不修改原包／模型。 新增宣告的typed唯讀unavailable_reason（legacy_package或None），用既有鎖保護、初始化／關閉清除，只接受合法私密failure組合，公開query回傳仍六固定碼。載入thread只快取原因，不發本機提示；下一明確有效query才能讓handler讀原因，無效query／工具停用不提示，不改failed至重啟的生命週期。
- [X] T068 [US2] 在 `tests/test_document_retrieval.py`、`tests/tools/test_search_document.py` 補v2結果及malformed query／第三方錯誤／model path的sentinel測試；INFO／DEBUG不洩漏內容，正常引用逐字稿與診斷界線分開。來源指令只當資料，無相機／記憶／機器人動作／其他來源權限；故障後一般中文對話仍可進行。
- [X] T069 [US2] 擴充 `tests/test_document_worker.py` 的external_prebuilt opt-in入口，接受005事先提供的v2包及雙模型，經fresh process核對原包全hash、retrieval資產hash、全rows／metadata／vectors／count及工作副本持久HNSW不變性，允許必要SQLite記帳但無索引寫入／replay／migration；合法／失敗／重啟皆測。在 `specs/004-single-document-rag/quickstart.md` 記實際Windows證據／命令，缺資產只記未執行，不在App建包或自動下載；此真實驗收可延後但阻擋真實交付。
- [X] T070 [US2] 執行 `tests/test_document_worker.py`、`tests/test_document_retrieval.py`、`tests/test_prompts.py` 的故障矩陣及停止App換完整v2包／重啟後僅新版本的離線情境，在 `specs/004-single-document-rag/quickstart.md` 對應SC-005／SC-007記錄八類結果、無標題TXT／空別名與不變性；不把合成測試當真實HNSW或品質通過。

## Phase 5: US3 — 雙後端與過期結果退役（P2）

**Independent Test**: HF／Gemini各用同一可控慢worker測有效／失效回合、timeout與duplicate；只有有效回合一次本機文字，零timeout語音，下一回合與其他工具正常。

- [X] T071 [P] [US3] 在 `tests/test_huggingface_realtime.py` 以v2結果測generation／response_epoch、插話／取消／換後端／停用／新對話／duplicate與跨await／queue競態；timeout只顯示一次固定中文文字、不等response.done／網路、不因error觸發response.create，mixed batch其他工具合法follow-up保留。成功／下一回合語音與原始500／501驗證順序不退化。 補U2共享handler測試：有效且通過結果驗證的unavailable＋runtime legacy原因，經DocumentOutput顯示固定舊包文字一次；duplicate、入queue後插話／取消／停用／換後端／新回合不得重複／補送。初始化晚到不復活首問，下一有效call可各提示一次；缺原因／其他故障／驗證拒絕後合成unavailable均不提示。專用文字零新增TTS／response.create／第二條transcript append，一般unavailable既有錯誤語音／follow-up仍按原行為。
- [X] T072 [P] [US3] 在 `tests/test_gemini_realtime.py` 測同一v2結果／六碼、NON_BLOCKING宣告、成功WHEN_IDLE／timeout SILENT、toolCallCancellation／response_epoch／duplicate與socket等待後重驗；有效回合文字恰一次、失效回合無輸出／舊段落重播，成功／下一輪語音正常；模型不相容明示、不換模型／provider／自動重連。 補與HF相同U2原因／提示／duplicate／queue失效／初始化競態，明確驗Gemini重用共享DocumentOutput路徑，不複製一份legacy顯示邏輯；公開function response仍只有document_unavailable，reason不外送。legacy文字不額外觸發語音，一般unavailable排程不改成timeout SILENT；timeout原SILENT與成功WHEN_IDLE各自回歸。
- [X] T073 [P] [US3] 在 `tests/test_document_retrieval.py` 測v2忙碌／超時／換人格toolset與共享runtime：status「accepted → running → completed／failed，或 retired」，answer_retired「bool，初始 false；timeout／取消／回合失效即 true，永久撤銷背景答案」、timeout_notice_sent「bool，初始 false；只在仍擁有原回合時顯示一次本機文字後設 true」。generation／response_epoch「由既有 handler 擷取，對話端檢查，不送文件包或作為使用者參數」；CPU完成不復活所有權，切換不新增worker。 另測legacy_notice_sent「bool，初始 false；已確認v1且該次有效查詢回unavailable時，排入一次本機專用提示前設true；與timeout標記獨立」；失效後不重排、不復活answer_retired。runtime unavailable_reason在載入／失敗／關閉的值符合私密原因契約，無效query／停用工具／初始化thread不直接輸出提示。
- [X] T074 [US3] 依T071～T073在 `src/reachy_mini_conversation_app/huggingface_realtime.py` 的共享handler及 `src/reachy_mini_conversation_app/gemini_realtime.py`、`src/reachy_mini_conversation_app/tools/core_tools.py` 作必要最小整合；保留兩種投遞資格、跨await重驗、一次AdditionalOutputs文字「文件查詢已逾時，請稍後再試。」、零重複transcript append與背景晚到永久退役。HF不由timeout貢獻batch follow-up，Gemini per-result SILENT而非整工具消音；不改其他工具語意或建立第二套對話控制。 依U2在共享 `_document_result()` 以deps.document_retrieval唯讀取得typed unavailable_reason；只對原call有效、query有效／工具啟用、真實通過結果驗證的unavailable排文字。ToolInvocation宣告legacy_notice_sent初始false、入queue前置true，經既有DocumentOutput／AdditionalOutputs與emit消費前所有權檢查顯示「此文件索引為舊版，請停止 App，使用離線產包腳本重新產生新版索引包。」每有效call最多一次，失效不補送，不帶路徑、不新增TTS／response.create或重複transcript。Gemini沿共享邏輯；通用錯誤對話／timeout_notice_sent及timeout SILENT互不改寫。
- [X] T075 [US3] 跑 `tests/test_huggingface_realtime.py`、`tests/test_gemini_realtime.py`、`tests/test_document_retrieval.py` 及既有manager／task_status回歸，在 `specs/004-single-document-rag/quickstart.md` 留v2生命週期與後續一般聊天結果；無舊語音／文字／動作、無重查／重播、timeout不等網路。fake wire只算離線證據，實際服務排程留T082，不宣稱已驗收。 一併跑U2 legacy私密原因／共享本機提示矩陣：同call一次、新有效call可再提示、首問結束後初始化失敗不補送、queue後失效丟棄、非legacy／合成錯誤不誤報；核對六碼及provider結果不帶reason，專用提示不新增語音而通用unavailable行為不變。

## Phase 6: Polish & Cross-Cutting Validation

**Goal**: 完成文件／包裝與實際資料量測，取得安全與現場證據後才審查結案。

- [X] T076 [P] 更新 `README.md`、`.env.example` 與 `specs/004-single-document-rag/quickstart.md`：第三模型路徑、v2-only／v1離線重產、005三步交接、固定scheme／來源限制、原文外送／診斷隱私、文字逾時／9秒回收；移除產品說明中已取代的品質合格門檻、保留歷史失敗。無額外README或docs Markdown，不改日常.env。 同步U1測前固定gold／測後人工核對與工具延遲分離、U2本機提示／六碼不變／原回合有效性及一般錯誤行為；說明當前設計／任務已同步而實作驗收未完成，舊日期狀態只作歷史記錄。
- [X] T077 [P] 依實作更新 `docs/scheme.mmd` 並用既有流程重生 `docs/assets/conversation_app_arch.svg`，檢查README嵌入，顯示預建BM25／雙模型與單worker有界資料流；不手編SVG、不改CI。
- [X] T078 在 `tests/test_profile_paths.py`、`tests/test_document_worker.py`、`tests/test_document_model.py` 驗證普通／rag安裝及wheel包含v2 manifest／角色receipt schema且與004／005設計契約一致，無checkout／遠端schema依賴；普通App／CLI help不import重型依賴，CPU／SDK公開API與lock共存。依使用者指示僅Windows實測，Linux／macOS略過／未驗證不算pass。 另驗私密legacy原因與typed本機屬性不出現在provider工具結果或一般設定回應；測試專用CPU資料／人工核對格式依 `specs/004-single-document-rag/contracts/cpu-evaluation.md`，不把標註／review資料新增成App持久查詢快取或產品服務。
- [X] T079 在 `tests/test_document_retrieval.py` 依 `specs/004-single-document-rag/contracts/cpu-evaluation.md` 先建立失敗可捕捉的dataset／review／計時報表測試，再更新external_cpu opt-in runner。輸入由舊純字串陣列改成「schema_version：整數1，不接受bool」、dataset_id／dataset_version「各為非空安全identifier，最多128 code points」、document只含id／version／64hex source_sha256且與包相符、questions「恰50項，順序固定，id全體唯一」、question ID最多128 code points、query「原始1～200 Unicode code points，trim後至少有字母／數字」。answerability為answerable或unanswerable，測前固定required_information／evidence；answerable各至少一項，unanswerable為空；evidence只含text／start／end／locator，非空原文且0<=start<end、end-start=len(text)，人工核對同一來源。拒絕舊陣列自動補標註、未知欄位／null／重複key／非有限數／來源不符，凍結dataset版本／bytes digest及包／兩模型／run身分；不新增runtime充分性判斷器或雲端審核。每題單次記question_id／accepted_at_monotonic／finished_at_monotonic／elapsed_seconds／outcome／原始有界result，時間有限非負，延遲止於工具結果或十秒逾時、冷載入另列；cache紀錄與產品診斷／query快取分開，終端僅安全摘要。先保留pending review，再讀人工核對紀錄：run_id／question_id、非個資reviewer、UTC ISO8601 reviewed_at_utc、有限非負review_seconds、decision「pending／supported／unsupported／uncertain／not_applicable」、annotation_status「pending／valid／invalid」及逐必要項checks（satisfied／missing／uncertain）／對應回傳chunk_id及可見原文定位／reason；pending可省reviewer／判讀時間，invalid須uncertain並留annotation_invalid理由。人工只看實際返回且評分可見原文，全部必要資訊齊全才supported；missing則unsupported、無法確定則uncertain，Tool失敗not_applicable；負例正確拒答另列expected_refusal不算段落成功。以合成50筆驗ok但不支持／pending／uncertain不成功、超5秒支持不算五秒內、人工耗時不更改原工具elapsed、錯標註不縮分母、修改gold另版本另run／保留原失敗、空成功子集不除零；47／50與48／50僅觀察。彙總完整50題nearest-rank p50第25／p95第48／max及成功子集、各錯誤／無支持放行／判讀狀態、RSS取樣／題間等待；十秒deadline及晚到退役仍測，不用歷史快取分數冒充本次執行。
- [X] T080 完成T069、T079及005實際v2包／雙模型交付後，依 `specs/004-single-document-rag/quickstart.md` 與 `specs/004-single-document-rag/contracts/cpu-evaluation.md` 明確opt-in執行 `tests/test_document_retrieval.py` CPU驗收：固定一台CPU／RAM／OS／架構／Python／lock／雙revision／threads2／1，最多1000段且每段最多512tokens包、恰50題每題最多200字的有效dataset。測前人工核對問題／可答性／必要資訊／原文證據／真實定位，凍結題組／文件版本與digest；執行時單次保留原工具結果／monotonic延遲及題間等待，不自動重送或看結果改標註。測後人工填逐項checks／可見回傳證據／判讀理由及supported／unsupported／uncertain／not_applicable，人工review時間另列不算工具延遲；pending與不確定／不支持／操作失敗都不計成功，負例正確拒答另列。全50分母、原始失敗／annotation_invalid、五秒內支持成功及超五秒支持、各錯誤、完整p50／p95／max與成功子集、冷載入／RSS／音訊可用性皆記錄；所有查詢十秒內完成或明確逾時。缺資產／未完成核對保持未完成；修訂gold須另版本／run且保留舊紀錄，不以品質比例／0.58／歷史試驗代替本次量測，不新增runtime充分性判斷。
- [ ] T081 於確認本次文件段落外送與既有服務額度後，依 `specs/004-single-document-rag/quickstart.md` 對HF／Gemini各測固定20題可答（至少10改寫）、10題無依據、5題要求其他文件；逐題記檢索完整證據／段落支持／回答正確／負例放行／引用與原因，不作比例或零檢索誤放行門檻。兩後端仍須如實表示資訊不足、不捏造／越權來源，數字／否定／日期／表格／注入均查；保留原題與分母，不把曝光200題稱新盲測或重測改寫舊失敗。
- [ ] T082 於現場及雲端範圍確認後，依 `specs/004-single-document-rag/quickstart.md` 對HF／Gemini各做10次v2查詢，含5次插話及5次取消／換後端／新對話；驗零非預期退出／遲到語音文字動作／重播、後續中文聊天正常。另各測有效回合timeout文字恰一次／零該錯誤語音、失效回合無notice、duplicate／late success退役及實際Gemini scheduling；驗停止換包與9秒回收／未確認保留副本。相機／記憶保持關閉、不自動換模型／provider，不能以fake替代。
- [X] T083 自審v2 diff並依 `AGENTS.md` 執行Ruff check／format、strict mypy、完整 `pytest tests/ -v` 及 `uv lock --check`，於 `specs/004-single-document-rag/quickstart.md` 記命令／實際結果與skips；核對typed APIs／頂層imports／無新ignore／SDK相容／鎖檔與schema包裝。新失敗先修，不將舊897項或合成證據當成本輪通過，不在gate自動下載／連雲端／啟動機器人。
- [ ] T084 在 `specs/004-single-document-rag/tasks.md` 與 `specs/004-single-document-rag/quickstart.md` 逐項對照FR-001～FR-021及SC-001～SC-008審查新版交付，只勾有實作／證據者。保留完整200題曝光／84/100、2/100、127/131與已知錯例；0.58僅選用實驗上限。安全／來源／不變性／工程gate或必要量測未完成時只能部分交付，不以品質門檻取消掩蓋缺項；舊T026／T040～T042／T044保持歷史未完成，不倒填通過、不改requirements checklist或建立上游PR。 納入U1逐題原始計時／人工支持核對的完整50分母及U2本機提示／私密原因／初始化與queue退役證據；核對人工時間未混入工具延遲，未判讀／uncertain不當成功，舊包提示不改公開六碼或一般錯誤回覆。

## Dependencies & Execution Order

```text
T045 → T046 → T047/T048 → T049 → T050 → T051
  → US1: T052/T053/T054 → T055 → T056 → T057 → T058 → T059 → T060 → T061 → T062 → T063
  → US2: T064/T065 → T066 → T067 → T068 → T069(opt-in) / T070(offline)
  → US3: T071/T072/T073 → T074 → T075
  → T076/T077 → T078 → T079 → T080 → T081 → T082 → T083 → T084
```

- T046只要求005設計／tasks對齊與責任協調，不要求005先產出真實包。005 producer及004 reader可分階段協作：先完成004離線reader（T055～T063），005再用它fresh verify；真實交付須005完成v2包／兩角色receipt後執行T069，無循環依賴。
- T056重用005的角色模型支援／receipt契約；實作由同一共享document_model／document_assets協調一次，004與005同檔案任務不得平行重複改。若005尚未有對應實作，T056可在合約下先做typed支援及假資料回歸，真正模型準備仍屬005。
- US2離線T064～T068／T070在US1後可做；T069需真實資產，可等待而繼續US3／文件／T079，不因缺資產反覆停下無關工作。真實包交付／T080及後續現場驗收必須先完成T069。
- US3需Foundation與US1結果契約及US2的單工作／錯誤／期限離線回歸；不依賴T069實際包已到場。三故事不宣稱無相依並行，但可用替身獨立驗證故事行為。
- T076／T077在行為固定後可與不同檔案工作並行；T078需相關程式／schema已整合。T079可離線先做；T080須T069、T079及005完整資產。T081／T082須T080實測與資料外送／額度／現場配合；接受低品質比例不等於免除量測或安全驗證。
- T083是最終工程gate，實作過程先跑各自相關回歸；T084結案需要完整證據，未提供資產／授權／現場配合只留未完成與限制，時間經過不是授權。

### U1／U2補充依賴與獨立驗證

- T047測v1標頭，T051先測並實作parent私密原因解析／typed快取；假worker足以驗完Foundation，不等待US2。T055才讓真worker輸出reason，T064擴充故障矩陣、T066／T067核對真實失敗與runtime生命週期整合，最後T071～T073先測通知、T074才共享接線；各階段測試通過才勾選，不將待補分支當已完成。
- US2獨立驗證再涵蓋v1與非v1的私密原因隔離；US3獨立驗證包含本機專用文字每有效call最多一次、duplicate／queue失效／初始化晚到不補送、通用unavailable行為不變，與timeout純文字／SILENT分開。新增範圍不改三故事優先順序或無資產可做的離線工作。
- T079在同一測試檔先寫資料契約／純合成報表回歸，再實作runner，與任何其他修改tests/test_document_retrieval.py任務不能並行。T080一定先完成合法測前gold與凍結，執行後人工final review；未核對不得宣告CPU成功數或T080完成。不要求改005包格式／產包驗證或新增產品CLI。
- T076／T078／T084對照新本機提示與測試資料契約；文件／wheel不把私密reason公開、也不將驗收cache當App持久查詢紀錄。T081／T082的品質／現場範圍與授權要求保留，T083最終工程gate不得用本輪文件檢查代替。

### Parallel examples per story

| 群組 | 相同前置完成後可並行的不同檔案 | 合併點 |
|---|---|---|
| Foundation | T047 worker契約測試、T048 config測試 | T049～T051 |
| US1 | T052 worker排序、T053模型輸入、T054 Tool／prompt測試 | T055～T063循序；不平行改worker |
| US2 | T064 worker故障／私密legacy、T065 runtime期限／退出測試 | T066～T068／T070；T069真實資產另排 |
| US3 | T071 HF、T072 Gemini、T073 runtime所有權／legacy_notice測試 | T074共享整合、T075回歸 |
| Polish | T076 README／env／guide、T077 Mermaid／SVG | T078以後；圖任務不編輯README |

## Requirement and Evidence Coverage

| 規格 | 新版實作／驗證任務 |
|---|---|
| FR-001 Tool／共用權限 | T049、T054、T061、T071～T075 |
| FR-002 唯一文件版本 | T050、T055、T057、T062、T064、T070、T081 |
| FR-003 原文／定位／BM25／別名 | T052、T055、T057～T063、T064、T069 |
| FR-004 版本／完整性／v1與本機專用提示 | T047、T050／T051、T055～T057、T064、T066／T067、T069、T071～T075、T078 |
| FR-005 對話零建索引 | T046、T055、T057／T058、T064、T069 |
| FR-006 原始輸入／CPU／無下載 | T048／T049、T053／T054、T056、T058／T059、T071／T072、T079／T080 |
| FR-007 有界原文／來源 | T050、T052、T054、T059～T062、T068、T081 |
| FR-008 回答／引用／繁體中文 | T054、T061、T063、T081／T082 |
| FR-009 無依據不捏造 | T052、T054、T060／T061、T064、T081 |
| FR-010 錯誤可區分／恢復 | T064～T068、T070、T075、T082 |
| FR-011 十秒／busy／文字逾時 | T051、T065、T067、T071～T075、T079／T080、T082 |
| FR-012 過期結果 | T065、T067、T071～T075、T082 |
| FR-013 零其他副作用 | T054、T061、T068、T070、T074、T081／T082 |
| FR-014 本機資料流／日誌 | T050、T055～T059、T062、T066、T068、T076、T081 |
| FR-015 三路徑／停止換包 | T048／T049、T051、T067、T070、T076、T082 |
| FR-016 九秒回收 | T065、T067、T073、T076、T082 |
| FR-017 雙模型／固定版本 | T046、T048／T049、T053、T056、T064、T078 |
| FR-018 候選／來源脈絡 | T052、T055、T057～T059、T063、T064、T069 |
| FR-019 raw logit／分差／可見原文 | T052／T053、T059／T060、T062／T063、T081 |
| FR-020 後置cosine0.58 | T047、T052、T058～T060、T063、T079／T080 |
| FR-021 追溯／曝光／限制 | T045／T046、T047、T055、T063、T076、T079～T084 |
| SC-001／002 品質觀察／不捏造 | T054、T061、T063、T081 |
| SC-003 固定50題／測前gold／測後人工核對／延遲分離 | T065、T079／T080、T084 |
| SC-004 雙後端現場生命週期 | T071～T075、T082 |
| SC-005 八類故障／無寫入 | T064～T070、T082 |
| SC-006 限額／診斷隱私 | T054、T059～T062、T066、T068、T081 |
| SC-007 順序邊界／v1本機提示／TXT／別名 | T047／T051、T052／T053、T055～T060、T064、T066／T067、T069～T075 |
| SC-008 舊結果與分母不改寫 | T045、T063、T076、T079～T084 |

### Historical pending-task handoff

| 歷史未完成項（不再按舊定義執行） | 新版接替 |
|---|---|
| T026 真實包不變性 | T069 |
| T040 CPU／48/50硬門檻 | T079／T080，門檻改觀察，安全仍驗 |
| T041 召回／品質硬門檻 | T081，比例改觀察，不免除禁止捏造 |
| T042 真實生命週期 | T082 |
| T044 舊版結案 | T084，新版未完成前不倒填舊勾選 |

## Implementation Strategy and Task Summary

1. MVP先完成Phase1／2與US1（T045～T063），用合成v2資料展示完整選案順序；真實即時對話前仍須US2／US3及資產安全回歸。
2. 接著完成US2／US3離線測試，再與005進行真實v2交接，不把準備腳本移入App。
3. 完整50題量測、雙後端品質觀察與現場安全分開記錄；原始失敗及曝露狀態不覆寫，資料／操作授權依實際範圍確認。
4. 新版40項：Setup2、Foundation5、US1 12、US2 7、US3 5、Polish9；12項[P]限表列不同檔案工作。全部含序號／路徑，故事任務有US標籤，共用任務無US標籤；本輪37／40完成，T081／T082／T084仍未完成；最新離線實作與完整gate證據見quickstart。歷史44項含39已完成／5未完成，僅存檔不計新版完成率。
5. 兩功能tasks同步後，分別執行speckit-analyze檢查跨文件覆蓋與005交接，再開始implement；本次不提交、不執行實作或驗收。

## 歷史任務與證據（2026-11-05，唯讀存檔）

以下原文完整保留，包括當時尚未完成的核取狀態、門檻與平台取消紀錄；它不授權執行舊流程、不代表新版證據，也不是本輪活動任務。

````markdown
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
- [X] T039 在 `tests/test_document_retrieval.py`、`tests/test_document_worker.py` 與 `tests/test_profile_paths.py` 的既有 wheel 測試補基本安裝／rag extra／worker module 打包驗證，確保安裝後的 runtime Schema 驗證不依賴 source checkout／specs 目錄或遠端 $ref，結構規則符合 `specs/004-single-document-rag/contracts/index-manifest.schema.json`；在 `specs/004-single-document-rag/quickstart.md` 記 Python 3.12 與三平台可取得證據，確認缺套件不退出普通 App、重型 import 隔離、CPU 套件來源、原包相容矩陣；依 2026-11-05 使用者對本功能的明確指示略過 Linux／macOS，保留未驗證限制，不將略過記成通過。
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

T026 需要實際鎖定 Chroma 及外部預建測試包；可先完成其 opt-in 測試實作，再繼續不依賴真實資產的離線任務，但 T026 未取得不變性證據就不能宣告可對真實包交付。除本功能已明確略過的 Linux／macOS 外，T039 平台不可取得、T040 模型／CPU 樣本未供應、T041／T042 尚未授權或無現場配合時，相關驗收保持未完成；繼續可執行的文件／離線 gate，不能重複要求同一已授權範圍，也不能用等待時間代替授權。

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

已完成 39／44 項：T001～T025、T027～T039、T043（T039 依本功能明確授權略過 Linux／macOS）。實作及離線驗證已完成，但功能尚未結案。詳細命令、套件及限制見 quickstart 的續作紀錄；requirements checklist 保持原有 16／16，不修改其標記。

- T026：已提供明確 opt-in 真實 Chroma 不變性測試；使用者回覆索引／模型「尚未準備」，未執行，不以 fake HNSW 證據替代。
- T039：Windows Python 3.12 普通／rag 安裝、CPU import、wheel／隨包 schema／checkout 外 import 已驗證；Linux／macOS 依使用者 2026-11-05「略過Linux與Mac測試」的明確指示略過；以既有 Windows 證據完成本次個人客製化範圍，不宣稱兩平台相容或測試通過。
- T040：已建立真實 CPU 50 題 opt-in 測試入口及 47／50 失敗、48／50 通過的固定分母回歸；尚無真實模型、索引、固定題組及主機量測，未完成。
- T041、T042：等待同一份實際素材及本次文件段落外送／雲端額度／語音與機器人驗收範圍確認。前次金鑰功能授權不作為 RAG 授權；本輪不連雲端、不啟動機器人。
- T043：Ruff check／format、strict mypy（59 source files）、完整 pytest 897 passed／2 skipped、uv lock --check 已通過。兩個 skip 僅為未提供素材的 opt-in 完整性與 CPU 測試；不是實際驗收通過。其他初期失敗與每輪測試紀錄保留於 ignored cache。
- T044：待上述實際證據與平台缺項完成後，才做最終全 feature 結案；目前僅記錄已完成部分。


### 平台範圍更新（2026-11-05）

使用者明確要求本功能略過 Linux／macOS 測試。已立即停止本輪 Ubuntu 24.04 的工作區專用 uv 安裝行程，行程以 15 結束；這是依指示取消，不是相容性測試失敗。先前只確認系統 Python 3.12.3，下載／建置了鎖定依賴，安裝尚未完成，沒有執行 Linux CPU import、gate 或模型／索引測試。隔離 cache 保留，沒有更動 Linux 系統套件或 Control App 環境。macOS 未執行。

T039 按調整後的 Windows 個人客製化驗收範圍完成；產品仍使用跨平台 API，既有 CI 與索引包 validated_targets 檢查不變。剩餘 T026、T040、T041、T042、T044 仍未完成，未因平台略過而免除真實素材、CPU、對話及結案要求。

````
