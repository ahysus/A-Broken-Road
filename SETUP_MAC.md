# Running the demo on the MacBook

## Before the day (5 minutes, can be done tonight)
1. Open **Terminal** (press Command + Space, type `Terminal`, press Return).
2. Type `python3 --version` and press Return.
   - If it shows **Python 3.9 or newer**, you are ready.
   - If it asks to install "command line developer tools" or shows an error, install Python from
     https://www.python.org/downloads/ (needs internet, about 5 minutes). Do this before the demo day.

## Copy the folder
1. Copy `guisad-system.zip` to the MacBook (Google Drive, AirDrop, or a USB drive formatted as exFAT or FAT32).
2. Double-click the zip. It creates a `system` folder. Move it to the Desktop.

## Set up (once, no internet needed)
In Terminal, type these two lines, pressing Return after each:
```
cd ~/Desktop/system
bash setup_mac.sh
```
Wait for **"Setup finished"**. It also runs the tests, which should all pass.

## Start the demo (every time)
```
cd ~/Desktop/system
bash run_mac.sh
```
Then open Safari or Chrome and go to **http://127.0.0.1:8000**.
Keep the Terminal window open during the demo. To stop, click Terminal and press Control + C.

## Without Wi-Fi
Everything works except the background street map, which loads from the internet.
Roads, routes, closures, markers and the Guisad boundary still show, on a plain gray background.
A phone hotspot brings the street map back.

## If something goes wrong
| Problem | Fix |
|---|---|
| `command not found: python3` | Install Python from python.org (see above) |
| `Address already in use` | The demo is already running in another Terminal window. Use that one, or close it and start again |
| Page does not open | Check Terminal still shows the server running, and use exactly `http://127.0.0.1:8000` |
| Map looks gray | No internet. The demo still works. Use a phone hotspot if you want the street map |
| Clicking a road closes the wrong one | Zoom in further and wait for the pink highlight before clicking |
| Anything else | Restart: Control + C in Terminal, then `bash run_mac.sh` again. Restarting also reopens all roads |
