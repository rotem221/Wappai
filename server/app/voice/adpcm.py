"""IMA ADPCM blocks from the board (meetings): int16 predictor LE, uint8 step index, 0, then 4-bit codes (low nibble first).
Each block carries its own starting state, so a lost block never corrupts the next one."""
import array
import struct

STEP = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
        130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166,
        1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845,
        8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767]
IDX = [-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8]
# delta for every (index, code): the inner loop becomes a table lookup
_DELTA = []
for _s in STEP:
    row = []
    for code in range(16):
        d = _s >> 3
        if code & 4: d += _s
        if code & 2: d += _s >> 1
        if code & 1: d += _s >> 2
        row.append(-d if code & 8 else d)
    _DELTA.append(row)


def decode(block: bytes) -> bytes:
    if len(block) < 5:
        return b""
    pred, idx = struct.unpack_from("<hB", block, 0)
    if idx>88:raise ValueError("Invalid ADPCM step index")
    out = array.array("h")
    app = out.append
    D, I = _DELTA, IDX
    for byte in block[4:]:
        for code in (byte & 15, byte >> 4):
            pred += D[idx][code]
            pred = 32767 if pred > 32767 else (-32768 if pred < -32768 else pred)
            idx += I[code]
            idx = 0 if idx < 0 else (88 if idx > 88 else idx)
            app(pred)
    return out.tobytes()


def encode(pcm: bytes, state: list | None = None) -> bytes:
    """Reference encoder (tests). state = [pred, idx] carried between blocks."""
    st = state if state is not None else [0, 0]
    pred, idx = st
    x = array.array("h", pcm)
    out = bytearray(struct.pack("<hBB", pred, idx, 0))
    for i, s in enumerate(x):
        step, diff, code = STEP[idx], s - pred, 0
        if diff < 0:
            code, diff = 8, -diff
        delta = step >> 3
        if diff >= step: code |= 4; diff -= step; delta += step
        step >>= 1
        if diff >= step: code |= 2; diff -= step; delta += step
        step >>= 1
        if diff >= step: code |= 1; delta += step
        pred += -delta if code & 8 else delta
        pred = max(-32768, min(32767, pred))
        idx = max(0, min(88, idx + IDX[code]))
        if i & 1: out[-1] |= code << 4
        else: out.append(code)
    st[0], st[1] = pred, idx
    return bytes(out)
