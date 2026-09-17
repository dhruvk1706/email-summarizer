import json
import os

STATE_FILE = "state.json"


def load_history_id():
    if not os.path.exists(STATE_FILE):
        return None

    with open(STATE_FILE, "r") as f:
        return json.load(f).get("history_id")


def save_history_id(history_id):
    with open(STATE_FILE, "w") as f:
        json.dump({"history_id": history_id}, f)