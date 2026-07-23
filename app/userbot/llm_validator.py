"""LLM validator — DeepSeek-powered precision filter for lead matching.

Shadow mode (default): validates every match, logs the verdict, never blocks.
Blocking mode: blocks OFFER/OTHER with high certainty, passes everything else.

Architecture:
- classify_message (rules, wide recall) → LLMValidator.validate (precision filter)
- Fail-open: LLM errors/timeouts → match passes through (never lose a lead)
- PII masking: phones/@usernames/links sanitized before sending to LLM
- Batch validation: matches collected across channels, sent in one API call
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from app.config import settings

from app.userbot.llm_prompt import (
    SYSTEM_PROMPT_VERSION as LLM_PROMPT_V2_VERSION,
    build_segment_aware_prompt,
    build_untrusted_batch_user_message,
)

logger = logging.getLogger(__name__)


def _llm_cache_key(text: str) -> str:
    """B5: ключ кэша вердиктов — sha256 нормализованного текста БЕЗ чата.

    Нормализация как в compute_content_hash (lower, схлоп пробелов, 500 симв.),
    но без chat_username: репост одного объявления в N чатов должен попадать
    в один ключ. Классификация детерминирована по тексту → одинаковый текст
    даёт одинаковые rule_segments, кэшировать вердикт безопасно.
    """
    import hashlib

    normalized = " ".join((text or "")[:500].lower().split())
    return f"llm:verdict:{hashlib.sha256(normalized.encode()).hexdigest()}"


_CACHE_TTL = 86400  # 24ч — как окно контентного дедупа доставки


async def _cache_get_verdicts(
    items: "list[tuple[int, PendingMatch]]",
) -> "dict[int, LLMResult]":
    """Достаёт кэшированные вердикты; ошибки Redis → пустой результат (miss)."""
    if not items:
        return {}
    try:
        from app.cache import get_redis
        redis = await get_redis()
        raw = await redis.mget([_llm_cache_key(m.text) for _, m in items])
        hits: dict[int, LLMResult] = {}
        for (idx, _m), val in zip(items, raw):
            if not val:
                continue
            data = json.loads(val)
            hits[idx] = LLMResult(
                verdict=data["verdict"],
                relevant_segments=data.get("segments", []),
                reason=data.get("reason", ""),
                certainty=data.get("certainty", "low"),
                from_cache=True,
            )
        if hits:
            date = time.strftime("%Y-%m-%d", time.gmtime())
            pipe = redis.pipeline()
            pipe.incrby(f"stats:llm:cache_hit:{date}", len(hits))
            pipe.expire(f"stats:llm:cache_hit:{date}", 7 * 86400)
            await pipe.execute()
        return hits
    except Exception:
        logger.warning("LLM verdict cache read failed — treating as miss", exc_info=True)
        return {}


async def _cache_put_verdicts(
    items: "list[tuple[int, PendingMatch]]", results: "dict[int, LLMResult]",
) -> None:
    """Кладёт успешные (не fail-open) вердикты в кэш; ошибки Redis глотаются."""
    try:
        from app.cache import get_redis
        redis = await get_redis()
        pipe = redis.pipeline()
        stored = 0
        for idx, m in items:
            r = results.get(idx)
            if r is None or r.error:
                continue
            payload = json.dumps({
                "verdict": r.verdict,
                "segments": r.relevant_segments or [],
                "reason": r.reason,
                "certainty": r.certainty,
            }, ensure_ascii=False)
            pipe.setex(_llm_cache_key(m.text), _CACHE_TTL, payload)
            stored += 1
        if stored:
            await pipe.execute()
    except Exception:
        logger.warning("LLM verdict cache write failed", exc_info=True)


async def _record_llm_stats(results: "list[LLMResult]") -> None:
    """A2: почасовые счётчики fail-open — все fail-open пути ставят LLMResult.error.

    Вызывается из validate_batch только для сообщений, реально ходивших к LLM.
    Ключи stats:llm:{total,fail_open}:{YYYY-MM-DDTHH} (UTC, TTL 48ч);
    читает poller._check_llm_fail_open. Ошибки Redis не роняют валидацию.
    """
    from datetime import datetime, timezone

    total = len(results)
    if not total:
        return
    fails = sum(1 for r in results if r.error)
    hour = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    try:
        from app.cache import get_redis
        redis = await get_redis()
        pipe = redis.pipeline()
        pipe.incrby(f"stats:llm:total:{hour}", total)
        pipe.expire(f"stats:llm:total:{hour}", 172800)
        if fails:
            pipe.incrby(f"stats:llm:fail_open:{hour}", fails)
            pipe.expire(f"stats:llm:fail_open:{hour}", 172800)
        await pipe.execute()
    except Exception:
        logger.warning("LLM stats recording failed", exc_info=True)

# ═══════════════════════════════════════════════════════════════
# Prompt — compact, tested at 92.5% accuracy (batch-adapted)
# ═══════════════════════════════════════════════════════════════

# Segments where the LEAD is a SELLER («продам байк» + цена = лид, «куплю» =
# конкурент-покупатель) — DEMAND/OFFER inverted in the prompt. Loaded from DB
# (segments.lead_direction = 'supply') via set_supply_segments(); this default
# matches the migration values. NOTE: housing-buy was wrongly listed here
# before B4 — its actual demand keywords are «куплю квартиру» (lead = buyer).
DEFAULT_SUPPLY_SEGMENTS: frozenset[str] = frozenset({"moto-purchase", "car-purchase"})

# B2: manually curated calibration examples (👍→DEMAND, 👎→OFFER/OTHER).
# NOT auto-selected from live feedback — edit this constant only after eval.
# Keep short (≤6 lines) so prompt_tokens growth stays within ~30%.
FEW_SHOT_EXAMPLES: tuple[tuple[str, str, str, str], ...] = (
    # (text, candidate_segments_json, verdict, short_reason)
    (
        "нужен сантехник сегодня, протечка",
        '["repair"]',
        "DEMAND",
        "specialist need",
    ),
    (
        "подскажите репетитора английского для ребёнка",
        '["language-courses"]',
        "DEMAND",
        "tutor ask = demand",
    ),
    (
        "обмен USDT/VND, лучший курс, в личку",
        '["currency-exchange"]',
        "OFFER",
        "rate ad",
    ),
    (
        "массаж выезд, прайс в шапке, записывайтесь",
        '["massage"]',
        "OFFER",
        "service ad",
    ),
    (
        "логотипы от 150$, портфолио по запросу",
        '["design"]',
        "OFFER",
        "self-promo",
    ),
    (
        "ищу попутчика до Хошимина, делим бензин",
        '["taxi-transfer"]',
        "OTHER",
        "social ride",
    ),
)


def _render_few_shot(examples: tuple[tuple[str, str, str, str], ...] = FEW_SHOT_EXAMPLES) -> str:
    """Format curated few-shot lines for the system prompt."""
    if not examples:
        return ""
    lines = ["", "CALIBRATION (from real 👍/👎 feedback — follow these patterns):"]
    for text, segs, verdict, reason in examples:
        lines.append(f'"{text}" / {segs} → {verdict}, high ({reason})')
    return "\n".join(lines) + "\n"


def build_system_prompt(
    supply_segments: "set[str] | frozenset[str]",
    *,
    include_few_shot: bool = True,
) -> str:
    """Render the system prompt with the supply-direction segment list.

    The inverted DEMAND/OFFER block is generated from DB-driven slugs so new
    segments (e.g. moto-sale) never silently fall into the wrong semantics.
    """
    if supply_segments:
        slugs = ", ".join(sorted(supply_segments))
        supply_block = f"""SUPPLY-DIRECTION SEGMENTS ({slugs}) — the lead is a SELLER:
