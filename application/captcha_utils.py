import os, requests

VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"

def captcha_is_valid(token: str, remote_ip: str | None = None) -> bool:
    """
    Return True if Google says the token is good.
    """
    secret = os.getenv("RECAPTCHA_SECRET")
    if not (secret and token):
        return False                       # missing data → fail closed

    data = {"secret": secret, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip

    try:
        r = requests.post(VERIFY_URL, data=data, timeout=5)
        result = r.json()
        return result.get("success", False)
    except requests.RequestException:
        return False                       # network error → treat as failure
