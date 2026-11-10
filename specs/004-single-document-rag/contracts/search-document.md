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

1–3 段；原文合計 <=2,000 code points；metadata 上限見 [data-model](../data-model.md)。只含唯一包指定來源，沒有 vectors、檔案路徑、整份文件或相關度百分比。排序為 BGE-base 原始 logit 降序，同分以 chunk_id 穩定排序；內部先 exact dense10＋BM25 正分10 經等權 RRF60 合併至多五個不同完整候選，再重排。第一名與附加段落均須 logit>=3.486859679222107，附加分差<=4，不限同父章節／無群組分差。先依排序選至多三段並套2,000 code points預算，再以父向量cosine<=0.58篩選：第一名超限則整次no_evidence；否則移除超限附加段，不補段、不替換第一名、不重排。詳見 [v2 包合約](index-package.md)。

僅回傳重排實際可見的原文；512 pair tokens裁切須保留query並對照來源offset，不能回傳未評分尾文。文字預算只取連續原文前綴，truncated=true；定位仍是真實行範圍。模型脈絡中的章節／人工別名不能冒充引文。參數只存在預建方案，不由工具query覆寫。

這是使用者選定的實驗方案，0.58不是獨立可信度或充分答案保證；不新增充分性規則／模型／雲端審核。對話模型還須核對段落支持程度、否定／數字／單位／日期；不足時說明找不到依據。繁體中文整理答案，引用保持原文。文字附文件名、版本及真實 locator；語音簡短指來源，無需朗讀全部 IDs。

## Error result

| error 固定字串 | 意義／對話行為 |
|---|---|
| document_not_ready | 三個路徑任一缺漏、選用套件／嵌入或重排模型缺失、載入中或模型初始化失敗；明確說尚未就緒，可稍後手動再問或請部署者處理 |
| document_busy | 原 CPU 工作仍執行；不排隊、不自動重試 |
| document_unavailable | 包缺失、壞檔、混合來源、缺預建BM25／脈絡、舊v1或相容／開啟失敗；v1提示離線重產，不修補、補建、降級或換來源 |
| document_invalid_query | 輸入未符 schema／語意限制；請縮短或重新表述 |
| document_no_evidence | 有效檢索未通過既定logit／距離條件或無候選；不代表可靠判斷了原文充分性；不以其他知識冒充文件 |
| document_timeout | 有效請求受理起達十秒；原回合仍有效時只顯示一次文字，不播放語音；原工作未必已停止，不自動重送 |

形狀只有 `{"error": "document_timeout"}` 等安全固定碼；預期錯誤在產生邊界以安全碼記錄。manager／兩後端須保留此字串，不轉成無法區分的通用錯誤。意外錯誤記錄安全例外類別，對外 unavailable，不回 traceback 或原始訊息。取消沿既有 tool cancelled 流程，但退役 callback 不送舊錯誤到新回合。

### Timeout display and protocol completion

固定本機文字為「文件查詢已逾時，請稍後再試。」；timeout_notice_sent 僅允許恰一次顯示，經既有 AdditionalOutputs 顯示入口，不再經模型生成或第二條 transcript append。背景答案在十秒期限時永久退役；notice 顯示前、跨 await 後及 queue 消費時仍須檢查原 generation／response epoch，若已失效就不顯示，也不在新對話補送。

本機十秒 deadline 與 provider 清理分開：提示不先等待 response.done 或 function response 傳送。網路上的協定完成用既有有界等待，且每次送出前重驗原 call 所有權，不能因此延後本機提示或把舊結果帶入新 session。

仍有效的 call 要完成 provider 協定，但不得因此發起逾時語音：HF 送固定 function_call_output 並完成此 call bookkeeping，跳過由此錯誤引起的 response.create／batch needs_response；其他非 timeout 工具正常需要的回覆不受影響。Gemini 僅此工具宣告 NON_BLOCKING，成功用 WHEN_IDLE、timeout 用 SILENT 的 per-result scheduling；保留 needs_response=true，不沿用整工具 silent flag。Gemini 對選定模型的排程支援須驗證，不支援就回報 RAG 不相容，不偷換模型或 provider。

duplicate ID 可在協定要求下對有效原 call 回應固定 silent timeout，但不能重查、重複 notice 或發起生成。若 call 已因回合／session 退役則不向新 session 送任何完成訊息。兩後端要覆蓋 timeout 與取消交錯、重複通知、late success、HF mixed-tool batch、Gemini wire scheduling，以及下一個使用者回合仍有正常語音；不能只靠 needs_response=false 或 system prompt 宣稱通過。

## Legacy v1 local notice

確認為v1包時對外仍只有 `{"error":"document_unavailable"}`，不新增公開error／reason／message欄位，不把本機格式原因送provider。另由共享handler經既有DocumentOutput／AdditionalOutputs本機文字入口顯示：「此文件索引為舊版，請停止 App，使用離線產包腳本重新產生新版索引包。」不帶路徑、不額外排TTS／response.create或追加第二條逐字稿；一般document_unavailable的provider錯誤對話維持既有行為，不把它改成timeout的SILENT特例。

