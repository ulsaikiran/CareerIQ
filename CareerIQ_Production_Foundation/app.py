import os, sqlite3, secrets, re
from functools import wraps
from pathlib import Path
from flask import Flask, g, session, request, redirect, url_for, flash, render_template, abort, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import json, smtplib, ssl, hashlib, random, time, itertools
from email.message import EmailMessage

ROOT = Path(__file__).resolve().parent
DB_PATH = os.environ.get('DATABASE_PATH', str(ROOT / 'careeriq.db'))
UPLOAD_DIR = Path(os.environ.get('UPLOAD_DIR', str(ROOT / 'private_uploads')))
ALLOWED_UPLOADS = {'pdf', 'png', 'jpg', 'jpeg'}
GCS_BUCKET = os.environ.get('GCS_BUCKET', '').strip()
CAREERIQ_ADMIN_EMAIL = os.environ.get('CAREERIQ_ADMIN_EMAIL', '').strip().lower()
JOB_FEED_TOKEN = os.environ.get('JOB_FEED_TOKEN', '').strip()
APP_ENV = os.environ.get('APP_ENV', 'development').strip().lower()
app = Flask(__name__)
_secret = os.environ.get('FLASK_SECRET_KEY')
if APP_ENV == 'production' and (not _secret or len(_secret) < 32):
    raise RuntimeError('Production startup blocked: set FLASK_SECRET_KEY to a random value of at least 32 characters in Secret Manager.')
app.secret_key = _secret or 'local-only-change-me-' + secrets.token_hex(24)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('COOKIE_SECURE','0') == '1'
app.config['MAX_CONTENT_LENGTH'] = 3 * 1024 * 1024
CAREERS = {
 'Cloud Engineer': ['Linux','Networking','Python','Git','Cloud Fundamentals','Docker'],
 'Python Developer': ['Python','SQL','Git','REST APIs','Testing'],
 'Web Developer': ['HTML','CSS','JavaScript','Python','SQL','Git'],
 'Data Analyst': ['SQL','Python','Excel','Statistics','Data Visualization']
}

def conn():
    db = sqlite3.connect(DB_PATH); db.row_factory = sqlite3.Row; db.execute('PRAGMA foreign_keys=ON'); return db

