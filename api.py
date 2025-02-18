from flask import Flask, jsonify
import smtplib
import time
from email.mime.text import MIMEText
from helium import S, start_chrome, wait_until, write, click as helium_click, Link, kill_browser, get_driver
from selenium.webdriver.common.by import By
from dotenv import load_dotenv
import os
import logfire


# Load environment variables from .env file
load_dotenv()

# Add logfire logging
logfire.configure()


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
    start_chrome(url, headless=True)
    
    try:
        # Wait for page to load
        wait_until(S("body").exists)
        
        # Login
        write(username, into="User Name")
        write(password, into="Password")
        helium_click("Sign In")
        
        # Wait for login to complete
        wait_until(Link("Classes").exists)
        helium_click("Classes")
        
        # Wait for iframe to load
        wait_until(S("#sg-legacy-iframe").exists)
        
        # Switch to iframe
        iframe = get_driver().find_element("id", "sg-legacy-iframe")
        get_driver().switch_to.frame(iframe)
        
        # Extract and save assignments
        assignments = extract_assignments()
        save_assignments_to_file(assignments)
        
    finally:
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


def send_email(analysis):
    """Sends the analysis via email with HTML content to multiple recipients."""
    sender_email = os.getenv('GMAIL_SENDER')
    sender_password = os.getenv('GMAIL_APP_PASSWORD')
    receiver_emails = [email.strip() for email in os.getenv('GMAIL_RECEIVERS').split(',')]
    
    # Create subject with current date
    current_date = time.strftime("%m/%d/%Y")
    subject = f"Naina's Grades/Assignments - {current_date}"
    
    # Create message as MIMEText with HTML content
    msg = MIMEText(analysis, 'html')
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = ', '.join(receiver_emails)  # Join all recipients with commas

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            # Send to all recipients
            server.sendmail(
                sender_email,
                receiver_emails,  # Pass list of recipients
                msg.as_string()
            )
            print(f"Email sent successfully to {len(receiver_emails)} recipients!")
    except Exception as e:
        print(f"Error sending email: {e}")

app = Flask(__name__)

@app.route('/check-grades', methods=['GET'])
def check_grades():
    try:
        print("Starting grade check...")
        
        print("Scraping website for assignments...")
        credentials = get_credentials()
        login_to_website(**credentials)
        print("Website scraping complete.")
        
        # Read the saved assignments
        print("Reading assignments file...")
        with open('assignments.txt', 'r') as f:
            assignments_content = f.read()
        
        return jsonify({
            "status": "success",
            "assignments": assignments_content
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": f"Error: {str(e)}"
        }), 500
