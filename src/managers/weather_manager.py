import requests
from datetime import datetime

# IIIT Una, Himachal Pradesh
DEFAULT_LATITUDE = 31.4685
DEFAULT_LONGITUDE = 76.2708


class WeatherManager:
    """Fetches weather data from Open-Meteo API (free, no API key needed)."""

    def __init__(self, latitude: float = DEFAULT_LATITUDE, longitude: float = DEFAULT_LONGITUDE):
        self.base_url = "https://api.open-meteo.com/v1/forecast"
        self.lat = latitude
        self.lon = longitude
        self.current_weather = None
        self.last_fetch = None

    def get_weather(self):
        """
        Fetch current + hourly weather. Returns dict with:
            temp, code, is_day, forecast (list), high, low
        """
        try:
            params = {
                "latitude": self.lat,
                "longitude": self.lon,
                "current": "temperature_2m,weather_code,is_day",
                "hourly": "temperature_2m,weather_code",
                "temperature_unit": "celsius",
                "timezone": "auto",
                "forecast_days": 1
            }

            response = requests.get(self.base_url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()

            # Current conditions
            current = data.get("current", {})
            self.current_weather = {
                "temp": current.get("temperature_2m", 0),
                "code": current.get("weather_code", 0),
                "is_day": current.get("is_day", 1)
            }

            # Hourly data
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            temps = hourly.get("temperature_2m", [])
            codes = hourly.get("weather_code", [])

            # Build 2-hour-step forecast from current hour
            now_hour = datetime.now().hour
            forecast = []
            for i in range(now_hour, min(now_hour + 7, len(times)), 2):
                t_str = datetime.fromisoformat(times[i]).strftime("%I%p").lstrip("0")
                forecast.append({
                    "time": t_str,
                    "temp": temps[i],
                    "code": codes[i]
                })

            self.current_weather["forecast"] = forecast[:4]

            # Day high/low from hourly data
            self.current_weather["high"] = max(temps) if temps else 0
            self.current_weather["low"] = min(temps) if temps else 0

            self.last_fetch = datetime.now()
            return self.current_weather

        except Exception as e:
            print(f"[WeatherManager] Fetch error: {e}")
            return None
