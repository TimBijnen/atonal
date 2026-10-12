# config.py - hardware settings. Change these to match your build.

# DAC: 'MCP4725' (breadboard prototype), 'MCP4728' (PCB) or None (no DAC yet).
# If the DAC is not found on I2C, the module still runs (screen only).
DAC_TYPE = 'MCP4725'
DAC_ADDR = 0x60            # MCP4725 is sometimes 0x62: check with i2c.scan()

# Reference voltage of the DAC and gain of the op-amp stage.
# MCP4725 powered from 3V3: 3.3   |   MCP4728 internal reference: 2.048
DAC_VREF = 3.3
GAIN = 2.5                 # trim RV1 so the octaves are in tune

# The transistor output stages invert: Pico pin high = jack low.
INVERT_OUTPUTS = True
TRIG_MS = 10               # length of the TRIG and END pulses

# Screen: the background is meant to be near-black. Some ST7796 panels show
# every colour inverted (a white background, a blue highlight instead of
# orange). For those, set True. AliExpress module: False. TinyTronics module
# (showed a white background): try True.
LCD_INVERT = False

# Encoder: most EC11 / KY-040 give 4 steps per click. If one click moves
# two items, set 2. If turning right goes the wrong way, set ENC_REVERSE.
ENC_STEPS = 4
ENC_REVERSE = False

# Pins (GPIO numbers, see the schematic)
PIN_CLK_IN = 2
PIN_RST_IN = 3
PIN_SDA = 4
PIN_SCL = 5
PIN_SW_DIR = 6
PIN_SW_MODE = 7
PIN_ENC_SW = 8
PIN_GATE = 10
PIN_TRIG = 11
PIN_END = 12
PIN_ENC_A = 13
PIN_ENC_B = 14
