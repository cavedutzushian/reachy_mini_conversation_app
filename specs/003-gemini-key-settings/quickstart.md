# Quickstart: Gemini 設定頁憑證驗收

## 2026-11-03 同頁方案待驗清單

使用者改要求整合回原設定頁、不額外開頁。本節為新方案目標；以下原獨立頁步驟與結果保留為基線，不代表同頁輸入通過。

1. 不輸入真實金鑰，先取得直接本機頂層頁與 Control App 內嵌的祖先來源、Origin／Fetch Metadata 能力證據；未通過 plan.md 的可信內嵌研究閘門，不放行 frame 秘密操作。
2. 在通過授權的同頁 Gemini 區完成輸入、取消、空白、驗證失敗、成功更新及清除確認；確認沒有 popup／新頁，未改一般設定或 HF session。
3. 模擬切換子頁、返回、reload、操作中離開與重新進入；欄位空白、token 重新取得、無重複輪詢／自動重送或舊結果覆蓋。以假值檢查日誌、錯誤、歷史、URL 及 browser storage 無洩漏。
4. 對遠端、relay、未知／opaque frame、惡意跨站及缺失祖先資訊，確認金鑰區只讀、沒有 token 或 mutation，一般設定仍可操作。不能用「API 同源」代替可信嵌入證據。
5. 複驗同頁鍵盤、焦點、Esc、繁體中文與窄視窗；移除舊獨立頁後確認沒有 static alias／第二秘密入口，再跑完整 gate。macOS／Linux 剩餘實測沿用已確認豁免，真實服務／語音測試仍需另外授權。

本指南含實作驗證方式與本輪證據；程式已完成本機驗證，尚待跨環境及實際對話驗收。未執行項目不能由命令預期結果推定通過。
Python 3.12，依根 README 建立開發環境。預設所有測試使用 fake vault 與假 Gemini endpoint，
不讀日常 `.env`、OS 使用者憑證庫或真實登入快取，不連 robot，不啟用相機／記憶。

## 1. 離線自動驗證

實作需提供 `tests/test_gemini_credentials.py`；測試以 tmp_path 與 dependency injection 隔離檔案、
環境來源、OS lock/vault 及 Live socket，並拒絕未預期外連。不要靠 `keyring.get_keyring()` 選測試 backend。

venv 啟用後執行（PowerShell／POSIX shell 均可逐行）：

```text
python --version
pytest tests/test_gemini_credentials.py tests/test_console.py tests/test_gemini_realtime.py tests/test_settings_store.py -v
```

必要結果：

| 情境 | 預期 |
|---|---|
| env-only/UI-only/both/neither，加 reload/restart/clear | 來源遵循優先順序；env-only 不需 vault；不修改 .env |
| 空白、取消、invalid auth、model eligibility、quota、timeout | 舊設定保留；錯誤分類正確；無暗中重試或 source fallback |
| vault locked/write/readback/delete 失敗、journal 損壞或 commit 不明 | 不假裝缺失、不錯報成功；blocked 或原 active；停止狀態誠實 |
| 每個 journal/vault 操作點模擬 crash 後重開 | pending 不升級；clearing 即使仍有 active ID 也先 blocked；舊槽 cleanup 可追蹤 |
| preparing 有舊 active／無舊 managed | 前者只讀舊 active、失敗 blocked；後者保留原 env snapshot/none，不讀候選 |
| 慢驗證後 clear、多分頁舊 revision、驗證中換 model/provider | 舊結果不能保存、覆蓋狀態或重啟；clear 不等雲端 timeout |
| 兩 scope、同 scope 第二行程 | namespace 隔離；第二行程不取得管理權或偷換 env |
| HF active／Gemini active／disconnected × update/clear/failure | HF session 不變；Gemini 新 session 或待手動重連；無舊音訊/工具重播 |
| silent setup | 僅 model/必要 speech config；無 user turn、personality/memory/tool/resumption/media |
| 惡意 Origin/Host、LAN peer、forwarded headers、缺 token、SDK RPC key | 拒絕；舊正常設定仍可運作；無 key echo |

