# seq.py - what is playing: matrix rows or tone clock fields
import logic
import toneclock

FORMS = ('P', 'R', 'I', 'RI')
FLIP_DIR = {'P': 'R', 'R': 'P', 'I': 'RI', 'RI': 'I'}      # DIR toggle
FLIP_MODE = {'P': 'I', 'I': 'P', 'R': 'RI', 'RI': 'R'}     # MODE toggle


class Seq:
    def __init__(self):
        self.mode = 'matrix'        # 'matrix' or 'clock'
        self.form = 'P'
        self.num = 0                # matrix: which P/R/I/RI (0..11)
        self.hour = 1               # clock: 1..12
        self.variant = 0            # clock: which twelve-tone field
        self.transpose = 0          # 0..11, 0 = C
        self.octave = 1             # base octave of the CV output
        self.step = 0
        self.items = []             # [(pitch class, cell or pc), ...]
        self.form_now = 'P'
        self.groups = []
        self.full = True
        self.m0 = None
        self.new_matrix()

    # ---- data
    def new_matrix(self):
        self.m0 = logic.matrix(logic.new_row())

    def matrix(self):
        return logic.transposed(self.m0, self.transpose)

    def variants(self):
        return toneclock.variants(self.hour)

    def build(self, dir_flip=False, mode_flip=False):
        """Work out the 12 notes to play. Call after any change."""
        if self.mode == 'matrix':
            f = self.form
            if mode_flip:
                f = FLIP_MODE[f]
            if dir_flip:
                f = FLIP_DIR[f]
            self.form_now = f
            m = self.matrix()
            self.items = [(m[r][c], (r, c)) for r, c in logic.path(self.m0, f, self.num)]
        else:
            self.variant %= self.variants()
            self.groups, self.full = toneclock.field(self.hour, self.variant, self.transpose)
            notes = [n for g in self.groups for n in g]
            if dir_flip:
                notes = notes[::-1]
            self.items = [(n, n) for n in notes]
        self.step %= len(self.items)

    def line(self):
        """('row', r) or ('col', c) for the matrix highlight."""
        r, c = self.items[0][1]
        r2, c2 = self.items[1][1]
        return ('row', r) if r == r2 else ('col', c)

    def name(self):
        if self.mode == 'matrix':
            return '%s%d' % (self.form_now, self.num)
        return 'Hour %s' % toneclock_roman(self.hour)

    # ---- playing
    def next(self):
        """Advance one step. Returns (pitch class, key, wrapped)."""
        pc, key = self.items[self.step]
        self.step += 1
        wrapped = self.step >= len(self.items)
        if wrapped:
            self.step = 0
        return pc, key, wrapped

    def semis(self, pc):
        return pc + 12 * self.octave


def toneclock_roman(h):
    return ('I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII')[h - 1]
