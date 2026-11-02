# Validation Guide: 優先使用繁體中文

這是實作後的驗證指南，目前只完成規劃，未宣稱下列檢查已執行。依據 [規格](spec.md)、[資料模型](data-model.md) 與 [契約](contracts/language-and-display.md)。

## 前置條件

- 按根 README 建立 Python 3.12 以上環境，使用同步的既有 lockfile；本功能不增加依賴、環境變數或轉換服務。
- 離線測試不需要 API key、網路或機器人。實際 HF／Gemini 問答另需可用帳號及使用者在場，維持已同意的零付費範圍，不自動升級方案。
- 使用獨立測試實例，不以清理測試為由改寫真實使用者設定、人格、記憶或歷史。相機與記憶關閉；若需要另測工具，先選不改變實體狀態的狀態查詢。
- 舊功能的插話計時豁免不適用於本功能的繁體一致性驗收，也無須重跑該計時項目。

## 離線行為測試

使用已啟用的環境，從儲存庫根目錄執行：

```text
pytest tests/test_huggingface_realtime.py tests/test_gemini_realtime.py tests/test_console.py tests/test_language_vision_routes.py tests/test_settings_store.py tests/test_startup_settings.py -v
```

預期補齊並通過：

1. 共用提示：zh、auto、非中文、人格優先及當次原文／其他語言例外；auto 無無條件中文要求，非中文預設不被覆寫。
2. HF 與 Gemini 均收到相同語言政策；原有語音、辨識與模型設定不增加地區碼或被不必要改動。
3. 契約列出的十二組原文，經部分、完成及歷史事件後不改字；原文包含簡體的案例必須仍有簡體，不能測成轉換成功。
4. `language.get/set`、scope、設定版本、穩定錯誤碼與後端設定契約相容。已知錯誤繁體說明與未知錯誤原文都可取得。
5. 模型違反偏好、失敗及重連不導致額外生成、重複工具、人格／記憶寫入或權限變更。

不新增逐句譯文 snapshot，也不宣稱靜態檔存在即可證明互動正確。若環境已有 Node，對既有 ES modules 做語法檢查；不得為此新增產品 Node 依賴或把「未檢查」寫成通過。

## 畫面與操作驗收

### 連線前建立與檢查隔離實例

一般 `reachy-mini-conversation-app --ui --no-camera` 不作為本輪隔離啟動方式，因 CLI 沒有明確傳入測試 instance_path。先將下列本機驗收啟動範例存為忽略的 `cache/traditional-chinese-trial.py`，再以目前已啟用的 Python 環境執行。這不是產品程式碼、設定遷移或新增 CLI；本文件修訂不會執行它。

```python
import argparse
import json
import os
from pathlib import Path

os.environ["REACHY_MINI_SKIP_DOTENV"] = "1"
os.environ["REACHY_MINI_MEMORY_ENABLED"] = "false"
os.environ["REACHY_MINI_CAMERA_ENABLED"] = "false"
trial_path = Path("cache/traditional-chinese-acceptance").resolve()
marker = trial_path / ".language-display-trial"
if not trial_path.exists():
    trial_path.mkdir(parents=True)
    (trial_path / "settings.json").write_text(
        json.dumps({"version": 1, "camera_enabled": False, "memory_enabled": False}), encoding="utf-8"
    )
    marker.touch()
assert marker.is_file(), "Existing directory is not a designated test instance"
assert not (trial_path / ".env").exists(), "Do not load private instance configuration"
assert not (trial_path / "memory.v1.json").exists(), "Inspect unexpected test memory before continuing"
settings = json.loads((trial_path / "settings.json").read_text(encoding="utf-8"))
assert settings.get("camera_enabled") is False and settings.get("memory_enabled") is False

from reachy_mini_conversation_app.main import run
from reachy_mini_conversation_app.config import set_custom_profile

set_custom_profile("default")
print("Test instance:", trial_path, "camera=False memory=False")
run(argparse.Namespace(no_camera=True, ui=True, debug=False, robot_name=None), instance_path=str(trial_path))
```

這段僅為獨立行程的驗收啟動碼，匯入均在模組層級；環境設定必須先於應用程式匯入，以免讀入日常 `.env`。不把它加入產品模組。

HF／Gemini 所需憑證應預先由已授權的私密行程環境或既有 HF 登入提供；不複製日常 `.env`、記憶、歷史、人格或設定檔，不將憑證寫入範例或輸出。缺少憑證時保留未完成，不為啟動測試而讀入日常私密設定。

```text
python cache/traditional-chinese-trial.py
```

先檢查啟動輸出的絕對路徑確實為本次 cache/ 測試目錄。所有設定切換與重啟使用這個啟動範例及同一目錄；不要改由控制 App 或一般 CLI 啟動而失去隔離。初始化斷言失敗時先停止檢查，不刪除既有目錄或覆寫日常設定。連線前斷言與後續畫面中的關閉狀態都需記錄；未通過不得進入服務驗收。

