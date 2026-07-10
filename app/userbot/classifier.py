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
    # Vietnamese currency prices: "9,7 VND", "10tr", "15 triệu", "20к донгов"
    r"\d+[\d,.]*\s*(vnd|донг|dong|₫|tr|triệu|🍋|к донгов)\b",
    # Phone/contact without @username: "WhatsApp +84...", "тел. 8900...", "звони 123"
    r"(тел|phone|whatsapp|wa|tg|звони|пиши|\+\d)[\s.:\-]*[\d\s\-+()]{7,}",
    # @username with long number (legacy)
    r"@\w+.*\d{7,}",
    # 3+ hashtags (promotional/marketing)
    r"(#[a-zA-Zа-яА-ЯёЁ0-9_]+[\s\n]*){3,}",
    # Vehicle documents: strongly indicates a sale/purchase listing (not service query)
    r"\b(blue card|green card|розовая карта|документы|документ|registration)\b",
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

# ── Purchase/rental segments (user is seller/agent searching for buyers/renters) ──
# For these segments, competitors post sale/rental listings with price, phone, documents.
# These are blocked by stop-words in Pass 2 — but if a buyer's message contains similar
# signals (e.g. "сниму квартиру, бюджет 500$, звоните 8..."), Pass 3 would incorrectly
# suppress it. Skipping Pass 3 prevents false negatives on legitimate buyer/renter demand.
# Note: housing-buy/housing-rent have the same pattern — stop-words block landlord/seller
# ads, and buyer/renter messages may contain phone numbers or price mentions.

PURCHASE_SEGMENTS: set[str] = {'moto-purchase', 'car-purchase', 'housing-buy', 'housing-rent'}


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


# ── Precompiled matching engine (B2) ──
# The hot path used to rebuild + re-search regexes for every keyword on every
# message (1500+ keywords → re module's 512-pattern cache thrashed) and
# re-lemmatize every keyword per message. Everything derivable from a keyword
# alone is now computed once, at compile_keyword_map() time.

_WORD_FLAGS = re.UNICODE | re.IGNORECASE
_NEG_PREFIX = r"(?<![а-яёa-z0-9])(не|нет|без)\s+"


class _CompiledWord(NamedTuple):
    rx: re.Pattern       # word-boundary match
    neg_rx: re.Pattern   # same word preceded by не/нет/без → treated as absent


# Explicit cache (NOT the re module's LRU): bounded by keyword vocabulary.
_word_cache: dict[str, _CompiledWord] = {}


def _compile_word(word: str) -> _CompiledWord:
    cw = _word_cache.get(word)
    if cw is None:
        pattern = _build_word_pattern(word)
        cw = _CompiledWord(
            rx=re.compile(pattern, _WORD_FLAGS),
            neg_rx=re.compile(_NEG_PREFIX + pattern, _WORD_FLAGS),
        )
        _word_cache[word] = cw
    return cw


def _cw_hit(cw: _CompiledWord, text: str) -> bool:
    """Word present at a word boundary and not negated — mirrors _word_in_text."""
    if not cw.rx.search(text):
        return False
    return not cw.neg_rx.search(text)


def _cws_match(cws: list[_CompiledWord], text: str) -> bool:
    """All words present — mirrors _match_keyword semantics."""
    return all(_cw_hit(cw, text) for cw in cws)


# ── Proximity window (C2) ──
# A multi-word DEMAND phrase matches only when all its words fall inside a
# window of N tokens («нужен совет … [50 слов] … продам байк» must NOT match
# «нужен байк»). Stop-phrases and short anchors are NOT windowed: tightening
# a stop would let more spam through.

# 20, не 12: на прод-корпусе (c2_diff, 10.07.2026) окно 12 теряло два
# 👍-подтверждённых лида и живые заявки («кто сдает автомобиль в аренду?» с
# разлётом слов 15-17 токенов); окно 20 сохраняет их и по-прежнему режет
# 73% разлётных матчей, включая все длинные офферы (>300 симв. разлёт).
DEFAULT_MATCH_WINDOW = 20  # tokens; poller passes settings.keyword_match_window


def _token_starts(text: str) -> list[int]:
    """Char offsets where whitespace-separated tokens begin."""
    starts: list[int] = []
    in_token = False
    for i, ch in enumerate(text):
        if ch.isspace():
            in_token = False
        elif not in_token:
            starts.append(i)
            in_token = True
    return starts


def _cw_positions(cw: _CompiledWord, text: str, starts: list[int]) -> list[int]:
    """Token indices of every hit; [] when absent or negated (as _cw_hit)."""
    from bisect import bisect_right
    if cw.neg_rx.search(text):
        return []
    return [bisect_right(starts, m.start()) - 1 for m in cw.rx.finditer(text)]


