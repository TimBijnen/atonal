# logic.py - 12-tone rows and the matrix
import random

MAJ_MIN = [(0, 4, 7), (0, 3, 7)]                      # major, minor
STRICT = MAJ_MIN + [(0, 3, 6), (0, 4, 8)]             # + diminished, augmented
CHORDS = MAJ_MIN                                      # the menu can switch this


def set_strict(on):
    global CHORDS
    CHORDS = STRICT if on else MAJ_MIN


def is_chord(a, b, c):
    s = {a, b, c}
    for root in s:
        for ch in CHORDS:
            if s == {(root + i) % 12 for i in ch}:
                return True
    return False


def ok(row):
    # no 3 neighbours may form a chord, wrapping around (11-12-1 and 12-1-2 too)
    return not any(is_chord(row[i], row[(i + 1) % 12], row[(i + 2) % 12])
                   for i in range(12))


def shuffle(lst):                         # MicroPython has no random.shuffle
    for i in range(len(lst) - 1, 0, -1):
        j = random.randrange(i + 1)
        lst[i], lst[j] = lst[j], lst[i]


def new_row():
    while True:
        row = list(range(12))
        shuffle(row)
        if ok(row):
            return [(n - row[0]) % 12 for n in row]     # starts on 0


def matrix(p):
    """p starts on 0. Row r starts on m[r][0]: that row is P<m[r][0]>."""
    return [[(c - r) % 12 for c in p] for r in p]


def transposed(m, t):
    return [[(x + t) % 12 for x in row] for row in m]


def path(m, form, n):
    """Cells (r, c) for form 'P', 'R', 'I' or 'RI' number n (0..11).
    m must be the untransposed matrix (top-left = 0)."""
    if form in ('P', 'R'):
        r = [row[0] for row in m].index(n)        # row that starts on n
        cells = [(r, c) for c in range(12)]
    else:
        c = m[0].index(n)                         # column that starts on n
        cells = [(r, c) for r in range(12)]
    return cells[::-1] if form in ('R', 'RI') else cells
