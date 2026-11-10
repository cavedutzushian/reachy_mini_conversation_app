# Research: 單一預建文件 RAG 工具

**Date**: 2026-11-09 | **Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

本輪採既有程式唯讀檢查、官方 CrossEncoder 文件及已保存的離線選案紀錄，未安裝套件、下載／載入模型、開啟真實索引引擎或重新量測 CPU。以下舊日期證據保留；涉及 dense-only、門檻校準及 48／50 的舊決策已由第 10～13 節取代，不代表歷史失敗變成通過。

## 1. Chroma 既有持久化索引

**Decision**: 本機 PersistentClient 只開完整工作副本；精確引擎版號及平台合約吻合才開啟，設定 `migrations="validate"`、`anonymized_telemetry=False`、`allow_reset=False`。只 `get_collection`、讀取既有資料及 `query(query_embeddings=...)`；明確 `embedding_function=None`，不使用 query_texts 或任何建立／修改 API。

**Rationale**: 官方提供本機持久化及直接傳 embedding 的介面，但沒有承諾 PersistentClient 的完全唯讀開啟；設定中的 migration 預設為 apply。僅改用 get_collection 不足以保證不遷移或沒有引擎記帳。包必須封存完成、無待回放的 ingestion WAL；工作副本不能被用來合理化索引重建。來源包雜湊及副本邏輯文件／向量／持久索引不變性都要驗收。

**Alternatives considered**: 直接對原包開 client 可能產生寫入；自動轉換版號違反規格；Chroma server 增加部署成本；自己解析 HNSW／sqlite 文件表會綁內部實作。採官方讀取 API，缺包或不相容即 unavailable，不 get_or_create。

