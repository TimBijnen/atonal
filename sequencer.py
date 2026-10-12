# sequencer.py - what is playing: 4 voices per step
#
#   matrix  12 steps: voice 1 plays the chosen form, voices 2-4 the other
#           three forms (P, R, I, RI) of the same number
#   clock   3 steps (4 for hour X): each voice loops through one trichord
#           of the field, so the four together sound all 12 notes
#   terts   one chord per step, set in four parts (bass, tenor, alto,
#           soprano); each next chord is a random tertsverwant
import logic
import toneclock
import terts

FORMS = ('P', 'R', 'I', 'RI')
FLIP_DIR = {'P': 'R', 'R': 'P', 'I': 'RI', 'RI': 'I'}      # DIR toggle
FLIP_MODE = {'P': 'I', 'I': 'P', 'R': 'RI', 'RI': 'R'}     # MODE toggle
VOICES = 4


class Sequencer:
    def __init__(self):
        self.mode = 'matrix'        # 'matrix', 'clock' or 'terts'
        self.form = 'P'
        self.num = 0                # matrix: which P/R/I/RI (0..11)
        self.hour = 1               # clock: 1..12
        self.variant = 0            # clock: which twelve-tone field
        self.transpose = 0          # 0..11, 0 = C (terts: the home key)
        self.octave = 1             # base octave of the CV outputs
        self.step = 0
        self.items = []             # matrix/clock: [(4 notes, display key), ...]
        self.form_now = 'P'
        self.groups = []
        self.full = True
        self.m0 = None
        self.terts_filter = 0       # terts: index into terts.FILTERS
        self.restart()
        self.new_matrix()

    # ---- data
    def new_matrix(self):
        self.m0 = logic.matrix(logic.new_row())

    def matrix(self):
        return logic.transposed(self.m0, self.transpose)

    def variants(self):
        return toneclock.variants(self.hour)

    def restart(self):
        """Terts: start again from the home chord (major triad on transpose)."""
        self.chord = None           # (root, quality) now playing
        self.prev = None            # the chord before it
        self.shared = None          # notes the two share (2, 1 or 0)
        self.voicing = None         # bass, tenor, alto, soprano
        self.home = self.transpose

    def build(self, dir_flip=False, mode_flip=False):
        """Work out the steps to play. Call after any change."""
        if self.mode == 'matrix':
            f = self.form
            if mode_flip:
                f = FLIP_MODE[f]
            if dir_flip:
                f = FLIP_DIR[f]
            self.form_now = f
            m = self.matrix()
            forms = [f] + [x for x in FORMS if x != f]          # voice 1 first
            paths = [logic.path(self.m0, x, self.num) for x in forms]
            self.items = []
            for k in range(12):
                cells = tuple(p[k] for p in paths)
                self.items.append((tuple(m[r][c] for r, c in cells), cells))
        elif self.mode == 'clock':
            self.variant %= self.variants()
            self.groups, self.full = toneclock.field(self.hour, self.variant, self.transpose)
            seqs = [list(g) for g in self.groups]
            if len(seqs) < VOICES:                  # hour X: 3 squares
                g = seqs[0]
                seqs.append(g[2:] + g[:2])          # voice 4: the first, half a turn on
            if dir_flip:
                seqs = [s[::-1] for s in seqs]
            self.items = []
            for k in range(len(seqs[0])):
                notes = tuple(s[k] for s in seqs)
                self.items.append((notes, notes))
        else:
            self.items = []
            if self.home != self.transpose:
                self.restart()
        if self.items:
            self.step %= len(self.items)

    def lines(self):
        """Matrix highlight: the row of P/R and the column of I/RI."""
        r = [row[0] for row in self.m0].index(self.num)
        c = self.m0[0].index(self.num)
        return [('row', r), ('col', c)]

    def name(self):
        if self.mode == 'matrix':
            return '%s%d' % (self.form_now, self.num)
        return 'Hour %s' % toneclock_roman(self.hour)

    # ---- playing
    def next(self):
        """Advance one step. Returns (4 notes, display key, wrapped).
        Notes are semitones above C of the base octave; wrapped is True at
        the end of a row or field, and in terts when the walk is back home."""
        if self.mode == 'terts':
            return self._next_chord()
        notes, key = self.items[self.step]
        self.step += 1
        wrapped = self.step >= len(self.items)
        if wrapped:
            self.step = 0
        return notes, key, wrapped

    def _next_chord(self):
        if self.chord is None:
            root, q = self.home, terts.MAJOR
            self.voicing = terts.first_voicing(root, q)
            wrapped = False
        else:
            root, q = self.chord
            root, q, self.shared = terts.pick(root, q, terts.FILTERS[self.terts_filter][1])
            self.voicing = terts.lead(self.voicing, root, q)
            wrapped = (root, q) == (self.home, terts.MAJOR)
        self.prev, self.chord = self.chord, (root, q)
        return tuple(self.voicing), self.chord, wrapped

    def reset(self):
        """RST in: back to the first note (terts: the home chord)."""
        self.step = 0
        if self.mode == 'terts':
            self.restart()

    def semis(self, n):
        return n + 12 * self.octave


def toneclock_roman(h):
    return ('I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII')[h - 1]
