"""C2: окно близости для multi-word keyword-матчинга.

Фраза матчится, только если ВСЕ её слова попадают в окно из N токенов
(config.keyword_match_window, дефолт 20 — выбран по прод-корпусу: окно 12
теряло 👍-подтверждённые лиды с разлётом слов 15-17 токенов, см.
docs/eval/c2_diff.md). Раньше слова могли быть где угодно в тексте —
«нужен совет … [50 слов] … продам байк» матчил «нужен байк».
Fuzzy-фолбэк (4+ слова) тоже считает совпадения только внутри окна.
Stop-фразы и короткие anchors окном НЕ ограничиваются (ужесточение стопов
пропускало бы больше спама).
"""

from app.userbot.classifier import classify_message, compile_keyword_map

MOTO = {
    "moto-rental": {
        "demand": ["нужен байк"],
        "stop": ["сдаю байк"],
    },
}

FILLER_50 = " ".join(f"слово{i}" for i in range(50))


def _matched(text: str, kw_map: dict, **kwargs) -> list[str]:
    return classify_message(text, kw_map, **kwargs).matched_segments


# ── Базовое окно ──

def test_adjacent_words_match():
    assert _matched("нужен байк на месяц", MOTO) == ["moto-rental"]


def test_words_within_window_match():
    # 5 токенов между словами — внутри окна
    assert _matched("нужен на пару недель нормальный не убитый байк", MOTO) == ["moto-rental"]


def test_real_lead_span_16_tokens_matches():
    # Кейс из прод-корпуса (👍-лид): разлёт слов ~16 токенов должен матчиться
    # при дефолтном окне 20 — на нём окно 12 теряло подтверждённый лид.
    kw = {"currency-exchange": {"demand": ["поменять деньги"], "stop": []}}
    text = ("скажите сколько брать денег чтобы все было на уровне экскурсии "
            "поездки еда и тд две недели хочу валюту поменять")
    assert _matched(text, kw) == ["currency-exchange"]


def test_words_beyond_window_no_match():
    # Ключевой кейс C2: слова фразы разнесены на 50 токенов → не матч
    text = f"нужен совет по визе {FILLER_50} кстати продам байк недорого"
    assert _matched(text, MOTO) == []


def test_single_word_keyword_unaffected():
    kw = {"visa": {"demand": ["виза"], "stop": []}}
    text = f"{FILLER_50} нужна виза"
    assert _matched(text, kw) == ["visa"]


def test_window_configurable():
    text = "нужен один два три четыре байк"  # разрыв 5 токенов
    tight = compile_keyword_map(MOTO, window=3)
    wide = compile_keyword_map(MOTO, window=12)
    assert classify_message(text, tight).matched_segments == []
    assert classify_message(text, wide).matched_segments == ["moto-rental"]


# ── Лемма-формы работают внутри окна ──

def test_lemma_forms_within_window():
    kw = {"cleaning": {"demand": ["нужна уборка"], "stop": []}}
    assert _matched("нужны уборки квартир срочно", kw) == ["cleaning"]


def test_lemma_forms_beyond_window_no_match():
    kw = {"cleaning": {"demand": ["нужна уборка"], "stop": []}}
    text = f"нужны советы {FILLER_50} после уборки урожая"
    assert _matched(text, kw) == []


# ── Fuzzy-фолбэк (4+ слова) — тоже в окне ──

FUZZY = {
    "transfer": {
        # 5 слов → required 4 значимых совпадения
        "demand": ["нужен трансфер из аэропорта в отель"],
        "stop": [],
    },
}


def test_fuzzy_within_window_matches():
    assert _matched(
        "нужен трансфер из аэропорта прямо в наш отель", FUZZY
    ) == ["transfer"]


def test_fuzzy_beyond_window_no_match():
    # Значимые слова присутствуют, но разнесены дальше окна
    text = f"нужен трансфер говорите {FILLER_50} аэропорта до отель далеко"
    assert _matched(text, FUZZY) == []


# ── Stop-фразы и негация не задеты окном ──

def test_stop_phrases_not_windowed():
    # Слова stop-фразы разнесены >12 токенов — стоп всё равно срабатывает
    text = f"байк свободен {FILLER_50} сдаю посуточно"
    assert _matched(text, MOTO) == []


def test_negation_still_respected():
    assert _matched("не нужен байк", MOTO) == []
