# Implementation Plan: 設定頁管理 Gemini API key

**Branch**: `feat/003-gemini-key-settings` | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

## Summary

在原設定頁 Gemini 區直接提供遮蔽欄位、驗證並套用、取消、確認清除與安全狀態，不另開頁面。金鑰操作不隨一般設定儲存，不回填已存金鑰。
沿用已實作的專用 HTTP、受保護憑證庫、來源 resolver、revision 與唯一 session owner；HF 維持預設，更新／清除的對話政策不變。

## Technical Context

**Language/Version**: Python 3.12、既有 JavaScript ES modules／HTML／CSS。
**Dependencies**: 沿用 Reachy Mini SDK 公開 API、FastAPI、websockets、platformdirs、已鎖定的 keyring 25.7.0；本修訂無新依賴、環境變數、登入服務或 SDK 修改。
**Storage**: 既有 OS vault 與非秘密 journal 不變；無憑證搬移、schema 升級或明文 fallback，保留 .env 相容來源。
**Target Platform**: 本機瀏覽器及具備所需能力的 Windows Control App 內嵌。其他平台保留相同直接本機設定頁及環境來源；不能驗證的 frame 只讀，不以 UA 或平台名稱放行。macOS／Linux 剩餘實測依使用者決定豁免。
**Testing**: 現有 pytest 故障／來源／對話矩陣；隔離瀏覽器測試 UI 及祖先鏈，原生 Control App 驗收獨立追蹤。不新增前端測試框架。
**Performance/Scope**: 每次掛載一份 controller 與輪詢，不中斷 HF；既有候選驗證時限及 Gemini fresh session／manual reconnect 政策不變。

## Phase 0 — Evidence and authority decision

研究詳見 [research.md](research.md)。本機執行檔版本 0.9.32；官方對應 commit 的 iframe 與 Tauri 設定支持 Windows release 父層預期來源 `http://tauri.localhost`。這是源碼推論，不是本機 WebView 執行結果。

**設計閘門：通過，可進入差異任務拆解。** 採瀏覽器提供的完整祖先來源鏈作 UI 反 clickjacking 邊界，配合既有 HTTP 防護；不聲稱伺服器驗證祖先或辨識具名／簽章程序。實際 WebView 的值及能力屬實作驗收條件；不符時有確定的只讀行為，不是待決的授權方案。

### UI eligibility

1. 預設只顯示非秘密狀態；不建立 password／mutation 控制，不取得管理 token。
2. 自身必須是直接本機 HTTP 設定頁：hostname 精確為 localhost、127.0.0.1 或 [::1]，pathname 精確為 / 或 /static/index.html。API 的精確 Host／port 檢查仍是必要條件。embedded、theme、referrer、UA、查詢參數均不是授權。
3. `window.top === window` 才視為頂層。若內嵌，讀取瀏覽器原生 `location.ancestorOrigins`，要求可用、非空，且每一項完整序列化 origin 精確屬於 `{location.origin, "http://tauri.localhost"}`；不做 hostname、suffix、正規表示式或任意 loopback port 放行。
4. 任一 null、空值、未知來源、讀取錯誤、能力缺失或內嵌時空列表均只讀。完整鏈避免可信直接 parent 外還有惡意 grandparent；被 referrer policy 遮蔽的來源也拒絕。不增加 devUrl localhost:1420、https 變體或 tauri:// 變體，未來需有證據及獨立測試才擴充。
5. 掛載、bootstrap、每次 mutation 前重新判定。eligibility 通過且專用 API bootstrap 成功才建立可輸入控制；bootstrap 失敗不保留欄位或 token。不得使用 postMessage／RPC／父頁宣稱的布林或 X-Ancestor-Trusted header 替代判斷。

`http://tauri.localhost` 為 Tauri 容器來源，非 Reachy 專屬程序身分。本方案依賴瀏覽器 SOP／原生來源資料；與既有邊界一致，不承諾防同源 XSS、同 OS 帳號惡意程式、擴充套件或 dump。一般頁維持原內嵌／遠端操作，只有金鑰 controller 受上述條件限制，不對整頁新增全面 frame 禁止。

### Server authority

