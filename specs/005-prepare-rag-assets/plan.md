# Implementation Plan: RAG 模型下載與單文件離線產包

**Branch**: `feat/005-prepare-rag-assets` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

**Input**: `specs/005-prepare-rag-assets/spec.md`

## Summary

增量更新既有兩個手動CLI：下載腳本以明確角色分別準備固定 BGE-M3／BGE-base，各自獨立驗證發布；產包腳本以單一 UTF-8 TXT／Markdown、可選人工別名、完整本機雙模型及明確選取的版本化方案，產出 [004 v2 包](../004-single-document-rag/contracts/index-package.md)。共三次手動呼叫；不提供一次準備雙模型的彙總流程。

所有章節切段／來源脈絡、文件向量、BM25詞頻／DF／長度／平均長度與持久索引均離線預建。發布前新程序以新版reader執行完整混合檢索／重排並核對不變性；App不補建、降級或轉換v1。設計基線（2026-11-09）的程式當時仍為v1；後續實作與實際驗收狀態以 [quickstart](quickstart.md) 最新日期紀錄為準，不以設計文字宣稱通過。

固定安全權重revision，無bin轉換、PR／模型fallback；0.58是使用者選定方案的後置實務上限，無須品質合格校準證明，也不宣稱新文件已校準。原包／來源／模型保護及發布後清理exit8保持不變。

## Technical Context

**Language/Version**: Python 3.12；現代型別、strict mypy；不新增 Any／cast／PEP 695／future annotations／ignore。

**Primary Dependencies**: 沿用既有 huggingface-hub 與 rag extra：Chroma 1.5.9、Sentence Transformers 6.2.0、產品 lock 的 torch／transformers；Windows CPU wheel。argparse、hashlib、pathlib、subprocess、json 等標準庫；不新增直接依賴、框架或修改鎖檔。

**Storage**: 三個 external_content 目的地（嵌入模型、獨立重排模型、索引包）；各角色 payload＋v2 receipt；包為manifest.json＋完整chroma/＋retrieval/chunks.jsonl及bm25.json。同父目錄私有 staging／backup／排他 lock directory；不改 .env／憑證庫。

**Testing**: pytest 離線 fake Hub／encoder、真實 Chroma 小資料可行性探針、CLI subprocess、故障注入／路徑保護、來源原文重現、wheel／base import；真實模型下載與整合採明確 opt-in。最後完整 Ruff／format／mypy／pytest／lock gate。

**Target Platform**: 本機 Windows／Python 3.12。Linux／macOS 依本規格不安排實測，保留未驗證限制；程式仍使用可攜 API，CI 不變。

**Project Type**: 既有 Python application 的兩個離線 CLI 模組；不是新 App、Tool、服務或 HTTP API。

**Performance Goals**: 兩次模型準備加一次產包，共三步；同完整角色／revision重用零網路，產包及驗證零網路。chapter-source-v1切段目標300 tokens、重疊30、標題64／別名48 tokens、嵌入輸入最多512；BGE-base pair512、batch4、CPU float32。準備時間／RAM不作未量測承諾。004固定50題／五秒成功率只作觀察，十秒查詢期限與退役安全仍保留；005產包時間不等同004查詢期限。

**Constraints**: 固定 revision、唯一本機文件、原文連續切片、精確版本／hash、無 dotenv／私密快取、僅公開模型匿名下載、禁止 runtime indexing。相同輸出拒絕並行；不得用私有 SDK／Chroma API 或修改 loader 來通過檢查。

**Scale/Scope**: 兩個使用者入口、一份文件、一個集合、一套嵌入加重排模型；不增加校準器、格式轉換、PDF／Word／OCR、上傳頁面或多文件管理。

## Constitution Check

*GATE: Phase 0 前檢查，Phase 1 後重新檢查。*

