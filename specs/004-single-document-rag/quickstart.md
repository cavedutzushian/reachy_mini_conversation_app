# Quickstart Validation: 單一預建文件 RAG

**2026-11-10：v2共用reader／三路徑及U2本機提示已完成離線實作；固定50題人工核對runner亦已更新。T069真實包獨立驗收已於下方最新紀錄通過；CPU50題已完成量測及測後人工核對，音訊與雙後端／現場仍未完成，不宣告004整體結案。** 下列2026-11-05與2026-11-09的基線／失敗屬歷史，不能當作目前產品狀態。不含產包程式；完整格式見 [index-package](contracts/index-package.md)，回傳見 [search-document](contracts/search-document.md)。


## 20組FAQ正式採用與收尾（2026-11-10，37／40，部分交付）

使用者要求按照建議執行，已將核對過的20組「問題＋短答案＋原文出處」寫入example.md，原文前段逐位元組保留，備份及全部證據在 `cache/004-single-document-rag/20261110-faq-adoption-v1/`。新source SHA為683495020805b60f3322f3e8db044bcdfce4e7622c00474b6013bd91b846b5d3，既有正式CLI全量產生330段v2包並由獨立fresh verifier驗證，exit0；document_version=faq-source-683495020805，index_version=v2-20261110-faq20。原包未覆蓋。正式reader另驗20／20預設題完整FAQ答案，source／包inventory前後不變；維持3.486859679222107／分差4／cosine0.58／五候選／三段2000字元，沒有採用0.81或拆句等實驗方案。

本輪隔離實例 `cache/004-single-document-rag/20261110-faq-live-v1/` 實際使用新包。事前固定每後端35題（20可答含10改寫、10資料不足、5其他文件），dataset SHA118844af36042295744acd941e8d943be7ea9d0a93bcd77b9f0b2fa468c602cd。HF35完整觀察：Tool20／20完整取回FAQ，逐字稿14／20保留全部必要資訊、3明確錯誤、3不足／不確定；15／15無依據／其他文件拒答。回覆書名全誤成「八年速成論」，學校及里程碑等錯誤逐題保留，不宣告忠實引用通過。

Gemini35案例分兩檔保留：Tool19／20完整取回、逐字稿19／20完整，Q13改寫未取回而拒答。無依據題14／15於窗內拒答，Q37未在60秒provider觀察窗完成，後有晚到定價拒答仍不改算成功；當時RAG工作約1.7秒，不能混成十秒worker deadline故障。剩餘批次在Q38送出前遇access_unavailable，確認同一後端明確重連後才執行Q38～Q50十三題，沒有重跑Q37。Gemini書名／版本／行號同時出現5／20，部分引用FAQ原文出處、部分缺欄；引用契約仍未完整驗收。固定文字仍逐題啟動新Gemini對話，沒有修改其對話處理或宣稱測過連續性。

上述為助手逐字稿與原文核對，不冒充使用者逐題人工驗收或獨立音訊辨字。使用者最後確認「有正常回復，語音除中途中斷連線皆正常」；不以問候補算Q13／Q37或名稱錯誤。daemon為mockup_sim_enabled=true，SDK1.12／daemon1.14差異、控制連線遺失及退出警告保留，不記實體動作通過。臺北22:59:47 worker2.813秒closed，22:59:48隔離credential cleared=true；metadata再驗active／pending空、retired清單空，未讀日常憑證，App已停止。

完整gate：Ruff／format及strict mypy64 source files通過，1067 passed／31 skipped（73.32秒）。PowerShell將uv正常stderr摘要包成NativeCommandError而外層exit1，原log保留；只將該項合併輸出重驗，uv lock --check --offline明確exit0，未重跑已通過pytest。收尾及模型／資料版本見同目錄report.md、closeout.json、preset20-results.json、full-gate.log及兩後端review。原始200題／CPU50／各輪失敗全部保留。日常App啟動設定／.env未動，本次驗收才明確指向新包；日常使用須另設定包路徑後重啟。FAQ資料更新及包已完成，T081忠實回答／引用、T082及T084仍未完成，保持37／40，不自動提交。

## 預設問題／FAQ副本比較（2026-11-10，37／40，原文件未改）

使用者要求評估在example.md加入預設問題。cache事前固定20組原文支持的FAQ與70問句，建立「只加問題＋出處」及「問題＋編輯短答＋出處」副本，各走既有chapter-source-v1切段器及完整dense10／BM25正分10／RRF60／BGE-base五候選，共140次離線推論。每版330段，308個完全相同model_text重用原包已驗證向量、22段新嵌入；BM25離線預建。這是全語料實驗矩陣，不是只挑正確候選的配對試驗，也尚未發布可部署Chroma v2包／完成新包reader驗收。

正式門檻3.486859679222107／分差4：原文件／只加問題／加入問答的20預設原題完整依據為9／7／20，20改寫為0／0／13，10跨段為0／0／2，20不可答各2題放行。「只加問題」原題20／20都有回傳，但13題缺完整答案，不能以命中當答對。候選0.81／分差2下三版原題14／6／20、改寫9／9／19、跨段1／1／5，不可答各6題放行。問答版覆蓋的18改寫題，正式門檻13／18、候選17／18；完整20分母保留，另2題非FAQ控制不剔除。

助手核對20條編輯答案與原gold必要資訊／定位，並閱讀問答版候選5個完整跨段結果；原文區間或完整FAQ答案區間須實際可見，問題／來源指標不算答案。全部題目及事實已曝光，預設原題直接寫入文件，20／20不是獨立盲測、實際語音答案正確率或重複一致性驗收。P02承辦學校改寫在候選仍無回傳；N11另一版出版年月仍可錯取目前FAQ日期。無HF／Gemini生成／音訊測試，不把檢索放行等同已觀察到捏造。

證據、兩版example.md草稿、140筆observations、results及原文核對在 `cache/004-single-document-rag/20261110-min-logit-calibration-v1/preset-faq-v1/`。建議固定題情境先採短Q＋A＋原文出處，一題一節、保留主體／年份／單位與原文，先不調正式數值。若明確採用，須核對內容後寫回原文件，離線重產新source digest／document version／index version的v2包，再驗reader與實際後端；本輪只評估，原example.md、原包、正式方案／程式未改，未下載、啟動App、連雲端或提交，T081／T082／T084仍未完成。

## 候選覆蓋與跨段比較（2026-11-10，37／40，僅離線）

依使用者同意，先固定並比較：50原問句最多十候選完整重排，以及10明示複合問題的20個原文字面子句，各用五候選後輪流合併，仍三段／2000字元、不跨query直接比較logit。兩案固定0.81／分差2及後置cosine0.58，未改正式程式或方案。人工拆句不從gold補查詢詞，不是已驗證的自動拆句器／充分性判斷器；全部題目已曝光，不稱盲測。

新舊RRF前五50／50一致，共同logit最大差約0.0000043；同次取前五的最終段落ID／文字／裁切50／50與舊結果一致。五→十候選的候選池完整gold可見原文覆蓋17／20→18／20改寫、6／10→8／10跨段，但最終覆蓋仍9／20、1／10，不可答仍6／20放行，沒有增加完整答案支持。不能把候選池上限當回傳成功；新增部分段落是錯年份紀錄／不是ISBN的隊號。

固定拆句後，10跨段題候選池全有gold，但最後只有5／10完整回傳；助手逐筆閱讀確認M03／M05／M06／M08／M10可完整支持，另外5題缺其中一半。這是助手來源檢查、不是使用者新人工驗收。拆句僅測這10個明示正例，未測複合負例／混合可答性、來源時間條件繼承或自動路由，不移用原20負例作拆句通過證據。十候選推論mean2.448／max3.359秒、雙子句推論合計max3.187秒僅作離線成本觀察，不能代替App十秒deadline／語音／取消驗收或與舊trace計時直接比速。

完整protocol／50筆whole-query／20筆subquery／summary／split-review／verification及報告位於 `cache/004-single-document-rag/20261110-min-logit-calibration-v1/coverage-cross-query-v1/`。建議保留五候選，後續先驗有界雙子查詢的混合負例／部分失敗／條件保留，再決定004／005規格變更。正式runtime、scheme及原包未改；未下載、啟動App、連雲端或提交，T081／T082／T084仍未完成。

## 0.81／分差2新問句驗證（2026-11-10，37／40，未升為正式方案）

使用者同意依建議進行，先驗證候選：在模型執行前固定20改寫、10跨段、20不可答，共50新問句，每題真實CPU推論一次；必要資訊與原證據沿用已核對gold，沒有改舊題／文件。20不可答是15個既有事實家族的20種問法；全部文件事實已曝光，新字串不等於獨立盲測。候選固定最低logit0.81／分差2，不依本輪結果再調值；max-distance0.58、五候選、三段／2000字元及選段順序不變。