- "продам байк"+price → DEMAND (seller = LEAD for buyer-user)
- "куплю/ищу мотоцикл"+budget → OFFER (competing buyer)

ALL OTHER SEGMENTS (rental, services, buy/sale where the lead is the buyer):
- "ищу парикмахера", "сниму квартиру", "куплю авто", "нужен сантехник" → DEMAND
- "предлагаю услуги", "сдам квартиру", "сдаю скутер" → OFFER

"""
        supply_examples = (
            '"продам байк, 3 млн" / ["moto-purchase"] → DEMAND, high (seller=lead for buyer)\n'
            '"куплю мотоцикл до 2000$" / ["moto-purchase"] → OFFER, high (competing buyer)\n'
        )
    else:
        supply_block = ""
        supply_examples = ""

    few_shot = _render_few_shot() if include_few_shot else ""

    return f"""You are a message classifier for LeadHunter, a lead generation service.
Classify each message as: DEMAND | OFFER | MIXED | OTHER.

DEMAND — author is LOOKING FOR a product/service/contractor. Markers: "ищу + service", "нужен + specialist", "кто делает/знает + job", "посоветуйте", "где купить/заказать", "сколько стоит", "сниму", "требуется", "кто может + verb", "подберите", "порекомендуйте".
NOT DEMAND: everyday social searches ("ищу попутчика", "ищу с кем поиграть") → OTHER.

