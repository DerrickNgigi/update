import time
import os
import json

# Directory for storing target readings
TARGET_DIR = '/flash/mem'

# ========== Persistent Storage Functions ==========

def save_target_reading(address, value):
    """
    Save target reading for a specific device to its own JSON file.
    Example file: /flash/mem/target_13.json => {"13": 789}
    """
    try:
        # Ensure storage directory exists
        if "mem" not in os.listdir("/flash"):
            os.mkdir(TARGET_DIR)

        filename = TARGET_DIR + "/target_" + str(address) + ".json"
        data = {str(address): value}

        with open(filename, 'w') as f:
            json.dump(data, f)

        print("✔ Target reading saved for address %s: %s" % (address, value))

    except Exception as e:
        print("❌ Failed to save target reading for address %s: %s" % (address, str(e)))


def load_target_reading(address):
    """
    Load target reading for a specific device from its own file.
    Returns None if the file or value doesn't exist.
    """
    try:
        filename = TARGET_DIR + "/target_" + str(address) + ".json"

        try:
            os.stat(filename)
        except OSError:
            print("⚠ No saved target reading file found for address %s." % address)
            return None

        with open(filename, 'r') as f:
            data = json.load(f)

        value = data.get(str(address))
        if value is not None:
            print("📦 Loaded target reading for address %s: %s" % (address, value))
            return value
        else:
            print("⚠ No target reading found in file for address %s." % address)
            return None

    except Exception as e:
        print("❌ Failed to load target reading for address %s: %s" % (address, str(e)))
        return None


def init_target_reading(address, default_value=45):
    """
    Initialize target reading with default if none exists.
    """
    value = load_target_reading(address)
    if value is None:
        print("🔧 Setting default target reading for address %s: %s" % (address, default_value))
        save_target_reading(address, default_value)
        return default_value
    return value


# ========== Billing Mode & Postpaid Period Storage ==========

def _ensure_dir():
    if "mem" not in os.listdir("/flash"):
        os.mkdir(TARGET_DIR)

def _save_json(filename, data):
    try:
        _ensure_dir()
        with open(filename, 'w') as f:
            json.dump(data, f)
        return True
    except Exception as e:
        print("Save failed %s: %s" % (filename, str(e)))
        return False

def _load_json(filename):
    try:
        os.stat(filename)
        with open(filename, 'r') as f:
            return json.load(f)
    except Exception:
        return None

def save_billing_mode(address, mode):
    """mode: 'prepaid' or 'postpaid'"""
    return _save_json(TARGET_DIR + "/mode_" + str(address) + ".json", {"mode": mode})

def load_billing_mode(address):
    data = _load_json(TARGET_DIR + "/mode_" + str(address) + ".json")
    if data and data.get("mode") == "postpaid":
        return "postpaid"
    return "prepaid"

def save_postpaid_period(address, start_ts, start_reading):
    return _save_json(TARGET_DIR + "/post_" + str(address) + ".json",
                      {"ts": start_ts, "vol": start_reading})

def load_postpaid_period(address):
    """Returns (start_ts, start_reading) or None."""
    data = _load_json(TARGET_DIR + "/post_" + str(address) + ".json")
    if data and "ts" in data and "vol" in data:
        return data["ts"], data["vol"]
    return None

def clear_postpaid_period(address):
    try:
        os.remove(TARGET_DIR + "/post_" + str(address) + ".json")
    except OSError:
        pass
