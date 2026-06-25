# CODING_STYLE.md — Конвенции кода LeadHunter

Этот файл задаёт правила написания кода. CLAUDE.md ссылается на него. Все участники (человек и Claude Code) следуют этим правилам.

---

## 0. Главный принцип

**Код пишется для чтения, не для написания.** Если коллега (или ты через месяц) не поймёт функцию за 15 секунд — перепиши.

---

## 1. Функции

### Одна ответственность
Функция делает ровно одну вещь. Если можно описать через «И» — разделяй.

```python
# ❌ Плохо: обрабатывает сообщение И отправляет уведомление
async def handle_message(event):
    text = event.message.text
    segments = classify_message(text)
    if segments:
        users = await find_users(...)
        for u in users:
            await send_notification(u, text)

# ✅ Хорошо: разделено
async def handle_message(event: NewMessage.Event) -> None:
    lead = extract_lead(event)
    if not lead:
        return
    await dispatch_to_interested_users(lead)
```

### Максимум 30 строк
Функция длиннее 30 строк — кандидат на разделение. Исключение: FSM-хендлеры с большим количеством состояний (но каждый state — отдельная функция).

### Ранний возврат
Избегай вложенных if'ов. Проверяй условия и выходи рано.

```python
# ❌ Плохо
async def process(user):
    if user:
        if user.plan != "free":
            if not user.is_banned:
                await send(user)

# ✅ Хорошо
async def process(user: User | None) -> None:
    if not user:
        return
    if user.plan == "free":
        return
    if user.is_banned:
        return
    await send(user)
```

---

## 2. Именование

### Переменные — осмысленно, не сокращая
```python
# ✅
user: User
matched_segments: list[str]
message_hash: str

# ❌
u, ms, mh
```

Исключения (только в узком контексте):
- `e` — исключение в `except X as e`
- `i`, `j` — индекс в коротком цикле
- `k`, `v` — в `.items()`
- `db` — сессия БД (устоявшееся)
- `redis` — клиент Redis

### Функции — глагол или глагол + существительное
```python
# ✅
def classify_message(text: str) -> list[str]: ...
async def find_interested_users(chat: str, segments: list[str]) -> list[dict]: ...
def build_message_hash(chat_username: str, message_id: int) -> str: ...

# ❌
def classification(text): ...
async def users(chat): ...
```

### Булевы переменные — `is_` / `has_` / `should_`
```python
is_urgent: bool
has_subscription: bool
should_retry: bool
```

---

## 3. Комментарии

### Правило: ПОЧЕМУ, а не ЧТО
Код говорит ЧТО. Комментарий объясняет ПОЧЕМУ сделано так, а не иначе.

```python
# ❌ Плохо: повторяет код
# умножаем на 100
total = price * 100

# ✅ Хорошо: объясняет неочевидное
# Telegram Stars API ожидает цену в минимальных единицах (копейки)
total = price * 100
```

### Без TODO в коде
Никаких `# TODO: потом доделать`. Если не сделано сейчас — создай задачу в todo-списке Claude Code или запиши в раздел предложений CLAUDE.md.

### Без закомментированного кода
Код в репозитории — только рабочий. Старые версии живут в git history. Закомментированный код удаляй.

---

## 4. Типизация

### Все публичные функции — с аннотациями
```python
# ✅
async def get_user(telegram_id: int) -> User | None: ...

# ❌
async def get_user(telegram_id): ...
```

### Современный синтаксис (Python 3.11+)
```python
# ✅
def process(items: list[str]) -> dict[str, int]: ...
def get_user(uid: int) -> User | None: ...

# ❌
from typing import List, Dict, Optional
def process(items: List[str]) -> Dict[str, int]: ...
def get_user(uid: int) -> Optional[User]: ...
```

### Protocol вместо ABC для интерфейсов
```python
from typing import Protocol

class PaymentProvider(Protocol):
    async def create_invoice(self, amount: float, user_id: int) -> str: ...
    async def check_payment(self, invoice_id: str) -> bool: ...
```

### Без `Any`
```python
# ❌
def parse(data: Any) -> Any: ...

# ✅
def parse(data: dict[str, object]) -> ParsedResult: ...
# или
def parse(data: object) -> ParsedResult: ...
```

---

## 5. Обработка ошибок

### Конкретные исключения, не `except Exception`
```python
# ✅
try:
    await client.connect()
except FloodWaitError as e:
    await asyncio.sleep(e.seconds)
except ConnectionError:
    logger.error("Cannot connect to Telegram")

# ❌
try:
    await client.connect()
except Exception:
    pass
```

### Обработка на границе, не в глубине
Внутренние функции (classifier, redis-кэш, crud) пробрасывают исключения наверх. Хендлеры и воркеры ловят и обрабатывают.

