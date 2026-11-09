#!/usr/bin/env python3
"""Pitch-transition candidate enumeration for Module 1 Output 3."""

from __future__ import annotations

from dataclasses import dataclass
import contextlib
import importlib.util
import io
import math
import os
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from eagleview_geometry_parser import EagleViewGeometry
from facet_basis import facet_fall_xy

_FLAT_FALL_TOL = 1e-9


def rise_above_edge(geom, edge_line_id, face_id) -> float:
    """How far (ft) a facet's highest point rises above the shared edge's HIGHEST point. THE ONE copy
    (FRAME v106): transition_events.upper_face_id used to hold its own, and the flat-facet rule below
    needs the same measurement, so it lives here — upstream of transition_events, which imports it."""
    edge_z = max(float(geom.points[pid][2]) for pid in geom.lines[str(edge_line_id)].path)
    face = geom.faces[str(face_id)]
    return max(float(geom.points[pid][2]) for lid in face.line_ids for pid in geom.lines[lid].path) - edge_z


def _fall_is_flat(f) -> bool:
    return (float(f[0]) ** 2 + float(f[1]) ** 2) ** 0.5 < _FLAT_FALL_TOL


def is_valley_typed(geom, line_id) -> bool:
    """THE ONE test for "EagleView typed this edge a valley" (FRAME v106.3).

    There were TWO, and they were not equivalent: this one, and `type == "VALLEY"` in
    `candidate_emitters.emit_transition_candidates`. The second was **dead code** — it filtered the
    enumerator's output, which has already dropped every valley-typed edge, so across 152 candidates on six
    real claims it had **zero** to drop. A dead guard with a different predicate is worse than none: it
    reads as a safeguard, and the moment the enumerator's exclusion is relaxed it wakes up with the other
    semantics. Collapsing it HERE, before anything relaxes that exclusion, is the point of doing this first.
    """
    return "VALLEY" in str(geom.lines[str(line_id)].type).upper()


def transition_for_pair(geom, line_id, face_a_id, face_b_id, fA, fB):
    """THE ONE decision: is this shared edge a transition? -> (two_condition, true_transition).

    Every ground on which an edge can be one lives here, in one place, so that adding another is adding an
    INPUT to this function rather than a branch somewhere else. Today there is one input, the geometry:

      * frozen `transition_detect` — the pitch difference, the shallow shared edge, and the two falls
        agreeing (`dot(fA, fB) > 0`); and
      * the FLAT-FACET rule (v106.0), because a flat facet has no fall, so that third condition is not
        false but UNANSWERABLE (`dot((0,0), f) == 0` for every f). Elevation decides instead, by the same
        measurement `upper_face_id` uses: the neighbour that rises above the shared edge. Joseph,
        2026-11-01: "1 of those 4 sides abuts an up-slope facet. The other 3 are down-slopes. The
        flat-to-steep (up slope) is the transition."

    A pitched pair never reaches the flat branch, so every existing render is untouched.
    """
    face_a = geom.faces[str(face_a_id)]
    face_b = geom.faces[str(face_b_id)]
    line = geom.lines[str(line_id)]
    eA = geom.points[line.path[0]]
    eB = geom.points[line.path[-1]]
    two_condition, true_transition = transition_detect(eA, eB, face_a.pitch, face_b.pitch, fA, fB)
    if two_condition and not true_transition and (_fall_is_flat(fA) or _fall_is_flat(fB)):
        flat_id, steep_id = ((face_a_id, face_b_id) if _fall_is_flat(fA) else (face_b_id, face_a_id))
        true_transition = (rise_above_edge(geom, line_id, steep_id)
                           > rise_above_edge(geom, line_id, flat_id))
    return bool(two_condition), bool(true_transition)

Point3 = Tuple[float, float, float]
Point2 = Tuple[float, float]


_REGRESSION_ENGINE = None


def _quiet_import_regression_engine():
    global _REGRESSION_ENGINE
    if _REGRESSION_ENGINE is not None:
        return _REGRESSION_ENGINE
    spec = importlib.util.find_spec("geometry_core")
    if spec is None or spec.loader is None:
        raise ImportError("geometry_core")
    module = importlib.util.module_from_spec(spec)
    cwd = os.getcwd()
    try:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                spec.loader.exec_module(module)
            except SystemExit as exc:
                if exc.code not in (0, None):
                    raise
    finally:
        os.chdir(cwd)
    _REGRESSION_ENGINE = module
    return module


def _quiet_import_regression_symbol(name: str):
    return getattr(_quiet_import_regression_engine(), name)


_engine = _quiet_import_regression_engine()
transition_detect = _engine.transition_detect
edge_contacts = _engine.edge_contacts
mkframe_pts = _engine.mkframe_pts


@dataclass(frozen=True)
class TransitionCandidate:
    edge_id: str
    face_a_id: str
    face_b_id: str
    face_a_designator: str
    face_b_designator: str
    endpoint_ids: Tuple[str, str]
    eA: Point3
    eB: Point3
    pA: float
    pB: float
    fA: Tuple[float, float]
    fB: Tuple[float, float]
    edge_total_LF: float
    two_condition: bool
    true_transition: bool


