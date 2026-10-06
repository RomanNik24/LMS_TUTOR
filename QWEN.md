# Qwen Project Instructions

## 0. Purpose

This repository contains the MY_LMS project.

The authoritative product specification is the documentation in `docs/`.

The goal of every code change is:

> **Bring the implementation into exact compliance with the current project specification without inventing functionality, changing the approved architecture, or mixing unrelated tasks.**

The repository is built from scratch according to the architecture defined in `docs/01`–`docs/12`. There is no legacy codebase.

The most important rule is:

> **One user request = one clearly defined task. Complete only that task. Do not start the next task automatically.**

---

# 1. Rules of the documentation

## 1.1. Documentation is the source of truth

The project documentation is normative. Read the relevant documents from `docs/` before any change:

```text
docs/00_README_INDEX.md
docs/01_project_overview.md
docs/02_tech_stack.md
docs/03_architecture.md
docs/04_database_schema.md
docs/05_bot_logic_and_fsm.md
docs/06_agent_rules.md
docs/07_design.md
docs/08_api_spec.md
docs/09_security_and_privacy.md
docs/10_deployment_and_ops.md
docs/11_roadmap.md
docs/12_frontend_guide.md
```

## 1.2. Priority when documents conflict

1. `docs/07_design.md` — visual design and UI tone.
2. `docs/01_project_overview.md` — business rules and product behavior.
3. `docs/04_database_schema.md` — data model.
4. `docs/08_api_spec.md` — API contract.
5. Other documentation.

If two documents conflict:

> **Do not invent a solution. Stop the implementation and report the contradiction to the owner.**

Do not silently choose one interpretation. Contradictions discovered in the documentation are tracked; unresolved ones are recorded in `docs/adr/OPEN_QUESTIONS.md`.

## 1.3. Do not invent functionality

Never introduce functionality that is not specified. Do not add new business rules, entities, roles, screens, API endpoints, background jobs, dependencies, authentication mechanisms, infrastructure, or storage unless explicitly requested by the owner or explicitly required by the documentation.

Do not "improve" the product by adding features that seem useful.

## 1.4. Do not change the approved stack and architecture

The technology stack and the layered architecture are approved in `docs/02`, `docs/03` and the ADR decisions in `docs/adr/`. Do not change them and do not add dependencies without agreement.

---

# 2. One task at a time

The owner gives tasks incrementally. For each task:

1. Identify the exact requested scope.
2. Inspect all files affected by that scope.
3. Implement only that scope.
4. Add or update tests for that scope.
5. Run the relevant checks.
6. Review the git diff.
7. Commit the task.
8. Stop.

Do NOT continue automatically into the next roadmap stage. If the task exposes an unrelated problem, do not fix it — mention it in the final report under "Additional issue noticed".

If a change modifies business rules, data model, permissions, financial calculations, scheduling or homework rules, authentication, or notifications, first verify the corresponding documentation. If the requested behavior is not reflected in the documentation, do not invent the specification: the documentation must be updated or the owner must explicitly define the behavior.

Every behavior change must include appropriate tests. Do not remove a test simply because the current implementation fails it; first determine whether the implementation is wrong or the test is based on obsolete behavior.

---

# 3. Agent roles and task cycle

Two agent roles are used:

- **CODE** — writes and changes code and documentation files.
- **TERM** — executes terminal commands (git, uv, pnpm, docker, and other tooling).

Standard task cycle:

```text
START → CODE → FINISH → owner review → merge → stop
```

After FINISH the owner reviews the result before it is merged. Do not merge automatically.

The collaboration process (branches / Pull Requests vs. direct commits to `main`) is defined separately by the owner and may change. Follow the owner's current instructions. Do not codify a workflow that the owner has not confirmed.

---

# 4. Git and commits

## 4.1. Commit messages

Commit messages must use Conventional Commits:

```text
feat: ...
fix: ...
refactor: ...
test: ...
docs: ...
chore: ...
```

Commit subjects are written in English. One task normally results in one focused commit. Do not mix unrelated fixes into the same commit.

## 4.2. Never rewrite published history

Do not use `git push --force`, `git push --force-with-lease`, `git reset --hard`, or otherwise rewrite published history unless the owner explicitly requests the operation and understands the consequences. Do not delete or rewrite existing commits merely to make history cleaner.

## 4.3. Diff review before commit

Before committing, always inspect:

```bash
git status
git diff --check
git diff
```

Confirm: no unrelated changes, `.gitignore` is NOT in the diff (see chapter 18), no secrets, no generated junk, no debug code, no temporary files, no accidental deletion, no accidental formatting of unrelated files.

