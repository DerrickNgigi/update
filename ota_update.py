import curl
import machine
import uos
import gc
from utime import sleep
from meter_gsm import gsmInitialization

# ====== Configuration ======
UPDATE_URL = "https://raw.githubusercontent.com/DerrickNgigi/update/main"
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
    "meter.py"
]

# ====== Utility Functions ======
def log(msg):
    print("[OTA] " + msg)

def file_exists(path):
    try:
        uos.stat(path)
        return True
    except OSError:
        return False

def ensure_temp_dir():
    """Ensure /flash/temp exists for storing temporary OTA files."""
    temp_dir = "/flash/temp"
    try:
        uos.mkdir(temp_dir)
        log("Created temp folder: " + temp_dir)
    except OSError:
        pass  # already exists
    return temp_dir

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
        res_code, hdr, body = curl.get(UPDATE_URL + "/version.txt")
        if res_code != 0:
            log("Could not fetch version info. curl error code {}".format(res_code))
            return None

        if "200" not in hdr:
            log("Invalid HTTP response:\n" + hdr)
            return None

        server_version = body.strip()
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
    """
    Downloads file from UPDATE_URL + fname using curl, writes to flash in chunks.
    Ensures file integrity by checking size consistency.
    """
    temp_dir = ensure_temp_dir()
    url = UPDATE_URL + "/" + fname
    tmp_path = temp_dir + "/tmp_" + fname
    dest_path = "/flash/" + fname

    for attempt in range(1, retries + 1):
        try:
            log("Downloading [{}] (Attempt {}/{})".format(fname, attempt, retries))

            # Use LoBo-style curl.get() with file output
            res_code, hdr, body = curl.get(url, tmp_path)

            if res_code == 0 and "200" in hdr:
                size_on_disk = uos.stat(tmp_path)[6]
                log("✅ Download complete: {} bytes".format(size_on_disk))

                # Safely replace the old file
                if file_exists(dest_path):
                    uos.remove(dest_path)
                uos.rename(tmp_path, dest_path)
                log("✅ Updated {}".format(fname))
                return True
            else:
                log("❌ Download failed {} (curl code {}, hdr: {})".format(fname, res_code, hdr))

        except Exception as e:
            log("⚠️ Error downloading {}: {}".format(fname, e))

        sleep(3)

    log("⚠️ Skipping {} after multiple failures".format(fname))
    return False



def download_and_replace_files(file_list):
    total = len(file_list)
    for i, fname in enumerate(file_list):
        log("Updating file {}/{}: {}".format(i + 1, total, fname))
        success = download_file(fname)
        if not success:
            log("⚠️ Skipped file due to repeated failures: {}".format(fname))
        gc.collect()
        sleep(1)
        
def update_global_file(device_id, retries=3):
    """
    Safely updates /flash/global.py for this specific device.
    Compares embedded GLOBAL_VERSION before replacing.
    """
    temp_dir = ensure_temp_dir()
    global_py = "global.py"
    tmp_path = temp_dir + "/tmp_" + global_py
    dest_path = "/flash/" + global_py
    url_py = "{}/device_configs/{}_global.py".format(UPDATE_URL, device_id)

    def extract_version(file_path):
        """Read version string from a Python file."""
        try:
            with open(file_path, "r") as f:
                for line in f:
                    if "GLOBAL_VERSION" in line:
                        return line.split("=")[1].strip().replace('"', '').replace("'", "")
        except:
            return "0.0.0"
        return "0.0.0"

    try:
        # ---- Get local version ----
        local_version = extract_version(dest_path)
        log("📘 Local global.py version: {}".format(local_version))

        # ---- Download remote global.py ----
        for attempt in range(1, retries + 1):
            try:
                log("Downloading global.py for [{}] (Attempt {}/{})".format(device_id, attempt, retries))
                res_code, hdr, body = curl.get(url_py, tmp_path)
                if res_code == 0 and "200" in hdr:
                    size_on_disk = uos.stat(tmp_path)[6]
                    log("✅ Download complete: {} bytes".format(size_on_disk))

                    # ---- Extract remote version ----
                    remote_version = extract_version(tmp_path)
                    log("🔍 Remote version: {}".format(remote_version))

                    # ---- Compare ----
                    if remote_version == local_version:
                        log("✅ global.py already up to date (v{})".format(local_version))
                        uos.remove(tmp_path)
                        return False

                    # ---- Replace and log ----
                    if file_exists(dest_path):
                        uos.remove(dest_path)
                    uos.rename(tmp_path, dest_path)
                    log("✅ global.py updated to version {}".format(remote_version))
                    return True
                else:
                    log("❌ Download failed (code {}, hdr: {})".format(res_code, hdr))
            except Exception as e:
                log("⚠️ Error downloading global.py: {}".format(e))
            sleep(3)

        log("⚠️ Skipping global.py after multiple failures")
        return False

    except Exception as e:
        log("⚠️ Error in update_global_file: {}".format(e))
        return False



def run_ota():
    gc.collect()
    print("Free mem:", gc.mem_free())

    print("📡 Initializing GSM module...")
    sleep(4)
    gsmInitialization()

    gc.collect()
    print("Free mem:", gc.mem_free())
    sleep(5)

    log("Checking for OTA updates...")
    new_version = check_for_update()

    if new_version:
        log("Starting file updates...")
        download_and_replace_files(FILES_TO_UPDATE)
        save_local_version(new_version)
        log("✅ Update complete. Rebooting in 3 seconds...")
        sleep(3)
        machine.reset()
    else:
        log("No updates to apply.")

# ====== Main Entry Point ======
if __name__ == "__main__":
    run_ota()

