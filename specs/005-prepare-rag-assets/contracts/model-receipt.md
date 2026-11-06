# Contract: model-receipt.json v1

receipt 位於已發布模型根，為本機可驗證的來源／完整性紀錄，不是簽章，也不代表上游 PR 或模型已獲維護者核准。

機器格式為 [model-receipt.schema.json](model-receipt.schema.json)，UTF-8 JSON、無 BOM／重複 key／NaN／Infinity、<=16 MiB；未知欄位拒絕。schema 只有內嵌 $defs，不讀遠端 $ref。

| 欄位 | 規則 |
|---|---|
| schema_version | 1 |
| model_id | BAAI/bge-m3 |
| revision／resolved_revision | 同一個完整 40 hex；上游 metadata 明確解析到相同 commit |
| files | 下列十個 payload 檔案，各自相對 path／size_bytes／小寫 SHA-256；無重複路徑 |
| runtime | 驗證時實際 ST／torch／transformers 完整版號，含 local suffix |
| verification.query | 固定非敏感問題 `這份文件主要說明什麼？` |
| verification.embedding | 共用 encoder 取得 1024 維 finite／非零／L2 normalized float32 reference |

Payload v1 精確清單：

```text
config.json
config_sentence_transformers.json
modules.json
sentence_bert_config.json
1_Pooling/config.json
sentencepiece.bpe.model
special_tokens_map.json
tokenizer.json
tokenizer_config.json
model.safetensors
```

不包含 README、Git／Hub metadata、圖片、onnx、bin／pt、Python、下載 locks。不得自行補不存在的 2_Normalize 配置。上述十檔若特定 revision 不齊全，v1 不支援該 snapshot，不擴大 allowlist 或改 reader 猜測。

實際模型根檔案集合恰為 payload＋model-receipt.json，不接受連結／junction／路徑逃逸或 Windows 別名碰撞。receipt.files 不含自身，避免循環；索引 manifest 的 embedding.files 必須重新列舉 payload＋receipt，包含 receipt 的實際 hash。

語意檢查另外要求：兩 revision 相等、檔案清單精確且不重複、大小及 hash 一致、模組／pooling／tokenizer／safe weights 滿足既有 004、runtime 比對、reference 有效與既有容差、載入前後所有 hash 不變。不能只驗 schema 或照信 verification 欄位宣告。

外部提供的同等模型也須有此 v1 receipt，且部署者信任其準備來源；檔案 hash 本身無法證明發行者身份。不同模型 runtime 若未驗證不改 receipt 來繞過；需重新完成離線驗證與素材準備。