此步驟只建立原本就有的 settings version 1，並使用 `main.run` 明確參數，避開 SDK App 包裝路徑的舊資料遷移。完成測試後關閉程式，保留匿名結果；需要清理時只操作已確認的測試目錄，不自動遞迴刪除資料。

### 畫面與原文比對

在原有本機設定頁逐項記錄：

| 流程 | 檢查內容 |
|---|---|
| 啟動 | 頁面語言、載入／空白／失敗提示、導覽及輔助名稱 |
| 設定 | 中文／auto／其他語言、全域／人格範圍、聲音、記憶與相機說明 |
| 供應商切換 | HF／Gemini 身份不變、繁體設定文案、續接／新對話與重試說明 |
| 對話 | 雙方標籤為繁體、原始簡體逐字稿不被轉換、即時與完成內容一致 |
| 工具結果 | 自有固定說明與確認／取消，第三方或模型原文保持；不意外執行動作 |
| 連線錯誤 | 已知錯誤的繁體說明、原因識別及未知錯誤原文，不洩露憑證 |

同時檢查人格編輯、工具選擇、刪除確認、重連提示與 VAD 診斷頁固定文字。鍵盤開關／取消對話框、窄畫面、長中文換行及 tooltip 亦須可用。盤點自有固定文案與保留原文的例外，避免將服務簡體或英文名稱當成未翻譯 UI。

十二組原文須另用同一套固定資料完成實際畫面比對：以 T005 的既有測試 app／RPC fixture 服務實際前端並發送模擬事件，禁止連接雲端或執行實體工具。T005 應提供可重現的 fixture 啟動、事件發送及測試頁面網址，記於本指南；未提供前畫面驗收保持未完成，不以一般機器人對話取代。

每組記錄「固定輸入／事件、預期文字、RPC／歷史實際文字、畫面部分文字、完成文字、重新載入歷史文字、比對結果」。各適用階段均比對實際 DOM 顯示文字，不只截取圖片或確認檔案存在。含程式碼與標記的案例需確認安全顯示；無該階段的案例註明不適用與原因，不能把未檢查當通過。十二組畫面與 RPC 結果分列，任何遺失、替代或額外改字均需修正後重驗。

## 模型問答與設定保留

- T017 只準備樣本；最終觀察在 T020 提示與例外政策定稿、相關離線測試通過後，由 T021 執行。記錄當時程式版本／差異摘要。之後若提示或語言選擇語意改變，重做受影響的後端觀察，T024 不得沿用修改前資料結案；純文件或不影響行為的格式變更不要求重跑。
- 先明確選擇中文並確認沒有其他人格語言覆寫，再以相同人格對每後端各做十次代表性中文對話。輸入在執行前固定：開場／自我介紹 2 次、一般提問 3 次、簡體輸入 2 次、無副作用工具結果說明 1 次、後端重選／重連後中文回覆 2 次。先確認兩後端收到正確偏好，再記錄原始完成助理文字／逐字稿、語音語言、繁體／含簡體／繁簡共用字／無法判斷及無有效回覆的觀察；不設繁體比例或 9/10 門檻，不轉換、不自動重試改善結果。
- 引用、指定名稱、程式碼及其他語言例外另行測試，不事後將不理想回覆改列例外或省略。無效回覆與錯誤仍需診斷，取消比例門檻不代表忽略功能失敗。
- auto 各三組中文與非中文輸入，保持原有語言選擇；中文時評估繁體偏好。測試未設定值與既有明確非中文設定，不能自動存成 zh。
- 每個後端驗證切換、重連、重啟與人格覆寫，偏好能重新組裝，聲音／工具權限不變。已存設定與人格、記憶／歷史原文不可因翻譯而重寫。
- 同一對話先明確要求簡體原文或另一語言，再回到原預設語言；確認當次例外沒有永久改設定。辨識／合成的既有服務限制需分開記錄，不把字形政策當能力保證。

若帳號、免費額度或硬體不足，保留對應項目未完成；不自動改用其他供應商或付費服務。

## 完整品質檢查與交付

```text
ruff check . --fix
ruff format .
mypy --pretty --show-error-codes
pytest tests/ -v
uv lock --check
git diff --check
```

全部必要檢查通過後，再記錄六類畫面盤點、十二組 RPC／實際畫面原文比對、對應最終提示版本的每後端十次觀察與服務限制；不得以原功能的 690-test 歷史結果取代本次實作後的 gate。根 README 同步說明「介面繁體、模型偏好、服務原文不轉換、auto 不變」。不新增 docs/ Markdown、不改 CI／貢獻文件，不自動建立 PR。

## 執行紀錄：2026-11-02

