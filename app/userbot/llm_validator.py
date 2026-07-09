"""LLM validator — DeepSeek-powered precision filter for lead matching.

Shadow mode (default): validates every match, logs the verdict, never blocks.
Blocking mode: blocks OFFER/OTHER with high certainty, passes everything else.

Architecture:
- classify_message (rules, wide recall) → LLMValidator.validate (precision filter)
- Fail-open: LLM errors/timeouts → match passes through (never lose a lead)
- PII masking: phones/@usernames/links sanitized before sending to LLM
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
# Prompt — tested at 92.5% accuracy, 0 Type A (lost leads)
# ═══════════════════════════════════════════════════════════════

LLM_SYSTEM_PROMPT = """You are a message classifier for LeadHunter, a lead generation service. Classify the message into exactly one of four categories:

DEMAND — Commercial demand. The author is LOOKING FOR a product/service/contractor/vendor. Markers: "ищу + service", "нужен + specialist", "кто делает/знает + job", "посоветуйте", "где купить/заказать", "сколько стоит", "сниму", "требуется". IMPORTANT: everyday social searches ("ищу попутчика", "ищу с кем поиграть") are OTHER, not DEMAND.

OFFER — The author is OFFERING a service/product, advertising. Markers: "продам/продаю", "сдам/сдаю", "предлагаю", price + product, "пишите в лс", phone numbers, price lists, "записывайтесь" + service, apartment codes.

MIXED — Contains BOTH demand and offer ("куплю байк или обменяю на свой"). Treat as DEMAND — if there is a demand component, it is a potential lead.

OTHER — Everything else: news, discussions, travel companion search, game partner search, memes, weather questions, personal experience questions.

PURCHASE SEGMENTS (moto-purchase, car-purchase, housing-buy): user is a BUYER looking for SELLERS.
- Classify seller messages ("продам байк", "продаю авто", price+product) as DEMAND — these are LEADS, the user wants to see them.
- Classify other buyer messages ("куплю мотоцикл", "ищу авто", "приобрету") as OFFER — these are COMPETITORS competing for the same supply, BLOCK them.

RENTAL & SERVICE SEGMENTS (housing-rent, scooter-rental, and everything else): user is a PROVIDER/LANDLORD looking for CLIENTS/RENTERS.
- DEMAND = people searching for a service or to rent ("ищу парикмахера", "сниму квартиру", "нужен сантехник", "хочу арендовать")
- OFFER = other providers/landlords advertising ("предлагаю услуги", "сдам квартиру", "сдаю скутер", "работаю мастером")

CRITICAL — ASYMMETRIC BIAS: If UNCERTAIN between DEMAND and OFFER → choose DEMAND.
Only classify as OFFER when CONFIDENT the author is selling/advertising.
When in doubt, the benefit goes to DEMAND.

Respond with STRICT JSON only:
{"category": "DEMAND"|"OFFER"|"MIXED"|"OTHER", "relevant_segments": [...], "certainty": "high"|"medium"|"low", "reason": "..."}

RULES:
- relevant_segments: DEMAND/MIXED → confirmed segments from candidates (may be subset); OFFER/OTHER → []
- certainty: "high" = clear markers, unambiguous; "medium" = some markers; "low" = borderline → treat as DEMAND

EXAMPLES:

[DEMAND — direct]
Message: "ищу повара для семьи в Нячанге, на постоянной основе"
Candidates: ["catering"]
→ {"category": "DEMAND", "relevant_segments": ["catering"], "certainty": "high", "reason": "Explicit service search — commercial demand"}

[DEMAND — question form]
Message: "кто знает хорошего стоматолога в Нячанге? желательно русскоговорящего"
Candidates: ["dentist"]
→ {"category": "DEMAND", "relevant_segments": ["dentist"], "certainty": "high", "reason": "Asking for a specialist recommendation — demand despite no 'ищу' word"}

[DEMAND — seller in purchase segment (LEAD)]
Message: "Продам байк Sym Atilla 2019, документы в наличии, 3 млн, Нячанг"
Candidates: ["moto-purchase"]
→ {"category": "DEMAND", "relevant_segments": ["moto-purchase"], "certainty": "high", "reason": "'Продам' + price — seller listing. User is a BUYER, this is a LEAD"}

[DEMAND — renter in housing segment (LEAD)]
Message: "Сниму квартиру в Нячанге, бюджет до 10 млн, на длительный срок"
Candidates: ["housing-rent"]
→ {"category": "DEMAND", "relevant_segments": ["housing-rent"], "certainty": "high", "reason": "'Сниму' + budget — renter looking for a place. User is a LANDLORD, this is a LEAD"}

