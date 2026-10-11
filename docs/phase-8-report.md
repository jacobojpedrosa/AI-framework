# Phase 8 report: file storage

Phase 8 adds a provider-neutral file contract with metadata, tenant-scoped
keys, maximum object size, content-type validation, atomic local writes and
delete idempotency. The local adapter rejects traversal, absolute paths,
empty path segments and symlink escapes. The S3 adapter uses an injected
boto-compatible client and keeps bucket credentials outside the domain.

`gcs` and `azure-blob` remain declared configuration choices but fail clearly
at scaffolding time until their adapters are added. This preserves the shared
port and avoids pretending that untested cloud integrations are complete.

The local contract was exercised in a generated service: put/get/delete,
tenant separation, size validation and traversal rejection all passed.