原因來自下節私密failure的typed reason與runtime快取，不能依query、例外字串或所有unavailable推測。只在已啟用工具、query有效、通知成功通過結果驗證且原call仍有效時顯示；結果驗證拒絕後合成的unavailable、其他包故障、缺配置、無效query及停用工具均不出舊包提示。

每個invocation新增獨立legacy_notice_sent，設true後才入queue，duplicate同call最多一次；同一壞包下一個明確有效call可再提示一次。入queue前與emit消費時檢查generation／response_epoch／tool權限，插話／取消／停用／換供應商／新對話後丟棄，不在新回合補送。它不重設timeout_notice_sent或復活answer_retired。

首次query目前可回not_ready以觸發載入；初始化thread後來識別v1只快取原因，不直接發UI或對首問補送。下一次明確有效query拿到快取unavailable時才顯示。原包不開Chroma／改寫、不自動產包／下載或換來源。至少測有效call一次／duplicate／queue後失效／首問已結束後載入失敗／再次明確查詢及其他故障不誤提示，兩後端共用一份顯示邏輯。

## Ownership / side effects

每次呼叫保存 generation／response epoch，與 answer_retired、timeout_notice_sent 分別追蹤。成功結果與 timeout notice 依各自資格在投遞前／跨 await 後重驗；接受插話、取消、停用、換供應商或新對話時兩者都退役。重複 call ID 不重跑或重播已退役結果。逾時／取消不釋放正在執行的實體工作槽；直到 worker 完成前，新查詢 busy。

App 結束先撤銷全部投遞資格；以單一 monotonic 九秒期限回收 worker：正常關閉最多五秒、terminate 後最多兩秒、kill 後最多兩秒，均再限制於總期限剩餘時間，提前退出不等滿。確認退出才清工作副本；仍未確認退出則回報 cleanup_incomplete、保留副本，不無界等待，不碰原包／模型。這是 RAG worker 的期限，不是整個 App 的退出保證。

工具只有檢索能力，不觸發其他工具／動作、改設定、相機或記憶。段落可傳給目前供應商以回答；不得用檢索資料觸發重連、自動換後端或隱性背景重送。

## Private worker boundary

不是公開 API 或網路服務。私密 pipes 採逐行 JSON，版本 `1`；控制訊息有 `type`（ready／query／result／failure／close）及 request_id。query 僅含驗證後的文字；result payload 必須先經上述限額及來源檢查。包／模型路徑只在本機啟動配置傳入，不放模型結果或日誌；不從模型參數取路徑。

初始化failure可多一個私密可選reason欄位，僅允許 `{"version":1,"type":"failure","error":"document_unavailable","reason":"legacy_package"}` 這種已確認舊包原因；不帶原文／路徑。reason省略表示沒有特定原因，不接受null／未知值／不相容error組合；不作v2包schema或公開Tool結果的一部分，私密協定仍版本1，兩端實作同步驗證。

worker先在有界UTF-8／JSON／重複key等安全檢查後辨認頂層整數schema_version=1（bool不算），於開引擎前拒絕；其他損壞／未知版本不冒稱v1。runtime以宣告的唯讀型別unavailable_reason快取legacy_package或None，受鎖保護，初始化／關閉清除，公用query結果不變。handler唯讀取得此本機屬性，不把它序列化到模型／一般設定查詢。

parent 限定每行最多 64 KiB、拒絕未知型別／錯 request_id／非 JSON 輸出；一次只允許一份 query，沒有在 pipe 中預排的多個問題。worker initialization 以獨立 ready 事件表示，載入期間不送問題。結果大小、固定 error 及 metadata 都在 parent 再驗，不能把 worker 任意原始輸出鏡射到模型或終端。協定錯誤記安全碼並進 failed，沒有自動重啟。

## Privacy acceptance

把專用 sentinel 放進有效／無效 query、文件段落及會失敗的路徑，開 INFO／DEBUG 檢查 RAG tool call、dispatcher、worker 及結果診斷；不得出現 sentinel、向量或絕對路徑。模擬底層例外亦不可洩漏原始訊息。既有正常回答／引用逐字稿不屬此診斷限制；不宣稱全 App 其他日誌已重新設計。

## 新版交付界線（2026-11-09）

本工具輸入／結果形狀與私密worker協定版本1不變；包格式v2是另一個版本範圍。200題是曝光回放，84／100正例、2／100負例誤放行及127／131段落支持保留，不稱新盲測或原品質合格。五秒成功率僅觀察，不影響本契約十秒deadline／文字逾時、退役、隱私與禁止捏造要求。新版流水線及U2本機提示已完成離線實作；正式CPU／雙後端與現場驗收狀態見quickstart，未完成前不宣告整體交付。
