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

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

# Twilio setup
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
client = Client(account_sid, auth_token)

# Email setup
email_user = os.getenv("EMAIL_USER")
email_password = os.getenv("EMAIL_PASSWORD")

# Active scheduler tracking (phone/email)
active_schedulers = {}

# Storage for tracking reminders
sent_sms_log = []
sent_email_log = []

def send_sms(to, message):
    try:
        client.messages.create(body=message, from_=twilio_number, to=to)
        sent_sms_log.append({
            "time": datetime.now().strftime("%H:%M"),
            "amount": message.split("drink ")[1].split("ml")[0] + " ml"
        })
    except Exception as e:
        print(f"SMS Error: {e}")

def send_email(to, subject, message):
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
        sent_email_log.append({
            "time": datetime.now().strftime("%H:%M"),
            "amount": message.split("drink ")[1].split("ml")[0] + " ml"
        })
    except Exception as e:
        print(f"Email Error: {e}")

def start_scheduling(name, total_ml, phone, email, start_time, end_time, interval):
    if phone in active_schedulers:
        active_schedulers[phone]['active'] = False

    now = datetime.now()
    start_datetime = now.replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0)
    end_datetime = now.replace(hour=end_time.hour, minute=end_time.minute, second=0, microsecond=0)

    if start_datetime < now:
        start_datetime += timedelta(days=1)
        end_datetime += timedelta(days=1)

    total_minutes = int((end_datetime - start_datetime).total_seconds() // 60)
    if total_minutes <= 0:
        return

    intervals = total_minutes // interval
    if intervals == 0:
        intervals = 1
    intake_per_interval = total_ml // intervals

    active_flag = {'active': True}
    active_schedulers[phone] = active_flag

    def schedule_loop():
        for i in range(intervals):
            if not active_flag['active']:
                break
            delay = (start_datetime - datetime.now()).total_seconds() + i * interval * 60
            if delay > 0:
                time.sleep(delay)
            if active_flag['active']:
                message = f"Hi {name}! 💧 It's time to drink {intake_per_interval}ml of water. Stay hydrated!"
                if phone:
                    send_sms(phone, message)
                elif email:
                    send_email(email, "Water Reminder", message)

    threading.Thread(target=schedule_loop).start()

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
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
            return "Please provide either a mobile number or email."

        base = 2000
        if gender == "male": base += 500
        if weight > 70: base += 250
        if height > 170: base += 250
        if age < 18: base -= 250

        start_time = datetime.now().replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        end_time = datetime.now().replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
        if start_time < datetime.now():
            start_time += timedelta(days=1)
            end_time += timedelta(days=1)

        total_minutes = int((end_time - start_time).total_seconds() // 60)
        intervals = total_minutes // interval
        if intervals == 0:
            intervals = 1
        intake_per_interval = base // intervals

        scheduled_times = [(start_time + timedelta(minutes=i * interval)).strftime('%H:%M') for i in range(intervals)]
        water_amounts = [intake_per_interval] * intervals

        session['user_info'] = {
            "name": name, "water": base, "scheduled_times": scheduled_times,
            "water_amounts": water_amounts, "phone": phone, "email": email
        }

        start_scheduling(name, base, phone, email, start_time, end_time, interval)

        return redirect(url_for("result"))

    return render_template("index.html")

@app.route("/result")
def result():
    user_info = session.get('user_info')
    if not user_info:
        return redirect(url_for('index'))

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
    if phone in active_schedulers:
        active_schedulers[phone]['active'] = False
    return redirect(url_for('index'))

@app.route("/track")
def track():
    delivered_count = len(sent_sms_log)  # Count how many messages have been delivered
    return render_template("track.html", 
                           reminders_sms=sent_sms_log, 
                           reminders_email=sent_email_log,
                           delivered=delivered_count)

if __name__ == "__main__":
    app.run(debug=True)
