"""Run the full LLM prompt against 40+ real messages from unmatched Redis log.

Usage:
    docker compose exec worker python tools/test_llm_prompt_batch.py

Prerequisites:
    DEEPSEEK_API_KEY=sk-... in .env
    LLM prompt is embedded inline (same as will be used in production).
"""

import asyncio
import json
import sys
import time

import aiohttp

# ═══════════════════════════════════════════════════════════════
# FULL SYSTEM PROMPT (verbatim — same as production llm_validator)
# ═══════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """You are a message classifier for LeadHunter, a lead generation service. Classify the message into exactly one of four categories:

DEMAND — Commercial demand. The author is LOOKING FOR a product/service/contractor/vendor that a business could provide. Markers: "ищу + service", "нужен + specialist", "кто делает + job", "посоветуйте + service", "где купить/заказать/сделать + product", "сколько стоит + service", "требуется + specialist". IMPORTANT: everyday social searches ("ищу попутчика", "ищу с кем поиграть", "ищу жену") are NOT demand, they are OTHER.

OFFER — The author is OFFERING a service/product, advertising themselves or someone else. Markers: "предлагаю", "продам/продаю/продаётся", "сдам/сдаю", price + product, "пишите в лс/личку", "звоните", phone numbers, price lists, apartment codes ("Код: ma-008"), "мы работаем", "накрутка", "записывайтесь" + service.

MIXED — Contains BOTH demand and offer ("куплю байк или обменяю на свой"). Treat as DEMAND — if there is a demand component, it is a potential lead.

OTHER — Everything else: everyday questions, news, discussions, travel companion search, game partner search, memes, weather/visa experience questions.

CRITICAL RULE — ASYMMETRIC BIAS:
If you are UNCERTAIN between DEMAND and OFFER — choose DEMAND.
It is better to let a questionable message through than to lose a real client request.
Only classify as OFFER when you are CONFIDENT the author is selling/advertising, not looking.
When in doubt, the benefit goes to DEMAND.

Respond with STRICT JSON only:
{"category": "DEMAND"|"OFFER"|"MIXED"|"OTHER", "relevant_segments": [...], "certainty": "high"|"medium"|"low", "reason": "..."}

RULES for relevant_segments:
- Only categories from candidate_segments that the message REALLY relates to
- DEMAND/MIXED: confirmed segments (may be subset of candidates)
- OFFER/OTHER: []

RULES for certainty:
- "high": absolutely confident (clear markers, unambiguous)
- "medium": reasonably confident, some markers present
- "low": uncertain, borderline case — treat as DEMAND (fail-open)

EXAMPLES:

[DEMAND — direct service search]
Message: "ищу повара для семьи в Нячанге, на постоянной основе"
Candidates: ["catering", "job-hiring"]
→ {"category": "DEMAND", "relevant_segments": ["catering", "job-hiring"], "certainty": "high", "reason": "Explicit search for a chef — commercial demand for a service and a job vacancy"}

[DEMAND — question without "ищу"]
Message: "кто знает хорошего стоматолога в Нячанге? желательно русскоговорящего"
Candidates: ["medical"]
→ {"category": "DEMAND", "relevant_segments": ["medical"], "certainty": "high", "reason": "Author is asking for a doctor recommendation — commercial demand, despite no explicit 'searching for'"}

[DEMAND — price inquiry]
Message: "подскажите сколько стоит завернуть чемодан пленкой в аэропорту Камрань?"
Candidates: ["tourism"]
→ {"category": "DEMAND", "relevant_segments": ["tourism"], "certainty": "high", "reason": "Price inquiry for an airport service — potential tourism services client"}

[DEMAND — relocation research]
Message: "хочу переехать с девушкой на Фукуок, реально ли жить на 1000$ в месяц с учётом жилья?"
Candidates: ["real-estate-rent", "real-estate-buy"]
→ {"category": "DEMAND", "relevant_segments": ["real-estate-rent"], "certainty": "high", "reason": "Author is researching rental costs for relocation — potential real estate client"}

[DEMAND — specialist needed]
Message: "нужна регулярная уборка квартиры, район европейский квартал, 2 комнаты"
Candidates: ["cleaning"]
→ {"category": "DEMAND", "relevant_segments": ["cleaning"], "certainty": "high", "reason": "Explicit cleaning service search with details — direct commercial demand"}

[OFFER — currency exchange]
Message: "наличный обмен USDT, лучший курс в городе, пишите в личку"
Candidates: ["crypto"]
→ {"category": "OFFER", "relevant_segments": [], "certainty": "high", "reason": "Currency exchange ad: author offers exchange, not looking for it. 'Best rate', 'DM me' — offer markers"}

[OFFER — vehicle sale]
Message: "Продам байк Sym Atilla 2019, документы в наличии, 3 млн, Нячанг"
Candidates: ["moto-purchase"]
→ {"category": "OFFER", "relevant_segments": [], "certainty": "high", "reason": "Author sells a motorbike — 'Продам', price, documents: explicit offer"}

