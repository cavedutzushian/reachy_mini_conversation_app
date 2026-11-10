# Data Model: RAG 素材準備

## ModelPreparationRequest

- role必填embedding／reranker；repo_id分別固定BAAI/bge-m3／BAAI/bge-reranker-base；revision必填且須等於方案固定SHA，見receipt契約。
- output 為已核對本機目錄；replace 為明確布林；預設 false。
- resolved_revision 必須與要求相同。既有同 revision receipt／payload 全部匹配才可 already_ready，該分支零網路。
- 不接受遠端 URL、model catalog 或 caller-supplied endpoint。

## ModelReceipt v2

發布於模型根的 model-receipt.json，結構見 [模型 receipt](contracts/model-receipt.md) 與 [schema](contracts/model-receipt.schema.json)。

- schema_version=2、role、model_id、revision、resolved_revision，角色與固定ID／SHA一致。
- files：payload 路徑／bytes／SHA-256，排除 receipt 自身；必須精確匹配各角色allowlist，不接受額外未知檔。
- runtime：實際 ST／torch／transformers 完整版本；pipeline 與 004 相同。
- verification：嵌入為固定reference query／1024維normalized finite embedding；重排為固定非敏感query／passage配對及有限原始logit。角色分支由schema固定，驗證不是簽章或品質通過證明。
- model-root 實際檔案集合須等於 payload＋receipt；下載 metadata 與 stage 記錄不在其中。
- 包manifest.embedding.files及reranking.files分別在發布模型上重新枚舉，包含 receipt hash；不把receipt inventory直接當任一角色的完整模型清單。

## TextSource

- source_path：唯一 .txt／.md／.markdown 常規檔，case-insensitive；不可為 link／junction／URL／glob。
- raw_bytes_sha256：UTF-8 解碼前 bytes（含原 BOM）hash。
- text：producer 一次讀取來源 bytes 後解碼的原字串；不進行 Unicode／語法／行尾正規化，不經 IPC 傳給父 CLI。
- initial_identity／initial_stat：初次讀取前後一致的來源身分、大小及修改資訊；raw_bytes_sha256、text、chunks、embeddings 均來自同一緩衝區。
- final_source_check：fresh verifier 在發布前串流 hash 並核對來源身分／stat，若修改或替換即拒絕發布；不重新解碼或 tokenize，也不宣稱封鎖其他程式寫入。
- document_id／version／index_version：004 安全 identifier；title 為既有 160 code point 限制；必須明確選取scheme，不接受單獨max_distance；固定方案帶入0.58及完整logit／檢索參數。
- 全無有效字母／數字內容拒絕；不解析圖片、連結、模板或目錄。

## SourceChunk

- chunk_id：`c-` 加 canonical JSON SHA-256，確切key、編碼與測試規則見 [chapter-source-v1](contracts/chapter-source-v1.md)，含來源／策略／別名與model_text身分。
- start、end：decoded text Unicode code point offsets，0-based、end-exclusive，0 <= start < end <= len(text)。
- text：恰為 source.text[start:end]；不能從 token decode 重建。
- ordinal：來源順序；長單行可多片且行號相同，用字元範圍辨識。
- locator：`L<first>-L<last>; chars[<start>,<end>)`；行號 1-based inclusive，字元範圍 0-based end-exclusive。CRLF／LF／單 CR 各算一個換行，片尾換行歸其所在行，不虛構下一行；不生成頁碼；來源標題另保存並驗證原文範圍。
- policy：chapter-source-v1；300token目標／30重疊、512完整嵌入輸入、64標題／48別名脈絡；Markdown真實ATX邊界與TXT單範圍，長段完整覆蓋，不生成不存在章節。舊source-window-v1只留歷史，不接受為v2替代。
- headings／aliases：同文件／版本的來源定位與適用scope；無清單為空，別名不作引用。
- context／alias_context／model_text／model_text_sha256：依004固定模板保存脈絡與原文映射，嵌入／BM25／重排使用同一model_text。
- embedding：共用 encoder 產生的 CPU float32 normalized dense 1024 向量，不進診斷。
- Chroma row：id=chunk_id、documents=text、metadatas 僅 document_id／document_version／locator；完整章節／別名與原文範圍在retrieval/chunks.jsonl，與row一對一。

## CandidatePackage / PublishedPackage

格式沿用004新版schema_version2，不另定第二份manifest schema；新增策略／切段／assets／BM25／reranking／provenance均須完整。原文在collection與chunks資產逐字一致、向量在collection，原始檔不必另複製。v1包拒絕、離線重產，不自動轉換。

