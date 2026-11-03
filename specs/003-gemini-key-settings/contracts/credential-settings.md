# Contract: 同頁 Gemini 憑證設定

## Browser eligibility and transport

金鑰控制位於既有一般設定頁 Gemini 區，不新增頁面、popup、iframe 表單或跨裝置秘密入口。一般設定頁及 RPC 保留原本內嵌／遠端操作；安全狀態可由既有 RPC 顯示，token／候選只走專用 HTTP。

controller 在允許前不建立輸入或 mutation 控制、不 bootstrap token：

- 自身必須為直接本機 HTTP、hostname 精確 localhost／127.0.0.1／[::1]、pathname 精確 / 或 /static/index.html；伺服器另驗精確 Host／port。query、embedded、UA 與 referrer 不作授權。
- 頂層必須 `window.top === window`。內嵌時必須可讀 `location.ancestorOrigins`，非空，且完整每項精確符合 `{location.origin, "http://tauri.localhost"}`。後者針對已研究的 Windows 0.9.32 release，不包含其他 scheme、suffix、任意 port 或 dev origin。
- 未知／空／null／能力缺失／讀取錯誤／內嵌時空鏈一律只讀。不能只看直接 parent；不能接受 postMessage、RPC、parent 布林或自報 header 代替原生瀏覽器鏈。
- 掛載、bootstrap、每次 mutation 前檢查；bootstrap 成功才建立可輸入控制。判定失敗清除既有 draft／token 並卸載秘密控制，不送後續 mutation；已在 server 執行的操作須重新查安全結果。

這是依賴瀏覽器 SOP 與原生 Location 資料的 UI 反 clickjacking 邊界，不是伺服器證明祖先或程式簽章。Tauri origin 不是 Reachy 獨有身分；同源 XSS、同 OS 帳號惡意程式仍屬原有信任邊界外。

所有 API 驗實際 loopback peer、精確 Host/port（localhost／127.0.0.1／[::1]），拒絕任意 Forwarded/X-Forwarded-*，不把代理 peer 當遠端授權。無法區分轉送的部署不得暴露秘密入口。不開 CORS；回應 no-store，不以 UI 宣稱的祖先 header 作認證。

| Method / path | Request | Response |
|---|---|---|
| GET /api/gemini-credential | 同源 fetch、X-Credential-Request: 1、Sec-Fetch-Site: same-origin；有 Origin 時亦同源 | 安全狀態及僅供 controller 記憶體的 CSRF token |
| POST /api/gemini-credential | JSON candidate、expected_revision；精確 Origin 同源、Sec-Fetch-Site same-origin、X-Credential-CSRF | 安全 operation/status，不含候選 |
| DELETE /api/gemini-credential | JSON expected_revision、confirm=true；同上 CSRF/Origin/Fetch Metadata | 刪除結果及安全狀態 |
| GET /settings/gemini-key | 舊路由 | 404；不提供另一輸入頁、不 redirect、不保留 static alias |

CSRF 有效期 600 秒，只留 controller 記憶體，重啟失效；不進 URL、cookie、browser storage、RPC 或父頁。過期後重新 bootstrap，mutation 不自動重送。一般 RPC 不得取得 token，backend.config 繼續拒絕 key 欄位。
request body 上限 16 KiB，只接受宣告欄位、字串 candidate 及合法 revision；trim 空白拒絕、不以 prefix／長度宣稱服務有效。缺少必要瀏覽器能力不降級授權。
框架 validation error 禁止包含 input／原始 body／exception repr；不記錄 request body、headers、CSRF、秘密片段或上游錯誤文字，access log 僅 method/path/status。

## Safe response

回應包含 [data-model.md](../data-model.md) 的 Public status，operation_id 及固定 reason/message。
query/status/error 不返回 key、mask suffix、長度或 fingerprint；日誌使用安全 reason 與非秘密 operation ID。
POST 為 bounded request，UI 提交後清空 draft；期間可輪詢安全狀態。
瀏覽器中斷不代表伺服器已取消；重新查詢才得知實際結果，禁止自動重送秘密操作。

| HTTP | reason | 意義與下一步 |
|---|---|---|
| 200 | applied / cleared / cleanup_pending | 已提交結果；cleanup_pending 需處理舊槽清理 |
| 400 | invalid_input | 修正輸入；空白不等於清除 |
| 403 | local_access_required / request_not_allowed | 使用 App 直接本機入口／重新開啟頁面 |
| 409 | revision_conflict / superseded / storage_busy | 重新查詢；不自動重送、不重啟 session |
| 422 | authentication_failed / model_not_available | 驗證未通過，原設定未取代；不回傳上游 body |
| 429 | quota_exceeded | 檢查資格／額度，原設定保留 |
| 503 / 504 | service_unavailable / validation_timeout | 網路或服務問題，不等於無效金鑰 |
| 503 | storage_unavailable / storage_locked / storage_failed / result_unknown | 保存／刪除未完成或結果不明；顯示實際 source 與 connection |

停止／退役 Gemini 失敗則不開始候選驗證或保存；回報安全 session_stop_failed，原設定不變。
清除仍以安全停用為優先，不能因雲端關閉逾時讓舊 owner 繼續產生音訊／工具。

## UI behavior

- 同頁 Gemini 區直接提供 password、label、autocomplete=off、spellcheck=false、繁體中文狀態、「驗證並套用」、取消、清除確認與必要的手動重連。保留既有 aria-live、焦點及 Tab/Enter/Esc 操作，不提供既存值 reveal。
- 金鑰區與一般設定 form 分開提交；HF active 亦可管理 Gemini，不改 provider。從已開啟區段起，提交一次；清除加確認兩次，不計輸入及等待。
- 來源、保存、驗證、套用、連線分開顯示。active Gemini 提交前提示中斷／fresh session／失敗後手動恢復；clear 提醒 env fallback 及不等於供應商撤銷。
- draft 不回填，提交、取消、清除、切頁、卸載及 pagehide 清空。卸載釋放 CSRF、輪詢與監聽；pageshow／返回重新判定及 bootstrap，不重送候選。
- 本地掛載 generation 與 server owner_epoch／revision 防舊回覆污染新控制；pending 禁止重複套用但允許 clear 退休舊操作。取消前端等待不宣稱 server 已取消。
- 遠端、relay、未知／不支援 frame 只顯示安全狀態與限制原因，無輸入 DOM、token fetch 或秘密 mutation；一般設定繼續可用。
- 刪除失敗不宣稱已移除；保留 result_unknown、cleanup_pending、revision_conflict 等既有錯誤及恢復方式。

## Session invariants

所有 mutation 不改 HF 預設、不自動換 provider。active HF session、音訊與工具不重啟。
active Gemini 操作經唯一 LocalStream owner fence：退休 session、停止 playback/舊工具結果、清空 resumption。
成功套用且 provider/model 仍符合快照才 fresh session；其他失敗／clear 都不自行重連。
重新連線由現有 backend.retry 或使用者明確重新選 Gemini 觸發；profile/voice/language/tool permissions 不變。
clear gate 跨重啟保留；獨立驗證不得初始化 robot、audio、camera、memory 或工具。
