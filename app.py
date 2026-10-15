import os
from datetime import date, datetime, time, timedelta
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_login import (LoginManager, UserMixin, current_user, login_required,
                         login_user, logout_user)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    preferred_hours = db.Column(db.Integer, nullable=False, default=2)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)


class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default='')
    difficulty = db.Column(db.String(20), default='Medium')
    priority = db.Column(db.String(20), default='Medium')
    exam_date = db.Column(db.Date, nullable=True)


class StudySession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id', ondelete='CASCADE'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('study_plan.id', ondelete='SET NULL'), nullable=True)
    topic = db.Column(db.String(160), nullable=False)
    session_date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='planned')
    notes = db.Column(db.Text, default='')
    subject = db.relationship('Subject')


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id', ondelete='SET NULL'), nullable=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, default='')
    due_date = db.Column(db.Date, nullable=True, index=True)
    priority = db.Column(db.String(20), nullable=False, default='Medium')
    status = db.Column(db.String(20), nullable=False, default='pending')
    subject = db.relationship('Subject')


class Exam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    exam_date = db.Column(db.Date, nullable=False, index=True)
    description = db.Column(db.Text, default='')
    subject = db.relationship('Subject')


class StudyPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, default='')
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    daily_goal_minutes = db.Column(db.Integer, nullable=False, default=60)
    status = db.Column(db.String(20), nullable=False, default='active')


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv('SECRET_KEY', 'dev-only-change-this-secret'),
        SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL', 'sqlite:///study_planner.db'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.getenv('SESSION_COOKIE_SECURE', '0') == '1',
    )
    if test_config:
        app.config.update(test_config)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    csrf.init_app(app)

    @app.context_processor
    def inject_globals():
        return {'today': date.today(), 'timedelta': timedelta}

    @app.route('/')
    @login_required
    def dashboard():
        from services.dashboard_service import get_dashboard_data

        try:
            dashboard_data = get_dashboard_data(
                current_user.id,
                database=db,
                session_model=StudySession,
                task_model=Task,
                exam_model=Exam,
            )
        except (SQLAlchemyError, RuntimeError) as error:
            app.logger.error(
                'Dashboard data query failed for authenticated user id=%s (error type=%s)',
                current_user.id,
                type(error).__name__,
            )
            return render_template('dashboard.html', dashboard=None, dashboard_error=True), 503
        return render_template('dashboard.html', dashboard=dashboard_data, dashboard_error=False)

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        if request.method == 'POST':
            name, email, password = request.form.get('name', '').strip(), request.form.get('email', '').strip().lower(), request.form.get('password', '')
            if len(name) < 2 or len(name) > 100 or '@' not in email or len(password) < 8:
                flash('Enter a valid name and email, and use a password with at least 8 characters.', 'error')
            elif User.query.filter(func.lower(User.email) == email).first():
                flash('An account with that email already exists.', 'error')
            else:
                user = User(name=name, email=email); user.set_password(password)
                db.session.add(user); db.session.commit(); login_user(user)
                return redirect(url_for('dashboard'))
        return render_template('auth.html', mode='register')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            user = User.query.filter(func.lower(User.email) == request.form.get('email', '').strip().lower()).first()
            if user and user.verify_password(request.form.get('password', '')):
                login_user(user, remember=False); return redirect(url_for('dashboard'))
            flash('Email or password is incorrect.', 'error')
        return render_template('auth.html', mode='login')

    @app.post('/logout')
    @login_required
    def logout():
        logout_user(); return redirect(url_for('login'))

    def owned(model, ident):
        item = db.session.get(model, ident)
        if not item or item.user_id != current_user.id:
            abort(404)
        return item

    def owned_subject(subject_id):
        if subject_id in (None, ''):
            return None
        subject = Subject.query.filter_by(id=subject_id, user_id=current_user.id).first()
        if not subject:
            abort(400)
        return subject

    @app.route('/subjects', methods=['GET', 'POST'])
    @login_required
    def subjects_page():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            if not name or len(name) > 100: flash('Subject name is required (up to 100 characters).', 'error')
            else:
                exam = request.form.get('exam_date') or None
                db.session.add(Subject(user_id=current_user.id, name=name, description=request.form.get('description', '').strip(), difficulty=request.form.get('difficulty', 'Medium'), priority=request.form.get('priority', 'Medium'), exam_date=date.fromisoformat(exam) if exam else None)); db.session.commit(); flash('Subject added.', 'success'); return redirect(url_for('subjects_page'))
        return render_template('subjects.html', subjects=Subject.query.filter_by(user_id=current_user.id).order_by(Subject.name).all())

    @app.post('/subjects/<int:item_id>/delete')
    @login_required
    def delete_subject(item_id):
        item = owned(Subject, item_id); db.session.delete(item); db.session.commit(); flash('Subject deleted.', 'success'); return redirect(url_for('subjects_page'))

    @app.route('/timetable', methods=['GET', 'POST'])
    @login_required
    def timetable():
        if request.method == 'POST':
            try:
                d = date.fromisoformat(request.form['session_date']); start = time.fromisoformat(request.form['start_time']); end = time.fromisoformat(request.form['end_time']); subject = owned_subject(int(request.form['subject_id']))
                if end <= start or (datetime.combine(d, end)-datetime.combine(d, start)).total_seconds() > 8 * 3600: raise ValueError()
                overlap = StudySession.query.filter_by(user_id=current_user.id, session_date=d).filter(StudySession.start_time < end, StudySession.end_time > start).first()
                if overlap: flash('That time overlaps another study session.', 'error')
                else:
                    db.session.add(StudySession(user_id=current_user.id, subject_id=subject.id, topic=request.form.get('topic', '').strip()[:160], session_date=d, start_time=start, end_time=end, notes=request.form.get('notes', '').strip())); db.session.commit(); flash('Study session scheduled.', 'success'); return redirect(url_for('timetable'))
            except (ValueError, KeyError): flash('Enter valid dates and times, with an end time after the start time.', 'error')
        sessions = StudySession.query.filter_by(user_id=current_user.id).order_by(StudySession.session_date, StudySession.start_time).all()
        return render_template('timetable.html', sessions=sessions, subjects=Subject.query.filter_by(user_id=current_user.id).all())

    @app.post('/sessions/<int:item_id>/complete')
    @login_required
    def complete_session(item_id):
        item = owned(StudySession, item_id); item.status = 'completed'; db.session.commit(); flash('Session marked complete.', 'success'); return redirect(url_for('timetable'))

    @app.post('/sessions/<int:item_id>/delete')
    @login_required
    def delete_session(item_id):
        db.session.delete(owned(StudySession, item_id)); db.session.commit(); return redirect(url_for('timetable'))

    @app.route('/tasks', methods=['GET', 'POST'])
    @login_required
    def tasks_page():
        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            if not title or len(title) > 160: flash('Task title is required.', 'error')
            else:
                due = request.form.get('due_date') or None
                db.session.add(Task(user_id=current_user.id, subject_id=(owned_subject(int(request.form['subject_id'])).id if request.form.get('subject_id') else None), title=title, description=request.form.get('description', '').strip(), due_date=date.fromisoformat(due) if due else None, priority=request.form.get('priority', 'Medium'))); db.session.commit(); flash('Task added.', 'success'); return redirect(url_for('tasks_page'))
        tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.due_date, Task.id.desc()).all()
        return render_template('tasks.html', tasks=tasks, subjects=Subject.query.filter_by(user_id=current_user.id).all())

    @app.post('/tasks/<int:item_id>/status')
    @login_required
    def task_status(item_id):
        item = owned(Task, item_id); value = request.form.get('status')
        if value not in ('pending', 'in progress', 'completed'): abort(400)
        item.status = value; db.session.commit(); return redirect(url_for('tasks_page'))

    @app.post('/tasks/<int:item_id>/delete')
    @login_required
    def delete_task(item_id):
        db.session.delete(owned(Task, item_id)); db.session.commit(); return redirect(url_for('tasks_page'))

    @app.route('/exams', methods=['GET', 'POST'])
    @login_required
    def exams_page():
        if request.method == 'POST':
            try:
                subject = owned_subject(int(request.form['subject_id'])); exam_date = date.fromisoformat(request.form['exam_date']); title = request.form.get('title', '').strip()
                if not title: raise ValueError()
                db.session.add(Exam(user_id=current_user.id, subject_id=subject.id, title=title[:160], exam_date=exam_date, description=request.form.get('description', '').strip())); db.session.commit(); flash('Exam added.', 'success'); return redirect(url_for('exams_page'))
            except (ValueError, KeyError): flash('Enter a title and valid exam date.', 'error')
        exams = Exam.query.filter_by(user_id=current_user.id).order_by(Exam.exam_date).all()
        return render_template('exams.html', exams=exams, subjects=Subject.query.filter_by(user_id=current_user.id).all())

    @app.post('/exams/<int:item_id>/delete')
    @login_required
    def delete_exam(item_id):
        db.session.delete(owned(Exam, item_id)); db.session.commit(); return redirect(url_for('exams_page'))

    @app.route('/plans', methods=['GET', 'POST'])
    @login_required
    def plans_page():
        if request.method == 'POST':
            try:
                start, end = date.fromisoformat(request.form['start_date']), date.fromisoformat(request.form['end_date']); title = request.form.get('title', '').strip(); goal = int(request.form.get('daily_goal_minutes', '60'))
                if not title or end < start or not 15 <= goal <= 720: raise ValueError()
                db.session.add(StudyPlan(user_id=current_user.id, title=title[:160], description=request.form.get('description', '').strip(), start_date=start, end_date=end, daily_goal_minutes=goal)); db.session.commit(); flash('Study plan created.', 'success'); return redirect(url_for('plans_page'))
            except (ValueError, KeyError): flash('Check the title, dates, and daily goal (15–720 minutes).', 'error')
        plans = StudyPlan.query.filter_by(user_id=current_user.id).order_by(StudyPlan.start_date.desc()).all()
        return render_template('plans.html', plans=plans)

    @app.post('/plans/<int:item_id>/delete')
    @login_required
    def delete_plan(item_id):
        db.session.delete(owned(StudyPlan, item_id)); db.session.commit(); return redirect(url_for('plans_page'))

    @app.route('/profile', methods=['GET', 'POST'])
    @login_required
    def profile():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            try: hours = int(request.form.get('preferred_hours', '2'))
            except ValueError: hours = 0
            if len(name) < 2 or not 1 <= hours <= 16: flash('Enter a valid name and study hours (1–16).', 'error')
            else:
                current_user.name, current_user.preferred_hours = name, hours; db.session.commit(); flash('Profile updated.', 'success')
        return render_template('profile.html')

    @app.route('/health')
    def health():
        return {'status': 'ok'}

    @app.cli.command('init-db')
    def init_db_command():
        """Create tables that do not exist; existing data is never reset."""
        db.create_all()
        print('Database tables are ready.')

    return app


app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=os.getenv('FLASK_DEBUG') == '1')
