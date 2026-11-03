# Research: 設定頁 Gemini 憑證

## 2026-11-03 同頁修訂研究

**Decision**: 遵循使用者新要求，在原 Gemini 設定區管理金鑰，不依賴 popup；保留專用 HTTP 與既有儲存／交易，不走一般 RPC 或 relay。下方原第 3 節的獨立頁選擇為已被取代的基線。

**Rationale**: 使用者實測 Control App 的另開連結無反應。一般設定頁允許內嵌，將秘密欄位移入後不能直接沿用獨立頁全面禁止 frame 的邊界；Origin／Fetch Metadata 描述 API 請求來源，不單獨證明外層嵌入者可信。

**Evidence**: 本機 `settings.js` 的 localCredentialPage 只看自身 hostname/path；`console.py` 已有 loopback/Host/Origin/Fetch Metadata/CSRF 檢查；SDK JsonRpcServer handler 僅有 params，沒有 request peer／Origin context。這些證據不足以放行未知原生 frame。參考 [Fetch Metadata 規格](https://www.w3.org/TR/fetch-metadata/) 與 [Chrome origin 驗證指引](https://developer.chrome.com/docs/modern-web-guidance/guides/security/validate-origins)；不得以 `null` 字串辨識可信來源。

**Alternatives considered**: 外開頁面及複製網址未符合最新同頁要求；全面允許 frame／經一般 RPC 傳密會擴大邊界；改 SDK 內部或另建登入服務超出本功能範圍。

**Open gate**: 尚未取得原生 Control App 祖先來源／WebView 能力證據，也尚未決定可驗證的放行機制。未知、opaque/null、缺失或不支援的內嵌來源只讀；安全契約定案前不實作內嵌秘密管理，不宣稱研究全部完成。

日期：2026-11-02。只讀研究；未讀取實際金鑰、存取 OS 憑證庫、安裝套件或呼叫 Gemini。

## 1. 受保護儲存

**Decision**: 新增 `keyring>=25.7,<26`，明確建立 Windows `WinVaultKeyring`（`persist = "local machine"`）、
macOS `Keyring` 或 Linux `SecretService.Keyring`。不用自動 backend discovery，不接受 chainer、null、fail、
`keyrings.alt` 或自訂檔案 backend。實作時由 uv 固定版本及平台依賴。

**Rationale**: 跨平台 API 可重用，Windows 本機持久化避免預設 enterprise 漫遊。
Linux 需可用的使用者 D-Bus／Secret Service／可解鎖 collection；不自動安裝服務、建立無密碼 vault 或收集解鎖密碼。
不可用時拒絕 UI 保存，env-only 照常使用。OS 同帳號隔離並非防同帳號其他程式存取的保證。

**Alternatives considered**: 明文 settings/.env 違反保存選擇；自行加密檔案增加主密鑰管理；
逐 OS 手寫秘密 API 重複工作；任意自動 backend 無法保證保護等級；新增 KWallet 支援延後。

官方來源（本日查閱）：[keyring 設定與安全限制](https://keyring.readthedocs.io/en/stable/)、
[Windows backend](https://github.com/jaraco/keyring/blob/main/keyring/backends/Windows.py)、
[Microsoft Credential persistence](https://learn.microsoft.com/en-us/windows/win32/api/wincred/ns-wincred-credentialw)、
[headless Linux](https://keyring.readthedocs.io/en/stable/#using-keyring-on-headless-linux-systems)。

## 2. 實例、來源與提交

**Decision**: SDK 傳入的 instance_path 作 scope；CLI 未傳路徑時，憑證專用 scope 採既有
`REACHY_MINI_INSTANCE_PATH` 或 platformdirs 的 `reachy_mini/conversation_app` 路徑。
此解析不觸發 legacy .env 搬移，也不改變一般設定的 CLI 持久化行為。
正規化絕對路徑（Windows 大小寫正規化）雜湊作 namespace；vault label 不放原始路徑或金鑰片段。
CLI 多實例沿用既有 instance path override。scope 不可寫或無法確認時，拒絕 managed 操作而不借用其他實例。

以獨立、嚴格解析的非秘密 journal 保存 revision、active/pending/retired 槽及 clear gate。
候選值先驗證，寫新槽並讀回確認，最後原子 replace active 指標；舊槽在提交後清理。
中途失敗不升級 pending。清除以持久化 clearing 意圖開始，所有已知槽確認刪除後才提交 cleared。
損壞、已知槽缺失、locked、寫入或刪除結果不明均 fail closed，不假裝沒有 managed 來源。
來源判斷先檢查 blocked/clearing，即使舊 active ID 還在也不讀取；preparing 無舊 managed 時保留原環境 snapshot/none，不能把已知槽讀取失敗當作 null。環境 key 保留獨立快照，refresh 不覆寫 managed 選擇，候選值永不寫入 global config。

**Rationale**: vault API 與檔案系統沒有共同交易；直接覆寫會破壞「失敗保留原設定」。
一般 settings_store 的錯誤 fallback 不適用秘密來源。versioned 槽須追蹤清理，不能留下不可見歷史。

**Alternatives considered**: 只用 threading.Lock 不足跨行程；直接存入 AppSettings 會混淆缺失與讀取錯誤。

同 scope 僅一行程取得憑證子系統 lifetime OS file lock：Windows 用 stdlib msvcrt、Linux/macOS 用 fcntl，
頂層依平台匯入、無新 lock 套件。第二行程不管理或使用 managed 憑證，不可改走環境掩蓋已知 managed 狀態；
HF 仍可用。程序退出釋放鎖，鎖檔存在本身不算鎖定。鎖不可用同樣 fail closed。

## 3. 設定頁 transport 與操作人員邊界

**Decision**: 在既有 settings_app 加專用 HTTP 路由；秘密不走 `/rpc` 或 SDK relay。
實際 socket peer 必須 loopback、Host 必須精確本機允許值且符合綁定 port；不信任轉送標頭。
Origin、Fetch Metadata、JSON 與記憶體 CSRF token 規則見契約。所有 credential routes 禁止跨源 CORS。

**Rationale**: 本機已安裝 SDK JsonRpcServer 的 handler 只有 params，沒有 Request/peer context；
普通設定頁可從 LAN/relay 存取，不代表已通過憑證管理授權。不能把公開 nonce 當遠端登入認證。
此界線授權同一電腦的本機使用者，不新增帳號或遠端秘密傳輸。

**Alternatives considered**: 通用 RPC mutation 缺來源保證；新增第二個服務或登入系統超出範圍。
本輪使用者選 A：一般設定頁在 Control App iframe／既有遠端入口維持可用，只顯示安全狀態與本機頁面入口。
輸入一律另開 GET /settings/gemini-key 頂層頁，拒絕所有 frame，不對一般頁施加此限制；同一 settings_app，不新增服務。
遠端 robot/relay-only 提示須在 App 所在電腦開啟，不得誤導使用者把筆電 localhost 當遠端 robot localhost。
保留一般頁並將受保護 HTML 放非公開 templates/，避免 static alias 繞過頁面存取／frame 保護。

本機證據：`console.py` 的 `_init_settings_ui_if_needed`、`backend.config` allowlist；
安裝 SDK `reachy_mini/apps/jsonrpc_server.py` 的公開 handler/mount；不修改 SDK。

## 4. 候選驗證

**Decision**: 在 Gemini 模組新增有型別的獨立 async 驗證入口。直接使用候選值、目前 model/voice 的快照，
沿用 Live URL、`x-goog-api-key` header、setup/close deadline 及安全錯誤分類。
僅傳 model 與 AUDIO/speechConfig 所需欄位，等待有效 `setupComplete` 後立即關閉。
不送 user turn，不啟用 resumption，不載入人格、記憶、逐字稿、tools、VAD 或 robot/audio 裝置。

**Rationale**: 正常 `start_up()` 會加入上述內容並播放問候，不適合資格檢查。
setupComplete 只能證明當下設定可建立，不能保證後續額度與可用性。
服務錯誤分 auth、eligibility/model、quota、network/service；不把逾時當無效 key。
不傳原始 exception/remote error；websockets debug/request header 日誌必須保持關閉。

**Alternatives considered**: 正規表示式不能驗證資格；新增 Google SDK 不必要；借用完整 handler 會傳送非必要內容。

官方來源：[Gemini Live WebSocket protocol](https://ai.google.dev/api/live)（本日查閱）；
現有 `gemini_realtime.py: start_up` 使用同一 protocol/header。

## 5. 生命週期及競態

**Decision**: LocalStream 繼續唯一持有重試與 handler。新增 Gemini manual-reconnect gate，
以 operation revision 及既有 session generation 防止遲到驗證、舊音訊／工具結果或保存完成後誤重啟。
對 active Gemini 的套用前提示會中斷：先 gate、fence、停止，再驗證，避免並行 Live sessions。
失敗保留原設定但維持停止，手動重連；成功保存且仍選 Gemini 才建立新 session、不帶舊 resumption。
active HF 完全不 restart、不 flush 動作，也不修改 session。

**Rationale**: 現有 startup loop 在 key 存在時自動恢復；clear 後若有 env，單純 shutdown 不會保持停止。
新 clear 立即退休舊 operation，短提交區段序列化；不能以取消 to_thread 宣稱 OS 寫入已取消。
保存前、發布與重啟前均檢查 revision 和 model/provider 快照。provider/model 變更退休未提交驗證。

**Alternatives considered**: 第二個 retry owner 會產生雙連線；失敗自動改用舊 key/env 違反明確套用語意。
所有技術未知已解決；實際 OS／服務能力是後續驗收事項，不能由本次研究推定通過。
