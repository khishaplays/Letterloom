# Letterloom Phase 3 Implementation Plan

**Status:** Proposed sequence for review. The milestones below are not implemented by the Phase 3.1 documentation task. They assume the existing FastAPI, SQLAlchemy 2.x, Alembic, and PostgreSQL foundation remains in place.

## Working principles

- Implement the current MVP requirements in the existing application. Do not introduce MFA, guest accounts, extra identity providers, or a new frontend as part of authentication v1.
- Keep protocol details in maintained libraries, with a small application service layer and FastAPI dependencies around them.
- Apply schema changes through reviewed Alembic revisions. Keep the existing Phase 2 migration immutable.
- Treat the authenticated user ID as the scope for every product query. Authentication does not itself authorize access to a particular letter.
- Make each milestone independently reviewable. Add tests alongside the behavior, not after all features have accumulated.
- Keep secrets out of source and `.env` files committed to Git. Use local environment settings for development and managed secrets in production.

## Milestones

| Order | Milestone | Main work | Completion evidence | Complexity |
|---|---|---|---|---|
| 0 | Resolve design decisions | Approve Google email trust, email normalization, password policy and Argon2id cost, token TTLs, session absolute lifetime, cookie/CORS topology, OIDC library, mail provider, and deletion/storage approach. | Short decision record; development and deployment settings are known. | Small–medium |
| 1 | Authentication schema | Add SQLAlchemy models and relationships for OAuth identities, server sessions, and one-time tokens; extend `User` only with approved fields. Generate, inspect, and test a new Alembic revision. | Migration upgrade/downgrade checks; constraints and cascade tests; schema agrees with the reviewed ERD. | Medium |
| 2 | Password registration and verification | Add password hashing/verification, registration, verification-token issuance and atomic redemption, resend flow, generic public responses, and an email adapter. Unverified password accounts may reach only verification/resend behavior. | Tests cover duplicate registration, hashing, delivery handoff, expiry, wrong purpose, replay, concurrent redemption, and unverified access. | Medium–large |
| 3 | Server sessions and password login | Add random opaque session issuance, digest-only persistence, login/logout, session lookup and revocation, seven-day idle expiry, cookie policy, and synchronizer-token CSRF protection. Keep the 30-day absolute expiry configurable only after approval. | Endpoint/dependency tests cover valid and invalid credentials, Google-only null hashes, session rotation, expiry, revocation, cookie attributes, CSRF, and rate limits. | Large |
| 4 | Google sign-in and explicit linking | Integrate the selected OIDC client using Authorization Code + PKCE S256; bind state and nonce to the browser transaction; verify ID token claims; create a user on first verified sign-in; support explicit linking only for an authenticated, recently reauthenticated account. | Mocked callback tests reject bad state/nonce/signature/issuer/audience/expiry/replay; integration smoke test uses a configured test client; email match never silently links. | Large |
| 5 | Password recovery | Issue and atomically consume expiring single-use password-reset tokens; use generic public responses; revoke existing sessions after reset; notify the user through the mail adapter. Google-only users must not gain a password through reset. | Tests cover unknown address response equivalence, expiry, replay, wrong purpose, null password hash, session revocation, and notification handoff. | Medium |
| 6 | Owner authorization and time unlocking | Add authenticated-user dependencies and scope letter, attachment, and reflection reads/writes by owner through the parent letter. Check ownership before sealed/unlocked state. Enforce date unlocking on the backend using timezone-aware UTC instants; do not add a redundant `is_unlocked` database flag. | Tests prove User A cannot read or mutate User B's resources, including locked letters; boundaries around `unlock_at` and naive datetimes are covered. | Large |
| 7 | Permanent account deletion and file cleanup | Add recent reauthentication and CSRF requirements; block access immediately; revoke auth records; delete external objects with durable, idempotent retry; delete the account and cascaded rows after file cleanup succeeds. Choose the outbox/worker design with the storage provider. | Tests cover immediate access denial, cascading database records, successful object deletion, retry after partial failure, and idempotent repeated work. | Large–very large |
| 8 | Security hardening and release readiness | Apply distributed rate limits, generic error behavior, safe logging, origin/redirect allowlists, HTTPS/proxy/cookie settings, dependency updates, monitoring, backup/restore and operational runbooks. Review privacy and deletion behavior end to end. | Full test suite; PostgreSQL migration run in CI; security checklist in [`authentication-security.md`](authentication-security.md) reviewed; manual production-like smoke test. | Medium–large |

## Dependency order and parallel decisions

Milestone 0 should be completed before committing to schema details or deployment behavior. The email provider and storage provider can be selected while schema work is designed, but their delivery/retry and physical deletion integration must be decided before those flows are marked complete.

Milestone 1 precedes feature code because user verification state, linked identities, server-side sessions, and one-time token persistence need a stable schema. Registration and verification in Milestone 2 can be developed alongside service interfaces, but product access must remain unavailable until session and authentication checks are wired in Milestone 3.

Google sign-in and password reset depend on the session/token foundations. Ownership enforcement is required before any protected letter API is considered complete. Account deletion depends on the actual storage provider because SQL `ON DELETE CASCADE` deletes rows, not stored file bytes.

## Cross-cutting test expectations

- Use isolated test databases and a fresh schema per test or test group. Keep tests deterministic with a controllable clock for token and session expiry.
- Run model/service tests on SQLite where it is useful, and run migration/integration checks against PostgreSQL in CI because database behavior and constraints can differ.
- Stub email, Google, rate-limit, and object-storage adapters in unit tests. Add a small number of integration tests against the real protocol/provider test configuration without using production credentials.
- Include negative tests: malformed credentials, expired and replayed tokens, wrong OAuth audience, mismatched owner IDs, missing CSRF, and deletion retry failure.
- Do not log test tokens or secrets. Use test-only values and never copy production credentials into fixtures.

## Scope boundaries

Authentication v1 includes email/password registration, mandatory email verification, Google authentication, password reset, server-side sessions, cookie CSRF protection, owner-only access, date-based unlocking, and permanent account deletion. MFA is explicitly outside the initial release. Actual attachment upload and storage still require their own implementation; account deletion cannot be considered complete until the storage behavior is integrated.

## Read this plan with

- [Authentication architecture](authentication-v1.md) for confirmed requirements and pending decisions.
- [Authentication flows](authentication-flows.md) for proposed interaction sequences.
- [Authentication API](authentication-api.md) for proposed routes and response behavior.
- [Authentication security controls](authentication-security.md) for implementation and review checks.
- [Authentication ERD](authentication-erd.dbml) for current schema fields and proposed authentication tables.