OFFER — author is SELLING/ADVERTISING. Markers: "продам/продаю", "сдам/сдаю", "предлагаю", price+product, "пишите в лс", phones/price-lists, "записывайтесь"+service.

MIXED — both demand and offer. Treat as DEMAND.

OTHER — news, discussions, travel companions, game partners, memes, weather.

{supply_block}CRITICAL: When UNCERTAIN between DEMAND and OFFER → DEMAND. Fail-open: never lose a lead.

EXAMPLES:
"ищу повара, Нячанг" / ["catering"] → DEMAND, high
{supply_examples}"сдам квартиру, 10 млн" / ["housing-rent"] → OFFER, high (competing landlord)
"сниму квартиру, бюджет 10 млн" / ["housing-rent"] → DEMAND, high (renter=lead)
"ищу с кем поиграть в теннис" / ["tennis"] → OTHER, high (social, not commercial)
{few_shot}
Return a JSON array with one object per message:
[{{"index": N, "category": "DEMAND"|"OFFER"|"MIXED"|"OTHER", "relevant_segments": [...], "certainty": "high"|"medium"|"low", "reason": "..."}}, ...]

RULES:
- relevant_segments: DEMAND/MIXED → confirmed segments (subset of candidates OK); OFFER/OTHER → []
- certainty: "high" = clear markers; "medium" = some markers; "low" = borderline → treat as DEMAND
- "index" must match the message number exactly"""


LLM_SYSTEM_PROMPT = build_system_prompt(DEFAULT_SUPPLY_SEGMENTS)

# ═══════════════════════════════════════════════════════════════
# Confidence gate — skip LLM for obvious demand signals
# ═══════════════════════════════════════════════════════════════

# Direct demand verbs at message start — high-confidence demand signal
_HIGH_CONFIDENCE_DEMAND_LEAD = re.compile(
    r'^(ищу|нужен|нужна|нужно|нужны|требуется|требуются|сниму|снимем|куплю|приобрету|закажу)\b',
    re.IGNORECASE,
)

# If message starts with demand verb AND is short (< 200 chars), skip LLM
HIGH_CONFIDENCE_MAX_LENGTH = 200


def is_high_confidence_demand(text: str) -> bool:
    """Check if message is an obvious demand that doesn't need LLM validation."""
    if len(text) > HIGH_CONFIDENCE_MAX_LENGTH:
        return False
    return bool(_HIGH_CONFIDENCE_DEMAND_LEAD.match(text.strip()))


# ═══════════════════════════════════════════════════════════════
# PII masking
# ═══════════════════════════════════════════════════════════════

_PHONE_RE = re.compile(r'\+?\d[\d\s\-().]{6,}\d')
_USERNAME_RE = re.compile(r'@\w{3,}')
_LINK_RE = re.compile(r't\.me/\S+|https?://\S+')

