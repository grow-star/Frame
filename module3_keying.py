#!/usr/bin/env python3
"""Production home for Module 3 keying / normalization.

Extracted verbatim from module3_keying_regression.py so production code no
longer imports from a regression suite.
"""
from collections.abc import Mapping

from shared_category_registry import (field_category_id, line_system, material_splits,   # FRAME v104c: per line
                                      RegistryWiringError)                            # v104d: the mixed-roof gate


def key_and_normalize(m2_lines, affected_SF):
    """Key Module 2's lines by category for the comparison. The field covering compares in SQ through the §2.4.2 dual:
    its affected area / 100, with the EA repair count as the supporting figure.

    FRAME v104d — PER SYSTEM. `affected_SF` is either one number (the claim's affected area) or a mapping
    {system_id: that system's affected SF}. Each field id belongs to exactly one system (a package owns it), so its dual
    is computed from THAT system's area and its supporting EA from ITS OWN lines. With one system a number is exactly
    today's value. With field covering from TWO OR MORE systems a single number RAISES (RegistryWiringError): handing
    each system the whole claim's area is the defect, not the fix — the caller must pass the per-system mapping."""
    # FRAME v104c: PER LINE — a line is a field line when its category is ITS OWN system's field covering
    # (line_system: the line's material_profile_id; a line with none falls back to the sole package, bridge 4
    # narrowed). A merged category is a core id, never a field covering, so it needs no lookup.
    _fsys = {}   # FRAME v104d: field id -> the system whose field covering it is (one system per field id)
    def _is_field(l):
        if not material_splits(l.category_id):
            return False
        _sys = line_system(l, "module3_keying.key_and_normalize: a line with no material")
        if l.category_id == field_category_id(_sys):
            _fsys[l.category_id] = _sys
            return True
        return False
    _fids = set()   # the field-covering ids actually present, for the dual-value entries below
    totals, units, detail = {}, {}, {}
    # v77 DEFECT 5: per-label breakdown within a category. GROUP BY THE USER'S LABEL — a user-placed,
    # user-labelled item (citation 'user-defined', e.g. '6" pipe jack') is a distinct row from the
    # generic category item, and identical labels combine. Matched on label text with case and
    # surrounding whitespace ignored, and nothing else (no fuzzy matching).
    labels = {}   # cid -> { casefold(label) : {"label": str, "qty": float, "unit": str, "user_defined": bool} }
    shake_ea = {}   # FRAME v104d: per field id (so per system) — one system's EA never supports another's figure
    for l in m2_lines:
        _f = _is_field(l)
        if not _f:
            _lab = str(getattr(l, "item", l.category_id) or l.category_id)
            _ud = (getattr(l, "citation", None) == "user-defined")
            _lm = labels.setdefault(l.category_id, {})
            _e = _lm.setdefault(_lab.strip().casefold(),
                                {"label": _lab, "qty": 0.0, "unit": l.unit, "user_defined": False,
                                 "citation": getattr(l, "citation", None)})
            _e["qty"] = round(_e["qty"] + l.qty, 4)
            _e["user_defined"] = _e["user_defined"] or _ud
        if _f:
            # SHAKE compares in SQ (affected_SF/100, the §2.4.2 dual value); the EA count is SUPPORTING
            # only. A mixed roof (v61) carries BOTH a replacement SQ line and a repair EA line under
            # this one id — legitimately two units — so SHAKE is exempt from the single-unit total and
            # guard below. The SQ replacement area is already inside affected_SF; only the EA repair
            # count is summed here, as the supporting figure.
            if str(l.unit) == "EA":
                shake_ea[l.category_id] = round(shake_ea.get(l.category_id, 0.0) + l.qty, 4)
            _fids.add(l.category_id)
            totals.setdefault(l.category_id, 0.0)
            detail.setdefault(l.category_id, []).append((l.item, l.qty, l.unit))
            continue
        totals[l.category_id] = round(totals.get(l.category_id, 0.0) + l.qty, 4)
        units.setdefault(l.category_id, l.unit)
        if units[l.category_id] != l.unit:
            raise ValueError(f"unit conflict within {l.category_id}")   # would be unit_mismatch
        detail.setdefault(l.category_id, []).append((l.item, l.qty, l.unit))

    # FRAME v104d: the dual's area, per system. A mapping answers per system; a single number is claim-level and is
    # correct only when one system has field covering here.
    _systems = sorted(set(_fsys.values()))
    if isinstance(affected_SF, Mapping):
        _missing = [s for s in _systems if s not in affected_SF]
        if _missing:
            raise RegistryWiringError(
                f"FRAME v104d: module3_keying.key_and_normalize — no affected area was given for roof system(s) "
                f"{_missing} (given: {sorted(affected_SF)}). Fix: pass every field-covering system's own affected SF.")
        _area = {s: float(affected_SF[s]) for s in _systems}
    elif len(_systems) > 1:
        raise RegistryWiringError(
            f"FRAME v104d: module3_keying.key_and_normalize — field covering from {len(_systems)} roof systems "
            f"({_systems}) was given ONE affected area ({affected_SF!r}); each system's dual would receive the whole "
            f"claim's area. Fix: pass {{system_id: that system's affected SF}}.")
    else:
        _area = {s: affected_SF for s in _systems}
    entries = {}
    for cid, tot in totals.items():
        if cid in _fids:
            entries[cid] = {                       # dual value (§2.4.2)
                "comparison_quantity": round(_area[_fsys[cid]] / 100.0, 4), "comparison_unit": "SQ",
                "supporting_quantity": shake_ea.get(cid, 0.0), "supporting_unit": "EA",
                "source_detail": detail[cid]}
        else:
            entries[cid] = {"comparison_quantity": tot, "comparison_unit": units[cid],
                            "source_detail": detail[cid],
                            "labels": list(labels.get(cid, {}).values())}

    # ridge/hip combine (§2.4.3): required RIDGE_CAPS + HIP_CAPS -> combined key
    if "RIDGE_CAPS" in totals or "HIP_CAPS" in totals:
        entries["RIDGE_HIP_CAP__combined"] = {
            "comparison_quantity": round(totals.get("RIDGE_CAPS",0.0) + totals.get("HIP_CAPS",0.0), 2),
            "comparison_unit": "LF", "combined_from": ["RIDGE_CAPS","HIP_CAPS"],
            "source_detail": [("RIDGE_CAPS", totals.get("RIDGE_CAPS",0.0)),
                              ("HIP_CAPS",  totals.get("HIP_CAPS",0.0))]}
    return entries, totals

