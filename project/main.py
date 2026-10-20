import sys
import time
import json

import lvgl as lv
import network

from board_lvgl import start_board
from debug_log import log

from secrets import WIFI_SSID, WIFI_PASSWORD


class Application:
    def __init__(self):
        self.display, self.touch, self.handler = start_board()

        #Available departure destinations
        self.stops = [
            "Karlskrona C",
            "Bergasa",
            "Lyckeby",
            "Campus Grasvik"
        ]
        
        #Availible transports types
        self.transports = [
            "All", 
            "Bus",
            "Train",
            "Ferry"
        ]

        #defult settings
        self.selected_transport = "All"
        self.selected_stop = "Karlskrona C"

        #Load saved settings
        self.load_settings()

        self.create_ui()
        self.connect_wifi()
        log("student application ready")
        


    @staticmethod
    def apply_tile_colors(tile, label, dark):
        tile.set_style_bg_opa(lv.OPA.COVER, 0)
        tile.set_style_bg_color(
            lv.color_hex(0x000000 if dark else 0xFFFFFF), 0
        )
        label.set_style_text_color(
            lv.color_hex(0xFFFFFF if dark else 0x000000), 0
        )

    def create_ui(self):
        'Function: Creates UI'
        #Demo data
        departures = [
            {
                "time": "14:30",
                "line": "1",
                "destination": "Karlskrona C",
                "status": "On time"
            },
            {
                "time": "14:35",
                "line": "2",
                "destination": "Campus Grasvik",
                "status": "On time"
            },
            {
                "time": "14:40",
                "line": "3",
                "destination": "Lyckeby",
                "status": "+2 min"
            },
            {
                "time": "14:45",
                "line": "4",
                "destination": "Bergasa",
                "status": "On time"
            },
            {
                "time": "14:50",
                "line": "5",
                "destination": "Salto",
                "status": "On time"
            }   
        ]
        
        self.tileview = lv.tileview(lv.screen_active())
        self.tileview.set_size(600, 450)
        self.tileview.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)

        self.tile1 = self.tileview.add_tile(0, 0, lv.DIR.RIGHT)
        self.tile2 = self.tileview.add_tile(2, 0, lv.DIR.LEFT )
        self.tile3 = self.tileview.add_tile(1, 0, lv.DIR.LEFT | lv.DIR.RIGHT)

        #------Start-screen------#
        self.tile1_label = lv.label(self.tile1)
        self.tile1_label.set_text(
            "Public Transporation\n Information"
            "\n\n Version 1.2 | Grupp 24"
            "\n\n Members:"
            "\n Hieu Phan, William Alvinsson H"
            "\n Zeinab Al Fadhili, Ivar Stark" 
            "\n Varun Mahesh"
            "\n\n Swipe -->"               
            )
        self.tile1_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.tile1_label.set_style_text_font(lv.font_montserrat_28, 0)
        self.tile1_label.center()
        self.apply_tile_colors(self.tile1, self.tile1_label, False)

        #------Depature-screen------#
        self.departure_table = lv.table(self.tile2)

        # White cells
        self.departure_table.set_style_bg_color(
            lv.color_hex(0xFFFFFF),
            lv.PART.ITEMS
        )

        # Black text
        self.departure_table.set_style_text_color(
            lv.color_hex(0x000000),
            lv.PART.ITEMS
        )

        #Table size
        self.departure_table.set_column_count(4)
        self.departure_table.set_row_count(6)

        # Column headings
        self.departure_table.set_cell_value(0, 0, "Time")
        self.departure_table.set_cell_value(0, 1, "Line")
        self.departure_table.set_cell_value(0, 2, "Destination")
        self.departure_table.set_cell_value(0, 3, "Status")

        # Add departure data
        for row, departure in enumerate(departures, start=1):
            self.departure_table.set_cell_value(row, 0, departure["time"])
            self.departure_table.set_cell_value(row, 1, departure["line"])
            self.departure_table.set_cell_value(row, 2, departure["destination"])
            self.departure_table.set_cell_value(row, 3, departure["status"])

        # Column widths
        self.departure_table.set_column_width(0, 90)
        self.departure_table.set_column_width(1, 70)
        self.departure_table.set_column_width(2, 250)
        self.departure_table.set_column_width(3, 130)

        self.departure_table.center()
        self.tile2.set_style_bg_opa(lv.OPA.COVER, 0)
        self.tile2.set_style_bg_color(lv.color_hex(0xFFFFFF), 0)
        
        #------Setting-screen------#

        #White backround
        self.tile3.set_style_bg_opa(lv.OPA.COVER, 0)
        self.tile3.set_style_bg_color(lv.color_hex(0xFFFFFF), 0)

        #Settings title
        self.tile3_label = lv.label(self.tile3)
        self.tile3_label.set_text("Settings")
        self.tile3_label.set_style_text_font(
            lv.font_montserrat_28, 0
        )
        self.tile3_label.set_style_text_color(
            lv.color_hex(0x000000), 0
            )
        self.tile3_label.align(lv.ALIGN.TOP_MID, 0, 20)

        #Stop selection

        #Create stop label
        self.stop_label = lv.label(self.tile3)
        self.stop_label.set_text("Depature destination:")
        self.stop_label.set_style_text_color(
            lv.color_hex(0x000000), 0
        )

        #Position label
        self.stop_label.align(
            lv.ALIGN.TOP_MID, 0, 75
        )

        #Create stop dropdown
        self.stop_dropdown = lv.dropdown(self.tile3)

        #Available stops
        self.stop_dropdown.set_options(
            "\n".join(self.stops)
        )
        self.stop_dropdown.set_selected(
            self.stops.index(self.selected_stop)
        )

        #Dropdown size
        self.stop_dropdown.set_size(300, 50)

        #Position dropdown
        self.stop_dropdown.align(
            lv.ALIGN.TOP_MID, 0, 105
        )

        #Text size
        self.stop_dropdown.set_style_text_font(
            lv.font_montserrat_28, 0
        )

        #Detect selection changes
        self.stop_dropdown.add_event_cb(
            self.on_stop_changed,
            lv.EVENT.VALUE_CHANGED,
            None
        )

        #Save button
        self.save_button = lv.button(self.tile3)
        self.save_button.set_size(200,50)
        self.save_button.align(
            lv.ALIGN.TOP_LEFT, 65, 310
        )

        self.save_label = lv.label(self.save_button)
        self.save_label.set_text("Save default")
        self.save_label.center()

        self.save_button.add_event_cb(
            self.save_settings,
            lv.EVENT.CLICKED,
            None
        )

        #Reset button
        self.reset_button = lv.button(self.tile3)
        self.reset_button.set_size(200, 50)
        self.reset_button.align(
            lv.ALIGN.TOP_RIGHT, -65, 310
        )

        self.reset_label = lv.label(self.reset_button)
        self.reset_label.set_text("Reset settings")
        self.reset_label.center()

        self.reset_button.add_event_cb(
            self.reset_settings,
            lv.EVENT.CLICKED,
            None
        )


        #Transport selection
     
        self.transport_label = lv.label(self.tile3)
        self.transport_label.set_text("Transport type:")
        self.transport_label.set_style_text_color(
            lv.color_hex(0x000000), 0
        )
        self.transport_label.align(
            lv.ALIGN.TOP_MID, 0, 190
        )

        #Create dropdown
        self.transport_dropdown = lv.dropdown(self.tile3)

        #Available transport typs
        self.transport_dropdown.set_options(
            "\n".join(self.transports)
        )

        #Show selected transport
        self.transport_dropdown.set_selected(
            self.transports.index(self.selected_transport)
        )

        #Dropdown size
        self.transport_dropdown.set_size(300, 50)

        #center dropdown
        self.transport_dropdown.align(
            lv.ALIGN.TOP_MID, 0, 220
        )

        self.transport_dropdown.set_style_text_font(
            lv.font_montserrat_28, 0
        )
       
        #Detect selection changes
        self.transport_dropdown.add_event_cb(
            self.on_transport_changed,
            lv.EVENT.VALUE_CHANGED,
            None
        )

    def on_stop_changed(self, event):
        selected = self.stop_dropdown.get_selected()
        self.selected_stop = self.stops[selected]
        log("Selected stop:" + self.selected_stop)

    def on_transport_changed(self, event):
        selected = self.transport_dropdown.get_selected()
        self.selected_transport = self.transports[selected]
        log("Selected transport: " + self.selected_transport)

    def save_settings(self, event):
        settings = {
            "stop": self.selected_stop,
            "transport": self.selected_transport
        }

        try:
            with open("settings.json", "w") as file:
                json.dump(settings, file)

            log("Settings saved successfully")
        
        except Exception as error:
            log("Faild to save settings: %r" %error)
    
    def load_settings(self):
        try:
            with open("settings.json", "r") as file:
                settings = json.load(file)

            #Check that saved values are valid
            if (settings["stop"] in self.stops and settings["transport"] in self.transports):

                self.selected_stop = settings["stop"]
                self.selected_transport = settings["transport"]

                log("Settings loaded successfully")

            else:
                log("Invalid saved settings, using current values")
            
        except (OSError, ValueError, KeyError, TypeError):
            log("No valid settings file found")

    def reset_settings(self, event):
        # Restore original defaults first
        self.selected_stop = "Karlskrona C"
        self.selected_transport = "All"

        # Load saved defaults if available
        self.load_settings()

        # Update stop dropdown
        self.stop_dropdown.set_selected(
            self.stops.index(self.selected_stop)
        )

        # Update transport dropdown
        self.transport_dropdown.set_selected(
            self.transports.index(self.selected_transport)
        )

        log("Settings reset to saved defaults")

    
    @staticmethod
    def connect_wifi():
        'Function: Connects to WiFi'
        log("connecting to Wi-Fi SSID: " + WIFI_SSID)
        station = network.WLAN(network.STA_IF)
        station.active(True)
        station.connect(WIFI_SSID, WIFI_PASSWORD)
        started = time.ticks_ms()
        while (not station.isconnected() and
               time.ticks_diff(time.ticks_ms(), started) < 15_000):
            time.sleep_ms(250)
        log("Wi-Fi connected" if station.isconnected()
            else "Wi-Fi could not connect (timeout)")

try:
    app = Application()
except Exception as error:
    log("FATAL: %r" % (error,))
    sys.print_exception(error)
    raise

