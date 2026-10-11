# Phase 7 report: authentication and provisional administration

Phase 7 adds local password authentication, generic OIDC and Firebase ID-token
verification to generated hexagonal services. Sessions use short lifetimes,
secure cookies and CSRF protection. Passwords are supplied as PBKDF2 hashes;
no default user or password is generated.

Authorization supports authentication-only, roles, and roles plus named
permissions. Starlette Admin is mounted only when explicitly enabled and only
resources listed in `admin.resources` are registered. The sample `records`
resource delegates to an application use case and repository port; ORM
discovery and catch-all model registration are not used.

The generated example is [examples/auth/project.yaml](../examples/auth/project.yaml).
Local login and unauthenticated `/api/me` rejection were exercised with a
generated service. OIDC and Firebase account flows remain configuration-only in
this environment; no external credentials or identity-provider calls were made.