def _window_covers(
    events: list[tuple[int, int]], num_words: int, required: int, window: int,
) -> bool:
    """True when ≥required distinct words occur within a span of <window tokens.

    events: sorted (token_pos, word_idx) occurrences; two-pointer sweep.
    """
    counts = [0] * num_words
    distinct = 0
    left = 0
    for pos, idx in events:
        counts[idx] += 1
        if counts[idx] == 1:
            distinct += 1
        while pos - events[left][0] >= window:
            lpos, lidx = events[left]
            counts[lidx] -= 1
            if counts[lidx] == 0:
                distinct -= 1
            left += 1
        if distinct >= required:
            return True
    return False


def _phrase_in_window(
    cws: list[_CompiledWord], text: str, starts: list[int], window: int,
) -> bool:
    """All phrase words present AND co-located within the window."""
    events: list[tuple[int, int]] = []
    for i, cw in enumerate(cws):
        positions = _cw_positions(cw, text, starts)
        if not positions:
            return False
        events.extend((p, i) for p in positions)
    if len(cws) == 1:
        return True
    events.sort()
    return _window_covers(events, len(cws), len(cws), window)


class _MatchCtx:
    """Per-message match context: window size + lazily-built token offsets.

    Token counts of text_lower and text_lemma are identical (_lemmatize_text
    splits/rejoins on whitespace), so token indices are comparable across forms.
    """

    __slots__ = ("window", "text_lower", "text_lemma", "_starts_lower", "_starts_lemma")

    def __init__(self, window: int, text_lower: str, text_lemma: str):
        self.window = window
        self.text_lower = text_lower
        self.text_lemma = text_lemma
        self._starts_lower: list[int] | None = None
        self._starts_lemma: list[int] | None = None

    def starts_lower(self) -> list[int]:
        if self._starts_lower is None:
            self._starts_lower = _token_starts(self.text_lower)
        return self._starts_lower

    def starts_lemma(self) -> list[int]:
        if self._starts_lemma is None:
            self._starts_lemma = _token_starts(self.text_lemma)
        return self._starts_lemma


class CompiledKeyword:
    """One demand/synonym keyword with every derivable artifact precomputed."""

    __slots__ = ("words", "lemma_words", "fuzzy")

    def __init__(self, kw: str):
        raw_words = kw.split()
        self.words = [_compile_word(w) for w in raw_words]

        # Lemma form of the whole keyword (was recomputed per message before)
        kw_lemma = _lemmatize_text(kw)
        self.lemma_words = (
            [_compile_word(w) for w in kw_lemma.split()]
            if kw_lemma != kw else None
        )

        # Fuzzy fallback for 4+ word phrases: required count from TOTAL words,
        # matching over significant (non-noise, len>2) words only.
        self.fuzzy: tuple[int, list[tuple[_CompiledWord, _CompiledWord]]] | None = None
        if len(raw_words) >= 4:
            if len(raw_words) == 4:
                required = 4                        # 4/4 — no fuzziness
            elif len(raw_words) == 5:
                required = 4                        # 4/5 = 80%
            else:
                required = max(len(raw_words) - 2, 5)  # 6+: miss ≤2, floor 5
            sig_pairs = [
                (_compile_word(w), _compile_word(_lemmatize_text(w)))
                for w in raw_words
                if len(w) > 2 and w.lower() not in FUZZY_NOISE
            ]
            if len(sig_pairs) >= 2:  # total_significant >= 2
                self.fuzzy = (required, sig_pairs)

    def match(self, ctx: "_MatchCtx", lemma_differs: bool) -> bool:
        """Old _match_kw semantics + proximity window for multi-word phrases (C2).

        Single-word keywords: window is trivially satisfied — boolean path.
        Multi-word: the three form-alternatives are kept separate (no
        mixed-form matching), each verified within ctx.window tokens.
        """
        text_lower, text_lemma = ctx.text_lower, ctx.text_lemma
        if len(self.words) == 1:
            if _cws_match(self.words, text_lower):
                return True
            if lemma_differs and _cws_match(self.words, text_lemma):
                return True
            if self.lemma_words is not None and _cws_match(self.lemma_words, text_lemma):
                return True
        else:
            if _phrase_in_window(self.words, text_lower, ctx.starts_lower(), ctx.window):
                return True
            if lemma_differs and _phrase_in_window(
                self.words, text_lemma, ctx.starts_lemma(), ctx.window,
            ):
                return True
            if self.lemma_words is not None and _phrase_in_window(
                self.lemma_words, text_lemma, ctx.starts_lemma(), ctx.window,
            ):
                return True
        if self.fuzzy is not None:
            required, sig_pairs = self.fuzzy
            # Occurrences of each significant word across all forms; token
            # indices are comparable between text_lower and text_lemma.
            events: list[tuple[int, int]] = []
            for i, (w_cw, wl_cw) in enumerate(sig_pairs):
                positions = _cw_positions(w_cw, text_lower, ctx.starts_lower())
                positions += _cw_positions(w_cw, text_lemma, ctx.starts_lemma())
                positions += _cw_positions(wl_cw, text_lemma, ctx.starts_lemma())
                events.extend((p, i) for p in positions)
            if events:
                events.sort()
                if _window_covers(events, len(sig_pairs), required, ctx.window):
                    return True
        return False


