# Public beta persistence contract

## Scope

This phase establishes the data ownership contract before authentication and UI
work. It does not upload files, connect production credentials, or expose any
database endpoint to a browser.

## Ownership model

- Authentication supplies a stable `auth_subject`; application data uses an
  internal UUID from `public.users`.
- Every private read and write takes the internal user ID. Repository methods
  never provide unscoped lookups for CVs, preferences, search runs or
  applications.
- Supabase Row Level Security maps the authenticated JWT `sub` claim to the
  internal user ID, so direct API access is constrained independently of the
  application server.
- Job listings are shared normalized records. User-specific actions live in
  `saved_jobs`, `applications`, `feedback`, and `usage_events`.

## Storage boundary

`jobforge-private` is a private storage bucket. CV and generated-document bytes
must not be stored in Postgres or committed to the repository. The database only
stores an owner-scoped object key, content metadata, checksum, and lifecycle
state. The server must verify ownership before creating a short-lived download.

## Environments

- Local tests use `SQLiteUserRepository`; it deliberately contains no document
  bytes, production secret, or external service call.
- Supabase applies the versioned migration at
  `supabase/migrations/202608020001_public_beta_foundation.sql`.
- The dashboard now gates its workspace with native Streamlit OIDC (or an
  explicit local personal mode). Its documents, preferences, searches and drafts
  remain session-only; it does not call the persistent repository. Connecting
  verified identities to durable account storage remains a separate phase.
- No unauthenticated dashboard code may call the persistent repository.

## Security invariants

1. A user cannot read or mutate another user's resource by changing an ID.
2. A CV object key must begin with `users/<owner-id>/`.
3. Search/application snapshots retain their owner and source version.
4. User exports are owner-scoped and omit document bytes and secrets.
5. A service credential stays in Railway/server configuration only.