def init_db():
    db = conn()
    db.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('student','faculty','company')), account_status TEXT NOT NULL DEFAULT 'approved', branch TEXT DEFAULT '', section TEXT DEFAULT '', roll_no TEXT DEFAULT '', subject TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS profiles(user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, department TEXT DEFAULT 'Computer Science', year TEXT DEFAULT '3rd Year', target TEXT DEFAULT 'Cloud Engineer', skills TEXT DEFAULT '', score REAL DEFAULT 8.0, bio TEXT DEFAULT '', recruitment_visible INTEGER NOT NULL DEFAULT 1 CHECK(recruitment_visible IN (0,1)));
    CREATE TABLE IF NOT EXISTS certificates(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES users(id), title TEXT NOT NULL, issuer TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending','Verified','Rejected')), file_name TEXT DEFAULT '', stored_name TEXT DEFAULT '', category TEXT NOT NULL DEFAULT 'Subject');
    CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, title TEXT NOT NULL, message TEXT NOT NULL, read_at TEXT DEFAULT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES users(id), title TEXT NOT NULL, description TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL REFERENCES users(id), title TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('Job','Internship')), description TEXT DEFAULT '', skills TEXT DEFAULT '', eligibility TEXT DEFAULT '', location TEXT DEFAULT 'Not specified', status TEXT NOT NULL DEFAULT 'Open' CHECK(status IN ('Open','Closed')));
    CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, status TEXT NOT NULL DEFAULT 'Applied' CHECK(status IN ('Applied','Under Review','Shortlisted','Rejected','Selected')), created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(job_id,student_id));
    CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY, topic TEXT, difficulty TEXT CHECK(difficulty IN ('Basic','Intermediate','Advanced')), question TEXT, a TEXT, b TEXT, c TEXT, d TEXT, answer TEXT, explanation TEXT);
    CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, student_id INTEGER REFERENCES users(id), score REAL, correct_count INTEGER, total_count INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, subject TEXT DEFAULT 'General');
    CREATE TABLE IF NOT EXISTS saved_jobs(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(student_id,job_id));
    CREATE TABLE IF NOT EXISTS exam_alerts(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, event_type TEXT NOT NULL, details TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, reviewed_at TEXT DEFAULT NULL);
    CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, recipient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, body TEXT NOT NULL, interview_url TEXT DEFAULT '', read_at TEXT DEFAULT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS achievements(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, title TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'Achievement', organization TEXT DEFAULT '', achieved_on TEXT DEFAULT '', description TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, title TEXT NOT NULL, organizer TEXT DEFAULT '', event_date TEXT DEFAULT '', participation_type TEXT DEFAULT 'Participant', description TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL, action TEXT NOT NULL, target_type TEXT DEFAULT '', target_id TEXT DEFAULT '', details TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS password_resets(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, token_hash TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL, used_at TEXT DEFAULT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS academic_records(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, faculty_id INTEGER NOT NULL REFERENCES users(id), record_type TEXT NOT NULL CHECK(record_type IN ('Attendance','Marks','SGPA','CGPA')), subject TEXT DEFAULT '', value TEXT NOT NULL, term TEXT DEFAULT '', note TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS skill_certificates(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, subject TEXT NOT NULL, score REAL NOT NULL, correct_count INTEGER NOT NULL, total_count INTEGER NOT NULL, certificate_code TEXT UNIQUE NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS project_links(id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE, repo_url TEXT DEFAULT '', live_url TEXT DEFAULT '', tech_stack TEXT DEFAULT '', role_description TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS exam_sessions(token TEXT PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, subject TEXT NOT NULL, questions_json TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0, expires_at TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP);
    ''')
    # Safe additive migrations for databases created by earlier CareerIQ versions.
    user_columns={r['name'] for r in db.execute('PRAGMA table_info(users)').fetchall()}
    if 'account_status' not in user_columns: db.execute("ALTER TABLE users ADD COLUMN account_status TEXT NOT NULL DEFAULT 'approved'")
    for col in ('branch','section','roll_no','subject'):
        if col not in user_columns: db.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT ''")
    cert_columns={r['name'] for r in db.execute('PRAGMA table_info(certificates)').fetchall()}
    if 'category' not in cert_columns: db.execute("ALTER TABLE certificates ADD COLUMN category TEXT NOT NULL DEFAULT 'Subject'")
    attempt_columns={r['name'] for r in db.execute('PRAGMA table_info(attempts)').fetchall()}
    if 'subject' not in attempt_columns: db.execute("ALTER TABLE attempts ADD COLUMN subject TEXT DEFAULT 'General'")
    db.execute("UPDATE users SET branch=COALESCE(NULLIF(branch,''),(SELECT department FROM profiles WHERE profiles.user_id=users.id),'') WHERE role='student' AND (branch IS NULL OR trim(branch)='')")
    profile_columns={r['name'] for r in db.execute('PRAGMA table_info(profiles)').fetchall()}
    if 'recruitment_visible' not in profile_columns: db.execute('ALTER TABLE profiles ADD COLUMN recruitment_visible INTEGER NOT NULL DEFAULT 1')
    cert_columns={r['name'] for r in db.execute('PRAGMA table_info(certificates)').fetchall()}
    if 'file_name' not in cert_columns: db.execute("ALTER TABLE certificates ADD COLUMN file_name TEXT DEFAULT ''")
    if 'stored_name' not in cert_columns: db.execute("ALTER TABLE certificates ADD COLUMN stored_name TEXT DEFAULT ''")
    # One-time hardening of legacy accounts: older releases may have had approved faculty/company users before admin approval existed.
    if not db.execute("SELECT 1 FROM schema_migrations WHERE version='branch-approval-gate-1'").fetchone():
        db.execute("UPDATE users SET account_status='pending' WHERE role IN ('faculty','company') AND email NOT LIKE '%@careeriq.demo' AND lower(email)<>?",(CAREERIQ_ADMIN_EMAIL,))
        db.execute("INSERT INTO schema_migrations(version) VALUES('branch-approval-gate-1')")
    if db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
        db.executemany('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)', [
          ('Aarav Student','student@careeriq.demo',generate_password_hash('Student@123'),'student'),
          ('Dr. Meera Faculty','faculty@careeriq.demo',generate_password_hash('Faculty@123'),'faculty'),
          ('Nova Tech HR','company@careeriq.demo',generate_password_hash('Company@123'),'company')])
        sid=db.execute("SELECT id FROM users WHERE email='student@careeriq.demo'").fetchone()['id']; cid=db.execute("SELECT id FROM users WHERE email='company@careeriq.demo'").fetchone()['id']
        db.execute('INSERT INTO profiles(user_id,department,year,target,skills,score,bio) VALUES(?,?,?,?,?,?,?)',(sid,'Computer Science','3rd Year','Cloud Engineer','Python, Git, Linux, HTML, CSS',8.4,'Interested in cloud platforms and practical software projects.'))
        db.executemany('INSERT INTO certificates(student_id,title,issuer,status) VALUES(?,?,?,?)',[(sid,'Python Fundamentals','Demo Learning Academy','Verified'),(sid,'Cloud Foundations','Demo Cloud Academy','Pending')])
        db.executemany('INSERT INTO projects(student_id,title,description) VALUES(?,?,?)',[(sid,'CareerIQ Prototype','A student-to-industry career platform.'),(sid,'Portfolio Website','A responsive personal portfolio.')])
        db.executemany('INSERT INTO jobs(company_id,title,kind,description,skills,eligibility,location) VALUES(?,?,?,?,?,?,?)',[
          (cid,'Cloud Support Intern','Internship','Assist with cloud labs, Linux basics and documentation.','Linux, Networking, Cloud Fundamentals','Basic Linux and networking knowledge','Hybrid'),
          (cid,'Python Developer Intern','Internship','Build and test small Python web features.','Python, SQL, Git','Basic Python and database knowledge','Remote'),
          (cid,'Junior Web Developer','Job','Help develop internal web tools.','HTML, CSS, JavaScript, Python','Portfolio or academic projects preferred','Vijayawada')])
        qs=[('Cloud','Basic','Which service model provides virtual machines?','SaaS','IaaS','FaaS','DaaS','b','IaaS provides infrastructure such as virtual machines.'),('Python','Basic','Which keyword defines a Python function?','func','define','def','function','c','Python functions are declared with def.'),('Web','Basic','Which HTML element creates a hyperlink?','<link>','<a>','<href>','<url>','b','The anchor element creates a hyperlink.'),('Database','Intermediate','Which SQL clause filters rows before grouping?','ORDER BY','HAVING','WHERE','LIMIT','c','WHERE filters rows before grouping.'),('Cloud','Intermediate','What is a cloud region?','A billing account','A geographic area containing cloud zones','A user role','A programming language','b','Regions are geographic locations containing zones.'),('Python','Intermediate','What does a Python dictionary store?','Only numbers','Key-value pairs','Only strings','Compiled classes','b','Dictionaries map keys to values.'),('Web','Advanced','Which HTTP status commonly indicates resource creation?','200','201','301','404','b','201 Created indicates a resource was created.'),('Cloud','Advanced','Which practice follows least privilege?','Give everyone admin','Share one account','Grant only necessary permissions','Disable logs','c','Least privilege limits permissions to what is needed.'),('Database','Advanced','What does a foreign key help enforce?','CSS layout','Referential integrity','Password hashing','HTTP caching','b','Foreign keys enforce valid record relationships.')]
        db.executemany('INSERT INTO questions(topic,difficulty,question,a,b,c,d,answer,explanation) VALUES(?,?,?,?,?,?,?,?,?)',qs)
    # Demo accounts are strictly development-only; never seed/reset credentials in production.
    if APP_ENV == 'production':
        db.commit(); db.close(); return
    # Always ensure demo credentials exist, even when upgrading an older database
    # that already contains other users. Reset these reserved demo accounts to the
    # documented passwords so the README credentials remain dependable locally.
    demo_users = [
        ('Aarav Student','student@careeriq.demo','Student@123','student'),
        ('Dr. Meera Faculty','faculty@careeriq.demo','Faculty@123','faculty'),
        ('Nova Tech HR','company@careeriq.demo','Company@123','company'),
    ]
    for demo_name, demo_email, demo_password, demo_role in demo_users:
        existing = db.execute('SELECT id FROM users WHERE email=?', (demo_email,)).fetchone()
        if existing:
            db.execute("UPDATE users SET name=?, password_hash=?, role=?, account_status='approved' WHERE id=?",
                       (demo_name, generate_password_hash(demo_password), demo_role, existing['id']))
        else:
            db.execute("INSERT INTO users(name,email,password_hash,role,account_status) VALUES(?,?,?,?, 'approved')",
                       (demo_name, demo_email, generate_password_hash(demo_password), demo_role))
    db.execute("UPDATE users SET branch='Computer Science',section='A',roll_no='DEMO001' WHERE email='student@careeriq.demo'")
    db.execute("UPDATE users SET branch='Computer Science',subject='Cloud Computing' WHERE email='faculty@careeriq.demo'")
    student_demo_id = db.execute("SELECT id FROM users WHERE email='student@careeriq.demo'").fetchone()['id']
    if not db.execute('SELECT 1 FROM profiles WHERE user_id=?', (student_demo_id,)).fetchone():
        db.execute('INSERT INTO profiles(user_id) VALUES(?)', (student_demo_id,))
    db.commit(); db.close()

@app.before_request
def open_db():
    g.db = conn()
    if request.method == 'POST':
        expected=session.get('_csrf_token','')
        supplied=request.form.get('_csrf_token','') or request.headers.get('X-CSRF-Token','')
        if not expected or not secrets.compare_digest(expected,supplied):
            abort(400, description='Invalid or missing security token. Refresh the page and try again.')

@app.teardown_request
def close_db(error=None):
    db=g.pop('db',None)
    if db: db.close()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        if not session.get('uid'): flash('Please sign in first.','warning'); return redirect(url_for('login'))
        return fn(*args,**kwargs)
    return wrapper

def roles(*allowed):
    def dec(fn):
        @wraps(fn)
        def wrapper(*args,**kwargs):
            if not session.get('uid'): return redirect(url_for('login'))
            if session.get('role') not in allowed: abort(403)
            return fn(*args,**kwargs)
        return wrapper
    return dec

def user():
    return g.db.execute('SELECT id,name,email,role,branch,section,roll_no,subject,account_status FROM users WHERE id=?',(session['uid'],)).fetchone() if session.get('uid') else None

def audit(action, target_type='', target_id='', details=''):
    actor = session.get('uid')
    g.db.execute('INSERT INTO audit_log(actor_id,action,target_type,target_id,details) VALUES(?,?,?,?,?)',
                 (actor, action[:100], target_type[:80], str(target_id)[:100], details[:500]))


@app.context_processor
def globals_for_templates():
    if '_csrf_token' not in session: session['_csrf_token']=secrets.token_urlsafe(32)
    return {'me':user(), 'csrf_token':session['_csrf_token'], 'is_admin': bool(user() and CAREERIQ_ADMIN_EMAIL and user()['email'].lower()==CAREERIQ_ADMIN_EMAIL)}

@app.after_request
def headers(response):
    response.headers['X-Content-Type-Options']='nosniff'; response.headers['X-Frame-Options']='SAMEORIGIN'; response.headers['Referrer-Policy']='strict-origin-when-cross-origin'; response.headers['Permissions-Policy']='camera=(self), microphone=(), geolocation=()';
    if request.path.startswith(('/dashboard','/profile','/certificate','/messages')): response.headers['Cache-Control']='no-store';
    return response

@app.route('/')
def home(): return render_template('page.html', page='home')

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        u=g.db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
        if u and check_password_hash(u['password_hash'],password):
            if u['account_status'] != 'approved':
                flash('Your account is pending administrator approval.' if u['account_status']=='pending' else 'Your account is suspended. Contact the institution administrator.','warning')
                return render_template('page.html',page='login')
            session.clear(); session['uid']=u['id']; session['role']=u['role']; flash('Welcome, '+u['name']+'!','success'); return redirect(url_for('dashboard'))
        flash('Invalid email or password.','danger')
    return render_template('page.html',page='login')

@app.route('/forgot-password', methods=['GET','POST'])
def forgot_password():
    if request.method == 'POST':
        email=request.form.get('email','').strip().lower()[:254]
        row=g.db.execute("SELECT id,email FROM users WHERE email=? AND account_status='approved'",(email,)).fetchone()
        # Always show the same response to avoid revealing whether an email is registered.
        if row:
            token=secrets.token_urlsafe(32)
            digest=hashlib.sha256(token.encode()).hexdigest()
            g.db.execute("UPDATE password_resets SET used_at=CURRENT_TIMESTAMP WHERE user_id=? AND used_at IS NULL",(row['id'],))
            g.db.execute("INSERT INTO password_resets(user_id,token_hash,expires_at) VALUES(?,?,datetime('now','+30 minutes'))",(row['id'],digest))
            g.db.commit()
            base_url=os.environ.get('PUBLIC_BASE_URL',request.url_root.rstrip('/')).rstrip('/')
            reset_url=base_url+url_for('reset_password',token=token)
            send_email(row['email'],'CareerIQ password reset',f'Reset your CareerIQ password within 30 minutes using this one-time link: {reset_url}\nIf you did not request this, ignore this email.')
        flash('If the account exists and email delivery is configured, a password-reset link will be sent.','info')
        return redirect(url_for('login'))
    return render_template('page.html',page='forgot_password')


@app.route('/reset-password/<token>', methods=['GET','POST'])
def reset_password(token):
    digest=hashlib.sha256(token.encode()).hexdigest()
    row=g.db.execute("SELECT id,user_id FROM password_resets WHERE token_hash=? AND used_at IS NULL AND expires_at > CURRENT_TIMESTAMP",(digest,)).fetchone()
    if not row:
        flash('This password-reset link is invalid, expired, or already used. Request a new link.','danger')
        return redirect(url_for('forgot_password'))
    if request.method=='POST':
        password=request.form.get('password',''); confirm=request.form.get('confirm_password','')
        if len(password)<12:
            flash('Use at least 12 characters for your new password.','danger')
        elif password != confirm:
            flash('Passwords do not match.','danger')
        else:
            g.db.execute('UPDATE users SET password_hash=? WHERE id=?',(generate_password_hash(password),row['user_id']))
            g.db.execute('UPDATE password_resets SET used_at=CURRENT_TIMESTAMP WHERE id=?',(row['id'],))
            audit('account.password_reset','user',row['user_id'],'Password reset token consumed')
            g.db.commit(); flash('Password updated. Please sign in.','success'); return redirect(url_for('login'))
    return render_template('page.html',page='reset_password',token=token)


@app.post('/logout')
def logout(): session.clear(); flash('Signed out.','info'); return redirect(url_for('home'))

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name=request.form.get('name','').strip()[:100]
        email=request.form.get('email','').strip().lower()[:254]
        password=request.form.get('password','')
        confirm_password=request.form.get('confirm_password','')
        role=request.form.get('role','student').strip().lower()
        branch=((request.form.get('faculty_branch','') or request.form.get('branch','')) if request.form.get('role','').strip().lower()=='faculty' else request.form.get('branch','')).strip()[:100]
        section=request.form.get('section','').strip()[:20]
        roll_no=request.form.get('roll_no','').strip().upper()[:30]
        subject=request.form.get('subject','').strip()[:120]
        target=request.form.get('target','Cloud Engineer').strip()
        skills=request.form.get('skills','').strip()[:1000]
        allowed_roles={'student','faculty','company'}
        if not name or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash('Enter a valid name and email address.','danger')
        elif role not in allowed_roles:
            flash('Choose Student, Faculty / Teacher, or Company.','danger')
        elif role=='student' and target not in CAREERS:
            flash('Choose a valid target career.','danger')
        elif role=='student' and (not branch or not section or not roll_no):
            flash('Students must provide branch, section and roll number.','danger')
        elif role=='faculty' and (not branch or not subject):
            flash('Faculty must provide branch and subject.','danger')
        elif role=='student' and g.db.execute("SELECT id FROM users WHERE role='student' AND lower(trim(branch))=lower(trim(?)) AND lower(trim(roll_no))=lower(trim(?))",(branch,roll_no)).fetchone():
            flash('That roll number is already registered in this branch. Contact the administrator if this is a duplicate.','danger')
        elif len(password) < 10:
            flash('Use a password with at least 10 characters.','danger')
        elif password != confirm_password:
            flash('Passwords do not match. Please confirm your password.','danger')
        else:
            try:
                status='approved' if role=='student' else 'pending'
                cur=g.db.execute('INSERT INTO users(name,email,password_hash,role,account_status,branch,section,roll_no,subject) VALUES(?,?,?,?,?,?,?,?,?)',(name,email,generate_password_hash(password),role,status,branch,section,roll_no,subject))
                uid=cur.lastrowid
                if role=='student': g.db.execute('INSERT INTO profiles(user_id,department,target,skills) VALUES(?,?,?,?)',(uid,branch,target,skills))
                g.db.commit()
                if status == 'pending':
                    flash('Registration received. Faculty/company access is pending approval; sign in after approval.','success')
                    return redirect(url_for('login'))
                session.clear(); session['uid']=uid; session['role']=role
                flash('Student account created successfully.','success'); return redirect(url_for('dashboard'))
            except sqlite3.IntegrityError:
                g.db.rollback()
                flash('An account with that email already exists. Sign in instead.','warning')
    return render_template('page.html',page='register')

@app.route('/dashboard')
@login_required
def dashboard():
    role=session['role']; uid=session['uid']; db=g.db
    if role=='student':
        p=db.execute('SELECT * FROM profiles WHERE user_id=?',(uid,)).fetchone()
        certs=db.execute('SELECT * FROM certificates WHERE student_id=? ORDER BY id DESC',(uid,)).fetchall()
        projects=db.execute('SELECT p.*,pl.repo_url,pl.live_url,pl.tech_stack,pl.role_description FROM projects p LEFT JOIN project_links pl ON pl.project_id=p.id WHERE p.student_id=? ORDER BY p.id DESC',(uid,)).fetchall()
        jobs=db.execute("SELECT j.*,u.name company FROM jobs j JOIN users u ON u.id=j.company_id WHERE j.status='Open' ORDER BY j.id DESC").fetchall()
        apps=db.execute('SELECT a.*,j.title,j.kind,u.name company FROM applications a JOIN jobs j ON j.id=a.job_id JOIN users u ON u.id=j.company_id WHERE a.student_id=? ORDER BY a.id DESC',(uid,)).fetchall()
        attempts=db.execute('SELECT * FROM attempts WHERE student_id=? ORDER BY id DESC LIMIT 5',(uid,)).fetchall()
        notifications=db.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 8',(uid,)).fetchall()
        saved_jobs=db.execute("SELECT j.*,u.name company FROM saved_jobs s JOIN jobs j ON j.id=s.job_id JOIN users u ON u.id=j.company_id WHERE s.student_id=? AND j.status='Open' ORDER BY s.id DESC",(uid,)).fetchall()
        saved_ids={r['job_id'] for r in db.execute('SELECT job_id FROM saved_jobs WHERE student_id=?',(uid,)).fetchall()}
        unread_count=db.execute('SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL',(uid,)).fetchone()[0]
        roadmap=roadmap_with_optional_ai(p['target'],p['skills'])
        return render_template('page.html',page='student',p=p,certs=certs,projects=projects,jobs=jobs,apps=apps,attempts=attempts,notifications=notifications,roadmap=roadmap,saved_jobs=saved_jobs,saved_ids=saved_ids,unread_count=unread_count,academic_records=db.execute('SELECT * FROM academic_records WHERE student_id=? ORDER BY id DESC LIMIT 30',(uid,)).fetchall(),messages=db.execute('SELECT m.*,u.name sender FROM messages m JOIN users u ON u.id=m.sender_id WHERE m.recipient_id=? ORDER BY m.id DESC LIMIT 30',(uid,)).fetchall(),achievements=db.execute('SELECT * FROM achievements WHERE student_id=? ORDER BY id DESC',(uid,)).fetchall(),events=db.execute('SELECT * FROM events WHERE student_id=? ORDER BY event_date DESC,id DESC',(uid,)).fetchall())
    if role=='faculty':
        faculty_row=db.execute("SELECT branch,subject FROM users WHERE id=?",(uid,)).fetchone()
        faculty_branch=(faculty_row['branch'] or '').strip().casefold()
        students=db.execute("SELECT u.id,u.name,u.email,u.branch,u.section,u.roll_no,p.department,p.year,p.target,p.skills,p.score,(SELECT COUNT(*) FROM certificates c WHERE c.student_id=u.id) cert_count FROM users u JOIN profiles p ON p.user_id=u.id WHERE u.role='student' AND lower(trim(u.branch))=lower(trim(?)) ORDER BY u.name",(faculty_row['branch'] or '',)).fetchall()
        pending=db.execute("SELECT c.*,u.name student FROM certificates c JOIN users u ON u.id=c.student_id WHERE c.status='Pending' AND lower(trim(u.branch))=lower(trim(?)) ORDER BY c.id DESC",(faculty_row['branch'] or '',)).fetchall()
        all_certs=db.execute('SELECT c.*,u.name student FROM certificates c JOIN users u ON u.id=c.student_id WHERE lower(trim(u.branch))=lower(trim(?)) ORDER BY c.id DESC LIMIT 50',(faculty_row['branch'] or '',)).fetchall()
        exam_alerts=db.execute('SELECT e.*,u.name student,u.email FROM exam_alerts e JOIN users u ON u.id=e.student_id WHERE lower(trim(u.branch))=lower(trim(?)) ORDER BY e.id DESC LIMIT 50',(faculty_row['branch'] or '',)).fetchall()
        academic_records=db.execute('SELECT ar.*,u.name student,u.roll_no FROM academic_records ar JOIN users u ON u.id=ar.student_id WHERE lower(trim(u.branch))=lower(trim(?)) ORDER BY ar.id DESC LIMIT 100',(faculty_row['branch'] or '',)).fetchall()
        return render_template('page.html',page='faculty',students=students,pending=pending,all_certs=all_certs,exam_alerts=exam_alerts,faculty_branch=faculty_row['branch'],faculty_subject=faculty_row['subject'],academic_records=academic_records)
    jobs=db.execute('SELECT * FROM jobs WHERE company_id=? ORDER BY id DESC',(uid,)).fetchall()
    apps=db.execute('SELECT a.*,j.title,u.name student,p.department,p.year,p.skills FROM applications a JOIN jobs j ON j.id=a.job_id JOIN users u ON u.id=a.student_id JOIN profiles p ON p.user_id=u.id WHERE j.company_id=? ORDER BY a.id DESC',(uid,)).fetchall()
    return render_template('page.html',page='company',jobs=jobs,apps=apps,student_messages=db.execute('SELECT m.*,u.name recipient FROM messages m JOIN users u ON u.id=m.recipient_id WHERE m.sender_id=? ORDER BY m.id DESC LIMIT 30',(uid,)).fetchall())

def make_roadmap(target,skills):
    required=CAREERS.get(target,CAREERS['Cloud Engineer']); have={x.strip().lower() for x in (skills or '').split(',') if x.strip()}
    matched=[s for s in required if s.lower() in have]; missing=[s for s in required if s.lower() not in have]
    return {'required':required,'matched':matched,'missing':missing,'milestones':[{'skill':s,'level':'Beginner' if i<2 else 'Intermediate' if i<4 else 'Advanced','project':f'Build a small {s} practice project'} for i,s in enumerate(missing)]}

@app.route('/profile',methods=['GET','POST'])
@roles('student')
def profile():
    uid=session['uid']; db=g.db
    if request.method=='POST':
        recruitment_visible=1 if request.form.get('recruitment_visible')=='on' else 0
        db.execute('UPDATE profiles SET recruitment_visible=? WHERE user_id=?',(recruitment_visible,uid))
        audit('profile.visibility_updated','student',uid,'Student changed recruitment visibility only')
        db.commit(); flash('Privacy preference saved. Identity and academic profile data remain locked; request corrections from the administrator.','success'); return redirect(url_for('profile'))
    return render_template('page.html',page='profile',u=db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone(),p=db.execute('SELECT * FROM profiles WHERE user_id=?',(uid,)).fetchone(),careers=list(CAREERS))

def send_email(to_address, subject, body):
    """Optional SMTP delivery; in-app notifications remain the source of truth."""
    host=os.environ.get('SMTP_HOST','').strip(); sender=os.environ.get('SMTP_FROM','').strip()
    if not host or not sender or not to_address: return False
    msg=EmailMessage(); msg['Subject']=subject; msg['From']=sender; msg['To']=to_address; msg.set_content(body)
    port=int(os.environ.get('SMTP_PORT','587')); username=os.environ.get('SMTP_USERNAME',''); password=os.environ.get('SMTP_PASSWORD','')
    try:
        with smtplib.SMTP(host,port,timeout=8) as server:
            if os.environ.get('SMTP_STARTTLS','1')=='1': server.starttls(context=ssl.create_default_context())
            if username: server.login(username,password)
            server.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        app.logger.warning('Email delivery failed: %s', type(exc).__name__)
        return False


def store_certificate(upload, stored_name):
    """Store in private GCS when configured; otherwise use local development storage."""
    if GCS_BUCKET:
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise RuntimeError('GCS_BUCKET is configured but google-cloud-storage is not installed') from exc
        client=storage.Client(); bucket=client.bucket(GCS_BUCKET); blob=bucket.blob('certificates/'+stored_name)
        blob.upload_from_file(upload.stream, rewind=True, content_type='application/octet-stream')
        return
    UPLOAD_DIR.mkdir(parents=True,exist_ok=True); upload.save(UPLOAD_DIR/stored_name)


def certificate_exists(stored_name):
    if GCS_BUCKET:
        from google.cloud import storage
        return storage.Client().bucket(GCS_BUCKET).blob('certificates/'+stored_name).exists()
    return bool(stored_name and (UPLOAD_DIR/stored_name).is_file())


def open_certificate(stored_name):
    if GCS_BUCKET:
        from google.cloud import storage
        return storage.Client().bucket(GCS_BUCKET).blob('certificates/'+stored_name).download_as_bytes()
    return (UPLOAD_DIR/stored_name).read_bytes()


def roadmap_with_optional_ai(target, skills):
    """Use Vertex AI only when configured; always retain transparent rule-based fallback."""
    result=make_roadmap(target,skills)
    project=os.environ.get('GOOGLE_CLOUD_PROJECT','').strip()
    if not project or os.environ.get('VERTEX_AI_ENABLED','0')!='1': return result
    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel
        vertexai.init(project=project, location=os.environ.get('VERTEX_AI_LOCATION','asia-south1'))
        prompt=("Give concise, supportive career-learning guidance. Do not make hiring decisions. "
                "Use only these supplied facts and never infer sensitive traits. Return 3 practical milestones. "
                f"Target career: {target}. Listed skills: {skills}. Skill gaps: {', '.join(result['missing'])}.")
        response=GenerativeModel(os.environ.get('VERTEX_AI_MODEL','gemini-2.5-flash')).generate_content(prompt)
        text_out=(getattr(response,'text','') or '').strip()
        if text_out: result['ai_guidance']=text_out[:4000]; result['guidance_source']='Vertex AI; review recommendations'
    except Exception as exc:
        app.logger.warning('Vertex AI guidance unavailable: %s',type(exc).__name__)
    return result


@app.post('/certificates')
@roles('student')
def add_certificate():
    title=request.form.get('title','').strip()[:150]; issuer=request.form.get('issuer','').strip()[:150]; category=request.form.get('category','Subject').strip()
    upload=request.files.get('certificate_file')
    if not title:
        flash('Certificate title is required.','danger')
    else:
        file_name=''; stored_name=''
        if upload and upload.filename:
            safe=secure_filename(upload.filename)
            ext=safe.rsplit('.',1)[-1].lower() if '.' in safe else ''
            if ext not in ALLOWED_UPLOADS:
                flash('Upload a PDF, PNG or JPG certificate.','danger'); return redirect(url_for('dashboard'))
            # Validate file signatures as well as extensions; do not trust the browser's MIME type.
            header=upload.stream.read(16); upload.stream.seek(0)
            signatures={'pdf': header.startswith(b'%PDF-'), 'png': header.startswith(b'\x89PNG\r\n\x1a\n'),
                        'jpg': header.startswith(b'\xff\xd8\xff'), 'jpeg': header.startswith(b'\xff\xd8\xff')}
            if not signatures.get(ext,False):
                flash('The file contents do not match a supported certificate format.','danger'); return redirect(url_for('dashboard'))
            stored_name=secrets.token_hex(16)+'.'+ext
            try: store_certificate(upload,stored_name)
            except Exception as exc:
                app.logger.error('Certificate storage failed: %s',type(exc).__name__)
                flash('Certificate storage is temporarily unavailable. Please try again later.','danger'); return redirect(url_for('dashboard'))
            file_name=safe[:180]
        if category not in ('Participation','Winning','Subject','Skill Test'): category='Subject'
        g.db.execute('INSERT INTO certificates(student_id,title,issuer,file_name,stored_name,category) VALUES(?,?,?,?,?,?)',(session['uid'],title,issuer,file_name,stored_name,category))
        g.db.commit(); flash('Certificate submitted for faculty review.','success')
    return redirect(url_for('dashboard'))

@app.get('/certificate/<int:cid>/download')
@login_required
def download_certificate(cid):
    from flask import send_from_directory
    cert=g.db.execute('SELECT * FROM certificates WHERE id=?',(cid,)).fetchone()
    if not cert: abort(404)
    if session.get('role') == 'faculty' and not is_admin_user():
        owner=g.db.execute('SELECT branch FROM users WHERE id=?',(cert['student_id'],)).fetchone()
        if not owner or (owner['branch'] or '').strip().casefold() != (user()['branch'] or '').strip().casefold(): abort(403)
    elif cert['student_id'] != session.get('uid') and not is_admin_user(): abort(403)
    if not cert['stored_name'] or not certificate_exists(cert['stored_name']): abort(404)
    data=open_certificate(cert['stored_name'])
    ext=(cert['stored_name'].rsplit('.',1)[-1] or '').lower()
    mime={'pdf':'application/pdf','png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg'}.get(ext,'application/octet-stream')
    response=Response(data,mimetype=mime)
    response.headers['Content-Disposition']='attachment; filename="'+secure_filename(cert['file_name'] or 'certificate')+'"'
    response.headers['Cache-Control']='private, no-store'
    return response

@app.post('/projects')
@roles('student')
def add_project():
    title=request.form.get('title','').strip()[:150]; desc=request.form.get('description','').strip()[:500]; repo=request.form.get('repo_url','').strip()[:500]; live=request.form.get('live_url','').strip()[:500]; stack=request.form.get('tech_stack','').strip()[:300]; role_desc=request.form.get('role_description','').strip()[:300]
    if any(x and not re.fullmatch(r'https://[^\s]+',x) for x in (repo,live)): flash('Project links must use HTTPS.','danger'); return redirect(url_for('dashboard'))
    if title:
        cur=g.db.execute('INSERT INTO projects(student_id,title,description) VALUES(?,?,?)',(session['uid'],title,desc)); g.db.execute('INSERT INTO project_links(project_id,repo_url,live_url,tech_stack,role_description) VALUES(?,?,?,?,?)',(cur.lastrowid,repo,live,stack,role_desc)); g.db.commit(); flash('Project added to your portfolio.','success')
    else: flash('Project title is required.','danger')
    return redirect(url_for('dashboard'))

@app.post('/faculty/student/<int:sid>')
@roles('faculty')
def update_student(sid):
    abort(403, description='Faculty can create academic records but cannot overwrite student records. Ask the administrator to correct an existing record.')

@app.post('/faculty/certificate/<int:cid>')
@roles('faculty')
def review_certificate(cid):
    status=request.form.get('status')
    if status not in ('Pending','Verified','Rejected'): abort(400)
    cert=g.db.execute('SELECT student_id,title FROM certificates WHERE id=?',(cid,)).fetchone()
    if not cert: abort(404)
    owner=g.db.execute('SELECT branch FROM users WHERE id=?',(cert['student_id'],)).fetchone()
    if not is_admin_user() and (not owner or (owner['branch'] or '').strip().casefold() != (user()['branch'] or '').strip().casefold()): abort(403)
    g.db.execute('UPDATE certificates SET status=? WHERE id=?',(status,cid)); audit('certificate.reviewed','certificate',cid,'Status: '+status)
    g.db.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(cert['student_id'],'Certificate review updated',f'Your certificate “{cert["title"]}” is now marked {status}.'))
    g.db.commit(); flash('Certificate status updated and student notified.','success'); return redirect(url_for('dashboard'))

@app.route('/opportunities')
@login_required
def opportunities():
    q=request.args.get('q','').strip()[:100]; kind=request.args.get('kind','')
    sql="SELECT j.*,u.name company FROM jobs j JOIN users u ON u.id=j.company_id WHERE j.status='Open'"; params=[]
    if q: sql+=' AND (j.title LIKE ? OR j.skills LIKE ? OR j.description LIKE ?)'; params += [f'%{q}%']*3
    if kind in ('Job','Internship'): sql+=' AND j.kind=?'; params.append(kind)
    rows=g.db.execute(sql+' ORDER BY j.id DESC',params).fetchall()
    saved_ids=set()
    if session.get('role')=='student': saved_ids={r['job_id'] for r in g.db.execute('SELECT job_id FROM saved_jobs WHERE student_id=?',(session['uid'],)).fetchall()}
    applied_ids={r['job_id'] for r in g.db.execute('SELECT job_id FROM applications WHERE student_id=?',(session['uid'],)).fetchall()} if session.get('role')=='student' else set()
    return render_template('page.html',page='opportunities',jobs=rows,q=q,kind=kind,saved_ids=saved_ids,applied_ids=applied_ids)

@app.post('/saved-jobs/<int:jid>')
@roles('student')
def toggle_saved_job(jid):
    job=g.db.execute("SELECT id FROM jobs WHERE id=? AND status='Open'",(jid,)).fetchone()
    if not job: abort(404)
    saved=g.db.execute('SELECT id FROM saved_jobs WHERE student_id=? AND job_id=?',(session['uid'],jid)).fetchone()
    if saved:
        g.db.execute('DELETE FROM saved_jobs WHERE id=?',(saved['id'],)); flash('Opportunity removed from saved list.','info')
    else:
        g.db.execute('INSERT INTO saved_jobs(student_id,job_id) VALUES(?,?)',(session['uid'],jid)); flash('Opportunity saved for later.','success')
    g.db.commit(); return redirect(url_for('opportunities'))

@app.post('/notifications/read-all')
@roles('student')
def read_all_notifications():
    g.db.execute("UPDATE notifications SET read_at=CURRENT_TIMESTAMP WHERE user_id=? AND read_at IS NULL",(session['uid'],)); g.db.commit()
    flash('All notifications marked as read.','success'); return redirect(url_for('dashboard'))

@app.post('/apply/<int:jid>')
@roles('student')
def apply(jid):
    job=g.db.execute("SELECT id FROM jobs WHERE id=? AND status='Open'",(jid,)).fetchone()
    if not job: flash('Opportunity is not available.','danger')
    else:
        try: g.db.execute('INSERT INTO applications(job_id,student_id) VALUES(?,?)',(jid,session['uid'])); g.db.commit(); flash('Application submitted.','success')
        except sqlite3.IntegrityError: flash('You have already applied.','warning')
    return redirect(url_for('opportunities'))

@app.route('/company/candidates')
@roles('company')
def candidates():
    q=request.args.get('q','').strip()[:100]
    sql="SELECT u.id,u.name,p.department,p.year,p.target,p.skills,p.score,p.bio,(SELECT COUNT(*) FROM certificates c WHERE c.student_id=u.id AND c.status='Verified') verified_certs,(SELECT COUNT(*) FROM projects pr WHERE pr.student_id=u.id) projects FROM users u JOIN profiles p ON p.user_id=u.id WHERE u.role='student' AND p.recruitment_visible=1"
    params=[]
    if q:
        sql += ' AND (u.name LIKE ? OR p.skills LIKE ? OR p.target LIKE ? OR p.department LIKE ?)'
        params=[f'%{q}%']*4
    rows=g.db.execute(sql+' ORDER BY p.score DESC,u.name',params).fetchall()
    return render_template('page.html',page='candidates',candidates=rows,q=q)

@app.post('/company/job')
@roles('company')
def create_job():
    title=request.form.get('title','').strip()[:150]; kind=request.form.get('kind',''); desc=request.form.get('description','').strip()[:2000]; skills=request.form.get('skills','').strip()[:500]; eligibility=request.form.get('eligibility','').strip()[:500]; location=request.form.get('location','').strip()[:100]
    if not title or kind not in ('Job','Internship'): flash('Enter a title and type.','danger')
    else:
        cur=g.db.execute('INSERT INTO jobs(company_id,title,kind,description,skills,eligibility,location) VALUES(?,?,?,?,?,?,?)',(session['uid'],title,kind,desc,skills,eligibility,location))
        job_id=cur.lastrowid
        students=g.db.execute("SELECT u.id,p.skills,p.target FROM users u JOIN profiles p ON p.user_id=u.id WHERE u.role='student'").fetchall()
        required={x.strip().lower() for x in skills.split(',') if x.strip()}
        for st in students:
            owned={x.strip().lower() for x in (st['skills'] or '').split(',') if x.strip()}
            if not required or required.intersection(owned):
                g.db.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(st['id'],'New opportunity: '+title, f'{kind} posted by your industry network. Review eligibility and apply if suitable.'))
        g.db.commit(); flash('Opportunity published and matching students notified.','success')
    return redirect(url_for('dashboard'))

@app.post('/company/job/<int:jid>/status')
@roles('company')
def job_status(jid):
    status=request.form.get('status')
    if status not in ('Open','Closed'): abort(400)
    cur=g.db.execute('UPDATE jobs SET status=? WHERE id=? AND company_id=?',(status,jid,session['uid']))
    if not cur.rowcount: abort(404)
    g.db.commit(); flash('Opportunity updated.','success'); return redirect(url_for('dashboard'))

@app.post('/company/application/<int:aid>')
@roles('company')
def app_status(aid):
    status=request.form.get('status')
    if status not in ('Under Review','Shortlisted','Rejected','Selected'): abort(400)
    app_row=g.db.execute('SELECT a.student_id,j.title FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.id=? AND j.company_id=?',(aid,session['uid'])).fetchone()
    if not app_row: abort(404)
    g.db.execute('UPDATE applications SET status=? WHERE id=?',(status,aid))
    g.db.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(app_row['student_id'],'Application status changed',f'Your application for “{app_row["title"]}” is now {status}.'))
    g.db.commit(); flash('Application status updated and student notified.','success'); return redirect(url_for('dashboard'))

def generate_assessment_questions(subject):
    """Generate a fresh 50-question exam from reusable subject-specific patterns.
    This is deterministic template generation, not a claim of generative AI."""
    rng=random.SystemRandom()
    subject=(subject or 'Python').strip()[:80]
    banks={
      'Python':[('Which keyword starts a function definition?','def',['func','function','method'],'def'),('Which collection stores key-value pairs?','dictionary',['list','tuple','set'],'dictionary'),('Which keyword handles an exception?','except',['catch','rescue','handle'],'except'),('What does len() return?','Number of items',['Memory address','Data type','File size'],'Number of items'),('Which structure is immutable?','tuple',['list','dictionary','set'],'tuple'),('Which keyword creates a class?','class',['object','struct','typeclass'],'class'),('Which operator tests equality?','==',['=','===','<>'],'=='),('Which mode appends to a file?','a',['r','w','x'],'a'),('Which value represents no value?','None',['null','nil','void'],'None'),('Which statement repeats over an iterable?','for',['repeat','foreach only','loop'],'for')],
      'Java':[('Which keyword declares a class?','class',['define','struct','object'],'class'),('Which method is the usual program entry point?','main',['start','run','init'],'main'),('Which keyword creates an object?','new',['make','create','alloc'],'new'),('Which type stores true or false?','boolean',['boolnum','bitstring','truth'],'boolean'),('Which block handles an exception?','catch',['except','rescue','handle'],'catch'),('Which keyword inherits a class?','extends',['inherits','implements-class','superclass'],'extends'),('Which collection rejects duplicate elements?','Set',['List','Queue','ArrayList'],'Set'),('Which keyword prevents method overriding?','final',['static','const','sealed-method'],'final'),('Which package contains Scanner?','java.util',['java.io','java.lang.reflect','java.net'],'java.util'),('Which keyword implements an interface?','implements',['extends-interface','inherits','uses'],'implements')],
      'C':[('Which function is the usual entry point?','main',['start','run','begin'],'main'),('Which header declares printf?','stdio.h',['stdlib.h','string.h','math.h'],'stdio.h'),('Which operator gets an address?','&',['*','%','->'],'&'),('Which function allocates dynamic memory?','malloc',['printf','scanf','strlen'],'malloc'),('Which loop checks condition before each iteration?','while',['do-while only','switch','goto'],'while'),('Which type stores a single character?','char',['string','character','bytechar'],'char'),('Which symbol ends most statements?',';',[':','.',','],';'),('Which function compares strings?','strcmp',['strcpy','strlen','strcat'],'strcmp'),('Which keyword exits a loop?','break',['stop','exitloop','end'],'break'),('Which operator accesses a struct member through pointer?','->',['.','::','&'],'->')],
      'SQL':[('Which clause filters rows?','WHERE',['ORDER BY','SELECT','JOIN'],'WHERE'),('Which function counts rows?','COUNT(*)',['SUM(*)','TOTAL()','ROWS()'],'COUNT(*)'),('Which clause sorts results?','ORDER BY',['GROUP BY','HAVING','SORT'],'ORDER BY'),('Which command adds rows?','INSERT',['UPDATE','ALTER','CREATE ROW'],'INSERT'),('Which command changes existing rows?','UPDATE',['MODIFY TABLE','CHANGE','REPLACE COLUMN'],'UPDATE'),('Which constraint uniquely identifies each row?','PRIMARY KEY',['FOREIGN KEY','CHECK','DEFAULT'],'PRIMARY KEY'),('Which join returns matching rows from both tables?','INNER JOIN',['CROSS JOIN','FULL TEXT','UNION ALL'],'INNER JOIN'),('Which clause filters grouped results?','HAVING',['WHERE','ORDER BY','LIMIT'],'HAVING'),('Which command removes rows?','DELETE',['DROP ROW','REMOVE','ERASE'],'DELETE'),('Which keyword removes duplicate results?','DISTINCT',['UNIQUE ROWS','ONLY','DEDUP'],'DISTINCT')],
      'HTML':[('Which element creates a hyperlink?','<a>',['<link>','<href>','<url>'],'<a>'),('Which element displays an image?','<img>',['<picture-src>','<image>','<media>'],'<img>'),('Which attribute provides image alternative text?','alt',['title-only','src','href'],'alt'),('Which element contains page metadata?','<head>',['<meta-body>','<header>','<footer>'],'<head>'),('Which element creates a form control label?','<label>',['<caption>','<legend-only>','<name>'],'<label>'),('Which tag creates an unordered list?','<ul>',['<ol>','<li>','<list>'],'<ul>'),('Which attribute points to a destination URL?','href',['src','alt','action-only'],'href'),('Which element represents a paragraph?','<p>',['<para>','<text>','<pg>'],'<p>'),('Which input type hides typed characters?','password',['hidden-text','secure','private'],'password'),('Which element is the largest default heading?','<h1>',['<h6>','<head>','<title>'],'<h1>')],
      'Cloud Computing':[('Which model provides virtual machines?','IaaS',['SaaS','PaaS','DBaaS'],'IaaS'),('What is a cloud region?','A geographic area containing zones',['A user group','A billing label','A programming language'],'A geographic area containing zones'),('Which principle grants only needed permissions?','Least privilege',['Open access','Shared admin','Default allow'],'Least privilege'),('What does autoscaling do?','Adjusts capacity based on demand',['Encrypts all files','Creates source code','Disables monitoring'],'Adjusts capacity based on demand'),('What is object storage best suited for?','Unstructured objects and files',['CPU scheduling','Running a kernel','Replacing DNS'],'Unstructured objects and files'),('Which service model provides a managed application platform?','PaaS',['IaaS','On-prem only','Bare metal only'],'PaaS'),('What does IAM manage?','Identities and access permissions',['Image compression','IP routing only','Source formatting'],'Identities and access permissions'),('What is a container image?','A packaged application and its dependencies',['A virtual network','A billing invoice','A user password'],'A packaged application and its dependencies'),('What does encryption at rest protect?','Stored data',['Only keyboard input','Only screen brightness','DNS names only'],'Stored data'),('Why use multiple zones?','Improve resilience to zonal failure',['Remove all costs','Avoid authentication','Replace backups'],'Improve resilience to zonal failure')]
    }
    key=next((k for k in banks if k.casefold()==subject.casefold()),'Python')
    templates=banks[key]
    questions=[]
    for i in range(50):
        base=templates[i%len(templates)]
        prompt,correct,distractors,answer=base
        # Parameterized variants ensure prompts are unique within and between attempts.
        level='Basic' if i<17 else ('Intermediate' if i<34 else 'Advanced')
        if i>=len(templates):
            prompt=f'{prompt} (practice scenario {i+1}, variant {rng.randint(100,9999)})'
        else:
            prompt=f'{prompt} (variant {rng.randint(100,9999)})'
        opts=[correct]+list(distractors)
        rng.shuffle(opts)
        answer_key='abcd'[opts.index(correct)]
        questions.append({'id':i+1,'topic':subject,'difficulty':level,'question':prompt,'a':opts[0],'b':opts[1],'c':opts[2],'d':opts[3],'answer':answer_key,'explanation':f'{correct} is the correct choice for this {subject} concept.'})
    rng.shuffle(questions)
    return questions

@app.route('/assessment',methods=['GET','POST'])
@roles('student')
def assessment():
    if request.method=='POST':
        token=session.get('exam_session_token')
        row=g.db.execute("SELECT * FROM exam_sessions WHERE token=? AND student_id=? AND active=1 AND expires_at>datetime('now')",(token,session['uid'])).fetchone() if token else None
        if not row: abort(400, description='Start a fresh assessment before submitting answers.')
        questions=json.loads(row['questions_json']); session.pop('exam_session_token',None)
        g.db.execute('DELETE FROM exam_sessions WHERE token=?',(token,))
        weights={'Basic':1,'Intermediate':2,'Advanced':3}; earned=total=correct=0; review=[]
        for q in questions:
            w=weights[q['difficulty']]; total+=w; chosen=request.form.get(f"q{q['id']}",''); ok=int(chosen==q['answer']); earned+=w if ok else 0; correct+=ok; review.append((q,chosen,ok))
        score=round(earned/total*100,2) if total else 0
        subject=row['subject']
        cur=g.db.execute('INSERT INTO attempts(student_id,score,correct_count,total_count,subject) VALUES(?,?,?,?,?)',(session['uid'],score,correct,len(questions),subject))
        certificate_id=None
        if score>=60:
            code='CIQ-'+secrets.token_hex(6).upper()
            curc=g.db.execute('INSERT INTO skill_certificates(student_id,subject,score,correct_count,total_count,certificate_code) VALUES(?,?,?,?,?,?)',(session['uid'],subject,score,correct,len(questions),code)); certificate_id=curc.lastrowid
            g.db.execute('INSERT INTO certificates(student_id,title,issuer,status,category) VALUES(?,?,?,?,?)',(session['uid'],f'{subject} Skill Assessment Certificate ({score}%)','CareerIQ Online Assessment','Verified','Skill Test'))
            flash('Congratulations! Your skill certificate has been generated.','success')
        else:
            fails=g.db.execute('SELECT COUNT(*) FROM attempts WHERE student_id=? AND subject=? AND score<60',(session['uid'],subject)).fetchone()[0]+1
            g.db.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(session['uid'],'Skill improvement plan suggested',f'You scored {score}% in {subject}. Attempt {fails}: follow the beginner-to-advanced roadmap and practice before retrying.'))
        g.db.commit()
        return render_template('page.html',page='result',score=score,earned=earned,total=total,correct=correct,review=review,total_count=len(questions),subject=subject,certificate_id=certificate_id)
    subject=request.args.get('subject','Python').strip()[:80]
    allowed=['Python','Java','C','SQL','HTML','Cloud Computing']
    if subject not in allowed: subject='Python'
    questions=generate_assessment_questions(subject)
    token=secrets.token_urlsafe(24)
    g.db.execute('DELETE FROM exam_sessions WHERE student_id=?',(session['uid'],))
    g.db.execute("INSERT INTO exam_sessions(token,student_id,subject,questions_json,active,expires_at) VALUES(?,?,?,?,0,datetime('now','+90 minutes'))",(token,session['uid'],subject,json.dumps(questions)))
    g.db.commit(); session['exam_session_token']=token; session.pop('exam_active',None)
    return render_template('page.html',page='assessment',questions=questions,subject=subject)

@app.post('/exam/start')
@roles('student')
def exam_start():
    token=session.get('exam_session_token')
    cur=g.db.execute("UPDATE exam_sessions SET active=1 WHERE token=? AND student_id=? AND expires_at>datetime('now')",(token,session.get('uid'))) if token else None
    if not cur or not cur.rowcount: abort(400,description='Assessment session expired. Reload and try again.')
    session['exam_active'] = True
    return {'ok': True}

@app.post('/exam/event')
@roles('student')
def exam_event():
    token=session.get('exam_session_token')
    active=g.db.execute("SELECT token FROM exam_sessions WHERE token=? AND student_id=? AND active=1 AND expires_at>datetime('now')",(token,session.get('uid'))).fetchone() if token else None
    if not active: abort(400, description='No active assessment session.')
    payload=request.get_json(silent=True) or {}
    event_type=str(payload.get('event_type','')).strip()[:60]
    details=str(payload.get('details','')).strip()[:240]
    allowed={'head_turn','face_not_detected','camera_stopped','fullscreen_exited','tab_hidden'}
    if event_type not in allowed: abort(400)
    # Rate-limit repeated client-side alerts by event and recent timestamp.
    recent=g.db.execute("SELECT id FROM exam_alerts WHERE student_id=? AND event_type=? AND created_at >= datetime('now','-10 seconds')",(session['uid'],event_type)).fetchone()
    if not recent:
        g.db.execute('INSERT INTO exam_alerts(student_id,event_type,details) VALUES(?,?,?)',(session['uid'],event_type,details))
        g.db.commit()
        student_row=g.db.execute('SELECT name,email FROM users WHERE id=?',(session['uid'],)).fetchone()
        student_branch=g.db.execute('SELECT branch FROM users WHERE id=?',(session['uid'],)).fetchone()['branch']
        faculty_rows=g.db.execute("SELECT email FROM users WHERE role='faculty' AND account_status='approved' AND lower(trim(branch))=lower(trim(?))",(student_branch or '',)).fetchall()
        for faculty_row in faculty_rows:
            send_email(faculty_row['email'],'CareerIQ exam monitoring review alert',f"A review signal ({event_type}) was recorded for {student_row['name']}. Details: {details or 'No additional details'}. This is not proof of misconduct; please review in CareerIQ.")
    return {'ok':True}

@app.post('/messages/send')
@roles('company')
def send_message():
    recipient=request.form.get('recipient_id','',type=int)
    body=request.form.get('body','').strip()[:2000]
    interview_url=request.form.get('interview_url','').strip()[:500]
    student=g.db.execute("SELECT u.id FROM users u JOIN profiles p ON p.user_id=u.id WHERE u.id=? AND u.role='student' AND (p.recruitment_visible=1 OR EXISTS (SELECT 1 FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.student_id=u.id AND j.company_id=?))",(recipient,session['uid'])).fetchone()
    if not student: abort(404)
    if not body:
        flash('Enter a message for the student.','danger')
    elif interview_url and not re.fullmatch(r'https://[^\s]+',interview_url):
        flash('Interview link must be a valid HTTPS URL.','danger')
    else:
        g.db.execute('INSERT INTO messages(sender_id,recipient_id,body,interview_url) VALUES(?,?,?,?)',(session['uid'],recipient,body,interview_url)); audit('recruiter.message_sent','student',recipient,'Interview link included: '+('yes' if interview_url else 'no'))
        g.db.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(recipient,'New message from a company', 'A recruiter sent you a message'+(' with an interview link.' if interview_url else '.')))
        g.db.commit()
        recipient_row=g.db.execute('SELECT email,name FROM users WHERE id=?',(recipient,)).fetchone()
        send_email(recipient_row['email'],'New CareerIQ recruiter message',f"Hello {recipient_row['name']}, a company sent you a message on CareerIQ. Sign in to view it.")
        flash('Message sent to the student.','success')
    return redirect(url_for('candidates'))

@app.post('/messages/<int:mid>/read')
@roles('student')
def read_message(mid):
    cur=g.db.execute('UPDATE messages SET read_at=CURRENT_TIMESTAMP WHERE id=? AND recipient_id=?',(mid,session['uid']))
    if not cur.rowcount: abort(404)
    g.db.commit(); return redirect(url_for('dashboard'))

@app.post('/achievements')
@roles('student')
def add_achievement():
    title=request.form.get('title','').strip()[:150]
    category=request.form.get('category','Achievement').strip()
    organization=request.form.get('organization','').strip()[:150]
    achieved_on=request.form.get('achieved_on','').strip()[:10]
    description=request.form.get('description','').strip()[:800]
    if not title or category not in ('Achievement','Certification','Competition','Publication','Award','Volunteer'):
        flash('Enter an achievement title and valid category.','danger')
    else:
        g.db.execute('INSERT INTO achievements(student_id,title,category,organization,achieved_on,description) VALUES(?,?,?,?,?,?)',
                     (session['uid'],title,category,organization,achieved_on,description))
        audit('achievement.created','student',session['uid'],title)
        g.db.commit(); flash('Achievement added to your profile.','success')
    return redirect(url_for('dashboard'))

@app.post('/events')
@roles('student')
def add_event():
    title=request.form.get('title','').strip()[:150]
    organizer=request.form.get('organizer','').strip()[:150]
    event_date=request.form.get('event_date','').strip()[:10]
    participation_type=request.form.get('participation_type','Participant').strip()
    description=request.form.get('description','').strip()[:800]
    if not title or participation_type not in ('Participant','Volunteer','Organizer','Presenter','Winner'):
        flash('Enter an event title and valid participation type.','danger')
    else:
        g.db.execute('INSERT INTO events(student_id,title,organizer,event_date,participation_type,description) VALUES(?,?,?,?,?,?)',
                     (session['uid'],title,organizer,event_date,participation_type,description))
        audit('event.created','student',session['uid'],title)
        g.db.commit(); flash('Event participation added.','success')
    return redirect(url_for('dashboard'))

@app.post('/faculty/exam-alert/<int:eid>/review')
@roles('faculty')
def review_exam_alert(eid):
    row=g.db.execute('SELECT e.student_id,u.branch FROM exam_alerts e JOIN users u ON u.id=e.student_id WHERE e.id=?',(eid,)).fetchone()
    if not row: abort(404)
    if not is_admin_user() and (row['branch'] or '').strip().casefold() != (user()['branch'] or '').strip().casefold(): abort(403)
    cur=g.db.execute('UPDATE exam_alerts SET reviewed_at=CURRENT_TIMESTAMP WHERE id=?',(eid,))
    if not cur.rowcount: abort(404)
    audit('exam_alert.reviewed','exam_alert',eid,'Faculty marked alert reviewed')
    g.db.commit(); flash('Exam alert marked as reviewed.','success')
    return redirect(url_for('dashboard'))

@app.route('/roadmap')
@roles('student')
def roadmap():
    p=g.db.execute('SELECT * FROM profiles WHERE user_id=?',(session['uid'],)).fetchone(); return render_template('page.html',page='roadmap',p=p,roadmap=roadmap_with_optional_ai(p['target'],p['skills']))

@app.get('/account')
@login_required
def account_settings():
    return render_template('page.html',page='account')


@app.get('/account/export')
@login_required
def export_account_data():
    """Provide an authenticated export of the signed-in user's own records."""
    uid=session['uid']; db=g.db
    tables={
      'profile':('SELECT * FROM profiles WHERE user_id=?',(uid,)),
      'certificates':('SELECT id,title,issuer,status,file_name FROM certificates WHERE student_id=?',(uid,)),
      'projects':('SELECT * FROM projects WHERE student_id=?',(uid,)),
      'achievements':('SELECT * FROM achievements WHERE student_id=?',(uid,)),
      'events':('SELECT * FROM events WHERE student_id=?',(uid,)),
      'applications':('SELECT a.id,a.status,a.created_at,j.title,j.kind FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.student_id=?',(uid,)),
      'messages_received':('SELECT m.id,m.body,m.interview_url,m.read_at,m.created_at,u.name sender FROM messages m JOIN users u ON u.id=m.sender_id WHERE m.recipient_id=?',(uid,)),
      'notifications':('SELECT title,message,read_at,created_at FROM notifications WHERE user_id=?',(uid,)),
      'assessments':('SELECT score,correct_count,total_count,subject,created_at FROM attempts WHERE student_id=?',(uid,)),
      'academic_records':('SELECT record_type,subject,value,term,note,created_at,updated_at FROM academic_records WHERE student_id=?',(uid,)),
      'skill_certificates':('SELECT subject,score,correct_count,total_count,certificate_code,created_at FROM skill_certificates WHERE student_id=?',(uid,)),
    }
    data={'exported_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'account':{'name':user()['name'],'email':user()['email'],'role':user()['role']}}
    for key,(sql,args) in tables.items():
        try: data[key]=[dict(row) for row in db.execute(sql,args).fetchall()]
        except sqlite3.OperationalError: data[key]=[]
    if user()['role']=='company':
        data['company_jobs']=[dict(r) for r in db.execute('SELECT id,title,kind,description,skills,eligibility,location,status FROM jobs WHERE company_id=?',(uid,)).fetchall()]
        data['applications_received']=[dict(r) for r in db.execute('SELECT a.id,a.status,a.created_at,j.title opportunity,u.name student FROM applications a JOIN jobs j ON j.id=a.job_id JOIN users u ON u.id=a.student_id WHERE j.company_id=?',(uid,)).fetchall()]
        data['messages_sent']=[dict(r) for r in db.execute('SELECT m.id,m.body,m.interview_url,m.created_at,u.name recipient FROM messages m JOIN users u ON u.id=m.recipient_id WHERE m.sender_id=?',(uid,)).fetchall()]
    if user()['role']=='faculty':
        data['audit_actions']=[dict(r) for r in db.execute('SELECT action,target_type,target_id,details,created_at FROM audit_log WHERE actor_id=?',(uid,)).fetchall()]
    audit('privacy.exported','user',uid,'User exported their own CareerIQ data')
    db.commit()
    return Response(json.dumps(data,default=str,indent=2),mimetype='application/json',headers={'Content-Disposition':'attachment; filename="careeriq-personal-data.json"','Cache-Control':'no-store'})


@app.post('/account/delete')
@login_required
def delete_account():
    """Self-service deletion is disabled; institutional records are administrator controlled."""
    if not is_admin_user():
        abort(403, description='Account deletion is administrator-controlled. Contact your institution administrator.')
    uid=session['uid']; password=request.form.get('password','')
    account=g.db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
    if not account or not check_password_hash(account['password_hash'],password):
        flash('Password confirmation failed. Account was not deleted.','danger'); return redirect(url_for('dashboard'))
    # Remove stored certificate objects/files before deleting database references.
    certs=g.db.execute('SELECT stored_name FROM certificates WHERE student_id=?',(uid,)).fetchall()
    for cert in certs:
        name=cert['stored_name']
        if not name: continue
        try:
            if GCS_BUCKET:
                from google.cloud import storage
                storage.Client().bucket(GCS_BUCKET).blob('certificates/'+name).delete(if_generation_match=None)
            elif (UPLOAD_DIR/name).is_file(): (UPLOAD_DIR/name).unlink()
        except Exception as exc:
            app.logger.warning('Certificate cleanup deferred: %s',type(exc).__name__)
    # Remove rows that reference the account even in older SQLite schemas without cascade rules.
    g.db.execute('DELETE FROM applications WHERE student_id=? OR job_id IN (SELECT id FROM jobs WHERE company_id=?)',(uid,uid))
    g.db.execute('DELETE FROM saved_jobs WHERE student_id=? OR job_id IN (SELECT id FROM jobs WHERE company_id=?)',(uid,uid))
    g.db.execute('DELETE FROM messages WHERE sender_id=? OR recipient_id=?',(uid,uid))
    g.db.execute('DELETE FROM notifications WHERE user_id=?',(uid,))
    g.db.execute('DELETE FROM exam_alerts WHERE student_id=?',(uid,))
    g.db.execute('DELETE FROM attempts WHERE student_id=?',(uid,))
    g.db.execute('DELETE FROM certificates WHERE student_id=?',(uid,))
    g.db.execute('DELETE FROM projects WHERE student_id=?',(uid,))
    g.db.execute('DELETE FROM achievements WHERE student_id=?',(uid,))
    g.db.execute('DELETE FROM events WHERE student_id=?',(uid,))
    g.db.execute('DELETE FROM profiles WHERE user_id=?',(uid,))
    g.db.execute('DELETE FROM jobs WHERE company_id=?',(uid,))
    g.db.execute('DELETE FROM audit_log WHERE actor_id=?',(uid,))
    g.db.execute('DELETE FROM users WHERE id=?',(uid,)); g.db.commit(); session.clear()
    flash('Your CareerIQ account and associated application records were deleted. Backups and external email systems may follow separate retention schedules.','success')
    return redirect(url_for('home'))


@app.get('/admin/approvals')
@login_required
def admin_approvals():
    if not CAREERIQ_ADMIN_EMAIL or user()['email'].lower()!=CAREERIQ_ADMIN_EMAIL: abort(403)
    pending=g.db.execute("SELECT id,name,email,role FROM users WHERE account_status='pending' ORDER BY id").fetchall()
    return render_template('page.html',page='admin',pending=pending)


@app.post('/admin/approvals/<int:uid>')
@login_required
def decide_account_approval(uid):
    if not CAREERIQ_ADMIN_EMAIL or user()['email'].lower()!=CAREERIQ_ADMIN_EMAIL: abort(403)
    decision=request.form.get('decision','')
    if decision not in ('approve','reject'): abort(400)
    row=g.db.execute("SELECT id,name,email,role FROM users WHERE id=? AND account_status='pending'",(uid,)).fetchone()
    if not row: abort(404)
    if decision=='approve':
        g.db.execute("UPDATE users SET account_status='approved' WHERE id=?",(uid,))
        g.db.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(uid,'Account approved','Your CareerIQ '+row['role']+' account has been approved. You can sign in now.'))
        g.db.commit(); send_email(row['email'],'CareerIQ account approved','Your CareerIQ account was approved. You can now sign in.')
        flash('Account approved.','success')
    else:
        g.db.execute("DELETE FROM users WHERE id=?",(uid,)); g.db.commit(); flash('Pending account rejected and removed.','info')
    return redirect(url_for('admin_approvals'))




def is_admin_user():
    current=user()
    return bool(current and CAREERIQ_ADMIN_EMAIL and current['email'].lower()==CAREERIQ_ADMIN_EMAIL)

@app.get('/admin')
@login_required
def admin_dashboard():
    if not is_admin_user(): abort(403)
    q=request.args.get('q','').strip()[:100]
    users=g.db.execute("SELECT users.id,users.name,users.email,users.role,users.account_status,users.branch,users.section,users.roll_no,users.subject,profiles.score,profiles.target,profiles.skills,profiles.bio FROM users LEFT JOIN profiles ON profiles.user_id=users.id WHERE (?='' OR name LIKE ? OR email LIKE ? OR branch LIKE ? OR roll_no LIKE ?) ORDER BY role,name",(q,f'%{q}%',f'%{q}%',f'%{q}%',f'%{q}%')).fetchall()
    records=g.db.execute("SELECT ar.*,s.name student,s.branch,s.roll_no,f.name faculty FROM academic_records ar JOIN users s ON s.id=ar.student_id JOIN users f ON f.id=ar.faculty_id ORDER BY ar.id DESC LIMIT 100").fetchall()
    audit_rows=g.db.execute("SELECT a.*,u.name actor_name FROM audit_log a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 100").fetchall()
    return render_template('page.html',page='admin_dashboard',users=users,records=records,audit_rows=audit_rows,q=q,stats={r['role']:r['n'] for r in g.db.execute('SELECT role,COUNT(*) n FROM users GROUP BY role').fetchall()})

@app.get('/admin/user/<int:uid>')
@login_required
def admin_user_detail(uid):
    if not is_admin_user(): abort(403)
    account=g.db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
    if not account: abort(404)
    data={}
    if account['role']=='student':
        data['profile']=g.db.execute('SELECT * FROM profiles WHERE user_id=?',(uid,)).fetchone()
        data['certificates']=g.db.execute('SELECT id,title,issuer,status,category,file_name,stored_name FROM certificates WHERE student_id=? ORDER BY id DESC',(uid,)).fetchall()
        data['projects']=g.db.execute('SELECT p.*,pl.repo_url,pl.live_url,pl.tech_stack FROM projects p LEFT JOIN project_links pl ON pl.project_id=p.id WHERE p.student_id=? ORDER BY p.id DESC',(uid,)).fetchall()
        data['achievements']=g.db.execute('SELECT * FROM achievements WHERE student_id=? ORDER BY id DESC',(uid,)).fetchall()
        data['events']=g.db.execute('SELECT * FROM events WHERE student_id=? ORDER BY id DESC',(uid,)).fetchall()
        data['academic']=g.db.execute('SELECT * FROM academic_records WHERE student_id=? ORDER BY id DESC',(uid,)).fetchall()
        data['attempts']=g.db.execute('SELECT * FROM attempts WHERE student_id=? ORDER BY id DESC',(uid,)).fetchall()
        data['applications']=g.db.execute('SELECT a.*,j.title,j.kind FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.student_id=? ORDER BY a.id DESC',(uid,)).fetchall()
    elif account['role']=='faculty':
        data['students']=g.db.execute("SELECT id,name,roll_no,section FROM users WHERE role='student' AND lower(trim(branch))=lower(trim(?)) ORDER BY name",(account['branch'] or '',)).fetchall()
        data['academic_records']=g.db.execute("SELECT ar.*,u.name student,u.roll_no FROM academic_records ar JOIN users u ON u.id=ar.student_id WHERE ar.faculty_id=? ORDER BY ar.id DESC",(uid,)).fetchall()
    else:
        data['jobs']=g.db.execute('SELECT * FROM jobs WHERE company_id=? ORDER BY id DESC',(uid,)).fetchall()
        data['applications']=g.db.execute('SELECT a.*,j.title,u.name student FROM applications a JOIN jobs j ON j.id=a.job_id JOIN users u ON u.id=a.student_id WHERE j.company_id=? ORDER BY a.id DESC',(uid,)).fetchall()
        data['messages']=g.db.execute('SELECT m.*,u.name recipient FROM messages m JOIN users u ON u.id=m.recipient_id WHERE m.sender_id=? ORDER BY m.id DESC',(uid,)).fetchall()
    audit('admin.account_detail_viewed','user',uid,'Administrator viewed account data'); g.db.commit()
    return render_template('page.html',page='admin_detail',account=account,data=data)

@app.post('/admin/user/<int:uid>/edit')
@login_required
def admin_edit_account(uid):
    if not is_admin_user(): abort(403)
    row=g.db.execute('SELECT id,role,email FROM users WHERE id=?',(uid,)).fetchone()
    if not row: abort(404)
    if row['email'].lower()==CAREERIQ_ADMIN_EMAIL: abort(403)
    name=request.form.get('name','').strip()[:100]
    branch=request.form.get('branch','').strip()[:100]
    subject=request.form.get('subject','').strip()[:120]
    if not name: abort(400)
    if row['role']=='faculty' and (not branch or not subject): abort(400)
    g.db.execute('UPDATE users SET name=?,branch=?,subject=? WHERE id=?',(name,branch,subject,uid))
    g.db.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(uid,'Account details updated by administrator','Your account details were updated by the administrator.'))
    audit('admin.account_details_changed','user',uid,f'Role={row["role"]}; branch={branch}; subject={subject}'); g.db.commit()
    flash('Account details updated and account holder notified.','success'); return redirect(url_for('admin_dashboard'))

@app.post('/admin/user/<int:uid>/delete')
@login_required
def admin_delete_account(uid):
    if not is_admin_user(): abort(403)
    row=g.db.execute('SELECT id,name,email,role FROM users WHERE id=?',(uid,)).fetchone()
    if not row: abort(404)
    if row['email'].lower()==CAREERIQ_ADMIN_EMAIL: abort(403)
    if row['role']=='faculty' and g.db.execute('SELECT 1 FROM academic_records WHERE faculty_id=? LIMIT 1',(uid,)).fetchone():
        flash('This faculty account has academic records. Suspend it or transfer its records before deletion.','danger')
        return redirect(url_for('admin_dashboard'))
    certs=g.db.execute('SELECT stored_name FROM certificates WHERE student_id=?',(uid,)).fetchall()
    for cert in certs:
        name=cert['stored_name']
        if not name: continue
        try:
            if GCS_BUCKET:
                from google.cloud import storage
                storage.Client().bucket(GCS_BUCKET).blob('certificates/'+name).delete()
            elif (UPLOAD_DIR/name).is_file(): (UPLOAD_DIR/name).unlink()
        except Exception as exc: app.logger.warning('Admin certificate cleanup deferred: %s',type(exc).__name__)
    g.db.execute('DELETE FROM applications WHERE student_id=? OR job_id IN (SELECT id FROM jobs WHERE company_id=?)',(uid,uid))
    g.db.execute('DELETE FROM saved_jobs WHERE student_id=? OR job_id IN (SELECT id FROM jobs WHERE company_id=?)',(uid,uid))
    g.db.execute('DELETE FROM messages WHERE sender_id=? OR recipient_id=?',(uid,uid))
    g.db.execute('DELETE FROM notifications WHERE user_id=?',(uid,))
    g.db.execute('DELETE FROM exam_alerts WHERE student_id=?',(uid,))
    g.db.execute('DELETE FROM attempts WHERE student_id=?',(uid,))
    g.db.execute('DELETE FROM exam_sessions WHERE student_id=?',(uid,))
    g.db.execute('DELETE FROM skill_certificates WHERE student_id=?',(uid,))
    g.db.execute('DELETE FROM academic_records WHERE student_id=?',(uid,))
    g.db.execute('DELETE FROM certificates WHERE student_id=?',(uid,))
    g.db.execute('DELETE FROM projects WHERE student_id=?',(uid,))
    g.db.execute('DELETE FROM achievements WHERE student_id=?',(uid,))
    g.db.execute('DELETE FROM events WHERE student_id=?',(uid,))
    g.db.execute('DELETE FROM profiles WHERE user_id=?',(uid,))
    g.db.execute('DELETE FROM password_resets WHERE user_id=?',(uid,))
    g.db.execute('DELETE FROM jobs WHERE company_id=?',(uid,))
    audit('admin.account_deleted','user',uid,f'Administrator deleted {row["role"]} account {row["email"]}')
    g.db.execute('DELETE FROM users WHERE id=?',(uid,)); g.db.commit()
    flash('Account and its active application data were deleted by the administrator. External email and backup retention may differ.','success')
    return redirect(url_for('admin_dashboard'))

@app.post('/admin/user/<int:uid>/status')
@login_required
def admin_user_status(uid):
    if not is_admin_user(): abort(403)
    status=request.form.get('status','')
    if status not in ('approved','pending','suspended'): abort(400)
    row=g.db.execute('SELECT id,role,email FROM users WHERE id=?',(uid,)).fetchone()
    if not row: abort(404)
    if row['email'].lower()==CAREERIQ_ADMIN_EMAIL: abort(403)
    g.db.execute('UPDATE users SET account_status=? WHERE id=?',(status,uid))
    g.db.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(uid,'Account access updated',f'Administrator changed your account status to {status}.'))
    audit('admin.account_status_changed','user',uid,status); g.db.commit()
    return redirect(url_for('admin_dashboard'))

@app.post('/admin/student/<int:sid>/edit')
@login_required
def admin_edit_student(sid):
    if not is_admin_user(): abort(403)
    st=g.db.execute("SELECT id FROM users WHERE id=? AND role='student'",(sid,)).fetchone()
    if not st: abort(404)
    name=request.form.get('name','').strip()[:100]
    branch=request.form.get('branch','').strip()[:100]
    section=request.form.get('section','').strip()[:20]
    roll_no=request.form.get('roll_no','').strip().upper()[:30]
    target=request.form.get('target','Cloud Engineer')
    skills=request.form.get('skills','').strip()[:1000]
    bio=request.form.get('bio','').strip()[:1000]
    try: score=float(request.form.get('score','8'))
    except ValueError: score=-1
    duplicate=g.db.execute("SELECT id FROM users WHERE role='student' AND id<>? AND lower(trim(branch))=lower(trim(?)) AND lower(trim(roll_no))=lower(trim(?))",(sid,branch,roll_no)).fetchone()
    if not all((name,branch,section,roll_no)) or target not in CAREERS or not 0<=score<=10 or duplicate:
        flash('Check required fields, unique branch/roll number, career goal, and score between 0 and 10.','danger')
        return redirect(url_for('admin_dashboard'))
    g.db.execute('UPDATE users SET name=?,branch=?,section=?,roll_no=? WHERE id=?',(name,branch,section,roll_no,sid))
    g.db.execute('UPDATE profiles SET department=?,score=?,target=?,skills=?,bio=? WHERE user_id=?',(branch,score,target,skills,bio,sid))
    g.db.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(sid,'Student data changed by administrator',f'Your student profile or academic data was changed by the administrator. Branch: {branch}; section: {section}; roll number: {roll_no}; academic score: {score}/10. Career goal and skills may also have been updated. Contact the administrator if you need details.'))
    audit('admin.student_identity_changed','student',sid,f'Branch={branch}; Section={section}; Roll={roll_no}; Score={score}')
    g.db.commit(); flash('Student record updated. Student has been notified.','success'); return redirect(url_for('admin_dashboard'))

@app.post('/faculty/academic-record')
@roles('faculty')
def faculty_add_academic_record():
    sid=request.form.get('student_id',type=int); record_type=request.form.get('record_type',''); value=request.form.get('value','').strip()[:80]; subject=request.form.get('subject','').strip()[:100]; term=request.form.get('term','').strip()[:80]; note=request.form.get('note','').strip()[:300]
    if record_type not in ('Attendance','Marks','SGPA','CGPA') or not value: abort(400)
    student=g.db.execute("SELECT id,branch FROM users WHERE id=? AND role='student'",(sid,)).fetchone()
    if not student or (student['branch'] or '').strip().casefold() != (user()['branch'] or '').strip().casefold(): abort(403)
    try:
        numeric=float(value.replace('%',''))
        if record_type=='Attendance' and not 0<=numeric<=100: raise ValueError()
        if record_type=='Marks' and not 0<=numeric<=100: raise ValueError()
        if record_type in ('SGPA','CGPA') and not 0<=numeric<=10: raise ValueError()
    except ValueError: flash('Use 0–100 for attendance/marks and 0–10 for SGPA/CGPA.','danger'); return redirect(url_for('dashboard'))
    g.db.execute('INSERT INTO academic_records(student_id,faculty_id,record_type,subject,value,term,note) VALUES(?,?,?,?,?,?,?)',(sid,session['uid'],record_type,subject,value,term,note))
    g.db.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(sid,record_type+' record posted',f'Faculty posted your {record_type.lower()} record: {value}'+(f' ({subject})' if subject else '')+'. If this appears incorrect, contact the administrator.'))
    audit('faculty.academic_record_created','student',sid,f'{record_type}={value}; subject={subject}; term={term}'); g.db.commit(); flash('Academic record posted and student notified.','success'); return redirect(url_for('dashboard'))

@app.post('/admin/academic-record/<int:rid>/edit')
@login_required
def admin_edit_academic_record(rid):
    if not is_admin_user(): abort(403)
    value=request.form.get('value','').strip()[:80]; note=request.form.get('note','').strip()[:300]
    row=g.db.execute('SELECT student_id,record_type FROM academic_records WHERE id=?',(rid,)).fetchone()
    if not row: abort(404)
    g.db.execute('UPDATE academic_records SET value=?,note=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(value,note,rid))
    g.db.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(row['student_id'],'Academic data altered by administrator',f'Your {row["record_type"].lower()} record was changed by the administrator. New value: {value}.'))
    audit('admin.academic_record_changed','academic_record',rid,f'{row["record_type"]}={value}'); g.db.commit(); return redirect(url_for('admin_dashboard'))

@app.get('/student/resume/<int:sid>')
@login_required
def student_resume(sid):
    if session.get('role')=='student' and session['uid']!=sid: abort(403)
    student=g.db.execute("SELECT u.id,u.name,u.email,u.branch,u.section,u.roll_no,p.year,p.target,p.skills,p.bio,p.score,p.recruitment_visible FROM users u JOIN profiles p ON p.user_id=u.id WHERE u.id=? AND u.role='student'",(sid,)).fetchone()
    if not student: abort(404)
    if session.get('role')=='faculty' and not is_admin_user() and (student['branch'] or '').strip().casefold() != (user()['branch'] or '').strip().casefold(): abort(403)
    if session.get('role')=='company' and not student['recruitment_visible']:
        applied=g.db.execute('SELECT 1 FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.student_id=? AND j.company_id=? LIMIT 1',(sid,session['uid'])).fetchone()
        if not applied: abort(404)
    certs=g.db.execute("SELECT title,issuer,status,category FROM certificates WHERE student_id=? AND status='Verified'",(sid,)).fetchall()
    projects=g.db.execute('SELECT p.*,pl.repo_url,pl.live_url,pl.tech_stack,pl.role_description FROM projects p LEFT JOIN project_links pl ON pl.project_id=p.id WHERE p.student_id=? ORDER BY p.id DESC',(sid,)).fetchall()
    achievements=g.db.execute('SELECT * FROM achievements WHERE student_id=? ORDER BY id DESC',(sid,)).fetchall()
    events=g.db.execute('SELECT * FROM events WHERE student_id=? ORDER BY id DESC',(sid,)).fetchall()
    academic=g.db.execute('SELECT record_type,subject,value,term,created_at FROM academic_records WHERE student_id=? ORDER BY id DESC',(sid,)).fetchall() if session.get('role')!='company' else []
    return render_template('page.html',page='resume',student=student,certs=certs,projects=projects,achievements=achievements,events=events,academic=academic)

@app.get('/skill-certificate/<int:cert_id>')
@login_required
def skill_certificate(cert_id):
    row=g.db.execute('SELECT sc.*,u.name FROM skill_certificates sc JOIN users u ON u.id=sc.student_id WHERE sc.id=?',(cert_id,)).fetchone()
    if not row: abort(404)
    if row['student_id']!=session['uid'] and not is_admin_user(): abort(403)
    return render_template('page.html',page='skill_certificate',certificate=row)

@app.post('/integrations/job-feed')
def ingest_authorized_job_feed():
    """Accept normalized postings from a trusted scheduler/authorized provider adapter."""
    expected=JOB_FEED_TOKEN
    supplied=request.headers.get('X-Job-Feed-Token','')
    if not expected or not secrets.compare_digest(expected,supplied): abort(403)
    payload=request.get_json(silent=True)
    if not isinstance(payload,dict) or not isinstance(payload.get('jobs'),list): abort(400)
    # Provider accounts are explicitly configured; never create arbitrary company identities from feed payloads.
    provider_email=os.environ.get('JOB_FEED_COMPANY_EMAIL','').strip().lower()
    company=g.db.execute("SELECT id FROM users WHERE email=? AND role='company' AND account_status='approved'",(provider_email,)).fetchone()
    if not company: return jsonify(error='Configure JOB_FEED_COMPANY_EMAIL to an approved company account'),503
    inserted=0
    for item in payload['jobs'][:100]:
        if not isinstance(item,dict): continue
        title=str(item.get('title','')).strip()[:150]; kind=str(item.get('kind','Job')).strip()
        if not title or kind not in ('Job','Internship'): continue
        description=str(item.get('description','')).strip()[:2000]
        skills=str(item.get('skills','')).strip()[:500]
        eligibility=str(item.get('eligibility','')).strip()[:500]
        location=str(item.get('location','Not specified')).strip()[:150]
        # Prevent duplicate imports by checking provider + title + description.
        exists=g.db.execute("SELECT 1 FROM jobs WHERE company_id=? AND title=? AND description=? LIMIT 1",(company['id'],title,description)).fetchone()
        if exists: continue
        cur=g.db.execute('INSERT INTO jobs(company_id,title,kind,description,skills,eligibility,location) VALUES(?,?,?,?,?,?,?)',(company['id'],title,kind,description,skills,eligibility,location)); inserted+=1
        job_skills={x.strip().lower() for x in skills.split(',') if x.strip()}
        students=g.db.execute("SELECT u.id,p.skills FROM users u JOIN profiles p ON p.user_id=u.id WHERE u.role='student' AND u.account_status='approved'").fetchall()
        for st in students:
            their_skills={x.strip().lower() for x in (st['skills'] or '').split(',') if x.strip()}
            if not job_skills or job_skills.intersection(their_skills):
                g.db.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(st['id'],'New matching opportunity',f'{title} was imported from an authorized opportunity feed.'))
    g.db.commit(); audit('jobs.feed_ingested','job_feed','authorized-provider',f'{inserted} postings imported'); g.db.commit()
    return jsonify(status='ok',inserted=inserted,received=min(len(payload['jobs']),100)),200


@app.get('/health')
def health():
    try:
        g.db.execute('SELECT 1').fetchone()
        return {'status':'ok','app':'CareerIQ','database':'reachable','storage':'gcs' if GCS_BUCKET else 'local'}
    except Exception:
        app.logger.exception('Health check failed')
        return {'status':'degraded','app':'CareerIQ'},503


@app.errorhandler(403)
def forbidden(e): return render_template('page.html',page='error',code=403,message='You do not have permission to access this page.'),403
@app.errorhandler(404)
def not_found(e): return render_template('page.html',page='error',code=404,message='The requested page or record was not found.'),404

if APP_ENV == 'production':
    # Fail closed rather than silently deploying ephemeral SQLite/local uploads on Cloud Run.
    raise RuntimeError('Production deployment remains blocked: PostgreSQL/Cloud SQL persistence is not yet integrated. GCS uploads, optional SMTP and optional Vertex AI adapters are available, but they do not replace a tested production database adapter.')
init_db()
if __name__=='__main__': app.run(debug=os.environ.get('FLASK_DEBUG')=='1')
