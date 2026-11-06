# Implementation Plan: RAG 模型下載與單文件離線產包

**Branch**: `feat/005-prepare-rag-assets` | **Date**: 2026-11-06 | **Spec**: [spec.md](spec.md)

**Input**: `specs/005-prepare-rag-assets/spec.md`

## Summary

提供兩個明確手動執行的模組腳本：下載使用者指定、已有安全權重的 BGE-M3 固定 revision；以本機模型把單一 UTF-8 TXT／Markdown 產成 004 v1 包。共享路徑／發布保護與模型驗證，重型工作放在獨立程序，既有 App 不自動下載或產包。

關鍵限制：官方 main 目前無 safetensors，不作預設版本；沒有合規安全權重的指定 revision 在下載大型檔前拒絕。不轉換 bin、不自動採 PR。Chroma 公開 close 只保證釋放資源，實作先證明小／奇數段落的完整封存；無法通過既有 reader 的全量／HNSW 不變性檢查即停止交付。

## Technical Context

**Language/Version**: Python 3.12；現代型別、strict mypy；不新增 Any／cast／PEP 695／future annotations／ignore。

**Primary Dependencies**: 沿用既有 huggingface-hub 與 rag extra：Chroma 1.5.9、Sentence Transformers 6.2.0、產品 lock 的 torch／transformers；Windows CPU wheel。argparse、hashlib、pathlib、subprocess、json 等標準庫；不新增直接依賴、框架或修改鎖檔。

**Storage**: 既有兩個 external_content 目的地；模型 payload＋來源 receipt；包維持 manifest.json＋完整 chroma/。同父目錄私有 staging／backup／排他 lock directory；不改 .env／憑證庫。

**Testing**: pytest 離線 fake Hub／encoder、真實 Chroma 小資料可行性探針、CLI subprocess、故障注入／路徑保護、來源原文重現、wheel／base import；真實模型下載與整合採明確 opt-in。最後完整 Ruff／format／mypy／pytest／lock gate。

**Target Platform**: 本機 Windows／Python 3.12。Linux／macOS 依本規格不安排實測，保留未驗證限制；程式仍使用可攜 API，CI 不變。

**Project Type**: 既有 Python application 的兩個離線 CLI 模組；不是新 App、Tool、服務或 HTTP API。

**Performance Goals**: 固定流程兩次手動呼叫；同完整 revision 不下載；產包零網路。切段固定 policy v1、目標 400 content tokens／約 50 overlap、含特殊 tokens 實際總數 <=512；不承諾未量測下載／建置時間與 RAM。

**Constraints**: 固定 revision、唯一本機文件、原文連續切片、精確版本／hash、無 dotenv／私密快取、僅公開模型匿名下載、禁止 runtime indexing。相同輸出拒絕並行；不得用私有 SDK／Chroma API 或修改 loader 來通過檢查。

**Scale/Scope**: 兩個使用者入口、一份文件、一個集合、一套編碼模型；不增加校準器、格式轉換、PDF／Word／OCR、上傳頁面或多文件管理。

## Constitution Check

*GATE: Phase 0 前檢查，Phase 1 後重新檢查。*

| 原則 | 設計前 | 設計後與證據 |
|---|---|---|
| SDK／架構相容 | PASS | 不碰 SDK internals、即時迴圈或 Tool；模型邏輯只做保留語意的共用抽取，004 regression 必跑 |
| 最小／可維護 | PASS | 兩個實際 CLI＋重複使用的發布／模型邊界；不新增通用排程器或交易服務 |
| 錯誤／日誌 | PASS | 固定錯誤碼、中文 CLI 摘要、例外類別；原文／向量／憑證不進診斷 |
| 必要測試／gate | PASS | SC 對應單元／故障／真實 reader 驗證；缺素材不得偽造 pass |
| 人工／貢獻流程 | PASS | 延續個人客製化，不代開上游 PR；若要上游，另走 issue／人工審閱 |
| 依賴／平台／文件 | PASS | 沿用 lock；README 同步；架構圖實作時編輯 Mermaid 再生成；不改受保護文件／CI |

無憲章豁免。尚未執行的模型與索引驗證是實作 gate，不是本計畫已取得的測試結果。

## Project Structure

### Documentation (this feature)

```text
specs/005-prepare-rag-assets/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── preparation-cli.md
│   ├── model-receipt.md
│   └── model-receipt.schema.json
└── checklists/requirements.md
```

