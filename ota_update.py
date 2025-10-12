import urequests
import machine
import time
import os

# ====== Configuration ======
UPDATE_URL = "https://pamwkbwyzgmwnsfbsucz.supabase.co/storage/v1/object/public/residential"
VERSION_FILE = "/flash/version.txt"

FILES_TO_UPDATE = [
    "boot.py",
    "main_meter.py",
    "main.py",
    "meter_gsm.py",
    "meter_mqtts.py",
    "meter_run.py",
    "meter_sim.py",
    "meter_storage.py",
    "meter_tests.py",
    "meter.py",
    "ota_update.py",
    "target_readings.json",
    "README.md"
]

# ====== Utility Functions ======
def log(msg):
    print("[OTA] " + msg)

def get_local_version():
    try:
        with open(VERSION_FILE, "r") as f:
            return f.read().strip()
    except:
        return "0.0.0"

def save_local_version(version):
    try:
        with open(VERSION_FILE, "w") as f:
            f.write(version)
        log("Local version updated to " + version)
    except Exception as e:
        log("Failed to write version file: {}".format(e))

# ====== OTA Logic ======
def check_for_update():
    try:
        res = urequests.get(UPDATE_URL + "/version.txt")
        if res.status_code != 200:
            log("Could not fetch version info. HTTP " + str(res.status_code))
            res.close()
            return None

        server_version = res.text.strip()
        res.close()

        local_version = get_local_version()
        if server_version != local_version:
            log("New version available: {} (local {})".format(server_version, local_version))
            return server_version
        else:
            log("Device is up to date.")
            return None
    except Exception as e:
        log("Error checking for update: {}".format(e))
        return None

def download_file(fname, retries=3):
    url = UPDATE_URL + "/" + fname
    for attempt in range(1, retries + 1):
        try:
            log("Downloading [{}] (Attempt {}/{})".format(fname, attempt, retries))
            res = urequests.get(url)
            if res.status_code == 200:
                tmp_path = "/flash/tmp_" + fname
                with open(tmp_path, "wb") as f:
                    f.write(res.content)
                res.close()

                # Replace old file safely
                dest_path = "/flash/" + fname
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                os.rename(tmp_path, dest_path)
                log("Updated {}".format(fname))
                return True
            else:
                log("Failed to download {} (HTTP {})".format(fname, res.status_code))
                res.close()
        except Exception as e:
            log("Error downloading {}: {}".format(fname, e))
        time.sleep(1)
    return False

def download_and_replace_files(file_list):
    for i, fname in enumerate(file_list):
        log("Updating file {}/{}: {}".format(i + 1, len(file_list), fname))
        success = download_file(fname)
        if not success:
            log("⚠️ Skipping {} after multiple failures".format(fname))

def run_ota():
    log("Checking for OTA updates...")
    new_version = check_for_update()
    if new_version:
        log("Starting file updates...")
        download_and_replace_files(FILES_TO_UPDATE)
        save_local_version(new_version)
        log("✅ Update complete. Rebooting in 3 seconds...")
        time.sleep(3)
        machine.reset()
    else:
        log("No updates to apply.")

# ====== Main Entry Point ======
if __name__ == "__main__":
    run_ota()