建置中可填本機 validated_targets／snapshot_complete 供新版reader完整混合／重排測試；那只是私有 candidate。producer 結束、完整 hash／邏輯／HNSW 不變性檢查全部成功，才把相同 bytes 發布。實際驗證平台以 runtime_target 取得；不能複製其他主機 target。

chunking／strategy／retrieval／reranking參數完整寫入004v2允許欄位，provenance保存明確選取方案與已知限制；0.58是實驗設定，不要求已校準品質合格證明。

## PreparationOperation

操作記錄位於目的地 sibling lock directory，不放進模型 payload 或索引包：

- operation_id：隨機 UUID；kind=model／package；本次 owner PID 僅診斷，不能用來自動授權清理。
- destination_name、stage_name、backup_name：已核對父目錄內的 basename，不接受 `..`／絕對路徑／link。
- phase：locked → preparing → validating → validated → backed_up（僅替換）→ published → cleaning。
- validated stage → destination rename 成功為發布界線；操作記錄寫入失敗也不能撤銷已發生的發布。
- 發布前新建失敗不留下可用目的地；替換第二個 rename 普通失敗回復 backup，舊 payload bytes 不變。舊目錄可暫移 backup，並非保證目的地路徑全程存在。
- 發布後 backup／stage／lock／操作記錄清理失敗：保留新版，status=recovery_required、code=cleanup_incomplete、published=true、exit=8；不得自動回復或重跑。
- 任一目的地 lock 已存在即 busy；builder兩模型按規範路徑排序取鎖，再取包鎖，失敗釋放本次已取得者。不根據時間自動過期，不自動 recover。
- 硬中斷保留階段與可恢復舊版的 backup。人工先確認無準備行程，再依記錄核對內容恢復；不只刪 lock 重新開始。

## PreparationResult

status 為 completed／already_ready／failed／busy／recovery_required。published 為必填布林，表示本次是否已將候選放入正式位置；already_ready 為 false，另有 ready（bool 或 null），true 表示素材已驗證就緒，null 表示未判定。completed 為 published=true、ready=true；發布前失敗／busy 為 published=false、ready=null，不據此推論既有素材不可用。發布後清理不全為 published=true、ready=true、exit=8，附精確自有殘留及人工清理指引。中文安全摘要可含目的地、revision、count、固定錯誤碼；不可含原文、完整向量、token 或 provider body。程序 exit code 與固定碼見 [CLI 合約](contracts/preparation-cli.md)。

模型／包若突然中斷，不會變成 completed；下載成功不等於 reader／語音驗收成功。005、004 的完成狀態各自保留。

## AliasSource / PrebuiltLexicalStatistics

可選--aliases檔案的身分與格式見chapter-source-v1；指定檔案才讀取，不搜尋其他文件。人工證據與scope必須對應指定source bytes／版本，無效清單整次拒絕。來源與別名讀入時快照並發布前串流核對hash／身分／stat，兩者改動或替換都拒絕發布。

retrieval/bm25.json固定版本bm25-prebuilt-v1，chunk_ids、term_frequencies、document_lengths、document_frequencies、average_document_length與004合約相符。N由chunk_ids長度取得；TF／DF正整數、df<=N、length=sum(tf)、avgdl為平均，無token段可length0，全語料空token時avgdl0合法且查詢lexical0分。統計由producer預建，不放入私密IPC或App重新生成。

## SelectedScheme / Provenance

scheme_id=bge-base-final-selection-20261109，selection=explicit-user-choice；strategy.id=chapter-alias-hybrid-bge-base-v1。reader／producer只接受同一固定參數與版本，不因文件改變自動調參。final-scheme.json／report.md名稱及SHA-256、模型／策略／選值來源、quality_gate_passed=false、200題曝光狀態、84/100正例／2/100負例誤放行／127/131段落支持與限制隨版本化方案交付，再寫入包，不依賴使用者cache。

歷史實驗來源摘要與實際document.source_sha256分開；新文件不冒稱原example或已校準，288段不是資料量常數。完整順序：exact dense10／BM25正分10→等權RRF60五候選→BGE-base raw logit最低3.486859679222107／附加drop4→最多三段及2000字元→父cosine0.58後置篩選。top1超限整次無依據、extras超限刪除不補段，不限父章節／無group margin。無充分性規則／額外模型／雲端審核。
