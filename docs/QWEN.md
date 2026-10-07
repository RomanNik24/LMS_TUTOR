# Qwen Project Instructions

> ⚠ **Устарело.** Этот файл — исходник режима «миграция legacy» (T0.04). Действующие правила
> для агентов лежат в корневом [`QWEN.md`](../QWEN.md) (чистая сборка, одна рабочая ветка,
> PR сразу в `main`). При расхождениях верен корневой файл; legacy-разделы (Flet, Arq, JWT)
> и правила веток «на каждую задачу» здесь не применяются.

## 0. Purpose

This repository contains the MY_LMS project.

The authoritative product specification is the documentation in `docs/`.

The goal of every code change is:

> **Bring the implementation into exact compliance with the current project specification without inventing functionality, changing the approved architecture, or mixing unrelated tasks.**

The repository is being migrated from a legacy implementation to the architecture defined in `docs/01`–`docs/12`.

Because the project is being corrected incrementally, the most important rule is:

> **One user request = one clearly defined task. Complete only that task. Do not start the next task automatically.**

---

# 1. Mandatory rules before any change

Before modifying anything, ALWAYS:

1. Read this file completely.
2. Read the relevant documentation from `docs/`.
3. For architecture, API, database, security, frontend, bot or deployment changes, read all directly related documents.
4. Inspect the current repository state.
5. Run:

   ```bash
   git status
   ```
6. Run:

   ```bash
   git fetch origin
   ```
7. Verify the current `origin/main`.
8. Compare the current working tree against `origin/main`.
9. Determine exactly which files and components are relevant to the requested task.
10. Do not modify unrelated files.
11. Never modify `.gitignore` (see 44.1).

Never assume that an old Qwen branch is current.

`origin/main` is the authoritative source for the starting point of every new task.

---

# 2. Git workflow

## 2.1. Never work directly on `main`

Never modify `main` directly.

Every task must be performed on a separate branch created from the latest `origin/main`.

Recommended branch names:

```text
feature/<name>
fix/<name>
refactor/<name>
chore/<name>
test/<name>
docs/<name>
```

Example:

```bash
git fetch origin
git checkout -b fix/telegram-init-data origin/main
```

---

## 2.2. One task = one branch

Every independent task gets its own branch.

Do not reuse an old feature/fix branch for a new unrelated task.

If the user explicitly continues the same task, continuing the same branch is acceptable only when its history and working tree are still clean and the branch is clearly associated with that task.

---

## 2.3. Never rewrite history

Never use:

```bash
git push --force
git push --force-with-lease
git reset --hard
```

unless the user explicitly requests the operation and understands the consequences.

Do not rewrite published history.

Do not delete or rewrite existing commits merely to make the history cleaner.

Do not merge Pull Requests automatically.

Do not force-push branches.

---

## 2.4. Normal workflow

```text
origin/main
   ↓
new task branch
   ↓
inspect relevant code
   ↓
implement ONE task
   ↓
write/update tests
   ↓
run checks
   ↓
review diff
   ↓
commit
   ↓
push branch
   ↓
Pull Request
   ↓
human review
   ↓
merge into main
```

---

# 3. Main is authoritative

`main` is the authoritative project branch.

Before every new task:

```bash
git fetch origin
git status
```

Then create the task branch from the latest:

```bash
git checkout -b <branch-name> origin/main
```

Do not assume a local branch is current.

Do not assume an old Qwen-generated implementation is correct merely because it already exists.

---

# 4. Documentation is the source of truth

The project documentation is normative.

Read:

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

Priority when documents conflict:

1. `docs/07_design.md` — visual design and UI tone.
2. `docs/01_project_overview.md` — business rules and product behavior.
3. `docs/04_database_schema.md` — data model.
4. `docs/08_api_spec.md` — API contract.
5. Other documentation.

If two documents conflict:

> **Do not invent a solution. Stop the implementation and report the contradiction to the owner.**

