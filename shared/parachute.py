from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.parse
import urllib.request
import time
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
import unicodedata
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def agent_model():
    """Devuelve el modelo configurado: Groq compatible si hay una clave gsk_, o el default de OpenAI."""
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not groq_key and openai_key.startswith("gsk_"):
        groq_key = openai_key
    if groq_key:
        from agents import OpenAIChatCompletionsModel, set_tracing_disabled
        from openai import AsyncOpenAI
        set_tracing_disabled(True)
        client = AsyncOpenAI(
            api_key=groq_key,
            base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        )
        model_name = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        # Este es el modelo Groq disponible en el entorno HDT4; ocultamos su razonamiento
        # para que no se mezcle con los nombres de herramientas del Agents SDK.
        if model_name in {"llama-3.3-70b-versatile", "qwen/qwen3.6-27b", "qwen/qwen3.8-27b"}:
            model_name = "openai/gpt-oss-20b"
        return OpenAIChatCompletionsModel(
            model=model_name,
            openai_client=client,
        )
    return None


def agent_model_settings():
    from agents import ModelSettings
    if os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY", "").startswith("gsk_"):
        return ModelSettings(extra_body={"include_reasoning": False})
    return None

LATITUDE = 14.013722
LONGITUDE = -90.771611
MAX_FORECAST_DAYS = 16


@dataclass
class WeatherReport:
    date: str
    temperature_c: float | None
    precipitation_mm: float | None
    cloud_cover_pct: float | None
    visibility_m: float | None
    wind_speed_kmh: float | None
    wind_gust_kmh: float | None
    decision: str
    reasons: list[str]


def validate_date(date_text: str, today: dt.date | None = None) -> dt.date:
    try:
        requested = dt.date.fromisoformat(date_text)
    except ValueError as exc:
        raise ValueError("La fecha debe tener el formato YYYY-MM-DD.") from exc
    today = today or dt.date.today()
    if requested < today:
        raise ValueError("No se pueden calendarizar citas en una fecha pasada.")
    # Los 16 días de Open-Meteo incluyen el día actual: el último día es hoy + 15.
    if requested >= today + dt.timedelta(days=MAX_FORECAST_DAYS):
        raise ValueError("Open-Meteo solo permite consultar los próximos 16 días, contando hoy.")
    return requested


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def fetch_weather(date_text: str) -> WeatherReport:
    requested = validate_date(date_text)
    params = urllib.parse.urlencode({
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "daily": "temperature_2m_mean,precipitation_sum,cloud_cover_mean,visibility_mean,wind_speed_10m_max,wind_gusts_10m_max",
        "timezone": "America/Guatemala",
        "start_date": requested.isoformat(),
        "end_date": requested.isoformat(),
    })
    url = "https://api.open-meteo.com/v1/forecast?" + params
    request = urllib.request.Request(url, headers={"User-Agent": "HDT5-Parachute/1.0"})
    last_error = None
    payload = None
    # Preferimos curl porque es la misma ruta que el usuario verificó manualmente.
    if shutil.which("curl"):
        for attempt in range(3):
            result = subprocess.run(
                ["curl", "--ipv4", "--fail", "--silent", "--show-error", "--max-time", "15", url],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if result.returncode == 0:
                payload = json.loads(result.stdout)
                break
            last_error = RuntimeError(result.stderr.strip() or "curl no pudo consultar Open-Meteo")
            if attempt < 2:
                time.sleep(1)
    if payload is None:
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    payload = json.load(response)
                break
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1)
    if payload is None:
        raise last_error or RuntimeError("No se pudo consultar Open-Meteo.")
    daily = payload.get("daily", {})
    temps = [x for x in daily.get("temperature_2m_mean", []) if x is not None]
    precip = [x for x in daily.get("precipitation_sum", []) if x is not None]
    clouds = [x for x in daily.get("cloud_cover_mean", []) if x is not None]
    visibility = [x for x in daily.get("visibility_mean", []) if x is not None]
    winds = [x for x in daily.get("wind_speed_10m_max", []) if x is not None]
    gusts = [x for x in daily.get("wind_gusts_10m_max", []) if x is not None]
    report = WeatherReport(
        date=date_text,
        temperature_c=_mean(temps),
        precipitation_mm=round(sum(precip), 2) if precip else None,
        cloud_cover_pct=round(max(clouds), 2) if clouds else None,
        visibility_m=round(min(visibility), 2) if visibility else None,
        wind_speed_kmh=round(max(winds), 2) if winds else None,
        wind_gust_kmh=round(max(gusts), 2) if gusts else None,
        decision="",
        reasons=[],
    )
    return evaluate_weather(report)


