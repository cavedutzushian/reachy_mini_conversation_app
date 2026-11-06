# Tasks: RAG 模型下載與單文件離線產包

**Input**: `specs/005-prepare-rag-assets/` 的 spec、plan、research、data-model、contracts 與 quickstart。
**Branch**: `feat/005-prepare-rag-assets` | **Date**: 2026-11-06
**Prerequisites**: 依 2026-11-06 最新 plan／data-model／CLI 與 [source-window-v1](contracts/source-window-v1.md) 重新同步；004 v1 包與 reader 拒絕條件不變。
**Tests**: 依 spec 的驗收情境／SC、plan 的明確驗證要求及專案憲章產生必要測試；先驗失敗再實作，不為每個薄函式另寫鏡像測試。
**Organization**: Setup → Foundation → US1(P1) → US2(P1) → US3(P2) → Cross-cutting。依 quickstart.md 的實際證據更新；38／42 完成，真實素材與整體結案仍待驗，核取方塊不代表規格品質審查結果。

## Format and paths

每項為 `- [ ] Tnnn [P?] [USn?] 說明及檔案路徑`。`[P]` 僅表示在所屬階段前置完成後，可處理不同檔案的工作；不是跳過前置或授權啟動代理。相同模組的實作依序進行，現有檔案只作必要修改。

## Phase 1: Setup

**Purpose**: 確認既有環境、資產範圍與隔離位置，不下載權重或建立日常文件索引。

- [X] T001 讀 `AGENTS.md`、`CONTRIBUTING.md`、`.specify/memory/constitution.md` 及本功能全部設計；核對 Python 3.12、產品 lock 與基線 gate，把環境、個人客製化範圍及既有結果記入 `specs/005-prepare-rag-assets/quickstart.md`；不代開上游 PR、不改 requirements checklist 標記。
- [X] T002 在 `specs/005-prepare-rag-assets/quickstart.md` 記錄隔離測試策略：所有合成素材放 `cache/005-prepare-rag-assets/`，沿用既有 rag／dev 環境與鎖檔；不讀日常 `.env`、私人 HF cache／憑證或啟動 App。真實下載須部署者提供信任的安全 revision 及明確測試範圍；未供應只阻擋真實素材驗收，不阻擋離線實作；Linux／macOS 不安排實測。
- [X] T003 在 `.gitignore` 補兩個預設目的地的狹窄 sibling stage／backup／lock 忽略規則，保留既有正式素材忽略項；於 `tests/test_document_assets.py` 驗證預設殘留被忽略，不新增會隱藏產品原始碼的廣泛規則。

## Phase 2: Foundational — 阻擋故事實作的共用邊界

**Purpose**: 先證明真實引擎可行性，再建共用來源驗證、CPU encoder、路徑與發布邊界。

