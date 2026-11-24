from difflib import SequenceMatcher  
import json  
import os  
import time  
import unicodedata  
from dotenv import load_dotenv  
import pandas as pd 
import requests  
import matplotlib.pyplot as plt


load_dotenv() #carga las variables definidas en el archivo .env (si existe)

API_KEY = os.getenv("API_FOOTBALL_KEY") #recupera la clave de API-Football desde las variables de entorno
if not API_KEY:
    raise ValueError("No se encontró API_FOOTBALL_KEY en el archivo .env") #si falta la clave, detenemos el script con un error claro

BASE_URL = "https://v3.football.api-sports.io" 
HEADERS = {"x-apisports-key": API_KEY} #URL base de la version 3 de API-Football y cabecera de autenticacion

EXCEL_ENTRADA = "data/jugadoresWC2026.xlsx"
EXCEL_SALIDA = "data/jugadoresWC2026_enriquecido.xlsx"
CACHE_PATH = "data/cache_api_football.json" #rutas de entrada, salida y cache para no repetir llamadas ya hechas

MAX_REQUESTS_RUN = 0 #0 = solo usar datos ya guardados en cache (no gasta peticiones de la API), se puede aumentar dependiendo de las llamadas y de la ejecucion
PAUSA_SEGUNDOS = 6  #segundos de espera tras cada llamada para respetar limites
MAX_PAGE_FREE = 3  # maximo de paginas por seleccion/temporada en plan gratuito
TEMPORADAS_ORDEN = [
    2024,
    2023,
    2022,
]  #prioridad de temporadas (2024 primero)
requests_made = 0  #contador de peticiones hechas en esta ejecucion

#traduccion de nombres de selecciones en español al nombre habitual en ingles en la API
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
    """pasa a minusculas, quita tildes y colapsa espacios"""
    if not isinstance(texto, str):
        return ""
    #descompone caracteres con tilde y elimina las tildes 
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return " ".join(texto.lower().strip().split())


def cargar_cache() -> dict:
    """carga la cache local desde JSON si existe; si no, crea una estructura vacia"""
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"teams": {}, "players_by_team": {}}


def guardar_cache(cache: dict) -> None:
    """guarda el diccionario de cache en disco para reutilizarlo en futuras ejecuciones"""
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def clave_temporada_cache(temporada: int) -> str:
    """devuelve la clave de cache correspondiente a cada temporada"""
    return (
        "players_by_team" if temporada == 2024 else f"players_by_team_{temporada}"
    ) #2024 usa 'players_by_team' por compatibilidad con la caché inicial


def api_get(endpoint: str, params: dict) -> dict:
    """realiza una peticion GET a la API controlando el limite de sesion y errores"""
    global requests_made
    for intento in range(3):
        #comprueba que no superemos el limite configurado para esta ejecucion
        if requests_made >= MAX_REQUESTS_RUN:
            raise RuntimeError(
                f"Limite de sesion alcanzado ({MAX_REQUESTS_RUN} peticiones)"
            )

        resp = requests.get(
            f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=20
        )
        requests_made += 1
        data = resp.json()
        errors = data.get("errors") or {}

        #si la API pide frenar por rafaga (rateLimit), espera de forma progresiva y reintenta
        if "rateLimit" in errors:
            espera = 20 * (intento + 1)
            print(
                f"  [Rate limit en {endpoint} {params}]: esperando {espera}s"
                f" (intento {intento + 1}/3)..."
            )
            time.sleep(espera)
            continue

        #si se acabo la cuota diaria de peticiones, abortamos limpiamente
        if "requests" in str(errors).lower():
            raise RuntimeError("Cuota diaria de API-Football agotada.")

        if errors:
            print(f"  [Aviso API en {endpoint} {params}]: {errors}")

        #pausa de cortesia entre peticiones exitosas
        time.sleep(PAUSA_SEGUNDOS)
        return data

    return {"response": [], "errors": {"rateLimit": "Persistente"}}


