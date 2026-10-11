# CareerIQ changelog

## Remaining-features release — 1.3 (2026-10-11)

- Added approval status for new faculty/company registrations; they cannot sign in until approved.
- Added a protected admin approval queue configured by `CAREERIQ_ADMIN_EMAIL`.
- Added one-time, 30-minute password reset tokens stored as hashes, with generic responses to reduce account enumeration.
- Added authenticated personal-data JSON export and password-confirmed account deletion with best-effort certificate object/file cleanup.
- Added optional private Google Cloud Storage adapter for certificate uploads/downloads.
- Added optional SMTP delivery for recruiter messages, account approval and exam review alerts.
- Added optional Vertex AI career-learning guidance with a rule-based fallback.
- Added a token-protected ingestion endpoint for normalized job listings from authorized sources, with duplicate avoidance and skill-match notifications.
- Added account settings UI, account recovery UI, configuration examples and additional tests.
- Kept production startup blocked until Cloud SQL/PostgreSQL persistence is integrated and tested.


## Next-level release — 1.2

- Added a consent gate before exam monitoring; assessment start requests camera access and fullscreen mode.
- Added browser-local MediaPipe face-landmark processing and sustained head-turn alerts, plus events for camera stop, missing face, tab hidden and fullscreen exit. No video/image is sent to the server.
- Added faculty exam-alert dashboard feed with student and event details.
- Added faculty view/download links for submitted certificate files.
- Added company-to-student direct messages with optional HTTPS interview links, plus student inbox and read state.
- Added tests for exam alert access and recruiter interview messages.
- Documented browser, privacy, accessibility and deployment limitations.


## Enhanced release — 1.1

- Added save/unsave controls for open opportunities and a saved-opportunities dashboard section.
- Added read/unread notification presentation and a mark-all-read action.
- Notify students when certificate reviews and company application decisions change.
- Added a visual history of recent difficulty-weighted assessment results.
- Restrict public account registration to students; faculty/company accounts require controlled provisioning.
- Validate basic PDF/PNG/JPEG file signatures in addition to the filename extension.
- Added a GitHub Actions workflow for Python compilation and automated tests.
- Updated README and cloud deployment notes to reflect current features and remaining production work.

## Important scope notes

This remains a college demonstration app. The Cloud Run starter does not yet include Cloud SQL or Cloud Storage integration, external vacancy feeds, real Vertex AI integration, email/push delivery, or browser/camera proctoring. Do not deploy it with real student records until those items and privacy/access controls are addressed.


## Production hardening candidate (2026-10-11)

- Added student achievement and event participation records to the profile workspace.
- Added a student-controlled recruitment visibility setting and enforced it in the recruiter directory and direct-message route.
- Added faculty actions to mark exam alerts reviewed.
- Added minimal audit events for profile updates, certificate reviews, achievements, events, recruiter messages and exam-alert reviews.
- Hardened assessment submission so answers cannot be submitted through the normal route without an active exam session.
- Added an explicit production startup gate: the current SQLite/local-upload implementation must not silently run as a production Cloud Run service.
- Added production readiness and security documentation describing remaining blockers and required Google Cloud architecture.
- Expanded automated tests for achievements/events, recruiter visibility and exam-alert review.

## Release 1.4 candidate — Branch governance and academic integrity
- Added student branch/section/roll number and faculty branch/subject registration fields.
- Added a dedicated administrator console with account-level detail, approval/suspension controls, student identity correction, and academic record correction.
- Restricted faculty views, certificate access, exam alerts and academic record creation to the faculty member's branch.
- Locked student identity fields from student self-edit and blocked faculty from overwriting existing academic records.
- Added faculty-posted attendance, marks, SGPA and CGPA with student notifications and audit records; administrator corrections notify students.
- Added separate Participation, Winning, Subject and Skill Test certificate categories.
- Added GitHub-style project metadata fields and resume view for students/recruiters.
- Added subject-selectable 50-question randomized assessments and printable platform-issued certificates on passing.


## Release 1.4.1 — Sign-in and registration fixes

- Development startup repairs reserved demo passwords and explicitly resets demo account status to `approved`, fixing demo faculty/company sign-ins after older approval migrations.
- Registration now renders student branch, section and roll-number fields and faculty branch and subject fields, with role-aware show/hide and required validation.
- Added global `[hidden]` CSS handling so conditional registration fields stay hidden consistently.
- Documented troubleshooting for stale database copies and the `DATABASE_PATH` setting.