基線3.486859679222107／4的完整gold區間覆蓋為改寫0／20、跨段0／10，不可答2／20放行；0.81／4及候選0.81／2均為9／20、1／10及6／20不可答放行。候選回傳34段／6529字元，相對0.81／4的36段／6740字元僅少約3.1%，沒有增加完整覆蓋；舊組15.1%差異不改寫。基線回放50／50與實際結果一致；追蹤elapsed不是新CPU延遲驗收，未執行語音或對話模型。

助手已讀全部26個回傳結果與必要資訊：11題支持（改寫10／20、跨段1／10）、9題回傳不足、6題不可答放行，另24題無回傳。P12在另一個真實段落明確給出2026年6校5隊，因此助手判支持，原gold區間代理9／20仍保留；不是使用者新人工驗收，也未修改T080。6個不可答放行涉及ISBN、調查日期、逐場分數／時刻、另一版出版日期及另一賽程首場時間，共5個事實家族。未呼叫雲端，不能把工具放行等同已觀察到答案捏造。

N07不可答段落logit約5.2993，比本輪全部單題正例第一名分數高；提高最低門檻擋它會讓本組20單題全無回傳，不能把分數當充分性。0.81／2能增加找回，但不建議直接宣告為可靠正式方案；這不是恢復已取消的零誤放行阻擋條件。完整證據及protocol／comparison／assistant-source-review見 `cache/004-single-document-rag/20261110-min-logit-calibration-v1/candidate-081-drop2-new-questions-v1/`。正式runtime及004／005方案、原包、原CPU50題與歷史失敗均未變；未啟動App、下載或自動提交。T081／T082／T084仍未完成，後續若接受限制選用或擴大query／候選改進需明確選定範圍。

## 數值調整建議比較（2026-11-10，37／40，未套用）

使用者要求尋找並提供數值建議；在cache事前列定6個最低logit×6個附加分差，共36組。文件／query、max-distance=0.58、五候選、三段／2000字元及後置距離順序不變，全部沿同一已曝光90問句分數探索。最低0.81／分差2與0.81／4的完整gold區間覆蓋均為原題28／35、現場改寫7／20、HF query9／20，不可答0／15放行；段落68→59、原文字元12774→10843（約少15.1%）。助手逐筆閱讀刪除的9段，涉及8個問句，剩餘固定必要資訊完整；不是新使用者review或延遲／語音品質測試。

分差1雖然整題覆蓋數未再下降，卻刪除兩個原本不完整三核心問句的部分正確資訊，因此不建議只看整題數字選1。若只調一項可用0.81／4；若減少多餘原文可優先另驗0.81／2；保守選項1.25／2為27／35、7／20、8／20及0／15不可答放行。五候選以外無分數，不能從本輪推論擴候選收益；距離未另掃描，不任意提高0.58。證據在 `cache/004-single-document-rag/20261110-min-logit-calibration-v1/parameter-advice-v1/`。此輪只建議，正式3.486859679222107／4、004／005版本及包未改，未啟動App、下載或提交；T081／T082／T084仍未完成。

## 最低logit邊界細查（2026-11-10，37／40，正式值不變）

使用者再要求繼續評估數值，固定21個0.77～0.90附近值，沿既有90問句分數回放。0.78～0.83的實際段落ID／文字／裁切完全相同，非僅摘要相同；相同選段區間為(0.7795348167419434, 0.8390169143676758]，下界等值放行Q49，上界等值保留Q34，高於上界少一題完整依據。中點0.8092758655548096，因此0.81可作簡單後續候選，對本批兩側邊界各約0.03餘裕；不宣稱這是泛化、可信度或可靠拒答保證。

0.81仍為原題28／35、現場改寫7／20、HF query9／20完整gold區間覆蓋，不可答0／15放行，未解決既有不足。文件／query／max-distance=0.58、正式logit及004／005版本不變。證據在 `cache/004-single-document-rag/20261110-min-logit-calibration-v1/boundary-refinement-v1/` 的protocol／results／report／inventory。僅cache與進度文件，未推論模型、下載或啟動App；全部題目已曝光，不算獨立驗證，未勾選T081／T082／T084。後續若需品質新證據應先固定新問法，而非繼續在相同分數區間微調。

## 其他最低logit比較（2026-11-10，37／40，僅探索）

使用者要求繼續評估其他數值。沿同一90問句真實模型分數、文件／query及後置max-distance=0.58，先列定18個值，再回放全部450個有限分數邊界（另含全拒答，共451列）。不重新推論或量測延遲、不變更正式方案；所有題目及先前驗證組均已曝光，不稱獨立驗證或原品質通過。

完整gold區間覆蓋（不是新人工支持率）：1.25的原題27／35、現場改寫7／20、HF實際query8／20，不可答0／15放行；0.8為28／35、7／20、9／20，不可答0／15；0.75開始放行Q49，0.5為29／35、8／20、12／20及2／15不可答放行。0.8相對1.5406759977340698新增四個完整依據問句（Q16 HF、Q19／Q20現場改寫、Q34原題），助手已逐筆閱讀原文；Q04英文全名及Q15三種問法仍不足，不能以回傳48／90冒稱48題有支持。

零觀察誤放行且覆蓋最多的探索區間為(0.7795348167419434, 0.8390169143676758]，0.8離Q49負例僅約0.0205，不代表新問法可靠。完整掃描最高覆蓋62／75可答問句版本時同時有11／15不可答放行，顯示只改最低logit仍有取捨；Q03距離限制及Q15三段名額等問題不能因此修復。不恢復已取消的品質選用阻擋條件。證據為 `cache/004-single-document-rag/20261110-min-logit-calibration-v1/other-values-v1/` 的protocol、grid、breakpoints、changed-passages、report及inventory。正式值3.486859679222107／004與005方案版本／程式／包均不變，未啟動App、下載或提交；T081／T082／T084仍待完成。

## 最低logit重校準與保守候選（2026-11-10，37／40，正式方案未變）

使用者取消未提交的Gemini對話連續性修正，改查取回不足；已撤回相關Gemini行為／測試變更。固定文字驗收沿用的conversation.say會開始新Gemini對話，因此下述實測不能當作同session連續性證據。另有獨立的原始DocumentOutput診斷日誌遮蔽修正保留，固定本機提示仍顯示；最後完整gate為1067 passed／31 skipped（88.96秒），Ruff／format、strict mypy及uv lock通過，見 `cache/004-single-document-rag/20261110-retrieval-focus-full-gate.log`。其後僅cache評估與進度文件，未新增依賴。

實例04的HF新版矩陣35／35已執行；Gemini原批15筆（Q15逾60秒，晚到事件保留）、續批10筆，共25／35已嘗試，Q41～Q50未執行。HF原文及回答仍有缺漏／轉述／書名問題，不把完成腳本當通過。原始 `cache/004-single-document-rag/20261110-live-acceptance-04/` 全部保留。04於臺北17:33停止，worker3.906秒回收且隔離金鑰清除；05連續性診斷在未輸入金鑰、未執行問句前依使用者改向停止，17:39記錄closed／cleared。沒有重啟App來重寫失敗。

離線同管線診斷60問句有43次先卡在最低logit；格式／FAQ配對試驗只存cache，未套用。依使用者C選擇，保留example.md及query，只評估最低logit，max-distance=0.58、分差4、三段／2000字元與後置距離順序均不變。

測前固定50題／90既有問句、校準28題／驗證22題，同題版本不跨組；全部已曝光。60筆沿用既有同模型分數、30筆新跑gold原題，原值回放90／90與實際結果一致。完整原文區間覆蓋只作保守篩選代理，不能當新的人工支持率／語音答案正確率或CPU延遲。固定校準規則候選-2.835425615310669雖增加覆蓋，但15不可答有8題放行，未採用；不恢復舊品質比例阻擋條件，不允許捏造。

使用者再選「先評估較保守1.5407，暫不改正式方案」：以完整值1.5406759977340698固定回放，不依結果重選。全部90問句完整gold覆蓋27→40，回傳29→44；gold原題覆蓋21／35→27／35，現場改寫2／20→5／20，HF實際query4／20→8／20。不可答0／15放行；助手逐筆確認新增15回傳中13有完整必要資訊，另Q04英文全名、Q15三核心仍不足。這不是使用者新人工review、獨立盲測或原50題重新通過，完整分母／不足保留。

