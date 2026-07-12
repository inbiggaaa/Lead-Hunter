"""A1 (fable_core_plan): гейт одиночных слов для buy/supply-сегментов.

В сегменте с lead_direction buy/supply одиночные keyword'ы гейтируются:
- одиночный ГЛАГОЛ («продам», «куплю») засчитывается только при domain-слове
  сегмента (synonym-словарь) в окне keyword_match_window токенов;
- одиночное НЕ-глагольное слово («байк», «хонда» — синонимы, слитые в demand
  при компиляции) само по себе Pass 1 не триггерит: словарь — не спрос.
Причина: голый глагол матчил «Кто продает двушку?» в moto/car-purchase,
а любое упоминание «Honda» матчило moto-purchase — вместе ~60% Pass1-объёма
с precision ~0% (данные 12.07: 30 синонимов-одиночек только у moto-purchase).

Не гейтится: multi-word фразы («куплю байк»), сегменты вне buy/supply,
buy/supply-сегменты без synonym-словаря (pass-through — как reality-фильтр C3).
"""

from app.userbot.classifier import classify_message

MOTO_BUY = {
    "moto-purchase": {
        "demand": ["продам", "продаю", "куплю", "куплю байк"],
        "stop": [],
        "synonym": ["байк", "мотоцикл", "скутер"],
    },
}
GATED = {"moto-purchase"}

FILLER_25 = " ".join(f"слово{i}" for i in range(25))


def _matched(text: str, kw_map: dict, gated: set[str]) -> list[str]:
    return classify_message(text, kw_map, purchase_segments=gated).matched_segments


# ── Ядро A1: голый глагол без domain-слова не матчит ──

def test_bare_trade_verb_without_domain_word_no_match():
    # Главный кейс из eval-корпуса: недвижимость, не мото
    assert _matched("Кто продает двушку?", MOTO_BUY, GATED) == []


def test_bare_verb_unrelated_context_no_match():
    assert _matched("продам холодильник и стиралку", MOTO_BUY, GATED) == []


# ── Глагол + domain-слово в окне — матчит ──

def test_verb_with_domain_word_nearby_matches():
    assert _matched("Продам байк Honda, торг уместен", MOTO_BUY, GATED) == ["moto-purchase"]


def test_verb_with_domain_word_lemma_form_matches():
    # «мотоциклы» → лемма «мотоцикл»; «продаете» → форма «продавать»
    assert _matched("кто продаёт мотоциклы в дананге", MOTO_BUY, GATED) == ["moto-purchase"]


def test_verb_and_domain_word_outside_window_no_match():
    text = f"куплю срочно {FILLER_25} байк"
    assert _matched(text, MOTO_BUY, GATED) == []


# ── Не гейтится ──

def test_multiword_phrase_not_gated():
    # «куплю байк» — multi-word фраза, работает как раньше (окно C2)
    assert _matched("куплю байк недорого", MOTO_BUY, GATED) == ["moto-purchase"]


def test_non_purchase_segment_verb_not_gated():
    # Тот же словарь, но сегмент НЕ в buy/supply → гейт не применяется
    assert _matched("продам холодильник", MOTO_BUY, set()) == ["moto-purchase"]


def test_gated_segment_without_synonyms_passthrough():
    # Нет synonym-словаря → гейт отключён (pass-through, как reality-фильтр C3)
    no_syn = {"moto-purchase": {"demand": ["продам"], "stop": [], "synonym": []}}
    assert _matched("продам холодильник", no_syn, GATED) == ["moto-purchase"]


def test_bare_domain_noun_alone_no_match_in_gated():
    # Упоминание домена без спроса: до A1 «байк» (synonym→demand) матчил сам
    assert _matched("классный байк у соседа, завидую", MOTO_BUY, GATED) == []


def test_brand_mention_alone_no_match_in_gated():
    syn_map = {
        "moto-purchase": {
            "demand": ["продам"], "stop": [], "synonym": ["хонда", "байк"],
        },
    }
    assert _matched("вчера видел хонду на парковке", syn_map, {"moto-purchase"}) == []


def test_single_noun_not_gated_outside_buy_supply():
    # Вне buy/supply одиночные слова работают как раньше
    noun = {
        "car-rental": {
            "demand": ["аренда"], "stop": [], "synonym": ["машина"],
        },
    }
    assert _matched("аренда до конца месяца", noun, set()) == ["car-rental"]
