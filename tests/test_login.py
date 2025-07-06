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



def test_authenticated_user_vote():
    with app.app_context():
        student = Student.query.get(2305105)
        assert student is not None, "❌ Student 2305105 not found in DB"

        user = User.query.filter_by(Username="2305105").first()
        assert user is not None, "❌ User 2305105 not found in DB"

        # Ensure user is in CCA
        cca = CCA.query.first()
        assert cca is not None, "❌ No CCA found"

        membership = CCAMembers.query.filter_by(UserId=user.UserId, CCAId=cca.CCAId).first()
        if not membership:
            db.session.add(CCAMembers(UserId=user.UserId, CCAId=cca.CCAId, CCARole="member"))
            db.session.commit()

    # Perform login and access poll
    with app.test_client() as client:
        client.post("/login", data={
            "username": "2305105",
            "password": "pppppp"
        }, follow_redirects=True)

        poll_id = Poll.query.filter_by(CCAId=cca.CCAId).first().PollId
        response = client.get(f"/poll/{poll_id}")
        assert response.status_code == 200