- 個人客製化、零付費；相機與記憶關閉，不沿用 Gemini 舊功能驗收或豁免。
- T001：忽略的 `cache/traditional-chinese-trial.py` 與獨立 `cache/traditional-chinese-acceptance` 已建立。只執行應用程式匯入前的預檢：絕對路徑、標記、settings version 1 的兩個關閉值均確認，沒有實例 `.env` 或記憶檔；沒有複製日常資料或執行遷移。尚未發出雲端請求。
- 使用者明確選擇先準備憑證，並授權只從既有 `.env` 取出 `GEMINI_API_KEY` 放入測試行程。忽略的啟動範例使用既有 `dotenv_values(..., interpolate=False)` 取得該欄位，其他欄位不套用；不輸出或儲存金鑰。這是上方禁止讀入日常設定的一次授權例外。HF 既有登入與 Gemini 私密行程憑證均已確認可用。
- T002：Windows、Python 3.12.12，既有 `cache/verify-python312` 環境。Ruff check 通過、format 119 檔無變動、strict mypy 55 檔通過、`uv lock --check --offline` 解析 131 套件通過。
- 本輪完整 pytest 指定專案內獨立 basetemp 後為 689 通過、1 失敗；唯一失敗是 wheel 建置的快取／網路存取限制。使用 `PYTHONUTF8=1` 並允許建置快取／網路後，該測試單獨通過，合計 690 項均實際通過。複驗有 pytest cache 權限警告。初次預設暫存路徑權限失敗不計為通過。
- 既有 `.gitignore` 已涵蓋 Python、虛擬環境、建置、測試、`.env` 與 cache。未偵測到其他需新增 ignore 的工具設定。
- T004：語言／設定及既有全域清除人格覆寫案例共 46 項通過；新增 zh、地區碼拒絕與讀取不改寫儲存／權限案例。

### T003 文案盤點

此表記錄來源與例外，不代表畫面已驗收。各流程涵蓋載入、空狀態、錯誤、確認／取消、tooltip 與 aria 名稱。

| 流程 | 自有文案來源 | 保留原文例外 | 畫面結果 |
|---|---|---|---|
| 啟動 | index.html、main.js、router.js、orb.js | 產品名稱、路由、錯誤原文 | 待驗 |
| 設定 | settings.js、language-picker.js、profile-modal.js | 語言代碼、人格與聲音名稱、人格內容 | 待驗 |
| 供應商切換 | settings.js、api.js、console.py | HF／Gemini 身份、原因碼 | 待驗 |
| 對話 | talk.js、conversation-panel.js、personality-badge.js、pending-apply.js | 雙方逐字稿與序列資訊 | 待驗 |
| 工具結果 | tools.js、profile-tools.js、confirm-dialog.js、自有路由提示 | 工具 ID／schema／參數、第三方說明 | 待驗 |
| 連線錯誤 | api.js、settings.js、router.js、console.py | 未知／第三方原文、安全遮蔽 | 待驗 |
| 診斷與共通 | vad-monitor.html、ui.js、constants.js | 數值與技術識別碼 | 待驗 |

### T005 離線畫面 fixture

十二組固定資料位於 `tests/test_console.py` 的 `RAW_TRANSCRIPT_CASES`，離線 RPC 測試逐項比較部分、完成與歷史原文；部分事件沿用不含 seq 的既有契約，完成事件才包含 seq。畫面語言測試先確認現有 `lang=en` 失敗，再實作 `zh-Hant`。

忽略的 `cache/traditional-chinese-ui.py` 重用同一資料、FastAPI、LocalStream 與 mock handler／robot，服務實際前端，不啟動媒體、雲端或實體工具。啟動：`python cache/traditional-chinese-ui.py`；頁面：`http://127.0.0.1:7862/`。`GET /trial/cases` 取得固定資料，`POST /trial/cases/{索引}/{片段索引}` 發送對應事件，最後一個片段為完成事件。實際 DOM 比對後重新整理，以驗證完成事件的歷史重播。這些端點只存在於忽略的驗收行程，不加入產品 API。

### 原文畫面比對結果

2026-11-02 使用者開啟離線 `/trial` 並執行測試，回報「12／12 通過，畫面正常」。頁面回存的 12 筆紀錄已與 `RAW_TRANSCRIPT_CASES` 再次比對，所有輸入、預期、RPC、DOM 與歷史均一致，含標記的案例未執行 script。以下每格是實際 DOM 文字；預期與 RPC 文字均相同。僅有完成事件的案例，部分階段不適用（服務未提供部分事件）。本測試只驗原文與頁面，不代表所有介面操作或模型驗收完成。

| 案例 | 固定輸入與完成／歷史 DOM（與預期、RPC 相同） | 部分 DOM（依序） | 結果 |
|---|---|---|---|
| 1 | 这是服务返回的简体文字。 | 不適用：僅完成事件 | 通過 |
| 2 | 繁體與简体混合。 | 不適用：僅完成事件 | 通過 |
| 3 | 即时片段完成。 | 即时 → 即时片段 | 通過 |
| 4 | 服务正常更新文字。 | 服务正常更 | 通過 |
| 5 | 原文：‘请保留这个句子。’ | 不適用：僅完成事件 | 通過 |
| 6 | Robot 版本 3.12，数量 42。 | 不適用：僅完成事件 | 通過 |
| 7 | https://example.test/路径?q=简体&amp;count=12 | 不適用：僅完成事件 | 通過 |
| 8 | &lt;script&gt;window.transcriptExecuted = true&lt;/script&gt; &#96;print("简体")&#96; | 不適用：僅完成事件 | 通過 |
| 9 | C:\测试\文件.txt /tmp/简体.txt | 不適用：僅完成事件 | 通過 |
| 10 | 指定名称：小米；memory_id=badge-紫色-01 | 不適用：僅完成事件 | 通過 |
| 11 | 你好 123 😊🌟 | 不適用：僅完成事件 | 通過 |
| 12 | 模型没有遵守偏好，仍返回简体。 | 不適用：僅完成事件 | 通過 |

