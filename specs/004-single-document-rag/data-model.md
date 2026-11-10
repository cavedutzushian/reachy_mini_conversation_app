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
| 包識別 | manifest schema `2`、index_version、唯一 DesignatedDocument；完整結構以 [JSON Schema](contracts/index-manifest.schema.json) 為準，未知欄位拒絕 |
| 引擎 | 精確 chromadb 版本、固定 collection；producer 與 validated_targets 皆使用 os=windows／linux／macos、architecture=x86_64／aarch64 的固定物件 |
| 資料 | chunk_count >0、files 為 path／sha256 物件陣列（path 相對 chroma 根）、完整且無待回放寫入的快照宣告；assets.files 相對 retrieval/，明列 chunks.jsonl 與 bm25.json |
| 模型 | 嵌入 model_id 固定 BAAI/bge-m3、revision固定50f9396f75618b3389c1fd1068a1ff58dc7b5b26、embedding.files 為 path／sha256 陣列（path 相對模型根），包括 tokenizer 與 modules 雜湊 |
| 管線 | sentence-transformers／torch／transformers 精確版本、dense、float32、CLS、L2、無 prefix、維度 1024、cosine、max_seq_length 8192 |
| 重排模型 | BAAI/bge-reranker-base、revision固定2cfc18c9415c912f9d8155881c133215df768a70、獨立模型根的完整檔案清單／hash；CPU float32、Identity logit、pair512、batch4 |
| 檢索／重排 | exact dense10、BM25正分10、等權RRF60、至多五個完整候選；min logit3.486859679222107、額外drop4、三段／2000code points，再套cosine0.58，無同父限制或group margin |
| 策略 | strategy.id=chapter-alias-hybrid-bge-base-v1；chunking_version=chapter-source-v1、source_context_version=source-title-alias-v1、selection_version=rerank-budget-then-distance-v1；未知版本拒絕 |
| 選值來源 | provenance記錄使用者選案、固定參數與來源紀錄、曝光200題、84/100正例、2/100負例誤放行、127/131段落支持及已知限制；不是新文件已校準證明 |
| 一致性 | 非敏感 reference_query／1024 維 reference_embedding；只驗證編碼一致性，不判斷品質 |

完整 preflight 對所有段落驗證來源一致、原文／locator／ID／向量維度及有限數值；不能只驗命中的三段。檔案 hash 對照 exact inventory，拒絕缺漏、未列檔、符號連結／junction、路徑穿越及不相容目標。雜湊用於完整性，不是簽章或可信發布者證明；只部署可信來源的包與模型。

JSON Schema 與 index-package.md 的額外語意檢查缺一不可；所有 required 欄不得 null／省略，清單不得同 path 不同 hash，精確版本包括 local suffix。reference 的 query 遵工具相同輸入順序，向量非零／有限／1024 維、norm 誤差 <=1e-4，參考 cosine 差距 <=1e-5。不在執行時補欄或放寬門檻。

包先通過靜態檢查，再複製到實例私有暫存目錄並重驗雜湊；原包不傳給 Chroma。載入既有 collection 後 count／逐批 get、完整來源／BM25／脈絡關聯與 manifest 相符才 ready；保留核對後的既有向量矩陣供 exact cosine 打分，不生成或重建索引。引擎不得藉驗證執行任何索引寫入；開啟相容性由真實測試確認。

## 3. DocumentChunk

| 欄位 | 型別／限制 |
|---|---|
| chunk_id | 唯一、穩定、安全字串 <=128 code points，對應 Chroma row ID |
| document_id / document_version | 必須等於 manifest 唯一文件 |
| text | 非空原文；存於 Chroma documents，與 retrieval/chunks.jsonl 的相同 ID／原文字串一致 |
| source range | 真實 start/end line 與來源code point範圍；無標題TXT是單文件範圍，無假頁碼／章節 |
| source context | 來源章節／文件名稱＋可選人工別名，與原文分開；model_text及其來源offset對照供評分裁切，不是引文 |
| locator | 非空文字 <=256 code points，例如真實章節／頁碼／段落；無頁碼者不虛構 |
| embedding | 1024 個有限數、非零、L2 normalized float32；不進模型工具結果 |

每個 row 只有一份文件版本。重複 ID、空 documents、metadata 缺漏或混合來源皆整包 unavailable，不略過壞段落繼續作答。