class CompiledKeywordMap:
    """Precompiled {slug: {demand/stop/synonym}} + universal stops.

    Built once per keyword reload (poller, every 5 min) instead of doing all
    regex/lemma work per message. Universal stops live here so the poller
    passes a single object to classify_message.
    """

    __slots__ = ("segments", "universal_stops", "window")

    def __init__(
        self,
        segment_keywords: dict[str, dict[str, list[str]]],
        universal_stops: list[str] | None = None,
        window: int = DEFAULT_MATCH_WINDOW,
    ):
        self.window = window
        # (slug, demand+synonym CompiledKeywords, stop word-lists)
        self.segments: list[tuple[str, list[CompiledKeyword], list[list[_CompiledWord]]]] = []
        for slug, by_type in segment_keywords.items():
            all_demand = by_type.get("demand", []) + by_type.get("synonym", [])
            demand = [CompiledKeyword(kw) for kw in all_demand]
            stops = [
                [_compile_word(w) for w in stop_kw.split()]
                for stop_kw in by_type.get("stop", [])
            ]
            self.segments.append((slug, demand, stops))

        self.universal_stops = [
            [_compile_word(w) for w in stop_kw.split()]
            for stop_kw in (universal_stops or [])
        ]

    def __bool__(self) -> bool:
        return bool(self.segments)


def compile_keyword_map(
    segment_keywords: dict[str, dict[str, list[str]]],
    universal_stops: list[str] | None = None,
    window: int = DEFAULT_MATCH_WINDOW,
) -> CompiledKeywordMap:
    """Precompile a raw keyword map for fast repeated classification.

    window: proximity window in tokens for multi-word phrases (C2);
    the poller passes settings.keyword_match_window.
    """
    return CompiledKeywordMap(segment_keywords, universal_stops, window)


# Module-level precompiled signal patterns (were re.search'd per call)
_DEMAND_SIGNAL_RX = [re.compile(p, re.UNICODE) for p in DEMAND_SIGNAL_PATTERNS]
_OFFER_SIGNAL_RX = [
    re.compile(p, re.UNICODE | re.IGNORECASE) for p in OFFER_SIGNAL_PATTERNS
]
_SHORT_ANCHOR_CWS = [[_compile_word(w) for w in a.split()] for a in SHORT_ANCHORS]
_PASS3_STRONG_DEMAND_RX = re.compile(
    r"^(ищу|нужен|нужна|нужны|сниму|возьму|ищем|посоветуйте|подскажите|кто знает|помогите|требуется|требуются|куплю|приобрету)\b",
    re.UNICODE,
)


def _has_strong_demand_signal(text: str) -> bool:
    """Strong demand: verb patterns, question-word starts, short anchors in context.

    A bare «?» is NOT a strong signal — ads routinely end with a rhetorical
    question («Ищешь квартиру? Пиши в ЛС»). Only strong demand may override
    stop-words (Pass 2) and trigger the channel pre-tag boost.
    """
    text_lower = text.lower().strip()
    for rx in _DEMAND_SIGNAL_RX:
        if rx.search(text_lower):
            return True
    # Check short anchors with context
    for anchor_cws in _SHORT_ANCHOR_CWS:
        if _cws_match(anchor_cws, text):
            # Need contextual demand signal
            if "подскажите" in text_lower or "посоветуйте" in text_lower or "?" in text:
                return True
    return False


def _has_demand_signal(text: str) -> bool:
    """Weak demand: any «?» or a strong signal. Used by Pass 3 only —
    there it is counter-balanced by offer signals (price/contact)."""
    if "?" in text:
        return True
    return _has_strong_demand_signal(text)


def _has_offer_signal(text: str) -> bool:
    """Check if text contains offer signals (price+contact, 3+ hashtags)."""
    text_lower = text.lower()
    for rx in _OFFER_SIGNAL_RX:
        if rx.search(text_lower):
            return True
    return False


def _word_in_text(word: str, text: str) -> bool:
    """Check if word appears in text with word boundary, accounting for negation.

    For multi-word keyword matching: a word preceded by 'не', 'нет', or 'без'
    (at word boundary) is NOT counted as a match.
    """
    pattern = _build_word_pattern(word)
    if not re.search(pattern, text, re.UNICODE | re.IGNORECASE):
        return False
    # Check for negation: "не нужны", "нет прав", "без прав"
    neg_pattern = r"(?<![а-яёa-z0-9])(не|нет|без)\s+" + _build_word_pattern(word)
    if re.search(neg_pattern, text, re.UNICODE | re.IGNORECASE):
        return False
    return True


