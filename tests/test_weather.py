"""`ul weather`: the seeded command run as a black box against a local Open-Meteo stand-in."""

from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ulbin import CoreTestCase

GEOCODE = {
    "results": [
        {
            "name": "Baku",
            "latitude": 40.37767,
            "longitude": 49.89201,
            "country": "Azerbaijan",
            "admin1": "Baku City",
            "timezone": "Asia/Baku",
        }
    ]
}


def forecast(days: int, unit: str = "°C", wind: str = "km/h") -> dict:
    dates = [f"2026-11-{11 + i:02d}" for i in range(days)]
    return {
        "timezone": "Asia/Baku",
        "current_units": {
            "temperature_2m": unit,
            "apparent_temperature": unit,
            "relative_humidity_2m": "%",
            "wind_speed_10m": wind,
            "precipitation": "mm",
        },
        "current": {
            "time": "2026-11-11T14:45",
            "temperature_2m": 12.3,
            "apparent_temperature": 10.1,
            "relative_humidity_2m": 83,
            "weather_code": 3,
            "wind_speed_10m": 4.5,
            "precipitation": 0.0,
        },
        "daily_units": {"temperature_2m_max": unit, "temperature_2m_min": unit},
        "daily": {
            "time": dates,
            "weather_code": [80, 0, 61, 95, 71, 45, 2, 3, 1, 0, 0, 0, 0, 0, 0, 0][
                :days
            ],
            "temperature_2m_max": [14.0 + i for i in range(days)],
            "temperature_2m_min": [6.0 + i for i in range(days)],
            "precipitation_probability_max": [85 - i for i in range(days)],
            "sunrise": [f"{d}T07:21" for d in dates],
            "sunset": [f"{d}T17:26" for d in dates],
        },
    }


class Handler(BaseHTTPRequestHandler):
    # Set per test on the server: routes maps a path to (status, body).
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        self.server.requests.append(
            {
                "path": parsed.path,
                "query": parse_qs(parsed.query),
                "agent": self.headers.get("User-Agent", ""),
            }
        )
        status, body = self.server.routes.get(parsed.path, (404, {"error": True}))
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args: object) -> None:
        pass


