# Contract: 兩個手動準備入口

**Status**: 2026-11-10 介面已完成離線實作，含雙角色下載、章節／別名／BM25產包與完整v2 reader；已完成兩固定BGE模型及Windows合成文件三步交接驗收；Linux／macOS未測，004語音／效能另驗。實際證據及限制見 [驗收指南](../quickstart.md)，不以假模型結果宣稱真實模型通過。

## Download

`python -m reachy_mini_conversation_app.download_document_model --role <embedding|reranker> --revision <40-hex> [--output <directory>] [--replace]`

- role 與 revision 都必填；每次只處理一個角色。embedding 固定 BAAI/bge-m3／50f9396f75618b3389c1fd1068a1ff58dc7b5b26；reranker 固定 BAAI/bge-reranker-base／2cfc18c9415c912f9d8155881c133215df768a70。revision 為40位小寫hex且必須符合該角色；不接受main／tag／URL／endpoint或其他模型。
- output 依角色預設 source checkout 根的 external_content/bge-m3-model 或 external_content/bge-reranker-base-model；無法辨識checkout則必須明確提供。不連帶準備另一角色，不提供雙目的地彙總發布。
- replace 預設 false，沒有替換授權不能寫入已存在目的地；同版本且 receipt／payload 完整可 already_ready。
- 已有完整同版本優先離線核對，不做 metadata 查詢；其餘先拒絕非法／重疊／busy 目的地，再匿名預檢固定 revision。
- public endpoint 固定、token=False、本次專用 cache；不使用私人 cache／HF_ENDPOINT／dotenv／對話金鑰。只取安全 allowlist。缺 safetensors 回 unsupported_revision，不改挑 PR 或轉換 bin。
- 大檔下載前核對 resolved SHA、必要檔名與小型配置；下載後核對可取得的上游 LFS／Git 檔案識別與本機 hash。終端只顯示版本、檔案數／進度、安全結果及路徑，不回傳原始 provider error body。
- 最終payload＋model-receipt.json先依角色離線驗證：嵌入產生合規向量，重排對固定非敏感配對輸出有限原始logit；前後hash一致才發布。單一角色ready不代表兩模型或整套素材ready；下載metadata不跟入模型根。舊v1 receipt不視為新版ready，不就地改寫；以明確--replace重新驗證／準備後發布v2。

## Build

`python -m reachy_mini_conversation_app.build_document_package --input <file> --document-id <id> --title <text> --document-version <version> --index-version <version> --scheme bge-base-final-selection-20261109 [--model <directory>] [--reranker-model <directory>] [--aliases <json-file>] [--output <directory>] [--replace]`

- input 僅一個常規 TXT／MD／MARKDOWN，副檔名不分大小寫；UTF-8／UTF-8 BOM，拒絕 URL／glob／目錄／link。重複 input 參數或額外 positional 拒絕，不採 argparse 預設的最後一個覆蓋行為。
- document-id／document-version／index-version遵004 identifier，title遵004 display text。--scheme必填且只接受bge-base-final-selection-20261109，未選取即停止；不自動套用預設、不逐項手填參數、不接受--max-distance或其他參數覆寫。自動帶入完整固定方案、0.58後置用途及已知限制，不要求品質通過／校準證明。
- model／reranker-model／output預設checkout的external_content/bge-m3-model、external_content/bge-reranker-base-model、external_content/document-package；無checkout時三者都要明確給出。相對的明確參數從呼叫 CWD 解析，預設值則從 checkout 解析，輸出顯示最終絕對值。
- 兩模型均須有可信v2角色receipt、完整必要檔與符合的實際runtime，不自動連網。先將兩模型的已解析、平台正規化路徑依固定字典序取得同款目的地鎖，再鎖output；任一busy立即釋放本次已取得鎖並失敗，不等待。模型目錄彼此相同／重疊或與來源／output危險重疊即拒絕。
- 原文hash／vectors遵data-model，切段／ID／locator／標題及可選人工別名遵[chapter-source-v1](chapter-source-v1.md)。--aliases僅接受一個本機常規UTF-8 JSON，內容／來源核對依該合約；未提供則保存明示空清單，不自動擷取／生成。別名檔只作本次指定文件的檢索脈絡，不是第二份文件。reference query固定非敏感文字，不送服務。
- producer事先生成全部文件向量、章節／來源別名資產、BM25 TF／DF／長度／avgdl及Chroma持久索引；公開close／退出後，fresh verifier以新版004 reader與兩模型重開並執行完整混合／重排，再核對全量／副本不變性才發布。正常無命中與操作失敗須區分，不以logit高低／命中率作品質通過證明；不能以snapshot_complete=true跳過驗證。
- 只產004 v2包；v1須由原始TXT／Markdown重新產包，不就地轉換、改版本欄或保留舊dense-only流程。新版reader未備妥或驗證失敗不宣告App可讀就緒。來源文件、別名輸入與兩模型不被修改；不自動設定／啟動App、不執行文件內連結與指令。

## Common lifecycle and result

