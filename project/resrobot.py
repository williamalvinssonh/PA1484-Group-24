
import gc

TRIP_URL = "https://api.resrobot.se/v2.1/trip"
NUM_JOURNEYS = 5        # US5.3: top 5 matching journeys


def fetch_trips(origin_id, dest_id, api_key, num=NUM_JOURNEYS,
                arrive_by=None):
    # Function: Fetches journeys from origin to destination.
    # arrive_by=None: the next journeys departing now (US5.3).
    # arrive_by="HH:MM": journeys arriving before that time today (US5.3B).
    import requests     # imported here so the tests run without it
    gc.collect()
    url = ("%s?format=json&originId=%s&destId=%s&numF=%d&passlist=0"
           "&accessId=%s" % (TRIP_URL, origin_id, dest_id, num, api_key))
    if arrive_by:
        url += "&searchForArrival=1&time=%s" % arrive_by
    response = requests.get(url)
    try:
        if response.status_code != 200:
            raise OSError("ResRobot HTTP %d" % response.status_code)
        data = response.json()
    finally:
        response.close()
    trips = parse_trips(data, num)
    del data
    gc.collect()
    return trips


def _as_list(value):
    #Function: Turning dict to list
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _hhmm(stop):
    # Function: Real-time time if available, otherwise scheduled, as "HH:MM"
    clock = stop.get("rtTime") or stop.get("time") or ""
    return clock[:5] if len(clock) >= 5 else "--:--"


def _short_name(name):
    # Function: "Lyckeby station (Karlskrona kn)" -> "Lyckeby station"
    return (name or "?").split(" (")[0]


def _duration_minutes(duration):
    # Function: Converts time data to minutes (65)
    minutes = 0
    number = ""
    for char in duration or "":
        if char.isdigit():
            number += char
        elif char == "H":
            minutes += int(number) * 60
            number = ""
        elif char == "M":
            minutes += int(number)
            number = ""
        else:
            number = ""         
    return minutes


def _line_name(leg):
    # Function: Short line name, e.g. "Bus 6" or "Train 1234"
    products = _as_list(leg.get("Product"))
    product = products[0] if products else {}
    category = (product.get("catOutL") or leg.get("name") or "").lower()
    if "buss" in category or "bus" in category:
        mode = "Bus"
    elif "tåg" in category or "train" in category:
        mode = "Train"
    elif "båt" in category or "färja" in category or "ferry" in category:
        mode = "Ferry"
    else:
        mode = ""
    number = product.get("num") or leg.get("transportNumber") or ""
    if mode and number:
        return "%s %s" % (mode, number)
    return mode or leg.get("name") or "?"


def parse_trips(data, num=NUM_JOURNEYS):
    # Function: Converts the ResRobot JSON response into a list of journeys.
    # Each journey has dep, arr, minutes, changes and rides. A ride is one
    # vehicle; walking and transfer legs are skipped.
    trips = []
    for trip in _as_list(data.get("Trip"))[:num]:
        rides = []
        for leg in _as_list((trip.get("LegList") or {}).get("Leg")):
            if leg.get("type") != "JNY":
                continue        # WALK / TRSF, not a vehicle
            origin = leg.get("Origin") or {}
            destination = leg.get("Destination") or {}
            rides.append({
                "from": _short_name(origin.get("name")),
                "dep": _hhmm(origin),
                "to": _short_name(destination.get("name")),
                "arr": _hhmm(destination),
                "line": _line_name(leg),
            })
        if not rides:
            continue            # walking-only journey, nothing to show
        trips.append({
            "dep": rides[0]["dep"],
            "arr": rides[-1]["arr"],
            "minutes": _duration_minutes(trip.get("duration")),
            "changes": len(rides) - 1,
            "rides": rides,
        })
    return trips


def best_by_arrival(trips, arrive_by):
    # Function: The top matching journey for an arrival time (US5.3B):
    # the latest arrival that is still on time. If two journeys arrive at
    # the same time, the one that departs latest (shortest trip) wins.
    # Returns None if no journey arrives in time.
    best = None
    for trip in trips:
        if trip["arr"] > arrive_by:
            continue            # arrives too late
        if (best is None or
                (trip["arr"], trip["dep"]) > (best["arr"], best["dep"])):
            best = trip
    return best

def earliest_arrival(trips):
    # Function: The top matching journey when leaving now (US5.3B):
    # the one that arrives first. If two arrive at the same time, the one
    # that departs latest (shortest trip) wins. None if there are no trips.
    best = None
    for trip in trips:
        if (best is None or trip["arr"] < best["arr"] or
                (trip["arr"] == best["arr"] and trip["dep"] > best["dep"])):
            best = trip
    return best


def format_changes(trip):
    # Function: Text for the "Changes" column: the departure time at each
    # stop where the traveller changes, with the line to change to
    if trip["changes"] == 0:
        return "Direct (%s)" % trip["rides"][0]["line"]
    lines = []
    for ride in trip["rides"][1:]:      # every ride after the first
        lines.append("%s %s (%s)" % (ride["dep"], ride["from"], ride["line"]))
    return "\n".join(lines)