MASK_PHONE = "[PHONE]"
MASK_USER = "@[USER]"
MASK_LINK = "[LINK]"


def sanitize_text(text: str) -> str:
    """Mask PII before sending to LLM or storing in DB."""
    text = _PHONE_RE.sub(MASK_PHONE, text)
    text = _USERNAME_RE.sub(MASK_USER, text)
    text = _LINK_RE.sub(MASK_LINK, text)
    return text


# ═══════════════════════════════════════════════════════════════
# LLM call result
# ═══════════════════════════════════════════════════════════════

@dataclass
class LLMResult:
    verdict: str          # "DEMAND" | "OFFER" | "MIXED" | "OTHER"
    relevant_segments: list[str] = field(default_factory=list)
    reason: str = ""
    certainty: str = "low"
    error: str | None = None  # set on API failure → fail-open
    raw_response: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    from_cache: bool = False  # B5: вердикт взят из кэша репостов, LLM не вызывалась


# ═══════════════════════════════════════════════════════════════
# Batch match entry (collected by poller, validated in batch)
# ═══════════════════════════════════════════════════════════════

@dataclass
class PendingMatch:
    """A classifier match queued for batch LLM validation."""
    chat_username: str
    message_id: int
    text: str
    candidate_segments: list[str]
    chat_title: str | None = None  # human-readable name for the notification
    account_id: int = 0  # which userbot account found this match
    is_urgent: bool = False
    sender: str | None = None
    # Author display name — shown when there is no public @username
    sender_name: str | None = None
    # Set after validation
    llm_result: LLMResult | None = None
    # High-confidence demand — skip LLM
    skip_llm: bool = False
    # Matched only by a personal user keyword (no segments) — always skips
    # LLM and the reality filter: personal keywords work unconditionally.
    keyword_only: bool = False


# ═══════════════════════════════════════════════════════════════
# Validator
# ═══════════════════════════════════════════════════════════════

MAX_BATCH_SIZE = 20       # max messages per LLM API call (reduced for reliable JSON)
BATCH_MAX_TOKENS = 2000   # max output tokens per batch call (~20 msgs × ~40t + markdown)


