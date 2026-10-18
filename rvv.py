from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests


API_URL = "https://efa.rvv.de/efa/XML_DM_REQUEST"
TIMEZONE = ZoneInfo("Europe/Berlin")


def parse_time(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TIMEZONE)
        return dt.astimezone(TIMEZONE)
    except (ValueError, TypeError):
        return None


def get_value(obj, *keys, default="?"):
    for key in keys:
        value = obj.get(key) if isinstance(obj, dict) else None
        if value not in (None, ""):
            return value
    return default


def get_departures(stop_id, amount=20):
    params = {
        "outputFormat": "rapidJSON",
        "language": "de",
        "type_dm": "stop",
        "name_dm": stop_id,
        "mode": "direct",
        "useProxFootSearch": "0",
        "useRealtime": "1",
        "limit": amount,
    }

    response = requests.get(
        API_URL,
        params=params,
        timeout=15,
        headers={"User-Agent": "RVVDepartureBoard/1.0"},
    )
    response.raise_for_status()
    data = response.json()

    events = data.get("stopEvents")
    if events is None:
        events = data.get("departureList", [])

    results = []

    for event in events:
        transport = event.get("transportation") or {}
        line_info = event.get("servingLine") or {}
        location = event.get("location") or {}
        properties = location.get("properties") or {}

        planned = parse_time(
            event.get("departureTimePlanned")
            or event.get("dateTime")
        )
        estimated = parse_time(
            event.get("departureTimeEstimated")
            or event.get("realDateTime")
        )

        departure = planned or estimated

        line = (
            get_value(
                transport, "number", "disassembledName", "name",
                default=None
            )
            or get_value(line_info, "number", "name", "symbol")
        )

        destination_info = transport.get("destination") or {}
        destination = (
            get_value(
                destination_info, "name", "disassembledName",
                default=None
            )
            or get_value(line_info, "direction")
        )

        platform = get_value(properties, "platformName", "platform")
        stop = get_value(
            location, "name", "disassembledName", default=stop_id
        )

        delay = 0
        if planned and estimated:
            delay = round(
                (estimated - planned).total_seconds() / 60
            )

        results.append({
            "time": departure.isoformat(),
            "estimated": estimated.isoformat() if estimated else "",
            "line": str(line),
            "destination": str(destination),
            "platform": str(platform),
            "stop": str(stop),
            "delay": delay,
        })

    results.sort(key=lambda item: item["time"])
    return results