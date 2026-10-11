# CareerIQ Production Readiness Gate

## Status: NOT APPROVED FOR REAL STUDENT DATA

This release adds more complete college-demo workflows and blocks `APP_ENV=production` startup rather than silently deploying an ephemeral SQLite database and local file uploads to Cloud Run. That is an intentional safety gate, not a deployment bug.

## Included application workflows

- Student, faculty and company workspaces with server-side role checks.
- Student profile, career target, skills, projects, certificates, achievements, event participation, assessment history and difficulty-weighted skill checks.
- Explainable rule-based career roadmap and skill-gap coverage.
- Opportunity search, saving, applications, status tracking and in-app matching notifications based on in-app company postings.
- Faculty student records, academic score updates, certificate file review, certificate status changes and reviewable exam-monitoring alerts.
- Company opportunity publishing, candidate discovery (subject to each student's recruitment visibility setting), applications review and direct messages with optional HTTPS interview links.
- Camera consent, fullscreen request, browser-side possible-head-turn signals, tab/fullscreen/camera event metadata. No video is uploaded or stored by this app.
- CSRF validation, password hashing, upload size limits, signature checks, security headers, basic audit log events and GitHub Actions tests.

## Required before production approval

1. **Persistent database:** implement and test a PostgreSQL adapter/migrations for Cloud SQL. The current code uses SQLite-specific SQL and cannot run in production mode.
2. **Private object storage:** the optional GCS adapter exists but must be tested against a private bucket with least-privilege IAM, malware scanning, retention and deletion policies. Local uploads remain the default for development.
3. **Identity and account approval:** faculty/company registrations now require admin approval using `CAREERIQ_ADMIN_EMAIL`; password reset is implemented using one-time hashed tokens when SMTP is configured; email verification and stronger identity verification remain missing.
4. **Secret management:** inject a random `FLASK_SECRET_KEY` through Secret Manager; never bake it into images or source.
5. **Operational security:** add distributed login/endpoint rate limits, structured logs, audit retention, alerting, vulnerability scanning, dependency lockfiles/SBOM, backups and restore drills.
6. **Privacy and consent:** publish a privacy notice, document purpose and retention, provide export/deletion/correction workflows, define student consent for recruiter visibility and camera monitoring, and review applicable local law/institutional policies.
7. **Exam integrity/accessibility:** browser fullscreen cannot be enforced absolutely. Head-turn detection is probabilistic and can be wrong. Provide accommodations and human review; never automatically penalize a student based on an alert alone. Add device/browser QA and a fallback assessment mode.
8. **External services:** optional Vertex AI, SMTP and token-protected normalized job-feed ingestion adapters are present but require cloud credential and integration tests. SMS, push and calendar integrations remain missing; only ingest from sources whose terms permit it.
9. **Testing:** run full integration tests, security tests, upload abuse tests, concurrency tests, database migration tests and browser end-to-end tests in CI/staging. Verify the latest CI run before release.
10. **Cloud infrastructure:** provision Cloud Run, Cloud SQL, private Cloud Storage, service accounts, Secret Manager, logging/monitoring, budget alerts, backups and disaster recovery using reviewed infrastructure-as-code.

## Local verification

```bash
python -m venv .venv
# Activate the environment, then:
python -m pip install -r requirements.txt
python -m compileall -q app.py tests
python -m unittest discover -s tests -v
```

The build environment used to prepare this archive had no network access, so Flask could not be installed and the integration suite could not be executed here. Static Python compilation and Jinja parsing were run; they are not a substitute for the integration tests.
