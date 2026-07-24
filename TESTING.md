# TESTING.md — Стратегия тестирования LeadHunter

Этот файл описывает как, когда и что тестировать. CLAUDE.md и CODING_STYLE.md ссылаются на него.

---

## 0. Пирамида тестов

```
         ┌─────────┐
         │  Smoke  │  ← ручной, перед деплоем
         │  1-2    │
        ┌┴─────────┴┐
        │ Integration│ ← pytest-asyncio + тестовая БД
        │   ~15-20   │
       ┌┴─────────────┴┐
       │     Unit       │ ← pytest, чистые функции
       │    ~50-80      │
       └────────────────┘
```

---

## 1. Unit-тесты (pytest)

### Что покрываем
- Чистые функции без внешних зависимостей
- Классификатор (`classifier.py`)
- Хеш-функции, парсинг, валидацию
- Retry-логику

### Правила
- **Каждая новая публичная функция → тест.** Без исключений с Фазы 2.
- Имя теста: `test_<функция>_<сценарий>`
- Использовать AAA (Arrange → Act → Assert)
- Один тест — один сценарий
- Фикстуры в `conftest.py`

### Пример
```python
# tests/test_keyword_matches.py

def test_exact_word_match():
    """Целое слово матчится."""
    assert keyword_matches("ищу повара на день", "повар") is False  # нет границы
    assert keyword_matches("ищу повара на день", "повара") is True   # граница слова

def test_substring_no_match():
    """Подстрока без границы слова НЕ матчится."""
    assert keyword_matches("работаю удалённо", "работа") is False

def test_unicode_boundary():
    """Unicode-границы: кириллица, вьетнамский."""
    assert keyword_matches("cần thợ nấu ăn", "thợ nấu") is True

def test_case_insensitive():
    """Регистр неважен."""
    assert keyword_matches("ИЩУ ПОВАРА", "ищу") is True
```

### Запуск
```bash
# Все unit-тесты
pytest tests/ -v -k "not integration and not smoke"

# Конкретный файл
pytest tests/test_classifier.py -v

# С coverage
pytest tests/ --cov=app --cov-report=term-missing
```

---

## 2. Integration-тесты (pytest-asyncio)

### Что покрываем
- CRUD операции через SQLAlchemy
- Redis-кэш (инвалидация, загрузка)
- FSM-цепочки
- Реферальную механику

### Тестовая БД
- Отдельная PostgreSQL база `leadhunter_test` (создаётся в `conftest.py`)
- Миграции применяются перед тестами: `alembic upgrade head`
- Данные очищаются после каждого теста (транзакция + rollback)

### Фикстуры (conftest.py)
```python
@pytest_asyncio.fixture
async def db_session():
    """Чистая сессия с rollback после теста."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as session:
        async with session.begin():
            yield session
            await session.rollback()

@pytest_asyncio.fixture
async def test_user(db_session):
    """Тестовый пользователь Free."""
    user = User(telegram_id=123456, plan="free", language="ru")
    db_session.add(user)
    await db_session.flush()
    return user
```

### Пример
```python
# tests/test_subscriptions.py

@pytest.mark.asyncio
async def test_subscribe_to_segment_all_cities(db_session, test_user):
    """Подписка на направление — все города."""
    sub = UserSubscription(
        user_id=test_user.id,
        segment_id=1,
        country_id=1,
        mode="all"
    )
    db_session.add(sub)
    await db_session.flush()

    assert sub.id is not None
    assert sub.mode == "all"

@pytest.mark.asyncio
async def test_subscribe_to_segment_specific_cities(db_session, test_user):
    """Подписка на направление — конкретные города."""
    sub = UserSubscription(
        user_id=test_user.id,
        segment_id=1,
        country_id=1,
        mode="cities"
    )
    db_session.add(sub)
    await db_session.flush()

    sc = SubscriptionCity(subscription_id=sub.id, city_id=1)
    db_session.add(sc)
    await db_session.flush()

    assert sc.subscription_id == sub.id
```

### Запуск
```bash
# Только integration
pytest tests/ -v -k "integration"

# Все тесты
pytest tests/ -v
```

---

