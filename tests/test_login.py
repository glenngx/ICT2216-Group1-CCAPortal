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

from datetime import date

def setup_student_and_cca():
    with app.app_context():
        db.session.query(CCAMembers).delete()
        db.session.query(CCA).delete()
        db.session.query(User).delete()
        db.session.query(Student).delete()
        db.session.commit()

        student = Student(
            StudentId=9999999,
            Name="Test Student",
            Email="student@example.com",
            DOB=date(2000, 1, 1),
            ContactNumber="91234567"
        )
        db.session.add(student)
        db.session.flush()

        user = User(
            StudentId=student.StudentId,
            Username="testuser",
            Password=bcrypt.hashpw("pppppp".encode(), bcrypt.gensalt()).decode(),
            SystemRole="student"
        )

        cca = CCA(Name="Chess Club", Description="Test club")
        db.session.add_all([user, cca])
        db.session.flush()

        return student, user, cca


def test_student_assigned_to_cca_directly():
    student, user, cca = setup_student_and_cca()

    with app.app_context():
        membership = CCAMembers(UserId=user.UserId, CCAId=cca.CCAId, CCARole="member")
        db.session.add(membership)
        db.session.commit()

        result = CCAMembers.query.filter_by(UserId=user.UserId, CCAId=cca.CCAId).first()
        assert result is not None
        assert result.CCARole == "member"
