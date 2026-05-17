from __future__ import annotations

import csv
import io
import json
import threading
import time
import webbrowser
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from data_sources import JST, load_cache, refresh_cache


HOST = "127.0.0.1"
PORT = 8765
WEEKLY_CHECK_HOUR = 18
PUBLIC_DIR = Path("public")

STATE = {
    "last_error": None,
    "last_weekly_check": None,
    "refreshing": False,
}


INDEX_HTML = r"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#1f6feb">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-title" content="日経225指標">
  <link rel="manifest" href="/manifest.json">
  <link rel="icon" href="/icons/icon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" href="/icons/icon.svg">
  <title>日経225 指標ダッシュボード</title>
  <style>
    :root { color-scheme: light; --ink:#20242a; --muted:#68707c; --line:#d8dde6; --panel:#f7f8fa; --accent:#1f6feb; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: #fff; }
    header { padding: 18px 22px 12px; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; gap: 16px; align-items: center; }
    h1 { margin: 0; font-size: 20px; letter-spacing: 0; }
    main { display: grid; grid-template-columns: 260px 1fr; min-height: calc(100vh - 67px); }
    aside { border-right: 1px solid var(--line); padding: 16px; background: var(--panel); }
    section { padding: 16px 20px 22px; min-width: 0; }
    button, select, input { font: inherit; }
    .stack { display: grid; gap: 8px; }
    .tabbar { display: inline-flex; gap: 4px; border: 1px solid var(--line); border-radius: 8px; padding: 3px; margin-bottom: 12px; background: #fff; }
    .tab { border: 0; border-radius: 6px; padding: 7px 14px; background: transparent; cursor: pointer; color: var(--muted); }
    .tab.active { background: var(--accent); color: #fff; font-weight: 700; }
    .view-control { border-color: #b7c7df; background: #f7fbff; color: var(--ink); font-weight: 700; }
    .pane { display: none; }
    .pane.active { display: block; }
    .category { width: 100%; text-align: left; border: 1px solid var(--line); background: #fff; border-radius: 7px; padding: 10px 11px; cursor: pointer; }
    .category.active { border-color: var(--accent); color: var(--accent); font-weight: 700; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 12px; }
    .toolbar > * { min-height: 34px; }
    .primary { border: 1px solid var(--accent); background: var(--accent); color: #fff; border-radius: 7px; padding: 7px 12px; cursor: pointer; }
    .secondary { border: 1px solid var(--line); background: #fff; border-radius: 7px; padding: 7px 12px; cursor: pointer; color: var(--ink); text-decoration: none; display: inline-flex; align-items: center; }
    select, input { border: 1px solid var(--line); border-radius: 7px; padding: 6px 8px; background: #fff; }
    .meta { color: var(--muted); font-size: 12px; }
    .chart-wrap { border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: #fff; }
    svg { display: block; width: 100%; height: 560px; }
    .legend { display: flex; flex-wrap: wrap; gap: 8px 14px; padding: 10px 12px; border-top: 1px solid var(--line); font-size: 13px; }
    .legend span { white-space: nowrap; }
    .swatch { display: inline-block; width: 11px; height: 11px; margin-right: 5px; border-radius: 2px; vertical-align: -1px; }
    .empty { padding: 40px; color: var(--muted); text-align: center; }
    .relation-grid { display: grid; grid-template-columns: repeat(3, minmax(300px, 1fr)); gap: 12px; overflow-x: auto; padding-bottom: 4px; }
    .mini-card { border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: #fff; min-width: 0; }
    .mini-card h2 { margin: 0; padding: 10px 12px; font-size: 14px; border-bottom: 1px solid var(--line); background: var(--panel); }
    .mini-card svg { height: 330px; }
    .summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 12px 0; }
    .metric { border: 1px solid var(--line); border-radius: 8px; padding: 10px; background: #fff; }
    .metric b { display: block; font-size: 18px; margin-top: 4px; }
    .relation-section { margin-top: 16px; border-top: 1px solid var(--line); padding-top: 14px; }
    .relation-section h2 { margin: 0 0 8px; font-size: 15px; }
    .selected-point { min-height: 32px; color: var(--muted); font-size: 13px; padding: 8px 0 0; }
    .selected-row { background: #fff4ce; }
    .clickable-point { cursor: pointer; }
    .rank-table-wrap { max-height: 360px; overflow: auto; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
    .rank-table-wrap table { margin-top: 0; }
    .rank-table-wrap tr { cursor: pointer; }
    .rank-table-wrap tr:hover { background: #f4f7fb; }
    .rank-table-wrap tr.checked { background: #eaf2ff; }
    .pair-grid { display: grid; grid-template-columns: repeat(3, minmax(260px, 1fr)); gap: 12px; margin-top: 12px; }
    .pair-card { border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: #fff; }
    .pair-card h3 { margin: 0; padding: 9px 10px; font-size: 12px; line-height: 1.35; background: var(--panel); border-bottom: 1px solid var(--line); }
    .pair-card svg { height: 260px; }
    .tech-shell { border: 1px solid #4b5563; border-radius: 8px; overflow: hidden; background: #06080c; color: #d5dae3; }
    .tech-toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; padding: 9px 12px; border-bottom: 1px solid #303846; background: #20242b; }
    .tech-toolbar select { background: #111827; color: #e5e7eb; border-color: #4b5563; }
    .tech-grid { display: grid; grid-template-columns: 1fr; gap: 0; }
    .tech-card { border-top: 1px solid #303846; background: #06080c; }
    .tech-card:first-child { border-top: 0; }
    .tech-card h2 { margin: 0; padding: 7px 10px; font-size: 12px; color: #d5dae3; border-bottom: 1px solid #222a36; background: #111827; }
    .tech-card.wide svg { height: 430px; }
    .tech-card svg { height: 190px; background: #06080c; }
    .stats-grid { display: grid; grid-template-columns: minmax(340px, .9fr) minmax(420px, 1.1fr); gap: 12px; align-items: start; }
    .panel { border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fff; }
    .panel h2 { margin: 0 0 10px; font-size: 15px; }
    .panel svg { height: 430px; }
    .regression-charts { display: grid; grid-template-columns: repeat(2, minmax(280px, 1fr)); gap: 12px; margin-top: 12px; }
    .regression-card { border-top: 1px solid var(--line); padding-top: 14px; margin-top: 14px; }
    .regression-card:first-child { border-top: 0; padding-top: 0; margin-top: 0; }
    .equation { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; line-height: 1.55; white-space: normal; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px; margin: 10px 0; }
    .check-list { border: 1px solid var(--line); border-radius: 8px; padding: 8px; max-height: 220px; overflow: auto; background: #fff; min-width: 300px; }
    .check-list label { display: flex; gap: 7px; align-items: flex-start; font-size: 12px; line-height: 1.35; padding: 4px 2px; color: var(--ink); }
    .check-list input { margin-top: 1px; min-height: auto; }
    .series-checks { min-width: 260px; max-height: 132px; }
    .axis-tools { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); }
    .axis-tools input[type="number"] { width: 88px; }
    .panel select[multiple] { width: 100%; min-height: 170px; }
    table { border-collapse: collapse; width: 100%; margin-top: 14px; font-size: 13px; }
    th, td { border-bottom: 1px solid var(--line); padding: 7px 8px; text-align: right; }
    th:first-child, td:first-child { text-align: left; }
    @media (max-width: 820px) {
      header { align-items: flex-start; flex-direction: column; padding: 14px 14px 10px; }
      h1 { font-size: 18px; }
      main { grid-template-columns: 1fr; min-height: auto; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); padding: 10px; position: sticky; top: 0; z-index: 5; }
      .stack { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 2px; }
      .category { width: auto; flex: 0 0 auto; white-space: nowrap; padding: 8px 10px; }
      section { padding: 12px; }
      .tabbar { max-width: 100%; overflow-x: auto; }
      .toolbar, .axis-tools, .tech-toolbar { align-items: stretch; }
      .toolbar > label, .toolbar > .check-list, .toolbar > button, .toolbar > a, .axis-tools > label { flex: 1 1 150px; }
      select, input { max-width: 100%; }
      .series-checks, .check-list { min-width: min(100%, 300px); width: 100%; }
      svg { height: 420px; }
      .summary { grid-template-columns: 1fr; }
      .relation-grid { grid-template-columns: repeat(3, minmax(260px, 84vw)); }
      .pair-grid { grid-template-columns: 1fr; }
      .tech-grid, .stats-grid, .regression-charts { grid-template-columns: 1fr; }
      .tech-card.wide svg { height: 360px; }
      .tech-card svg { height: 170px; }
      table { font-size: 12px; display: block; overflow-x: auto; white-space: nowrap; }
    }
  </style>
</head>
<body>
  <header>
    <h1>日経225 指標ダッシュボード</h1>
    <div class="meta" id="status">読み込み中...</div>
  </header>
  <main>
    <aside>
      <div class="stack" id="categories"></div>
    </aside>
    <section>
      <div class="tabbar" role="tablist" aria-label="表示切替">
        <button class="tab active" data-tab="time" type="button">時系列</button>
        <button class="tab" data-tab="tech" type="button">テクニカル</button>
        <button class="tab" data-tab="relation" type="button">関係性</button>
      </div>
      <div id="timePane" class="pane active">
        <div class="toolbar">
          <div id="series" class="check-list series-checks" title="系列"></div>
          <label class="meta">チャート種類 <select id="timeView" class="view-control"><option value="line">折れ線グラフ</option><option value="tech">テクニカル分析</option></select></label>
          <label class="meta">比較方法 <select id="timeScale"><option value="raw">実データ</option><option value="indexed">左端=1の変化率</option></select></label>
          <label class="meta">開始 <input id="from" type="date"></label>
          <label class="meta">終了 <input id="to" type="date"></label>
          <button class="primary" id="refresh" type="button">更新チェック</button>
          <a class="secondary" id="csv" href="/api/export.csv">CSV</a>
        </div>
        <div class="axis-tools meta">
          <label><input id="showCustomLine" type="checkbox"> 基準線</label>
          <input id="customLineValue" type="number" step="any" placeholder="例: 2">
          <label><input id="showZeroLine" type="checkbox"> ゼロライン</label>
          <label><input id="showSigma2" type="checkbox"> ±2σ</label>
          <label><input id="showSigma3" type="checkbox"> ±3σ</label>
        </div>
        <div class="chart-wrap">
          <svg id="chart" role="img" aria-label="時系列チャート"></svg>
          <div class="legend" id="legend"></div>
        </div>
        <div id="table"></div>
        <div id="technicalPane" style="display:none">
          <div class="summary" id="techSummary"></div>
          <div class="tech-shell">
            <div class="tech-toolbar">
              <strong>テクニカルチャート</strong>
              <label>ボリンジャーバンド <select id="bandSigma"><option value="2">±2σ</option><option value="3">±3σ</option></select></label>
              <span id="bandSignal"></span>
            </div>
            <div class="tech-grid">
              <div class="tech-card wide"><h2>価格・ローソク足・ボリンジャーバンド</h2><svg id="candleChart" aria-label="ローソク足とボリンジャーバンド"></svg></div>
              <div class="tech-card"><h2>RSI</h2><svg id="rsiChart" aria-label="RSI"></svg></div>
              <div class="tech-card"><h2>MACD</h2><svg id="macdChart" aria-label="MACD"></svg></div>
              <div class="tech-card"><h2>出来高</h2><svg id="volumeChart" aria-label="出来高"></svg></div>
            </div>
          </div>
        </div>
      </div>
      <div id="relationPane" class="pane">
        <div class="toolbar">
          <label class="meta">横軸 <select id="xFactor"></select></label>
          <label class="meta">縦軸 <select id="yFactor"></select></label>
          <label class="meta">開始 <input id="relFrom" type="date"></label>
          <label class="meta">終了 <input id="relTo" type="date"></label>
          <label class="meta">相関期間 <input id="corrWindow" type="number" min="10" max="260" value="90" style="width:82px"></label>
        </div>
        <div class="summary" id="relationSummary"></div>
        <div class="relation-grid">
          <div class="mini-card"><h2>散布図</h2><svg id="scatterChart" aria-label="散布図"></svg></div>
          <div class="mini-card"><h2>標準化して重ね合わせ</h2><svg id="overlayChart" aria-label="標準化時系列"></svg></div>
          <div class="mini-card"><h2>ローリング相関</h2><svg id="corrChart" aria-label="ローリング相関"></svg></div>
        </div>
        <div class="selected-point" id="selectedPoint"></div>
        <div id="relationTable"></div>
        <div class="relation-section">
          <h2>相関ランキング</h2>
          <div class="meta">指標と株価トレンド・為替・商品先物の関係を、相関係数の絶対値が高い順に表示します。最大6件まで選択できます。</div>
          <div class="rank-table-wrap" id="correlationRank"></div>
          <div id="selectedPairCharts" class="pair-grid"></div>
        </div>
      </div>
      <div id="overviewPane" class="pane">
        <div class="toolbar">
          <label class="meta">開始 <input id="allFrom" type="date"></label>
          <label class="meta">終了 <input id="allTo" type="date"></label>
          <label class="meta">最小データ数 <input id="allMinCount" type="number" min="10" max="3000" value="60" style="width:92px"></label>
        </div>
        <div class="relation-section" style="border-top:0;padding-top:0;margin-top:0">
          <h2>全データ相関ランキング</h2>
          <div class="meta">株価トレンド・為替・商品先物と、NT倍率・信用評価損益率・投資主体別売買動向・空売り比率・騰落レシオの関係を、相関係数の絶対値が高い順に表示します。</div>
          <div class="rank-table-wrap" id="allCorrelationRank"></div>
          <div id="allSelectedPairCharts" class="pair-grid"></div>
        </div>
      </div>
      <div id="statsPane" class="pane">
        <div class="stats-grid">
          <div class="panel">
            <h2>統計処理</h2>
            <div class="toolbar">
              <label class="meta">対象カテゴリ<br><select id="statsCategories" multiple size="7"></select></label>
              <label class="meta">最小データ数<br><input id="statsMinCount" type="number" min="30" max="3000" value="120" style="width:100px"></label>
            </div>
            <div class="meta">多変量解析 目的変数（最大5個）<div id="regTargets" class="check-list"></div></div>
            <div style="height:8px"></div>
            <div class="meta">説明変数<div id="regFeatures" class="check-list"></div></div>
          </div>
          <div>
            <div class="summary" id="statsSummary"></div>
            <div class="panel">
              <h2>主成分分析</h2>
              <svg id="pcaChart" aria-label="主成分分析ローディング図"></svg>
              <div id="pcaResult"></div>
            </div>
            <div class="panel" style="margin-top:12px">
              <h2>多変量解析</h2>
              <div id="regressionResult"></div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </main>
  <script>
    const colors = ["#1f6feb", "#d1242f", "#2da44e", "#8250df", "#bf8700", "#0969da", "#cf222e", "#116329", "#6f42c1", "#953800"];
    let payload = null;
    let category = null;
    let activeTab = "time";
    let selectedPointDates = [];
    let selectedPairs = [];
    let currentRankPairs = [];
    let allSelectedPairs = [];
    let allRankPairs = [];
    let restoredRelationPairs = false;
    let restoredOverviewPairs = false;

    const $ = id => document.getElementById(id);
    const STORAGE_KEY = "nikkei225-dashboard-ui-state-v1";
    const loadUiState = () => {
      try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); }
      catch { return {}; }
    };
    let savedUi = loadUiState();
    const parseDate = d => new Date(d + "T00:00:00+09:00").getTime();
    const fmt = n => Number(n).toLocaleString("ja-JP", { maximumFractionDigits: 3 });
    const esc = s => String(s).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
    const factorKey = r => `${r.category} / ${r.series}`;
    const factorParts = key => {
      const [category, ...seriesParts] = key.split(" / ");
      return { category, series: seriesParts.join(" / ") };
    };
    const factorLabel = key => {
      const { category, series } = factorParts(key);
      const weekly = series.match(/^(.*) \(週平均\)$/);
      return weekly ? `${category} / ${weekly[1]} / 過去週平均` : key;
    };
    const mean = values => values.reduce((a, b) => a + b, 0) / (values.length || 1);
    const stdev = values => {
      const m = mean(values);
      return Math.sqrt(values.reduce((a, b) => a + (b - m) ** 2, 0) / Math.max(values.length - 1, 1)) || 1;
    };
    const corr = pairs => {
      if (pairs.length < 3) return NaN;
      const xs = pairs.map(p => p.x), ys = pairs.map(p => p.y);
      const mx = mean(xs), my = mean(ys);
      const num = pairs.reduce((a, p) => a + (p.x - mx) * (p.y - my), 0);
      const den = Math.sqrt(xs.reduce((a, v) => a + (v - mx) ** 2, 0) * ys.reduce((a, v) => a + (v - my) ** 2, 0));
      return den ? num / den : NaN;
    };
    const groupBy = (rows, fn) => rows.reduce((acc, row) => {
      const key = fn(row);
      (acc[key] ||= []).push(row);
      return acc;
    }, {});
    const baseCategories = new Set(["NT倍率", "信用評価損益率", "投資主体別売買動向", "空売り比率", "騰落レシオ"]);
    const comparisonCategories = new Set(["株価トレンド", "為替", "商品先物"]);
    const factorCategory = key => key.split(" / ")[0];
    const relationId = pair => `${pair.xKey}::${pair.yKey}`;
    const pct = n => Number(n * 100).toLocaleString("ja-JP", { maximumFractionDigits: 1 }) + "%";

    function checkedValues(id) {
      return [...$(id).querySelectorAll("input:checked")].map(input => input.value);
    }

    function currentAxisSettings() {
      return {
        showCustomLine: $("showCustomLine").checked,
        customLineValue: $("customLineValue").value,
        showZeroLine: $("showZeroLine").checked,
        showSigma2: $("showSigma2").checked,
        showSigma3: $("showSigma3").checked,
      };
    }

    function applyAxisSettings(settings = {}) {
      $("showCustomLine").checked = !!settings.showCustomLine;
      $("customLineValue").value = settings.customLineValue || "";
      $("showZeroLine").checked = !!settings.showZeroLine;
      $("showSigma2").checked = !!settings.showSigma2;
      $("showSigma3").checked = !!settings.showSigma3;
    }

    function saveUiState() {
      const current = loadUiState();
      const seriesByCategory = { ...(current.seriesByCategory || {}) };
      if (category && $("series")) seriesByCategory[category] = selectedTimeSeries();
      const axisByCategory = { ...(current.axisByCategory || {}) };
      if (category && category !== "全体" && category !== "統計処理") {
        axisByCategory[category] = currentAxisSettings();
      }
      const state = {
        category,
        activeTab,
        seriesByCategory,
        axisByCategory,
        from: $("from").value,
        to: $("to").value,
        timeView: $("timeView").value,
        timeScale: $("timeScale").value,
        bandSigma: $("bandSigma").value,
        xFactor: $("xFactor").value,
        yFactor: $("yFactor").value,
        relFrom: $("relFrom").value,
        relTo: $("relTo").value,
        corrWindow: $("corrWindow").value,
        allFrom: $("allFrom").value,
        allTo: $("allTo").value,
        allMinCount: $("allMinCount").value,
        statsCategories: $("statsCategories").options.length ? [...$("statsCategories").selectedOptions].map(o => o.value) : current.statsCategories,
        statsMinCount: $("statsMinCount").value,
        regTargets: $("regTargets").querySelectorAll("input").length ? checkedValues("regTargets") : current.regTargets,
        regFeatures: $("regFeatures").querySelectorAll("input").length ? checkedValues("regFeatures") : current.regFeatures,
        selectedPairIds: activeTab === "relation" ? selectedPairs.map(relationId) : current.selectedPairIds,
        allSelectedPairIds: activeTab === "overview" ? allSelectedPairs.map(relationId) : current.allSelectedPairIds,
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
      savedUi = state;
    }

    function restoreStaticControls() {
      $("from").value = savedUi.from || "";
      $("to").value = savedUi.to || "";
      $("timeView").value = savedUi.timeView || "line";
      $("timeScale").value = savedUi.timeScale || "raw";
      applyAxisSettings();
      $("bandSigma").value = savedUi.bandSigma || "2";
      $("relFrom").value = savedUi.relFrom || "";
      $("relTo").value = savedUi.relTo || "";
      $("corrWindow").value = savedUi.corrWindow || "90";
      $("allFrom").value = savedUi.allFrom || "";
      $("allTo").value = savedUi.allTo || "";
      $("allMinCount").value = savedUi.allMinCount || "60";
      $("statsMinCount").value = savedUi.statsMinCount || "120";
      if (savedUi.activeTab) activeTab = savedUi.activeTab;
    }

    function ema(values, period) {
      const k = 2 / (period + 1);
      const out = [];
      let prev = values[0] ?? 0;
      values.forEach((v, i) => {
        prev = i === 0 ? v : v * k + prev * (1 - k);
        out.push(prev);
      });
      return out;
    }

    function movingStats(values, period) {
      return values.map((_, i) => {
        const slice = values.slice(Math.max(0, i - period + 1), i + 1);
        const m = mean(slice);
        const s = Math.sqrt(slice.reduce((a, v) => a + (v - m) ** 2, 0) / Math.max(slice.length - 1, 1)) || 0;
        return { mean: m, upper: m + 2 * s, lower: m - 2 * s };
      });
    }

    function rsi(values, period = 14) {
      const out = values.map(() => null);
      for (let i = period; i < values.length; i++) {
        let gains = 0, losses = 0;
        for (let j = i - period + 1; j <= i; j++) {
          const diff = values[j] - values[j - 1];
          if (diff >= 0) gains += diff; else losses -= diff;
        }
        out[i] = losses === 0 ? 100 : 100 - 100 / (1 + gains / losses);
      }
      return out;
    }

    function solveLinearSystem(matrix, vector) {
      const n = vector.length;
      const a = matrix.map((row, i) => [...row, vector[i]]);
      for (let i = 0; i < n; i++) {
        let pivot = i;
        for (let r = i + 1; r < n; r++) if (Math.abs(a[r][i]) > Math.abs(a[pivot][i])) pivot = r;
        [a[i], a[pivot]] = [a[pivot], a[i]];
        if (Math.abs(a[i][i]) < 1e-10) a[i][i] = 1e-10;
        const div = a[i][i];
        for (let c = i; c <= n; c++) a[i][c] /= div;
        for (let r = 0; r < n; r++) {
          if (r === i) continue;
          const f = a[r][i];
          for (let c = i; c <= n; c++) a[r][c] -= f * a[i][c];
        }
      }
      return a.map(row => row[n]);
    }

    async function loadData() {
      const res = await fetch("/api/data");
      payload = await res.json();
      if (!payload.rows || !payload.rows.length) {
        $("status").textContent = "データがありません。更新チェックを押してください。";
        return;
      }
      $("status").textContent = `取得: ${payload.fetched_at} / ${payload.rows.length.toLocaleString()}点`;
      const realCats = [...new Set(payload.rows.map(r => r.category))];
      const cats = ["全体", "統計処理", ...realCats];
      category = category || (cats.includes(savedUi.category) ? savedUi.category : realCats[0]);
      $("categories").innerHTML = cats.map(c => `<button class="category ${c === category ? "active" : ""}" data-c="${c}">${c}</button>`).join("");
      document.querySelectorAll(".category").forEach(b => b.onclick = () => {
        saveUiState();
        category = b.dataset.c;
        if (category === "全体") {
          activateTab("overview");
          document.querySelectorAll(".category").forEach(btn => btn.classList.toggle("active", btn.dataset.c === "全体"));
          draw();
          saveUiState();
          return;
        }
        if (category === "統計処理") {
          activateTab("stats");
          document.querySelectorAll(".category").forEach(btn => btn.classList.toggle("active", btn.dataset.c === "統計処理"));
          initStatsControls();
          draw();
          saveUiState();
          return;
        }
        if (activeTab === "overview" || activeTab === "stats") activateTab("time");
        loadData();
      });
      if (category === "全体") {
        activateTab("overview");
        initRelationControls();
        draw();
        saveUiState();
        return;
      }
      if (category === "統計処理") {
        activateTab("stats");
        initRelationControls();
        initStatsControls();
        draw();
        saveUiState();
        return;
      }
      applyAxisSettings(savedUi.axisByCategory?.[category]);
      const series = [...new Set(payload.rows.filter(r => r.category === category).map(r => r.series))];
      const old = (savedUi.seriesByCategory && savedUi.seriesByCategory[category]) || selectedTimeSeries();
      const hasKeptSelection = series.some(s => old.includes(s));
      $("series").innerHTML = series.map((s, i) => `<label><input type="checkbox" value="${esc(s)}" ${old.includes(s) || (!hasKeptSelection && i === 0) ? "checked" : ""}>${s}</label>`).join("");
      $("series").querySelectorAll("input").forEach(input => input.onchange = () => { draw(); saveUiState(); });
      initRelationControls();
      draw();
      saveUiState();
    }

    function initRelationControls() {
      const factors = [...new Set(payload.rows.map(factorKey))].sort();
      const oldX = $("xFactor").value || savedUi.xFactor;
      const oldY = $("yFactor").value || savedUi.yFactor;
      const categoryOrder = ["NT倍率", "信用評価損益率", "投資主体別売買動向", "空売り比率", "騰落レシオ", "株価トレンド", "為替", "商品先物", "日経225 PER", "ドル建て日経平均"];
      const categories = [...new Set(factors.map(f => factorParts(f).category))]
        .sort((a, b) => {
          const ai = categoryOrder.indexOf(a), bi = categoryOrder.indexOf(b);
          return (ai < 0 ? 999 : ai) - (bi < 0 ? 999 : bi) || a.localeCompare(b, "ja");
        });
      const optionHtml = (selected, sourceFactors = factors) => categories
        .filter(cat => sourceFactors.some(f => factorParts(f).category === cat))
        .map(cat => {
        const options = sourceFactors
          .filter(f => factorParts(f).category === cat)
          .sort((a, b) => factorLabel(a).localeCompare(factorLabel(b), "ja"))
          .map(f => `<option value="${f}" ${f === selected ? "selected" : ""}>${factorLabel(f)}</option>`)
          .join("");
        return `<optgroup label="${cat}">${options}</optgroup>`;
      }).join("");
      const xFactors = payload.rows.some(r => r.category === category)
        ? [...new Set(payload.rows.filter(r => r.category === category).map(factorKey))].sort((a, b) => factorLabel(a).localeCompare(factorLabel(b), "ja"))
        : factors;
      $("xFactor").innerHTML = optionHtml(xFactors.includes(oldX) ? oldX : xFactors[0], xFactors);
      $("yFactor").innerHTML = optionHtml(factors.includes(oldY) ? oldY : (factors[1] || factors[0]));
    }

    function selectedTimeSeries() {
      return [...$("series").querySelectorAll("input:checked")].map(input => input.value);
    }

    function filteredRows() {
      if (!payload) return [];
      const selected = selectedTimeSeries();
      const from = $("from").value ? parseDate($("from").value) : -Infinity;
      const to = $("to").value ? parseDate($("to").value) : Infinity;
      return payload.rows.filter(r => r.category === category && selected.includes(r.series))
        .filter(r => { const t = parseDate(r.date); return t >= from && t <= to; });
    }

    function draw() {
      if (activeTab === "relation") {
        drawRelationship();
        return;
      }
      if (activeTab === "overview") {
        drawOverview();
        return;
      }
      if (activeTab === "stats") {
        drawStats();
        return;
      }
      const techMode = activeTab === "tech" || $("timeView").value === "tech";
      $("timeView").value = techMode ? "tech" : "line";
      $("technicalPane").style.display = techMode ? "block" : "none";
      document.querySelector(".chart-wrap").style.display = techMode ? "none" : "block";
      $("table").style.display = techMode ? "none" : "block";
      if (techMode) {
        drawTechnical();
        return;
      }
      const rows = filteredRows();
      const svg = $("chart");
      const legend = $("legend");
      if (!rows.length) {
        svg.innerHTML = "";
        legend.innerHTML = '<div class="empty">表示するデータがありません</div>';
        $("table").innerHTML = "";
        return;
      }
      const scaleMode = $("timeScale").value;
      const byOriginalSeries = groupBy(rows, r => r.series);
      const baseBySeries = {};
      Object.entries(byOriginalSeries).forEach(([name, points]) => {
        const sorted = points.slice().sort((a, b) => parseDate(a.date) - parseDate(b.date));
        const base = sorted.find(p => p.value !== 0 && Number.isFinite(p.value))?.value;
        if (base) baseBySeries[name] = base;
      });
      const chartRows = scaleMode === "indexed"
        ? rows
          .filter(r => baseBySeries[r.series])
          .map(r => ({ ...r, rawValue: r.value, value: r.value / baseBySeries[r.series] }))
        : rows.map(r => ({ ...r, rawValue: r.value }));
      const width = svg.clientWidth || 900, height = svg.clientHeight || 560;
      const pad = { left: 72, right: 26, top: 24, bottom: 52 };
      const xs = chartRows.map(r => parseDate(r.date)), ys = chartRows.map(r => r.value);
      const minX = Math.min(...xs), maxX = Math.max(...xs);
      let minY = Math.min(...ys), maxY = Math.max(...ys);
      const refLines = [];
      if ($("showZeroLine").checked) refLines.push({ value: 0, label: "0", color: "#111827", dash: "none", width: 1.5 });
      if ($("showCustomLine").checked && $("customLineValue").value !== "") {
        refLines.push({ value: Number($("customLineValue").value), label: `基準 ${fmt(Number($("customLineValue").value))}`, color: "#d1242f", dash: "6 4", width: 1.8 });
      }
      const mY = mean(ys), sdY = stdev(ys);
      if ($("showSigma2").checked) {
        refLines.push({ value: mY + 2 * sdY, label: "+2σ", color: "#bf8700", dash: "5 4", width: 1.4 });
        refLines.push({ value: mY - 2 * sdY, label: "-2σ", color: "#bf8700", dash: "5 4", width: 1.4 });
      }
      if ($("showSigma3").checked) {
        refLines.push({ value: mY + 3 * sdY, label: "+3σ", color: "#8250df", dash: "2 4", width: 1.4 });
        refLines.push({ value: mY - 3 * sdY, label: "-3σ", color: "#8250df", dash: "2 4", width: 1.4 });
      }
      if (refLines.length) {
        minY = Math.min(minY, ...refLines.map(l => l.value));
        maxY = Math.max(maxY, ...refLines.map(l => l.value));
      }
      if (minY === maxY) { minY -= 1; maxY += 1; }
      const x = t => pad.left + ((t - minX) / (maxX - minX || 1)) * (width - pad.left - pad.right);
      const y = v => height - pad.bottom - ((v - minY) / (maxY - minY)) * (height - pad.top - pad.bottom);
      let grid = "";
      for (let i = 0; i <= 5; i++) {
        const gy = pad.top + i * (height - pad.top - pad.bottom) / 5;
        const val = maxY - i * (maxY - minY) / 5;
        grid += `<line x1="${pad.left}" y1="${gy}" x2="${width-pad.right}" y2="${gy}" stroke="#edf0f5"/><text x="${pad.left-8}" y="${gy+4}" text-anchor="end" font-size="11" fill="#68707c">${fmt(val)}</text>`;
      }
      for (let i = 0; i <= 4; i++) {
        const tx = pad.left + i * (width - pad.left - pad.right) / 4;
        const dt = new Date(minX + i * (maxX - minX) / 4);
        grid += `<text x="${tx}" y="${height-20}" text-anchor="middle" font-size="11" fill="#68707c">${dt.getFullYear()}/${String(dt.getMonth()+1).padStart(2,"0")}</text>`;
      }
      const bySeries = groupBy(chartRows, r => r.series);
      let paths = "";
      let dots = "";
      Object.entries(bySeries).forEach(([name, points], idx) => {
        points.sort((a,b) => parseDate(a.date) - parseDate(b.date));
        const color = colors[idx % colors.length];
        const d = points.map((p, i) => `${i ? "L" : "M"} ${x(parseDate(p.date)).toFixed(1)} ${y(p.value).toFixed(1)}`).join(" ");
        paths += `<path d="${d}" fill="none" stroke="${color}" stroke-width="2"/>`;
        points.slice(-1).forEach(p => dots += `<circle cx="${x(parseDate(p.date))}" cy="${y(p.value)}" r="3.5" fill="${color}"><title>${name} ${p.date}: ${scaleMode === "indexed" ? `${fmt(p.value)} (実値 ${fmt(p.rawValue)})` : fmt(p.value)}</title></circle>`);
      });
      const referenceSvg = refLines.map(line => {
        const yy = y(line.value);
        const dash = line.dash === "none" ? "" : `stroke-dasharray="${line.dash}"`;
        return `<line x1="${pad.left}" y1="${yy}" x2="${width-pad.right}" y2="${yy}" stroke="${line.color}" stroke-width="${line.width}" ${dash}/><text x="${width-pad.right-4}" y="${yy-5}" text-anchor="end" font-size="11" font-weight="700" fill="${line.color}">${line.label}</text>`;
      }).join("");
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
      svg.innerHTML = `${grid}<line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height-pad.bottom}" stroke="#c8ced8"/><line x1="${pad.left}" y1="${height-pad.bottom}" x2="${width-pad.right}" y2="${height-pad.bottom}" stroke="#c8ced8"/>${referenceSvg}${paths}${dots}`;
      const refLegend = refLines.map(l => `<span><i class="swatch" style="background:${l.color}"></i>${l.label}</span>`).join("");
      legend.innerHTML = (scaleMode === "indexed" ? `<span><i class="swatch" style="background:#111827"></i>左端=1</span>` : "") + Object.keys(bySeries).map((s, i) => `<span><i class="swatch" style="background:${colors[i % colors.length]}"></i>${s}</span>`).join("") + refLegend;
      const latest = chartRows.slice().sort((a,b) => b.date.localeCompare(a.date)).slice(0, 30);
      const valueHead = scaleMode === "indexed" ? "左端=1" : "値";
      const rawHead = scaleMode === "indexed" ? "<th>実値</th>" : "";
      $("table").innerHTML = `<table><thead><tr><th>日付</th><th>項目</th><th>${valueHead}</th>${rawHead}</tr></thead><tbody>${latest.map(r => `<tr><td>${r.date}</td><td>${r.series}</td><td>${fmt(r.value)}</td>${scaleMode === "indexed" ? `<td>${fmt(r.rawValue)}</td>` : ""}</tr>`).join("")}</tbody></table>`;
    }

    function joinedRelationshipRows() {
      return relationshipRowsForKeys($("xFactor").value, $("yFactor").value);
    }

    function relationshipRowsForKeys(xKey, yKey) {
      const from = $("relFrom").value ? parseDate($("relFrom").value) : -Infinity;
      const to = $("relTo").value ? parseDate($("relTo").value) : Infinity;
      return relationshipRowsForKeysInRange(xKey, yKey, from, to);
    }

    function relationshipRowsForKeysInRange(xKey, yKey, from, to) {
      const xMap = new Map();
      const yMap = new Map();
      for (const r of payload.rows) {
        const t = parseDate(r.date);
        if (t < from || t > to) continue;
        if (factorKey(r) === xKey) xMap.set(r.date, r.value);
        if (factorKey(r) === yKey) yMap.set(r.date, r.value);
      }
      return [...xMap.entries()]
        .filter(([date]) => yMap.has(date))
        .map(([date, x]) => ({ date, x, y: yMap.get(date) }))
        .sort((a, b) => a.date.localeCompare(b.date));
    }

    function drawAxes(svg, minX, maxX, minY, maxY, xLabelFn = fmt) {
      const width = svg.clientWidth || 320, height = svg.clientHeight || 330;
      const pad = { left: 54, right: 18, top: 18, bottom: 42 };
      const xp = v => pad.left + ((v - minX) / (maxX - minX || 1)) * (width - pad.left - pad.right);
      const yp = v => height - pad.bottom - ((v - minY) / (maxY - minY || 1)) * (height - pad.top - pad.bottom);
      let grid = "";
      for (let i = 0; i <= 4; i++) {
        const gy = pad.top + i * (height - pad.top - pad.bottom) / 4;
        const val = maxY - i * (maxY - minY) / 4;
        grid += `<line x1="${pad.left}" y1="${gy}" x2="${width-pad.right}" y2="${gy}" stroke="#edf0f5"/><text x="${pad.left-7}" y="${gy+4}" text-anchor="end" font-size="10" fill="#68707c">${fmt(val)}</text>`;
      }
      for (let i = 0; i <= 3; i++) {
        const gx = pad.left + i * (width - pad.left - pad.right) / 3;
        const val = minX + i * (maxX - minX) / 3;
        grid += `<text x="${gx}" y="${height-17}" text-anchor="middle" font-size="10" fill="#68707c">${xLabelFn(val)}</text>`;
      }
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
      return { width, height, pad, xp, yp, grid };
    }

    function selectedTechnicalRows() {
      const selected = selectedTimeSeries();
      const seriesName = selected[0];
      const from = $("from").value ? parseDate($("from").value) : -Infinity;
      const to = $("to").value ? parseDate($("to").value) : Infinity;
      if (category === "株価トレンド" && seriesName && seriesName.includes("日経225") && payload.technical?.length) {
        return payload.technical
          .filter(r => { const t = parseDate(r.date); return t >= from && t <= to; })
          .map(r => ({ date: r.date, series: "日経225", value: r.close, volume: r.volume }))
          .sort((a, b) => a.date.localeCompare(b.date));
      }
      return payload.rows
        .filter(r => r.category === category && r.series === seriesName)
        .filter(r => { const t = parseDate(r.date); return t >= from && t <= to; })
        .sort((a, b) => a.date.localeCompare(b.date));
    }

    function drawLineSeries(svg, values, color = "#1f6feb", yDomain = null) {
      if (values.length < 2) {
        svg.innerHTML = `<text x="50%" y="50%" text-anchor="middle" fill="#68707c">データ不足</text>`;
        return null;
      }
      const xs = values.map(p => parseDate(p.date));
      const ys = values.map(p => p.value).filter(Number.isFinite);
      let minY = yDomain ? yDomain[0] : Math.min(...ys);
      let maxY = yDomain ? yDomain[1] : Math.max(...ys);
      if (minY === maxY) { minY -= 1; maxY += 1; }
      const a = drawAxes(svg, Math.min(...xs), Math.max(...xs), minY, maxY, v => {
        const dt = new Date(v);
        return `${dt.getFullYear()}/${String(dt.getMonth()+1).padStart(2,"0")}`;
      });
      const path = values.filter(p => Number.isFinite(p.value)).map((p, i) => `${i ? "L" : "M"} ${a.xp(parseDate(p.date)).toFixed(1)} ${a.yp(p.value).toFixed(1)}`).join(" ");
      svg.innerHTML = `${a.grid}<path d="${path}" fill="none" stroke="${color}" stroke-width="2"/>`;
      return a;
    }

    function drawTechAxes(svg, minX, maxX, minY, maxY, xLabelFn = null) {
      const width = svg.clientWidth || 900, height = svg.clientHeight || 220;
      const pad = { left: 70, right: 54, top: 18, bottom: 30 };
      if (minY === maxY) { minY -= 1; maxY += 1; }
      const xp = v => pad.left + ((v - minX) / (maxX - minX || 1)) * (width - pad.left - pad.right);
      const yp = v => height - pad.bottom - ((v - minY) / (maxY - minY || 1)) * (height - pad.top - pad.bottom);
      let grid = `<rect x="0" y="0" width="${width}" height="${height}" fill="#06080c"/>`;
      for (let i = 0; i <= 4; i++) {
        const y = pad.top + i * (height - pad.top - pad.bottom) / 4;
        const val = maxY - i * (maxY - minY) / 4;
        grid += `<line x1="${pad.left}" y1="${y}" x2="${width-pad.right}" y2="${y}" stroke="#26303d" stroke-dasharray="2 2"/><text x="${width-pad.right+8}" y="${y+4}" font-size="10" fill="#b7c0cc">${fmt(val)}</text>`;
      }
      for (let i = 0; i <= 6; i++) {
        const x = pad.left + i * (width - pad.left - pad.right) / 6;
        grid += `<line x1="${x}" y1="${pad.top}" x2="${x}" y2="${height-pad.bottom}" stroke="#202833" stroke-dasharray="2 2"/>`;
        if (xLabelFn) {
          const t = minX + i * (maxX - minX) / 6;
          grid += `<text x="${x}" y="${height-10}" text-anchor="middle" font-size="10" fill="#b7c0cc">${xLabelFn(t)}</text>`;
        }
      }
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
      return { width, height, pad, xp, yp, grid };
    }

    function drawTechnical() {
      const rows = selectedTechnicalRows();
      const name = rows[0]?.series || selectedTimeSeries()[0] || "";
      if (rows.length < 30) {
        ["candleChart", "rsiChart", "macdChart", "volumeChart"].forEach(id => $(id).innerHTML = `<text x="50%" y="50%" text-anchor="middle" fill="#68707c">データ不足</text>`);
        $("techSummary").innerHTML = `<div class="metric"><span class="meta">対象</span><b>${name || "-"}</b></div>`;
        return;
      }
      const closes = rows.map(r => r.value);
      const candleRows = rows.map((r, i) => {
        const open = i === 0 ? r.value : rows[i - 1].value;
        return { ...r, open, close: r.value, high: Math.max(open, r.value), low: Math.min(open, r.value) };
      });
      const latest = rows[rows.length - 1];
      const change = rows.length > 1 ? latest.value - rows[rows.length - 2].value : 0;
      const sigma = Number($("bandSigma").value) || 2;
      const bands = movingStats(closes, 20).map(b => ({ ...b, upper: b.mean + sigma * ((b.upper - b.mean) / 2), lower: b.mean - sigma * ((b.mean - b.lower) / 2) }));
      const latestBand = bands[bands.length - 1];
      const bandState = latest.value > latestBand.upper ? "買われすぎ圏" : latest.value < latestBand.lower ? "売られすぎ圏" : "バンド内";
      $("bandSignal").textContent = `${sigma}σ判定: ${bandState}`;
      $("techSummary").innerHTML = [
        ["対象", name],
        ["最新値", fmt(latest.value)],
        ["前回差", `${change >= 0 ? "+" : ""}${fmt(change)}`],
        [`BB ${sigma}σ`, bandState],
      ].map(([k, v]) => `<div class="metric"><span class="meta">${k}</span><b>${v}</b></div>`).join("");

      const xs = rows.map(r => parseDate(r.date));
      const bandRowsAll = rows.map((r, i) => ({ date: r.date, close: r.value, ...bands[i] })).slice(19);
      let minY = Math.min(...candleRows.map(r => r.low), ...bandRowsAll.map(r => r.lower)), maxY = Math.max(...candleRows.map(r => r.high), ...bandRowsAll.map(r => r.upper));
      const candleSvg = $("candleChart");
      const dateLabel = v => {
        const dt = new Date(v);
        return `${dt.getFullYear()}/${String(dt.getMonth()+1).padStart(2,"0")}`;
      };
      const a = drawTechAxes(candleSvg, Math.min(...xs), Math.max(...xs), minY, maxY, dateLabel);
      const bodyW = Math.max(3, (a.width - a.pad.left - a.pad.right) / Math.min(rows.length, 120) * .55);
      const bandPath = field => bandRowsAll.map((p, i) => `${i ? "L" : "M"} ${a.xp(parseDate(p.date)).toFixed(1)} ${a.yp(p[field]).toFixed(1)}`).join(" ");
      const bandArea = `${bandRowsAll.map((p, i) => `${i ? "L" : "M"} ${a.xp(parseDate(p.date)).toFixed(1)} ${a.yp(p.upper).toFixed(1)}`).join(" ")} ${bandRowsAll.slice().reverse().map(p => `L ${a.xp(parseDate(p.date)).toFixed(1)} ${a.yp(p.lower).toFixed(1)}`).join(" ")} Z`;
      const candles = candleRows.map(r => {
        const x = a.xp(parseDate(r.date));
        const up = r.close >= r.open;
        const color = up ? "#f40f23" : "#00d05a";
        const y1 = a.yp(Math.max(r.open, r.close));
        const y2 = a.yp(Math.min(r.open, r.close));
        return `<line x1="${x}" y1="${a.yp(r.high)}" x2="${x}" y2="${a.yp(r.low)}" stroke="${color}"/><rect x="${x-bodyW/2}" y="${y1}" width="${bodyW}" height="${Math.max(1, y2-y1)}" fill="${color}" stroke="${color}"><title>${r.date} O:${fmt(r.open)} C:${fmt(r.close)}</title></rect>`;
      }).join("");
      candleSvg.innerHTML = `${a.grid}<path d="${bandArea}" fill="#204060" opacity=".22"/><path d="${bandPath("upper")}" fill="none" stroke="#5aa0ff" stroke-width="1.1"/><path d="${bandPath("lower")}" fill="none" stroke="#5aa0ff" stroke-width="1.1"/><path d="${bandPath("mean")}" fill="none" stroke="#eab308" stroke-width="1.2"/>${candles}`;

      const rsiValues = rsi(closes).map((v, i) => ({ date: rows[i].date, value: v })).filter(p => p.value !== null);
      const rsiSvg = $("rsiChart");
      const rsiAxis = drawTechAxes(rsiSvg, Math.min(...xs), Math.max(...xs), 0, 100, dateLabel);
      const rsiPath = rsiValues.map((p, i) => `${i ? "L" : "M"} ${rsiAxis.xp(parseDate(p.date)).toFixed(1)} ${rsiAxis.yp(p.value).toFixed(1)}`).join(" ");
      rsiSvg.innerHTML = `${rsiAxis.grid}<rect x="${rsiAxis.pad.left}" y="${rsiAxis.yp(70)}" width="${rsiAxis.width-rsiAxis.pad.left-rsiAxis.pad.right}" height="${rsiAxis.yp(30)-rsiAxis.yp(70)}" fill="#1f2937" opacity=".45"/><line x1="${rsiAxis.pad.left}" y1="${rsiAxis.yp(70)}" x2="${rsiAxis.width-rsiAxis.pad.right}" y2="${rsiAxis.yp(70)}" stroke="#ff5d73"/><line x1="${rsiAxis.pad.left}" y1="${rsiAxis.yp(30)}" x2="${rsiAxis.width-rsiAxis.pad.right}" y2="${rsiAxis.yp(30)}" stroke="#60a5fa"/><path d="${rsiPath}" fill="none" stroke="#f7d000" stroke-width="1.6"/>`;

      const ema12 = ema(closes, 12), ema26 = ema(closes, 26);
      const macdLine = closes.map((_, i) => ema12[i] - ema26[i]);
      const signal = ema(macdLine, 9);
      const macdRows = rows.map((r, i) => ({ date: r.date, value: macdLine[i], signal: signal[i], hist: macdLine[i] - signal[i] })).slice(26);
      const macdSvg = $("macdChart");
      const macdVals = macdRows.flatMap(r => [r.value, r.signal, r.hist]);
      const m = drawTechAxes(macdSvg, Math.min(...xs), Math.max(...xs), Math.min(...macdVals), Math.max(...macdVals), dateLabel);
      const macdPath = field => macdRows.map((p, i) => `${i ? "L" : "M"} ${m.xp(parseDate(p.date)).toFixed(1)} ${m.yp(p[field]).toFixed(1)}`).join(" ");
      const barW = Math.max(2, (m.width - m.pad.left - m.pad.right) / Math.min(macdRows.length, 140) * .45);
      const hist = macdRows.map(p => {
        const x = m.xp(parseDate(p.date));
        const y = m.yp(Math.max(0, p.hist)), h = Math.abs(m.yp(p.hist) - m.yp(0));
        return `<rect x="${x-barW/2}" y="${y}" width="${barW}" height="${Math.max(1,h)}" fill="${p.hist >= 0 ? "#ff4d5f" : "#22c55e"}" opacity=".7"/>`;
      }).join("");
      macdSvg.innerHTML = `${m.grid}<line x1="${m.pad.left}" y1="${m.yp(0)}" x2="${m.width-m.pad.right}" y2="${m.yp(0)}" stroke="#9ca3af"/>${hist}<path d="${macdPath("value")}" fill="none" stroke="#60a5fa" stroke-width="2"/><path d="${macdPath("signal")}" fill="none" stroke="#ff5d73" stroke-width="1.8"/>`;

      const volumeRows = rows.map((r, i) => ({ date: r.date, value: r.volume ?? Math.abs(i ? r.value - rows[i - 1].value : 0) }));
      const volSvg = $("volumeChart");
      const vMax = Math.max(...volumeRows.map(r => r.value)) || 1;
      const v = drawTechAxes(volSvg, Math.min(...xs), Math.max(...xs), 0, vMax, dateLabel);
      const vBarW = Math.max(2, (v.width - v.pad.left - v.pad.right) / Math.min(volumeRows.length, 140) * .5);
      const bars = volumeRows.map(p => {
        const x = v.xp(parseDate(p.date)), y = v.yp(p.value);
        return `<rect x="${x-vBarW/2}" y="${y}" width="${vBarW}" height="${v.height-v.pad.bottom-y}" fill="#7dd3fc" opacity=".55"><title>${p.date}: ${fmt(p.value)}</title></rect>`;
      }).join("");
      volSvg.innerHTML = `${v.grid}${bars}`;
    }

    function drawScatter(points) {
      const svg = $("scatterChart");
      let dragStart = null;
      let dragMoved = false;
      const xs = points.map(p => p.x), ys = points.map(p => p.y);
      let minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
      if (minX === maxX) { minX -= 1; maxX += 1; }
      if (minY === maxY) { minY -= 1; maxY += 1; }
      const a = drawAxes(svg, minX, maxX, minY, maxY);
      const mx = mean(xs), my = mean(ys);
      const slope = xs.reduce((s, v, i) => s + (v - mx) * (ys[i] - my), 0) / (xs.reduce((s, v) => s + (v - mx) ** 2, 0) || 1);
      const intercept = my - slope * mx;
      const line = `<line x1="${a.xp(minX)}" y1="${a.yp(slope*minX+intercept)}" x2="${a.xp(maxX)}" y2="${a.yp(slope*maxX+intercept)}" stroke="#d1242f" stroke-width="2"/>`;
      const plotPoints = points.map(p => ({ ...p, cx: a.xp(p.x), cy: a.yp(p.y) }));
      const dots = points.map(p => {
        const active = selectedPointDates.includes(p.date);
        return `<circle class="clickable-point" data-date="${p.date}" cx="${a.xp(p.x)}" cy="${a.yp(p.y)}" r="${active ? 5 : 2.8}" fill="${active ? "#bf8700" : "#1f6feb"}" opacity="${active ? ".95" : ".55"}"><title>${p.date} X:${fmt(p.x)} Y:${fmt(p.y)}</title></circle>`;
      }).join("");
      svg.innerHTML = `${a.grid}${line}${dots}`;
      const pointFromEvent = ev => {
        const rect = svg.getBoundingClientRect();
        return {
          x: (ev.clientX - rect.left) * (a.width / rect.width),
          y: (ev.clientY - rect.top) * (a.height / rect.height),
        };
      };
      svg.querySelectorAll(".clickable-point").forEach(dot => {
        dot.addEventListener("click", ev => {
          if (dragMoved) return;
          const date = dot.dataset.date;
          if (ev.ctrlKey || ev.metaKey) {
            selectedPointDates = selectedPointDates.includes(date)
              ? selectedPointDates.filter(d => d !== date)
              : [...selectedPointDates, date];
          } else {
            selectedPointDates = [date];
          }
          drawRelationship();
        });
      });
      svg.addEventListener("mousedown", ev => {
        if (ev.target.classList.contains("clickable-point")) return;
        dragStart = pointFromEvent(ev);
        dragMoved = false;
        svg.insertAdjacentHTML("beforeend", `<rect id="brushRect" x="${dragStart.x}" y="${dragStart.y}" width="0" height="0" fill="rgba(31,111,235,.12)" stroke="#1f6feb" stroke-dasharray="4 3"/>`);
      });
      svg.addEventListener("mousemove", ev => {
        if (!dragStart) return;
        const p = pointFromEvent(ev);
        const rect = $("brushRect");
        if (!rect) return;
        const x = Math.min(dragStart.x, p.x), y = Math.min(dragStart.y, p.y);
        const w = Math.abs(p.x - dragStart.x), h = Math.abs(p.y - dragStart.y);
        if (w > 3 || h > 3) dragMoved = true;
        rect.setAttribute("x", x);
        rect.setAttribute("y", y);
        rect.setAttribute("width", w);
        rect.setAttribute("height", h);
      });
      svg.addEventListener("mouseup", ev => {
        if (!dragStart) return;
        const p = pointFromEvent(ev);
        const x1 = Math.min(dragStart.x, p.x), x2 = Math.max(dragStart.x, p.x);
        const y1 = Math.min(dragStart.y, p.y), y2 = Math.max(dragStart.y, p.y);
        $("brushRect")?.remove();
        const picked = plotPoints.filter(pt => pt.cx >= x1 && pt.cx <= x2 && pt.cy >= y1 && pt.cy <= y2).map(pt => pt.date);
        dragStart = null;
        if (dragMoved && picked.length) {
          selectedPointDates = ev.ctrlKey || ev.metaKey
            ? [...new Set([...selectedPointDates, ...picked])]
            : [...new Set(picked)];
          drawRelationship();
        }
      });
    }

    function drawOverlay(points) {
      const svg = $("overlayChart");
      const xs = points.map(p => p.x), ys = points.map(p => p.y);
      const mx = mean(xs), sx = stdev(xs), my = mean(ys), sy = stdev(ys);
      const series = [
        { name: "X", color: "#1f6feb", values: points.map(p => ({ t: parseDate(p.date), v: (p.x - mx) / sx })) },
        { name: "Y", color: "#d1242f", values: points.map(p => ({ t: parseDate(p.date), v: (p.y - my) / sy })) },
      ];
      const all = series.flatMap(s => s.values);
      let minX = Math.min(...all.map(p => p.t)), maxX = Math.max(...all.map(p => p.t)), minY = Math.min(...all.map(p => p.v)), maxY = Math.max(...all.map(p => p.v));
      if (minY === maxY) { minY -= 1; maxY += 1; }
      const a = drawAxes(svg, minX, maxX, minY, maxY, v => {
        const dt = new Date(v);
        return `${dt.getFullYear()}/${String(dt.getMonth()+1).padStart(2,"0")}`;
      });
      const paths = series.map(s => `<path d="${s.values.map((p, i) => `${i ? "L" : "M"} ${a.xp(p.t).toFixed(1)} ${a.yp(p.v).toFixed(1)}`).join(" ")}" fill="none" stroke="${s.color}" stroke-width="2"><title>${s.name}</title></path>`).join("");
      svg.innerHTML = `${a.grid}${paths}`;
    }

    function drawRollingCorrelation(points) {
      const svg = $("corrChart");
      const windowSize = Math.max(10, Number($("corrWindow").value) || 90);
      const values = [];
      for (let i = windowSize - 1; i < points.length; i++) {
        const slice = points.slice(i - windowSize + 1, i + 1);
        const c = corr(slice);
        if (Number.isFinite(c)) values.push({ t: parseDate(points[i].date), v: c });
      }
      if (!values.length) {
        svg.innerHTML = `<text x="50%" y="50%" text-anchor="middle" fill="#68707c">データ不足</text>`;
        return;
      }
      const minX = Math.min(...values.map(p => p.t)), maxX = Math.max(...values.map(p => p.t));
      const a = drawAxes(svg, minX, maxX, -1, 1, v => {
        const dt = new Date(v);
        return `${dt.getFullYear()}/${String(dt.getMonth()+1).padStart(2,"0")}`;
      });
      const zero = `<line x1="${a.pad.left}" y1="${a.yp(0)}" x2="${a.width-a.pad.right}" y2="${a.yp(0)}" stroke="#c8ced8"/>`;
      const path = `<path d="${values.map((p, i) => `${i ? "L" : "M"} ${a.xp(p.t).toFixed(1)} ${a.yp(p.v).toFixed(1)}`).join(" ")}" fill="none" stroke="#8250df" stroke-width="2"/>`;
      svg.innerHTML = `${a.grid}${zero}${path}`;
    }

    function renderRelationTable(points) {
      const selectedRows = selectedPointDates
        .map(date => points.find(p => p.date === date))
        .filter(Boolean)
        .sort((a, b) => b.date.localeCompare(a.date));
      $("selectedPoint").textContent = selectedRows.length
        ? `選択中: ${selectedRows.length.toLocaleString()}点`
        : "散布図の点をクリック、Ctrl/Commandクリック、またはドラッグ範囲選択で該当データを抽出できます。";
      const selectedSet = new Set(selectedRows.map(p => p.date));
      const latest = points.slice(-30).reverse().filter(p => !selectedSet.has(p.date));
      const rows = [...selectedRows, ...latest];
      $("relationTable").innerHTML = `<table><thead><tr><th>日付</th><th>X</th><th>Y</th></tr></thead><tbody>${rows.map(p => `<tr class="${selectedSet.has(p.date) ? "selected-row" : ""}"><td>${p.date}</td><td>${fmt(p.x)}</td><td>${fmt(p.y)}</td></tr>`).join("")}</tbody></table>`;
    }

    function buildFactorMaps() {
      const from = activeTab === "overview"
        ? ($("allFrom").value ? parseDate($("allFrom").value) : -Infinity)
        : ($("relFrom").value ? parseDate($("relFrom").value) : -Infinity);
      const to = activeTab === "overview"
        ? ($("allTo").value ? parseDate($("allTo").value) : Infinity)
        : ($("relTo").value ? parseDate($("relTo").value) : Infinity);
      const maps = new Map();
      for (const r of payload.rows) {
        const t = parseDate(r.date);
        if (t < from || t > to) continue;
        const key = factorKey(r);
        if (!maps.has(key)) maps.set(key, new Map());
        maps.get(key).set(r.date, r.value);
      }
      return maps;
    }

    function pairedRowsFromMaps(maps, xKey, yKey) {
      const xMap = maps.get(xKey);
      const yMap = maps.get(yKey);
      if (!xMap || !yMap) return [];
      return [...xMap.entries()]
        .filter(([date]) => yMap.has(date))
        .map(([date, x]) => ({ date, x, y: yMap.get(date) }))
        .sort((a, b) => a.date.localeCompare(b.date));
    }

    function computeCorrelationRanking(mode = "focused") {
      const maps = buildFactorMaps();
      const keys = [...maps.keys()].sort();
      const base = keys.filter(k => baseCategories.has(factorCategory(k)));
      const comps = keys.filter(k => comparisonCategories.has(factorCategory(k)));
      const minCount = mode === "all" ? Math.max(10, Number($("allMinCount").value) || 60) : 30;
      const out = [];
      for (let i = 0; i < base.length; i++) {
        const xKey = base[i];
        for (let j = 0; j < comps.length; j++) {
          const yKey = comps[j];
          if (xKey === yKey) continue;
          const points = pairedRowsFromMaps(maps, xKey, yKey);
          if (points.length < minCount) continue;
          const c = corr(points);
          if (!Number.isFinite(c)) continue;
          out.push({ xKey, yKey, corr: c, abs: Math.abs(c), count: points.length, first: points[0].date, last: points[points.length - 1].date });
        }
      }
      return out.sort((a, b) => b.abs - a.abs).slice(0, 80);
    }

    function toggleRankPair(index) {
      const pair = currentRankPairs[index];
      if (!pair) return;
      const id = relationId(pair);
      if (selectedPairs.some(p => relationId(p) === id)) {
        selectedPairs = selectedPairs.filter(p => relationId(p) !== id);
      } else if (selectedPairs.length < 6) {
        selectedPairs.push(pair);
      } else {
        alert("表示できるグラフは最大6つまでです。");
        return;
      }
      $("xFactor").value = pair.xKey;
      $("yFactor").value = pair.yKey;
      selectedPointDates = [];
      drawRelationship();
      saveUiState();
    }

    function drawSmallScatter(svg, points) {
      const xs = points.map(p => p.x), ys = points.map(p => p.y);
      let minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
      if (minX === maxX) { minX -= 1; maxX += 1; }
      if (minY === maxY) { minY -= 1; maxY += 1; }
      const a = drawAxes(svg, minX, maxX, minY, maxY);
      const dots = points.map(p => `<circle cx="${a.xp(p.x)}" cy="${a.yp(p.y)}" r="2" fill="#1f6feb" opacity=".45"><title>${p.date} X:${fmt(p.x)} Y:${fmt(p.y)}</title></circle>`).join("");
      svg.innerHTML = `${a.grid}${dots}`;
    }

    function renderSelectedPairCharts() {
      const target = $("selectedPairCharts");
      target.innerHTML = selectedPairs.map((pair, i) => `<div class="pair-card"><h3>${i + 1}. ${factorLabel(pair.xKey)}<br>× ${factorLabel(pair.yKey)}<br>r=${pair.corr.toFixed(3)} / n=${pair.count.toLocaleString()}</h3><svg id="pairChart${i}" aria-label="選択ペア散布図"></svg></div>`).join("");
      for (let i = 0; i < selectedPairs.length; i++) {
        const points = relationshipRowsForKeys(selectedPairs[i].xKey, selectedPairs[i].yKey);
        if (points.length >= 3) drawSmallScatter($(`pairChart${i}`), points);
      }
    }

    function renderPairCharts(targetId, pairs, idPrefix) {
      const target = $(targetId);
      target.innerHTML = pairs.map((pair, i) => `<div class="pair-card"><h3>${i + 1}. ${factorLabel(pair.xKey)}<br>× ${factorLabel(pair.yKey)}<br>r=${pair.corr.toFixed(3)} / n=${pair.count.toLocaleString()}</h3><svg id="${idPrefix}${i}" aria-label="選択ペア散布図"></svg></div>`).join("");
      const from = activeTab === "overview" && $("allFrom").value ? parseDate($("allFrom").value) : ($("relFrom").value ? parseDate($("relFrom").value) : -Infinity);
      const to = activeTab === "overview" && $("allTo").value ? parseDate($("allTo").value) : ($("relTo").value ? parseDate($("relTo").value) : Infinity);
      for (let i = 0; i < pairs.length; i++) {
        const points = relationshipRowsForKeysInRange(pairs[i].xKey, pairs[i].yKey, from, to);
        if (points.length >= 3) drawSmallScatter($(`${idPrefix}${i}`), points);
      }
    }

    function renderCorrelationRanking() {
      currentRankPairs = computeCorrelationRanking();
      if (!restoredRelationPairs && savedUi.selectedPairIds?.length) {
        selectedPairs = savedUi.selectedPairIds
          .map(id => currentRankPairs.find(p => relationId(p) === id))
          .filter(Boolean);
        restoredRelationPairs = true;
      }
      selectedPairs = selectedPairs
        .map(pair => currentRankPairs.find(p => relationId(p) === relationId(pair)))
        .filter(Boolean);
      $("correlationRank").innerHTML = `<table><thead><tr><th>選択</th><th>横軸</th><th>縦軸</th><th>相関</th><th>n</th><th>期間</th></tr></thead><tbody>${currentRankPairs.map((p, i) => {
        const checked = selectedPairs.some(s => relationId(s) === relationId(p));
        return `<tr class="${checked ? "checked" : ""}" data-rank="${i}"><td><input type="checkbox" ${checked ? "checked" : ""} aria-label="選択"></td><td>${factorLabel(p.xKey)}</td><td>${factorLabel(p.yKey)}</td><td>${p.corr.toFixed(3)}</td><td>${p.count.toLocaleString()}</td><td>${p.first} - ${p.last}</td></tr>`;
      }).join("")}</tbody></table>`;
      $("correlationRank").querySelectorAll("tbody tr").forEach(row => {
        row.addEventListener("click", () => toggleRankPair(Number(row.dataset.rank)));
      });
      $("correlationRank").querySelectorAll("input").forEach(input => {
        input.addEventListener("click", ev => ev.stopPropagation());
        input.addEventListener("change", ev => toggleRankPair(Number(input.closest("tr").dataset.rank)));
      });
      renderSelectedPairCharts();
    }

    function toggleAllRankPair(index) {
      const pair = allRankPairs[index];
      if (!pair) return;
      const id = relationId(pair);
      if (allSelectedPairs.some(p => relationId(p) === id)) {
        allSelectedPairs = allSelectedPairs.filter(p => relationId(p) !== id);
      } else if (allSelectedPairs.length < 6) {
        allSelectedPairs.push(pair);
      } else {
        alert("表示できるグラフは最大6つまでです。");
        return;
      }
      renderOverviewRanking();
      saveUiState();
    }

    function renderOverviewRanking() {
      allRankPairs = computeCorrelationRanking("all");
      if (!restoredOverviewPairs && savedUi.allSelectedPairIds?.length) {
        allSelectedPairs = savedUi.allSelectedPairIds
          .map(id => allRankPairs.find(p => relationId(p) === id))
          .filter(Boolean);
        restoredOverviewPairs = true;
      }
      allSelectedPairs = allSelectedPairs
        .map(pair => allRankPairs.find(p => relationId(p) === relationId(pair)))
        .filter(Boolean);
      $("allCorrelationRank").innerHTML = `<table><thead><tr><th>選択</th><th>系列A</th><th>系列B</th><th>相関</th><th>n</th><th>期間</th></tr></thead><tbody>${allRankPairs.map((p, i) => {
        const checked = allSelectedPairs.some(s => relationId(s) === relationId(p));
        return `<tr class="${checked ? "checked" : ""}" data-rank="${i}"><td><input type="checkbox" ${checked ? "checked" : ""} aria-label="選択"></td><td>${factorLabel(p.xKey)}</td><td>${factorLabel(p.yKey)}</td><td>${p.corr.toFixed(3)}</td><td>${p.count.toLocaleString()}</td><td>${p.first} - ${p.last}</td></tr>`;
      }).join("")}</tbody></table>`;
      $("allCorrelationRank").querySelectorAll("tbody tr").forEach(row => {
        row.addEventListener("click", () => toggleAllRankPair(Number(row.dataset.rank)));
      });
      $("allCorrelationRank").querySelectorAll("input").forEach(input => {
        input.addEventListener("click", ev => ev.stopPropagation());
        input.addEventListener("change", () => toggleAllRankPair(Number(input.closest("tr").dataset.rank)));
      });
      renderPairCharts("allSelectedPairCharts", allSelectedPairs, "allPairChart");
    }

    function initStatsControls() {
      if (!payload?.rows?.length) return;
      const categories = [...new Set(payload.rows.map(r => r.category))].filter(c => c !== "統計処理");
      const preferred = ["NT倍率", "信用評価損益率", "投資主体別売買動向", "空売り比率", "騰落レシオ", "株価トレンド", "為替", "商品先物"];
      const selectedCats = [...$("statsCategories").selectedOptions].map(o => o.value);
      const savedCats = savedUi.statsCategories || [];
      $("statsCategories").innerHTML = categories.map(c => `<option value="${c}" ${selectedCats.includes(c) || (!selectedCats.length && preferred.includes(c)) ? "selected" : ""}>${c}</option>`).join("");
      if (!selectedCats.length && savedCats.length) {
        [...$("statsCategories").options].forEach(o => o.selected = savedCats.includes(o.value));
      }
      const factors = [...new Set(payload.rows.map(factorKey))].sort((a, b) => factorLabel(a).localeCompare(factorLabel(b), "ja"));
      const oldTargets = [...$("regTargets").querySelectorAll("input:checked")].map(input => input.value);
      const defaultTargets = factors.filter(f => f.includes("日経225")).slice(0, 1);
      const targetSet = new Set(oldTargets.length ? oldTargets : (savedUi.regTargets?.length ? savedUi.regTargets.slice(0, 5) : defaultTargets));
      $("regTargets").innerHTML = factors.map(f => `<label><input type="checkbox" name="regTarget" value="${esc(f)}" ${targetSet.has(f) ? "checked" : ""}>${factorLabel(f)}</label>`).join("");
      const oldFeatures = [...$("regFeatures").querySelectorAll("input:checked")].map(input => input.value);
      const featureSet = new Set(oldFeatures.length ? oldFeatures : (savedUi.regFeatures?.length ? savedUi.regFeatures : factors.filter(f => baseCategories.has(factorCategory(f)))));
      $("regFeatures").innerHTML = factors.map(f => `<label><input type="checkbox" name="regFeature" value="${esc(f)}" ${featureSet.has(f) ? "checked" : ""}>${factorLabel(f)}</label>`).join("");
      wireStatsCheckboxes();
    }

    function selectedRegressionTargets() {
      return [...$("regTargets").querySelectorAll("input:checked")].map(input => input.value).slice(0, 5);
    }

    function selectedRegressionFeatures() {
      return [...$("regFeatures").querySelectorAll("input:checked")].map(input => input.value);
    }

    function wireStatsCheckboxes() {
      $("regTargets").querySelectorAll("input").forEach(input => {
        input.onchange = () => {
          const checked = selectedRegressionTargets();
          if ($("regTargets").querySelectorAll("input:checked").length > 5) {
            input.checked = false;
            alert("目的変数は最大5個まで選択できます。");
            return;
          }
          draw();
          saveUiState();
        };
      });
      $("regFeatures").querySelectorAll("input").forEach(input => {
        input.onchange = () => { draw(); saveUiState(); };
      });
    }

    function statsMaps() {
      const cats = new Set([...$("statsCategories").selectedOptions].map(o => o.value));
      const minCount = Math.max(30, Number($("statsMinCount").value) || 120);
      const maps = new Map();
      for (const r of payload.rows) {
        if (!cats.has(r.category)) continue;
        const key = factorKey(r);
        if (!maps.has(key)) maps.set(key, new Map());
        maps.get(key).set(r.date, r.value);
      }
      return new Map([...maps.entries()].filter(([, map]) => map.size >= minCount));
    }

    function alignedMatrix(maps, keys) {
      if (!keys.length) return { dates: [], matrix: [] };
      const dateCounts = new Map();
      keys.forEach(k => maps.get(k)?.forEach((_, d) => dateCounts.set(d, (dateCounts.get(d) || 0) + 1)));
      const dates = [...dateCounts.entries()].filter(([, c]) => c === keys.length).map(([d]) => d).sort();
      return { dates, matrix: dates.map(d => keys.map(k => maps.get(k).get(d))) };
    }

    function pcaFromMatrix(matrix) {
      const rows = matrix.length, cols = matrix[0]?.length || 0;
      if (rows < 30 || cols < 2) return null;
      const means = Array.from({ length: cols }, (_, j) => mean(matrix.map(r => r[j])));
      const sds = Array.from({ length: cols }, (_, j) => stdev(matrix.map(r => r[j])));
      const z = matrix.map(r => r.map((v, j) => (v - means[j]) / sds[j]));
      const cov = Array.from({ length: cols }, (_, i) => Array.from({ length: cols }, (_, j) => z.reduce((a, r) => a + r[i] * r[j], 0) / Math.max(rows - 1, 1)));
      const mv = (mat, vec) => mat.map(row => row.reduce((a, v, i) => a + v * vec[i], 0));
      const norm = vec => Math.sqrt(vec.reduce((a, v) => a + v * v, 0)) || 1;
      const component = mat => {
        let v = Array.from({ length: cols }, () => 1 / Math.sqrt(cols));
        for (let it = 0; it < 80; it++) {
          const next = mv(mat, v);
          const n = norm(next);
          v = next.map(x => x / n);
        }
        const av = mv(mat, v);
        const eigen = v.reduce((a, x, i) => a + x * av[i], 0);
        return { vector: v, eigen };
      };
      const pc1 = component(cov);
      const deflated = cov.map((row, i) => row.map((v, j) => v - pc1.eigen * pc1.vector[i] * pc1.vector[j]));
      const pc2 = component(deflated);
      const total = cov.reduce((a, row, i) => a + row[i], 0) || 1;
      return { pc1, pc2, total };
    }

    function drawPcaChart(loadings, pc1Ratio, pc2Ratio) {
      const svg = $("pcaChart");
      if (!loadings.length) {
        svg.innerHTML = `<text x="50%" y="50%" text-anchor="middle" fill="#68707c">データ不足</text>`;
        return;
      }
      const width = svg.clientWidth || 720, height = svg.clientHeight || 430;
      const pad = { left: 58, right: 28, top: 28, bottom: 54 };
      const maxAbs = Math.max(1, ...loadings.flatMap(r => [Math.abs(r.pc1), Math.abs(r.pc2)]));
      const domain = Math.min(1.25, Math.max(1, maxAbs * 1.12));
      const xp = v => pad.left + ((v + domain) / (domain * 2)) * (width - pad.left - pad.right);
      const yp = v => height - pad.bottom - ((v + domain) / (domain * 2)) * (height - pad.top - pad.bottom);
      const cx = xp(0), cy = yp(0);
      let grid = "";
      for (let i = -1; i <= 1; i += .5) {
        if (Math.abs(i) > domain) continue;
        grid += `<line x1="${xp(i)}" y1="${pad.top}" x2="${xp(i)}" y2="${height-pad.bottom}" stroke="#edf0f5"/>`;
        grid += `<line x1="${pad.left}" y1="${yp(i)}" x2="${width-pad.right}" y2="${yp(i)}" stroke="#edf0f5"/>`;
        grid += `<text x="${xp(i)}" y="${height-20}" text-anchor="middle" font-size="10" fill="#68707c">${i.toFixed(1)}</text>`;
        if (i !== 0) grid += `<text x="${pad.left-8}" y="${yp(i)+4}" text-anchor="end" font-size="10" fill="#68707c">${i.toFixed(1)}</text>`;
      }
      const radius = Math.min(xp(1) - xp(0), yp(0) - yp(1));
      const circle = `<circle cx="${cx}" cy="${cy}" r="${radius}" fill="none" stroke="#c8ced8" stroke-dasharray="4 4"/>`;
      const axes = `<line x1="${pad.left}" y1="${cy}" x2="${width-pad.right}" y2="${cy}" stroke="#8c96a3"/><line x1="${cx}" y1="${height-pad.bottom}" x2="${cx}" y2="${pad.top}" stroke="#8c96a3"/>
        <text x="${width-pad.right}" y="${height-16}" text-anchor="end" font-size="12" font-weight="700" fill="#20242a">PC1 ${pct(pc1Ratio)}</text>
        <text x="${pad.left+4}" y="${pad.top+12}" font-size="12" font-weight="700" fill="#20242a">PC2 ${pct(pc2Ratio)}</text>`;
      const arrows = loadings.map((r, i) => {
        const x = xp(r.pc1), y = yp(r.pc2);
        const color = colors[i % colors.length];
        const labelX = x + (r.pc1 >= 0 ? 7 : -7);
        const labelY = y + (r.pc2 >= 0 ? -7 : 13);
        const anchor = r.pc1 >= 0 ? "start" : "end";
        return `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="${color}" stroke-width="1.8" marker-end="url(#arrowhead)"><title>${esc(factorLabel(r.key))} PC1:${r.pc1.toFixed(3)} PC2:${r.pc2.toFixed(3)}</title></line>
          <circle cx="${x}" cy="${y}" r="3.5" fill="${color}"/>
          <text x="${labelX}" y="${labelY}" text-anchor="${anchor}" font-size="10.5" fill="#20242a">${esc(factorLabel(r.key)).slice(0, 34)}</text>`;
      }).join("");
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
      svg.innerHTML = `<defs><marker id="arrowhead" markerWidth="8" markerHeight="8" refX="7" refY="3.5" orient="auto"><polygon points="0 0, 8 3.5, 0 7" fill="#68707c"/></marker></defs>${grid}${circle}${axes}${arrows}`;
    }

    function renderPca(maps) {
      const keys = [...maps.keys()].sort((a, b) => maps.get(b).size - maps.get(a).size).slice(0, 16);
      const { dates, matrix } = alignedMatrix(maps, keys);
      const pca = pcaFromMatrix(matrix);
      if (!pca) {
        $("pcaResult").innerHTML = `<div class="empty">共通日付のデータが不足しています</div>`;
        return { dates: 0, factors: keys.length };
      }
      const loadings = keys.map((key, i) => ({
        key,
        pc1: pca.pc1.vector[i] * Math.sqrt(Math.max(pca.pc1.eigen, 0)),
        pc2: pca.pc2.vector[i] * Math.sqrt(Math.max(pca.pc2.eigen, 0)),
      }))
        .sort((a, b) => Math.abs(b.pc1) - Math.abs(a.pc1));
      drawPcaChart(loadings, pca.pc1.eigen / pca.total, pca.pc2.eigen / pca.total);
      $("pcaResult").innerHTML = `<div class="summary">
        <div class="metric"><span class="meta">PC1寄与率</span><b>${pct(pca.pc1.eigen / pca.total)}</b></div>
        <div class="metric"><span class="meta">PC2寄与率</span><b>${pct(pca.pc2.eigen / pca.total)}</b></div>
      </div><table><thead><tr><th>因子</th><th>PC1</th><th>PC2</th></tr></thead><tbody>${loadings.map(r => `<tr><td>${factorLabel(r.key)}</td><td>${r.pc1.toFixed(3)}</td><td>${r.pc2.toFixed(3)}</td></tr>`).join("")}</tbody></table>`;
      return { dates: dates.length, factors: keys.length };
    }

    function drawFactorEffectChart(svg, rows) {
      if (!rows.length) {
        svg.innerHTML = `<text x="50%" y="50%" text-anchor="middle" fill="#68707c">データ不足</text>`;
        return;
      }
      const width = svg.clientWidth || 420, height = svg.clientHeight || 430;
      const pad = { left: 150, right: 28, top: 24, bottom: 34 };
      const maxAbs = Math.max(...rows.map(r => Math.abs(r.beta))) || 1;
      const xp = v => pad.left + ((v + maxAbs) / (maxAbs * 2)) * (width - pad.left - pad.right);
      const rowH = (height - pad.top - pad.bottom) / rows.length;
      let out = `<rect x="0" y="0" width="${width}" height="${height}" fill="#fff"/><line x1="${xp(0)}" y1="${pad.top}" x2="${xp(0)}" y2="${height-pad.bottom}" stroke="#8c96a3"/>`;
      rows.forEach((r, i) => {
        const y = pad.top + i * rowH + rowH * .5;
        const x0 = xp(0), x1 = xp(r.beta);
        const x = Math.min(x0, x1), w = Math.abs(x1 - x0);
        const color = r.beta >= 0 ? "#d1242f" : "#1f6feb";
        out += `<text x="${pad.left-8}" y="${y+4}" text-anchor="end" font-size="10" fill="#20242a">${esc(factorLabel(r.key)).slice(0, 24)}</text>`;
        out += `<rect x="${x}" y="${y-rowH*.28}" width="${Math.max(1,w)}" height="${rowH*.56}" fill="${color}" opacity=".78"><title>${esc(factorLabel(r.key))}: ${r.beta.toFixed(3)}</title></rect>`;
        out += `<text x="${r.beta >= 0 ? x1 + 5 : x1 - 5}" y="${y+4}" text-anchor="${r.beta >= 0 ? "start" : "end"}" font-size="10" fill="#20242a">${r.beta.toFixed(2)}</text>`;
      });
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
      svg.innerHTML = out;
    }

    function drawPredActualChart(svg, points, c) {
      if (points.length < 3) {
        svg.innerHTML = `<text x="50%" y="50%" text-anchor="middle" fill="#68707c">データ不足</text>`;
        return;
      }
      const xs = points.map(p => p.pred), ys = points.map(p => p.actual);
      let min = Math.min(...xs, ...ys), max = Math.max(...xs, ...ys);
      if (min === max) { min -= 1; max += 1; }
      const a = drawAxes(svg, min, max, min, max);
      const dots = points.map(p => `<circle cx="${a.xp(p.pred)}" cy="${a.yp(p.actual)}" r="2.6" fill="#1f6feb" opacity=".48"><title>${p.date} 予測:${fmt(p.pred)} 実績:${fmt(p.actual)}</title></circle>`).join("");
      svg.innerHTML = `${a.grid}<line x1="${a.xp(min)}" y1="${a.yp(min)}" x2="${a.xp(max)}" y2="${a.yp(max)}" stroke="#d1242f" stroke-width="2"/><text x="${a.pad.left+8}" y="${a.pad.top+18}" font-size="12" font-weight="700" fill="#20242a">予測値と実績値の相関 r=${Number.isFinite(c) ? c.toFixed(3) : "-"}</text>${dots}`;
    }

    function renderRegression() {
      const maps = buildFactorMaps();
      const targets = selectedRegressionTargets();
      if (!targets.length) {
        $("regressionResult").innerHTML = `<div class="empty">目的変数を1個以上選択してください</div>`;
        return;
      }
      $("regressionResult").innerHTML = targets.map((target, i) => `<div class="regression-card" id="regCard${i}">
        <div class="summary" id="regSummary${i}"></div>
        <div id="regEquation${i}" class="equation"></div>
        <div class="regression-charts">
          <div><h2>予測式と各因子の関係</h2><svg id="factorEffectChart${i}" aria-label="予測式と各因子の関係"></svg></div>
          <div><h2>予測値と実績値</h2><svg id="predActualChart${i}" aria-label="予測値と実績値の相関"></svg></div>
        </div>
        <div id="regTable${i}"></div>
      </div>`).join("");
      targets.forEach((target, index) => renderRegressionForTarget(target, selectedRegressionFeatures().filter(k => k !== target).slice(0, 12), maps, index));
    }

    function renderRegressionForTarget(target, featureKeys, maps, index) {
      const keys = [target, ...featureKeys].filter(k => maps.has(k));
      const usableFeatures = keys.slice(1);
      const { dates, matrix } = alignedMatrix(maps, keys);
      if (dates.length < 30 || keys.length < 2) {
        $(`regSummary${index}`).innerHTML = `<div class="metric"><span class="meta">目的変数</span><b>${factorLabel(target)}</b></div>`;
        $(`regEquation${index}`).innerHTML = "回帰に必要な共通日付のデータが不足しています。";
        [`factorEffectChart${index}`, `predActualChart${index}`].forEach(id => $(id).innerHTML = `<text x="50%" y="50%" text-anchor="middle" fill="#68707c">データ不足</text>`);
        $(`regTable${index}`).innerHTML = "";
        return;
      }
      const y = matrix.map(r => r[0]);
      const xRaw = matrix.map(r => r.slice(1));
      const xMeans = usableFeatures.map((_, j) => mean(xRaw.map(r => r[j])));
      const xSds = usableFeatures.map((_, j) => stdev(xRaw.map(r => r[j])));
      const yMean = mean(y), ySd = stdev(y);
      const x = xRaw.map(r => r.map((v, j) => (v - xMeans[j]) / xSds[j]));
      const zy = y.map(v => (v - yMean) / ySd);
      const p = usableFeatures.length;
      const xtx = Array.from({ length: p }, (_, i) => Array.from({ length: p }, (_, j) => x.reduce((a, row) => a + row[i] * row[j], 0) + (i === j ? 1e-6 : 0)));
      const xty = Array.from({ length: p }, (_, i) => x.reduce((a, row, r) => a + row[i] * zy[r], 0));
      const beta = solveLinearSystem(xtx, xty);
      const preds = x.map(row => row.reduce((a, v, i) => a + v * beta[i], 0));
      const actualPreds = preds.map(v => yMean + v * ySd);
      const ssRes = preds.reduce((a, pred, i) => a + (zy[i] - pred) ** 2, 0);
      const ssTot = zy.reduce((a, v) => a + v ** 2, 0) || 1;
      const unscaled = usableFeatures.map((key, i) => ({ key, beta: beta[i], coef: ySd * beta[i] / xSds[i] }));
      const intercept = yMean - unscaled.reduce((a, r, i) => a + r.coef * xMeans[i], 0);
      const rows = unscaled.slice().sort((a, b) => Math.abs(b.beta) - Math.abs(a.beta));
      const predPoints = dates.map((date, i) => ({ date, actual: y[i], pred: actualPreds[i], x: actualPreds[i], y: y[i] }));
      const predCorr = corr(predPoints);
      $(`regSummary${index}`).innerHTML = `
        <div class="metric"><span class="meta">目的変数</span><b>${factorLabel(target)}</b></div>
        <div class="metric"><span class="meta">決定係数 R²</span><b>${Math.max(0, 1 - ssRes / ssTot).toFixed(3)}</b></div>
        <div class="metric"><span class="meta">予測・実績相関</span><b>${Number.isFinite(predCorr) ? predCorr.toFixed(3) : "-"}</b></div>
        <div class="metric"><span class="meta">共通データ数</span><b>${dates.length.toLocaleString()}</b></div>
      `;
      $(`regTable${index}`).innerHTML = `<table><thead><tr><th>説明変数</th><th>標準化係数</th></tr></thead><tbody>${rows.map(r => `<tr><td>${factorLabel(r.key)}</td><td>${r.beta.toFixed(3)}</td></tr>`).join("")}</tbody></table>`;
      $(`regEquation${index}`).innerHTML = `<b>予測式</b><br>${esc(factorLabel(target))} = ${intercept.toFixed(4)} ${unscaled.map(r => `${r.coef >= 0 ? "+" : "-"} ${Math.abs(r.coef).toFixed(4)} × ${esc(factorLabel(r.key))}`).join(" ")}`;
      drawFactorEffectChart($(`factorEffectChart${index}`), rows);
      drawPredActualChart($(`predActualChart${index}`), predPoints, predCorr);
    }

    function drawStats() {
      if (!$("statsCategories").options.length) initStatsControls();
      const maps = statsMaps();
      const pcaInfo = renderPca(maps);
      renderRegression();
      $("statsSummary").innerHTML = [
        ["対象因子", maps.size.toLocaleString()],
        ["PCA使用因子", pcaInfo.factors.toLocaleString()],
        ["PCA共通日付", pcaInfo.dates.toLocaleString()],
      ].map(([k, v]) => `<div class="metric"><span class="meta">${k}</span><b>${v}</b></div>`).join("");
    }

    function drawOverview() {
      if (!payload || !payload.rows) return;
      renderOverviewRanking();
    }

    function drawRelationship() {
      if (!payload || !payload.rows) return;
      const points = joinedRelationshipRows();
      if (points.length < 3) {
        ["scatterChart", "overlayChart", "corrChart"].forEach(id => $(id).innerHTML = `<text x="50%" y="50%" text-anchor="middle" fill="#68707c">共通日付のデータ不足</text>`);
        $("relationSummary").innerHTML = "";
        $("relationTable").innerHTML = "";
        $("selectedPoint").textContent = "";
        renderCorrelationRanking();
        return;
      }
      const c = corr(points);
      const xs = points.map(p => p.x), ys = points.map(p => p.y);
      const slope = xs.reduce((s, v, i) => s + (v - mean(xs)) * (ys[i] - mean(ys)), 0) / (xs.reduce((s, v) => s + (v - mean(xs)) ** 2, 0) || 1);
      $("relationSummary").innerHTML = [
        ["共通データ数", points.length.toLocaleString()],
        ["相関係数", Number.isFinite(c) ? c.toFixed(3) : "-"],
        ["回帰傾き", Number.isFinite(slope) ? slope.toFixed(4) : "-"],
        ["期間", `${points[0].date} - ${points[points.length - 1].date}`],
      ].map(([k, v]) => `<div class="metric"><span class="meta">${k}</span><b>${v}</b></div>`).join("");
      drawScatter(points);
      drawOverlay(points);
      drawRollingCorrelation(points);
      renderRelationTable(points);
      renderCorrelationRanking();
    }

    const drawAndSave = () => { draw(); saveUiState(); };
    $("series").onchange = drawAndSave;
    $("timeView").onchange = () => { activateTab($("timeView").value === "tech" ? "tech" : "time"); drawAndSave(); };
    $("timeScale").onchange = drawAndSave;
    $("from").onchange = drawAndSave;
    $("to").onchange = drawAndSave;
    $("xFactor").onchange = () => { selectedPointDates = []; drawAndSave(); };
    $("yFactor").onchange = () => { selectedPointDates = []; drawAndSave(); };
    $("relFrom").onchange = drawAndSave;
    $("relTo").onchange = drawAndSave;
    $("corrWindow").onchange = drawAndSave;
    $("allFrom").onchange = drawAndSave;
    $("allTo").onchange = drawAndSave;
    $("allMinCount").onchange = drawAndSave;
    $("statsCategories").onchange = drawAndSave;
    $("statsMinCount").onchange = drawAndSave;
    $("bandSigma").onchange = drawAndSave;
    $("showCustomLine").onchange = drawAndSave;
    $("customLineValue").oninput = drawAndSave;
    $("showZeroLine").onchange = drawAndSave;
    $("showSigma2").onchange = drawAndSave;
    $("showSigma3").onchange = drawAndSave;
    function activateTab(tabName) {
      activeTab = tabName;
      document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === tabName));
      if (tabName === "time") $("timeView").value = "line";
      if (tabName === "tech") $("timeView").value = "tech";
      $("timePane").classList.toggle("active", tabName === "time" || tabName === "tech");
      $("relationPane").classList.toggle("active", tabName === "relation");
      $("overviewPane").classList.toggle("active", tabName === "overview");
      $("statsPane").classList.toggle("active", tabName === "stats");
    }
    document.querySelectorAll(".tab").forEach(tab => {
      tab.onclick = () => {
        if (category === "全体" || category === "統計処理") {
          const realCats = [...new Set(payload.rows.map(r => r.category))];
          category = realCats[0];
          activateTab(tab.dataset.tab);
          loadData();
          return;
        }
        activateTab(tab.dataset.tab);
        drawAndSave();
      };
    });
    $("refresh").onclick = async () => {
      $("status").textContent = "更新確認中...";
      const res = await fetch("/api/update", { method: "POST" });
      const data = await res.json();
      $("status").textContent = data.changed ? "新しいデータを取得しました" : "更新なし";
      await loadData();
    };
    window.onresize = draw;
    restoreStaticControls();
    loadData();
    if ("serviceWorker" in navigator) {
      window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
    }
  </script>
</body>
</html>"""


def ensure_cache() -> None:
    if load_cache() is None:
        try:
            refresh_cache()
        except Exception as exc:
            STATE["last_error"] = str(exc)


def weekly_worker() -> None:
    while True:
        now = datetime.now(JST)
        week_key = f"{now.isocalendar().year}-{now.isocalendar().week}"
        if now.weekday() == 3 and now.hour >= WEEKLY_CHECK_HOUR and STATE["last_weekly_check"] != week_key:
            try:
                STATE["refreshing"] = True
                refresh_cache()
                STATE["last_weekly_check"] = week_key
                STATE["last_error"] = None
            except Exception as exc:
                STATE["last_error"] = str(exc)
            finally:
                STATE["refreshing"] = False
        time.sleep(60 * 30)


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path in ("/manifest.json", "/sw.js") or path.startswith("/icons/"):
            file_path = PUBLIC_DIR / path.lstrip("/")
            if file_path.exists() and file_path.is_file():
                content_type = "application/manifest+json" if path.endswith(".json") else "application/javascript" if path.endswith(".js") else "image/svg+xml"
                self._send(200, file_path.read_bytes(), content_type)
                return
        if path == "/api/data":
            cache = load_cache() or {"rows": [], "error": STATE["last_error"]}
            self._send(200, json.dumps(cache, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        if path == "/api/status":
            body = {**STATE, "now": datetime.now(JST).isoformat(timespec="seconds")}
            self._send(200, json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        if path == "/api/export.csv":
            cache = load_cache() or {"rows": []}
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=["date", "category", "series", "value"])
            writer.writeheader()
            writer.writerows(cache.get("rows", []))
            self._send(200, output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/update":
            try:
                STATE["refreshing"] = True
                payload = refresh_cache()
                STATE["last_error"] = None
                self._send(200, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                STATE["last_error"] = str(exc)
                self._send(500, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            finally:
                STATE["refreshing"] = False
            return
        self._send(404, b"not found", "text/plain; charset=utf-8")

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    ensure_cache()
    threading.Thread(target=weekly_worker, daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print(f"Open {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    server.serve_forever()


if __name__ == "__main__":
    main()
