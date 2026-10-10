import socket
import machine
import time
import sys
import gsm
import globals
import _thread

SIM800L_IP5306_VERSION_20190610 = 0
SIM800L_AXP192_VERSION_20200327 = 1
SIM800C_AXP192_VERSION_20200609 = 2
SIM800L_IP5306_VERSION_20200811 = 3


# Please change to the version you use here, the default version is IP5306
board_type = SIM800L_IP5306_VERSION_20200811


# APN credentials (replace with yours)
GSM_APN = globals.GSM_APN
GSM_USER = globals.GSM_USER
GSM_PASS = globals.GSM_PASS

UART_BAUD = 115200

# defaule use SIM800L_IP5306_VERSION_20190610
MODEM_POWER_PIN = 23
#MODEM_RST = 5
MODEM_PWRKEY_PIN = 4
MODEM_TX = 27
MODEM_RX = 26
LED_PIN = 13

# Independent outer deadline for the whole of gsmInitialization(). Field
# evidence (bench trace, 2026-10-03): the native gsm.start()/connect() call
# can block for an unbounded time inside its own C-level AT handshake - it
# restarts the ENTIRE sequence from scratch on any AT+CREG? response other
# than "registered" (0,1), including 0,2 ("searching"), which is a normal,
# temporary state during real-world registration. On a bench run this
# looped 5 times (~15s) before landing; on weak/slow signal in the field
# there is no evidence it is bounded at all. Because this loop lives inside
# a blocking native call, our own Python-level retry/timeout logic never
# gets a chance to run until that call itself returns - which may be never.
# This timer is the only thing that can still force a recovery in that case.
GSM_INIT_DEADLINE_MS = getattr(globals, 'GSM_INIT_DEADLINE_MS', 180000)  # 3 min

# Background-thread watchdog, not machine.Timer: two separate Timer attempts
# on this exact bench hardware both failed before even reaching the code
# being guarded - Timer(-1) ("auto-assign", valid on mainline MicroPython)
# raised "Only base timers 0~3 and extended timers 4~11 can be used", and
# the suggested-looking fix Timer(4) then raised "Timer 0 not configured as
# extended timer" - this LoBo port's Timer API needs some undocumented setup
# step we don't have a reference for. _thread, by contrast, is already
# proven working on this exact board: main.py's own supervisor_thread() uses
# the identical shared-tick-variable pattern below for the same "force a
# reset if nothing checks in in time" purpose, continuously, for every
# connected session observed on the bench. Reusing a pattern this codebase
# already trusts beats guessing further at an unfamiliar native API.
_gsm_init_done = True

def _gsm_watchdog_thread(deadline_ms):
    waited_ms = 0
    step_ms = 250
    while waited_ms < deadline_ms:
        if _gsm_init_done:
            return  # gsmInitialization() returned normally - stand down
        time.sleep_ms(step_ms)
        waited_ms += step_ms
    if not _gsm_init_done:
        print("[WATCHDOG] GSM init exceeded {}ms deadline - forcing reset".format(deadline_ms))
        machine.reset()

def gsmInitialization():
    # Power on the GSM module
    global MODEM_RST

    GSM_POWER = machine.Pin(MODEM_POWER_PIN, machine.Pin.OUT)
    GSM_POWER.value(1)

    LED = machine.Pin(LED_PIN, machine.Pin.OUT)
    LED.value(1)

    if True:
        MODEM_RST = machine.Pin(5, machine.Pin.OUT)
        MODEM_RST.value(1)

    GSM_PWR = machine.Pin(MODEM_PWRKEY_PIN, machine.Pin.OUT)
    GSM_PWR.value(1)
    time.sleep_ms(200)
    GSM_PWR.value(0)
    time.sleep_ms(1000)
    GSM_PWR.value(1)

    # Init PPPoS

    gsm.debug(True)  # Uncomment this to see more logs, investigate issues, etc.

    # Armed before the blocking calls below: whatever happens inside
    # gsm.start()/gsm.connect()/the status-wait loop, including a hang
    # inside the native driver itself, this fires and forces a reset if
    # nothing has returned control to us within the deadline. Disarmed in
    # the `finally` on any normal return path.
    global _gsm_init_done
    _gsm_init_done = False
    try:
        _thread.start_new_thread(_gsm_watchdog_thread, (GSM_INIT_DEADLINE_MS,))
    except TypeError:
        _thread.start_new_thread("GsmWatchdog", _gsm_watchdog_thread, (GSM_INIT_DEADLINE_MS,))

    try:
        gsm.start(tx=MODEM_TX, rx=MODEM_RX, apn=GSM_APN,
                  user=GSM_USER, password=GSM_PASS, roaming=True)

        for retry in range(20):
            if gsm.atcmd('AT'):
                break
            else:
                sys.stdout.write('.')
                time.sleep_ms(5000)
        else:
            #raise Exception("Modem not responding!")
            print("Modem not responding!")
            machine.reset()
        print()

        print("Connecting to GSM...")
        gsm.connect()

        # Bounded like the AT-command retry above: previously
        # `while gsm.status()[0] != 1: pass` could spin forever with no
        # way out if status never reached 1. Still backstopped by the
        # watchdog thread above in case this doesn't even get polled often
        # enough to notice (e.g. status() itself blocks).
        for retry in range(min(600, GSM_INIT_DEADLINE_MS // 500)):
            if gsm.status()[0] == 1:
                break
            time.sleep_ms(500)
        else:
            print("GSM status never reached connected - resetting")
            machine.reset()

        print('IP:', gsm.ifconfig()[0])
        # GSM connection is complete.
        # You can now use modules like urequests, uPing, etc.
        # Let's try socket API:
        print("Connected !")
    finally:
        _gsm_init_done = True

def gsmCheckStatus():
    gsmconnectivity = gsm.status()[0]
    return gsmconnectivity