用假的可辨識 sentinel 作候選（不用真 key），擷取 request validation error、狀態查詢、所有 log level、
逐字稿、settings.json、journal、URL 與瀏覽器持久儲存；六類操作 input/update/clear/failure/reload/restart
均不得出現 sentinel 或可辨識片段。fake vault 的 secret 欄位及必要 transport/body 記憶體不算洩漏。
檢查 redacted request/error repr、websockets DEBUG 與不合法欄位驗證路徑；不是只測正常結果。

## 2. 本機瀏覽器（先模擬）

使用 console 測試相同的 fake backend/vault 與臨時 scope，另以隔離測試入口啟動既有 settings_app；
入口由實作提供，啟動前必須 fail closed 確認 fake 模式且阻擋外連，不能把假 key 交給日常 App。
測試入口只保留於既有測試／ignored cache，不新增產品 mock 開關。

1. 開啟該次入口顯示的 loopback 一般設定頁，確認 Gemini 區只有安全狀態與按鈕；按「開啟本機金鑰設定」另開 /settings/gemini-key，檢查空白 password、來源與非連線混淆的狀態。
2. 完成新增、更新、取消、空白、確認清除，計數明確操作；reload/restart 仍不回填秘密。
3. 獨立頁 Tab/Enter/Esc、焦點、aria-live、窄視窗繁體換行正常；Control App 本機 iframe 內的一般設定仍可用，按鈕開啟頂層本機頁。
4. 遠端／relay-only 一般設定仍可用且顯示本機金鑰管理限制；獨立頁拒絕所有 frame 與遠端導覽，沒有公開 static HTML alias；跨源頁面不能取得 token、改值或清除，一般 RPC 不受影響。
5. 檢查開發工具 Network：只有專用 mutation request body 持有候選，無 key 回應/URL/cache；
   Local/Session Storage、歷史與逐字稿無秘密。不要將含秘密 request 的 HAR 匯出。

這是人工驗收，未做前保持未完成。自動 HTTP fixture 不取代真實 WebView／browser 來源檢查。
後續本機實作只依賴前置程式與必要離線自動測試，不依賴這些人工結果；未驗證的 UI／OS／live 項目分開追蹤，完整結案前仍須完成或取得明確範圍決定。

## 3. 各平台受保護保存（明確 opt-in）

取得使用者當輪同意後，使用獨立 scope 及唯一測試 namespace，僅操作該 namespace：
Windows 本機 Credential Manager、macOS 已解鎖 Keychain、Linux 有 D-Bus/Secret Service 的使用者 session。
先用非真實 sentinel 做跨行程保存/讀回/刪除，再檢查 locked/unavailable 情境；不列出或讀取日常條目。
預期重啟仍保存、不同 scope 不互讀、clear 後所有已知測試槽皆刪除。
完成後刪除 fixture、恢復原設定並記錄平台；未執行的 OS 不可宣稱通過。
無 Secret Service 的 Linux 必須清楚拒絕保存，但 env-only fixture 仍能解析來源。

## 4. 真實 Gemini／對話驗收（另行授權）

不沿用舊功能的真實金鑰／機器人測試授權。需要當輪同意、可用額度與測試範圍。
先在獨立 scope 透過 UI 輸入使用者持有的 key；不得請使用者貼進聊天或 shell 命令。
驗證只做最小 setup；確認無問候／工具／音訊／照片／使用者內容送出。
之後如同意對話測試，依契約做 active Gemini update/clear/fail 與 active HF 管理；
核對新對話、手動重連、無雙重回覆及設定未變，最後清除該 scope 的測試 key。
保留不含秘密的時間、錯誤分類與現場回報；不能把真實服務失敗改報通過。

## 5. 完整 gate 與文件

```text
ruff check . --fix
ruff format .
mypy --pretty --show-error-codes
pytest tests/ -v
uv lock --check
```

實作加入依賴時先 `uv lock`，不要在本輪規劃修改 lock。
自審根 README、架構來源與重新產生的 SVG、無秘密 diff；不修改 CONTRIBUTING/CI/PR 範本。
記錄自動 gate、UI、OS vault、雲端／實機結果的實際範圍；人工驗收未完成要明列，不以舊功能結果補足。

## Implementation evidence — 2026-11-03

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
