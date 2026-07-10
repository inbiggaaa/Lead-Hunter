"""Eval-конвейер качества матчинга (задача C1 из fable_audit.md).

Офлайн, read-only к прод-БД/Redis (localhost-биндинги, worker НЕ трогается):
- корпус: llm_decisions (последние N) + feedback (👍=relevant / 👎=not_relevant,
  текст через join с llm_decisions) + сэмпл stats:unmatched из Redis;
- прогон через ТЕКУЩИЙ классификатор (app.userbot.classifier) с прод-набором
  keywords из БД — по-сегментно: pass1-хиты, блоки stop-словами, блоки Pass 3,
  блоки reality-фильтром, финальные матчи;
- LLM-вердикты и precision по feedback — из сохранённых решений;
- шаблон таблицы ручной разметки 100 unmatched-сообщений (кандидаты в FN).

Правило процесса: любые изменения правил классификатора или LLM-промпта
сопровождаются прогоном этого скрипта; отчёты — docs/eval/report_YYYY-MM-DD.md.

Usage: venv/bin/python tools/eval_matching.py [--decisions 1000] [--unmatched 500]
"""

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import asyncpg
from redis.asyncio import Redis

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.userbot.classifier import (  # noqa: E402
    CompiledKeywordMap,
    _cws_match,
    _has_offer_signal,
    _has_strong_demand_signal,
    _lemmatize_text,
    _MatchCtx,
    _PASS3_STRONG_DEMAND_RX,
    classify_message,
    compile_keyword_map,
)

OUT_DIR = PROJECT_ROOT / "docs" / "eval"
LLM_PASS_VERDICTS = ("DEMAND", "MIXED")  # llm_validator: пропускающие вердикты
MANUAL_SAMPLE = 100


def _read_env(path: Path) -> dict[str, str]:
    """Minimal .env parser — KEY=VALUE lines, no interpolation."""
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


# ── Загрузка прод-конфигурации классификатора (зеркало poller._load_keywords) ──

async def load_classifier_config(conn) -> tuple[CompiledKeywordMap, dict, set, dict]:
    """Returns (compiled_map, domain_word_map, pass3_skip, keyword_map)."""
    try:
        seg_rows = await conn.fetch(
            "SELECT id, slug, lead_direction FROM segments"
        )
        pass3_skip = {
            r["slug"] for r in seg_rows if r["lead_direction"] in ("buy", "supply")
        }
    except asyncpg.UndefinedColumnError:
        # БД до миграции lead_direction01 (B4) — легаси-константа классификатора
        from app.userbot.classifier import PURCHASE_SEGMENTS
        seg_rows = await conn.fetch("SELECT id, slug FROM segments")
        pass3_skip = set(PURCHASE_SEGMENTS)
    segments = {r["id"]: r["slug"] for r in seg_rows}

    kw_rows = await conn.fetch(
        "SELECT segment_id, text, keyword_type FROM segment_keywords"
        " WHERE is_active = true"
    )
    keyword_map: dict[str, dict[str, list[str]]] = {}
    domain_word_map: dict[str, list[str]] = {}
    universal_stops: list[str] = []
    for r in kw_rows:
        if r["segment_id"] is None:
            if r["keyword_type"] == "stop":
                universal_stops.append(r["text"])
            continue
        slug = segments.get(r["segment_id"])
        if not slug:
            continue
        keyword_map.setdefault(slug, {"demand": [], "stop": [], "synonym": []})
        keyword_map[slug][r["keyword_type"]].append(r["text"])
        if r["keyword_type"] == "synonym":
            domain_word_map.setdefault(slug, []).append(r["text"].lower())

    compiled = compile_keyword_map(keyword_map, universal_stops)
    return compiled, domain_word_map, pass3_skip, keyword_map


# ── Инструментированная классификация ──
# Зеркало classify_message с раскладкой по проходам; финальный результат
# сверяется с настоящим classify_message на каждом сообщении (защита от дрейфа).

