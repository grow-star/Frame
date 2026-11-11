#!/usr/bin/env python3
"""
MODULE 3 — COMPARISON BUILDER + FROZEN YAGER COMPARISON ORACLE  (item 4)
=======================================================================
First place the WHOLE comparison runs against a known-good expected result.
Builds `scope_comparison` from the required side (Module 2 seed, keyed/normalized
by Module 3 §2.4) and a frozen carrier `carrier_scope_summary`, then asserts the
6-state assignment, the hybrid tolerance, the signed difference, and the §2.7
precondition.

SCOPE / HONESTY (read this):
  The required side is the FROZEN Module 2 SEED (facet D), keyed by the same
  Module 3 normalization proven in item 3. The carrier side is a FROZEN fixture
  built on the YAGER / State Farm identity but with quantities deliberately
  SEED-ALIGNED to facet D's area — i.e. the §2.7 shared-physical-area precondition
  is satisfied by construction — and crafted to fire each of the 6 states + both
  tolerance bases. It is NOT the raw whole-roof Yager statement (1.55 SQ shakes,
  154.77 LF valley); a whole-roof Yager comparison needs the full 20-side Module 2,
  which is still gated on the Module 2 grow. This oracle proves the BUILDER; it
  grows into the real whole-roof Yager comparison when Module 2 grows.

  Proves the comparison LOGIC (deterministic). Does NOT run the LLM parser or
  Module 1/2 (imported/frozen). No F9, no Authority, no policy/coverage.

FRAME ARC-04a: THE ORACLE'S FIXTURES AND SELF-TESTS LEFT deploy/. The frozen seed facet D (`_D`, `_required()`),
YAGER_CARRIER, EXPECTED, the five self-tests and the `__main__` entry moved byte-for-byte to
verification/module3_comparison_oracle_seed.py (run by verification/module3_comparison_oracle_seed_regression.py).
This module now holds the comparison BUILDER only — the production code page 3 boots — unchanged. With the seed
gone it no longer imports the scope contract or the roof-system registry: it never scopes anything itself.
"""

from module3_keying import key_and_normalize
from shared_category_registry import REGISTRY_SET
from shared_category_registry import field_category_ids   # FRAME v104e: bridge 4 RETIRED here — membership, no package picked
from operation_dimension import (
    apply_operation_overlay,
    carrier_operation_for_category,
    required_operation_for_category,
    default_required_operation,
    operation_delta,
    R_AND_R, REPLACE,
)

# v72 DEFECT 2 — the required ACTIVITY CODE depends on REPAIR vs REPLACEMENT (Joseph, binding):
#   REPAIR       -> every component is R&R.
#   REPLACEMENT  -> the shakes are R&R; most other components are REPLACE (the carrier's position is
#                   they come off with the shakes anyway).
# EXCEPT the items below, which are ALWAYS R&R in BOTH contexts. This list is NOT exhaustive — Joseph:
# "the examples I provided are the common ones carriers typically agree on." It is a single named
# constant precisely so the next item is a ONE-LINE addition, never a scattered conditional.
ALWAYS_R_AND_R = frozenset({
    "CHIMNEY_FLASH",   # chimney flashings
    "VENT_CAP",        # rain caps / rain cap & collars
    "POWER_VENT",      # power vent covers
    # add the next carrier-agreed always-R&R category id here — one line.
})


# FRAME v104e: bridge 4 RETIRED in _required_op_ctx — "non-shake" is "not ANY registered system's field covering"
# (field_category_ids(), no package picked), the same membership operation_dimension.default_required_operation asks;
# on a mixed roof every covering stays R_AND_R on a full replacement. (Outside the function: its source is compared
# semantically to v97.1's by two_facet_operation_regression.)
def _required_op_ctx(category_id, required_operations, is_replacement):
    """Context-aware required operation. A Page-3 assertion still wins; then the ALWAYS_R_AND_R
    exception; then the §2.1 default, promoted to REPLACE for non-shake components on a full
    replacement. operation_dimension is untouched — the context is layered on here at comparison
    time, exactly like required_operations."""
    if required_operations and category_id in required_operations:
        return required_operations[category_id]
    if category_id in ALWAYS_R_AND_R:
        return R_AND_R
    base = default_required_operation(category_id)
    if is_replacement and base == R_AND_R and category_id not in field_category_ids():
        return REPLACE
    return base

