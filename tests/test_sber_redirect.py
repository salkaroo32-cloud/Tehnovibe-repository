from app.sber_redirect import build_redirect_html, detect_platform


def test_detect_platform_android() -> None:
    assert detect_platform("Mozilla/5.0 (Linux; Android 15; Pixel 9)") == "android"


def test_detect_platform_ios() -> None:
    assert detect_platform("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)") == "ios"


def test_detect_platform_other() -> None:
    assert detect_platform("Mozilla/5.0 (Windows NT 10.0; Win64; x64)") == "other"


def test_redirect_html_contains_deep_link_and_fallback() -> None:
    html = build_redirect_html(
        "sberbankonline://sberbankid/sso",
        "https://online.sberbank.ru/",
        "android",
    )
    assert "sberbankonline://sberbankid/sso" in html
    assert "https://online.sberbank.ru/" in html
