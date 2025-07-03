from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

options = Options()
options.add_argument('--headless')
driver = webdriver.Chrome(options=options)

driver.get("https://ccap-app.domloh.com/login")

# 🛠 Corrected selectors — from name="email" to name="username"
driver.find_element(By.NAME, "username").send_keys("test@example.com")
driver.find_element(By.NAME, "password").send_keys("badpassword")
driver.find_element(By.ID, "loginBtn").click()

# Let the page load (better: use WebDriverWait later)
time.sleep(2)

# ✅ Adjust based on your flash message content
assert "Invalid" in driver.page_source or "Please log in" in driver.page_source

driver.quit()
