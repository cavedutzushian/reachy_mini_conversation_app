# Quickstart: Gemini 設定頁憑證驗收

本指南供實作完成後使用；目前尚未實作，不能把命令預期結果視為已通過。
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
