# Quickstart Validation: 單一預建文件 RAG

這是實作完成後的驗收指南，**目前功能尚未實作，以下新增環境變數／extra／測試為計畫合約，不是已可使用的功能**。不含產包程式；完整格式見 [index-package](contracts/index-package.md)，回傳見 [search-document](contracts/search-document.md)。

## Prerequisites

**2026-11-05 開發基線（T001）**：分支 `feat/004-single-document-rag`，Python 3.12.12／Windows x86_64。Ruff check 通過、122 檔 format check 通過、strict mypy 56 source files 通過；`uv lock --check` 基線解析 139 packages，完整 pytest 793 passed（96.85 秒）。首輪 pytest 因回合中斷未完成、不計通過；接續重跑完整通過。記錄位於忽略追蹤的 `cache/004-single-document-rag/baseline-*.log`／`baseline-resume-pytest.log`，未讀日常私密設定，未啟動 App／daemon 或服務。

尚未供應本功能可驗證的單文件預建包／BGE-M3 snapshot；未掃描私人文件／既有模型快取，未下載模型。真實資產與雲端／實機驗收保持未完成，不阻擋本機離線實作；Linux／macOS 依同日後續明確指示略過，詳見平台範圍更新。既有 `.gitignore` 涵蓋 Python／venv／build／cache／秘密檔，本輪無需新增其他技術的 ignore 檔。

**T003～T018 本機進度（2026-11-05）**：已接入選用 rag extra、啟動固定路徑、typed ToolDependencies、單 worker runtime／有界協定與既有人格 Tool；提供隨 wheel 交付的 manifest schema、本機 CPU encoder／既有集合讀取、來源／原文限額與條件式指令。先完成 red tests 再實作；相關 149 項回歸通過（`us1-regression.log`），mypy 59 source files 通過，Ruff／format 通過。另有一次以 40ms 當正常查詢上限的測試因主機排程失敗，已改成只在慢工作測試暫縮 deadline、正常重問恢復十秒並等待真實完成；原失敗保留在 `us1-offline.log`，不列為服務／模型問題。

工具／索引測試均使用合成檔案與假的 encoder／Chroma，沒有真實 HNSW 不變性、BGE-M3 效能或服務驗收證據。產品 lock 的精確組合另在隔離環境 import 通過：SDK 1.12.0、HF hub 1.33.0、Chroma 1.5.9、ST 6.2.0、torch 2.15.0+cpu、transformers 5.21.0（`product-probe-import.log`）；不含 extra 的依賴匯出沒有 Chroma／ST／torch。已加入範例文件包／模型目錄忽略項，請勿把實際文件、模型或私密來源加入 Git。後續 US2／US3 進度見下列續作紀錄；這一段只記錄當時的本機 MVP，不能當作即時語音交付證據。

1. Python 3.12、既有 README 安裝環境；個人客製化分支。若要上游貢獻，先走 AGENTS／CONTRIBUTING 的 issue 與人工審閱流程。
2. 已由外部建置者提供一份無敏感資料的完整包，只有一個文件／版本，含原文、locator、校準門檻及相容 metadata，符合 [完整 JSON Schema](contracts/index-manifest.schema.json) 及包合約的額外語意條件；不用自己的日常文件先試。此 schema 不是產包工具，結構範例／dummy hash 不算可載入的真實資產。
3. 完整本機 BGE-M3 安全權重／tokenizer，與包指定 immutable revision／pipeline／runtime 一致。事先供應，對話時不下載。
4. 先隔離驗證候選依賴與 SDK、Python 3.12 的解析及 CPU wheel 安裝；成功才更新產品依賴和 uv.lock，不能以本文件宣告相容。

實作完成後的安裝／鎖檔檢查：

```text
uv sync --extra rag --group dev
uv lock --check
```

Windows／Linux torch 必須解析為官方 CPU 套件；macOS 執行仍固定 CPU。未安裝 extra、未配置、未啟用工具的普通安裝也必須可啟動／通過 gate，不 import worker 重型依賴。

## Offline behavior and quality gate

先使用 fake encoder／worker／暫存包，無網路、雲端憑證及機器人：

```text
python -m pytest tests/test_document_retrieval.py tests/test_document_worker.py tests/tools/test_search_document.py -v
python -m pytest tests/test_huggingface_realtime.py tests/test_gemini_realtime.py tests/test_prompts.py tests/test_config.py -v
ruff check . --fix
ruff format .
mypy --pretty --show-error-codes
python -m pytest tests/ -v
uv lock --check
```

上述測試與 extra 已建立；opt-in 素材測試未提供路徑時會明確略過。完整 gate、基本／選用安裝及 wheel 驗證都要留下實際結果。一般 gate 不自動下載模型、調雲端或啟動 daemon。

必要情境：

