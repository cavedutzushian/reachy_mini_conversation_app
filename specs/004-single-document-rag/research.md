# Research: 單一預建文件 RAG 工具

**Date**: 2026-11-05 | **Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

研究採既有程式唯讀檢查及官方文件；未安裝套件、下載模型、打開實際文件包或量測 CPU。下列選擇完成設計澄清，實作驗證不可省略。

## 1. Chroma 既有持久化索引

**Decision**: 本機 PersistentClient 只開完整工作副本；精確引擎版號及平台合約吻合才開啟，設定 `migrations="validate"`、`anonymized_telemetry=False`、`allow_reset=False`。只 `get_collection`、讀取既有資料及 `query(query_embeddings=...)`；明確 `embedding_function=None`，不使用 query_texts 或任何建立／修改 API。

**Rationale**: 官方提供本機持久化及直接傳 embedding 的介面，但沒有承諾 PersistentClient 的完全唯讀開啟；設定中的 migration 預設為 apply。僅改用 get_collection 不足以保證不遷移或沒有引擎記帳。包必須封存完成、無待回放的 ingestion WAL；工作副本不能被用來合理化索引重建。來源包雜湊及副本邏輯文件／向量／持久索引不變性都要驗收。

**Alternatives considered**: 直接對原包開 client 可能產生寫入；自動轉換版號違反規格；Chroma server 增加部署成本；自己解析 HNSW／sqlite 文件表會綁內部實作。採官方讀取 API，缺包或不相容即 unavailable，不 get_or_create。

**Sources**: [Chroma Python client](https://docs.trychroma.com/reference/python/client)、[embedding functions](https://docs.trychroma.com/docs/embeddings/embedding-functions)、[query and get](https://docs.trychroma.com/docs/querying-collections/query-and-get)、[官方設定原始碼](https://github.com/chroma-core/chroma/blob/main/chromadb/config.py)、[維護者 storage layout](https://cookbook.chromadb.dev/core/storage-layout/)。

**Validation boundary**: 設定不等於已證明無索引變動。以實際鎖定版執行合法、失敗、重啟測試；若開啟／query 導致需建立或遷移索引，該包不得上線，不能背景修復。平台／架構不同的 HNSW 檔案也不僅憑同版號接受。

## 2. CPU dense BGE-M3

**Decision**: Sentence Transformers、本機完整 BAAI/bge-m3 snapshot、CPU float32、原模型 CLS pooling 後 L2 normalization，1024 維；不加 query prefix，不啟用 sparse／ColBERT／rerank。`local_files_only=True`、`trust_remote_code=False`；模型目錄需事先供應，使用安全權重格式，不允許任意 pickle／自訂模組執行。

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

**Decision**: 包含 manifest、完整 Chroma 目錄與 checksums；每段有原文、文件 ID／版本、段落 ID 及真實 locator。使用相同模型的 normalized dense embeddings 與 cosine distance。manifest 的門檻由外部校準後固定，最多取三段；低於支援程度的問題如實拒答。

**Rationale**: 只有向量無法還原可引用原文；文件名稱不等於版本身分。Chroma 距離不是答案機率，模型還要判斷段落能否支持回答。唯一定義的 chunk 與穩定 locator 是可核對引用的最小資料。

**Alternatives considered**: 運行時讀 PDF／OCR 或自動建置被排除；只依文件名篩選混合集合不能保證只有唯一文件；更大的 top-k、混合檢索、reranker 增加延遲及調參範圍。本功能不交付產包工具，但提供外部建置者可遵循的合約。

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

包格式、啟動配置、model pipeline、worker 所有權、固定錯誤碼、回傳上限、來源／日誌邊界均已定義；下列補充決策同步 2026-11-05 澄清。仍須實作取得的證據：依賴鎖定共存、真實包不變性／平台、模型 snapshot 與實際 CPU 資源、標註題門檻及服務／現場驗收。這些不是已通過結果；不能以文件檢查取代它們。

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

**Decision**: 遵使用者 A 選擇，以 monotonic 總九秒限制 worker 關閉，分段最多 5／2／2 秒；未確認退出就保留副本、記錄清理未完成，不無限 join。不把 RAG 期限擴張為整個 App 關閉保證。輸入先計原始字串（含空白）<=500 code points 再 trim；固定效能 50 題至少 48 題五秒內取得段落，所有快速失敗皆不計成功且分母不減。

**Rationale**: 固定時限才能驗證退出；在 child 仍可能持有檔案時刪副本會引起清理競態。原始輸入長度與 schema maxLength 一致可避免雙後端差異；成功率是取回段落而非完成回傳任意錯誤，不能用低延遲失敗美化 p95。

**Alternatives considered**: 四秒／二十秒已由使用者選擇九秒取代；先 trim 才限長與原始 schema 不一致；只計成功樣本的 latency percentile 會掩蓋失敗，故 percentile 僅作額外觀察，硬門檻為 48／50 與全部 <=10 秒。

**Validation boundary**: 以上五項分析問題在 Phase 0／1 設計已明確化，不代表舊 tasks 已同步，也不代表 shutdown、模型／索引或雙後端語音已測；下次 tasks 必須補上述測試與 FR-016 對應後再 analyze。