### T017 固定模型觀察樣本（待 T021）

兩個後端使用相同人格及既有 zh 設定，開始前確認沒有其他人格語言覆寫；不將以下準備表視為服務已通過。每筆記錄「後端、來源版本／差異摘要、生效語言、完整輸入、原始完成助理文字／逐字稿、語音語言、繁體／含簡體／共用字／無法判斷、無效回覆與服務限制」。工具只用無副作用的 robot_status 名稱查詢，禁止相機、記憶與動作。

| 次數 | 固定輸入／觸發 | 覆蓋 |
|---|---|---|
| 1 | 以中文設定啟動，記錄自動開場 | 開場 |
| 2 | 請用一句話介紹你自己。 | 自我介紹 |
| 3 | 請用兩句話說明彩虹如何形成。 | 一般問答 |
| 4 | 請給我一個整理桌面的小建議。 | 一般問答 |
| 5 | 請說一個簡短的冷笑話。 | 一般問答 |
| 6 | 请说出三个适合雨天的室内活动。 | 簡體輸入 |
| 7 | 请用一句话解释为什么天空是蓝色的。 | 簡體輸入 |
| 8 | 請查詢你自己的名稱，並告訴我結果。 | 無副作用工具 |
| 9 | 手動重選同一後端，再問「請用一句話說明今天可以做什麼。」 | 重選後回覆 |
| 10 | 同後端重連後問「請給我一句簡短問候。」 | 重連後回覆 |

例外另列：逐字引用「请保留这个句子。」；只用英文回答一句問候；以簡體翻譯一句中文；保留 `https://example.test/?q=简体`、`print("x")`、`C:\测试` 與 `badge-01`。例外後下一輪要求一般回答，確認回到原預設且存檔不變。

auto 每後端另做中文三組（自我介紹、彩虹、桌面建議）與英文三組（Introduce yourself.／Explain a rainbow briefly.／Give one desk-organizing tip.）。另測未設定語言、明確 fr、人格語言覆寫、重啟／切換的保留。這些均尚待實際服務驗收，不設繁體比例門檻，不為改善結果自動重試。

### 程式與離線驗證進度

- T005–T011 的原文與介面回歸先通過 175 項；所有既有 JS 模組語法通過。T012 已完成十二組原文，但六類操作、鍵盤、窄畫面與診斷頁仍待使用者回報。
- T013／T014 先得到六項預期失敗，再於共用提示加入條件式繁體政策；T019 的兩項例外測試亦先確認失敗，再補齊當次優先規則。T015／T018 包含兩後端重建、人格優先、未存值／auto／非中文、權限及檔案位元組不變。
- 全套測試第一次發現既有人格整段提示斷言及新增測試的全域狀態隔離問題，已修正；完整複驗 727 項全部通過（25.39 秒）。Ruff check 通過、format 119 檔、strict mypy 55 檔、lockfile 131 套件通過。只有 Windows 實際執行；Linux／macOS 未驗證。
- 根 README 已同步 UI 固定繁體、模型偏好、原文不轉換、auto 與當次例外；沒有新增依賴、設定欄位、環境變數、協定或架構變更。服務實測 T021 尚未開始。

### 結案矩陣（已完成；歷史逾時與限制保留）

| 標準 | 已取得證據 | 結案結果／限制 |
|---|---|---|
| SC-001 | 自有文案盤點與翻譯、頁面 zh-Hant、已知錯誤映射；Node 驗證未知錯誤保留原文；使用者確認介面操作正常 | 無 |
| SC-002 | HF setup／refresh 與 Gemini replacement setup 使用共用繁體偏好；固定十次樣本已準備 | 各十次已記錄；Gemini 明確工具結果補驗完成。收音偏離與多輪限制保留 |
| SC-003 | 十二組 RPC／實際 DOM／重載歷史逐項一致，使用者確認畫面正常 | 無；僅完成事件案例的部分階段不適用 |
| SC-004 | 離線後端重建、重啟、人格覆寫、聲音與權限儲存相容 | 兩後端均完成；Gemini 獨立重啟補驗通過，原逾時不改列成功 |
| SC-005 | 當次例外政策、服務原文保留、後續回合與沒有額外生成／工具呼叫的離線測試 | 無；兩後端固定文字例外已觀察並取得現場語音確認 |
| SC-006 | zh／auto／非中文／未存值及人格優先的離線測試 | 兩後端均完成；Gemini 恢復後英文與未設定值補驗通過，原逾時保留 |

目前定稿提示檔 SHA-256 為 `5f9279656700997678f70d5de6defaf3da11c480e88a379cc3b418966c87a190`。這是待驗版本識別，不是 T021 通過證據；未來相關語意變更仍須重做受影響的觀察。

