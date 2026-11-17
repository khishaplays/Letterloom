# Letterloom Authentication Architecture v1

**Status:** Proposal for review. Nothing in this document is implemented by this milestone.

## Decision labels

- **Confirmed** — explicitly required in the Phase 3.1 brief.
- **Recommended** — the proposed design for implementation; it is not yet code or an approved product decision.
- **Pending approval** — a product, deployment, or implementation choice that still needs an owner.

## Product requirements

### Confirmed

- Registration is required; guest use is not part of the described product.
- A person can register with an email address and password or authenticate with Google.
- First-time Google authentication creates a Letterloom account automatically.
- Email/password accounts must verify their email before getting product access. Before verification they may use only verification-screen and resend-verification functionality.
- A trusted Google email-verification claim satisfies the email-verification requirement.
- Passwords use Argon2id. Password recovery uses secure, expiring, single-use tokens.
- Authentication uses server-managed sessions. The inactivity lifetime is seven days; a 30-day absolute lifetime is proposed, not confirmed.
- Session cookies are HttpOnly, Secure in production, and use an appropriate SameSite policy. CSRF protection is required for state-changing cookie-authenticated requests.
- Google sign-in uses OAuth 2.0 Authorization Code flow. OAuth state and OIDC nonce, issuer, audience, signature, and expiry must be validated.
- Accounts are never linked to Google silently based only on matching email addresses.
- Users can access only their own letters, attachments, and reflections. Ownership is checked even for locked letters.
- Account deletion is permanent and must cover records, sessions, linked identities, and stored files. MFA is outside the initial release.

## Existing application baseline

The current code has no authentication implementation. The Phase 2 `users` table has a UUID primary key, a required unique `email`, and creation/update timestamps. Its `User.letters` relationship is one-to-many. `Letter.user_id` is the letter ownership foreign key. Attachments and reflections belong to a letter and inherit its owner through that relationship; they have no direct `user_id`. Existing foreign keys cascade from user to letters and from letters to attachments/reflections. Attachments hold metadata and a `storage_key`; the repository has no file upload or physical storage implementation.

The existing unique constraint on `users.email` compares stored strings as the database does. It does not define a canonicalization policy for differently cased or otherwise equivalent addresses. Existing IDs use SQLAlchemy's Python-side `uuid4` default; the migration does not define a database-side UUID generator. Existing `updated_at` values are advanced by SQLAlchemy writes, not by a database trigger. See the actual definitions in [`user.py`](../../app/db/models/user.py), [`letter.py`](../../app/db/models/letter.py), [`attachment.py`](../../app/db/models/attachment.py), [`reflection.py`](../../app/db/models/reflection.py), and the [initial revision](../../migrations/versions/ecdc9062cc28_initial_user_letter_attachment_and_.py).

## Architecture overview

**Recommended:** keep the existing FastAPI application and PostgreSQL schema as the center of the design. Add a small authentication service layer that verifies credentials and resolves a server-side `Session` to a `User`. Protected route dependencies authenticate first; domain queries then scope every letter to that user. Email delivery and Google identity verification are adapter boundaries, not hard-coded provider logic.

```text
Browser -- HttpOnly session cookie --> FastAPI authentication dependency
                                      |-- Session + user lookup --> PostgreSQL
                                      |-- Letter ownership query --> PostgreSQL
                                      |-- verification/reset mail --> email adapter
                                      `-- Google OIDC callback --> Google