## 4. DocumentQuery / InvocationOwnership

| 欄位 | 生命週期 |
|---|---|
| request_id / call_id | runtime 請求及既有工具呼叫的唯一關聯 |
| query | 先檢查原始字串（含前後空白）<=500 Unicode code points，再 trim 後檢查至少一個字母或數字；無效不送 worker |
| generation / response_epoch | 由既有 handler 擷取，對話端檢查，不送文件包或作為使用者參數 |
| accepted_at / deadline | monotonic 受理時間及 +10 秒期限 |
| status | accepted → running → completed／failed，或 retired |
| answer_retired | bool，初始 false；timeout／取消／回合失效即 true，永久撤銷背景答案 |
| timeout_notice_sent | bool，初始 false；只在仍擁有原回合時顯示一次本機文字後設 true |
| legacy_notice_sent | bool，初始 false；已確認v1且該次有效查詢回unavailable時，排入一次本機專用提示前設true；與timeout標記獨立 |

`retired`／answer_retired 不可恢復。逾時永久丟棄背景答案，但 timeout_notice_sent 與 generation／response_epoch 的回合所有權另外判斷：同回合仍有效才顯示一次固定文字、不播放語音；若已取消／插話／停用／切換或開始新對話則連 notice 也不投遞。duplicate call ID 不能復活背景答案或重複 notice；有效 call 必需的協定完成不代表新的顯示／語音授權。CPU 工作完成、背景答案失效及回合所有權是不同狀態，不能混成一個 completed flag。

## 5. RetrievalResult

成功：依logit降序／ID同分序並完成後置距離篩選，文件 title／ID／version、index_version 及 1–3 個 CitationPassage。每段有 chunk_id、locator、text、truncated；text 合計 <=2,000 code points。只複製重排實際可見的同一原文或連續前綴，不改寫引用、拼接兩句或生成 locator。title／locator metadata 不列入原文預算，但受各自上限限制。

未成功：`{"error": "document_..."}`，固定碼見工具合約。無依據也使用此固定失敗形狀，避免現有 manager 丟失額外 code 欄位。document_timeout 是只顯示本機文字的特殊投遞模式，不能因 error 存在強制 spoken follow-up；成功結果仍需要正常回答。錯誤不含使用者輸入、完整路徑或底層例外內容。

## 6. RuntimeState

| 狀態 | 允許行為／轉移 |
|---|---|
| unconfigured | 不讀包／模型；query → not_ready；配置須重啟 |
| dormant | 配置完整且尚未啟動；只有已啟用工具的 query 可觸發 loading |
| loading | 唯一 worker 驗證包／載入模型，query → not_ready；<=120 秒轉 ready 或 failed |
| ready | 最多接一份工作 → busy |
| busy | query → busy；worker 實際結束 → ready；waiter 逾時／取消仍 busy |
| failed | 固定 not_ready 或 unavailable，依原因區分；不自動重啟，重啟 App 才重新檢查 |
| closing / closed | 撤銷 answer／notice 所有權；依 5／2／2、總九秒回收 worker，確認退出才清副本；未確認則保留並記 cleanup_incomplete，不接受新查詢 |

設定讀取不等於檔案讀取授權。人格停用時 dispatcher 不得查文件；先前已啟用載入的模型可保留，但不執行新工作。worker 永久卡住時一直 busy，直到 App 停止回收；不藉另開 worker 堆疊資源。

## 7. SourceContext / ManualAlias

每個chunk_id對應唯一文件版本的原文字串、真實行號／code point範圍、原有標題與model_text來源offset。Markdown章節路徑只取原有標題；TXT沒有標題時以文件名作來源，不編造章節。人工別名是可選清單，沒有時明示空清單；每項包含可定位同文件／版本的原文證據及適用來源範圍，不能因其他位置出現名稱就錯配章節。不自動擷取／生成別名或同義詞。

raw text／定位與來源模型脈絡分開；原文保留BOM外的實際解碼內容及原始行尾，原始bytes摘要含BOM。模型右側裁切按tokenizer offset映回原文，不能把標題或別名重複部分當作支持文字；實際評分可見範圍才可回傳。模型可見prefix與2000字元結果prefix不同，兩種裁切都明示truncated，不重寫原文。

## 8. PrebuiltBM25