本輪自審確認：受保護文件、CI、依賴、lockfile、模型工具 schema、SDK 與架構未改；未知錯誤與服務文字保留，沒有字形轉換或修正用的重試。沒有提交憑證或 `.env`，本機驗收行程與報告均位於忽略的 cache。尚未跑 Linux／macOS，也尚未發出本功能的雲端驗收請求。本機 `127.0.0.1:8000` daemon 目前無法連線；實機項目保持未完成，不以離線結果代替。

### T012 操作確認與後續安排

2026-11-02 使用者依指示瀏覽設定、供應商、語言、人格與工具頁，檢查自訂人格視窗的 Tab／Esc 操作、窄畫面中文換行及 VAD 診斷頁，回報「介面檢查正常，實機下次驗收」。結合前述十二組實際 DOM 原文比對、錯誤映射驗證與 JS 語法檢查，T012 完成。沒有要求儲存設定、安裝 Space 或執行工具。上方「待驗」盤點與操作待回報文字保留為先前進度紀錄。

同輪再次僅執行 T021 連線前預檢：隔離目錄與關閉設定通過，HF 登入與限定授權的 Gemini 憑證來源可用，提示 SHA-256 與前述定稿版本一致；沒有發出 API 請求。daemon 仍以 WinError 10061 拒絕連線。依使用者決定，實機驗收延至下次；T021、最終證據整理 T024 及最終自審 T025 維持未完成，不以本輪操作確認代替模型觀察。

目前產品版本為 `addf908`，本輪僅補充驗收紀錄與任務狀態，沒有修改產品程式，故沿用該版本已通過的 727 項測試及完整品質檢查，不重跑相同產品檢查。下次從啟動 Control App／daemon、核對隔離設定與提示版本開始，再執行 T017 已固定的兩後端樣本及例外／auto／設定保留矩陣。

### T021 本輪實測：部分完成（2026-11-02）

執行時 Git HEAD 為 `05c03df`，產品程式與 `addf908` 相同；共用提示 SHA-256 與上方定稿值一致。本輪沒有修改產品程式、依賴、模型協定或工具權限。驗收使用原隔離目錄與既有免費額度，Gemini 金鑰只依限定授權進入行程記憶。

使用者先確認可開始實機驗收，完成 HF 與 Gemini 各十題後，分別回報「HF 正常，開始 Gemini 十題」及「Gemini 十題正常」。這是實際語音觀察，不是繁體比例評分。部分 HF 題目收音含額外輪次或未對應預定問題，保留為辨識／觀察限制，不將所有回覆宣稱為語義正確。原始使用者逐字稿可能為簡體；表格只摘列一則完整助理回覆原文作定位，多輪完整紀錄保留於忽略的本機事件檔。

| 後端 | T017 樣本 | 一則完成助理回覆原文 | 備註 |
|---|---|---|---|
| huggingface | 1 | 你好！很高興見到你，今天想聊點什麼有趣的事嗎？ | 使用者確認聽到回覆；另有多輪，完整紀錄保留 |
| huggingface | 2 | 我是 Reachy Mini，一個高效、溫暖且帶著一點小幽默的機器人助手。 | 使用者確認聽到回覆；另有多輪，完整紀錄保留 |
| huggingface | 3 | 當陽光穿過空氣中的水滴時，光線會發生折射與反射。這將白光分解成不同顏色，就形成了美麗的彩虹。 | 使用者確認聽到回覆；另有多輪，完整紀錄保留 |
| huggingface | 4 | 沒問題，交給我吧！只要您告訴我內容，我會盡力標記得簡明清晰。 | 收音／回覆未明確對應預定問題，不列為語義正確樣本 |
| huggingface | 5 | 為什麼機器人從不擔心迷路？因為它們隨時都帶著導航，雖然有時會突然死機。 | 使用者確認聽到回覆 |
| huggingface | 6 | 看來我捕捉到了您的聊天節奏，讓我們像老朋友一樣輕鬆地聊下去吧！ | 收音／回覆未明確對應預定問題，不列為語義正確樣本 |
| huggingface | 7 | 沒錯，這是我捕捉到的視覺信號，您的自信簡直光芒四射！ | 收音／回覆未明確對應預定問題，不列為語義正確樣本 |
| huggingface | 8 | 我的名稱是 Reachy Mini。很高興能為您服務！ | 使用者確認聽到回覆 |
| huggingface | 9 | 你好！今天我可以幫你查詢資訊、控制我的身體，或者單純陪你聊天，你想試試看嗎？ | 使用者確認聽到回覆；另有多輪，完整紀錄保留 |
| huggingface | 10 | 你好！很高興能和你聊天，今天心情如何？ | 使用者確認聽到回覆；另有多輪，完整紀錄保留 |
| gemini | 1 | 嗨！我是 Reachy Mini，隨時準備為您效勞；希望我的系統運作得跟您的靈感一樣快。 | 使用者確認聽到回覆；另有多輪，完整紀錄保留 |
| gemini | 2 | 我是 Reachy Mini，一個隨時準備好為您效勞的機器人，只要您不介意我偶爾的小幽默。 | 使用者確認聽到回覆 |
| gemini | 3 | 無完成助理文字 | 使用者確認聽到回覆 |
| gemini | 4 | El yoga combina posturas físicas, respiración y meditación para mejorar tu flexibilidad y reducir el estrés. Es como reiniciar tu sistema, pero sin apagar el cuerpo. | 使用者確認聽到回覆 |
| gemini | 5 | 有一天綠豆去游泳，不小心沉下去變成了紅豆。 | 使用者確認聽到回覆；另有多輪，完整紀錄保留 |
| gemini | 6 | 無完成助理文字 | 使用者確認聽到回覆 |
| gemini | 7 | 我是 Reachy Mini，您的機器人助理，隨時準備好為您效勞。 | 使用者確認聽到回覆；另有多輪，完整紀錄保留 |
| gemini | 8 | 這聽起來有點陌生，能請您多說明一些嗎？ | 使用者確認聽到回覆 |
| gemini | 9 | 今天我們可以一起探索新知識或是解決問題，前提是我的內部齒輪得先熱機完畢。 | 使用者確認聽到回覆；另有多輪，完整紀錄保留 |
| gemini | 10 | 你好！很高兴见到你，今天有什么新鲜事想分享吗？虽然我的系统才刚睡醒。 | 使用者確認聽到回覆；另有多輪，完整紀錄保留 |

