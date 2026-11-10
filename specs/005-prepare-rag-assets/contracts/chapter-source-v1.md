# Contract: chapter-source-v1

本合約供 005 離線產包，對齊 [004 v2 包合約](../../004-single-document-rag/contracts/index-package.md) 與 [manifest schema](../../004-single-document-rag/contracts/index-manifest.schema.json)。取代新包的 source-window-v1；舊合約及實驗失敗保留，不自動轉換舊包。這是設計，不是現有程式或新包驗收證據。

## 固定輸入與版本

- 策略 `chapter-alias-hybrid-bge-base-v1`；切段 `chapter-source-v1`；脈絡 `source-title-alias-v1`；選段 `rerank-budget-then-distance-v1`。不得逐文件任意調參卻保留相同版本。
- 部署者明確選取 `bge-base-final-selection-20261109`；模型版本及其 CPU／safe-only 條件依 004／receipt 合約。嵌入 tokenizer 必須與實際模型相同；不在 App 執行本流程。
- producer 一次讀取指定 TXT／Markdown 原始 bytes，先計 SHA-256（含 BOM），再以 UTF-8-sig 解碼。保留 Unicode code points、空白、CRLF／LF／單 CR；不正規化、翻譯、render 或展開連結。無任何字母／數字的文件拒絕。
- `target_tokens=300`、`overlap_tokens=30`、`embedding_input_max_tokens=512`、`heading_context_max_tokens=64`、`alias_context_max_tokens=48`、`heading_levels=3`。512 是本策略含 special tokens 的完整嵌入輸入限制，模型原本8192上限不因此改寫。
- 使用 fast tokenizer 的非截斷 content IDs／code point offsets 及完整輸入 encoded count。ID／offset筆數須相同，範圍合法且 start／end 各自非遞減；允許零寬／重複映射。無法安全映射即失敗，不以 decode IDs 重建原文，不猜測座標。

## 原文章節與範圍

Markdown 僅辨識行首最多三個空格後的一至六個 `#`、其後空白或行尾的 ATX 標題；保存實際標題文字與定位。可選結尾 `#` 只依 ATX語法識別為標記，標題文字仍為來源連續切片。相同文字但不同位置是不同標題，不合併。

fenced code 依行首最多三空格後至少三個連續反引號或波浪號開始；反引號 opening 的資訊字串不能含反引號。直到相同字元、長度至少 opening、其後只有空白的 closing 行才離開；未關閉延續至 EOF。fence內的 `#` 不作標題。縮排code、HTML、Setext等不另解析為章節；內容一律保留原文，不執行。

按真實標題位置分出相鄰範圍，每個範圍從標題行開始到下一個標題或EOF；hierarchy stack遇同級／較高級先退棧再加入新標題。每段可用的source context是其範圍所屬stack最後三層。文件開頭到首標題間的前言保留為一個範圍；純空白前言也不得丟失，可併入首範圍但context仍以第一個實際標題起算。只有標題沒有正文的範圍也不能刪除；它可單獨切段，避免原文缺口。

TXT不解讀 `#` 為章節；整份是單一文件範圍，依段落／長度切分，以文件名稱及真實行號作來源。Markdown無標題亦使用整份範圍。無標題脈絡為指定來源檔basename（包含副檔名、不含路徑），不以任意合成章節或顯示title代替。檔名作模型輸入時不得帶入完整路徑。

上述TXT、前言、fence及純標題範圍為通用產包補強，須另以fixtures驗證；不能宣稱它們已在288段實驗中通過。288不是產包段數常數或上限。

## 可選人工別名清單

CLI可由 `--aliases` 指定唯一UTF-8 JSON常規檔，不展開其他檔案。檔案固定欄位如下，所有物件拒絕未知欄位、null、重複key及非有限數：

```json
{
  "schema_version": 1,
  "document_id": "manual",
  "document_version": "v1",
  "source_sha256": "原始文件bytes的64位小寫SHA-256",
  "aliases": [
    {"text": "原文明示名稱", "evidence_start": 100, "evidence_end": 106, "scope_start": 80, "scope_end": 300}
  ]
}
```

此為形狀示意，不是可直接使用的有效資料。文件ID／版本／digest必須與當次唯一來源完全相符。每個數值是非負整數且不可為bool；字元範圍為0-based半開區間，須非空且不超出解碼原文。`text`恰等於原文證據切片，不做大小寫／空白／字體容錯，不接受推測同義詞。

`scope_start/end`必須精確對應一個真正章節的完整子樹範圍，或無標題範圍／整份文件；證據必須位於該範圍內。段落只有其所屬章節範圍落在scope內才展開該別名，不能因文件其他位置有相同名稱就套到無關章節。人工清單順序是別名優先序，完全相同的重複項拒絕；不同證據／scope的同字串仍各自驗證，展開同一段時依首次出現去重。

不提供檔案等同 `aliases=[]`，不是缺資料；保存明示空清單。不得自動從正文擷取名稱、補別名、搜尋其他文件或要求模型／雲端生成。產包時推導並核對真實證據行號；`chunks.jsonl`的展開項依004欄位附 evidence_line_start/end，並保留原scope。fresh verifier在發布前重讀同一清單bytes摘要與身分／stat，變更即拒絕；不在App補清單。

## 脈絡與確定性切段

context取最後三層原始標題文字以 ` > ` 接合；無標題用basename。alias_context取該範圍適用別名依清單順序以 ` / ` 接合。超過64／48 content tokens時，依既有實驗保留最後limit個token所對應的原字串尾段；取token offset的start裁字串，重新計數，必要時向右移至下一合法code point切點，直到符合上限。零寬offset不能作無限循環；全部零寬時以最短可計數尾段檢查，若無合規非空尾段則拒絕。不得用token decode或自動改寫字詞。

