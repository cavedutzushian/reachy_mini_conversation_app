# Implementation Plan: 設定頁管理 Gemini API key

**Branch**: `feat/003-gemini-key-settings` | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

**Input**: `specs/003-gemini-key-settings/spec.md`，含三項已確認的 A 選項。

## Summary

在既有 Gemini 設定區提供遮蔽輸入、「驗證並套用」、取消及確認清除。已保存的值永不回填。
設定頁來源優先；成功清除後可回到環境來源，但 Gemini 必須等待手動重連。
候選值以獨立、無使用者內容的 Live setup 驗證，再透過系統憑證庫保存，最後提交生效指標。
Hugging Face 維持預設，使用中不受這些操作影響。

## Technical Context

**Language/Version**: Python 3.12；既有原生 JavaScript ES modules、HTML/CSS。

**Primary Dependencies**: 沿用 Reachy Mini SDK 公開 API、FastAPI/Starlette、websockets、platformdirs。
計畫新增唯一直接依賴 `keyring>=25.7,<26`；已於規劃時告知使用者，實作時執行 `uv lock`。
不加入 Google SDK、前端框架、登入系統或其他 provider。

**Storage**: 金鑰只進允許的 OS 憑證 backend；獨立 `gemini-credential.json` 僅存非秘密交易 metadata。
沿用 `.env`／啟動環境作相容來源，不修改它們。不同 App 實例及 OS 使用者分開保存。

**Testing**: pytest 注入 fake vault、假 Gemini WebSocket、暫存實例；現有 console、settings、Gemini、session 測試擴充。
前端沿用既有測試方式及人工瀏覽器檢查，不新增 DOM 測試依賴。

**Target Platform**: Windows Credential Manager、macOS Keychain、Linux Secret Service；
未提供可用受保護儲存的部署拒絕 UI 保存，env-only 仍可運作。

**Project Type**: Reachy Mini SDK 上的本機語音應用，既有設定頁加專用 HTTP 路由。

**Performance Goals**: 非阻塞既有 HF 音訊迴圈；驗證沿用既有 setup/close 時限，沒有隱藏重試。
新 clear 意圖立即退休舊驗證並停止 Gemini，不等待雲端驗證逾時。OS 儲存呼叫移出事件迴圈，不能假設取消執行緒即取消寫入。

**Constraints**: 無明文 fallback、無秘密查詢、無自動 provider/source fallback、無工具或媒體驗證。
本機受信任 OS 使用者是信任邊界；不承諾防止同帳號惡意程式、瀏覽器擴充或 OS dump 取密。

**Scale/Scope**: 每實例一個生效 Gemini 憑證、多個設定分頁、單一憑證管理行程；不新增跨裝置管理。

## Constitution Check

| 閘門 | Phase 0 前 | Phase 1 後 |
|---|---|---|
| SDK 公開 API；共享 realtime 行為留在 huggingface_realtime.py | 通過：讀取現有模組及 CONTRIBUTING | 通過：SDK 不修改，LocalStream 繼續單獨擁有重試；共用 session fencing 重用既有路徑 |
| 單一功能、型別及最小改動 | 通過 | 通過：一個憑證儲存模組，不引入一般 secrets framework；無新 Any/cast/ignore |
| 安全錯誤與日誌 | 通過 | 通過：固定錯誤碼，禁止原始 request/header/exception body；失敗仍記錄安全分類 |
| 必要測試及完整 gate | 通過：計畫不改產品 | 通過：離線故障矩陣、前端與各 OS opt-in 驗收、完整 gate 已列入 quickstart |
| 個人客製化與人工審查 | 通過：使用者已授權個人客製化 | 通過：不建立上游 PR；若日後投稿仍需 Issue、維護者同意及人工審查 |
| Python 3.12、跨平台及依賴 | 通過 | 通過：keyring 已標示；各 OS 不可用時有明確降級，實作同步 uv.lock |
| 文件及受保護檔案 | 通過 | 通過：實作更新根 README；標記架構圖需更新；不修改 CI／貢獻文件／PR 範本 |

