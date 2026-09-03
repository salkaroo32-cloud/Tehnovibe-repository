from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import re
from statistics import mean


DATE_RE = re.compile(r"(?P<date>\d{2}\.\d{2}\.\d{4})\s+(?P<time>\d{2}:\d{2})")
AMOUNT_RE = re.compile(r"(?P<sign>[+-]?)\s*(?P<amount>\d[\d\s\u00a0]*,\d{2})")

BANK_PATTERNS = (
    "regular charge",
    "перевод с карты",
    "перевод сбп",
    "перевод на карту",
    "перевод от",
    "перевод для",
    "т-банк",
    "t-bank",
    "ozon bank",
)

KNOWN_SERVICE_PATTERNS = {
    "Yandex Plus": ("yandex*", "yandex plus", "yandex*plus"),
    "Wildberries": ("wb*wildberries", "wildberries"),
}


@dataclass(frozen=True)
class Operation:
    date: datetime
    amount: float
    description: str
    category: str
    outgoing: bool


@dataclass(frozen=True)
class Classification:
    operation: Operation
    type: str
    confidence: float
    reason: str


@dataclass(frozen=True)
class SubscriptionCandidate:
    merchant: str
    amount: float
    occurrences: int
    period_days: float
    confidence: float
    last_date: datetime
    reason: str


def _money(value: str) -> float:
    return float(value.replace(" ", "").replace("\u00a0", "").replace(",", "."))


def _blocks(text: str) -> list[str]:
    matches = list(DATE_RE.finditer(text))
    return [text[matches[i].start() : matches[i + 1].start() if i + 1 < len(matches) else len(text)] for i in range(len(matches))]


def parse_statement_text(text: str) -> list[Operation]:
    operations: list[Operation] = []
    for block in _blocks(text):
        header = block.splitlines()[0].strip()
        dm = DATE_RE.search(header)
        if not dm:
            continue
        amount_match = AMOUNT_RE.search(header[dm.end() :])
        if not amount_match:
            continue
        amount = _money(amount_match.group("amount"))
        sign = amount_match.group("sign")
        category_part = header[dm.end() : amount_match.start()].strip()
        description = " ".join(x.strip() for x in block.splitlines()[1:] if x.strip())
        description = re.sub(r"\s+", " ", description)
        # Sber's statement places the transaction description after the auth code.
        if not description:
            description = category_part
        outgoing = sign != "+" and not category_part.lower().startswith("перевод на карту")
        # For this MVP, expense-like categories and merchant descriptors are outgoing unless explicitly credited.
        if category_part.lower().startswith("перевод с карты") or category_part.lower().startswith("прочие расходы"):
            outgoing = True
        if category_part.lower().startswith("прочие операции") and sign != "+":
            outgoing = True
        operations.append(
            Operation(
                date=datetime.strptime(f"{dm.group('date')} {dm.group('time')}", "%d.%m.%Y %H:%M"),
                amount=amount,
                description=f"{category_part} {description}".strip(),
                category=category_part,
                outgoing=outgoing,
            )
        )
    return operations


def normalize_merchant(description: str) -> str:
    value = description.lower()
    value = re.sub(r"\*+\d+\*", "*", value)
    value = re.sub(r"\d{4,}", "", value)
    value = re.sub(r"\s+", " ", value).strip(" .,-")
    for name, patterns in KNOWN_SERVICE_PATTERNS.items():
        if any(pattern in value for pattern in patterns):
            return name
    return value


def classify_operations(operations: list[Operation]) -> list[Classification]:
    result: list[Classification] = []
    for op in operations:
        text = f"{op.category} {op.description}".lower()
        if any(pattern in text for pattern in BANK_PATTERNS):
            if "regular charge" in text:
                result.append(Classification(op, "банковская комиссия/услуга", 0.92, "Признак Regular Charge в выписке; не считаем подпиской без подтверждения сервиса."))
            elif "перевод" in text or "банк" in text:
                result.append(Classification(op, "перевод/финансовая операция", 0.95, "Операция похожа на перевод между финансовыми организациями/счетами."))
            else:
                result.append(Classification(op, "банковская комиссия/услуга", 0.80, "Descriptor похож на банковскую операцию."))
            continue
        if any(pattern in text for patterns in KNOWN_SERVICE_PATTERNS.values() for pattern in patterns):
            result.append(Classification(op, "подписка/сервис", 0.75, "Descriptor соответствует известному сервису подписочного типа."))
        elif op.outgoing:
            result.append(Classification(op, "регулярный платёж неизвестного типа", 0.45, "Списание требует дополнительных повторений или идентификации merchant."))
        else:
            result.append(Classification(op, "недостаточно данных", 0.30, "Операция не выглядит как расход на сервис."))
    return result


def detect_subscriptions(operations: list[Operation], classifications: list[Classification]) -> list[SubscriptionCandidate]:
    eligible = [c.operation for c in classifications if c.type == "подписка/сервис" and c.operation.outgoing]
    grouped: dict[str, list[Operation]] = defaultdict(list)
    for op in eligible:
        grouped[normalize_merchant(op.description)].append(op)

    candidates: list[SubscriptionCandidate] = []
    for merchant, ops in grouped.items():
        ops.sort(key=lambda x: x.date)
        if len(ops) < 2:
            continue
        gaps = [(ops[i].date - ops[i - 1].date).days for i in range(1, len(ops))]
        avg_gap = mean(gaps)
        if not (20 <= avg_gap <= 45):
            continue
        amounts = [x.amount for x in ops]
        avg_amount = mean(amounts)
        spread = max(amounts) - min(amounts)
        stability = max(0.0, 1.0 - spread / max(avg_amount, 1.0))
        periodicity = 1.0 - min(abs(avg_gap - 30) / 30, 1.0)
        confidence = min(0.99, 0.45 + 0.25 * periodicity + 0.20 * stability + 0.10 * min(len(ops) / 6, 1.0))
        candidates.append(
            SubscriptionCandidate(
                merchant=merchant,
                amount=avg_amount,
                occurrences=len(ops),
                period_days=avg_gap,
                confidence=confidence,
                last_date=ops[-1].date,
                reason=f"{len(ops)} списаний, средний интервал {avg_gap:.0f} дн., средняя сумма {avg_amount:.2f} ₽.",
            )
        )
    return sorted(candidates, key=lambda x: x.confidence, reverse=True)


def analyze_statement(text: str) -> dict:
    operations = parse_statement_text(text)
    classifications = classify_operations(operations)
    subscriptions = detect_subscriptions(operations, classifications)
    counts: dict[str, int] = defaultdict(int)
    for c in classifications:
        counts[c.type] += 1
    return {
        "operations": operations,
        "classifications": classifications,
        "subscriptions": subscriptions,
        "counts": dict(counts),
    }
