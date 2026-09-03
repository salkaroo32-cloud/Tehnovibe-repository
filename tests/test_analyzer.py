from app.analyzer import analyze_statement, parse_statement_text


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
    charges = [
        c for c in result["classifications"]
        if "Regular Charge" in c.operation.description
    ]
    assert charges
    assert all(c.type == "банковская комиссия/услуга" for c in charges)
    assert not result["subscriptions"]


def test_yandex_is_service_candidate_but_not_subscription_from_one_payment():
    result = analyze_statement(SAMPLE)
    service_candidates = [
        c for c in result["classifications"]
        if c.type == "подписка/сервис"
    ]
    assert any("YANDEX" in c.operation.description.upper() for c in service_candidates)
    assert not any(s.merchant == "Yandex Plus" for s in result["subscriptions"])


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


def test_sber_processing_date_in_description_does_not_break_operation_parsing():
    text = """
26.06.2026 17:21 Прочие операции 40,00 1 960,00
06.07.2026 514360 3801 Regular Charge: June. Операция по карте ****5402
"""
    operations = parse_statement_text(text)
    assert len(operations) == 1
    assert operations[0].date.strftime("%d.%m.%Y") == "26.06.2026"
    assert operations[0].amount == 40.0
    assert "Regular Charge" in operations[0].description


def test_sber_transfer_and_incoming_transfer_are_not_services():
    text = """
03.09.2026 22:53 Прочие операции +10,00 10,00
03.09.2026 107150 Т-Банк. Операция по карте ****5402
14.08.2026 20:28 Перевод СБП 2 000,00 0,00
14.08.2026 269734 Перевод в T-Bank. Операция по карте ****5402
14.08.2026 20:03 Перевод на карту +2 000,00 2 000,00
14.08.2026 913710 Перевод от С. Сергей Александрович. Операция по карте ****5402
"""
    result = analyze_statement(text)
    assert not any(c.type == "подписка/сервис" for c in result["classifications"])
    assert all(c.type in {"перевод/финансовая операция", "недостаточно данных"} for c in result["classifications"])
