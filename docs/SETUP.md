# 管理者向け 事前準備

⚠️ **これは講師・管理者が事前に実施する手順です。** 参加者向けは [HANDSON.md](../HANDSON.md)。

⭐ **参加者手順と物理的に分離しています。** 管理者だけが持つ権限に無自覚に依存すると、
当日参加者が権限エラーで止まります。**必ず最後に「参加者 1 名での通しリハーサル」を行ってください。**

---

## STEP 0 — 事前チェック

- [ ] 参加者全員のアカウントが対象ワークスペースに追加されている
- [ ] 参加者を 1 つのグループにまとめている（個別付与を避けるため）
- [ ] Serverless SQL ウェアハウスが起動できる
- [ ] ⚠️ `ai_forecast()` の前提: **Pro または Serverless** の SQL ウェアハウスがある
      （Classic では動きません）+ Predictive AI Functions のプレビュー登録
- [ ] ⚠️ `08_mmf_genie_code` の前提: **DBR 18 for ML 以上**のクラスタが起動できる

## STEP 1 — 認証

```bash
databricks auth login --host <workspace-url> --profile <profile>
```

## STEP 2 — bundle をデプロイ

```bash
databricks bundle validate -t dev -p <profile>
databricks bundle deploy   -t dev -p <profile>
```

## STEP 3 — サンプルデータを投入（セット A）

ジョブ `[handson] 01 サンプルデータを Volume に投入` を `load_set = A` で実行。

## STEP 4 — パイプラインを実行

<!-- Phase 2 で追記 -->

## STEP 5 — UC メタデータを適用

⚠️ **ここを飛ばすと Genie Agent の回答精度が出ません。**

<!-- Phase 2 で追記 -->

## STEP 6 — 参加者に権限を付与

参加者が持つ権限は**これだけ**です。

```sql
GRANT USE CATALOG    ON CATALOG <catalog> TO `<participant-group>`;
-- 自分専用のスキーマを作れるようにする
GRANT CREATE SCHEMA  ON CATALOG <catalog> TO `<participant-group>`;
-- 共有スキーマは読み取りのみ
GRANT USE SCHEMA     ON SCHEMA  <catalog>.fc_shared TO `<participant-group>`;
GRANT SELECT         ON SCHEMA  <catalog>.fc_shared TO `<participant-group>`;
-- CSV の投入先 Volume（自由時間で自分のデータを置くため書き込みも許可）
GRANT READ VOLUME    ON VOLUME  <catalog>.fc_shared.landing TO `<participant-group>`;
GRANT WRITE VOLUME   ON VOLUME  <catalog>.fc_shared.landing TO `<participant-group>`;
```

さらに UI 側で以下を付与します。

- [ ] SQL ウェアハウスに `CAN USE`
- [ ] サーバーレスコンピュートが使える
- [ ] 完成見本のダッシュボード / Genie Agent に `CAN VIEW`

## STEP 7 — MMF のスキルを配置

<!-- Phase 5 で追記 -->

## STEP 8 — 当日直前のウォームアップ

- [ ] SQL ウェアハウスを起動しておく（コールドスタート回避）
- [ ] パイプラインを 1 回空実行しておく（⚠️ サーバーレスの初回起動は 4〜6 分かかる）
- [ ] ⭐ **セット B の CSV はまだ投入しない**（当日投入するのがデモの山場）

## STEP 9 — ⭐ 参加者 1 名での通しリハーサル

⚠️ **最重要**。管理者アカウントではなく、**参加者グループの権限だけを持つアカウント**で
`HANDSON.md` を上から読み、書かれている通りにだけ操作して最後まで通してください。

- [ ] 各 Part の所要時間を実測する
- [ ] 権限エラーが出た箇所を STEP 6 に反映する