`tasks.md` 留給下一個 speckit-tasks，本輪不產生。

### Source Code (repository root)

```text
src/reachy_mini_conversation_app/
├── download_document_model.py     # 公開下載 CLI，含匿名 Hub 預檢／下載流程
├── build_document_package.py      # 公開離線 CLI，輸入與流程協調
├── document_assets.py             # stdlib 路徑／receipt／排他發布與安全狀態
├── document_model.py              # 從 worker 抽取共享模型檢查／載入／encode
├── document_prepare_worker.py     # 模型驗證／建置／包驗證的受控子程序
├── document_model_receipt.schema.json # 隨 wheel 交付，與本功能 receipt schema 一致
├── document_worker.py             # 重用 document_model，既有讀取語意不變
└── document_manifest.schema.json  # 004 合約不變

tests/
├── test_download_document_model.py
├── test_build_document_package.py
├── test_document_assets.py
├── test_document_model.py
├── test_document_prepare_worker.py
└── test_document_worker.py        # 保留既有 reader 回歸
```

**Structure Decision**: 使用 `python -m ...` 入口，不增加薄 wrapper 或 console entry points。兩個公開 CLI 及共享 stdlib 模組不 import config／core_tools／main，避免 dotenv、Tool registry 與機器人初始化。重型 imports 僅在明確呼叫的 worker／模型模組。CLI help 與普通 App import 不載入 inference stack。

## Phase 0 — Research conclusions

詳見 [research.md](research.md)。決策已定：安全 revision 預檢、精確 payload allowlist、可核對 receipt、匿名專用 cache、原文 offset 切片、公開 Chroma close、新程序驗證、同父目錄發布與手動殘留恢復。沒有未解的使用者選擇；不把未證實的 flush／效能寫成已通過。

## Phase 1 — Design

### 1. 模型下載與共用編碼

下載入口要求 `--revision`，先核對目的地安全性並取得模型排他鎖，再檢查已有完整同版本 receipt；成功即零網路返回。其餘先確認替換授權，再以固定公開 endpoint、token=False 取得該 SHA metadata，確認 resolved SHA 及小型配置／安全權重存在後才下載大型檔。呼叫者明確禁止網路時不自行解除限制。

下載 cache 與乾淨 payload 分開。只發布合約列出的必要常規檔案，不攜帶 .cache/huggingface、symlink、bin／pt／pickle 或 Python。receipt 的 inventory 不含自己；包 embedding.files 另枚舉模型根所有檔案，包含 receipt 的實際 hash，避免自我 hash。

receipt schema 以 package resource 隨 wheel 交付，沿用現有 *.schema.json package-data 規則；安裝後不依賴 specs checkout 或遠端 schema，wheel 測試核對與設計合約一致。

將既有 DocumentIndex 的模型配置／hash／load／encode 抽成 typed 公開共用元件；reader、downloader、builder 使用同一檢查。只抽取，不改安全權重限制、CLS／Normalize、CPU float32、threads 2／1、無 prefix、8192 上限、1024 維、reference／norm 容差。離線子程序設專用空 HF_HOME／cache、offline、telemetry off、SKIP_DOTENV；不依賴日常快取。模型驗證後關閉程序再發布，避免 Windows 檔案鎖。

### 2. 原文切段與來源定位

先 read_bytes 算來源 hash，再 UTF-8-sig 解碼；保留原始 CRLF／LF／單 CR、語法及空白。拒絕全無有效文字，不 render Markdown、不抓其他文件；v1 只輸出行／字元範圍，不解析章節，符合 spec 的可選章節條件。

固定 `source-window-v1`：fast tokenizer offsets 供提議切點，目標 400 content tokens、約 50 overlap；輸出始終是原字串連續 slice，不以 decode(tokens) 重建文字。每片以實際編碼含 special tokens 驗 <=512；超限確定性後退字元直到合規，不假設前綴 token 數單調。不切斷 CRLF；每次起點必須前進，完整覆蓋來源。空白等零長 offsets 區域以固定字元切點候選前進，再重新計數；不得因此漏掉空白區域。不提供合規 offsets 的 tokenizer 明確拒絕。ID 由文件 ID／版本、來源 hash、policy 與原字元範圍產生安全 digest。locator 使用 1-based `Lx:Cy-Lz:Cw`，end-exclusive；不因結尾換行虛增定位。

