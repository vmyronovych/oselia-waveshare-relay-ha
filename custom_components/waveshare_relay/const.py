"""Constants for the Waveshare Modbus RTU Relay integration.

The Modbus wire contract here matches Waveshare's "Protocol Manual of Modbus RTU
Relay" (https://www.waveshare.com/wiki/Protocol_Manual_of_Modbus_RTU_Relay) and works
for the whole relay family (4/8/16/32-ch) since they share one protocol:

  - Read relay states  : function 0x01 (read coils) from coil 0x0000, count = channels
  - Set a single relay : function 0x05 (write coil) at coil <channel> -> 0xFF00 / 0x0000
  - Set ALL relays     : function 0x05 (write coil) at coil 0x00FF -> 0xFFFF / 0x0000
  - Set device address : function 0x06 (write register) at 0x4000  (range 1..255)
  - Set baud rate      : function 0x06 (write register) at 0x2000  (code, see BAUD_RATES)
  - Read sw version    : function 0x03 (read register)  at 0x2000  (value / 100 = vX.YZ)
  - Read device address: function 0x03 (read register)  at 0x4000  (broadcast on addr 0)
"""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "waveshare_relay"
MANUFACTURER = "Waveshare"
DEFAULT_MODEL = "Modbus RTU Relay"

# --- config-entry / option keys ---
CONF_TYPE = "type"                # transport: TYPE_SERIAL or TYPE_TCP
CONF_PORT = "port"                # serial: device path
CONF_BAUDRATE = "baudrate"        # serial: bus baud rate
CONF_HOST = "host"                # tcp: gateway / bridge host
CONF_TCP_PORT = "tcp_port"        # tcp: gateway / bridge port
CONF_FRAMER = "framer"            # tcp: FRAMER_RTU (socat/transparent) or FRAMER_SOCKET
CONF_DEVICES = "devices"          # list[ {address, name, channels} ] on the bus
CONF_ADDRESS = "address"          # Modbus slave address of one board
CONF_NAME = "name"
CONF_CHANNELS = "channels"
CONF_SCAN_INTERVAL = "scan_interval"

# --- roller-shutter cover keys ---
# A cover pairs two coils on ONE board (address) into a native `cover` entity.
CONF_COVERS = "covers"            # list[ cover-config dict ] on the bus
CONF_ID = "id"                    # stable per-cover uuid (survives rename/reorder)
CONF_UP_CHANNEL = "up_channel"    # 0-based coil that drives the motor OPEN
CONF_DOWN_CHANNEL = "down_channel"  # 0-based coil that drives the motor CLOSE
CONF_UP_TRAVEL_TIME = "up_travel_time"      # seconds, full close -> full open (0 = uncalibrated)
CONF_DOWN_TRAVEL_TIME = "down_travel_time"  # seconds, full open -> full close

# transport types
TYPE_SERIAL = "serial"
TYPE_TCP = "tcp"
# tcp framing: RTU-over-TCP (socat raw / "transparent" gateways) vs Modbus-TCP (MBAP)
FRAMER_RTU = "rtu"
FRAMER_SOCKET = "socket"

DEFAULT_BAUDRATE = 9600           # Waveshare factory default
DEFAULT_ADDRESS = 1               # Waveshare factory default
DEFAULT_CHANNELS = 8              # the (B) variant
DEFAULT_SCAN_INTERVAL = 10        # seconds between coil-state polls
DEFAULT_TCP_PORT = 502
DEFAULT_FRAMER = FRAMER_RTU
MIN_ADDRESS = 1
MAX_ADDRESS = 255

CHANNEL_OPTIONS = [4, 8, 16, 32]

# baud-rate register code (REG_BAUD) -> bits per second, per the protocol manual.
BAUD_RATES: dict[int, int] = {
    0: 4800,
    1: 9600,
    2: 19200,
    3: 38400,
    4: 57600,
    5: 115200,
    6: 128000,
    7: 256000,
}
# inverse, for the config flow / service (bps -> code)
BAUD_CODES: dict[int, int] = {bps: code for code, bps in BAUD_RATES.items()}

# --- Modbus addresses (see module docstring) ---
COIL_FIRST = 0x0000               # first relay coil
COIL_ALL = 0x00FF                 # write-only "all relays" coil
REG_BAUD = 0x2000                 # baud-rate register / software-version register
REG_ADDRESS = 0x4000             # device-address register
BROADCAST_ADDRESS = 0x00          # read a lone device's address with this

PLATFORMS = [
    Platform.SWITCH,
    Platform.COVER,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.BUTTON,
]

# --- services ---
SERVICE_PULSE = "pulse"
SERVICE_ALL_ON = "all_on"
SERVICE_ALL_OFF = "all_off"
SERVICE_SET_ADDRESS = "set_device_address"
SERVICE_SET_BAUD_RATE = "set_baud_rate"

ATTR_DURATION = "duration"
ATTR_INVERT = "invert"
ATTR_NEW_ADDRESS = "new_address"
ATTR_BAUD_RATE = "baud_rate"

DEFAULT_PULSE_DURATION = 0.5      # seconds

# --- roller-shutter safety / timing ---
# Break-before-make: pause after de-energizing one coil before energizing the other on
# a direction reversal, so the motor/capacitor never sees an instant reversal even if a
# board's own interlock ever failed. Defense-in-depth on top of the HW interlock.
REVERSAL_PAUSE = 0.6              # seconds
# Max-run cutoff: de-energize this many seconds past the expected travel time so a lost
# "stop" (missed event, crash mid-move) can never leave a motor powered indefinitely.
MAX_RUN_MARGIN = 3.0             # seconds added to the calibrated travel time
# Hard cap used when travel time is not yet calibrated (no position estimate available).
DEFAULT_MAX_RUN = 120.0          # seconds
# How often to push a position update to the UI while the cover is moving.
POSITION_UPDATE_INTERVAL = 1.0   # seconds

# --- dispatcher signals ---
# Fired (per entry) when the bus link goes up/down -- refreshes availability entities.
SIGNAL_CONNECTION = DOMAIN + "_connection_{}"