本輪只完成設計與文件檢查，未執行產品 gate、實際憑證庫或雲端驗收，不沿用舊功能結果宣稱通過。

## Project Structure

### Documentation (this feature)

```text
specs/003-gemini-key-settings/
├── spec.md
├── checklists/requirements.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/credential-settings.md
```

`tasks.md` 由下一步 `$speckit-tasks` 產生。

### Source Code (repository root; planned changes)

```text
src/reachy_mini_conversation_app/
├── gemini_credentials.py          # 新增：受保護儲存、來源解析、交易與安全狀態
├── config.py                      # 環境來源與生效來源分離
├── main.py                        # 提供穩定 credential scope、初始化及釋放
├── console.py                     # 專用 HTTP、操作協調及 manual-reconnect gate
├── gemini_realtime.py             # 候選 setup 驗證、正式 handler 使用憑證快照
├── huggingface_realtime.py        # 必要共用 session fencing；不複製語音迴圈
└── static/js/
    ├── api.js                    # 專用 HTTP transport；不走通用 RPC
    └── views/settings.js         # 遮蔽輸入、來源及操作結果
 tests/
├── test_gemini_credentials.py    # 新增：來源、持久化、復原及隔離
├── test_console.py
├── test_gemini_realtime.py
└── test_settings_store.py
```

**Structure Decision**: 沿用既有應用與 tests 鏡像，不建立第二個服務。
`settings_store.py` 的一般設定不保存秘密，亦不借用其「讀取錯誤視為空設定」行為。

## Phase 0 — Research decisions

見 [research.md](research.md)：所有技術未知已決定，包括 Linux 無 vault、CLI scope、
本機 HTTP 安全邊界、候選驗證、交易 crash windows 與多行程排他。

## Phase 1 — Design and delivery boundaries

1. 先建立非秘密狀態及受保護儲存交易，證明 env-only 不依賴 vault；故障不會偷偷換來源。
2. 再加入獨立候選驗證及唯一 owner 協調，確保 clear、遲到結果、設定變更不會重啟舊 session。
3. 加入受限專用 HTTP 契約與 UI；`backend.config` 繼續拒絕 key 參數。
4. 完成 [quickstart.md](quickstart.md) 的離線、安全及實際儲存驗收；live 驗收另行取得當輪同意。

實作同步根 `README.md`：保存範圍、來源優先、清除非撤銷、本機入口、Linux 前提及失敗恢復。
此功能增加憑證資料流，需更新 `docs/scheme.mmd` 並重新產生 SVG；不可手改 SVG。
不新增環境變數，沿用 `GEMINI_API_KEY` 及 `REACHY_MINI_INSTANCE_PATH`；若實作確需新變數，須同步 `.env.example` 並先檢視範圍。

## Requirement coverage

| 規格 | 設計與驗收 |
|---|---|
| FR-001、FR-002、FR-007；SC-001 | 契約 UI、三次操作限制、空白與取消、鍵盤及欄位清空 |
| FR-003；SC-002 | 分離 presence/source/validation/connection，revision 衝突與無秘密快照 |
| FR-004、FR-012；SC-002 | 專用 HTTP、本機限制、CSRF、無回填、固定錯誤及洩漏測試 |
| FR-005、FR-006；SC-003 | OS allowlist、metadata journal、四種來源、重啟及讀取失敗測試 |
| FR-008、FR-009、FR-011；SC-004 | HF 不動、Gemini gate、fresh session、clear 錯誤及手動重連 |
| FR-010；SC-005 | auth／eligibility／quota／network／storage 分類及原設定保留 |
| FR-013、FR-014 | 最小 setup、不載入使用者內容、不建立 robot/audio/tool 依賴的驗證測試 |

## Complexity Tracking

沒有未豁免的憲章違反。版本化 vault 槽與非秘密 journal 是為了避免直接覆寫舊秘密造成無法回復；
本機專用 HTTP 是既有 RPC 缺少 Request 授權來源資訊所需的最小邊界。
