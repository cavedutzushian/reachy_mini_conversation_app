# Quickstart: 同頁 Gemini 憑證設定驗收

本指南前半為同頁實作後的目標驗收，尚未宣稱產品已完成；後半保留原獨立頁基線證據。採 Python 3.12、假 key、fake vault／假 Gemini endpoint、隔離 scope，不讀日常 .env／憑證、不連 robot／雲端。設計細節見 plan.md 與 contracts/credential-settings.md。

## 1. 研究結果與可重現 spike

本機 Control App 執行檔版本 0.9.32；官方對應源碼與 Tauri 設定支持 Windows release parent 預期 http://tauri.localhost，仍待原生 runtime 驗收。以下研究測試已執行，不代表正式 controller 通過：

```powershell
node cache/003-gemini-key-settings/ancestor_research.mjs
```

此 ignored harness 只啟動短暫 loopback 假頁及獨立 headless Chrome，結束關閉 browser／server；五項 PASS：頂層、可信 parent、惡意 parent、惡意 grandparent、opaque parent。Chrome／Puppeteer 是既有工具 cache，不是新產品依賴，cache 可能不隨 checkout 存在。正式回歸須由實作任務保存可重現測試，不把此研究 harness 當交付測試套件。

## 2. 離線自動驗證（實作後）

```powershell
$env:REACHY_MINI_SKIP_DOTENV = '1'
$env:PYTHONUTF8 = '1'
cache/verify-python312/Scripts/python.exe -m pytest tests/test_gemini_credentials.py tests/test_console.py tests/test_gemini_realtime.py tests/test_settings_store.py -v
```

依 spec.md 測四種來源 × reload／clear／restart、vault 與 journal 故障、更新／清除競態、HF 不動、Gemini fresh session／manual gate。上述既有回歸保留；新 UI 還須檢查：

| 情境 | 同頁預期 |
|---|---|
| 直接本機頂層、可信完整內嵌鏈 | bootstrap 成功才建立空白遮蔽欄位；提交一次、清除加確認兩次，不開新頁 |
| 惡意 parent／grandparent、null／未知來源、嵌入時空鏈、API 缺失／讀取錯誤 | 無 password DOM、token fetch 或秘密 mutation；一般設定與安全狀態可用 |
| no-referrer、opaque sandbox、遠端／relay、非 loopback 自身網址、dev origin | 不以缺失資訊或自報參數放行；若來源被遮蔽為 null 則只讀 |
| 切頁、取消、pagehide、返回／pageshow／BFCache、bootstrap 中離開 | draft／token 清空，監聽與輪詢釋放，新 generation 不受舊回覆污染；不重送候選 |
| 一般設定儲存、RPC／postMessage 自稱可信 | 一般設定不帶 key；無 RPC／parent token 通道；既有 HTTP 拒絕不減少 |
| 舊路由／打包 | GET /settings/gemini-key 404、無 redirect、無 template/static alias；根設定頁仍 200 可內嵌 |

用假 sentinel 擷取六類操作的 log、狀態／錯誤、逐字稿、一般設定、journal、URL 及 browser storage，不得有 key 或片段。fake vault 與必要 request body 記憶體不算洩漏；不匯出含候選的 HAR。

## 3. 同頁畫面與原生 Control App

實作時更新既有 cache/003-gemini-key-settings/settings_trial.py 為同頁 fake fixture，保留 fake 依賴、隔離 scope 及阻擋外連；目前舊 harness 仍是獨立頁基線，不能拿它宣告同頁通過。

```powershell
$env:PYTHONUTF8 = '1'
cache/verify-python312/Scripts/python.exe cache/003-gemini-key-settings/settings_trial.py
```

