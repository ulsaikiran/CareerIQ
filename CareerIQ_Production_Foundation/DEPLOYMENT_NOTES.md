# Deployment status and Google Cloud path

## Current status

This archive is a local release candidate, **not approved for production**. Setting `APP_ENV=production` deliberately stops startup because the current implementation uses SQLite and local certificate files. Those storage choices are not durable or safe for multi-instance Cloud Run.

## Required Google Cloud architecture

- **Cloud Run:** stateless web application container.
- **Cloud SQL for PostgreSQL:** persistent relational data, migrations and automated backups.
- **Private Cloud Storage bucket:** optional certificate object adapter is implemented; validate bucket IAM, object lifecycle, malware scanning and delete behavior before use.
- **Secret Manager:** Flask session secret and any integration credentials.
- **Cloud Logging / Monitoring:** structured logs, service health, latency/error alerts.
- **Cloud Scheduler + authorized feeds:** scheduled opportunity refresh only from permitted APIs/data sources.
- **Vertex AI (optional):** optional personalized learning guidance with rule-based fallback; enable only after privacy, safety, evaluation and cost controls are designed.
- **Pub/Sub (optional):** asynchronous notifications/jobs if scale requires it.

## Deployment prerequisites

1. Replace SQLite-specific connection/query code with a PostgreSQL adapter and versioned migrations.
2. Replace local file writes with Cloud Storage upload/download and test authorization.
3. Add admin-controlled faculty/company approval; public registration should create students only.
4. Create a dedicated service account with minimum required IAM roles.
5. Set secrets through Secret Manager; enable HTTPS-only secure cookies and appropriate trusted-host configuration.
6. Run all unit, integration, security, migration, upload and browser end-to-end tests in CI/staging.
7. Configure budget alerts, backup/restore drills, retention/deletion procedures and incident response.

## Local container smoke test (development only)

```bash
docker build -t careeriq .
docker run --rm -p 8080:8080 -e PORT=8080 -e FLASK_SECRET_KEY="use-a-random-local-secret-of-at-least-32-characters" careeriq
```

Do not set `APP_ENV=production` until the PostgreSQL and Cloud Storage adapters are implemented and tested. Cloud resources can incur charges.

## Release 1.4 candidate notes

Set `CAREERIQ_ADMIN_EMAIL` to the email address of a dedicated, secured existing account to enable `/admin`. For local demonstration only, the existing `faculty@careeriq.demo` account can be used as the administrator by setting that variable before starting the app. Do not use demo credentials for a public deployment. The configured admin account is treated as a superuser across branches, while ordinary faculty access remains branch-scoped.

New student registrations require branch, section, roll number, and a desired career target. Faculty registration requires branch and subject and stays pending until approved. Existing legacy faculty/company accounts are moved to pending once by the migration marker unless they are the configured administrator or reserved demo accounts; review and approve them explicitly in the admin console.

The exam question engine is a randomized template-based demo. For a real institution, replace its template bank with a curated, reviewed question repository or a validated generation service, add answer-quality review, and audit fairness/accessibility before using results for high-stakes decisions.
