from datetime import date, time

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from app import Exam, StudySession, Subject, Task, User, db
from services import dashboard_service


TODAY = date(2026, 10, 14)  # Wednesday; week begins Monday 12 October.


def make_user(name, email):
    user = User(name=name, email=email)
    user.set_password('a-secure-test-password')
    db.session.add(user)
    db.session.flush()
    return user


def add_session(user_id, subject_id, day, start, end, status='completed', topic='Study'):
    session = StudySession(
        user_id=user_id, subject_id=subject_id, session_date=day,
        start_time=start, end_time=end, status=status, topic=topic,
    )
    db.session.add(session)
    return session


def dashboard_data(user_id, today=TODAY):
    return dashboard_service.get_dashboard_data(
        user_id,
        today=today,
        database=db,
        session_model=StudySession,
        task_model=Task,
        exam_model=Exam,
    )


def test_dashboard_aggregates_boundaries_users_and_completed_sessions(app):
    with app.app_context():
        student = make_user('Student One', 'one@example.com')
        other = make_user('Student Two', 'two@example.com')
        own_subject = Subject(user_id=student.id, name='Physics')
        other_subject = Subject(user_id=other.id, name='Chemistry')
        db.session.add_all([own_subject, other_subject])
        db.session.flush()

        add_session(student.id, own_subject.id, date(2026, 10, 12), time(0, 0), time(1, 0))
        add_session(student.id, own_subject.id, TODAY, time(0, 0), time(1, 30), topic='Midnight start')
        add_session(student.id, own_subject.id, TODAY, time(10, 0), time(11, 0), status='planned')
        add_session(student.id, own_subject.id, date(2026, 10, 19), time(0, 0), time(2, 0))
        add_session(other.id, other_subject.id, TODAY, time(0, 0), time(3, 0))

        db.session.add_all([
            Task(user_id=student.id, subject_id=own_subject.id, title='Due today', due_date=TODAY, status='pending'),
            Task(user_id=student.id, subject_id=own_subject.id, title='No date', due_date=None, status='in progress'),
            Task(user_id=student.id, subject_id=own_subject.id, title='Done already', due_date=date(2026, 10, 1), status='completed'),
            Task(user_id=other.id, subject_id=other_subject.id, title='Private task', due_date=TODAY, status='pending'),
            Exam(user_id=student.id, subject_id=own_subject.id, title='Today exam', exam_date=TODAY),
            Exam(user_id=student.id, subject_id=own_subject.id, title='Tomorrow exam', exam_date=date(2026, 10, 15)),
            Exam(user_id=student.id, subject_id=own_subject.id, title='Past exam', exam_date=date(2026, 10, 13)),
            Exam(user_id=other.id, subject_id=other_subject.id, title='Other exam', exam_date=TODAY),
        ])
        db.session.commit()

        data = dashboard_data(student.id)
        assert data['completed_hours_today'] == 1.5
        assert data['completed_hours_total'] == 4.5
        assert [day['hours'] for day in data['weekly']] == [1.0, 0.0, 1.5, 0.0, 0.0, 0.0, 0.0]
        assert len(data['weekly']) == 7
        assert [session.topic for session in data['sessions']] == ['Midnight start', 'Study']
        assert [task.title for task in data['tasks']] == ['Due today', 'No date']
        assert data['tasks'][0].due_state == 'Due today'
        assert data['tasks'][1].due_state == 'No due date'
        assert [exam.title for exam in data['exams']] == ['Today exam', 'Tomorrow exam']
        assert [exam.days_remaining for exam in data['exams']] == [0, 1]
        # The schema has no study_logs table, so completed sessions are counted once.
        assert 'study_logs' not in inspect(db.engine).get_table_names()


def test_empty_dashboard_returns_seven_zero_days(app):
    with app.app_context():
        student = make_user('Empty Student', 'empty@example.com')
        data = dashboard_data(student.id)
        assert data['sessions'] == []
        assert data['tasks'] == []
        assert data['exams'] == []
        assert data['completed_hours_today'] == 0
        assert data['completed_hours_total'] == 0
        assert [day['hours'] for day in data['weekly']] == [0] * 7


def test_overdue_tasks_are_sorted_first_and_missing_dates_last(app):
    with app.app_context():
        student = make_user('Task Student', 'task@example.com')
        subject = Subject(user_id=student.id, name='Math')
        db.session.add(subject)
        db.session.flush()
        db.session.add_all([
            Task(user_id=student.id, subject_id=subject.id, title='Undated', status='pending'),
            Task(user_id=student.id, subject_id=subject.id, title='Upcoming', due_date=date(2026, 10, 15), status='pending'),
            Task(user_id=student.id, subject_id=subject.id, title='Overdue', due_date=date(2026, 10, 13), status='pending'),
        ])
        db.session.commit()
        data = dashboard_data(student.id)
        assert [task.title for task in data['tasks']] == ['Overdue', 'Upcoming', 'Undated']
        assert [task.due_state for task in data['tasks']] == ['Overdue', 'Upcoming', 'No due date']


def test_dashboard_requires_valid_authentication(client):
    assert client.get('/').status_code == 302
    with client.session_transaction() as session:
        session['_user_id'] = 'not-an-integer'
        session['_fresh'] = True
    assert client.get('/').status_code == 302


def test_dashboard_shows_database_error_without_exposing_details(client, app, monkeypatch, caplog):
    response = client.post('/register', data={
        'name': 'Error Student', 'email': 'error@example.com',
        'password': 'a-secure-test-password',
    })
    assert response.status_code == 302

    def fail_query(*args, **kwargs):
        raise SQLAlchemyError('database-password-must-not-leak')

    monkeypatch.setattr(dashboard_service, 'get_dashboard_data', fail_query)
    response = client.get('/')
    assert response.status_code == 503
    assert b"couldn't load your study data" in response.data
    assert b'database-password-must-not-leak' not in response.data
    assert 'Dashboard data query failed' in caplog.text

