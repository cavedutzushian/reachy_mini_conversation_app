# Contract: 本機 Gemini 憑證設定

## Transport and authority

沿用現有 settings_app，秘密只走以下 HTTP 路由；`backend.config` RPC 仍拒絕任何 key 欄位。
不將秘密放在 URL、RPC events、狀態推播、通用設定或瀏覽器儲存。

所有路由檢查實際 peer 為 loopback、Host 為明確允許的 localhost/127.0.0.1/[::1] 與當前 port。
不用 suffix 比對；拒絕任意 Forwarded/X-Forwarded-*，不以反向代理的 loopback peer 代表遠端授權。
部署如有無法區分的本機代理轉送，該入口不得啟用秘密路由，須使用 App 直接本機 listener。
不開跨源 CORS。管理頁與 bootstrap 回應 `Cache-Control: no-store`、禁止被第三方 frame 嵌入；
只允許已知本機 Control App parent origin（部署可確認時）及 self，不能放寬為任意 parent。
不新增遠端授權。未符合條件的 UI 顯示「請在 App 所在電腦開啟本機設定頁」。

| Method / path | Request | Response |
|---|---|---|
| GET /api/gemini-credential | 同源 fetch，`X-Credential-Request: 1`；Sec-Fetch-Site 必須 same-origin | 安全狀態與短期 CSRF token（只供此頁記憶體使用） |
| POST /api/gemini-credential | JSON：candidate、expected_revision；`X-Credential-CSRF`，精確 Origin 同源、Sec-Fetch-Site same-origin | 驗證／保存完成的安全 operation/status；不含候選值 |
| DELETE /api/gemini-credential | JSON：expected_revision、confirm=true；相同 CSRF/Origin 規則 | 刪除結果及安全狀態 |

缺 Fetch Metadata、CSRF 或 Origin 的寫入拒絕；GET 不要求瀏覽器通常不送的 Origin，若有則必須同源。
無此能力的舊 WebView 顯示不支援，提示以本機瀏覽器使用；不能降級為無驗證路由。
CSRF token 隨行程重啟失效、不可經 RPC/remote bootstrap 取得、不進 localStorage/sessionStorage/cookie/URL。
這是本機使用者邊界與防跨站請求，並非保護已遭入侵的同源程式。

request body 大小上限 16 KiB；僅接受宣告欄位、字串 candidate 及合法 revision。
字串 trim 後空白拒絕，不用 key prefix/長度證明有效；超過 transport 上限報 invalid_input。
須攔截框架 validation error，禁止回應包含 `input`、原始 body 或 exception repr。
不要記錄 payload、CSRF、headers、秘密片段或上游錯誤文字；access log 僅 method/path/status。

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

- 固定繁體中文。password input 有 label、autocomplete=off、spellcheck=false；無顯示舊 key 功能。
- 輸入區不受 Gemini 是否為目前 backend 限制；HF 使用中可管理 Gemini，但不改 provider。
- 顯示來源、已保存/尚未驗證/驗證中/已套用、連線與 storage 狀態，不能合併為單一「成功」。
- active Gemini 按「驗證並套用」前已有可見提示：將停止目前對話，成功後開始新對話；失敗需手動重連。
  提交後不再追加確認，避免不必要操作；清除按鈕另開確認，提醒 env fallback 與非 provider 撤銷。
- 從已開啟 Gemini 區起，輸入後按套用一次；清除按按鈕加確認兩次，符合最多三次明確操作。
- 取消、提交、清除、離開設定頁均清空 draft；重載不回填。pending 時停用重複提交，clear 仍可退休舊操作。
- 錯誤透過 aria-live 安全訊息提示，焦點可回輸入；Tab/Enter/Esc 可操作，中文窄螢幕換行正常。
- clear 成功顯示「設定頁金鑰已移除」及 env 是否仍可用，連線已停止／待手動重連。
  刪除失敗顯示未完成或未確認；不宣稱 provider 上的金鑰已撤銷。

## Session invariants

所有 mutation 不改 HF 預設、不自動換 provider。active HF session、音訊與工具不重啟。
active Gemini 操作經唯一 LocalStream owner fence：退休 session、停止 playback/舊工具結果、清空 resumption。
成功套用且 provider/model 仍符合快照才 fresh session；其他失敗／clear 都不自行重連。
重新連線由現有 backend.retry 或使用者明確重新選 Gemini 觸發；profile/voice/language/tool permissions 不變。
clear gate 跨重啟保留；獨立驗證不得初始化 robot、audio、camera、memory 或工具。
