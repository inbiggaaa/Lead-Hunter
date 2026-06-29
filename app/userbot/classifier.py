"""Three-pass classifier: classifies Telegram messages into matched segments.

Pass 1 — demand: word-boundary match against segment keywords (demand type).
Pass 2 — stop: candidate checked against stop-phrases.
Pass 3 — structural signals: demand markers vs offer markers.
"""

import re
from typing import NamedTuple

from app.db.models import SegmentKeyword


class ClassificationResult(NamedTuple):
    matched_segments: list[str]  # list of segment slugs
    is_urgent: bool


# ── Universal stop-phrases (from segment_seed.md §1) ──

UNIVERSAL_STOP = [
    # Booking/scheduling (offer)
    "записывайтесь", "запись открыта", "открыта запись", "свободные окошки",
    "свободно окошко", "есть окошко", "бронируйте", "по записи",
    # Self-promotion
    "прайс", "прайс-лист", "портфолио", "мастер с опытом", "работаю на дому",
    "принимаю у себя", "наш салон", "наша студия", "приглашаем вас",
    "у нас работают", "мы принимаем", "мы работаем", "мы предлагаем",
    "предлагаем услуги", "наши услуги", "записывайтесь к нам", "ждём вас",
    "приходите к нам", "мы открылись", "открылись", "новое место",
    "мы работаем по адресу", "наш адрес", "скидка сегодня", "акция сегодня",
    "спецпредложение",
    # Contact bait
    "пишите нам", "звоните нам", "подписывайтесь", "подписывайтесь на нас",
    "link in bio", "see our profile", "follow us", "ссылка в шапке",
    "ссылка в профиле", "ссылка в описании",
    # Price-first (offer signal)
    "цена от", "стоимость от", "цена указана", "цены в профиле",
    "доступные цены", "лучшие цены",
    # Already resolved
    "уже нашла", "уже нашёл", "уже записался", "уже записалась",
    "нашла мастера", "нашёл мастера", "вопрос решён", "уже не актуально",
    "спасибо всем", "нашли", "решила сама", "решил сам",
    "вопрос закрыт", "сделано",
    # Recommendation (past tense)
    "советую", "рекомендую", "был у", "была у", "ходил к", "ходила к",
    "попробовала", "попробовал", "понравилось", "не понравилось",
    "отличный мастер", "довольна результатом",
    # Urgency bait (offer)
    "места ещё есть", "осталось мало мест", "только сегодня", "только сейчас",
    "последние места", "акция действует", "набор закрыт",
    # English
    "book now", "slots available", "price list", "taking clients",
    "open for booking", "dm for price", "promotion today", "special offer",
    "discount today", "check out our", "visit us", "contact us",
    "hurry up", "limited time",
]

# ── Demand signals (from segment_seed.md §2) ──

DEMAND_SIGNAL_PATTERNS = [
    # Strong demand verbs at start
    r"^(ищу|нужен|нужна|нужны|сниму|возьму|хочу|ищем)\b",
    r"^(посоветуйте|подскажите|кто знает|помогите)\b",
    r"^(looking for|need a?|want to|iso|wtb|searching for|looking to)\b",
]

# ── Offer signals ──

OFFER_SIGNAL_PATTERNS = [
    r"(цена|прайс|стоимость|price)\s*[:-]?\s*\d+",
    r"@\w+.*\d{7,}",  # @username + phone
    r"(#[a-zA-Zа-яА-ЯёЁ0-9_]+[\s\n]*){3,}",  # 3+ hashtags
]

# ── Urgency markers ──

URGENCY_WORDS = [
    "срочно", "сегодня", "на завтра", "asap", "urgent",
    "сейчас", "прямо сейчас", "сегодня же",
]

# ── Short anchors (match ONLY with contextual demand signal) ──

SHORT_ANCHORS = {
    "нужен байк", "нужен скутер", "нужен мотоцикл", "нужен мопед",
    "хочу байк", "хочу скутер", "хочу мотоцикл", "хочу мопед",
    "возьму байк", "возьму скутер", "возьму мотоцикл",
    "сниму байк", "сниму скутер", "ищу байк", "ищу скутер", "ищу мотоцикл",
    "rent a bike", "need a scooter", "bike rental", "need a motorbike",
    "хочу мото", "ищу мото", "б/у байк", "б/у скутер", "б/у мотоцикл",
    "подержанный байк", "подержанный скутер",
    "куплю байк", "куплю скутер", "куплю мотоцикл", "куплю мопед",
    "рассмотрю байк", "рассмотрю мотоцикл",
    "buy motorcycle", "buy scooter", "used bike",
}


