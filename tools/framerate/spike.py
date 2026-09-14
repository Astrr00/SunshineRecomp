"""Zuordnung von Zeichenbefehlen aufeinander folgender Frames (WP13).

Siehe tools/framerate/__main__.py fuer die Befehlszeile.
"""

from __future__ import annotations

import math
import struct
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
    # Gemeinsamer Anfang und gemeinsames Ende werden direkt zugeordnet; die
    # LCS-Tabelle braucht nur der Rest dazwischen. Bei identischen Frames (der
    # Regelfall in den Messungen) kostet das O(n) statt O(n*m).
    head = 0
    while head < len(a) and head < len(b) and a[head] == b[head]:
        head += 1
    tail = 0
    while (tail < len(a) - head and tail < len(b) - head
           and a[-1 - tail] == b[-1 - tail]):
        tail += 1
    pairs = [(i, i) for i in range(head)]
    pairs += [(i + head, j + head)
              for i, j in _lcs(a[head:len(a) - tail], b[head:len(b) - tail])]
    pairs += [(len(a) - tail + k, len(b) - tail + k) for k in range(tail)]
    return pairs


def _lcs(a: list, b: list) -> list[tuple[int, int]]:
    n, m = len(a), len(b)
    if not n or not m:
        return []
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


def _f32(word: int) -> float:
    return struct.unpack("<f", struct.pack("<I", word))[0]


def motion(previous: fifo.Draw, current: fifo.Draw) -> tuple[float, float] | None:
    """Bewegung der Positionsmatrix eines zugeordneten Zeichenbefehls.

    Liefert (Verschiebung, Drehanteil): die Laenge der Differenz der vierten
    Spalte (Translation, in Spieleinheiten) und die Frobenius-Norm der
    Differenz des 3x3-Anteils. None, wenn die Matrix je Vertex kommt (dann
    gibt es keine einzelne Matrix) oder Werte nicht endlich sind.
    """
    if current.per_vertex_matrix or previous.per_vertex_matrix:
        return None
    a, b = previous.matrix, current.matrix
    if len(a) != 12 or len(b) != 12:
        return None
    if not all(math.isfinite(v) for v in a + b):
        return None
    translation = math.sqrt(sum((b[i] - a[i]) ** 2 for i in (3, 7, 11)))
    rotation = math.sqrt(sum((b[i] - a[i]) ** 2 for i in range(12) if i not in (3, 7, 11)))
    return translation, rotation


def _percentile(values: list[float], share: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))]


def cut_verdict(pair: dict, previous: dict | None = None, share_floor: float = 0.6,
                hard_jump: float = 1000.0, jump_floor: float = 50.0, jump_ratio: float = 8.0) -> bool:
    """Heuristik fuer einen Schnitt zwischen zwei Frames.

    Drei Regeln, kalibriert an den Aufzeichnungen (docs/11-FRAMERATE-SPIKE.md):

    1. Weniger als ``share_floor`` der Zeichenbefehle zuordenbar: anderer
       Inhalt (Filmuebergang 0 %, Titel gegen Dateiauswahl 38 %).
    2. Median der Verschiebung der zugeordneten Positionsmatrizen ueber
       ``hard_jump``: gleicher Inhalt, andere Kamera (Titel gegen
       Dateiauswahl: 1.638). Kameraschwenks in Zwischensequenzen erreichen
       263 je Frame, darum liegt die Schwelle weit darueber.
    3. Sprung gegenueber dem Vorpaar: Verschiebung ueber ``jump_floor`` und
       mehr als ``jump_ratio``-mal so gross wie im Vorpaar. Ein Schwenk
       waechst stetig (41, 118, 205, 263, 229 ...), ein Schnitt kommt aus dem
       Stand. Ein abrupt beginnender Schwenk (126 aus dem Stand) wird dabei
       einmal als Schnitt gewertet: ein ausgelassenes Zwischenbild, kein
       Geisterbild.
    """
    share = pair.get("matched_share_of_current")
    if share is not None and share < share_floor:
        return True
    median = pair.get("motion_translation_median")
    if median is None:
        return False
    if median > hard_jump:
        return True
    if previous is not None and median > jump_floor:
        before = previous.get("motion_translation_median")
        if before is not None and median > jump_ratio * max(before, 0.0):
            return True
    return False


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
        ortho = sum(1 for d in s.draws if d.projection[6] == 1)  # 0x1026: Projektionstyp
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
        moves = [m for m in (motion(prev[a], cur[b]) for a, b in pairs) if m is not None]
        translations = [m[0] for m in moves if m[0] > 0]
        rotations = [m[1] for m in moves if m[1] > 0]
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
            "motion_draws": len(moves),
            "motion_translation_median": _percentile(translations, 0.5),
            "motion_translation_p90": _percentile(translations, 0.9),
            "motion_translation_max": max(translations) if translations else None,
            "motion_rotation_median": _percentile(rotations, 0.5),
            "motion_rotation_p90": _percentile(rotations, 0.9),
        })
        report["pairs"][-1]["cut"] = cut_verdict(
            report["pairs"][-1], report["pairs"][-2] if len(report["pairs"]) > 1 else None)
    return report