Do not silently choose one interpretation.

---

# 5. Do not invent functionality

Never introduce functionality that is not specified.

Do not add:

* new business rules;
* new entities;
* new roles;
* new screens;
* new API endpoints;
* new background jobs;
* new dependencies;
* alternative authentication mechanisms;
* alternative infrastructure;
* alternative storage;
* alternative frontend frameworks;

unless explicitly requested by the owner or explicitly required by the documentation.

Do not "improve" the product by adding features that seem useful.

---

# 6. Work strictly one task at a time

The owner will give tasks incrementally.

For each task:

1. Identify the exact requested scope.
2. Inspect all files affected by that scope.
3. Implement only that scope.
4. Add or update tests for that scope.
5. Run the relevant checks.
6. Review the git diff.
7. Commit the task.
8. Stop.

Do NOT continue automatically into the next roadmap stage.

Example:

If the task is:

```text
Fix Telegram initData validation.
```

Do not additionally:

* rewrite the whole authentication system;
* migrate the database;
* rewrite the frontend;
* replace the worker;
* refactor unrelated repositories.

Those are separate tasks.

---

# 7. If the task exposes another bug

When working on a task, another problem may become visible.

Use this rule:

### Critical dependency

If the discovered issue makes the current task impossible or unsafe, fix the minimum required dependency or report it before proceeding.

### Independent issue

If the discovered issue is unrelated to the current task:

> Do not fix it.

Mention it in the final report as:

```text
Additional issue noticed:
<short description>
Not changed because it is outside the current task scope.
```

Do not expand the task silently.

---

# 8. Before changing business rules

If a change modifies:

* data model;
* business logic;
* permissions;
* status transitions;
* financial calculations;
* scheduling rules;
* homework rules;
* authentication;
* notifications;

then first verify the corresponding documentation.

If the requested behavior is not reflected in the documentation:

> Do not invent the specification.

The documentation must be updated or the owner must explicitly define the behavior.

---

# 9. Architecture rules

The project uses layered architecture:

```text
API / Bot / Worker
        ↓
    Services
        ↓
  Repositories
        ↓
      DB
```

## 9.1. API layer

`src/api/` may:

* parse requests;
* use Pydantic schemas;
* resolve authenticated user;
* check basic route-level permissions;
* call services;
* translate domain errors to HTTP responses.

`src/api/` must NOT:

* contain business logic;
* perform SQLAlchemy queries directly;
* manipulate database models directly when a service exists;
* duplicate service logic.

---

## 9.2. Bot layer

`src/bot/` may:

* receive Telegram events;
* parse commands;
* obtain authenticated user through middleware;
* call services;
* render bot messages;
* handle FSM interactions.

`src/bot/` must NOT:

* contain business rules;
* contain database queries;
* implement financial calculations;
* implement scheduling logic;
* directly manipulate SQLAlchemy;
* duplicate service logic.

The bot is a transport/interface layer.

---

## 9.3. Worker layer

`src/worker/` may:

* trigger scheduled jobs;
* call services;
* enqueue/dispatch notifications.

`src/worker/` must NOT:

* contain business rules that belong in services;
* duplicate scheduling logic;
* directly implement domain transitions that belong to services.

The worker is a scheduler/execution layer.

---

## 9.4. Services

`src/services/` contains business logic.

Services may:

* call repositories;
* validate business rules;
* manage transactions;
* create audit records;
* create notification outbox records;
* invoke approved abstractions such as `Notifier` and `FileService`.

Services must NOT import:

```text
fastapi
aiogram
flet
react
```

Services must not know about HTTP status codes or Telegram event objects.

---

## 9.5. Repositories

`src/repositories/` contains database access only.

Repositories may:

```text
select
insert
update
delete
flush
```

Repositories must NOT:

* commit transactions;
* implement business rules;
* decide permissions;
* send Telegram messages;
* create HTTP responses.

Complex queries must have explicit, meaningful repository methods.

