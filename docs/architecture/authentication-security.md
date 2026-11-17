# Letterloom Authentication Security Controls

**Status:** Security design only; these controls are not implemented. “Confirmed,” “Recommended,” and “Pending approval” have the meanings in [`authentication-v1.md`](authentication-v1.md).

## Password security

- **Confirmed:** password accounts use Argon2id. Never store or log plaintext passwords.
- **Recommended:** use a maintained password-hashing library that generates a unique random salt and stores algorithm/version/cost parameters in its encoded output. Verify with the library and rehash after a successful login when stored parameters are below the approved policy.
- OWASP's current floor is Argon2id `m=19 MiB, t=2, p=1`; benchmark under expected concurrent login load before choosing production parameters. RFC 9106 presents higher-memory profiles. The final memory/time/parallelism parameters are **Pending approval**.
- **Recommended:** because MFA is out of scope and passwords are a single factor, use a 15-character minimum, allow at least 64 characters, allow spaces and passphrases, and reject common/compromised values. Avoid arbitrary character-class rules. This recommendation follows current NIST guidance but needs product approval.
- Set an explicit maximum request/body size to limit resource abuse, but do not silently truncate passwords. Make password comparison behavior consistent and use a dummy Argon2 hash for nonexistent email addresses to reduce timing differences.
- A null `password_hash` is valid for a Google-only account. It means there is no password credential to verify, not an empty password. Do not auto-create a local password from Google claims.

## Token creation, storage, expiry, and use

Session secrets and one-time verification/reset tokens are different from passwords: generate each from a cryptographically secure random source with at least 256 bits of entropy. Send the raw random value only to its intended browser/email recipient. Store a SHA-256 digest (`token_hash`) in the database and compare by digest. A slow password hash is unnecessary for a uniformly random 256-bit token; the main protections are entropy, expiry, one-time use, rate limits, and no token disclosure.

For one-time token redemption, use a single conditional database update (or equivalent transaction/row lock) that checks the digest, expected `purpose`, `consumed_at IS NULL`, and `expires_at > now`. Only a request that changes exactly one row succeeds. Then apply the account change in that same transaction. This prevents two concurrent requests from both consuming one token. Never put tokens in server logs, analytics, error telemetry, or untrusted redirect targets. Build email links from a configured public origin, not the request `Host` header. Use HTTPS and a `no-referrer` policy on token landing pages.

**Recommended starting expiries, Pending approval:** verification 24 hours; password reset 30 minutes; OAuth transaction 10 minutes. Rate-limit issuance and redemption. On successful reset, consume other reset tokens for that user and revoke all their sessions. Notify the verified address that the password changed; do not include the password or token.

## Session lifecycle and cookies

1. After verified email/password login or a successful trusted Google callback, generate a fresh opaque session secret; do not accept a caller-chosen session ID.
2. Store the SHA-256 digest, owner UUID, creation time, last-seen time, rolling idle expiry, absolute expiry, optional CSRF-token digest, and nullable revocation time in `sessions`.
3. Enforce server-side expiry and revocation on every authenticated request. A seven-day inactive session expires even if a browser retains the cookie. A proposed 30-day absolute expiry caps rolling renewal and remains pending approval.
4. On activity, update `last_seen_at` and set the idle expiry to `min(now + 7 days, absolute_expires_at)`. Throttle writes, for example to at most once per minute per active session; final interval is an implementation choice.
5. On logout, set `revoked_at` and clear the cookie using the same name, path, and domain attributes. Password reset and account deletion revoke all sessions. Consider revoking sessions on future email/password changes and high-risk events.

**Recommended production cookie:** a host-only cookie such as `__Host-letterloom_session`, `HttpOnly`, `Secure`, `Path=/`, no `Domain`, and `SameSite=Lax`. `Lax` supports ordinary top-level OAuth callback navigation while blocking many cross-site subrequests; it is a defense-in-depth choice, not the CSRF control itself. Use HTTPS and HSTS in production. Local HTTP development may disable `Secure` only for loopback and must not share production credentials. Do not store session secrets in localStorage or expose them to frontend JavaScript. OWASP recommends explicit HttpOnly/Secure/SameSite cookie attributes and server-enforced expiry ([Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)).