def obtener_team_id(seleccion_es: str, cache: dict) -> int | None:
    """obtiene el ID de la seleccion en API-Football (usando cache o consultando /teams)"""
    if cache["teams"].get(seleccion_es) is not None:
        return cache["teams"][seleccion_es]

    nombre_en = SELECCIONES_EN.get(seleccion_es, seleccion_es)
    data = api_get("teams", {"name": nombre_en})
    if "rateLimit" in (data.get("errors") or {}):
        return None

    resp = data.get("response", [])
    #si la busqueda exacta por nombre no devuelve nada, probamos busqueda parcial
    if not resp:
        data = api_get("teams", {"search": nombre_en})
        if "rateLimit" in (data.get("errors") or {}):
            return None
        resp = data.get("response", [])

    #preferimos explicitamente el equipo nacional (seleccion absoluta)
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
    """comprueba coincidencia directa o por inicial + apellido entre Excel y API"""
    ex_norm = normalizar(nombre_excel)
    ex_tokens = ex_norm.split()
    if not ex_tokens:
        return False

    full_api = normalizar(
        f"{player_api.get('firstname', '')} {player_api.get('lastname', '')}"
    )
    short_api = normalizar(player_api.get("name", ""))

    #coincidencia exacta con nombre completo o nombre corto ("apodo" futbolistico)
    if ex_norm == full_api or ex_norm == short_api:
        return True

    #todas las palabras del nombre del Excel aparecen en el nombre completo de la API
    api_tokens = set(full_api.split())
    if len(ex_tokens) >= 2 and all(t in api_tokens for t in ex_tokens):
        return True

    #mismo apellido y misma inicial del primer nombre
    if len(ex_tokens) >= 2 and ex_tokens[-1] in api_tokens:
        if full_api.startswith(ex_tokens[0][0]) or short_api.startswith(
            ex_tokens[0][0]
        ):
            return True

    return False


def coinciden_nombres_flexible(nombre_excel: str, player_api: dict) -> bool:
    """amplia la busqueda con reglas flexibles (apellido + nombre parcial o similitud)"""
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
        #exige apellido de al menos 4 letras para evitar falsos positivos cortos
        if apellido in cand_tokens and len(apellido) >= 4:
            if any(t in cand_tokens for t in ex_tokens[:-1] if len(t) >= 3):
                return True
            if SequenceMatcher(None, ex_norm, cand).ratio() >= 0.65:
                return True

    return False


def buscar_datos_jugador(nombre_excel: str, lista_players_api: list) -> tuple:
    """busca un jugador en una lista de la API y devuelve (fecha, altura, peso)"""
    for p in lista_players_api:
        if coinciden_nombres_flexible(nombre_excel, p):
            fecha = (p.get("birth") or {}).get("date") or "No disponible"
            altura = p.get("height") or "No disponible"
            peso = p.get("weight") or "No disponible"
            return fecha, altura, peso
    #si no se encuentra o faltan datos, se indica explicitamente como No disponible
    return "No disponible", "No disponible", "No disponible"
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
    """descarga paginas de jugadores de una temporada y las guarda en cache"""
    clave_cache = clave_temporada_cache(temporada)
    cache.setdefault(clave_cache, {})

    selecciones = df["seleccion_nacional"].dropna().unique().tolist()
    if solo_huecos:
        #prioriza primero las selecciones con mas fechas de nacimiento sin cubrir
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
            str_id,
            {"players": [], "pages_fetched": 0, "total_pages": MAX_PAGE_FREE},
        )
        max_pages_permitidas = min(
            entry.get("total_pages", MAX_PAGE_FREE), MAX_PAGE_FREE
        )

        #pide paginas mientras queden paginas permitidas y no hayamos encontrado a todos
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
                "players",
                {"team": team_id, "season": temporada, "page": next_page},
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
    """rellena fecha_nacimiento, altura_jugador y peso_jugador usando la cache"""
    claves_temporadas = [clave_temporada_cache(t) for t in temporadas]
    fechas, alturas, pesos = [], [], []

    for _, row in df.iterrows():
        sel = row["seleccion_nacional"]
        nombre = row["nombre_jugador"]
        tid = cache.get("teams", {}).get(sel)

        f_final, a_final, p_final = (
            "No disponible",
            "No disponible",
            "No disponible",
        )
        if tid is not None:
            str_id = str(tid)
            #revisa las temporadas en orden (2024 -> 2023 -> 2022) solo para lo que falte
            for clave in claves_temporadas:
                lista_p = cache.get(clave, {}).get(str_id, {}).get("players", [])
                f_nac, alt, pes = buscar_datos_jugador(nombre, lista_p)
                if f_final == "No disponible" and f_nac != "No disponible":
                    f_final = f_nac
                if a_final == "No disponible" and alt != "No disponible":
                    a_final = alt
                if p_final == "No disponible" and pes != "No disponible":
                    p_final = pes
                #si ya tenemos los 3 datos del jugador, no hace falta seguir buscando
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