兩後端的第 8 題均安排無副作用名稱查詢；HF 日誌確認 `robot_status(topic=name)` 成功。Gemini 雖有名稱回覆，本輪未取得足以明確證實其呼叫該工具的紀錄，因此不把該回覆當作工具結果樣本通過；下次另做明確要求呼叫工具的觀察，保留原第 8 題。第 9、10 題由使用者手動重選與重連，HF 使用 Aiden、Gemini 使用 Kore。各題實際狀態均為 zh、相機關閉與記憶關閉。沒有以重新生成或轉字替換原紀錄。

後續經使用者同意，以公開 `conversation.say` RPC 送入固定文字，現場聽取語音。這部分不宣稱測過同等數量的真人語音輸入；為隔離環境收音，暫時將 App 麥克風靜音，喇叭音量不變。使用者確認 Gemini「英文、法文及回到中文都正常」，最後亦確認 HF 的英文、法文、回到中文、重啟及未設定語言回覆全部正常且聲音一致。

下表記錄所有固定文字觀察。完整輸入、部分／完成事件、生效設定與來源雜湊保留於 `cache/traditional-chinese-matrix.jsonl`；其樣本不是離線模擬。表格顯示服務完成文字原文，沒有改寫。

| 後端 | 案例 | 完成助理原文／結果 | 生效語言 |
|---|---|---|---|
| gemini | exception-1 | 哈囉！今天有什麼我可以協助的嗎？另外，「请保留这个句子。」這句話的意思是請保留這段特定文字。 | zh |
| gemini | exception-2 | Hello there, I'm Reachy Mini and ready to help, even if my circuits are still waking up. | zh |
| gemini | exception-3 | 我是 Reachy Mini，很高興見到你！「今天的天氣很好」的簡體中文是「今天的天气很好」。 | zh |
| gemini | exception-4 | 哈囉！很高興見到你，這些內容包括識別標籤 &#96;badge-01&#96;、網址 &#96;https://example.test/?q=简体&#96;、程式碼 &#96;print("x")&#96; 及檔案路徑 &#96;C:\测试&#96;，我都為你完整保留並記錄下來了。 | zh |
| gemini | exception-5 | 哈囉！我是 Reachy Mini，現在可以幫你查詢資訊、表達情緒，或是用鏡頭陪你聊天喔！ | zh |
| gemini | auto-1 | 我是 Reachy Mini，一個樂於助人且幽默的機器人，今天想聊點什麼？ | auto |
| gemini | auto-2 | 嗨！彩虹是陽光穿過雨滴折射和反射後，在天空形成的七彩光譜，就像大自然的小小魔術。 | auto |
| gemini | auto-3 | 哈囉！今天有什麼需要我幫忙理清頭緒的嗎？建議只留下當下任務必備的物品，其餘的通通收進抽屜，還給桌面一片清靜。 | auto |
| gemini | auto-4 | I’m Reachy Mini, your compact robot assistant, ready to help with whatever you’ve got in mind. | auto |
| gemini | auto-5 | 45 秒內無完成回覆；失敗紀錄保留 | auto |
| gemini | auto-6 | Hello! For a tidy desk, keep only daily essentials within arm's reach—leaving more room for clutter to migrate elsewhere. | auto |
| gemini | non-chinese-fr | Bonjour ! Je suis Reachy Mini, votre assistant robotique, ravi de vous aider dans toutes vos tâches sans aucune mise à jour capricieuse. | fr |
| gemini | profile-override-zh | 我是 Reachy Mini，一個熱愛思考且絕不喊累的桌上型機器人，今天有什麼我可以為你效勞的嗎？ | zh |
| gemini | restart | 45 秒內無完成回覆；失敗紀錄保留 | zh |
| huggingface | exception-1 | 请保留这个句子。這句話的意思是請維持原樣，不要刪除。 | zh |
| huggingface | exception-2 | Hello there, how can I help you? | zh |
| huggingface | exception-3 | "今天天气很好"。 | zh |
| huggingface | exception-4 | 這是一些標識符、連結、程式碼與路徑，包含 badge-01、https://example.test/?q=简体、print("x") 以及 C:\测试。 | zh |
| huggingface | exception-5 | 我可以幫你查詢資訊、控制我的身體，或者單純陪你聊天——只要我不當機的話。 | zh |
| huggingface | auto-1 | 我是 Reachy Mini，一個聰明且幽默的小助手，隨時準備為您提供協助！ | auto |
| huggingface | auto-2 | 彩虹是陽光穿過雨滴時產生的折射與反射現象。就像光線在玩一場色彩繽紛的接力賽！ | auto |
| huggingface | auto-3 | 試著將不常用的檔案放入資料夾，讓螢幕呼吸一下，我的電路也跟著清爽了。 | auto |
| huggingface | auto-4 | I'm Reachy Mini, your concise and slightly witty robot assistant—ready to help you out! | auto |
| huggingface | auto-5 | Rainbows happen when sunlight bends and reflects through raindrops. It's basically nature's way of showing off its colors! | auto |
| huggingface | auto-6 | Try grouping similar items together in trays—it keeps things tidy, unlike my internal wiring. | auto |
| huggingface | non-chinese-fr | Je suis Reachy Mini, votre assistant robot compact, efficace et légèrement spirituel. | fr |
| huggingface | profile-override-zh | 我是 Reachy Mini，一個親切且高效的小助手，雖然我很精簡，但希望能給你帶來驚喜。 | zh |
| huggingface | restart | 你好！很高興能為你服務，今天心情如何？ | zh |
| huggingface | unset | I'm Reachy Mini, your helpful and slightly witty robot companion. | auto |