## CSRF

Because browsers attach cookies automatically, every state-changing cookie-authenticated endpoint needs CSRF protection. **Recommended:** a synchronizer token generated per session, returned in an authenticated response body, and sent by the client in a custom header such as `X-CSRF-Token`. Store only its digest with the server session. Validate the token and the request `Origin` against an explicit configured origin allowlist; if `Origin` is absent, apply a strict `Referer` policy or reject unsafe requests. Keep `SameSite=Lax` as an additional layer, not a substitute for the token. Require JSON and exact credentialed CORS origins if the frontend is cross-origin. OWASP recommends synchronizer tokens for stateful applications and notes SameSite alone is not sufficient in all cases ([CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)).

OAuth start/callback CSRF is separate: bind one-time `state` and OIDC `nonce` to the exact browser transaction, and use PKCE `S256`. Do not assume the general application CSRF token protects the provider callback.

## Google OAuth / OIDC validation

Use a maintained OIDC client and a fixed Google issuer/authorization/token configuration. Do not construct token-verification rules from untrusted claims.

- Use Authorization Code flow with PKCE `S256`, exact pre-registered callback URI, unique state, and nonce. Protect the PKCE verifier and transaction until the callback; expire and discard it after use.
- Exchange the code on the server over TLS. Do not accept an ID token merely because it can be decoded.
- Verify the ID token signature against Google's current published keys; validate key rotation and allowed algorithms using the library.
- Validate `iss`, `aud` (must contain the configured client ID), `exp`, `nonce`, and `sub`. Validate `azp` where required for multiple audiences. Validate the response issuer/mix-up protection for the single configured provider.
- Use `(provider='google', provider_subject=sub)` as the identity lookup key. Email is an attribute, not the provider's stable identity key.
- Require `email_verified=true` and the approved trust rule before setting `email_verified_at`. Google documents that its email is authoritative for Gmail and for Workspace accounts with `hd`; a verified third-party address without `hd` may no longer be controlled by that Google account. Exact handling is **Pending approval**.
- Never silently link a new Google subject to an existing account based only on an email match. Linking is an explicit flow requiring an authenticated, recently reauthenticated user, a fresh OIDC transaction, CSRF on the start request, and uniqueness checks on `(provider, provider_subject)`.
- Do not persist Google access/refresh tokens unless a later product feature needs Google API access. Do not log authorization codes, tokens, state, nonce, or PKCE values.

RFC 9700 recommends PKCE for confidential clients and transaction-specific binding; Google's server-verification guidance specifies signature, issuer, audience, and expiry checks and identifies `sub` as the stable account identifier ([RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html), [Google verification](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)).

## Account enumeration and abuse

- Return generic responses for registration, resend-verification, and password-reset requests whether the address exists, is verified, or has a password credential. Keep status/body and timing reasonably consistent.
- Login failure should not distinguish unknown email from wrong password. A correct password on an unverified account may receive the documented `verification_required` response; it must not receive a product session.
- Apply distributed rate limits to login, registration, token issue/redemption, and OAuth start/callback. Key limits by IP and a privacy-preserving normalized identifier; do not rely only on an in-process counter.
- Prefer throttling and alerting over permanent account lockout that attackers can trigger. Use `429` and `Retry-After` for request limits.
- Mask/pseudonymize email addresses in logs. Do not log password values, raw session/CSRF/token values, OAuth codes, or full verification/reset URLs.
- Avoid user-controlled redirect URLs. Use a short allowlist of post-login destinations.

## Account linking and passwordless users

Identity is determined by local credentials or a stored `(provider, provider_subject)` link, not by email equality alone. If a Google callback has a verified email matching a local account but no matching identity, stop and ask the person to sign in using the existing method before linking. A conflict response must not expose the other account's profile. For explicit linking, verify the current account and recent authentication, then enforce provider-subject uniqueness transactionally.

