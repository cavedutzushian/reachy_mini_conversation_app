# Data Model: RAG 素材準備

## ModelPreparationRequest

- repo_id 固定 BAAI/bge-m3；revision 為 40 位小寫 hex，無預設。
- output 為已核對本機目錄；replace 為明確布林；預設 false。
- resolved_revision 必須與要求相同。既有同 revision receipt／payload 全部匹配才可 already_ready，該分支零網路。
- 不接受遠端 URL、model catalog 或 caller-supplied endpoint。

## ModelReceipt v1

發布於模型根的 model-receipt.json，結構見 [模型 receipt](contracts/model-receipt.md) 與 [schema](contracts/model-receipt.schema.json)。

- schema_version=1、model_id、revision、resolved_revision。
- files：payload 路徑／bytes／SHA-256，排除 receipt 自身；必須精確匹配 v1 allowlist，不接受額外未知檔。
- runtime：實際 ST／torch／transformers 完整版本；pipeline 與 004 相同。
- verification：固定 reference query、1024 維 normalized finite embedding；記載的是完成的本機檢查，不是簽章。
- model-root 實際檔案集合須等於 payload＋receipt；下載 metadata 與 stage 記錄不在其中。
- 包 manifest.embedding.files 在發布模型上重新枚舉，包含 receipt hash；不把 receipt inventory 直接當 embedding.files。

## TextSource

- source_path：唯一 .txt／.md／.markdown 常規檔，case-insensitive；不可為 link／junction／URL／glob。
- raw_bytes_sha256：UTF-8 解碼前 bytes（含原 BOM）hash。
- text：producer 一次讀取來源 bytes 後解碼的原字串；不進行 Unicode／語法／行尾正規化，不經 IPC 傳給父 CLI。
- initial_identity／initial_stat：初次讀取前後一致的來源身分、大小及修改資訊；raw_bytes_sha256、text、chunks、embeddings 均來自同一緩衝區。
- final_source_check：fresh verifier 在發布前串流 hash 並核對來源身分／stat，若修改或替換即拒絕發布；不重新解碼或 tokenize，也不宣稱封鎖其他程式寫入。
- document_id／version／index_version：004 安全 identifier；title 為既有 160 code point 限制；max_distance 有限 [0,2]，必須明確提供。
- 全無有效字母／數字內容拒絕；不解析圖片、連結、模板或目錄。

## SourceChunk

- chunk_id：`c-` 加 canonical JSON SHA-256，確切 key、編碼與測試規則見 [source-window-v1](contracts/source-window-v1.md)。
- start、end：decoded text Unicode code point offsets，0-based、end-exclusive，0 <= start < end <= len(text)。
- text：恰為 source.text[start:end]；不能從 token decode 重建。
- ordinal：來源順序；長單行可多片且行號相同，用字元範圍辨識。
- locator：`L<first>-L<last>; chars[<start>,<end>)`；行號 1-based inclusive，字元範圍 0-based end-exclusive。CRLF／LF／單 CR 各算一個換行，片尾換行歸其所在行，不虛構下一行；不生成頁碼或解析標題。
- policy：固定 source-window-v1，400 content token 候選、50 token 重疊起點規則、512 字元零 offset fallback；含特殊 tokens 的每片實際編碼 <=512。完整演算法、CRLF／尾端／零 offset／非單調處理與 golden fixtures 以切段合約為準，不使用概略重疊或未定字元 fallback。
- embedding：共用 encoder 產生的 CPU float32 normalized dense 1024 向量，不進診斷。
- Chroma row：id=chunk_id、documents=text、metadatas 僅 document_id／document_version／locator；heading 不是 v1 必要欄位。

## CandidatePackage / PublishedPackage

格式完全沿用 004，無新 schema／未知 manifest 欄位。完整原文與向量只在 collection，原始檔不必複製進交付包。

建置中可填本機 validated_targets／snapshot_complete 供現有 reader 測試；那只是私有 candidate。producer 結束、完整 hash／邏輯／HNSW 不變性檢查全部成功，才把相同 bytes 發布。實際驗證平台以 runtime_target 取得；不能複製其他主機 target。

chunker policy 是程式固定版本與準備操作記錄的一部分，不塞入不接受未知欄位的 004 manifest。使用者的已校準 max_distance 不是這個程式自動產生的結論。

## PreparationOperation

操作記錄位於目的地 sibling lock directory，不放進模型 payload 或索引包：

- operation_id：隨機 UUID；kind=model／package；本次 owner PID 僅診斷，不能用來自動授權清理。
- destination_name、stage_name、backup_name：已核對父目錄內的 basename，不接受 `..`／絕對路徑／link。
- phase：locked → preparing → validating → validated → backed_up（僅替換）→ published → cleaning。
- validated stage → destination rename 成功為發布界線；操作記錄寫入失敗也不能撤銷已發生的發布。
- 發布前新建失敗不留下可用目的地；替換第二個 rename 普通失敗回復 backup，舊 payload bytes 不變。舊目錄可暫移 backup，並非保證目的地路徑全程存在。
- 發布後 backup／stage／lock／操作記錄清理失敗：保留新版，status=recovery_required、code=cleanup_incomplete、published=true、exit=8；不得自動回復或重跑。
- 任一目的地 lock 已存在即 busy；builder 模型鎖→包鎖固定順序，失敗釋放本次已取得者。不根據時間自動過期，不自動 recover。
- 硬中斷保留階段與可恢復舊版的 backup。人工先確認無準備行程，再依記錄核對內容恢復；不只刪 lock 重新開始。

## PreparationResult

status 為 completed／already_ready／failed／busy／recovery_required。published 為必填布林，表示本次是否已將候選放入正式位置；already_ready 為 false，另有 ready（bool 或 null），true 表示素材已驗證就緒，null 表示未判定。completed 為 published=true、ready=true；發布前失敗／busy 為 published=false、ready=null，不據此推論既有素材不可用。發布後清理不全為 published=true、ready=true、exit=8，附精確自有殘留及人工清理指引。中文安全摘要可含目的地、revision、count、固定錯誤碼；不可含原文、完整向量、token 或 provider body。程序 exit code 與固定碼見 [CLI 合約](contracts/preparation-cli.md)。

模型／包若突然中斷，不會變成 completed；下載成功不等於 reader／語音驗收成功。005、004 的完成狀態各自保留。