證據：`cache/004-single-document-rag/20261110-min-logit-calibration-v1/` 的protocol／observations／screening／report及 `conservative-followup/report.md`、results.json、review.json。正式004／005方案仍用3.486859679222107，未改example.md、query、包、runtime或模型。若後續採用才同步版本化方案及重新產包；T081／T082／T084仍未完成。此次只離線評估、不啟動App、不下載、不讀.env、不自動提交。

## 本輪補驗收尾（2026-11-10，37／40，隔離實例已關閉）

使用者確認「有正常收音與回覆，語音皆正常」，涵蓋前述Gemini重量／三核心資訊不足語音及恢復麥克風後中文問候。實例03已於臺北時間16:36由30分鐘保護計時停止；worker於2.547秒回收、state=closed，16:36:51記錄隔離credential cleared=true。再次確認本實例metadata為cleared、active／pending revision皆空、retired revisions為空；未列舉或讀取日常憑證。最後停止HTTP請求遇connection reset，核對為App已關閉，不為此重新啟動。原CPU run digest再驗不變。

完整收尾證據為 `cache/004-single-document-rag/20261110-live-acceptance-03/final-confirmation.json`、events.jsonl、fixed-smoke-review.json及resume-status.json。退出仍有nanobind leak warning；SDK／daemon版本不一致及控制連線遺失紀錄保留，不宣稱已修復這些問題或零警告。這是少量對話／來源及音訊診斷完成，不是完整T081或T082通過，也不視為實體動作驗收。

本輪有修改程式後的完整gate仍為1063 passed／31 skipped（77.54秒），Ruff／format、strict mypy、uv lock通過；其後僅更新測試紀錄與說明，diff --check再驗。T080已完成，T081／T082／T084保持未完成，37／40不變；下一步須以明確新版本完成修正後完整雙後端矩陣，並補生命週期證據。既有HF35題／Gemini13題與中斷Q14、品質限制及完整原始分母不覆寫，不將本次少量補驗充當剩餘題。相機／記憶維持關閉，未讀.env、未新增依賴、未自動提交。

## 修正後Gemini少量補驗（2026-11-10，37／40，待現場最終回覆）

使用者在隔離實例03同頁重新設定金鑰後，Gemini connected，相機／記憶仍false。另行固定並單次執行warmup、school、weight、cores四個診斷案例，原始 `cache/004-single-document-rag/20261110-live-acceptance-03/fixed-smoke.jsonl`、完整RPC事件及人工原文核對 `fixed-smoke-review.json` 保留。與舊35題分開，不替換舊失敗或稱盲測。

- warmup：首次工具not_ready，回覆告知無法存取；另等40秒供工作行程載入，不計成功。
- school：工具no_evidence，拒答，仍是可答題未取回；不因啟動修正宣稱召回改善。
- weight：工具2.203秒返回L98-L111，回覆忠實說「重達56公斤」，書名「新北市FRC機器人教育八年逐夢誌」、版本source-e623baa45cf2及行號L98-L111均符合返回資料，未將敘述重量說成上限。
- cores：工具1.078秒返回兩個核心及總述，缺第三項，回覆告知無法完整列出、未補造第三項；仍缺完整行號，且把檢索不足泛稱為文件不足，列為限制。

這四個完整觀察窗都有對應主題回覆，沒有只收到開場問候便計成功；仍有問候前綴，不宣稱所有交錯已消失。script elapsed含重新連線、語音回覆及五秒安靜觀察窗，不能混入CPU50題的本機工具延遲。模型仍未完全遵循「完整問題」指令，例如核心工具query縮為「FRC 三個恆星核心」，因此提示詞僅是約束，不是強制保證；未變更重排／距離方案或增加充分性判斷器。

麥克風已由測試靜音恢復，正在請使用者確認重量與不足提示的實際音訊、以及後續中文問候無舊語音重播／重複回覆。現場回覆前不宣告補驗完成；之後停止App並刪除實例03隔離憑證。T081完整雙後端矩陣、T082及T084仍未完成，活動37／40。此前1063／31完整工程gate仍有效，本節僅增量記錄診斷證據。

## 雙後端實測發現與修正（2026-11-10，37／40，T081／T082未結案）

隔離實例02的HF已保留完整35題（20可答／10資訊不足／5其他文件）原始紀錄 `huggingface-live35.jsonl` 及逐題文字／證據核對 `huggingface-live35-review.json`。前20題當次檢索完整支持3／20；2／20題答案事實完整，其中一題使用先前對話中已曝光的STEM段落、當次工具仍無證據；完整事實與忠實引用同時滿足為0／20。不得把這些分母互換或將原始final_reply_observed當答對。資訊不足10／10及其他文件5／5皆未提供所要求的無依據資料，另記拒答；不計可答題成功。Q07開場問候、Q08／Q09時段額外麥克風輸入等污染保留，不補跑或選最好成績；其後暫時靜音測試App麥克風以固定文字輸入，非更動系統音量。書名被轉述成速記／速讀錄、Q19師資及Q20基地名稱改寫不準等限制保留。

Gemini保留13題完整原始觀察列，Q14執行中中止，另21題未開始；分母仍35，不把13題當完整35題驗收。詳見 `gemini-live35.jsonl`、`gemini-live35-interrupted.json` 及全程 `conversation-events.jsonl`。目前僅確認Q02／Q06／Q10／Q12有原文支持的回答例子，仍缺版本／定位等完整引用；不輸出整組通過率。實測發現固定文字注入會在開場問候間交錯；Gemini每次conversation.say會重啟為新對話，與HF連續對話不同，不能以單一final回覆等同已完成題目。另有Backend cleanup failed及nanobind退出警告，原log保留；沒有宣稱零警告或服務故障根因已修復。

已新增可重現的Gemini啟動順序回歸：VAD初始化被阻擋時原程式仍回報connected，red **1 failed，3.17秒**；修正將ready延後至VAD及開場訊息送出完成後，驗初始化與訊息送出均未完成時不連線，完成後才可連線。另補文件提示詞完整問題／忠實來源及限定語意的回歸（先red），強化共享指令但不新增充分性規則／模型、依賴或修改0.58。只證明指令契約與啟動時序，尚未宣稱新提示已改善真實模型品質或交錯已全面消失。相關回歸 **75 passed，6.47秒**，完整gate **1063 passed／31 skipped，77.54秒**，Ruff／format、strict mypy（64 source files）、uv lock --check（183 packages）通過。log在 `cache/004-single-document-rag/20261110-live-fixes-*.log`，red另保留gemini-readiness-red及evidence-prompt-red。

實例02已停止；worker回收2.75秒、state=closed，隔離憑證明確cleared=true。只是一筆實際停止觀察，不代替T082完整雙後端生命週期矩陣。原CPU50題及人工核對不變，沒有覆寫舊失敗。修正後獨立實例03於同一7863埠等待使用者重新輸入金鑰，準備另記少量啟動／來源複驗；此補驗不是盲測、不併入原35題成績、不自動補齊剩餘題。相機／記憶關閉，不讀.env；T081／T082／T084仍未勾選。 實例03設定頁可用、Gemini為waiting_for_config且未設定金鑰；daemon HTTP仍running／mockup且無backend error，但SDK出現控制連線遺失，這次補驗只限啟動／文件回覆，不擴稱動作驗收。續接狀態保存在該實例resume-status.json。

## T080音訊補充與實際服務授權（2026-11-10，37／40）

使用者明確授權example.md每次最多三段／2000字元結果送至HF／Gemini、使用既有免費額度、啟動App及現場配合；相機／記憶關閉，不讀.env，缺Gemini憑證由設定頁輸入。本輪隔離實例為 `cache/004-single-document-rag/20261110-live-acceptance-02/`。daemon回報mockup_sim_enabled=true，因此不能記為實體機器人動作驗收；SDK1.12.0／daemon1.13.0不一致警告保留，未更動安裝或daemon。

首次啟動因測試profile建立時序失敗；第二次沙箱拒絕雲端socket（WinError10013）且音訊開啟失敗，已停止該測試行程；第三次在授權的網路／音訊範圍下連上HF。上述失敗log保留，沒有以重試抹除。首次語音工具查詢document_not_ready啟動模型；暖機後FRC重量查詢2.328秒回ok，之後兩次區域賽時間查詢為no_evidence（1.703／2.109秒）。使用者確認「有中文回覆與逐字稿，可以正常執行」，補充證據為同目錄 `t080-audio-supplement.json` 及events／conversation-events。這是定性音訊可用性確認，不冒稱逐sample無斷訊、插話計時或T082通過。

原50題CPU run／計時／人工review均未更動，digest再核對一致；另存音訊補充，不把新語音問題混入50題分母。T080必要量測完成並勾選，活動任務37／40；T081／T082／T084仍未完成。模型將原文敘述「重達56公斤」誤說成上限、書名轉述不準，以及區域賽題無證據均保留為實際限制。

