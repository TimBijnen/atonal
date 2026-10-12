# toneclock.py - Peter Schat's Tone Clock
#
# The 12 "hours" are the 12 possible three-note chords (trichords).
# For most hours, four copies of the trichord (transposed and/or mirrored)
# together use all 12 notes exactly once: a twelve-tone field.
# Hour X (the diminished trichord) is the only one that cannot do that.
# Schat extends it to the diminished seventh chord (0 3 6 9): three of
# those fill the twelve notes, drawn as three squares on the clock.

HOURS = (
    (0, 1, 2), (0, 1, 3), (0, 1, 4), (0, 1, 5), (0, 1, 6), (0, 2, 4),
    (0, 2, 5), (0, 2, 6), (0, 2, 7), (0, 3, 6), (0, 3, 7), (0, 4, 8),
)

# chords that build an hour's field, where it is not the hour's trichord
FIELD_CHORD = {10: (0, 3, 6, 9)}


def _forms(tri):
    """Every transposition and mirror of a trichord, as ordered note lists."""
    seen, out = set(), []
    for n in range(12):
        for sign in (1, -1):
            f = [(n + sign * i) % 12 for i in tri]
            key = tuple(sorted(f))
            if key not in seen:
                seen.add(key)
                out.append(f)
    return out


def _canon(field):
    """Same field transposed counts once: compare all 12 transpositions."""
    best = None
    for t in range(12):
        k = tuple(sorted(tuple(sorted((x + t) % 12 for x in g)) for g in field))
        if best is None or k < best:
            best = k
    return best


_cache = {}


def fields(hour):
    """All twelve-tone fields of an hour (1..12), one per transposition class.
    Each field is a list of chords (ordered note lists), the first starting on C:
    4 trichords, or 3 tetrachords for hour X."""
    if hour in _cache:
        return _cache[hour]
    forms = _forms(FIELD_CHORD.get(hour, HOURS[hour - 1]))
    found, seen = [], set()

    def rec(left, chosen):
        if not left:
            k = _canon(chosen)
            if k not in seen:
                seen.add(k)
                found.append(list(chosen))
            return
        low = min(left)
        for f in forms:
            if low in f and all(x in left for x in f):
                chosen.append(f)
                rec(left - set(f), chosen)
                chosen.pop()

    rec(set(range(12)), [])
    # normalise: rotate each field so its first trichord starts on 0 (C)
    out = []
    for fld in found:
        t = -fld[0][0] % 12
        out.append([[(x + t) % 12 for x in g] for g in fld])
    _cache[hour] = out
    return out


def field(hour, variant=0, transpose=0):
    """The chords to play. Returns (groups, is_full)."""
    fl = fields(hour)
    if fl:
        g = fl[variant % len(fl)]
        full = True
    else:
        # no field found (does not happen with FIELD_CHORD): chromatic groups
        g = [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9, 10, 11]]
        full = False
    return [[(x + transpose) % 12 for x in grp] for grp in g], full


def variants(hour):
    return max(1, len(fields(hour)))
