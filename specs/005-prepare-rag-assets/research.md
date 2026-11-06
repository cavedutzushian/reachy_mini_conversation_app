# Research: RAG 素材準備

**Date**: 2026-11-06 | **Scope**: Phase 0；唯讀官方文件、模型 metadata 與已鎖定套件來源。未下載權重、未建立索引、未執行模型。

## 1. 指定 revision 與安全權重

**Decision**: 僅接受部署者指定的完整 commit、且該版本已存在 loader 所需 safetensors。先匿名取得 metadata／必要小配置，resolved SHA 必須相同，缺檔在大型下載前拒絕。沒有預設 revision、格式轉換或 PR fallback。

**Rationale**: 官方 main 檔案樹目前只有 pytorch_model.bin 等權重，與現有 use_safetensors=True 及 bin／pt 拒絕條件不相容。存在 SFconvertbot 的未合併 PR #114／commit `3c42d559426f02b44d317f987c5336017333671e`，只能證明有候選檔案，不能當成已核准信任或預設來源。

**Alternatives considered**: 直接下載整個 main 會失敗且多取無關格式；自動 PR 選擇擴張信任；bin 轉換增加安全與數值一致性驗收，未納入此功能。

**Sources**: [官方 tree](https://huggingface.co/BAAI/bge-m3/tree/main)、[候選 commit（未採用）](https://huggingface.co/BAAI/bge-m3/commit/3c42d559426f02b44d317f987c5336017333671e)、現有 `document_worker.py`。

## 2. 匿名下載、乾淨 payload 與來源紀錄

**Decision**: 使用既有 HfApi／snapshot_download，固定 https://huggingface.co、token=False、指定 commit、精確 allowlist 及本次專用 cache。忽略自訂 HF_ENDPOINT／日常 token／快取。下載 staging 與最終 payload 分離，以普通檔案 bytes 複製必要內容。

必要 payload：config.json、config_sentence_transformers.json、modules.json、sentence_bert_config.json、1_Pooling/config.json、sentencepiece.bpe.model、special_tokens_map.json、tokenizer.json、tokenizer_config.json、model.safetensors。指定 revision 若不符合此 v1 形狀就拒絕；不製造來源不存在的配置。Normalize 模組 path 雖為 2_Normalize，已檢查鎖定 ST 允許沒有實體配置，不能因此宣稱下載不完整。

**Rationale**: Hub local_dir 會建立 .cache/huggingface；不能把下載 metadata 或 symlink 當模型內容發布。model-receipt.json 記來源 SHA 與 payload 雜湊，其清單不含 receipt 自己；包的 embedding.files 另包含 receipt 的實際 hash。這是來源／完整性紀錄，不是數位簽章。

**Alternatives considered**: 直接使用共用 HF cache 容易混入私人來源或連結；資料夾名不能證明 revision；receipt 自我 hash 形成循環。

**Sources**: [Hub API](https://huggingface.co/docs/huggingface_hub/package_reference/hf_api)、[下載參考](https://huggingface.co/docs/huggingface_hub/package_reference/file_download)、[local_dir](https://huggingface.co/docs/huggingface_hub/guides/download#download-files-to-a-local-folder)。

## 3. 共用模型檢查與 import 邊界

**Decision**: 從現有 worker 抽取模型驗證／load／encode 到重型共用模組，三個使用端共用；CLI 協調只用 stdlib 與既有 Hub，不 import config／core_tools。工作子程序設專用 HF_HOME／offline／telemetry off／SKIP_DOTENV；驗證後退出再移動目錄。

**Rationale**: config 在 import 時會讀 dotenv；一般 App import 不應載入 optional inference stack。抽取可避免 builder 與 reader 的 prefix／pooling／dtype／hash 檢查漂移，Windows 也需要釋放權重檔案鎖。

**Alternatives considered**: 複製整套驗證違反重用；從 CLI import DocumentIndex 來驗證尚無索引的模型會耦合不相干生命週期。抽取不能降低既有拒絕條件，004 回歸必跑。

**Sources**: 本機 config.py、document_retrieval.py、document_worker.py；既有 004 合約。

## 4. 原文、token 與定位

**Decision**: raw bytes hash 後 UTF-8-sig 解碼；source-window-v1 使用 tokenizer offsets 提議 400 content token／約 50 overlap 的切點，實際含 special tokens <=512。輸出只取原字串 slice，每片重驗上限，起點前進且不分開 CRLF。定位用行／字元範圍，不解析 Markdown 標題。

**Rationale**: decode token IDs 可能改空白與原文；文字模式讀取會轉換行尾。行／字元範圍足以符合既有 locator，同時避免把程式碼內 # 誤認為章節。非單調 token 計數用確定性後退處理，不做錯誤二分假設。

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

**Decision**: 同父目錄 staging／backup、排他 mkdir lock 與小型操作記錄。普通 rename 失敗恢復 backup；硬中斷留可辨識狀態與人工指引，不根據 PID／逾時自動刪鎖。模型鎖在前、包鎖在後，busy 立即失敗。預設根來自已驗證 checkout，不來自 CWD。

**Rationale**: Windows 不支援把非空目錄 os.replace 成另一個非空目錄；不能宣稱整包原子替換。預設素材 sibling 暫存目前未被 .gitignore 涵蓋，實作需補狹窄規則；custom output 要 repo 外或已忽略。

**Alternatives considered**: 先刪舊目錄會失去可用版本；跨 volume temp 不能可靠 rename；強制 PID 清理有誤判風險；不建立通用自動復原系統。

**Sources**: [Python os.replace](https://docs.python.org/3.12/library/os.html#os.replace)、[mkdir](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.mkdir)、本機 .gitignore。

## Research closure

設計選擇已解決；沒有待使用者澄清標記。尚未提供核准安全 revision，也未執行 Chroma 封存探針或實際模型／效能驗收；這些為實作前置／交付 gate，不是已通過證據。若可行性 gate 失敗，必須報告並重新評估範圍，不能私自改合約。
