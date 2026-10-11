import os
import tempfile
import unittest

# Isolate the database for each test run before importing the application.
TMP = tempfile.TemporaryDirectory()
os.environ['DATABASE_PATH'] = os.path.join(TMP.name, 'test.db')
os.environ['UPLOAD_DIR'] = os.path.join(TMP.name, 'uploads')
os.environ['FLASK_SECRET_KEY'] = 'test-secret-key-for-automated-tests-only'

from app import app, init_db  # noqa: E402

class CareerIQTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def csrf(self):
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as sess:
            return sess['_csrf_token']

    def login(self, email, password):
        token = self.csrf()
        return self.client.post('/login', data={'email': email, 'password': password, '_csrf_token': token}, follow_redirects=True)

    def test_health(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['status'], 'ok')

    def test_demo_student_login(self):
        response = self.login('student@careeriq.demo', 'Student@123')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'STUDENT WORKSPACE', response.data)

    def test_role_protection(self):
        self.login('student@careeriq.demo', 'Student@123')
        response = self.client.get('/company/candidates')
        self.assertEqual(response.status_code, 403)

    def test_csrf_required(self):
        response = self.client.post('/logout')
        self.assertEqual(response.status_code, 400)


    def test_register_selected_faculty_role(self):
        token = self.csrf()
        response = self.client.post('/register', data={
            'name': 'Faculty Test', 'email': 'faculty.test@example.com',
            'password': 'SecurePass123!', 'confirm_password': 'SecurePass123!',
            'role': 'faculty', 'branch':'Computer Science', 'subject':'Cloud Computing', '_csrf_token': token
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'pending approval', response.data)
        import sqlite3
        db = sqlite3.connect(os.environ['DATABASE_PATH'])
        status = db.execute("SELECT account_status FROM users WHERE email='faculty.test@example.com'").fetchone()[0]
        db.close()
        self.assertEqual(status, 'pending')

    def test_register_selected_company_role(self):
        token = self.csrf()
        response = self.client.post('/register', data={
            'name': 'Company Test', 'email': 'company.test@example.com',
            'password': 'SecurePass123!', 'confirm_password': 'SecurePass123!',
            'role': 'company', '_csrf_token': token
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'pending approval', response.data)
        import sqlite3
        db = sqlite3.connect(os.environ['DATABASE_PATH'])
        status = db.execute("SELECT account_status FROM users WHERE email='company.test@example.com'").fetchone()[0]
        db.close()
        self.assertEqual(status, 'pending')

    def test_register_rejects_mismatched_passwords(self):
        token = self.csrf()
        response = self.client.post('/register', data={
            'name': 'Mismatch Test', 'email': 'mismatch@example.com',
            'password': 'SecurePass123!', 'confirm_password': 'DifferentPass123!',
            'role': 'student', 'branch':'Computer Science', 'section':'A', 'roll_no':'TEST001', '_csrf_token': token
        }, follow_redirects=True)
        self.assertIn(b'Passwords do not match', response.data)

    def test_student_can_save_and_unsave_opportunity(self):
        self.login('student@careeriq.demo', 'Student@123')
        token = self.csrf()
        with self.client.session_transaction() as sess:
            student_id = sess['uid']
        # Seed data includes an open internship; use its ID from the isolated test database.
        import sqlite3
        db = sqlite3.connect(os.environ['DATABASE_PATH'])
        row = db.execute("SELECT id FROM jobs WHERE status='Open' ORDER BY id LIMIT 1").fetchone()
        db.close()
        self.assertIsNotNone(row)
        jid = row[0]
        response = self.client.post(f'/saved-jobs/{jid}', data={'_csrf_token': token}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        db = sqlite3.connect(os.environ['DATABASE_PATH'])
        saved = db.execute('SELECT COUNT(*) FROM saved_jobs WHERE student_id=? AND job_id=?', (student_id, jid)).fetchone()[0]
        db.close()
        self.assertEqual(saved, 1)

    def test_exam_alert_requires_active_exam(self):
        self.login('student@careeriq.demo', 'Student@123')
        token = self.csrf()
        response = self.client.post('/exam/event', json={'event_type': 'head_turn', 'details': 'test'}, headers={'X-CSRF-Token': token})
        self.assertEqual(response.status_code, 400)

    def test_exam_start_and_alert(self):
        self.login('student@careeriq.demo', 'Student@123')
        token = self.csrf()
        response = self.client.post('/exam/start', headers={'X-CSRF-Token': token})
        self.assertEqual(response.status_code, 200)
        response = self.client.post('/exam/event', json={'event_type': 'head_turn', 'details': 'test turn'}, headers={'X-CSRF-Token': token})
        self.assertEqual(response.status_code, 200)

    def test_company_can_message_student_with_interview_link(self):
        self.login('company@careeriq.demo', 'Company@123')
        token = self.csrf()
        import sqlite3
        db = sqlite3.connect(os.environ['DATABASE_PATH'])
        row = db.execute("SELECT id FROM users WHERE email='student@careeriq.demo'").fetchone()
        db.close()
        response = self.client.post('/messages/send', data={
            'recipient_id': str(row[0]), 'body': 'Interview invitation',
            'interview_url': 'https://example.com/interview', '_csrf_token': token
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        db = sqlite3.connect(os.environ['DATABASE_PATH'])
        count = db.execute('SELECT COUNT(*) FROM messages WHERE recipient_id=?', (row[0],)).fetchone()[0]
        db.close()
        self.assertGreaterEqual(count, 1)


    def test_student_can_add_achievement_and_event(self):
        self.login('student@careeriq.demo', 'Student@123')
        token = self.csrf()
        response = self.client.post('/achievements', data={
            'title': 'Cloud Lab Challenge', 'category': 'Competition',
            'organization': 'College Tech Club', 'achieved_on': '2026-10-10',
            'description': 'Completed a cloud deployment challenge.', '_csrf_token': token
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Cloud Lab Challenge', response.data)
        response = self.client.post('/events', data={
            'title': 'Cloud Workshop', 'organizer': 'Department',
            'event_date': '2026-10-10', 'participation_type': 'Participant',
            'description': 'Attended a cloud workshop.', '_csrf_token': token
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Cloud Workshop', response.data)

    def test_student_can_hide_profile_from_company_directory(self):
        self.login('student@careeriq.demo', 'Student@123')
        token = self.csrf()
        response = self.client.post('/profile', data={
            'name': 'Aarav Student', 'department': 'Computer Science',
            'year': '3rd Year', 'target': 'Cloud Engineer',
            'skills': 'Python, Git', 'bio': 'Demo profile',
            '_csrf_token': token
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Profile saved', response.data)
        import sqlite3
        db = sqlite3.connect(os.environ['DATABASE_PATH'])
        row = db.execute("SELECT recruitment_visible FROM profiles JOIN users ON users.id=profiles.user_id WHERE users.email='student@careeriq.demo'").fetchone()
        db.close()
        self.assertEqual(row[0], 0)

    def test_faculty_can_review_exam_alert(self):
        self.login('student@careeriq.demo', 'Student@123')
        token = self.csrf()
        self.client.post('/exam/start', headers={'X-CSRF-Token': token})
        self.client.post('/exam/event', json={'event_type': 'head_turn', 'details': 'test'}, headers={'X-CSRF-Token': token})
        import sqlite3
        db = sqlite3.connect(os.environ['DATABASE_PATH'])
        row = db.execute("SELECT id FROM exam_alerts WHERE event_type='head_turn' ORDER BY id DESC LIMIT 1").fetchone()
        db.close()
        self.login('faculty@careeriq.demo', 'Faculty@123')
        token = self.csrf()
        response = self.client.post(f'/faculty/exam-alert/{row[0]}/review', data={'_csrf_token': token}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Reviewed', response.data)


    def test_pending_faculty_cannot_login(self):
        token = self.csrf()
        self.client.post('/register', data={
            'name': 'Pending Faculty', 'email': 'pending.faculty@example.com',
            'password': 'SecurePass123!', 'confirm_password': 'SecurePass123!',
            'role': 'faculty', 'branch':'Computer Science', 'subject':'Cloud Computing', '_csrf_token': token
        }, follow_redirects=True)
        response = self.login('pending.faculty@example.com', 'SecurePass123!')
        self.assertIn(b'awaiting faculty/admin approval', response.data)
        with self.client.session_transaction() as sess:
            self.assertNotIn('uid', sess)

    def test_student_can_export_own_data(self):
        self.login('student@careeriq.demo', 'Student@123')
        response = self.client.get('/account/export')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'application/json', response.content_type.encode())
        self.assertIn(b'careeriq.demo', response.data)


    def test_password_recovery_page_loads(self):
        response = self.client.get('/forgot-password')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'ACCOUNT RECOVERY', response.data)

    def test_account_privacy_page_requires_login(self):
        response = self.client.get('/account')
        self.assertIn(response.status_code, (302, 401))
        self.login('student@careeriq.demo', 'Student@123')
        response = self.client.get('/account')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Export my data', response.data)

    def test_register_student(self):
        token = self.csrf()
        response = self.client.post('/register', data={
            'name': 'Test Student', 'email': 'test.student@example.com',
            'password': 'SecurePass123!', 'confirm_password': 'SecurePass123!', 'role': 'student', 'branch':'Computer Science', 'section':'A', 'roll_no':'TEST001', '_csrf_token': token
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'STUDENT WORKSPACE', response.data)

if __name__ == '__main__':
    unittest.main()