| 原則 | 設計前 | 設計後與證據 |
|---|---|---|
| SDK／架構相容 | PASS | 不碰 SDK internals、即時迴圈或 Tool；沿用既有模型支援邊界，雙角色安全載入與004 v2共同設計，004 regression 必跑 |
| 最小／可維護 | PASS | 兩個實際 CLI＋重複使用的發布／模型邊界；不新增通用排程器或交易服務 |
| 錯誤／日誌 | PASS | 固定錯誤碼、中文 CLI 摘要、例外類別；原文／向量／憑證不進診斷 |
| 必要測試／gate | PASS | SC-001～007對應雙模型／新切段／BM25／故障／真實v2 reader；缺素材不得偽造pass，舊數字不當新版證據 |
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
│   ├── source-window-v1.md      # 舊版歷史契約
│   ├── chapter-source-v1.md     # 新版章節／別名／BM25
│   ├── preparation-cli.md
│   ├── model-receipt.md
│   └── model-receipt.schema.json
└── checklists/requirements.md
```

tasks.md已增量同步新版任務T043–T082與004依賴，並完整保留T001–T042歷史進度與證據。設計與任務同步不代表產品實作或新版驗收已完成；本次狀態文字修正不變更任何任務勾選。

### Source Code (repository root)

```text
src/reachy_mini_conversation_app/
├── download_document_model.py     # 公開下載 CLI，含匿名 Hub 預檢／下載流程
├── build_document_package.py      # 公開離線 CLI，輸入與流程協調
├── document_assets.py             # stdlib 路徑／receipt／排他發布與安全狀態
├── document_model.py              # 既有模型支援擴充角色／安全檢查／encode／raw rerank
├── document_prepare_worker.py     # 模型驗證／建置／包驗證的受控子程序
├── document_model_receipt.schema.json # 隨 wheel 交付，與本功能 receipt schema 一致
├── document_scheme.json           # 固定選案參數、來源digest與已知限制
├── document_worker.py             # 與004協作新版reader，保留Tool／錯誤／生命週期介面
└── document_manifest.schema.json  # 實作時同步004 v2 schema

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

詳見 [research.md](research.md)。決策已定：安全 revision 預檢、精確 payload allowlist、可核對 receipt、匿名專用 cache、章節／別名原文offset切片、預建BM25與完整選案來源、公開 Chroma close、新程序驗證、同父目錄發布與手動殘留恢復。沒有未解的使用者選擇；不把未證實的 flush／效能寫成已通過。

## Phase 1 — Design

### 1. 模型下載與共用編碼

下載入口要求 `--role embedding|reranker`及`--revision`，角色固定模型ID／revision（見receipt合約），無角色或版本不合即失敗。先核對目的地安全性並取得模型排他鎖，再檢查已有完整同版本 receipt；成功即零網路返回。其餘先確認替換授權，再以固定公開 endpoint、token=False 取得該 SHA metadata，確認 resolved SHA 及小型配置／安全權重存在後才下載大型檔。呼叫者明確禁止網路時不自行解除限制。

下載 cache 與乾淨 payload 分開。只發布合約列出的必要常規檔案，不攜帶 .cache/huggingface、symlink、bin／pt／pickle 或 Python。receipt 的 inventory 不含自己；包embedding.files與reranking.files分別枚舉各模型根全部檔案，包含 receipt 的實際 hash，避免自我 hash。

receipt schema 以 package resource 隨 wheel 交付，沿用現有 *.schema.json package-data 規則；安裝後不依賴 specs checkout 或遠端 schema，wheel 測試核對與設計合約一致。

沿用既有document_model typed支援，增加角色分支，reader／downloader／builder共用安全檢查，不複製loader或加framework。嵌入維持CLS／Normalize、CPU float32、無prefix、8192模型上限／本方案512輸入、1024維及reference容差；重排使用既有ST CrossEncoder、原始Identity logit、CPU float32／pair512／batch4。PyTorch threads2／1於各工作程序入口設定一次，不重複呼叫inter-op設定。

離線子程序清除日常憑證／自訂endpoint，以專用空HF_HOME／cache、offline、telemetry off、SKIP_DOTENV執行。兩角色receipt驗證不同：嵌入有限normalized reference向量，重排固定非敏感配對的有限原始分數；不能把重排分數說成品質通過。模型驗證後程序退出才發布，避免Windows檔案鎖。v1 receipt不能冒充v2或另一角色；已有payload仍須使用者明確準備新格式，App不轉換。

### 2. 原文切段與來源定位

producer 子程序一次讀取來源 bytes，從同一緩衝區計算 hash、UTF-8-sig 解碼、切段與向量；保留 CRLF、LF、單 CR 與所有空白，不 render Markdown、不展開其他文件。fresh verifier 在發布前串流重算來源 hash 並比對身分／stat；不重新解碼／切段。若來源被修改或替換則拒絕發布，這是變更偵測，不宣稱阻止外部寫入。

