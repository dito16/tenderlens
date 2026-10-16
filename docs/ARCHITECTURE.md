# Architecture and data boundaries

Input PDF -> security preflight/limits -> PyMuPDF page extraction -> candidate
facts and conservative comparative questions -> SQLite local audit trail ->
Flask on 127.0.0.1 -> optional human review -> JSON/CSV/HTML export.

Fact evidence stores source document SHA256, physical page number,
normalized text span and quoted context. These links demonstrate source
provenance but **not** legal validity, which edition is effective, or truth
on unknown third-party documents. Reviewer corrections append to a journal;
they do not overwrite original extracted evidence.

Cross-document comparisons attempt to respect scope, revision, day-count
units and payment triggers; when metadata is unknown, differences are
presented as questions. Wrong automatic positive assertions about price,
SRO obligations or deadlines are release blockers. Data stays on the user's
machine, not published or uploaded to third-party servers.

## Development server warning

`127.0.0.1` only, single-user, no LAN/production deployment. CSRF and path
hardening are defense in depth but are not a complete production threat model.
Use a proper WSGI deployment and independent security assessment for any
future production product; this release does not authorize such deployment.
