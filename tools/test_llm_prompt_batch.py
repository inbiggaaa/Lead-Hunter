"""Run production LLMValidator against 40+ golden messages (B2 acceptance).

Usage:
    docker compose exec worker python tools/test_llm_prompt_batch.py

Prerequisites:
    DEEPSEEK_API_KEY=sk-... in .env
    Uses app.userbot.llm_validator.build_system_prompt (incl. B2 few-shot).
"""

from __future__ import annotations

import asyncio
import sys
import time

from app.userbot.llm_validator import LLMValidator, PendingMatch

# Format: (text, expected_category, note)
TEST_CASES = [
    # ── EXPECTED: DEMAND ──
    ("ищу повара для семьи в Нячанге, на постоянной основе", "DEMAND", "явный спрос"),
    ("кто знает хорошего стоматолога в Нячанге? желательно русскоговорящего", "DEMAND", "вопрос-спрос"),
    ("подскажите сколько стоит завернуть чемодан пленкой в аэропорту Камрань?", "DEMAND", "запрос цены"),
    ("хочу переехать с девушкой на Фукуок, реально ли жить на 1000$ с учётом жилья?", "DEMAND", "исследование переезда"),
    ("нужна регулярная уборка квартиры, район европейский квартал, 2 комнаты", "DEMAND", "явный спрос на уборку"),
    ("Всем привет. Может кто подскажет, где на острове можно купить свечи электронные на батарейках?", "DEMAND", "где купить"),
    ("Добрый день. Подскажите сколько стоит в аэропорту Камрань завернуть чемодан пленкой?", "DEMAND", "запрос цены услуги"),
    ("Нужна помощь с перевозкой вещей из Нячанга в Дананг. Кто может?", "DEMAND", "логистика"),
    ("ищу русскоговорящего риэлтора для аренды квартиры в Нячанге", "DEMAND", "риэлтор"),

    # ── EXPECTED: OFFER ──
    ("Продам. 3 млн. Sym Atilla Viktoria. Документы в наличии. Заводится, едет. Нячанг", "OFFER", "продажа байка"),
    ("Эндуро шлем ORZ-11. Использовался 0 раз. 750.000внд. Очки Scott-250.000vnd", "OFFER", "продажа с ценой"),
    ("наличный обмен USDT, лучший курс в городе, пишите в личку", "OFFER", "обменник"),
    ("Здравствуйте, предлагаю услуги няни. Писать в личные сообщения.", "OFFER", "предлагаю услуги"),
    ("есть места на йогу по утрам, записывайтесь, район центр", "OFFER", "замаскированный оффер"),
    ("🌟Продается шлем L52 в отличном состоянии. Размер xxl. Цена 1,5 млн", "OFFER", "продажа шлема"),
    ("2-КОМНАТНАЯ КВАРТИРА В ЦЕНТРЕ НЯЧАНГ ЗА 13 МЛН. Код: ma-008. Бассейн.", "OFFER", "квартира с кодом"),
    ("Сдаётся уютный, чистый 3х этажный дом после ремонта. Duong Bao, Sonasea Area.", "OFFER", "сдаётся дом"),
    ("💸 ПРАЙС НА НАКРУТКУ СОЦСЕТЕЙ. Instagram подписчики 1,5₽/шт, лайки 0,1₽/шт", "OFFER", "прайс-лист"),
    ("В  meyhomes есть свободные апартаменты, 8,5 месяц сутки 400", "OFFER", "есть свободные"),

    # ── EXPECTED: OTHER ──
    ("Вы прямым рейсом летели? Визу оформляли на 90 дней? Спасибо за ваше время", "OTHER", "визовый опыт"),
    ("Тунц тунц. Автор видео Bao Le", "OTHER", "мусор"),
    ("ищу с кем поиграть в теннис в Муйне, уровень средний", "OTHER", "бытовой поиск"),
    ("ищу попутчика на Фукуок 15 июля, скинемся на такси", "OTHER", "попутчик"),
    ("Как погода на Фукоке в июле? Кто сейчас там, отзовитесь!", "OTHER", "погода"),
    ("Привет, кто-то в курсе, тут есть клубы или кафе с приставкой игровой?", "OTHER", "социальный досуг"),
    ("Здравствуйте, есть ли на острове русскоговорящие христианские собрания?", "OTHER", "религиозный"),
    ("Ничего вообще не спрашивали. только паспорт взял", "OTHER", "обрывок разговора"),
    ("Кто знает ядовита, опасна? (про змею на пляже)", "OTHER", "бытовой вопрос"),
    ("Есть кто-то в Муйне кто хорошо играет в настольный теннис?", "OTHER", "бытовой поиск"),

    # ── EXPECTED: MIXED ──
    ("ищу партнёра в бизнес по аренде байков, предлагаю долю 30%, инвестирую", "MIXED", "спрос + оффер"),
    ("куплю Honda Air Blade или обменяю на свой Sym, с доплатой", "MIXED", "куплю или обменяю"),

    # ── BORDERLINE ──
    ("🔥SOUL HOSTORY + POIDEM POZHREM. Мы спросили гостей что нравится в ресторанах", "OFFER", "реклама ресторана"),
    ("ХВАТИТ БОЯТЬСЯ ПОЛИЦИИ НА ДОРОГАХ! Мы делаем правильные МВУ для твоих поездок.", "OFFER", "реклама МВУ"),
    ("🥭 Туристы из России приезжают в Cam Lâm собирать манго прямо с дерева", "OTHER", "новость"),
    ("Шляпа/Панама - 100к. Мяч волейбольный - 70к. Нячанг. Центр", "OFFER", "товары с ценой"),
    ("Всем доброго дня. В связи со срочным переездом пересдам очень уютные апартаменты", "OFFER", "пересдам"),
    ("ищу поставщика кофе в Нячанге", "DEMAND", "коммерческий поиск"),
    ("кто делает профессиональный маникюр на дому?", "DEMAND", "спрос на услугу"),
    ("Может кто подскажет хорошего мастера по ремонту кондиционеров?", "DEMAND", "спрос-вопрос"),
    ("Доброго дня! Откликнитесь, кто отдыхал в Matie Beach Hotel в Муйне", "OTHER", "опыт отеля"),
]