retrieval/bm25.json保存版本化tokenizer／公式參數、chunk ID列表、每段tf、doc length、全文件df、N、avgdl與對應model_text身分。所有資料由005預先產生，與Chroma及chunks資產ID全集一致。文件數N由chunk_ids長度取得，沒有另設可分歧的N欄位；TF／length陣列依相同順序。已列TF／DF為正整數，df<=N、每段長度等於tf總和、N等於chunk_count、avgdl等於總長度/N；空token段合法但不得除零。失配／缺資料是unavailable，不在App重新tokenize全文件或修復。

query以相同ASCII／CJK二三字組tokenizer轉換並去重；BM25使用預建TF／DF／長度計算正分top10，不新建詞頻或倒排。RRF一項每路最多一次，同分ID；lexical-only候選亦必須有既有父向量，不能臨時計算文件向量。標準庫運算不增索引依賴。

## 9. Package lifecycle / v1 rejection

v2靜態檢查 → 原包與雙模型核對 → 私有工作副本 → 既有引擎／全部段落與BM25關聯檢查 → 雙模型離線載入與reference一致性 → ready。任一步不相容即failed；v1不升級、不遷移、不維持舊dense-only分支，提示部署者在App外依005重產。hash只證明完整性，來源信任仍由部署者提供。

包schema版本2、worker私密pipe版本1、策略版本與文件版本是獨立欄位，不能混用。新版只有在實作與005 reader驗證完成後才能宣告App可讀；本輪資料模型不是發布或驗收完成證據。

## 10. VersionedChunkingConfiguration

chapter-source-v1保存target_tokens=300、overlap_tokens=30、embedding_input_max_tokens=512、heading_context_max_tokens=64、alias_context_max_tokens=48、heading_levels=3。BGE-M3本身8192上限與本方案512輸入上限是不同欄位。長段落不得靜默省略，切分後來源範圍必須完整覆蓋；TXT無標題／Markdown前言／code fence是通用建包案例，不能聲稱在原288段測過。完整演算法與固定model_text標籤以包合約為準，不自動換模板或硬套實驗別名。

## 11. LocalUnavailableReason / LegacyNotice

runtime新增本機唯讀typed屬性unavailable_reason，值只為legacy_package或None，以既有鎖保護；初始化／關閉清除，只接受私密worker failure中與document_unavailable相容的已驗證reason。不是model／query參數、Tool結果、日誌原始文字或設定查詢欄位；不得從例外字串推斷。

有效manifest header的整數schema_version=1是舊包識別，非JSON／bool／未知版本或其他格式故障不冒稱v1。不開舊引擎或維護dense-only讀取路徑。初次query回not_ready後的載入失敗只快取原因；不從thread發UI或對已結束query補送。下一個有效明確query的unavailable才可讓共享handler顯示，duplicate同call不重複；新有效call可各顯示一次。

固定提示：「此文件索引為舊版，請停止 App，使用離線產包腳本重新產生新版索引包。」沿既有DocumentOutput附原generation／response_epoch，入queue前及emit消費時都驗原回合／tool權限；失效不顯示、不補送。legacy_notice_sent只表示該call已排入提示，失效後不重排；不把它合併成timeout_notice_sent或改answer_retired的原意。專用文字不要求provider朗讀，不加第二條transcript append；一般錯誤回覆保持既有行為。

## 12. FrozenCpuDataset / CpuObservation / ManualEvidenceReview

資料僅供工作區cache的離線驗收，與App查詢快取／診斷日誌分開；只使用明確提供的無敏感測試文件。完整欄位與狀態見 [cpu-evaluation](contracts/cpu-evaluation.md)。

FrozenCpuDataset有版本／digest、唯一document ID／version／source digest、固定50個唯一question ID、問題／可答性／必要資訊／原文與定位；引用綁定同一來源，測前凍結。CpuObservation保存每題單次工具執行時間／安全錯誤或原始有界結果及包／模型版本；延遲是受理到工具結果或逾時，不含人工。

ManualEvidenceReview保存question ID／run ID、supported／unsupported／uncertain／not_applicable狀態、逐必要資訊判定、可見回傳證據定位、判讀理由、非個資reviewer標籤／判讀時間。未判讀不能當成功；只有supported且正常工具成功才算具支持成功，並以原工具時間判斷是否五秒內。否定／不確定／不可判定標註不計成功，但全部50分母保留。標註更正另版本／另run，不改舊原始紀錄，不新增任何runtime充分性判斷器。
