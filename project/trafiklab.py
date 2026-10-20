import gc

BASE_URL = "https://realtime-api.trafiklab.se/v1"


def _requests():
    # Nyare MicroPython har "requests", äldre "urequests"
    try:
        import requests
    except ImportError:
        import urequests as requests
    return requests


def fetch_departures(area_id, api_key, max_rows=8):
    'Hämtar avgångar (nästa 60 min) och returnerar en förenklad lista'
    gc.collect()
    url = "%s/departures/%s?key=%s" % (BASE_URL, area_id, api_key)
    response = _requests().get(url)
    try:
        if response.status_code != 200:
            raise OSError("Trafiklab HTTP %d" % response.status_code)
        data = response.json()
    finally:
        response.close()
    result = parse_departures(data, max_rows)
    del data
    gc.collect()
    return result


def _hhmm(ts):
    # "2025-04-01T14:30:00" -> "14:30"
    return ts[11:16] if ts and len(ts) >= 16 else "--:--"


def _seconds_of_day(ts):
    return int(ts[11:13]) * 3600 + int(ts[14:16]) * 60 + int(ts[17:19])


def minutes_until(now, departure):
    'Minuter kvar. "now" tas från API-svaret, så ingen klocka behövs'
    diff = _seconds_of_day(departure) - _seconds_of_day(now)
    if departure[:10] > now[:10]:      # avgång efter midnatt
        diff += 86400
    return diff // 60


def departure_status(dep):
    if dep.get("canceled"):
        return "Installd"
    if not dep.get("is_realtime"):
        return "Enl. tidtabell"
    delay = dep.get("delay") or 0       # sekunder
    if delay >= 60:
        return "+%d min" % ((delay + 30) // 60)
    if delay <= -60:
        return "%d min tidig" % ((-delay + 30) // 60)
    return "I tid"


def parse_departures(data, max_rows=8):
    now = data.get("timestamp", "")
    result = []
    for dep in data.get("departures", []):
        route = dep.get("route") or {}
        when = dep.get("realtime") or dep.get("scheduled")
        minutes = minutes_until(now, when)
        if minutes < 0:
            continue                    # redan avgått
        result.append({
            "time": _hhmm(when),
            "minutes": minutes,
            "line": route.get("designation") or route.get("name") or "?",
            "destination": route.get("direction")
                or (route.get("destination") or {}).get("name") or "?",
            "status": departure_status(dep),
        })
    result.sort(key=lambda d: d["minutes"])
    return result[:max_rows]