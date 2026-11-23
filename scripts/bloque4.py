import os
from dotenv import load_dotenv
import requests

load_dotenv()
api_key = os.getenv("API_FOOTBALL_KEY")

if not api_key:
  raise ValueError("No se encontró API_FOOTBALL_KEY en .env")

url = "https://v3.football.api-sports.io/status"
headers = {"x-apisports-key": api_key}

response = requests.get(url, headers=headers, timeout=15)
print("Código HTTP:", response.status_code)
print(response.json())