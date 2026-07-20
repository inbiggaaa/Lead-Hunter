# Payment E2E checklist (Stars + CryptoBot)

> **Статус 20.07.2026:** live E2E **пропущен** по решению владельца
> (сначала продукт без шлюза; платежи — отдельным этапом).
> Чек-лист сохранён для будущего прогона.

Run on a dedicated test Telegram account. Do **not** skip idempotency cases.

## Pre-flight

- [ ] Prod/staging `.env`: prices 9/19/39, `CRYPTOBOT_API_TOKEN` set if crypto enabled
- [ ] `alembic current` includes `pay_idempotency01`
- [ ] Bot + worker healthy; admin reachable (public port until TLS — owner decision)
- [ ] Test user starts on Free (or fresh `/start`)

## Stars — Start $9 (or minimal invoice)

1. [ ] Open Тариф → Start → 1 month → Stars invoice arrives
2. [ ] Pre-checkout succeeds; payment completes
3. [ ] DB: `users.plan=start`, `plan_expires_at` ~+30d, `subscriptions.payment_status=paid`
4. [ ] `provider_charge_id` set and UNIQUE
5. [ ] Cache invalidated: paid lead shows contacts / reply buttons
6. [ ] Replay / duplicate charge_id → **no** second extension (`activate_paid_subscription` returns existing)
7. [ ] Referral path (optional): invitee pays once → referrer +10 days; second invitee in same month beyond cap → status `capped`

## CryptoBot

1. [ ] Create invoice → pending key in Redis `pay:pending`
2. [ ] Pay invoice → `payment_checker` activates within ~5–15s
3. [ ] User gets `payment_success` message
4. [ ] Expired invoice → user notified with retry button; pending removed
5. [ ] Duplicate paid poll → no double activation

## Expiry / support

1. [ ] Force near-expiry → −2/−1 reminders fire
2. [ ] At expiry → instant Free, contacts hidden
3. [ ] Document refund/support response template for owner

## Sign-off

| Item | Owner | Date | Pass |
|---|---|---|---|
| Stars E2E |  |  |  |
| CryptoBot E2E |  |  |  |
| Idempotency |  |  |  |