# §2.5 tolerance floors (continuous units); EA is exact-only
FLOORS = {"SQ": 0.10, "LF": 0.50, "SF": 5.0, "HR": 0.25}

def classify(required, approved, unit):
    """§2.5 -> (state, tolerance_basis, signed_diff). signed_diff = required - approved."""
    signed = round(required - approved, 4)
    if unit == "EA":
        return ("MATCHED", "EXACT_EA", signed) if required == approved \
               else ("QUANTITY_DIFFERENCE", "EXACT_EA", signed)
    diff = abs(required - approved)
    rel = diff / required if required else float("inf")
    if rel <= 0.02:
        return "MATCHED", "RELATIVE_2PCT", signed          # measurement noise
    if diff <= FLOORS[unit]:
        return "MATCHED", "ABSOLUTE_FLOOR", signed         # tiny-quantity noise
    return "QUANTITY_DIFFERENCE", "OUTSIDE_TOLERANCE", signed  # real difference (waste NOT absorbed)

# RIDGE_CAPS + HIP_CAPS are folded into the combined key (§2.4.3); compared as RIDGE_HIP_CAP
_FOLD = {"RIDGE_CAPS", "HIP_CAPS"}
# v71 DEFECT 1: the required side folds ridge+hip into the combined RIDGE_HIP_CAP key, but a carrier
# writes them as RIDGE_CAPS and/or HIP_CAPS (overwhelmingly ONE "Hip / Ridge cap" line -> RIDGE_CAPS).
# The combined required must be reconciled against the SUM of whichever of those the carrier carries,
# so a single combined carrier line AND a split ridge/hip pair both meet the combined requirement
# instead of printing a false "not present" beside a stranded acknowledgement.
_CARRIER_FOLD = {"RIDGE_HIP_CAP": ("RIDGE_CAPS", "HIP_CAPS")}