def explain_classify(
    text: str, compiled: CompiledKeywordMap, pass3_skip: set[str],
) -> dict[str, list[str]]:
    """{'pass1': [...], 'stop_blocked': [...], 'pass3_blocked': [...], 'matched': [...]}"""
    out: dict[str, list[str]] = {
        "pass1": [], "stop_blocked": [], "pass3_blocked": [], "matched": [],
    }
    if not text:
        return out

    text_lower = text.lower()
    text_lemma = _lemmatize_text(text_lower)
    lemma_differs = text_lemma != text_lower
    match_ctx = _MatchCtx(compiled.window, text_lower, text_lemma)
    has_strong = _has_strong_demand_signal(text)
    has_demand_ctx = has_strong or ("?" in text)
    has_offer_ctx = _has_offer_signal(text)
    universal_hit: bool | None = None

    for slug, demand_kws, stop_cws in compiled.segments:
        if not demand_kws:
            continue
        if not any(ck.match(match_ctx, lemma_differs) for ck in demand_kws):
            continue
        out["pass1"].append(slug)

        if not has_strong:
            if universal_hit is None:
                universal_hit = any(
                    _cws_match(cws, text_lower) for cws in compiled.universal_stops
                )
            if universal_hit or any(_cws_match(cws, text_lower) for cws in stop_cws):
                out["stop_blocked"].append(slug)
                continue

        if slug not in pass3_skip:
            if has_offer_ctx and not has_demand_ctx:
                out["pass3_blocked"].append(slug)
                continue
            if has_offer_ctx and has_demand_ctx:
                if not _PASS3_STRONG_DEMAND_RX.search(text_lower):
                    out["pass3_blocked"].append(slug)
                    continue

        out["matched"].append(slug)

    real = classify_message(text, compiled, purchase_segments=pass3_skip)
    if real.matched_segments != out["matched"]:
        raise AssertionError(
            f"explain_classify разошёлся с classify_message: "
            f"{out['matched']} != {real.matched_segments} | text={text[:80]!r}"
        )
    return out


def filter_by_domain(
    text: str, segments: list[str], domain_word_map: dict[str, list[str]],
) -> list[str]:
    """Зеркало poller._filter_by_domain (reality-фильтр перед LLM).

    Держать синхронно с app/userbot/poller.py::_filter_by_domain.
    """
    text_lower = text.lower()
    verified = []
    for slug in segments:
        words = domain_word_map.get(slug)
        if not words:
            verified.append(slug)
            continue
        for w in words:
            if w in text_lower:
                verified.append(slug)
                break
    return verified


# ── Сбор корпуса ──

async def fetch_decisions(conn, limit: int) -> list[dict]:
    rows = await conn.fetch(
        "SELECT chat_username, message_id, message_text_masked,"
        " rule_segments, llm_verdict, llm_segments, llm_mode"
        " FROM llm_decisions ORDER BY id DESC LIMIT $1",
        limit,
    )
    return [dict(r) for r in rows]


async def fetch_feedback(conn) -> list[dict]:
    """Feedback + текст/сегменты из последнего llm_decision по тому же сообщению."""
    rows = await conn.fetch(
        """
        SELECT f.chat_username, f.message_id, f.verdict,
               d.message_text_masked, d.rule_segments, d.llm_segments
        FROM feedback f
        LEFT JOIN LATERAL (
            SELECT message_text_masked, rule_segments, llm_segments
            FROM llm_decisions d
            WHERE d.chat_username = f.chat_username
              AND d.message_id = f.message_id
            ORDER BY d.id DESC LIMIT 1
        ) d ON true
        ORDER BY f.id
        """
    )
    return [dict(r) for r in rows]


async def fetch_unmatched(redis: Redis, limit: int) -> list[dict]:
    entries = await redis.lrange("stats:unmatched", 0, limit - 1)
    out = []
    for e in entries:
        try:
            out.append(json.loads(e))
        except json.JSONDecodeError:
            continue
    return out


# ── Агрегация ──

def new_seg_stats() -> dict[str, int]:
    return {
        "pass1": 0, "stop_blocked": 0, "pass3_blocked": 0, "matched": 0,
        "reality_blocked": 0, "llm_pass": 0, "llm_reject": 0,
        "fb_relevant": 0, "fb_not_relevant": 0,
    }


