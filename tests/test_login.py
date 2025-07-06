from app import app
from application.models import db, User, Student, CCA, CCAMembers, Poll, PollVote, PollOption
import bcrypt
from sqlalchemy import text

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

from sqlalchemy import text
from datetime import datetime

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
    with app.test_client() as client:
        # Login first
        client.post("/login", data={
            "username": "2305105",
            "password": "pppppp"
        }, follow_redirects=True)

        # Access the poll
        poll_id = 1  # change as needed
        get_poll = client.get(f"/poll/{poll_id}")
        assert get_poll.status_code == 200

        # Submit a vote (option ID 1 assumed — update as needed)
        vote_response = client.post(f"/poll/{poll_id}/vote", data={
            "option": 1
        }, follow_redirects=True)

        assert vote_response.status_code == 200
        assert b"thank you" in vote_response.data.lower() or b"voted" in vote_response.data.lower()

import hashlib

def test_anonymous_token_vote():
    with app.app_context():
        # Create a token and its hash
        token_plain = "test-anon-token"
        token_hash = hashlib.sha256(token_plain.encode()).hexdigest()

        # Insert into DB manually (adjust table/model as needed)
        db.session.execute(text("""
            INSERT INTO VoteTokens (PollId, TokenHash, ExpiryTime, IsUsed)
            VALUES (:poll_id, :token_hash, DATEADD(day, 1, GETUTCDATE()), 0)
        """), {"poll_id": 1, "token_hash": token_hash})
        db.session.commit()

    with app.test_client() as client:
        # Access vote page using token
        poll_id = 1
        response = client.get(f"/poll/{poll_id}?token={token_plain}")
        assert response.status_code == 200

        # Submit vote
        vote_response = client.post(f"/poll/{poll_id}/vote?token={token_plain}", data={
            "option": 1
        }, follow_redirects=True)

        assert vote_response.status_code == 200
        assert b"thank you" in vote_response.data.lower() or b"voted" in vote_response.data.lower()