[OFFER — competing buyer in purchase segment]
Message: "Ищу мотоцикл до 2000$, рассматриваю Honda Air Blade и Yamaha NVX"
Candidates: ["moto-purchase"]
→ {"category": "OFFER", "relevant_segments": [], "certainty": "high", "reason": "'Ищу' + budget — another BUYER competing for supply. User is a BUYER too → BLOCK"}

[OFFER — landlord in housing segment]
Message: "Сдам квартиру в Нячанге, район европейский квартал, 10 млн/мес"
Candidates: ["housing-rent"]
→ {"category": "OFFER", "relevant_segments": [], "certainty": "high", "reason": "'Сдам' + price — another LANDLORD advertising. User is a LANDLORD too → BLOCK"}

[OFFER — disguised ad]
Message: "есть места на йогу по утрам, записывайтесь, район центр"
Candidates: ["yoga"]
→ {"category": "OFFER", "relevant_segments": [], "certainty": "high", "reason": "Disguised ad: 'spots available' + 'sign up' — selling, not looking"}

[MIXED — seller is the lead]
Message: "Продам Honda Air Blade или обменяю на скутер, с доплатой"
Candidates: ["moto-purchase"]
→ {"category": "DEMAND", "relevant_segments": ["moto-purchase"], "certainty": "medium", "reason": "Primary intent 'Продам' — seller is a lead for the user (buyer). Trade secondary → DEMAND per fail-open"}

[OTHER — social search (NOT demand)]
Message: "ищу с кем поиграть в теннис в Муйне, уровень средний"
Candidates: ["tennis"]
→ {"category": "OTHER", "relevant_segments": [], "certainty": "high", "reason": "Social game partner search — not commercial demand"}

Now classify this message:"""

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
# Validator
# ═══════════════════════════════════════════════════════════════

class LLMValidator:
    """Calls DeepSeek API to validate rule-based matches."""

    def __init__(self) -> None:
        self._endpoint = "https://api.deepseek.com/v1/chat/completions"
        self._timeout = aiohttp.ClientTimeout(total=10)

    @property
    def enabled(self) -> bool:
        return settings.llm_enabled and bool(settings.deepseek_api_key)

    async def validate(
        self, text: str, candidate_segments: list[str],
    ) -> LLMResult:
        """Validate a rule-based match. Fail-open: errors → DEMAND."""
        if not self.enabled:
            return LLMResult(verdict="DEMAND", reason="LLM disabled")

        masked = sanitize_text(text)
        segments_str = json.dumps(candidate_segments)
        user_message = f"Message: {masked}\nCandidates: {segments_str}"

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": settings.deepseek_model,
                    "messages": [
                        {"role": "system", "content": LLM_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": 0.0,
                    "max_tokens": 300,
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
                            "LLM API error %d (%.1fs): %s",
                            resp.status, elapsed, body[:200],
                        )
                        return LLMResult(
                            verdict="DEMAND",
                            reason="LLM API error — fail-open",
                            error=f"HTTP {resp.status}",
                            raw_response=body[:500],
                        )

                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {})
                    tokens_total = usage.get("total_tokens", 0)
                    tokens_prompt = usage.get("prompt_tokens", 0)
                    tokens_completion = usage.get("completion_tokens", 0)

                    try:
                        parsed = json.loads(content)
                    except json.JSONDecodeError:
                        logger.warning("LLM JSON parse failed: %s", content[:200])
                        return LLMResult(
                            verdict="DEMAND",
                            reason="LLM response parse error — fail-open",
                            error="JSON parse",
                            raw_response=content[:500],
                        )

                    logger.debug(
                        "LLM: %s cert=%s (%.1fs %dt) — %s",
                        parsed.get("category", "?"),
                        parsed.get("certainty", "?"),
                        elapsed, tokens_total,
                        parsed.get("reason", "")[:100],
                    )
                    return LLMResult(
                        verdict=parsed.get("category", "DEMAND"),
                        relevant_segments=parsed.get("relevant_segments", []),
                        reason=parsed.get("reason", ""),
                        certainty=parsed.get("certainty", "low"),
                        raw_response=content,
                        prompt_tokens=tokens_prompt,
                        completion_tokens=tokens_completion,
                        total_tokens=tokens_total,
                    )

        except asyncio.TimeoutError:
            logger.warning("LLM timeout after %.0fs — fail-open", self._timeout.total)
            return LLMResult(
                verdict="DEMAND",
                reason="LLM timeout — fail-open",
                error="timeout",
            )
        except Exception as exc:
            logger.warning("LLM call failed: %s — fail-open", exc)
            return LLMResult(
                verdict="DEMAND",
                reason=f"LLM error — fail-open: {exc}",
                error=str(exc),
            )

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
