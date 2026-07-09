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

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Prompt — compact, tested at 92.5% accuracy (batch-adapted)
# ═══════════════════════════════════════════════════════════════

LLM_SYSTEM_PROMPT = """You are a message classifier for LeadHunter, a lead generation service.
Classify each message as: DEMAND | OFFER | MIXED | OTHER.

DEMAND — author is LOOKING FOR a product/service/contractor. Markers: "ищу + service", "нужен + specialist", "кто делает/знает + job", "посоветуйте", "где купить/заказать", "сколько стоит", "сниму", "требуется", "кто может + verb", "подберите", "порекомендуйте".
NOT DEMAND: everyday social searches ("ищу попутчика", "ищу с кем поиграть") → OTHER.

OFFER — author is SELLING/ADVERTISING. Markers: "продам/продаю", "сдам/сдаю", "предлагаю", price+product, "пишите в лс", phones/price-lists, "записывайтесь"+service.

MIXED — both demand and offer. Treat as DEMAND.

OTHER — news, discussions, travel companions, game partners, memes, weather.

PURCHASE SEGMENTS (moto-purchase, car-purchase, housing-buy):
- "продам байк"+price → DEMAND (seller = LEAD for buyer-user)
- "куплю/ищу мотоцикл"+budget → OFFER (competing buyer)

RENTAL & SERVICE SEGMENTS (housing-rent, scooter-rental, everything else):
- "ищу парикмахера", "сниму квартиру", "нужен сантехник" → DEMAND
- "предлагаю услуги", "сдам квартиру", "сдаю скутер" → OFFER

CRITICAL: When UNCERTAIN between DEMAND and OFFER → DEMAND. Fail-open: never lose a lead.

EXAMPLES:
"ищу повара, Нячанг" / ["catering"] → DEMAND, high
"продам байк, 3 млн" / ["moto-purchase"] → DEMAND, high (seller=lead for buyer)
"куплю мотоцикл до 2000$" / ["moto-purchase"] → OFFER, high (competing buyer)
"сдам квартиру, 10 млн" / ["housing-rent"] → OFFER, high (competing landlord)
"сниму квартиру, бюджет 10 млн" / ["housing-rent"] → DEMAND, high (renter=lead)
"ищу с кем поиграть в теннис" / ["tennis"] → OTHER, high (social, not commercial)

Return a JSON array with one object per message:
[{"index": N, "category": "DEMAND"|"OFFER"|"MIXED"|"OTHER", "relevant_segments": [...], "certainty": "high"|"medium"|"low", "reason": "..."}, ...]

RULES:
- relevant_segments: DEMAND/MIXED → confirmed segments (subset of candidates OK); OFFER/OTHER → []
- certainty: "high" = clear markers; "medium" = some markers; "low" = borderline → treat as DEMAND
- "index" must match the message number exactly"""

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
    account_id: int = 0  # which userbot account found this match
    is_urgent: bool = False
    sender: str | None = None
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

        # Process in batches of MAX_BATCH_SIZE
        all_batch_results: dict[int, LLMResult] = {}

        for batch_start in range(0, len(needs_llm), MAX_BATCH_SIZE):
            batch_items = needs_llm[batch_start:batch_start + MAX_BATCH_SIZE]
            batch_results = await self._call_llm_batch(batch_items)
            all_batch_results.update(batch_results)

        # Merge: fill in LLM results for messages that needed validation
        for i, r in enumerate(results):
            if r is None:
                results[i] = all_batch_results.get(i, LLMResult(
                    verdict="DEMAND",
                    reason="Missing in LLM response — fail-open",
                    error="missing_in_response",
                ))

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
                        {"role": "system", "content": LLM_SYSTEM_PROMPT},
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
