from difflib import SequenceMatcher
import json
import os
import time
import unicodedata
from dotenv import load_dotenv
import pandas as pd
import requests

load_dotenv()
API_KEY = os.getenv("API_FOOTBALL_KEY")
if not API_KEY:
  raise ValueError("No se encontró API_FOOTBALL_KEY en el archivo .env")

BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}

EXCEL_ENTRADA = "data/jugadoresWC2026.xlsx"
EXCEL_SALIDA = "data/jugadoresWC2026_enriquecido.xlsx"
CACHE_PATH = "data/cache_api_football.json"

# 0 para consolidar y cruzar desde caché sin gastar cuota;
# ajusta si necesitas descargar páginas pendientes respetando el límite diario.
MAX_REQUESTS_RUN = 0
PAUSA_SEGUNDOS = 6
MAX_PAGE_FREE = 3
TEMPORADAS_ORDEN = [2024, 2023, 2022]
requests_made = 0

SELECCIONES_EN = {
    "Alemania": "Germany",
    "Arabia Saudí": "Saudi Arabia",
    "Argelia": "Algeria",
    "Argentina": "Argentina",
    "Australia": "Australia",
    "Austria": "Austria",
    "Bosnia y Herzegovina": "Bosnia & Herzegovina",
    "Brasil": "Brazil",
    "Bélgica": "Belgium",
    "Cabo Verde": "Cape Verde Islands",
    "Canadá": "Canada",
    "Catar": "Qatar",
    "Chequia": "Czechia",
    "Colombia": "Colombia",
    "Corea del Sur": "South Korea",
    "Costa de Marfil": "Ivory Coast",
    "Croacia": "Croatia",
    "Curazao": "Curacao",
    "Ecuador": "Ecuador",
    "Egipto": "Egypt",
    "Escocia": "Scotland",
    "España": "Spain",
    "Estados Unidos": "USA",
    "Francia": "France",
    "Ghana": "Ghana",
    "Haití": "Haiti",
    "Inglaterra": "England",
    "Irak": "Iraq",
    "Irán": "Iran",
    "Japón": "Japan",
    "Jordania": "Jordan",
    "Marruecos": "Morocco",
    "México": "Mexico",
    "Noruega": "Norway",
    "Nueva Zelanda": "New Zealand",
    "Panamá": "Panama",
    "Paraguay": "Paraguay",
    "Países Bajos": "Netherlands",
    "Portugal": "Portugal",
    "RD Congo": "Congo DR",
    "Senegal": "Senegal",
    "Sudáfrica": "South Africa",
    "Suecia": "Sweden",
    "Suiza": "Switzerland",
    "Turquía": "Turkiye",
    "Túnez": "Tunisia",
    "Uruguay": "Uruguay",
    "Uzbekistán": "Uzbekistan",
}


def normalizar(texto: str) -> str:
  if not isinstance(texto, str):
    return ""
  texto = unicodedata.normalize("NFD", texto)
  texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
  return " ".join(texto.lower().strip().split())


def cargar_cache() -> dict:
  if os.path.exists(CACHE_PATH):
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
      return json.load(f)
  return {"teams": {}, "players_by_team": {}}


def guardar_cache(cache: dict) -> None:
  os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
  with open(CACHE_PATH, "w", encoding="utf-8") as f:
    json.dump(cache, f, ensure_ascii=False, indent=2)


def clave_temporada_cache(temporada: int) -> str:
  return (
      "players_by_team" if temporada == 2024 else f"players_by_team_{temporada}"
  )


def api_get(endpoint: str, params: dict) -> dict:
  global requests_made
  for intento in range(3):
    if requests_made >= MAX_REQUESTS_RUN:
      raise RuntimeError(
          f"Límite de sesión alcanzado ({MAX_REQUESTS_RUN} peticiones)."
      )

    resp = requests.get(
        f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=20
    )
    requests_made += 1
    data = resp.json()
    errors = data.get("errors") or {}

    if "rateLimit" in errors:
      espera = 20 * (intento + 1)
      print(
          f"  [Rate limit en {endpoint} {params}]: esperando {espera}s"
          f" (intento {intento + 1}/3)..."
      )
      time.sleep(espera)
      continue

    if "requests" in str(errors).lower():
      raise RuntimeError("Cuota diaria de API-Football agotada.")

    if errors:
      print(f"  [Aviso API en {endpoint} {params}]: {errors}")

    time.sleep(PAUSA_SEGUNDOS)
    return data

  return {"response": [], "errors": {"rateLimit": "Persistente"}}