固定 [chapter-source-v1](contracts/chapter-source-v1.md) 及004 v2契約：Markdown按真實ATX章節（排除fenced code假標題），保留前言／尾文；TXT無標題以單文件範圍按原始段落及長度切分。原始切片不重寫、300 token目標／30 token重疊、完整model_text最多512，長段後續續切而非丟字。tokenizer offsets與CRLF合法切點保留既有防護，ID包含策略／來源／範圍與脈絡身分，不沿用舊400／50視窗規則。

來源標題自原文取得；額外別名只用--aliases可選人工清單，逐項核對同文件ID／版本／原始bytes摘要、證據文字與適用章節範圍。無清單明示空清單，不自動擷取正文別名或生成同義詞。別名檔也納入來源快照／變更偵測與路徑保護。脈絡與原文分開；model_text及offset對照持久保存，引用只用原文。

producer預建固定tokenizer的BM25 TF／DF／長度／avgdl，寫retrieval/bm25.json，與chunks及Chroma row ID全集一致；同來源／別名／策略重建結果相同。保存ASCII字母數字／CJK二三字組版本、k1=1.2、b=.75、正IDF及unique query term規則，App不重建這些語料資料。

父 CLI 不讀全文作切段，也不建立 tokenizer／模型。純切段函式可留在 build_document_package，接受 typed tokenizer 介面，由 producer 呼叫；所有模型／tokenizer 載入與編碼只在內部 worker。模型驗證 worker 與 fresh verifier 仍各自獨立載入驗證。worker 寫 candidate receipt／manifest／collection，私有 IPC 只傳已驗證路徑、scalar metadata、狀態及摘要，禁止全文／chunks／vectors／模型物件；詳見 [CLI 合約](contracts/preparation-cli.md)。

### 3. 產包、封存與發布 gate

builder 使用已驗證 receipt 與本機模型，在獨立 producer 中用公開 create_collection／add，embedding_function=None、cosine，原文／metadata／vectors 自行提供。實際版本含 +cpu 寫入既有 manifest；必須明確傳入`--scheme bge-base-final-selection-20261109`，自動帶入完整固定參數與來源；不接受單獨`--max-distance`或逐項覆寫。固定非敏感reference `這份文件主要說明什麼？`。不自動校準、不使用文件的指令當操作授權。

既有2026-11-06真實Chroma小包已有歷史證據（見quickstart），新版仍需回歸：以合成向量、真實鎖定 Chroma 測 1／2／3／奇數／多 batch 段落。候選設定 batch_size=2、sync_threshold=2、num_threads=2；不可設 1。必要時只在 producer 對最後一個真實 row 做一次相同內容的公開 update 以觸發尾批持久化，這是已有小包證據但新版需再驗證的方法，不能當成v2已通過。不得加入假段落、刪 journal 或動私有表。若無法以公開 API 滿足全部合法小文件情境，停止實作並報限制，不放寬 004。

producer public close 並退出後才算候選 inventory。新的verifier使用完整工作副本、migrations=validate及004新版DocumentIndex，載入雙模型後執行exact dense／預建BM25／RRF／五候選重排／後置距離完整查詢；有界無命中可為正常結果，操作失敗不可發布。比對原包全檔 hash、全部documents／metadatas／embeddings／count及retrieval脈絡／BM25檔、工作副本所有持久索引 hash（包含未知必要檔，不只四個名稱）；query 及 close／退出後重驗。SQLite 允許記帳，但邏輯內容及 HNSW 不變。封存候選的待回放journal、重建／replay需求或持久索引差異皆拒絕；工作副本必要SQLite記帳須與文件／索引變更分開判定；不得以改 manifest hash 掩蓋。

候選 manifest 可暫填本機 target 及 snapshot_complete=true 讓新版reader驗證，這不算發布宣告。只有驗證通過才發布相同候選 bytes，正式列入本機 target；無驗證證據不得擴增平台。建置例外不等同讀取端損壞錯誤，對 CLI 回固定碼。

### 4. 路徑、鎖與中斷

預設根從模組所在預期 source checkout 及 pyproject／src 標記辨識，不從 CWD 推斷。wheel無法辨識checkout時須明確傳入output（builder另傳model及reranker-model），不寫 site-packages 或任意 CWD。

每個目的地排他 mkdir sibling lock，內記 operation UUID、目的地、stage／backup 相對名稱及階段；已存在即 busy，不根據時間／PID 自動刪鎖。stage／backup 同父目錄。模型發布與產包讀模型使用同一模型目錄鎖；builder將兩模型解析成規範路徑，拒絕同路徑／危險重疊，再依規範路徑穩定排序取模型鎖，最後取包鎖；任一busy即釋放本次已取得鎖退出，無等待佇列。這防止兩腳本互相破壞，不提供 App 行程鎖；部署者須先停止 App。

