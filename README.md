# 日経225 指標ダッシュボード

`nikkei225jp.com` のチャート用JavaScriptデータを取得し、ローカルWebアプリまたはVercel上の個人用Webアプリとして表示します。

## 構成

- バックエンド: Python 標準ライブラリ `http.server`、Vercel Python Serverless Functions
- フロントエンド: 依存ライブラリなしのHTML/CSS/JavaScript
- データ取得: `requests`
- PWA: `public/manifest.json`、`public/sw.js`、`public/icons/icon.svg`
- 認証: Vercel用の簡易パスワード認証

## 起動

```bash
python3 app.py
```

起動後、ブラウザで以下を開きます。

```text
http://127.0.0.1:8765
```

## Vercelデプロイ

Vercelでは常駐Pythonサーバーではなく、`api/app.py` のServerless Functionで画面とAPIを返します。

必要な環境変数:

```text
DASHBOARD_PASSWORD=自分だけが知っているログイン用パスワード
DASHBOARD_SECRET=長いランダム文字列
CRON_SECRET=長いランダム文字列
```

任意の環境変数:

```text
NIKKEI225_DATA_DIR=/tmp/nikkei225-dashboard-data
NIKKEI225_AUTO_REFRESH_HOURS=12
```

Vercel設定手順:

1. このフォルダをGitHubへ push します。
2. Vercelで新規プロジェクトとしてImportします。
3. Framework Presetは `Other` のままで構いません。
4. Environment Variables に `DASHBOARD_PASSWORD`、`DASHBOARD_SECRET`、`CRON_SECRET` を設定します。
5. Deployします。
6. 発行されたURLへアクセスし、設定したパスワードでログインします。

`vercel.json` には毎週木曜日 18:30 JST（09:30 UTC）に `/api/update` を呼ぶ Cron Job を設定しています。Vercelは `CRON_SECRET` を `Authorization` ヘッダーとして送るため、この値を設定してからRedeployしてください。

注意: VercelのServerless環境では保存領域が永続ではないため、初期表示は同梱の `data/cache.json` を使います。画面表示時にキャッシュが古い場合は自動で再取得し、画面の `更新チェック` やCronで取得した最新データは、その実行インスタンス上の一時領域に保存されます。nikkei225jp.com 側のデータURL末尾のキャッシュキーはページから自動検出します。通常ドメインが403を返す場合は `origin.nikkei225jp.com` に自動フォールバックします。より完全な永続化が必要な場合は、Vercel Blob/KVやGitHub Actionsで `data/cache.json` を更新する方式を追加してください。

## できること

- 左側の項目で縦軸の対象を切り替え
- 複数系列を選択して同一チャートに表示
- 開始日・終了日で表示期間を絞り込み
- `関係性` タブで、任意の因子を横軸・縦軸にして比較
- 関係性タブでは、散布図、標準化時系列、ローリング相関の3グラフを横並び表示
- 散布図では、点クリック、Ctrl/Commandクリック、ドラッグ範囲選択でデータ点を抽出
- 左側の `全体` で、株価トレンド・為替・商品先物と指定因子群の相関ランキングを確認し、最大6件までグラフ表示
- 左側の `統計処理` で、主成分分析と多変量解析を確認
- 時系列の `テクニカル` 表示で、ローソク足、RSI、ボリンジャーバンド、MACD、出来高を確認
- `更新チェック` で最新データを再取得
- `CSV` で抽出済みデータを書き出し
- PWAとしてスマホのホーム画面に追加
- Vercel上ではパスワード認証で自分だけが利用

## スマホ確認

1. VercelのURLをスマホのSafariまたはChromeで開きます。
2. パスワードでログインします。
3. 画面上部のタブ、左側カテゴリー、時系列チェックボックスが横スクロールまたは折り返しで操作できることを確認します。
4. iPhone Safariの場合は共有ボタンから `ホーム画面に追加` を選びます。
5. Android Chromeの場合はメニューから `アプリをインストール` または `ホーム画面に追加` を選びます。

## 秘密情報

OpenAI APIキーなどの外部APIキーは、このアプリ内にはありません。
ログイン用パスワードはコードに直書きせず、Vercelの環境変数 `DASHBOARD_PASSWORD` に設定してください。

## 取得対象

- 投資主体別売買動向
- 騰落レシオ
- 日経225 PER
- 空売り比率
- 信用評価損益率、信用売り残、信用買い残
- NT倍率
- ドル建て日経平均
- 株価トレンド: 日経225、TOPIX、グロース250、東証REIT指数、日経VI、VIX指数、NYダウ、NASDAQ総合、S&P 500、NASDAQ 100、Russell 2000
- 為替: USD/JPY、EUR/JPY、GBP/JPY、AUD/JPY、EUR/USD、ドルインデックス
- 商品先物: WTI原油、ブレント原油、金、銅

株価トレンド・為替・商品先物は日次データをそのまま使わず、NT倍率などの分析対象指標の日付に合わせて、各日付までの直近7日間の平均値として保存します。これにより、週次系の指標と同じ日付で相関を比較できます。

最新値タブの上段では、加重平均PER、加重平均EPS（`日経平均 ÷ 加重平均PER`）、PER20倍から30倍までの日経平均水準、PBR、空売り比率合計、投資主体別売買動向の主要3項目、VIX指数、信用損益率、信用売り残、信用買い残、日経平均、TOPIX、NT倍率を優先表示します。指数ベースPER/EPSも参考値として併記します。空売り比率合計が40%を超えた場合は緑色、VIXが20超で黄色・30超で赤色、信用損益率が10%超で赤色、売り残が8,000億円超で青色、買い残が4兆円超で黄色・5兆円超で赤色に強調します。投資主体別売買動向はプラスを緑、マイナスを赤で表示します。

最新値タブの「信用残・騰落レシオ 日々推移」では、売り残、買い残、騰落レシオ25日・15日・10日・6日を横並びで表示します。騰落レシオは120超で赤、80未満で青にし、130超では赤み、70未満では青みが段階的に強くなります。

## 更新チェック

ローカルアプリ起動中は、毎週木曜日の18:00以降に一度だけ自動チェックします。

Vercel本番では、`vercel.json` の Cron Job が毎週木曜日18:30 JST頃に `/api/update` を実行します。Cronを動かすには、VercelのEnvironment Variablesに `CRON_SECRET` を設定してRedeployしてください。

また、`/api/data` はキャッシュの `fetched_at` が `NIKKEI225_AUTO_REFRESH_HOURS`（既定12時間）以上古い場合、自動で最新データを取得してから返します。Cronや手動更新が失敗していても、次回表示時に再取得を試みます。

nikkei225jp.com のデータURL末尾に付くキャッシュキーは固定せず、`https://nikkei225jp.com/data/shutai.php` から現在値を自動検出します。通常ドメインが403やCloudflare応答を返した場合は、`https://origin.nikkei225jp.com/data/shutai.php` と同じJSONパスへ自動フォールバックします。取得に失敗した場合は、画面上部ステータスと `/api/status` にエラー内容とキャッシュ内の最新日付を表示します。緊急時だけ `NIKKEI225_DATA_CACHE_KEY` を Vercel の環境変数に設定すると手動上書きできます。

投資主体別売買動向と信用評価損益率は週次データです。空売り比率、株価、為替、騰落レシオなどの日次データより最終日が数営業日遅れることがあります。

抽出済みデータは外付けドライブの `/Volumes/Crucial X9/AI/nikkei225-dashboard-data/cache.json` に保存されます。
保存先を変える場合は、起動前に `NIKKEI225_DATA_DIR` を指定してください。