```python
# ✅ classifier.py — не ловит
def classify_message(text: str) -> list[str]:
    # чистая функция, исключения не ожидаются
    ...

# ✅ listener.py — ловит на границе
async def on_new_message(event: NewMessage.Event) -> None:
    try:
        await handle_message(event)
    except Exception:
        logger.exception("Failed to handle message")
```

---

## 6. Константы и конфигурация

### В config.py, не в коде
```python
# ❌
MAX_SEGMENTS = 3  # где-то в handlers/catalog_nav.py

# ✅ config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    max_segments_free: int = 1
    max_segments_pro: int = 3
    max_channels_pro: int = 15
    max_keywords_pro: int = 50
    notifications_per_day_free: int = 50
    notifications_per_day_pro: int = 150
    trial_days: int = 5
    referral_trial_bonus: int = 3
    referral_bonus_days: int = 7
    heartbeat_interval_minutes: int = 15
    sender_throttle_per_second: int = 25
    sender_retry_count: int = 3
    daily_report_hour: int = 19
```

### Без магических чисел
```python
# ❌
await asyncio.sleep(1 / 25)

# ✅
await asyncio.sleep(1 / settings.sender_throttle_per_second)
```

---

## 7. Импорты

### Порядок: стандартная библиотека → внешние → внутренние
```python
# Стандартная библиотека
import asyncio
import hashlib
from datetime import datetime, timezone

# Внешние зависимости
from aiogram import Router, F
from sqlalchemy import select

# Внутренние
from app.config import settings
from app.db.models import User
from app.userbot.classifier import classify_message
```

### Без `from module import *`
Всегда явные импорты.

### Без циклических импортов
Если два модуля ссылаются друг на друга — вынести общую часть в третий модуль или использовать late import внутри функции.

---

## 8. Структура модулей

### Хендлеры aiogram
```python
# app/bot/handlers/catalog_nav.py
router = Router()

@router.callback_query(F.data == "catalog_subscribe")
async def on_subscribe(callback: CallbackQuery, state: FSMContext) -> None:
    """Начало FSM-воронки: выбор направления."""
    ...
```

### Модели SQLAlchemy
```python
# app/db/models.py
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(20), default="free")
    ...
```

### CRUD
```python
# app/db/crud.py
async def get_user(db: AsyncSession, telegram_id: int) -> User | None:
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()
```

---

## 9. Redis

### Ключи — с префиксом и разделителем `:`
```python
CACHE_CHAT_KEY = "sub:by_chat:{chat_username}"
CACHE_CLASS_KEY = "class:cache:{message_hash}"
QUEUE_NOTIFICATIONS = "queue:notifications"
QUEUE_DEAD_LETTER = "dlq:notifications"
STATS_DAILY = "stats:daily:{user_id}:{date}"
HEARTBEAT_KEY = "heartbeat:userbot:{account_id}"
```

---

## 10. Логирование

### Структурное, с уровнем
```python
import logging

logger = logging.getLogger(__name__)

# INFO: нормальный поток
logger.info("User %d subscribed to segment %s", user_id, segment_slug)

# WARNING: потенциальная проблема
logger.warning("Userbot heartbeat missed for account %d", account_id)

# ERROR: ошибка, требующая внимания
logger.exception("Failed to send notification to user %d", user_id)
```

### Без print()
Только `logger`. Sentry ловит ERROR и выше автоматически.

---

## 11. Асинхронность

### `await` а не `.result()`
```python
# ✅
user = await get_user(telegram_id)

# ❌
user = asyncio.run(get_user(telegram_id))  # никогда внутри async-функции
```

### `asyncio.gather` для параллельных запросов
```python
# параллельные запросы к БД
users, segments, channels = await asyncio.gather(
    get_users(ids),
    get_segments(),
    get_channels()
)
```

### Таймауты на внешние запросы
```python
async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
    ...
```

---

## 12. Тесты

### Именование: `test_<что тестируем>_<сценарий>`
```python
def test_keyword_matches_exact_word():
    assert keyword_matches("ищу повара", "повар") is False  # граница слова!

def test_keyword_matches_unicode():
    assert keyword_matches("cần thợ nấu", "thợ nấu") is True

def test_find_users_no_segments_returns_empty():
    ...
```

### AAA: Arrange → Act → Assert
```python
def test_build_message_hash():
    # Arrange
    chat = "danang_chat"
    msg_id = 12345

    # Act
    result = build_message_hash(chat, msg_id)

    # Assert
    assert len(result) == 64
    assert result == build_message_hash(chat, msg_id)  # детерминированный
```

---

## 13. Безопасность

- Секреты ТОЛЬКО в `.env`, никогда в коде
- `.env` — в `.gitignore`
- `secrets.compare_digest()` для сравнения токенов
- SQL: только параметризованные запросы (SQLAlchemy делает это автоматически)
- HTML-экранирование для пользовательского ввода (aiogram экранирует по умолчанию)