---

# 10. Transaction rules

Transactions follow Unit of Work principles.

The intended flow is:

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

* Repository does not call `commit()`.
* Repository may call `flush()`.
* A business operation should normally be one service transaction.
* On failure, transaction is rolled back.
* External side effects must happen after commit or through the notification/outbox mechanism.

Do not introduce random `session.commit()` calls inside routers or repositories.

---

# 11. Database rules

The database must follow `docs/04_database_schema.md`.

Target database:

```text
PostgreSQL 16+
SQLAlchemy 2.x async
Alembic
```

Use:

* `BIGINT` identifiers where specified;
* `TIMESTAMPTZ` for timestamps;
* `DATE` for dates;
* `JSONB` where specified;
* target enums/check constraints;
* required indexes;
* required foreign keys;
* required uniqueness constraints;
* required PostgreSQL-specific constraints.

SQLite `create_all()` tests are NOT sufficient when behavior depends on PostgreSQL features.

For PostgreSQL-specific functionality, use real PostgreSQL integration tests.

---

# 12. Migration rules

Any database schema change requires an Alembic migration.

Every migration must:

1. have a correct `upgrade()`;
2. have a working `downgrade()` when rollback is applicable;
3. preserve existing data unless the task explicitly defines a migration;
4. be tested against PostgreSQL.

Never modify an old migration that has already been applied in shared environments unless the owner explicitly requests history rewriting.

Create a new migration instead.

---

# 13. Time and date rules

The application uses UTC.

Do not use naive datetimes for business logic.

Do not use:

```python
datetime.utcnow()
```

Do not use:

```python
datetime.now().replace(tzinfo=None)
```

Use the project's centralized time utilities.

Database timestamps must use the target UTC model.

User-visible times must be converted using the user's IANA timezone.

Scheduling code must correctly account for:

* timezone conversion;
* daylight saving time where applicable;
* day boundaries;
* ISO weeks;
* UTC storage.

---

# 14. Identity and authentication

Target authentication is:

```text
Telegram initData
        ↓
server validation
        ↓
Redis server-side session
        ↓
HttpOnly cookie
        ↓
current_user
```

Do not reintroduce password authentication.

Do not use `initDataUnsafe` for authorization.

Do not trust a raw Telegram ID supplied by the client.

Do not store raw invitation/web-login tokens in the database.

Store only hashes.

Sessions must be revocable server-side.

---

# 15. Security rules

Security is enforced on the server.

Never rely on frontend button hiding for authorization.

Required principles:

* server-side RBAC;
* IDOR protection;
* student isolation;
* manager/owner separation;
* secure cookies;
* CSRF protection;
* rate limiting;
* secure file handling;
* audit logging;
* private storage;
* no sensitive values in logs.

For unauthorized access to resources that the user must not know exist, return the documented `404`.

---

# 16. Role model

Target roles are:

```text
owner
manager
student
```

Do not reintroduce:

```text
admin
```

unless the documentation is changed first.

Role rules are:

```text
student
manager
owner
```

with different DTOs and permissions.

Students must never receive:

* lesson price;
* price snapshot;
* financial data;
* teacher notes;
* billable flags;
* other students' information.

Managers must never receive owner-only financial information.

---

# 17. Legacy functionality rules

This repository contains legacy functionality.

Examples include:

```text
password_hash
JWT auth
balance
debtors
admin role
Flet
Arq
legacy homework model
legacy mock exam model
legacy API paths
```

Do not preserve legacy behavior merely because it already exists.

Do not create hybrid architecture accidentally.

When a roadmap task replaces legacy functionality with the target implementation:

1. implement the target behavior;
2. remove the obsolete legacy path when the task explicitly covers its replacement;
3. update tests;
4. update documentation if the contract changes.

Do not leave two competing implementations active without an explicit reason.

---

# 18. API rules

The target REST API is defined in:

```text
docs/08_api_spec.md
```