class WeatherBase(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.requests = []
        self.server.routes = {
            "/geo": (200, GEOCODE),
            "/forecast": (200, forecast(3)),
        }
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.env["UNLAW_WEATHER_GEOCODE_URL"] = base + "/geo"
        self.env["UNLAW_WEATHER_FORECAST_URL"] = base + "/forecast"

    def asked(self, path: str) -> list[dict]:
        return [r for r in self.server.requests if r["path"] == path]


class WeatherTests(WeatherBase):
    def test_help_makes_no_request(self) -> None:
        for flag in ("--help", "-h"):
            self.assertIn("ul weather", self.ok("weather", flag).stdout)
        self.assertEqual(self.server.requests, [])

    def test_a_city_argument_prints_conditions_and_a_table(self) -> None:
        out = self.ok("weather", "Baku").stdout
        self.assertIn("Baku", out)
        self.assertIn("Azerbaijan", out)
        self.assertIn("Overcast", out)
        self.assertIn("12.3", out)
        self.assertIn("feels", out)
        self.assertIn("83%", out)
        self.assertIn("2026-11-11", out)
        self.assertIn("Slight rain showers", out)
        self.assertIn("85%", out)
        self.assertEqual(
            sum(1 for line in out.splitlines() if line.strip().startswith("2026-11-")),
            3,
        )

    def test_requests_use_the_documented_parameters(self) -> None:
        self.ok("weather", "New", "York", "--days", "5")
        geo = self.asked("/geo")[0]
        self.assertEqual(geo["query"]["name"], ["New York"])
        self.assertEqual(geo["query"]["count"], ["1"])
        self.assertEqual(geo["query"]["language"], ["en"])
        self.assertEqual(geo["query"]["format"], ["json"])
        self.assertEqual(geo["agent"], "unlaw-weather")
        query = self.asked("/forecast")[0]["query"]
        self.assertEqual(query["latitude"], ["40.37767"])
        self.assertEqual(query["longitude"], ["49.89201"])
        self.assertEqual(query["timezone"], ["auto"])
        self.assertEqual(query["forecast_days"], ["5"])
        self.assertEqual(
            query["current"],
            [
                "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,precipitation"
            ],
        )
        self.assertEqual(
            query["daily"],
            [
                "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset"
            ],
        )
        for key in ("temperature_unit", "wind_speed_unit", "precipitation_unit"):
            self.assertNotIn(key, query)
        self.assertEqual(self.asked("/forecast")[0]["agent"], "unlaw-weather")

    def test_the_default_is_three_days(self) -> None:
        self.ok("weather", "Baku")
        self.assertEqual(self.asked("/forecast")[0]["query"]["forecast_days"], ["3"])

    def test_no_city_explains_how_to_set_one(self) -> None:
        result = self.ul("weather")
        self.assertEqual(result.returncode, 2)
        self.assertIn('ul config set weather.city "Baku"', result.stderr)
        self.assertEqual(self.server.requests, [])

    def test_the_configured_city_is_the_default(self) -> None:
        self.ok("config", "set", "weather.city", "Baku")
        self.ok("weather")
        self.assertEqual(self.asked("/geo")[0]["query"]["name"], ["Baku"])

    def test_imperial_units_from_the_flag_and_the_config(self) -> None:
        self.server.routes["/forecast"] = (200, forecast(3, "°F", "mp/h"))
        out = self.ok("weather", "Baku", "--units", "imperial").stdout
        query = self.asked("/forecast")[0]["query"]
        self.assertEqual(query["temperature_unit"], ["fahrenheit"])
        self.assertEqual(query["wind_speed_unit"], ["mph"])
        self.assertEqual(query["precipitation_unit"], ["inch"])
        self.assertIn("°F", out)
        self.ok("config", "set", "weather.units", "imperial")
        self.ok("weather", "Baku")
        self.assertEqual(
            self.asked("/forecast")[1]["query"]["temperature_unit"], ["fahrenheit"]
        )
        self.ok("weather", "Baku", "--units", "metric")
        self.assertNotIn("temperature_unit", self.asked("/forecast")[2]["query"])

    def test_json_output(self) -> None:
        data = json.loads(self.ok("weather", "Baku", "--days", "3", "--json").stdout)
        self.assertEqual(data["location"]["name"], "Baku")
        self.assertEqual(data["location"]["country"], "Azerbaijan")
        self.assertEqual(data["units"], "metric")
        self.assertEqual(data["current"]["temperature"], 12.3)
        self.assertEqual(data["current"]["summary"], "Overcast")
        self.assertEqual(data["current"]["weather_code"], 3)
        self.assertEqual(len(data["daily"]), 3)
        day = data["daily"][0]
        self.assertEqual(day["date"], "2026-11-11")
        self.assertEqual(day["temperature_max"], 14.0)
        self.assertEqual(day["precipitation_probability"], 85)
        self.assertEqual(day["sunrise"], "2026-11-11T07:21")
        self.assertEqual(day["summary"], "Slight rain showers")

    def test_bad_options_are_usage_errors(self) -> None:
        for args in (
            ("Baku", "--days", "0"),
            ("Baku", "--days", "17"),
            ("Baku", "--days", "abc"),
            ("Baku", "--days"),
            ("Baku", "--units", "kelvin"),
            ("Baku", "--bogus"),
        ):
            self.assertEqual(self.ul("weather", *args).returncode, 2, args)
        self.assertEqual(self.server.requests, [])

    def test_unknown_city(self) -> None:
        self.server.routes["/geo"] = (200, {"generationtime_ms": 0.1})
        result = self.ul("weather", "Nowhereville")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no city found", result.stderr)
        self.assertIn("Nowhereville", result.stderr)

    def test_http_errors_are_explained(self) -> None:
        self.server.routes["/forecast"] = (
            500,
            {"error": True, "reason": "database on fire"},
        )
        result = self.ul("weather", "Baku")
        self.assertEqual(result.returncode, 1)
        self.assertIn("500", result.stderr)
        self.assertIn("database on fire", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_garbage_answers_are_explained(self) -> None:
        self.server.routes["/geo"] = (200, b"<html>captive portal</html>")
        result = self.ul("weather", "Baku")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)

    def test_incomplete_forecast_is_explained(self) -> None:
        self.server.routes["/forecast"] = (200, {"current": {}})
        result = self.ul("weather", "Baku")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)

    def test_offline(self) -> None:
        self.env["UNLAW_WEATHER_GEOCODE_URL"] = "http://127.0.0.1:9/geo"
        result = self.ul("weather", "Baku")
        self.assertEqual(result.returncode, 1)
        self.assertIn("could not reach", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_control_characters_in_the_city_are_refused(self) -> None:
        result = self.ul("weather", "Ba\x1bku")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.server.requests, [])

    def test_server_text_is_stripped_of_control_characters(self) -> None:
        bad = json.loads(json.dumps(GEOCODE))
        bad["results"][0]["name"] = "Ba\x1b[31mku"
        self.server.routes["/geo"] = (200, bad)
        out = self.ok("weather", "Baku").stdout
        self.assertNotIn("\x1b", out)


if __name__ == "__main__":
    unittest.main()
