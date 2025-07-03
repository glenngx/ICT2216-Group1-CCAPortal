from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

options = Options()
options.add_argument('--headless')
driver = webdriver.Chrome(options=options)

driver.get("https://ccap-app.domloh.com/login")

# adjust selectors as needed
driver.find_element("name", "email").send_keys("test@example.com")
driver.find_element("name", "password").send_keys("badpassword")
driver.find_element("name", "submit").click()

time.sleep(1)
assert "Invalid" in driver.page_source

driver.quit()
