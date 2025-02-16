import click as click_cli
import sys
import smtplib
from email.mime.text import MIMEText
from helium import S, start_chrome, wait_until, write, click as helium_click, Link, kill_browser, get_driver
from selenium.webdriver.common.by import By
import time
from dotenv import load_dotenv
import os
from litellm import completion


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

def invoke_llm(assignments_content):
    # Clean and format the assignments content
    cleaned_content = "\n".join([
        line.strip() for line in assignments_content.splitlines() 
        if line.strip() and not line.startswith("Timestamp:")
    ])
    
    # Prepare the prompt
    prompt = f"""
    Analyze this student's assignments and grades. Focus on:
    1. Missing assignments (marked with 'M - Missing')
    2. Class grades below 80%
    
    Here is the data:
    {cleaned_content[:10000]}
    
    Provide:
    - Summary of key issues
        -- Aggregation of missing assignments
        -- Aggregation of class assignment grades that are less than 80%
    - Table of missing assignments with formatted spacing to look like a table
        -- Course Name
        -- Assignment
        -- Due Date
        -- Sort by Due Date from oldest to newest
    - Table of low class grades with formatted spacing to look like a table
        -- Course Name
        -- Current Grade
        -- Sort by Current Grade from lowest to highest
    
    Keep the response concise and focused.
    """

    try:
        # Send to Claude with timeout via LiteLLM
        response = completion(
            model="anthropic/claude-3-5-sonnet-20240620",
            messages=[{"role": "user", "content": prompt}],
            timeout=30,
            max_tokens=1500,
            temperature=0
        )
        
        # Extract and return the content
        return response.get('choices', [{}])[0].get('message', {}).get('content')
    
    except Exception as e:
        return f"Error processing assignments: {str(e)}"

def send_email(analysis):
    """Sends the analysis via email."""
    sender_email = os.getenv('GMAIL_SENDER')
    sender_password = os.getenv('GMAIL_APP_PASSWORD')
    receiver_email = os.getenv('GMAIL_RECEIVERS')
    subject = "Grade Analysis Report"
    
    msg = MIMEText(analysis)  # Create the email message object
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = receiver_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server: # For Gmail SSL
            server.login(sender_email, sender_password)
            server.send_message(msg)
            print("Email sent successfully!")
    except Exception as e:
        print(f"Error sending email: {e}")

@click_cli.command()
@click_cli.option('--local', is_flag=True, help='Use local assignments.txt instead of scraping website')
@click_cli.option('--email', is_flag=True, help='Send analysis via email')
def cli(local, email):
    """Grade Checker Application"""
    try:
        print("Starting grade check...")
        
        if not local:
            print("Scraping website for assignments...")
            credentials = get_credentials()
            login_to_website(**credentials)
            print("Website scraping complete.")
        else:
            print("Using local assignments file...")
        
        # Read the saved assignments
        print("Reading assignments file...")
        with open('assignments.txt', 'r') as f:
            assignments_content = f.read()
        
        print("Sending assignments to LLM for analysis...")
        try:
            analysis = invoke_llm(assignments_content)
            print("\nAnalysis complete!")
            print(analysis)
            
            if email:
                print("\nSending analysis via email...")
                send_email(analysis)
            
            sys.exit(0)  # Exit successfully
        except Exception as e:
            print(f"\nError during LLM analysis: {str(e)}")
            sys.exit(1)  # Exit with error
        
    except Exception as e:
        print(f"\nError: {str(e)}")
        sys.exit(1)  # Exit with error

if __name__ == "__main__":
    cli()
