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
- 原文 hash／切段／locator／vectors 遵 data-model。reference query 固定非敏感文字，不送服務；索引只含本次單一文件。
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
| 8 | recovery_required／cleanup_incomplete；須明示是否已發布 |
| 130 | cancelled；若留下需恢復的發布階段須一併明示 |

--help 在未裝 rag 或未提供素材時仍可閱讀。只有實際重型操作才需要 rag；缺套件明確說明安裝既有 extra，不自行安裝。

目的地 lock 已存在就拒絕，不自動根據時間／PID 破鎖。預設 siblings 的 stage／backup／lock 只屬本次操作，需窄範圍 Git 忽略；自訂輸出在 repo 內但未忽略時拒絕並請使用者改位置或自行管理忽略，不修改 Git 設定。

替換前先由使用者停止 App。普通失敗 rollback，硬中斷留操作記錄、可核對舊版及恢復指引。沒有自動 recovery 入口；人工先確認無準備程序，核對記錄及 stage／backup hashes，恢復完整目的地後才清理自有殘留。不能只刪 lock／舊目錄，也不停止其他應用程式。

## Internal worker boundary

document_prepare_worker 是兩 CLI 的內部本機子程序，不是第三個使用者腳本。以私有管道傳入 typed operation／已驗證本機路徑及 metadata，結果只含固定狀態／摘要；不開 socket、不載 dotenv、不啟動 SDK。分工為模型驗證、producer、fresh verifier；父程序持有發布鎖，子程序不得移動正式目的地。

producer 與 verifier 必須是不同程序；工作完成後 public close 並正常退出，父程序確認退出才接續。中斷時先終止工作程序、確認資源已釋放再清理；無法確認則保留操作狀態，不刪檔、不發布。