def analizar_y_graficar_nacimientos(
    df: pd.DataFrame, ruta_grafico: str = "outputs/distribucion_nacimientos.png"
) -> None:
    """analiza la distribucion por mes y trimestre de nacimiento y guarda un grafico."""
    #filtramos solo las filas con fecha disponible y las convertimos a tipo fecha de pandas
    fechas_validas = pd.to_datetime(
        df.loc[df["fecha_nacimiento"] != "No disponible", "fecha_nacimiento"],
        errors="coerce",
    ).dropna()

    total_validos = len(fechas_validas)
    if total_validos == 0:
        print(
            "[!] No hay fechas de nacimiento válidas para analizar."
        )
        return

    #extraemos el mes (1-12) y el trimestre (1-4)
    meses = fechas_validas.dt.month
    conteo_meses = meses.value_counts().reindex(range(1, 13), fill_value=0)

    trimestres = fechas_validas.dt.quarter
    conteo_trimestres = trimestres.value_counts().reindex(
        range(1, 5), fill_value=0
    )

    nombres_meses = [
        "Ene",
        "Feb",
        "Mar",
        "Abr",
        "May",
        "Jun",
        "Jul",
        "Ago",
        "Sep",
        "Oct",
        "Nov",
        "Dic",
    ]
    media_mensual = total_validos / 12.0

    print(
        f"\n--- Análisis de fechas de nacimiento (n = {total_validos}) ---"
    )
    for m in range(1, 13):
        n_m = int(conteo_meses.loc[m])
        pct_m = (n_m / total_validos) * 100
        print(
            f"  {nombres_meses[m - 1]}: {n_m} jugadores ({pct_m:.1f}%)"
        )

    print("\nPor trimestres:")
    etiquetas_t = {
        1: "T1 (Ene-Mar)",
        2: "T2 (Abr-Jun)",
        3: "T3 (Jul-Sep)",
        4: "T4 (Oct-Dic)",
    }
    for t in range(1, 5):
        n_t = int(conteo_trimestres.loc[t])
        pct_t = (n_t / total_validos) * 100
        print(f"  {etiquetas_t[t]}: {n_t} jugadores ({pct_t:.1f}%)")

    #creamos una figura con dos subgraficos: por mes y por trimestre
    os.makedirs(os.path.dirname(ruta_grafico), exist_ok=True)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.6))

    #grafico por mes
    ax1.bar(
        nombres_meses,
        conteo_meses.values,
        color="#2b6cb0",
        edgecolor="black",
        alpha=0.85,
    )
    ax1.axhline(
        media_mensual,
        color="#c53030",
        linestyle="--",
        linewidth=1.5,
        label=f"Media uniforme ({media_mensual:.1f})",
    )
    ax1.set_title("Jugadores por mes de nacimiento")
    ax1.set_xlabel("Mes")
    ax1.set_ylabel("Número de jugadores")
    ax1.tick_params(axis="x", rotation=35)
    ax1.legend()
    ax1.grid(axis="y", linestyle=":", alpha=0.5)

    #grafico por trimestre para ver el efecto de la edad relativa
    etiquetas_barras_t = [etiquetas_t[t] for t in range(1, 5)]
    ax2.bar(
        etiquetas_barras_t,
        conteo_trimestres.values,
        color="#2f855a",
        edgecolor="black",
        alpha=0.85,
    )
    ax2.axhline(
        total_validos / 4.0,
        color="#c53030",
        linestyle="--",
        linewidth=1.5,
        label=f"Media trimestral ({total_validos / 4.0:.1f})",
    )
    ax2.set_title("Distribución por trimestre (Edad relativa)")
    ax2.set_xlabel("Trimestre")
    ax2.set_ylabel("Número de jugadores")
    ax2.legend()
    ax2.grid(axis="y", linestyle=":", alpha=0.5)

    fig.suptitle(
        f"Distribución de fechas de nacimiento (n = {total_validos} jugadores)",
        fontsize=13,
        fontweight="bold",
    )

    conclusion = (
        "conclusion: se aprecia efecto de la edad relativa - T1 y T2 superan la"
        " media trimestral (224.2),\nmientras T4 cae por debajo (~160) y"
        " Oct-Dic son los meses con menos jugadores (muestra n = 897/1248)."
    )
    fig.text(
        0.5,
        0.02,
        conclusion,
        ha="center",
        va="bottom",
        fontsize=9.5,
        style="italic",
        color="#2d3748",
    )

    #dejamos margen abajo (0.12) para que el texto no se solape con los ejes
    plt.tight_layout(rect=[0, 0.12, 1, 0.94])
    plt.savefig(ruta_grafico, dpi=200)
    plt.close(fig)



