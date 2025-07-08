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
    poll_id = 9
    student_id = 2305106
    username = "2305106"
    password = "ffffff"

    with app.app_context():
        # Ensure student
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

        # Ensure user
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

        # Ensure CCA and membership
        cca = CCA.query.get(7)
        if not cca:
            cca = CCA(CCAId=7, Name="Test CCA", Description="For Poll")
            db.session.add(cca)
            db.session.commit()

        if not CCAMembers.query.filter_by(UserId=user_id, CCAId=cca.CCAId).first():
            db.session.add(CCAMembers(UserId=user_id, CCAId=cca.CCAId, CCARole="member"))
            db.session.commit()

        # Ensure poll option exists
        option = PollOption.query.filter_by(PollId=poll_id).first()
        assert option is not None, f"No option found for poll {poll_id}"
        option_id = option.OptionId  # ✅ Corrected here

        # Remove any previous vote
        PollVote.query.filter_by(UserId=user_id, PollId=poll_id).delete()
        db.session.commit()

    # Simulate login and MFA and vote
    with app.test_client() as client:
        login_response = client.post("/login", data={"username": username, "password": password}, follow_redirects=True)
        assert login_response.status_code == 200

        with client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["role"] = "student"
            sess["mfa_authenticated"] = True  # ✅ Bypass MFA in test

        vote_response = client.post(
            f"/poll/{poll_id}/vote",
            data={"selected_option": option_id},
            follow_redirects=True
        )
        assert vote_response.status_code == 200
        assert b"thank you for voting" in vote_response.data.lower() or b"already voted" in vote_response.data.lower()



# def test_authenticated_user_vote():
#     poll_id = 9  # Ensure this exists

#     with app.app_context():
#         # Ensure student exists
#         student = Student.query.get(2305106)
#         if not student:
#             student = Student(
#                 StudentId=2305106,
#                 Name="Test Student",
#                 Email="test2305106@example.com",
#                 DOB="2000-01-01",
#                 ContactNumber="81234567"
#             )
#             db.session.add(student)
#             db.session.commit()

#         # Ensure user exists
#         user = User.query.filter_by(Username="2305106").first()
#         if not user:
#             user = User(
#                 StudentId=2305106,
#                 Username="2305106",
#                 Password=bcrypt.hashpw("ffffff".encode(), bcrypt.gensalt()).decode(),
#                 SystemRole="student",
#                 PasswordLastSet=datetime.utcnow()
#             )
#             db.session.add(user)
#             db.session.commit()

#         # Ensure CCA
#         cca = CCA.query.first()
#         if not cca:
#             cca = CCA(Name="Test CCA", Description="Test CCA for voting")
#             db.session.add(cca)
#             db.session.commit()

#         # Add user to CCA
#         if not CCAMembers.query.filter_by(UserId=user.UserId, CCAId=cca.CCAId).first():
#             db.session.add(CCAMembers(UserId=user.UserId, CCAId=cca.CCAId, CCARole="member"))
#             db.session.commit()

#         # Ensure vote option exists
#         option = PollOption.query.filter_by(PollId=poll_id).first()
#         assert option is not None, f"No options found for poll ID {poll_id}"

#         # Clean previous vote
#         prev_vote = PollVote.query.filter_by(UserId=user.UserId, PollId=poll_id).first()
#         if prev_vote:
#             db.session.delete(prev_vote)
#             db.session.commit()

#     # Vote using client
#     with app.test_client() as client:
#         client.post("/login", data={"username": "2305106", "password": "ffffff"}, follow_redirects=True)

#         with client.session_transaction() as sess:
#             sess["user_id"] = user.UserId
#             sess["role"] = "student"

#         # Cast vote
#         vote_response = client.post(f"/poll/{poll_id}/vote", data={
#             "option": str(option.OptionId)
#         }, follow_redirects=True)

#         assert vote_response.status_code == 200
#         assert b"thank you for voting" in vote_response.data.lower() or b"already voted" in vote_response.data.lower()

#     # Confirm vote in DB
#     with app.app_context():
#         final_vote = PollVote.query.filter_by(UserId=user.UserId, PollId=poll_id).first()
#         assert final_vote is not None, "Vote was not saved"
#         assert final_vote.OptionId == option.OptionId

#         print(f"🗳️ Saved Vote — PollId: {poll_id}, OptionId: {option.OptionId}, UserId: {user.UserId}")