[OFFER — real estate listing]
Message: "2-КОМНАТНАЯ КВАРТИРА В ЦЕНТРЕ НЯЧАНГ ЗА 13 МЛН. Код: ma-008. Бассейн, тренажёрка."
Candidates: ["real-estate-rent"]
→ {"category": "OFFER", "relevant_segments": [], "certainty": "high", "reason": "Rental listing with apartment code, price, amenities — real estate agent offer"}

[OFFER — price list]
Message: "💸 ПРАЙС НА НАКРУТКУ СОЦСЕТЕЙ. Instagram: подписчики 1,5₽/шт, лайки 0,1₽/шт"
Candidates: ["it-services"]
→ {"category": "OFFER", "relevant_segments": [], "certainty": "high", "reason": "Service ad with price list — offer, not a request for IT services"}

[OFFER — disguised as invitation]
Message: "есть места на йогу по утрам, записывайтесь, район центр"
Candidates: ["fitness"]
→ {"category": "OFFER", "relevant_segments": [], "certainty": "high", "reason": "Disguised offer: 'spots available' + 'sign up' — this is selling yoga classes, not looking for them"}

[OFFER — nanny services]
Message: "Здравствуйте, предлагаю услуги няни. Писать в личные сообщения."
Candidates: ["childcare", "job-seeking"]
→ {"category": "OFFER", "relevant_segments": [], "certainty": "high", "reason": "Author offers nanny services — this is an offer, not a search for childcare"}

[OFFER — helmet sale]
Message: "🌟Продается шлем L52 в отличном состоянии. Размер xxl. Цена 1,5 млн"
Candidates: ["moto-purchase"]
→ {"category": "OFFER", "relevant_segments": [], "certainty": "high", "reason": "Author sells a helmet — sale listing, not a purchase request"}

[MIXED — partner search + offer]
Message: "ищу партнёра в бизнес по аренде байков, предлагаю долю 30%, инвестирую"
Candidates: ["bike-rental"]
→ {"category": "MIXED", "relevant_segments": ["bike-rental"], "certainty": "medium", "reason": "Author seeks a partner (demand) AND offers a stake (offer). Demand component exists → MIXED → lead"}

[MIXED — buy or trade]
Message: "куплю Honda Air Blade или обменяю на свой Sym, с доплатой"
Candidates: ["moto-purchase"]
→ {"category": "MIXED", "relevant_segments": ["moto-purchase"], "certainty": "medium", "reason": "Author wants to buy (demand) AND sell/trade (offer). Demand component → MIXED → potential lead"}

[OTHER — social game partner search]
Message: "ищу с кем поиграть в теннис в Муйне, уровень средний"
Candidates: ["fitness"]
→ {"category": "OTHER", "relevant_segments": [], "certainty": "high", "reason": "Social search for a game partner — not commercial demand. A tennis club cannot 'sell' a playing partner"}

[OTHER — travel companion]
Message: "ищу попутчика на Фукуок 15 июля, скинемся на такси"
Candidates: ["tourism"]
→ {"category": "OTHER", "relevant_segments": [], "certainty": "high", "reason": "Travel companion search — social, not commercial. One cannot sell a 'being a travel companion' service"}

[OTHER — personal visa experience]
Message: "Вы прямым рейсом летели? Визу оформляли на 90 дней или на 45?"
Candidates: ["visa"]
→ {"category": "OTHER", "relevant_segments": [], "certainty": "high", "reason": "Author asks about PERSONAL flight/visa experience — not searching for a visa agent. No service demand markers"}

[OTHER — weather question]
Message: "Как погода на Фукоке в июле? Кто сейчас там, отзовитесь!"
Candidates: ["tourism"]
→ {"category": "OTHER", "relevant_segments": [], "certainty": "high", "reason": "General weather question — not a search for tourism services"}

[OTHER — news article]
Message: "🥭 Туристы из России приезжают в Cam Lâm собирать манго прямо с дерева"
Candidates: ["tourism"]
→ {"category": "OTHER", "relevant_segments": [], "certainty": "high", "reason": "News piece — neither demand nor offer, informational message"}

[VN — OFFER]
Message: "Cho thuê xe máy giá rẻ 100k/ngày, liên hệ 090xxxxx"
Candidates: ["bike-rental"]
→ {"category": "OFFER", "relevant_segments": [], "certainty": "high", "reason": "Cho thuê = for rent — rental offer, not a rental request"}

[VN — DEMAND]
Message: "Cần tìm thợ sửa ống nước gấp, khu vực Mỹ Khê, Đà Nẵng"
Candidates: ["repair"]
→ {"category": "DEMAND", "relevant_segments": ["repair"], "certainty": "high", "reason": "Cần tìm = looking for — author seeks a plumber, commercial demand"}

