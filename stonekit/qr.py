"""QR Code encoder (byte mode, versions 1-10), stdlib only.

Follows ISO/IEC 18004 the same way Project Nayuki's reference encoder does:
Reed-Solomon over GF(256), interleaved blocks, all eight masks tried and the
lowest-penalty one kept.
"""

# error correction level -> (format bits, codewords per block, blocks) by version
_ECL = {
    "L": (1, [-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18],
          [-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4]),
    "M": (0, [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26],
          [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5]),
    "Q": (3, [-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24],
          [-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8]),
}


def _gf_mul(x, y):
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree):
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return result


def _rs_remainder(data, divisor):
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_mul(coef, factor)
    return result


def _raw_modules(ver):
    result = (16 * ver + 128) * ver + 64
    if ver >= 2:
        n = ver // 7 + 2
        result -= (25 * n - 10) * n - 55
        if ver >= 7:
            result -= 36
    return result


def _align_positions(ver):
    if ver == 1:
        return []
    n = ver // 7 + 2
    step = (ver * 8 + n * 3 + 5) // (n * 4 - 4) * 2
    size = ver * 4 + 17
    result = [6]
    pos = size - 7
    while len(result) < n:
        result.insert(1, pos)
        pos -= step
    return result


def encode(text, ecl="M"):
    """Return a square list of lists of bools (True = dark), no quiet zone."""
    data = text.encode("utf-8")
    fbits, ecc_per, blocks_tab = _ECL[ecl]
    for ver in range(1, 11):
        cap = _raw_modules(ver) // 8 - ecc_per[ver] * blocks_tab[ver]
        need = 4 + (8 if ver <= 9 else 16) + 8 * len(data)
        if need <= cap * 8:
            break
    else:
        raise ValueError("text too long for a version 1-10 QR code")
    # bit stream
    bits = [0, 1, 0, 0]
    cc = 8 if ver <= 9 else 16
    bits += [(len(data) >> i) & 1 for i in reversed(range(cc))]
    for b in data:
        bits += [(b >> i) & 1 for i in reversed(range(8))]
    bits += [0] * min(4, cap * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)
    pad = 0xEC
    while len(bits) < cap * 8:
        bits += [(pad >> i) & 1 for i in reversed(range(8))]
        pad ^= 0xEC ^ 0x11
    codewords = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]

    # split into blocks, add ECC, interleave
    nblocks, ecc_len = blocks_tab[ver], ecc_per[ver]
    raw_cw = _raw_modules(ver) // 8
    n_short = nblocks - raw_cw % nblocks
    short_len = raw_cw // nblocks
    div = _rs_divisor(ecc_len)
    blocks, k = [], 0
    for i in range(nblocks):
        dl = short_len - ecc_len + (0 if i < n_short else 1)
        dat = codewords[k:k + dl]
        k += dl
        ecc = _rs_remainder(dat, div)
        if i < n_short:
            dat = dat + [0]
        blocks.append(dat + ecc)
    final = []
    for i in range(len(blocks[0])):
        for j, blk in enumerate(blocks):
            if i != short_len - ecc_len or j >= n_short:
                final.append(blk[i])

    size = ver * 4 + 17
    mod = [[False] * size for _ in range(size)]
    fun = [[False] * size for _ in range(size)]

    def setf(x, y, dark):
        mod[y][x] = dark
        fun[y][x] = True

    for i in range(size):
        setf(6, i, i % 2 == 0)
        setf(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size:
                    setf(x, y, max(abs(dx), abs(dy)) not in (2, 4))
    al = _align_positions(ver)
    na = len(al)
    for i in range(na):
        for j in range(na):
            if (i == 0 and j == 0) or (i == 0 and j == na - 1) or (i == na - 1 and j == 0):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    setf(al[i] + dx, al[j] + dy, max(abs(dx), abs(dy)) != 1)

    def draw_format(mask):
        d = fbits << 3 | mask
        rem = d
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        b = (d << 10 | rem) ^ 0x5412
        bit = lambda i: (b >> i) & 1 == 1
        for i in range(6):
            setf(8, i, bit(i))
        setf(8, 7, bit(6)); setf(8, 8, bit(7)); setf(7, 8, bit(8))
        for i in range(9, 15):
            setf(14 - i, 8, bit(i))
        for i in range(8):
            setf(size - 1 - i, 8, bit(i))
        for i in range(8, 15):
            setf(8, size - 15 + i, bit(i))
        setf(8, size - 8, True)

    draw_format(0)  # reserve the format areas
    if ver >= 7:
        rem = ver
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        vb = ver << 12 | rem
        for i in range(18):
            dark = (vb >> i) & 1 == 1
            a, b_ = size - 11 + i % 3, i // 3
            setf(a, b_, dark); setf(b_, a, dark)

    # place data in the zigzag
    i = 0
    right = size - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(size):
            for j in range(2):
                x = right - j
                upward = ((right + 1) & 2) == 0
                y = size - 1 - vert if upward else vert
                if not fun[y][x] and i < len(final) * 8:
                    mod[y][x] = (final[i >> 3] >> (7 - (i & 7))) & 1 == 1
                    i += 1
        right -= 2

    masks = [
        lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0,
        lambda x, y: x % 3 == 0, lambda x, y: (x + y) % 3 == 0,
        lambda x, y: (x // 3 + y // 2) % 2 == 0, lambda x, y: x * y % 2 + x * y % 3 == 0,
        lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
        lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
    ]

    def apply(m):
        f = masks[m]
        for y in range(size):
            for x in range(size):
                if not fun[y][x] and f(x, y):
                    mod[y][x] = not mod[y][x]

    best, best_pen = 0, None
    for m in range(8):
        apply(m)
        draw_format(m)
        pen = _penalty(mod)
        if best_pen is None or pen < best_pen:
            best, best_pen = m, pen
        apply(m)  # undo
    apply(best)
    draw_format(best)
    return mod


def _penalty(mod):
    size = len(mod)
    pen = 0
    lines = [row for row in mod] + [[mod[y][x] for y in range(size)] for x in range(size)]
    finder_a = [True, False, True, True, True, False, True, False, False, False, False]
    finder_b = finder_a[::-1]
    for line in lines:
        run, prev = 0, None
        for v in line:
            if v == prev:
                run += 1
            else:
                if run >= 5:
                    pen += 3 + (run - 5)
                run, prev = 1, v
        if run >= 5:
            pen += 3 + (run - 5)
        padded = [False] * 4 + list(line) + [False] * 4
        for k in range(len(padded) - 10):
            seg = padded[k:k + 11]
            if seg == finder_a or seg == finder_b:
                pen += 40
    for y in range(size - 1):
        for x in range(size - 1):
            c = mod[y][x]
            if c == mod[y][x + 1] == mod[y + 1][x] == mod[y + 1][x + 1]:
                pen += 3
    dark = sum(sum(r) for r in mod)
    total = size * size
    k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
    pen += max(0, k) * 10
    return pen


def polys(matrix, module, center=(0.0, 0.0), rotate_deg=0.0):
    """Dark modules as rectangles (one per horizontal run), centred, in mm.

    Row 0 of the matrix ends up at the top (+y) so the code reads upright.
    """
    import math
    n = len(matrix)
    half = n * module / 2
    c, s = math.cos(math.radians(rotate_deg)), math.sin(math.radians(rotate_deg))
    out = []
    for r, row in enumerate(matrix):
        x = 0
        while x < n:
            if row[x]:
                x0 = x
                while x < n and row[x]:
                    x += 1
                ax, bx = -half + x0 * module, -half + x * module
                ay, by = half - (r + 1) * module, half - r * module
                pts = [(ax, ay), (bx, ay), (bx, by), (ax, by)]
                out.append([(center[0] + px * c - py * s, center[1] + px * s + py * c)
                            for px, py in pts])
            else:
                x += 1
    return out