T081已測前固定 `live35-dataset.json`（SHA256 `80d68a729423524b08bad8ae21a3e29e5228bfd173b6f5f07ba6efe2147abb0f`）：依既有gold的來源順序取前20可答，20題均改寫；保留全部10無資料及5其他文件題，不依CPU成功與否挑選。每後端分母35，非盲測；實際回答與證據仍待逐題核對，不以腳本完成代替品質結論。HF矩陣執行中，Gemini尚待使用者同頁輸入金鑰；不自動換供應商。

## T080人工核對已匯入（2026-11-10，36／40）

使用者回覆「核對完成，繼續進行」，已找到並嚴格驗證同一run的完整50題人工匯出檔。review-only驗收 **1 passed，2.62秒**（`cache/004-single-document-rag/20261110-review-accepted.log`）；未呼叫Tool／模型、未重跑50題、未覆寫原始計時或舊報表。下方「稍後核對」為先前交接歷史，本節為最新狀態。

- 正式核對檔：`cache/004-single-document-rag/cpu/d67cde5418bf489295a5124aef8dce61/cpu-reviews-d67cde5418bf489295a5124aef8dce61.json`；新報表為同目錄 `cpu-summary-20261110T072846808104Z.json`，檔案digest與確認另記 `manual-review-accepted.json`。50題無pending／uncertain／annotation_invalid，人工前景核對時間共323.484秒，未計入工具延遲。
- 完整分母50：22題回傳段落，其中21題支持、Q15一題不支持；28題無證據，包含13題可答未找回與15題不可答的預期拒答。Q15僅回傳「創新基石」，缺其他兩個核心名稱，不能以gold補足。這是工具返回證據不足，不代表已觀察到雲端模型捏造。
- 五秒內支持21／50；可答題支持21／35；有回傳段落的題目支持21／22。這三個分母用途不同，不能互換或用後者宣稱全題通過。15題預期拒答另列，不算支持成功。未另計段落層級支持率，也不將題目比率冒稱段落支持率。
- 全50題延遲仍為p50=1.672、p95=2.859、max=2.906秒；21題支持子集p50=1.672、p95=max=1.906秒。冷載入27.047秒、最大遞迴worker RSS約4.33GiB及舊失敗均保留。沒有重新調整0.58或品質門檻，這些結果不是新盲測。
- T080仍缺音訊可用性證據（原始run為not_evaluated），不以人工核對完成代替。T081文件段落外送／服務額度與T082現場範圍仍待確認；T080／T081／T082／T084保持未完成，36／40不變。後續先補查詢期間音訊／插話可用性，再按既有固定20可答（至少10改寫）＋10不可答＋5其他文件的雙後端流程，最後做各10次生命週期驗收；不得以重測覆寫本次50題結果。

## T069與T080原始量測（2026-11-10，36／40，人工核對延後）

使用者最新指示「進行驗收」，取代前輪延後決定的T069範圍；後續又明確指定「使用專案example.md，先離線產v2包並整理50題供核對」。本輪T069／產包及題組準備均離線，不啟動App／daemon／機器人、不讀.env／私人快取、不下載、不向雲端傳送文件。T081／T082仍需當次資料外送／服務額度及現場範圍，不能用本機驗收代替。

- T069：`RUN_DOCUMENT_SNAPSHOT_ACCEPTANCE=1`，使用005已驗證的首份中文合成包及兩固定角色模型，執行 `tests/test_document_worker.py::test_external_prebuilt_snapshot_integrity`。**1 passed，66.35秒，無warning**；原始 `cache/004-single-document-rag/20261110-t069-actual.log`。本輪改為兩個獨立新程序、各設torch intra2／inter1一次，避免同程序重建物件冒充重啟、也避免同時持有兩套模型。兩次各驗真實v2載入／query／close、公開Chroma重開後全rows／metadata／vectors／count與持久HNSW不變；測試副本改為v1後明確拒絕且副本hash不變。原包及retrieval資產全hash不變，沒有create／add／migration／重建。
- 本輪模型沿005 `20261110-real-model-summary.json` 的固定SHA／v2 receipt，包為 `cache/005-prepare-rag-assets/20261110-real-packages/test_real_local_model_builds_f0/package-0`；兩個新程序work及v1負向副本在 `cache/004-single-document-rag/20261110-t069-actual/`，不改005原素材。socket audit在 `20261110-t069-audit/sitecustomize.py`，拒絕connect／DNS／sendto；network-attempts.log未建立，零外連嘗試。
- 修改驗收入口後的完整gate：`cache/004-single-document-rag/20261110-t069-gate.log` **1061 passed／31 skipped，75.69秒**；Ruff／format（141檔）、strict mypy（64 source files）、uv lock --check（183 packages）通過。一般gate的真實驗收略過未計入通過，T069以上獨立實測另記。
- 指定example.md為159,463 bytes／63,383 code points，source SHA256 `e623baa45cf2d31a72d964b6f5beaaddb082dfa81671e4b8cc466e7994bdf57e`。保留原檔，不修改內容；用005既有build_document_package CLI、固定scheme與已驗證雙模型離線產包至 `cache/004-single-document-rag/20261110-example-acceptance-v1/package`，document id=example-frc-manual、version=source-e623baa45cf2、index_version=v2-20261110-cpu50，無額外人工別名清單。此處是離線準備，不是App內建索引。產包已成功發布309段，原始20261110-example-build.log、完整摘要20261110-example-package-summary.json；validated_targets僅Windows x86_64。manifest SHA256為ee2af56996db530e72b69cc470cc2a89710d1fb8d131ec5a846d0497958c0492、包inventory摘要c18d717ee84c03cca8a29a01c68fc7eaa5e421db987c6f6abfb221840e7cc491，來源hash仍相同、零網路嘗試。新策略產309段，不將歷史288段當常數。
- 50題測前草稿在 `cache/004-single-document-rag/20261110-example-cpu50-gold-v1/dataset.json`；dataset id=example-frc-cpu50、version=preflight-v1，bytes SHA256 `64a5b1723edf7ebf276ecf5eccb0f760d19e2d444aade33a0479cf4b0c95998c`。35可答／10缺資訊／5其他文件；各可答題已固定required_information及原文連續切片／行號，資料契約及來源逐字定位檢查通過。preflight-review.md供使用者逐題核對，preflight-review.json保存分類／不可答理由／pending狀態；兩者不是擴充正式dataset欄位。原文與題型已曝光，不能稱盲測；未使用本次檢索結果選題或調整gold。
- 使用者已逐題確認preflight-v1並要求繼續CPU；確認記錄保存在v1的user-confirmation.json。正式檢索開始前，人工複核發現18題須補原文年份／章節／表格指標，因此保留v1另存preflight-v2。v2的50題問題／可答性／required_information均與v1完全一致，只有18個evidence連續切片擴充；新hash為914f12008fdc79b7d2d3406e964576b238c89d72aef100a504af433a0f96ab6c，位於20261110-example-cpu50-gold-v2/dataset.json。v2 preflight-review.md列出前後locator及完整原文，資料／定位檢查通過。使用者後續明確確認「採用v2補充證據並繼續CPU驗收」，確認記錄保存在v2/user-confirmation.json；題組bytes與SHA凍結後才執行以下量測。若需改題，保留本版並另增dataset版本；T080／T081／T082／T084仍未完成。舊35／40與延後決定作歷史記錄保留，未改歷史task核取狀態／requirements checklist，未自動提交。

### T080量測、修正與待核對狀態

本輪只做離線資料／CPU驗收，不讀日常金鑰、不使用HF／Gemini對話或機器人。50題gold為已獲使用者核對的preflight-v2（SHA256 `914f12008fdc79b7d2d3406e964576b238c89d72aef100a504af433a0f96ab6c`）；模型／309段包／0.58與全部檢索參數固定，沒有依量測結果改題或調參。