1. 在 fixture 印出的根設定頁 Gemini 區，只用 offline-first／offline-second／offline-invalid 完成新增、更新、失敗、取消、空白、確認清除、reload；全程不開 popup／另一頁，不回填值。
2. Tab／Enter／Esc、焦點、aria-live、繁體換行與窄視窗正常；一般設定儲存不提交 key。驗證中離開再返回，只查結果、不重送。
3. 模擬可信及惡意全祖先鏈、缺能力與 null；確認拒絕時連 token bootstrap 都不送，不僅是按鈕停用；跨站直接 HTTP mutation 仍遭後端拒絕。
4. 原生 Control App 必須另外取得當輪啟動／實機同意，相機及記憶維持關閉。使用者確認原頁直接出現空白遮蔽欄位、操作不用開窗。檢查實際祖先鏈、Origin／Fetch Metadata 與能力；符合精確 allowlist 才啟用，不符只讀並保留未通過結果。
5. 不靠「版本 0.9.32」或「是 WebView2」放行；未知 Runtime／來源不得放寬設定。Chrome 模擬及源碼推論不等於原生驗收。

## 4. 平台與真實服務範圍

保留已完成 Windows vault 與既有 Linux 不可用證據；使用者已明確豁免 macOS／Linux 剩餘實測，不重新要求或記為通過。原生驗收、真實 key／免費額度、HF/Gemini 語音矩陣仍須另外授權；沒有授權先用假值與無音訊模擬。真實 key 只由使用者在已允許的同頁輸入，不貼聊天或命令列，完成後清理隔離測試槽。
更新／清除／驗證失敗的三種連線狀態矩陣與既有後端政策不變。未做範圍分開記錄，不沿用上一頁型態或前兩個功能的結果宣告通過。

## 5. 完整 gate（實作後）

```text
ruff check . --fix
ruff format .
mypy --pretty --show-error-codes
pytest tests/ -v
uv lock --check --offline
```

更新根 README、必要架構來源與 wheel 檢查；驗收證據區分源碼研究、離線模擬、原生、vault 與 live，不把預期結果當實測。本輪只更新設計，沒有執行產品 gate 或金鑰操作。

## 原獨立頁基線證據（歷史記錄）— 2026-11-03

以下依當時實作與決策保留，包含曾未解決的研究閘門；最新同頁設計以 plan.md、research.md 及本指南前五節為準，不將歷史 UI 成功或研究限制當成現行結論。

T001：分支 feat/003-gemini-key-settings、Python 3.12.12、初始工作目錄乾淨。
Ruff check／format check 通過（119 files），strict mypy 通過（55 source files），uv lock --check --offline 通過（131 packages）。
基線 pytest：726 passed；wheel 建置受 PyPI 沙箱限制，另以公開套件下載權限獨立複驗 1 passed，合計 727 項基線通過。
初次預設 Temp 無權限的結果不計成功；改用 workspace basetemp。未讀 .env／真實 vault，不連 Gemini／robot。

隔離環境命令（PowerShell，環境路徑僅供本儲存庫開發驗證）：

```powershell
$env:REACHY_MINI_SKIP_DOTENV = '1'
$env:PYTHONUTF8 = '1'
$env:UV_CACHE_DIR = Join-Path $PWD 'cache/uv'
cache/verify-python312/Scripts/python.exe -m pytest tests/ -v --basetemp=cache/003-pytest -o cache_dir=cache/003-pytest-cache
```

新憑證測試一律使用 tmp_path／fake vault／fake WebSocket，阻擋未預期外連；缺少當輪明確同意時，OS vault／live／robot 驗收保持待驗。

T004～T010：model／scope lock／OS backend allowlist／journal resolver／本機 request guard／Gemini hold 已加入；隔離整合測試 185 passed，strict mypy 56 source files 通過。原型憑證流程尚未對使用者開放。


### 本輪驗收結果

