import sys
import time
import json

import lvgl as lv
import network

import trafiklab

from board_lvgl import start_board
from debug_log import log

from secrets import WIFI_SSID, WIFI_PASSWORD, TRAFIKLAB_API_KEY

REFRESH_MS = 60_000   # US4.1: update every 60 seconds
MAX_ROWS = 8          # number of departures shown in the table

# NF3: Attribution in accordance with Trafiklab's license (CC BY 4.0)
ATTRIBUTION = "Data from Trafiklab.se (modified) - CC BY 4.0"

BLACK = 0x000000
WHITE = 0xFFFFFF
GREY = 0x555555

# US3.2B: Stop name in dropdown -> Trafiklab area ID.
# Find the actual IDs using:
# https://realtime-api.trafiklab.se/v1/stops/name/<name>?key=<api_key>
STOP_IDS = {
    "Karlskrona C": "740000230",
    "Bergasa": "740001537",
    "Lyckeby": "740000663",
    "Campus Grasvik": "740032188",
    "Salto": "740031870",
    "Aspo": "740068805",
}

# US3.3: Name in dropdown -> transport_mode in the API (None = all)
TRANSPORT_MODES = {
    "All": None,
    "Bus": "BUS",
    "Train": "TRAIN",
    "Ferry": "BOAT",   # Trafiklab calls ferries BOAT
}

DEFAULT_STOP = "Karlskrona C"
DEFAULT_TRANSPORT = "All"

_ASCII = {"å": "a", "ä": "a", "ö": "o", "Å": "A", "Ä": "A", "Ö": "O"
          ,"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "é": "e", "è": "e", "ü": "u"
          }


def ascii_text(text):
    #Function: Replaces å/ä/ö, which are missing from LVGL built-in fonts
    return "".join(_ASCII.get(c, c) for c in text)