Base path:

```text
/api/v1
```

All endpoints must follow the documented contract.

For each endpoint:

* define Pydantic request schema;
* define Pydantic response schema;
* define tags;
* define summary;
* define stable `operation_id`;
* define documented status codes;
* use the common error envelope;
* enforce required permissions;
* use pagination where specified.

Do not invent alternative endpoint names when the specification already defines one.

---

# 19. API errors

The target error format is:

```json
{
  "error": {
    "code": "example_code",
    "message": "Human-readable message",
    "details": {}
  }
}
```

Do not return ad-hoc:

```json
{
  "detail": "..."
}
```

for documented business/API errors.

Distinguish:

```text
400 = business rule violation
401 = unauthenticated
403 = permission denied
404 = not found
409 = state/resource conflict
413 = file too large
415 = unsupported file type
422 = schema validation
429 = rate limited
500 = unexpected internal error
```

---

# 20. API pagination

All documented list endpoints must follow the target pagination contract:

```text
limit
offset
total
items
```

Default:

```text
limit = 50
```

Maximum:

```text
limit = 200
```

Do not return unlimited lists when the API specification requires pagination.

---

# 21. OpenAPI contract

FastAPI OpenAPI is the source for frontend API types.

The frontend must not manually duplicate backend response types.

Target flow:

```text
FastAPI
   ↓
OpenAPI
   ↓
openapi-typescript
   ↓
schema.d.ts
   ↓
openapi-fetch
```

Whenever an API contract changes:

1. update backend schemas;
2. update API implementation;
3. regenerate frontend types;
4. update frontend usage;
5. update tests.

Never manually edit generated `schema.d.ts`.

---

# 22. Frontend rules

The target frontend is:

```text
React
TypeScript
Vite
React Router
TanStack Query
Tailwind CSS
shadcn/ui
Recharts
Vitest
Testing Library
MSW
Playwright
```

Do not use Flet for the target frontend.

---

# 23. TypeScript rules

Frontend TypeScript must use strict mode.

Forbidden:

```text
any
@ts-ignore
@ts-nocheck
implicit any
```

Type assertions using `as` are allowed only when necessary and must have a comment explaining why they are safe.

Remember:

```text
array[0]
```

may be undefined because `noUncheckedIndexedAccess` is enabled.

---

# 24. Frontend structure

Use feature-oriented architecture:

```text
frontend/src/
├── api/
├── app/
├── components/
│   ├── common/
│   └── ui/
├── features/
├── lib/
└── styles/
```

One component should normally have one file.

Use named exports unless the component is a lazily loaded page where `default` export is appropriate.

---

# 25. Frontend data fetching

Server data must be managed through TanStack Query.

Do not load server data using arbitrary `useEffect` calls.

API requests belong in:

```text
features/*/api.ts
```

through the shared API client.

Direct `fetch` is allowed only where the documented file upload flow requires it.

Do not introduce Redux, Zustand or another global state manager.

Use:

```text
useState
useReducer
TanStack Query
```

as appropriate.

---

# 26. Frontend business logic

The frontend must NOT calculate domain rules.

Do not implement in React:

* grading conversion;
* exam scoring;
* financial calculations;
* deadline expiration rules;
* homework extension limits;
* billable logic;
* price snapshots;
* authorization decisions.

The backend is authoritative.

Frontend only:

```text
display server result
send user action
show loading/error/success state
```

---

# 27. Frontend text rules

User-facing frontend text must be stored in:

```text
frontend/src/lib/texts.ts
```

Do not scatter Russian product copy throughout components.

Backend/bot text must be stored in:

```text
src/core/texts.py
```

---

# 28. Bot rules

The bot is a transport/interface layer.

Target commands and scenarios are defined in:

```text
docs/05_bot_logic_and_fsm.md
```

Important:

* role-aware menus;
* guest mode;
* invitation flow;
* relink confirmation;
* logout flow;
* `/app`;
* `/web`;
* `/today`;
* `/hw`;
* `/help`;
* catalog;
* notification actions.