| 項目 | 2026-11-03 結果 |
|---|---|
| US1／US2 隔離回歸 | 先確認 12 項缺少功能的測試失敗；補實作後通過。clear 另先確認 2 項缺少功能失敗，再補交易。 |
| 故障／來源／對話 owner | 325 項相關整合測試通過；涵蓋四種來源、壞檔、locked/write/commit/delete 失敗、跨行程鎖、慢寫入與 clear、過期驗證／gate 結果、HF 不受影響、Gemini 舊 owner 退役。 |
| 使用者畫面回報 | 使用者確認 offline-first／offline-second／offline-invalid 的新增、更新、認證失敗、清除、重整空欄、Tab/Esc、窄視窗與一般設定皆正常。 |
| Chrome 實際頁面檢查 | 獨立測試 profile、loopback fake fixture：開頁、輸入／提交／更新／失敗／清除／reload、欄位清空、Esc 關閉確認、360px 無水平溢出、回應／URL／Local/Session Storage 無測試金鑰、跨源 fetch 拒絕、金鑰 iframe=403、一般 iframe=200、無 page errors。 |
| Windows 原生 vault | 使用者當輪同意，只在獨立 namespace 操作非真實假值；原生保存、跨行程讀回、實例隔離、刪除與缺失確認通過，測試條目與 scope 清理完成。未列出或讀取日常憑證。 |
| 真實 Gemini 最小驗證 | 使用者當輪同意既有免費額度，親自在獨立頁輸入金鑰。gemini-3.8-live／Kore 收到 setupComplete，UI 顯示 validated/applied 且 backend 維持 huggingface；使用者確認。沒有 user turn／音訊／人格／記憶／工具／robot。測試端已關閉、原生隔離金鑰確認刪除且測試 scope 清理完成。 |
| 最終完整 gate | Ruff check 通過、format 121 files unchanged、strict mypy 56 source files 通過、pytest 786 passed、uv lock --check --offline 139 packages 通過。 |
| 初次完整 gate 故障 | 2 個 forget 測試因新增測試未還原共用記憶設定失敗；修正測試 fixture 的狀態還原，未更改記憶工具或豁免測試。保留原結果於 ignored cache，最後整套通過。 |
| wheel | 新 gemini_credentials.py、templates/gemini-key.html、static/js/gemini-key.js 均包含於建置 wheel；Windows 路徑 budget 測試通過。 |
| 文件與架構 | 根 README 同步；scheme.mmd 重新生成 SVG，PNG 預覽人工視覺檢查完成；未手改 SVG。Mermaid CLI／Puppeteer 僅在 ignored cache，未加入應用依賴。 |

瀏覽器腳本的回應讀取／等待條件曾失敗，修正 fixture 等待與 CDP 回應擷取後才記為通過；
這不是 Gemini 服務錯誤或產品通過比例。最後調整金鑰頁專用按鈕換行後再跑 Chrome 檢查。
owner_epoch 是行程隨機 ID，非 key fingerprint；用來接受重啟後的狀態並拒絕舊行程回覆，
CSRF 有效期為 600 秒且只存在頁面記憶體。啟動讀取失敗時，修正 vault 後需重啟 App 再明確重連。

### 可重現的本機 fixture

先依根 README 安裝開發依賴。以下 cache harness 為本機驗收輔助，不隨 wheel 交付；重建時使用 tests 的 FakeVault、
假 validator 及暫存 scope，啟動前明確阻擋外連，不新增產品 mock 開關。

```powershell
$env:PYTHONUTF8 = '1'
cache/verify-python312/Scripts/python.exe cache/003-gemini-key-settings/settings_trial.py
# 另開終端；只使用 offline-first、offline-second、offline-invalid
node cache/003-gemini-key-settings/browser_trial.mjs
```

fixture URL：`http://127.0.0.1:7864/#/settings`；獨立頁為 `/settings/gemini-key`。
只有明確授權後才執行 native_vault_trial.py／live_setup_trial.py；不在文件、命令列或聊天記錄輸入真實 key。
不得將離線 harness 的假值輸入真實服務；本輪驗收結束會停止 fixture，網址不保證持續可用。

### 尚未完成的範圍

- T037：原生 Reachy Mini Control App WebView 與真正遠端／WebRTC relay 未實測；Chrome 跨來源 iframe 模擬不等同原生驗收。
- T041：實際 HF/Gemini 語音對話中更新／清除／失敗、動作停止與手動恢復仍待當輪授權及現場配合；本輪限定最小無語音驗證。
- T044：完整結案保持待驗；不使用前兩個功能的舊驗收代替本功能結果，也不自動認定範圍豁免。

