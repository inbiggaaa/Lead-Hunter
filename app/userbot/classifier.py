"""Three-pass classifier: classifies Telegram messages into matched segments.

Pass 1 — demand: word-boundary match against segment keywords (demand type).
Pass 2 — stop: candidate checked against stop-phrases.
Pass 3 — structural signals: demand markers vs offer markers.

Lemmatization: input text and keywords are lemmatized via pymorphy3 before
comparison, so grammatical forms (рублей/рубли, нужен/нужна) match automatically.
Does NOT handle lexical synonyms (поменять/обменять) — those must be in the seed.
"""

import re
from typing import NamedTuple

try:
    import pymorphy3
    _morph = pymorphy3.MorphAnalyzer()
except Exception:
    _morph = None


class ClassificationResult(NamedTuple):
    matched_segments: list[str]  # list of segment slugs
    is_urgent: bool


# ── Lemmatization ──

def _lemmatize_word(word: str) -> str:
    """Lemmatize a single word. Falls back to original if parsing fails."""
    if _morph is None:
        return word
    try:
        parsed = _morph.parse(word)
        if parsed:
            return parsed[0].normal_form
    except Exception:
        pass
    return word


def _lemmatize_text(text: str) -> str:
    """Lemmatize all Russian words in text, preserving non-Russian tokens."""
    if _morph is None:
        return text
    words = text.split()
    lemmas = [_lemmatize_word(w) for w in words]
    return " ".join(lemmas)


# ── Universal stop-phrases ──
# Moved to DB (segment_keywords with segment_id=NULL, keyword_type='stop').
# Loaded at startup via poller._load_keywords() and passed as universal_stops parameter.

# ── Demand signals (from segment_seed.md §2) ──

DEMAND_SIGNAL_PATTERNS = [
    # Strong demand verbs at start of message
    r"^(ищу|нужен|нужна|нужны|сниму|возьму|хочу|ищем)\b",
    r"^(посоветуйте|подскажите|кто знает|помогите)\b",
    r"^(looking for|need a?|want to|iso|wtb|searching for|looking to)\b",
    # Location/question demand at start: "Где арендовать...?", "Как найти...?"
    r"^(где|куда|откуда|как|кто)\b.*\?",
    # Strong demand anywhere in the message (no ^ anchor)
    r"\b(требуется|требуются)\b",
    r"\b(кто может|кто сможет|кто умеет|кто занимается)\b",
    r"\b(подберите|порекомендуйте|посоветуйте)\b",
    r"\b(есть у кого|у кого есть|у кого нибудь есть)\b",
]

# ── Offer signals ──
# Patterns that indicate the message is an ad/offer, not a client request.
# Used in Pass 3 to suppress matches when offer signals dominate.

OFFER_SIGNAL_PATTERNS = [
    # Price mentions: "Цена от 50к", "цена: 50000", "price $100", "стоимость 1000"
    r"(цена|прайс|стоимость|price|стоит)\b.*?\d+",
    # Phone/contact without @username: "WhatsApp +84...", "тел. 8900...", "звони 123"
    r"(тел|phone|whatsapp|wa|tg|звони|пиши|\+\d)[\s.:\-]*[\d\s\-+()]{7,}",
    # @username with long number (legacy)
    r"@\w+.*\d{7,}",
    # 3+ hashtags (promotional/marketing)
    r"(#[a-zA-Zа-яА-ЯёЁ0-9_]+[\s\n]*){3,}",
    # Commercial language: company introductions, self-promotion, service descriptions.
    # These NEVER appear in genuine client demand — purely offer/ads.
    r"\b(добро пожаловать|welcome to)\b",
    r"\b(ваш|твой) (надёжный )?(партнёр|партнер|помощник|финансовый партнёр)\b",
    r"\bработаем с \d{4}\b",
    r"\b(что мы делаем|как мы работаем|наши услуги|наши контакты|наши преимущества)\b",
    r"\b(по выгодному курсу|по лучшему курсу)\b",
]

# ── Noise words for fuzzy matching (excluded from word count) ──

