# machine.py - stand-in for MicroPython's `machine` module.
# Pins keep their state in a global registry so the simulator's input thread
# can read/write them and fire the IRQ handlers the firmware registered.

pins = {}          # id -> Pin instance


class Pin:
    OUT = 1
    IN = 0
    PULL_UP = 2
    PULL_DOWN = 1
    IRQ_RISING = 1
    IRQ_FALLING = 2

    def __init__(self, id, mode=-1, pull=-1, value=None):
        self.id = id
        self.mode = mode
        self.pull = pull
        # inputs with a pull-up idle high, pull-down idle low
        if value is None:
            self._v = 1 if pull == Pin.PULL_UP else 0
        else:
            self._v = value
        self.handler = None
        self.trigger = 0
        pins[id] = self

    def init(self, mode=-1, pull=-1, value=None):
        if mode != -1:
            self.mode = mode
        if pull != -1:
            self.pull = pull
        if value is not None:
            self._v = value

    def value(self, v=None):
        if v is None:
            return self._v
        self._v = 1 if v else 0

    def __call__(self, v=None):
        return self.value(v)

    def on(self):
        self._v = 1

    def off(self):
        self._v = 0

    def irq(self, handler=None, trigger=0):
        self.handler = handler
        self.trigger = trigger

    # --- used by the simulator input layer, not by the firmware ---
    def drive(self, v):
        """Set the pin and fire the firmware IRQ if the edge matches."""
        old, self._v = self._v, (1 if v else 0)
        if self.handler is None or old == self._v:
            return
        rising = old == 0 and self._v == 1
        if (rising and (self.trigger & Pin.IRQ_RISING)) or \
           (not rising and (self.trigger & Pin.IRQ_FALLING)):
            self.handler(self)


class SPI:
    def __init__(self, *a, **k):
        pass

    def init(self, *a, **k):
        pass

    def write(self, buf):
        pass


class I2C:
    def __init__(self, *a, **k):
        pass

    def scan(self):
        return []          # no DAC -> firmware runs in screen-only mode

    def writeto(self, addr, buf):
        pass


def disable_irq():
    return 0


def enable_irq(state):
    pass
