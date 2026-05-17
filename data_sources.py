from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://nikkei225jp.com"
REFERER = f"{BASE_URL}/data/shutai.php"
JST = timezone(timedelta(hours=9))
DEFAULT_DATA_DIR = Path("/tmp/nikkei225-dashboard-data") if os.environ.get("VERCEL") else Path("/Volumes/Crucial X9/AI/nikkei225-dashboard-data")
DATA_DIR = Path(os.environ.get("NIKKEI225_DATA_DIR", DEFAULT_DATA_DIR))
CACHE_PATH = DATA_DIR / "cache.json"
BUNDLED_CACHE_PATH = Path("data/cache.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    ),
    "Referer": REFERER,
}


DATA_FILES = {
    "daily2": "/_data/_nfsWEB/DAY/daily2.json?494150",
    "daily2year": "/_data/_nfsWEB/DAY/daily2year.json?494150",
    "dailyweek2": "/_data/_nfsWEB/DAY/dailyweek2.json?494150",
    "s111": "/_data/_nfsWEB/HS_DATA_DAY/S111.json?494150",
    "s112": "/_data/_nfsWEB/HS_DATA_DAY/S112.json?494150",
    "s113": "/_data/_nfsWEB/HS_DATA_DAY/S113.json?494150",
}


MARKET_SERIES = {
    "111": ("株価トレンド", "日経225"),
    "112": ("株価トレンド", "TOPIX"),
    "121": ("株価トレンド", "グロース250"),
    "141": ("株価トレンド", "東証REIT指数"),
    "161": ("株価トレンド", "日経VI"),
    "211": ("株価トレンド", "NYダウ"),
    "212": ("株価トレンド", "NASDAQ総合"),
    "213": ("株価トレンド", "S&P 500"),
    "214": ("株価トレンド", "NASDAQ 100"),
    "216": ("株価トレンド", "Russell 2000"),
    "511": ("為替", "USD/JPY"),
    "514": ("為替", "EUR/JPY"),
    "515": ("為替", "GBP/JPY"),
    "516": ("為替", "AUD/JPY"),
    "523": ("為替", "EUR/USD"),
    "501": ("為替", "ドルインデックス"),
    "921": ("商品先物", "WTI原油先物"),
    "922": ("商品先物", "ブレント原油先物"),
    "931": ("商品先物", "金先物"),
    "912": ("商品先物", "銅先物"),
}

MARKET_CATEGORIES = {category for category, _ in MARKET_SERIES.values()}
ANALYSIS_ANCHOR_CATEGORIES = {
    "NT倍率",
    "信用評価損益率",
    "投資主体別売買動向",
    "空売り比率",
    "騰落レシオ",
}


def _array_text(source: str, var_name: str) -> str:
    marker = re.search(rf"\bvar\s+{re.escape(var_name)}\s*=", source)
    if not marker:
        raise ValueError(f"{var_name} was not found in source")
    start = source.find("[", marker.end())
    if start < 0:
        raise ValueError(f"{var_name} array start was not found")

    depth = 0
    in_string = False
    quote = ""
    escape = False
    for pos in range(start, len(source)):
        ch = source[pos]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
            continue
        if ch in ("'", '"'):
            in_string = True
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return source[start : pos + 1]
    raise ValueError(f"{var_name} array end was not found")


def _parse_js_array(source: str, var_name: str) -> list[list[Any]]:
    text = _array_text(source, var_name)
    text = text.replace("'", '"')
    # The site uses JavaScript sparse-array notation such as `1,,3`.
    # JSON has no sparse values, so normalize those holes to null.
    text = re.sub(r"\[\s*,", "[null,", text)
    text = re.sub(r",\s*\]", ",null]", text)
    while re.search(r",\s*,", text):
        text = re.sub(r",\s*,", ",null,", text)
    return json.loads(text)


