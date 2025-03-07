from decouple import config

BASE_URL = "https://canvas.uautonoma.cl/api/v1"
API_TOKEN = config("TOKEN")
HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}