| 類別 | 驗收內容／預期 |
|---|---|
| 啟用／停用 | 既有人格明確啟用才讀包；停用無存取；換人格不產生第二個 worker |
| 包格式 | required／null／未知巢狀欄位、清單形狀、平台 enum、revision／hash 格式／重複 key；合法 schema 後仍須真實語意／檔案／引擎驗證，全部離線 |
| 輸入／限額 | 原始字串先限 500 code points，再 trim 檢查；原始 501 即使 trim 後合法仍拒絕、原始 500 有效可接受，HF／Gemini 一致；空白、純標點、非字串、額外欄拒絕，結果最多三段／2,000 字 |
| 八類失敗 | 缺包、壞包、不相容、混合文件、缺原文／定位、模型未就緒、busy、timeout 均有可區分固定結果 |
| 取消／退役 | waiter 取消後 worker 未完成仍 busy；舊結果不送模型／UI／follow-up；worker 完成才釋放槽；無隱性佇列／重試 |
| 文字逾時 | 有效回合十秒時只顯示一次固定繁體中文文字，沒有 timeout 語音／模型生成；與取消／插話／切換／queue 消費交錯後無舊提示，duplicate ID 不重複顯示，late success 永久丟棄 |
| HF／Gemini | generation／response epoch／duplicate ID 防遲到；manager 不丟固定錯誤碼，後續一般聊天正常 |
| 逾時協定 | HF timeout 不產生 response.create，但其他工具 batch 的合法 follow-up 仍正常；Gemini RAG NON_BLOCKING、timeout SILENT、成功 WHEN_IDLE，所選模型不相容要明示而非換模型 |
| 日誌 | INFO／DEBUG 加 query／段落／路徑 sentinel、malformed JSON 及底層例外；診斷無原文／向量／完整路徑 |
| 無建索引／下載 | 攔截任何寫索引／建 collection／migration／重播及外連 embedding／模型下載；嘗試即失敗 |
| 退出 | loading、busy、timeout 後都測 monotonic 5／2／2、總 <=9 秒；已退出即提前結束；未確認退出時報 cleanup_incomplete 並保留工作副本，確認退出才清理；原包不變，不要求其他 App 元件也九秒退出 |

## Actual local index and CPU validation

先記錄固定主機 OS／架構、CPU 型號、實體 RAM、可用 RAM、Python／套件／模型版本及執行緒設定；不要用包權重大小當 RAM 測量。用該平台已驗證的 snapshot，不要求跨平台臨時轉換。

Windows PowerShell 範例（僅實作後；自行替換測試路徑）：

```powershell
$env:REACHY_MINI_DOCUMENT_INDEX_PATH = (Resolve-Path 'cache/rag-acceptance/package').Path
$env:REACHY_MINI_DOCUMENT_MODEL_PATH = (Resolve-Path 'cache/rag-acceptance/model').Path
reachy-mini-conversation-app --help
```

Linux／macOS 以同名啟動環境變數設定本機路徑；不把這些變數當工具參數。只改隔離測試行程，勿覆寫日常 `.env`、人格／記憶資料。使用既有工具設定啟用 `search_document` 後按 README 的既有方式啟動；啟動機器人可能有動作，須有現場可配合的驗收範圍。

第一次明確查詢可回尚未就緒，確認模型載入後再明確查詢；不自動重播第一問。測試前後核對原包 hash、工作副本文件／向量／count 及 HNSW 不變性；以唯讀原包、缺集合、需 migration、未 flush snapshot 再測，不能自動修復。

準備最多 1,000 段、每段 <=512 tokenizer tokens 的固定測試文件。就緒後依固定順序執行 50 個 <=200 字元問題，量 monotonic 端到端工具時間、是否成功取得段落、timeout／error 數、App 及 worker RAM 峰值與語音可用性。硬門檻是至少 48／50 題在五秒內成功取得段落，且全部題目十秒內完成或明確失敗；無依據、busy、not_ready、timeout／error 即使快速回傳也不計成功，不剔除失敗改分母。p50／p95 可另報，不能單憑 percentile 宣稱通過；報表說明其分母／取法，冷啟動／載入時間另外記錄，不能混入暖機結果。CPU 飽和時仍須能插話；如未達目標，保留失敗，不能私下換模型／量化或省略題目。

本地模型整合測試需以明確 opt-in 選項與已提供路徑執行；不存在模型時報未執行原因，不能自動下載。實作時將實際可執行命令補進根 README 及本指南，不在規劃中假造已存在的 benchmark CLI。

## HF／Gemini end-to-end acceptance

真實服務測試前確認使用者同意測試文件段落送到供應商、帳戶額度及是否使用語音／實體機器人；舊 API key 功能的授權不是本次文件外送授權。金鑰不貼聊天、不出日誌；相機／記憶保持既有關閉狀態。HF 維持預設、Gemini 由使用者手動選。