---

# 5. Architecture and layers

The backend uses a layered architecture:

```text
API / Bot / Worker
        ↓
    Services
        ↓
  Repositories
        ↓
      DB
```

## 5.1. API layer (`src/api/`)

May: parse requests, use Pydantic schemas, resolve the authenticated user, check basic route-level permissions, call services, translate domain errors to HTTP responses.

Must NOT: contain business logic, perform SQLAlchemy queries directly, manipulate database models directly when a service exists, duplicate service logic.

## 5.2. Bot layer (`src/bot/`)

May: receive Telegram events, parse commands, obtain the authenticated user through middleware, call services, render bot messages, handle FSM interactions.

Must NOT: contain business rules, contain database queries, implement financial calculations, implement scheduling logic, directly manipulate SQLAlchemy, duplicate service logic. The bot is a transport/interface layer.

## 5.3. Worker layer (`src/worker/`)

May: trigger scheduled jobs, call services, enqueue/dispatch notifications.

Must NOT: contain business rules that belong in services, duplicate scheduling logic, directly implement domain transitions that belong to services. The worker is a scheduler/execution layer.

## 5.4. Services (`src/services/`)

Contain business logic. Services may: call repositories, validate business rules, manage transactions, create audit records, create notification outbox records, invoke approved abstractions such as `Notifier` and `FileService`.

Services must NOT import `fastapi` or `aiogram` and must not know about HTTP status codes or Telegram event objects. A service layer method should normally implement one business operation.

## 5.5. Repositories (`src/repositories/`)

Contain database access only. Repositories may: `select`, `insert`, `update`, `delete`, `flush`.

Repositories must NOT: commit transactions, implement business rules, decide permissions, send Telegram messages, create HTTP responses. Complex queries must have explicit, meaningful repository methods.

---

# 6. Transactions

Transactions follow Unit of Work principles:

```text
request/event/task
       ↓
service
       ↓
repositories
       ↓
service commit
```

Rules:

- Repository does not call `commit()`; repository may call `flush()`.
- **Commit is made only by the service layer.**
- A business operation should normally be one service transaction.
- On failure the transaction is rolled back.
- External side effects (messages, S3 writes) must happen after commit or through the notification/outbox mechanism.
- Do not introduce random `session.commit()` calls inside routers, bot handlers or repositories.

---

# 7. Database rules

The database must follow `docs/04_database_schema.md`.

Target database:

```text
PostgreSQL 16+
SQLAlchemy 2.x async
Alembic
```

Use: `BIGINT` identifiers where specified, `TIMESTAMPTZ` for timestamps, `DATE` for dates, `JSONB` where specified, the chosen enum/check approach, required indexes, foreign keys, uniqueness constraints and PostgreSQL-specific constraints.

The enum strategy is `VARCHAR` + `CHECK` (SQLAlchemy `Enum(native_enum=False)`) — see `docs/adr/0003`. Core values live in `src/core/enums.py`.

SQLite `create_all()` tests are NOT sufficient when behavior depends on PostgreSQL features. For PostgreSQL-specific functionality use real PostgreSQL integration tests.

Any database schema change requires an Alembic migration. Every migration must: have a correct `upgrade()`; have a working `downgrade()` where rollback is applicable; preserve existing data unless the task explicitly defines a migration; be tested against PostgreSQL.

Never modify an old migration that has already been applied in shared environments. Create a new migration instead.

Migrations live in `src/db/migrations/`; the Alembic configuration file `alembic.ini` is at the repository root (see `docs/adr/0002`).

---

# 8. Time and date

The application uses UTC.

Do not use naive datetimes for business logic. Do not use `datetime.utcnow()` or `datetime.now().replace(tzinfo=None)`; use the project's centralized time utilities (`src/core/timeutils.py`).

Database timestamps must use the target UTC model. User-visible times must be converted using the user's IANA timezone. Scheduling code must correctly account for timezone conversion, daylight saving time where applicable, day boundaries, ISO weeks and UTC storage.

---

# 9. Identity and authentication

Target authentication:

```text
Telegram initData / one-time invitation link
        ↓
server validation
        ↓
Redis server-side session
        ↓
HttpOnly cookie
        ↓
current_user
```

Rules:

- Password authentication is not used.
- `initData` is validated on the server (HMAC, age ≤ 24 hours). Never trust a raw Telegram ID supplied by the client; authorization data is derived from the server-side record.
- Sessions are server-side (Redis), revocable, stored in an `HttpOnly; Secure; SameSite=Lax` cookie.
- Invitation and web-login tokens are stored only as SHA-256 hashes, are single-use and have a TTL.
- Sessions are removed on logout, on user archival, on `telegram_id` change and on role change.

