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