- [X] T004 在 `tests/test_document_prepare_worker.py` 建立明確選用、只需真實鎖定 Chroma 及合成 normalized 1024 維向量的獨立程序探針，覆蓋 1／2／3／奇數／超過 API batch／最後餘一段；公開建集合／add／close 後新程序驗原包 hash、所有 row 邏輯／向量／count 與副本所有持久 HNSW hash；fixture 不使用 BGE 或文件，不寫日常路徑。
- [X] T005 執行 T004，在 `specs/005-prepare-rag-assets/quickstart.md` 留真實結果與可用公開操作順序；候選 `batch_size=2`、`sync_threshold=2`、`num_threads=2`、cosine，不能設 1。必要時實測一次相同真實 row 的公開 update 能否完成尾批；不得假段落、刪 journal、私有 API／表或改 reader。任何合法小包無法封存就停止後續實作並回報，不把猜測或 skip 算通過。
- [X] T006 [P] 在 `tests/test_document_assets.py` 先寫 receipt／預設根／路徑／排他鎖／基本發布測試：不同 CWD 預設一致、wheel 無 checkout 要明確路徑、根目錄／重疊／祖先 link／junction／Windows 別名拒絕，既有 output 未授權不覆寫、發布前普通 rename 失敗保留或恢復舊版。先覆蓋 stage→destination 成功後清理失敗保留新版、exit 8 的基本行為，完整矩陣留 T030；測 schema 與額外語意規則，不靠私有 helper 名稱斷言。
- [X] T007 [P] 在 `tests/test_document_model.py` 及 `tests/test_document_worker.py` 寫模型共用抽取回歸：CPU／安全權重／local-only／無 remote code、模組與版本／hash／reference 不符拒絕、encoder 輸出與 reader 一致，且一般 App／light runtime import 不載入 torch／Chroma／ST。
- [X] T008 在 `src/reachy_mini_conversation_app/document_assets.py` 建 typed 模型要求／receipt／輸入驗證與路徑解析，並新增隨包 `src/reachy_mini_conversation_app/document_model_receipt.schema.json`，與 `contracts/model-receipt.schema.json` 相同。逐項落實「repo_id 固定 BAAI/bge-m3；revision 為 40 位小寫 hex，無預設」、「replace 為明確布林；預設 false」、resolved_revision 相等、schema_version=1、files 路徑唯一／size_bytes >=1／SHA-256 64 小寫 hex、UTF-8 無 BOM／重複 key／NaN／Infinity 且 <=16 MiB、未知欄位拒絕；payload 精確十檔為 config.json、config_sentence_transformers.json、modules.json、sentence_bert_config.json、1_Pooling/config.json、sentencepiece.bpe.model、special_tokens_map.json、tokenizer.json、tokenizer_config.json、model.safetensors。receipt inventory 排除自己，實際根只能 payload＋receipt，不接受額外檔案或連結；schema 只解析內嵌 $defs。
- [X] T009 將 `src/reachy_mini_conversation_app/document_worker.py` 的重複模型驗證／load／encode 抽至 `src/reachy_mini_conversation_app/document_model.py` 並重用，保留 CPU float32、dense 1024 維 finite／非零／L2 norm 誤差 <=1e-4、CLS／Normalize、threads 2／1、空前綴、8192 上限及 reference cosine 差距 <=1e-5；實際 ST／torch／transformers 完整版號含 local suffix 比對。在同一模型模組提供 worker 使用的 typed tokenizer adapter，回傳未截斷／不含特殊 tokens 的 offsets 及實際含特殊 tokens 的 count；不讓輕量 CLI 載入 tokenizer。頂層重型 imports 只在受控模組，不能放寬 004 合約或新增 Any／cast／ignore；跑 T007 與既有 worker 回歸。
- [X] T010 在 `src/reachy_mini_conversation_app/document_assets.py` 實作共用路徑與基本發布：checkout 標記辨識、明確相對參數按 CWD 解析；同父目錄排他 mkdir lock、stage／backup，「operation_id：隨機 UUID；kind=model／package；本次 owner PID 僅診斷，不能用來自動授權清理」，「destination_name、stage_name、backup_name：已核對父目錄內的 basename，不接受 `..`／絕對路徑／link」。落實「locked → preparing → validating → validated → backed_up（僅替換）→ published → cleaning」；stage→destination rename 成功即發布界線，之前普通失敗恢復 backup／舊 payload bytes 不變，之後清理失敗保留新版並回 exit 8，不自動回復或重跑。Windows 不保證目的地路徑全程存在；不以 os.replace 假定非空目錄原子替換，不按 PID／時間破鎖。預設根不落 site-packages／任意 CWD，自訂 repo 內未忽略輸出拒絕。
- [X] T011 在 `src/reachy_mini_conversation_app/document_prepare_worker.py` 與 `src/reachy_mini_conversation_app/document_assets.py` 建 typed 私有子程序邊界：request 僅模型驗證／producer／fresh verifier operation、已驗證 source／model／stage／副本路徑及 scalar metadata；result 僅固定狀態／錯誤碼、來源／檔案 digest、count、安全結果。IPC 禁止全文／chunks／向量（含 reference embedding）／model／tokenizer／pickle；worker 寫 candidate receipt／manifest／collection，父 CLI 只核對摘要／路徑並持鎖發布。全部 inference／tokenizer 僅在 worker，模型驗證與 fresh verifier 可各自載入，不開 socket／dotenv／SDK。啟動前專用 HF_HOME／cache、offline／telemetry off／SKIP_DOTENV，確認子程序退出才發布／清理。「status 為 completed／already_ready／failed／busy／recovery_required」、「published 為必填布林」、「ready（bool 或 null）」：completed 為 published=true／ready=true，already_ready 為 published=false／ready=true，發布前失敗／busy 為 published=false／ready=null；發布後清理不全 published=true／ready=true、status=recovery_required、code=cleanup_incomplete、exit=8，附自有殘留／人工指引，不能當 completed 或自動重跑。

**Checkpoint**: T005 必須有真實合成索引證據，T006～T011 通過相關離線回歸。Foundation 後才進入故事實作；缺使用者模型不應阻擋本階段。