```

**Authentication** answers “who is making this request?” **Authorization** answers “may that user access this particular record?” A valid session alone never grants access to a letter. For a nested attachment or reflection request, resolve its parent letter and require `letter.user_id == session.user_id`. For a locked letter, check ownership before returning its lock state so another user cannot probe its existence.

## Recommended data design

All items below are proposals until their implementation milestones are approved. The full proposed shape is in [`authentication-erd.dbml`](authentication-erd.dbml).

### User extensions

- Add nullable `password_hash`. A Google-only user has no password hash; do not invent a placeholder password. Password login must reject a null hash without treating it as an Argon2 string.
- Add nullable `email_verified_at`. A null value means the email/password account is not yet allowed into product routes.
- Add nullable `display_name`; the provider may not return a name and users may not want to share one.
- **Recommended:** add `email_normalized` with a unique constraint while retaining the original `email` for display and delivery. Define normalization before use. A safe starting policy lowercases the domain and trims whitespace; local-part case folding remains pending because it can merge distinct addresses. Apply the same policy at registration, login, reset, verification, and linking. Do not use provider-specific transformations such as removing Gmail dots.
- **Recommended:** add nullable `deletion_requested_at` to block new access while an account's external files are being removed. This is an implementation aid for permanent deletion, not a current field.

### Google identities

Use a separate `oauth_identities` table. It allows an account to have one or more provider identities without adding provider-specific columns to `users`. Store the provider and its stable subject identifier; for Google, that is the verified ID token's `sub`, not the email address. Enforce uniqueness on `(provider, provider_subject)` and index `user_id`. Google documents that `sub` remains the stable account identifier even if the email changes ([Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect)).

Do not store Google access or refresh tokens unless a later product feature needs Google APIs. Sign-in needs a verified identity, not continuing access to the user's Google data.

### Server-managed sessions

**Recommended:** generate a cryptographically random 256-bit opaque session secret. Send the raw secret only in the cookie and persist only its SHA-256 digest (`token_hash`) in a `sessions` row. The secret has high random entropy, unlike a human password, so a fast digest is appropriate for lookup; Argon2id is for passwords. Hashing means a database-only leak does not directly disclose replayable session cookies.

Each row should include `user_id`, `created_at`, rolling `expires_at`, fixed `absolute_expires_at`, `last_seen_at`, and nullable `revoked_at`. Add a per-session CSRF token hash if using the recommended synchronizer-token approach. On activity, set the idle expiry to the earlier of `now + 7 days` and the absolute expiry. The 30-day absolute lifetime is a proposal and must be approved. Throttle `last_seen_at` writes rather than updating it on every request.

On successful login or Google callback, issue a new session; do not reuse a pre-authentication identifier. On logout, password reset, and account deletion, revoke relevant database sessions and clear the browser cookie. Deleting a cookie alone does not invalidate a copied token.

### One-time tokens: one table or separate tables?

**Recommended:** one `one_time_tokens` table with a required `purpose` (`email_verification` or `password_reset`), `user_id`, unique `token_hash`, `created_at`, `expires_at`, and nullable `consumed_at`.

The two flows share the same lifecycle: generate a random secret, send it out-of-band, store only its digest, check expiry, and consume it once. A shared table avoids duplicating the same columns and redemption code. The `purpose` value must be checked on every redemption so a verification token can never reset a password. Keep purpose-specific expiry, messages, and authorization rules in the service layer.

Separate tables would make each token's purpose visible in its schema and allow different columns or retention rules, at the cost of duplicated lifecycle code. Choose separate tables only if the flows acquire materially different data or retention needs. Token redemption must be atomic: update the row only where the digest matches, `consumed_at IS NULL`, `expires_at > now`, and the expected purpose matches. Only one concurrent request may succeed.

### Passwords and email verification

**Confirmed:** Argon2id. **Recommended:** use a maintained library that emits self-describing encoded hashes with per-password salts; never implement the primitive or store plaintext. OWASP lists `m=19 MiB, t=2, p=1` as a minimum configuration and recommends benchmarking on the target system; RFC 9106 also describes higher-memory profiles. Select parameters through production-like load measurement and record the decision. NIST SP 800-63B-4 recommends a 15-character minimum for a password used as a single factor, permits at least 64 characters, and discourages arbitrary composition rules. Treat the exact minimum, maximum, Unicode handling, and compromised-password blocklist as pending policy decisions.

Verification/reset tokens should be generated from a cryptographic random source, be long enough to resist online guessing, and be single-use and time-limited. A 32-byte random value encoded for a URL is a reasonable recommendation. Store its SHA-256 digest; never log tokens or complete token URLs. Proposed initial expiries are 24 hours for email verification and 30 minutes for password reset; both need approval. OWASP recommends consistent responses for account-existence flows and single-use, expiring reset tokens ([Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html), [Email Validation and Verification](https://cheatsheetseries.owasp.org/cheatsheets/Email_Validation_and_Verification_Cheat_Sheet.html)).

### Google OAuth / OpenID Connect

Use a maintained OIDC client and the Authorization Code flow with PKCE `S256`. Bind a fresh, one-use `state`, `nonce`, and PKCE verifier to the browser's specific login attempt. The client must validate the authorization response and the ID token signature, issuer, audience, expiry, nonce, and—where applicable—authorized party. Accept only an intended Google issuer and the configured client ID. Do not use decoded but unverified claims. RFC 9700 recommends PKCE for confidential clients and requires transaction-specific binding; Google's documentation lists signature, `iss`, `aud`, and `exp` checks and says to use `sub` as the identity key ([RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html), [Google ID token verification](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)).

First look up `(provider='google', provider_subject=sub)`. If found, authenticate that linked user. If not found and no existing account conflicts with the verified/canonical email, create `User` and `OAuthIdentity` together in one transaction. If an account already uses that email, do not attach the identity automatically. Give a generic conflict response and require the user to authenticate using the existing method, then explicitly link Google from an authenticated, reauthenticated session.

**Pending approval:** Google's `email_verified` claim is not equally authoritative for every address. Google says it is authoritative for Gmail addresses and for Workspace addresses with a verified hosted-domain claim; for third-party email addresses without `hd`, it warns that the address may no longer be controlled by the Google user. The product requirement accepts a *trusted* verified claim; approve the exact trust rule. Until then, only mark `email_verified_at` from a claim that meets the approved rule; otherwise send Letterloom's own verification email.

### Account deletion and file storage

Database cascades can remove a user's sessions, identity rows, tokens, letters, and attachment/reflection metadata. They cannot remove file bytes from an external object store. The current code has no storage provider, so the final deletion integration is pending that choice.

**Recommended process:** require a verified authenticated session and recent reauthentication; set `deletion_requested_at` and revoke sessions in a database transaction; deny further access while deletion is pending; enumerate storage keys; delete external objects idempotently with retryable work; then delete the `User` row so database cascades remove related records. If object deletion fails, retain the pending marker and retry rather than claim completion. Decide whether a small durable deletion queue/outbox is warranted when the storage worker is designed.

## Technology choices and trade-offs

| Area | Status | Proposal and reason |
|---|---|---|
| Password hash | Confirmed / parameters pending | Argon2id; expensive, salted password verification. Use a maintained library and benchmark settings. |
| Session | Recommended | Opaque random cookie plus server-side row gives immediate revocation and supports idle/absolute expiry. More database lookups than a self-contained JWT, but simpler logout and account deletion. |
| One-time tokens | Recommended | Shared table because the two token types have the same lifecycle; purpose is explicit and checked. |
| Google sign-in | Confirmed / library pending | OAuth Authorization Code + OIDC + PKCE S256; a vetted client handles protocol details. |
| Email delivery | Pending | Keep a small mailer interface; choose a provider and secret-management mechanism separately. |
| Database | Existing target | PostgreSQL in production; SQLite in tests/development. Verify migration constraints on both dialects. |
| MFA | Confirmed out of initial scope | Do not represent it as implemented or required in v1. |

Do not add secrets to source code or committed `.env` files. Read Google client credentials and other deployment secrets from environment-backed settings or a production secret manager. Keep development settings separate: local HTTP may use `Secure=False` only for loopback development; production must require HTTPS and `Secure=True`. Never weaken production behavior based on a request header alone.

## Threat considerations

- **Credential stuffing and guessing:** Argon2id, rate limits, generic login errors, and monitoring.
- **Database disclosure:** password hashes are slow to verify; session and one-time tokens are stored as digests, not replayable values.
- **Session theft/fixation:** random secrets, rotation on authentication, HttpOnly/Secure/SameSite cookies, TLS, expiry, and server-side revocation.
- **CSRF:** a session-bound synchronizer token in a custom header on state-changing requests plus origin checks. SameSite is defense in depth, not the only control.
- **OAuth code injection/replay/mix-up:** exact registered redirect URI, state, nonce, PKCE S256, one-use callback transaction, issuer/audience/signature/expiry verification, and no open redirects.
- **Account takeover via linking:** stable provider subject, explicit authenticated linking, reauthentication, and no email-only auto-link.
- **Object-level authorization:** scope every letter query to the authenticated owner; reach attachments and reflections only through an owned letter; apply the same rule before revealing lock state.
- **Enumeration and mail abuse:** generic registration/resend/reset responses, per-IP and per-identifier rate limits, and no secret tokens in logs.
- **Incomplete deletion:** distinguish database cascade from object-store deletion; make external deletion idempotent and retryable.

## Outstanding decisions

| Decision | Status | Recommendation / question |
|---|---|---|
| 30-day absolute session lifetime | Pending approval | Approve or change; enforce alongside the confirmed seven-day inactivity expiry. |
| Google email claim trust | Pending approval | Accept only claims Google treats as authoritative, or require Letterloom email verification for external addresses without `hd`? |
| Email normalization | Pending approval | Preserve original address and enforce a documented canonical comparison key; decide local-part case policy. |
| Password policy and Argon2id parameters | Pending approval | Choose length/blocklist rules and benchmark hash costs on production-like hardware. |
| Token and OAuth transaction expiry | Pending approval | Proposed: verification 24h, reset 30m, OAuth state 10m; approve values. |
| Cookie/site topology | Pending approval | Confirm frontend/API origins, HTTPS termination, SameSite value, and CORS allowlist. |
| OIDC library | Pending approval | Select a maintained Python OIDC client and verify its state/nonce/PKCE support. |
| Account linking/unlinking | Pending approval | Explicit link flow is recommended; decide whether one account may link more than one Google subject, whether unlink is allowed, and require another credential before removing the last login method. |
| Email provider | Pending approval | Select delivery provider, sender domain, retry and bounce handling. |
| File storage/deletion worker | Pending approval | Select provider and retry/outbox design before enabling physical uploads or claiming deletion is complete. |

## References

- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [RFC 9700: OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect)
