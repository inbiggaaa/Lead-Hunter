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
