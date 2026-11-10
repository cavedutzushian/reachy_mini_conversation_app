# Contract: 外部預建索引包 v2

本文件定義外部產包者的交付邊界，**不交付建索引／文件解析程式**。App 不在啟動、對話或修復流程建立文件向量、BM25 統計／索引。v2 採用本輪已選定的混合檢索／重排方案；舊 v1 一律拒絕並提示停止 App 後離線重產，不自動轉換、遷移或保留 dense-only 分支。這是設計合約，不代表現有讀取程式已支援 v2。已確認v1的本機專用提示依 [工具合約](search-document.md#legacy-v1-local-notice) 傳遞，不新增對外工具錯誤碼。

## Layout and startup configuration

```text
<designated-package>/
├── manifest.json
├── retrieval/
│   ├── chunks.jsonl
│   └── bm25.json
└── chroma/
    ├── chroma.sqlite3
    └── <既有持久索引所需的完整檔案與目錄>
<local-bge-m3-model>/
└── <相同 immutable revision 的完整模型／tokenizer／ST 模組檔案>
<local-bge-base-reranker>/
└── <相同 immutable revision 的安全權重／tokenizer／配置>
```

啟動環境／既有 `.env` 提供 `REACHY_MINI_DOCUMENT_INDEX_PATH`、`REACHY_MINI_DOCUMENT_MODEL_PATH`、`REACHY_MINI_DOCUMENT_RERANKER_PATH`；預設空白。第一個目錄是唯一包，不是待掃描的文件資料夾；後兩個分別是完整本機嵌入及重排模型，不是遠端 model ID。任一配置缺漏回未就緒；不自動搜尋模型快取。005 預設分別準備至 `external_content/bge-m3-model/`、`external_content/bge-reranker-base-model/`，完成後顯示路徑，由使用者明確設定，不代改 `.env`。工具不能覆寫任何路徑。停止 App 後換完整包再重啟，沒有熱更新、上傳或管理 endpoint。

## Manifest required fields

機器可讀格式以 [index-manifest.schema.json](index-manifest.schema.json)（JSON Schema 2020-12）為準，以下表格與額外語意檢查共同構成 v2 合約。Schema 只描述資料，不是產包器或執行期下載入口；驗證時所有 `$ref` 只解析本檔的 `$defs`，使用既有 jsonschema 套件，不讀遠端 schema。所有物件拒絕未知欄位、所有 required 欄位不得省略／null，不替缺欄補預設，也不自動升級。

| 欄位 | 契約 |
|---|---|
| schema_version | 整數 2，拒絕 v1 及未知版本，不自動升級 |
| index_version | 非空 <=128 安全字元；外部建置版本 |
| document | `id`、`title`、`version`、`source_sha256`，約束見 data-model |
| engine | `name=chromadb`、精確 `version`、`collection`，不得讓使用者 query 改選 |
| producer | `os`、`architecture`；可辨認的建置平台 |
| validated_targets | 真正完成開啟／查詢／不變性驗收的 `os`／`architecture` 組合；未列目標拒絕 |
| snapshot_complete | true；引擎已正常關閉、flush，無待套用 ingestion log、migration 或重建需求 |
| chunk_count | 正整數，與 collection 全部 row 一致；僅一個使用者 collection |
| files | chroma 內完整相對檔案清單及 SHA-256；manifest 本身不自我 hash |
| embedding | 見下節；必須吻合本機模型與實際集合 metric／向量 |
| strategy / chunking | 固定策略與切段／來源脈絡版本、長度／重疊參數；見下節 |
| assets | `retrieval/` 下完整檔案清單及 SHA-256；必含 `chunks.jsonl`、`bm25.json`，不得有未列檔 |
| bm25 | 固定 tokenizer、k1=1.2、b=0.75、positive IDF、預建統計；App 不重建 |
| retrieval | dense10／正分 BM25 10、等權 RRF60、完整五候選及固定後置 cosine 上限 0.58 |
| reranking | BGE-base 固定版本、檔案清單、精確套件版本、CPU／float32、原始 logit 與選段設定 |
| provenance | 使用者明確選取的方案與來源紀錄雜湊、200 題曝光狀態、原分母／失敗及已知限制；不是品質通過證明 |
| reference | 非敏感 `query`（<=500 code points）及 `embedding`（1024 有限 float），測試模型載入後一致性 |

安全字串欄位不接受控制字元／本機絕對路徑；文件／索引 ID 使用英數、`-`、`_`、`.`，title／locator 可用原語言文字。manifest 最大 16 MiB、UTF-8 JSON、不得重複 key；限制不符就是不支援的包，不能略過檢查。此為交付格式上限，非文件段落數的固定上限。

files 不含逃逸路徑、連結、junction 或不明額外檔；不在 App 內解壓縮。預建者需確保傳輸／複製的是已封存 snapshot；`snapshot_complete` 宣告不取代實測。不要手工刪掉引擎必要檔來假造乾淨快照。

### Exact encoding and semantic checks

- `files`、`assets.files`、`embedding.files` 與 `reranking.files` 均為非空陣列，每個元素只有 `{"path": "相對路徑", "sha256": "64位小寫十六進位"}`。前者相對包根的 `chroma/`，例如 `chroma.sqlite3`；`assets.files` 相對 `retrieval/` 根，模型清單各相對其角色模型根，例如 `1_Pooling/config.json`。不要在清單 path 再加各自根的前綴，不將模型檔加入索引清單。每一清單涵蓋其根下所有常規檔案，不包含 manifest；拒絕相同路徑不同 hash，不能只靠 uniqueItems。
- 路徑只用 `/` 分隔，禁止空段、`.`／`..` 段、前導 `/`、反斜線、冒號、控制字元及 URI。解析後不得逃出各自根目錄，禁止連結／junction；拒絕目標平台正規化後碰撞的名稱（包括 Windows 大小寫／尾端空白或點的別名），不能把它們覆寫成同一檔。
- SHA-256 全部為 64 位小寫 hex；`embedding.revision` 與 `reranking.revision` 是各模型 snapshot 的 40 位小寫 Git commit hex，不接受 main、tag 或模型路徑。`source_sha256` 是外部對原文件原始 bytes 的 digest；App 不需取得原文件。
- `producer` 與 `validated_targets` 元素形狀固定為 `{"os":"windows|linux|macos", "architecture":"x86_64|aarch64"}`，字串填單一 enum 值而不是含 `|` 的文字。Windows／Linux／Darwin 名稱映射為 windows／linux／macos，AMD64／x86_64 映射 x86_64，ARM64／aarch64 映射 aarch64；其他值拒絕。producer 是來源資訊，runtime 必須精確出現在 validated_targets；列出目標不是實測證據，驗收仍須記錄包 digest／平台的實際開啟與不變性結果。
- 引擎／ST／torch／transformers 版本填實際安裝的完整版本字串（包括如 `+cpu` 的 local suffix），逐字比對；不接受版本範圍或自動忽略 suffix。若目標平台需要不同版本組合，外部交付相容的單文件包；App 不改 manifest 或重建索引。collection 另須符合鎖定 Chroma 的名稱規則，文件 version／ID／index_version 使用 schema 的安全 identifier，不混用標題。
- JSON 為 UTF-8（不接受 BOM），整檔 <=16 MiB；解析前檢查 bytes 大小，拒絕重複 key、NaN／Infinity／非有限數或數值溢位。JSON Schema 之外，reference.query 依工具相同順序檢查原始 500 code points 上限、再 trim 檢查有效內容；reference.embedding 也須非零／L2 norm 誤差 <=1e-4。
- schema 驗證不等於資料相容：仍須檔案真實存在與 hash 相符、必要模型模組／權重齊全、Chroma 真實 metric、count／唯一來源、所有 row 向量、來源／BM25 資產一致性、reference 向量及平台檢查。缺任何檢查不能直接 ready；未知 schema_version 整包拒絕。

## Embedding compatibility

`embedding` 必須記錄：

- `model_id="BAAI/bge-m3"`、固定 `revision="50f9396f75618b3389c1fd1068a1ff58dc7b5b26"`、模型所需全部檔案的相對路徑／SHA-256（包括 tokenizer、ST modules／pooling／normalize config、安全權重）。
- `sentence_transformers_version`、`torch_version`、`transformers_version`，與該包認可的精確 runtime 組合一致；不要要求安裝文件產包者無關工具。
- `mode="dense"`、`dimension=1024`、`precision="float32"`、`pooling="cls"`、`normalize=true`、`query_prefix=""`、`document_prefix=""`、`max_seq_length=8192`、`metric="cosine"`。

使用 ST 原模型 pipeline，不換 mean pooling，不重正規化原文／改字體。原有長度限制按官方 tokenizer 設定；無效／超過問題字元上限由工具拒絕。CPU 執行明確 float32、禁用自動 device／CUDA／MPS、remote code 與模型下載。模型只接受預期內建 Transformer／Pooling／Normalize 模組及安全權重；trust_remote_code=false 本身不等於可任意信任 model directory。

驗證模型與檔案 hash 後，用 reference.query 產生同設定向量，檢查維度、有限數、非零及 L2 norm；與 reference.embedding 的 cosine 差距初始容許 <=1e-5。這是管線相容檢查，不是檢索分數門檻；若實際 CPU 浮點差異超出，須重新評估並記錄證據，不運行時放寬。

## Prebuilt strategy, source assets and lexical data

本輪策略固定 `strategy.id=chapter-alias-hybrid-bge-base-v1`、`chunking_version=chapter-source-v1`、`source_context_version=source-title-alias-v1`、`selection_version=rerank-budget-then-distance-v1`。005 必須明確選取完整版本化方案才可產包；未選取就停止，不自動套用預設或要求逐項抄寫參數。所有文件向量與 lexical 資料於離線產包時生成，App 只讀既有資料及計算本次 query 分數。

- `retrieval/chunks.jsonl`：每行一個固定物件，欄位為 `chunk_id`、`document_id`、`document_version`、`start`、`end`（解碼後原文 code point 半開區間）、`line_start`、`line_end`（真實一基行號）、`text`、`headings`、`aliases`、`context`、`alias_context`、`model_text`、`model_text_sha256`。ID 與 Chroma row 一對一，順序採原文位置／ID；同一原始父段落也是 dense 向量身分，不產生重排視窗或另一份向量。每個 offset 必須非負、end>start、end-start=len(text)，行號順序正確；005 發布前以唯一原檔逐項核對，App 核對資產與 collection 及區間間重疊內容一致，不把 hash 當原文真實性證明。
- `headings` 是原始章節階層的物件清單，每項只有 `text`、`start`、`end`、`line_start`、`line_end`，定位須指向該標題原文，且層級／範圍歸屬由離線產包驗證。額外 `aliases` 可為空；每項只有 `text`、`evidence_start`、`evidence_end`、`evidence_line_start`、`evidence_line_end`、`scope_start`、`scope_end`，保存同文件／版本的原文證據及適用章節範圍。人工清單缺來源、版本不符、字串不符或套到無關範圍均拒絕，不接受「文件其他地方存在」作任意配對。相同別名在多段的重複是已驗證範圍展開，不是自動生成。
- `chapter-source-v1`：Markdown 取真正 ATX 章節邊界（忽略 fenced code 內的假標題），保留章節前非空前言；無標題 TXT 為單一文件範圍。以嵌入 tokenizer 的 300 token 為目標、30 token 重疊，優先在後半段的真實空行邊界切分，不漏掉過長段落或尾段。全文都要被原文範圍覆蓋；重複標題以實際位置區別。新增 TXT／前言／code fence 的通用處理須另驗證，不宣稱它們曾包含在 288 段實驗中。
- source context 取末三層原始標題、以 ` > ` 連接，上限 64 embedding tokens；別名按人工清單順序以 ` / ` 連接，上限 48 tokens。沿用實驗的保留尾端 token 邊界策略；無標題時使用文件名稱。`model_text` 為 `脈絡：{context}\n`，有別名時再接 `戰隊別名：{alias_context}\n`，最後接 `原文：\n{text}`。標籤只是固定策略字串，不表示工具只限戰隊文件；不能按文件任意換模板卻沿用同一策略版本。完整輸入最多 512 embedding tokens（模型本身上限仍 8192），必要時縮短本段並以後續段落保留未覆蓋原文；context／別名不得冒充可引用原文。
- `retrieval/bm25.json` 是 UTF-8 JSON，拒絕重複 key／非有限數；固定欄位 `version="bm25-prebuilt-v1"`、`chunk_ids`、`term_frequencies`、`document_lengths`、`document_frequencies`、`average_document_length`。chunk_ids 及其 TF／length 陣列順序與 chunks 完全相同，N=count；TF／DF 為正整數，length 可為零且等於 TF 總和，DF 不超過 N、等於含該詞的段落數，avgdl 等於 length 平均。若全部無 lexical token，avgdl=0、DF 空，查詢 lexical 分數皆0，禁止除零或臨時建索引。
- tokenizer `ascii-cjk23-v1`：先 casefold 取 `[a-z0-9]+`；另對原輸入每個 `[\u3400-\u9fff]+` 連續序列取所有相鄰二字／三字 n-gram。不翻譯、同義詞擴增或中文斷詞；query 重複詞只計一次。文件 TF 來自完整 `model_text`，標題／別名影響檢索但不增加引文。
- BM25：`sum(log(1+(N-df+0.5)/(df+0.5))*tf*(k1+1)/(tf+k1*(1-b+b*dl/avgdl)))`，固定 k1=1.2、b=0.75。只讀預建 TF／length／DF／avgdl；開啟時驗證既有資料的一致性不代表可於 App 補建缺失資料或重算後取代資產。不得使用 pickle、任意反序列化類別或遠端 tokenizer。

## Hybrid retrieval, reranking and selection

1. 一次以相同 BGE-M3 管線編碼有效 query。從已核對的 Chroma row 讀取預建 parent 向量，在 CPU 計算 exact cosine（`1-dot(normalized_parent,normalized_query)`），取前十，以距離升序／chunk_id 升序解同分。不使用 ANN 近似候選替換原實驗的 exact top10，不建立另一份向量索引。完整向量可於 worker 載入一次保留；資源不足明確不可用，不改成另一檢索策略。
2. BM25 正分前十以分數降序／chunk_id 升序排序；與 dense 前十以等權 `1/(60+rank)` 相加（rank 自1），依總分降序／chunk_id 升序取最多五個不同 parent。不足不重複湊數。額外候選的 parent cosine 從既有向量計算，不能拿 RRF／BM25／logit 當 distance。
3. 本機 BGE-base 使用完整 `model_text` 候選配對 query、CPU float32、Identity activation 原始有限 logit、batch_size=4、max_pair_tokens=512，不拆成短視窗再取最大值。先保留完整 query，剩餘 pair token 預算只從候選右側裁切，利用 tokenizer offset mapping 保留原文連續前綴；若完整query已超出pair預算，整次回無依據，不靜默裁短query；無原文可見則不回傳該段，不補新候選。回傳及支持判定只可用實際評分可見原文；真實 locator 跟隨可見範圍，裁切標記 true，不回傳模型沒看過的尾端。
4. 按 raw logit 降序／chunk_id 升序，第一名至少 `3.486859679222107`，附加段也至少此值且相對第一名分差最多4。最多三段，依序套用總2,000 code point原文預算，必要時只取連續前綴並標記裁切。沒有通過者回無依據；不限同父章節、最低群組分差停用，不新增充分性規則或審核模型。
5. **最後**才套用 parent cosine<=0.58：既定第一名超限則整次無依據；否則移除超限附加段，不改選第一名、不補段、不重新排序、不因移除而重分配文字預算。等於上限仍保留。此值不是機率、獨立可信度、dense-only 通用門檻或新文件已校準證明。

### Reranker compatibility and provenance

`reranking` 固定 `BAAI/bge-reranker-base` revision `2cfc18c9415c912f9d8155881c133215df768a70`，本機目錄與嵌入模型分開，清單核對全部必要安全權重、原生 tokenizer／配置；拒絕 pickle／任意程式碼、auto_map、連結與缺檔。以 local_files_only、trust_remote_code=false、use_safetensors、device=cpu 載入；不自動降低精度／換模型。精確 ST／torch／transformers 版本須與嵌入同一已驗證 runtime 相容。005 為各角色提供可驗證 receipt；receipt 識別、revision、權重雜湊與 manifest 一致才可使用，receipt 形狀由 005 計畫同步，舊僅嵌入 receipt 不能冒充重排就緒。發布前各模型均完成無網路 CPU 驗證，重排以固定非敏感配對確認輸出有限原始分數，不以該分數冒稱品質通過。

`provenance` 保存明確選取的 `bge-base-final-selection-20261109`、選值記錄 `final-scheme.json`／`report.md` 的 SHA-256、200題皆曝光及歷史分母／限制。記錄本例來源摘要 `e623baa45cf2d31a72d964b6f5beaaddb082dfa81671e4b8cc466e7994bdf57e` 與包內實際 document.source_sha256 分開；新文件不必冒稱是 example.md。0.58 由既有正例所需上限約0.5759704113006592向上取兩位小數，歷史84/100正例、2/100負例誤放行、127/131段落支持，quality_gate_passed=false；原失敗保留，不稱新盲測。已知誤放行包括錦和量具品牌／型號／校正日期、中和與Team399交流確切時刻；known_limits 必須保存兩項及未校準新文件／效能限制。records 每個名稱恰有一筆且 hash 對應選定原始紀錄；reader以隨策略交付的固定紀錄digest核對，不從cache取檔或接受任意宣稱的hash；可攜包保存來源身分／摘要與完整必要參數，不要求使用者或 App 擁有工作區 cache 路徑，也不在 App 讀 cache 補設定。288段、實驗別名不設為通用包常數。取消品質比例作選用阻擋不取消禁止捏造、來源／隱私、十秒期限／取消／晚到結果退役或工程 gate。

## Collection rows and validation

每 row 的 id 是 chunk_id，documents 是非空原文且與 chunks.jsonl 的 text 完全一致；metadatas 包含 `document_id`、`document_version`、`locator`。不需要原 PDF／DOCX 仍可完整回答；缺原文不可只拿向量使用。title 由唯一 manifest document 提供，不依 query 或任意 metadata 改寫。

開啟前核對全部檔案、引擎精確版號及目標；副本開啟使用 migration validate。開啟後只讀 API 檢查使用者 collection 數、count、全部段落來源／locator／原文及向量形狀；向量要求有限、非零及 norm 誤差 <=1e-4。不能只驗第一段／抽樣後假稱整包唯一。

禁止 create／get_or_create／modify／add／upsert／update／delete／reset／ingestion replay／migration。缺任何必要項目均 unavailable；原包不修復、不用其他文件替代。

## Working copy and no-mutation evidence

原包只以一般檔案讀取，絕不把原路徑交給 PersistentClient。完整位元組副本存於實例私有暫存目錄、複製完成後重驗雜湊才開啟；此動作沒有解析文件、重新嵌入或建立 HNSW。原包 hash 在開啟／查詢／關閉前後不變。

Chroma 沒有公開承諾的嚴格 read-only 模式。工作副本允許鎖、SQLite journal／SHM 等必要記帳，但不能有 schema migration、文件／向量變更、重放未完成寫入或持久檢索索引變更。實作需以真實鎖定版本驗證：文件／metadata／向量／count 邏輯相同、retrieval 資產 hash 不變、持久 HNSW 檔案 hash 相同、沒有建立／變更 API 呼叫及 ingestion replay；SQLite 主檔不可只因整檔 hash 改變就誤判所有情況，也不可用「記帳」掩蓋文件索引寫入。

如果引擎在正常開啟／query 仍需要補建索引，此包不符合合約，停用工具並回報限制。App 停止時依 FR-016 最多九秒回收 worker（正常五秒、terminate 兩秒、kill 後兩秒）；只在確認已退出後清除自己的暫存目錄。超時仍未確認則安全記錄清理未完成、保留副本，不無限等待，不刪／改原包或模型。

## Trust and data flow

本功能不是任意不可信檔案的沙箱。部署者事先信任文件、模型及包供應者並授權使用；hash 不提供簽章保證。只有命中且限額的原文與來源會傳到所選 HF／Gemini；本機向量、索引檔、模型與路徑不傳送。文件原文是證據，不是工具／機器人動作授權。
