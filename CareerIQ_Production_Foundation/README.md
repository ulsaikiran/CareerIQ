# CareerIQ — Student Career & Industry Connect Platform

**Release candidate status: local demo / pre-production hardening. Not yet approved for real student data.** See [`PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md) for the explicit blockers. This release intentionally refuses `APP_ENV=production` until persistent PostgreSQL and private Cloud Storage adapters are implemented, rather than silently running with ephemeral storage.

A role-based college project built with Flask, SQLite, Jinja2, HTML/CSS and JavaScript. This enhanced release adds saved opportunities, read/unread notifications, assessment history, application-status alerts, exam camera/fullscreen monitoring, faculty exam alerts, certificate preview/download for faculty, direct recruiter messages with optional interview links, stricter certificate file checks and GitHub Actions checks. It is designed as a runnable local application with demo data and an upgrade path to Google Cloud; it is not represented as a production-ready service.

## Included features

- Separate student, faculty and company workspaces with server-side role checks.
- Password hashing, account registration, session clearing at login/logout, CSRF tokens for POST forms, security headers, upload-size limit and secure filenames.
- Student profile with administrator-controlled identity/career/skills fields, recruitment visibility preference, projects, achievements, event participation and certificate submission with private local file storage (PDF/PNG/JPG/JPEG).
- Branch-scoped faculty student directory (one student detail view at a time), certificate review and private file access, exam-alert review, and faculty-posted attendance/marks/SGPA/CGPA records with student notifications.
- Company job/internship posting, open/close controls, applicant status workflow, searchable candidate directory and direct student messages with optional HTTPS interview links.
- Opportunity search and duplicate-safe applications.
- Notifications created for students when a new posting matches at least one listed skill (or when the posting has no listed skills), with read/unread state and a mark-all-read action.
- Save/unsave job and internship opportunities for later, with duplicate-safe saved records.
- Student assessment history with visual score trends.
- Exam mode requests fullscreen and camera permission after the student explicitly consents. Browser-based face landmarks flag sustained possible head turns; fullscreen exits, hidden tabs, missing-face periods and camera stops can create faculty alerts. Camera frames are processed locally and are not uploaded or recorded by this application.
- Students can view recruiter messages and open optional interview links from their dashboard.
- Students receive in-app updates when faculty review certificates or companies change application status.
- Certificate uploads check allowed extensions and basic file signatures; uploads remain private and access-controlled.
- GitHub Actions workflow compiles Python and runs automated tests on pushes and pull requests.
- Faculty/company registrations are held pending approval; students can register and use their account immediately with branch, section and roll number. Configure `CAREERIQ_ADMIN_EMAIL` to a dedicated, secured existing account to expose the account-approval queue.
- Authenticated account data export (`/account/export`). Self-service account deletion is disabled; account removal is institution-administrator controlled.
- Optional private Google Cloud Storage adapter for certificate objects (`GCS_BUCKET`), optional SMTP email notifications, optional Vertex AI career guidance with rule-based fallback, and a token-protected normalized job-feed ingestion endpoint for authorized sources.
- Difficulty-weighted assessment scoring: Basic = 1, Intermediate = 2, Advanced = 3. Time taken does not affect the score.
- Explainable, rule-based career roadmap and skill-gap recommendations.
- Health endpoint at `/health`, Docker starter and automated tests.

## Run locally (Windows PowerShell)

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal and activate again. Open `http://127.0.0.1:5000`.

## Sign-in and registration troubleshooting (Release 1.4.1)

- The local development startup repairs the three reserved demo accounts and sets them to `approved`, including existing databases where the demo faculty/company accounts had been left pending by an earlier approval migration. Restart the application after replacing the source files.
- Demo credentials: `student@careeriq.demo` / `Student@123`; `faculty@careeriq.demo` / `Faculty@123`; `company@careeriq.demo` / `Company@123`.
- The registration form now reveals the correct fields when the role changes: students must enter branch, section and roll number; faculty must enter branch and subject; company registrations explain that administrator approval is required.
- The application uses the database beside `app.py` by default. If you run a different extracted copy, that copy may have a different `careeriq.db`. Check `DATABASE_PATH` if you intentionally configured a custom database.
- Demo credential repair is development-only and is skipped when `APP_ENV=production`. Never expose these reserved demo accounts on a public service.

## Demo accounts

The application now repairs/ensures these reserved demo accounts at startup, including when upgrading a database that already contains other users.

| Role | Email | Password |
|---|---|---|
| Student | `student@careeriq.demo` | `Student@123` |
| Faculty | `faculty@careeriq.demo` | `Faculty@123` |
| Company | `company@careeriq.demo` | `Company@123` |

Demo accounts and seeded content are fictional. The local college demo lets a registrant choose Student, Faculty / Teacher, or Company / Recruiter. This role selector is for demonstration only: before public deployment, faculty and company roles must require administrator approval or invitation so users cannot grant themselves elevated access.

## Automated tests

```powershell
python -m unittest discover -s tests -v
```

Install dependencies first. Tests use an isolated temporary SQLite database and do not touch the main local database.

## Optional integrations

- Set `PUBLIC_BASE_URL` to the canonical HTTPS application URL so password-reset emails cannot be influenced by an untrusted request Host header.

- **Account approval:** set `CAREERIQ_ADMIN_EMAIL` to a secured account email. Faculty/company registrations stay pending until approved. Do not use a shared or public mailbox.
- **Private certificate storage:** set `GCS_BUCKET` and grant the runtime service account least-privilege access. Do not make the bucket public. Install dependencies from `requirements.txt`.
- **Vertex AI:** set `GOOGLE_CLOUD_PROJECT`, `VERTEX_AI_ENABLED=1`, and a supported `VERTEX_AI_LOCATION`; use Application Default Credentials/service account identity. The system falls back to rule-based roadmap output on service failure. Review generated suggestions before relying on them.
- **Email:** configure SMTP variables via secret manager/environment. Email is best-effort; in-app notifications remain authoritative.
- **Authorized job feeds:** configure `JOB_FEED_TOKEN` and `JOB_FEED_COMPANY_EMAIL`. A trusted provider/scheduler may POST `{\"jobs\":[{\"title\":\"...\",\"kind\":\"Job\",\"description\":\"...\",\"skills\":\"Python, SQL\",\"eligibility\":\"...\",\"location\":\"Remote\"}]}` to `/integrations/job-feed` with header `X-Job-Feed-Token`. Use only sources whose terms explicitly permit ingestion; this endpoint does not scrape third-party websites.

## Environment variables

Copy `.env.example` to `.env` for reference, but the app does not automatically load `.env`; export variables in your shell or deployment platform. Set a long random `FLASK_SECRET_KEY`, `DATABASE_PATH`, `UPLOAD_DIR`, and set `COOKIE_SECURE=1` when served over HTTPS. Never commit real secrets or personal documents.

## Production readiness

This release is not production-ready. SQLite-specific persistence remains and `APP_ENV=production` deliberately fails closed until a tested Cloud SQL for PostgreSQL adapter is integrated. Optional GCS certificate storage, Vertex AI guidance, SMTP email, authorized job-feed ingestion, account approval, password-reset flow and authenticated personal-data export/deletion have been added. SMS/push delivery, email verification, malware scanning, distributed rate limiting, migrations and full security/browser tests remain outstanding. Review [`PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md), [`SECURITY.md`](SECURITY.md), and [`DEPLOYMENT_NOTES.md`](DEPLOYMENT_NOTES.md) before deployment.

## Google Cloud deployment notes

The included Dockerfile is a container starting point, not a complete managed-database deployment. **Do not use local SQLite or local file uploads as durable storage on Cloud Run.** Cloud Run instances can be replaced and local files are ephemeral. Before a reliable cloud deployment, migrate persistence to Cloud SQL for PostgreSQL, store uploaded certificates in a private Cloud Storage bucket, grant the Cloud Run service account least-privilege access, and keep secrets in Secret Manager. Use HTTPS, configure CORS if a separate frontend is introduced, enable logs/monitoring, set budget alerts, and test restore/access policies. Cloud resources can incur charges.

## Current limitations (honest scope)

- Career roadmaps remain deterministic by default. Optional Vertex AI adds supplemental learning guidance when explicitly enabled and configured; it is not a hiring decision engine.
- Vacancy alerts are generated from in-app company postings and from normalized postings sent by a configured authorized feed integration. No scraping of third-party websites is performed.
- Certificate status is faculty-reviewed; the app does not independently verify an issuer or certificate authenticity.
- The local assessment uses a fixed question bank. Camera monitoring uses a third-party MediaPipe Face Mesh script loaded from a CDN and requires network access. Detection can fail or generate false alerts due to lighting, camera placement, disability/accessibility needs or normal movement; alerts are not proof of misconduct. Browser fullscreen cannot be made unbreakable, and this implementation is not a certified remote-proctoring system.
- Camera access requires explicit user permission and a secure browser context (HTTPS or localhost). The app sends event metadata only, not camera video or images.
- Notifications are stored in-app. SMTP email is optional/best-effort; SMS and push delivery are not configured.
- SQLite is suitable for a local single-instance demonstration, not a multi-instance production deployment.

Never use this demo to make high-stakes hiring decisions. Obtain consent for personal data, show students what companies can view, and provide correction/appeal workflows before real deployment.

## Branch-aware academic governance (Release 1.4 candidate)

- Student registration requires **branch, section and roll number**. Duplicate roll numbers within a branch are rejected. Student identity fields are read-only in the student profile; correction requests go through the administrator.
- Faculty registration requires **branch and subject** and remains pending until the configured administrator approves it. Company accounts also remain pending until approval.
- Faculty student lists, certificate queues, exam-alert queues, academic-record creation, and student-detail access are restricted to matching branches (case-insensitive). Faculty sees an individual student's academic detail only after opening that student's record.
- Faculty may post new attendance, marks, SGPA and CGPA records. Existing academic records can only be corrected by the administrator. Changes create an in-app notification for the student and an audit event.
- The administrator console is available at `/admin` only when `CAREERIQ_ADMIN_EMAIL` exactly matches the signed-in account email. Create/verify the intended admin account out-of-band, set that environment variable, and protect the account with a unique strong password. The configured administrator can view account details, approve/suspend accounts, correct student identity records and correct academic records.
- Account deletion is not self-service. Student and faculty users must contact the institution administrator.
- Certificates are categorized as Participation, Winning, Subject, or Skill Test. Project entries support repository URL, live demo URL, tech stack and contribution notes.
- The assessment generator creates 50 randomized template-based questions for Python, Java, C, SQL, HTML or Cloud Computing. It is a local question-template generator, not an LLM-generated question bank. A score of 60% or more generates a platform-issued, printable skill certificate; below 60%, the student is prompted to follow a learning roadmap and retake the exam. Certificate wording explicitly avoids claiming external accreditation.

### Important deployment note

This is still a **pre-production candidate**. The existing production guard intentionally blocks `APP_ENV=production` until a tested PostgreSQL/Cloud SQL adapter and deployment verification are available. Run the automated tests in CI and conduct browser/device, privacy, access-control, backup/restore and security testing before real student records are used.

### Administrator access for local demonstration

On Windows PowerShell, before launching `python app.py`, you may temporarily use the demo faculty account as the administrator:

```powershell
$env:CAREERIQ_ADMIN_EMAIL = "faculty@careeriq.demo"
python app.py
```

Sign in with the documented demo faculty credentials, then open `/admin`. This is for local evaluation only. Never use the demo password or demo administrator configuration on a public deployment; create a dedicated administrator identity and store its configuration securely.