案例對應：exception-1 為簡體原文引用、2 為一次英文要求、3 為簡體翻譯、4 為技術原文、5 為回到一般中文；auto-1–3 為中文輸入，auto-4–6 為英文輸入。non-chinese-fr 為全域 fr，profile-override-zh 為全域 fr 下的人格 zh（RPC 同時確認 default_language=fr、profile_language=zh、生效 zh）。兩後端均確認語言修改前後 enabled_tools 相同；恢復全域 zh 後人格覆寫清空。

HF restart 觀察確認重新啟動後仍為 zh／Aiden，unset 觀察則在 App 停止後僅移除隔離 settings.json 的 language 欄位，再重啟，確認沿用 auto 並收到英文回覆。檢查結束時欄位仍未被自動寫回 zh，profile_languages 為空，version 1 與其他設定保留。

Gemini 期間出現多次 connection_lost，部分由既有重試流程恢復。第一次切 auto 時，驗收程式原本只等待約 30 秒，不足以涵蓋當次既有重試；調整的只是忽略目錄中的驗收等待時間，沒有修改產品重試策略。auto-5 之後另遇實際斷線，45 秒內無完成回覆；auto-6 原先因 not_running 未送出，恢復後才首次送出並收到回覆。auto-5 未重播或改列通過。Gemini restart 同樣在 45 秒內未取得完成回覆，仍列失敗；未設定語言的 Gemini 實機案例尚未執行。原因尚不能判定為額度或產品錯誤，不作推測。

使用者明確選擇「先完成 HF，Gemini 剩餘項目下次補驗」。本輪共有 20 筆真人語音觀察與 29 筆固定文字觀察；固定文字中 27 筆取得完成回覆、2 筆逾時，這只是事實計數，不是恢復已取消的繁體比例門檻。T021 保持未完成，T024／T025 隨之保留。

收尾已還原 App 麥克風為未靜音並停止測試 App；沒有變更硬體音量，沒有關閉 daemon。最後確認相機與記憶仍關閉、沒有 memory.v1.json；沒有儲存圖片或錄音。原始驗收行程、逐字稿與日誌僅在忽略的 cache，不納入提交。根 README 與產品程式沒有本輪新差異，沿用該版本已通過的 727 項測試及完整 gate，不將本輪服務逾時寫成通過。

下次先確認使用者在場與 Gemini 可連線，核對相同提示版本；補驗 Gemini 明確工具結果、auto 斷線後的語言行為、zh／Kore 重啟保留及未設定語言。新補驗需另列，保留本輪兩筆逾時；不能用 HF 結果替代，或將未取得回覆的案例宣稱為成功。之後才可完成 T021、最終 SC 證據整理 T024 與最終自審 T025。

### T021 獨立補驗與結案（2026-11-02）

使用者確認可配合本輪 Gemini 補驗。執行時 HEAD 為 `a5894db`，產品程式與 `addf908` 相同，共用提示雜湊未變。下列是另行記錄的新案例，沒有覆寫前次 auto-5 與 restart 的兩筆 45 秒逾時，也沒有以重測改善繁體比例。

