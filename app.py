from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from twilio.rest import Client
import threading
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

# Twilio setup
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
client = None

if account_sid and auth_token:
    client = Client(account_sid, auth_token)
else:
    logger.error("Twilio credentials not found in environment variables!")

# Email setup
email_user = os.getenv("EMAIL_USER")
email_password = os.getenv("EMAIL_PASSWORD")

# Active scheduler tracking
active_schedulers = {}

# Logs
sent_sms_log = []
sent_email_log = []

def send_sms(to, message):
    try:
        if not client:
            logger.error("Twilio client not initialized - SMS not sent")
            return
            
        logger.info(f"Attempting to send SMS to {to}")
        message = client.messages.create(
            body=message,
            from_=twilio_number,
            to=to
        )
        logger.info(f"SMS sent successfully! SID: {message.sid}")
        sent_sms_log.append({
            "time": datetime.now().strftime("%H:%M"),
            "amount": message.split("drink ")[1].split("ml")[0] + " ml"
        })
    except Exception as e:
        logger.error(f"SMS Error: {str(e)}")
        print(f"SMS Error details: {str(e)}")

def send_email(to, subject, message):
    msg = MIMEMultipart()
    msg['From'] = email_user
    msg['To'] = to
    msg['Subject'] = subject
    msg.attach(MIMEText(message, 'plain'))

    try:
        logger.info(f"Attempting to send email to {to}")
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(email_user, email_password)
            server.sendmail(email_user, to, msg.as_string())
        logger.info("Email sent successfully!")
        sent_email_log.append({
            "time": datetime.now().strftime("%H:%M"),
            "amount": message.split("drink ")[1].split("ml")[0] + " ml"
        })
    except Exception as e:
        logger.error(f"Email Error: {str(e)}")
        print(f"Email Error details: {str(e)}")

def start_scheduling(name, total_ml, phone, email, start_time, end_time, interval):
    logger.info(f"Starting scheduler for {name} (Phone: {phone}, Email: {email})")
    print(f"⏰ New scheduler started at {datetime.now()}")

    if phone in active_schedulers:
        logger.info(f"Stopping existing scheduler for {phone}")
        active_schedulers[phone]['active'] = False

    now = datetime.now()
    start_datetime = now.replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0)
    end_datetime = now.replace(hour=end_time.hour, minute=end_time.minute, second=0, microsecond=0)

    if start_datetime < now:
        logger.info("Adjusting schedule to tomorrow (start time passed)")
        start_datetime += timedelta(days=1)
        end_datetime += timedelta(days=1)

    total_minutes = int((end_datetime - start_datetime).total_seconds() // 60)
    if total_minutes <= 0:
        logger.error("Invalid time range - end time before start time")
        return

    intervals = total_minutes // interval or 1
    intake_per_interval = total_ml // intervals
    logger.info(f"Will send {intervals} reminders, {intake_per_interval}ml each")

    active_flag = {'active': True}
    active_schedulers[phone] = active_flag

    def schedule_loop():
        logger.info(f"Scheduler loop started for {name}")
        print(f"🔁 Starting scheduler loop at {datetime.now()}")

        # Calculate initial delay
        delay = (start_datetime - datetime.now()).total_seconds()
        if delay > 0:
            logger.info(f"Waiting {delay / 60:.1f} minutes until first reminder")
            time.sleep(delay)  # Wait for the first reminder to send

        # Send reminders at intervals
        for i in range(intervals):
            if not active_flag['active']:
                logger.info("Scheduler stopped by user request")
                print("❌ Scheduler stopped")
                break

            if active_flag['active']:
                message = f"Hi {name}! 💧 It's time to drink {intake_per_interval}ml of water. Stay hydrated!"
                logger.info(f"Sending reminder #{i+1}/{intervals}")
                print(f"📤 Sending reminder to {phone or email}")

                if phone:
                    send_sms(phone, message)
                elif email:
                    send_email(email, "Water Reminder", message)

            # Wait for the next reminder based on the interval
            time.sleep(interval * 60)  # Wait for the next reminder

    thread = threading.Thread(target=schedule_loop)
    thread.daemon = True  # Important for Render worker service
    thread.start()
    logger.info("Background scheduler thread started")

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        logger.info("Received form submission")
        try:
            name = request.form["name"]
            age = int(request.form["age"])
            height = int(request.form["height"])
            weight = int(request.form["weight"])
            gender = request.form["gender"]
            start_hour = int(request.form["start_hour"])
            start_minute = int(request.form["start_minute"])
            end_hour = int(request.form["end_hour"])
            end_minute = int(request.form["end_minute"])
            interval = int(request.form["interval"])
            phone = request.form.get("phone")
            email = request.form.get("email")

            if not phone and not email:
                logger.error("No contact method provided")
                return "Please provide either a mobile number or email."

            logger.info(f"Processing form for {name}")
            
            # Calculate total water intake
            base = 2000
            if gender == "male": base += 500
            if weight > 70: base += 250
            if height > 170: base += 250
            if age < 18: base -= 250
            logger.info(f"Calculated water intake: {base}ml")

            start_time = datetime.now().replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
            end_time = datetime.now().replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
            if start_time < datetime.now():
                logger.info("Adjusting schedule to tomorrow")
                start_time += timedelta(days=1)
                end_time += timedelta(days=1)

            total_minutes = int((end_time - start_time).total_seconds() // 60)
            intervals = total_minutes // interval or 1
            intake_per_interval = base // intervals

            scheduled_times = [(start_time + timedelta(minutes=i * interval)).strftime('%H:%M') for i in range(intervals)]
            water_amounts = [intake_per_interval] * intervals

            session['user_info'] = {
                "name": name, "water": base, "scheduled_times": scheduled_times,
                "water_amounts": water_amounts, "phone": phone, "email": email
            }

            start_scheduling(name, base, phone, email, start_time, end_time, interval)
            logger.info("Scheduling started successfully")

            return redirect(url_for("result"))
            
        except Exception as e:
            logger.error(f"Form processing error: {str(e)}")
            return f"An error occurred: {str(e)}"

    return render_template("index.html")

@app.route("/result")
def result():
    user_info = session.get('user_info')
    if not user_info:
        logger.warning("Attempt to access result without session data")
        return redirect(url_for('index'))

    logger.info(f"Displaying results for {user_info['name']}")
    return render_template(
        "result.html",
        name=user_info['name'],
        water=user_info['water'],
        scheduled_times=user_info['scheduled_times'],
        water_amounts=user_info['water_amounts'],
        phone=user_info['phone'],
        email=user_info['email']
    )

@app.route("/stop", methods=["POST"])
def stop():
    phone = request.form["phone"]
    logger.info(f"Stop request received for {phone}")
    if phone in active_schedulers:
        active_schedulers[phone]['active'] = False
        logger.info(f"Scheduler stopped for {phone}")
    return redirect(url_for('index'))

@app.route("/track")
def track():
    delivered_count = len(sent_sms_log)
    logger.info(f"Track page accessed - {delivered_count} SMS sent")
    return render_template("track.html", 
                         reminders_sms=sent_sms_log, 
                         reminders_email=sent_email_log,
                         delivered=delivered_count)

if __name__ == "__main__":
    logger.info("Starting Flask application")
    print("🚀 Application starting...")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
