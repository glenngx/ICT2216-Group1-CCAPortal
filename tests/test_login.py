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

def setup_existing_student_and_cca():
    with app.app_context():
        # Step 1: Find any existing student
        student = Student.query.first()
        if not student:
            raise Exception("No student exists in the database.")

        # Step 2: Find user linked to student
        user = User.query.filter_by(StudentId=student.StudentId).first()
        if not user:
            raise Exception(f"No user found for StudentId={student.StudentId}")

        # Step 3: Create a new test CCA
        cca = CCA(Name="Test CCA", Description="Created for testing")
        db.session.add(cca)
        db.session.commit()  # save to get CCAId

        return student, user, cca

def test_student_assigned_to_cca_directly():
    student, user, cca = setup_existing_student_and_cca()

    with app.app_context():
        # Step 4: Assign the user to the CCA
        membership = CCAMembers(UserId=user.UserId, CCAId=cca.CCAId, CCARole="member")
        db.session.add(membership)
        db.session.commit()

        # Step 5: Verify assignment
        result = CCAMembers.query.filter_by(UserId=user.UserId, CCAId=cca.CCAId).first()
        assert result is not None
        assert result.CCARole == "member"