class LLMValidator:
    """Calls DeepSeek API to validate rule-based matches."""

    def __init__(self) -> None:
        self._endpoint = "https://api.deepseek.com/v1/chat/completions"
        self._timeout = aiohttp.ClientTimeout(total=30)  # longer for batches
        self._system_prompt = LLM_SYSTEM_PROMPT
        self._supply_segments: frozenset[str] = DEFAULT_SUPPLY_SEGMENTS

    def set_supply_segments(self, slugs: "set[str] | frozenset[str]") -> None:
        """Rebuild the cached system prompt from DB-driven supply segments.

        Called by the poller after every keyword reload — prompt follows
        segments.lead_direction without a code change.
        """
        slugs = frozenset(slugs)
        if slugs != self._supply_segments:
            self._supply_segments = slugs
            self._system_prompt = build_system_prompt(slugs)
            logger.info("LLM prompt rebuilt: supply segments = %s", sorted(slugs))

    def build_prompt_v2(
        self,
        profiles: tuple,
        *,
        system_prompt_version: int = LLM_PROMPT_V2_VERSION,
    ) -> str:
        """Compose segment-aware prompt v2 (not used for delivery until Phase 8)."""
        return build_segment_aware_prompt(
            system_prompt_version=system_prompt_version,
            supply_segments=self._supply_segments,
            profiles=profiles,
        )

    @staticmethod
    def build_user_message_v2(
        items: list[tuple[int, str, list[str]]],
    ) -> str:
        """User-role payload with Telegram text marked UNTRUSTED_CONTENT."""
        return build_untrusted_batch_user_message(items)

    @property
    def enabled(self) -> bool:
        return settings.llm_enabled and bool(settings.deepseek_api_key)

    # ── Single-message validation (kept for backward compat) ──

    async def validate(
        self, text: str, candidate_segments: list[str],
    ) -> LLMResult:
        """Validate a single match. Prefer validate_batch() for efficiency."""
        results = await self.validate_batch([
            PendingMatch(
                chat_username="", message_id=0,
                text=text, candidate_segments=candidate_segments,
            )
        ])
        return results[0] if results else LLMResult(
            verdict="DEMAND", reason="Empty batch result — fail-open",
        )

    # ── Batch validation (primary path) ──

    async def validate_batch(
        self, matches: list[PendingMatch],
    ) -> list[LLMResult]:
        """Validate multiple matches in one API call. Fail-open per message."""
        if not matches:
            return []

        if not self.enabled:
            return [
                LLMResult(verdict="DEMAND", reason="LLM disabled")
                for _ in matches
            ]

        # Separate: high-confidence demands skip LLM entirely
        results: list[LLMResult | None] = [None] * len(matches)
        needs_llm: list[tuple[int, PendingMatch]] = []

        for i, m in enumerate(matches):
            if m.skip_llm or is_high_confidence_demand(m.text):
                results[i] = LLMResult(
                    verdict="DEMAND",
                    relevant_segments=m.candidate_segments,
                    reason="High-confidence demand — skipped LLM",
                    certainty="high",
                )
            else:
                needs_llm.append((i, m))

        if not needs_llm:
            return [r for r in results if r is not None]

        # B5: репосты одного объявления в N чатов — вердикт из кэша, без LLM
        cached = await _cache_get_verdicts(needs_llm)
        for idx, r in cached.items():
            results[idx] = r
        to_llm = [(i, m) for i, m in needs_llm if i not in cached]

        # Process in batches of MAX_BATCH_SIZE
        all_batch_results: dict[int, LLMResult] = {}

        for batch_start in range(0, len(to_llm), MAX_BATCH_SIZE):
            batch_items = to_llm[batch_start:batch_start + MAX_BATCH_SIZE]
            batch_results = await self._call_llm_batch(batch_items)
            all_batch_results.update(batch_results)

        await _cache_put_verdicts(to_llm, all_batch_results)

        # Merge: fill in LLM results for messages that needed validation
        for i, r in enumerate(results):
            if r is None:
                results[i] = all_batch_results.get(i, LLMResult(
                    verdict="DEMAND",
                    reason="Missing in LLM response — fail-open",
                    error="missing_in_response",
                ))

        # A2: метрика fail-open — ТОЛЬКО по сообщениям, реально ходившим к LLM
        # (skip_llm/high-confidence/кэш-хиты не разбавляют знаменатель алерта)
        await _record_llm_stats([results[i] for i, _ in to_llm])

        return [r for r in results if r is not None]

    async def _call_llm_batch(
        self, items: list[tuple[int, PendingMatch]],
    ) -> dict[int, LLMResult]:
        """Send one batch of messages to LLM, return index→result map."""
        # Build batch user message
        lines = []
        for idx, m in items:
            masked = sanitize_text(m.text)
            segs = json.dumps(m.candidate_segments)
            lines.append(f"[{idx + 1}] Message: {masked}\n    Candidates: {segs}")

        user_message = (
            f"Classify these {len(items)} messages:\n\n"
            + "\n\n".join(lines)
        )

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": settings.deepseek_model,
                    "messages": [
                        {"role": "system", "content": self._system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": 0.0,
                    "max_tokens": BATCH_MAX_TOKENS,
                }
                headers = {
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                }

                t0 = time.monotonic()
                async with session.post(
                    self._endpoint, json=payload, headers=headers,
                    timeout=self._timeout,
                ) as resp:
                    elapsed = time.monotonic() - t0

                    if resp.status != 200:
                        body = await resp.text()
                        logger.warning(
                            "LLM batch API error %d (%.1fs): %s",
                            resp.status, elapsed, body[:200],
                        )
                        return self._fail_open_all(items, f"HTTP {resp.status}")

                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {})
                    tokens_total = usage.get("total_tokens", 0)
                    tokens_prompt = usage.get("prompt_tokens", 0)
                    tokens_completion = usage.get("completion_tokens", 0)

                    # Parse JSON — accept both array and single object
                    try:
                        cleaned = content.strip()
                        # Remove markdown code fences (```json or ```)
                        if cleaned.startswith("```"):
                            first_nl = cleaned.find("\n")
                            if first_nl != -1:
                                cleaned = cleaned[first_nl + 1:]
                            if cleaned.rstrip().endswith("```"):
                                cleaned = cleaned.rstrip()[:-3]
                        # Balance brackets (LLM may truncate mid-response)
                        if cleaned.count("[") > cleaned.count("]"):
                            cleaned = cleaned.rstrip() + "]" * (cleaned.count("[") - cleaned.count("]"))
                        parsed = json.loads(cleaned)
                    except json.JSONDecodeError:
                        logger.warning(
                            "LLM batch JSON parse failed: %s", content[:300],
                        )
                        return self._fail_open_all(items, "JSON parse error")

                    # Normalize: single object → list
                    if isinstance(parsed, dict):
                        parsed_list = [parsed]
                    elif isinstance(parsed, list):
                        parsed_list = parsed
                    else:
                        logger.warning("LLM batch response not JSON: %s", content[:200])
                        return self._fail_open_all(items, "Response not JSON")

                    # Map results by index
                    results: dict[int, LLMResult] = {}
                    seen_indices: set[int] = set()

                    # Handle single-object response for single-item batches
                    if len(parsed_list) == 1 and len(items) == 1:
                        obj = parsed_list[0]
                        if isinstance(obj, dict) and "index" not in obj:
                            obj = {**obj, "index": 1}  # assume index 1
                            parsed_list = [obj]

                    for obj in parsed_list:
                        if not isinstance(obj, dict):
                            continue
                        idx = obj.get("index", -1)
                        if idx < 1:
                            continue
                        real_idx = idx - 1  # convert to 0-based
                        seen_indices.add(real_idx)
                        results[real_idx] = LLMResult(
                            verdict=obj.get("category", "DEMAND"),
                            relevant_segments=obj.get("relevant_segments", []),
                            reason=obj.get("reason", ""),
                            certainty=obj.get("certainty", "low"),
                            raw_response=json.dumps(obj),
                            prompt_tokens=tokens_prompt,
                            completion_tokens=tokens_completion,
                            total_tokens=tokens_total,
                        )

                    # Fail-open for any missing indices
                    for orig_idx, _ in items:
                        if orig_idx not in results:
                            results[orig_idx] = LLMResult(
                                verdict="DEMAND",
                                reason="Missing in LLM batch response — fail-open",
                                error="missing_in_batch",
                            )

                    logger.debug(
                        "LLM batch: %d/%d msgs classified (%.1fs, %d tokens)",
                        len(seen_indices), len(items), elapsed, tokens_total,
                    )
                    return results

        except asyncio.TimeoutError:
            logger.warning(
                "LLM batch timeout after %.0fs — fail-open %d msgs",
                self._timeout.total, len(items),
            )
            return self._fail_open_all(items, "timeout")
        except Exception as exc:
            logger.warning("LLM batch call failed: %s — fail-open", exc)
            return self._fail_open_all(items, str(exc))

    def _fail_open_all(
        self, items: list[tuple[int, PendingMatch]], error: str,
    ) -> dict[int, LLMResult]:
        """All items pass through on failure."""
        return {
            orig_idx: LLMResult(
                verdict="DEMAND",
                reason=f"LLM batch error — fail-open: {error}",
                error=error,
            )
            for orig_idx, _ in items
        }

    def should_block(self, result: LLMResult) -> bool:
        """Whether to block the match in 'blocking' mode.

        Only blocks OFFER/OTHER with high certainty.
        DEMAND/MIXED always pass. Low/medium certainty → pass.
        """
        if result.verdict in ("DEMAND", "MIXED"):
            return False
        if result.certainty != "high":
            return False
        return True


# Global singleton
llm_validator = LLMValidator()