def verdict_correct(expected: str, actual: str) -> bool:
    if expected == "MIXED":
        return actual in ("DEMAND", "MIXED")
    return actual == expected


async def main() -> None:
    from app.config import settings

    if not settings.deepseek_api_key or settings.deepseek_api_key.startswith("#"):
        print("❌ DEEPSEEK_API_KEY not set or is a comment placeholder.")
        sys.exit(1)

    # Force enabled for this offline tool even if LLM_ENABLED=false in .env
    object.__setattr__(settings, "llm_enabled", True)

    # Golden suite must exercise the real LLM path (not high-confidence skip).
    import app.userbot.llm_validator as lv
    lv.is_high_confidence_demand = lambda _text: False  # type: ignore[assignment]

    validator = LLMValidator()
    print(f"🤖 Model: {settings.deepseek_model}")
    print(f"📊 Test cases: {len(TEST_CASES)}")
    print(f"📝 Prompt chars: {len(validator._system_prompt)}")
    print(f"{'=' * 70}")

    correct = 0
    type_a_errors = 0
    type_b_errors = 0
    total_tokens = 0
    total_time = 0.0
    scored = 0

    for i, (text, expected, note) in enumerate(TEST_CASES, 1):
        t0 = time.monotonic()
        result = await validator.validate(text, candidate_segments=["general"])
        elapsed = time.monotonic() - t0
        total_time += elapsed
        total_tokens += result.total_tokens

        if result.error:
            print(f"\n❌ #{i} API ERROR: {result.error}")
            print(f"   Text: {text[:100]}")
            continue

        actual = result.verdict
        scored += 1
        is_correct = verdict_correct(expected, actual)
        if is_correct:
            correct += 1
            status = "✅"
        elif expected in ("DEMAND", "MIXED") and actual in ("OFFER", "OTHER"):
            type_a_errors += 1
            status = "🔴 TYPE A (lost lead)"
        elif expected in ("OFFER", "OTHER") and actual in ("DEMAND", "MIXED"):
            type_b_errors += 1
            status = "🟡 TYPE B (spam through)"
        else:
            status = "❌"

        print(
            f"{status} #{i} expected={expected} got={actual} "
            f"cert={result.certainty} tokens={result.total_tokens} "
            f"({elapsed:.1f}s) — {note}"
        )
        if not is_correct:
            print(f"   text: {text[:120]}")
            print(f"   reason: {result.reason[:160]}")

    print(f"\n{'=' * 70}")
    print(f"Score: {correct}/{scored} ({(100 * correct / scored) if scored else 0:.0f}%)")
    print(f"Type A (lost lead): {type_a_errors}")
    print(f"Type B (spam through): {type_b_errors}")
    print(f"Tokens: {total_tokens} · time: {total_time:.1f}s")
    if scored and correct >= 37 and type_a_errors == 0:
        print("ACCEPT: ≥37/40 and 0 type-A errors")
        sys.exit(0)
    print("REJECT: need ≥37 correct and 0 type-A")
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
