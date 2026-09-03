from app.analyzer import analyze_statement


SAMPLE = """
08.01.2026 16:47 Прочие расходы 27 813,00 2 147,80
108060 WB*WILDBERRIES SBERPAY MOSCOW RUS
26.12.2025 17:21 Прочие операции 40,00 29 960,80
08.01.2026 020674 3801 Regular Charge: December
26.01.2026 17:21 Прочие операции 40,00 7,80
26.01.2026 989808 3801 Regular Charge: January
26.04.2026 17:21 Прочие операции 40,00 51,80
06.05.2026 849213 3801 Regular Charge: April
01.06.2026 17:57 Перевод СБП 9 960,00 0,00
01.06.2026 171474 3801 Regular Charge: May
17.02.2026 19:48 Прочие расходы 1,00 6,80
17.02.2026 452446 YANDEX*5815*PLUS MOSCOW RUS
"""


def test_regular_charge_is_not_subscription():
    result = analyze_statement(SAMPLE)
    assert any(c.type == "банковская комиссия/услуга" and "Regular Charge" in c.operation.description for c in result["classifications"])


def test_yandex_is_service_candidate_but_not_subscription_from_one_payment():
    result = analyze_statement(SAMPLE)
    service_candidates = [c for c in result["classifications"] if c.type == "подписка/сервис"]
    assert any("YANDEX" in c.operation.description.upper() for c in service_candidates)
    assert not any("Yandex Plus" == s.merchant for s in result["subscriptions"])


def test_repeated_service_can_be_subscription():
    sample = """
01.01.2026 10:00 Прочие расходы 299,00 0,00
123456 YANDEX*PLUS MOSCOW RUS
31.01.2026 10:00 Прочие расходы 299,00 0,00
123457 YANDEX*PLUS MOSCOW RUS
02.03.2026 10:00 Прочие расходы 299,00 0,00
123458 YANDEX*PLUS MOSCOW RUS
01.04.2026 10:00 Прочие расходы 299,00 0,00
123459 YANDEX*PLUS MOSCOW RUS
"""
    result = analyze_statement(sample)
    assert any(s.merchant == "Yandex Plus" for s in result["subscriptions"])
