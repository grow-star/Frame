#!/usr/bin/env python3
"""Layer 3 Piece B: Workbench diagram drawing-data exporter.

This module is intentionally an exporter, not a calculator.  The UI selection is
translated through the same confirmation seam as Piece A, then the frozen Module
1 service and affected_area(return_zone=True) engine path are used to expose the
already-computed affected regions as JSON-safe drawing data.

Returned polygons are raster-zone outlines re-projected into the same shared
roof coordinate frame used by workbench_roof_layout.  They are for drawing red
affected regions and labeling the verified per-event shake count; they are not
per-shake footprints.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from math import ceil
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np

from candidate_display import confirmed_candidates_from_selection
from confirmation_builder import build_confirmation_from_selections
from eagleview_geometry_parser import EagleViewGeometry, parse_eagleview_geometry, _frame_anchor_line
from module1_service import (
    _confirmed_mapping,
    _derived_notch_union_area,
    _dimensional_pens,
    _require_bordering_face,
    _require_candidate,
    _require_notch_candidate,
    _valley_event_for_notch,
    affected_area,
    run_module1_service,
)
from workbench_roof_layout import _xy, _facet_local_to_shared, _local_to_shared_transform
from module2_assembly import _replacement_facet_area, encoding_b_zone, _encoding_b_candidate   # v62/v69: ONE authority for replacement area and for
                                                       # diagram total can never disagree with the scope.
# FRAME ARC-05a: the per-event piece count is a PACKAGE OPERATION (field_piece_count), asked of the one installed package
# that declares it — no longer a direct import of the wood-shake package's _shake_count (package isolation exception E3
# retired). module1_service (imported above) has already registered the installed packages.
from roof_systems import operation_owner as _operation_owner, require_operation as _require_operation
from roof_systems import declares_operation as _declares_operation   # FRAME ARC-06a (E)
from roof_systems import system_for_facet as _system_for_facet, system_for_facets as _system_for_facets
from roof_systems import system_for_profile as _system_for_profile
from roof_systems import geometry_profile_for_facet as _geometry_profile_for_facet   # FRAME ARC-06a (B1)


def _piece_count(affected_sf, measured_profile) -> int:
    """How many pieces of the field covering `affected_sf` takes, from the claim's measured profile: the
    `field_piece_count` operation of the ONE installed package that declares it, repair_factor 1.0 (the diagram's
    fixed value). Before ARC-05a this was _shake_count(sf, 1.0, width, exposure) imported from the wood-shake package,
    with width / exposure read from the profile beside a 7.0 / 10.0 fallback written HERE; the package now reads its
    own settings and its own defaults from the same profile, so every count is unchanged. A covering that declares no
    piece count (a membrane) is never asked; with no declarer, or two, this raises by name (ARC-06 decides mixed
    ownership) — it never fabricates a count."""
    owner = _operation_owner("field_piece_count", "the diagram's per-event piece count")
    return _require_operation(owner, "field_piece_count")(float(affected_sf), 1.0, measured_profile)


def _facet_ids_of(facet_id) -> list:
    """The member facets an event names: 'F7', or a notch's members joined by '/' (the diagram) or '+' (the engine)."""
    return [x for x in str(facet_id).replace("+", "/").split("/") if x]


def _event_piece_system(facet_id, confirmed_selection):
    """FRAME ARC-06a (E): the roof system whose `field_piece_count` answers for THIS event — the event's own facet's
    system (members of a merge must agree: system_for_facets raises otherwise, and such a merge never reaches here)."""
    ids = _facet_ids_of(facet_id)
    return _system_for_facets(ids, confirmed_selection) if len(ids) > 1 else _system_for_facet(ids[0], confirmed_selection)


def _event_piece_count(affected_sf, measured_profile, facet_id, confirmed_selection):
    """FRAME ARC-06a (E): the per-event piece count, PER FACET. Until ARC-06a every event was counted by the one
    package that declares `field_piece_count` (wood shake) — including events on MODBIT facets, a borrowed wood-shake
    EA. Now: the event's own facet's package answers if it declares the operation; otherwise the count is NOT
    APPLICABLE (None) and is never fabricated. `confirmed_selection` None = the pre-ARC-06a call, unchanged."""
    if confirmed_selection is None:
        return _piece_count(affected_sf, measured_profile)
    sid = _event_piece_system(facet_id, confirmed_selection)
    if not _declares_operation(sid, "field_piece_count"):
        return None
    return _require_operation(sid, "field_piece_count")(float(affected_sf), 1.0, measured_profile)
from workbench_seam import XML_TEXT_KEYS, _selection_for_candidate_display
from roof_systems import roof_system_keys, validate_roof_system_selection   # FRAME v104a: the per-facet system contract
from roof_systems import PROJECT_CONFIG_KEY   # FRAME ARC-03a


_REQUIRED_CONFIRMED_KEYS = {
    "selected_valley_ids",
    "single_valley_repairs",
    "multi_valley_facets",
    "penetration_appurtenance_repairs",
    "notch_repairs",
}