A Google-only user has `password_hash = NULL`. Password-login and password-reset code must handle null explicitly. If a product flow later lets a Google-only user add a password, require an authenticated recent Google reauthentication and a separate password setup flow. Unlinking Google is allowed only if another usable login method remains; whether unlinking is offered is pending approval.

## Ownership enforcement

Every resource query must use the authenticated user scope. For letters, query by both `letter.id` and `letter.user_id`. For attachments and reflections, join through their required letter and apply the same owner filter. Return not-found behavior for both foreign-owned and absent records. Do this before checking `sealed_at`/`unlock_at`, so locked content cannot be used to probe another user's data. Enforce ownership in service/query code and test it; a valid session is not a substitute for authorization.

## Permanent account deletion

Database `ON DELETE CASCADE` removes database rows only. It does not delete bytes held by object storage. The repository's current Attachment model has metadata and `storage_key`, not a file store.

**Recommended safe order:** require a verified session, CSRF, and recent reauthentication; mark deletion pending and revoke sessions/tokens in a transaction; prevent new login and reads; enumerate storage keys; delete objects idempotently using durable retryable work; only after file deletion succeeds, delete the User row so cascades remove OAuth identities, sessions, one-time tokens, letters, attachment metadata, and reflections. If deletion fails, keep the account inaccessible and pending, then retry. Choose a durable outbox/worker design when the storage provider is selected. Do not report deletion complete while file objects remain.

## Development and production controls

- Keep Google client ID/secret, signing/encryption keys (if used), and mail credentials out of source and committed `.env` files. Load from environment-backed settings in development and a managed secret store in production.
- Production requires HTTPS, secure cookie, fixed callback URL, strict allowed origins, real mail delivery, stable public URL configuration, and externally stored secrets.
- Development may use SQLite and loopback HTTP with a non-secure local cookie only; do not copy production secrets or use production Google callbacks locally.
- Log security events without credential values. Monitor unusual verification/reset sends, failed logins, OAuth validation failures, deletion retry backlog, and repeated ownership denials.
- Exact origins, proxy/trusted-host configuration, deployment topology, and provider settings are **Pending approval**.

## Security testing checklist

- [ ] Passwords are Argon2id-hashed; no plaintext/hash/token leaks in logs or responses.
- [ ] Null password hash for Google-only users cannot authenticate by password or request a password reset that exposes account state.
- [ ] Email is unverified until a valid one-time token is consumed; unverified accounts have no product session.
- [ ] Verification/reset tokens fail when expired, consumed, wrong-purpose, malformed, or replayed concurrently.
- [ ] Registration, login, resend, and reset responses do not reveal account existence beyond the approved verification UX; rate limits are tested.
- [ ] Session secret is random, only its digest is stored, and cookie has expected HttpOnly/Secure/SameSite/Path/Domain attributes per environment.
- [ ] Idle and absolute expiry, revocation, logout, reset-all-sessions, cookie clearing, and session rotation are tested.
- [ ] State-changing cookie requests fail with missing/invalid CSRF token, wrong origin, and `Origin: null` where applicable.
- [ ] OAuth callback rejects state mismatch/replay, nonce mismatch, invalid signature, issuer, audience, expiry, wrong client, and reused code; PKCE S256 is required.
- [ ] Existing Google identity logs in the linked user; matching email alone never links; explicit link rejects a provider subject already owned elsewhere.
- [ ] User A cannot read or mutate User B's letters, attachments, or reflections, including locked letters; absent and foreign-owned IDs have indistinguishable responses.
- [ ] Deletion revokes sessions immediately, blocks login/access while pending, removes DB rows, removes external file bytes, retries partial failures idempotently, and preserves no unique storage references.

## References

- [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html)
- [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [OWASP Email Validation and Verification](https://cheatsheetseries.owasp.org/cheatsheets/Email_Validation_and_Verification_Cheat_Sheet.html)
- [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html)
- [Google ID token verification](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)