RUTA_PARTIDOS_WC26 = "data/partidosWC26.xlsx"
RUTA_CACHE_NOMINATIM = "data/cache_nominatim_estadios.json"
RUTA_EXCEL_ESTADIOS = "data/estadiosWC26_geocodificados.xlsx"
HEADERS_NOMINATIM = {
    "User-Agent": (
        "Mundial2026Proyecto-ICAI/1.0"
        " (https://github.com/yagovfc/mundial-2026-proyecto)"
    )
}

CONSULTAS_RESPALDO_ESTADIOS = {
    "estadio bbva, monterrey, mexico": [
        "Estadio BBVA, Guadalupe, Nuevo Leon, Mexico",
        "Estadio de Futbol Monterrey, Guadalupe, Mexico",
        "Monterrey, Nuevo Leon, Mexico",
    ],
    "estadio akron, guadalajara, mexico": [
        "Estadio Akron, Zapopan, Jalisco, Mexico",
        "Estadio Chivas, Zapopan, Jalisco, Mexico",
        "Guadalajara, Jalisco, Mexico",
    ],
}


def _consultar_nominatim_segura(query: str) -> dict | None:
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": query, "format": "json", "limit": 1},
        headers=HEADERS_NOMINATIM,
        timeout=15,
    )
    resp.raise_for_status()
    datos = resp.json()
    if datos:
        return {
            "lat": float(datos[0]["lat"]),
            "lon": float(datos[0]["lon"]),
            "display_name": datos[0].get("display_name", query),
            "query_usada": query,
        }
    return None


