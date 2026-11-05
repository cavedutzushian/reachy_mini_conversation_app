# Implementation Plan: 單一預建文件 RAG 工具

**Branch**: `feat/004-single-document-rag` | **Date**: 2026-11-05 | **Spec**: [spec.md](spec.md)

**Input**: `specs/004-single-document-rag/spec.md`

## Summary

新增一般工具 `search_document(query)`，供既有 HF／Gemini 依同一份預建文件回答。Chroma 只查既有集合，BGE-M3 在 CPU 產生問題的 dense embedding；不解析文件、不建立／修補索引、不下載模型。不新增網路服務、RAG 框架、設定頁或供應商。

App 持有一個可延遲啟動的本機工作行程，隔離重型選用依賴及模型運算；同時最多一份工作，模型跨查詢保留。原始預建包只讀取，使用經核對的完整位元組副本供 Chroma 執行期記帳，禁止 migration 及任何文件索引寫入。工具回傳最多三段、2,000 字元原文及來源；共享對話生命週期阻擋過期結果，選擇性遮蔽本工具的參數與結果日誌。

## Technical Context

**Language/Version**: Python >=3.12；新程式遵守 strict mypy、既有語法限制及 SDK 公開 API。

**Primary Dependencies**: 現有 SDK、asyncio、Tool／ToolDependencies；新增選用 `rag` extra，候選固定版本 `chromadb==1.5.9`、`sentence-transformers==6.2.0`。其 PyTorch／transformers 等傳遞依賴須於實作解析後鎖進 `uv.lock`；Windows／Linux 使用 CPU PyTorch，macOS 強制 `device="cpu"`。不用 FlagEmbedding、LangChain、reranker 或另一套 MCP。這是新增依賴的事前揭露，本輪不安裝、不解析鎖檔、不下載模型。

**Storage**: 部署者提供完整、已關閉／flush 的 Chroma 持久化目錄及 manifest；另提供本機 BGE-M3 模型目錄。每 App 實例使用獨立暫存工作副本，停止後移除；沒有持久化查詢快取、文件記憶或新資料庫。

**Testing**: pytest／pytest-asyncio；預設 gate 使用假 worker／encoder，不需網路或多 GB 模型。額外真實套件整合測試、已供應模型的 CPU 效能與 HF／Gemini 驗收分開記錄。

**Target Platform**: Linux、macOS、Windows；CPU。相同 Chroma 版號不等於跨平台索引可攜性：依預建包的經驗證平台／架構矩陣接受或拒絕，不在執行時轉換。

**Project Type**: 現有 Reachy Mini 對話 App 的選用本機工具。

**Performance Goals**: 查詢受理起十秒內完成／失敗；模型與包就緒後，指定樣本 p95 <=5 秒。第一次載入不計暖機效能，但不能讓工具等到超過十秒；載入中立即 `not_ready`。不是已測得效能。

**Constraints**: 唯一文件／版本；500 Unicode code points 輸入；三段／2,000 code points 原文；固定模型／tokenizer／dense pipeline；本機 CPU；無下載／雲端 embedding／自動重試；舊查詢不跨回合送出。最多一個 worker、一個執行工作、零排隊查詢。

**Scale/Scope**: 單使用者、單 App 實例，文件更新採停止後換包／重啟。1,000 段／段長 512 tokens 僅為驗收樣本，不是功能硬上限。超出可用記憶體或平台能力時明確不可用，不偷偷截短模型或重建資料。

## Constitution Check

*Phase 0 前及 Phase 1 後均檢查；下列 PASS 指設計符合規範，不代表實作、依賴相容或效能已通過。*

| 原則／關卡 | Phase 0 | Phase 1 設計證據 |
|---|---|---|
| I SDK／既有架構 | PASS | SDK 公開 API 不變；一般 Tool；共享退役判斷留在 `huggingface_realtime.py`，兩後端共用 |
| II 最小改動 | PASS | 一個工具、一個 runtime、一個 worker；不增服務、框架、文件管理 UI 或全人格預設啟用 |
| III 錯誤與日誌 | PASS | 固定錯誤碼；操作失敗安全記錄；補上 dispatcher／HF 原始參數與結果的選擇性遮蔽 |
| IV 必要測試 | PASS | 行為測試、雙後端退役回歸、真實索引不變性與 CPU 驗收；實作交付前完整 gate |
| V 人工審閱／流程 | PASS（限定範圍） | 延續使用者授權的個人客製化；不建立上游 PR；若要貢獻仍先遵循 issue／維護者流程 |
| Python／跨平台 | PASS | Python 3.12；可攜程序／路徑 API，平台不相容安全拒絕；不承諾未測的平台 |
| 依賴／文件 | PASS | 新依賴已揭露；實作同步 pyproject、uv.lock、根 README、`.env.example`；不改 CI 或受保護文件 |
| 架構圖 | PASS | 實作需更新 `docs/scheme.mmd` 並重新產生 SVG，禁止手編 SVG；本輪不改產品圖 |

