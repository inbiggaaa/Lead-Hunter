# Paid beta MVP — 14-day controlled launch

Audience: 20–30 users in 2–3 high-quality segments. Weak segments quarantined.

## Entry criteria (all required)

- [ ] Precision ≥ 35% on current-catalog feedback (docs/launch/quality_gates.md)
- [ ] Sentry events from bot+worker+admin
- [ ] Daily backup cron + restore drill recorded
- [ ] Owner assigned to daily monitoring

> **Платежи / шлюз:** live Stars/CryptoBot E2E и оферта для аудита шлюза —
> **пропущены** до отдельной команды владельца (не блокер текущей разработки).

> **Отложено (не блокер этой итерации):** admin bind 127.0.0.1 / unauth WS reject /
> ban-filter / hardened deploy.sh — вернуться отдельной задачей до публичного релиза.

## Daily monitoring (14 days)

Track: activation, first-value time, 👍/👎 precision, latency, trial→paid,
churn/refunds, queue/DLQ, LLM cost, FloodWait.

## Stop-the-line

- Security incident
- Any FloodWait
- Payment duplication
- Fail-open >20%/hour
- Precision <35%
- Queue loss / backup failure

## Exit / go-no-go

| Gate | Target | Actual | Pass |
|---|---|---|---|
| Activated users | ≥10 |  |  |
| Real payments | ≥3 |  |  |
| Precision | ≥35% |  |  |
| P0 incidents | 0 |  |  |
| Payment success | ≥95% |  |  |
| Owner decision | go / no-go |  |  |
