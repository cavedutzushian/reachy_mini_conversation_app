# Research: 設定頁 Gemini 憑證

## 2026-11-03 同頁修訂研究（設計已決定）

**Decision**: 原 Gemini 設定區直接管理金鑰；以瀏覽器完整祖先來源鏈限制 controller，保留專用 HTTP 與既有儲存／交易，不依賴 popup，不經 RPC／relay 傳密。不新增依賴或 SDK patch。

**Native evidence**: 本機執行檔 ProductVersion／FileVersion 為 0.9.32。官方 v0.9.32 對應 commit `d6d97cd5d6514d222764088d8f85f29ade3a5c10`：

- [EmbeddedAppView.tsx](https://github.com/pollen-robotics/reachy-mini-desktop-app/blob/d6d97cd5d6514d222764088d8f85f29ade3a5c10/src/views/active-robot/right-panel/EmbeddedAppView.tsx#L278) 的 iframe 無 sandbox／referrerPolicy；URL 中 embedded、主題與時間參數只作顯示，不是授權。
- [tauri.conf.json](https://github.com/pollen-robotics/reachy-mini-desktop-app/blob/d6d97cd5d6514d222764088d8f85f29ade3a5c10/src-tauri/tauri.conf.json) 與 [Windows overlay](https://github.com/pollen-robotics/reachy-mini-desktop-app/blob/d6d97cd5d6514d222764088d8f85f29ade3a5c10/src-tauri/tauri.windows.conf.json) 未覆寫正式主視窗來源或 useHttpsScheme；依 [Tauri 配置](https://v2.tauri.app/reference/config/#usehttpsscheme) 推論 Windows 正式版來源為 `http://tauri.localhost`。這不是原生 runtime 觀察，也不是 Reachy 獨有程序身分；devUrl 不加入 allowlist。
- [daemon.ts](https://github.com/pollen-robotics/reachy-mini-desktop-app/blob/d6d97cd5d6514d222764088d8f85f29ade3a5c10/src/config/daemon.ts#L414) 區分本機與遠端連線，因此即使外殼可信，設定頁自身也須為直接 loopback。

**Browser boundary**: [WHATWG ancestor origins](https://html.spec.whatwg.org/multipage/dom.html#ancestor-origins) 與 [getter](https://html.spec.whatwg.org/multipage/nav-history-apis.html#dom-location-ancestororigins) 定義瀏覽器提供的完整鏈；被隱藏／opaque 的來源可序列化為 null，必須拒絕。以 top===window 判頂層；內嵌時 ancestorOrigins 必須可用、非空且每項精確屬於 `{location.origin, "http://tauri.localhost"}`。不信任自身 hostname、parent 宣稱、query、referrer、UA 或任意 loopback origin；讀取失敗、API 缺失或未知值一律只讀。

**Server boundary**: [Fetch Metadata](https://w3c.github.io/webappsec-fetch-metadata/#sec-fetch-site-header) 描述請求發起者與目標，不是祖先認證。既有 loopback／Host／Origin／Fetch Metadata／CSRF 全部保留。此方案以 SOP 與可信 App 腳本的 UI 檢查防 clickjacking，不新增偽 server 祖先認證 header；同源 XSS、同帳號惡意程式及其他可用相同 Tauri origin 的本機程式不在原有防護承諾內。

**Research spike**: 隔離 Chrome、短暫 loopback 假頁及無秘密資料，`cache/003-gemini-key-settings/ancestor_research.mjs` 五例通過：頂層、可信 parent 可通過；惡意 parent、可信 parent 外的惡意 grandparent、鏈中 null 均拒絕。兩層惡意鏈實際有兩項，opaque 案實際含 null。未使用 Control App 或產品 API，也未連雲端／robot；只證明候選瀏覽器機制，未宣稱正式 controller 或原生 WebView 已通過。

**Alternatives considered**: 外開／複製網址不符合最新需求；只查 parent 不能阻擋惡意 grandparent；全放 frame、把嵌入查詢參數或 RPC 當認證會擴大邊界；對整頁加 frame-ancestors none 破壞既有一般內嵌功能。

**Outcome**: 授權設計未知已解決，可拆解任務。實作須在原生 0.9.32 WebView 複驗完整鏈、能力與 API headers；不符時保持只讀，不靠服務端沒有祖先 header 或平台 UA 改為放行。查閱日 2026-11-03。

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

**Decision**: 同頁 controller 使用既有 settings_app 的專用 HTTP，不走 SDK RPC／relay。來源判定採上方新研究的 browser UI eligibility，API 保留實際 socket／Host／同源及 CSRF 檢查；無寬鬆 CORS 或公開 nonce 認證。

**Rationale**: SDK JsonRpcServer handler 只有 params，沒有 Request/peer context。一般設定可以內嵌或從遠端使用，不代表金鑰管理有權限；只對金鑰控制作來源限制，保留一般頁功能。

**Alternatives considered**: 原獨立頁被使用者同頁要求取代。無新登入系統或第二服務；移除舊秘密入口後，GET /settings/gemini-key 為 404，不 redirect 或留下 static alias。

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