def _build_word_pattern(word: str) -> str:
    """Build a word-boundary regex pattern for a keyword phrase."""
    escaped = re.escape(word)
    return r"(?<!\w)" + escaped + r"(?!\w)"


def _has_demand_signal(text: str) -> bool:
    """Check if text starts with a demand signal or contains ?."""
    if "?" in text:
        return True
    text_lower = text.lower().strip()
    for pattern in DEMAND_SIGNAL_PATTERNS:
        if re.search(pattern, text_lower, re.UNICODE):
            return True
    # Check short anchors with context
    for anchor in SHORT_ANCHORS:
        if _match_keyword(anchor, text):
            # Need contextual demand signal
            if "подскажите" in text_lower or "посоветуйте" in text_lower or "?" in text:
                return True
    return False


def _has_offer_signal(text: str) -> bool:
    """Check if text contains offer signals (price+contact, 3+ hashtags)."""
    text_lower = text.lower()
    for pattern in OFFER_SIGNAL_PATTERNS:
        if re.search(pattern, text_lower, re.UNICODE | re.IGNORECASE):
            return True
    return False


def _match_keyword(keyword: str, text: str) -> bool:
    """Check if keyword matches text with word boundary, case-insensitive, Unicode."""
    pattern = _build_word_pattern(keyword)
    return bool(re.search(pattern, text, re.UNICODE | re.IGNORECASE))


def _is_urgent(text: str) -> bool:
    """Check for urgency markers."""
    text_lower = text.lower()
    return any(word in text_lower for word in URGENCY_WORDS)


def classify_message(
    text: str,
    segment_keywords: dict[str, dict[str, list[str]]],
) -> ClassificationResult:
    """
    Classify a text message against segment keywords.

    Args:
        text: The message text to classify.
        segment_keywords: Dict of {segment_slug: {"demand": [...], "stop": [...], "synonym": [...]}}

    Returns:
        ClassificationResult with matched segment slugs and urgency flag.
    """
    if not text or not segment_keywords:
        return ClassificationResult(matched_segments=[], is_urgent=False)

    text_lower = text.lower()
    has_demand_context = _has_demand_signal(text)
    has_offer_context = _has_offer_signal(text)
    is_urgent = _is_urgent(text)

    matched: list[str] = []

    for segment_slug, keywords_by_type in segment_keywords.items():
        demand_kws = keywords_by_type.get("demand", [])
        stop_kws = keywords_by_type.get("stop", [])
        synonym_kws = keywords_by_type.get("synonym", [])

        # Pass 1: demand phrases
        all_demand = demand_kws + synonym_kws
        if not all_demand:
            continue

        demand_matched = False
        for kw in all_demand:
            if _match_keyword(kw, text):
                demand_matched = True
                break

        if not demand_matched:
            continue

        # Pass 2: stop phrases (universal + segment-specific)
        blocked = False
        all_stops = list(UNIVERSAL_STOP) + stop_kws
        for stop_kw in all_stops:
            if _match_keyword(stop_kw, text):
                # If there's a strong demand signal, stop-phrase might be overridden
                if not has_demand_context:
                    blocked = True
                    break

        if blocked:
            continue

        # Pass 3: structural signals
        # Offer signal without demand signal → suppress
        if has_offer_context and not has_demand_context:
            continue

        # Strong offer (price+contact) even with weak demand → suppress
        # unless strong demand signal at start
        if has_offer_context and has_demand_context:
            # Check if demand is strong enough to override offer
            strong_demand = bool(re.search(
                r"^(ищу|нужен|нужна|нужны|сниму|возьму|посоветуйте|подскажите)\b",
                text_lower,
                re.UNICODE,
            ))
            if not strong_demand and "?" not in text:
                continue

        matched.append(segment_slug)

    return ClassificationResult(matched_segments=matched, is_urgent=is_urgent)
