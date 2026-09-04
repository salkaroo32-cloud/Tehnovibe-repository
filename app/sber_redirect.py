from __future__ import annotations

import html
import os
from urllib.parse import quote

from aiohttp import web

SBER_ONLINE_URL = (os.getenv("SBER_ONLINE_URL") or "https://online.sberbank.ru/").strip()
SBER_ANDROID_DEEPLINK = (
    os.getenv("SBER_ANDROID_DEEPLINK") or "sberbankonline://sberbankid/sso"
).strip()
SBER_IOS_DEEPLINK = (
    os.getenv("SBER_IOS_DEEPLINK") or "sberbankonline://sberbankid/sso"
).strip()


def detect_platform(user_agent: str) -> str:
    ua = user_agent.lower()
    if "android" in ua:
        return "android"
    if "iphone" in ua or "ipad" in ua or "ipod" in ua:
        return "ios"
    return "other"


def build_redirect_html(deep_link: str, fallback_url: str, platform: str) -> str:
    # The deep link is intentionally configurable. Sber documents these links
    # for Sber ID/SSO flows; this page only performs a best-effort app launch.
    safe_deep_link = html.escape(deep_link, quote=True)
    safe_fallback = html.escape(fallback_url, quote=True)
    js_deep_link = deep_link.replace("\\", "\\\\").replace("'", "\\'")
    js_fallback = fallback_url.replace("\\", "\\\\").replace("'", "\\'")
    return f"""<!doctype html>
<html lang=\"ru\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
  <title>Открываем СберБанк Онлайн</title>
</head>
<body>
  <p>Открываем приложение СберБанк Онлайн…</p>
  <p><a href=\"{safe_deep_link}\">Если приложение не открылось, нажмите здесь</a></p>
  <p><a href=\"{safe_fallback}\">Открыть веб-версию</a></p>
  <script>
    const deepLink = '{js_deep_link}';
    const fallback = '{js_fallback}';
    const startedAt = Date.now();
    window.location.href = deepLink;
    setTimeout(() => {{
      if (Date.now() - startedAt < 2500) window.location.href = fallback;
    }}, 1800);
  </script>
</body>
</html>"""


async def sber_redirect(request: web.Request) -> web.Response:
    platform = detect_platform(request.headers.get("User-Agent", ""))

    if platform == "android":
        deep_link = SBER_ANDROID_DEEPLINK
    elif platform == "ios":
        deep_link = SBER_IOS_DEEPLINK
    else:
        raise web.HTTPFound(SBER_ONLINE_URL)

    return web.Response(
        text=build_redirect_html(deep_link, SBER_ONLINE_URL, platform),
        content_type="text/html",
    )


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/sber", sber_redirect)
    app.router.add_get("/health", lambda _: web.json_response({"ok": True}))
    return app


def public_redirect_url() -> str:
    base = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/sber"
