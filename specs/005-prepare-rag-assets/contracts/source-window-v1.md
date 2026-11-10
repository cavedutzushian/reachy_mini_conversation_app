# Contract: source-window-v1

**歷史合約（2026-11-09）**：以下原文保留供舊v1實作與測試追溯；新版產包改用 [chapter-source-v1](chapter-source-v1.md) 與004 v2包，不再以本policy建新包，也不自動轉換舊包。舊測試成功不代表新版完成。

本合約固定單文件原文切段、重疊、ID 與定位。模型仍使用既有 CPU dense encoder；此 policy 不加入 004 manifest 未允許的欄位，僅記於準備操作記錄。變更規則須改 policy 版本。

## 輸入與 tokenizer 邊界

producer 一次讀取原始 bytes，先算 SHA-256（含 BOM），以 UTF-8-sig 解碼。保留所有 code points／行尾，整份文件無字母或數字時拒絕。切段可含純空白片，不可藉此刪除來源內容。

純切段函式接受原字串與 typed tokenizer 介面：回傳不含特殊 tokens、未截斷的 content token offsets，以及實際 slice 含特殊 tokens、未截斷的 encoded count。模型 adapter 只在 worker；父 CLI 不建立 tokenizer。offsets 是原字串 Python Unicode code point 座標；每次呼叫 ID 與 offset 筆數須一致，滿足 0 <= start <= end <= len(輸入字串)，start／end 各自非遞減，允許重複與零寬映射。映射不合規、沒有 fast tokenizer 或計數無效均失敗，不猜測或 decode IDs 重建原文。

固定常數：candidate_content_tokens=400、overlap_content_tokens=50、max_encoded_tokens=512、zero_offset_window_chars=512。400 是候選點規則，不保證重新編碼後恰好 400；512（含特殊 tokens）是每片硬上限。

## 確定性視窗

初始 start=0。合法切點為 Unicode code point 邊界，但 CR 與緊接的 LF 之間不是合法切點。

1. 對 text[start:] 取得不含特殊 tokens、未截斷的 IDs／offsets，驗證映射。
2. 剩餘 content tokens <=400 時，候選 end=EOF，保留尾端空白；否則取前 400 個 token 中非零寬映射的最大 char_end，加上 start。若沒有可前進的 char_end，候選 end=min(start+512, EOF)。這是唯一字元長度 fallback。
3. 候選 end 落在 CRLF 中間時左移一個 code point；若不能前進，改選 start 後第一個合法切點。
4. 重新編碼實際原文 text[start:end]，包含特殊 tokens、禁止截斷。計數 >512 時，每次退到前一合法字元切點並重新編碼，直到第一個合規非空 slice；即使中間計數上升也繼續逐點檢查。不能以二分或其他單調假設跳過候選。最短合法 slice 也不合規則失敗。
5. 發出原文字串 slice；若 end=EOF 即完成，不製造重複末片。
6. 否則重新取得已接受 slice 的 content IDs／offsets。令筆數為 n；n>50 時取 index n−50 的 token 原文 char_start 加上 start 作 next_start。該 token 必須非零寬且 start < next_start < end。若切在 CRLF 中間則向右移至 LF 之後，再檢查範圍。
7. n<=50、選中零寬映射、無法嚴格前進或修正後 next_start>=end，一律 next_start=end，不另設字元重疊 fallback。以 next_start 重複步驟 1。

同一字元可對應多個 token，因此重疊不是保證恰好 50 tokens，而是固定第 n−50 個 token 的原文起點。每片 end>start，下一 start 嚴格增加且 <=end，全部來源被覆蓋且有限終止。起點後退、gaps 或靜默截斷都不合約。

## ID 與定位

chunk_id=`c-` 加 SHA-256 小寫 hex。hash 輸入為含下列確切 keys 的 JSON object：document_id、document_version、source_sha256、policy、start、end；policy 固定 source-window-v1，start／end 為整數。使用 sort_keys=true、ensure_ascii=false、separators=(',', ':')，再 UTF-8 encode；無 BOM／尾端換行，不含路徑或 title。相同 bytes／識別資訊／policy／範圍必須同 ID。

locator 固定 `L<first>-L<last>; chars[<start>,<end>)`。行號 1-based inclusive；字元範圍是全文件 decoded text 的 0-based 半開區間。逐字掃描，CRLF 為一個換行，單 CR／LF 各一個；換行字元歸其結束的行。first 是 start 字元所在行，last 是 end−1 字元所在行；不把片尾換行虛增成下一行。CRLF 兩個字元歸同一行。原文沒有頁碼時不生成頁碼；不解析 Markdown 章節。

例：`A\r\nB\n` 的 [0,3) 為 `L1-L1; chars[0,3)`，[3,5) 為 `L2-L2; chars[3,5)`。同一長行可有多片，以 chars 區分。

## Golden fixtures（假 tokenizer，非 BGE-M3 品質證據）

使用正式常數，不以縮小參數代替。第一組 tokenizer 對每個 code point 產生 100 個相同 offset [i,i+1) 的 IDs；特殊 tokens 固定 2 個。

| 原文字串 | 預期全文件範圍 | 預期原文 slices | 含特殊 tokens 計數 |
|---|---|---|---|
| ABCDEFGH | [0,4), [3,7), [6,8) | ABCD / DEFG / GH | 402 / 402 / 202 |
| ABC\r\nDEF | [0,3), [2,6), [5,8) | ABC / C\r\nD / DEF | 302 / 402 / 302 |

第二組：`X` 重複 600 次，每個字元一個 ID，但全部 offsets=(0,0)，特殊 tokens=2。預期 [0,510)、[510,600)，含特殊 tokens 分別 512／92；首片 fallback 512→511→510，無重疊。這也驗證零 offset 不丟字元。

非單調 backoff fixture：候選 end=4，合法切點 4／3／2 的實際含特殊 token 計數依序為 514／600／10，必須按 4→3→2 檢查並選 2；測試不得假定退一字後計數必降。

另需覆蓋不合法映射、n<=50、選中零寬重疊 token、CRLF 重疊修正至 end、最短 slice 仍超限、中文／表格／程式碼、EOF 尾空白、重建 ID／locator 相同。所有片皆核對原文字串與完整覆蓋，不要求 Chroma 二進位重現。