固定模型輸入是以下字串；只有別名非空時有第二行：

```text
脈絡：{context}
戰隊別名：{alias_context}
原文：
{text}
```

各模板行間固定LF，原文text仍保留來源實際行尾；沒有別名時直接由脈絡行接原文行。`戰隊別名`只是歷史選案的固定策略標籤，不表示只支援戰隊文件。更改標籤／排列須升策略版本並留下新驗證，不能宣稱沿用原分數。原文向量由完整model_text產生，Chroma documents仍只存原文text。

每個章節範圍獨立執行，position初值是範圍起點，不能跨章節重疊；合法切點不位於CR與緊接LF之間：

1. 對剩餘範圍取非截斷content offsets。<=300個token時候選end為範圍尾；否則取前300個token中非零寬offset的最大char_end。若無可前進offset，候選end=min(position+512個code points,範圍尾)，保留舊安全fallback思想而非丟棄文字。
2. 非尾片優先在候選後半部最近的真實空行邊界結束。空行是只有空白字元的實際行，以CRLF／LF／單CR辨識；以空白行起點作邊界。無此邊界則保留候選。CRLF中間切點向左修正，不能前進時改取下一合法切點。
3. 對固定prefix＋原文字串slice計實際含special tokens數；>512則逐個合法code point切點後退並重算，直到首個合規非空slice。不可二分或假定token數單調。最短合法slice仍不合規即失敗，不能單獨截掉context或靜默省略原文。
4. 發出text=source[position:end]。end到範圍尾即完成，不製造重複尾片；否則重取已接受text的content offsets，n>30時以index n−30之token原文start作next_position。該offset須非零寬且position<next_position<end，CRLF中間向右修正再檢查；不符或n<=30時next_position=end。
5. next_position嚴格增加且<=end，與下一章節範圍相接，故有限終止且所有來源code points被至少一片涵蓋。允許純空白slice但不能產出空字串；不得靠切段省略難編碼內容。

300為候選目標，30為固定token座標重疊，不保證每片恰300／重疊恰30。不得按不同文件自動換參數；來源過長只增加有界段落數，不在App建索引。

## ID、定位與產物

canonical JSON採UTF-8、sort_keys=true、ensure_ascii=false、separators=(',',':')，無BOM／尾換行。`aliases_sha256`為已驗證人工清單aliases陣列的canonical摘要；無清單為空陣列摘要。`configuration_sha256`為manifest的strategy＋chunking及嵌入model_id／revision組成物件的canonical摘要，固定keys為strategy、chunking、embedding_model_id、embedding_revision。

chunk_id=`c-`＋SHA-256，輸入固定keys為document_id、document_version、source_sha256、policy（chapter-source-v1）、configuration_sha256、aliases_sha256、model_text_sha256、start、end。model_text_sha256為UTF-8完整model_text摘要；ID不含路徑、ordinal、輸出位置。相同來源與參數重建必須同ID；別名／來源檔名脈絡或模型輸入不同不能錯用舊ID。這是正式v2 ID規則，不宣稱與實驗section-IDs逐字相同。

locator=`L<first>-L<last>; chars[<start>,<end>)`，行號1-based inclusive、字元0-based半開；CRLF為一個換行，單CR／LF各一個，換行字元歸其結束的行。first為start所在行，last為end−1所在行；不虛構頁碼或多算片尾下一行。headings的text與offset是同一來源切片，aliases保存原文證據與scope；所有定位在producer及發布前來源核對中可驗證。

`retrieval/chunks.jsonl`固定欄位依004：chunk_id、document_id、document_version、start、end、line_start、line_end、text、headings、aliases、context、alias_context、model_text、model_text_sha256。headings保存真實層級stack中的原始標題物件；context只選末三層。每行UTF-8 JSON，欄位不省略，空headings／aliases明示空陣列。Chroma row與此清單一對一，順序按start／end／ID；row文稿為text、embedding為model_text的既有normalized1024向量。

`retrieval/bm25.json`固定version=bm25-prebuilt-v1、chunk_ids、term_frequencies、document_lengths、document_frequencies、average_document_length。以完整model_text預建詞頻：casefold後ASCII `[a-z0-9]+`；原輸入CJK U+3400..U+9FFF連續序列全部相鄰二字／三字組。TF／DF只列正整數詞項，空段length=0；N為chunk_ids長度，DF為含詞段數，avgdl為全部length平均。全部空詞時avgdl=0、DF空；query lexical分數為0，不除零。

詞彙key固定Unicode字串，JSON object canonical key排序，TF／length陣列與chunks順序一致；不使用pickle或執行期Python物件。BM25 k1=1.2、b=.75、正log1p IDF、query詞去重，公式依004契約。所有文件向量／詞頻／統計／索引在此離線預建，App不得修復或補建。

## 驗證案例與證據界線

必測：無標題TXT、Markdown前言／重複標題／純標題、未閉fence／fence內假標題、CRLF／單CR／EOF空白、超長單行、零寬offset、非單調回退、最短slice超限、人工別名空／真實／錯版本／錯證據／錯scope／來源中途變更。每片核對source[start:end]及全部範圍覆蓋，兩次重建核對text／ID／定位／model_text／BM25一致；不要要求Chroma二進位完全相同。

另將固定實驗文稿與可核對的人工別名對照舊288段結果，逐項記錄任何通用化造成的邊界或ID差異，保留原候選與分數。段數相同不證明等價；新切段／別名不自動繼承0.58的品質。v2產包與reader完整性通過，仍不是新的盲測、召回／段落支持率合格或兩後端語音驗收完成。