def aggregate_corpus(
    texts: list[str], compiled: CompiledKeywordMap,
    pass3_skip: set[str], domain_word_map: dict,
    stats: dict[str, dict[str, int]],
) -> None:
    """Прогон текстов через классификатор + reality-фильтр, инкремент stats."""
    for text in texts:
        detail = explain_classify(text, compiled, pass3_skip)
        verified = filter_by_domain(text, detail["matched"], domain_word_map)
        for slug in detail["pass1"]:
            stats[slug]["pass1"] += 1
        for slug in detail["stop_blocked"]:
            stats[slug]["stop_blocked"] += 1
        for slug in detail["pass3_blocked"]:
            stats[slug]["pass3_blocked"] += 1
        for slug in detail["matched"]:
            stats[slug]["matched"] += 1
            if slug not in verified:
                stats[slug]["reality_blocked"] += 1


def aggregate_llm(decisions: list[dict], stats: dict[str, dict[str, int]]) -> dict:
    """LLM-вердикты: по-сегментно (одобрен ли slug) и общая сводка по вердиктам."""
    verdict_counts: dict[str, int] = defaultdict(int)
    for d in decisions:
        verdict_counts[d["llm_verdict"]] += 1
        approved = set(d["llm_segments"] or [])
        passing = d["llm_verdict"] in LLM_PASS_VERDICTS
        for slug in d["rule_segments"] or []:
            if passing and (not approved or slug in approved):
                stats[slug]["llm_pass"] += 1
            else:
                stats[slug]["llm_reject"] += 1
    return dict(verdict_counts)


def aggregate_feedback(feedback: list[dict], stats: dict[str, dict[str, int]]) -> dict:
    """Precision по feedback: общая и по-сегментно (сегменты — из llm_decision)."""
    totals = {"relevant": 0, "not_relevant": 0, "no_text": 0}
    for fb in feedback:
        v = fb["verdict"]
        if v not in ("relevant", "not_relevant"):
            continue
        totals[v] += 1
        if fb["message_text_masked"] is None:
            totals["no_text"] += 1  # keyword-only уведомления минуют LLM-лог
            continue
        segs = fb["llm_segments"] or fb["rule_segments"] or []
        field = "fb_relevant" if v == "relevant" else "fb_not_relevant"
        for slug in segs:
            stats[slug][field] += 1
    return totals


# ── Отчёт ──

def _pct(num: int, den: int) -> str:
    return f"{100 * num / den:.0f}%" if den else "—"


