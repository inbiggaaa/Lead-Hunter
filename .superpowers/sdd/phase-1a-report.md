# Phase 1A report

## Status

Implemented only Phase 1 items 1–7: localhost admin bind, fail-closed
authentication, proxy-header policy, WebSocket session enforcement, and
server-resolved support chat delivery. CRUD, broadcast, deploy, production,
`docs/SESSION_LOG.md`, and `CLAUDE.md` were not changed by this subtask.

Implementation commit: `cea8852 fix(admin): harden authentication and chat`.

## TDD evidence

### RED

Command:

```text
set -a && source /tmp/lh-stability-ci.env && set +a
../../venv/bin/python -m pytest tests/test_admin_security.py -q
```

Result: `1 failed, 10 passed`. The expected failure was
`test_chat_resolves_telegram_id_and_reuses_bot`: two messages created two Bot
instances (`assert 2 == 1`).

### GREEN

Host command (after the minimum implementation and refactor):

```text
../../venv/bin/python -m pytest tests/test_admin_security.py -q
```

Result: `11 passed`. The host Python 3.14 environment emitted pre-existing
`pytest-asyncio` deprecation warnings.

Authoritative isolated Python 3.11 command:

```text
docker build -t lh-stability-phase1a .
docker run --rm --name lh-stability-phase1a-tests \
  --network lh-stability-net \
  --env-file /tmp/lh-stability-ci.env \
  lh-stability-phase1a \
  python -m pytest tests/test_admin_security.py -q
```

Result: `11 passed in 1.97s`. No Compose command was run.

## Additional verification

- `git diff --check`: passed before commit.
- IDE lint diagnostics for changed Python, TypeScript, and tests: no errors.
- `npm run lint`: exit 0; five pre-existing Fast Refresh warnings in unrelated
  shared UI/auth files.
- `npm run build`: exit 0; Vite warned about the existing bundle size.
- A host full-suite attempt was not a valid gate because the supplied env uses
  Docker DNS names unavailable from macOS. It reported `485 passed`, two
  failures, and 27 connection errors. One failure came from the separate,
  uncommitted Phase 1 deploy test; DB/Redis failures were environment-related.

## Changed files

- `docker-compose.yml`: localhost bind by default with explicit host override.
- `.env.example`: documents `ADMIN_BIND_HOST` and proxy-header trust.
- `app/config.py`: typed `admin_trust_proxy_headers` flag.
- `app/admin/api/auth.py`: constant-time password comparison, trusted-proxy
  opt-in, and Redis fail-closed 503 behavior.
- `app/admin/api/chat.py`: WebSocket session gate, payload validation,
  server-side `telegram_id` lookup, unknown-user rejection, one Bot per
  connection, and deterministic Bot/listener cleanup.
- `admin-panel/src/pages/ChatPage.tsx`: sends only `user_id` and `text`.
- `tests/test_admin_security.py`: focused coverage for items 1–7.

## Self-review

- Confirmed no client `telegram_id` is used by the backend.
- Confirmed an unknown `user_id` creates no `SupportMessage`.
- Confirmed the existing plain-text Telegram body is unchanged and no
  `parse_mode` was added.
- Confirmed Redis errors cannot establish an authenticated session.
- Confirmed listener cancellation and Bot session close happen in the
  WebSocket cleanup path.
- Confirmed no broad scope changes to CRUD, broadcast, or deploy were staged
  in the Phase 1A commit.

## Concerns

The worktree contained concurrent uncommitted Phase 1B/deploy changes before
this subtask started. They were not staged, edited, reverted, or committed by
Phase 1A, so the shared worktree is not clean after the Phase 1A commit. A
meaningful full-suite gate should be run after those concurrent changes are
finished and committed, using the isolated Docker network.
