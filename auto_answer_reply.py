#!/usr/bin/env python3
"""
Auto-answer incoming calls on an Android phone via ADB, then:
  1. Answer
  2. Tap the "Speaker" button
  3. Tap the "Keypad"/"Dialpad" button
  4. Press 2, then 3 (DTMF)
  5. Play a "Thanks for call me" message out loud (through the speaker,
     picked up by the mic since speakerphone is on)
  6. Hang up

Requires:
  - adb installed and phone connected with USB debugging authorized
  - A pre-generated audio file for the spoken message pushed to the phone
    (see generate_tts() below, uses pyttsx3 — offline, no API key needed:
    pip install pyttsx3)
"""

import subprocess
import re
import time
import os

# ---------------- CONFIG ----------------
POLL_INTERVAL = 1.0
DELAY_AFTER_ANSWER = 2.0        # let the call connect before touching the UI
DELAY_AFTER_SPEAKER_TAP = 1.0
DELAY_AFTER_KEYPAD_TAP = 1.0
DELAY_BETWEEN_DIGITS = 0.7
DELAY_BEFORE_MESSAGE = 1.0
DELAY_BEFORE_HANGUP = 1.0
DEVICE_SERIAL = None             # set if you have more than one device attached

MESSAGE_TEXT = "Thanks for calling me"
LOCAL_AUDIO_FILE = "thanks_message.m4a"          # your existing file
REMOTE_AUDIO_PATH = "/sdcard/thanks_message.m4a"  # pushed to the phone

# Fallback tap coordinates, used when uiautomator can't read the call screen
# (very common — many dialers mark the in-call screen FLAG_SECURE, which blocks
# uiautomator/screenshot capture entirely). Find these once with scrcpy or by
# trial-and-error (see notes below), then set them here. Leave as None to skip
# a tap if not calibrated yet.
SPEAKER_COORDS = None   # e.g. (200, 1400)
KEYPAD_COORDS = None    # e.g. (540, 1400)
# -----------------------------------------


def adb(*args, timeout=10):
    cmd = ["adb"]
    if DEVICE_SERIAL:
        cmd += ["-s", DEVICE_SERIAL]
    cmd += list(args)
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"  (adb command timed out: {' '.join(args)})")
        return subprocess.CompletedProcess(cmd, returncode=-1, stdout="", stderr="timeout")


def get_call_state():
    result = adb("shell", "dumpsys", "telephony.registry")
    if result.returncode != 0:
        return None
    match = re.search(r"mCallState=(\d+)", result.stdout)
    return int(match.group(1)) if match else None


def keyevent(code):
    adb("shell", "input", "keyevent", code)


def dump_ui():
    """Pulls the current screen's UI hierarchy as XML text. Returns "" if it
    can't be read (common on the in-call screen — many dialers set FLAG_SECURE,
    which blocks uiautomator from capturing it)."""
    dump_result = adb("shell", "uiautomator", "dump", "/sdcard/window_dump.xml", timeout=6)
    if dump_result.returncode != 0:
        return ""
    result = adb("shell", "cat", "/sdcard/window_dump.xml", timeout=6)
    return result.stdout or ""


def find_and_tap(label_keywords, fallback_coords=None):
    """
    Searches the current UI dump for a node whose text or content-desc
    matches one of the given keywords (case-insensitive) and taps its center.
    If the dump can't be read (e.g. FLAG_SECURE call screen) and fallback_coords
    is set, taps that fixed (x, y) instead. Returns True if a tap was sent.
    """
    xml = dump_ui()
    if xml:
        nodes = re.findall(r'<node[^>]*/>', xml)
        for node in nodes:
            text_match = re.search(r'text="([^"]*)"', node)
            desc_match = re.search(r'content-desc="([^"]*)"', node)
            label = ((text_match.group(1) if text_match else "") + " " +
                     (desc_match.group(1) if desc_match else "")).lower()
            if any(kw in label for kw in label_keywords):
                bounds_match = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
                if bounds_match:
                    x1, y1, x2, y2 = map(int, bounds_match.groups())
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    adb("shell", "input", "tap", str(cx), str(cy))
                    return True

    if fallback_coords:
        print(f"  (UI dump unavailable — using fixed coordinates {fallback_coords})")
        adb("shell", "input", "tap", str(fallback_coords[0]), str(fallback_coords[1]))
        return True

    return False


def push_audio_if_needed():
    if not os.path.exists(LOCAL_AUDIO_FILE):
        print(f"WARNING: {LOCAL_AUDIO_FILE} not found locally — run generate_tts() first.")
        return False
    adb("push", LOCAL_AUDIO_FILE, REMOTE_AUDIO_PATH)
    return True


def play_message():
    """Opens the audio file with the default player so it plays out loud."""
    adb("shell", "am", "start", "-a", "android.intent.action.VIEW",
        "-d", f"file://{REMOTE_AUDIO_PATH}", "-t", "audio/mp4")


def generate_tts():
    """Generate the spoken message locally with pyttsx3 (offline TTS)."""
    import pyttsx3
    engine = pyttsx3.init()
    engine.save_to_file(MESSAGE_TEXT, LOCAL_AUDIO_FILE)
    engine.runAndWait()
    print(f"Generated {LOCAL_AUDIO_FILE}")


def handle_call():
    print("Incoming call -> answering")
    keyevent("KEYCODE_CALL")
    time.sleep(DELAY_AFTER_ANSWER)

    print("Tapping Speaker")
    if not find_and_tap(["speaker"], fallback_coords=SPEAKER_COORDS):
        print("  (couldn't find or tap a Speaker button — continuing anyway)")
    time.sleep(DELAY_AFTER_SPEAKER_TAP)

    print("Tapping Keypad/Dialpad")
    if not find_and_tap(["keypad", "dialpad", "dial pad"], fallback_coords=KEYPAD_COORDS):
        print("  (couldn't find or tap a Keypad button — continuing anyway)")
    time.sleep(DELAY_AFTER_KEYPAD_TAP)

    print("Sending DTMF: 2")
    keyevent("KEYCODE_2")
    time.sleep(DELAY_BETWEEN_DIGITS)

    print("Sending DTMF: 3")
    keyevent("KEYCODE_3")
    time.sleep(DELAY_BEFORE_MESSAGE)

    print("Playing message")
    play_message()
    # give the message time to actually play — adjust to match its length
    time.sleep(4.0)

    time.sleep(DELAY_BEFORE_HANGUP)
    print("Hanging up")
    keyevent("KEYCODE_ENDCALL")


def main():
    push_audio_if_needed()
    print("Watching for incoming calls (Ctrl+C to stop)...")
    last_state = None
    while True:
        state = get_call_state()
        if state == 1 and last_state != 1:
            handle_call()
            while get_call_state() != 0:
                time.sleep(POLL_INTERVAL)
        last_state = state
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()