The bot must not contain duplicate business logic.

---

# 29. FSM rules

FSM uses Redis.

FSM should only be used for short-lived conversational workflows.

Examples:

```text
ConfirmRelinkState
LogoutState
```

FSM data must not become a substitute for persistent business state.

Do not put business data into FSM when the data belongs in PostgreSQL.

---

# 30. Notifications architecture

Target notifications use an outbox.

Expected flow:

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

Do not send Telegram messages directly from domain services.

Do not introduce `Bot.send_message()` into business logic.

Target notification state is persisted in the database.

Support:

* deduplication;
* retries;
* attempts;
* quiet hours;
* `bot_blocked`;
* `sent`;
* `failed`;
* `skipped`.

---

# 31. Worker rules

Target background stack:

```text
TaskIQ
taskiq-redis
scheduler
worker
```

Do not reintroduce Arq unless the specification is explicitly changed.

Worker jobs must match the schedule and semantics documented in `docs/03`, `docs/05` and `docs/10`.

Do not use "close lesson" logic that invents statuses absent from the target database model.

---

# 32. File handling rules

Target storage:

```text
S3-compatible private storage
```

Use the approved async S3 client.

Files must:

* be stored under server-generated IDs/keys;
* never trust user-provided storage paths;
* validate size;
* validate MIME type;
* validate extension;
* use the target allowed formats;
* enforce per-assignment limits;
* be private;
* be accessed through presigned URLs.

Do not expose `/uploads` publicly.

Do not store production user files in Git.

---

# 33. Logging rules

Never use:

```python
print(...)
```

Use the configured logger.

Never log:

* passwords;
* session IDs;
* invitation tokens;
* web-login tokens;
* Telegram `initData`;
* personal data unnecessarily;
* authorization headers;
* secrets.

Error logs should include identifiers only when necessary and must avoid PII.

Use `logger.exception(...)` for unexpected errors at service/application boundaries.

---

# 34. Dependencies

Do not add a dependency casually.

Before adding a library:

1. Verify the project documentation requires it or the task clearly needs it.
2. Prefer an existing dependency when it already solves the problem.
3. Check compatibility with the target stack.
4. Update dependency lock files.
5. Run the appropriate test and lint/type checks.

Do not introduce alternative frameworks merely because they are familiar.

---

# 35. Code style

## Backend

Target:

```text
Python 3.11
Ruff
MyPy strict
```

Use type hints everywhere.

Avoid:

```text
Any
untyped public functions
dead code
magic values
large functions
duplicate business logic
```

Identifiers:

```text
English
```

Comments and docstrings:

```text
Russian
```

Docstrings should follow Google style.

---

## Frontend

Use:

```text
TypeScript strict
ESLint
Prettier
```

Identifiers:

```text
English
```

User-facing text:

```text
Russian
```

Avoid clever abstractions.

Prefer obvious code over compact code.

---

# 36. Testing rules

Every behavior change must include appropriate tests.

Do not remove a test simply because the current implementation fails it.

First determine whether:

```text
implementation is wrong
or
test is based on obsolete behavior
```

If the test represents the old specification and the target specification changed, update the test to the target contract.

---

# 37. Backend tests

Use:

```text
pytest
pytest-asyncio
```

For PostgreSQL-specific behavior use PostgreSQL, not only SQLite.

Test:

* success cases;
* validation;
* authorization;
* IDOR;
* negative cases;
* race conditions where relevant;
* boundary values;
* migration behavior;
* external integration boundaries.

---

# 38. Frontend tests

Use:

```text
Vitest
Testing Library
MSW
Playwright
```

Test user-visible behavior rather than internal implementation details whenever possible.

---

# 39. Security regression tests

Whenever changing authentication, permissions, file handling or sensitive data, add negative tests.

At minimum consider:

