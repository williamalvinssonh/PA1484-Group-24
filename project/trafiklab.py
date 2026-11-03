import gc

import requests

BASE_URL = "https://realtime-api.trafiklab.se/v1"


def fetch_departures(area_id, api_key):
    # Function: Fetches all departures (next 60 min) as a simplified list
    gc.collect()
    url = "%s/departures/%s?key=%s" % (BASE_URL, area_id, api_key)
    response = requests.get(url)
    try:
        if response.status_code != 200:
            raise OSError("Trafiklab HTTP %d" % response.status_code)
        data = response.json()
    finally:
        response.close()
    result = parse_departures(data)
    del data
    gc.collect()
    return result


def _hhmm(ts):
    # Function: Converts "2025-04-01T14:30:00" to "14:30"
    return ts[11:16] if ts and len(ts) >= 16 else "--:--"


def _seconds_of_day(ts):
    # Function: Seconds since midnight for a Trafiklab timestamp
    return int(ts[11:13]) * 3600 + int(ts[14:16]) * 60 + int(ts[17:19])


def minutes_until(now, departure):
    # Function: Minutes left. "now" comes from the API response,
    # so no clock is needed
    diff = _seconds_of_day(departure) - _seconds_of_day(now)
    if departure[:10] > now[:10]:      # departure after midnight
        diff += 86400
    return diff // 60


def departure_status(dep):
    # Function: Status text: cancelled, delayed, early, on time or scheduled
    if dep.get("canceled"):
        return "Cancelled"
    if not dep.get("is_realtime"):
        return "Scheduled"              # no real-time data available
    delay = dep.get("delay") or 0       # seconds
    if delay >= 60:
        return "+%d min" % ((delay + 30) // 60)
    if delay <= -60:
        return "%d min early" % ((-delay + 30) // 60)
    return "On time"


def parse_departures(data):
    # Function: Converts the Trafiklab JSON response into a list of dicts,
    # sorted by time until departure
    now = data.get("timestamp", "")
    result = []
    for dep in data.get("departures", []):
        route = dep.get("route") or {}
        when = dep.get("realtime") or dep.get("scheduled")
        minutes = minutes_until(now, when)
        if minutes < 0:
            continue                    # already departed
        result.append({
            "time": _hhmm(when),
            "minutes": minutes,
            "line": route.get("designation") or route.get("name") or "?",
            "destination": route.get("direction")
                or (route.get("destination") or {}).get("name") or "?",
            "status": departure_status(dep),
            "mode": route.get("transport_mode") or "",
        })
    result.sort(key=lambda d: d["minutes"])
    return result


def filter_by_mode(departures, mode, max_rows):
    # Function: Filters by transport type and returns at most max_rows.
    # mode=None means all.
    if mode is None:
        return departures[:max_rows]
    filtered = []
    for departure in departures:
        if departure["mode"] == mode:
            filtered.append(departure)
        if len(filtered) == max_rows:
            break       # enough departures, no need to check the rest
    return filtered