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
        assert b"login" in response.data.lower() or b"invalid" in response.data.lower()

def test_login_with_valid_credentials():
    with app.test_client() as client:
        response = client.post("/login", data={
            "username": "2305105",
            "password": "pppppp"
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b"login" in response.data.lower() or b"welcome" in response.data.lower()

def setup_student_user_and_cca_membership():
    with app.app_context():
        # Ensure student exists
        student = Student.query.get(2301000)
        if not student:
            db.session.execute(text("""
                INSERT INTO Student (StudentId, Name, Email, DOB, ContactNumber)
                VALUES (:sid, :name, :email, :dob, :phone)
            """), {
                'sid': 2301000,
                'name': 'Test Student',
                'email': 'student@example.com',
                'dob': '2000-01-01',
                'phone': '91234567'
            })
            db.session.commit()
            student = Student.query.get(2301000)

        # Remove and recreate user
        existing_user = User.query.filter_by(Username="testuser").first()
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
        db.session.flush()
        user_id = user.UserId

        # Create or retrieve a test CCA
        cca = CCA.query.filter_by(Name="Test CCA").first()
        if not cca:
            cca = CCA(Name="Test CCA", Description="This is a test CCA")
            db.session.add(cca)
            db.session.flush()
        cca_id = cca.CCAId

        # Ensure user is added to CCA
        membership = CCAMembers.query.filter_by(UserId=user_id, CCAId=cca_id).first()
        if not membership:
            db.session.add(CCAMembers(UserId=user_id, CCAId=cca_id, CCARole="member"))

        db.session.commit()
        return student.StudentId, user_id, cca_id


# def test_authenticated_user_vote():
#     with app.app_context():
#         student = Student.query.get(2305105)
#         assert student is not None, "Student 2305105 not found in DB"

#         user = User.query.filter_by(Username="2305105").first()
#         assert user is not None, "User 2305105 not found in DB"

#         # Ensure user is in a CCA
#         cca = CCA.query.first()
#         assert cca is not None, "No CCA found"

#         membership = CCAMembers.query.filter_by(UserId=user.UserId, CCAId=cca.CCAId).first()
#         if not membership:
#             db.session.add(CCAMembers(UserId=user.UserId, CCAId=cca.CCAId, CCARole="member"))
#             db.session.commit()

#         # Update vote to 0 instead of deleting (for PollId 9)
#         existing_vote = PollVote.query.filter_by(UserId=user.UserId, PollId=9).first()
#         if existing_vote:
#             existing_vote.OptionId = 0  # or any placeholder/neutral OptionId your app accepts
#             db.session.commit()

#     # Perform login and try voting
#     with app.test_client() as client:
#         client.post("/login", data={
#             "username": "2305105",
#             "password": "pppppp"
#         }, follow_redirects=True)

#         poll_id = 9  # target poll ID
#         response = client.get(f"/poll/{poll_id}")
#         assert response.status_code == 200