def obtener_team_id(seleccion_es: str, cache: dict) -> int | None:
  if cache["teams"].get(seleccion_es) is not None:
    return cache["teams"][seleccion_es]

  nombre_en = SELECCIONES_EN.get(seleccion_es, seleccion_es)
  data = api_get("teams", {"name": nombre_en})
  if "rateLimit" in (data.get("errors") or {}):
    return None

  resp = data.get("response", [])
  if not resp:
    data = api_get("teams", {"search": nombre_en})
    if "rateLimit" in (data.get("errors") or {}):
      return None
    resp = data.get("response", [])

  team_id = None
  for item in resp:
    if item.get("team", {}).get("national") is True:
      team_id = item["team"]["id"]
      break
  if team_id is None and resp:
    team_id = resp[0]["team"]["id"]

  if team_id is not None:
    cache["teams"][seleccion_es] = team_id
    guardar_cache(cache)
  return team_id


def coinciden_nombres(nombre_excel: str, player_api: dict) -> bool:
  ex_norm = normalizar(nombre_excel)
  ex_tokens = ex_norm.split()
  if not ex_tokens:
    return False

  full_api = normalizar(
      f"{player_api.get('firstname', '')} {player_api.get('lastname', '')}"
  )
  short_api = normalizar(player_api.get("name", ""))

  if ex_norm == full_api or ex_norm == short_api:
    return True

  api_tokens = set(full_api.split())
  if len(ex_tokens) >= 2 and all(t in api_tokens for t in ex_tokens):
    return True

  if len(ex_tokens) >= 2 and ex_tokens[-1] in api_tokens:
    if full_api.startswith(ex_tokens[0][0]) or short_api.startswith(
        ex_tokens[0][0]
    ):
      return True

  return False


def coinciden_nombres_flexible(nombre_excel: str, player_api: dict) -> bool:
  if coinciden_nombres(nombre_excel, player_api):
    return True

  ex_norm = normalizar(nombre_excel)
  ex_tokens = ex_norm.split()
  if not ex_tokens:
    return False

  full_api = normalizar(
      f"{player_api.get('firstname', '')} {player_api.get('lastname', '')}"
  )
  short_api = normalizar(player_api.get("name", ""))
  candidatos = [c for c in [full_api, short_api] if c]

  apellido = ex_tokens[-1]
  for cand in candidatos:
    cand_tokens = set(cand.split())
    if apellido in cand_tokens and len(apellido) >= 4:
      if any(t in cand_tokens for t in ex_tokens[:-1] if len(t) >= 3):
        return True
      if SequenceMatcher(None, ex_norm, cand).ratio() >= 0.65:
        return True

  return False


def buscar_datos_jugador(nombre_excel: str, lista_players_api: list) -> tuple:
  for p in lista_players_api:
    if coinciden_nombres_flexible(nombre_excel, p):
      fecha = (p.get("birth") or {}).get("date") or "No disponible"
      altura = p.get("height") or "No disponible"
      peso = p.get("weight") or "No disponible"
      return fecha, altura, peso
  return "No disponible", "No disponible", "No disponible"


