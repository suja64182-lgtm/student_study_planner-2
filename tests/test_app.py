from app import User, db

def csrf_post(client, url, data):
    return client.post(url, data=data)

def test_register_hash_and_protected_route(client, app):
    response = csrf_post(client, '/register', {'name':'Ada Student','email':'ada@example.com','password':'long-secure-password'})
    assert response.status_code == 302
    with app.app_context():
        user = User.query.filter_by(email='ada@example.com').first()
        assert user and user.password_hash != 'long-secure-password'
    assert client.get('/').status_code == 200

def test_duplicate_registration(client):
    csrf_post(client, '/register', {'name':'Ada Student','email':'ada@example.com','password':'long-secure-password'})
    client.post('/logout')
    response = csrf_post(client, '/register', {'name':'Ada Student','email':'ada@example.com','password':'long-secure-password'})
    assert b'already exists' in response.data

def test_ownership_protects_subject_deletion(client, app):
    from app import Subject
    csrf_post(client, '/register', {'name':'Ada Student','email':'ada@example.com','password':'long-secure-password'})
    with app.app_context():
        subject=Subject(user_id=1,name='Math'); db.session.add(subject); db.session.commit(); sid=subject.id
    client.post('/logout')
    csrf_post(client, '/register', {'name':'Other Student','email':'other@example.com','password':'another-secure-password'})
    response=client.post(f'/subjects/{sid}/delete')
    assert response.status_code == 404

def test_invalid_registration_stays_on_form(client):
    response=csrf_post(client, '/register', {'name':'A','email':'bad','password':'short'})
    assert response.status_code == 200
    assert b'valid name' in response.data

def test_all_planner_pages_render_after_registration(client):
    csrf_post(client, '/register', {'name':'Ada Student','email':'ada@example.com','password':'long-secure-password'})
    for path in ('/', '/subjects', '/timetable', '/tasks', '/exams', '/plans', '/profile'):
        assert client.get(path).status_code == 200, path

def test_session_overlap_is_rejected(client):
    from app import Subject, db
    csrf_post(client, '/register', {'name':'Ada Student','email':'ada@example.com','password':'long-secure-password'})
    with client.application.app_context():
        subject = Subject(user_id=1, name='Physics')
        db.session.add(subject); db.session.commit(); subject_id = subject.id
    def schedule(start, end):
        return client.post('/timetable', data={'subject_id':subject_id, 'topic':'Revision', 'session_date':'2030-05-01', 'start_time':start, 'end_time':end})
    assert schedule('09:00', '10:00').status_code == 302
    response = schedule('09:30', '10:30')
    assert response.status_code == 200
    assert b'overlaps another study session' in response.data
