# Tiny chess engine: 0x88 board, PVS + aspiration + LMR, fixed 45000 nodes/move.
import os, sys, json, urllib.request
sys.setrecursionlimit(10000)

INF = 30000
BUDGET = 45000
VAL = (0, 100, 320, 330, 500, 900, 0)
# piece-square tables, index 0 = a1, written for White; Black mirrors with sq ^ 56
PST_P = (0,0,0,0,0,0,0,0, 50,50,50,50,50,50,50,50, 10,10,20,30,30,20,10,10,
 5,5,10,25,25,10,5,5, 0,0,0,20,20,0,0,0, 5,-5,-10,0,0,-10,-5,5,
 5,10,10,-20,-20,10,10,5, 0,0,0,0,0,0,0,0)
PST_N = (-50,-40,-30,-30,-30,-30,-40,-50, -40,-20,0,0,0,0,-20,-40,
 -30,0,10,15,15,10,0,-30, -30,5,15,20,20,15,5,-30, -30,0,15,20,20,15,0,-30,
 -30,5,10,15,15,10,5,-30, -40,-20,0,5,5,0,-20,-40, -50,-40,-30,-30,-30,-30,-40,-50)
PST_B = (-20,-10,-10,-10,-10,-10,-10,-20, -10,0,0,0,0,0,0,-10,
 -10,0,5,10,10,5,0,-10, -10,5,5,10,10,5,5,-10, -10,0,10,10,10,10,0,-10,
 -10,10,10,10,10,10,10,-10, -10,5,0,0,0,0,5,-10, -20,-10,-10,-10,-10,-10,-10,-20)
PST_R = (0,0,0,0,0,0,0,0, 5,10,10,10,10,10,10,5, -5,0,0,0,0,0,0,-5,
 -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5,
 -5,0,0,0,0,0,0,-5, 0,0,0,5,5,0,0,0)
PST_Q = (-20,-10,-10,-5,-5,-10,-10,-20, -10,0,0,0,0,0,0,-10,
 -10,0,5,5,5,5,0,-10, -5,0,5,5,5,5,0,-5, 0,0,5,5,5,5,0,-5,
 -10,5,5,5,5,5,0,-10, -10,0,5,0,0,0,0,-10, -20,-10,-10,-5,-5,-10,-10,-20)
PST_K = (-30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30,
 -30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30,
 -20,-30,-30,-40,-40,-30,-30,-20, -10,-20,-20,-20,-20,-20,-20,-10,
 20,20,0,0,0,0,20,20, 20,30,10,0,0,10,30,20)
