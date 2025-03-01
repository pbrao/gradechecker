import click as click_cli
import sys
import smtplib
import time
import schedule
import time as schedule_time  # Rename to avoid conflict with existing time import
from email.mime.text import MIMEText
from helium import S, start_chrome, wait_until, write, click as helium_click, Link, kill_browser, get_driver
from selenium.webdriver.common.by import By
import time
from dotenv import load_dotenv
import os
from pydantic_ai import Agent
import logfire


# Load environment variables from .env file
load_dotenv()

# Add logfire logging
logfire.configure()


def save_assignments_to_file(content):
    with logfire.span("save_assignments_to_file"):
        logfire.info("Saving assignments to file")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open('assignments.txt', 'w', encoding='utf-8') as f:
            f.write(f"Timestamp: {timestamp}\n\n")
            for line in content:
                f.write(line + "\n")
        logfire.info("Assignments saved to file")

def extract_assignments():
    with logfire.span("extract_assignments"):
        logfire.info("Extracting assignments from website")
        # Get all content from the iframe
        elements = get_driver().find_elements(By.CLASS_NAME, "AssignmentClass")
        assignments = [element.text for element in elements]
        logfire.info(f"Extracted {len(assignments)} assignments")
        return assignments

def get_credentials():
    with logfire.span("get_credentials"):
        logfire.info("Getting credentials from environment variables")
        credentials = {
            "url": os.getenv('HAC_URL'),
            "username": os.getenv('HAC_USERNAME'),
            "password": os.getenv('HAC_PASSWORD')
        }
        logfire.info("Credentials retrieved")
        return credentials


def login_to_website(url, username, password):
    with logfire.span("login_to_website"):
        logfire.info(f"Logging in to website: {url}")
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
        logfire.info("Login and assignment extraction successful")
        
    except Exception as e:
        logfire.error(f"Login or assignment extraction failed: {str(e)}")
        raise
    finally:
        # Switch back to default content
        get_driver().switch_to.default_content()
        kill_browser()


def main():
    with logfire.span("main"):
        logfire.info("Starting Website Login CLI")
    credentials = get_credentials()
    
    try:
        login_to_website(**credentials)
        print("Login successful!")
        logfire.info("Login successful")
    except Exception as e:
        print(f"Login failed: {str(e)}")
        logfire.error(f"Login failed: {str(e)}")

def invoke_llm(assignments_content):
    with logfire.span("invoke_llm"):
        logfire.info("Invoking LLM for analysis")
        # Clean and format the assignments content
    cleaned_content = "\n".join([
        line.strip() for line in assignments_content.splitlines() 
        if line.strip() and not line.startswith("Timestamp:")
    ])
    
    # Prepare the prompt
    prompt = f"""
    Analyze this student's assignments and grades. Focus on:
    1. Missing assignments (marked with 'M - Missing' or a '0.00')
    2. Class grades below 80%
    3. Class grades above 80%
    
    Here is the data:
    {cleaned_content[:10000]}
    
    Provide the following sections:
    - Summary of Key Issues
        -- Number of missing assignments plus those with a 0.00 grade
        -- Number of class assignment grades that are less than 80%
    - Missing Assignments
        -- Table of all of the missing assignments with formatted spacing to look like a table
        -- Course Name
        -- Assignment
        -- Due Date
        -- Sort by Due Date from the newest date to the oldest date
    - Low Class Grades (Below 80%) 
        -- Table of overall course grades below 80% with formatted spacing to look like a table
        -- Course Name
        -- Current Grade
        -- Sort by Current Grade from lowest to highest
    - Other Class Grades (Above 80%) 
        -- Table of overall course grade above 80% with formatted spacing to look like a table
        -- Course Name
        -- Current Grade
        -- Sort by Current Grade from lowest to highest
    
    Keep the response concise and focused.
    The response should be in HTML format that includes headings, bullet points, 
    and tables with headings so that it is easy to read.
    Only include the analysis within the start <html> and end <html> tags.
    """
    system_prompt = """
    You are an expert in evaluating the grades and performance of high school students.
    """
    #agent = Agent('anthropic:claude-3-5-sonnet-latest', system_prompt=system_prompt, model_settings={'temperature': 0.0})
    agent = Agent('gemini-2.0-flash-thinking-exp-01-21', system_prompt=system_prompt, model_settings={'temperature': 0.0})
    try:
        # Extract and return the content
        result = agent.run_sync(prompt)
        return result.data
    except Exception as e:
        return f"Error processing assignments: {str(e)}"