1. 固定人工標註 20 題可答（>=10 題換句話）、10 題不可答、5 題索取其他文件。檢索 >=18/20 有正確證據；兩後端各 >=18/20 答案正確，全部文件型答案可核對來源，無依據／其他文件題皆不捏造。
2. 兩後端各 10 次查詢，覆蓋 5 次插話與 5 次取消／換後端／新對話；用可控慢查詢留出操作時間。沒有遲到語音／文字／動作、舊工具重播或 App 退出，後續一般聊天正常。
3. 問原文含數字／否定／日期／表格及注入指令的題目，核對上下文、繁體中文整理／原文保留與工具權限；負向文字不能造成額外動作或資料存取。
4. 停止 App，換另一份完整單文件版本包，重啟後只引用新版本；舊結果不可重用。此為部署更新測試，並非同時支援多文件。
5. 用可控慢 worker 讓每個後端各出現 timeout：有效原回合只看到一次「文件查詢已逾時，請稍後再試。」且沒有該錯誤觸發的語音；取消／插話／切換則連提示也不出現。duplicate 不重播、晚到成功不朗讀，接著明確新提問仍能正常語音。雲端協定支援不可只靠 fake 成功認定。
6. 依 FR-016 記錄 RAG worker 實際退出與副本清理；用受控卡住 child 測九秒截止及保留副本分支，不把 App 其他關閉作業算進或聲稱也受此九秒上限。

## Evidence and closure

記錄測試資料 digest／版本、主機、模型 snapshot、實際鎖檔、命令及結果；不寫私密段落、金鑰或日常路徑。維持原始失敗記錄，不用重測抹去第一次失敗。逐項對應 SC-001～SC-006 及 FR-016，包含 schema 正反例、文字 timeout／零語音、九秒關閉與 48／50 成功計數；未驗證的平台、CPU 延遲、雲端限制與現場項目照實列未完成／限制，不以離線 pass 代替。此指南不是免除實測的簽核。tasks.md 已依實際證據逐項更新；未完成的實際素材／服務驗收保留未勾選。


## 續作紀錄（2026-11-05）

