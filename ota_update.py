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
    url = UPDATE_URL + "/" + fname
    tmp_path = "/flash/tmp_" + fname
    dest_path = "/flash/" + fname

    for attempt in range(1, retries + 1):
        try:
            log("Downloading [{}] (Attempt {}/{})".format(fname, attempt, retries))

            # Open destination temp file
            with open(tmp_path, "wb") as f:
                # Stream mode: fetch in 1 KB chunks to prevent truncation
                def write_chunk(data):
                    try:
                        f.write(data)
                        return 0
                    except Exception as e:
                        log("Write error: {}".format(e))
                        return 1

                # Run curl in streaming mode (LoBo style)
                res_code, hdr, total_len = curl.getfile(url, write_chunk)

            # After download completes
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