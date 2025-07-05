from application import app

def test_login_page_loads():
    with app.test_client() as client:
        response = client.get('/login')
        assert response.status_code == 200
        assert b"Login" in response.data or b"Student ID" in response.data