- US2：故障矩陣、六種錯誤經真實 BackgroundToolManager 保留、取消後 busy、初始化期限、單一 monotonic 九秒回收及未確認退出時保留副本的離線測試已完成。拒絕未完成 snapshot／資料庫 journal、migrations、混合來源、錯誤雜湊、模型模組路徑跳脫、缺少模型與壞向量；不呼叫建立／寫入 API。
- US3：HF／Gemini 共用 generation、response epoch、answer_retired／timeout_notice_sent。只在原回合有效時經 AdditionalOutputs 顯示固定文字一次；不另加 transcript append。HF 不因 timeout 排程 response.create，保留 mixed-tool 的其他合法 follow-up；Gemini 使用 NON_BLOCKING declaration，結果 WHEN_IDLE、timeout SILENT。跨 provider wait／socket lock／queue 消費均檢查有效性，duplicate 不重啟 CPU 工作；取消／插話／停用／新對話後丟棄舊結果。task_status 僅回文件工作的狀態，不重送原段落。
- 依官方 [Live tools 文件](https://aistudio.google.com/docs/live-api/tools#async-function-calling) 設明確非同步模型能力檢查；本機白名單為 gemini-3.8-live、gemini-3.8-live-extended-thinking、gemini-2.5-flash-native-audio-preview-12-2025。其他模型在有啟用文件工具時明確 setup 失敗，不換模型／供應商；這不是實際服務排程驗收。
- 已修正 ready handshake 的文件識別須與 query 結果完全一致，避免來源 digest 內部欄位造成誤判。此問題由離線協定回歸涵蓋，沒有宣稱曾成功載入真實索引。
- 根 README／環境範例與 Mermaid 架構圖已同步。SVG 由既有 CLI 重新產生，PNG 預覽確認內容完整；未手改 SVG。
- Windows Python 3.12 的 wheel 測試確認 runtime、worker、Tool 與完整 schema 一併交付，schema 與規格合約相同；在 checkout 之外匯入 runtime 不載入 Chroma／torch／ST。普通依賴匯出不含 rag；另以產品鎖檔的 rag 隔離環境驗證 CPU wheel／imports／mypy 與全套測試。未執行 Linux／macOS，不能以 Windows 結果代替。
- 本輪使用者回覆「尚未準備」索引包與模型。T026 真實 Chroma／HNSW 不變性、T040 真實 CPU 50 題、T041 品質及 T042 兩後端語音／插話驗收都保留未完成，沒有下載模型、產生索引、讀取私密文件、連雲端或啟動機器人。

### 已提供素材後的本機 opt-in 命令

以下變數僅供測試，不是產品新增設定。只設定在隔離測試行程；請使用已驗證相容且可公開測試的素材。問題 JSON 是恰好 50 個有效問題的陣列，每題 <=200 Unicode 字元；在外部先確認文件 <=1,000 段、每段 <=512 BGE tokenizer tokens。此工具沒有產包器。

```powershell
$env:RAG_ACCEPTANCE_PACKAGE = '完整索引包資料夾'
$env:RAG_ACCEPTANCE_MODEL = '對應本機模型資料夾'
$env:RAG_ACCEPTANCE_QUESTIONS = '固定五十題.json'
python -m pytest tests/test_document_worker.py -k external_prebuilt -v
python -m pytest tests/test_document_retrieval.py -k external_cpu -v --basetemp=cache/rag-cpu-acceptance
```

第一個測試以真實 Chroma 檢查原包雜湊、工作副本原文／metadata／向量／count 及 HNSW 雜湊不變性，失敗不能當作已支援。第二個經現有 Tool 量測 50 題，產生 `cache/rag-cpu-acceptance/` 下的 `cpu-benchmark.json`：記錄主機／RAM／runtime／revision／資料 digest、載入時間、逐題時間／段落數／錯誤、p50／nearest-rank p95（50 題分母）與 App／worker RSS 取樣峰值。取樣不代表 OS 的精確瞬時峰值，實際語音可用性仍須 T042。只有 >=48/50 題五秒內取得段落且所有題目十秒內完成才通過；47/50、錯誤／無依據及縮小分母的反例已有離線測試。缺素材時的 skip 不是通過。


### 最後離線 gate 證據

本輪完整 `.venv` gate：Ruff check／format、strict mypy（59 source files）、`pytest tests/ -v` **897 passed／2 skipped**（`cache/004-single-document-rag/final-review.log`）、`uv lock --check` 通過。兩個 skip 是上面列出的真實素材 opt-in，未降低成功門檻。產品鎖檔的隔離 rag 環境另有全套 880 passed／2 skipped（較早 snapshot，`rag-installed-gate.log`）及 mypy 59 files 通過；最後的 RAG／兩個 handler／manager 回歸另行補驗，不把早期數字冒充最新完整 gate。

最後審查新增兩個 regression：HF 合併空回覆時保留帶回合所有權的 document follow-up；BackgroundToolManager 的文件通知不排在其他工具等待雲端的 callback 後面，避免延遲本機十秒逾時文字。RAG 仍走同一 Tool／dispatcher／manager；其他工具保留原通知路徑。網路傳送失敗只記錄安全固定訊息，本機 timeout notice 仍可顯示。已保留先失敗、修正後通過的測試紀錄；本輪無真實服務／文件事件可宣稱修復。

目前 FR-001～FR-016 具程式與離線回歸對應；SC-001／002 文件品質、SC-003 實際 CPU、SC-004 實際語音、SC-005 真實 Chroma 不變性及 SC-006 兩服務內容／日誌驗收尚待 T026／T040～T042。T039 依使用者對本功能的明確指示略過 Linux／macOS，兩平台仍未驗證。以上限制不影響繼續一般未啟用 RAG 的使用，但本 feature 保持未結案。

最終 rag 隔離環境複驗：strict mypy 59 source files 通過（`rag-final-mypy.log`）；RAG、HF／Gemini、BackgroundToolManager、task_status 共 **275 passed／2 skipped**（`rag-final.log`）。這是最後 source snapshot 的相關回歸，較早的全套 rag 880 項結果仍依原 snapshot 保留。


## 平台範圍更新（2026-11-05）

使用者明確指示「略過Linux與Mac測試」，本次個人客製化以已完成的 Windows Python 3.12 普通／rag 安裝、CPU wheel／import、wheel 內容／checkout 外 runtime 及完整 gate 證據完成 T039。Linux／macOS 記為使用者要求略過，不記 pass，也不新增相容性保證。跨平台程式要求、既有 CI 與包的平台／架構驗證保持不變。

略過指示前已在 Ubuntu 24.04 檢查到 Python 3.12.3，並嘗試在 `cache/004-single-document-rag/linux-project/` 以原產品 lock 準備隔離環境；165 個依賴已完成下載／建置，寫入環境尚未完成。收到指示後只終止該專用 uv 命令，確認行程退出碼 15（依指示取消），沒有執行 Linux imports／Ruff／mypy／pytest／wheel／模型驗收。只使用工作區 cache，未安裝系統套件、未讀私密文件或憑證、未下載模型、未啟動機器人；cache 與原安裝紀錄 `linux-sync.log` 保留，不能作為驗收成功證據。macOS 未執行。

本輪只調整計畫、任務及驗收紀錄，沒有變更產品程式或依賴，沿用既有 897 passed／2 skipped 與相關 gate 證據，不重跑相同測試。進度為 39／44；剩餘 T026／T040／T041／T042／T044 等待實際素材與後續驗收，功能尚未結案。