## 3. Smoke-тесты

### Offline harness (CI / pre-commit)

```bash
pytest tests/test_smoke_harness.py tests/test_phase6_runtime_flows.py -q
```

- `tests/test_smoke_harness.py` — classify + FakeRedis claim/ack (без Telegram API).
- `tests/test_phase6_runtime_flows.py` — live Postgres+Redis: queue claim, digest reclaim,
  payment activate idempotency, immediate expiry → Free paywall (Bot API замокан).

### Live channel → inbox (ручной, owner gate)

Требует работающих bot/worker и тестовый канал. Не автоматизирован в CI
(anti-ban / Telethon). Чеклист: `docs/launch/` + ручная проверка после deploy.

### Когда запускать
- Offline harness — в каждом CI и перед merge
- Live smoke — перед публичным релизом / по решению владельца

---

## 4. Pre-commit checklist (QA)

Перед каждым `git commit`:

### Все фазы
- [ ] `pytest tests/ -v` — все тесты зелёные
- [ ] `docker compose up -d --build` — проект запускается без ошибок
- [ ] `docker compose logs --tail=20` — нет WARNING/ERROR в логах
- [ ] `.env` не в git (`git status` не показывает `.env`)

### Фазы 3+ (бизнес-логика)
- [ ] artifact-code-reviewer на диффе:
  > Проверь дифф на качество кода, соответствие CODING_STYLE.md
  > и потенциальные баги. Верни blocker/concern/suggestion.
- [ ] Исправлены все blocker'ы
- [ ] Новые публичные функции имеют тесты

### Фазы 5+ (рассыльщик)
- [ ] `pytest tests/test_smoke_harness.py tests/test_phase6_runtime_flows.py` — offline critical path

### Фазы 7+ (оплата)
- [ ] Тестовый платёж проходит (Stars test environment)
- [ ] План пользователя меняется после оплаты
- [ ] Лимиты расширяются соответственно тарифу

---

## 5. Регрессия: как не сломать работающее

### Правило: перед изменением существующей функции
1. Прочитать все тесты на эту функцию
2. Добавить тест на новый сценарий ДО изменения кода
3. Убедиться что старые тесты ломаются (если ожидаемо)
4. Изменить код
5. Все тесты зелёные → готово

### Git bisect
Если что-то сломалось и неясно когда:
```bash
git bisect start
git bisect bad HEAD
git bisect good phase-5-done  # последний стабильный тег
# ... тестируем каждый шаг ...
git bisect good  # или bad
# ... в конце:
git bisect reset
```

---

## 4а. Closed matching feedback

Focused suite (test DB on `127.0.0.1:55432`, Redis `56379`):

```bash
export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432
export POSTGRES_USER=lhtest POSTGRES_PASSWORD=lhtest POSTGRES_DB=lhtest
export REDIS_HOST=127.0.0.1 REDIS_PORT=56379
pytest -q tests/test_matching_feedback_*.py tests/test_eval_matching_feedback.py
```

Migration reversibility smoke: `tests/test_matching_feedback_migration.py`
Canonical analytics: `app.matching_feedback.analytics.aggregate_feedback`
Runbook: `docs/ops/closed_matching_feedback_ru.md`

---

## 6. Известные ограничения

- **Smoke-тест требует живого Telegram-соединения** — не в CI, только локально
- **Тестовая БД требует отдельной PostgreSQL** — создаётся в `docker-compose.override.yml` для тестов
- **Userbot-тесты требуют живого session-файла** — не автоматизированы в v1
- **Платёжные тесты требуют тестового окружения (Stars sandbox / CryptoBot testnet)** — см. Фазу 7


## Userbot Capacity Governor

Targeted suite (no live Telegram):

```bash
pytest tests/test_userbot_capacity.py tests/test_poll_schedule.py tests/test_rate_limiter.py \
  tests/test_pool.py tests/test_poller_fixes.py tests/test_tier_geo.py \
  tests/test_userbot_capacity_api.py tests/test_watchdog_integrity.py tests/test_cache_invalidation.py -q
```

Rollout runbook: `docs/ops/userbot_capacity_governor_ru.md`.
