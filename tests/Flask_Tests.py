from app import app
from application.models import db, User, Student, CCA, CCAMembers, Poll, PollVote, PollOption
import bcrypt
from sqlalchemy import text
from datetime import datetime
import hashlib
import os

#--------------------- TESTING USER LOGIN WITH VALID AND INVALID CREDENTIALS ----------------------------#

def test_login_page_loads():
    with app.test_client() as client:
        response = client.get("/login", follow_redirects=False)
        assert response.status_code in (200, 302)
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
            "username": "2305106",
            "password": "ffffff",
        }, follow_redirects=True)

        # Inject session variable to break redirect loop
        with client.session_transaction() as sess:
            sess["mfa_authenticated"] = True

        # Now follow the redirect to dashboard
        response = client.get("/dashboard")
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
    poll_id = 9
    student_id = 2305106
    username = "2305106"
    password = "ffffff"

    with app.app_context():
        # Ensure student exists
        student = Student.query.get(student_id)
        if not student:
            student = Student(
                StudentId=student_id,
                Name="Test Voter",
                Email="voter@example.com",
                DOB="2000-01-01",
                ContactNumber="81234567"
            )
            db.session.add(student)
            db.session.commit()

        # Ensure user exists
        user = User.query.filter_by(Username=username).first()
        if not user:
            user = User(
                StudentId=student_id,
                Username=username,
                Password=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
                SystemRole="student",
                PasswordLastSet=datetime.utcnow()
            )
            db.session.add(user)
            db.session.commit()
        user_id = user.UserId

        # Ensure CCA exists
        cca = CCA.query.get(7)
        if not cca:
            cca = CCA(CCAId=7, Name="Test CCA", Description="For Poll")
            db.session.add(cca)
            db.session.commit()

        # Ensure user is a member of the CCA
        if not CCAMembers.query.filter_by(UserId=user_id, CCAId=cca.CCAId).first():
            db.session.add(CCAMembers(UserId=user_id, CCAId=cca.CCAId, CCARole="member"))
            db.session.commit()

        # Ensure poll option exists
        option = PollOption.query.filter_by(PollId=poll_id).first()
        assert option is not None, f"No option found for poll {poll_id}"
        option_id = option.OptionId

        # Delete any existing vote
        PollVote.query.filter_by(UserId=user_id, PollId=poll_id).delete()
        db.session.commit()

    # Simulate login and vote
    with app.test_client() as client:
        login_response = client.post("/login", data={"username": username, "password": password}, follow_redirects=True)
        
        # Check for login failure clues
        if not os.getenv("TESTING") == "1":
            assert b"captcha" not in login_response.data.lower(), "Login blocked by CAPTCHA"
        assert b"invalid" not in login_response.data.lower(), "Login failed due to invalid credentials"

        # Force session variables
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["role"] = "student"
            sess["mfa_authenticated"] = True

        print("Inserting vote for:", user_id, poll_id, option_id)

        # Vote submission
        vote_response = client.post(f"/poll/{poll_id}/vote", data={"option": str(option_id)}, follow_redirects=True)
        print("▶ VOTE RESPONSE:", vote_response.data.decode()[:1000])  # debug