PST = (None, PST_P, PST_N, PST_B, PST_R, PST_Q, PST_K)
M64 = [((i >> 4) * 8 + (i & 7)) if not i & 0x88 else 0 for i in range(128)]
KDIR = (15, 17, -15, -17)
RDIR = (16, 1, -16, -1)
NDIR = (31, 33, 14, 18, -31, -33, -14, -18)
# deterministic pseudo-random keys for Zobrist hashing (fixed-seed LCG)
_z = []
_s = 0x9E3779B97F4A7C15
for _i in range(13 * 128 + 32):
    _s = (_s * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
    _z.append(_s)
Z = _z
ZSIDE = _z[-1]

# board state: 0x88, pieces +1..+6 white, -1..-6 black; side 0 white, 1 black
bd = [0] * 128
side = 0
castle = 0  # bits: 1 WK, 2 WQ, 4 BK, 8 BQ
epsq = -1
king = [0, 0]
H = 0  # zobrist hash of current position
stack = []
path = set()

def zh(p, sq):
    return Z[(p + 6) * 128 + sq]

def parse_fen(f):
    global side, castle, epsq, H
    parts = f.split()
    for i in range(128):
        bd[i] = 0
    r = 7
    c = 0
    for ch in parts[0]:
        if ch == '/':
            r -= 1
            c = 0
        elif ch.isdigit():
            c += int(ch)
        else:
            p = 'PNBRQK'.index(ch.upper()) + 1
            if ch.islower():
                p = -p
            bd[r * 16 + c] = p
            c += 1
    side = 0 if parts[1] == 'w' else 1
    castle = 0
    if len(parts) > 2:
        for ch in parts[2]:
            if ch == 'K':
                castle |= 1
            elif ch == 'Q':
                castle |= 2
            elif ch == 'k':
                castle |= 4
            elif ch == 'q':
                castle |= 8
    epsq = -1
    if len(parts) > 3 and parts[3] != '-':
        epsq = 'abcdefgh'.index(parts[3][0]) + ('12345678'.index(parts[3][1])) * 16
    king[0] = king[1] = -1
    for i in range(128):
        if bd[i] == 6:
            king[0] = i
        elif bd[i] == -6:
            king[1] = i
    H = 0
    for i in range(128):
        if bd[i]:
            H ^= zh(bd[i], i)
    if side:
        H ^= ZSIDE
    H ^= ZC[castle] ^ ZE[epfile()]

def attacked(sq, by):
    # is sq attacked by side `by` (0 white, 1 black)? by>0 means black
    if by == 0:
        if not (sq - 15) & 0x88 and bd[sq - 15] == 1:
            return True
        if not (sq - 17) & 0x88 and bd[sq - 17] == 1:
            return True
    else:
        if not (sq + 15) & 0x88 and bd[sq + 15] == -1:
            return True
        if not (sq + 17) & 0x88 and bd[sq + 17] == -1:
            return True
    for d in NDIR:
        t = sq + d
        if not t & 0x88 and bd[t] == (2 if by == 0 else -2):
            return True
    for d in KDIR + RDIR:
        t = sq + d
        if not t & 0x88 and bd[t] == (6 if by == 0 else -6):
            return True
    for d in KDIR:
        t = sq + d
        while not t & 0x88:
            p = bd[t]
            if p:
                if p == (3 if by == 0 else -3) or p == (5 if by == 0 else -5):
                    return True
                break
            t += d
    for d in RDIR:
        t = sq + d
        while not t & 0x88:
            p = bd[t]
            if p:
                if p == (4 if by == 0 else -4) or p == (5 if by == 0 else -5):
                    return True
                break
            t += d
    return False

def gen(caps_only=False):
    # returns list of int moves: from | to<<7 | promo<<14 ; promo 2=N, 5=Q
    mv = []
    us = 1 if side == 0 else -1
    them = -us
    pdir = 16 if side == 0 else -16
    start = 1 if side == 0 else 6
    last = 7 if side == 0 else 0
    for sq in range(128):
        if sq & 0x88:
            continue
        p = bd[sq]
        if p == 0 or (p > 0) != (side == 0):
            continue
        ap = abs(p)
        if ap == 1:
            one = sq + pdir
            if not one & 0x88 and bd[one] == 0:
                if (one >> 4) == last:
                    mv.append(sq | (one << 7) | (5 << 14))
                    mv.append(sq | (one << 7) | (2 << 14))
                    mv.append(sq | (one << 7) | (4 << 14))
                    mv.append(sq | (one << 7) | (3 << 14))
                else:
                    mv.append(sq | (one << 7))
                    if (sq >> 4) == start:
                        two = sq + 2 * pdir
                        if bd[two] == 0:
                            mv.append(sq | (two << 7))
            for d in (pdir - 1, pdir + 1):
                t = sq + d
                if t & 0x88:
                    continue
                if bd[t] != 0 and (bd[t] > 0) != (side == 0):
                    if (t >> 4) == last:
                        mv.append(sq | (t << 7) | (5 << 14))
                        mv.append(sq | (t << 7) | (2 << 14))
                        mv.append(sq | (t << 7) | (4 << 14))
                        mv.append(sq | (t << 7) | (3 << 14))
                    else:
                        mv.append(sq | (t << 7))
                elif t == epsq:
                    mv.append(sq | (t << 7))
        elif ap == 2:
            for d in NDIR:
                t = sq + d
                if t & 0x88:
                    continue
                if bd[t] == 0:
                    if not caps_only:
                        mv.append(sq | (t << 7))
                elif (bd[t] > 0) != (side == 0):
                    mv.append(sq | (t << 7))
        elif ap == 3 or ap == 5:
            for d in (KDIR if ap == 3 else KDIR + RDIR):
                t = sq + d
                while not t & 0x88:
                    if bd[t] == 0:
                        if not caps_only:
                            mv.append(sq | (t << 7))
                    else:
                        if (bd[t] > 0) != (side == 0):
                            mv.append(sq | (t << 7))
                        break
                    t += d
        elif ap == 4:
            for d in RDIR:
                t = sq + d
                while not t & 0x88:
                    if bd[t] == 0:
                        if not caps_only:
                            mv.append(sq | (t << 7))
                    else:
                        if (bd[t] > 0) != (side == 0):
                            mv.append(sq | (t << 7))
                        break
                    t += d
        else:  # king
            for d in KDIR + RDIR:
                t = sq + d
                if t & 0x88:
                    continue
                if bd[t] == 0:
                    if not caps_only:
                        mv.append(sq | (t << 7))
                elif (bd[t] > 0) != (side == 0):
                    mv.append(sq | (t << 7))
            if not caps_only:
                # castling: rights, empty squares, king not in/passing through check
                if side == 0 and sq == 4:
                    if castle & 1 and bd[5] == 0 and bd[6] == 0 and bd[7] == 4 \
                            and not attacked(4, 1) and not attacked(5, 1) and not attacked(6, 1):
                        mv.append(4 | (6 << 7))
                    if castle & 2 and bd[3] == 0 and bd[2] == 0 and bd[1] == 0 and bd[0] == 4 \
                            and not attacked(4, 1) and not attacked(3, 1) and not attacked(2, 1):
                        mv.append(4 | (2 << 7))
                elif side == 1 and sq == 116:
                    if castle & 4 and bd[117] == 0 and bd[118] == 0 and bd[119] == -4 \
                            and not attacked(116, 0) and not attacked(117, 0) and not attacked(118, 0):
                        mv.append(116 | (118 << 7))
                    if castle & 8 and bd[115] == 0 and bd[114] == 0 and bd[113] == 0 and bd[112] == -4 \
                            and not attacked(116, 0) and not attacked(115, 0) and not attacked(114, 0):
                        mv.append(116 | (114 << 7))
    return mv

ZC = _z[1664:1680]
ZE = _z[1680:1689]

def epfile():
    return (epsq & 7) if epsq >= 0 else 8

def make(m):
    global side, castle, epsq, H
    f = m & 127
    t = (m >> 7) & 127
    pr = (m >> 14) & 7
    p = bd[f]
    H ^= ZC[castle] ^ ZE[epfile()]
    cap = 0
    csq = -1
    if abs(p) == 1 and t == epsq and bd[t] == 0:
        csq = t - 16 if side == 0 else t + 16
        cap = bd[csq]
        H ^= zh(cap, csq)
        bd[csq] = 0
    elif bd[t] != 0:
        cap = bd[t]
        csq = t
        H ^= zh(cap, t)
    stack.append((m, cap, csq, castle, epsq))
    H ^= zh(p, f)
    bd[f] = 0
    if pr:
        np = pr if side == 0 else -pr
        bd[t] = np
        H ^= zh(np, t)
    else:
        bd[t] = p
        H ^= zh(p, t)
    if abs(p) == 6 and abs(t - f) == 2:
        if t == 6:
            bd[5] = 4
            bd[7] = 0
            H ^= zh(4, 7) ^ zh(4, 5)
        elif t == 2:
            bd[3] = 4
            bd[0] = 0
            H ^= zh(4, 0) ^ zh(4, 3)
        elif t == 118:
            bd[117] = -4
            bd[119] = 0
            H ^= zh(-4, 119) ^ zh(-4, 117)
        elif t == 114:
            bd[115] = -4
            bd[112] = 0
            H ^= zh(-4, 112) ^ zh(-4, 115)
    if abs(p) == 6:
        king[side] = t
    if f == 4 or t == 4:
        castle &= ~3
    if f == 0 or t == 0:
        castle &= ~2
    if f == 7 or t == 7:
        castle &= ~1
    if f == 116 or t == 116:
        castle &= ~12
    if f == 112 or t == 112:
        castle &= ~8
    if f == 119 or t == 119:
        castle &= ~4
    if abs(p) == 1 and abs(t - f) == 32:
        epsq = (f + t) // 2
    else:
        epsq = -1
    H ^= ZC[castle] ^ ZE[epfile()]
    side ^= 1
    H ^= ZSIDE

def unmake():
    global side, castle, epsq, H
    m, cap, csq, oc, oe = stack.pop()
    f = m & 127
    t = (m >> 7) & 127
    pr = (m >> 14) & 7
    side ^= 1
    H ^= ZSIDE
    H ^= ZC[castle] ^ ZE[epfile()]
    p = bd[t]
    H ^= zh(p, t)
    bd[t] = 0
    if abs(p) == 6 and abs(t - f) == 2:
        if t == 6:
            bd[7] = 4
            bd[5] = 0
            H ^= zh(4, 5) ^ zh(4, 7)
        elif t == 2:
            bd[0] = 4
            bd[3] = 0
            H ^= zh(4, 3) ^ zh(4, 0)
        elif t == 118:
            bd[119] = -4
            bd[117] = 0
            H ^= zh(-4, 117) ^ zh(-4, 119)
        elif t == 114:
            bd[112] = -4
            bd[115] = 0
            H ^= zh(-4, 115) ^ zh(-4, 112)
    if pr:
        op = 1 if side == 0 else -1
        bd[f] = op
        H ^= zh(op, f)
    else:
        bd[f] = p
        H ^= zh(p, f)
    if cap:
        bd[csq] = cap
        H ^= zh(cap, csq)
    if abs(bd[f]) == 6:
        king[side] = f
    castle = oc
    epsq = oe
    H ^= ZC[castle] ^ ZE[epfile()]

TT = {}
KILL = [[0, 0] for _ in range(128)]
N = 0

class AB(Exception):
    pass

def ev():
    s = 0
    wb = 0
    bb = 0
    for i in range(128):
        if i & 0x88:
            continue
        p = bd[i]
        if p:
            a = abs(p)
            q = M64[i]
            v = VAL[a] + PST[a][q if p > 0 else q ^ 56]
            if p > 0:
                s += v
                if a == 3:
                    wb += 1
            else:
                s -= v
                if a == 3:
                    bb += 1
    if wb >= 2:
        s += 25
    if bb >= 2:
        s -= 25
    return s if side == 0 else -s

def mscore(m):
    t = (m >> 7) & 127
    f = m & 127
    if bd[t]:
        return 10000 + 10 * VAL[abs(bd[t])] - VAL[abs(bd[f])] // 10
    return 0

def qs(a, b, ply):
    global N
    N += 1
    if N >= BUDGET:
        raise AB
    st = ev()
    if st >= b:
        return b
    if st > a:
        a = st
    mv = gen(True)
    mv.sort(key=mscore, reverse=True)
    for m in mv:
        make(m)
        if attacked(king[side ^ 1], side):
            unmake()
            continue
        s = -qs(-b, -a, ply + 1)
        unmake()
        if s >= b:
            return b
        if s > a:
            a = s
    return a

def sr(a, b, d, ply):
    global N
    N += 1
    if N >= BUDGET:
        raise AB
    if ply and H in path:
        return 0
    e = TT.get(H)
    if e and e[0] >= d:
        _, fl, sc, _ = e
        if fl == 0:
            return sc
        if fl == 1:
            a = max(a, sc)
        else:
            b = min(b, sc)
        if a >= b:
            return sc
    if d <= 0:
        if attacked(king[side], side ^ 1):
            d = 1
        else:
            return qs(a, b, ply)
    path.add(H)
    mv = gen()
    tm = e[3] if e else 0
    k0, k1 = KILL[ply]
    mv.sort(key=lambda m: (100000 if m == tm else 0) + (9000 if m == k0 or m == k1 else 0) + mscore(m), reverse=True)
    ao = a
    best = -INF
    bm = 0
    j = 0
    for m in mv:
        f = m & 127
        t = (m >> 7) & 127
        capm = bd[t] != 0 or (abs(bd[f]) == 1 and t == epsq)
        make(m)
        if attacked(king[side ^ 1], side):
            unmake()
            continue
        j += 1
        if j == 1:
            s = -sr(-b, -a, d - 1, ply + 1)
        else:
            red = 0
            if d >= 3 and j >= 4 and not capm and not ((m >> 14) & 7):
                red = 1 if d < 6 else 2
            if red:
                s = -sr(-a - 1, -a, d - 1 - red, ply + 1)
                if s > a:
                    s = -sr(-b, -a, d - 1, ply + 1)
            else:
                s = -sr(-a - 1, -a, d - 1, ply + 1)
                if s > a:
                    s = -sr(-b, -a, d - 1, ply + 1)
        unmake()
        if s > best:
            best = s
            bm = m
        if s > a:
            a = s
        if a >= b:
            break
    path.discard(H)
    if j == 0:
        return -INF + ply if attacked(king[side], side ^ 1) else 0
    if best >= b and bm:
        f = bm & 127
        t = (bm >> 7) & 127
        if bd[t] == 0:
            KILL[ply][1] = KILL[ply][0]
            KILL[ply][0] = bm
    fl = 2 if best <= ao else (1 if best >= b else 0)
    TT[H] = (d, fl, best, bm)
    return best

def root():
    global N
    N = 0
    if len(TT) > 200000:
        TT.clear()
    best = 0
    sc = 0
    for d in range(1, 64):
        try:
            if d == 1:
                s = sr(-INF, INF, d, 0)
            else:
                s = sr(sc - 25, sc + 25, d, 0)
                if s <= sc - 25 or s >= sc + 25:
                    s = sr(-INF, INF, d, 0)
        except AB:
            break
        e = TT.get(H)
        if e and e[3]:
            best = e[3]
            sc = s
        if N >= BUDGET:
            break
    return best

def uci_to_move(u):
    f = 'abcdefgh'.index(u[0]) + ('12345678'.index(u[1])) * 16
    t = 'abcdefgh'.index(u[2]) + ('12345678'.index(u[3])) * 16
    pr = 0
    if len(u) > 4:
        pr = {'n': 2, 'b': 3, 'r': 4, 'q': 5}[u[4]]
    return f | (t << 7) | (pr << 14)

def move_to_uci(m):
    f = m & 127
    t = (m >> 7) & 127
    pr = (m >> 14) & 7
    s = 'abcdefgh'[f & 7] + str((f >> 4) + 1) + 'abcdefgh'[t & 7] + str((t >> 4) + 1)
    if pr:
        s += {2: 'n', 3: 'b', 4: 'r', 5: 'q'}[pr]
    return s

def choose(fen, lm, hist):
    global path
    parse_fen(fen)
    # replay the game's moves from the start to collect position hashes
    parse_fen('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')
    path = set()
    path.add(H)
    for u in hist:
        make(uci_to_move(u))
        path.add(H)
    parse_fen(fen)
    mv = root()
    if not mv:
        return lm[0]
    return move_to_uci(mv)

U = os.environ.get('MAKEFUN_ENV_URL', 'http://127.0.0.1:18080')

def post(p, d):
    req = urllib.request.Request(U + p, data=json.dumps(d).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def main():
    while True:
        try:
            g = post('/game', {})
        except Exception:
            continue
        if g.get('status') == 'done':
            return
        if g.get('status') != 'your_move':
            continue
        try:
            mv = choose(g['fen'], g['legal_moves'], g['moves'])
        except Exception:
            mv = g['legal_moves'][0]
        try:
            post('/move', {'game': g['game'], 'move': mv})
        except Exception:
            pass

if __name__ == '__main__':
    main()
