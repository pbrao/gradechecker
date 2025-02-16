import argparse
from helium import S, start_chrome, wait_until, write, click, Link, kill_browser, get_driver
from selenium.webdriver.common.by import By
import time
from dotenv import load_dotenv
import os
from litellm import completion

def show_spinner():
    import itertools
    import threading
    import sys
    import time

    spinner = itertools.cycle(['-', '/', '|', '\\'])
    stop_spinner = False

    def spin():
        while not stop_spinner:
            sys.stdout.write(next(spinner))  # Write the next character
            sys.stdout.flush()               # Flush stdout buffer
            sys.stdout.write('\b')           # Move cursor back
            time.sleep(0.1)

    spinner_thread = threading.Thread(target=spin)
    spinner_thread.start()
    return stop_spinner, spinner_thread

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
    # Prepare the prompt
    prompt = f"""
    You are an expert academic assistant. Analyze the following student assignments and grades:
    
    {assignments_content}
    
    Your task:
    1. Identify all missing assignments
    2. Identify all class grades below 80%
    3. Provide a detailed explanation of the findings
    4. Create a tabular breakdown with:
       - Class name
       - Missing assignments (if any)
       - Current grade
       - Recommended actions
    
    Format your response as follows:
    
    [Summary Explanation]
    <detailed explanation here>
    
    [Grade Breakdown]
    | Class Name       | Missing Assignments | Current Grade | Recommended Actions |
    |------------------|---------------------|---------------|---------------------|
    | <class name>     | <missing>           | <grade>       | <actions>           |
    | <class name>     | <missing>           | <grade>       | <actions>           |
    """

    # Send to LLM
    response = completion(
        model="gemini/gemini-1.5-pro-latest",
        messages=[{"role": "user", "content": prompt}]
    )
    
    # Extract and return the content
    return response.get('choices', [{}])[0].get('message', {}).get('content')

if __name__ == "__main__":
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Grade Checker Application")
    parser.add_argument('--local', action='store_true', 
                       help='Use local assignments.txt instead of scraping website')
    args = parser.parse_args()

    try:
        print("Starting grade check...")
        stop_spinner, spinner_thread = show_spinner()
        
        if not args.local:
            # Full scraping mode
            credentials = get_credentials()
            login_to_website(**credentials)
        
        # Read the saved assignments
        with open('assignments.txt', 'r') as f:
            assignments_content = f.read()
        
        print("\nProcessing assignments...")
        
        # Process assignments through LLM
        analysis = invoke_llm(assignments_content)
        
        # Stop the spinner
        stop_spinner = True
        spinner_thread.join()
        
        print("\nAnalysis complete!")
        print(analysis)
        
    except Exception as e:
        # Ensure spinner stops on error
        stop_spinner = True
        spinner_thread.join()
        print(f"\nError: {str(e)}")
