from apscheduler.schedulers.background import BackgroundScheduler
from django.core.mail import send_mail
from django.conf import settings
from twilio.rest import Client
from django.utils.timezone import now
from datetime import timedelta
from decimal import Decimal
from django.db.models import Sum
from TFF.models import TiexCollect

# -----------------------------
# WhatsApp sender function
# -----------------------------
def send_whatsapp_message(message):
    """
    Send WhatsApp message using Twilio
    """
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=settings.TWILIO_WHATSAPP_NUMBER,
            to=settings.OWNER_WHATSAPP
        )
        print("[GST WhatsApp] Message sent successfully")
    except Exception as e:
        print(f"[GST WhatsApp] Failed to send WhatsApp message: {e}")

def send_sms(message, to_numbers):
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
        # Ensure we have a list
        if isinstance(to_numbers, str):
            to_numbers = [to_numbers]
        
        for number in to_numbers:
            client.messages.create(
                body=message,
                from_=settings.TWILIO_PHONE_NUMBER,  # SMS-enabled Twilio number
                to=number
            )
            print(f"[SMS] Message sent successfully to {number}")
    
    except Exception as e:
        print(f"[SMS] Failed to send message: {e}")

def generate_gst_sms_message(total_gst, month_year):
    today = now()
    due_month_year = today.strftime('%B %Y')
    
    message = f"TFF GST Summary ({month_year}): Total GST Rs.{total_gst}. Due: 20 {due_month_year}. Please file return."
    return message


# -----------------------------
# Generate message content
# -----------------------------
def generate_gst_message(total_gst, month_year):
    today = now()
    due_month_year = today.strftime('%B %Y') 
    return (
        f"*TFF – MONTHLY GST SUMMARY*\n\n"
        f"*MONTH:* {month_year}\n"
        f"*TOTAL GST:* ₹{total_gst}\n"
        f"*DUE DATE:* 20 {due_month_year}\n\n"
        f"This figure is calculated based on consolidated sales data from all branches.\n"
        f"Request you to proceed with GST return filing and payment within the prescribed due date to ensure statutory compliance.\n"
        f"– TFF Automated Accounts Notification"
    )

# -----------------------------
# Send monthly GST Email
# -----------------------------
def send_monthly_gst_email():
    today = now()
    first_day_this_month = today.replace(day=1)
    last_month = first_day_this_month - timedelta(days=1)
    start_date = last_month.replace(day=1)
    end_date = last_day_of_month = first_day_this_month - timedelta(days=1)

    total_gst = TiexCollect.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).aggregate(total=Sum('gst'))['total'] or Decimal('0.00')

    month_year = start_date.strftime('%B %Y')
    message = generate_gst_message(total_gst, month_year)
    subject = f"GST Collection Intimation - {month_year}"

    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [settings.ADMIN_EMAIL])
        print(f"[GST Email] Sent monthly GST email: ₹{total_gst}")
    except Exception as e:
        print(f"[GST Email] Failed to send email: {e}")

# -----------------------------
# Send monthly GST WhatsApp
# -----------------------------
def send_monthly_gst_whatsapp():
    today = now()
    first_day_this_month = today.replace(day=1)
    last_month = first_day_this_month - timedelta(days=1)
    start_date = last_month.replace(day=1)
    end_date = first_day_this_month - timedelta(days=1)

    total_gst = TiexCollect.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).aggregate(total=Sum('gst'))['total'] or Decimal('0.00')

    month_year = start_date.strftime('%B %Y')
    message = generate_gst_message(total_gst, month_year)

    send_whatsapp_message(message)

    sms_message = generate_gst_sms_message(total_gst, month_year)
    phone_numbers = [
        "+919573404709",
        "+918500279333",  
    ]
    send_sms(sms_message, phone_numbers)

# -----------------------------
# Scheduler
# -----------------------------
def start_scheduler():
    scheduler = BackgroundScheduler()

    # Email job
    scheduler.add_job(
        send_monthly_gst_email,
        trigger='cron',
        day=1,
        hour=00,
        minute=5,
        id='monthly_gst_email',
        replace_existing=True
    )

    # WhatsApp job
    scheduler.add_job(
        send_monthly_gst_whatsapp,
        trigger='cron',
        day=1,
        hour=00,
        minute=5,
        id='monthly_gst_whatsapp',
        replace_existing=True
    )

    scheduler.start()
    print("[Scheduler] Monthly GST email & WhatsApp scheduler started")
