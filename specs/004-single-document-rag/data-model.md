# Data Model: 單一預建文件 RAG

資料由外部預建包提供；App 只產生暫時查詢／結果與執行期狀態，不增文件持久寫入。詳見 [包合約](contracts/index-package.md) 及 [工具合約](contracts/search-document.md)。

## 1. DesignatedDocument

| 欄位 | 型別／限制 | 關係 |
|---|---|---|
| document_id | 非空安全識別字串，<=128 code points | 包內唯一 |
| title | 非空顯示文字，<=160 code points | 文字／語音來源名稱 |
| version | 非空安全字串，<=128 code points | 與 ID 組成唯一版本 |
| source_sha256 | 原文件內容 digest | 外部建置者提供；App 不重讀原文件驗算 |

同一名稱不代表相同 ID／版本；版本不同不得合併。顯示 metadata 不得含本機絕對路徑、控制字元或工具指令用途欄位。

## 2. IndexPackage / EmbeddingConfiguration

| 欄位群 | 內容 |
|---|---|
| 包識別 | manifest schema `1`、index_version、唯一 DesignatedDocument |
| 引擎 | 精確 chromadb 版本、固定 collection、producer OS／architecture、允許且已驗證的 runtime targets |
| 資料 | chunk_count >0、每個持久化檔案的相對路徑／sha256、完整且無待回放寫入的快照宣告 |
| 模型 | model_id 固定 BAAI/bge-m3、不可浮動 revision、本機模型檔案清單／sha256、tokenizer 與 modules 雜湊 |
| 管線 | sentence-transformers／torch／transformers 精確版本、dense、float32、CLS、L2、無 prefix、維度 1024、cosine、max_seq_length 8192 |
| 品質 | 校準固定 cosine max_distance；非敏感 reference_query／1024 維 reference_embedding |

完整 preflight 對所有段落驗證來源一致、原文／locator／ID／向量維度及有限數值；不能只驗命中的三段。檔案 hash 對照 exact inventory，拒絕缺漏、未列檔、符號連結／junction、路徑穿越及不相容目標。雜湊用於完整性，不是簽章或可信發布者證明；只部署可信來源的包與模型。

包先通過靜態檢查，再複製到實例私有暫存目錄並重驗雜湊；原包不傳給 Chroma。載入既有 collection 後 count／逐批 get 與 manifest 相符才 ready。引擎不得藉驗證執行任何索引寫入；開啟相容性由真實測試確認。

## 3. DocumentChunk

| 欄位 | 型別／限制 |
|---|---|
| chunk_id | 唯一、穩定、安全字串 <=128 code points，對應 Chroma row ID |
| document_id / document_version | 必須等於 manifest 唯一文件 |
| text | 非空原文；存於 Chroma documents，含合理鄰近上下文 |
| locator | 非空文字 <=256 code points，例如真實章節／頁碼／段落；無頁碼者不虛構 |
| embedding | 1024 個有限數、非零、L2 normalized float32；不進模型工具結果 |

每個 row 只有一份文件版本。重複 ID、空 documents、metadata 缺漏或混合來源皆整包 unavailable，不略過壞段落繼續作答。

## 4. DocumentQuery / InvocationOwnership

| 欄位 | 生命週期 |
|---|---|
| request_id / call_id | runtime 請求及既有工具呼叫的唯一關聯 |
| query | 去除前後空白後 1–500 Unicode code points，至少含字母或數字；無效不送 worker |
| generation / response_epoch | 由既有 handler 擷取，對話端檢查，不送文件包或作為使用者參數 |
| accepted_at / deadline | monotonic 受理時間及 +10 秒期限 |
| status | accepted → running → completed／failed，或 retired |

`retired` 不可恢復。逾時、取消、插話、換供應商、停用工具／換人格或新對話後不可把結果重新送入模型；duplicate call ID 也不復活。CPU 工作完成與 waiter 退役是兩種狀態，不能混成一個 completed flag。

## 5. RetrievalResult

成功：文件 title／ID／version、index_version 及 1–3 個 CitationPassage。每段有 chunk_id、locator、text、truncated；text 合計 <=2,000 code points。只複製同一原文或連續前綴，不改寫引用、拼接兩句或生成 locator。title／locator metadata 不列入原文預算，但受各自上限限制。

未成功：`{"error": "document_..."}`，固定碼見工具合約。無依據也使用此固定失敗形狀，避免現有 manager 丟失額外 code 欄位。錯誤不含使用者輸入、完整路徑或底層例外內容。

## 6. RuntimeState

| 狀態 | 允許行為／轉移 |
|---|---|
| unconfigured | 不讀包／模型；query → not_ready；配置須重啟 |
| dormant | 配置完整且尚未啟動；只有已啟用工具的 query 可觸發 loading |
| loading | 唯一 worker 驗證包／載入模型，query → not_ready；<=120 秒轉 ready 或 failed |
| ready | 最多接一份工作 → busy |
| busy | query → busy；worker 實際結束 → ready；waiter 逾時／取消仍 busy |
| failed | 固定 not_ready 或 unavailable，依原因區分；不自動重啟，重啟 App 才重新檢查 |
| closing / closed | 撤銷所有權、回收 worker、清理工作副本；不接受新查詢 |

設定讀取不等於檔案讀取授權。人格停用時 dispatcher 不得查文件；先前已啟用載入的模型可保留，但不執行新工作。worker 永久卡住時一直 busy，直到 App 停止回收；不藉另開 worker 堆疊資源。