## Phase 3: US1 — 下載一次即可離線使用指定模型 (P1 / MVP)

**Goal**: 一次手動下載供應正確模型，重跑同完整版本零網路，無索引也能獨立驗證。
**Independent Test**: fake Hub／encoder 走完整公開 CLI；真實安全 revision 明確 opt-in 後再做斷網 load／encode，不需文件、provider 或機器人。

### Tests

- [X] T012 [P] [US1] 在 `tests/test_download_document_model.py` 寫 CLI／Hub 合約測試：revision 必填且 40 小寫 hex、拒絕 main／tag／model／URL／endpoint，checkout／明確 output／replace 行為、中文輸出與 exit codes；固定公開 endpoint、token=False、精確十檔 allowlist、獨立 cache、先小配置後大檔，缺 safetensors／resolved SHA 不同即拒絕，無 PR fallback／bin 轉換／私人 cache／dotenv 讀取。
- [X] T013 [P] [US1] 在 `tests/test_document_prepare_worker.py` 補模型角色的離線檢查：載入前後檔案 hash 不變、必要檔缺失／safe weights／模組／runtime／reference 壞值拒絕、子程序不外連／不讀私密設定，權重釋放後才可發布。以程序與 IPC spy 確認只有 worker 載入模型／tokenizer、receipt／reference 向量寫 candidate 而非回傳父 CLI；例外內容 sentinel 不洩漏。

### Implementation

- [X] T014 [US1] 在 `src/reachy_mini_conversation_app/download_document_model.py` 實作真正的模組 CLI（不加薄 wrapper／console entry point），沿用 `contracts/preparation-cli.md` 參數；--help 不需 rag／模型。先路徑安全與模型鎖，再核對現有同版本 receipt／payload；已完整則 already_ready，零 metadata 查詢／下載／覆寫；不同或損壞目的地未 replace 即拒絕。
- [X] T015 [US1] 在 `src/reachy_mini_conversation_app/download_document_model.py` 實作匿名固定 revision metadata／小配置預檢及 payload 下載；尊重呼叫者明確的 offline 禁令，核對可取得的 LFS／Git 檔案識別及本機 hash。專用傳輸 cache 與乾淨 stage 分開，只複製十檔正常 bytes，不攜帶 .cache/huggingface／symlink／bin／pt／Python，不製造來源未提供的 2_Normalize 配置。
- [X] T016 [US1] 在 `src/reachy_mini_conversation_app/document_prepare_worker.py` 實作共享 encoder 的模型驗證，固定 reference「這份文件主要說明什麼？」及「1024 維 normalized finite embedding」；由該 worker 呼叫 `src/reachy_mini_conversation_app/document_assets.py` 寫 candidate model-receipt.json，reference 向量不經 IPC。payload 清單不含 receipt，自有 runtime 使用實際完整版本；模型驗證與前後 hash 核對後正常退出，不以欄位宣告替代真實檢查。
- [X] T017 [US1] 在 `src/reachy_mini_conversation_app/download_document_model.py` 串接完整下載→離線驗證→程序退出→共用發布與結果處理；依 CLI 合約處理 0／2／3／4／5／6／7／8／130 及固定錯誤碼，中文 CLI 可顯示指定路徑／revision，診斷不含 provider body／token／私密例外。不改 .env／App 設定或自行安裝依賴。
- [X] T018 [US1] 跑 T012～T017 的正常／重用／中斷／缺檔／寫入失敗回歸，於 `specs/005-prepare-rag-assets/quickstart.md` 記 fake 驗證與限制，確認不需要索引或 US2 即可單獨展示 US1；不得宣稱已下載真實安全模型。
- [ ] T019 [US1] 在 `tests/test_download_document_model.py` 建立明確 opt-in 真實指定安全 revision 驗收並依授權執行：下載、離線載入、receipt 與模型完整性、同完整版本重跑零下載；於 `specs/005-prepare-rag-assets/quickstart.md` 記 revision／主機／runtime／digest／原始結果。未提供信任 revision 或下載範圍保持未完成，不自選未合併 PR；不阻擋其他故事的離線工作。

**Checkpoint**: T018 是離線 MVP，T019 才是實際模型證據；兩者分開，不以 fake 代替下載成功。

## Phase 4: US2 — 將唯一文字文件產成完整包 (P1)

**Goal**: 只用既有本機模型，取得可核對原文／定位、符合 004 的完整包。
**Independent Test**: 可用可信 receipt／受控 encoder fixture 單獨開發，不依賴下載網路；實際交付仍需明確提供的真實模型。