專用 API 繼續要求實際 loopback peer、精確 Host/port、拒絕 Forwarded/X-Forwarded-*、同源 Origin／Fetch Metadata、JSON、記憶體 CSRF、16 KiB 及 no-store。無 CORS、SDK RPC 或 relay 秘密入口。UI eligibility 是可信 App 程式的瀏覽器防線，不是新 server 認證；不送祖先宣稱作授權。無法區分的轉送部署不得暴露秘密路由。

## Phase 1 — Controller and delivery design

### Files and ownership

- `static/js/views/settings.js`：原 Gemini 區掛載安全狀態與 controller，移除外開按鈕，不將 key 加入一般設定表單。
- `static/js/gemini-key.js`：由 document 全域初始化改為有生命週期的掛載函式，持有 draft、CSRF、operation 顯示、監聽及輪詢；沿用既有錯誤訊息與確認對話框。
- `static/js/api.js`：沿用專用 HTTP transport；必要時接收 AbortSignal，取消前端等待不表示後端操作已取消，也不自動重送。
- `console.py`：保留 API 的授權／交易／安全狀態；移除舊獨立頁 handler，舊 GET /settings/gemini-key 回 404，不 redirect、不保留另一輸入介面。一般根頁及 RPC 不新增限制。
- `templates/gemini-key.html`：controller 整合完成及回歸通過後刪除；確認 wheel 不再含舊 template／static alias。新控制重用 style.css 與現有 modal，不新增 UI 框架。
- 根 README、docs/scheme.mmd：同步同頁操作與來源限制，必要時重新產生 SVG，不能手改生成圖。

### Lifecycle and races

掛載時先判定 eligibility，再 bootstrap；成功後顯示同頁控制。每次掛載有本地 generation，忽略上一掛載的遲到回覆；仍沿用 server owner_epoch／revision 的新舊判定。
提交、取消、清除、切換設定子頁、卸載及 pagehide 清空 draft；卸載移除監聽、停止輪詢、釋放 CSRF 與候選引用。pageshow（包含 BFCache）重新判定與 bootstrap，不恢復草稿或重送。短暫 UI 取消／離開不取消伺服器已開始的驗證或保存，返回時只重新查狀態。
一般設定儲存不提交金鑰；按一次驗證並套用才變更候選，清除加確認兩步；明確 retry 仍沿用既有對話 API。eligibility 在操作前不再通過時立即卸載秘密控制、清 token，不送 mutation。

### Backend invariants

既有受保護保存／來源優先／清理與結果不明政策全部保留。HF 不重啟；active Gemini 更新成功為 fresh session，失敗保留原設定並如實顯示連線，clear 後等待手動恢復。單獨驗證不送媒體／人格／記憶／工具，key 不進一般設定、RPC、日誌、逐字稿或 browser storage。

## Constitution Check

| 原則 | 設計結果 |
|---|---|
| SDK 相容與既有架構 | 通過：不修改 SDK、共享 realtime 留原處，重用現有 API／session owner |
| 最小改動、型別與重用 | 通過：整理既有 controller、刪舊頁，無新 framework／secrets 系統 |
| 錯誤與機密邊界 | 通過：保留固定安全錯誤，未知來源只讀，無祖先宣稱型認證 |
| 必要驗證 | 通過：quickstart 已列離線、攻擊與原生驗收；設計通過不等於產品實測通過 |
| Python／跨平台／依賴 | 通過：Python 3.12、無新依賴，能力缺失有只讀行為，非 Windows 可用直接本機設定頁 |
| 文件與人工審查 | 通過：同步根文件／架構來源；不改 CI／CONTRIBUTING／PR template，不自動開 PR |

## Validation and handoff

[contracts/credential-settings.md](contracts/credential-settings.md) 為現行同頁契約；[data-model.md](data-model.md) 定義 runtime eligibility／生命週期與既有交易。[quickstart.md](quickstart.md) 定義驗收與歷史證據。
Phase 0 的五項 Chrome 來源鏈研究測試通過；原生 Control App、正式 controller 與舊頁移除尚未實作／驗收。本輪不讀 key、不啟動對話、不重跑產品 gate。
下一步 `$speckit-tasks` 產生同頁差異任務，再 `$speckit-analyze`。原 tasks.md 41／44 是獨立頁基線，不可直接沿用為同頁完成狀態；重新規劃的工作須保持未完成，既有平台豁免與歷史證據保留。