### 2026-11-03 補充驗收

- T037：使用者確認 Control App 必須先啟動 Conversation App 才能查看設定，依本輪「不啟動對話」範圍保持停止、尚未操作。電腦操作原生輔助程式未連線，沒有執行 UI 操作；原生入口與遠端／relay 驗收仍待補。
- T040：使用者同意限定 Linux 假值驗收。已運作的 WSL Ubuntu 24.04（Python 3.12.3）沒有運作中的 Secret Service；僅在工作區 cache 建立隔離環境，使用 keyring 25.7.0，不啟動或更動系統服務。
- 原生 SecretService backend 指向不存在的獨立 D-Bus socket，並以 audit hook 禁止其他 socket 連線。保存假值回報安全的 `storage_failed`，原環境假值仍有效；新行程讀回來源一致，journal 不含候選假值，沒有寫入 `.env` 或一般設定。測試 scope 已清理，未讀取日常憑證，也未連雲端或機器人。
- 隔離 harness：`cache/003-gemini-key-settings/linux_unavailable_trial.py`。首次啟動逾時，後續發現測試 socket 路徑超過 Unix socket 長度限制；縮短測試路徑後，全部斷言通過（exit 0）。這是測試環境修正，沒有修改產品程式。
- 該輪結束時，Linux 成功保存／跨行程讀回／刪除、鎖定及 scope 隔離仍缺少可用的 Secret Service，macOS 未驗，因此當時 T040 保持未完成。該輪只更新驗收文件，完整 gate 沿用上方未變更產品程式的 786 passed 結果。

### 2026-11-03 平台測試範圍決定

- 使用者明確要求「略過macOS與Linux測試」，本次個人客製化的 macOS／Linux 剩餘實測列為已豁免，不再作為 T040 結案前提；T040 據此結束追蹤。
- Windows 原生驗收及 Linux 服務不可用的既有結果保留。macOS 未實測、Linux 成功保存／跨行程讀回／刪除、鎖定及 scope 隔離未實測，均不記為通過。
- 此決定只調整本功能人工平台驗收範圍，保留跨平台產品實作、依賴與 CI；T037、T041 及 T044 仍未完成。本輪沒有執行新的平台測試或修改產品程式。

### 2026-11-03 Control App 入口與方向調整

- Control App 原先只安裝 testbench；工作區 venv 的 App 不會自動出現在其獨立 apps_venv。使用者明確同意後，以 editable 模式安裝本機客製版 1.1.1，只補缺少的 soxr 1.1.0、keyring 25.7.0 及必要依賴；未覆蓋 SDK 1.13.0。daemon 已安裝清單辨識 App，`uv pip check` 檢查 122 packages 相容。安裝保留供後續本機使用。
- 使用者授權啟動 T037；安全狀態確認 Hugging Face、相機與記憶關閉，設定頁提供本機版本。使用者回報按「開啟本機金鑰設定」無反應，原生入口不記為通過。未輸入真實金鑰，未進行 T041。
- 曾以離線 sandbox iframe 重現 popup 被阻擋，測試加入可手動開啟的網址提示。該回歸先失敗後通過；Ruff、format、mypy 通過，pytest 785 passed，wheel 因沙箱阻擋 PyPI 下載失敗，開放該次公開下載後單獨複驗 1 passed。原始失敗保留 cache；不冒稱原整套首次全過。
- 使用者在複驗時改要求規劃同頁整合；上述網址提示及 README 產品改動已撤回，本輪最後只保留規劃文件。Conversation App 與離線 fixture 已停止，未變更的暫時設定已依 guard 移除、還原原先不存在狀態。fixture 關閉曾輸出 Windows Proactor shutdown 的 WinError 10022，未將它當作同頁產品修正或成功證據。
- 同頁安全研究與計畫見 research.md、plan.md；可信 Control App 內嵌機制尚未驗證。T037、T041、T044 保持未完成，同頁差異任務尚待產生。