def _fetch_js(path: str) -> str:
    response = requests.get(BASE_URL + path, headers=HEADERS, timeout=30)
    response.raise_for_status()
    if "404 Not Found" in response.text[:300]:
        raise RuntimeError(f"404 from {path}; the site may require updated cache keys")
    return response.text


def _to_date(ms: int | float) -> str:
    return datetime.fromtimestamp(ms / 1000, JST).date().isoformat()


def _to_date_obj(ms: int | float) -> date:
    return datetime.fromtimestamp(ms / 1000, JST).date()


def _num(value: Any) -> float | None:
    if value == "" or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _add(rows: list[dict[str, Any]], date_ms: Any, category: str, series: str, value: Any) -> None:
    number = _num(value)
    if number is None:
        return
    _add_date(rows, _to_date(int(date_ms)), category, series, number)


def _add_date(rows: list[dict[str, Any]], date_str: str, category: str, series: str, value: Any) -> None:
    number = _num(value)
    if number is None:
        return
    rows.append({"date": date_str, "category": category, "series": series, "value": number})


def _moving_ratio(period: int):
    rises: list[float] = []
    falls: list[float] = []

    def calc(up: Any, down: Any) -> float | None:
        u = _num(up)
        d = _num(down)
        if u is None:
            return None
        rises.append(u)
        if len(rises) > period:
            rises.pop(0)
        if d and d > 0:
            falls.append(d)
            if len(falls) > period:
                falls.pop(0)
            return sum(rises) / sum(falls) * 100 if sum(falls) else None
        return sum(rises) / period

    return calc


