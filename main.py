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

        if (gcode.split()[0].upper()) in gcode_with_notify:
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
    retract_z = z + 3
    return is_gcode_success(run_gcode(f"G0 Z{retract_z}"))

def draw_line(x=0, y=0, z=0, x_size=10, y_size=0):
    if is_gcode_success(run_gcode(f"G0 X{x} Y{y} Z{z}")) == True:
        if is_gcode_success(run_gcode(f"G0 X{x + x_size} X{y + y_size} F4500")) == True:
            return retract(z)
    return False

def main():
    with open('gcode_notify.txt', 'r', encoding="utf-8") as f:
        gcode_with_notify = f.read()
        init(gcode_with_notify)
    
    r = input("Warning printer is about to go home, continue ? (Y/N) : ")

    if r != 'Y':
        print("stoping program...")
        return
    
    # go home
    print("homing...")
    if not is_gcode_success(run_gcode("G28")):
        print("stoping program...")
        return
    
    z = 3
    print(f"going to (0, 0, {z})")
    if not is_gcode_success(run_gcode(f"G0 X0 Y0 Z{z}")):
        print("stoping program...")
        return
    
    print("Please insert pen")

    r = input("Would you like to calibrate pen ? (Y/N) : ")

    retract(z)

    if r == 'Y':
        y = 0
        while True:
            draw_line(y=y,z=z)
            y += 2
            r = input("Need to go higher or lower or good ? : (H/L/G)")
            if r == 'H':
                z += 0.1
            elif r == 'L':
                z -= 0.1
            else:
                print(f"Calibrated with z={z}")
                break
    
    r = input("Would you like to create limits ? (Y/N) : ")

    x_size = 200
    y_size = 200
    if r == 'Y':
        x_size = int(input("enter x size : "))
        y_size = int(input("enter y size : "))

    r = input("Would you like to draw frame ? (Y/N) : ")
    if r == 'Y':
        draw_line(0, 0, z, x_size, 0)
        draw_line(0, 0, z, 0, y_size)
        draw_line(0, y_size, z, x_size, 0)
        draw_line(x_size, 0, z, 0, y_size)
    
    while True:
        r = input("Please enter a gcode file path to draw : ")
        with open(r, 'r') as file:
            for line in file:
                line = line.replace("G0", "G")
                line = line.replace("Z6", "Z" + z + 3)
                line = line.replace("Z1", "Z" + z)
                line = re.sub(r"\(.*?\)", "", line)
                run_gcode(line)
    
    return


if __name__ == '__main__':
    main()