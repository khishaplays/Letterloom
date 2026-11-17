# Letterloom Authentication API (Proposed)

**Status:** Design only. None of these routes exists yet. The intended API framework is the current FastAPI application.

## Conventions

- All request and response bodies use JSON unless a route is an OAuth redirect/callback.
- Require HTTPS in production. Authentication cookies are sent automatically by browsers; state-changing cookie-authenticated requests require CSRF validation.
- Responses must not contain passwords, password hashes, session secrets, one-time tokens, OAuth codes, ID tokens, or provider credentials.
- Use a consistent generic response for registration, verification resend, and password-reset requests where an email's existence would otherwise be exposed.
- Authenticated product endpoints require both a valid server-side session and a verified account. They still perform object-level ownership checks.
- Rate-limit public authentication endpoints by source IP and canonical account identifier; use `429 Too Many Requests` and `Retry-After` where appropriate. Exact thresholds are pending operational measurement.

## Proposed endpoints

| Method and path | Access | Request fields | Successful behavior | Important failures / rate limits |
|---|---|---|---|---|
| `POST /auth/register` | Public | `email`, `password`, optional `display_name` | `202 Accepted`; create unverified email/password account and send verification mail if eligible. Same response for duplicate address. No session. | `422` malformed input; `429` registration/mail abuse. Never overwrite an existing password. |
| `POST /auth/email/verify` | Public | `token` | `204`; consume a valid verification token and set `email_verified_at`. | `400` generic invalid/expired/used/wrong-purpose token; `429` guesses. |
| `POST /auth/email/verification/resend` | Public | `email` | `202` generic response whether unknown, verified, or eligible; deliver only where appropriate. | `422`, `429`. Do not reveal account existence or verification state. |
| `POST /auth/login` | Public | `email`, `password` | `200`; create server-side session, set cookie, return minimal user profile and CSRF token. | `401` generic invalid credentials; `403 verification_required` for correct password on an unverified account, without a session; `429` by IP and account. |
| `GET /auth/session` | Session | No body | `200`; return minimal current-user/session view. | `401` missing, expired, or revoked session. Never return the raw session token. |
| `GET /auth/csrf` | Verified session | No body | `200 {"csrf_token": "..."}` for synchronizer-token clients. | `401` missing/expired/revoked session. Token must not be placed in a URL or log. |
| `POST /auth/logout` | Session + CSRF | No body | `204`; revoke current session and clear the cookie. Idempotent from the client's perspective. | `403` invalid CSRF; `429` if abuse controls require it. |
| `GET /auth/google/start` | Public | Optional fixed `intent=login`; no arbitrary redirect URL | `302/303` to Google after creating a short-lived, one-use OIDC transaction. | `429`; reject invalid intent and unregistered callback/redirect values. |
| `GET /auth/google/callback` | Public callback | Provider `code`, `state`, optional `iss` response parameter | Validate transaction and ID token; log in a linked identity or create an account; set a session only if trusted email verification is satisfied. Redirect only to a configured local path. | Generic OAuth failure for missing/replayed state, code, nonce, issuer, signature, audience, expiry, or provider error. Never echo secrets. |
| `POST /auth/google/link/start` | Verified session + CSRF + recent reauthentication | No provider subject or email from client | `302/303` to Google; bind link intent and current user to a one-use transaction. Callback attaches only after successful validation. | `401/403` session or CSRF failure; `409` if the Google subject is linked elsewhere; `429` abuse. |
| `POST /auth/password-reset/request` | Public | `email` | `202` same body for unknown, unverified, password-enabled, and Google-only addresses. Send only if eligible. | `422`, `429`; avoid timing differences that reveal account existence. |
| `POST /auth/password-reset/complete` | Public | `token`, `new_password` | `204`; consume one reset token, update Argon2id hash, invalidate other reset tokens, revoke all sessions. Require a normal login afterward. | `400` generic invalid/expired/used token; `422` password policy; `429` token guesses. |
| `DELETE /auth/account` | Verified session + CSRF + recent reauthentication | Confirmation or credential appropriate to login method | `202` while permanent deletion is pending; revoke sessions immediately, block access, remove stored files, then delete the user and cascaded rows. | `401/403`, reauthentication failure, or `429`; file deletion failures remain pending and retryable. |

