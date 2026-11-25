# Public Transport Information on ESP32 – Group 24

## Introduction
This project is a touchscreen app for the LILYGO T4-S3 (ESP32-S3) that shows public transport information for the Karlskrona region. It displays live departures for a chosen stop, can filter them by transport type, and includes a journey planner that finds the best journey between two stops. All data comes from Trafiklab: the Trafiklab Realtime APIs for departures and ResRobot for journeys. The data is shown under the CC BY 4.0 license, with attribution on every screen.

The app is written in MicroPython with the LVGL graphics library and is developed in Visual Studio Code with PlatformIO, based on the BTH/LILYGO skeleton code, which is left unchanged.

**Group 24:** Hieu Phan, William Alvinsson H, Zeinab Al Fadhili,
Ivar Stark, Varun Mahesh

## Getting started

This section explains how to set up the project and install the
dependencies needed to start developing.

### Prerequisites

**Hardware**
- LILYGO T4-S3 (ESP32-S3 with touchscreen)
- USB-C cable that supports data (not only charging)

**Software**
- [Visual Studio Code](https://code.visualstudio.com/)
- [PlatformIO IDE](https://platformio.org/install/ide?install=vscode)
  extension for VS Code
- Git, or [GitHub Desktop](https://desktop.github.com/)
- Python

**Accounts and network**
- A free account on [developer.trafiklab.se](https://developer.trafiklab.se)
  with a project that has API keys for:
  - **Trafiklab Realtime APIs** (departures)
  - **ResRobot v2.1** (journey planner)
- A 2.4 GHz Wi-Fi network. The ESP32 does not support 5 GHz. If you use an
  iPhone hotspot, turn on **Maximise Compatibility**.

### Installation

1. Clone the repository and open the folder in VS Code:
   ```bash
   git clone <repository-url>
   cd PA1484-Group-24
   code .
   ```
2. Install the PlatformIO extension if VS Code suggests it. PlatformIO
   downloads its tools the first time the project is opened.
3. Create your own secrets file from the example:
   ```bash
   cp project/secrets_example.py project/secrets.py
   ```
4. Fill in `project/secrets.py`:
   ```python
   WIFI_SSID = "your-wifi-name"
   WIFI_PASSWORD = "your-wifi-password"
   TRAFIKLAB_API_KEY = "your-realtime-api-key"
   RESROBOT_API_KEY = "your-resrobot-key"
   ```
   `secrets.py` is listed in `.gitignore` and must never be committed, so
   that the API keys stay private (Trafiklab's terms, NF3).

### Project structure

| File | Purpose |
|---|---|
| `main.py` | The app: screens, touch handling, Wi-Fi, timers |
| `trafiklab.py` | Fetches and parses departures from Trafiklab Realtime APIs |
| `resrobot.py` | Fetches and parses journeys from ResRobot Route Planner |
| `secrets_example.py` | Template for `secrets.py` |
| `board_lvgl.py`, `debug_log.py` | BTH/LILYGO skeleton files, not modified (NF4) |

## Building and running

### Uploading to the ESP32

1. Connect the T4-S3 with the USB-C cable.
2. **Close the Serial Monitor** if it is open. It uses the same USB port,
   and the upload fails with *"multiple access on port"* otherwise.
3. Run the deploy task, either from the PlatformIO sidebar under
   **Project Tasks → Custom → Deploy**, or in a terminal:
   ```bash
   platformio run --target deploy --environment t4s3-micropython
   ```
4. Wait for `[SUCCESS]`. The device restarts automatically.

Deploy writes a complete filesystem image to the device. This means that
settings saved with **Save default** are reset after each deploy.

### Viewing the log

Open the Serial Monitor (the plug icon in the PlatformIO status bar, or
`platformio device monitor`) at 115200 baud. Press the reset button on the
device to see the log from start-up.

### Start-up procedure

1. The start screen is shown with the project name, version, group number
   and members.
2. Saved settings (`settings.json`) are loaded, if there are any.
3. The device connects to Wi-Fi. This can take up to 15 seconds.
4. Live departures are fetched for the selected stop.
5. A timer updates the departures automatically about once a minute.

The program has no command-line arguments or modes. Wi-Fi, API keys and
the list of stops are configured in `secrets.py` and `STOP_IDS` in
`main.py`.

### Operating the app

**Navigation:** swipe left or right anywhere on the screen to move between
the four screens:

```
Start  <->  Settings  <->  Departures  <->  Journey Planner
```

**Departures:** shows time, line, destination and status (on time, delayed,
early, cancelled, or scheduled when no real-time data exists). Tap
**Refresh** to update immediately.

**Settings:**
- Tap the **stop button** to open the stop search. Type part of a name with
  the on-screen keyboard and tap a stop in the list.
- Choose **transport type** (All, Bus, Train, Ferry) in the dropdown.
- **Save default** stores the current choices so they are restored when the
  device restarts. **Reset settings** restores the saved defaults.

**Journey Planner:**
1. Tap the left button to search for a starting stop and the right button
   for the final destination.
2. Choose **Arrive by**:
   - **Now**: shows the journey that arrives first.
   - **A time** (hour and minute): shows the latest journey that still
     arrives in time.
3. Tap **Search**. The table shows departure, arrival, travel time and the
   departure time at every stop where you have to change.

**Status line:** the bottom of the Departures, Settings and Journey Planner
screens shows the Wi-Fi and live data status, for example
`Wi-Fi connected - live data OK`, an error message, or `No Wi-Fi`.

## Known limitations

- The device has no reliable clock, so **Arrive by** always searches for
  today. A time that has already passed gives a journey in the past, or no
  journey.
- The stop search filters the stops listed in `STOP_IDS`. It does not
  search all stops in Sweden.
- The screen freezes for a second or two while data is downloaded.
- LVGL's built-in fonts have no å, ä, ö, so they are shown as a and o.

## Features

- [x] US1.1: As a user, I want to see a starting screen displaying the project name, current program version, group number, and members' names.
- [x] US1.2B: As a user, I want to see the departure screen showing departure data: departure time, line, destination, and departure status for any destinations in Karlskrona using live data from Trafiklab.
- [x] US2.1: As a user, I want to navigate between different screens by sliding a finger over the touchscreen.
- [x] US3.1: As a user, I want to access a settings screen.
- [x] US3.2C: As a user, I want to search and select different stops for US1.2B.
- [x] US3.3: As a user, I want to select a transport type (bus, train, ferry, and all) using a dropdown.
- [x] US3.4: As a user, I want to save my current settings as the default and have them restored when the device restarts.
- [x] US3.5: As a user, I want to reset my current settings to the stored default settings.
- [x] US4.1: As a user, I want the live departure data to update automatically in 60 seconds.
- [x] US4.2B: As a user, I want to manually refresh the departure data with a button in the settings screen. (Manual refresh is implemented, but the button is on the departure screen instead of the settings screen. It was approved by supervisor)
- [x] US4.3: As a user, I want to see the current Wi-Fi connection and live data status on the settings screen.
- [x] US5.1: As a user, I want to access a journey selection screen.
- [x] US5.2B: As a user, I want to search for and select a starting stop and a final destination stop for US5.3.
- [x] US5.3B: As a user, I want to see the top matching journey, based on arrival time to the final destination, that shows the departure time for each intermediate stop where I must change transportation.