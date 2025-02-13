from helium import S, start_chrome, wait_until, write, click, Link, kill_browser, get_driver
from selenium.webdriver.common.by import By
import time
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()


def save_assignments_to_file(content):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open('assignments.txt', 'w', encoding='utf-8') as f:
        f.write(f"Timestamp: {timestamp}\n\n")
        for line in content:
            f.write(line + "\n")

def extract_assignments():
    # Get all content from the iframe
    elements = get_driver().find_elements(By.CLASS_NAME, "AssignmentClass")
    return [element.text for element in elements]

def get_credentials():
    return {
        "url": os.getenv('HAC_URL'),
        "username": os.getenv('HAC_USERNAME'),
        "password": os.getenv('HAC_PASSWORD')
    }


def login_to_website(url, username, password):
    # Start browser and go to URL
    start_chrome(url, headless=False)
    
    # Wait for page to load
    wait_until(S("body").exists)
    
    # Login
    write(username, into="User Name")
    write(password, into="Password")
    click("Sign In")
    
    # Wait for login to complete
    wait_until(Link("Classes").exists)
    click("Classes")
    
    # Wait for iframe to load
    wait_until(S("#sg-legacy-iframe").exists)
    
    # Switch to iframe
    iframe = get_driver().find_element("id", "sg-legacy-iframe")
    get_driver().switch_to.frame(iframe)
    
    # Extract and save assignments
    assignments = extract_assignments()
    save_assignments_to_file(assignments)
    
    # Switch back to default content
    get_driver().switch_to.default_content()
    kill_browser()


def main():
    print("Website Login CLI")
    credentials = get_credentials()
    
    try:
        login_to_website(**credentials)
        print("Login successful!")
    except Exception as e:
        print(f"Login failed: {str(e)}")

if __name__ == "__main__":
    main()
