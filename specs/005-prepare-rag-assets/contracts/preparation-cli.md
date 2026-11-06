# Contract: 兩個手動準備入口

**Status**: 設計合約，尚未實作；不得將以下命令視為已可執行。

## Download

`python -m reachy_mini_conversation_app.download_document_model --revision <40-hex> [--output <directory>] [--replace]`

- revision 必填、40 位小寫 hex；repo 固定 BAAI/bge-m3，不接受 main／tag／URL／endpoint 參數。
- output 預設 source checkout 根的 external_content/bge-m3-model；無法辨識 checkout 則必須明確提供。
- replace 預設 false，沒有替換授權不能寫入已存在目的地；同版本且 receipt／payload 完整可 already_ready。
- 已有完整同版本優先離線核對，不做 metadata 查詢；其餘先拒絕非法／重疊／busy 目的地，再匿名預檢固定 revision。
- public endpoint 固定、token=False、本次專用 cache；不使用私人 cache／HF_ENDPOINT／dotenv／對話金鑰。只取安全 allowlist。缺 safetensors 回 unsupported_revision，不改挑 PR 或轉換 bin。
- 大檔下載前核對 resolved SHA、必要檔名與小型配置；下載後核對可取得的上游 LFS／Git 檔案識別與本機 hash。終端只顯示版本、檔案數／進度、安全結果及路徑，不回傳原始 provider error body。
- 最終 payload＋model-receipt.json 先離線 load／encode、前後 hash 一致，再發布；下載 metadata 不跟入模型根。

## Build

`python -m reachy_mini_conversation_app.build_document_package --input <file> --document-id <id> --title <text> --document-version <version> --index-version <version> --max-distance <number> [--model <directory>] [--output <directory>] [--replace]`

- input 僅一個常規 TXT／MD／MARKDOWN，副檔名不分大小寫；UTF-8／UTF-8 BOM，拒絕 URL／glob／目錄／link。重複 input 參數或額外 positional 拒絕，不採 argparse 預設的最後一個覆蓋行為。
- document-id／document-version／index-version 遵 004 identifier，title 遵 004 display text；max-distance 必填有限 [0,2]，是使用者提供的已校準值，無通用預設。
- model／output 預設 checkout 的兩個既有目錄；無 checkout 時兩者都要明確給出。相對的明確參數從呼叫 CWD 解析，預設值則從 checkout 解析，輸出顯示最終絕對值。
- model 必須有可信的合約 receipt、完整必要檔與符合的實際 runtime；不自動連網。先鎖模型、再鎖 output，任一 busy 明確失敗。
- 原文 hash／vectors 遵 data-model，切段／ID／locator 遵 [source-window-v1](source-window-v1.md)。reference query 固定非敏感文字，不送服務；索引只含本次單一文件。
- producer 公開寫入／close／退出；verifier 全量／副本不變性成功才發布。不能以 metadata snapshot_complete=true 跳過驗證。
- 不修改既有 v1 包 schema、讀取端拒絕條件或來源文件；不自動設定／啟動 App、不執行文件內連結與指令。

## Common lifecycle and result

標準輸出是繁體中文 CLI 結果，可顯示使用者指定路徑、revision、段落數與既有兩個環境設定值。這些只是設定建議，不寫 .env。診斷日誌只含固定碼／安全類別／非內容摘要，不含文件全文、向量或 token。

| Exit | 結果／固定碼範例 |
|---|---|
| 0 | completed／already_ready；help 也為 0 |
| 2 | invalid_arguments／invalid_document／invalid_distance |
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

- Request：typed operation（模型驗證／producer／fresh verifier）、已驗證 source／model／stage／副本路徑，以及 revision、文件 ID／title／versions／max_distance／policy 等 scalar metadata；不傳全文、chunks、向量、model／tokenizer 或 pickle。
- Result：固定狀態／錯誤碼、來源與檔案 digests、count、安全驗證結果；不傳 reference embedding、文件段落或 collection。所有 receipt／manifest／collection 由 worker 寫入本次 candidate 檔案，父程序只核對摘要與路徑並發布。
- 所有模型／tokenizer 載入與 inference 均在 worker。producer 唯一負責初次來源 bytes 讀取、hash、解碼、切段、locator 與文件向量。純切段函式可位於輕量 build 模組，接受 typed tokenizer 介面，不 import inference stack 或自行建立 tokenizer。
- 模型驗證 worker 與 fresh verifier 仍各自獨立載入／編碼。fresh verifier 發布前串流核對來源 hash 與初始身分／stat，變更即拒絕；不重新 decode／tokenize，也不宣稱禁止外部寫入。

producer 與 verifier 必須是不同程序；工作完成後 public close 並正常退出，父程序確認退出才接續。中斷時先終止工作程序、確認資源已釋放再清理；無法確認則保留操作狀態，不刪檔、不發布。
