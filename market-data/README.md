# 楽器買取LP 相場シミュレーター用データ作成環境

イシバシ楽器・島村楽器の公開買取価格を参考に、相場シミュレーターで使う公開用CSVを作成するためのローカル作業環境です。

## ディレクトリ構成

```text
market-data/
  raw-html/
    shimamura/   # 島村楽器の保存済みHTMLを配置
    ishibashi/   # イシバシ楽器の保存済みHTMLを配置
  working/       # 作業用CSV・解析エラー
  public/        # 公開用CSV・品質レポート
  scripts/       # 変換・チェック用Pythonスクリプト
```

## CSVテンプレート

- 作業用CSV: `working/work_template.csv`
- 公開用CSV: `public/public_template.csv`

## 基本フロー

> 注意: スクリプトはWebサイトへアクセスしません。ブラウザ等でローカル保存したHTMLだけを読み込みます。

1. 保存済みHTMLを `raw-html/shimamura/` または `raw-html/ishibashi/` に配置します。
2. HTMLから作業用CSVを作成します。

   ```bash
   python3 market-data/scripts/parse_raw_html_to_working_csv.py \
     --raw-dir market-data/raw-html \
     --output market-data/working/working_prices.csv \
     --errors market-data/working/parse_errors.csv \
     --checked-date 2026-07-06
   ```

3. 作業用CSVを確認・補正します。解析できなかった行は `working/parse_errors.csv` を確認してください。
4. 作業用CSVから公開用CSVを作成します。

   ```bash
   python3 market-data/scripts/build_public_csv.py \
     --input market-data/working/working_prices.csv \
     --output market-data/public/market_prices.csv \
     --errors market-data/working/build_public_errors.csv \
     --updated-month 2026-07
   ```

5. 公開用CSVの品質チェックを行います。

   ```bash
   python3 market-data/scripts/check_public_csv.py \
     --input market-data/public/market_prices.csv \
     --report market-data/public/quality_report.csv \
     --updated-month 2026-07
   ```

## 状態ランク対応

| 参照元 | 元データ状態 | 公開CSVカラム |
| --- | --- | --- |
| 島村楽器 | Aランク | `price_good` |
| 島村楽器 | Bランク | `price_normal` |
| 島村楽器 | Cランク | `price_used` |
| イシバシ楽器 | 美品 | `price_good` |
| イシバシ楽器 | 良品 | `price_normal` |
| イシバシ楽器 | 並品 | `price_used` |

## 価格作成ルール

- 島村楽器とイシバシ楽器の両方に価格がある場合は平均価格を採用します。
- 片方にしか価格がない場合は、公式公開価格 × 0.95 を採用します。
- 価格は1,000円単位で丸めます。
- `price_min` は `price_used`、`price_max` は `price_good` にします。
- `updated_month` は `2026-07`、`is_active` は `true` にします。

## 品質チェック内容

`check_public_csv.py` は以下をレポートします。

- 必須カラム不足・余分なカラム
- 必須値の空欄
- 価格の数値不正・1,000円単位でない価格
- `price_good >= price_normal >= price_used` になっていない行
- `price_min` / `price_max` の不一致
- `updated_month` / `is_active` の不一致
- 重複行
- 目標件数に満たないカテゴリ
