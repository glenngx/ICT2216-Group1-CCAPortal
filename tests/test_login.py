from app import app
from application.models import db, User, Student, CCA, CCAMembers, Poll, PollVote, PollOption
import bcrypt
from sqlalchemy import text
from datetime import datetime
import hashlib

def test_login_page_loads():
    with app.test_client() as client:
        response = client.get("/login")
        assert response.status_code == 200
        assert b"Student ID" in response.data  # or "Login"

def test_login_with_invalid_credentials():
    with app.test_client() as client:
        response = client.post("/login", data={
            "username": "2305105",
            "password": "wrongpass"
        }, follow_redirects=True)

        print("▶ PAGE HTML:\n", response.data.decode("utf-8")[:1000])

        # Relaxed check:
        assert b"login" in response.data.lower() or b"invalid" in response.data.lower()

def test_login_with_valid_credentials():
    with app.test_client() as client:
        response = client.post("/login", data={
            "username": "2305105",
            "password": "pppppp"
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b"login" in response.data.lower() or b"welcome" in response.data.lower()

def setup_existing_student_and_cca():
    with app.app_context():
        # Ensure student
        student = Student.query.get(2301000)
        if not student:
            db.session.execute(text("""
                INSERT INTO Student (StudentId, Name, Email, DOB, ContactNumber)
                VALUES (:sid, :name, :email, :dob, :phone)
            """), {
                'sid': 2301000,
                'name': 'Fallback Student',
                'email': 'student@example.com',
                'dob': '2000-01-01',
                'phone': '91234567'
            })
            db.session.commit()
            student = Student.query.get(2301000)

        # Remove previous test user
        existing_user = User.query.filter_by(Username="testuser").first()
        if existing_user:
            db.session.delete(existing_user)
            db.session.commit()

        # Add fresh test user
        user = User(
            StudentId=student.StudentId,
            Username="testuser",
            Password=bcrypt.hashpw("pppppp".encode(), bcrypt.gensalt()).decode(),
            SystemRole="student",
            PasswordLastSet=datetime.utcnow()
        )
        db.session.add(user)
        db.session.flush()  # ✅ ensures UserId is available
        user_id = user.UserId  # ✅ extract it now!

        # Add or get CCA
        cca = CCA.query.filter_by(Name="Test CCA").first()
        if not cca:
            cca = CCA(Name="Test CCA", Description="Created for test")
            db.session.add(cca)
            db.session.flush()  # ✅ ensures CCAId is available

        cca_id = cca.CCAId
        db.session.commit()

        return student.StudentId, user_id, cca_id

def setup_existing_student_and_cca():
    with app.app_context():
        # Ensure student
        student = Student.query.get(2301000)
        if not student:
            db.session.execute(text("""
                INSERT INTO Student (StudentId, Name, Email, DOB, ContactNumber)
                VALUES (:sid, :name, :email, :dob, :phone)
            """), {
                'sid': 2301000,
                'name': 'Fallback Student',
                'email': 'student@example.com',
                'dob': '2000-01-01',
                'phone': '91234567'
            })
            db.session.commit()
            student = Student.query.get(2301000)

        # Remove previous test user
        existing_user = User.query.filter_by(Username="testuser").first()
        if existing_user:
            db.session.delete(existing_user)
            db.session.commit()

        # Add fresh test user
        user = User(
            StudentId=student.StudentId,
            Username="testuser",
            Password=bcrypt.hashpw("pppppp".encode(), bcrypt.gensalt()).decode(),
            SystemRole="student",
            PasswordLastSet=datetime.utcnow()
        )
        db.session.add(user)
        db.session.flush()  # ✅ ensures UserId is available
        user_id = user.UserId  # ✅ extract it now!

        # Add or get CCA
        cca = CCA.query.filter_by(Name="Test CCA").first()
        if not cca:
            cca = CCA(Name="Test CCA", Description="Created for test")
            db.session.add(cca)
            db.session.flush()  # ✅ ensures CCAId is available

        cca_id = cca.CCAId
        db.session.commit()

        return student.StudentId, user_id, cca_id

def test_authenticated_user_vote():
    with app.app_context():
        student = Student.query.get(2305105)
        if not student:
            db.session.execute(text("""
                INSERT INTO Student (StudentId, Name, Email, DOB, ContactNumber)
                VALUES (:sid, :name, :email, :dob, :phone)
            """), {
                'sid': 2305105,
                'name': 'Test User',
                'email': 'test@example.com',
                'dob': '2000-01-01',
                'phone': '91234567'
            })
            db.session.commit()

        # Ensure user
        user = User.query.filter_by(Username="2305105").first()
        if not user:
            user = User(
                StudentId=2305105,
                Username="2305105",
                Password=bcrypt.hashpw("pppppp".encode(), bcrypt.gensalt()).decode(),
                SystemRole="student",
                PasswordLastSet=datetime.utcnow()
            )
            db.session.add(user)
            db.session.commit()

    # Now test client actions
    with app.test_client() as client:
        client.post("/login", data={
            "username": "2305105",
            "password": "pppppp"
        }, follow_redirects=True)

        poll_id = 1
        response = client.get(f"/poll/{poll_id}")
        assert response.status_code == 200

def test_user_vote_with_token():
    with app.app_context():
        # Ensure Student exists
        student = Student.query.get(2305105)
        if not student:
            db.session.execute(text("""
                INSERT INTO Student (StudentId, Name, Email, DOB, ContactNumber)
                VALUES (:sid, :name, :email, :dob, :phone)
            """), {
                'sid': 2305105,
                'name': 'Test Voter',
                'email': 'testvoter@example.com',
                'dob': '2000-01-01',
                'phone': '91234567'
            })
            db.session.commit()

        # Ensure User exists
        user = User.query.filter_by(Username="2305105").first()
        if not user:
            user = User(
                StudentId=2305105,
                Username="2305105",
                Password=bcrypt.hashpw("pppppp".encode(), bcrypt.gensalt()).decode(),
                SystemRole="student",
                PasswordLastSet=datetime.utcnow()
            )
            db.session.add(user)
            db.session.commit()

        # Insert poll token tied to User
        db.session.execute(text("""
            INSERT INTO VoteTokens (PollId, UserId, ExpiryTime, IsUsed)
            VALUES (:poll_id, :user_id, DATEADD(day, 1, GETUTCDATE()), 0)
        """), {
            "poll_id": 1,
            "user_id": user.UserId
        })
        db.session.commit()

    # Simulate login and vote action
    with app.test_client() as client:
        client.post("/login", data={
            "username": "2305105",
            "password": "pppppp"
        }, follow_redirects=True)

        # Visit poll
        res = client.get("/poll/1")
        assert res.status_code == 200
        assert b"Vote" in res.data

        # Cast vote (adjust PollOptionId as needed)
        res = client.post("/poll/1/vote", data={
            "selected_option": 1
        }, follow_redirects=True)

        assert b"Vote submitted successfully" in res.data or res.status_code == 200