def render_report(
    stats: dict, verdict_counts: dict, fb_totals: dict,
    corpus_sizes: dict, unmatched: list[dict],
    recovered: list[tuple[dict, list[str]]],
) -> str:
    lines = [
        f"# Eval-отчёт качества матчинга — {date.today().isoformat()}",
        "",
        "Скрипт: `tools/eval_matching.py` (read-only к прод-БД/Redis).",
        "",
        "## Корпус",
        "",
        f"- llm_decisions: {corpus_sizes['decisions']}",
        f"- feedback: {corpus_sizes['feedback']}",
        f"- stats:unmatched (сэмпл): {corpus_sizes['unmatched']}",
        "",
        "## Итоги по корпусу (decisions + unmatched, текущий классификатор)",
        "",
        "| Сегмент | Pass 1 | Stop-блок | Pass 3-блок | Матч | Reality-блок | LLM ✅ | LLM ❌ | 👍 | 👎 | Precision (fb) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for slug in sorted(stats, key=lambda s: -stats[s]["matched"]):
        s = stats[slug]
        if not any(s.values()):
            continue
        fb_total = s["fb_relevant"] + s["fb_not_relevant"]
        lines.append(
            f"| {slug} | {s['pass1']} | {s['stop_blocked']} | {s['pass3_blocked']} "
            f"| {s['matched']} | {s['reality_blocked']} | {s['llm_pass']} "
            f"| {s['llm_reject']} | {s['fb_relevant']} | {s['fb_not_relevant']} "
            f"| {_pct(s['fb_relevant'], fb_total)} |"
        )

    fb_rated = fb_totals["relevant"] + fb_totals["not_relevant"]
    lines += [
        "",
        "## LLM-вердикты (из сохранённых решений)",
        "",
        "| Вердикт | Кол-во |",
        "|---|---|",
        *[f"| {v} | {n} |" for v, n in sorted(verdict_counts.items())],
        "",
        "## Precision по feedback (все уведомления)",
        "",
        f"- 👍 relevant: {fb_totals['relevant']}",
        f"- 👎 not_relevant: {fb_totals['not_relevant']}",
        f"- **Precision: {_pct(fb_totals['relevant'], fb_rated)}**",
        f"- без текста в llm_decisions (keyword-only и до-LLM эпоха): {fb_totals['no_text']}",
        "",
        "## Unmatched: восстановленные текущими правилами (кандидаты-FN, закрытые)",
        "",
        f"Из {corpus_sizes['unmatched']} unmatched сейчас матчатся: **{len(recovered)}**",
        "",
    ]
    for entry, segs in recovered[:20]:
        text_short = " ".join(entry.get("text", "").split())[:110]
        lines.append(f"- `@{entry.get('chat')}` → {', '.join(segs)}: {text_short}")

    lines += [
        "",
        f"## Ручная разметка: {MANUAL_SAMPLE} unmatched-сообщений (кандидаты в FN)",
        "",
        "Заполняет владелец: FN = реальный лид, пропущенный классификатором.",
        "",
        "| # | Чат | Текст (обрезан) | FN? (да/нет) | Сегмент |",
        "|---|---|---|---|---|",
    ]
    for i, entry in enumerate(unmatched[:MANUAL_SAMPLE], 1):
        text_short = " ".join(entry.get("text", "").split())[:100].replace("|", "\\|")
        lines.append(f"| {i} | @{entry.get('chat')} | {text_short} | | |")

    lines.append("")
    return "\n".join(lines)


# ── main ──

async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=int, default=1000)
    parser.add_argument("--unmatched", type=int, default=500)
    parser.add_argument("--pg-host", default="127.0.0.1")
    parser.add_argument("--pg-port", type=int, default=5432)
    parser.add_argument("--redis-host", default="127.0.0.1")
    parser.add_argument("--redis-port", type=int, default=6379)
    parser.add_argument("--out", default=None, help="путь отчёта (default: docs/eval/report_YYYY-MM-DD.md)")
    args = parser.parse_args()

    env = _read_env(PROJECT_ROOT / ".env")
    conn = await asyncpg.connect(
        host=args.pg_host, port=args.pg_port,
        user=env["POSTGRES_USER"], password=env["POSTGRES_PASSWORD"],
        database=env["POSTGRES_DB"],
    )
    try:
        compiled, domain_word_map, pass3_skip, keyword_map = (
            await load_classifier_config(conn)
        )
        decisions = await fetch_decisions(conn, args.decisions)
        feedback = await fetch_feedback(conn)
    finally:
        await conn.close()

    redis = Redis(
        host=args.redis_host, port=args.redis_port,
        db=int(env.get("REDIS_DB", "0")), decode_responses=True,
    )
    try:
        unmatched = await fetch_unmatched(redis, args.unmatched)
    finally:
        await redis.aclose()

    stats: dict[str, dict[str, int]] = defaultdict(new_seg_stats)

    corpus_texts = [d["message_text_masked"] for d in decisions if d["message_text_masked"]]
    corpus_texts += [u.get("text", "") for u in unmatched]
    aggregate_corpus(corpus_texts, compiled, pass3_skip, domain_word_map, stats)

    verdict_counts = aggregate_llm(decisions, stats)
    fb_totals = aggregate_feedback(feedback, stats)

    recovered = []
    for u in unmatched:
        result = classify_message(u.get("text", ""), compiled, purchase_segments=pass3_skip)
        if result.matched_segments:
            recovered.append((u, result.matched_segments))

    report = render_report(
        stats, verdict_counts, fb_totals,
        {"decisions": len(decisions), "feedback": len(feedback), "unmatched": len(unmatched)},
        unmatched, recovered,
    )

    out_path = Path(args.out) if args.out else (
        OUT_DIR / f"report_{date.today().isoformat()}.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"segments={len(keyword_map)} decisions={len(decisions)} "
          f"feedback={len(feedback)} unmatched={len(unmatched)} "
          f"recovered={len(recovered)}")
    print(f"report → {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