| 階段 | 結果與原始紀錄 |
|---|---|
| 首次setup失敗 | 20261110-t080-actual.log：pytest事件迴圈建置即被過嚴socket audit阻擋，1 error（4.26秒），沒有CPU題目執行。Windows asyncio的stdlib socketpair使用127.0.0.1建立內部喚醒管線；原失敗及析構warning保留。 |
| 修正audit後首個完整run | `cpu/e5dae237e3f04492bafc77447188c57d/cpu-run.json`，log為20261110-t080-loopfix.log。完整50題、22 ok／28 document_no_evidence，冷載入51.843秒；全50 p50=1.532、p95=1.843、max=1.922秒，worker closed。RSS只取直接child，5,554,176 bytes實為Windows launcher，不能當作真實worker記憶體；rss-measurement-note.json保留缺陷說明，50題原始結果與計時不改。 |
| RSS回歸先紅後綠 | 20261110-rss-red.log：1 failed，預期4GiB interpreter卻只量到5MiB launcher；改為parent.children(recursive=True)，取最大實際descendant RSS並記取樣方法。20261110-rss-green.log：71 passed／1 skipped（7.61秒），包含不重跑查詢的人工review更新回歸。這只修驗收harness，沒有改產品檢索策略。 |
| 必要量測修正後的新run | `cpu/d67cde5418bf489295a5124aef8dce61/cpu-run.json`，20261110-t080-rssfixed.log：1 passed（117.33秒）。另建run、不覆寫首run；完整50題、22 ok／28 document_no_evidence，冷載入27.047秒；全50 p50=1.672、p95=2.859、max=2.906秒，沒有busy／not_ready／timeout／其他操作錯誤。parent峰值138,653,696 bytes；最大遞迴worker峰值4,652,834,816 bytes（約4.33GiB），不是相加的獨占實體RAM。每20ms RSS取樣；worker closed，音訊可用性仍not_evaluated。 |
| 兩run一致性 | corrected run內comparison-to-first-run.json：50／50有界工具結果完全相同（含原文、chunk ID、locator、錯誤），只有量測時間與RSS方式不同；沒有以速度／命中率擇優刪除run。每個run各保留完整50分母，不合併為新的成功分母。 |
| 來源及安全不變性 | 20261110-t080-invariance-summary.json：example.md／v2題組SHA不變、包全inventory與雙角色payload／receipt不變。修正版audit阻擋全部connect／DNS／sendto，僅准stdlib socket._fallback_socketpair的loopback；兩run各一次內部self-pipe，其他網路嘗試0。原T069 audit log後來的1次阻擋對應首次T080 setup的內部socketpair，不是T069或文件外送。 |
| 最終完整gate | 20261110-t080-final-gate.log：**1062 passed／31 skipped，85.21秒**。Ruff check／format（141檔）、strict mypy（64 source files）、uv lock --check（183 packages）通過；一般gate仍不執行真實CPU／模型。 |

所有以上檔案均位於cache/004-single-document-rag/，cpu/下的run目錄除外以相對路徑列示。標準20ms取樣不能承諾捕捉所有瞬時峰值，報告如實標註方法。首run的模型、查詢及輸出未因RSS缺陷變更；其RSS缺陷不能改寫成通過，也未用快取代替第二次執行。

### 人工核對交接（使用者選擇稍後核對）

修正run的 `manual-review.html` 在 `cache/004-single-document-rag/cpu/d67cde5418bf489295a5124aef8dce61/`。這是單檔本機驗收資料檢視，不是App頁面或服務：不連網、不執行模型、不建立查詢快取，文件原文以textContent呈現。每題顯示固定必要資訊、測前gold與實際返回原文；支持判定只使用後者，缺項不可用gold補答。按「確認本題」後記錄UTC與前景停留秒數，與唯讀工具延遲分開；全部50題完成才可匯出完整核對JSON。可匯出草稿／匯入接續，沒有localStorage持久化，重整會清除未匯出操作。匯出後需將檔案保存至本run cache並提供完整路徑，再以既有review-only分支嚴格驗證及更新報表，不重跑50題。

助理離線逐題檢查後，草稿建議21題supported、Q15一題unsupported（只返回第一個核心，缺另外兩項名稱）、28題not_applicable。這些僅供人工核對參考；`cpu-review-proposals.json`使用suggested_reviews／pending狀態，不能當作正式manual review。正式cpu-reviews.pending.json與cpu-summary仍為50題pending／0個已核對支持成功，不將建議當作人類已完成標註。35可答題中13題未返回段落；15不可答題均document_no_evidence，expected_refusal另列，不算支持成功。段落是否支持的正式數字及人工總耗時待使用者匯出核對JSON後產生。

本機UI自動檢查在20261110-review-qa.json：50題載入／建議套用／50題匯出門檻／360px無溢出／重整不持久化，零頁面錯誤與外連。僅在獨立headless Edge cache profile做短暫QA，未匯出任何人工核對結果，raw run及pending JSON保持不變；已目視PNG確認文字與控制可見。PNG與QA不是使用者核對證據。

使用者最後明確回覆「稍後核對」。因此T080尚未完成：原始CPU量測已完成，測後人工review及音訊可用性仍缺；T081資料外送／服務額度與T082現場範圍尚未確認，T084不結案。活動任務36／40，剩T080／T081／T082／T084；不自動進雲端、啟動App或機器人、不下載、不提交。後續只更新review報表即可使用既有raw observations，若另有必要重跑，須另記run與理由，不覆寫本次兩run。

## 004增量離線實作（2026-11-10，35／40，部分交付）

本輪明確使用 `SPECIFY_FEATURE_DIRECTORY=specs/004-single-document-rag`，Git仍為feat/005-prepare-rag-assets；未重建feature或變更歷史任務。已核對AGENTS／CONTRIBUTING／憲章，Python3.12.12／Windows及現有lock（Chroma1.5.9／ST6.2.0／torch2.15.0+cpu／transformers5.21.0），不新增依賴／CI或SDK內部變更。005已完成兩固定角色v2 receipt、16次合成產包及交接，但其成功不自動勾004實機／CPU任務。一般gate及本輪不下載、不讀.env／私人模型快取、不啟動App／daemon／雲端或機器人。使用者本輪選擇「先完成離線實作，正式驗收資料稍後準備」；T069／T080／T081／T082及總結案T084保持未完成。Linux／macOS仍依既有指示略過，不記pass。

### 已核對實作及新增缺口

- T045～T050：005共享的v2 manifest／雙角色safe loader／三路徑、schema及完整性檢查已逐項核對，無需複製一套reader。先前005最終gate1003／31只作開發基線，004新的回歸另列，不以舊勾選代表新版完成。
- T051／T055／T064／T066／T067：私密協定仍1；parent使用共用有界JSON解析，拒絕BOM／重複key／非有限值及非法reason組合。僅初始化failure＋unavailable＋legacy_package快取typed唯讀原因，鎖保護，初始化／關閉清除；初始化thread不發UI，首問not_ready不被復活，下個明確query才回unavailable。worker私密failure移除exception欄位，安全例外類別改記logger，不送模型或設定回應。
- T052～T062：固定v2雙模型／exact dense10／預建BM25正分10／RRF60／五完整候選／raw logit／可見來源／最多三段2000字元及最後0.58，成功結果只含唯一來源與原文。Fake排序／邊界及模型安全／Tool／prompt／source injection／診斷限額回歸沿用共享實作，無運行期充分性規則、額外模型或雲端審核。
- T063：已曝光200題固定候選回放 **200／200符合歷史保存的段落ID／可見原文**。`cache/004-single-document-rag/20261110-cached-selection-replay.py` 呼叫產品DocumentIndex.query，供應原前五候選及已記錄logit、用合成向量保留已記錄父距離；`20261110-cached-selection-replay.json`記輸入hash及逐題ID比對，`cache/004-cached-selection-replay.log`保留執行結果。這不是模型重推論、dense／BM25候選生成重驗、重新產288段包或新盲測。原候選來源順序／分數沿保存紀錄，通過的是選段／字元預算／後置距離與可見原文一致性；v2真實新產包切段／ID不承諾等同舊288段。84/100正例、2/100負例誤放行、127/131段落支持及舊錯例全部保留，不改寫成品質通過。
- T065／T068／T070：單worker／單工作／零排隊、120秒載入、十秒逾時及忙碌槽保留、9秒5／2／2回收與未確認保留、來源版本替換／故障不補建等離線矩陣已回歸；sentinel不進診斷，原文僅正常工具／引用結果可見。真實HNSW的005證據不冒充本輪T069執行。
- T071～T075：新增ToolInvocation.legacy_notice_sent；共享handler只在結果驗證成功、真實unavailable及本機legacy原因、原call仍有效時入queue前設旗標。duplicate一次、新有效call可再提示；malformed合成unavailable／通用故障／invalid_query無提示，queue消費時再次驗generation／epoch／取消／tool權限。固定文字不帶路徑、不新增TTS／response.create或第二次transcript append。HF一般錯誤仍排一個既有DocumentResponse；Gemini一般unavailable仍WHEN_IDLE，timeout才SILENT。兩後端共用一份本機顯示邏輯。
- T077：更新Mermaid來源呈現10秒／9秒邊界及回合擁有的本機提示，既有本機renderer重生SVG／PNG，已目視確認標籤無遮擋／裁切；未下載renderer、未手改SVG。圖仍由root README嵌入。

### 原始測試與失敗