### Tests

- [X] T020 [P] [US2] 在 `tests/test_build_document_package.py` 寫輸入與 `specs/005-prepare-rag-assets/contracts/source-window-v1.md` golden 測試：唯一常規 txt／md／markdown case-insensitive、UTF-8／BOM、CRLF／LF／CR 保留，拒絕無有效字母／數字、目錄／glob／link／URL／多輸入及重複 --input；原始 bytes 含 BOM hash 不變，安全 identifier <=128、「title 為既有 160 code point 限制」、「max_distance 有限 [0,2]，必須明確提供」。用正式常數驗 ABCDEFGH→[0,4)／[3,7)／[6,8)、CRLF→[0,3)／[2,6)／[5,8)、600 字元零 offset→[0,510)／[510,600)；驗非單調 514→600→10 必須逐點後退。另驗映射筆數／範圍／單調性錯誤、n<=50、零寬 overlap、CRLF overlap 到 end、最短片仍超限、EOF 空白、超長單行、原文完整覆蓋與兩次原文／ID／順序／locator 一致；語法／連結／指令不執行，假 tokenizer 不當真實 BGE 證據。
- [X] T021 [P] [US2] 在 `tests/test_document_prepare_worker.py` 寫 producer／fresh verifier 合約測試：公開索引寫入只在 producer、embedding_function=None／cosine／單一 collection／來源；拒絕缺檔／journal／混合來源／hash／向量不符／replay 或 HNSW 改變，區分 SQLite 必要記帳與邏輯變更，不改 manifest 掩蓋。驗 producer 一次 bytes 讀取衍生 hash／text／chunks／vectors、初次讀取前後身分／stat 一致；來源修改／替換於 fresh verifier 最後串流檢查拒絕，不重 decode／tokenize。以 IPC／程序 spy 驗父 CLI 不讀全文切段／不載 inference、管道無內容或向量、worker 寫 candidate。測來源／模型及原包不變、所有 rows（非抽樣）及未知必要索引檔也受保護。

### Implementation

