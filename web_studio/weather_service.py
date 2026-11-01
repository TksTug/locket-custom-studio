import requests

# WMO Weather interpretation codes
WMO_CODES = {
    0: ("Trời quang đãng", "☀️"),
    1: ("Chủ yếu quang đãng", "🌤️"),
    2: ("Có mây rải rác", "⛅"),
    3: ("Nhiều mây u ám", "☁️"),
    45: ("Có sương mù", "🌫️"),
    48: ("Sương mù đọng", "🌫️"),
    51: ("Mưa phùn nhẹ", "🌦️"),
    53: ("Mưa phùn vừa", "🌦️"),
    55: ("Mưa phùn dày", "🌧️"),
    61: ("Mưa nhỏ", "🌧️"),
    63: ("Mưa vừa", "🌧️"),
    65: ("Mưa to rào rực", "🌧️"),
    71: ("Tuyết rơi nhẹ", "🌨️"),
    73: ("Tuyết rơi vừa", "🌨️"),
    75: ("Tuyết rơi dày", "❄️"),
    80: ("Mưa rào nhẹ", "🌦️"),
    81: ("Mưa rào vừa", "🌧️"),
    82: ("Mưa rào rất lớn", "⛈️"),
    95: ("Dông sét có mưa", "⛈️"),
    96: ("Dông bão kèm mưa đá", "⛈️"),
    99: ("Dông bão sấm chớp dữ dội", "⚡"),
}

DEFAULT_LOCATIONS = {
    "hanoi": {"name": "Hà Nội", "lat": 21.0285, "lon": 105.8542},
    "hcm": {"name": "TP. Hồ Chí Minh", "lat": 10.8231, "lon": 106.6297},
    "danang": {"name": "Đà Nẵng", "lat": 16.0544, "lon": 108.2022},
    "dalat": {"name": "Đà Lạt", "lat": 11.9404, "lon": 108.4583},
    "haiphong": {"name": "Hải Phòng", "lat": 20.8449, "lon": 106.6881},
    "cantho": {"name": "Cần Thơ", "lat": 10.0452, "lon": 105.7469},
}

def get_coordinates(city_name: str) -> tuple[str, float, float]:
    """Search for latitude & longitude of city via Open-Meteo Geocoding."""
    slug = city_name.strip().lower()
    for k, v in DEFAULT_LOCATIONS.items():
        if k in slug or v["name"].lower() in slug:
            return v["name"], v["lat"], v["lon"]

    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&language=vi&format=json"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            results = data.get("results")
            if results and len(results) > 0:
                first = results[0]
                return first.get("name", city_name), first.get("latitude"), first.get("longitude")
    except Exception:
        pass

    # Default to Hanoi if not found
    return "Hà Nội", 21.0285, 105.8542

def fetch_live_weather(city_name: str = "Hà Nội") -> dict:
    """Fetches real-time weather metrics (temp, apparent temp, humidity, wind, condition)."""
    resolved_name, lat, lon = get_coordinates(city_name)
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m"
        )
        res = requests.get(url, timeout=6)
        if res.status_code == 200:
            data = res.json()
            current = data.get("current", {})
            w_code = current.get("weather_code", 0)
            cond_desc, emoji = WMO_CODES.get(w_code, ("Quang đãng", "☀️"))
            temp = round(current.get("temperature_2m", 28))
            feels = round(current.get("apparent_temperature", temp))
            humidity = round(current.get("relative_humidity_2m", 65))
            wind = round(current.get("wind_speed_10m", 10))
            precip = current.get("precipitation", 0.0)

            return {
                "success": True,
                "city": resolved_name,
                "temp": f"{temp}°C",
                "feels_like": f"{feels}°C",
                "condition": f"{emoji} {cond_desc}",
                "humidity": f"{humidity}%",
                "wind": f"{wind} km/h",
                "rain_prob": f"{precip} mm",
                "radar_scan": True,
                "lat": lat,
                "lon": lon
            }
    except Exception as e:
        pass

    # Fallback default if offline
    return {
        "success": False,
        "city": resolved_name,
        "temp": "31°C",
        "feels_like": "34°C",
        "condition": "🌤️ Trời đẹp",
        "humidity": "68%",
        "wind": "12 km/h",
        "rain_prob": "0 mm",
        "radar_scan": True,
        "lat": lat,
        "lon": lon
    }
