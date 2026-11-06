# Validation Guide: 模型下載與單文件離線產包

**階段**：離線實作已完成；下列命令可用。實際證據及未完成項目見文末；真實安全模型下載已補驗通過，真實 BGE-M3 文件產包仍未完成，不代表整體結案。

## 前置條件

- Windows／Python 3.12 與本儲存庫；依現有 README 安裝，以 `uv sync --frozen --extra rag --group dev` 取得既有鎖定環境。本輪不重新解析／安裝依賴。
- 部署者提供信任的 BAAI/bge-m3 完整 40 hex revision，且該版本已包含合約所需安全權重與配置。官方 main 不符合目前 safe-only loader；不使用浮動版本，也不把研究中的未合併 PR 當預設核准來源。
- 一份無敏感資料的 UTF-8 TXT／Markdown，以及文件識別資訊與已校準距離門檻。門檻不存在時先準備標註／校準，不隨便填範例值來宣稱完成。
- App 保持停止，相機／記憶不變；兩腳本不啟動機器人、不讀日常 .env／憑證。真實模型下載只有部署者明確執行下載腳本才開始。
- 本功能沿用兩個已忽略正式目錄；實作需加入預設 sibling stage／backup／lock 的狹窄忽略規則。自訂輸出放 repo 外或事先自行管理忽略。

## 兩個正常準備步驟

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
9. 發布前保護：既有目的地無 replace：拒絕。明確 `--replace` 時，注入新包驗證失敗／第二個 rename 失敗：舊資料保持或復原，沒有虛假 completed。
10. 在 preparing／validating／backed_up／published／cleaning 各階段中止子／父程序：不把半成品當完成；顯示可辨識 stage／backup／lock 狀態。先人工確認無準備程序，再核對 operation 記錄及 hashes 恢復完整舊版或已驗證新版；不可直接刪 lock、刪整個輸出或停止無關程序。

11. 新版 rename 已成功後注入 backup／stage／lock／操作記錄清理失敗或取消：新版維持可用且不回復，顯示「已發布，清理未完成」、exit 8、published=true／ready=true，保留可核對殘留；確認沒有自動下載、產包或重試。與第 9 項發布前普通失敗／第 10 項硬中斷分開判定，來源 bytes 在全部案例均不變。

依 [source-window-v1](contracts/source-window-v1.md) 驗證 golden fixtures、原文完整覆蓋、CRLF、末片、零 offset 與非單調計數；兩次重建的段落／ID／定位必須一致。假 tokenizer fixtures 只證明演算法，不取代真實 BGE-M3 驗收。另以程序／IPC spy 確認父 CLI 不載 tokenizer／模型、不讀全文切段；worker 產出 candidate 檔案，管道無原文／向量；來源中途修改／替換須在發布前拒絕。

以上錯誤碼、CLI 輸出與狀態依 [CLI 合約](contracts/preparation-cli.md)；不將 provider body、原文、向量、token 或私密例外內容加入診斷。

## 實作第一道 gate：真實 Chroma 小包

不需 BGE 模型，先用明確合成 normalized 1024 維向量，獨立 producer 建立 1／2／3／奇數／多 batch fixture；只在 cache 建置，不從 App 路徑建索引。

候選 batch_size／sync_threshold=2、公有 close；必要時相同真實 row update 只是一個待驗證做法。每種案例都要經 fresh process 檢查完整 inventory、原包 hash、全部 row 邏輯／向量／count、副本持久 HNSW hash 及 query／close 後不變性。出現 WAL／SHM／journal、重建或 replay 差異就拒絕。

若任何合法小文件情境不能以公開 API 產出合規包，**停止交付並回報**。不加假段落、不修改 Chroma 私有表或 004 schema、不刪 journal 掩蓋，不把目前研究當成功證據。

## 自動化驗證命令

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



## 已取得證據（2026-11-06）

範圍為個人客製化、Windows 11 x86_64／Python 3.12.12。使用既有鎖檔，以 `uv sync --frozen --extra rag --group dev --offline --cache-dir cache/uv` 從工作區快取補齊依賴，未改 pyproject.toml／uv.lock、未新增依賴。實際版本：Chroma 1.5.9、Sentence Transformers 6.2.0、torch 2.15.0+cpu、transformers 5.21.0。所有合成資料在 `cache/005-prepare-rag-assets/`；未讀日常 .env／憑證或私人 HF cache，未啟動 App／provider 對話／機器人。