def send_email(analysis):
    with logfire.span("send_email"):
        logfire.info("Sending email with analysis")
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
            logfire.info(f"Email sent successfully to {len(receiver_emails)} recipients!")
    except Exception as e:
        logfire.error(f"Error sending email: {e}")
        print(f"Error sending email: {e}")

def scheduled_job():
    with logfire.span("scheduled_job"):
        logfire.info("Running scheduled job")
    """Function to be scheduled to run daily at 3:00 PM"""
    print(f"Running scheduled job at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        # Get credentials and login
        credentials = get_credentials()
        login_to_website(**credentials)
        
        # Read the saved assignments
        with open('assignments.txt', 'r') as f:
            assignments_content = f.read()
        
        # Analyze assignments
        analysis = invoke_llm(assignments_content)
        print("\nAnalysis complete!")
        
        # Send email with analysis
        send_email(analysis)
        
        print("Scheduled job completed successfully")
        logfire.info("Scheduled job completed successfully")
    except Exception as e:
        logfire.error(f"Error in scheduled job: {str(e)}")
        print(f"Error in scheduled job: {str(e)}")

@click_cli.command()
@click_cli.option('--local', is_flag=True, help='Use local assignments.txt instead of scraping website')
@click_cli.option('--email', is_flag=True, help='Send analysis via email')
@click_cli.option('--schedule', is_flag=True, help='Schedule to run daily at 3:00 PM')
def cli(local, email, schedule):
    with logfire.span("cli"):
        logfire.info("Starting CLI")
    """Grade Checker Application"""
    if schedule:
        print("Setting up scheduled job to run daily at 3:00 PM...")
        logfire.info("Setting up scheduled job to run daily at 3:00 PM...")
        schedule.every().day.at("15:00").do(scheduled_job)
        print(f"Job scheduled. Current time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        logfire.info(f"Job scheduled. Current time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("Press Ctrl+C to exit")
        
        try:
            while True:
                schedule.run_pending()
                schedule_time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            print("Scheduler stopped by user")
            logfire.info("Scheduler stopped by user")
            sys.exit(0)
    else:
        try:
            print("Starting grade check...")
            logfire.info("Starting grade check...")
            
            if not local:
                print("Scraping website for assignments...")
                logfire.info("Scraping website for assignments...")
                credentials = get_credentials()
                login_to_website(**credentials)
                print("Website scraping complete.")
                logfire.info("Website scraping complete.")
            else:
                print("Using local assignments file...")
                logfire.info("Using local assignments file...")
            
            # Read the saved assignments
            print("Reading assignments file...")
            logfire.info("Reading assignments file...")
            with open('assignments.txt', 'r') as f:
                assignments_content = f.read()
            
            print("Sending assignments to LLM for analysis...")
            logfire.info("Sending assignments to LLM for analysis...")
            try:
                analysis = invoke_llm(assignments_content)
                print("\nAnalysis complete!")
                print(analysis)
                logfire.info("Analysis complete!")
                
                if email:
                    print("\nSending analysis via email...")
                    logfire.info("Sending analysis via email...")
                    send_email(analysis)
                
                sys.exit(0)  # Exit successfully
            except Exception as e:
                print(f"\nError during LLM analysis: {str(e)}")
                logfire.error(f"LLM analysis failed: {str(e)}")
                sys.exit(1)  # Exit with error
            
        except Exception as e:
            print(f"\nError: {str(e)}")
            logfire.error(f"Grade check failed: {str(e)}")
            sys.exit(1)  # Exit with error

if __name__ == "__main__":
    with logfire.span("grade_checker_application"):
        cli()
