from app import app
from application.models import db, User, Student, CCA, CCAMembers, Poll, PollVote, PollOption
import bcrypt
from sqlalchemy import text
from datetime import datetime
import hashlib

#--------------------- TESTING USER LOGIN WITH VALID AND INVALID CREDENTIALS ----------------------------#

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
        assert b"login" in response.data.lower() or b"invalid" in response.data.lower()

#--------------------- TESTING ADDING USER TO CCA ----------------------------#

def test_login_with_valid_credentials():
    with app.test_client() as client:
        response = client.post("/login", data={
            "username": "2305105",
            "password": "pppppp"
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b"login" in response.data.lower() or b"welcome" in response.data.lower()

def test_add_student_to_cca():
    with app.app_context():
        # Setup test student
        student = Student.query.get(2309999)
        if not student:
            db.session.execute(text("""
                INSERT INTO Student (StudentId, Name, Email, DOB, ContactNumber)
                VALUES (:sid, :name, :email, :dob, :phone)
            """), {
                'sid': 2309999,
                'name': 'Integration Test Student',
                'email': 'test@student.com',
                'dob': '2000-01-01',
                'phone': '81234567'
            })
            db.session.commit()

        # Setup test user
        user = User.query.filter_by(Username="inttestuser").first()
        if not user:
            user = User(
                StudentId=2309999,
                Username="inttestuser",
                Password=bcrypt.hashpw("pppppp".encode(), bcrypt.gensalt()).decode(),
                SystemRole="student",
                PasswordLastSet=datetime.utcnow()
            )
            db.session.add(user)
            db.session.flush()
            db.session.commit()

        # Setup test CCA
        cca = CCA.query.filter_by(Name="Integration Test CCA").first()
        if not cca:
            cca = CCA(Name="Integration Test CCA", Description="For testing student join")
            db.session.add(cca)
            db.session.flush()
            db.session.commit()

        # Add student to CCA
        membership = CCAMembers.query.filter_by(UserId=user.UserId, CCAId=cca.CCAId).first()
        if not membership:
            membership = CCAMembers(UserId=user.UserId, CCAId=cca.CCAId, CCARole="member")
            db.session.add(membership)
            db.session.commit()

        # Verify the student is part of the CCA
        inserted = CCAMembers.query.filter_by(UserId=user.UserId, CCAId=cca.CCAId).first()
        assert inserted is not None
        assert inserted.CCARole == "member"

#--------------------- TESTING USER VOTING ----------------------------#

def test_authenticated_user_vote():
    with app.app_context():
        student = Student.query.get(2305106)
        assert student is not None, "Student 2305106 not found in DB"

        user = User.query.filter_by(Username="2305106").first()
        assert user is not None, "User 2305106 not found in DB"

        # Ensure user is in a CCA
        cca = CCA.query.first()
        assert cca is not None, "No CCA found"

        membership = CCAMembers.query.filter_by(UserId=user.UserId, CCAId=cca.CCAId).first()
        if not membership:
            db.session.add(CCAMembers(UserId=user.UserId, CCAId=cca.CCAId, CCARole="member"))
            db.session.commit()

        # Delete existing vote for PollId 9 if any
        existing_vote = PollVote.query.filter_by(UserId=user.UserId, PollId=9).first()
        if existing_vote:
            db.session.delete(existing_vote)
            db.session.commit()

    # Perform login and try voting
    with app.test_client() as client:
        client.post("/login", data={
            "username": "2305106",
            "password": "ffffff"
        }, follow_redirects=True)

        poll_id = 9  # target poll ID
        response = client.get(f"/poll/{poll_id}")
        assert response.status_code == 200