```text
unauthenticated access
wrong role
wrong student
foreign resource
expired resource
archived user
missing CSRF headers
wrong Origin
invalid token
replayed token
rate limit
```

---

# 40. Quality checks before commit

Run the checks relevant to the repository and changed area.

For backend, expected checks include:

```bash
uv sync --frozen
ruff check .
ruff format --check .
mypy --strict .
pytest
```

For frontend, expected checks include:

```bash
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

If the relevant tooling does not yet exist because an earlier migration task is responsible for introducing it, do not invent a replacement toolchain.

Instead:

* run all checks that currently exist;
* report missing target checks;
* add them only when that is part of the current task.

---

# 41. Database validation before commit

For schema/migration changes, additionally verify:

```bash
alembic upgrade head
```

against the supported PostgreSQL environment.

Where applicable, also verify:

```bash
alembic downgrade <revision>
```

Do not claim a migration works if it has only been inspected statically.

---

# 42. OpenAPI validation

For API changes:

1. Run the backend.
2. Generate OpenAPI.
3. Verify the documented routes and schemas.
4. Regenerate frontend types if the frontend exists.
5. Verify no unexpected API schema drift.

The generated API contract must match the intended specification.

---

# 43. Diff review

Before committing, always inspect:

```bash
git status
git diff --check
git diff
```

Confirm:

* no unrelated changes;
* `.gitignore` is NOT in the diff (see 44.1);
* no secrets;
* no generated junk;
* no debug code;
* no temporary files;
* no accidental deletion;
* no accidental formatting of unrelated files.

---

# 44. Generated files and repository hygiene

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

Generated files may be committed only when explicitly required by the repository rules.

Examples:

```text
frontend/src/api/schema.d.ts
```

may be generated and versioned when the project specification requires it.

---

## 44.1 Never modify `.gitignore`

`.gitignore` is the single source of truth that keeps secrets and junk out of the repository.

It must NOT be created, modified, renamed, deleted, truncated, regenerated or restored by Qwen.

Never run:

```bash
git checkout <ref> -- .gitignore
git restore .gitignore
git checkout HEAD~1 -- .gitignore
git clean -xdf
rm .gitignore
```

Never write ignore rules into it, and never "tidy" it by rewriting it from an older revision.

This file is owned exclusively by the repository owner. It has already been reverted three times by automated work that restored a stale revision, and each revert silently removed the rules protecting `.env.local`, virtual environments, caches, logs and IDE directories.

If `.gitignore` appears broken, truncated or empty:

```text
Do not fix it.
Do not restore it from any commit.
Report it in the final report under "Remaining" and stop touching the file.
```

The owner restores it.

The only permitted interaction is verification. To check that the rules work, use:

```bash
git check-ignore -v <path>
```

Reading the file is allowed. Writing it is not.

---

# 45. Secrets

Never hardcode secrets.

Never commit real values for:

```text
BOT_TOKEN
WEBHOOK_SECRET
SESSION_SECRET
DATABASE_PASSWORD
REDIS credentials
S3 credentials
SENTRY secrets
```

Use environment variables.

Update `.env.example` when a new configuration variable becomes part of the approved project architecture.

---

# 46. Docker and deployment

Deployment behavior must follow:

```text
docs/10_deployment_and_ops.md
```

Target production architecture:

```text
nginx
app
worker
scheduler
postgres
redis
```

Do not expose PostgreSQL or Redis publicly in production.

Do not put application secrets into images.

Do not invent a different production topology without owner approval.

---

# 47. Nginx / frontend architecture

Target production flow:

```text
Browser / Telegram Mini App
          ↓
        Nginx
       /     \
      /       \
 frontend     FastAPI
               ↓
       PostgreSQL / Redis / S3