def fetch_all() -> dict[str, Any]:
    market_files = {
        f"s{code}": f"/_data/_nfsWEB/HS_DATA_DAY/S{code}.json?494150"
        for code in MARKET_SERIES
    }
    sources = {name: _fetch_js(path) for name, path in {**DATA_FILES, **market_files}.items()}
    daily2 = _parse_js_array(sources["daily2"], "DAILY")
    daily2year = _parse_js_array(sources["daily2year"], "DAILY")
    dailyweek2 = _parse_js_array(sources["dailyweek2"], "DAILY")
    s111 = _parse_js_array(sources["s111"], "S111")
    s112 = _parse_js_array(sources["s112"], "S112")
    s113 = _parse_js_array(sources["s113"], "S113")

    rows: list[dict[str, Any]] = []
    market_daily: dict[tuple[str, str], list[tuple[date, float]]] = {}

    for code, (category, label) in MARKET_SERIES.items():
        source_key = f"s{code}"
        try:
            series_rows = _parse_js_array(sources[source_key], f"S{code}")
        except ValueError:
            continue
        points: list[tuple[date, float]] = []
        for r in series_rows:
            if len(r) >= 2 and _num(r[1]) is not None:
                points.append((_to_date_obj(int(r[0])), float(_num(r[1]))))
        market_daily[(category, label)] = sorted(points, key=lambda item: item[0])

    for r in dailyweek2:
        if len(r) < 24 or int(r[0]) <= 1365351600000:
            continue
        labels = {
            7: "信用評価損益率",
            8: "信用倍率",
            9: "証券自己",
            11: "個人 計",
            12: "海外投資家",
            14: "投資信託",
            15: "事業法人",
            16: "その他法人",
            18: "生保・損保",
            19: "都銀・地銀",
            20: "信託銀行",
            22: "個人 現金",
            23: "個人 信用",
        }
        for idx, label in labels.items():
            category = "信用評価損益率" if idx in (7, 8) else "投資主体別売買動向"
            _add(rows, r[0], category, label, r[idx])

    ratio25 = _moving_ratio(25)
    ratio15 = _moving_ratio(15)
    ratio10 = _moving_ratio(10)
    ratio6 = _moving_ratio(6)
    for r in daily2year:
        if len(r) < 25:
            continue
        _add(rows, r[0], "騰落レシオ", "25日(掲載値)", r[7])
        for label, value in (
            ("25日(計算値)", ratio25(r[5], r[6])),
            ("15日", ratio15(r[5], r[6])),
            ("10日", ratio10(r[5], r[6])),
            ("6日", ratio6(r[5], r[6])),
        ):
            _add(rows, r[0], "騰落レシオ", label, value)
        _add(rows, r[0], "空売り比率", "空売り比率 合計", (_num(r[22]) or 0) + (_num(r[24]) or 0))
        _add(rows, r[0], "空売り比率", "価格規制あり", r[22])
        _add(rows, r[0], "空売り比率", "価格規制なし", r[24])

    for r in daily2:
        if len(r) < 28:
            continue
        per = r[25] if _num(r[25]) is not None else r[12]
        pbr = r[26] if _num(r[26]) is not None else r[13]
        _add(rows, r[0], "日経225 PER", "PER", per)
        _add(rows, r[0], "日経225 PER", "PBR", pbr)
        _add(rows, r[0], "日経225 PER", "配当利回り", r[27] if _num(r[27]) is not None else r[14])
        if _num(r[1]) is not None and _num(r[17]) not in (None, 0):
            _add(rows, r[0], "ドル建て日経平均", "ドル建て日経平均", _num(r[1]) / _num(r[17]))
        if _num(r[1]) is not None and _num(r[18]) not in (None, 0):
            _add(rows, r[0], "ドル建て日経平均", "ユーロ建て日経平均", _num(r[1]) / _num(r[18]))

    for i, r in enumerate(s111):
        if i >= len(s112):
            break
        n225 = _num(r[1])
        topix = _num(s112[i][1])
        jpx400 = _num(s113[i][1]) if i < len(s113) else None
        if n225 is not None and topix:
            _add(rows, r[0], "NT倍率", "NT倍率(日経225/TOPIX)", n225 / topix)
        if n225 is not None and jpx400:
            _add(rows, r[0], "NT倍率", "日経225/JPX400", n225 / jpx400)
        if topix and jpx400:
            _add(rows, r[0], "NT倍率", "JPX400/TOPIX", jpx400 / topix)

    anchor_dates = sorted(
        {
            datetime.fromisoformat(row["date"]).date()
            for row in rows
            if row["category"] in ANALYSIS_ANCHOR_CATEGORIES
        }
    )
    for (category, label), points in market_daily.items():
        if not points:
            continue
        values_by_date = dict(points)
        for anchor in anchor_dates:
            start = anchor - timedelta(days=6)
            values = [value for day, value in values_by_date.items() if start <= day <= anchor]
            if values:
                _add_date(rows, anchor.isoformat(), category, f"{label} (週平均)", sum(values) / len(values))

    technical: list[dict[str, Any]] = []
    for r in daily2:
        if len(r) < 20:
            continue
        close = _num(r[1])
        if close is None:
            continue
        item = {"date": _to_date(int(r[0])), "series": "日経225", "close": close}
        volume = _num(r[19])
        if volume is not None:
            item["volume"] = volume
        technical.append(item)

    rows.sort(key=lambda row: (row["category"], row["series"], row["date"]))
    payload = {
        "source": BASE_URL,
        "fetched_at": datetime.now(JST).isoformat(timespec="seconds"),
        "data_dir": str(DATA_DIR),
        "rows": rows,
        "technical": sorted(technical, key=lambda row: row["date"]),
    }
    payload["fingerprint"] = hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return payload


def load_cache() -> dict[str, Any] | None:
    if not CACHE_PATH.exists():
        if BUNDLED_CACHE_PATH.exists():
            return json.loads(BUNDLED_CACHE_PATH.read_text(encoding="utf-8"))
        return None
    return json.loads(CACHE_PATH.read_text(encoding="utf-8"))


def save_cache(payload: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def refresh_cache() -> dict[str, Any]:
    old = load_cache()
    payload = fetch_all()
    payload["changed"] = bool(old and old.get("fingerprint") != payload["fingerprint"])
    payload["previous_fetched_at"] = old.get("fetched_at") if old else None
    save_cache(payload)
    return payload
