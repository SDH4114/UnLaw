from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence

from unlawful.command_help import COMMAND_HELP

from .config import ConfigError, load_config

# ul weather: Open-Meteo (https://open-meteo.com/en/docs), no API key. Two requests per run: geocoding of the city
# name, then the forecast. Nothing is cached: the geocoding answer is tiny and a cache would need a place to live
# (this command has no storage of its own) and an invalidation rule for no real gain.
# UNLAW_WEATHER_GEOCODE_URL and UNLAW_WEATHER_FORECAST_URL replace the two endpoints. They exist only for tests
# (a local HTTP server); they must be http(s) URLs.

USAGE = """Usage: ul weather [city...] [--days N] [--units metric|imperial] [--json]
Run `ul weather --help` for details.
"""

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "unlaw-weather"
TIMEOUT = 10
MAX_BYTES = 1_000_000
DEFAULT_DAYS = 3
MAX_DAYS = 16
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
CURRENT = "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,precipitation"
DAILY = "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset"
IMPERIAL = {
    "temperature_unit": "fahrenheit",
    "wind_speed_unit": "mph",
    "precipitation_unit": "inch",
}

# WMO weather interpretation codes as Open-Meteo documents them: text and a plain symbol.
WMO = {
    0: ("Clear sky", "☀"),
    1: ("Mainly clear", "☀"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁"),
    45: ("Fog", "≋"),
    48: ("Depositing rime fog", "≋"),
    51: ("Light drizzle", "☂"),
    53: ("Moderate drizzle", "☂"),
    55: ("Dense drizzle", "☂"),
    56: ("Light freezing drizzle", "☂"),
    57: ("Dense freezing drizzle", "☂"),
    61: ("Slight rain", "☂"),
    63: ("Moderate rain", "☂"),
    65: ("Heavy rain", "☂"),
    66: ("Light freezing rain", "☂"),
    67: ("Heavy freezing rain", "☂"),
    71: ("Slight snow fall", "❄"),
    73: ("Moderate snow fall", "❄"),
    75: ("Heavy snow fall", "❄"),
    77: ("Snow grains", "❄"),
    80: ("Slight rain showers", "☂"),
    81: ("Moderate rain showers", "☂"),
    82: ("Violent rain showers", "☂"),
    85: ("Slight snow showers", "❄"),
    86: ("Heavy snow showers", "❄"),
    95: ("Thunderstorm", "⚡"),
    96: ("Thunderstorm with slight hail", "⚡"),
    99: ("Thunderstorm with heavy hail", "⚡"),
}


class WeatherError(Exception):
    """`code` is the exit status: 2 for usage problems, 1 for everything else."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- helpers


def clean(value: object) -> str:
    """Text from a server: control characters removed so it can never drive the terminal."""
    return CONTROL.sub("", value) if isinstance(value, str) else ""


def number(value: object) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def describe(code: object) -> tuple[str, str]:
    if isinstance(code, int) and not isinstance(code, bool) and code in WMO:
        return WMO[code]
    return ("Unknown conditions", "?")


def endpoint(variable: str, default: str) -> str:
    url = os.environ.get(variable) or default
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise WeatherError(f"{variable} must be an http(s) URL", 2)
    return url


def fetch(base: str, params: dict[str, str]) -> dict:
    url = base + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as error:
        reason = ""
        try:
            detail = json.loads(error.read(65536).decode("utf-8", "replace"))
            reason = clean(detail.get("reason")) if isinstance(detail, dict) else ""
        except (ValueError, OSError):
            pass
        raise WeatherError(
            f"Open-Meteo answered HTTP {error.code}" + (f": {reason}" if reason else "")
        ) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise WeatherError(
            f"could not reach Open-Meteo ({clean(str(getattr(error, 'reason', error)))})"
        ) from error
    if len(raw) > MAX_BYTES:
        raise WeatherError("Open-Meteo sent an answer that is too large")
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError as error:
        raise WeatherError("Open-Meteo sent an answer that is not JSON") from error
    if not isinstance(data, dict):
        raise WeatherError("Open-Meteo sent an unexpected answer")
    if data.get("error") is True:
        raise WeatherError(
            f"Open-Meteo: {clean(data.get('reason')) or 'request refused'}"
        )
    return data


# ---------------------------------------------------------------- lookups


def geocode(city: str) -> dict:
    data = fetch(
        endpoint("UNLAW_WEATHER_GEOCODE_URL", GEOCODE_URL),
        {"name": city, "count": "1", "language": "en", "format": "json"},
    )
    results = data.get("results")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        raise WeatherError(f"no city found for {city!r}")
    found = results[0]
    latitude, longitude = number(found.get("latitude")), number(found.get("longitude"))
    if (
        latitude is None
        or longitude is None
        or abs(latitude) > 90
        or abs(longitude) > 180
    ):
        raise WeatherError("Open-Meteo sent an unusable location")
    return {
        "name": clean(found.get("name")) or city,
        "admin1": clean(found.get("admin1")),
        "country": clean(found.get("country")),
        "latitude": latitude,
        "longitude": longitude,
        "timezone": clean(found.get("timezone")),
    }


def forecast(place: dict, days: int, units: str) -> dict:
    params = {
        "latitude": str(place["latitude"]),
        "longitude": str(place["longitude"]),
        "current": CURRENT,
        "daily": DAILY,
        "timezone": "auto",
        "forecast_days": str(days),
    }
    if units == "imperial":
        params.update(IMPERIAL)
    data = fetch(endpoint("UNLAW_WEATHER_FORECAST_URL", FORECAST_URL), params)
    current, daily = data.get("current"), data.get("daily")
    if (
        not isinstance(current, dict)
        or not isinstance(daily, dict)
        or not isinstance(daily.get("time"), list)
        or number(current.get("temperature_2m")) is None
    ):
        raise WeatherError("Open-Meteo sent an incomplete forecast")
    return data


def unit_labels(data: dict) -> dict[str, str]:
    current = (
        data.get("current_units") if isinstance(data.get("current_units"), dict) else {}
    )
    return {
        "temperature": clean(current.get("temperature_2m")),
        "wind_speed": clean(current.get("wind_speed_10m")),
        "precipitation": clean(current.get("precipitation")),
    }


def column(daily: dict, key: str, index: int) -> object:
    values = daily.get(key)
    return values[index] if isinstance(values, list) and index < len(values) else None


def build(place: dict, data: dict, units: str) -> dict:
    current, daily = data["current"], data["daily"]
    summary, _ = describe(current.get("weather_code"))
    days = []
    for index, date in enumerate(daily["time"]):
        code = column(daily, "weather_code", index)
        days.append(
            {
                "date": clean(date),
                "weather_code": code,
                "summary": describe(code)[0],
                "temperature_max": number(column(daily, "temperature_2m_max", index)),
                "temperature_min": number(column(daily, "temperature_2m_min", index)),
                "precipitation_probability": number(
                    column(daily, "precipitation_probability_max", index)
                ),
                "sunrise": clean(column(daily, "sunrise", index)),
                "sunset": clean(column(daily, "sunset", index)),
            }
        )
    return {
        "location": place,
        "units": units,
        "unit_labels": unit_labels(data),
        "current": {
            "time": clean(current.get("time")),
            "weather_code": current.get("weather_code"),
            "summary": summary,
            "temperature": number(current.get("temperature_2m")),
            "apparent_temperature": number(current.get("apparent_temperature")),
            "humidity": number(current.get("relative_humidity_2m")),
            "wind_speed": number(current.get("wind_speed_10m")),
            "precipitation": number(current.get("precipitation")),
        },
        "daily": days,
    }


# ---------------------------------------------------------------- output


def fmt(value: object, suffix: str = "") -> str:
    return "n/a" if value is None else f"{value}{suffix}"


def clock(stamp: str) -> str:
    return stamp.split("T", 1)[1] if "T" in stamp else (stamp or "n/a")


def render(report: dict) -> str:
    place, now, labels = report["location"], report["current"], report["unit_labels"]
    temp = labels["temperature"]
    name = ", ".join(
        part for part in (place["name"], place["admin1"], place["country"]) if part
    )
    lines = [f"{name} ({place['latitude']:.2f}, {place['longitude']:.2f})"]
    symbol = describe(now["weather_code"])[1]
    lines.append(
        f"Now: {symbol} {now['summary']}, {fmt(now['temperature'], temp)} "
        f"(feels like {fmt(now['apparent_temperature'], temp)}), humidity {fmt(now['humidity'], '%')}, "
        f"wind {fmt(now['wind_speed'], ' ' + labels['wind_speed'])}, "
        f"precipitation {fmt(now['precipitation'], ' ' + labels['precipitation'])}"
    )
    lines.append("")
    rows = []
    for day in report["daily"]:
        symbol = describe(day["weather_code"])[1]
        rows.append(
            (
                day["date"],
                f"{symbol} {day['summary']}",
                fmt(day["temperature_max"], temp),
                fmt(day["temperature_min"], temp),
                fmt(day["precipitation_probability"], "%"),
                clock(day["sunrise"]),
                clock(day["sunset"]),
            )
        )
    header = ("Date", "Weather", "High", "Low", "Rain", "Sunrise", "Sunset")
    widths = [max(len(row[i]) for row in [header, *rows]) for i in range(len(header))]
    for row in [header, *rows]:
        lines.append(
            "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip()
        )
    return "\n".join(lines)


# ---------------------------------------------------------------- command


def parse(args: list[str]) -> tuple[list[str], int, str | None, bool]:
    words: list[str] = []
    days, units, as_json = DEFAULT_DAYS, None, False
    index = 0
    while index < len(args):
        arg = args[index]
        name, equals, inline = arg.partition("=")
        if arg == "--json":
            as_json = True
        elif name in ("--days", "--units"):
            if equals:
                value = inline
            elif index + 1 < len(args):
                index += 1
                value = args[index]
            else:
                raise WeatherError(f"{name} needs a value", 2)
            if name == "--days":
                if (
                    not re.fullmatch(r"[0-9]{1,3}", value)
                    or not 1 <= int(value) <= MAX_DAYS
                ):
                    raise WeatherError(f"--days takes a number from 1 to {MAX_DAYS}", 2)
                days = int(value)
            else:
                if value not in ("metric", "imperial"):
                    raise WeatherError("--units takes metric or imperial", 2)
                units = value
        elif arg.startswith("-"):
            raise WeatherError(f"unknown option {arg}", 2)
        else:
            words.append(arg)
        index += 1
    return words, days, units, as_json


def run(args: list[str]) -> int:
    words, days, units, as_json = parse(args)
    settings = load_config()["weather"]
    city = " ".join(words).strip() or str(settings.get("city") or "").strip()
    if not city:
        raise WeatherError(
            'no city given and weather.city is empty; set one with: ul config set weather.city "Baku"',
            2,
        )
    if CONTROL.search(city):
        raise WeatherError("the city must not contain control characters", 2)
    units = units or str(settings.get("units") or "metric")
    place = geocode(city)
    report = build(place, forecast(place, days, units), units)
    print(json.dumps(report, ensure_ascii=False) if as_json else render(report))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "-h" in args or "--help" in args or args[:1] == ["help"]:
        print(COMMAND_HELP["weather"], end="")
        return 0
    try:
        return run(args)
    except WeatherError as error:
        print(f"unlaw weather: {error}", file=sys.stderr)
        if error.code == 2:
            print(USAGE, end="", file=sys.stderr)
        return error.code
    except ConfigError as error:
        print(f"unlaw weather: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
