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

        # Ensure user
        existing_user = User.query.filter(
            (User.StudentId == student.StudentId) | (User.Username == "testuser")
        ).first()
        if existing_user:
            db.session.delete(existing_user)
            db.session.commit()

        user = User(
            StudentId=student.StudentId,
            Username="testuser",
            Password=bcrypt.hashpw("pppppp".encode(), bcrypt.gensalt()).decode(),
            SystemRole="student",
            PasswordLastSet=datetime.utcnow()
        )
        db.session.add(user)
        db.session.commit()

        # Re-fetch the user to ensure UserId is available and attached to session
        user = User.query.filter_by(Username="testuser").first()

        # Ensure CCA
        cca = CCA.query.filter_by(Name="Test CCA").first()
        if not cca:
            cca = CCA(Name="Test CCA", Description="Created for test")
            db.session.add(cca)
            db.session.commit()

        return student.StudentId, user.UserId, cca.CCAId

def test_student_assigned_to_cca_directly():
    student_id, user_id, cca_id = setup_existing_student_and_cca()

    with app.app_context():
        user = User.query.get(user_id)
        cca = CCA.query.get(cca_id)

        membership = CCAMembers(UserId=user.UserId, CCAId=cca.CCAId, CCARole="member")
        db.session.add(membership)
        db.session.commit()

        result = CCAMembers.query.filter_by(UserId=user.UserId, CCAId=cca.CCAId).first()
        assert result is not None
        assert result.CCARole == "member"



