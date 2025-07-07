# tests/test_selenium.py
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

def setup_browser():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def test_login_valid_credentials():
    driver = setup_browser()
    try:
        driver.get("http://localhost:5000/login")
        driver.find_element(By.NAME, "username").send_keys("2305105")
        driver.find_element(By.NAME, "password").send_keys("pppppp")
        driver.find_element(By.XPATH, "//button[contains(text(),'Login')]").click()
        time.sleep(1)
        assert "dashboard" in driver.current_url or "welcome" in driver.page_source.lower()
    finally:
        driver.quit()
