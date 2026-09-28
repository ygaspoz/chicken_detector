#!/bin/bash

# 1. Run python script to get the target time (e.g. "19:47")
TARGET_TIME=$(/home/yann/chicken_detector/.venv/Scripts/python.exe /home/yann/chicken_detector/get_closing_time.py | grep -oE '[0-9]{2}:[0-9]{2}')

if [ -z "$TARGET_TIME" ]; then
    echo "Error: Could not retrieve target time."
    exit 1
fi

echo "Scheduling target_script.py for $TARGET_TIME"

# 2. Pipe the execution command into the `at` daemon
echo "/home/yann/chicken_detector/.venv/Scripts/python.exe /home/yann/chicken_detector/run_detection.py" | at "$TARGET_TIME"