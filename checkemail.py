import smtplib
from dotenv import load_dotenv
import os

def main():
    load_dotenv()

    """Sends the analysis via email with HTML content to multiple recipients."""
    sender_email = os.getenv('GMAIL_SENDER')
    sender_password = os.getenv('GMAIL_APP_PASSWORD')
    #receiver_emails = [email.strip() for email in os.getenv('GMAIL_RECEIVERS').split(',')]
    
    # Create subject with current date
    subject = f"Naina's Grades/Assignments"
    
   

    try:
        #with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            print('sender_email='+sender_email)
            print('sender_password='+ sender_password)
            server.login(sender_email, sender_password)
            print("FINISHED LOGIN")
            # Send to all recipients
            server.sendmail(
                sender_email,
                'pbrao@pmbrao.com',  # Pass list of recipients
                'Test eamil'
            )
            
    except Exception as e:
        print(f"Error sending email: {e}")



if __name__ == "__main__":
    main()