from selenium import webdriver
from selenium.webdriver.common.by import By
import time

def test_student_login():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')  # Remove this line if you want to see the browser window
    driver = webdriver.Remote(
        command_executor='http://localhost:4444/wd/hub',
        options=options
    )

    try:
        print("▶ Opening login page...")
        driver.get("http://localhost:5000/login")

        print("▶ Entering student credentials...")
        driver.find_element(By.NAME, "username").send_keys("2305105")
        driver.find_element(By.NAME, "password").send_keys("pppppp")

        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        driver.execute_script("arguments[0].scrollIntoView(true);", login_button)
        time.sleep(0.5)
        login_button.click()

        time.sleep(2)

        current_url = driver.current_url
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()

        print("▶ URL after login:", current_url)
        print("▶ Page snippet:", page_text[:300])

        assert "dashboard" in current_url or "welcome" in page_text

    finally:
        driver.quit()
