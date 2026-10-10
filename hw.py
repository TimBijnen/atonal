# hw.py - inputs and outputs: encoder, button, clock/reset, toggles, DAC, gates
from machine import Pin, I2C
import machine
import time
import config


class Encoder:
    # quadrature table: (old state << 2 | new state) -> -1, 0, +1
    _T = (0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0)

    def __init__(self, a, b):
        self.a = Pin(a, Pin.IN, Pin.PULL_UP)
        self.b = Pin(b, Pin.IN, Pin.PULL_UP)
        self.state = (self.a.value() << 1) | self.b.value()
        self.acc = 0
        for p in (self.a, self.b):
            p.irq(self._irq, Pin.IRQ_RISING | Pin.IRQ_FALLING)

    def _irq(self, _):
        s = (self.a.value() << 1) | self.b.value()
        self.acc += self._T[(self.state << 2) | s]
        self.state = s

    def delta(self):
        """Clicks turned since the last call (+ = clockwise)."""
        irq = machine.disable_irq()
        steps = config.ENC_STEPS
        d = int(self.acc / steps)
        self.acc -= d * steps
        machine.enable_irq(irq)
        return -d if config.ENC_REVERSE else d


class Button:
    """Encoder push. poll() returns 'click', 'long' (held 0.7 s) or None."""

    def __init__(self, pin):
        self.p = Pin(pin, Pin.IN, Pin.PULL_UP)
        self.down = False
        self.t = time.ticks_ms()
        self.long_sent = False

    def poll(self):
        now = time.ticks_ms()
        pressed = self.p.value() == 0
        if time.ticks_diff(now, self.t) < 30:          # debounce
            return None
        if pressed and not self.down:
            self.down, self.t, self.long_sent = True, now, False
        elif pressed and self.down and not self.long_sent and time.ticks_diff(now, self.t) > 700:
            self.long_sent = True
            return 'long'
        elif not pressed and self.down:
            self.down, self.t = False, now
            if not self.long_sent:
                return 'click'
        return None


class TrigIn:
    """Clock or reset input. Counts rising edges in the background."""

    def __init__(self, pin):
        self.p = Pin(pin, Pin.IN, Pin.PULL_DOWN)
        self.n = 0
        self.p.irq(self._irq, Pin.IRQ_RISING)

    def _irq(self, _):
        self.n += 1

    def take(self):
        irq = machine.disable_irq()
        n, self.n = self.n, 0
        machine.enable_irq(irq)
        return n

    def high(self):
        return self.p.value() == 1


class Toggle:
    """Panel toggle to GND. flipped() is True when the switch closes."""

    def __init__(self, pin):
        self.p = Pin(pin, Pin.IN, Pin.PULL_UP)

    def flipped(self):
        return self.p.value() == 0


class Outputs:
    def __init__(self):
        self.gate = Pin(config.PIN_GATE, Pin.OUT)
        self.trig = Pin(config.PIN_TRIG, Pin.OUT)
        self.end = Pin(config.PIN_END, Pin.OUT)
        self.led = Pin('LED', Pin.OUT)              # on-board LED blinks per note
        for p in (self.gate, self.trig, self.end):
            self.set(p, False)
        self.i2c = I2C(0, sda=Pin(config.PIN_SDA), scl=Pin(config.PIN_SCL), freq=400000)
        try:
            found = self.i2c.scan()
        except OSError:
            found = []
        self.dac_ok = bool(config.DAC_TYPE) and config.DAC_ADDR in found

    def set(self, pin, on):
        pin.value((not on) if config.INVERT_OUTPUTS else on)

    def note(self, semis):
        """Send a pitch: semitones above 0V (0..60 = 5 octaves)."""
        volts = semis / 12
        code = int(round(volts / config.GAIN / config.DAC_VREF * 4095))
        code = max(0, min(4095, code))
        if not self.dac_ok:
            return code
        try:
            if config.DAC_TYPE == 'MCP4728':
                # channel A, internal 2.048 V reference, gain 1
                self.i2c.writeto(config.DAC_ADDR, bytes([0x58, 0x80 | (code >> 8), code & 0xFF]))
            else:
                self.i2c.writeto(config.DAC_ADDR, bytes([(code >> 8) & 0x0F, code & 0xFF]))
        except OSError:
            self.dac_ok = False
        return code