**Sources**: [Chroma Python client](https://docs.trychroma.com/reference/python/client)、[embedding functions](https://docs.trychroma.com/docs/embeddings/embedding-functions)、[query and get](https://docs.trychroma.com/docs/querying-collections/query-and-get)、[官方設定原始碼](https://github.com/chroma-core/chroma/blob/main/chromadb/config.py)、[維護者 storage layout](https://cookbook.chromadb.dev/core/storage-layout/)。

**Validation boundary**: 設定不等於已證明無索引變動。以實際鎖定版執行合法、失敗、重啟測試；若開啟／query 導致需建立或遷移索引，該包不得上線，不能背景修復。平台／架構不同的 HNSW 檔案也不僅憑同版號接受。

## 2. CPU dense BGE-M3

**Decision**: Sentence Transformers、本機完整 BAAI/bge-m3 snapshot、CPU float32、原模型 CLS pooling 後 L2 normalization，1024 維；不加 query prefix，不啟用 BGE-M3 sparse／ColBERT；另以 BGE-base 重排。`local_files_only=True`、`trust_remote_code=False`；模型目錄需事先供應，使用安全權重格式，不允許任意 pickle／自訂模組執行。

**Rationale**: 官方模型支援 multilingual dense retrieval，提供 Sentence Transformers 用法。官方 modules 是 Transformer → Pooling → Normalize，pooling 設定是 CLS，不能隨意換成 mean。文件與問題必須同一 revision、tokenizer、pipeline、precision 及 cosine 設定。1024 維相同仍可能完全不相容，因此額外使用檔案雜湊與固定參考向量檢查。

**Alternatives considered**: FlagEmbedding 能提供多種模式，但首版不需要其 sparse／多向量功能；量化、ONNX、OpenVINO 可能降低 CPU 成本，但需另一套輸出相容與品質評估；不預先增加。模型載入失敗不改小模型或雲端 embedding。

**Sources**: [BAAI 模型卡](https://huggingface.co/BAAI/bge-m3)、[pooling 設定](https://huggingface.co/BAAI/bge-m3/blob/main/1_Pooling/config.json)、[modules](https://huggingface.co/BAAI/bge-m3/blob/main/modules.json)、[SentenceTransformer API](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html)、[效率與精度選項](https://sbert.net/docs/sentence_transformer/usage/efficiency.html)。

**Validation boundary**: 模型權重約 GB 級不是實際 RAM 數字，沒有本機 benchmark；不可承諾既有筆電一定滿足 p95。參考向量接近只可偵測管線偏差，不證明所有問題等價；仍需人工標註與雙後端測試。

首版 worker 固定 intra-op 兩個 CPU threads、inter-op 一個，僅作用於獨立行程；這是保護即時音訊並固定驗收條件的設計預設，不是最佳效能結論。若需改動，先以同一組題目重測並更新紀錄，不自動調整模型／精度。[PyTorch thread API](https://docs.pytorch.org/docs/stable/generated/torch.set_num_threads.html)

## 3. 選用依賴及跨平台

**Decision**: 規劃 `rag` extra 候選 `chromadb==1.5.9`、`sentence-transformers==6.2.0`；實作時解析及鎖定其傳遞依賴。Windows／Linux 的 torch 採官方 CPU index、僅綁 torch 的 explicit source，不能把整個專案主要 index 改掉；macOS 用平台相容 wheel 並明確 CPU。不要加入 torchvision／torchaudio 作為直接依賴。

**Rationale**: 套件資訊顯示候選支援 Python 3.12，Chroma 有主要平台 wheel；ST 新版搭配 transformers 5 的方向亦須檢查與現有 HF hub 1.x 共存。wheel 存在不證明 SDK、鎖檔或特定預建包已相容。既有 `uv exclude-newer` 及 SDK 約束需保留，不為快速安裝取消。

**Alternatives considered**: 全域必裝會讓一般語音使用者承擔模型依賴；未限定 CPU 的套件解析可能帶入 GPU 大型套件；任意浮動版本讓預建包相容難以重現。首版使用單一固定相容組合，不維護多版本 migration。

**Sources**: [Chroma 1.5.9](https://pypi.org/project/chromadb/1.5.9/)、[Sentence Transformers 6.2.0](https://pypi.org/project/sentence-transformers/6.2.0/)、[PyTorch 安裝](https://pytorch.org/get-started/locally/)、[ST installation](https://sbert.net/docs/installation.html)。

**Validation boundary**: 本輪沒有 resolver／安裝成功證據。實作第一步必須隔離解析、wheel 安裝及 import 檢查；失敗時先解決，不把候選寫成已驗證組合，也不靜默換成別的功能。模型 snapshot revision 必須由實際交付包固定，不能使用浮動 main。

## 4. 預建包及檢索品質

**T002 實作預檢證據（2026-11-05）**：在 `cache/004-single-document-rag/dependency-probe/` 複製專案 metadata 並加入候選 extra／explicit torch CPU source，以 Python 3.12.12 解析 191 packages，`uv sync --frozen --no-dev --extra rag --no-install-project` 成功。Windows x86_64 的隔離 import 組合：Chroma 1.5.9、Sentence Transformers 6.2.0、torch 2.15.0+cpu、transformers 5.21.0、HF hub 1.33.0、Reachy Mini SDK 1.13.0、soxr 1.1.0。確認 torch.version.cuda=None、cuda.is_available()=False；在模型離線模式下 import，沒有建立 SentenceTransformer／SDK robot 實例。套件預檢日誌為 `probe-lock.log`、`probe-sync.log`、`probe-import.log`；原先沙箱禁止套件網路的解析失敗已保留，核准的公開索引連線後成功，未修改安全設定或日常環境。

此證據只證明該 Windows 組合的套件 wheel／import 可共存，尚未證明模型、索引、CPU 延遲或其他平台相容；產品 `uv.lock` 會沿用既有可相容鎖定版本，因此以 T003 產生的產品鎖檔為實際交付準據，不能把本隔離解析所有版本當成產品已升級。

**Decision**: 包含 manifest、完整 Chroma 目錄與 checksums；每段有原文、文件 ID／版本、段落 ID 及真實 locator。使用相同模型的 normalized dense embeddings 與 cosine distance。新版方案固定實驗選值及其來源，最多回三段；數值不是充分作答保證，沒有原文支持仍不得猜測。

**Rationale**: 只有向量無法還原可引用原文；文件名稱不等於版本身分。Chroma 距離不是答案機率，模型還要判斷段落能否支持回答。唯一定義的 chunk 與穩定 locator 是可核對引用的最小資料。

**Alternatives considered**: 運行時讀 PDF／OCR 或自動建置被排除；只依文件名篩選混合集合不能保證只有唯一文件；混合檢索／重排原先因延遲與範圍被排除，2026-11-09 使用者已明確納入，並保留其成本與失敗限制。本功能不交付產包工具，但提供外部建置者可遵循的合約。

**Sources**: [Chroma add data](https://docs.trychroma.com/docs/collections/add-data)、[query results](https://docs.trychroma.com/docs/querying-collections/query-and-get)、上述 BGE 模型卡。

## 5. 非同步、取消與依賴隔離

**Decision**: App-owned 持續本機工作行程，私密 pipe、最多一個實際工作且不排隊；缺選用依賴只影響工具。timeout／cancel 退役等待者，保留工作槽直到計算真正完成；App finally 受控回收行程。共享對話層對 query 的 generation／response epoch 做回覆前後檢查。

**Rationale**: `asyncio.to_thread()` 的等待者取消不會終止已在執行的 CPU 工作。單純 async lock 的 finally 放行會讓後續工作累積；ThreadPoolExecutor 的執行緒亦可能拖住退出。獨立 worker 同時隔離 import／冷啟動，並可在 App 停止時回收；不是提供新服務或通用排程器。

**Alternatives considered**: event loop 直接 encode 會妨礙音訊；每次新 process 反覆載入模型；只靠 BackgroundToolManager 預設 timeout 太長；單背景 thread 較少協定，但對卡住的 native 計算沒有可回收邊界。

**Sources**: [Python asyncio task/cancellation](https://docs.python.org/3.12/library/asyncio-task.html)、[executor shutdown](https://docs.python.org/3.12/library/concurrent.futures.html)、[subprocess lifecycle](https://docs.python.org/3.12/library/subprocess.html)。

## 6. 現有 Tool 接線與日誌檢查

**Decision**: 新 Tool 不加入 SystemTool；經既有人格 toolset 啟用，runtime 由 ToolDependencies 注入。使用固定 `error` 字串碼以穿過現有 manager，並針對 RAG 呼叫修正共同日誌與退役判斷。

**Rationale / repository evidence**:

- `tools/idle_do_nothing.py` 是既有 subclass／schema／async 字典回傳範例；不照抄其舊 Any／Dict 到新公共型別。
- `core_tools.py` 會重建工具 registry，所以不能把單 worker 鎖存在每個 Tool 實例。其 malformed JSON 與 dispatcher 例外會印 raw payload，需選擇性遮蔽。
- `personality.available_tool_catalog()` 掃描 tools 模組，支援檔放在 package 根。
- `background_tool_manager.py` 遇到 `error` 只保留字串；新增另一個 `code` 欄並不會自然到達模型。
- HF 會 INFO 記原參數、DEBUG 記完整工具結果；result callback 只靠連線所有權不足以擋同連線的插話舊結果。
- Gemini 已有 ToolInvocation.response_epoch，但結果回呼尚未用它攔截所有 RAG 過期結果；duplicate call 的 result reuse 也要受退役規則限制。
- `prompts.get_session_instructions()` 已由兩後端使用，是文件回答規則的共同入口，不另寫第二份人格或檢索對話服務。

**Alternatives considered**: 全面重寫工具 manager／全部工具日誌超出本功能；只在新 Tool 中不 log 仍有上游洩漏；只有回傳時才看 `_owns_connection()` 擋不住同 session 的取消。採針對 RAG 的最小共用修正及回歸測試。

## Resolved unknowns and remaining evidence

包格式、啟動配置、model pipeline、worker 所有權、固定錯誤碼、回傳上限、來源／日誌邊界均已定義；下列補充決策同步 2026-11-05 澄清。仍須實作取得的證據：依賴鎖定共存、真實包不變性／平台、模型 snapshot 與實際 CPU 資源、新方案回放一致性與非阻擋品質量測及服務／現場驗收。這些不是已通過結果；不能以文件檢查取代它們。

## 7. 外部包的完整資料格式（U1）

**Decision**: 新增 [index-manifest.schema.json](contracts/index-manifest.schema.json)，採 JSON Schema 2020-12；固定所有巢狀欄位、required／禁止 null、未知欄位拒絕、檔案清單 path／sha256 物件、平台 enum、精確版本與模型 revision。搭配 index-package.md 的額外語意檢查（hash、唯一來源、路徑、非有限數、向量、真實引擎設定）。沿用既有 jsonschema，不新增套件、服務或產包器。

**Rationale**: 外部包必須在 App 執行前就可交付，不能讓產包者猜清單形狀。Schema 可檢查資料形狀，但不能證明檔案存在、可信來源或 Chroma 沒有寫索引，這些仍要分別驗證。規則只用本檔 $defs，不在執行時抓取外部 schema。

**Alternatives considered**: 只有欄位表不足以固定巢狀結構；增加產包 CLI 超出範圍；只提供一份含虛構 hash／向量的範例容易被誤當可用包。選擇完整 schema 加語意條件，驗證時用記憶體中的結構樣本，明示不是實際可載入資產。

**Source**: [JSON Schema 2020-12 Core](https://json-schema.org/draft/2020-12/json-schema-core)。

## 8. 逾時只顯示文字及所有權分離（U2）

**Decision**: 遵使用者 B 選擇，document_timeout 在原回合有效時只顯示一次本機繁體中文文字，不觸發語音。永久退役背景答案與一次 notice 的所有權分開；正常成功仍 needs_response=true。HF 完成 function output 但 timeout 不貢獻 batch follow-up；Gemini 針對 RAG 宣告 NON_BLOCKING，成功 WHEN_IDLE、timeout SILENT，固定錯誤碼不得被通用 error 吃掉。

**Rationale**: 原有 HF 錯誤會強制 follow-up，Gemini 的 _silent_tools 則是整工具層級；單把 needs_response 設 false 既可能沒擋錯誤語音，又會讓成功結果不回答。既有 AdditionalOutputs 可顯示本機文字，無須模型朗讀或另一條重複 transcript。官方 Gemini 工具文件描述 NON_BLOCKING 及結果 scheduling，但所選模型的實際支援仍需 setup／wire／服務驗證。

**Alternatives considered**: 使用者已否決逾時語音；不回 function response 可能留下懸而未決 call；用同一 retired flag 會把合法 notice 一起丟掉；只靠 system prompt 沒有可測的協定控制。不自動換模型或 provider 來繞過不相容。

**Source**: [Gemini Live asynchronous tools](https://aistudio.google.com/docs/live-api/tools#async-function-calling)，以及 `huggingface_realtime.py::_handle_tool_result`、`gemini_realtime.py::_declarations/_handle_tool_result/_function_response` 的唯讀檢查。此為設計，未呼叫實際 API。

## 9. 固定關閉與驗收／輸入規則（A1／A2／I1）

**Decision**: 遵使用者 A 選擇，以 monotonic 總九秒限制 worker 關閉，分段最多 5／2／2 秒；未確認退出就保留副本、記錄清理未完成，不無限 join。不把 RAG 期限擴張為整個 App 關閉保證。輸入先計原始字串（含空白）<=500 code points 再 trim；固定效能 50 題的分母不減，快速失敗不算成功；原 48／50 要求已改為觀察，見第 12 節。

**Rationale**: 固定時限才能驗證退出；在 child 仍可能持有檔案時刪副本會引起清理競態。原始輸入長度與 schema maxLength 一致可避免雙後端差異；成功率是取回段落而非完成回傳任意錯誤，不能用低延遲失敗美化 p95。

**Alternatives considered**: 四秒／二十秒已由使用者選擇九秒取代；先 trim 才限長與原始 schema 不一致；只計成功樣本的 latency percentile 會掩蓋失敗，故 percentile 僅作額外觀察，原 48／50 已不作阻擋，全部 <=10 秒完成或明確逾時與晚到退役仍保留。

**Validation boundary**: 以上五項分析問題在 Phase 0／1 設計已明確化，不代表舊 tasks 已同步，也不代表 shutdown、模型／索引或雙後端語音已測；上述原始待辦已納入新版tasks；本輪U1／U2新增設計仍須同步任務再analyze，舊結果不當新版證據。

## 10. 最終選案與驗收語意（2026-11-09）

**Decision**: 以 [final-scheme.json](../../cache/005-prepare-rag-assets/calibration/bge-base-final-selection-20261109/final-scheme.json) 及同目錄 [report.md](../../cache/005-prepare-rag-assets/calibration/bge-base-final-selection-20261109/report.md) 為選案依據，採章節／來源別名、精確 dense10＋正分 BM25 top10、等權 RRF60、完整五候選 BGE-base 重排。固定 raw logit 3.486859679222107、附加分差4、三段／2000字元，再套 cosine 0.58，不限制同父章節、無群組分差。完整順序見包契約。

**Rationale**: 使用者明確選取先前最佳實驗組合並取消檢索品質比例選用阻擋。0.58 由所需最大距離約0.5759704113006592向上取兩位小數，保留既有84個正例命中及131個回傳段落。200題全部已曝光，84／100正例、2／100負例誤放行、127／131段落支持只屬回放結果，非盲測、非原驗收通過。288段與實驗別名屬該版 example.md，不能成為所有文件的常數。

**Alternatives considered**: dense-only、短段落重排、其他模型及充分性規則／模型均不是本輪最終方案；不因品質門檻取消加入雲端審核或允許回答捏造。保留全部舊實驗資料與分母。

## 11. 可重現計算與依賴

**Decision**: 沿用 rag extra 的 Chroma1.5.9／Sentence Transformers6.2.0 及產品 CPU torch；CrossEncoder 已在既有套件，BM25 以標準庫 Counter／math／re 運算，無新直接依賴。模型固定 BGE-M3 `50f9396f75618b3389c1fd1068a1ff58dc7b5b26` 及 BGE-base `2cfc18c9415c912f9d8155881c133215df768a70`；CPU float32、兩 intra-op／一 inter-op，執行緒設定移至 worker 入口一次，不因兩模型重複設定 inter-op。

**Rationale**: 本機選案腳本 `cache/005-prepare-rag-assets/calibration/bge-base-best-retest-20261109/rerun_once.py` 用 `1-vectors@query` 的精確 cosine，而非 Chroma ANN。因此 worker 從已核對集合讀取既有向量並計算 exact dense10，包含 lexical-only 候選距離；讀矩陣與打分不建立新索引。BM25 預建 TF／DF／長度／avgdl，runtime 只 tokenize query 與打分。Tokenizer 為 casefold ASCII字母數字與 CJK U+3400..U+9FFF 二／三字組，query terms去重，k1=1.2、b=.75、正 log1p IDF；所有排名同分以穩定 ID。

BGE-base 使用 Identity activation 的原始 logit，pair最大512 tokens、batch4、保留query與來源右側前綴的offset對照；完整候選不拆成多個短窗取最大值。評分未看到的原文不能引用，裁切明示。兩模型均 local_files_only、trust_remote_code=False、安全權重，無自訂模組與pickle fallback。套件 API 設計由 [官方 CrossEncoder 文件](https://sbert.net/docs/package_reference/cross_encoder/model.html) 支持；本輪精確 revision 的供應證據以既有離線紀錄／receipt 為準，未重新連線下載驗證。

**Alternatives considered**: Chroma ANN 直接取10會改變候選且未重校準；rank-bm25 或 FlagEmbedding 增加不必要依賴；跨多短窗最高分、量化、GPU、其他模型不是選定組合。API 可用性仍需既有鎖檔的隔離回歸，文件不能取代安裝測試。

## 12. 新包、模型配置與可觀察效能

**Decision**: schema_version=2、單一新版讀取路徑；v1明確拒絕並請離線重產，不自動轉換。保留原嵌入／索引路徑，新增 REACHY_MINI_DOCUMENT_RERANKER_PATH，任一缺漏 not_ready、一般對話不受影響。v2包完整保存來源範圍／章節、可選人工別名證據與明示空清單、預建BM25、兩模型固定版本、完整設定／策略與選值來源。005分角色準備兩模型後離線產包，共三步；必須明確選取版本化方案，不能默認套用或要求品質合格證明。

**Rationale**: 舊schema與reader無法驗證混合檢索設定，不能僅將max_distance改為0.58。別名只用原有標題及可核對同文件／版本／範圍的人工清單；TXT無標題按單範圍與真實段落／行號處理。新版來源與BM25資產缺漏時 unavailable，不讀原文補建或降級。

**Alternatives considered**: 維護雙reader增加未選用舊流程；共用模型根目錄迫使搬移現有模型；自動擷取別名增加使用者未選取的推測。五秒／95%改為完整50題固定主機的觀察，不是阻擋；p50／p95／max、各失敗數與RSS分開記錄。十秒文字逾時、退役、單工作、九秒回收、來源與隱私仍是安全要求。

## 13. 設計後檢查與待取得證據

**Decision**: v2選案設計與004／005基礎tasks已同步；產品仍v1，本輪新增U1／U2的設計與後續任務須分開追蹤。先協調兩功能契約，再新增實作任務，重跑analyze及必要完整gate。無未解決的使用者決策或憲章例外。

**Rationale**: 可重用舊worker／Tool／退役控制，但舊離線通過與已曝光模型試驗不證明新版包、雙後端引用、完整流水線CPU或私密資料外送已驗收。新增測試應對準v1拒絕、三路徑／雙模型、候選順序與邊界、可見原文及不變性，不能用改分母改寫舊失敗。

**Alternatives considered**: 本輪啟動App、下載、直接改產品schema或勾完任務均超出plan範圍。Linux／macOS保持使用者要求略過及未驗證限制，程式跨平台與既有CI不變。

## 14. CPU樣本的人工支持判讀（U1，2026-11-09）

**Decision**: 測前固定50題問題、可答性、必要資訊與原文證據／定位，綁定文件版本／digest及題組識別；測後人工只依實際回傳且評分可見的原文判斷全部必要資訊是否齊全。不足／無法確定不算成功。格式、凍結／更正規則與結果欄位見 [cpu-evaluation](contracts/cpu-evaluation.md)。工具延遲在執行時以monotonic固定，人工核對時間另列，不進查詢延遲。

**Rationale**: 成功工具形狀與分數不能判斷原文充分性；沒有測前證據會讓成功分母隨觀察結果改變。人工標註屬離線驗收，不是執行期規則、另一模型或雲端審核。全部50題保留；五秒／比例仍僅觀察，不恢復舊門檻。

**Alternatives considered**: 只在測後自由判讀較難重現；用chunk_id命中當作足夠會漏掉裁切和多資訊問題；自動充分性模型超出使用者決策。錯標註如實標為不可判定，保留原run／分母；修訂題組另版另run，不能覆寫舊失敗。

## 15. 舊包本機提示與私密原因（U2，2026-11-09）

**Decision**: worker確認manifest整數schema_version=1時，於開Chroma前回私密failure reason=legacy_package及document_unavailable；runtime以宣告的typed本機屬性快取，對外query與模型結果仍只有六碼。共享handler從deps.document_retrieval取得此原因，僅真實有效的unavailable通知可經既有DocumentOutput／AdditionalOutputs顯示固定舊包文字；每invocation獨立legacy_notice_sent，與timeout_notice_sent分開。初始化thread不直接發提示；首問not_ready後非同步載入失敗不復活舊回合，下次明確有效查詢才可提示。

**Rationale**: 本機 `_document_result()` 已持有invocation generation／response_epoch，`emit()`會丟棄失效的DocumentOutput；Gemini繼承共享行為。既有通用unavailable不含格式原因，不能靠模型猜或把所有故障都說成v1。小型typed私密原因避免更動Tool API與provider協定。

**Alternatives considered**: 新增公開錯誤碼、把reason塞進工具結果、傳原始例外／路徑、啟動thread直接推UI、依字串猜舊版，均不採用。無效query／工具停用／通用故障／結果驗證合成的unavailable不得誤發提示。固定文字不新增TTS或response.create，不另追加逐字稿；一般unavailable對話行為不變，timeout專用消音規則也不變。

**Repository evidence**: 唯讀檢查document_worker.py::main、DocumentRuntime::_run_worker/query、huggingface_realtime.py::ToolInvocation/_document_result/emit。這是設計推導，不是本輪實作或雙後端驗收。無新依賴／SDK變更／憲章例外；無待使用者決定事項。