### 3. 產包、封存與發布 gate

builder 使用已驗證 receipt 與本機模型，在獨立 producer 中用公開 create_collection／add，embedding_function=None、cosine，原文／metadata／vectors 自行提供。實際版本含 +cpu 寫入既有 manifest；使用者提供門檻，固定非敏感 reference `這份文件主要說明什麼？`。不自動校準、不使用文件的指令當操作授權。

實作第一關：先以合成向量、真實鎖定 Chroma 測 1／2／3／奇數／多 batch 段落。候選設定 batch_size=2、sync_threshold=2、num_threads=2；不可設 1。必要時只在 producer 對最後一個真實 row 做一次相同內容的公開 update 以觸發尾批持久化，這是待實測的方法，不是已證明保證。不得加入假段落、刪 journal 或動私有表。若無法以公開 API 滿足全部合法小文件情境，停止實作並報限制，不放寬 004。

producer public close 並退出後才算候選 inventory。新的 verifier 使用完整工作副本、migrations=validate、既有 DocumentIndex。比對原包全檔 hash、全部 documents／metadatas／embeddings／count、工作副本所有持久索引 hash（包含未知必要檔，不只四個名稱）；query 及 close／退出後重驗。SQLite 允許記帳，但邏輯內容及 HNSW 不變。任何 journal 殘留／重建／replay 跡象／差異皆拒絕；不得以改 manifest hash 掩蓋。

候選 manifest 可暫填本機 target 及 snapshot_complete=true 讓既有 reader 驗證，這不算發布宣告。只有驗證通過才發布相同候選 bytes，正式列入本機 target；無驗證證據不得擴增平台。建置例外不等同讀取端損壞錯誤，對 CLI 回固定碼。

### 4. 路徑、鎖與中斷

預設根從模組所在預期 source checkout 及 pyproject／src 標記辨識，不從 CWD 推斷。wheel 無法辨識 checkout 時須明確傳入 output（builder 另傳 model），不寫 site-packages 或任意 CWD。

每個目的地排他 mkdir sibling lock，內記 operation UUID、目的地、stage／backup 相對名稱及階段；已存在即 busy，不根據時間／PID 自動刪鎖。stage／backup 同父目錄。模型發布與產包讀模型使用同一模型目錄鎖；builder 先鎖模型、再鎖包，任一 busy 即釋放本次鎖退出。這防止兩腳本互相破壞，不提供 App 行程鎖；部署者須先停止 App。

新目錄以完成 stage rename 發布；替換為 old→backup、stage→dest，普通錯誤恢復 backup。Windows 非空目錄不能靠 os.replace 達成整包原子替換。硬中斷保留 lock／backup／stage 與恢復指引；不加入自動 recover 命令，不自動根據 PID 判斷已停。人工確認沒有準備程序後，依已核對操作記錄恢復舊目錄或完成新目錄，再清理該次自有殘留；不得盲刪 lock 或遞迴刪任意目的地。

操作前／發布前重驗解析後路徑、所有祖先 link／junction、來源／模型／output 重疊及根目錄／專案保護目錄。拒絕不可安全判斷的情況。預設 sibling 殘留新增狹窄 .gitignore 規則；自訂目的地須在 repo 外或已被 Git 忽略，不自動編輯使用者 Git 設定。

### 5. Validation and handoff

先通過 Chroma 持久化可行性 gate，再做兩 CLI happy paths／離線驗證／兩次重現／至少八類故障與中斷。測 no-config/no-key/no-model 的一般 App 與 CLI help；spy 驗證產包零網路、相同已就緒模型零下載；source／model hash、sentinel 日誌、cwd／路徑及檔案鎖負向案例。至少五份文件驗 SC-002，不以語意品質取代原文核對。

真實安全 revision 由部署者明確提供；模型下載／重型整合採 opt-in，沒有適合 snapshot 時記未執行，不自選 PR。無雲端／相機／記憶／機器人。Windows gate、普通／rag wheel 與 004 模型抽取回歸後，更新根 README 與 Mermaid 來源並生成 SVG。005 完成不自動勾選 004 T026／T040～T042。

## Complexity Tracking

無憲章違規。新增程序只處理重型離線工作與釋放資源；發布記錄只處理兩個目錄的已知操作，不發展為通用工作／交易框架。
