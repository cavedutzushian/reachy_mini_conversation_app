# Contract: 固定50題CPU量測與人工證據核對

本合約落實SC-003／U1，只定義實作後的離線驗收輸入／紀錄，不是新產品CLI、執行期充分性規則或模型。資料僅放工作區cache，使用明確提供的無敏感單文件；不搜尋私密文件、下載模型或連雲端。五秒／品質比例維持非阻擋觀察，十秒期限／退役與工程gate仍必須驗證。

## 測前凍結的輸入

沿既有external_cpu opt-in測試入口，將原問題字串陣列擴充為版本化dataset物件；舊陣列缺人工標註，不得當作新合約資料或自動補答案。檔案採UTF-8 JSON、拒絕重複key／非有限數／未知欄位，所有required欄不得null。runner只讀資料，不從檔案載入程式碼、路徑參照或URL。

| 欄位 | 型別／條件 |
|---|---|
| schema_version | 整數1，不接受bool |
| dataset_id / dataset_version | 各為非空安全identifier，最多128 code points |
| document | 只含id、version、source_sha256；與包唯一文件相符，digest為64位小寫hex |
| questions | 恰50項，順序固定，id全體唯一 |
| questions[].id | 非空安全identifier，最多128 code points |
| questions[].query | 原始1～200 Unicode code points，trim後至少有字母／數字；仍遵工具原始500上限，不靜默裁切 |
| questions[].answerability | answerable或unanswerable；不是測後依結果填寫 |
| questions[].required_information | 字串陣列；answerable至少一項非空必要資訊，unanswerable為空；項目是回答問題不可缺的事實／條件 |
| questions[].evidence | 原文證據物件陣列；answerable至少一項，unanswerable為空；每項只含text、start、end、locator |
| evidence[].text / start / end / locator | 非空原文連續切片，0-based code point半開範圍、0<=start<end且end-start=len(text)，locator為真實來源定位；測前人工核對同文件版本 |

safe identifier沿包合約的英數首字元與英數／點／底線／連字號，不含路徑。問題可要求多項資訊，原文可跨多段共同提供；必要資訊與證據不得根據檢索結果刪減。gold evidence是事先人工核對的依據，不要求返回相同chunk_id或逐字等於整段gold，因切段／裁切可能不同；仍只依固定文件與實際可見原文判定。

測前記錄完整dataset bytes SHA-256、文件／包／兩模型／lock身分、固定主機CPU／RAM／OS／架構及threads。標註若有錯或文件已變，保留原run並標記annotation_invalid，不改既有分母或舊失敗；修訂dataset_version、digest與run_id後另跑，不稱獨立盲測。此合約不新增正負題比例要求；不可答題正確拒答另列expected_refusal，不算提供支持段落的成功數。

## 執行紀錄與計時

記錄schema_version、run_id、dataset_id／version／sha256、document／index_version／package digest、兩模型revision／runtime、固定主機與執行緒、初始化／暖機時間、每題原始結果、RSS取樣方式。每題依dataset順序單次執行，不自動重送；忙碌／未就緒／逾時也保留原題與分母。題間等待若有須另記，不能併入人工時間或隱藏排隊成本。

每題CpuObservation有question_id、accepted_at_monotonic、finished_at_monotonic、elapsed_seconds、outcome、result。outcome為ok或既有六種document_*錯誤；result為原始有界Tool結果／固定錯誤，不含embedding或模型檔案。所有時間有限非負，elapsed為工具受理有效問題至結果／十秒逾時的monotonic差；HTTP/provider與人工判讀不在本次本機工具延遲中。初始化載入獨立記錄，不以快速not_ready混作暖機後成功。

只有對照本次50題的原始計時與結果，才能產生延遲摘要；不得讀歷史快取分數當本次執行。預設測試使用假資料，真實包／CPU需要明確opt-in。此驗收紀錄是受控測試輸出，不是App持久化query cache或診斷日誌；終端僅安全計數與摘要，不傾印原文／私密路徑。

## 測後人工核對

每題ManualEvidenceReview含run_id、question_id、reviewer（非個資標籤）、reviewed_at_utc、review_seconds、decision、annotation_status、checks、reason。decision為pending／supported／unsupported／uncertain／not_applicable；annotation_status為pending／valid／invalid，invalid對應annotation_invalid並要求decision=uncertain、保留理由；checks依固定required_information順序逐項記satisfied／missing／uncertain與對應回傳chunk_id及可見原文定位，reason記判讀理由。review_seconds有限非負，reviewed_at_utc為UTC ISO8601；pending時判讀時間／reviewer可省略，不能偽造已完成核對。

- 先確認Tool回ok，再人工檢查實際返回且模型評分可見的原文，不能拿未回傳全文、別名／標題脈絡或未評分尾文補答案。
- 合起來涵蓋全部必要資訊且無缺漏／不確定才supported；僅主題相近、姓名／日期／單位缺項或相互矛盾不算支持。只允許必要的原文理解，不補常識或外部來源。
- 任一必需項missing則unsupported；無法確定則uncertain。資料標註不合法另記annotation_invalid與理由，decision=uncertain；不為讓結果好看事後改gold。
- Tool失敗／無依據時not_applicable，保留錯誤類型；unanswerable題即使正常回段落也不得計為supported，可另記負例放行／expected_refusal。
- pending／unsupported／uncertain／not_applicable均不計成功。人工核對時間另報，不能加進或扣改已固定工具elapsed_seconds。由測試驅動的明確pending→人工final判定是報表更新，不是重新執行或覆寫原始觀察。

## 摘要與驗收

全部50題保留，分開列正常ok、具支持成功、無支持放行、無依據／busy／not_ready／timeout／其他操作失敗及pending／uncertain／annotation_invalid。五秒內成功須同時為ok、人工supported、工具elapsed<=5；超五秒supported另列，不算五秒內。逾時及未支持不能以回傳迅速美化成功率。

p50／p95／max對完整50筆有限elapsed按nearest-rank計算（p50取排序第25、p95第48），成功子集另報樣本數與相同取法，空子集回無資料。冷載入與RSS取樣峰值另列，不用權重檔大小當RAM。五秒比例、召回／支持率不是方案選用阻擋；量測、人工核對、十秒完成或明確逾時與晚到結果退役仍不可省略。

以合成資料驗以下報表規則：ok但不支持不成功、uncertain／pending不成功、超五秒支持不算五秒內、人工耗時不改工具延遲、錯題保持50分母、無成功子集不除零、47／50與48／50只為觀察而非舊品質gate。真實CPU與雙後端／音訊安全另外依quickstart實測；本合約不是本輪測試通過證明。