| 範圍 | 結果及記錄 |
|---|---|
| U2先紅後綠 | cache/004-u2-red.log：16 failed／3 passed（缺新原因／提示）；004-u2-green.log：19 passed。缺logger的初期Ruff／mypy結果亦已修復，未當作通過。 |
| Foundation與共用reader／模型／工具／prompt／兩後端 | cache/004-foundation.log：300 passed／2 skipped（36.54秒）。 |
| CPU資料契約先紅後綠 | cache/004-cpu-red.log保留缺module初期結果；004-cpu-green.log：33 passed，合成dataset／review／報表，非實際CPU50題。 |
| U2 wire測試接線修正 | cache/004-integration.log：4 failed／286 passed／2 skipped；新增測試最初誤以為HF直接response.create、Gemini未建立NON_BLOCKING宣告，修正測試接線後004-integration-fixed.log：290 passed／2 skipped（26.72秒）；產品一般錯誤流程未為測試改寫。 |

### 最終離線驗證與任務界線

- 最終 `cache/004-full-gate.log`：**1061 passed／31 skipped，85.48秒**。Ruff check／format（141檔）、strict mypy（64 source files）、uv lock --check（183 packages）及git diff --check通過；未新增依賴或變更lock，完整gate不下載、不啟動App／機器人。
- CPU契約與review-only回歸：`cache/004-review-final.log` **70 passed／1 skipped（10.24秒）**，包含在最終完整gate；33項純合成資料測試與本機私密原因／通知等runtime測試，沒有實跑50題CPU。review-only測試兩次產生pending與人工final報表，實際Tool呼叫被禁止，原cpu-run bytes不變；其cache資料只含固定合成問題。
- T069 opt-in入口最後補齊close／重開後的持久HNSW及全rows核對、真實v1拒絕副本；僅compile檢查與離線worker回歸，未執行真實包。`cache/004-snapshot-entry.log`：50 passed／1 skipped（10.16秒）；修改後Ruff／format／strict mypy／lock及diff --check再次通過，T069仍保持未完成。
- 完成T045～T068、T070～T079及T083，共35／40。T069獨立真實快照入口已更新但本輪未執行；005素材證據保留。T080缺指定正式v2包與測前核對的50題資料；T081需另確認本次文件段落外送與服務額度，T082需現場／雲端範圍，T084需上述完整證據後才能結案。
- 舊T001～T044四反引號存檔內容／核取狀態未改，requirements checklist唯讀16／16未改。before／after implement僅optional Git提交hook，依既有不自動提交要求略過，無mandatory hook。
- 未重新執行005大模型或操作日常設定。005已完成的CPU安全載入／包不變性不冒充004固定50題、語音品質或十秒查詢實測；Linux／macOS保持未測。原200題曝光、84/100／2/100／127/131及歷史錯例不改寫，新舊失敗log都保留。

### T084預備審查表（2026-11-10，未結案）

本表增量整理既有證據，沒有新增測試結果或免除待辦。一般gate的1061／31及200題固定候選回放僅支持各自範圍；T084保持未完成。使用者已選擇正式資料稍後準備，本輪未進行T069～T082的實際驗收。

| 要求 | 已有離線證據 | 尚需正式證據 |
|---|---|---|
| FR-001 | Tool／權限及共享runtime、兩後端替身回歸 | T081／T082：兩後端實際文件對話 |
| FR-002 | 唯一文件／版本、路徑與混合來源拒絕測試 | T069：指定真實包；T081：其他文件要求拒絕 |
| FR-003 | chunks／原文定位／預建BM25／TXT／空及合法別名語意檢查；005素材紀錄 | T069：004獨立真實快照驗證 |
| FR-004 | v1安全辨識、私密原因及本機提示一次／queue退役／非legacy負例 | T069：真實包拒絕不變性；T082：現場行為 |
| FR-005 | 禁止索引寫入／migration／fallback的負向測試 | T069：真實包及持久索引不變性 |
| FR-006 | 原始500／501字先驗、三路徑與CPU安全載入邊界 | T080：固定主機查詢量測；T081／T082：雙後端實測 |
| FR-007 | 原文／真實定位／三段2000字元及可見前綴回歸 | T069／T081：實際返回內容與引用核對 |
| FR-008 | 有條件文件指令、繁體中文整理與引文保留的prompt測試 | T081：實際文字／語音引用與回答 |
| FR-009 | 無依據固定碼及不捏造指令；未新增充分性判斷器 | T081：不足／矛盾／無依據題的實際回答 |
| FR-010 | 六固定碼、初始化／busy／故障及後續聊天替身回歸 | T082：實際服務故障後一般對話 |
| FR-011 | 十秒deadline、busy槽保留、文字一次／timeout消音與晚到退役 | T080：50題延遲與音訊可用性；T082：現場timeout／插話 |
| FR-012 | generation／epoch／取消／換後端／新對話／duplicate競態測試 | T082：兩後端現場零遲到回覆／動作 |
| FR-013 | 注入文字不授權其他工具、RAG不變更設定的回歸 | T081／T082：實際來源注入與權限邊界 |
| FR-014 | 本機模型資料流及INFO／DEBUG sentinel遮蔽、公開結果不帶私密原因 | T081：確認當次有界段落外送範圍；T082：實際服務流程 |
| FR-015 | 三路徑啟動凍結、換完整包／重啟的新版本替身驗證 | T069／T082：實際快照及停止換包交接 |
| FR-016 | 單monotonic九秒5／2／2、提前退出／未確認保留副本回歸 | T082：實際工作行程回收及現場停止 |
| FR-017 | 固定雙角色／revision／safe CPU／缺一路徑拒絕；005真模型receipt | T069／T080：004實際載入與CPU查詢 |
| FR-018 | exact dense／預建BM25／RRF／五完整候選與來源脈絡邊界測試 | T069：004真實pipeline；T081：實際來源使用 |
| FR-019 | Identity logit／分差／同分ID／可見原文／預算測試及固定候選回放 | T080／T081：實際查詢／回傳支持核對 |
| FR-020 | 0.58後置篩選／等於門檻／top1拒絕／extras不補段測試 | T080：在本次run記錄原始結果；不是重新校準 |
| FR-021 | 固定scheme／digest／曝光200題及原失敗／分母保存 | T080～T082：新增實測獨立記錄，不覆寫歷史 |
| SC-001 | prompt／選段回歸及歷史觀察保留 | T081：各後端20題可答（至少10改寫）的完整量測 |
| SC-002 | 其他來源參數拒絕、無依據及注入邊界回歸 | T081：各後端10題無依據＋5題其他文件 |
| SC-003 | 50題dataset／review／nearest-rank報表及review-only不重跑測試 | T080：指定文件／50題測前核對、實跑、測後人工核對與音訊證據 |
| SC-004 | 兩後端替身的插話／取消／退役／後續聊天回歸 | T082：各10次實際查詢及指定插話／切換情境 |
| SC-005 | 八類故障／配置缺漏／零自動下載或索引寫入回歸 | T069／T082：實際包與服務的故障恢復 |
| SC-006 | 有界結果與診斷sentinel回歸；私密reason不外送 | T081／T082：正式情境的結果／來源核對 |
| SC-007 | 排序／距離／v1提示／TXT／別名完整離線邊界；005相關素材證據 | T069：004真實快照；T082：提示的現場行為 |
| SC-008 | 舊失敗與曝光200題84/100、2/100、127/131保存；回放未宣稱盲測 | T080～T082：正式run獨立標識／原始分母；T084最終審閱 |

接續順序：先明確選定T069的既有v2包與兩角色模型並啟用獨立驗收；再準備T080的50題資料與測前人工核對。T081另確認當次文件段落外送及服務額度，T082另確認現場範圍。完成這些證據後才更新T084與整體結案；既有「正式驗收延後」決定不因再次執行implement而失效。

### CPU驗收runner與後續入口（測試專用）

格式依[cpu-evaluation契約](contracts/cpu-evaluation.md)，實作位於tests/document_cpu_evaluation.py及tests/test_document_retrieval.py，不打包為App服務。dataset使用整數schema_version=1、唯一50個id、query原始<=200字、固定可答性／required_information／evidence；evidence locator固定為 `Lfirst-Llast; chars[start,end)`。測前從已供應包的完整原文切片核對證據、行號、文件id／version／source_sha256；不重新建索引、不從結果補gold。需人工先核對問題可答性及必要資訊，程式的切片比對不能代替人。