---

# 10. Security rules

Security is enforced on the server. Never rely on frontend button hiding for authorization.

Required principles:

- server-side RBAC;
- IDOR protection;
- student isolation;
- manager/owner separation;
- secure cookies;
- CSRF protection (`SameSite=Lax`, `Origin` and `X-Requested-With` checks on mutating requests);
- rate limiting;
- secure file handling (size, MIME, extension checks; server-generated storage keys; private bucket; presigned URLs);
- audit logging;
- no sensitive values in logs.

For unauthorized access to resources that the user must not know exist, return the documented `404`.

---

# 11. Role model and privacy

Target roles: `owner`, `manager`, `student`. An account is created only through a one-time invitation link; one account = one `telegram_id`.

Students must never receive:

- lesson price;
- price snapshot;
- financial data;
- teacher notes;
- billable flags;
- other students' information.

Managers must never receive owner-only financial information. Use different response schemas for student, manager and owner rather than hiding fields after the fact.

---

# 12. API rules

The target REST API is defined in `docs/08_api_spec.md` under the base path `/api/v1`.

For each endpoint:

- define a Pydantic request schema;
- define a Pydantic response schema;
- define tags, summary and a stable `operation_id`;
- define documented status codes;
- use the common error envelope;
- enforce required permissions;
- use pagination where specified.

Error envelope:

```json
{
  "error": {
    "code": "example_code",
    "message": "Human-readable message",
    "details": {}
  }
}
```

Do not return ad-hoc `{"detail": ...}` for documented business/API errors.

List endpoints follow the pagination contract `limit / offset / total / items` (default `limit = 50`, maximum `limit = 200`).

FastAPI OpenAPI is the single source for frontend API types. The frontend must not manually duplicate backend response types and must not edit the generated `frontend/src/api/schema.d.ts` by hand. When the API contract changes, regenerate the frontend types and update frontend usage and tests.

---

# 13. Frontend rules

## 13.1. Stack and style

The target frontend is React + TypeScript (strict) built with Vite. Use feature-oriented architecture (`frontend/src/features/<name>/`, common components in `components/common/`, basic UI in `components/ui/`). One component normally has one file; use named exports unless a lazily loaded page requires a `default` export.

Forbidden in TypeScript:

```text
any
@ts-ignore
@ts-nocheck
implicit any
```

Type assertions using `as` are allowed only when necessary and must have a comment explaining why they are safe. Remember that `array[0]` may be undefined because `noUncheckedIndexedAccess` is enabled.

## 13.2. Data fetching

Server data must be managed through TanStack Query. Do not load server data using arbitrary `useEffect` calls. API requests belong in `features/*/api.ts` through the shared API client; direct `fetch` is allowed only where the documented file upload flow requires it. Do not introduce Redux, Zustand or another global state manager.

## 13.3. No business logic on the frontend

The frontend must NOT calculate domain rules: grading conversion, exam scoring, financial calculations, deadline expiration rules, homework extension limits, billable logic, price snapshots, authorization decisions. The backend is authoritative. The frontend only displays server results, sends user actions and renders loading/error/empty/success states.

Any user-facing frontend text must be stored in:

```text
frontend/src/lib/texts.ts
```

Backend and bot user-facing text must be stored in:

```text
src/core/texts.py
```

Do not scatter Russian product copy throughout components. Visual style and text tone follow `docs/07_design.md`; colors, spacing and typography come only from tokens in `frontend/src/styles/tokens.css`. Hex colors in components are forbidden.

## 13.4. Frontend security

- No secrets in frontend code or `VITE_*` variables.
- `dangerouslySetInnerHTML` is forbidden. User-generated content is rendered as text only.
- External links open only with `https://` and `rel="noopener noreferrer"`.
- `initData`, tokens and personal data must not reach the console or Sentry.
- Telegram integration is isolated in `frontend/src/lib/telegram.ts`; the rest of the code must not import the Telegram SDK.

---

# 14. Bot and FSM rules

The bot is a transport/interface layer. Target commands and scenarios are defined in `docs/05_bot_logic_and_fsm.md`. The bot must not contain duplicate business logic.

FSM uses Redis and is used only for short-lived conversational workflows (e.g., `ConfirmRelinkState`, `LogoutState`). FSM data must not become a substitute for persistent business state that belongs in PostgreSQL.