No endpoint accepts a `user_id` to choose the acting user. The server derives identity from the session. For account deletion reauthentication, a password account proves its current password; a Google-only account completes a fresh Google OIDC challenge. The exact reauthentication window is pending approval.

## Request and response sketches

These are examples of proposed wire shapes, not committed Pydantic schemas.

### Register

```json
{
  "email": "reader@example.test",
  "password": "a long passphrase chosen by the user",
  "display_name": "Reader"
}
```

`202` response:

```json
{"message": "If the address can be registered, verification instructions will be sent."}
```

### Login

```json
{"email": "reader@example.test", "password": "..."}
```

`200` body is minimal and contains no credential data:

```json
{
  "user": {"id": "uuid", "email": "reader@example.test", "display_name": "Reader"},
  "csrf_token": "random session-bound value"
}
```

The response also sets the session cookie. An unverified valid password receives a `403` with a stable `verification_required` code and no cookie; the public verification and resend functions remain available.

### Reset request and completion

Reset request accepts only an email. Reset completion accepts a one-time token and new password; it does not accept a target `user_id`. On success, the user must log in normally, which avoids building a second implicit session-creation path into recovery.

## Authorization requirements by route family

- **Public:** register, verify, resend, login, reset request/complete, Google login start/callback.
- **Session-bound:** session view and logout.
- **Verified session-bound:** product API and Google linking.
- **State-changing cookie requests:** require a valid session-bound CSRF token and origin validation in addition to authentication.
- **Letters:** query by both `letter.id` and `letter.user_id == current_user.id`; return the same not-found behavior for a foreign owner's letter as for an absent ID.
- **Attachments/reflections:** authorize through the parent letter's `user_id`; do not trust a child UUID alone.
- **Locked letters:** establish ownership first, then calculate whether the owned letter is unlocked. Never bypass ownership because a letter is locked.
- **Account deletion:** reauthenticate, revoke sessions, prevent new login, and wait for the external-file cleanup process before reporting permanent completion.

## Error behavior

| Status | Use |
|---|---|
| `400` | Invalid, expired, consumed, or wrong-purpose one-time token; invalid OAuth transaction. Keep token-specific details generic. |
| `401` | No valid session or generic incorrect login credentials. |
| `403` | Valid password but unverified account (`verification_required`), invalid CSRF, or authenticated account lacking a required verification state. |
| `404` | Missing resource or resource not owned by the current user. |
| `409` | Explicit Google-link conflict where a provider subject is already attached elsewhere; do not auto-link. Avoid returning the matched account's data. |
| `422` | Invalid input shape or password-policy violation, without reflecting secrets. |
| `429` | Rate limit; include `Retry-After` when known. |

Generic responses must be consistent in body and reasonably consistent in timing for account-existence operations. Authentication errors must not include a submitted password/token or database details.

## Rate-limiting requirements

- Registration: per IP and normalized email, plus global/provider mail-send limits.
- Login: per IP and normalized email; use bounded backoff and monitoring rather than permanent account lockout that an attacker can trigger.
- Verification resend and password-reset request: per IP, identifier, and delivery destination; coalesce repeated sends.
- Token verification/reset: per IP and token digest prefix or associated account; reject expired and consumed values in constant time where applicable.
- Google start/callback: per IP and transaction; reject replayed or expired state.
- Authenticated routes: per user/session and endpoint class as product load requires.

Exact counts and windows are **Pending approval** and should be tuned using expected traffic and email-provider capacity. Never rely on process-local counters if multiple application instances are deployed.
