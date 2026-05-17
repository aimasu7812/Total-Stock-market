from __future__ import annotations

import csv
import hmac
import io
import json
import os
import sys
from datetime import datetime
from http import cookies
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import INDEX_HTML  # noqa: E402
from data_sources import JST, load_cache, refresh_cache  # noqa: E402


COOKIE_NAME = "nikkei_dashboard_auth"


def _password() -> str:
    return os.environ.get("DASHBOARD_PASSWORD", "")


def _secret() -> bytes:
    return os.environ.get("DASHBOARD_SECRET") or _password() or "local-dev-only"


def _token() -> str:
    return hmac.new(str(_secret()).encode("utf-8"), b"nikkei225-dashboard", "sha256").hexdigest()


def _login_html(message: str = "") -> bytes:
    msg = f"<p class='error'>{message}</p>" if message else ""
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ログイン - 日経225指標</title>
  <style>
    body {{ margin:0; min-height:100vh; display:grid; place-items:center; font-family:system-ui,-apple-system,sans-serif; background:#f7f8fa; color:#20242a; }}
    form {{ width:min(92vw,380px); background:#fff; border:1px solid #d8dde6; border-radius:10px; padding:24px; box-shadow:0 10px 30px rgba(0,0,0,.08); }}
    h1 {{ font-size:20px; margin:0 0 16px; }}
    label {{ display:grid; gap:6px; font-size:13px; color:#68707c; }}
    input {{ font:inherit; padding:10px 12px; border:1px solid #d8dde6; border-radius:8px; }}
    button {{ width:100%; margin-top:16px; padding:10px 12px; border:0; border-radius:8px; background:#1f6feb; color:#fff; font-weight:700; }}
    .error {{ color:#d1242f; font-size:13px; }}
  </style>
</head>
<body>
  <form method="post" action="/login">
    <h1>日経225 指標ダッシュボード</h1>
    {msg}
    <label>パスワード<input type="password" name="password" autocomplete="current-password" autofocus></label>
    <button type="submit">ログイン</button>
  </form>
</body>
</html>""".encode("utf-8")


class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _authenticated(self) -> bool:
        password = _password()
        if not password:
            return not os.environ.get("VERCEL")
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        morsel = jar.get(COOKIE_NAME)
        return bool(morsel and hmac.compare_digest(morsel.value, _token()))

    def _require_auth(self) -> bool:
        if self._authenticated():
            return True
        if not _password() and os.environ.get("VERCEL"):
            self._send(503, _login_html("Vercelの環境変数 DASHBOARD_PASSWORD を設定してください。"), "text/html; charset=utf-8")
        else:
            self._send(401, _login_html(), "text/html; charset=utf-8")
        return False

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/login":
            self._send(200, _login_html(), "text/html; charset=utf-8")
            return
        if not self._require_auth():
            return
        if path in ("/", "/index.html"):
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/data":
            cache = load_cache()
            if cache is None:
                cache = refresh_cache()
            cache = {k: v for k, v in cache.items() if k != "data_dir"}
            self._send(200, json.dumps(cache, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        if path == "/api/status":
            body = {"now": datetime.now(JST).isoformat(timespec="seconds")}
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
        if path == "/login":
            length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(length).decode("utf-8")
            supplied = parse_qs(body).get("password", [""])[0]
            if _password() and hmac.compare_digest(supplied, _password()):
                headers = {
                    "Set-Cookie": f"{COOKIE_NAME}={_token()}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000",
                    "Location": "/",
                }
                self._send(303, b"", "text/plain; charset=utf-8", headers)
                return
            self._send(401, _login_html("パスワードが違います。"), "text/html; charset=utf-8")
            return
        if not self._require_auth():
            return
        if path == "/api/update":
            try:
                payload = refresh_cache()
                payload = {k: v for k, v in payload.items() if k != "data_dir"}
                self._send(200, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain; charset=utf-8")