正式資料準備後，在本次明確opt-in範圍中設定 `RUN_DOCUMENT_CPU_ACCEPTANCE=1`、`RAG_ACCEPTANCE_GOLD_REVIEWED=1`，再明確給 `RAG_ACCEPTANCE_PACKAGE`、`RAG_ACCEPTANCE_MODEL`、`RAG_ACCEPTANCE_RERANKER`、`RAG_ACCEPTANCE_QUESTIONS`；執行 `pytest tests/test_document_retrieval.py::test_external_cpu_fifty_question_benchmark -v`。沒有雙旗標／完整素材就skip，舊字串陣列拒絕。本輪未設旗標或實跑。

每run新UUID資料夾固定於cache/004-single-document-rag/cpu/；cpu-input.json在載入前保存dataset原始UTF-8及digest、包inventory digest、兩receipt／revision／runtime、host／RAM／Python／lock及threads2／1；初始化probe不是50題之一，冷載入另計。每題只問一次，逐題保存單調受理／完成／原始elapsed／outcome／bounded result與題間等待，RSS每20ms取樣，不以權重大小作RAM。即使busy／timeout也保留完整50分母；中斷留下partial及run，不重送。音訊可用性標為not_evaluated，需後續現場證據。

先產生cpu-reviews.pending.json，pending／uncertain不計成功。人工核對格式：頂層 `{schema_version:1, run_id, reviews:[...]}`；每題含run_id／question_id／reviewer（非個資識別標籤）／reviewed_at_utc（UTC）／review_seconds／decision／annotation_status／checks／reason。每個required item依原順序對應一個 `checks`：`{status: satisfied|missing|uncertain, evidence:[{chunk_id, locator}]}`；引用必須出自本次實際可見passage，locator使用返回的定位。supported須全部必要項齊全，missing為unsupported、uncertain不成功；標註錯誤用annotation_status=invalid、decision=uncertain及annotation_invalid理由，原run／50分母保留，另版修gold才可新run。工具失敗not_applicable；不可答正確no_evidence另記expected_refusal，不算支持成功。

完成人工核對後，設定 `RAG_ACCEPTANCE_RUN` 指向既有cache內cpu-run.json、`RAG_ACCEPTANCE_REVIEWS`指向人工核對檔，再跑同一測試。此分支只讀既有觀察及凍結dataset／digest，產生帶UTC時間戳的新cpu-summary，不重新呼叫Tool／模型或覆寫原cpu-run。五秒內支持與超五秒支持分開、完整50題nearest-rank p50第25／p95第48／max與支持子集、各錯誤／pending／uncertain／annotation_invalid／人工總秒數各列，不產生舊48／50或其他品質passed旗標。最終T080仍需測前／測後人工核對及音訊／deadline證據，測試程序完成不是整體產品驗收。

T069的獨立快照入口也已要求 `RUN_DOCUMENT_SNAPSHOT_ACCEPTANCE=1`＋上述package／兩模型，更新為v2、原包與全rows／vectors／assets／count／HNSW核對、close後新副本重開；本輪依你選擇不執行。005的真模型／包交接紀錄仍可查，但不倒填004現場待辦。

## Prerequisites

**2026-11-05 開發基線（T001）**：分支 `feat/004-single-document-rag`，Python 3.12.12／Windows x86_64。Ruff check 通過、122 檔 format check 通過、strict mypy 56 source files 通過；`uv lock --check` 基線解析 139 packages，完整 pytest 793 passed（96.85 秒）。首輪 pytest 因回合中斷未完成、不計通過；接續重跑完整通過。記錄位於忽略追蹤的 `cache/004-single-document-rag/baseline-*.log`／`baseline-resume-pytest.log`，未讀日常私密設定，未啟動 App／daemon 或服務。

**歷史狀態（2026-11-05，非目前素材盤點）**：當時尚未供應本功能可驗證的單文件預建包／BGE-M3 snapshot；未掃描私人文件／既有模型快取，未下載模型。真實資產與雲端／實機驗收保持未完成，不阻擋本機離線實作；Linux／macOS 依同日後續明確指示略過，詳見平台範圍更新。既有 `.gitignore` 涵蓋 Python／venv／build／cache／秘密檔，本輪無需新增其他技術的 ignore 檔。

**T003～T018 本機進度（2026-11-05）**：已接入選用 rag extra、啟動固定路徑、typed ToolDependencies、單 worker runtime／有界協定與既有人格 Tool；提供隨 wheel 交付的 manifest schema、本機 CPU encoder／既有集合讀取、來源／原文限額與條件式指令。先完成 red tests 再實作；相關 149 項回歸通過（`us1-regression.log`），mypy 59 source files 通過，Ruff／format 通過。另有一次以 40ms 當正常查詢上限的測試因主機排程失敗，已改成只在慢工作測試暫縮 deadline、正常重問恢復十秒並等待真實完成；原失敗保留在 `us1-offline.log`，不列為服務／模型問題。

工具／索引測試均使用合成檔案與假的 encoder／Chroma，沒有真實 HNSW 不變性、BGE-M3 效能或服務驗收證據。產品 lock 的精確組合另在隔離環境 import 通過：SDK 1.12.0、HF hub 1.33.0、Chroma 1.5.9、ST 6.2.0、torch 2.15.0+cpu、transformers 5.21.0（`product-probe-import.log`）；不含 extra 的依賴匯出沒有 Chroma／ST／torch。已加入範例文件包／模型目錄忽略項，請勿把實際文件、模型或私密來源加入 Git。後續 US2／US3 進度見下列續作紀錄；這一段只記錄當時的本機 MVP，不能當作即時語音交付證據。