- [X] T022 [US2] 在 `src/reachy_mini_conversation_app/build_document_package.py` 實作模組 CLI 與輸入 metadata 驗證；預設 model／output 按 checkout，無 checkout 須兩者明確給出；相對明確參數按 CWD。先鎖模型再鎖包，任一 busy 釋放本次鎖退出；不 import config／main／core_tools、不讀日常設定，不自動抓模型或啟用 App。
- [X] T023 [US2] 在 `src/reachy_mini_conversation_app/build_document_package.py` 實作由 producer 呼叫的純切段函式及 TextSource／SourceChunk typed 邊界；只接受原字串與 typed tokenizer 介面，不 import inference 或建立 tokenizer。逐條實作 `specs/005-prepare-rag-assets/contracts/source-window-v1.md`：candidate_content_tokens=400、overlap_content_tokens=50、max_encoded_tokens=512、zero_offset_window_chars=512；剩餘 <=400 取 EOF，否則前 400 非零寬 offset 最大 end，無可前進 end 才用 512 字元 fallback。每片實際含特殊 tokens <=512、禁止截斷；逐個合法字元點後退，不假定 token 數單調，CRLF end 向左修正。重疊取 n−50 token 原文起點；零寬／n<=50／不前進／CRLF 向右修正後 >=end 則 next_start=end，不另造 fallback。落實「0 <= start < end <= len(text)」、「text：恰為 source.text[start:end]；不能從 token decode 重建」、ordinal 順序、全覆蓋／有限終止／EOF 不重複。ID 用確切 keys document_id／document_version／source_sha256／policy／start／end，sort_keys=true、ensure_ascii=false、separators=(',', ':') 的 UTF-8 JSON SHA-256，`c-`＋64 小寫 hex；locator 為「`L<first>-L<last>; chars[<start>,<end>)`；行號 1-based inclusive，字元範圍 0-based end-exclusive」，換行歸其結束的行，CRLF 合算一行，不解析章節／生成頁碼。
- [X] T024 [US2] 在 `src/reachy_mini_conversation_app/document_prepare_worker.py` 實作 producer：唯一負責初次來源 bytes 讀取、身分／stat、同緩衝區 raw hash／UTF-8-sig decode／切段／locator／文件向量，呼叫 T023 純函式與 worker 內 tokenizer adapter；不正規化 Unicode／行尾。使用 T005 已證明的公開 Chroma 操作及共用模型；row「id=chunk_id、documents=text、metadatas 僅 document_id／document_version／locator」，禁止假段落或其他文件。public close／程序退出後才取 inventory，原文／模型不改動；只回摘要，全文／vectors 不經 IPC。
- [X] T025 [US2] 由 `src/reachy_mini_conversation_app/document_prepare_worker.py` 呼叫 `src/reachy_mini_conversation_app/document_assets.py` 在 candidate 生成既有 004 v1 manifest：單文件／版本／集合、實際完整 engine／embedding runtime、source hash、完整 chroma files、model payload＋receipt 的 embedding.files／hash、非敏感 reference 及使用者門檻；receipt／manifest／collection（含 reference 向量）不透過 IPC 傳回父 CLI。重新枚舉 embedding.files，不直接採 receipt.files、不加未知欄位／自我 hash，不改 `src/reachy_mini_conversation_app/document_manifest.schema.json`。policy 只入準備操作記錄，不入 004 manifest。
- [X] T026 [US2] 在 `src/reachy_mini_conversation_app/document_prepare_worker.py` 實作獨立 fresh verifier：在完整副本以 migrations=validate／現有 DocumentIndex 全量開啟、query、public close／退出後驗所有 row documents／metadata／embedding／count、原包全 hash 及副本所有持久索引 hash；原檔 journal 或任何重建／replay 差異拒絕。最後串流重算來源 hash、比對 initial_identity／initial_stat，修改／替換拒絕發布，不再次 decode／tokenize，不宣稱阻止外部寫入。candidate 暫列本機 target／snapshot_complete 不等於發布；只發布相同已驗證 bytes，target 取本機 runtime_target，不能複製其他主機；父 CLI 確認 verifier 退出／摘要成功後才發布。
- [X] T027 [US2] 在 `src/reachy_mini_conversation_app/build_document_package.py` 串接 metadata／receipt 核對、獨立 producer／verifier 與共用發布；父 CLI 只協調路徑／scalar metadata／安全摘要，不讀全文切段、不載模型或 tokenizer，也不接收 chunks／vectors。全程 offline／專用 cache／telemetry off，父程序持鎖、子程序不能搬正式輸出；缺素材明確失敗，依 CLI 合約顯示中文結果、published／ready／exit codes，不校準或換模型，只顯示設定建議、不改 .env。
- [X] T028 [US2] 在 `tests/test_build_document_package.py`、`tests/test_document_prepare_worker.py` 執行至少五份合成文件（中文、英文、否定、表格、程式碼／連結）及兩次重現、來源 sentinel／zero-network 回歸，於 `specs/005-prepare-rag-assets/quickstart.md` 記 SC-002／SC-004／SC-006 證據；區分 fake encoder 與真實 Chroma，不宣稱模型／語意品質已通過。
- [ ] T029 [US2] 在 `tests/test_build_document_package.py` 建 opt-in 的真實本機安全模型＋五份固定無敏感文件產包／既有 reader 驗收，確認完整素材、原文／位置／不變性及零外連，於 `specs/005-prepare-rag-assets/quickstart.md` 記來源／receipt／包 digest、主機及原始結果。可用已驗證外部同等模型，不強制先做 T019 網路下載；缺素材保持未完成，不降低 004 驗證。

**Checkpoint**: T028 完成離線故事；T029 完成實際產包證據。US2 可用已準備模型單獨執行，不需要 US1 在線運作。

## Phase 5: US3 — 安全發布素材並交接給 App (P2)

**Goal**: 驗證完整跨腳本生命週期，已完成／未完成狀態清楚，發布前失敗保留舊版，發布後清理失敗保留新版並明確回報。
**Independent Test**: 使用受控子程序與自有 fixture 目錄測替換／中斷／鎖；不必下載權重或啟動 App。

### Tests

- [X] T030 [P] [US3] 在 `tests/test_document_assets.py` 增加分界故障矩陣：preparing／validating／validated／backed_up 前普通失敗恢復舊 payload bytes 與目的地；stage→destination 成功後，在 backup／stage／lock／operation record 清理或階段記錄注入失敗，必須保留新版、顯示「已發布，清理未完成」、status=recovery_required、code=cleanup_incomplete、published=true、ready=true、exit 8，且沒有 rollback／下載／產包／自動重試。分別測 hard interruption、記錄仍停舊 phase、發布前取消 exit 130／恢復失敗 exit 8 published=false、發布後取消清理 exit 8 published=true。驗 UUID、kind=model／package、basename 範圍、不依 PID／時間破鎖，原文件全部情境零修改；不要求 Windows 目的地 namespace 全程不變。
- [X] T031 [P] [US3] 在 `tests/test_download_document_model.py` 與 `tests/test_build_document_package.py` 增加真正跨程序 CLI 測試：不同 CWD／wheel explicit paths、同目的地競爭、模型發布對 builder 的鎖順序、輸出含既有路徑設定值而不寫 `.env`／一般設定／憑證；以 safe sentinel 檢查 stdout／診斷不含原文／向量／token／provider body，正常操作僅兩次手動啟動。

