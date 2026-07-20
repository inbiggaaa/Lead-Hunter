# Production / боевой релиз checklist

## Pre-launch

- [ ] Precision ≥ 50% for 14 days on beta cohort
- [ ] Fresh recall sample labeled; no regression vs beta baseline
- [ ] U10 RU/EN matrix closed
- [ ] Admin remains private **or** TLS reverse proxy + secure cookies + trusted proxy
- [ ] GitHub Environment `production` reviewers + `DEPLOY_*` secrets configured
- [ ] Release rehearsal: backup → migrate → approved deploy → live smoke → 30 min FloodWait watch
- [ ] Rollback image digest + DB restore plan written
- [ ] Support/legal/analytics owners named

## Launch day

1. [ ] pg_dump + offsite copy
2. [ ] Approved GitHub deploy (or manual `scripts/deploy.sh`)
3. [ ] Health: bot/worker/admin Up; alembic head expected
4. [ ] Live smoke: search → lead notification paid format
5. [ ] 30-minute log watch: no FloodWait/ERROR/CRITICAL
6. [ ] Segmented `/broadcast` announcement only (not blast-all)

## First 48h / 14d

- [ ] Intensified monitoring first 48h
- [ ] Daily product report for 14 days
- [ ] Rollback only via pre-tested image/DB plan

## Production gate sign-off

| Item | Owner | Date | Pass |
|---|---|---|---|
| Quality 50% |  |  |  |
| Security |  |  |  |
| Deploy+rollback |  |  |  |
| Support/legal |  |  |  |
| Go live |  |  |  |
