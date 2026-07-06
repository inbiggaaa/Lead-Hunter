# Аудит двойной записи alembic_version — 2026-07-04

## 0. Git
```
ahead=1, behind=0 ✓
```

## 1. alembic heads / branches

```
alembic heads:    c2a1d3b4e5f6 (head)  — 1 голова
alembic branches: (no output)          — ветвлений НЕТ
```

## 2. alembic_version — дословно

```
 version_num
--------------
 4afd135dc3f1
 b11187f388a9
(2 rows)
```

## 3. Родство ревизий

| Ревизия | down_revision | Родитель? |
|---|---|---|
| 4afd135dc3f1 | da0a81014466 | da0a → 4afd |
| b11187f388a9 | **4afd135dc3f1** | **ДА** — 4afd родитель b111 |
| c2a1d3b4e5f6 | b11187f388a9 | b111 → c2a1 |

**4afd — родитель b111. Подтверждено.**

Наличие ОБЕИХ в alembic_version аномально. При линейной цепочке `upgrade head` заменяет предыдущую голову новой. Две строки означают, что b111 была применена без удаления 4afd — вероятно, через `docker compose run` (отдельный контейнер с отдельной сессией Alembic).

## 4. stamp c2a1 --sql — сухой прогон

```sql
BEGIN;

-- Alembic создаёт таблицу заново, если её нет (CREATE IF NOT EXISTS подразумевается)
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Основная операция: INSERT c2a1 (НЕ DELETE старых строк!)
INSERT INTO alembic_version (version_num)
VALUES ('c2a1d3b4e5f6')
RETURNING alembic_version.version_num;

COMMIT;
```

**Критично: stamp НЕ удаляет старые строки.** После stamp alembic_version будет иметь 3 строки: 4afd, b111, c2a1.

## 5. ВЫВОД

### Безопасен ли простой `alembic stamp c2a1`?
**ДА, но с остатком.** stamp INSERT'ит c2a1, не трогая 4afd и b111. Результат: 3 строки. Дальнейшая работа Alembic будет корректна (новая миграция от c2a1 создаст upgrade, который заменит c2a1 на новую голову). 4afd и b111 останутся в таблице навсегда — безвредно, но загрязняет учёт.

### Чистый вариант (рекомендуется)
Ручная очистка перед stamp:
```sql
-- В одном скрипте, до stamp:
DELETE FROM alembic_version;
-- Затем:
INSERT INTO alembic_version VALUES ('c2a1d3b4e5f6');
-- Или короче:
-- docker compose exec worker alembic stamp c2a1d3b4e5f6
-- затем:
-- docker compose exec db psql -U leadhunter -d leadhunter -c "DELETE FROM alembic_version WHERE version_num IN ('4afd135dc3f1','b11187f388a9');"
```

Но проще: сделать stamp, принять 3 строки, затем новая миграция is_ignored → upgrade → Alembic сам заменит c2a1 на новую голову. 4afd и b111 останутся артефактами. На работу не влияют.

### Рекомендация
1. `alembic stamp c2a1d3b4e5f6` — приведёт учёт в соответствие (3 строки)
2. Создать ревизию is_ignored (от c2a1)
3. `alembic upgrade head` — применит новую миграцию, заменит c2a1 на is_ignored-ревизию
4. При желании — удалить 4afd и b111 из alembic_version руками (необязательно)