| 驗證 | 結果與範圍 |
|---|---|
| T004／T005 Chroma gate | 10 個真實 Chroma 案例通過，另含忽略規則測試共 11 項。1／2／3／5／超過 API batch 且最後餘一段；原包 hash、全部 rows／向量／count、副本所有持久 HNSW hash 與 query／close 後不變性核對。 |
| 封存方法 | 1 段資料只 close 的負向對照確實改寫 data_level0.bin／length.bin；正式流程 batch_size=2、sync_threshold=2、num_threads=2，最後對最後一筆真實 row 做一次相同內容的公開 update，再 close／退出。未使用假段落、私有 API、刪 journal 或修改 loader 合約。 |
| 五份離線文件 | 中文、英文、否定、表格、程式碼／連結：假 encoder＋真實 Chroma、獨立 producer／verifier 共 5 項通過。audit hook 禁止 socket.connect／getaddrinfo；全量邏輯摘要、原包與持久索引不變。這不是 BGE-M3 語意品質證據。 |
| CLI 串接／來源失敗 | 同一合成中文文件再經實際 builder CLI、隔離私有管道及新工作程序完成驗證／發布，與第一次文件識別／段落數一致；來源修改拒絕發布；無效 UTF-8 回 invalid_document／exit 2，不留可用目的地。最終針對新增無效編碼分支的複驗 1 passed。 |
| 切段 | 正式常數的原文／ID／CRLF／零 offset／非單調計數 golden fixtures、非法映射與重建一致性通過，不比較 Chroma 二進位重現。 |
| 發布／IPC | 發布前各階段取消保留舊版、第二個 rename 失敗復原、發布後清理／記錄失敗及取消維持新版並回 exit 8；跨程序 busy、硬中斷殘留、無法確認 worker 退出時保留素材均通過。私有管道不接受內容型結果，測試 sentinel 不進診斷；模型環境清除憑證並使用獨立 cache／offline。 |
| 下載 | fake Hub／worker 完整準備與同版本重用通過，重用不呼叫 metadata。公開 endpoint、token=False、精確十檔 allowlist、LFS／Git blob hash、傳輸失敗保留舊資料及 provider body 遮蔽均有檢查。 |
| Wheel／文件 | 兩 CLI／共用模型／worker／runtime receipt schema 進 wheel，schema 與合約相同；從 wheel import 輕量入口不載 inference／config。root README 已同步；scheme.mmd 重新產生 SVG，另渲染 PNG 視覺檢查，未手改 SVG。 |
| 完整 gate | Ruff check／format 通過；strict mypy：64 source files 無錯誤；pytest：939 passed、19 skipped；uv lock --check --offline 通過。 |

19 項略過包含 15 項需明確啟用的 Chroma／合成產包測試、2 項真實模型／產包 opt-in，以及 2 項既有 opt-in。前 15 項已另外明確執行，其中 Chroma gate 與五份合成文件的原始 XML／log 留在工作區快取；不把一般 gate 的 skip 算成實際通過。

主要結果檔：`cache/005-prepare-rag-assets/probe-confirmed.xml`、`package-close-and-mutation.xml`、`package-cli-final.xml`、`cli-invalid-encoding-final.xml`、`verified-final-gate.xml`（及對應 log）。測試程序使用自有工作區 basetemp，uv 使用工作區 cache，不修改電腦網路或系統服務。

### 保留的首次失敗與修正

- 初次基線使用系統 tmp 產生環境錯誤；改工作區 basetemp 後基線為 896 passed／2 skipped，唯一 wheel 失敗是工作區外 uv cache 權限；改工作區離線 cache 單獨複驗通過。
- 初次忽略規則測試受 Windows CRLF stdin 影響，改 Git 的 NUL 分隔介面；一段 close-only 的 HNSW 不變性失敗保留為負向對照，正式 producer 依已證明的 public update 方法封存。
- 初次合成產包把 atime 納入來源 stat 比較而誤拒絕；改核對 dev／ino／size／mtime_ns 與最終串流 hash。來源變更測試仍明確拒絕。
- 一輪完整 gate 為 916 passed／17 skipped，wheel 測試以 CP950 讀含中文 receipt schema 失敗；測試明定 UTF-8 後單獨複驗及最終完整 gate 通過，產品原有 UTF-8 讀取未放寬。

### 真實素材待驗

使用者指定 revision：`5617a9f61b028005a4858fdac845db406aefb181`。匿名公開 metadata 回同一 SHA，列出 pytorch_model.bin，但沒有 model.safetensors；實際下載 CLI 回 unsupported_revision，在權重下載前拒絕，隔離目的地未發布。沒有轉換、選用 PR／另一個 commit 或下載不被接受的權重。此舊 revision 的成功驗收未完成；其後使用者另提供的合規 revision 已通過 T019，詳見下節。

指定來源 `example.md`：62213 bytes、UTF-8-sig 解碼 25453 code points，SHA-256 `d1696eed28fa4043645b256ac587f63a7cd1d722e40d13eb6144aef4effb3c07`。僅做指定檔案編碼／摘要檢查；未複製或建立真實索引，來源與模型／索引不入 Git。使用者明確回覆「尚未校準」，因此沒有代填 max-distance。

