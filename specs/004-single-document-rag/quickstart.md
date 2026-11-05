# Quickstart Validation: 單一預建文件 RAG

這是實作完成後的驗收指南，**目前功能尚未實作，以下新增環境變數／extra／測試為計畫合約，不是已可使用的功能**。不含產包程式；完整格式見 [index-package](contracts/index-package.md)，回傳見 [search-document](contracts/search-document.md)。

## Prerequisites

1. Python 3.12、既有 README 安裝環境；個人客製化分支。若要上游貢獻，先走 AGENTS／CONTRIBUTING 的 issue 與人工審閱流程。
2. 已由外部建置者提供一份無敏感資料的完整包，只有一個文件／版本，含原文、locator、校準門檻及相容 metadata；不用自己的日常文件先試。
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

新增測試檔與 extra 由實作階段建立；不要在目前分支把不存在測試當成通過。完整 gate、基本／選用安裝及 wheel 驗證都要留下實際結果。一般 gate 不自動下載模型、調雲端或啟動 daemon。

必要情境：

| 類別 | 驗收內容／預期 |
|---|---|
| 啟用／停用 | 既有人格明確啟用才讀包；停用無存取；換人格不產生第二個 worker |
| 輸入／限額 | 空白、純標點、非字串、額外欄、501 字拒絕；合法最多三段／2,000 字，truncated 與 locator 正確 |
| 八類失敗 | 缺包、壞包、不相容、混合文件、缺原文／定位、模型未就緒、busy、timeout 均有可區分固定結果 |
| 取消／退役 | waiter 取消後 worker 未完成仍 busy；舊結果不送模型／UI／follow-up；worker 完成才釋放槽；無隱性佇列／重試 |
| HF／Gemini | generation／response epoch／duplicate ID 防遲到；manager 不丟固定錯誤碼，後續一般聊天正常 |
| 日誌 | INFO／DEBUG 加 query／段落／路徑 sentinel、malformed JSON 及底層例外；診斷無原文／向量／完整路徑 |
| 無建索引／下載 | 攔截任何寫索引／建 collection／migration／重播及外連 embedding／模型下載；嘗試即失敗 |
| 退出 | loading、busy、timeout 後停止皆回收 worker；原包不變，只清除本實例暫存資料 |

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

準備最多 1,000 段、每段 <=512 tokenizer tokens 的固定測試文件。就緒後執行 50 個 <=200 字元問題，量 monotonic 端到端工具時間、p50／p95、timeout／error 數、App 及 worker RAM 峰值與語音可用性。p95 <=5 秒，所有請求 <=10 秒完成或失敗；冷啟動／載入時間另外記錄，不能混入暖機結果。CPU 飽和時仍須能插話；如未達目標，保留失敗，不能私下換模型／量化或省略題目。

本地模型整合測試需以明確 opt-in 選項與已提供路徑執行；不存在模型時報未執行原因，不能自動下載。實作時將實際可執行命令補進根 README 及本指南，不在規劃中假造已存在的 benchmark CLI。

## HF／Gemini end-to-end acceptance

真實服務測試前確認使用者同意測試文件段落送到供應商、帳戶額度及是否使用語音／實體機器人；舊 API key 功能的授權不是本次文件外送授權。金鑰不貼聊天、不出日誌；相機／記憶保持既有關閉狀態。HF 維持預設、Gemini 由使用者手動選。

1. 固定人工標註 20 題可答（>=10 題換句話）、10 題不可答、5 題索取其他文件。檢索 >=18/20 有正確證據；兩後端各 >=18/20 答案正確，全部文件型答案可核對來源，無依據／其他文件題皆不捏造。
2. 兩後端各 10 次查詢，覆蓋 5 次插話與 5 次取消／換後端／新對話；用可控慢查詢留出操作時間。沒有遲到語音／文字／動作、舊工具重播或 App 退出，後續一般聊天正常。
3. 問原文含數字／否定／日期／表格及注入指令的題目，核對上下文、繁體中文整理／原文保留與工具權限；負向文字不能造成額外動作或資料存取。
4. 停止 App，換另一份完整單文件版本包，重啟後只引用新版本；舊結果不可重用。此為部署更新測試，並非同時支援多文件。

## Evidence and closure

記錄測試資料 digest／版本、主機、模型 snapshot、實際鎖檔、命令及結果；不寫私密段落、金鑰或日常路徑。維持原始失敗記錄，不用重測抹去第一次失敗。逐項對應 SC-001～SC-006；未驗證的平台、CPU 延遲、雲端限制與現場項目照實列未完成／限制，不以離線 pass 代替。此指南不是免除實測的簽核。