def build_diagram_data(geom_or_xml: EagleViewGeometry | str, ui_selection: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return JSON-safe affected-region drawing data for the Workbench UI.

    Parameters
    ----------
    geom_or_xml:
        Either EagleView XML text or a parsed EagleViewGeometry.  If parsed
        geometry is supplied, include the source XML text in ``ui_selection``
        under one of workbench_seam.XML_TEXT_KEYS.
    ui_selection:
        A Workbench display-shaped selection, or the five-collection confirmed
        selection shape. Empty/None is valid and returns no events.

    The function does not compute affected area. It asks the frozen engine for
    the zone mask using affected_area(..., return_zone=True), then traces the
    mask into a drawable outline. The verified affected_SF remains the value
    emitted by run_module1_service.
    """
    selection: Mapping[str, Any] = ui_selection or {}
    geom, xml_text = _resolve_geometry_and_xml(geom_or_xml, selection)
    confirmed_selection = _confirmed_selection_from_ui(geom, selection)

    service_result = run_module1_service(xml_text, confirmed_selection)

    # COMPUTE THE EVENTS, THEN DECIDE. Module 1 builds `components` from valleys / notches /
    # appurtenances only, so a TRANSITION-ONLY selection has ZERO components — yet it is a real
    # repair event whose bands are computed inside _event_regions(). Early-returning on empty
    # components skipped the band code entirely: no shading, and the Continue gate's in-zone
    # penetration check ran against an empty diagram. Emptiness is a property of the EVENTS,
    # not of Module-1's components.
    _unsupported: list = []
    events = _event_regions(service_result.candidate_package.geom, service_result, confirmed_selection,
                            unsupported_out=_unsupported)
    if not events:
        _empty = {
            "events": [],
            "summary": {
                "total_SF": 0.0,
                "total_EA": 0,
                "pct_of_roof": 0.0,
            },
        }
        if _unsupported:
            _empty["summary"]["unsupported_events"] = _unsupported   # FRAME ARC-06a (B1)
        return _empty
    # THE DIAGRAM READS FROM THE MATH. total_SF used to come from `service_result` — a Module-1 value
    # computed BEFORE the transition bands exist — while total_EA was summed from the events (which
    # DO include them). So EA moved and SF did not, and the header contradicted the picture beneath
    # it. Both totals are now summed from the same events, so the summary can never disagree with
    # what was actually drawn, and it matches the scope.
    #
    # This IS the scope's own convention: affected_SF_display_total rounds EACH COMPONENT to 1 dp and
    # sums those (Yager: 1639.4 — the raw component sum is 1639.60 and rounding once at the end would
    # print 1639.6, moving the anchor). So the diagram must likewise sum the per-event DISPLAY values.
    # The corollary matters when one scope component is drawn as TWO regions (a valley zone + the
    # incremental transition band on the same facet): the band region must carry the component's
    # ROUNDED REMAINDER, not its own independent rounding, or the split leaks 0.1 SF. That is done at
    # source, in _transition_regions — not papered over here.
    total_sf = round(float(sum(float(e["affected_SF"]) for e in events)), 1)
    total_ea = int(sum(int(e["shake_count"]) for e in events))
    # pct_of_roof (§4's most persuasive number). TWO fixes from v63:
    #   (2a) it must count REPLACEMENTS, not repair events only — the numerator is total_sf, summed from
    #        ALL events (repairs + replacements), so a full replacement is no longer 0%.
    #   (2b/2c) numerator and denominator must SHARE A BASIS. total_sf is NET of penetrations, so the
    #        denominator is the SHAKEABLE area (facet area minus penetrations), computed by the SAME
    #        per-facet function and per-facet rounding the replacement events use. That makes a
    #        fully-replaced roof read EXACTLY 100.0% by construction: when every facet is marked the
    #        numerator is the sum of _round_sf(_replacement_facet_area) over every facet, which is the
    #        denominator itself — no residual (the old ~1.21 SF gap was exactly the mismatch between the
    #        penetration-inclusive facet-area denominator and the penetration-net numerator).
    geom = service_result.candidate_package.geom
    shakeable_sf = round(float(sum(_round_sf(_replacement_facet_area(geom, f)) for f in geom.roof_faces)), 1)
    pct = round((total_sf / shakeable_sf) * 100.0, 2) if shakeable_sf else 0.0
    out = {
        "events": events,
        "summary": {
            "total_SF": total_sf,
            "total_EA": total_ea,
            "pct_of_roof": pct,
        },
    }
    # FRAME ARC-06a: present ONLY when there is something to say, so a single-covering diagram is byte-identical.
    if _unsupported:
        out["summary"]["unsupported_events"] = _unsupported
    _na = [e["event_label"] for e in events if e.get("piece_count_applicable") is False]
    if _na:
        out["summary"]["piece_count_not_applicable_events"] = _na
    return out


def _resolve_geometry_and_xml(geom_or_xml: EagleViewGeometry | str, selection: Mapping[str, Any]) -> tuple[EagleViewGeometry, str]:
    if isinstance(geom_or_xml, str):
        return parse_eagleview_geometry(geom_or_xml), geom_or_xml
    for key in XML_TEXT_KEYS:
        value = selection.get(key)
        if isinstance(value, str) and value.strip():
            return geom_or_xml, value
    raise ValueError(
        "build_diagram_data needs XML text for the Module 1 service. "
        "Pass XML text as geom_or_xml, or include it in ui_selection under one of: "
        + ", ".join(XML_TEXT_KEYS)
    )


def _confirmed_selection_from_ui(geom: EagleViewGeometry, selection: Mapping[str, Any]) -> Mapping[str, Any]:
    # FRAME v104a: the claim's roof system is validated against this roof's facets on BOTH shapes, and (below) rides
    # onto the converted selection exactly as given — carried to module1_service, read by nothing yet (v104b).
    if PROJECT_CONFIG_KEY in selection:
        # FRAME ARC-03a: a schema_version 1 project — THE SAME carry the scope seam uses (project_config.carry_to_engine),
        # so the diagram and the scope cannot read the project differently. No legacy material key is read.
        from project_config import carry_to_engine
        validate_roof_system_selection(roof_system_keys(selection), geom.roof_faces)   # one authority; exclusions
        _carried = carry_to_engine(selection, xml_text=None, geometry=geom)
        _plain = {k: v for k, v in selection.items() if k not in (PROJECT_CONFIG_KEY,)}
        return {**dict(_confirmed_selection_from_ui(geom, _plain)), **_carried}
    _systems = roof_system_keys(selection)
    if _systems:
        validate_roof_system_selection(_systems, geom.roof_faces)
    if _REQUIRED_CONFIRMED_KEYS.issubset(selection.keys()):
        return selection
    engine_selection = _selection_for_candidate_display(selection)
    confirmed_candidates = confirmed_candidates_from_selection(geom, engine_selection)
    confirmed = build_confirmation_from_selections(confirmed_candidates, geom=geom)
    # User-defined appurtenances carve directly in the engine (no candidate translation),
    # so carry them onto the confirmed selection rather than through candidate_display.
    user_rows = list(engine_selection.get("user_appurtenance_repairs", ()))
    if user_rows:
        confirmed = {**dict(confirmed), "user_appurtenance_repairs": user_rows}
    # BUG FIX: user-confirmed pitch-transition repair events were being SILENTLY DROPPED here.
    # `workbench_seam` carries them (which is why the REPORT was right) but this conversion did not
    # (which is why the DIAGRAM was wrong): the band never became an event, so it neither shaded nor
    # contributed EA/SF. Carried now by exactly the same pattern, from the same source dict.
    # The exposed+damaged gate is NOT duplicated here — it stays enforced downstream in
    # transition_events.selected_transition_repairs(), which requires BOTH to be explicitly True.
    transition_rows = [dict(r) for r in (selection.get("transition_repairs", ()) or ())]
    if transition_rows:
        confirmed = {**dict(confirmed), "transition_repairs": transition_rows}
    # v62 DEFECT 1: replaced facets were dropped here (like transitions once were), so the diagram
    # produced no replacement events and reported ~0 SF for a full roof. Carried now, same pattern.
    replaced_rows = [dict(r) if isinstance(r, dict) else {"face_id": str(r)}
                     for r in (selection.get("replaced_facets", ()) or ())]
    if replaced_rows:
        confirmed = {**dict(confirmed), "replaced_facets": replaced_rows}
    # FRAME v104a.1 (K8): the job's MEASURED shake profile was SILENTLY DROPPED here — the third carry this
    # conversion was missing (transitions v55, replaced facets v62, now this). workbench_seam carries it, so the
    # SCOPE was right; this did not, so every DIAGRAM built from a UI selection fell back to 7 x 10in in
    # _event_regions, and the report's "% of roof" (and the diagram's SF / EA) were wrong on any job measured
    # otherwise. Same three aliases, same order, same guard as workbench_seam: only set when one is present, so a
    # selection with no profile converts exactly as before and _event_regions' fallback is untouched.
    shake_measurements = selection.get("shake_measurements") or selection.get("shakeMeasurements") or selection.get("shake_profile")
    if shake_measurements:
        confirmed = {**dict(confirmed), "shake_measurements": shake_measurements}
    if _systems:
        confirmed = {**dict(confirmed), **_systems}
    return confirmed


def _event_regions(geom: EagleViewGeometry, service_result: Any, confirmed_selection: Mapping[str, Any],
                   unsupported_out: list | None = None) -> list[dict[str, Any]]:
    valley_candidates = {c.source_ids[0]: c for c in service_result.candidate_package.valleys}
    penetration_candidates = {c.source_ids[0]: c for c in service_result.candidate_package.penetrations}
    notch_candidates = {tuple(c.source_ids): c for c in service_result.candidate_package.notches}
    components = iter(service_result.components)
    # FRAME ARC-06a (B1): events the facet's own package refused — collected into the caller's list when it passes one
    unsupported: list[dict[str, Any]] = unsupported_out if unsupported_out is not None else []
    repair_facet_ids = _repair_facet_ids(confirmed_selection)
    replaced_facet_ids = {str(_confirmed_mapping(_it)["face_id"]) for _it in confirmed_selection.get("replaced_facets", [])}
    out: list[dict[str, Any]] = []
    shake_measurements = confirmed_selection.get("shake_measurements") or confirmed_selection.get("shake_profile") or {"width_in": 7.0, "exposure_in": 10.0}
    # FRAME ARC-06a (B1): the claim profile RESOLVED by its own package (so a facet of that package is handed exactly
    # this profile back), and each facet's geometry asks ITS OWN profile (roof_systems.geometry_profile_for_facet).
    _claim = _system_for_profile(shake_measurements).resolve_profile(shake_measurements)
    _sel = confirmed_selection

    def _gp(fid):
        return _geometry_profile_for_facet(fid, _sel, _claim)

    def _refused(component, kind, face_id):
        # FRAME ARC-06a (B1): module1_service left a placeholder for an event the facet's package refused: list it,
        # draw nothing, count nothing.
        if getattr(component, "unsupported_reason", None) is None:
            return False
        unsupported.append({"event_label": str(component.label), "facet_id": str(face_id), "kind": kind,
                            "reason": str(component.unsupported_reason)})
        return True

    for item in confirmed_selection.get("single_valley_repairs", []):
        row = _confirmed_mapping(item)
        component = next(components)
        face_id = str(row["face_id"])
        valley_id = str(row["valley_id"])
        cand = _require_candidate(valley_candidates, valley_id, "valley")
        _require_bordering_face(cand, face_id)
        if _refused(component, "single_valley", face_id):
            continue
        # v69 NINTH DIVERGENCE FIX: an Encoding-B face (self-bounding HIDDEN slit) is reframed in the
        # SCOPE (module2). The diagram must draw the SAME zone, from the SAME authority — never a second
        # reframing here. encoding_b_zone returns the reframed mask+area (or None for a plain facet).
        ebz = encoding_b_zone(geom, face_id, [valley_id], confirmed_selection, _gp(face_id))
        if ebz is not None:
            area, zone, gx, gy, _facet = ebz
            _f, _v, _n, _p, to_shared = _notch_zone_inputs(geom, _encoding_b_candidate(geom, face_id))
            out.append(_event_dict(row.get("label", f"{face_id}:{valley_id}"), face_id, area, zone, gx, gy, to_shared, _gp(face_id), confirmed_selection=_sel))
            continue
        to_shared = _facet_local_to_shared(geom, face_id)  # Module 1's mask, drawn directly (no re-derivation)
        out.append(_event_dict(row.get("label", f"{face_id}:{valley_id}"), face_id, component.affected_SF_raw, component.zone, component.gx, component.gy, to_shared, _gp(face_id), confirmed_selection=_sel))

    for item in confirmed_selection.get("multi_valley_facets", []):
        row = _confirmed_mapping(item)
        component = next(components)
        face_id = str(row["face_id"])
        valley_ids = tuple(str(v) for v in row.get("valley_ids", ()))
        for valley_id in valley_ids:
            cand = _require_candidate(valley_candidates, valley_id, "valley")
            _require_bordering_face(cand, face_id)
        if _refused(component, "multi_valley", face_id):
            continue
        ebz = encoding_b_zone(geom, face_id, list(valley_ids), confirmed_selection, _gp(face_id))
        if ebz is not None:
            area, zone, gx, gy, _facet = ebz
            _f, _v, _n, _p, to_shared = _notch_zone_inputs(geom, _encoding_b_candidate(geom, face_id))
            out.append(_event_dict(row.get("label", f"{face_id}:multi-valley"), face_id, area, zone, gx, gy, to_shared, _gp(face_id), confirmed_selection=_sel))
            continue
        to_shared = _facet_local_to_shared(geom, face_id)  # Module 1's mask, drawn directly
        out.append(_event_dict(row.get("label", f"{face_id}:multi-valley"), face_id, component.affected_SF_raw, component.zone, component.gx, component.gy, to_shared, _gp(face_id), confirmed_selection=_sel))

    # v62 DEFECT 1: a REPLACED facet must emit a diagram event, or page 2 reports ~0 for a full roof
    # while the scope reports the whole roof. It is NOT a run_module1_service component (that builder
    # skips replacement, exactly like this iterator did), so it does not consume `next(components)` —
    # the iterator stays aligned. The whole facet comes off: the polygon is the facet itself, the area
    # is the SAME authority the scope bills (`_replacement_facet_area`, net of penetrations), and the
    # count is 0 because a replacement bills SQ, not EA. Diagram total == scope total by construction.
    for item in confirmed_selection.get("replaced_facets", []):
        row = _confirmed_mapping(item)
        face_id = str(row["face_id"])
        polygon = [_xy(geom.points[pid]) for pid in geom.ordered_face_point_ids(face_id)]
        out.append({
            "event_label": str(row.get("label", f"{face_id}:replacement")),
            "facet_id": face_id,
            "affected_polygon": [polygon],       # list-of-rings, like every other event
            "affected_SF": _round_sf(_replacement_facet_area(geom, face_id)),
            "shake_count": 0,
            "kind": "replacement",              # v63: drawn as REPLACED in §4, not as a red repair zone
        })

    for item in confirmed_selection.get("penetration_appurtenance_repairs", []):
        row = _confirmed_mapping(item)
        component = next(components)
        penetration_id = str(row["penetration_face_id"])
        cand = _require_candidate(penetration_candidates, penetration_id, "penetration")
        host_face_id = str(row.get("host_face_id") or cand.params["host_facet_id"])
        if host_face_id != cand.params["host_facet_id"]:
            raise ValueError(f"penetration {penetration_id} is not hosted by {host_face_id}")
        if _refused(component, "penetration_appurtenance", host_face_id):
            continue
        zone_face_id = str(component.face_id or host_face_id)
        if "+" in zone_face_id:
            member_face_ids = tuple(zone_face_id.split("+"))
            notch_cand = _require_notch_candidate(notch_candidates, member_face_ids)
            _f, _v, _n, _p, to_shared = _notch_zone_inputs(geom, notch_cand)
        else:
            to_shared = _facet_local_to_shared(geom, zone_face_id)
        # v62 DEFECT 2: appurtenance on a REPLACED facet is unioned into the replacement — its area and
        # count are 0 in the diagram too, so the diagram total stays equal to the scope total. (The
        # material line and IWS are scope-only concerns; the diagram only reports affected area/count.)
        _union = host_face_id in replaced_facet_ids
        out.append(_event_dict(
            row.get("label", f"{host_face_id}:{penetration_id}:appurtenance"),
            host_face_id,
            component.affected_SF_raw,
            component.zone,
            component.gx,
            component.gy,
            to_shared,
            _gp(host_face_id),
            affected_SF=0.0 if _union else None,
            shake_count=0 if _union else None,
            confirmed_selection=_sel,
        ))
        if _union:
            out[-1]["kind"] = "subsumed"     # v63: inside a full replacement — not a separate §4 box

    for item in confirmed_selection.get("user_appurtenance_repairs", []):
        row = _confirmed_mapping(item)
        if not bool(row.get("repair_event", True)):
            continue
        component = next(components)
        host_face_id = str(row["host_facet_id"])
        if _refused(component, "user_appurtenance", host_face_id):
            continue
        zone_face_id = str(component.face_id or host_face_id)
        if "+" in zone_face_id:
            member_face_ids = tuple(zone_face_id.split("+"))
            notch_cand = _require_notch_candidate(notch_candidates, member_face_ids)
            _f, _v, _n, _p, to_shared = _notch_zone_inputs(geom, notch_cand)
        else:
            to_shared = _facet_local_to_shared(geom, zone_face_id)
        label = row.get("designator") or row.get("label") or f"{host_face_id}:user-appurtenance"
        _union = host_face_id in replaced_facet_ids   # v62: unioned into the full replacement
        out.append(_event_dict(
            label,
            host_face_id,
            component.affected_SF_raw,
            component.zone,
            component.gx,
            component.gy,
            to_shared,
            _gp(host_face_id),
            affected_SF=0.0 if _union else None,
            shake_count=0 if _union else None,
            confirmed_selection=_sel,
        ))
        if _union:
            out[-1]["kind"] = "subsumed"     # v63: inside a full replacement — not a separate §4 box

    for item in confirmed_selection.get("notch_repairs", []):
        row = _confirmed_mapping(item)
        component = next(components)
        member_face_ids = tuple(str(v) for v in row["member_face_ids"])
        cand = _require_notch_candidate(notch_candidates, member_face_ids)
        if _refused(component, "notch", "/".join(member_face_ids)):
            continue
        _f, _v, _n, _p, to_shared = _notch_zone_inputs(geom, cand)  # transform only; mask is Module 1's
        out.append(_event_dict(row.get("label", ":".join(member_face_ids) + ":notch"), "/".join(member_face_ids), component.affected_SF_raw, component.zone, component.gx, component.gy, to_shared,
                               _geometry_profile_for_facet(member_face_ids[0], _sel, _claim), confirmed_selection=_sel))

    out.extend(_transition_regions(geom, confirmed_selection, shake_measurements, _gp, unsupported_out=unsupported))
    return out


def _transition_regions(geom: EagleViewGeometry, confirmed_selection: Mapping[str, Any], shake_measurements, profile_for_face=None,
                        unsupported_out: list | None = None) -> list[dict[str, Any]]:
    """Shade the tear-off band of every ACTIVE transition (Path A or Path B), on EVERY facet it
    carves — including facets that also carry a valley repair.

    THE DIAGRAM READS FROM THE MATH, NEVER THE REVERSE. The scope counts this band, so the diagram
    must draw it — otherwise the picture and the numbers disagree, which is exactly the failure the
    regression's diagram==count check exists to catch.

    BUG FIX (v56): this loop used to SKIP any facet that carried a valley component, on the false
    assumption that the valley zone it had already drawn contained the band. It does not.
    module2_assembly threads the bands into the SAME affected_area call as that facet's valley
    events, so the SCOPE's valley component is the UNION of valley zone + band. The DIAGRAM's valley
    zone, however, comes from module1_service — which NEVER receives the bands. So the band was in
    the scope and absent from the picture: on Yager (L79 confirmed + the Q side of L83/L84 repaired)
    the diagram was 11.3 SF short; on Devore (L24 confirmed + a valley on O) it was missing the whole
    70.4 SF upper band. It also punched a hole in the page-2 Continue gate, which reads the DIAGRAM
    events to decide whether a penetration sits in an affected zone.

    ONE ZONE AUTHORITY. The fix is NOT to thread bands into module1_service as well — that would
    leave two zone derivations to keep in step by hand, which IS the bug. The band's region is
    derived here, once, as the INCREMENTAL area it contributes beyond everything else already drawn
    on that facet:

        net_zone = zone(that facet's other events + band) MINUS zone(that facet's other events)

    Union-correct by construction: the region added is exactly what the band opens up beyond the rest
    of that facet, so diagram total == scope total and no pixel is counted twice. Where a valley zone
    already sweeps the band (Yager's V under the default selection), net_zone is empty and the band
    adds ZERO — the anchor cannot move.

    "That facet's other events" is whatever the SCOPE nets the band against on that facet, mirrored
    exactly:
      * VALLEY facet — module2_assembly's `_single_valley_area` / `_multi_valley_union_area` pass the
        bands into affected_area alongside the valley events and the penetrations, and NOT the
        appurtenances (an appurtenance is its own component, already netted against the valley zone).
        So the "other events" here are the valley events + penetrations.
      * NON-VALLEY facet — module2_assembly emits a standalone transition component whose area is
        netted against that facet's appurtenances + penetrations. Unchanged from v55.

    The SHAKE COUNT follows the same mirror, because EA is ceil()ed once PER SCOPE COMPONENT:
      * VALLEY facet — the band lives INSIDE the valley component, which ceils the union once. The
        band region therefore carries the INCREMENTAL count, count(union) - count(valley alone), so
        that valley_region_EA + band_region_EA == the component's single ceil. Counting ceil(net_SF)
        instead would over-count by up to one shake per band.
      * NON-VALLEY facet — the band IS its own scope component, so it carries ceil(net_SF), exactly
        as the scope does. Unchanged from v55.
    """
    import numpy as _np
    from module2_assembly import _confirmed_appurtenance_geometries_for_face, _penetrations_with_user_footprints
    from transition_events import engine_bands, transition_bands_by_face

    bands_by_face = transition_bands_by_face(geom, confirmed_selection, shake_measurements)
    if not bands_by_face:
        return []

    # FRAME ARC-06a r1 (independent QA r0 §5, owner question Q-E3): a transition whose two facets carry DIFFERENT roof
    # systems is a SYSTEM BOUNDARY. The scope stops on it by name (module2_assembly, v105.3) and bills neither side; the
    # band above is a WOOD-SHAKE course band, so drawing it — on the membrane side or the shake side — would picture a
    # repair nobody computed. It is drawn on NO facet and listed once as unsupported (kind SYSTEM_BOUNDARY); every other
    # transition is untouched. Only on the registry-aware path (profile_for_face given) — the legacy call is unchanged.
    if profile_for_face is not None:
        from transition_events import active_transitions
        from roof_systems import system_for_facet as _sys_for_facet
        _boundary: dict[str, tuple[str, str, str, str]] = {}
        for _tr in active_transitions(geom, confirmed_selection):
            _sa = _sys_for_facet(str(_tr.face_a_id), confirmed_selection)
            _sb = _sys_for_facet(str(_tr.face_b_id), confirmed_selection)
            if _sa != _sb:
                _boundary[str(_tr.edge_id)] = (str(_tr.face_a_id), _sa, str(_tr.face_b_id), _sb)
        if _boundary:
            if unsupported_out is not None:
                for _eid, (_fa, _sa, _fb, _sb) in sorted(_boundary.items()):
                    unsupported_out.append({
                        "event_label": f"Transition {_eid}", "facet_id": f"{_fa}+{_fb}", "kind": "SYSTEM_BOUNDARY",
                        "reason": (f"Transition {_eid} spans facets carrying DIFFERENT roof systems ({_fa}: {_sa}, "
                                   f"{_fb}: {_sb}) — a SYSTEM BOUNDARY. Not computed and not drawn: what each side "
                                   f"bills there has not been ruled on (owner question Q-E3).")})
            bands_by_face = {f: [b for b in bs if str(b["edge_id"]) not in _boundary]
                             for f, bs in bands_by_face.items()}
            bands_by_face = {f: bs for f, bs in bands_by_face.items() if bs}
            if not bands_by_face:
                return []

    # The valley events the SCOPE unions the band into, per facet. Notch members are deliberately
    # absent: module2_assembly does not thread bands into a notch component either, so a banded notch
    # member is a NON-VALLEY facet on both sides of the seam and stays byte-for-byte as it was.
    valley_events_by_face: dict[str, list[Any]] = {}
    for item in confirmed_selection.get("single_valley_repairs", []):
        row = _confirmed_mapping(item)
        face_id = str(row["face_id"])
        valley_events_by_face.setdefault(face_id, []).append(
            geom.valley_event_for_face(face_id, str(row["valley_id"])))
    for item in confirmed_selection.get("multi_valley_facets", []):
        row = _confirmed_mapping(item)
        face_id = str(row["face_id"])
        for valley_id in row.get("valley_ids", ()):
            valley_events_by_face.setdefault(face_id, []).append(
                geom.valley_event_for_face(face_id, str(valley_id)))

    out: list[dict[str, Any]] = []
    for face_id, bands in sorted(bands_by_face.items()):
        engine_face = geom.engine_facet(face_id)
        pens = _penetrations_with_user_footprints(geom, confirmed_selection, face_id)
        valley_events = valley_events_by_face.get(face_id, [])
        apps = [] if valley_events else _confirmed_appurtenance_geometries_for_face(geom, confirmed_selection, face_id)
        # FRAME ARC-06a (B1): the facet's own profile; a facet whose package refuses its valley geometry draws no band
        # region here (the refused event is listed once, as unsupported, by _event_regions).
        _fp = shake_measurements if profile_for_face is None else profile_for_face(face_id)
        try:
            _p0, area_without, zone_without, gx, gy = affected_area(
                engine_face.facet, valley_events, appurtenances=apps, penetrations=pens,
                return_zone=True, shake_measurements=_fp)
            _p1, area_with, zone_with, _gx, _gy = affected_area(
                engine_face.facet, valley_events, appurtenances=apps, penetrations=pens,
                return_zone=True, shake_measurements=_fp,
                transition_bands=engine_bands(bands))
        except NotImplementedError:
            continue
        net_zone = _np.asarray(zone_with, bool) & ~_np.asarray(zone_without, bool)
        cell = float((gx[1] - gx[0]) * (gy[1] - gy[0]))
        net_sf = float(net_zone.sum() * cell)
        if net_sf <= 0:
            continue                          # the facet's own zone already sweeps the band: ZERO new area
        if valley_events:
            # The band is INSIDE the valley component. Carry that component's REMAINDER so the two
            # regions sum to exactly the one component the scope billed (Devore: 161.7 - 91.2 = 70.5,
            # not round(70.44) = 70.4, which would leak 0.1 SF; 349 - 204 = 145 EA, not ceil(70.44)).
            sf_receipt: float | None = round(_round_sf(area_with) - _round_sf(area_without), 1)
            _cw = _event_piece_count(area_with, _fp, face_id, confirmed_selection if profile_for_face else None)
            _co = _event_piece_count(area_without, _fp, face_id, confirmed_selection if profile_for_face else None)
            count: int | None = (None if _cw is None or _co is None else int(_cw - _co))
        else:
            # The band IS its own scope component. Its own area, its own rounding. Unchanged from v55.
            sf_receipt, count = None, None
        edge_ids = ", ".join(sorted({str(b["edge_id"]) for b in bands}))
        to_shared = _facet_local_to_shared(geom, face_id)
        out.append(_event_dict(f"Transition {edge_ids}", face_id, net_sf, net_zone, gx, gy,
                               to_shared, _fp,
                               affected_SF=sf_receipt, shake_count=count,
                               confirmed_selection=(confirmed_selection if profile_for_face else None)))
    return out


def _repair_facet_ids(confirmed_selection: Mapping[str, Any]) -> set[str]:
    out: set[str] = set()
    for item in confirmed_selection.get("single_valley_repairs", []):
        out.add(str(_confirmed_mapping(item)["face_id"]))
    for item in confirmed_selection.get("multi_valley_facets", []):
        out.add(str(_confirmed_mapping(item)["face_id"]))
    for item in confirmed_selection.get("notch_repairs", []):
        for member in _confirmed_mapping(item).get("member_face_ids", []):
            out.add(str(member))
    return out


def _notch_zone_inputs(geom: EagleViewGeometry, candidate: Any):
    anchor_line_id = str(candidate.params["anchor_line_id"])
    anchor_line = geom.lines[anchor_line_id]
    frame_ids = tuple(str(pid) for pid in candidate.params["frame_point_ids"])
    from module1_service import mkframe_pts
    frame = mkframe_pts(
        [geom.points[pid] for pid in frame_ids],
        geom.points[anchor_line.path[0]],
        geom.points[anchor_line.path[-1]],
    )
    to_shared = _local_to_shared_transform(
        [geom.points[pid] for pid in frame_ids],
        geom.points[anchor_line.path[0]],
        geom.points[anchor_line.path[-1]],
    )
    facet = [tuple(frame(geom.points[pid])) for pid in candidate.params["merged_facet_point_ids"]]
    notches = [
        [tuple(frame(geom.points[pid])) for pid in notch_ids]
        for notch_ids in candidate.params["notch_polygon_point_ids"]
    ]
    valleys = [
        _valley_event_for_notch(geom, candidate, frame, facet, str(line_id))
        for line_id in candidate.params["bordering_valley_line_ids"]
    ]
    pens = []
    for member_face_id in candidate.params["member_face_ids"]:
        member_face = geom.faces.get(str(member_face_id))
        for child_id in (member_face.children if member_face else []):
            pen_face = geom.penetration_faces.get(child_id)
            if pen_face is not None and getattr(pen_face, "size", 0) > 0:
                pens.append([tuple(frame(geom.points[pid])) for pid in geom.ordered_face_point_ids(child_id)])
    return facet, valleys, notches, pens, to_shared


def _event_dict(
    label: object,
    facet_id: str,
    affected_sf_raw: float,
    zone: Any,
    gx: Sequence[float],
    gy: Sequence[float],
    to_shared: Callable[[Sequence[float]], list[float]],
    shake_measurements: Mapping[str, Any] | None = None,
    affected_SF: float | None = None,
    shake_count: int | None = None,
    confirmed_selection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    # `affected_SF` / `shake_count` are explicit REMAINDER values, supplied ONLY by an incremental
    # transition-band region drawn on a facet whose band the scope counts INSIDE another component
    # (see _transition_regions). Both SF and EA are rounded/ceil()ed ONCE PER SCOPE COMPONENT, so a
    # region that is only PART of a component must carry that component's remainder rather than its
    # own independent rounding — otherwise the two regions sum to 0.1 SF (and up to one shake) less
    # than the single component they are drawing. The POLYGON is always the region's true traced
    # zone; only the receipt it is labelled with is the remainder. Every other event is a component in
    # its own right and derives both values from its own area, exactly as before.
    # FRAME ARC-06a (E): the count is the EVENT'S OWN FACET's package's piece count, or NOT APPLICABLE when that package
    # declares none (a membrane) — then shake_count is 0 (no pieces are billed by piece) and the event says so; a
    # wood-shake EA is never borrowed for it. Events of a declaring package carry exactly the keys they always did.
    applicable = True
    if shake_count is None:
        _c = _event_piece_count(affected_sf_raw, shake_measurements, facet_id, confirmed_selection)
        applicable = _c is not None
        count = int(_c) if applicable else 0
    else:
        count = int(shake_count)
        if confirmed_selection is not None:
            applicable = _declares_operation(_event_piece_system(facet_id, confirmed_selection), "field_piece_count")
    out = {
        "event_label": str(label),
        "facet_id": str(facet_id),
        "affected_polygon": _zone_to_polygon(zone, gx, gy, to_shared, affected_sf_raw),
        "affected_SF": _round_sf(affected_sf_raw) if affected_SF is None else _round_sf(affected_SF),
        "shake_count": count,
    }
    if not applicable:
        out["piece_count_applicable"] = False
        out["piece_count_system"] = str(_event_piece_system(facet_id, confirmed_selection))
    return out


def _zone_to_polygon(
    zone: Any,
    gx: Sequence[float],
    gy: Sequence[float],
    to_shared: Callable[[Sequence[float]], list[float]] | None = None,
    target_area: float | None = None,
) -> list[list[float]]:
    """Trace the engine zone mask into a JSON-safe polygon ring.

    The affected area is not derived here. The frozen engine returns the zone
    mask and Module 1 returns the verified SF; this exporter only converts the
    occupied mask cells into a drawable rectilinear outline. When ``to_shared``
    is supplied, each traced local point is re-projected into the same shared
    roof frame used by workbench_roof_layout. ``target_area`` is retained for
    call compatibility and intentionally not used for centroid rescaling.
    """
    arr = np.asarray(zone, dtype=bool)
    if arr.size == 0 or not arr.any():
        return []

    res_x = _grid_res(gx)
    res_y = _grid_res(gy)
    rings = _mask_boundary_rings(arr)
    if not rings:
        return []

    x0 = float(gx[0]) - res_x / 2.0
    y0 = float(gy[0]) - res_y / 2.0

    def to_points(ring: Sequence[tuple[int, int]]) -> list[list[float]]:
        return _round_and_clean_ring([(x0 + col * res_x, y0 + row * res_y) for col, row in ring])

    # Preserve the single-ring UI contract. When the mask contains holes or rare
    # disconnected islands, concatenate the rings with zero-area bridge segments.
    # The shoelace area remains the signed sum of the engine mask boundaries, and
    # SVG still receives one closed [x, y] path.  # TODO multi-component
    cleaned_rings = [to_points(ring) for ring in sorted(rings, key=lambda r: abs(_signed_shoelace_area(r)), reverse=True)]
    cleaned_rings = [ring for ring in cleaned_rings if len(ring) >= 4]
    if not cleaned_rings:
        return []

    # Multi-ring: return each connected mask boundary (and hole) as its OWN ring,
    # drawn with fill-rule=evenodd on the client. No zero-area bridge segments, so
    # no stray connector lines. Largest ring first (used for the label centroid).
    if to_shared is None:
        return cleaned_rings
    return [[to_shared(pt) for pt in ring] for ring in cleaned_rings]


def _mask_boundary_rings(arr: Any) -> list[list[tuple[int, int]]]:
    """Return directed boundary rings of a boolean cell mask.

    Nodes are integer grid-corner coordinates (col, row). The directed edges are
    emitted clockwise around True cells, which makes holes naturally carry the
    opposite signed area.
    """
    import numpy as np
    from collections import defaultdict

    mask = np.asarray(arr, dtype=bool)
    if mask.size == 0 or not mask.any():
        return []

    nrows, ncols = mask.shape
    ys, xs = np.nonzero(mask)
    outgoing: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    directed_edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()

    def add(a: tuple[int, int], b: tuple[int, int]) -> None:
        edge = (a, b)
        if edge not in directed_edges:
            directed_edges.add(edge)
            outgoing[a].append(b)

    for i, j in zip(ys.tolist(), xs.tolist()):
        below_empty = i == 0 or not mask[i - 1, j]
        above_empty = i == nrows - 1 or not mask[i + 1, j]
        left_empty = j == 0 or not mask[i, j - 1]
        right_empty = j == ncols - 1 or not mask[i, j + 1]

        if below_empty:
            add((j + 1, i), (j, i))
        if above_empty:
            add((j, i + 1), (j + 1, i + 1))
        if left_empty:
            add((j, i), (j, i + 1))
        if right_empty:
            add((j + 1, i + 1), (j + 1, i))

    visited: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    rings: list[list[tuple[int, int]]] = []

    for edge in list(directed_edges):
        if edge in visited:
            continue
        start, nxt = edge
        ring = [start]
        current = start
        next_node = nxt
        while True:
            step = (current, next_node)
            if step in visited:
                break
            visited.add(step)
            ring.append(next_node)
            current = next_node
            if current == start:
                rings.append(ring)
                break
            candidates = outgoing.get(current, [])
            unvisited = [cand for cand in candidates if (current, cand) not in visited]
            if not unvisited:
                break
            next_node = _choose_boundary_successor(ring[-2], current, unvisited)

    return rings


def _choose_boundary_successor(prev: tuple[int, int], current: tuple[int, int], candidates: Sequence[tuple[int, int]]) -> tuple[int, int]:
    """Choose a deterministic continuation at a boundary corner."""
    if len(candidates) == 1:
        return candidates[0]

    dx = current[0] - prev[0]
    dy = current[1] - prev[1]
    # Prefer right turn, then straight, then left, then reverse for clockwise
    # cell boundaries with the occupied mask on the right-hand side.
    ranked: list[tuple[int, tuple[int, int]]] = []
    for cand in candidates:
        ndx = cand[0] - current[0]
        ndy = cand[1] - current[1]
        cross = dx * ndy - dy * ndx
        dot = dx * ndx + dy * ndy
        if cross < 0:
            rank = 0
        elif cross == 0 and dot > 0:
            rank = 1
        elif cross > 0:
            rank = 2
        else:
            rank = 3
        ranked.append((rank, cand))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return ranked[0][1]


def _row_runs(arr: Any) -> list[tuple[int, int, int]]:
    """Return one occupied [start,end] column run per occupied row."""
    import numpy as np

    mask = np.asarray(arr, dtype=bool)
    rows = np.flatnonzero(mask.any(axis=1))
    out: list[tuple[int, int, int]] = []
    for row in rows.tolist():
        cols = np.flatnonzero(mask[row])
        if cols.size:
            out.append((int(row), int(cols.min()), int(cols.max())))
    return out


def _largest_mask_component(arr: Any) -> Any:
    """Keep the largest 4-connected mask component without new dependencies."""
    import numpy as np
    from collections import deque

    mask = np.asarray(arr, dtype=bool)
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return mask

    occupied = set(zip(ys.tolist(), xs.tolist()))
    best: set[tuple[int, int]] = set()
    while occupied:
        start = occupied.pop()
        component = {start}
        q: deque[tuple[int, int]] = deque([start])
        while q:
            y, x = q.popleft()
            for nb in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if nb in occupied:
                    occupied.remove(nb)
                    component.add(nb)
                    q.append(nb)
        if len(component) > len(best):
            best = component

    out = np.zeros_like(mask, dtype=bool)
    if best:
        by, bx = zip(*best)
        out[list(by), list(bx)] = True
    return out


def _round_and_clean_ring(points: Sequence[Sequence[float]]) -> list[list[float]]:
    cleaned: list[tuple[float, float]] = []
    for x, y in points:
        pt = (round(float(x), 4), round(float(y), 4))
        if not cleaned or cleaned[-1] != pt:
            cleaned.append(pt)

    if len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
        open_pts = cleaned[:-1]
    else:
        open_pts = cleaned

    changed = True
    while changed and len(open_pts) >= 3:
        changed = False
        next_pts: list[tuple[float, float]] = []
        n = len(open_pts)
        for idx, pt in enumerate(open_pts):
            prev_pt = open_pts[(idx - 1) % n]
            next_pt = open_pts[(idx + 1) % n]
            collinear_vertical = prev_pt[0] == pt[0] == next_pt[0]
            collinear_horizontal = prev_pt[1] == pt[1] == next_pt[1]
            if collinear_vertical or collinear_horizontal:
                changed = True
                continue
            next_pts.append(pt)
        open_pts = next_pts

    if not open_pts:
        return []
    if open_pts[0] != open_pts[-1]:
        open_pts.append(open_pts[0])
    return [[float(x), float(y)] for x, y in open_pts]


def _scale_polygon_to_area(poly: Sequence[Sequence[float]], target_area: float) -> list[list[float]]:
    """Preserve the engine's surface-area receipt after shared-frame placement.

    The shared roof frame is the parser POINT x/y drawing frame.  For pitched
    facets, a 3D -> x/y projection naturally has smaller shoelace area than the
    surface-area returned by affected_area.  The UI still needs the verified SF
    receipt to reconcile, so after landing the polygon in the shared frame we
    scale about its centroid to keep the polygon's drawable area equal to the
    frozen engine affected area.  This changes only drawing coordinates.
    """
    current = _shoelace_area(poly)
    if current <= 0 or target_area <= 0:
        return [[round(float(p[0]), 6), round(float(p[1]), 6)] for p in poly]
    factor = (target_area / current) ** 0.5
    closed = len(poly) > 1 and list(poly[0]) == list(poly[-1])
    pts = list(poly[:-1] if closed else poly)
    cx = sum(float(p[0]) for p in pts) / len(pts)
    cy = sum(float(p[1]) for p in pts) / len(pts)
    scaled = [
        [round(cx + (float(p[0]) - cx) * factor, 6), round(cy + (float(p[1]) - cy) * factor, 6)]
        for p in pts
    ]
    if closed:
        scaled.append(list(scaled[0]))
    return scaled


# local/shared affine helpers are imported from workbench_roof_layout so layout export
# and diagram drawing share one coordinate transform implementation.

def _grid_res(values: Sequence[float]) -> float:
    return abs(float(values[1]) - float(values[0])) if len(values) > 1 else 0.04


def _round_sf(value: float) -> float:
    return round(float(value), 1)


def _roof_area_sf(geom: EagleViewGeometry) -> float:
    total = 0.0
    for face in geom.roof_faces.values():
        if face.unrounded_size is not None:
            total += float(face.unrounded_size)
        elif face.size is not None:
            total += float(face.size)
    return total


def _signed_shoelace_area(poly: Sequence[Sequence[float]]) -> float:
    if len(poly) < 3:
        return 0.0
    pts = list(poly)
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    area = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        area += float(x1) * float(y2) - float(x2) * float(y1)
    return area / 2.0

def _shoelace_area(poly: Sequence[Sequence[float]]) -> float:
    if len(poly) < 3:
        return 0.0
    pts = list(poly)
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    area = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        area += float(x1) * float(y2) - float(x2) * float(y1)
    return abs(area) / 2.0


if __name__ == "__main__":
    # FRAME ARC-04a: the self-receipt `_run_receipts` MOVED, byte-for-byte, to
    # verification/workbench_diagram_receipts_regression.py (it held a shipped material-term site) and now runs in the
    # suite. Running this module no longer runs it; it says where it went and exits non-zero rather than passing silently.
    import sys as _sys
    print("deploy/workbench_diagram_data.py: the diagram self-receipt moved to "
          "verification/workbench_diagram_receipts_regression.py (FRAME ARC-04a).")
    _sys.exit(2)
