# Research: RAG 素材準備

**Date**: 2026-11-09 | **Scope**: Phase 0；唯讀官方文件、模型 metadata 與已鎖定套件來源。本輪僅唯讀既有程式、004 v2契約與已保存選案紀錄，未下載／執行模型或建立索引。2026-11-06證據與舊決策的後續取代關係如下；歷史失敗不改寫通過。

## 1. 指定 revision 與安全權重

**Decision**: 僅接受部署者明確指定角色及選用方案固定commit，且該版本已有角色loader所需safetensors。先匿名取得 metadata／必要小配置，resolved SHA 必須相同，缺檔在大型下載前拒絕。沒有預設 revision、格式轉換或 PR fallback。

**Rationale**: 2026-11-06研究當時的main檔案樹只有 pytorch_model.bin 等權重，與現有 use_safetensors=True 及 bin／pt 拒絕條件不相容。存在 SFconvertbot 的未合併 PR #114／commit `3c42d559426f02b44d317f987c5336017333671e`，只能證明有候選檔案，不能當成已核准信任或預設來源。

**Alternatives considered**: 直接下載整個 main 會失敗且多取無關格式；自動 PR 選擇擴張信任；bin 轉換增加安全與數值一致性驗收，未納入此功能。

**Sources**: [官方 tree](https://huggingface.co/BAAI/bge-m3/tree/main)、[候選 commit（未採用）](https://huggingface.co/BAAI/bge-m3/commit/3c42d559426f02b44d317f987c5336017333671e)、現有 `document_worker.py`。

## 2. 匿名下載、乾淨 payload 與來源紀錄

**Decision**: 使用既有 HfApi／snapshot_download，固定 https://huggingface.co、token=False、指定 commit、精確 allowlist 及本次專用 cache。忽略自訂 HF_ENDPOINT／日常 token／快取。下載 staging 與最終 payload 分離，以普通檔案 bytes 複製必要內容。

舊嵌入角色必要payload（新版角色清單以receipt契約為準）：config.json、config_sentence_transformers.json、modules.json、sentence_bert_config.json、1_Pooling/config.json、sentencepiece.bpe.model、special_tokens_map.json、tokenizer.json、tokenizer_config.json、model.safetensors。嵌入revision若不符合其角色形狀就拒絕；不製造來源不存在的配置。Normalize 模組 path 雖為 2_Normalize，已檢查鎖定 ST 允許沒有實體配置，不能因此宣稱下載不完整。

**Rationale**: Hub local_dir 會建立 .cache/huggingface；不能把下載 metadata 或 symlink 當模型內容發布。model-receipt.json 記來源 SHA 與 payload 雜湊，其清單不含 receipt 自己；包embedding.files與reranking.files各自包含其receipt的實際hash。這是來源／完整性紀錄，不是數位簽章。

**Alternatives considered**: 直接使用共用 HF cache 容易混入私人來源或連結；資料夾名不能證明 revision；receipt 自我 hash 形成循環。

**Sources**: [Hub API](https://huggingface.co/docs/huggingface_hub/package_reference/hf_api)、[下載參考](https://huggingface.co/docs/huggingface_hub/package_reference/file_download)、[local_dir](https://huggingface.co/docs/huggingface_hub/guides/download#download-files-to-a-local-folder)。

## 3. 共用模型檢查與 import 邊界

**Decision**: 從現有 worker 抽取模型驗證／load／encode 到重型共用模組，三個使用端共用；CLI 協調只用 stdlib 與既有 Hub，不 import config／core_tools。工作子程序設專用 HF_HOME／offline／telemetry off／SKIP_DOTENV；驗證後退出再移動目錄。

**Rationale**: config 在 import 時會讀 dotenv；一般 App import 不應載入 optional inference stack。抽取可避免 builder 與 reader 的 prefix／pooling／dtype／hash 檢查漂移，Windows 也需要釋放權重檔案鎖。

**Alternatives considered**: 複製整套驗證違反重用；從 CLI import DocumentIndex 來驗證尚無索引的模型會耦合不相干生命週期。抽取不能降低既有拒絕條件，004 回歸必跑。

**Sources**: 本機 config.py、document_retrieval.py、document_worker.py；既有 004 合約。

## 4. 原文、token 與定位

**Decision**: producer以同一次bytes讀取計算hash／解碼／章節切段。新版採 [chapter-source-v1](contracts/chapter-source-v1.md)，取代400／50的source-window-v1；後者保留為歷史契約。Markdown真實ATX章節、前言與TXT單範圍依原始段落／長度處理，300／30目標與重疊、標題64／別名48、完整model_text<=512tokens；所有原文完整覆蓋，CRLF／offset與非單調token計數保護不變。

人工別名只接受可選清單並核對同文件／版本／bytes摘要、原文證據與適用章節範圍，沒有則明示空清單。不自動從正文擷取或生成。章節與別名供embedding／lexical／rerank脈絡，不能冒充引文。

**程序歸屬**：純函式留在輕量 build 模組，typed tokenizer adapter 與全部 inference 僅在 worker；producer 處理來源，其他驗證 worker 獨立載入模型。worker 寫 candidate 檔案，不經 IPC 傳原文／向量。fresh verifier 最後串流核對來源摘要及身分／stat，外部變更就拒絕。

**Rationale**: decode token IDs 可能改空白與原文；文字模式讀取會轉換行尾。行／字元範圍足以符合既有 locator，同時排除fenced code內假標題。非單調 token 計數用確定性後退處理，不做錯誤二分假設。

**Alternatives considered**: Markdown renderer／parser 不必要；只按字元長度無法保證模型 token 上限；清理語法會破壞引用。分段規則見 data-model，不承諾索引二進位重現。

**Sources**: [Path.read_bytes](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.read_bytes)、[tokenizer offsets](https://huggingface.co/docs/transformers/main_classes/tokenizer)。

## 5. Chroma 封存的實作可行性 gate

**Decision**: 公開 create_collection／add／必要的相同內容 update 僅發生在 producer；public close 後退出。候選 batch_size=2、sync_threshold=2、num_threads=2、cosine。實作前先以真實鎖定引擎、合成向量證明 1／2／3／奇數／多 batch 都可封存；尾批相同 row update 僅為待證方法，失敗即停止交付。

**Rationale**: Chroma 1.5.9 有 public close／context manager，最後共享 client 關閉釋放資源；但 Rust HNSW 僅達 sync_threshold 才持久化。Python 舊 validator 雖允許 1，Rust 實際兩參數最小為 2；不可用 1 假定所有小文件都會 flush。

**Alternatives considered**: `_system.stop()`、手改 SQLite、刪 WAL 或假段落湊批皆不採用；close 不能代替實測。研究 source 是辨認風險，產品只用公開 API，沒有 vendor／monkey patch。

**Sources**: [client.close](https://github.com/chroma-core/chroma/blob/1.5.9/chromadb/api/client.py)、[1.5.9 Rust 設定](https://raw.githubusercontent.com/chroma-core/chroma/1.5.9/rust/types/src/hnsw_configuration.rs)、[持久化條件](https://raw.githubusercontent.com/chroma-core/chroma/1.5.9/rust/segment/src/local_hnsw.rs)、[官方設定](https://docs.trychroma.com/docs/collections/configure)。

## 6. 不變性與平台宣告

**Decision**: producer 退出後取得全檔 inventory；新 verifier 在完整副本上用既有 reader 開啟／query／close，驗證原包全 hash、全部 row 邏輯內容／向量及副本所有持久索引 hash。journal 殘留或索引改變拒絕。候選宣告不等於發布，驗證成功才正式列入本機 target。

**Rationale**: 引擎可能允許 SQLite 記帳，主檔 hash 不是唯一判據；HNSW metadata 也在持久檢索索引範圍。未測 Linux／macOS 不加入 validated_targets。005 產包驗證與 004 的 CPU／語音／品質驗收不同。

**Alternatives considered**: 只測 count、只查第一列、只看 query 有結果、或複製 SQLite 單檔均不足。讀取副本若必須補建，包不可交付。

**Sources**: 004 index-package.md／完整 schema、現有 DocumentIndex。

## 7. Windows 發布／鎖／恢復

**Decision**: 同父目錄 staging／backup、排他 mkdir lock 與小型操作記錄。已驗證 stage rename 至 destination 成功即發布；界線前普通失敗恢復 backup，界線後清理失敗保留新版、published=true、exit 8，顯示「已發布，清理未完成」，不自動回復或重跑。硬中斷保留可辨識狀態供人工核對，不根據 PID／逾時自動刪鎖。兩模型鎖依規範路徑排序在前、包鎖在後，busy 立即失敗；預設根來自已驗證 checkout。

**Rationale**: Windows 不支援把非空目錄 os.replace 成另一個非空目錄；不能宣稱整包原子替換。既有實作已加入預設素材sibling忽略規則，新重排目的地仍需實作時核對並擴充狹窄規則；custom output 要 repo 外或已忽略。

**Alternatives considered**: 發布後回復會違反本次澄清，目的地路徑零變動則需額外 indirection／loader 變更，均不採用；先刪舊目錄會失去可用版本；跨 volume temp 不能可靠 rename；強制 PID 清理有誤判風險；不建立通用自動復原系統。

**Sources**: [Python os.replace](https://docs.python.org/3.12/library/os.html#os.replace)、[mkdir](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.mkdir)、本機 .gitignore。

## Research closure

設計選擇已解決，無待使用者澄清。既有2026-11-06 Chroma小包與BGE-M3安全模型驗證是當時v1證據（見quickstart），不是本輪v2／雙模型／章節別名／BM25已整合通過。以下增量決策取代舊單模型、舊切段及已校準門檻必填；本輪不重新驗收模型或包。

## 8. 雙模型角色、receipt與操作單位

**Decision**: 同一下載器明確--role embedding或reranker，每次獨立目的地／驗證／發布。模型固定BAAI/bge-m3@50f9396f75618b3389c1fd1068a1ff58dc7b5b26與BAAI/bge-reranker-base@2cfc18c9415c912f9d8155881c133215df768a70，要求--revision不接受main／tag／其他版本。預設重排位置external_content/bge-reranker-base-model/，保留原嵌入／索引位置。兩次模型準備再一次產包，共三步；不加入彙總發布。

**Rationale**: 明確角色避免BGE-M3 encoder驗證冒充cross-encoder可用。receipt升v2，角色對應ID／固定revision／完整allowlist、CPU／raw logit或reference向量檢查，皆不證明文件品質。舊receipt不能默默升級；新格式未備妥就提示重新準備，不由App改模型。既有ST CrossEncoder與標準庫BM25足夠，不新增直接依賴；thread2／1在worker入口只設一次。

**Alternatives considered**: 單次兩模型命令需額外彙總與跨目的地失敗語意，使用者已選分開；共用模型根會迫使搬移舊模型；bin轉換、任意模型下載與雲端驗證不納入。安全payload與schema見 [model-receipt](contracts/model-receipt.md)。

## 9. 明確完整方案與v2資料

**Decision**: builder必填--scheme bge-base-final-selection-20261109，自動帶入完整參數／兩固定模型，不要求逐項抄值；缺scheme停止、不默認，不接受--max-distance或個別數值覆寫。以004唯一v2schema保存策略、chunking、BM25、reranking及provenance；舊v1離線重產，不維持dense-only或App遷移。

**Rationale**: [最終方案](../../cache/005-prepare-rag-assets/calibration/bge-base-final-selection-20261109/final-scheme.json) 的0.58只在固定重排／文字預算之後套父向量cosine，不能移到dense預篩；200題均曝光，84/100正例、2/100負例誤放行、127/131段落支持不是盲測或品質通過。隨程式交付選案來源digest／參數／限制，不把工作區cache路徑變成部署依賴；包實際來源摘要與歷史example摘要分開。

**Alternatives considered**: 繼續要求已通過品質門檻的校準值會違反新決定；只保存0.58無法重現選案。充分性規則、另一判斷模型、雲端審核、短窗最高分與替代模型均排除。288段與實驗別名只屬example.md，不能硬編碼。

## 10. 離線詞彙預建與完整reader驗證

**Decision**: producer用固定ascii-cjk23-v1 tokenizer預建完整model_text的TF／DF／各段長度／avgdl，與chunks ID相同順序寫入bm25.json。query term去重、k1=1.2、b=.75、positive log1p IDF；runtime僅計分、不重新tokenize語料補統計。新程序用004v2reader讀全部向量／脈絡／BM25，執行exact dense10＋BM25正分10／RRF60／完整五候選Identity raw logits、選段及後置距離。

**Rationale**: 選案實驗用精確1-dot而非Chroma ANN，lexical-only候選也要有預建父向量。以模型載入、schema通過或query回空值不能取代完整流程／不變性；正常no_evidence可接受，操作失敗不可發布。空lexical語料avgdl0時全部0分，不除零、不建新索引。統計驗證只核對既有資料，不修復或替代。

**Alternatives considered**: rank-bm25／框架增加不必要依賴；runtime重建統計與自動dense-only fallback違規；只驗前幾段會遺漏混合來源／對應錯誤。既有真實Chroma封存方法仍需新版回歸，不能靠舊passed數字放行。

## 11. 設計後憲章與證據界線

**Decision**: 雙模型／包沿用公開API、typed支援、可回收子程序、獨立目的地發布與exit8。兩模型讀鎖依規範路徑排序，後取輸出鎖，busy立即失敗並釋放本次鎖；源文件與別名檔納入同一來源快照／發布前hash及stat核對。v2reader未實作時，005不得宣告App可讀並發布。

**Rationale**: 保留原資料／模型不變與隱私要求；五秒／95%及品質比例改為量測而非阻擋，不免除完整性、安全、十秒期限／退役或工程gate。無新依賴／服務／憲章例外。Linux／macOS不測且不稱pass；準備成功不代表雙後端語音或真實CPU已驗收。

**Alternatives considered**: 本輪直接執行下載／產包／修改App超出plan；自動刪lock／rollback已發布新版與exit8衝突。下一步保留舊tasks完成紀錄、追加v2工作、analyze再實作，不以改分母或覆寫舊報告結案。
