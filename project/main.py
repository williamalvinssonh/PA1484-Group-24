import sys
import time

import lvgl as lv
import network

from board_lvgl import start_board
from debug_log import log

from secrets import WIFI_SSID, WIFI_PASSWORD


class Application:
    def __init__(self):
        self.display, self.touch, self.handler = start_board()
        self.tile3_dark = False
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

    def on_tile3_clicked(self, _event):
        self.tile3_dark = not self.tile3_dark
        self.apply_tile_colors(self.tile3, self.tile3_label, self.tile3_dark)

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
        self.tile2 = self.tileview.add_tile(1, 0, lv.DIR.LEFT | lv.DIR.RIGHT)
        self.tile3 = self.tileview.add_tile(2, 0, lv.DIR.LEFT)

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

        self.tile3_label = lv.label(self.tile3)
        self.tile3_label.set_text(
            "Settings"            
            )
        self.tile3_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.tile3_label.set_style_text_font(lv.font_montserrat_28, 0)
        self.tile3_label.center()
        self.apply_tile_colors(self.tile3, self.tile3_label, False)
        self.tile3.add_flag(lv.obj.FLAG.CLICKABLE)
        self.tile3.add_event_cb(self.on_tile3_clicked, lv.EVENT.CLICKED, None)
    
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