合規本機模型已依下節補驗備妥；T029／T039 尚缺已校準門檻，T042 保留整體未結案。真實驗收入口已建立，需部署者明確選用：下載使用 RUN_DOCUMENT_MODEL_ACCEPTANCE=1 與 DOCUMENT_MODEL_REVISION；本機產包使用 RUN_DOCUMENT_PACKAGE_ACCEPTANCE=1、DOCUMENT_MODEL_PATH、DOCUMENT_MAX_DISTANCE。這些是測試行程變數，不是 App 設定；未提供有效素材不得勾完成。Linux／macOS 未測，004 真實 CPU／雙後端／語音／品質任務未更動。

| 需求 | 證據／尚缺項目 |
|---|---|
| FR-001～004 | 兩 CLI、固定 revision／allowlist、receipt／hash、CWD／wheel 路徑與零網路重用；真實安全模型下載已依下節 T019 補驗通過。 |
| FR-005～008 | 單文件格式／識別／門檻拒絕、原文 golden fixtures、離線 producer／來源一致性；真實模型編碼待 T029。 |
| FR-009～010 | 真實 Chroma 小包 gate、五份合成文件與既有 reader 全量／關閉後不變性；未擴增平台，真實 BGE-M3 待 T029。 |
| FR-011～013 | 分界取消／rollback／cleanup／hard-crash、跨程序排他、危險路徑與 IPC／日誌 sentinel；來源不修改、沒有 App 行程控制。 |
| FR-014 | README／Mermaid／wheel／全 gate／lock，無新依賴，既有 HF／Tool／相機／記憶設定不變。 |
| SC-001 | fake 下載與合成 CLI 產包分別通過；真實下載已通過；完整交接待 T029／T039。 |
| SC-002 | 五份合成文件通過原文／位置／格式；真實模型同組文件待 T029。 |
| SC-003 | 編碼、格式、revision、完整性、傳輸、未授權覆寫、危險路徑、發布前驗證與發布後清理／中斷有分界保護證據。 |
| SC-004 | fake Hub 同版本零 metadata／下載；五份合成產包禁止網路；真實模型同版本零網路重用已依下節通過。 |
| SC-005 | 真實 Chroma＋假 encoder fresh reader／全量邏輯／HNSW 不變，僅 Windows；真實模型包待 T029。 |
| SC-006 | 純原文切段重建一致、兩次 producer／CLI 文件識別與段落數一致、sentinel／IPC 保護；真實模型完整重現待 T029／T039。 |

## T019 補驗通過（2026-11-06）

- 使用者明確指定的新 revision：`50f9396f75618b3389c1fd1068a1ff58dc7b5b26`。匿名 metadata 解析至同一 SHA，十個必要安全 payload 齊全；舊 revision 的缺檔結果仍保留。
- 第一次實際下載在 hf_xet 原生傳輸階段發生 Windows access violation，沒有發布可用模型。原始 log：`cache/005-prepare-rag-assets/approved-model-50f9396f.log`；沒有依此失敗自動換版本、模型或格式。當時的操作殘留位於同名隔離測試根，未自動破鎖或清除。
- 使用套件支援的當次行程設定 `HF_HUB_DISABLE_XET=1`，在新隔離目錄以一般匿名 HTTP 下載同一 snapshot。此設定不修改 .env、依賴或模型，不是自動模型替代。
- 實際執行 `RUN_DOCUMENT_MODEL_ACCEPTANCE=1`、`DOCUMENT_MODEL_REVISION=<上述 SHA>` 的 `tests/test_download_document_model.py::test_approved_snapshot_loads_offline_and_reuses_without_network`，結果 **1 passed，152.23 秒**；另有 1 個 pytest cache 權限警告，沒有模型驗證錯誤。模型通過離線 CPU 載入、1024 維 normalized finite reference、前後 hash 一致性、receipt 及第二次呼叫零 metadata／下載／覆寫檢查。
- Payload 共 10 檔、2,293,234,427 bytes；根目錄精確 11 檔（含 receipt）。receipt SHA-256：`841e6563d296d012d5be146a11df8084980db4e25d99844c38630522a08fd2d7`；實際 runtime 為 ST 6.2.0／torch 2.15.0+cpu／transformers 5.21.0。
- 已保留模型位置：`cache/005-prepare-rag-assets/approved-model-http-50f9396f/test_approved_snapshot_loads_o0/model/`。這是隔離驗收目錄，不是 App 已啟用的設定；後續可明確以此作為 --model。沒有自動搬移模型或改 App 設定，素材仍不入 Git。
- 原始結果：`approved-model-http-50f9396f.log`／`.xml`；不含向量的本機摘要：`approved-model-http-summary.json`，皆在同一工作區 cache 根。

本次僅更新驗收證據與傳輸方式說明，沒有程式或依賴變更；前輪完整 gate 939 passed／19 skipped 仍保留，這次另外明確執行的真實模型測試補足其中一項 opt-in。不能將本次 reference 向量驗證當成文件檢索品質、CPU 50 題或語音驗收通過。使用者仍明確表示門檻尚未準備，T029／T039／T042 保持未完成，進度 39／42；example.md 未產包、未修改或外送。
