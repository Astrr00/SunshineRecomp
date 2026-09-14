"""Zuordnung von Zeichenbefehlen aufeinander folgender Frames (WP13).

Siehe tools/framerate/__main__.py fuer die Befehlszeile.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fifo  # noqa: E402


def signature(draw: fifo.Draw) -> tuple:
    """Was einen Zeichenbefehl ueber Frames hinweg wiedererkennbar macht."""
    return (draw.primitive, draw.vat, draw.vertices, draw.vertex_size,
            draw.pos_kind, draw.per_vertex_matrix, draw.texture_key)


def match(previous: list[fifo.Draw], current: list[fifo.Draw]) -> list[tuple[int, int]]:
    """Ordnet Zeichenbefehle in Reihenfolge zu (laengste gemeinsame Teilfolge).

    Reihenfolge zaehlt: Dieselbe Signatur an anderer Stelle im Frame ist
    wahrscheinlich ein anderes Objekt. Eine LCS ueber Signaturen ist dafuer das
    einfachste Verfahren, das Einfuegungen und Auslassungen vertraegt.
    """
    a = [signature(d) for d in previous]
    b = [signature(d) for d in current]
    n, m = len(a), len(b)
    # Speicherarme LCS: Laenge ueber zwei Zeilen, Rueckverfolgung ueber Tabelle
    # nur, wenn die Frames klein genug sind (hier: bis ~5000 x 5000).
    table = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        row, nxt = table[i], table[i + 1]
        ai = a[i]
        for j in range(m - 1, -1, -1):
            row[j] = nxt[j + 1] + 1 if ai == b[j] else max(nxt[j], row[j + 1])
    pairs: list[tuple[int, int]] = []
    i = j = 0
    while i < n and j < m:
        if a[i] == b[j]:
            pairs.append((i, j))
            i += 1
            j += 1
        elif table[i + 1][j] >= table[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def analyze(dff: fifo.Dff) -> dict:
    summaries = fifo.summarize(dff)
    report = {"file": str(dff.path), "version": dff.version, "game_id": dff.game_id,
              "frames": [], "pairs": []}
    for i, s in enumerate(summaries):
        frame = dff.frames[i]
        updates = Counter()
        for u in frame.updates:
            updates[{1: "texture", 2: "xf_data", 4: "vertex_stream", 8: "tmem"}.get(u.kind, str(u.kind))] += len(u.data)
        pos_kinds = Counter(d.pos_kind for d in s.draws)
        ortho = sum(1 for d in s.draws if d.projection[5] & 1)  # 0x1025: Bit 0 = orthographisch
        report["frames"].append({
            "fifo_bytes": len(frame.data), "decoded_bytes": s.bytes_decoded,
            "stopped_early": s.stopped_early, "unknown_opcodes": s.unknown_opcodes,
            "draws": len(s.draws),
            "vertices": sum(d.vertices for d in s.draws),
            "draws_direct_positions": pos_kinds.get(1, 0),
            "draws_indexed_positions": pos_kinds.get(2, 0) + pos_kinds.get(3, 0),
            "draws_per_vertex_matrix": sum(1 for d in s.draws if d.per_vertex_matrix),
            "draws_orthographic": ortho,
            "xf_matrix_loads_immediate": s.xf_matrix_loads,
            "xf_matrix_loads_indexed": s.xf_indexed_loads,
            "xf_matrix_loads_indexed_unresolved": s.xf_indexed_unresolved,
            "projection_loads": s.projection_loads,
            "display_lists": s.display_lists,
            "memory_updates_bytes": dict(updates),
        })
    for i in range(1, len(summaries)):
        prev, cur = summaries[i - 1].draws, summaries[i].draws
        pairs = match(prev, cur)
        matrix_changed = sum(1 for a, b in pairs
                             if (prev[a].matrices_hash != cur[b].matrices_hash
                                 if cur[b].per_vertex_matrix
                                 else prev[a].matrix != cur[b].matrix))
        index_changed = sum(1 for a, b in pairs if prev[a].matrix_index != cur[b].matrix_index)
        proj_changed = sum(1 for a, b in pairs if prev[a].projection != cur[b].projection)
        report["pairs"].append({
            "frames": [i - 1, i],
            "draws_previous": len(prev), "draws_current": len(cur),
            "matched": len(pairs),
            "matched_share_of_current": round(len(pairs) / len(cur), 4) if cur else None,
            "matched_matrix_changed": matrix_changed,
            "matched_matrix_index_changed": index_changed,
            "matched_projection_changed": proj_changed,
            "matched_per_vertex_matrix": sum(1 for a, b in pairs if cur[b].per_vertex_matrix),
            "matched_direct_positions": sum(1 for a, b in pairs if cur[b].pos_kind == 1),
        })
    return report