標準輸出是繁體中文 CLI 結果，可顯示使用者指定路徑、revision、段落數與嵌入／重排／索引三個環境設定值（REACHY_MINI_DOCUMENT_MODEL_PATH、REACHY_MINI_DOCUMENT_RERANKER_PATH、REACHY_MINI_DOCUMENT_INDEX_PATH）。這些只是設定建議，不寫 .env。診斷日誌只含固定碼／安全類別／非內容摘要，不含文件全文、向量或 token。

| Exit | 結果／固定碼範例 |
|---|---|
| 0 | completed／already_ready；help 也為 0 |
| 2 | invalid_arguments／invalid_document／invalid_scheme／invalid_aliases |
| 3 | unsupported_revision／model_not_ready／model_incompatible |
| 4 | destination_exists／destination_busy／unsafe_path |
| 5 | download_unavailable |
| 6 | validation_failed／snapshot_incomplete |
| 7 | io_failed |
| 8 | recovery_required；發布後清理不全 code=cleanup_incomplete、published=true、ready=true，保留新版且不自動重跑；發布前恢復失敗則 published=false |
| 130 | 發布前 cancelled；若無法安全回復則 exit 8／published=false 並附恢復指引。發布後取消清理按 exit 8／published=true 處理，不宣稱未發布 |

--help 在未裝 rag 或未提供素材時仍可閱讀。只有實際重型操作才需要 rag；缺套件明確說明安裝既有 extra，不自行安裝。

目的地 lock 已存在就拒絕，不自動根據時間／PID 破鎖。預設 siblings 的 stage／backup／lock 只屬本次操作，需窄範圍 Git 忽略；自訂輸出在 repo 內但未忽略時拒絕並請使用者改位置或自行管理忽略，不修改 Git 設定。

結果必須區分 published（本次是否發布）與 ready（是否已驗證就緒）：completed 的 published=true／ready=true，already_ready 的 published=false／ready=true；發布前失敗／busy 為 published=false、ready=null，不推測既有素材。發布後清理不全 true／true 仍非 exit 0。

替換前先由使用者停止 App。先 old→backup，再 validated stage→destination；後者 rename 成功就是發布界線。界線前普通失敗恢復 backup，舊 payload bytes 不變，但不保證目的地路徑全程存在。界線後任何清理／階段記錄失敗均保留新版、exit 8／published=true，顯示「已發布，清理未完成」及自有殘留；不得自動 rollback、下載、產包或重試。硬中斷留操作記錄、可核對舊版及恢復指引；人工需核對實際目錄／hash，不能只相信可能尚未更新的 phase。沒有自動 recovery 入口；人工先確認無準備程序，核對記錄及 stage／backup hashes，恢復完整目的地後才清理自有殘留。不能只刪 lock／舊目錄，也不停止其他應用程式。

## Internal worker boundary

document_prepare_worker 是兩 CLI 的內部本機子程序，不是第三個使用者腳本；不開 socket、不載 dotenv、不啟動 SDK。父程序持有發布鎖，子程序不得移動正式目的地。

- Request：typed operation（模型驗證／producer／fresh verifier）、已驗證 source／model／stage／副本路徑，以及role／revision、文件ID／title／versions／scheme與固定策略等scalar metadata；別名檔路徑也需先驗證；不傳全文、chunks、向量、model／tokenizer 或 pickle。
- Result：固定狀態／錯誤碼、來源與檔案 digests、count、安全驗證結果；不傳 reference embedding、文件段落或 collection。所有 receipt／manifest／collection 由 worker 寫入本次 candidate 檔案，父程序只核對摘要與路徑並發布。
- 所有模型／tokenizer載入與inference均在worker；CPU float32、intra-op2／inter-op1只在程序入口設定一次，不因載入兩模型重設inter-op。producer 唯一負責初次來源 bytes 讀取、hash、解碼、切段、locator 與文件向量。純切段函式可位於輕量 build 模組，接受 typed tokenizer 介面，不 import inference stack 或自行建立 tokenizer。
- 模型驗證worker與fresh verifier仍各自獨立依角色載入／驗證。producer一次讀取來源及可選別名bytes並保存初始hash／身分；fresh verifier發布前串流核對兩輸入hash與初始身分／stat，變更即拒絕，不重新建立文件向量或BM25資料，也不宣稱禁止外部寫入。

producer 與 verifier 必須是不同程序；工作完成後 public close 並正常退出，父程序確認退出才接續。中斷時先終止工作程序、確認資源已釋放再清理；無法確認則保留操作狀態，不刪檔、不發布。

## 固定三步與方案追溯

依序明確下載embedding、下載reranker，再以--scheme執行產包，共三次手動呼叫。每個目的地獨立發布／結束碼8；任一模型未ready不宣告整套ready。包保存固定完整設定、選案紀錄digest、200題曝光與84/100正例、2/100負例誤放行、127/131段落支持及限制；不依賴App讀取工作區cache，不稱0.58為新文件已校準。產品既有CLI入口與Tool／HF預設不因本契約更新自動改變。