新目錄以完成 stage rename 發布；替換為 old→backup、stage→dest，發布前普通錯誤恢復 backup。Windows 非空目錄不能靠 os.replace 達成整包原子替換。硬中斷保留 lock／backup／stage 與恢復指引；不加入自動 recover 命令，不自動根據 PID 判斷已停。人工確認沒有準備程序後，依已核對操作記錄恢復舊目錄或完成新目錄，再清理該次自有殘留；不得盲刪 lock 或遞迴刪任意目的地。

操作前／發布前重驗解析後路徑、所有祖先 link／junction、原文／別名檔／兩模型／output重疊及根目錄／專案保護目錄。拒絕不可安全判斷的情況。預設 sibling 殘留新增狹窄 .gitignore 規則；自訂目的地須在 repo 外或已被 Git 忽略，不自動編輯使用者 Git 設定。

### 5. Validation and handoff

先通過 Chroma 持久化可行性 gate，再做兩 CLI happy paths／離線驗證／兩次重現／至少八類故障與中斷。測 no-config/no-key/no-model 的一般 App 與 CLI help；spy 驗證產包零網路、相同已就緒模型零下載；source／model hash、sentinel 日誌、cwd／路徑及檔案鎖負向案例。至少五份文件含無標題TXT、重複Markdown章節／前言／fence、空／合法／不合法別名驗SC-002，不以語意品質取代原文核對。

兩模型固定revision依已選案，角色由部署者明確指定；模型下載／重型整合採 opt-in，沒有適合 snapshot 時記未執行，不自選 PR。無雲端／相機／記憶／機器人。Windows gate、普通／rag wheel 與 004 模型抽取回歸後，更新根 README 與 Mermaid 來源並生成 SVG。005 完成不自動勾選 004 T026／T040～T042。

## Complexity Tracking

無憲章違規。新增程序只處理重型離線工作與釋放資源；發布記錄只處理每次單一目的地及已知模型讀鎖，不發展為通用工作／交易框架。

## 本次澄清後同步

已驗證 stage → 正式目的地 rename 成功就是發布界線。界線前普通失敗不改舊 payload bytes；若舊目錄已暫移 backup，先恢復原位置。Windows 替換不保證目的地路徑全程存在；硬中斷依操作記錄人工恢復。界線後清理失敗保留新版，`published=true`、exit 8，顯示「已發布，清理未完成」，不得自動 rollback、下載、產包或重試。來源文件在所有情境均不得由腳本修改。

Phase 1 後設計層級的憲章檢查仍 PASS：無新增依賴、架構例外或 loader 合約放寬。tasks.md已同步本輪v2／雙角色／章節別名／BM25／完整方案；產品實作與新版驗收仍未完成。狀態文字修正後再執行 speckit-analyze，確認跨文件一致性。

## 新版設定與004交接（2026-11-09）

選用方案固定BGE-M3 revision50f9396f75618b3389c1fd1068a1ff58dc7b5b26、BGE-base revision2cfc18c9415c912f9d8155881c133215df768a70；dense10與BM25正分10等權RRF60，完整五候選原始logit>=3.486859679222107、附加drop<=4、最多三段／2000字元，之後才套父向量cosine<=0.58；第一名超限整次無依據，附加超限刪除不補段／重排，不限同父章節／無群組分差。完整順序與schema沿用004，不另造第二份包schema。

把final-scheme.json／report.md的來源digest、完整選定參數與限制作為版本化方案的一部分隨產包程式交付，離線產包／App不依賴cache路徑。包內實際document摘要與歷史example來源摘要分開；200題均已曝光、84/100正例、2/100負例誤放行及127/131支持為原始觀察。0.58不是通用dense門檻或新文件已校準；288段、實驗別名不能硬編碼。取消品質選用門檻不取消禁止捏造、私密來源、十秒期限／取消及工程gate。

004 v2 reader、產品package schema與005 producer／receipt需協同實作；reader未就緒時005不得宣稱App可讀並發布。兩功能設計與增量tasks已同步；完成一致性分析後，依跨功能任務依賴進行實作。產品README／.env.example／Mermaid與SVG／wheel schema同步留待實作，本輪未改。
