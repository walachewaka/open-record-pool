# Single sign-on (OIDC identity providers)

Members can sign in with Microsoft Entra ID (Microsoft 365), Google, Google
Workspace, or Okta **as well as** a local username/password account. Both kinds
of account coexist on the same pool.

With `OIDC_PROVIDERS` empty — the default — none of this exists: the login gate
shows the same local form it always did, and no new account-creation path is
added. Everything below is opt-in per deployment.

## How it works

A provider is a **config entry, not code**. All four providers speak OpenID
Connect, so they are the same code path with different environment variables:
adding Keycloak or Authentik later means adding variables, not shipping a
feature.

The flow is the authorization-code flow with PKCE (`S256`), a `state` and a
`nonce`. The ID token's signature is verified against the provider's JWKS
(cached, key-rotation aware), and only RS256 is accepted. After a successful
verification the pool issues **its own session** — the same revocable
`auth_sessions` cookie a local login gets. Provider access/refresh tokens are
used once, for identity, and are never stored.

**Logout is local.** Signing out of the pool revokes the pool's session; it does
not sign you out of Google or Microsoft. That is the normal expectation for a
"Sign in with X" button.

## What you register with each provider

Every provider needs the same redirect URI whitelisted — substitute your
`PUBLIC_BACKEND_URL` and the provider id you chose in `OIDC_PROVIDERS`:

```
<PUBLIC_BACKEND_URL>/auth/oidc/<provider-id>/callback
```

The exact string per configured provider is shown (and copyable) in
**Admin → Settings → Integrations → Single sign-on**.

| Provider | Where you get the credentials | Issuer |
|---|---|---|
| **Entra ID / M365** | Entra portal → App registrations → New registration (Web) → client id + client secret + tenant id | `https://login.microsoftonline.com/<tenant-id>/v2.0` (single-tenant). Multi-tenant: issuer `https://login.microsoftonline.com/{tenantid}/v2.0` **and** `OIDC_<ID>_DISCOVERY_URL=https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration` |
| **Google** | Google Cloud Console → Credentials → OAuth client ID (Web application) | `https://accounts.google.com` |
| **Google Workspace** | Same as Google (own client or shared) | `https://accounts.google.com` + `OIDC_<ID>_ALLOWED_DOMAINS=yourfirm.com` |
| **Okta** | Okta admin console → Applications → OIDC Web App | `https://<your-org>.okta.com` (or a custom auth server's issuer) |

Client secrets are read from the environment/secret store only. They are never
written to the database, never returned by any API, and never logged.

`.env.example` carries a ready-to-fill block for all four.

### Google Workspace specifically

Setting `ALLOWED_DOMAINS` on a Google-issuer provider turns on hosted-domain
enforcement: the `hd` claim **inside the verified ID token** must be one of the
allowed domains. A login from a personal gmail.com account, or from another
Workspace domain, is rejected with a clear message on the gate. The `hd` request
*parameter* is sent too, but only to pre-filter the account picker — it is never
trusted for enforcement.

The check runs on **every** login and link, not only at first sign-up, so a user
removed from the workspace loses access on their next attempt.

## Registration policy

The existing `ADMIN_USERNAME` gate is not weakened by SSO. Each provider carries
its own policy, `OIDC_<ID>_PROVISIONING`:

- **`closed` (default)** — no account is ever created. Only a user who already
  has this identity linked can sign in. New members get an account the way they
  do today (an admin creates it) and then link the provider from Account
  settings.
- **`invite`** — a first login creates a *pending* account and issues no
  session. It appears under **Admin → Users** with status `pending`; flip it to
  `active` and the next SSO login works.
- **`domain`** — a first login creates an active account, but only for a
  verified address in `ALLOWED_DOMAINS` (or a matching `hd` on Google).
- **`open`** — anyone the IDP authenticates gets an account. Requires a verified
  email.

A JIT-provisioned account is always a passwordless `member` (unless a group
claim maps a role, below) and can never be, or claim, the `ADMIN_USERNAME`
account.

## Account linking

One account, N linked identities. A login is matched on `(provider, subject)` —
never on the email address — so a user who changes their email at the provider
still lands on the same account.

Users link and unlink providers under **Account → Sign-in methods**. Unlinking
is refused when it would leave the account with no way to sign in at all.

`OIDC_EMAIL_AUTOLINK=false` by default. When turned on, an unknown identity
whose **verified** email matches exactly one existing account is linked to it
automatically. It is off by default on purpose: providers disagree about what
"verified" means, mailbox addresses get recycled, and an attacker-controlled IDP
account with a matching address would inherit the local account.

## Role mapping (optional)

Set both `OIDC_<ID>_GROUPS_CLAIM` (e.g. `groups`) and `OIDC_<ID>_GROUP_ROLE_MAP`
(e.g. `{"orp-admins": "admin"}`) to have a group claim grant a role on every
login. `owner` is not mappable. With mapping off — or when a token carries no
mapped group — the locally assigned role stays authoritative.

## IDP-only pools

`LOCAL_LOGIN_ENABLED=false` turns off the username/password form: `POST /login`
403s and the gate hides the form. The backend refuses to boot if that is set
with no provider configured, since nobody could sign in.

In production (`ORP_ENV=production`) the boot also refuses an empty client
secret and any non-https issuer, discovery URL, `PUBLIC_BACKEND_URL` or
`PUBLIC_FRONTEND_URL`.

## Security notes

- Auth endpoints are rate limited (`idp_start`, `idp_callback`: 10/min/IP).
- Every login, failure, provisioning and link/unlink is written to the audit log
  (`auth.sso.login`, `auth.sso.login_failure`, `user.sso_provisioned`,
  `user.identity.linked`, `user.identity.unlinked`).
- Sign-in failures redirect to `/login?sso_error=<code>` with a coarse code
  (`denied`, `expired`, `invalid`, `not_permitted`, `pending_approval`,
  `domain_not_allowed`, `already_linked`, `rate_limited`). No provider detail,
  email or username is ever put in that URL — an error page must not become an
  account-enumeration oracle.
