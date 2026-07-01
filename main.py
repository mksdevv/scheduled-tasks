import csv
import datetime as dt
import smtplib
import random

#--------------------------------------Globals------------------------------------------#
sender_email = "maxshahnazaryan774@gmail.com"
sender_password = "wwan ypey bolm aavk"
sender_email_smtp = 'smtp.gmail.com'
file_1 = "../letter_templates/letter_1.txt"
file_2 = "../letter_templates/letter_2.txt"
file_3 = "../letter_templates/letter_3.txt"
text_templates = [file_1, file_2, file_3]
#-------------------------------------Functions-----------------------------------------#
def load_birthdays():
    with open("birthdays.csv", "r", encoding="utf-8") as data:
        reader = csv.DictReader(data)
        all_data = []
        for row in reader:
            all_data.append(row)
        return all_data
def find_birthday():
    data = load_birthdays()
    now = dt.datetime.now()
    month = now.month
    day = now.day
    if not data:
        print("No data, func: find_birthday")
        return None
    matches = []
    for item in data:
        if int(item["month"]) == month and int(item["day"]) == day:
            matches.append(item)
    if not matches:
        print("No matches, func: find_birthday")
        return None
    return matches
def load_text_templates():
    try:
        with open(f"{random.choice(text_templates)}", "r", encoding="utf-8") as file:
            original_text = file.read()
    except FileNotFoundError:
        original_text = """Dear [NAME],\n\nHappy birthday!\n\nAll the best for the year!\n\nAngela"""
    return original_text
def change_text(name, text):
    new_text = text.replace("[NAME]", name)
    return new_text
def send_email(recipient, letter):
    with smtplib.SMTP(sender_email_smtp) as connection:
        connection.starttls()
        connection.login(sender_email, sender_password)
        connection.sendmail(from_addr=sender_email,
                            to_addrs=recipient,
                            msg=f"Subject: Happy birthday!\n\n"
                                f"{letter}")
def main():
    birthdays = find_birthday()
    if not birthdays:
        print("No birthdays")
        return
    for birthday in birthdays:
        name = birthday["name"]
        email = birthday["email"]
        text = change_text(name, load_text_templates())
        send_email(email, text)
        print(f"Sent email to {name}")
main()










