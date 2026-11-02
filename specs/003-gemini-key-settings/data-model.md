# Data Model: Gemini 憑證設定

## Persisted credential metadata（非秘密）

獨立 `gemini-credential.json`，version=1；嚴格解析，不能將壞檔當成空設定。

| 欄位 | 型別／規則 |
|---|---|
| version | 固定整數 1；未知版本阻擋 managed 使用 |
| revision | 單調非負整數；同實例 lifetime lock 及提交鎖保護 |
| state | active、preparing、clearing、cleared；清除失敗保留 clearing |
| active_revision | opaque 隨機槽 ID 或 null；不是 key hash |
| pending_revision | 尚未提交槽 ID 或 null |
| retired_revisions | 待刪除槽 ID 集合；包含已提交更新的舊槽 |
| manual_reconnect_required | bool；clear／受影響失敗後跨重啟保留，不以 env 存在解除 |

namespace 由 App scope 路徑決定；各 OS 帳號的 vault 提供使用者邊界。
metadata 不存 key、片段、key hash、provider response、原始路徑或錯誤文字。
不存在的 journal 代表從未建立 managed 來源；已知 active 槽讀不到是錯誤，兩者不可混淆。

## Protected credential entry

service = App 固定前綴 + scope digest + 隨機槽 ID；account = 固定 `gemini`。
secret = 完整候選金鑰，只有 OS vault 與短暫行程記憶可持有。
一個 active，可有尚未提交／清理中的槽；不提供歷史查詢或 UI reveal。
更新、清除、重啟均要處理所有 journal 已知槽；不得刪除其他 App/實例的憑證。

## Runtime operation

operation_id（opaque）、revision、expected_revision、model/voice 快照、provider/session generation、
phase（validating/saving/clearing/done/failed/superseded）、安全 reason。
候選值只在驗證及保存所需記憶體生命週期存在，不進 repr、例外、序列化或事件。
瀏覽器提交後立即清空輸入，後端放棄後釋放引用；不承諾 Python/JS 的記憶體安全抹除。

## Credential source

獨立環境 snapshot 與 managed resolver。優先順序：

1. journal 有 active → 讀此槽；錯誤時 source=blocked，不嘗試 env。
2. journal 為 preparing → 只使用原 active；pending 不自動升級。
3. clearing／損壞／無法讀取／其他管理行程持鎖 → blocked。
4. 沒有 managed 或已完成 cleared → environment（若有），否則 none。

環境 snapshot 保留既有 dotenv／啟動環境載入規則；不另改兩者內部優先順序。
一般 refresh 只能更新環境來源，不能讓候選或 managed 值被寫回 os.environ/.env。

## Public status（全為非秘密）

configured: bool；managed_presence: absent/present/unknown；environment_available: bool；
source: settings/environment/none/blocked；storage: available/locked/unavailable/error/busy；
validation: unverified/validating/validated/failed；apply: idle/saving/applied/clearing/failed；
connection: 沿用既有連線狀態；manual_reconnect_required、revision、operation_id、安全 reason。

`validated` 綁定當次 revision/model/voice，重啟後顯示「已保存、尚未重新驗證」，不得宣稱仍連線。
既有 `gemini_key_configured` 保留為當下可解析生效金鑰的 bool，不代表已驗證或連線。

## State transitions and recovery

| 意圖 | 保存／提交 | 對話與復原 |
|---|---|---|
| 草稿／取消／空白提交 | 不寫任何來源；空白報 invalid_input | 不改連線；取消清空欄位 |
| 驗證並套用 | 前置來源/鎖檢查；驗證 → journal 記 pending → 新 vault 槽 write/readback → 原子 active commit | active Gemini 先停止；成功且仍選 Gemini 才 fresh session；HF 不動 |
| 驗證／write/readback／commit 失敗 | 舊 active 保留；pending 只清理不升級 | Gemini 若已停止則待手動重連；顯示真實結果 |
| 成功提交後刪舊槽失敗 | 新 active 有效，保留 retired ID，顯示 cleanup_pending | 不回滾已提交值；下次清理／clear 需包含舊槽 |
| 確認清除 | 立即 gate/fence；journal clearing → 刪所有已知槽並確認缺失 → cleared commit | 停止 Gemini；成功才允許 env 成為來源，仍等待明確重連 |
| clear 刪除或 metadata 失敗 | 保留 blocking clearing/error；不得聲稱已刪 | 不重連、不 fallback；可明確重試清除 |
| crash/restart | pending 不升級；清理未提交槽；clearing 保持阻擋至明確重試 | 不自動播放、重播工具或取消 manual gate |
| 後到結果／其他分頁舊 revision | superseded/conflict；不得 commit 或發布覆蓋新狀態 | 不得重啟任何 session |

進入提交區前以 revision 再檢查；OS call 完成後不能只依 task cancellation 判斷。
若新 clear 在 write 中到達，先 gate/fence，待短儲存區結束後清理該已知槽，舊 operation 不得發布或重啟。
原子 replace 例外後重讀 journal 確認提交結果；無法確認則 source blocked/result_unknown，不能宣稱保留或成功。
metadata 無法寫入 clear 意圖時，本行程仍停止且回報未完成；不能保證下次啟動記得該次失敗意圖，須明示重試。