---

# 15. Notifications architecture

Target notifications use an outbox:

```text
business action
      ↓
notifications row
      ↓
TaskIQ scheduler/worker
      ↓
Notifier
      ↓
TelegramNotifier
```

Do not send Telegram messages directly from domain services. Do not introduce `Bot.send_message()` into business logic. Notification state is persisted in the database and supports deduplication, retries, attempts, quiet hours, `bot_blocked`, `sent`, `failed`, `skipped`.

---

# 16. Worker rules

Target background stack: TaskIQ with a Redis broker, a scheduler (strictly one instance) and a worker. Worker jobs must match the schedule and semantics documented in `docs/03`, `docs/05` and `docs/10`.

---

# 17. File handling

Target storage is S3-compatible private storage using the approved async S3 client. Files must:

- be stored under server-generated IDs/keys;
- never trust user-provided storage paths;
- validate size, MIME type and extension against the allowed formats;
- enforce per-assignment limits;
- be private and accessed through presigned URLs.

Do not expose `/uploads` publicly. Do not store production user files in Git.

---

# 18. Repository hygiene and `.gitignore`

Never commit:

```text
__pycache__/
*.pyc
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
node_modules/
dist/
coverage/
.env
.env.local
user uploads
temporary files
logs
```

Generated files may be committed only when explicitly required by the repository rules (example: `frontend/src/api/schema.d.ts` when the specification requires a versioned contract).

## 18.1. Never modify `.gitignore`

`.gitignore` is the single source of truth that keeps secrets and junk out of the repository.

It must NOT be created, modified, renamed, deleted, truncated, regenerated or restored by an agent. Never run:

```bash
git checkout <ref> -- .gitignore
git restore .gitignore
git clean -xdf
rm .gitignore
```

Never write ignore rules into it and never "tidy" it by rewriting it from an older revision. This file is owned exclusively by the owner.

If `.gitignore` appears broken, truncated or empty: do not fix it, do not restore it from any commit. Report it in the final report under "Remaining" and stop touching the file. The owner restores it.

The only permitted interaction is verification:

```bash
git check-ignore -v <path>
```

Reading the file is allowed. Writing it is not.

---

# 19. Secrets

Never hardcode secrets. Never commit real values for:

```text
BOT_TOKEN
WEBHOOK_SECRET
SESSION_SECRET
DATABASE_PASSWORD
REDIS credentials
S3 credentials
SENTRY DSN/secret
```

Use environment variables. Real values live only in `.env.local` (never in Git) and in GitHub Secrets. Update `.env.example` when a new configuration variable becomes part of the approved architecture.

---

# 20. Logging

Never use `print(...)` in committed code; use the configured logger. Never log passwords, session IDs, invitation tokens, web-login tokens, Telegram `initData`, authorization headers, secrets or personal data unnecessarily. Error logs should include identifiers only when necessary and avoid PII. Use `logger.exception(...)` for unexpected errors at service/application boundaries.

---

# 21. Dependencies

Do not add a dependency casually. Before adding a library: verify the documentation or task requires it; prefer an existing dependency; check compatibility with the target stack; update lock files; run the relevant tests and lint/type checks. Do not introduce alternative frameworks.

---

# 22. Code style

## 22.1. Backend

Target: Python 3.11, Ruff (lint + format), MyPy strict. Type hints are mandatory. Docstrings in Google style. Functions are short and have a single responsibility; services are classes with dependencies injected through the constructor. No magic values: constants and enums live in dedicated modules.

Identifiers, file names and commit messages: **English**. Comments and docstrings: **Russian**.

Blocking I/O is forbidden in the async context. Use `httpx`, `asyncpg`, and the approved async S3 client; CPU-heavy operations are delegated with `asyncio.to_thread`. SQLAlchemy uses 2.0 syntax only (`select()`, `AsyncSession`, eager load via `selectinload`/`joinedload`).

## 22.2. Frontend

Use TypeScript strict, ESLint, Prettier. Identifiers in English, user-facing text in Russian. Avoid clever abstractions; prefer obvious code over compact code.

---

# 23. Testing

## 23.1. Backend

Use `pytest`, `pytest-asyncio`, `testcontainers` (PostgreSQL, Redis). Every business-logic function has a test. Mandatory for the MVP: permission tests (including negative cases), schedule generation (idempotency, horizon, template edits), lesson overlap prevention, deadline extension limits, `expired` transitions, score conversion (all four exam scales), price snapshot, earnings formulas, quiet hours and notification deduplication, invitations (single-use, TTL, relink), sessions and `initData` validation, and a contract test that student/manager response schemas do not contain forbidden fields.