def descargar_temporada(
    df: pd.DataFrame, cache: dict, temporada: int, solo_huecos: bool = False
) -> None:
  clave_cache = clave_temporada_cache(temporada)
  cache.setdefault(clave_cache, {})

  selecciones = df["seleccion_nacional"].dropna().unique().tolist()
  if solo_huecos:
    pendientes = []
    for sel in selecciones:
      faltan = (
          df[df["seleccion_nacional"] == sel]["fecha_nacimiento"]
          == "No disponible"
      ).sum()
      if faltan > 0:
        pendientes.append((faltan, sel))
    pendientes.sort(reverse=True)
    selecciones_iter = [sel for _, sel in pendientes]
  else:
    selecciones_iter = selecciones

  for sel in selecciones_iter:
    jugadores_sel = df[df["seleccion_nacional"] == sel][
        "nombre_jugador"
    ].tolist()
    team_id = obtener_team_id(sel, cache)
    if not team_id:
      print(f"[!] No se encontró team_id para {sel}")
      continue

    str_id = str(team_id)
    entry = cache[clave_cache].setdefault(
        str_id, {"players": [], "pages_fetched": 0, "total_pages": MAX_PAGE_FREE}
    )
    max_pages_permitidas = min(
        entry.get("total_pages", MAX_PAGE_FREE), MAX_PAGE_FREE
    )

    while entry["pages_fetched"] < max_pages_permitidas:
      encontrados = sum(
          1
          for j in jugadores_sel
          if buscar_datos_jugador(j, entry["players"])[0] != "No disponible"
      )
      if encontrados == len(jugadores_sel):
        break

      next_page = entry["pages_fetched"] + 1
      data = api_get(
          "players", {"team": team_id, "season": temporada, "page": next_page}
      )
      errors = data.get("errors") or {}

      if "rateLimit" in errors:
        break
      if errors:
        entry["pages_fetched"] = max_pages_permitidas
        guardar_cache(cache)
        break

      paging = data.get("paging", {})
      entry["total_pages"] = min(
          paging.get("total", MAX_PAGE_FREE), MAX_PAGE_FREE
      )
      max_pages_permitidas = entry["total_pages"]
      entry["pages_fetched"] = next_page

      for item in data.get("response", []):
        entry["players"].append(item["player"])
      guardar_cache(cache)


def consolidar_desde_cache(
    df: pd.DataFrame, cache: dict, temporadas: list[int] = TEMPORADAS_ORDEN
) -> pd.DataFrame:
  claves_temporadas = [clave_temporada_cache(t) for t in temporadas]
  fechas, alturas, pesos = [], [], []

  for _, row in df.iterrows():
    sel = row["seleccion_nacional"]
    nombre = row["nombre_jugador"]
    tid = cache.get("teams", {}).get(sel)

    f_final, a_final, p_final = "No disponible", "No disponible", "No disponible"
    if tid is not None:
      str_id = str(tid)
      for clave in claves_temporadas:
        lista_p = cache.get(clave, {}).get(str_id, {}).get("players", [])
        f_nac, alt, pes = buscar_datos_jugador(nombre, lista_p)
        if f_final == "No disponible" and f_nac != "No disponible":
          f_final = f_nac
        if a_final == "No disponible" and alt != "No disponible":
          a_final = alt
        if p_final == "No disponible" and pes != "No disponible":
          p_final = pes
        if (
            f_final != "No disponible"
            and a_final != "No disponible"
            and p_final != "No disponible"
        ):
          break

    fechas.append(f_final)
    alturas.append(a_final)
    pesos.append(p_final)

  df = df.copy()
  df["fecha_nacimiento"] = fechas
  df["altura_jugador"] = alturas
  df["peso_jugador"] = pesos
  return df


def main():
  df = pd.read_excel(EXCEL_ENTRADA)
  cache = cargar_cache()
  cache.setdefault("teams", {})["México"] = 16

  print(
      f"Total selecciones: {df['seleccion_nacional'].nunique()} | Total"
      f" jugadores: {len(df)}"
  )

  # Consolidación inicial desde caché (0 peticiones)
  df = consolidar_desde_cache(df, cache, TEMPORADAS_ORDEN)

  if MAX_REQUESTS_RUN > 0:
    try:
      for temp in TEMPORADAS_ORDEN:
        descargar_temporada(
            df, cache, temporada=temp, solo_huecos=(temp != 2024)
        )
        df = consolidar_desde_cache(df, cache, TEMPORADAS_ORDEN)
    except RuntimeError as e:
      print(f"\n[Pausa controlada]: {e}")
      print("Progreso guardado en data/cache_api_football.json.")
      df = consolidar_desde_cache(df, cache, TEMPORADAS_ORDEN)

  df.to_excel(EXCEL_SALIDA, index=False)
  print(f"\nArchivo guardado en: {EXCEL_SALIDA}")
  print(
      "Resumen fecha_nacimiento disponibles:",
      (df["fecha_nacimiento"] != "No disponible").sum(),
      "/",
      len(df),
  )
  print(
      "Resumen altura_jugador disponibles:",
      (df["altura_jugador"] != "No disponible").sum(),
      "/",
      len(df),
  )
  print(
      "Resumen peso_jugador disponibles:",
      (df["peso_jugador"] != "No disponible").sum(),
      "/",
      len(df),
  )
  print(f"Peticiones usadas en esta sesión: {requests_made}/{MAX_REQUESTS_RUN}")


if __name__ == "__main__":
  main()