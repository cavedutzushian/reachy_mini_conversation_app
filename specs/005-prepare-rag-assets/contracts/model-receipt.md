# Contract: model-receipt.json v2

receipt 位於已發布模型根，為本機可驗證的來源／完整性紀錄，不是簽章，也不代表上游 PR 或模型已獲維護者核准。

機器格式為 [model-receipt.schema.json](model-receipt.schema.json)，UTF-8 JSON、無 BOM／重複 key／NaN／Infinity、<=16 MiB；未知欄位拒絕。schema 只有內嵌 $defs，不讀遠端 $ref。

| 欄位 | 規則 |
|---|---|
| schema_version | 2；拒絕v1，不自動改寫／轉換 |
| role／model_id | embedding／BAAI/bge-m3，或reranker／BAAI/bge-reranker-base；不能混用 |
| revision／resolved_revision | 同一固定40hex：embedding=50f9396f75618b3389c1fd1068a1ff58dc7b5b26；reranker=2cfc18c9415c912f9d8155881c133215df768a70；上游metadata解析到相同commit |
| files | 依角色下列精確payload；相對path／size_bytes／小寫SHA-256，每個必要檔恰一筆 |
| runtime | 驗證時實際 ST／torch／transformers 完整版號，含 local suffix |
| verification.kind／query | 依角色embedding／reranker；query固定非敏感問題`這份文件主要說明什麼？` |
| verification.embedding | 只有embedding角色：1024維finite／非零／L2 normalized float32 reference |
| verification.passage／logit | 只有reranker角色：固定非敏感配對文字`這是一份提供文件查詢的示範說明。`及有限原始logit，activation=identity、max_pair_tokens=512；分數高低不作品質門檻 |
| verification.device／precision | 固定cpu／float32；實際驗證不得外連、執行遠端程式或使用pickle權重 |

Embedding角色v2 payload精確清單（保留原十檔）：

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

Reranker角色v2 payload精確清單（依既有固定revision的離線實驗交付）：

```text
config.json
model.safetensors
sentencepiece.bpe.model
special_tokens_map.json
tokenizer.json
tokenizer_config.json
```

不包含 README、Git／Hub metadata、圖片、onnx、bin／pt、Python、下載 locks。不得自行補不存在的 2_Normalize 配置。對應角色必要檔若指定revision不齊全，v2不支援該snapshot，不擴大 allowlist 或改 reader 猜測。

實際模型根檔案集合恰為 payload＋model-receipt.json，不接受連結／junction／路徑逃逸或 Windows 別名碰撞。receipt.files 不含自身，避免循環；索引manifest的embedding.files或reranking.files依各自模型根重新列舉payload＋receipt，包含receipt的實際hash。模型驗證先生成candidate receipt並以同一角色驗證、關閉worker與確認前後hash後才發布，不用嵌入receipt冒充重排就緒。

語意檢查另外要求：兩 revision 相等、檔案清單精確且不重複、大小及 hash 一致、模組／pooling／tokenizer／safe weights 滿足既有 004、runtime 比對、嵌入reference有效與既有norm／cosine容差，或重排固定配對有限raw logit與Identity設定、載入前後所有 hash 不變。不能只驗 schema 或照信 verification 欄位宣告。

外部提供的同等模型也須有此v2角色receipt，且部署者信任其準備來源；檔案 hash 本身無法證明發行者身份。不同模型 runtime 若未驗證不改 receipt 來繞過；需重新完成離線驗證與素材準備。


舊v1 receipt與既有payload原檔保留；不是自動升級入口。使用者可明確重新準備對應固定角色／版本（替換須--replace），下載腳本不得把未經新版驗證的舊檔標記already_ready。外部安全本機模型可由可信產製者提供等價v2紀錄，但App／builder不掃描私有快取、就地補receipt或接受模型名稱推測。

兩角色驗證皆使用同一精確runtime與安全載入規則，intra-op2／inter-op1每個worker只設一次；重排不轉sigmoid、不降低精度、不自動換模型。receipt只證明角色、來源／完整性與有限運算，不證明文件召回、段落充分性、0.58校準、CPU時限或雙後端驗收通過。產包需兩角色ready，單一下載結果不彙總宣告整套ready。