FUZZY_NOISE = {
    # Prepositions / conjunctions / particles
    'на', 'в', 'по', 'для', 'с', 'не', 'к', 'за', 'от', 'до', 'из',
    'без', 'о', 'об', 'у', 'под', 'а', 'и', 'но', 'или', 'то', 'же',
    'бы', 'ли', 'со', 'ко', 'во', 'над', 'при', 'про', 'ради', 'через',
    'как', 'что', 'где', 'когда', 'кто', 'кому', 'кого', 'чем', 'чём',
    'это', 'там', 'тут', 'туда', 'сюда', 'здесь', 'так', 'тоже',
    'ещё', 'уже', 'пока', 'потом', 'сейчас', 'сегодня',
}

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
    """Check if keyword matches text with word boundary, case-insensitive, Unicode.

    Multi-word keywords match if ALL individual words appear in text (not
    necessarily adjacent — real messages rarely have words exactly side by side).
    """
    words = keyword.split()
    if len(words) == 1:
        pattern = _build_word_pattern(keyword)
        return bool(re.search(pattern, text, re.UNICODE | re.IGNORECASE))
    # Multi-word: all words must be present as word-boundary matches
    return all(
        bool(re.search(_build_word_pattern(w), text, re.UNICODE | re.IGNORECASE))
        for w in words
    )


def _is_urgent(text: str) -> bool:
    """Check for urgency markers."""
    text_lower = text.lower()
    return any(word in text_lower for word in URGENCY_WORDS)


def classify_message(
    text: str,
    segment_keywords: dict[str, dict[str, list[str]]],
    universal_stops: list[str] | None = None,
) -> ClassificationResult:
    """
    Classify a text message against segment keywords.

    Args:
        text: The message text to classify.
        segment_keywords: Dict of {segment_slug: {"demand": [...], "stop": [...], "synonym": [...]}}
        universal_stops: Global stop-phrases applied to all segments (from DB, segment_id=NULL).

    Returns:
        ClassificationResult with matched segment slugs and urgency flag.
    """
    if not text or not segment_keywords:
        return ClassificationResult(matched_segments=[], is_urgent=False)

    text_lower = text.lower()
    text_lemma = _lemmatize_text(text_lower)  # Grammatical form normalization
    has_demand_context = _has_demand_signal(text)
    has_offer_context = _has_offer_signal(text)
    is_urgent = _is_urgent(text)

    def _match_kw(kw: str) -> bool:
        """Match keyword against original text and lemmatized forms.

        Multi-word keywords (3+ words) use fuzzy matching as fallback:
        if ≥70% of individual words appear in text, it's a match.
        """
        # Exact match first
        if _match_keyword(kw, text_lower):
            return True
        if text_lemma != text_lower and _match_keyword(kw, text_lemma):
            return True
        kw_lemma = _lemmatize_text(kw)
        if kw_lemma != kw and _match_keyword(kw_lemma, text_lemma):
            return True

        # Fuzzy fallback for multi-word keywords (4+ words)
        #   4 words → ≥3/4 (75%), 5 words → ≥4/5 (80%), 6+ → miss ≤2
        #   Noise words (prepositions, particles) are excluded from counting
        words = kw.split()
        if len(words) >= 4:
            required = len(words) - 1 if len(words) <= 5 else max(len(words) - 2, 4)
            matched = 0
            total_significant = 0
            for w in words:
                if len(w) <= 2 or w.lower() in FUZZY_NOISE:
                    continue
                total_significant += 1
                w_lemma = _lemmatize_text(w)
                if (_match_keyword(w, text_lower)
                        or _match_keyword(w, text_lemma)
                        or _match_keyword(w_lemma, text_lemma)):
                    matched += 1
            if total_significant >= 2 and matched / max(total_significant, 1) >= 0.7:
                return True

        return False

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
            if _match_kw(kw):
                demand_matched = True
                break

        if not demand_matched:
            continue

        # Pass 2: stop phrases (universal + segment-specific)
        # Stop words match against original text only — lemmatization would
        # cause false positives (e.g. "сделано" → "сделать" blocks "сделать сайт")
        blocked = False
        all_stops = (universal_stops or []) + stop_kws
        for stop_kw in all_stops:
            if _match_keyword(stop_kw, text_lower):
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

        # Strong offer (price+contact) even with demand → suppress
        # unless demand is a strong verb at the START of the message.
        # A "?" alone is NOT enough — rhetorical ad questions ("Ищешь байк?") are offers.
        if has_offer_context and has_demand_context:
            strong_demand = bool(re.search(
                r"^(ищу|нужен|нужна|нужны|сниму|возьму|ищем|посоветуйте|подскажите|кто знает|помогите|требуется|требуются)\b",
                text_lower,
                re.UNICODE,
            ))
            if not strong_demand:
                continue

        matched.append(segment_slug)

    return ClassificationResult(matched_segments=matched, is_urgent=is_urgent)
