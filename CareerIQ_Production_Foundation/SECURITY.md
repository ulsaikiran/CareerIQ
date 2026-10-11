# Security policy and reporting

CareerIQ is currently a development/demo application. Do not upload real student records, government identifiers, private credentials or sensitive certificates until the production readiness gate is completed.

## Current safeguards

- Passwords are stored as password hashes.
- Mutating form requests require a CSRF token.
- Role checks are enforced server-side on protected routes.
- Certificate file extensions and file signatures are checked; uploads are size-limited and stored under random names.
- Certificate downloads require the owning student or faculty role.
- Recruiters see only students who have enabled recruitment visibility, and messages are rejected for hidden profiles.
- Exam monitoring is consent-gated; the browser sends event metadata only and does not upload camera frames.
- A minimal audit log records selected profile, certificate, recruiter-message and exam-alert review actions.
- Faculty/company registrations are pending until approved by the configured admin account.
- Password reset uses one-time hashed tokens with a 30-minute expiry; account lookup responses are generic. SMTP must be configured for delivery.
- Authenticated users can export their own data and request deletion of their account and active records.
- Optional GCS certificate storage, SMTP notification delivery, Vertex AI learning guidance and token-protected authorized job-feed ingestion are configurable; none is enabled by default.

## Known gaps

This release is not security-audited. It still uses SQLite and defaults to local file storage; the optional GCS adapter requires validation. Email verification, robust identity verification, distributed rate limiting, complete audit retention, malware scanning, verified data deletion across backups and end-to-end recovery testing remain outstanding. Browser-based exam monitoring can be bypassed or misclassify normal movement. Do not rely on it as a certified proctoring service.

## Reporting

For a real deployment, configure a private security contact and incident response procedure before collecting user data. Never publish vulnerabilities with live secrets, tokens, database files or personal documents attached.