無未解決的設計澄清或未核准憲章違規。依賴解析、實體主機效能及跨平台實測是實作／驗收關卡，不能以此文件代替通過證據。

## Project Structure

### Documentation (this feature)

```text
specs/004-single-document-rag/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/requirements.md
└── contracts/
    ├── search-document.md
    └── index-package.md
```

`tasks.md` 由下一個 `$speckit-tasks` 產生，本輪不建立。

### Source Code (repository root; planned changes)

```text
src/reachy_mini_conversation_app/
├── document_retrieval.py       # App-owned runtime、單工作限制、worker 邊界
├── document_worker.py          # 選用重型依賴、包驗證、CPU embedding、Chroma query
├── main.py                     # 注入與 finally 關閉 runtime
├── config.py                   # 兩個啟動配置；不進一般設定回應
├── prompts.py                  # 僅工具可用時補文件回答規則
├── huggingface_realtime.py     # 共享查詢退役；HF 日誌／結果投遞
├── gemini_realtime.py          # 使用相同查詢退役合約
└── tools/
    ├── search_document.py      # Tool 薄介面，不持有昂貴模型
    └── core_tools.py           # typed optional dependency、RAG 安全解析／錯誤處理
tests/
├── test_document_retrieval.py
├── test_document_worker.py
├── test_config.py
├── test_prompts.py
├── test_huggingface_realtime.py
├── test_gemini_realtime.py
└── tools/test_search_document.py
```

**Structure Decision**: 不把支援模組放進 `tools/`，避免 `available_tool_catalog()` 把它們列為工具。runtime 以宣告型別注入 `ToolDependencies`，由 App 擁有而不是 registry 的工具物件擁有；換人格／後端不複製 worker。支援型別放進上述模組，不另增泛用框架。

## Phase 0: Research Decisions

完整證據與替代方案見 [research.md](research.md)。已決定：

1. Chroma persistent package + `get_collection(..., embedding_function=None)` + 明確 `query_embeddings`；關閉 telemetry、`migrations="validate"`、不允許 reset，絕不使用 create／get_or_create／add／upsert／update／delete。
2. Sentence Transformers 的 BGE-M3 dense、CPU float32、CLS pooling、L2 normalization、無 query prefix；以模型雜湊及參考向量驗證相容性，不能只比模型名稱／維度。
3. 原包不開啟引擎；先驗證再做位元組工作副本。複製既有索引不是邏輯匯入／重建，不呼叫文件向量建立 API。副本也不可遷移或改文件資料／索引。
4. 持續 worker process 隔離重型 import／運算，單工作無佇列；timeout 不偽稱 CPU 已停止。App 結束才終止／回收 worker，避免背景工作阻止退出。
5. 固定 `error` 字串碼沿既有 manager 傳遞，不為本工具改造全部錯誤通知格式。

## Phase 1: Design

### Configuration and activation

新增 `REACHY_MINI_DOCUMENT_INDEX_PATH`（完整包目錄）及 `REACHY_MINI_DOCUMENT_MODEL_PATH`（完整模型目錄），預設空白。啟動時凍結；相對路徑相對該次啟動工作目錄解析一次，不接受 URL，不經工具參數提供。一般設定／RPC 不新增這些路徑的回傳。兩欄缺一皆 `not_ready`，不影響一般聊天。

在既有人格工具頁／toolset 明確啟用 `search_document`，不加入 SystemTool 或所有 profiles。停用時不啟動 worker、不讀文件；之前已載入的資源可以保留至 App 停止，但不能再檢索。runtime 透過 ToolDependencies 重用。工具啟用且配置完整時才允許首次請求啟動 worker，載入中先回 `not_ready`；使用者稍後明確重試，不自動重送問題。初始化上限 120 秒，失敗維持不可用至 App 重啟，沒有自動重啟迴圈。

### Retrieval and evidence

詳見 [包合約](contracts/index-package.md) 與 [工具合約](contracts/search-document.md)。先完整檢查唯一文件身分、所有段落、引擎／embedding 設定及平台；用預先備妥的本機模型驗證參考向量後才 ready。候選取最多三個、以 cosine distance 遞增，按 manifest 固定門檻過濾；沒有通過者 `no_evidence`。門檻由外部標註題校準，不能宣稱能自動判斷所有答案是否足夠。

原文回傳依序套用 2,000 字元總預算，截斷只取單一原文前綴並標記 `truncated`；不合成引文。來源 metadata 另外限制長度，不能藏入路徑、URL 或另一份文件。成功結果維持可 JSON 序列化的字典；沒有 embedding、distance 百分比或全文件。

