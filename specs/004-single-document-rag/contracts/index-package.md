# Contract: 外部預建索引包 v1

本文件定義外部產包者的交付邊界，**不交付建索引／文件解析程式**。App 不在啟動、對話或修復流程建立文件向量／索引。

## Layout and startup configuration

```text
<designated-package>/
├── manifest.json
└── chroma/
    ├── chroma.sqlite3
    └── <既有持久索引所需的完整檔案與目錄>
<local-bge-m3-model>/
└── <相同 immutable revision 的完整模型／tokenizer／ST 模組檔案>
```

啟動環境／既有 `.env` 提供 `REACHY_MINI_DOCUMENT_INDEX_PATH`、`REACHY_MINI_DOCUMENT_MODEL_PATH`；預設空白。第一個目錄是唯一包，不是待掃描的文件資料夾；第二個是完整本機模型，不是遠端 model ID。工具不能覆寫任何路徑。停止 App 後換完整包再重啟，沒有熱更新、上傳或管理 endpoint。

## Manifest required fields

| 欄位 | 契約 |
|---|---|
| schema_version | 整數 1，不自動升級 |
| index_version | 非空 <=128 安全字元；外部建置版本 |
| document | `id`、`title`、`version`、`source_sha256`，約束見 data-model |
| engine | `name=chromadb`、精確 `version`、`collection`，不得讓使用者 query 改選 |
| producer | `os`、`architecture`；可辨認的建置平台 |
| validated_targets | 真正完成開啟／查詢／不變性驗收的 `os`／`architecture` 組合；未列目標拒絕 |
| snapshot_complete | true；引擎已正常關閉、flush，無待套用 ingestion log、migration 或重建需求 |
| chunk_count | 正整數，與 collection 全部 row 一致；僅一個使用者 collection |
| files | chroma 內完整相對檔案清單及 SHA-256；manifest 本身不自我 hash |
| embedding | 見下節；必須吻合本機模型與實際集合 metric／向量 |
| retrieval | `max_distance` 為 [0,2] 有限數，cosine 距離 <=門檻才接受；外部標註校準 |
| reference | 非敏感 `query`（<=500 code points）及 `embedding`（1024 有限 float），測試模型載入後一致性 |

安全字串欄位不接受控制字元／本機絕對路徑；文件／索引 ID 使用英數、`-`、`_`、`.`，title／locator 可用原語言文字。manifest 最大 16 MiB、UTF-8 JSON、不得重複 key；限制不符就是不支援的包，不能略過檢查。此為交付格式上限，非文件段落數的固定上限。

files 不含逃逸路徑、連結、junction 或不明額外檔；不在 App 內解壓縮。預建者需確保傳輸／複製的是已封存 snapshot；`snapshot_complete` 宣告不取代實測。不要手工刪掉引擎必要檔來假造乾淨快照。

## Embedding compatibility

`embedding` 必須記錄：

- `model_id="BAAI/bge-m3"`、不可浮動的 `revision`、模型所需全部檔案的相對路徑／SHA-256（包括 tokenizer、ST modules／pooling／normalize config、安全權重）。
- `sentence_transformers_version`、`torch_version`、`transformers_version`，與該包認可的精確 runtime 組合一致；不要要求安裝文件產包者無關工具。
- `mode="dense"`、`dimension=1024`、`precision="float32"`、`pooling="cls"`、`normalize=true`、`query_prefix=""`、`document_prefix=""`、`max_seq_length=8192`、`metric="cosine"`。

使用 ST 原模型 pipeline，不換 mean pooling，不重正規化原文／改字體。原有長度限制按官方 tokenizer 設定；無效／超過問題字元上限由工具拒絕。CPU 執行明確 float32、禁用自動 device／CUDA／MPS、remote code 與模型下載。模型只接受預期內建 Transformer／Pooling／Normalize 模組及安全權重；trust_remote_code=false 本身不等於可任意信任 model directory。

驗證模型與檔案 hash 後，用 reference.query 產生同設定向量，檢查維度、有限數、非零及 L2 norm；與 reference.embedding 的 cosine 差距初始容許 <=1e-5。這是管線相容檢查，不是檢索分數門檻；若實際 CPU 浮點差異超出，須重新評估並記錄證據，不運行時放寬。

## Collection rows and validation

每 row 的 id 是 chunk_id，documents 是非空原文；metadatas 包含 `document_id`、`document_version`、`locator`。不需要原 PDF／DOCX 仍可完整回答；缺原文不可只拿向量使用。title 由唯一 manifest document 提供，不依 query 或任意 metadata 改寫。

開啟前核對全部檔案、引擎精確版號及目標；副本開啟使用 migration validate。開啟後只讀 API 檢查使用者 collection 數、count、全部段落來源／locator／原文及向量形狀；向量要求有限、非零及 norm 誤差 <=1e-4。不能只驗第一段／抽樣後假稱整包唯一。

禁止 create／get_or_create／modify／add／upsert／update／delete／reset／ingestion replay／migration。缺任何必要項目均 unavailable；原包不修復、不用其他文件替代。

## Working copy and no-mutation evidence

原包只以一般檔案讀取，絕不把原路徑交給 PersistentClient。完整位元組副本存於實例私有暫存目錄、複製完成後重驗雜湊才開啟；此動作沒有解析文件、重新嵌入或建立 HNSW。原包 hash 在開啟／查詢／關閉前後不變。

Chroma 沒有公開承諾的嚴格 read-only 模式。工作副本允許鎖、SQLite journal／SHM 等必要記帳，但不能有 schema migration、文件／向量變更、重放未完成寫入或持久檢索索引變更。實作需以真實鎖定版本驗證：文件／metadata／向量／count 邏輯相同、持久 HNSW 檔案 hash 相同、沒有建立／變更 API 呼叫及 ingestion replay；SQLite 主檔不可只因整檔 hash 改變就誤判所有情況，也不可用「記帳」掩蓋文件索引寫入。

如果引擎在正常開啟／query 仍需要補建索引，此包不符合合約，停用工具並回報限制。App 停止回收 worker 後只清除自己的暫存目錄，不刪／改原包或模型。

## Trust and data flow

本功能不是任意不可信檔案的沙箱。部署者事先信任文件、模型及包供應者並授權使用；hash 不提供簽章保證。只有命中且限額的原文與來源會傳到所選 HF／Gemini；本機向量、索引檔、模型與路徑不傳送。文件原文是證據，不是工具／機器人動作授權。
