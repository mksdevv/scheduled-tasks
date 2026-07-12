import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from twilio.rest import Client


# -------------------------------------Globals-------------------------------------#
RAIN_WARNING_HOURS = 12
MIN_WARNING_MINUTES = 30

MY_LAT = float(os.environ.get("MY_LAT", 41.06))
MY_LONG = float(os.environ.get("MY_LONG", 44.61))

UNIT = "metric"
FORECAST_COUNT = 10
OWM_ENDPOINT = "https://api.openweathermap.org/data/2.5/forecast"

SEND_SMS = os.environ.get(
    "SEND_SMS",
    "false",
).lower() == "true"

MESSAGES_LOG_FILE = os.environ.get(
    "MESSAGES_LOG_FILE",
    "sent_messages.log",
)

WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")


# --------------------------------Helper functions--------------------------------#
def get_weather_data():
    parameters = {
        "lat": MY_LAT,
        "lon": MY_LONG,
        "units": UNIT,
        "appid": WEATHER_API_KEY,
        "cnt": FORECAST_COUNT,
    }
    response = requests.get(
        OWM_ENDPOINT,
        params=parameters,
        timeout=5,
    )
    response.raise_for_status()
    return response.json()

def get_weather_data_with_delay():
    attempt = 1
    max_attempts = 5
    delay = 5
    max_delay = 120
    while attempt <= max_attempts:
        try:
            return get_weather_data()
        except requests.RequestException as error:
            attempts_left = max_attempts - attempt
            print(f"Failed to get weather data: {error}")
            if attempts_left == 0:
                return None
            time.sleep(delay)
            delay = min(
                max_delay,
                delay * 2,
            )
            attempt += 1
    return None


def send_sms(message_text, send_enabled=False):
    if not send_enabled:
        return None
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    sender_number = os.environ.get("TWILIO_PHONE_NUMBER")
    receiver_number = os.environ.get("RECEIVER_PHONE_NUMBER")
    if not all(
        [
            account_sid,
            auth_token,
            sender_number,
            receiver_number,
        ]
    ):
        raise RuntimeError(
            "One or more Twilio environment variables are missing."
        )
    client = Client(
        account_sid,
        auth_token,
    )
    message = client.messages.create(
        from_=sender_number,
        to=receiver_number,
        body=message_text,
    )
    return message.sid

def get_city_timezone(data):
    try:
        timezone_shift = data.get("city").get("timezone")
        return timezone(
            timedelta(seconds=timezone_shift)
        )
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None

def get_forecast_local_time(forecast, city_timezone):
    forecast_timestamp = forecast.get("dt")
    if forecast_timestamp is None:
        return None
    try:
        forecast_utc = datetime.fromtimestamp(
            forecast_timestamp,
            timezone.utc,
        )
        return forecast_utc.astimezone(city_timezone)
    except (TypeError, ValueError, OSError, OverflowError):
        return None

def format_time_difference(time_difference):
    total_seconds = int(
        time_difference.total_seconds()
    )
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    if hours == 0:
        minute_text = (
            "minute"
            if minutes == 1
            else "minutes"
        )
        return f"{minutes} {minute_text}"
    if minutes == 0:
        hour_text = (
            "hour"
            if hours == 1
            else "hours"
        )
        return f"{hours} {hour_text}"
    hour_text = (
        "hour"
        if hours == 1
        else "hours"
    )
    minute_text = (
        "minute"
        if minutes == 1
        else "minutes"
    )
    return (
        f"{hours} {hour_text} "
        f"and {minutes} {minute_text}"
    )

def check_weather_code(weather_code):
    weather_group = weather_code // 100
    return weather_group in (2, 3, 5)
def save_message_record(forecast_time):
    log_path = Path(MESSAGES_LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a",encoding="utf-8") as file:
        file.write(
            f"{datetime.now(timezone.utc).isoformat()} | "
            f"{forecast_time.isoformat()}\n"
        )

def was_message_already_sent(forecast_time):
    log_path = Path(MESSAGES_LOG_FILE)
    try:
        with log_path.open("r",encoding="utf-8") as file:
            for line in file:
                parts = line.strip().split(" | ")
                if len(parts) != 2:
                    continue
                saved_forecast_text = parts[1]
                try:
                    saved_forecast_time = datetime.fromisoformat(
                        saved_forecast_text
                    )
                except ValueError:
                    continue
                if saved_forecast_time == forecast_time:
                    return True
    except FileNotFoundError:
        return False
    except OSError as error:
        print(f"Could not read message log: {error}")
        return False
    return False


# ---------------------------------Main function----------------------------------#
def main():
    if not WEATHER_API_KEY:
        print("WEATHER_API_KEY environment variable is missing.")
        return
    data = get_weather_data_with_delay()
    if not data:
        return
    forecasts = data.get("list", [])
    if not forecasts:
        print("No forecast data found")
        return
    city_timezone = get_city_timezone(data)
    if city_timezone is None:
        print("City timezone not found")
        return
    local_time_now = datetime.now(city_timezone)
    warning_limit = timedelta(hours=RAIN_WARNING_HOURS)
    minimum_warning_time = timedelta(minutes=MIN_WARNING_MINUTES)
    city_data = data.get("city", {})
    if not isinstance(city_data, dict):
        city_data = {}
    city = city_data.get("name") or "your area"
    rain_found = False
    duplicate_warning_found = False
    for forecast in forecasts:
        weather_data = forecast.get("weather", [])
        weather = (weather_data[0] if weather_data else None)
        if not weather:
            continue
        weather_id = weather.get("id")
        description = weather.get("description")
        if weather_id is None or not description:
            continue
        forecast_local_time = get_forecast_local_time(
            forecast,
            city_timezone,
        )
        if forecast_local_time is None:
            continue
        difference = (forecast_local_time - local_time_now)
        if difference < minimum_warning_time:
            continue
        if difference > warning_limit:
            break
        if not check_weather_code(weather_id):
            continue
        rain_found = True
        if was_message_already_sent(
            forecast_local_time
        ):
            duplicate_warning_found = True
            print(
                "A warning for the forecast at "
                f"{forecast_local_time:%H:%M} "
                "was already sent."
            )
            continue
        probability = forecast.get("pop", 0) * 100
        time_until_rain_text = format_time_difference(
            difference
        )
        message_text = (
            f"Weather warning: {description.capitalize()} ☂️ "
            f"is expected in {city} in approximately "
            f"{time_until_rain_text}, "
            f"at {forecast_local_time:%H:%M} "
            f"(probability: {probability:.0f}%)."
        )
        print(message_text)
        try:
            message_sid = send_sms(message_text,SEND_SMS)
            if message_sid:
                save_message_record(forecast_local_time)
                print(f"Message submitted to Twilio: {message_sid}")
            else:
                print("SMS sending is disabled")
        except Exception as error:
            print(f"Failed to send message to Twilio: {error}")
            return
        return
    if rain_found and duplicate_warning_found:
        print("Rain was found, but warnings for those forecasts "
            "were already sent.")
    else:
        print(
            f"No rain found between "
            f"{MIN_WARNING_MINUTES} minutes "
            f"and {RAIN_WARNING_HOURS} hours from now."
        )


if __name__ == "__main__":
    main()