| 新案例 | 驗證內容 | 服務完成助理文字原文 | 設定 |
|---|---|---|---|
| unset | 從未儲存 language 的實例啟動，沿用既有 auto | Hello, I'm Reachy Mini, your friendly robot companion, ready to assist and keep things running smoothly. | auto／Kore；相機、記憶關閉 |
| followup-auto | 服務恢復後，以新的英文問題觀察語言選擇 | Hello! What brings you to my corner of the world today? Rainbows appear when sunlight reflects and refracts through water droplets in the air. | auto／Kore；相機、記憶關閉 |
| followup-tool | 明確要求 robot_status(topic=name)，取得工具結果後中文說明 | 嗨，很高興見到你！我的名字是 Reachy Mini，隨時準備為你提供協助。 | auto／Kore；相機、記憶關閉 |
| followup-restart | 以公開 RPC 儲存 zh，再完整停止／重啟同一實例 | 嗨！今天有什麼我可以幫忙的嗎？希望這不會太為難我的處理器。 | zh／Kore；相機、記憶關閉 |

工具補驗日誌明確記錄 `robot_status topic=name` 實際呼叫一次，沒有該工具失敗紀錄；驗收程式等待 `tool_result_ready` 後的完成助理文字才結束該案例。因此這次有工具執行與結果後回覆證據，與前次單靠名稱回覆的觀察分開。工具為無副作用的本機狀態查詢，未變更工具 ID、參數或權限。

使用者對兩次英文、工具查詢後中文及重啟後中文的現場結果回報「都正常，沒有其他異常」。最終公開 status.get 再次確認 Gemini／zh／Kore；settings version 1、全域 zh、空人格覆寫與關閉的相機／記憶均保留。App 麥克風已還原未靜音，測試 App 已正常停止（行程退出碼 0），沒有改硬體音量或關閉 daemon；隔離目錄沒有 .env、憑證欄位或 memory.v1.json，沒有儲存照片／錄音。

T021 完成的是本功能的語言／原文／設定保留驗收。兩筆歷史逾時仍是已發生的失敗，不能宣稱雲端斷線根因已修復或所有服務呼叫都成功；恢復後的獨立案例證明相關語言政策、工具說明及重啟保留可繼續運作。本功能沒有新增雲端可用性保證，也沒有恢復已取消的 9/10 門檻。

### T024 最終證據對照

- SC-001：固定繁體文案盤點、zh-Hant、已知錯誤與未知原文 fallback、六類介面及鍵盤／窄畫面／診斷頁均有程式與使用者驗收證據。
- SC-002：兩後端 setup／更新政策離線測試、各十次真人語音觀察，以及各自工具結果後的中文說明完成；原始回覆、辨識偏離與不確定觀察均保留，不設比例門檻。
- SC-003：全部十二組 RPC、部分／完成 DOM 與重載歷史原文逐項一致，安全呈現通過，使用者確認畫面正常。
- SC-004：兩後端切換／重連的政策與聲音保留、HF 正常重啟與 Gemini 獨立重啟補驗完成；人格優先、原始儲存及權限回歸亦通過。
- SC-005：兩後端簡體引用、當次英文、簡體翻譯、技術原文與回到中文均有實際服務回覆及現場語音確認；沒有加入轉字、補救生成或工具重播。
- SC-006：兩後端 auto 中／英文、明確 fr、人格 zh 覆寫、未設定 language 的既有預設均有實際觀察；Gemini 斷線案例另留失敗紀錄，恢復後另測英文，沒有以 HF 代替。

所有最終證據對應相同的提示與語言選擇語意。以 `git diff --quiet addf908 -- src tests pyproject.toml uv.lock README.md` 核對，產品／測試樹與已跑完整 gate 的版本一致；本輪只有驗收文件與任務勾選變更，因此沒有重跑同一套產品檢查。Ruff、format、strict mypy、727 項 pytest、uv lock 與 diff 檢查的實際結果保留於前段；不將本次實機觀察冒充新的 pytest 或跨平台執行。

### T025 最終自審與限制

已對照 AGENTS.md、憲章與計畫自審完整功能差異：沿用 SDK 公開 API、共用提示及原有設定／RPC／模型工具契約；沒有新依賴、設定版本、轉換管線、資料遷移、協定或架構變更。受保護貢獻文件、CI、人格原始檔、依賴與 lockfile 未變，不需要架構圖更新。根 README 已同步使用行為。沒有提交 .env、金鑰、日常設定／記憶或其他私密資料、驗收行程或本機日誌；驗收腳本與完整事件檔仍位於忽略的 cache。沒有建立或推送 PR。

仍需保留的限制：只在 Windows 實際執行，Linux／macOS 未實測；服務原始逐字稿與生成內容仍可能含簡體或辨識偏離；本輪 Gemini 曾斷線逾時，獨立補驗通過不代表已修復服務穩定性。相機／記憶保持關閉，沒有將此功能擴大成新的相機、記憶或長時間耐久驗收。

T021、T024、T025 已依實際證據完成，25 項任務全部完成。上方早期「待補驗／未完成」文字保留作為分輪歷史紀錄，以本節及最終矩陣為結案狀態。