def geocodificar_estadios_wc26(
    ruta_partidos: str = RUTA_PARTIDOS_WC26,
    ruta_cache: str = RUTA_CACHE_NOMINATIM,
    ruta_salida: str = RUTA_EXCEL_ESTADIOS,
) -> pd.DataFrame:
    """lee estadios de partidosWC26.xlsx, geocodifica con Nominatim + cache y guarda Excel."""
    df_partidos = pd.read_excel(ruta_partidos)

    cache = {}
    if os.path.exists(ruta_cache):
        with open(ruta_cache, "r", encoding="utf-8") as f:
            cache = json.load(f)

    estadios_unicos = (
        df_partidos[["estadio", "ciudad_partido", "pais_partido"]]
        .dropna(subset=["estadio"])
        .drop_duplicates(subset=["estadio"])
        .reset_index(drop=True)
    )

    filas = []
    consultas_nuevas = 0

    for _, row in estadios_unicos.iterrows():
        estadio = str(row["estadio"]).strip()
        ciudad = (
            str(row["ciudad_partido"]).strip()
            if pd.notna(row["ciudad_partido"])
            else ""
        )
        pais = (
            str(row["pais_partido"]).strip()
            if pd.notna(row["pais_partido"])
            else ""
        )

        consulta_base = ", ".join(p for p in (estadio, ciudad, pais) if p)
        clave = consulta_base.lower()

        cached_entry = cache.get(clave)
        tiene_coords_validas = (
            isinstance(cached_entry, dict)
            and cached_entry.get("lat") is not None
            and cached_entry.get("lon") is not None
        )

        if tiene_coords_validas:
            entry = cached_entry
        else:
            candidatos = [consulta_base] + CONSULTAS_RESPALDO_ESTADIOS.get(
                clave, []
            )
            if ciudad and pais:
                candidatos.append(f"{ciudad}, {pais}")

            entry = {
                "lat": None,
                "lon": None,
                "display_name": "No disponible",
                "query_usada": consulta_base,
            }
            for q in candidatos:
                try:
                    res = _consultar_nominatim_segura(q)
                    consultas_nuevas += 1
                    time.sleep(1.1)
                    if res is not None:
                        entry = res
                        break
                except Exception as exc:
                    print(f"[!] Error en Nominatim para '{q}': {exc}")
                    time.sleep(1.1)

            cache[clave] = entry
            os.makedirs(os.path.dirname(ruta_cache), exist_ok=True)
            with open(ruta_cache, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)

        filas.append({
            "estadio": estadio,
            "ciudad_partido": ciudad,
            "pais_partido": pais,
            "latitud": entry.get("lat"),
            "longitud": entry.get("lon"),
            "osm_nombre": entry.get("display_name", "No disponible"),
        })

    df_estadios = pd.DataFrame(filas)
    os.makedirs(os.path.dirname(ruta_salida), exist_ok=True)
    df_estadios.to_excel(ruta_salida, index=False)

    validos = df_estadios.dropna(subset=["latitud", "longitud"])
    print(
        f"Estadios geocodificados: {len(validos)}/{len(df_estadios)} "
        f"(consultas nuevas: {consultas_nuevas}) -> {ruta_salida}"
    )
    return df_estadios


import plotly.express as px
import streamlit as st
from streamlit.runtime import exists as streamlit_runtime_exists


