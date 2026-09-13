# 見本 Genie Agent

⚠️ **この Genie Agent は、まだ自動で作れません。**

`resources/` に DAB のリソースを書いて試しましたが、`serialized_space` の
スキーマが公開されておらず、手で書いた JSON では通りませんでした。

```
Invalid JSON in field 'serialized_space': Expected 'START_OBJECT' not 'VALUE_STRING'
```

⭐ **CLI には逆生成のコマンドが用意されています。** 設計された順番は
「**画面で 1 回作る → 逆生成してリポジトリに取り込む**」です。

## 手順

### 1. 画面で作る

1. 左メニュー **「Genie Agents」** → 右上 **「New」**
2. データを選ぶ — ⭐ **メトリクスビュー 2 本だけ**
   - `<catalog>.fc_sample.mv_demand`
   - `<catalog>.fc_sample.mv_forecast_accuracy`
   - ⚠️ 生のファクトテーブルは渡さないこと（結合を誤りやすく精度が落ちます）
3. タイトルに **「見本」** を入れる（`01_dashboard` と参加者がその文字で探します）
4. **「指示」** に [`demand_agent.geniespace.json`](./demand_agent.geniespace.json) の
   `instructions` を貼る
5. **サンプル質問**も同ファイルの `sample_questions` から貼る
6. 参加者グループに **`CAN VIEW`** を付ける

### 2. リポジトリに取り込む

```bash
databricks bundle generate genie-space --key demand_agent_sample
```

⭐ 生成された YAML と JSON をコミットすれば、次回以降は
`databricks bundle deploy` で配れるようになります。

## このファイルの中身

[`demand_agent.geniespace.json`](./demand_agent.geniespace.json) は
**画面に貼り付ける内容の下書き**として残しています。
指示・サンプル質問・渡すテーブルが書かれています。