### Implementation

- [X] T032 [US3] 在 `src/reachy_mini_conversation_app/document_assets.py` 完成 T030 的發布／恢復／清理矩陣：old→backup、validated stage→destination 成功即發布，第二步前普通失敗復原舊版，恢復失敗留 recovery_required／published=false／exit 8。發布後階段記錄或清理失敗仍保留新版，status=recovery_required／code=cleanup_incomplete／published=true／ready=true／exit 8，禁止自動回復、下載、產包或重試。只清本次記錄與已核對父目錄內自有資料，保留精確殘留／hash 及人工指引；硬中斷時核對實際目錄而非僅信 phase，不加自動 recovery、不先刪舊版／盲刪 lock。
- [X] T033 [US3] 在 `src/reachy_mini_conversation_app/download_document_model.py`、`src/reachy_mini_conversation_app/build_document_package.py` 及 `src/reachy_mini_conversation_app/document_prepare_worker.py` 完成中斷傳遞／退出確認：未確認子程序釋放資源就保留狀態、不刪檔／發布；發布前 cancelled 且可安全恢復回 130，無法恢復回 8／published=false；發布後取消清理回 8／published=true／ready=true，保留新版與人工清理資訊，不假裝未發布或自動重試。不記原始 traceback／私密內容。
- [X] T034 [US3] 執行 `tests/test_document_assets.py`、`tests/test_download_document_model.py`、`tests/test_build_document_package.py` 的競爭／危險路徑／分界故障矩陣：至少八類 SC-003 發布前可處理失敗，原檔與既有 payload bytes 變更為零；另測發布後清理失敗保留新版、exit 8、不自動回復／重跑，不把「舊版零變更」誤套到已發布新版。所有情境來源文件零修改；Windows 自有檔案鎖／rename 失敗不停止其他程序，不操作日常 App。
- [X] T035 [US3] 在 `specs/005-prepare-rag-assets/quickstart.md` 留 US3 獨立驗證結果與人工恢復步驟、中文 exit 對照及未驗證限制；確認沒有 App 行程控制、runtime indexing、相機／記憶或供應商設定變更，不將 005 結果當成 004 整體結案。

## Phase 6: Polish & Cross-Cutting Validation

**Purpose**: 文件、包裝、實際證據與必要 gate；未完成素材驗收如實保留。

- [X] T036 [P] 更新根 `README.md` 的兩個實際模組命令、rag 前置、信任且含 safetensors 的固定 revision／main 不支援、已校準門檻、預設／明確路徑、固定切段／定位行為、替換前停止 App、恢復與錯誤碼。清楚區分發布前失敗／發布後保留新版但待清理 exit 8，後者不得自動重跑；不新增 README／docs Markdown，不自動改 `.env`。
- [X] T037 [P] 依兩支離線準備腳本的資料流更新 `docs/scheme.mmd` 並用既有 Mermaid 工具重新生成 `docs/assets/conversation_app_arch.svg`，視覺檢查下載／本機產包／既有 reader 的邊界；不手改 SVG、不改 CI。
- [X] T038 在 `tests/test_profile_paths.py` 的既有 wheel 驗證補兩 CLI 模組／worker／共用模型及 receipt schema 打包，核對 `src/reachy_mini_conversation_app/document_model_receipt.schema.json` 與本功能 schema 相同、安裝後不依 source specs／遠端 $ref、普通安裝與 --help 無 optional stack／dotenv／機器人初始化；無 checkout 時要求明確路徑、不寫 site-packages。
- [ ] T039 依 T019／T029 可取得的真實安全模型與 Windows 檔案操作證據，在 `specs/005-prepare-rag-assets/quickstart.md` 記完整兩步流程、至少五份文件、讀取／query／close 後不變性、已就緒重用、offline／並行／替換／中斷恢復結果及來源／模型／包 digest；未提供信任 revision 或實際素材，保留未完成。Linux／macOS 只列未測，不把 fake 或其他功能授權代替實際驗收。
- [X] T040 在 `specs/005-prepare-rag-assets/quickstart.md` 整理每項 FR／SC 的已取得證據、未完成／失敗／平台限制與實際命令，將「尚未實作」設計指引更新成實際行為但不虛構 pass；保留首次失敗，004 的實際 CPU／雙後端／現場驗收仍由原任務獨立處理。
- [X] T041 自審相關 `src/reachy_mini_conversation_app/`、`tests/`、`README.md`、`.gitignore` 與架構 diff，依 AGENTS 跑完整 Ruff check／format、strict mypy、`pytest tests/ -v`、`uv lock --check`，於 `specs/005-prepare-rag-assets/quickstart.md` 留結果；檢查 typed 公開 API／頂層 imports／SDK 公開 API／無新 ignore／未變 CI／沒有新依賴，尤其確認 004 模型抽取回歸。真實 Chroma 探針不可用缺 extra skip 冒充通過。
- [ ] T042 在 `specs/005-prepare-rag-assets/tasks.md` 與 `specs/005-prepare-rag-assets/quickstart.md` 逐項結案：只勾實際完成證據充分的任務；T019／T029／T039 或可行性 gate 未完成就保留整體未結案。不得修改 requirements checklist 來表示實作完成、不自動勾 004 待辦、不代開 PR。

