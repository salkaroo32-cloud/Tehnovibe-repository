from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv
from pypdf import PdfReader

from .analyzer import analyze_statement

load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SBER_ONLINE_URL = os.getenv("SBER_ONLINE_URL", "https://online.sberbank.ru/")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", "15")) * 1024 * 1024

router = Router()


class Flow(StatesGroup):
    waiting_statement = State()


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Получить выписку", callback_data="get_statement")],
    ])


def sber_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏦 Открыть СберБанк Онлайн", url=SBER_ONLINE_URL)],
        [InlineKeyboardButton(text="📎 Я получил выписку", callback_data="waiting_statement")],
    ])


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Привет! Я помогу найти регулярные платежи и возможные подписки по банковской выписке.\n\n"
        "Нажми «Получить выписку», чтобы открыть СберБанк Онлайн.",
        reply_markup=main_keyboard(),
    )


@router.callback_query(F.data == "get_statement")
async def get_statement(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Flow.waiting_statement)
    await callback.message.answer(
        "Открой СберБанк Онлайн и скачай выписку по нужной карте/счёту. "
        "Для первого анализа лучше выбрать период 6–12 месяцев.\n\n"
        "После скачивания пришли сюда PDF-файл выписки. Я жду файл.",
        reply_markup=sber_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "waiting_statement")
async def waiting_statement(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Flow.waiting_statement)
    await callback.message.answer("Отлично. Пришли сюда PDF-файл выписки — я начну анализ сразу после получения.")
    await callback.answer()


async def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def format_report(result: dict) -> str:
    counts = result["counts"]
    lines = [
        "📊 <b>Отчёт по выписке</b>",
        "",
        f"Операций распознано: <b>{len(result['operations'])}</b>",
        f"Регулярных платежей-кандидатов: <b>{counts.get('регулярный платёж неизвестного типа', 0)}</b>",
        f"Банковских/финансовых операций: <b>{counts.get('банковская комиссия/услуга', 0) + counts.get('перевод/финансовая операция', 0)}</b>",
        "",
        "<b>Подписки</b>",
    ]
    subscriptions = result["subscriptions"]
    if not subscriptions:
        lines.append("Пока нет подписок с достаточным количеством повторений для уверенного определения.")
    else:
        for item in subscriptions[:10]:
            lines.extend([
                "",
                f"• <b>{item.merchant}</b>",
                f"  ≈ {item.amount:.2f} ₽ / {item.period_days:.0f} дней",
                f"  Повторений: {item.occurrences}",
                f"  Уверенность: {item.confidence:.0%}",
                f"  Основание: {item.reason}",
            ])

    service_like = [
        c for c in result["classifications"]
        if c.type == "подписка/сервис" and c.operation.outgoing
    ]
    if service_like:
        lines.extend(["", "<b>Сервисы, требующие дополнительной проверки</b>"])
        for c in service_like[:10]:
            lines.append(f"• {c.operation.description[:90]} — {c.operation.amount:.2f} ₽ ({c.confidence:.0%})")

    lines.extend([
        "",
        "ℹ️ Регулярность сама по себе не означает подписку. "
        "В отчёт не включаются как подписки операции, похожие на банковские комиссии и переводы.",
        "Результат является аналитическим предположением, а не финансовой рекомендацией.",
    ])
    return "\n".join(lines)


@router.message(Flow.waiting_statement, F.document)
async def statement_received(message: Message, state: FSMContext, bot: Bot) -> None:
    document = message.document
    if not document:
        return
    if document.file_size and document.file_size > MAX_FILE_SIZE:
        await message.answer(f"Файл слишком большой. Максимальный размер: {MAX_FILE_SIZE // 1024 // 1024} МБ.")
        return
    if not document.file_name or not document.file_name.lower().endswith(".pdf"):
        await message.answer("Для этого MVP пришли, пожалуйста, PDF-выписку из СберБанка.")
        return

    await message.answer("⏳ Выписка получена. Распознаю операции и проверяю регулярные платежи…")
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        await bot.download(document, destination=tmp_path)
        text = await asyncio.to_thread(extract_pdf_text, tmp_path)
        if len(text.strip()) < 100:
            await message.answer("Не удалось извлечь текст из PDF. Пришли текстовую PDF-выписку из СберБанка или выгрузку в табличном формате.")
            return
        result = await asyncio.to_thread(analyze_statement, text)
        await message.answer(format_report(result), parse_mode="HTML")
        await state.clear()
    except Exception:
        logging.exception("Statement analysis failed")
        await message.answer("Не удалось обработать выписку. Проверь, что это PDF из СберБанка, и попробуй ещё раз.")
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)


@router.message(Flow.waiting_statement)
async def wrong_document(message: Message) -> None:
    await message.answer("Я жду PDF-выписку из СберБанка. Пришли её сюда как файл.")


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
