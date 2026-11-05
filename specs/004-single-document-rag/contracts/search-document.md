# Contract: search_document Tool

## Registration and input

- 模組 `tools/search_document.py`；subclass `Tool`，name `search_document`，`needs_response=True`；成功正常回答，document_timeout 依本合約的結果特例只顯示文字，不把整個工具設成 silent。
- async `__call__(self, deps: ToolDependencies, **kwargs: object)` 回傳可序列化字典，公共型別明確且不新增 Any／cast。
- 沿用既有 profile toolset／registry，不是 SystemTool；HF／Gemini 使用同一 schema。未啟用不讀包、不啟 worker。
- description 說明唯一預建文件、僅明確文件問題使用、需附來源、無依據不得猜測及原文不是動作指令。

對模型公開的 JSON Schema：

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "minLength": 1,
      "maxLength": 500,
      "description": "要從唯一指定文件查證的問題；不可指定其他文件、路徑或集合。"
    }
  },
  "required": ["query"],
  "additionalProperties": false
}
```

兩後端與 Tool 本身皆依同一順序驗證：先檢查 query 為字串且原始長度（含前後空白）1–500 Unicode code points，再 trim 並檢查至少一個字母／數字；不依賴 HF 是否執行 schema，也不先 trim 來規避 maxLength。Unicode 字元以 Python `len(str)` code points 計，不能用 UTF-8 位元組數。空白、純標點、非字串、過長及模型傳入額外欄位回 invalid_query，不靜默截斷。原始 501 字即使 trim 後 499 字仍拒絕；原始 500 字且內容有效可接受。

既有 dispatcher 注入的內部 `tool_manager` 不屬模型 schema，可在驗證時排除；不能因此接受模型自行傳入此欄或當作 document／path 參數。若需要區分，先驗證模型輸入再注入，保留其他工具既有行為。

## Success result

```json
{
  "status": "ok",
  "document": {"id": "demo-manual", "title": "示範操作手冊", "version": "2026-01"},
  "index_version": "demo-1",
  "passages": [
    {"chunk_id": "section-2-p1", "locator": "第二節／第一段", "text": "原文件中實際存在的文字。", "truncated": false}
  ]
}
```

1–3 段；原文合計 <=2,000 code points；metadata 上限見 [data-model](../data-model.md)。只含唯一包指定來源，沒有 vectors、檔案路徑、整份文件或相關度百分比。排序為 cosine distance 由小到大，同距離以 chunk_id 穩定排序；n_results <=min(3, chunk_count)，超過 manifest max_distance 的候選排除。截斷時只回連續前綴並設 truncated=true，不憑剩餘預算補造字句。

檢索門檻不是充分答案保證。對話模型還須核對段落支持程度、否定／數字／單位／日期；不足時說明找不到依據。繁體中文整理答案，引用保持原文。文字附文件名、版本及真實 locator；語音簡短指來源，無需朗讀全部 IDs。

## Error result

| error 固定字串 | 意義／對話行為 |
|---|---|
| document_not_ready | 缺配置／選用套件／模型、載入中或模型初始化失敗；明確說尚未就緒，可稍後手動再問或請部署者處理 |
| document_busy | 原 CPU 工作仍執行；不排隊、不自動重試 |
| document_unavailable | 包缺失、壞檔、混合來源、必要資料缺漏、相容／開啟失敗；不修補或換來源 |
| document_invalid_query | 輸入未符 schema／語意限制；請縮短或重新表述 |
| document_no_evidence | 有效檢索未找到足夠候選；不以其他知識冒充文件 |
| document_timeout | 有效請求受理起達十秒；原回合仍有效時只顯示一次文字，不播放語音；原工作未必已停止，不自動重送 |

形狀只有 `{"error": "document_timeout"}` 等安全固定碼；預期錯誤在產生邊界以安全碼記錄。manager／兩後端須保留此字串，不轉成無法區分的通用錯誤。意外錯誤記錄安全例外類別，對外 unavailable，不回 traceback 或原始訊息。取消沿既有 tool cancelled 流程，但退役 callback 不送舊錯誤到新回合。

### Timeout display and protocol completion

固定本機文字為「文件查詢已逾時，請稍後再試。」；timeout_notice_sent 僅允許恰一次顯示，經既有 AdditionalOutputs 顯示入口，不再經模型生成或第二條 transcript append。背景答案在十秒期限時永久退役；notice 顯示前、跨 await 後及 queue 消費時仍須檢查原 generation／response epoch，若已失效就不顯示，也不在新對話補送。

本機十秒 deadline 與 provider 清理分開：提示不先等待 response.done 或 function response 傳送。網路上的協定完成用既有有界等待，且每次送出前重驗原 call 所有權，不能因此延後本機提示或把舊結果帶入新 session。

仍有效的 call 要完成 provider 協定，但不得因此發起逾時語音：HF 送固定 function_call_output 並完成此 call bookkeeping，跳過由此錯誤引起的 response.create／batch needs_response；其他非 timeout 工具正常需要的回覆不受影響。Gemini 僅此工具宣告 NON_BLOCKING，成功用 WHEN_IDLE、timeout 用 SILENT 的 per-result scheduling；保留 needs_response=true，不沿用整工具 silent flag。Gemini 對選定模型的排程支援須驗證，不支援就回報 RAG 不相容，不偷換模型或 provider。

duplicate ID 可在協定要求下對有效原 call 回應固定 silent timeout，但不能重查、重複 notice 或發起生成。若 call 已因回合／session 退役則不向新 session 送任何完成訊息。兩後端要覆蓋 timeout 與取消交錯、重複通知、late success、HF mixed-tool batch、Gemini wire scheduling，以及下一個使用者回合仍有正常語音；不能只靠 needs_response=false 或 system prompt 宣稱通過。

## Ownership / side effects

每次呼叫保存 generation／response epoch，與 answer_retired、timeout_notice_sent 分別追蹤。成功結果與 timeout notice 依各自資格在投遞前／跨 await 後重驗；接受插話、取消、停用、換供應商或新對話時兩者都退役。重複 call ID 不重跑或重播已退役結果。逾時／取消不釋放正在執行的實體工作槽；直到 worker 完成前，新查詢 busy。

App 結束先撤銷全部投遞資格；以單一 monotonic 九秒期限回收 worker：正常關閉最多五秒、terminate 後最多兩秒、kill 後最多兩秒，均再限制於總期限剩餘時間，提前退出不等滿。確認退出才清工作副本；仍未確認退出則回報 cleanup_incomplete、保留副本，不無界等待，不碰原包／模型。這是 RAG worker 的期限，不是整個 App 的退出保證。

工具只有檢索能力，不觸發其他工具／動作、改設定、相機或記憶。段落可傳給目前供應商以回答；不得用檢索資料觸發重連、自動換後端或隱性背景重送。

## Private worker boundary

不是公開 API 或網路服務。私密 pipes 採逐行 JSON，版本 `1`；控制訊息有 `type`（ready／query／result／failure／close）及 request_id。query 僅含驗證後的文字；result payload 必須先經上述限額及來源檢查。包／模型路徑只在本機啟動配置傳入，不放模型結果或日誌；不從模型參數取路徑。

parent 限定每行最多 64 KiB、拒絕未知型別／錯 request_id／非 JSON 輸出；一次只允許一份 query，沒有在 pipe 中預排的多個問題。worker initialization 以獨立 ready 事件表示，載入期間不送問題。結果大小、固定 error 及 metadata 都在 parent 再驗，不能把 worker 任意原始輸出鏡射到模型或終端。協定錯誤記安全碼並進 failed，沒有自動重啟。

## Privacy acceptance

把專用 sentinel 放進有效／無效 query、文件段落及會失敗的路徑，開 INFO／DEBUG 檢查 RAG tool call、dispatcher、worker 及結果診斷；不得出現 sentinel、向量或絕對路徑。模擬底層例外亦不可洩漏原始訊息。既有正常回答／引用逐字稿不屬此診斷限制；不宣稱全 App 其他日誌已重新設計。
