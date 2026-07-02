# Промпт для Claude Code — Задача 0.5

> Скопируй всё, что ниже разделителя, в новую сессию Claude Code, открытую в корне репозитория. Перед этим создай ветку: `git checkout -b fix/0.5-per-account-limiter`.

---

Прочитай перед началом, целиком:
- `CLAUDE.md` §0 (правила разработки) и §8 (session log — писать туда в конце)
- `OPERATIONS.md` §2 (Hard Rules) и §5 (чек-лист) — обязательно перед любой правкой поллера/лимитера
- `AGENT_WORKFLOW.md` §0 — расхождения аудита с реальным кодом
- `LEADHUNTER_FIX_PLAN.md` → Задача 0.5

Работаем ТОЛЬКО над **Задачей 0.5 — Пер-аккаунтный rate limiter + суточный бюджет запросов**. Это первая задача Фазы 0 и фундамент для всего остального поллинга. Не выходи за её рамки.

## Контекст проблемы (проверено по коду)

`app/userbot/rate_limiter.py` содержит `TelegramRateLimiter` — синглтон (`limiter = TelegramRateLimiter()`, строка ~175) с **одним общим** `self._last_call` (строка ~42) и одним `self._lock` (строка ~43). Метод `acquire()` (строки ~45-53) не принимает `account_id` и сериализует вызовы **всех** аккаунтов в одну очередь. При двух аккаунтах `DEFAULT_MIN_INTERVAL=0.3` ограничивает их суммарный темп, а не темп каждого. Это первопричина FloodWait-банов: anti-ban меры наслаивались на общий лимитер.

Вызовы `await limiter.acquire()` в `app/userbot/poller.py` на строках ~240 (в `_poll_channel`) и ~330 (в `_fetch_all_since`) — **без** `account_id`. В `_poll_channel` доступен объект `account` (параметр метода), в `_fetch_all_since` — тоже (параметр `account`). У него есть `account.account_id`.

Circuit breaker в этом же файле уже пер-аккаунтный (ключи `circuit:open:{account_id}`) — берём его как образец стиля ключей.

## ЭТАП 1 — анализ, БЕЗ правок кода

1. Открой и покажи мне:
   - `app/userbot/rate_limiter.py` целиком.
   - Все места вызова `limiter.acquire(` и `limiter.` в `app/userbot/` (grep).
   - Как `account_id` доступен в каждой точке вызова.
2. Подтверди, что уже пер-аккаунтное (circuit breaker) и что глобальное (`_last_call`, `_lock`, `acquire`).
3. Проверь, есть ли в `requirements.txt` `fakeredis` (для теста части B нужен Redis). Если нет — предложи добавить `fakeredis>=2.0` в блок Testing.
4. Предложи план изменений: список файлов, функций, сигнатур. Отдельно — какие тесты напишешь.

**СТОП. Жди моего подтверждения плана. Не переходи к ЭТАПу 2.**

## ЭТАП 2 — реализация (только после моего «ок»)

Порядок: сначала тесты, потом код (тесты сперва падают, потом зеленеют).

### Часть A — пер-аккаунтный лимитер
- Переделать `TelegramRateLimiter`: `_last_call` и `_lock` — на каждый `account_id` (например `dict[int, float]` и `dict[int, asyncio.Lock]`, лениво создаваемые).
- `acquire(account_id: int)` — обязательный параметр. Разные аккаунты не делят очередь; вызовы одного сериализуются его личным локом и интервалом.
- Обновить вызовы в `poller.py` (строки ~240 и ~330): передать `account.account_id`.
- `min_interval` вынести в конфиг: добавить в `app/config.py` поле `userbot_min_interval: float = 1.5` (0.3 слишком агрессивно — поднимаем; значение читается из `.env`). Использовать его в лимитере вместо константы `DEFAULT_MIN_INTERVAL`.