class Application:
    def __init__(self):
        self.display, self.touch, self.handler = start_board()

        # Available departure stops
        self.stops = list(STOP_IDS.keys())

        # Available transport types
        self.transports = list(TRANSPORT_MODES.keys())

        # Default settings
        self.selected_stop = DEFAULT_STOP
        self.selected_transport = DEFAULT_TRANSPORT

        # Latest download from Trafiklab (unfiltered)
        self.all_departures = []

        # US3.4: Load saved settings
        self.load_settings()

        self.create_ui()

        if self.connect_wifi():
            self.refresh_departures()
        else:
            self.set_status("No Wi-Fi")

        # US4.1: Automatic update. Store the timer in self,
        # otherwise it might be garbage-collected.
        self.refresh_timer = lv.timer_create(
            self.on_refresh_timer, REFRESH_MS, None)
        log("student application ready")

    @staticmethod
    def apply_tile_colors(tile, label, dark):
        #Function: Sets background and text color of a tile
        tile.set_style_bg_opa(lv.OPA.COVER, 0)
        tile.set_style_bg_color(
            lv.color_hex(BLACK if dark else WHITE), 0
        )
        label.set_style_text_color(
            lv.color_hex(WHITE if dark else BLACK), 0
        )

    # ====================== UI =======================

    def create_ui(self):
        #Function: Creates UI
        self.tileview = lv.tileview(lv.screen_active())
        self.tileview.set_size(600, 450)
        self.tileview.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)

        # Order: Start (0) <-> Settings (1) <-> Departures (2)
        self.tile1 = self.tileview.add_tile(0, 0, lv.DIR.RIGHT)
        self.tile3 = self.tileview.add_tile(1, 0, lv.DIR.LEFT | lv.DIR.RIGHT)
        self.tile2 = self.tileview.add_tile(2, 0, lv.DIR.LEFT)

        self.create_start_screen()
        self.create_departure_screen()
        self.create_settings_screen()

        # NF3: Attribution. Created last and directly on the screen
        # so that it is visible on all tiles.
        self.attribution = lv.label(lv.screen_active())
        self.attribution.set_text(ATTRIBUTION)
        self.attribution.set_style_text_color(lv.color_hex(GREY), 0)
        self.attribution.align(lv.ALIGN.BOTTOM_MID, 0, -6)

    def create_start_screen(self):
        #Function: Start screen (US1.1)
        self.tile1.set_style_bg_opa(lv.OPA.COVER, 0)
        self.tile1.set_style_bg_color(lv.color_hex(WHITE), 0)

        self.tile1_title = lv.label(self.tile1)
        self.tile1_title.set_text("Public Transportation\nInformation")
        self.tile1_title.set_width(600)
        self.tile1_title.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.tile1_title.set_style_text_font(lv.font_montserrat_28, 0)
        self.tile1_title.set_style_text_color(lv.color_hex(BLACK), 0)
        self.tile1_title.align(lv.ALIGN.TOP_MID, 0, 50)

        self.tile1_label = lv.label(self.tile1)
        self.tile1_label.set_text(
            "Version 4.1 | Group 24"
            "\n\nMembers:"
            "\nHieu Phan, William Alvinsson H"
            "\nZeinab Al Fadhili, Ivar Stark"
            "\nVarun Mahesh"
            "\n\nSwipe -->"
        )
        self.tile1_label.set_width(600)
        self.tile1_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.tile1_label.set_style_text_font(lv.font_montserrat_28, 0)
        self.tile1_label.set_style_text_color(lv.color_hex(BLACK), 0)
        self.tile1_label.align(lv.ALIGN.TOP_MID, 0, 150)

    def create_departure_screen(self):
        #Function: Departure screen with live data (US1.2B)
        self.tile2.set_style_bg_opa(lv.OPA.COVER, 0)
        self.tile2.set_style_bg_color(lv.color_hex(WHITE), 0)

        # Heading with the name of the stop
        self.header = lv.label(self.tile2)
        self.header.set_style_text_color(lv.color_hex(BLACK), 0)
        self.header.set_text("Loading departures...")
        self.header.align(lv.ALIGN.TOP_MID, 0, 10)

        self.departure_table = lv.table(self.tile2)

        # White cells
        self.departure_table.set_style_bg_color(
            lv.color_hex(WHITE), lv.PART.ITEMS)

        # Black text
        self.departure_table.set_style_text_color(
            lv.color_hex(BLACK), lv.PART.ITEMS)

        # Table size
        self.departure_table.set_column_count(4)
        self.departure_table.set_row_count(1)

        # Column headings
        self.departure_table.set_cell_value(0, 0, "Time")
        self.departure_table.set_cell_value(0, 1, "Line")
        self.departure_table.set_cell_value(0, 2, "Destination")
        self.departure_table.set_cell_value(0, 3, "Status")

        # Column widths
        self.departure_table.set_column_width(0, 90)
        self.departure_table.set_column_width(1, 70)
        self.departure_table.set_column_width(2, 250)
        self.departure_table.set_column_width(3, 130)

        # Fits between the header and the status bar, scrolls if needed
        self.departure_table.set_height(340)
        self.departure_table.align(lv.ALIGN.TOP_MID, 0, 40)

        # Status bar for errors ("No Wi-Fi", "HTTP 401", ...)
        self.status_label = lv.label(self.tile2)
        self.status_label.set_style_text_color(lv.color_hex(BLACK), 0)
        self.status_label.set_text("")
        self.status_label.align(lv.ALIGN.BOTTOM_MID, 0, -28)

    def create_settings_screen(self):
        'Function: Settings screen (US3.1, US3.2B, US3.3, US3.4, US3.5)'
        # White background
        self.tile3.set_style_bg_opa(lv.OPA.COVER, 0)
        self.tile3.set_style_bg_color(lv.color_hex(WHITE), 0)

        # Settings title
        self.tile3_label = lv.label(self.tile3)
        self.tile3_label.set_text("Settings")
        self.tile3_label.set_style_text_font(lv.font_montserrat_28, 0)
        self.tile3_label.set_style_text_color(lv.color_hex(BLACK), 0)
        self.tile3_label.align(lv.ALIGN.TOP_MID, 0, 20)

        # ---- Stop selection (US3.2B) ----
        self.stop_label = lv.label(self.tile3)
        self.stop_label.set_text("Departure stop:")
        self.stop_label.set_style_text_color(lv.color_hex(BLACK), 0)
        self.stop_label.align(lv.ALIGN.TOP_MID, 0, 75)

        self.stop_dropdown = lv.dropdown(self.tile3)
        self.stop_dropdown.set_options("\n".join(self.stops))
        self.stop_dropdown.set_selected(
            self.stops.index(self.selected_stop))
        self.stop_dropdown.set_size(300, 50)
        self.stop_dropdown.align(lv.ALIGN.TOP_MID, 0, 105)
        self.stop_dropdown.set_style_text_font(lv.font_montserrat_28, 0)
        self.stop_dropdown.add_event_cb(
            self.on_stop_changed, lv.EVENT.VALUE_CHANGED, None)

        # ---- Transport selection (US3.3) ----
        self.transport_label = lv.label(self.tile3)
        self.transport_label.set_text("Transport type:")
        self.transport_label.set_style_text_color(lv.color_hex(BLACK), 0)
        self.transport_label.align(lv.ALIGN.TOP_MID, 0, 190)

        self.transport_dropdown = lv.dropdown(self.tile3)
        self.transport_dropdown.set_options("\n".join(self.transports))
        self.transport_dropdown.set_selected(
            self.transports.index(self.selected_transport))
        self.transport_dropdown.set_size(300, 50)
        self.transport_dropdown.align(lv.ALIGN.TOP_MID, 0, 220)
        self.transport_dropdown.set_style_text_font(lv.font_montserrat_28, 0)
        self.transport_dropdown.add_event_cb(
            self.on_transport_changed, lv.EVENT.VALUE_CHANGED, None)

        # ---- Save button (US3.4) ----
        self.save_button = lv.button(self.tile3)
        self.save_button.set_size(200, 50)
        self.save_button.align(lv.ALIGN.TOP_LEFT, 65, 310)
        self.save_label = lv.label(self.save_button)
        self.save_label.set_text("Save default")
        self.save_label.center()
        self.save_button.add_event_cb(
            self.save_settings, lv.EVENT.CLICKED, None)

        # ---- Reset button (US3.5) ----
        self.reset_button = lv.button(self.tile3)
        self.reset_button.set_size(200, 50)
        self.reset_button.align(lv.ALIGN.TOP_RIGHT, -65, 310)
        self.reset_label = lv.label(self.reset_button)
        self.reset_label.set_text("Reset settings")
        self.reset_label.center()
        self.reset_button.add_event_cb(
            self.reset_settings, lv.EVENT.CLICKED, None)

    def set_status(self, text):
        #Function: Shows a message below the departure table
        self.status_label.set_text(text)
        self.status_label.align(lv.ALIGN.BOTTOM_MID, 0, -28)

    # =================== Trafiklab ======================

    def refresh_departures(self):
        #Function: Fetches live data for the selected stop (one API call)
        stop_id = STOP_IDS[self.selected_stop]
        try:
            self.all_departures = trafiklab.fetch_departures(
                stop_id, TRAFIKLAB_API_KEY)
        except Exception as error:
            log("departures failed: %r" % (error,))
            self.set_status("Could not update: %s" % (error,))
            return

        self.header.set_text(ascii_text(self.selected_stop))
        self.header.align(lv.ALIGN.TOP_MID, 0, 10)
        self.set_status("")
        self.show_departures()
        log("departures updated: %d rows" % len(self.all_departures))

    def show_departures(self):
        #Function: Fills the table, filtered by transport type (no API call)
        mode = TRANSPORT_MODES[self.selected_transport]
        departures = trafiklab.filter_by_mode(
            self.all_departures, mode, MAX_ROWS)

        if not departures:
            self.departure_table.set_row_count(2)
            self.departure_table.set_cell_value(1, 0, "-")
            self.departure_table.set_cell_value(1, 1, "-")
            self.departure_table.set_cell_value(1, 2, "No departures")
            self.departure_table.set_cell_value(1, 3, "-")
            return

        self.departure_table.set_row_count(len(departures) + 1)
        for row, departure in enumerate(departures, start=1):
            self.departure_table.set_cell_value(row, 0, departure["time"])
            self.departure_table.set_cell_value(
                row, 1, ascii_text(departure["line"]))
            self.departure_table.set_cell_value(
                row, 2, ascii_text(departure["destination"]))
            self.departure_table.set_cell_value(row, 3, departure["status"])

    def on_refresh_timer(self, _timer):
        #Function: Runs every 60 seconds (US4.1)
        if network.WLAN(network.STA_IF).isconnected():
            self.refresh_departures()
        elif self.connect_wifi():
            self.refresh_departures()
        else:
            self.set_status("No Wi-Fi")

    # ========================== Settings ==============================

    def on_stop_changed(self, _event):
        #Function: New stop selected, fetch new departures (US3.2B)
        selected = self.stop_dropdown.get_selected()
        self.selected_stop = self.stops[selected]
        log("Selected stop: " + self.selected_stop)
        self.refresh_departures()

    def on_transport_changed(self, _event):
        #Function: New transport type selected, filter the table (US3.3)
        selected = self.transport_dropdown.get_selected()
        self.selected_transport = self.transports[selected]
        log("Selected transport: " + self.selected_transport)
        self.show_departures()

    def save_settings(self, _event):
        #Function: Saves the current selection as default (US3.4)
        settings = {
            "stop": self.selected_stop,
            "transport": self.selected_transport,
        }
        try:
            with open("settings.json", "w") as file:
                json.dump(settings, file)
            log("Settings saved successfully")
        except Exception as error:
            log("Failed to save settings: %r" % (error,))

    def load_settings(self):
        #Function: Loads saved settings at start-up (US3.4)
        try:
            with open("settings.json", "r") as file:
                settings = json.load(file)

            # Check that saved values are valid
            if (settings["stop"] in self.stops and 
                    settings["transport"] in self.transports):
                self.selected_stop = settings["stop"]
                self.selected_transport = settings["transport"]
                log("Settings loaded successfully")
            else:
                log("Invalid saved settings, using current values")

        except (OSError, ValueError, KeyError, TypeError):
            log("No valid settings file found")

    def reset_settings(self, _event):
        #Function: Restores the saved default settings (US3.5)
        old_stop = self.selected_stop

        # Restore original defaults first
        self.selected_stop = DEFAULT_STOP
        self.selected_transport = DEFAULT_TRANSPORT

        # Load saved defaults if available
        self.load_settings()

        # Update dropdowns
        self.stop_dropdown.set_selected(
            self.stops.index(self.selected_stop))
        self.transport_dropdown.set_selected(
            self.transports.index(self.selected_transport))

        # Update the table. New API call only if the stop changed.
        if self.selected_stop != old_stop:
            self.refresh_departures()
        else:
            self.show_departures()

        log("Settings reset to saved defaults")

    # ======================= Wi-Fi ========================

    @staticmethod
    def connect_wifi():
        #Function: Connects to WiFi, returns True if connected
        log("connecting to Wi-Fi SSID: " + WIFI_SSID)
        station = network.WLAN(network.STA_IF)
        station.active(True)
        if not station.isconnected():
            station.connect(WIFI_SSID, WIFI_PASSWORD)
        started = time.ticks_ms()
        while (not station.isconnected() and
               time.ticks_diff(time.ticks_ms(), started) < 15_000):
            time.sleep_ms(250)
        log("Wi-Fi connected" if station.isconnected()
            else "Wi-Fi could not connect (timeout)")
        return station.isconnected()


try:
    app = Application()
except Exception as error:
    log("FATAL: %r" % (error,))
    sys.print_exception(error)
    raise