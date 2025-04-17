# email_utils.py
import os
import smtplib
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

load_dotenv()

email_user = os.getenv("EMAIL_USER")
email_password = os.getenv("EMAIL_PASSWORD")

def send_email(to, subject, message):
    print(f"Sending email from: {email_user} to: {to}")  # Debug
    print(f"Using app password starting with: {email_password[:4]}")  # Debug

    msg = MIMEMultipart()
    msg['From'] = email_user
    msg['To'] = to
    msg['Subject'] = subject
    msg.attach(MIMEText(message, 'plain'))

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(email_user, email_password)
            server.sendmail(email_user, to, msg.as_string())
        return "Delivered"
    except Exception as e:
        print(f"Error sending email: {e}")
        return "Failed"
