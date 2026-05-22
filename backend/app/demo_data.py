"""Demo records used when the user has no RapidAPI key.

The data covers multiple languages, countries, stream states, and genres so
the interface can be exercised without any external dependency.
"""

DEMO_LANGUAGES = [
    {"code": "es", "nameEnglish": "Spanish", "nameNative": "Español", "stationCount": 4, "isRtl": False},
    {"code": "fr", "nameEnglish": "French", "nameNative": "Français", "stationCount": 3, "isRtl": False},
    {"code": "ar", "nameEnglish": "Arabic", "nameNative": "العربية", "stationCount": 3, "isRtl": True},
    {"code": "pt", "nameEnglish": "Portuguese", "nameNative": "Português", "stationCount": 2, "isRtl": False},
]

DEMO_STATIONS = [
    {"id": 1001, "name": "Radio Derechos Madrid", "slug": "radio-derechos-madrid", "location": {"cityName": "Madrid", "countryName": "Spain", "countryCode": "ES"}, "genre": {"text": "News"}, "popularity": {"global": 86}, "streams": [{"url": "https://example.com/es-news.mp3", "bitrate": 128, "format": "mp3", "isHttps": True}], "languageCode": "es"},
    {"id": 1002, "name": "Voces de la Frontera", "slug": "voces-frontera", "location": {"cityName": "Tijuana", "countryName": "Mexico", "countryCode": "MX"}, "genre": {"text": "Talk"}, "popularity": {"global": 77}, "streams": [{"url": "https://example.com/frontera.aac", "bitrate": 96, "format": "aac", "isHttps": True}], "languageCode": "es"},
    {"id": 1003, "name": "Andes Seguridad", "slug": "andes-seguridad", "location": {"cityName": "Quito", "countryName": "Ecuador", "countryCode": "EC"}, "genre": {"text": "News"}, "popularity": {"global": 71}, "streams": [], "languageCode": "es"},
    {"id": 2001, "name": "Radio Droits Paris", "slug": "radio-droits-paris", "location": {"cityName": "Paris", "countryName": "France", "countryCode": "FR"}, "genre": {"text": "News"}, "popularity": {"global": 84}, "streams": [{"url": "https://example.com/fr-news.mp3", "bitrate": 128, "format": "mp3", "isHttps": True}], "languageCode": "fr"},
    {"id": 2002, "name": "Voix Migration", "slug": "voix-migration", "location": {"cityName": "Marseille", "countryName": "France", "countryCode": "FR"}, "genre": {"text": "Public"}, "popularity": {"global": 64}, "streams": [{"url": "https://example.com/voix.ogg", "bitrate": 64, "format": "ogg", "isHttps": True}], "languageCode": "fr"},
    {"id": 3001, "name": "إذاعة العدالة", "slug": "idhaat-aladala", "location": {"cityName": "Tunis", "countryName": "Tunisia", "countryCode": "TN"}, "genre": {"text": "News"}, "popularity": {"global": 80}, "streams": [{"url": "https://example.com/ar-news.mp3", "bitrate": 128, "format": "mp3", "isHttps": True}], "languageCode": "ar"},
    {"id": 3002, "name": "صوت الحدود", "slug": "sawt-alhudud", "location": {"cityName": "Amman", "countryName": "Jordan", "countryCode": "JO"}, "genre": {"text": "Talk"}, "popularity": {"global": 61}, "streams": [{"url": "https://example.com/border.mp3", "bitrate": 96, "format": "mp3", "isHttps": True}], "languageCode": "ar"},
    {"id": 4001, "name": "Rádio Direitos Lisboa", "slug": "radio-direitos-lisboa", "location": {"cityName": "Lisbon", "countryName": "Portugal", "countryCode": "PT"}, "genre": {"text": "News"}, "popularity": {"global": 73}, "streams": [{"url": "https://example.com/pt-news.mp3", "bitrate": 128, "format": "mp3", "isHttps": True}], "languageCode": "pt"},
]


def stations_for_language(code: str) -> list[dict]:
    return [station for station in DEMO_STATIONS if station["languageCode"] == code]