## Dependencies & Execution Order

### Phase graph

```text
T001 → T002 → T003
  → T004 → T005（真實 Chroma 可行性，失敗即停止）
  → T006 / T007 → T008 → T009 → T010 → T011
  → US1: T012 / T013 → T014 → T015 → T016 → T017 → T018 → T019(opt-in)
  → US2: T020 / T021 → T022 → T023 → T024 → T025 → T026 → T027 → T028 → T029(opt-in)
  → US3: T030 / T031 → T032 → T033 → T034 → T035
  → T036 / T037 → T038 → T039 → T040 → T041 → T042
```

### Required ordering and exceptions

- T004／T005 是實作第一道 gate，不需要 BGE；新引擎探針不得改產品 lock 或 reader 來過關。T005 通過才開共用／故事實作，並在 T024 重用已證明的操作，不重新猜測 flush。
- T006／T007 皆依 T005，可在不同測試檔並行；共用模型與 worker 抽取、document_assets 的 schema／路徑／發布依序修改。
- 所有故事依 Foundation。建議按 US1→US2→US3 逐階段驗證；US2 若有可信外部同等模型，可在 Foundation 後獨立開發／測試，不依賴 US1 網路。因共享 worker／assets，不能兩故事同時修改這些檔案。
- T019 沒有核准 revision，仍可做 T020～T038 的離線實作；T029 缺真實模型，也可做不依賴素材的 US3／文件／wheel／gate。但這兩項保持未完成，不宣稱真實故事驗收通過。T039 需要完整 T019＋T029，才能驗證下載與產包的真實兩步交接。
- T030／T031 依兩 CLI 離線整合 T018／T028，不依真實模型；hard-crash 狀態與 ordinary rollback 的基礎行為不得拖到此時才開始保護舊資料，T010 已需具基本保護。
- T036／T037 依介面穩定 T035，僅不同文件可並行；T038 需要前面程式完成。T040／T041 遇真實素材缺項時仍可記錄部分結果、執行可做的 gate，不可跳過有新回歸的必要檢查。T042 只能記錄部分交付，不能在缺項時勾整體完成。
- T020 的假 tokenizer golden fixtures 先於 T023；T021 先於 T024～T027，來源最後核對與 IPC 邊界不可留待結案補上。T006／T010 已含發布界線基本保護，T030～T034 再擴充矩陣；不得到 US3 才修正已發布後 rollback。每個故事的測試先於對應實作。新 regression 先跑相關測試再必要 gate；沒有新改動或疑慮時不重複同一全套測試。測試啟動／素材處理須符合 T002 範圍。

### Parallel examples per story

| 階段 | 前置 | 可並行的不同檔案 | 後續接點 |
|---|---|---|---|
| Foundation | T005 | T006 assets 測試／T007 model＋reader 測試 | T008～T011 依序 |
| US1 | Foundation | T012 download CLI 測試／T013 worker 模型測試 | T014～T018 |
| US2 | Foundation，建議 T018 | T020 builder 輸入／切段測試／T021 worker 產包測試 | T022～T028 |
| US3 | T018、T028 | T030 assets 中斷測試／T031 兩 CLI 整合測試 | T032～T035 |
| Polish | T035 | T036 README／T037 Mermaid＋SVG | T038 之後 |

