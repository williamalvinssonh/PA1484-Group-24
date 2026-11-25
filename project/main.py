import sys
import time
import json

import lvgl as lv
import network

import trafiklab
import resrobot

from board_lvgl import start_board
from debug_log import log

from secrets import (WIFI_SSID, WIFI_PASSWORD,
                     TRAFIKLAB_API_KEY, RESROBOT_API_KEY)

# US4.1: The LVGL timer runs about twice as fast on this board, so
# 120 000 gives roughly 60 seconds (measured by the group).
REFRESH_MS = 120_000
MAX_ROWS = 8          # number of departures shown in the table

# NF3: Attribution in accordance with Trafiklab's license (CC BY 4.0)
ATTRIBUTION = "Data from Trafiklab.se (modified) - CC BY 4.0"

BLACK = 0x000000
WHITE = 0xFFFFFF
GREY = 0x555555

# US3.2C / US5.2B: Searchable stops -> Trafiklab area ID.
# The same IDs are used by the Realtime API and ResRobot.
STOP_IDS = {
    "Karlskrona C": "740000230",
    "Bergasa": "740001537",
    "Lyckeby": "740000663",
    "Campus Grasvik": "740032188",
    "Salto": "740031870",
    "Lango": "740031879",
    "Kungsplan": "740020510",
    "Af Chapmangymnasiet": "740031814",
    "Sparre": "740031816",
    "Alamedan": "740031817",
    "Amiralitetstorget": "740040917",
    "Varvet": "740031821",
    "Lokstallarna": "740037242",
    "Landsvagsgatan": "740031777",
    "Tullskolan": "740031778",
    "Ekholmen": "740031874",
    "Salto torg": "740031871",
    "Galgamarkstrappan": "740031888",
    "Annebo": "740031796",
    "Kungsmarken": "740031827",
    "Gullaberg": "740031828",
    "Amiralen": "740031800",
    "Lyckeby slottsbacken": "740032193",

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
DEFAULT_JOURNEY_START = "Karlskrona C"
DEFAULT_JOURNEY_DESTINATION = "Lyckeby"

# US5.3B: Arrival time choices. "Now" = the journey that arrives first
ARRIVE_HOURS = ["Now"] + ["%02d" % hour for hour in range(24)]
ARRIVE_MINUTES = ["%02d" % minute for minute in range(0, 60, 5)]

_ASCII = {
    "å": "a", "ä": "a", "ö": "o",
    "Å": "A", "Ä": "A", "Ö": "O",
    "ø": "o", "Ø": "O",
    "æ": "ae", "Æ": "AE",
    "é": "e", "è": "e", "ü": "u",
}


def ascii_text(text):
    # Function: Replaces characters missing from LVGL built-in fonts
    return "".join(_ASCII.get(c, c) for c in text)


class Application:
    def __init__(self):
        self.display, self.touch, self.handler = start_board()

        # Available stops and transport types
        self.stops = list(STOP_IDS.keys())
        self.transports = list(TRANSPORT_MODES.keys())

        # Default settings
        self.selected_stop = DEFAULT_STOP
        self.selected_transport = DEFAULT_TRANSPORT
        self.journey_start = DEFAULT_JOURNEY_START
        self.journey_destination = DEFAULT_JOURNEY_DESTINATION
        self.arrive_hour = "Now"
        self.arrive_minute = "00"

        # Stop search overlay (US3.2C / US5.2B), created when opened
        self.search_overlay = None
        self.search_target = None

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
        # Function: Sets background and text color of a tile
        tile.set_style_bg_opa(lv.OPA.COVER, 0)
        tile.set_style_bg_color(
            lv.color_hex(BLACK if dark else WHITE), 0)
        label.set_style_text_color(
            lv.color_hex(WHITE if dark else BLACK), 0)

    # ============================== UI ==============================

    def create_ui(self):
        # Function: Creates UI
        self.tileview = lv.tileview(lv.screen_active())
        self.tileview.set_size(600, 450)
        self.tileview.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)

        # Order: Start (0) <-> Settings (1) <-> Departures (2)
        #        <-> Journey Planner (3)
        self.tile1 = self.tileview.add_tile(0, 0, lv.DIR.RIGHT)
        self.tile3 = self.tileview.add_tile(1, 0, lv.DIR.LEFT | lv.DIR.RIGHT)
        self.tile2 = self.tileview.add_tile(2, 0, lv.DIR.LEFT | lv.DIR.RIGHT)
        self.tile4 = self.tileview.add_tile(3, 0, lv.DIR.LEFT)

        self.create_start_screen()
        self.create_departure_screen()
        self.create_settings_screen()
        self.create_journey_screen()

        # US2.1: Instant screen change on swipe, without slide animation
        # (also less lag, since the screen is only redrawn once).
        # The list must be in the same order as on the screen.
        self.tiles = [self.tile1, self.tile3, self.tile2, self.tile4]
        self.tile_index = 0
        # No scrolling on the tileview or the tiles, so a sideways swipe
        # becomes a gesture instead of a slide
        self.tileview.remove_flag(lv.obj.FLAG.SCROLLABLE)
        for tile in self.tiles:
            tile.remove_flag(lv.obj.FLAG.SCROLLABLE)

        # LVGL passes gestures up to the screen itself
        lv.screen_active().add_event_cb(
            self.on_gesture, lv.EVENT.GESTURE, None)

        # NF3: Attribution. Created last and directly on the screen
        # so that it is visible on all tiles.
        self.attribution = lv.label(lv.screen_active())
        self.attribution.set_text(ATTRIBUTION)
        self.attribution.set_style_text_color(lv.color_hex(GREY), 0)
        self.attribution.align(lv.ALIGN.BOTTOM_MID, 0, -6)

    def on_gesture(self, _event):
        # Function: Changes screen instantly when the user swipes (US2.1)
        if self.search_overlay is not None:
            return                      # no swiping while searching
        direction = lv.indev_active().get_gesture_dir()

        if direction == lv.DIR.LEFT and self.tile_index < len(self.tiles) - 1:
            self.tile_index += 1        # finger to the left -> next screen
        elif direction == lv.DIR.RIGHT and self.tile_index > 0:
            self.tile_index -= 1        # finger to the right -> previous screen
        else:
            return
        self.tileview.set_tile(self.tiles[self.tile_index], False)

    def create_status_label(self, tile):
        # Function: Status line at the bottom of a tile (US4.3)
        label = lv.label(tile)
        label.set_style_text_color(lv.color_hex(BLACK), 0)
        label.set_text("")
        label.align(lv.ALIGN.BOTTOM_MID, 0, -28)
        return label

    def create_start_screen(self):
        # Function: Start screen (US1.1)
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
            "Version 5.3B | Group 24"
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
        # Function: Departure screen with live data (US1.2B)
        self.tile2.set_style_bg_opa(lv.OPA.COVER, 0)
        self.tile2.set_style_bg_color(lv.color_hex(WHITE), 0)

        # Heading with the name of the stop
        self.header = lv.label(self.tile2)
        self.header.set_style_text_color(lv.color_hex(BLACK), 0)
        self.header.set_text("Loading departures...")
        self.header.align(lv.ALIGN.TOP_MID, 0, 10)

        self.departure_table = lv.table(self.tile2)

        # White cells, black text
        self.departure_table.set_style_bg_color(
            lv.color_hex(WHITE), lv.PART.ITEMS)
        self.departure_table.set_style_text_color(
            lv.color_hex(BLACK), lv.PART.ITEMS)

        # Table size and column headings
        self.departure_table.set_column_count(4)
        self.departure_table.set_row_count(1)
        self.departure_table.set_cell_value(0, 0, "Time")
        self.departure_table.set_cell_value(0, 1, "Line")
        self.departure_table.set_cell_value(0, 2, "Destination")
        self.departure_table.set_cell_value(0, 3, "Status")

        # Column widths
        self.departure_table.set_column_width(0, 90)
        self.departure_table.set_column_width(1, 70)
        self.departure_table.set_column_width(2, 250)
        self.departure_table.set_column_width(3, 130)

        # Fits between the header and the status line, scrolls if needed
        self.departure_table.set_height(340)
        self.departure_table.align(lv.ALIGN.TOP_MID, 0, 40)

        # Status line ("Wi-Fi connected", "No Wi-Fi", errors)
        self.status_label = self.create_status_label(self.tile2)

        # Manual refresh, also available here for convenience (US4.2B)
        self.refresh_button = lv.button(self.tile2)
        self.refresh_button.set_size(110, 32)
        self.refresh_button.align(lv.ALIGN.TOP_RIGHT, -10, 4)
        self.refresh_label = lv.label(self.refresh_button)
        self.refresh_label.set_text("Refresh")
        self.refresh_label.center()
        self.refresh_button.add_event_cb(
            self.on_refresh_clicked, lv.EVENT.CLICKED, None)

    def create_settings_screen(self):
        # Function: Settings screen
        # (US3.1, US3.2C, US3.3, US3.4, US3.5, US4.3)
        self.tile3.set_style_bg_opa(lv.OPA.COVER, 0)
        self.tile3.set_style_bg_color(lv.color_hex(WHITE), 0)

        # Settings title
        self.tile3_label = lv.label(self.tile3)
        self.tile3_label.set_text("Settings")
        self.tile3_label.set_style_text_font(lv.font_montserrat_28, 0)
        self.tile3_label.set_style_text_color(lv.color_hex(BLACK), 0)
        self.tile3_label.align(lv.ALIGN.TOP_MID, 0, 20)

        

        # ---- Searchable departure stop (US3.2C) ----
        self.stop_label = lv.label(self.tile3)
        self.stop_label.set_text("Departure stop:")
        self.stop_label.set_style_text_color(lv.color_hex(BLACK), 0)
        self.stop_label.align(lv.ALIGN.TOP_MID, 0, 75)

        self.stop_button, self.stop_value_label = self.create_stop_selector(
            self.tile3, self.selected_stop, "departure",
            300, 50, lv.ALIGN.TOP_MID, 0, 105)

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

        # ---- Wi-Fi and live data status (US4.3) ----
        self.settings_status = self.create_status_label(self.tile3)

    def create_journey_screen(self):
        # Function: Journey planner with search and result on one screen
        # (US5.1, US5.2B, US5.3B)
        self.tile4.set_style_bg_opa(lv.OPA.COVER, 0)
        self.tile4.set_style_bg_color(lv.color_hex(WHITE), 0)

        # ---- Title ----
        self.tile4_title = lv.label(self.tile4)
        self.tile4_title.set_text("Journey Planner")
        self.tile4_title.set_style_text_color(lv.color_hex(BLACK), 0)
        self.tile4_title.align(lv.ALIGN.TOP_MID, 0, 6)

        # ---- Row 1: searchable From -> To (US5.2B) ----
        self.start_button, self.start_value_label = self.create_stop_selector(
            self.tile4, self.journey_start, "start",
            250, 40, lv.ALIGN.TOP_LEFT, 10, 30)

        self.arrow_label = lv.label(self.tile4)
        self.arrow_label.set_text("->")
        self.arrow_label.set_style_text_color(lv.color_hex(BLACK), 0)
        self.arrow_label.align(lv.ALIGN.TOP_LEFT, 285, 42)

        (self.destination_button,
         self.destination_value_label) = self.create_stop_selector(
            self.tile4, self.journey_destination, "destination",
            250, 40, lv.ALIGN.TOP_LEFT, 330, 30)

        # ---- Row 2: Arrive by + Search (US5.3B) ----
        self.arrive_label = lv.label(self.tile4)
        self.arrive_label.set_text("Arrive by:")
        self.arrive_label.set_style_text_color(lv.color_hex(BLACK), 0)
        self.arrive_label.align(lv.ALIGN.TOP_LEFT, 10, 92)

        self.hour_dropdown = lv.dropdown(self.tile4)
        self.hour_dropdown.set_options("\n".join(ARRIVE_HOURS))
        self.hour_dropdown.set_size(90, 40)
        self.hour_dropdown.align(lv.ALIGN.TOP_LEFT, 95, 80)
        self.hour_dropdown.add_event_cb(
            self.on_arrive_hour_changed, lv.EVENT.VALUE_CHANGED, None)

        self.minute_dropdown = lv.dropdown(self.tile4)
        self.minute_dropdown.set_options("\n".join(ARRIVE_MINUTES))
        self.minute_dropdown.set_size(90, 40)
        self.minute_dropdown.align(lv.ALIGN.TOP_LEFT, 195, 80)
        self.minute_dropdown.add_event_cb(
            self.on_arrive_minute_changed, lv.EVENT.VALUE_CHANGED, None)

        self.search_button = lv.button(self.tile4)
        self.search_button.set_size(150, 40)
        self.search_button.align(lv.ALIGN.TOP_LEFT, 430, 80)
        self.search_label = lv.label(self.search_button)
        self.search_label.set_text("Search")
        self.search_label.center()
        self.search_button.add_event_cb(
            self.on_search_clicked, lv.EVENT.CLICKED, None)

        # ---- Result heading ("From -> To" or error) ----
        self.journey_header = lv.label(self.tile4)
        self.journey_header.set_style_text_color(lv.color_hex(BLACK), 0)
        self.journey_header.set_text("Choose stops and press Search")
        self.journey_header.align(lv.ALIGN.TOP_MID, 0, 130)

        # ---- Result table ----
        self.journey_table = lv.table(self.tile4)
        self.journey_table.set_style_bg_color(
            lv.color_hex(WHITE), lv.PART.ITEMS)
        self.journey_table.set_style_text_color(
            lv.color_hex(BLACK), lv.PART.ITEMS)
        self.journey_table.set_column_count(4)
        self.journey_table.set_row_count(1)
        self.journey_table.set_cell_value(0, 0, "Depart")
        self.journey_table.set_cell_value(0, 1, "Arrive")
        self.journey_table.set_cell_value(0, 2, "Time")
        self.journey_table.set_cell_value(0, 3, "Changes")
        self.journey_table.set_column_width(0, 100)
        self.journey_table.set_column_width(1, 75)
        self.journey_table.set_column_width(2, 80)
        self.journey_table.set_column_width(3, 325)
        self.journey_table.set_size(580, 245)
        self.journey_table.align(lv.ALIGN.TOP_MID, 0, 150)

        # Status line, same as on the other screens
        self.journey_status = self.create_status_label(self.tile4)

    def set_status(self, text):
        # Function: Shows a status message on Departures, Settings and
        # Journey Planner (US4.3)
        for label in (self.status_label, self.settings_status,
                      self.journey_status):
            label.set_text(text)
            label.align(lv.ALIGN.BOTTOM_MID, 0, -28)

    # ===================== Searchable stop list =====================

    def create_stop_selector(self, parent, stop, target,
                             width, height, align, x, y):
        # Function: Button showing the chosen stop. Tapping it opens the
        # searchable stop list (US3.2C / US5.2B).
        button = lv.button(parent)
        button.set_style_bg_color(lv.color_hex(BLACK), 0)
        button.set_size(width, height)
        button.align(align, x, y)

        label = lv.label(button)
        label.set_style_text_color(lv.color_hex(WHITE), 0)
        label.set_text(ascii_text(stop))
        label.center()

        button.add_event_cb(
            lambda event: self.open_stop_search(target),
            lv.EVENT.CLICKED,
            None)

        return button, label

    def open_stop_search(self, target):
        # Function: Opens a full-screen overlay with a search field,
        # keyboard and result list
        if self.search_overlay is not None:
            return              # already open
        self.search_target = target

        # Overlay prevents interaction with the screens behind it
        self.search_overlay = lv.obj(lv.screen_active())
        self.search_overlay.set_size(600, 450)
        self.search_overlay.set_pos(0, 0)
        self.search_overlay.set_style_bg_color(lv.color_hex(WHITE), 0)
        self.search_overlay.set_style_border_width(0, 0)
        self.search_overlay.remove_flag(lv.obj.FLAG.SCROLLABLE)

        title = lv.label(self.search_overlay)
        title.set_text("Select stop")
        title.set_style_text_color(lv.color_hex(BLACK), 0)
        title.align(lv.ALIGN.TOP_MID, 0, 5)

        # Cancel button
        close_button = lv.button(self.search_overlay)
        close_button.set_size(90, 35)
        close_button.align(lv.ALIGN.TOP_RIGHT, -5, 0)
        close_label = lv.label(close_button)
        close_label.set_text("Cancel")
        close_label.center()
        close_button.add_event_cb(
            self.close_stop_search, lv.EVENT.CLICKED, None)

        # Search field
        self.search_input = lv.textarea(self.search_overlay)
        self.search_input.set_one_line(True)
        self.search_input.set_placeholder_text("Search stop...")
        self.search_input.set_size(530, 45)
        self.search_input.align(lv.ALIGN.TOP_MID, 0, 50)

        # Scrollable result list
        self.search_results = lv.list(self.search_overlay)
        self.search_results.set_size(530, 275)
        self.search_results.align(lv.ALIGN.TOP_MID, 0, 105)

        # Keyboard, hidden until the search field is tapped
        self.search_keyboard = lv.keyboard(self.search_overlay)
        self.search_keyboard.set_size(530, 175)
        self.search_keyboard.align(lv.ALIGN.BOTTOM_MID, 0, -5)
        self.search_keyboard.set_textarea(self.search_input)
        self.search_keyboard.add_flag(lv.obj.FLAG.HIDDEN)

        self.search_input.add_event_cb(
            self.on_search_focused, lv.EVENT.FOCUSED, None)
        self.search_input.add_event_cb(
            self.on_search_changed, lv.EVENT.VALUE_CHANGED, None)

        # Show all stops before anything is typed
        self.update_search_results("")

    def on_search_focused(self, _event):
        # Function: Shows the keyboard and makes room for it
        self.search_keyboard.remove_flag(lv.obj.FLAG.HIDDEN)
        self.search_results.set_height(105)

    def on_search_changed(self, _event):
        # Function: Filters the list each time the text changes
        self.update_search_results(self.search_input.get_text())

    def update_search_results(self, query):
        # Function: Lists the stops whose name contains the search text,
        # ignoring case and å/ä/ö
        query = ascii_text(query).lower().strip()
        self.search_results.clean()

        matches = 0
        for stop in self.stops:
            if query in ascii_text(stop).lower():
                matches += 1
                button = self.search_results.add_button(
                    None, ascii_text(stop))
                button.set_style_bg_color(lv.color_hex(BLACK), 0)
                button.set_style_text_color(lv.color_hex(WHITE), 0)
                button.add_event_cb(
                    lambda event, name=stop: self.select_searched_stop(name),
                    lv.EVENT.CLICKED,
                    None)

        if matches == 0:
            self.search_results.add_text("No matching stops")

    def select_searched_stop(self, stop):
        # Function: Saves the chosen stop and updates its button
        if self.search_target == "departure":
            self.selected_stop = stop
            self.stop_value_label.set_text(ascii_text(stop))
            self.stop_value_label.center()
        elif self.search_target == "start":
            self.journey_start = stop
            self.start_value_label.set_text(ascii_text(stop))
            self.start_value_label.center()
        elif self.search_target == "destination":
            self.journey_destination = stop
            self.destination_value_label.set_text(ascii_text(stop))
            self.destination_value_label.center()

        log("Selected %s stop: %s" % (self.search_target, stop))

        # Close before refreshing, so the screen is usable again
        target = self.search_target
        self.close_stop_search(None)

        if target == "departure":
            self.update_data()

    def close_stop_search(self, _event):
        # Function: Deletes the whole search overlay
        if self.search_overlay is not None:
            self.search_overlay.delete()
            self.search_overlay = None

    # =========================== Trafiklab ===========================

    def refresh_departures(self):
        # Function: Fetches live data for the selected stop (one API call)
        stop_id = STOP_IDS[self.selected_stop]
        try:
            self.all_departures = trafiklab.fetch_departures(
                stop_id, TRAFIKLAB_API_KEY)
        except Exception as error:
            log("departures failed: %r" % (error,))
            self.set_status("Wi-Fi connected - live data error: %s"
                            % (error,))
            return

        self.header.set_text(ascii_text(self.selected_stop))
        self.header.align(lv.ALIGN.TOP_MID, 0, 10)
        self.set_status("Wi-Fi connected - live data OK")
        self.show_departures()
        log("departures updated: %d rows" % len(self.all_departures))

    def show_departures(self):
        # Function: Fills the table, filtered by transport type
        # (no API call)
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

    def update_data(self):
        # Function: Checks Wi-Fi and fetches new departures
        try:
            if network.WLAN(network.STA_IF).isconnected():
                self.refresh_departures()
            elif self.connect_wifi():
                self.refresh_departures()
            else:
                self.set_status("No Wi-Fi")
        except OSError as error:
            log("Wi-Fi error: %r" % (error,))
            self.set_status("No Wi-Fi")

    def on_refresh_timer(self, _timer):
        # Function: Runs about every 60 seconds (US4.1)
        try:
            self.update_data()
        except OSError as error:
            log("Wi-Fi refresh failed: %r" % (error,))
            self.set_status("Wi-Fi connection error")

    def on_refresh_clicked(self, _event):
        # Function: Manual refresh, from Settings or Departures (US4.2B)
        log("manual refresh")
        self.update_data()
        # Restart the countdown so no extra fetch happens right after
        self.refresh_timer.reset()

    # ============================ Settings ============================

    def on_transport_changed(self, _event):
        # Function: New transport type selected, filter the table (US3.3)
        selected = self.transport_dropdown.get_selected()
        self.selected_transport = self.transports[selected]
        log("Selected transport: " + self.selected_transport)
        self.show_departures()

    def save_settings(self, _event):
        # Function: Saves the current selection as default (US3.4)
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
        # Function: Loads saved settings at start-up (US3.4)
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
        # Function: Restores the saved default settings (US3.5)
        old_stop = self.selected_stop

        # Restore original defaults first
        self.selected_stop = DEFAULT_STOP
        self.selected_transport = DEFAULT_TRANSPORT

        # Load saved defaults if available
        self.load_settings()

        # Update the stop button and the transport dropdown
        self.stop_value_label.set_text(ascii_text(self.selected_stop))
        self.stop_value_label.center()
        self.transport_dropdown.set_selected(
            self.transports.index(self.selected_transport))

        # Update the table. New API call only if the stop changed.
        if self.selected_stop != old_stop:
            self.refresh_departures()
        else:
            self.show_departures()

        log("Settings reset to saved defaults")

    # ============================ Journey ============================

    def on_arrive_hour_changed(self, _event):
        # Function: New arrival hour selected (US5.3B)
        self.arrive_hour = ARRIVE_HOURS[self.hour_dropdown.get_selected()]
        log("Arrive hour: " + self.arrive_hour)

    def on_arrive_minute_changed(self, _event):
        # Function: New arrival minute selected (US5.3B)
        self.arrive_minute = ARRIVE_MINUTES[
            self.minute_dropdown.get_selected()]
        log("Arrive minute: " + self.arrive_minute)

    def on_search_clicked(self, _event):
        # Function: Shows the top matching journey based on arrival time
        # (US5.3B).
        # Now             -> the journey that arrives first.
        # Arrive by HH:MM -> the latest journey that still arrives in time.
        arrive_by = None
        if self.arrive_hour != "Now":
            arrive_by = "%s:%s" % (self.arrive_hour, self.arrive_minute)

        route = "%s -> %s" % (self.journey_start, self.journey_destination)
        if arrive_by:
            route = "Arrive by %s: %s" % (arrive_by, route)
        else:
            route = "Arrive first: %s" % route
        self.journey_header.set_text(ascii_text(route))
        self.journey_header.align(lv.ALIGN.TOP_MID, 0, 130)

        if self.journey_start == self.journey_destination:
            self.show_journey_message("Choose two different stops")
            return
        if not (network.WLAN(network.STA_IF).isconnected()
                or self.connect_wifi()):
            self.show_journey_message("No Wi-Fi")
            return

        try:
            trips = resrobot.fetch_trips(
                STOP_IDS[self.journey_start],
                STOP_IDS[self.journey_destination],
                RESROBOT_API_KEY, arrive_by=arrive_by)
        except Exception as error:
            log("journey search failed: %r" % (error,))
            self.show_journey_message("Could not search: %s" % (error,))
            return

        # Pick the single top matching journey
        if arrive_by:
            best = resrobot.best_by_arrival(trips, arrive_by)
        else:
            best = resrobot.earliest_arrival(trips)

        if best is None:
            self.show_journey_message("No journey arrives in time")
            return

        self.show_journeys([best])
        log("top journey: %s -> %s, %d change(s)" % (
            best["dep"], best["arr"], best["changes"]))

    def show_journeys(self, trips):
        # Function: Fills the journey table, one row per journey
        if not trips:
            self.show_journey_message("No journeys found")
            return
        self.journey_table.set_row_count(len(trips) + 1)
        for row, trip in enumerate(trips, start=1):
            self.journey_table.set_cell_value(row, 0, trip["dep"])
            self.journey_table.set_cell_value(row, 1, trip["arr"])
            self.journey_table.set_cell_value(
                row, 2, "%d min" % trip["minutes"])
            self.journey_table.set_cell_value(
                row, 3, ascii_text(resrobot.format_changes(trip)))
        self.journey_table.scroll_to_y(0, False)

    def show_journey_message(self, text):
        # Function: Shows a single message row in the journey table
        self.journey_table.set_row_count(2)
        for col in range(3):
            self.journey_table.set_cell_value(1, col, "-")
        self.journey_table.set_cell_value(1, 3, text)

    # ============================= Wi-Fi =============================

    @staticmethod
    def connect_wifi():
        # Function: Connects to Wi-Fi, returns True if connected
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