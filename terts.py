# terts.py - tertsverwanten: triads whose roots are a third apart
#
# From any major or minor triad, moving the root a minor or major third up
# or down and taking a major or minor triad there gives 8 neighbours. They
# fall into three groups by the number of notes they share with it:
#
#   2 shared   diatonic          C -> Em, Am
#   1 shared   chromatic         C -> E, A, Eb, Ab
#   0 shared   doubly chromatic  C -> Ebm, Abm
#
# The chords are set in four parts, as in a school harmony exercise:
# bass on the root, root doubled, notes the chords share stay in the same
# voice, the other voices move to the nearest note.
import random

MAJOR, MINOR = 'M', 'm'

# which groups (shared notes) the next chord may come from: (label, groups)
FILTERS = (
    ('all', (2, 1, 0)),
    ('2', (2,)),
    ('1', (1,)),
    ('0', (0,)),
    ('2+1', (2, 1)),
    ('1+0', (1, 0)),
    ('2+0', (2, 0)),
)

# voices: bass, tenor, alto, soprano, in semitones above C of the base octave
BASS = (0, 19)
SOPRANO = (12, 36)
PERMS = ((0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0))


def triad(root, q):
    """Pitch classes (root, third, fifth)."""
    return root % 12, (root + (4 if q == MAJOR else 3)) % 12, (root + 7) % 12


def neighbours(root, q):
    """The 8 tertsverwanten of (root, q) as (root, quality, shared notes)."""
    a = set(triad(root, q))
    out = []
    for d in (3, 4, -3, -4):
        r = (root + d) % 12
        for q2 in (MAJOR, MINOR):
            out.append((r, q2, len(a & set(triad(r, q2)))))
    return out


def pick(root, q, groups):
    """A random neighbour from the allowed groups: (root, quality, shared)."""
    c = [n for n in neighbours(root, q) if n[2] in groups]
    return c[random.randrange(len(c))]


def first_voicing(root, q):
    """Root position: bass on the root, then fifth, root and third above."""
    r = root % 12
    return [r, r + 7, r + 12, r + 12 + (4 if q == MAJOR else 3)]


def _near(prev, pc):
    """The nearest note of pitch class pc at or above prev, and the one below."""
    d = (pc - prev) % 12
    return prev + d, prev + d - 12


def _parallels(a, b):
    """Voice pairs that move in parallel (or contrary) fifths or octaves."""
    n = 0
    for i in range(4):
        if a[i] == b[i]:
            continue
        for j in range(i + 1, 4):
            if a[j] == b[j]:
                continue
            iv = (a[j] - a[i]) % 12
            if iv in (0, 7) and (b[j] - b[i]) % 12 == iv:
                n += 1
    return n


def lead(prev, root, q):
    """Move the voicing prev (bass, tenor, alto, soprano) to the new triad."""
    pcs = triad(root, q)
    best, best_cost = None, 0
    for b in _near(prev[0], pcs[0]):
        if not BASS[0] <= b <= BASS[1]:
            continue
        for p in PERMS:
            for t in _near(prev[1], pcs[p[0]]):
                if t <= b:
                    continue
                for a in _near(prev[2], pcs[p[1]]):
                    if a <= t or a - t > 12:
                        continue
                    for s in _near(prev[3], pcs[p[2]]):
                        if s <= a or s - a > 12 or not SOPRANO[0] <= s <= SOPRANO[1]:
                            continue
                        new = (b, t, a, s)
                        cost = (2 * (abs(t - prev[1]) + abs(a - prev[2]) + abs(s - prev[3]))
                                + abs(b - prev[0]) + 48 * _parallels(prev, new))
                        if best is None or cost < best_cost:
                            best, best_cost = new, cost
    return list(best) if best else first_voicing(root, q)