## Requirement and Evidence Coverage

| 規格 | 對應任務 |
|---|---|
| FR-001 手動兩入口／不動 App | T011、T014、T022、T031、T035、T038 |
| FR-002 固定安全 revision／匿名下載 | T002、T012、T015、T019 |
| FR-003 完整安全模型／receipt／已就緒 | T007～T009、T013、T016～T019 |
| FR-004 路徑／不寫設定 | T006、T010、T014、T022、T031、T038 |
| FR-005 單文件／UTF-8／不展開 | T020、T022、T023、T028 |
| FR-006 識別資訊／門檻／來源 hash | T020、T022、T023、T025、T028 |
| FR-007 原文切段／可重現定位 | T020、T023、T028、T029 |
| FR-008 本機編碼／零外連 | T009、T011、T016、T021、T024、T027～T029 |
| FR-009 既有 v1／完整包 | T008、T021、T025～T029、T038 |
| FR-010 真實封存／不變性／平台 | T004、T005、T021、T024～T026、T029、T039 |
| FR-011 替換／中斷／舊版保護 | T006、T010、T017、T027、T030～T035 |
| FR-012 危險路徑／不控 App | T006、T010、T020、T022、T031～T035 |
| FR-013 中文／固定碼／日誌 | T011～T018、T022、T027、T028、T031、T033 |
| FR-014 README／既有依賴與設定 | T001～T003、T035～T038、T041 |
| SC-001 兩步完整素材 | T019、T029、T031、T039 |
| SC-002 五份原文／定位核對 | T020、T023、T028、T029、T039 |
| SC-003 發布前八類保護／發布後待清理／來源不變 | T006、T012、T013、T020、T021、T030～T034、T039 |
| SC-004 零外連／零重下載 | T012、T015～T019、T027～T029、T039 |
| SC-005 真實 reader／索引不變 | T004、T005、T021、T026、T029、T039 |
| SC-006 兩次重現／日誌零洩漏 | T020、T023、T028、T029、T031、T039 |

## Implementation Strategy

1. 先確認 T005 真實引擎可行性，避免寫完才發現小文件無法滿足 004。probe 只用合成向量，不自行取模型／日常文件。
2. **MVP 為 US1**：共用基礎＋T012～T018 的下載／驗證／安全發布。fake 展示與 T019 真實模型驗收分開，不能把 fake 稱為可交付模型。
3. 加入 US2，使用既有模型獨立測試；原文與來源優先，不靠清理文字、放寬距離或換模型改善表面結果。US3 再完成跨腳本中斷／交接矩陣，不延後基本保護。
4. 最後文件／wheel／gate 與真實範圍逐項留證。安全 revision 未供應、真實包／模型或 Windows 驗收未完成就保持未結案；Linux／macOS 不要求重啟測試，不自動外送段落或控制機器人。

## Task Summary

共 42 項：Setup 3、Foundation 8、US1 8、US2 10、US3 6、Cross-cutting 7。已同步發布前／後失敗界線、published／ready／取消結果、worker／IPC 歸屬、來源最後核對與固定切段 golden fixtures。10 項 `[P]` 僅涵蓋不同檔案工作群。所有任務含連續 ID、checkbox 與具體路徑；只有故事階段標記 `[USn]`。本輪離線實作與 gate 已通過，證據見 quickstart.md；T019／T029／T039／T042 保持未完成，不宣稱真實安全模型下載、真實 BGE-M3 產包或整體結案。

## 實作進度（2026-11-06）

38／42 完成。T019 的測試入口已建立，但使用者指定的 `5617a9f61b028005a4858fdac845db406aefb181` 缺 `model.safetensors`，公開 metadata 與實際 CLI 均確認在權重下載前拒絕；未轉換 bin 或另選 revision。T029 的實際驗收入口亦已建立，但沒有合規本機模型，使用者確認尚未校準門檻；`example.md` 只確認 UTF-8／摘要，沒有產包。T039 因此未完成，T042 保留整體未結案。

requirements.md 維持原有 16／16；004 任務未更動；未啟動 App、雲端對話、相機、記憶或機器人。完整 gate 939 passed／19 skipped，另行明確執行的真實 Chroma 合成向量與假 encoder 產包結果不能當成真實 BGE-M3 證據。