def enumerate_transition_candidates(geom: EagleViewGeometry) -> List[TransitionCandidate]:
    """Enumerate every shared-edge roof-face pair and let frozen transition_detect filter it."""
    line_to_roof_faces: Dict[str, List[str]] = {}
    for face_id, face in geom.roof_faces.items():
        for line_id in face.line_ids:
            line_to_roof_faces.setdefault(line_id, []).append(face_id)

    candidates: List[TransitionCandidate] = []
    for line_id in sorted(line_to_roof_faces, key=_line_sort_key):
        face_ids = line_to_roof_faces[line_id]
        if len(face_ids) != 2:
            continue
        # EV VALLEY-typed lines are valleys, not pitch transitions: exclude from the automatic transition
        # pool. (EV typing is authoritative for this; rare mistypes are handled by user confirmation of
        # repair events, not by auto-detection.) FRAME v106.3: asked of is_valley_typed, THE ONE test.
        if is_valley_typed(geom, line_id):
            continue
        face_a_id, face_b_id = sorted(face_ids, key=_face_sort_key)
        face_a = geom.faces[face_a_id]
        face_b = geom.faces[face_b_id]
        if face_a.pitch is None or face_b.pitch is None:
            continue
        line = geom.lines[line_id]
        endpoint_ids = (line.path[0], line.path[-1])
        eA = geom.points[endpoint_ids[0]]
        eB = geom.points[endpoint_ids[1]]
        pts_a = [geom.points[pid] for pid in geom.ordered_face_point_ids(face_a_id)]
        pts_b = [geom.points[pid] for pid in geom.ordered_face_point_ids(face_b_id)]
        fA = facet_fall_xy(pts_a)
        fB = facet_fall_xy(pts_b)
        # FRAME v106.3 — ONE DECISION, asked once. Both grounds (transition_detect and the flat-facet
        # rule) live in transition_for_pair; this loop enumerates pairs and does not decide anything.
        two_condition, true_transition = transition_for_pair(geom, line_id, face_a_id, face_b_id, fA, fB)
        candidates.append(TransitionCandidate(
            edge_id=line_id,
            face_a_id=face_a_id,
            face_b_id=face_b_id,
            face_a_designator=face_a.designator,
            face_b_designator=face_b.designator,
            endpoint_ids=endpoint_ids,
            eA=eA,
            eB=eB,
            pA=float(face_a.pitch),
            pB=float(face_b.pitch),
            fA=fA,
            fB=fB,
            edge_total_LF=_line_length_3d(geom, line_id),
            two_condition=bool(two_condition),
            true_transition=bool(true_transition),
        ))
    return candidates


def confirmed_transitions(geom: EagleViewGeometry) -> List[TransitionCandidate]:
    return [c for c in enumerate_transition_candidates(geom) if c.true_transition]


def transition_contact_readings(
    geom: EagleViewGeometry,
    transition: TransitionCandidate,
    selected_valley_ids: Optional[Iterable[str]] = None,
    res: float = 0.04,
) -> List[Mapping[str, object]]:
    """Soft-read contact on each side of a confirmed transition using frozen edge_contacts."""
    selected = set(selected_valley_ids or [])
    readings: List[Mapping[str, object]] = []
    for face_id in (transition.face_a_id, transition.face_b_id):
        face = geom.faces[face_id]
        engine_face = geom.engine_facet(face_id)
        frame = geom.face_frame(face_id)
        line = geom.lines[transition.edge_id]
        edge = [(
            tuple(float(v) for v in frame(geom.points[line.path[0]])),
            tuple(float(v) for v in frame(geom.points[line.path[-1]])),
            "TRANSITION",
            transition.edge_total_LF,
        )]
        valleys = []
        for valley_id in selected:
            if valley_id in face.line_ids and "VALLEY" in geom.lines[valley_id].type.upper():
                valleys.append(geom.valley_event_for_face(face_id, valley_id))
        contact_lf = 0.0
        if valleys:
            contact = edge_contacts(engine_face.facet, valleys, edge, res=res)
            contact_lf = float(contact["TRANSITION"][0])
        readings.append({
            "edge_id": transition.edge_id,
            "face_id": face_id,
            "designator": face.designator,
            "contact_LF": contact_lf,
            "edge_total_LF": transition.edge_total_LF,
            "contact_pct": (contact_lf / transition.edge_total_LF * 100.0) if transition.edge_total_LF else 0.0,
            "selected_valley_ids_used": sorted(v for v in selected if v in face.line_ids),
        })
    return readings


def _line_length_3d(geom: EagleViewGeometry, line_id: str) -> float:
    line = geom.lines[line_id]
    return float(sum(math.dist(geom.points[a], geom.points[b]) for a, b in zip(line.path, line.path[1:])))


def _line_sort_key(line_id: str) -> Tuple[str, int]:
    prefix = "".join(ch for ch in line_id if not ch.isdigit())
    number = int("".join(ch for ch in line_id if ch.isdigit()) or "0")
    return (prefix, number)


def _face_sort_key(face_id: str) -> Tuple[str, int]:
    prefix = "".join(ch for ch in face_id if not ch.isdigit())
    number = int("".join(ch for ch in face_id if ch.isdigit()) or "0")
    return (prefix, number)