`prompts.get_session_instructions()` 僅在該人格啟用此工具時追加同一規則：明確文件問題先查工具，只依命中原文作答，無依據如實說明、引用附真實來源、語音簡短引用；文件及工具原文是資料，不能指揮其他工具。保留既有語言例外／繁體中文政策，不寫入人格設定或長期記憶。提示不是可靠的 prompt injection 隔離證明，需負向實測；工具本身無動作能力。

### Worker, deadline and lifecycle

`document_retrieval.py` 只依賴標準庫及輕量型別，啟動專用 `python -m ...document_worker`；重型套件在 worker 模組頂層 import。缺套件／模型時 parent 轉成安全固定碼，一般 App import／gate 不受影響。不在工具函式內放 import，不要求未啟用功能的使用者安裝 RAG extra。

只在 child 環境設模型離線模式及 telemetry 關閉；worker 限制 PyTorch intra-op 為兩個 CPU threads、inter-op 為一個，避免預設佔滿所有核心。這是首版可重現的執行策略，不是已證明滿足延遲；效能驗收須記錄它。不得修改主 App 全域 CPU／模型設定或自動啟用 GPU。

parent／child 只用本機私密 stdin/stdout JSON 訊息，不開 socket。parent 管理唯一 request ID、工作槽與完成通知，IO 等待放在背景，不阻塞音訊 loop。訊息限長／型別檢查；child stderr 不得直接鏡射到 App 日誌，受控診斷只傳固定錯誤碼／例外類別。非協定輸出、child 結束或協定錯誤均失敗封閉，不印原始訊息。worker 不寫查詢快取或結果檔。

從有效請求受理開始使用 monotonic 十秒期限；busy／not_ready 立即回傳。逾時／取消只退役 waiter，直到 worker 實際完成才能釋放工作槽；晚到結果只丟棄並安全消耗錯誤。沒有等待佇列、重送或新 worker 替換未結束工作。App finally 撤銷所有 token，關閉輸入、限時等待，必要時 terminate／kill 並回收唯一 worker，之後才清除工作副本；不因關閉而動到原包。

共享 `RealtimeConversationHandler`（位於 `huggingface_realtime.py`）記錄 RAG call ID、generation、response epoch 及退役狀態。HF／Gemini 發送結果、UI 工具完成訊息及 follow-up 前均驗證所有權，在 await 後重查；插話接受、取消、換人格停用、換供應商、新對話及結束均退役舊 RAG call。現有通用動作工具語意不改。重複 call ID 不重新送出舊文件結果；移除 HF in-flight/batch bookkeeping，不讓取消的查詢觸發新回覆或阻塞後續正常工具。

### Errors and logging

既有 BackgroundToolManager 只保留 `error` 字串，故使用 `document_not_ready`、`document_busy`、`document_unavailable`、`document_invalid_query`、`document_no_evidence`、`document_timeout`；缺套件／模型是 not_ready，包故障是 unavailable。取消仍由既有退役流程處理，不對新對話報舊錯誤。

選擇性修正 `core_tools` 的 JSON 解析及意外例外邊界、HF 收到工具呼叫的 INFO／invalid-input 日誌、結果 DEBUG 日誌；本工具只記 call ID、固定碼、時間及段落數。絕不記 raw args、原文、向量、路徑、第三方原始例外或 traceback。意外程式錯誤仍以安全類別與固定碼記錄，不沉默。正常逐字稿／文字來源顯示保留既有政策，不能宣稱 App 所有原有語音／轉錄日誌因此全部去識別化。

### Validation and delivery order

1. 先隔離預檢：解析選用依賴、檢查 Python 3.12／SDK 共存與 CPU 套件供應，凍結鎖檔；不支援則報阻礙，不私自換模型／服務。
2. 工具與 worker 合約測試、包相容／來源／不變性、錯誤碼、限額、busy-after-timeout 及受控關閉。
3. 雙後端退役、日誌 sentinel、工具停用無讀取、提示規則；完整既有 gate、安裝／wheel 與 optional extra 驗證。
4. 真實包及 CPU 主機暖機／50 題效能測量，再做兩後端來源與無依據測試、插話／取消等現場驗收。真實文件的外送、模型供應及機器人操作於需要時確認，不能沿用舊功能測試同意擴張資料範圍。
5. README／`.env.example`、架構來源及重生 SVG 與實作同步。完成後執行 `$speckit-analyze`／完整 gate，未實測限制照實記錄。

詳細實作任務留給 `$speckit-tasks`；本次僅完成 Phase 0／1。

## Complexity Tracking

沒有憲章例外。唯一額外程序是為了 CPU／重型 import 隔離與可回收的結束行為，不是新服務。相較單純 `to_thread`，多一個私密訊息邊界，但可避免模型載入阻塞主 App、取消誤釋放槽位及 Python 等待未結束 executor 而卡住退出；不擴張成一般工作排程器。