[TR — OFFER]
Message: "Antalya'da profesyonel masaj hizmeti, uygun fiyat, iletisim 05xx"
Candidates: ["massage"]
→ {"category": "OFFER", "relevant_segments": [], "certainty": "high", "reason": "Hizmeti = service — author offers massage, not looking for one"}

[TR — DEMAND]
Message: "Antalya'da temizlikçi arıyorum, haftada 2 gün, ev temizliği"
Candidates: ["cleaning"]
→ {"category": "DEMAND", "relevant_segments": ["cleaning"], "certainty": "high", "reason": "Arıyorum = I'm searching — author seeks a cleaner, commercial demand"}

Now classify this message:"""

# ═══════════════════════════════════════════════════════════════
# TEST DATA: 40 real messages from unmatched Redis + known examples
# Format: (text, expected_category, note)
# ═══════════════════════════════════════════════════════════════
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

    # ── BORDERLINE (tricky cases) ──
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


async def classify_one(session, api_key, model, text):
    """Send one message to DeepSeek, return parsed JSON."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.0,
        "max_tokens": 300,
    }

    async with session.post(
        "https://api.deepseek.com/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=aiohttp.ClientTimeout(total=15),
    ) as resp:
        if resp.status != 200:
            return {"error": f"HTTP {resp.status}", "raw": await resp.text()}
        data = await resp.json()
        content = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("total_tokens", 0)
        try:
            parsed = json.loads(content)
            parsed["_tokens"] = tokens
            return parsed
        except json.JSONDecodeError:
            return {"error": "JSON parse failed", "raw": content, "_tokens": tokens}


def verdict_correct(expected, actual_category):
    """Check if LLM verdict matches expected.

    MIXED counts as correct if LLM says DEMAND or MIXED (fail-open towards lead).
    """
    if expected == "MIXED":
        return actual_category in ("DEMAND", "MIXED")
    return actual_category == expected


async def main():
    from app.config import settings

    api_key = settings.deepseek_api_key
    model = settings.deepseek_model

    if not api_key or api_key.startswith("#"):
        print("❌ DEEPSEEK_API_KEY not set or is a comment placeholder.")
        sys.exit(1)

    print(f"🤖 Model: {model}")
    print(f"📊 Test cases: {len(TEST_CASES)}")
    print(f"{'='*70}")

    correct = 0
    type_a_errors = 0  # lost lead: DEMAND/MIXED classified as OFFER/OTHER
    type_b_errors = 0  # missed spam: OFFER/OTHER classified as DEMAND/MIXED
    total_tokens = 0
    total_time = 0.0

    async with aiohttp.ClientSession() as session:
        for i, (text, expected, note) in enumerate(TEST_CASES, 1):
            t0 = time.monotonic()
            result = await classify_one(session, api_key, model, text)
            elapsed = time.monotonic() - t0
            total_time += elapsed

            if "error" in result:
                print(f"\n❌ #{i} API ERROR: {result['error']}")
                print(f"   Text: {text[:100]}")
                continue

            actual = result.get("category", "?")
            certainty = result.get("certainty", "?")
            reason = result.get("reason", "")[:120]
            tokens = result.get("_tokens", 0)
            total_tokens += tokens

            is_correct = verdict_correct(expected, actual)

            if is_correct:
                correct += 1
                status = "✅"
            else:
                # Classify error type
                if expected in ("DEMAND", "MIXED") and actual in ("OFFER", "OTHER"):
                    type_a_errors += 1
                    status = "🔴 TYPE A (lost lead)"
                elif expected in ("OFFER", "OTHER") and actual in ("DEMAND", "MIXED"):
                    type_b_errors += 1
                    status = "🟡 TYPE B (spam through)"
                else:
                    status = "⚠️ OTHER"

            print(
                f"{status} #{i:02d} [{elapsed:.1f}s] exp={expected:<6} got={actual:<7} "
                f"cert={certainty:<6} | {note:<25} | {reason}"
            )

    # Summary
    n = len(TEST_CASES)
    print(f"\n{'='*70}")
    print(f"📊 RESULTS: {correct}/{n} correct ({100*correct/n:.0f}%)")
    print(f"🔴 Type A (lost leads):  {type_a_errors}/{n}")
    print(f"🟡 Type B (spam through): {type_b_errors}/{n}")
    print(f"💰 Tokens used: {total_tokens}")
    print(f"⏱️  Total time: {total_time:.1f}s, avg {total_time/n:.2f}s/call")
    print(f"💵 Est. cost: ${total_tokens * 0.14 / 1_000_000:.4f} (input) + "
          f"${total_tokens * 0.28 / 1_000_000:.4f} (output)")

    if type_a_errors == 0:
        print("\n🎉 ZERO lost leads — prompt is ready for production.")
    else:
        print(f"\n⚠️ {type_a_errors} lost leads — prompt needs fixing before production.")


if __name__ == "__main__":
    asyncio.run(main())