def build_comparison(required, carrier, required_operations=None, is_replacement=False):
    """required: keyed M2 entries (item 3). carrier: frozen carrier_scope_summary or None.

    required_operations (ADDITIVE, Operation Dimension §2/§3): optional per-category mapping
    {category_id -> canonical operation} supplied by Page 3. When omitted, §2.1 defaults apply
    (e.g. the field covering -> R_AND_R). Module 2 is NOT modified — the required operation is
    layered on here, at comparison time. Backward compatible: existing 2-arg callers get the
    defaults, and no line moves to OPERATION_DIFFERENCE unless BOTH operations are known and
    differ, so every pre-existing MATCHED case is preserved.
    """
    # FRAME v104e: bridge 4 RETIRED here. The site only asks "is this category a field covering?" — answered for
    # every registered system at once, no package picked. The dual's figures are already per system in `required`
    # (key_and_normalize, v104d); the map is NOT re-keyed by system (_aggregate_lines owns that rule).
    _fids = field_category_ids()
    if carrier is None:                                    # §2.7 optional-statement path
        return {"mode": "REQUIRED_SCOPE_ONLY", "comparison_precondition": None,
                "lines": [], "required_only": [k for k in required if k not in _FOLD]}

    approved, excluded, unmapped = carrier["approved"], carrier["excluded"], carrier["unmapped"]
    lines, matched = [], set()

    for rkey, rent in required.items():
        if rkey in _FOLD:                                  # folded into combined; not a standalone line
            continue
        cat = "RIDGE_HIP_CAP" if rkey == "RIDGE_HIP_CAP__combined" else rkey
        runit, rqty = rent["comparison_unit"], rent["comparison_quantity"]
        line = {"category_id": cat, "required_quantity": rqty, "required_unit": runit}
        if cat in _fids:                       # dual value (§2.4.2)
            line["supporting_quantity"] = rent.get("supporting_quantity")
            line["supporting_unit"] = "EA"

        # v77 DEFECT 5 (Joseph, binding): a category the user gave DISTINCT LABELS to on page 2 (a
        # user-placed, user-labelled appurtenance, e.g. "6\" pipe jack") splits into per-label rows.
        #   - The GENERIC portion compares against the carrier's generic line (rule 4) — on the real
        #     estimate the carrier wrote one "R&R Flashing - pipe jack" line, which matches the generic
        #     "Pipe-jack flashing" required row exactly.
        #   - Each USER-LABELLED row is its OWN required row with NO carrier counterpart, because the
        #     carrier did not scope it. That is the argument the row exists to make.
        # The carrier's 4 EA is NOT spread across both rows; the generic row matches and the labelled
        # row carries its own quantity. A carrier line that itself carries a distinguishing label (a
        # "lead pipe jack") would match a required row of the same label where one exists (via `approved`
        # keyed by that label); with no such carrier label today, it falls to the generic row.
        # Categories with no user labels take the existing single-line path, so every prior report is
        # byte-identical.
        _labels = rent.get("labels") or []
        _user_labels = [L for L in _labels if L.get("user_defined")]
        if _user_labels and cat not in _fids and _CARRIER_FOLD.get(cat) is None:
            _generic_qty = round(sum(L["qty"] for L in _labels if not L.get("user_defined")), 4)
            _gen_cite = next((L.get("citation") for L in _labels if not L.get("user_defined")), None)
            if _generic_qty > 1e-9:
                gline = {"category_id": cat, "required_quantity": _generic_qty, "required_unit": runit,
                         "row_citation": _gen_cite}
                if cat in approved:
                    a = approved[cat]; matched.add(cat)
                    if a["unit"] != runit:
                        gline.update(state="UNMAPPED_REVIEW", note="unit_mismatch",
                                     approved_quantity=a["qty"], approved_unit=a["unit"])
                    else:
                        st, basis, diff = classify(_generic_qty, a["qty"], runit)
                        gline.update(state=st, approved_quantity=a["qty"], approved_unit=a["unit"],
                                     tolerance_basis=basis,
                                     required_scope_difference=(diff if st == "QUANTITY_DIFFERENCE" else None))
                        if a.get("rr_pair"):
                            gline["carrier_pair_note"] = a.get("pair_note")
                elif cat in excluded:
                    gline.update(state="MISSING_FROM_CARRIER_EXCLUDED",
                                 exclusion_reason=excluded[cat]["reason"],
                                 exclusion_source_text=excluded[cat]["source_text"])
                else:
                    gline.update(state="MISSING_FROM_CARRIER")
                apply_operation_overlay(gline, _required_op_ctx(cat, required_operations, is_replacement),
                                        carrier_operation_for_category(carrier, cat))
                lines.append(gline)
            for L in _labels:
                if not L.get("user_defined"):
                    continue
                # A carrier line whose OWN label matches this user label would compare here; none does
                # on the generic estimate, so the row shows no carrier counterpart (rule 4).
                uline = {"category_id": cat, "label": L["label"],
                         "required_quantity": L["qty"], "required_unit": L["unit"],
                         "state": "MISSING_FROM_CARRIER", "row_citation": L.get("citation")}
                apply_operation_overlay(uline, _required_op_ctx(cat, required_operations, is_replacement), None)
                lines.append(uline)
            continue

        # v71 DEFECT 1: a COMBINED required key (RIDGE_HIP_CAP) is reconciled against the SUM of the
        # carrier ids it folds (RIDGE_CAPS + HIP_CAPS), whichever the carrier actually carries — one
        # combined line or a split pair. Both carrier ids are marked matched so neither strands as an
        # ACKNOWLEDGED_ONLY line, and the combined requirement gets a single real comparison row.
        combine_ids = _CARRIER_FOLD.get(cat)
        if combine_ids is not None:
            present = [cid for cid in combine_ids if cid in approved]
            if present:
                for cid in present:
                    matched.add(cid)
                aunits = {approved[cid]["unit"] for cid in present}
                summed = round(sum(approved[cid]["qty"] for cid in present), 4)
                if aunits != {runit}:                      # §2.4.4 no hidden conversion
                    line.update(state="UNMAPPED_REVIEW", note="unit_mismatch",
                                approved_quantity=summed, approved_unit=sorted(aunits)[0])
                else:
                    st, basis, diff = classify(rqty, summed, runit)
                    line.update(state=st, approved_quantity=summed, approved_unit=runit,
                                tolerance_basis=basis,
                                required_scope_difference=(diff if st == "QUANTITY_DIFFERENCE" else None))
                    if len(present) > 1:
                        line["combined_carrier_from"] = present   # carrier split ridge/hip into two
                    for cid in present:
                        if approved[cid].get("rr_pair"):
                            line["carrier_pair_note"] = approved[cid].get("pair_note")
                            break
            else:
                line.update(state="MISSING_FROM_CARRIER")
            cops = {carrier_operation_for_category(carrier, cid) for cid in present}
            cops.discard(None)
            apply_operation_overlay(
                line,
                _required_op_ctx(cat, required_operations, is_replacement),
                cops.pop() if len(cops) == 1 else None,
            )
            lines.append(line)
            continue

        if cat in approved:
            a = approved[cat]; matched.add(cat)
            _aops = a.get("operations")
            if a["unit"] != runit:                         # §2.4.4 no hidden conversion
                line.update(state="UNMAPPED_REVIEW", note="unit_mismatch",
                            approved_quantity=a["qty"], approved_unit=a["unit"])
            elif _aops and len(_aops) > 1:
                # v75: the carrier funded MORE THAN ONE operation on this category. State the required
                # quantity ONCE (the anchored number) and list EACH carrier operation with its own
                # quantity — never a combined total, never a summed-across-operations figure. Attach the
                # operation-difference explanation to the operations that differ from the required one.
                req_op = _required_op_ctx(cat, required_operations, is_replacement)
                approved_ops = []
                for o in _aops:
                    row = {"operation": o["op"], "quantity": o["qty"], "unit": runit}
                    if req_op and o["op"] != req_op:
                        row["operation_delta"] = operation_delta(req_op, o["op"])
                    approved_ops.append(row)
                line.update(state="OPERATION_SPLIT", required_operation=req_op,
                            approved_operations=approved_ops)
                lines.append(line)
                continue
            else:
                st, basis, diff = classify(rqty, a["qty"], runit)
                line.update(state=st, approved_quantity=a["qty"], approved_unit=a["unit"],
                            tolerance_basis=basis,
                            required_scope_difference=(diff if st == "QUANTITY_DIFFERENCE" else None))
                # Carry the engine-authored R&R pair note (authored once in manual_carrier_entry via
                # the shared consolidate_RR rule) so the report can explain why the approved quantity
                # is the Replace side and not the naive Remove+Replace sum.
                if a.get("rr_pair"):
                    line["carrier_pair_note"] = a.get("pair_note")
        elif cat in excluded:                              # §2.2 neutral factual surfacing
            line.update(state="MISSING_FROM_CARRIER_EXCLUDED",
                        exclusion_reason=excluded[cat]["reason"],
                        exclusion_source_text=excluded[cat]["source_text"])
        else:
            line.update(state="MISSING_FROM_CARRIER")
        # ADDITIVE operation overlay (§3.2–§3.5): attach op attributes; rescue a would-be
        # MATCHED line to OPERATION_DIFFERENCE only when both ops are known and differ.
        apply_operation_overlay(
            line,
            _required_op_ctx(cat, required_operations, is_replacement),
            carrier_operation_for_category(carrier, cat),
        )
        lines.append(line)

    for cat, a in approved.items():                        # carrier-only -> acknowledgement
        if cat not in matched:
            ack = {"category_id": cat, "state": "ACKNOWLEDGED_ONLY",
                   "approved_quantity": a["qty"], "approved_unit": a["unit"]}
            # carrier-only line: no required operation to compare (§3.4 unchanged); attach the
            # carrier operation as supporting detail. Never rescues (state stays ACKNOWLEDGED_ONLY).
            apply_operation_overlay(ack, None, carrier_operation_for_category(carrier, cat))
            lines.append(ack)

    unresolved = [{"description": d, "state": "UNMAPPED_REVIEW"} for d in unmapped]
    return {"mode": "COMPARISON", "comparison_precondition": "SHARED_AREA_ASSERTED_BY_UPLOAD",
            "lines": lines, "unresolved": unresolved}


if __name__ == "__main__":
    # FRAME ARC-04a: the oracle's self-tests and their `__main__` entry MOVED, byte-for-byte, to
    # verification/module3_comparison_oracle_seed.py (they held 28 shipped material-term sites); the suite runs them through
    # verification/module3_comparison_oracle_seed_regression.py. Running this module no longer runs them; it says where
    # they went and exits non-zero rather than passing silently.
    print("deploy/module3_comparison_oracle.py: the Yager oracle self-tests moved to "
          "verification/module3_comparison_oracle_seed.py (FRAME ARC-04a); the suite runs them via "
          "module3_comparison_oracle_seed_regression.py.")
    raise SystemExit(2)
