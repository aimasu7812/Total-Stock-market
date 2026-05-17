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
```

任意の環境変数:

```text
NIKKEI225_DATA_DIR=/tmp/nikkei225-dashboard-data
```

Vercel設定手順:

1. このフォルダをGitHubへ push します。
2. Vercelで新規プロジェクトとしてImportします。
3. Framework Presetは `Other` のままで構いません。
4. Environment Variables に `DASHBOARD_PASSWORD` と `DASHBOARD_SECRET` を設定します。
5. Deployします。
6. 発行されたURLへアクセスし、設定したパスワードでログインします。

注意: VercelのServerless環境では保存領域が永続ではないため、初期表示は同梱の `data/cache.json` を使います。画面の `更新チェック` で取得した最新データは、その実行インスタンス上の一時領域に保存されます。

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
- 信用評価損益率
- NT倍率
- ドル建て日経平均
- 株価トレンド: 日経225、TOPIX、グロース250、東証REIT指数、日経VI、NYダウ、NASDAQ総合、S&P 500、NASDAQ 100、Russell 2000
- 為替: USD/JPY、EUR/JPY、GBP/JPY、AUD/JPY、EUR/USD、ドルインデックス
- 商品先物: WTI原油、ブレント原油、金、銅

株価トレンド・為替・商品先物は日次データをそのまま使わず、NT倍率などの分析対象指標の日付に合わせて、各日付までの直近7日間の平均値として保存します。これにより、週次系の指標と同じ日付で相関を比較できます。

## 更新チェック

アプリ起動中は、毎週木曜日の18:00以降に一度だけ自動チェックします。
アプリを起動していない場合は自動チェックできないため、木曜18:00以降に起動するか、画面の `更新チェック` を押してください。

抽出済みデータは外付けドライブの `/Volumes/Crucial X9/AI/nikkei225-dashboard-data/cache.json` に保存されます。
保存先を変える場合は、起動前に `NIKKEI225_DATA_DIR` を指定してください。
