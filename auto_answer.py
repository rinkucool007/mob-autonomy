#!/usr/bin/env python3
"""
Auto-answer incoming calls on an Android phone connected via ADB:
answer -> press 2 -> press 3 -> hang up.

Requires: adb installed and phone connected with USB debugging enabled
(adb devices should list it as 'device', not 'unauthorized').
"""

import subprocess
import re
import time

# ---- tweak these delays if your carrier/device is slower to connect ----
POLL_INTERVAL = 1.0          # seconds between checks for a ringing call
DELAY_AFTER_ANSWER = 2.0     # wait for the call to actually connect before sending DTMF
DELAY_BETWEEN_DIGITS = 0.7   # gap between pressing "2" and "3"
DELAY_BEFORE_HANGUP = 1.0    # wait after last digit before ending the call
DEVICE_SERIAL = None         # set to a serial string if you have multiple devices connected
# --------------------------------------------------------------------------

def adb(*args):
    cmd = ["adb"]
    if DEVICE_SERIAL:
        cmd += ["-s", DEVICE_SERIAL]
    cmd += list(args)
    return subprocess.run(cmd, capture_output=True, text=True)

def get_call_state():
    """Returns 0 (idle), 1 (ringing), 2 (offhook/active), or None if it couldn't be read."""
    result = adb("shell", "dumpsys", "telephony.registry")
    if result.returncode != 0:
        return None
    match = re.search(r"mCallState=(\d+)", result.stdout)
    if match:
        return int(match.group(1))
    return None

def keyevent(code):
    adb("shell", "input", "keyevent", code)

def handle_call():
    print("Incoming call detected -> answering")
    keyevent("KEYCODE_CALL")  # answer

    time.sleep(DELAY_AFTER_ANSWER)
    print("Sending DTMF: 2")
    keyevent("KEYCODE_2")

    time.sleep(DELAY_BETWEEN_DIGITS)
    print("Sending DTMF: 3")
    keyevent("KEYCODE_3")

    time.sleep(DELAY_BEFORE_HANGUP)
    print("Hanging up")
    keyevent("KEYCODE_ENDCALL")

def main():
    print("Watching for incoming calls (Ctrl+C to stop)...")
    last_state = None
    while True:
        state = get_call_state()
        if state == 1 and last_state != 1:
            handle_call()
            # wait for state to drop back to idle before resuming watch
            while get_call_state() != 0:
                time.sleep(POLL_INTERVAL)
        last_state = state
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")