def ejecutar_dashboard_streamlit():
    """Dashboard interactivo de estadios del Mundial 2026 con Streamlit y Plotly."""
    st.set_page_config(
        page_title="Mundial 2026 - Estadios", layout="wide"
    )
    st.title("Mundial 2026 — Estadios en Norteamérica")
    st.caption(
        "Tamaño de burbuja = partidos jugados | Color = goles marcados"
    )

    df_partidos = pd.read_excel(RUTA_PARTIDOS_WC26)
    df_eventos = (
        pd.read_excel("data/eventosWC26.xlsx")
        if os.path.exists("data/eventosWC26.xlsx")
        else pd.DataFrame()
    )

    # Asegura que existan coordenadas (y corrige BBVA / Akron si aún no estaban)
    if os.path.exists(RUTA_EXCEL_ESTADIOS):
        df_est = pd.read_excel(RUTA_EXCEL_ESTADIOS)
        if df_est["latitud"].isna().any() or df_est["longitud"].isna().any():
            df_est = geocodificar_estadios_wc26()
    else:
        df_est = geocodificar_estadios_wc26()

    # Calcular goles por partido desde eventosWC26.xlsx (con respaldo en marcadores)
    goles_por_id = {}
    if not df_eventos.empty and {"tipo_evento", "index_partido"}.issubset(
        df_eventos.columns
    ):
        goles_df = df_eventos[
            df_eventos["tipo_evento"].astype(str).str.strip().str.lower()
            == "gol"
        ]
        goles_por_id = goles_df.groupby("index_partido").size().to_dict()

    goles_lista = []
    for idx, fila in df_partidos.iterrows():
        if (idx + 1) in goles_por_id:
            goles_lista.append(int(goles_por_id[idx + 1]))
        elif idx in goles_por_id:
            goles_lista.append(int(goles_por_id[idx]))
        else:
            ml = pd.to_numeric(fila.get("marcador_local", 0), errors="coerce")
            mv = pd.to_numeric(
                fila.get("marcador_visitante", 0), errors="coerce"
            )
            goles_lista.append(
                int((0 if pd.isna(ml) else ml) + (0 if pd.isna(mv) else mv))
            )

    df_partidos = df_partidos.copy()
    df_partidos["goles_partido"] = goles_lista

    # Selector de ronda
    rondas = ["Todas"] + sorted(
        df_partidos["ronda"].dropna().astype(str).str.strip().unique().tolist()
    )
    ronda_sel = st.selectbox("Selecciona la ronda", rondas, index=0)

    if ronda_sel != "Todas":
        df_partidos = df_partidos[
            df_partidos["ronda"].astype(str).str.strip() == ronda_sel
        ]

    resumen = (
        df_partidos.groupby("estadio", as_index=False)
        .agg(
            partidos_jugados=("estadio", "count"),
            goles_marcados=("goles_partido", "sum"),
        )
        .merge(
            df_est[["estadio", "ciudad_partido", "pais_partido", "latitud", "longitud"]],
            on="estadio",
            how="left",
        )
        .dropna(subset=["latitud", "longitud"])
    )

    fig = px.scatter_geo(
        resumen,
        lat="latitud",
        lon="longitud",
        scope="north america",
        size="partidos_jugados",
        color="goles_marcados",
        hover_name="estadio",
        hover_data={
            "ciudad_partido": True,
            "pais_partido": True,
            "partidos_jugados": True,
            "goles_marcados": True,
            "latitud": ":.4f",
            "longitud": ":.4f",
        },
        size_max=35,
        color_continuous_scale="Viridis",
        title=f"Estadios del Mundial 2026 — Ronda: {ronda_sel}",
    )
    fig.update_layout(height=600)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(resumen, use_container_width=True, hide_index=True)



def main():
    """flujo principal: ejecuta dashboard en Streamlit o flujo batch en Python"""
    if streamlit_runtime_exists():
        ejecutar_dashboard_streamlit()
        return

    df = pd.read_excel(EXCEL_ENTRADA)
    cache = cargar_cache()
    cache.setdefault("teams", {})["México"] = 16  # ID verificado para mexico

    print(
        f"Total selecciones: {df['seleccion_nacional'].nunique()} | Total"
        f" jugadores: {len(df)}"
    )

    #consolida primero todo lo disponible en cache sin gastar cuota de API
    df = consolidar_desde_cache(df, cache, TEMPORADAS_ORDEN)

    #solo si MAX_REQUESTS_RUN > 0, intenta descargar datos adicionales
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

    #guarda el DataFrame enriquecido en Excel y muestra el resumen final
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
    print(
        f"Peticiones usadas en esta sesión: {requests_made}/{MAX_REQUESTS_RUN}"
    )

    analizar_y_graficar_nacimientos(df)
    geocodificar_estadios_wc26()


if __name__ == "__main__":
    main()
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