def _match_keyword(keyword: str, text: str) -> bool:
    """Check if keyword matches text with word boundary, case-insensitive, Unicode.

    Multi-word keywords match if ALL individual words appear in text (not
    necessarily adjacent — real messages rarely have words exactly side by side).
    Negation-aware: words preceded by 'не', 'нет', 'без' are treated as absent.
    """
    words = keyword.split()
    if len(words) == 1:
        return _word_in_text(keyword, text)
    # Multi-word: all words must be present as word-boundary matches,
    # and none may be negated (preceded by 'не', 'нет', 'без').
    return all(
        _word_in_text(w, text)
        for w in words
    )


def _is_urgent(text: str) -> bool:
    """Check for urgency markers."""
    text_lower = text.lower()
    return any(word in text_lower for word in URGENCY_WORDS)


def classify_message(
    text: str,
    segment_keywords: "dict[str, dict[str, list[str]]] | CompiledKeywordMap",
    universal_stops: list[str] | None = None,
    purchase_segments: set[str] | None = None,
) -> ClassificationResult:
    """
    Classify a text message against segment keywords.

    Args:
        text: The message text to classify.
        segment_keywords: Either a raw dict {segment_slug: {"demand": [...],
            "stop": [...], "synonym": [...]}} (compiled on the fly — fine for
            tests, wasteful for the poller hot path) or a CompiledKeywordMap
            built once via compile_keyword_map().
        universal_stops: Global stop-phrases (ignored when a CompiledKeywordMap
            is passed — they are baked in at compile time).
        purchase_segments: Slugs whose leads legitimately write offer-shaped
            messages (price/phone/docs) — Pass 3 is skipped for them. None →
            module default PURCHASE_SEGMENTS; the poller passes the DB-driven
            set (segments.lead_direction in 'buy'/'supply', task B4).

    Returns:
        ClassificationResult with matched segment slugs and urgency flag.
    """
    if not text or not segment_keywords:
        return ClassificationResult(matched_segments=[], is_urgent=False)

    pass3_skip = PURCHASE_SEGMENTS if purchase_segments is None else purchase_segments

    if isinstance(segment_keywords, CompiledKeywordMap):
        compiled = segment_keywords
    else:
        compiled = compile_keyword_map(segment_keywords, universal_stops)

    text_lower = text.lower()
    text_lemma = _lemmatize_text(text_lower)  # Grammatical form normalization
    lemma_differs = text_lemma != text_lower
    match_ctx = _MatchCtx(compiled.window, text_lower, text_lemma)
    has_strong_demand = _has_strong_demand_signal(text)
    has_demand_context = has_strong_demand or ("?" in text)  # weak — Pass 3 only
    has_offer_context = _has_offer_signal(text)
    is_urgent = _is_urgent(text)

    # Universal stops are identical for every segment — evaluated at most once
    # per message (lazily: only if some segment passes Pass 1), not per segment.
    universal_hit: bool | None = None

    matched: list[str] = []

    for segment_slug, demand_kws, stop_cws in compiled.segments:
        # Pass 1: demand phrases (demand + synonym, first hit wins)
        if not demand_kws:
            continue
        if not any(ck.match(match_ctx, lemma_differs) for ck in demand_kws):
            continue

        # Pass 2: stop phrases (universal + segment-specific).
        # Stop words match against original text only — lemmatization would
        # cause false positives (e.g. "сделано" → "сделать" blocks "сделать сайт").
        # Only a STRONG demand signal overrides a stop-phrase; a bare «?»
        # does not (ads end with rhetorical questions).
        if not has_strong_demand:
            if universal_hit is None:
                universal_hit = any(
                    _cws_match(cws, text_lower) for cws in compiled.universal_stops
                )
            if universal_hit or any(_cws_match(cws, text_lower) for cws in stop_cws):
                continue

        # Pass 3: structural signals
        # For purchase segments, offer signals (price, phone, documents) are
        # EXPECTED in sale listings — skip Pass 3 entirely.
        if segment_slug not in pass3_skip:
            # Offer signal without demand signal → suppress
            if has_offer_context and not has_demand_context:
                continue

            # Strong offer (price+contact) even with demand → suppress
            # unless demand is a strong verb at the START of the message.
            # A "?" alone is NOT enough — rhetorical ad questions ("Ищешь байк?") are offers.
            if has_offer_context and has_demand_context:
                if not _PASS3_STRONG_DEMAND_RX.search(text_lower):
                    continue

        matched.append(segment_slug)

    return ClassificationResult(matched_segments=matched, is_urgent=is_urgent)
