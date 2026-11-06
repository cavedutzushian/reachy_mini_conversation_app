# Validation Guide: 模型下載與單文件離線產包

**階段**：Phase 1 設計。以下新增入口／測試尚未實作，命令供後續實作驗證，不是本輪已執行結果。本輪沒有下載模型或建立索引。

## 前置條件

- Windows／Python 3.12 與本儲存庫；依現有 README 安裝，以 `uv sync --frozen --extra rag --group dev` 取得既有鎖定環境。本輪不重新解析／安裝依賴。
- 部署者提供信任的 BAAI/bge-m3 完整 40 hex revision，且該版本已包含合約所需安全權重與配置。官方 main 不符合目前 safe-only loader；不使用浮動版本，也不把研究中的未合併 PR 當預設核准來源。
- 一份無敏感資料的 UTF-8 TXT／Markdown，以及文件識別資訊與已校準距離門檻。門檻不存在時先準備標註／校準，不隨便填範例值來宣稱完成。
- App 保持停止，相機／記憶不變；兩腳本不啟動機器人、不讀日常 .env／憑證。真實模型下載只有部署者明確執行下載腳本才開始。
- 本功能沿用兩個已忽略正式目錄；實作需加入預設 sibling stage／backup／lock 的狹窄忽略規則。自訂輸出放 repo 外或事先自行管理忽略。

## 兩個正常準備步驟（實作後）

在已安裝本專案的環境，先由使用者在當次行程設定 BGE_M3_REVISION、RAG_SOURCE_FILE、RAG_MAX_DISTANCE；這些是示範命令變數，不是新增 App 設定。值分別為信任完整 SHA、本機文件路徑及明確已校準數值，不能直接使用占位字串。

```powershell
python -m reachy_mini_conversation_app.download_document_model --revision $env:BGE_M3_REVISION
python -m reachy_mini_conversation_app.build_document_package --input $env:RAG_SOURCE_FILE --document-id manual --title "測試手冊" --document-version v1 --index-version build-1 --max-distance $env:RAG_MAX_DISTANCE
```

預期：第一次只下載指定安全 snapshot，離線檢查後發布 `external_content/bge-m3-model/`，含 receipt；第二次零網路產生 `external_content/document-package/manifest.json` 與完整 `chroma/`，經 fresh reader 驗證後發布，兩命令 exit=0。標題／版本請依實際文件調整。

從不同 CWD 呼叫結果仍指 source checkout 預設目錄。若用 wheel 而無 checkout，下載傳 `--output`；builder 明確傳 `--model`／`--output`，不可寫 site-packages。只顯示既有 REACHY_MINI_DOCUMENT_MODEL_PATH／INDEX_PATH 的可用值，不改 .env；後續如何手動啟用請依 root README。

## 故障與保護

1. 同一完整 revision 再執行下載：already_ready，零網路／零覆寫。
2. 缺 safetensors／不相容配置的完整 revision：大型下載前拒絕，不採另一 SHA／PR、不轉換 bin。
3. 改 model payload 或 receipt hash、移除 tokenizer：明確失敗；無 replace 不寫目的地，有 replace 的新下載驗證失敗仍保留舊模型。
4. builder 使用已準備模型，於使用者提供的斷網／禁止外連測試環境執行：成功；缺模型時失敗，不代為連網。腳本不自行修改電腦網路。
5. `.txt`、`.MD`、UTF-8 BOM、CRLF／LF／單 CR、中文／英文／否定／表格／程式碼／連結共至少五份 fixture：原文 slice、定位、上限與只讀來源皆正確；不抓連結或執行內容。
6. 無效編碼／空白／PDF／目錄／glob／URL／多輸入、無效識別欄位、NaN／越界門檻：明確錯誤，無可用半成品。
7. model／input／output 重疊、根目錄、link／junction、專案受保護目錄或未忽略 repo 內自訂輸出：拒絕，不影響來源。
8. 並行兩命令處理相同模型／目的地：一方持鎖，另一方 busy 立即失敗，沒有互刪；不要用時間或 PID 自動破鎖。
9. 既有目的地無 replace：拒絕。明確 `--replace` 時，注入新包驗證失敗／第二個 rename 失敗：舊資料保持或復原，沒有虛假 completed。
10. 在 preparing／validating／backed_up／published／cleaning 各階段中止子／父程序：不把半成品當完成；顯示可辨識 stage／backup／lock 狀態。先人工確認無準備程序，再核對 operation 記錄及 hashes 恢復完整舊版或已驗證新版；不可直接刪 lock、刪整個輸出或停止無關程序。

以上錯誤碼、CLI 輸出與狀態依 [CLI 合約](contracts/preparation-cli.md)；不將 provider body、原文、向量、token 或私密例外內容加入診斷。

## 實作第一道 gate：真實 Chroma 小包

不需 BGE 模型，先用明確合成 normalized 1024 維向量，獨立 producer 建立 1／2／3／奇數／多 batch fixture；只在 cache 建置，不從 App 路徑建索引。

候選 batch_size／sync_threshold=2、公有 close；必要時相同真實 row update 只是一個待驗證做法。每種案例都要經 fresh process 檢查完整 inventory、原包 hash、全部 row 邏輯／向量／count、副本持久 HNSW hash 及 query／close 後不變性。出現 WAL／SHM／journal、重建或 replay 差異就拒絕。

若任何合法小文件情境不能以公開 API 產出合規包，**停止交付並回報**。不加假段落、不修改 Chroma 私有表或 004 schema、不刪 journal 掩蓋，不把目前研究當成功證據。

## 自動化驗證命令（實作後）

```text
python -m pytest tests/test_document_assets.py tests/test_document_model.py tests/test_download_document_model.py tests/test_build_document_package.py tests/test_document_prepare_worker.py -v
python -m pytest tests/test_document_worker.py tests/test_document_retrieval.py tests/test_huggingface_realtime.py tests/test_gemini_realtime.py tests/test_profile_paths.py -v
ruff check . --fix
ruff format .
mypy --pretty --show-error-codes
python -m pytest tests/ -v
uv lock --check
```

一般 gate 不抓模型、不連 provider、不啟動 daemon。fake Hub 驗證 endpoint／token=False／allowlist／專用 cache，spy 驗證 builder 零外連與已就緒分支零下載。模型／索引真正整合採明確 opt-in，未提供核准安全 snapshot 記未執行，不能自選研究候選或把 fake 當真實模型通過。

wheel 測試要涵蓋兩 CLI help、runtime receipt schema 與本功能 schema 相同、不依賴 source specs／遠端 ref、普通 App 不 import optional stack。004 模型抽取的原有安全拒絕、編碼／reference／CPU 與回合回歸仍須通過。

## 證據與交接

記錄 OS／架構、Python／lock、指定 revision、receipt／來源／包 digest、固定 fixture、命令與原始結果；不發布私密原文。每個已發布 target 有 fresh reader 證據，至少五份文件可核對原文，八類故障、兩次切段重現與日誌 sentinel 皆有結果。

本輪 Windows 設計不等於 Windows 實測通過；Linux／macOS 明確未測。模型下載成功也不代表 004 真實 CPU 50 題、兩後端來源品質／插話／文字 timeout 已驗收。完成這兩腳本後才用實際素材續做 004 的待辦，不能在此提前結案。