External services (Telegram, S3) are mocked. Time is controlled (`time-machine`). For PostgreSQL-specific behavior use real PostgreSQL integration tests, not only SQLite.

## 23.2. Frontend

Use Vitest, Testing Library, MSW. Mandatory coverage: `lib/datetime.ts`, API error/unwrap handling, role-guarded rendering, forms with boundary values, the student homework screen states, and absence of financial data on student/manager screens. Playwright comes after the core MVP.

## 23.3. Security regression tests

Whenever changing authentication, permissions, file handling or sensitive data, add negative tests covering at least: unauthenticated access, wrong role, wrong student, foreign resource, expired resource, archived user, missing CSRF headers, wrong `Origin`, invalid token, replayed token, rate limit.

---

# 24. Quality checks before commit

Run the checks relevant to the changed area.

Backend:

```bash
uv sync --frozen
ruff check .
ruff format --check .
mypy --strict src
pytest
```

Frontend:

```bash
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test --run
pnpm build
```

A unified runner exists as `scripts/check.py` (`uv run python scripts/check.py`). The same checks run in the CI workflow (`.github/workflows/ci.yml`).

For database changes additionally verify against PostgreSQL:

```bash
alembic upgrade head
alembic downgrade <revision>
```

Do not claim a migration works if it has only been inspected statically. For API changes: run the backend, generate OpenAPI, verify the documented routes and schemas, regenerate frontend types, and verify no unexpected schema drift.

---

# 25. Definition of Done

A task is done only when:

- Backend: `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` are green.
- Frontend: `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build` are green; `schema.d.ts` is up to date.
- A migration exists, applies and rolls back (`upgrade`/`downgrade`).
- No hardcoded secrets; `.env.example` updated when configuration changed.
- Permissions are enforced on the server and covered by tests.
- Student/manager response schemas contain no private fields.
- Texts are collected in `texts.py` / `texts.ts`.
- UI states (loading, error, empty, submitting) are handled.
- No blocking I/O and no N+1 queries in the added code.
- Documentation is updated if rules, data or endpoints changed.
- Only what is described in the documentation was implemented.

An agent must NEVER: invent scenarios, fields, roles or statuses; add dependencies or change the stack without agreement; write SQL outside `repositories/` or call `commit()` in repositories; change exam scales in code; return financial data to students or managers; duplicate business logic in the frontend; use `any`, `@ts-ignore`, `dangerouslySetInnerHTML` or `localStorage` for sensitive data.

---

# 26. Stop conditions

STOP and report to the owner when:

1. The documentation contains a contradiction.
2. The requested behavior would violate security requirements.
3. A migration would cause destructive data loss without an approved migration plan.
4. The requested implementation requires changing the approved technology stack or adding a dependency.
5. A required external credential or service is unavailable.
6. A task cannot be safely completed without deciding an unspecified business rule.
7. The current branch contains unrelated uncommitted changes that would be overwritten or mixed into the task.
8. A task appears to require creating, changing or restoring `.gitignore` — report it instead of doing it (see 18.1).
9. The same check category has failed three times in a row for the current task ("three red circles") — stop and report instead of making further guesses.

Do not guess in these situations.

---

# 27. Do not hide failures

Never swallow exceptions silently, skip failing tests without explanation, disable lint/type checks to make CI green, weaken security checks to make tests pass, remove tests merely because they fail, or change requirements to fit the current implementation.

When something fails: identify, explain, fix, or explicitly report.

---

# 28. Task completion report

After completing a task, the final response must contain:

## Changed

A concise list of what was implemented.

## Files

A list of important modified/created/deleted files.

## Tests

Exactly which checks were run and their result:

```text
pytest: N passed
ruff check: passed
mypy: passed
```

## Commit

```text
<commit SHA>
<commit message>
```

## Remaining

Only issues directly discovered but intentionally left outside the task scope. Do not claim that the whole project is fixed unless the user explicitly asked for a full-project task and all relevant checks actually passed.

---

# 29. Final principle

The quality criterion for this repository is not "the code works somehow". The criterion is:

> **The implementation, database, API, security model, bot, worker, frontend and infrastructure match the approved MY_LMS specification.**

Always prefer:

```text
correct architecture  over  quick patch
explicit code         over  clever code
documented behavior   over  assumption
focused task          over  large refactor
verified result       over  "it should work"
```

And most importantly:

> **Complete only the task requested by the owner. Stop after that task is verified and committed.**