1. Python 3.12、既有 README 安裝環境；個人客製化分支。若要上游貢獻，先走 AGENTS／CONTRIBUTING 的 issue 與人工審閱流程。
2. 已由外部建置者提供一份無敏感資料的完整包，只有一個文件／版本，含原文、真實locator、章節／明示空或合法人工別名、完整預建BM25、固定完整選案設定／來源與相容 metadata，符合 [完整 JSON Schema](contracts/index-manifest.schema.json) 及包合約的額外語意條件；不用自己的日常文件先試。此 schema 不是產包工具，結構範例／dummy hash 不算可載入的真實資產。
3. 完整本機 BGE-M3 與獨立BGE-base安全權重／tokenizer，與包指定固定revision／pipeline／runtime一致；版本見包合約。事先供應，對話時不下載。
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
| 包格式 | v2合法、v1拒絕並要求離線重產；缺BM25／錯策略／缺重排模型不得補建或降級；required／null／未知巢狀欄位、清單形狀、平台 enum、revision／hash 格式／重複 key；合法 schema 後仍須真實語意／檔案／引擎驗證，全部離線 |
| 輸入／限額 | 原始字串先限 500 code points，再 trim 檢查；原始 501 即使 trim 後合法仍拒絕、原始 500 有效可接受，HF／Gemini 一致；空白、純標點、非字串、額外欄拒絕，結果最多三段／2,000 字 |
| 八類失敗 | 缺包、壞包、不相容、混合文件、缺原文／定位、模型未就緒、busy、timeout 均有可區分固定結果 |
| 檢索順序 | exact dense10／BM25正分10／RRF60／完整五候選；Identity logit邊界與drop4；三段預算後套0.58，top1超限全拒、附加超限刪除無補段；同分穩定ID與不足五段不湊數 |
| 評分脈絡 | 保留原文與標題／人工別名來源，query不截短、pair512來源prefix可見才引用；空別名合法、錯定位拒絕 |
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
$env:REACHY_MINI_DOCUMENT_RERANKER_PATH = (Resolve-Path 'cache/rag-acceptance/reranker').Path
reachy-mini-conversation-app --help
```

Linux／macOS 以同名啟動環境變數設定本機路徑；不把這些變數當工具參數。上列第三變數是本輪計畫新增，須待實作與根README同步後使用。只改隔離測試行程，勿覆寫日常 `.env`、人格／記憶資料。使用既有工具設定啟用 `search_document` 後按 README 的既有方式啟動；啟動機器人可能有動作，須有現場可配合的驗收範圍。

第一次明確查詢可回尚未就緒，確認模型載入後再明確查詢；不自動重播第一問。測試前後核對原包 hash、工作副本文件／向量／count 及 HNSW 不變性；以唯讀原包、缺集合、需 migration、未 flush snapshot 再測，不能自動修復。

準備最多 1,000 段、每段 <=512 tokenizer tokens 的固定測試文件。就緒後依固定順序執行 50 個 <=200 字元問題，量 monotonic 端到端工具時間、是否取得具原文支持的段落、無支持放行／無依據／busy／not_ready／timeout／error 數、App 及 worker RAM 峰值與語音可用性。五秒成功數／比例僅作觀察，不再以48／50或95%阻擋個人方案選用／結案；全部題目仍須十秒內完成或明確逾時，晚到結果永久退役。未能支持問題的段落、無依據、busy、not_ready、timeout／error不算成功，不刪題或縮分母。另報完整50題的p50／p95／max、成功子集分布及各失敗數，標明percentile算法；冷啟動與RSS另列，不用快速失敗美化成功延遲。CPU飽和仍要驗證語音／插話，未完成如實記錄，不私下換模型／量化。

本地模型整合測試需以明確 opt-in 選項與已提供路徑執行；不存在模型時報未執行原因，不能自動下載。實作時將實際可執行命令補進根 README 及本指南，不在規劃中假造已存在的 benchmark CLI。

## 固定50題證據與人工核對（U1）

新版external_cpu輸入依 [cpu-evaluation](contracts/cpu-evaluation.md)，不能只給50個問題字串。測前準備版本化JSON：文件ID／版本／digest，恰50個唯一題號，每題query／可答性／必要資訊／證據原文及start／end／locator。人工先核對來源，凍結dataset bytes digest與版本，不依執行結果改標註；這不是自動校準或新的盲測。

實作後先以原有pytest入口指定隔離v2包、嵌入與重排模型及新版dataset。測試環境變數在T079實作時同步README／guide；下方歷史純問題陣列命令不能直接作新版驗收。先驗schema、恰50題／來源身分／gold定位，記固定主機與雙模型／包版本。缺合法資料記未執行，不補答案、不下載或讀其他文件。

runner一次記每題原始工具結果及monotonic elapsed，先保留pending review，不宣告具支持成功；本輪不實際執行runner。執行後由人工逐必要資訊對照實際回傳且模型看過的原文，填supported／unsupported／uncertain／not_applicable、checks／理由／非個資reviewer標籤與另列人工時間。全部必要資訊齊全才supported；不確定／不足不成功，正確負例拒答另列。人工耗時不改原工具計時、不計進查詢延遲。

最後以完整50分母彙總五秒內supported成功、超五秒supported、無支持放行及各固定錯誤／未判讀。p50／p95／max與成功子集分開標示；annotation_invalid不縮分母，修訂資料另版本另run、舊結果仍保存。合成案例先驗這些計數規則，實際CPU再opt-in；不新增runtime充分性判斷器或雲端審核。

## 舊v1本機提示驗證（U2）

先用合成安全manifest header與假worker，確認v1被拒絕前未開原包Chroma。私密failure reason=legacy_package只存在worker／runtime，不進模型結果或設定回應；公開仍document_unavailable，不能因其他壞包／例外文字冒稱v1。

對HF／Gemini共享handler各驗：有效call在本機文字區顯示一次「此文件索引為舊版，請停止 App，使用離線產包腳本重新產生新版索引包。」無路徑、無專用TTS／response.create或重複逐字稿；通用錯誤對話仍按既有行為。重複通知同call不重複；入queue後插話／取消／停用／切換／新回合則不顯示、不補送。下次明確有效query可各顯示一次，不是整個App只提示一次。

首次query觸發載入回not_ready後，非同步發現v1只快取原因，不復活已結束首問；下一次有效query才出提示。無效query、工具停用、一般unavailable與結果驗證失敗合成的unavailable不提示。timeout仍另測一次文字／零該錯誤語音，不因新增legacy提示改變SILENT。以上為新測試情境，未在本輪執行。

## HF／Gemini end-to-end acceptance

真實服務測試前確認使用者同意測試文件段落送到供應商、帳戶額度及是否使用語音／實體機器人；舊 API key 功能的授權不是本次文件外送授權。金鑰不貼聊天、不出日誌；相機／記憶保持既有關閉狀態。HF 維持預設、Gemini 由使用者手動選。

1. 固定人工標註 20 題可答（>=10 題換句話）、10 題不可答、5 題索取其他文件。逐題記錄檢索證據、段落支持、兩後端回答正確率、負例誤放行及來源；比例與零檢索誤放行不再是方案選用阻擋，不將舊題稱盲測。全部文件型回答仍須可核對來源，不得捏造或以其他文件／外部知識冒充原文。
2. 兩後端各 10 次查詢，覆蓋 5 次插話與 5 次取消／換後端／新對話；用可控慢查詢留出操作時間。沒有遲到語音／文字／動作、舊工具重播或 App 退出，後續一般聊天正常。
3. 問原文含數字／否定／日期／表格及注入指令的題目，核對上下文、繁體中文整理／原文保留與工具權限；負向文字不能造成額外動作或資料存取。
4. 停止 App，換另一份完整單文件版本包，重啟後只引用新版本；舊結果不可重用。此為部署更新測試，並非同時支援多文件。
5. 用可控慢 worker 讓每個後端各出現 timeout：有效原回合只看到一次「文件查詢已逾時，請稍後再試。」且沒有該錯誤觸發的語音；取消／插話／切換則連提示也不出現。duplicate 不重播、晚到成功不朗讀，接著明確新提問仍能正常語音。雲端協定支援不可只靠 fake 成功認定。
6. 依 FR-016 記錄 RAG worker 實際退出與副本清理；用受控卡住 child 測九秒截止及保留副本分支，不把 App 其他關閉作業算進或聲稱也受此九秒上限。

## Evidence and closure

記錄測試資料 digest／版本、主機、模型 snapshot、實際鎖檔、命令及結果；不寫私密段落、金鑰或日常路徑。維持原始失敗記錄，不用重測抹去第一次失敗。逐項對應 SC-001～SC-008、FR-001～FR-021，包含 schema 正反例、文字 timeout／零語音、九秒關閉與完整50題成功／失敗計數；未驗證的平台、CPU 延遲、雲端限制與現場項目照實列未完成／限制，不以離線 pass 代替。此指南不是免除實測的簽核。活動tasks T045～T084已同步v2基礎，本輪新增U1／U2尚待增量同步，歷史勾選只代表舊證據；未完成的實際素材／服務驗收保留未勾選。


## 2026-11-09 新版驗證與005交接

先由005分別準備兩固定模型，再明確選取版本化方案離線產v2包；未選取就停止。005 plan／CLI／receipt與新版reader需先同步，不能沿用舊命令加0.58就宣稱新流程可用。005發布前需獨立離線重開完整混合／重排並核對原包、模型、BM25、向量與持久索引不變；App不補建資料，發布後清理失敗exit8保持不變。

新版實作完成後，沿用上述現有pytest入口並擴充三路徑／雙模型與v2案例，不在本輪假造可執行benchmark CLI。真實整合測試缺任一資產只記未執行，不能自動下載。新runner須保存完整50題逐筆結果與既有失敗；重放已曝光200題只驗證實作一致性，不是新的獨立品質測試。

選值紀錄：max-distance0.58是固定組合在曝光200題的後置實務上限；84/100正例、2/100負例誤放行、127/131支持保留原分母與已知失敗。288段僅example.md實驗樣本，後續文件不得硬編碼此數量或自動繼承品質。語音／文件外送授權仍須依本次資料與服務範圍確認。

## 歷史證據邊界

以下2026-11-05續作、命令、平台取消及gate皆為當時v1 snapshot紀錄，原文保留。舊RAG_ACCEPTANCE_MODEL及48/50測試斷言尚未支援本輪三路徑／v2；請勿當作新版驗收指令或完成證據。新版測試與tasks須在實作階段更新，不能直接沿用歷史passed數字。

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


## 005共用讀取端交接（2026-11-10，非004整體結案）

005已離線實作v2 manifest／完整asset驗證、三路徑啟動配置、共用CPU模型／query可見原文、exact dense＋預建BM25／RRF／完整五候選重排及後置0.58；使用真正DocumentIndex供fresh verifier測原包與完整副本不變性。額外18項真實Chroma／假模型測試通過，非真實BGE／CPU50題／雙後端或現場證據。詳005 quickstart最新紀錄；004任務勾選維持原狀，舊包本機專用提示排程與完整生命週期驗收仍按004進行。使用者本輪選擇保存進度，未下載模型、啟動App或提交；舊失敗與曝光資料不改寫通過。


## 005 Windows真實素材交接（2026-11-10）

005已依當次明確授權完成兩固定模型v2 receipt、八份合成文件各兩次產包及實際替換／busy／worker啟動取消恢復驗收；詳見[005逐項結案證據](../005-prepare-rag-assets/quickstart.md)。模型與17個保留v2包仍在工作區 `cache/005-prepare-rag-assets/20261110-real-*` 的本輪隔離目錄，兩模型實際完整路徑見 `20261110-real-model-summary.json`，包與來源摘要見 `20261110-real-package-summary.json` 及 `20261110-real-lifecycle-summary.json`。未讀example.md／私人快取、未配置或啟動App、未勾004任務；不能用005素材完整性成功取代004專用提示、50題CPU／語音／雙後端／插話等剩餘驗收。Linux／macOS未實測，0.58及原品質限制不變。
