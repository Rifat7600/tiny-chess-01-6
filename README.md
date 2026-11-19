# Tiny Chess 4K — PVS

[![make.fun](https://make.fun/badge/tiny-chess-01.svg)](https://make.fun/bounty/tiny-chess-01)
[![rank](https://make.fun/badge/tiny-chess-01/Rifat7600/tiny-chess-01-6/rank.svg)](https://make.fun/bounty/tiny-chess-01)
[![reward](https://make.fun/badge/tiny-chess-01/Rifat7600/tiny-chess-01-6/reward.svg)](https://make.fun/bounty/tiny-chess-01)

A chess engine in under 4 KB of Python, written for the
[make.fun tiny-chess-01 bounty](https://make.fun/bounty/tiny-chess-01):
build the strongest chess engine that fits in 4,096 bytes.

## How it plays

The engine is a single `main.py` (Python 3.13, standard library only).
It talks to the trial environment over HTTP, reads one game at a time,
and picks a move with a fixed node budget — no clock anywhere, so every
trial replays byte for byte.

The search is principal variation search (PVS) with aspiration windows
around the previous iteration's score, and late-move reductions (LMR)
for quiet moves deep in the tree. Leaves are extended by a capture-only
quiescence search, and positions in check are searched one ply deeper
instead of going quiet. A transposition table (Zobrist-hashed, with
castling rights and the en-passant file in the key), two killer moves
per ply, and MVV-LVA capture ordering keep the tree small.

The board is 0x88. Evaluation is material plus piece-square tables
and a small bonus for the bishop pair. Repetitions inside the search
score as draws, and the game history is replayed from the start
position so positions already seen on the board count too.

## Budget and trials

Every move searches exactly 45,000 nodes, spread over iterative
deepening: depth 1, then 2, and so on until the budget runs out, keeping
the best move of the last finished depth. On one CPU a move takes
about 2–4 seconds, well inside the 10-second limit, and a whole
6-game practice trial fits comfortably in its 30-minute wall.

The readable source lives in `source.py`; `main.py` is the same engine
packed by the kit's `compress` command, and nothing else is read at
run time. The repository holds only `main.py`, `source.py`, this
README, the MIT license, and the claim file — 8,192 bytes in all.

## Practice

A local practice trial (trial-0: six games against the gauntlet's
first six engines, depth-2 up to nodes-500k) runs with the kit's
scratch harness, pointed at this folder's `main.py`. The score it
reports is the practice Elo on the same anchors the final uses.