def evaluate_weather(report: WeatherReport) -> WeatherReport:
    reasons: list[str] = []
    unsafe = False
    marginal = False
    if report.wind_speed_kmh is None or report.wind_gust_kmh is None or report.precipitation_mm is None or report.cloud_cover_pct is None:
        unsafe, reasons = True, ["Faltan datos meteorológicos para autorizar el salto."]
    else:
        if report.wind_speed_kmh > 28:
            unsafe, reasons = True, reasons + ["Viento superficial superior a 28 km/h."]
        elif report.wind_speed_kmh >= 20:
            marginal, reasons = True, reasons + ["Viento superficial marginal (20–28 km/h): solo tándem experimentado."]
        if report.wind_gust_kmh > 35:
            unsafe, reasons = True, reasons + ["Ráfagas superiores a 35 km/h."]
        if report.precipitation_mm > 0:
            unsafe, reasons = True, reasons + ["Existe precipitación."]
        if report.cloud_cover_pct > 75:
            unsafe, reasons = True, reasons + ["Cobertura de nubes superior a 75%."]
        elif report.cloud_cover_pct >= 30:
            marginal, reasons = True, reasons + ["Cobertura marginal (30–75%)."]
    report.decision = "NO SEGURO / PROHIBIDO" if unsafe else ("MARGINAL" if marginal else "IDEAL")
    report.reasons = reasons or ["Condiciones dentro del rango ideal definido por Parachute S.A."]
    return report


def weather_tool(date: str) -> str:
    """Consulta Open-Meteo y evalúa si la fecha es apta para saltar. Recibe YYYY-MM-DD."""
    try:
        return json.dumps(asdict(fetch_weather(date)), ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def schedule_tool(date: str) -> str:
    """Consulta nuevamente Open-Meteo y calendariza solo si el clima real es IDEAL o MARGINAL."""
    try:
        validate_date(date)
        # Nunca se confía en un reporte generado por el LLM: la calendarización
        # ejecuta su propia consulta de clima como última barrera de seguridad.
        report = fetch_weather(date)
        decision = report.decision
        if decision not in {"IDEAL", "MARGINAL"}:
            return json.dumps({"scheduled": False, "error": "La cita no puede calendarizarse: condiciones NO SEGURO / PROHIBIDO o reporte inválido."}, ensure_ascii=False)
        APPOINTMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        appointments = json.loads(APPOINTMENTS_PATH.read_text(encoding="utf-8")) if APPOINTMENTS_PATH.exists() else []
        appointment = {"date": date, "decision": decision, "status": "pending_instructor_confirmation", "weather": asdict(report)}
        appointments.append(appointment)
        APPOINTMENTS_PATH.write_text(json.dumps(appointments, ensure_ascii=False, indent=2), encoding="utf-8")
        return json.dumps({"scheduled": True, **appointment, "message": "Cita calendarizada tentativamente; el instructor debe confirmar la operación."}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"scheduled": False, "error": str(exc)}, ensure_ascii=False)


FAQ_PATH = Path(__file__).resolve().parents[2] / "ai-function-calls" / "data" / "Corpus_FAQs_Parachute_SA_2026.txt"
APPOINTMENTS_PATH = Path(__file__).resolve().parents[1] / "data" / "citas.json"

def _normalize(text: str) -> set[str]:
    text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return set(re.findall(r"[a-z0-9]{3,}", text))

def faq_tool(question: str) -> str:
    """Busca la pregunta más parecida en el corpus FAQ de HDT4, sin inventar respuestas."""
    if not FAQ_PATH.exists():
        return "No está disponible el corpus FAQ de HDT4."
    query_words = _normalize(question)
    blocks = [b for b in FAQ_PATH.read_text(encoding="utf-8").split("------------------------------------------------------------") if "PREGUNTA:" in b]
    best, score = None, 0
    for block in blocks:
        question_match = re.search(r"PREGUNTA:\s*(.+)", block)
        answer_match = re.search(r"RESPUESTA:\s*(.+)", block)
        if question_match and answer_match:
            current = len(query_words & _normalize(question_match.group(1)))
            if current > score:
                score, best = current, answer_match.group(1).strip()
    return best if best and score else "No encontré esa respuesta en el corpus FAQ de HDT4. Puedo ayudar a revisar clima y calendarización si indica una fecha YYYY-MM-DD."


def extract_date(text: str) -> str | None:
    match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    return match.group(1) if match else None


def run_agent(agent, user_text: str) -> str:
    from agents import Runner
    try:
        output = Runner.run_sync(agent, user_text).final_output or ""
        date = extract_date(user_text)
        is_calendar = date and any(word in user_text.lower() for word in ("cita", "calendar", "agendar", "reservar"))
        if is_calendar:
            # Postcondición de seguridad: el texto del LLM nunca puede contradecir
            # el clima real consultado por la integración compartida.
            report = fetch_weather(date)
            metrics = (f"Temperatura: {report.temperature_c} °C; precipitación: {report.precipitation_mm} mm; "
                       f"nubes: {report.cloud_cover_pct}%; visibilidad: {report.visibility_m} m; "
                       f"viento: {report.wind_speed_kmh} km/h; ráfagas: {report.wind_gust_kmh} km/h.")
            if report.decision == "NO SEGURO / PROHIBIDO":
                return f"Decisión: NO SEGURO / PROHIBIDO.\n{metrics}\nLa cita no fue calendarizada. Razones: {' '.join(report.reasons)}"
            if not output.strip() or "no puedo" in output.lower() or "no dispongo" in output.lower():
                result = json.loads(schedule_tool(date, json.dumps(asdict(report), ensure_ascii=False)))
                return f"{metrics}\n{result.get('message', 'Resultado de calendarización.') if result.get('scheduled') else result.get('error')}"
        return output
    except Exception as exc:
        return f"No se pudo completar la solicitud. Verifica el modelo y la conexión del proveedor: {exc}"
