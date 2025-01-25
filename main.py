import os
import re
import json
import asyncio
import threading
import time
import requests
import playsound
import websockets
from gtts import gTTS
from g4f.client import Client

notify_gcode = ""
notify_timeout = 10000
gcode_with_notify = ""
setup_z = 20
setup_y = 100
setup_x = 40
retraction_distance = 3

def init(gcode_with_notify_text):
    global gcode_with_notify
    gcode_with_notify = gcode_with_notify_text
    thread_listen_to_websocket = threading.Thread(target=asyncio.run, args=(listen_to_websocket(), ))
    thread_listen_to_websocket.daemon = True
    thread_listen_to_websocket.start()

async def listen_to_websocket():
    global notify_gcode

    uri = "ws://192.168.1.50/websocket"
    async with websockets.connect(uri) as websocket:
        while True:
            message = json.loads(await websocket.recv())
            if message['method'] == 'notify_gcode_response':
                notify_gcode = message['params']

def run_gcode(gcode):
    global notify_gcode, gcode_with_notify
    
    print("> " + gcode)
    url = "http://192.168.1.50/printer/gcode/script?script=" + gcode

    try:
        response = requests.get(url)
        response.raise_for_status()

        tab = gcode.split()

        if len(tab) >= 1:
            if (tab[0].upper()) in gcode_with_notify:
                time_wait = 0
                while notify_gcode == '' and time_wait < notify_timeout:
                    time.sleep(0.1)
                    time_wait += 0.1
                if time_wait >= notify_timeout:
                    return "Timeout lors de la reception du retour"
                
                tmp = notify_gcode
                notify_gcode = ''
                return tmp
            return response.text
    except requests.exceptions.RequestException as e:
        return f"Erreur lors de l'envoi du G-code : {e}"
    
def is_gcode_success(resp):
    return ("{\"result\": \"ok\"}") == resp

def retract(z=0):
    retract_z = z + retraction_distance
    return is_gcode_success(run_gcode(f"G0 Z{retract_z}"))

def draw_line(x=0, y=0, z=0, end_x=10, end_y=0, feed_rate=4500):
    if is_gcode_success(run_gcode(f"G0 X{x} Y{y}")) == True:
        if is_gcode_success(run_gcode(f"G0 Z{z}")) == True:
            if is_gcode_success(run_gcode(f"G0 X{end_x} Y{end_y} F{feed_rate}")) == True:
                return retract(z)
    return False

def main():
    global setup_x, setup_y, setup_z

    x_limit, y_limit = 200, 200

    def home_printer():
        r = input("Would you like to home ? (Y/N) : ")
        if r.upper() == 'Y':
            r = input("Warning: printer is about to go home, continue? (Y/N) : ")
            if r.upper() == 'Y':
                print("Homing...")
                if not is_gcode_success(run_gcode("G28")):
                    print("Stopping program...")
                    return False
        return True

    def calibrate_pen(z):
        r = input("Would you like to calibrate the pen? (Y/N) : ")
        if r.upper() == 'Y':
            y_calibrate = float(setup_y)
            while True:
                draw_line(x=setup_x, y=y_calibrate, end_y=y_calibrate, z=z)
                y_calibrate += 2
                r = input("Need to go higher, lower, or is it good? (H/L/G) : ")
                if r.upper() == 'H':
                    z += 0.1
                elif r.upper() == 'L':
                    z -= 0.1
                else:
                    print(f"Calibrated with z={z}")
                    break
        return z

    def create_limits():
        x_size = 200
        y_size = 200
        r = input("Would you like to create limits? (Y/N) : ")
        if r.upper() == 'Y':
            x_size = int(input("Enter x size: "))
            y_size = int(input("Enter y size: "))
            r = input("Would you like to draw the frame? (Y/N) : ")
            if r.upper() == 'Y':
                draw_line(setup_x, setup_y, setup_z, setup_x + x_size, setup_y)  # Bottom edge
                draw_line(setup_x + x_size, setup_y, setup_z, setup_x + x_size, setup_y + y_size)  # Right edge
                draw_line(setup_x + x_size, setup_y + y_size, setup_z, setup_x, setup_y + y_size)  # Top edge
                draw_line(setup_x, setup_y + y_size, setup_z, setup_x, setup_y)  # Left edge
        return x_size, y_size
    
    def check_xyz_values(line):
        match = re.search(r"X([\d\.]+) Y([\d\.]+) Z([\d\.]+)", line)
        if match:
            match_x = re.search(r"X([\d\.]+)", line)
            match_y = re.search(r"Y([\d\.]+)", line)
            match_z = re.search(r"Z([\d\.]+)", line)
            x_value = float(match_x.group(1)) if match_x else None
            y_value = float(match_y.group(1)) if match_y else None
            z_value = float(match_z.group(1)) if match_z else None

            if x_value is not None and (x_value < setup_x or x_value > (x_limit + setup_x)):
                print(f"Out-of-bounds X detected: X={x_value}")
                return False

            if y_value is not None and (y_value < setup_y or y_value > (y_limit + setup_y)):
                print(f"Out-of-bounds Y detected: Y={y_value}")
                return False

            if z_value is not None and (z_value != 2 and z_value != 6):
                print(f"Out-of-bounds Y detected: Y={y_value}")
                return False

        return True
                
    def draw_from_file():
        file_path = input("Please enter a G-code file path to draw (or type 'exit' to return to menu): ")
        if file_path.lower() == 'exit':
            return
        try:
            print("Starting...\n")
            with open(file_path, 'r') as file:
                for line in file:
                    if not check_xyz_values(line): 
                        r = input("Would you like to continue? (Y/N) : ")
                        if r.upper() == 'N':
                            return
                        
                    line = line.replace("G0", "G")
                    line = line.replace("G ", "G0")
                    line = line.replace("Z6.000000", "Z" + str(setup_z + float(retraction_distance)))
                    line = line.replace("Z2.000000", "Z" + str(setup_z))
                    line = re.sub(r"\(.*?\)", "", line)
                    run_gcode(line)
        except FileNotFoundError:
            print("File not found. Please try again.")
            return

    with open('gcode_notify.txt', 'r', encoding="utf-8") as f:
        gcode_with_notify = f.read()
        init(gcode_with_notify)

    while True:
        print("\nMain Menu:")
        print("1. Home Printer")
        print("2. Insert Pen")
        print("3. Calibrate Pen")
        print("4. Create Limits")
        print("5. Draw from G-code File")
        print("6. Exit")

        choice = input("Please select an option (1-6): ")

        if choice == '1':
            if not home_printer():
                break
        elif choice == '2':
            z = float(setup_z)
            y = float(setup_y)
            x = float(setup_x)
            print(f"Going to ({x}, {y}, {z})")
            if not is_gcode_success(run_gcode(f"G0 X{x} Y{y} Z{z}")):
                print("Stopping program...")
                break
            print("Please insert pen.")
            r = input("Press ENTER when the pen is inserted")
            retract(z)
        elif choice == '3':
            setup_z = calibrate_pen(setup_z)
        elif choice == '4':
            x_limit, y_limit = create_limits()
        elif choice == '5':
            draw_from_file()
        elif choice == '6':
            print("Exiting program...")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()
