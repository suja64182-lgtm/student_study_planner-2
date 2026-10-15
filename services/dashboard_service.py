"""Dashboard data queries and date-only study planning calculations."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import Integer, cast, case, func, select
from sqlalchemy.orm import joinedload

def _duration_hours_expression(database, session_model):
    """Return a SQL duration expression for the supported MySQL/SQLite schemas."""
    dialect = database.session.get_bind().dialect.name
    if dialect == 'mysql':
        seconds = func.time_to_sec(session_model.end_time) - func.time_to_sec(session_model.start_time)
    elif dialect == 'sqlite':
        seconds = cast(func.strftime('%s', session_model.end_time), Integer) - cast(
            func.strftime('%s', session_model.start_time), Integer
        )
    else:
        raise RuntimeError(f'Unsupported dashboard database dialect: {dialect}')
    return seconds / 3600.0


def _duration_minutes(start_time, end_time):
    """Duration for the existing same-day DATE + TIME session model."""
    start = datetime.combine(date.min, start_time)
    end = datetime.combine(date.min, end_time)
    return max(0, int((end - start).total_seconds() // 60))


def _task_due_state(due_date, today):
    if due_date is None:
        return 'No due date'
    if due_date < today:
        return 'Overdue'
    if due_date == today:
        return 'Due today'
    return 'Upcoming'


def get_dashboard_data(
    user_id,
    today=None,
    *,
    database,
    session_model,
    task_model,
    exam_model,
):
    """Load dashboard data for one student using aggregated duration queries."""
    StudySession, Task, Exam = session_model, task_model, exam_model
    today = today or date.today()
    week_start = today - timedelta(days=today.weekday())
    next_week_start = week_start + timedelta(days=7)
    day_dates = [week_start + timedelta(days=offset) for offset in range(7)]

    sessions = database.session.scalars(
        select(StudySession)
        .options(joinedload(StudySession.subject))
        .where(StudySession.user_id == user_id, StudySession.session_date == today)
        .order_by(StudySession.start_time, StudySession.id)
    ).all()
    for session in sessions:
        session.duration_minutes = _duration_minutes(session.start_time, session.end_time)

    tasks = database.session.scalars(
        select(Task)
        .options(joinedload(Task.subject))
        .where(Task.user_id == user_id, Task.status != 'completed')
        .order_by(case((Task.due_date.is_(None), 1), else_=0), Task.due_date, Task.id)
        .limit(8)
    ).all()
    for task in tasks:
        task.due_state = _task_due_state(task.due_date, today)

    exams = database.session.scalars(
        select(Exam)
        .options(joinedload(Exam.subject))
        .where(Exam.user_id == user_id, Exam.exam_date >= today)
        .order_by(Exam.exam_date, Exam.id)
        .limit(6)
    ).all()
    for exam in exams:
        # DATE exams are treated as upcoming for the entirety of their calendar day.
        exam.days_remaining = (exam.exam_date - today).days

    duration_hours = _duration_hours_expression(database, StudySession)
    valid_completed = (
        StudySession.user_id == user_id,
        StudySession.status == 'completed',
        StudySession.end_time > StudySession.start_time,
    )
    totals = database.session.execute(
        select(
            func.coalesce(
                func.sum(case((StudySession.session_date == today, duration_hours), else_=0.0)), 0.0
            ),
            func.coalesce(func.sum(duration_hours), 0.0),
        ).where(*valid_completed)
    ).one()

    daily_rows = database.session.execute(
        select(StudySession.session_date, func.sum(duration_hours))
        .where(
            *valid_completed,
            StudySession.session_date >= week_start,
            StudySession.session_date < next_week_start,
        )
        .group_by(StudySession.session_date)
    ).all()
    hours_by_day = {row[0]: float(row[1] or 0) for row in daily_rows}
    weekly = [
        {'date': day, 'label': day.strftime('%a'), 'hours': round(hours_by_day.get(day, 0), 2)}
        for day in day_dates
    ]

    return {
        'today': today,
        'week_start': week_start,
        'sessions': sessions,
        'tasks': tasks,
        'exams': exams,
        'completed_hours_today': round(float(totals[0] or 0), 2),
        'completed_hours_total': round(float(totals[1] or 0), 2),
        'weekly': weekly,
    }
