import datetime as dt
import unittest
from pathlib import Path
from unittest.mock import patch
import shared.parachute as parachute
from shared.parachute import WeatherReport, evaluate_weather, schedule_tool, validate_date

def report(**kwargs):
    base = dict(date="2026-01-01", temperature_c=25, precipitation_mm=0, cloud_cover_pct=10, visibility_m=10000, wind_speed_kmh=10, wind_gust_kmh=20)
    base.update(kwargs)
    return WeatherReport(**base, decision="", reasons=[])

class ParachuteTests(unittest.TestCase):
  def test_ideal(self):
    self.assertEqual(evaluate_weather(report()).decision, "IDEAL")

  def test_marginal_wind(self):
    self.assertEqual(evaluate_weather(report(wind_speed_kmh=20)).decision, "MARGINAL")

  def test_unsafe_any_critical_threshold(self):
    self.assertEqual(evaluate_weather(report(wind_gust_kmh=35.1)).decision, "NO SEGURO / PROHIBIDO")
    self.assertEqual(evaluate_weather(report(precipitation_mm=0.01)).decision, "NO SEGURO / PROHIBIDO")
    self.assertEqual(evaluate_weather(report(wind_speed_kmh=28.01)).decision, "NO SEGURO / PROHIBIDO")
    self.assertEqual(evaluate_weather(report(cloud_cover_pct=75.01)).decision, "NO SEGURO / PROHIBIDO")

  def test_all_marginal_boundaries(self):
    self.assertEqual(evaluate_weather(report(wind_speed_kmh=20)).decision, "MARGINAL")
    self.assertEqual(evaluate_weather(report(wind_speed_kmh=28)).decision, "MARGINAL")
    self.assertEqual(evaluate_weather(report(cloud_cover_pct=30)).decision, "MARGINAL")
    self.assertEqual(evaluate_weather(report(cloud_cover_pct=75)).decision, "MARGINAL")

  def test_date_limit(self):
    today = dt.date(2026, 9, 16)
    self.assertEqual(validate_date("2026-09-20", today), dt.date(2026, 9, 20))
    self.assertEqual(validate_date("2026-10-01", today), dt.date(2026, 10, 1))
    with self.assertRaises(ValueError): validate_date("2026-10-02", today)
    with self.assertRaises(ValueError): validate_date("2026-10-03", today)
    with self.assertRaises(ValueError): validate_date("2026-09-15", today)
    with self.assertRaises(ValueError): validate_date("2026-99-99", today)

  def test_date_continuation_is_calendar_request(self):
    safe = evaluate_weather(report())
    with patch.object(parachute, "fetch_weather", return_value=safe), patch.object(
      parachute, "schedule_tool", return_value='{"scheduled": true, "message": "Cita calendarizada"}'
    ):
      answer = parachute._apply_calendar_guard("2026-09-17 quiero esa fecha", "No puedo responder esa pregunta")
    self.assertIn("Cita calendarizada", answer)

  def test_reservation_phrase_with_date_is_calendar_request(self):
    safe = evaluate_weather(report())
    with patch.object(parachute, "fetch_weather", return_value=safe), patch.object(
      parachute, "schedule_tool", return_value='{"scheduled": true, "message": "Cita calendarizada"}'
    ):
      answer = parachute._apply_calendar_guard("la quiero para el 2026-09-17", "No puedo responder esa pregunta")
    self.assertIn("Cita calendarizada", answer)

  def test_schedule_requires_approved_weather(self):
    approved = evaluate_weather(report())
    unsafe = evaluate_weather(report(precipitation_mm=1))
    test_file = Path("/tmp/hdt5-test-citas.json")
    with patch.object(parachute, "APPOINTMENTS_PATH", test_file), patch.object(parachute, "fetch_weather", return_value=approved):
      self.assertIn('"scheduled": true', schedule_tool("2026-09-20"))
    with patch.object(parachute, "fetch_weather", return_value=unsafe):
      self.assertIn('"scheduled": false', schedule_tool("2026-09-20"))
    test_file.unlink(missing_ok=True)

  def test_domain_guard_rejects_unrelated_topics(self):
    def fake_answer(query):
      if "peso" in query.lower():
        return "El límite de peso máximo estricto es de 100 kg."
      return "Lo siento, no puedo responder esa pregunta con la información disponible en la base de conocimientos de Parachute S.A."
    with patch.object(parachute, "_hdt4_faq_answer", side_effect=fake_answer):
      self.assertIn("no puedo responder", parachute._apply_domain_guard("¿Cuándo debutó BabyMonster?", "respuesta inventada"))
      self.assertIn("100 kg", parachute._apply_domain_guard("¿Cuál es el peso máximo?", "respuesta inventada"))
    self.assertEqual(parachute._apply_domain_guard("¿Cómo estás?", "saludo del modelo"), "saludo del modelo")

  def test_domain_guard_evaluates_compound_questions_independently(self):
    def fake_answer(query):
      return ("No puedo responder la parte sobre Ahyeon con la información disponible. "
              "La zona de salto se ubica en el aeródromo del evento.")
    with patch.object(parachute, "_hdt4_faq_answer", side_effect=fake_answer):
      answer = parachute._apply_domain_guard(
        "¿Quién es Ahyeon y dónde es el evento?",
        "respuesta inventada",
      )
    self.assertIn("Ahyeon", answer)
    self.assertIn("zona de salto", answer)
    self.assertNotIn("altitud", answer)

if __name__ == "__main__":
  unittest.main()