```

The frontend and API should use the same public origin in production.

Do not build a second proxy architecture unless explicitly required.

---

# 48. Business-domain rules that must remain backend-authoritative

The following must never be calculated or decided solely by frontend code:

```text
lesson overlap
lesson participants
attendance
billable state
price snapshot
earnings
expected earnings
homework status
deadline expiration
deadline extensions
score limits
exam conversion
exam scale selection
permissions
resource ownership
session validity
file access
```

---

# 49. Working with the legacy codebase

The current repository may contain code that conflicts with the target documentation.

When encountering legacy code:

1. Determine whether the requested task is specifically replacing it.
2. Prefer the documented target architecture.
3. Do not create another layer on top of legacy behavior.
4. Do not keep obsolete code "just in case" unless compatibility is explicitly required.
5. Do not silently migrate unrelated legacy components.

The target architecture is the destination.

---

# 50. Task completion report

After completing a task, the final response must contain:

## Changed

A concise list of what was implemented.

## Files

A list of important modified/created/deleted files.

## Tests

Exactly which checks were run and their result.

Example:

```text
pytest: 84 passed
ruff check: passed
mypy: passed
```

## Commit

Provide:

```text
<commit SHA>
<commit message>
```

## Remaining

Only issues directly discovered but intentionally left outside the task scope.

Do not claim that the whole project is fixed unless the user explicitly asked for a full-project task and all relevant checks actually passed.

---

# 51. Commit rules

Commit messages must use Conventional Commits.

Examples:

```text
fix: correct telegram init data validation
feat: add student profile service
refactor: move lesson business logic to service layer
test: add homework expiry regression tests
docs: clarify invitation flow
chore: add postgres integration test workflow
```

One task should normally result in one focused commit unless the owner explicitly requests another strategy.

Do not mix unrelated fixes into the same commit.

---

# 52. Pull Request rules

A Pull Request must:

* describe the task;
* describe the implemented solution;
* mention tests;
* mention migrations;
* mention API contract changes;
* mention security implications when relevant.

Do not merge the Pull Request automatically.

Human review is required before merge.

---

# 53. Special rule for remote/web Qwen work

This repository may be edited by QWEN-CODER remotely through the web interface.

Therefore:

* Never assume local files that are not visible in the current workspace exist.
* Never assume a command succeeded without checking its output.
* Never assume `main` is current without `git fetch origin`.
* Never assume a remote branch is based on current `origin/main`.
* Never make broad changes simply because remote execution makes them convenient.
* Keep each task small and independently reviewable.
* Prefer deterministic, reproducible commands.
* Do not leave uncommitted unrelated changes.
* Before finishing, verify the exact git diff.

---

# 54. Stop conditions

STOP and report to the owner when:

1. Documentation contains a contradiction.
2. The requested behavior would violate security requirements.
3. A migration would cause destructive data loss without an approved migration plan.
4. The requested implementation requires changing the approved technology stack.
5. A required external credential/service is unavailable.
6. A task cannot be safely completed without deciding an unspecified business rule.
7. The current branch contains unrelated uncommitted changes that would be overwritten or mixed into the task.
8. A task appears to require creating, changing or restoring `.gitignore`. Report it instead of doing it (see 44.1).

Do not guess in these situations.

---

# 55. Do not hide failures

Never:

* swallow exceptions silently;
* skip failing tests without explanation;
* disable lint/type checks to make CI green;
* weaken security checks to make tests pass;
* remove tests merely because they fail;
* change requirements to fit the current implementation.

When something fails:

```text
identify
explain
fix
or explicitly report
```

---

# 56. Final principle

The quality criterion for this repository is not:

> "The code works somehow."

The criterion is:

> **"The implementation, database, API, security model, bot, worker, frontend and infrastructure match the approved MY_LMS specification."**

Always prefer:

```text
correct architecture
over
quick patch
```

```text
explicit code
over
clever code
```

```text
documented behavior
over
assumption
```

```text
focused task
over
large refactor
```

```text
verified result
over
"it should work"
```

And most importantly:

> **Complete only the task requested by the owner. Stop after that task is verified and committed.**