### Часть B — суточный бюджет
- Redis-ключ `budget:used:{account_id}:{date}` (INT), TTL до конца суток UTC.
- Инкремент внутри `acquire(account_id)` — так учёт покрывает все API-вызовы автоматически. Проверять лимит до инкремента; при исчерпании — не спать, а бросать специальное исключение `BudgetExceeded` (аккаунт останавливается на уровне вызывающего, до следующих суток).
- Конфиг `daily_request_budget: int = 10000` в `app/config.py`.
- Метод `budget_remaining(account_id) -> int`.
- Обработать `BudgetExceeded` в `poller.py`: аккаунт пропускает цикл до сброса суток (по аналогии с тем, как обрабатывается circuit breaker), лог + вызов `notify_admin` («аккаунт #N исчерпал суточный бюджет»).

### Ограничения (из CLAUDE.md §0)
- Функции ≤30 строк, ранний возврат, полная типизация.
- Точечно: не трогай `_distribute`, `handle_account_failure`, тиры — это другие задачи (0.1, 0.2).
- Параметры — в `config.py`/`.env`, не хардкод.
- **НЕ запускай worker против реальных аккаунтов.** Только `pytest` и, если сделаешь харнесс, dry-run с моками.
- Миграций БД тут нет (всё в Redis) — Alembic не трогать.

### Тесты (в `tests/`, стиль как в `test_classifier.py`)

Часть A — без Redis, с monkeypatch времени:
```python
# tests/test_rate_limiter.py
import asyncio, pytest
from app.userbot.rate_limiter import TelegramRateLimiter

async def test_accounts_do_not_share_interval(monkeypatch):
    """Два аккаунта не делят один интервал: acquire для acc2 не ждёт из-за acc1."""
    fake_now = {"t": 0.0}
    async def _now(): return fake_now["t"]
    lim = TelegramRateLimiter(min_interval=1.0)
    monkeypatch.setattr(lim, "_now", _now, raising=False)  # или подмени модульный _now
    # первый вызов каждого аккаунта проходит без ожидания
    await lim.acquire(account_id=1)
    # acc2 в тот же момент времени НЕ должен ждать интервал acc1
    # (проверяем, что его last_call независим)
    assert lim._account_last_call.get(1) is not None
    assert lim._account_last_call.get(2) is None
    await lim.acquire(account_id=2)
    assert lim._account_last_call.get(2) is not None
```
(Точную форму подгони под реализацию; идея — раздельные `_last_call` на аккаунт. Если модульный `_now()` мешает — сделай его подменяемым или инжектируй clock.)

Часть B — с fakeredis:
```python
async def test_budget_blocks_after_limit(monkeypatch):
    """При budget=100 101-й запрос аккаунта → BudgetExceeded; второй аккаунт не затронут."""
    # monkeypatch get_redis → fakeredis.aioredis.FakeRedis(decode_responses=True)
    # daily_request_budget=100
    # 100 acquire(1) проходят, 101-й бросает BudgetExceeded
    # acquire(2) в это же время проходит (свой счётчик)
    ...

async def test_budget_resets_next_day(monkeypatch):
    """Смена даты в ключе budget:used:{id}:{date} обнуляет счётчик."""
    ...
```

## Критерии приёмки (проверю сам)
- `pytest` зелёный, включая новые тесты.
- Два аккаунта в тесте не сериализуются в общий интервал.
- `daily_request_budget=100` → 101-й запрос аккаунта блокируется, второй аккаунт со своим бюджетом работает.
- Счётчик сбрасывается на смене суток.
- Все вызовы `limiter.acquire(` в репозитории передают `account_id` (grep не находит ни одного без него).
- `min_interval` и `daily_request_budget` читаются из конфига.

## После задачи
Допиши в `CLAUDE.md §8` session log в формате:
`**DD.MM.YYYY HH:MM — Задача 0.5: пер-аккаунтный лимитер + бюджет.** Что сделано. Уроки.`

Без этой записи задача не считается завершённой (правило §0).

Начинай с ЭТАПа 1.
