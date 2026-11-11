#!/usr/bin/env python3
# CHANGELOG 2026-07-04: notch valley set now selection-driven (override_valley_ids); fallback preserves anchor 3691.
# CHANGELOG 2026-06-29 (Phase-2 re-baseline 3709->3691 EA / 1645.6->1638.0 SF):
#   Consistent clipped penetration exclusion across single/multi/notch paths,
#   dimensional-only (footprint >= 0.5 SF carves; point < 0.5 SF lays over).
#   - multi path: no longer include_child_penetrations flag-gated; always passes
#     dimensional penetrations to affected_area's existing clipped exclusion.
#   - notch path: now carves member-facet dimensional penetrations (frame-transformed).
#   - dedup-as-subsumed-event: in-field appurtenance (host is a confirmed repair facet)
#     contributes flashing/IWS only, 0 double-counted field shakes.
#   Prior multi/notch skipped the exclusion the single path already ran; only F70
#   (in-zone chimney on F4) moves the total. See module1_yager_proof.py.
"""Full-roof Module 2 assembly with physical shared-edge deduplication.

Assembly/translation only. Frozen expand_scope remains the material-rule engine;
this layer prevents physical edges shared by two in-scope facets from being
scoped twice by unioning contact by XML line id before one final edge-only
expand_scope call.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

import numpy as np

from candidate_model import Candidate
from eagleview_geometry_parser import EagleViewGeometry, parse_eagleview_geometry, _frame_anchor_line   # v105.2: THE ONE anchor rule
from module1_m2interface import affected_area, build_m1_interface_for_face, edge_contacts, _quiet_import_regression_symbol
from module1_selected_valley_handoff import selected_valley_handoff
from scope_contract import (Edge, M1Interface, ScopeLine, SYSTEM_BOUNDARY,   # FRAME v106.3b: the boundary edge type
                            Transition)   # FRAME v104b: the contract from core (the same objects)
from facet_basis import facet_frame_axes   # FRAME v105.1: THE ONE fall-line basis
from geometry_core import shared_edge_overlap_ft   # FRAME v106.6d: the cut line two split markers share
# FRAME ARC-05a: the eave-IWS helpers are no longer imported from the wood-shake package (package isolation exception
# E2 retired). The roof-level eave ice & water line is a PACKAGE OPERATION, asked of the one installed package that
# declares it (roof_systems.operation_owner / require_operation) — the same two functions, the same answer.
from roof_systems import operation_owner, require_operation   # FRAME ARC-05a
from roof_systems import declares_operation   # FRAME ARC-06a: per-edge ownership of a roof-level operation
# FRAME v104b: the scope engine is ASKED FOR, never imported (bridge 6 retired). With a facet in hand, system_for_facet;
# with none (per-transition, per-edge, per-structure calls), the sole registered system — both v104a's, no third path.
from roof_systems import get as roof_system, system_for_facet, system_for_facets   # FRAME v105.3: never the SOLE system
from roof_systems import excluded_facets   # FRAME v106.1: facets this claim does not scope
from roof_systems import PROJECT_CONFIG_KEY   # FRAME ARC-03a: a schema_version 1 project's header
from roof_systems import system_for_profile   # FRAME v105.4: the profile's OWN package resolves it
from roof_systems import system_boundary_tie_in_ft   # FRAME v106.3b: THE ONE evaluation of the boundary ruling
from roof_systems import appurtenance_clearance_for_facet   # FRAME v106.6c: the facet's own setback
from roof_systems import appurtenance_clearance_for_facets   # FRAME v106.6c: a merged slope's setback
from roof_systems import claim_geometry_profile as _claim_geometry_profile   # FRAME ARC-06a
from roof_systems import geometry_profile_for_facet as _geometry_profile_for_facet   # FRAME ARC-06a (B1)
from roof_systems import geometry_profile_for_facets as _geometry_profile_for_facets   # FRAME ARC-06a (B1)
from roof_systems import RegistryWiringError as _RegistryWiringError   # ARC-06a: a cross-material union
# FRAME ARC-05a: this module dispatches to roof-system engines, so a roof system must be registered before it can run
# (A11). Until ARC-05a that was a by-product of the E2 import above, which registered the wood-shake package only; ARC-05a
# kept that set as data (installed_packages.ASSEMBLY_ENTRY_PACKAGES). FRAME ARC-06a: that set is now every installed
# package (owner direction), so page 2 — which reaches the engine through this module — lists every installed covering
# on a fresh load and requires an explicit declaration. This module still names no package.
import installed_packages as _installed_packages
_installed_packages.install_assembly_roof_systems()
from candidate_emitters import emit_valley_candidates          # v93: THE valley facet-pair source (bordering_roof_face_ids)
from operation_dimension import R_AND_R, REPLACE                  # v93: the canonical operation constants
from transition_events import (
    replaced_face_ids,                                            # v93: THE replaced-facet set (the one Path R reads)
    active_transitions as _active_transitions,
    engine_bands,
    selected_transition_repairs,
    transition_metal_facts,
    path_r_transitions,
    transition_bands_by_face,
    system_boundary_band_for_face,                                # FRAME v106.3b: the same band, on a boundary
    transition_contact_lf,
)
from notch_candidate_emitter import emit_notch_candidates, encoding_b_candidate as _emit_encoding_b_candidate
# ONE AUTHORITY for "does this appurtenance disturb the shake field?". module1_service imports
# the SAME function for the diagram, so the picture cannot disagree with the scope.
from shared_category_registry import appurtenance_carves, is_power_vent
from shared_category_registry import (field_category_id, line_system, material_splits,   # FRAME v104c: per system
                                      sole_category_package, RegistryWiringError)       # v104d: the mixed-roof gate


@dataclass(frozen=True)
class EdgeContribution:
    line_id: str
    edge_type: str
    contact_LF: float
    edge_total_LF: float
    component: str
    # FRAME v105.3: the roof system of the facet(s) that contributed this edge — stamped where the component's face id
    # is in hand (never looked up from the line). The per-edge scope line is expanded by THIS system's engine.
    system_id: str = ""


@dataclass(frozen=True)
class ComponentAssembly:
    label: str
    face_id: str
    component_type: str
    geometry_status: str
    surface_status: str
    reason: str
    iface: M1Interface
    scope_lines: Tuple[ScopeLine, ...]
    edge_contributions: Tuple[EdgeContribution, ...]


@dataclass(frozen=True)
class AggregatedScopeLine:
    item: str
    category_id: str
    qty: float
    unit: str
    gate: str
    # The Xactimate code the line will actually be billed under. Additive: defaults to None, so every
    # existing construction is unchanged. It was previously DROPPED at aggregation, so the size the
    # user set on page 2 never reached the report at all.
    xact_code: Optional[str] = None
    # THE AUTHORITY that puts this item in a proper repair — "IRC drip edge", "CSSB ridge detail",
    # "mfr / IRC flashing". Every ScopeLine has carried one all along; _aggregate_lines DROPPED it,
    # exactly as it dropped xact_code (fixed in v48). The consequence was severe: §5 could only print
    # the bare word "required", which is the TOOL drawing the conclusion — the very thing an adjuster
    # pushes back on. The report is supposed to DEMONSTRATE and let the reader conclude; it could not,
    # because the reason was destroyed before it reached the renderer.
    citation: Optional[str] = None
    # FRAME v104c: the roof system the merged lines came from. A SPLIT category (the default) never mixes systems,
    # so it carries its one material; a MERGED category carries the common material, or None when two systems summed.
    material_profile_id: Optional[str] = None


@dataclass(frozen=True)
class SystemBoundaryDisclosure:
    """A facet this claim does NOT scope, and what reached it anyway (FRAME v106.1).

    THE REASON THIS EXISTS AT ALL is the rule already written into this file for appurtenance dedupe:
    "An over-scope is visible and correctable; an under-scope is not." Dropping an excluded facet's band
    silently would be exactly that invisible under-scope — the tear-off that vanished on Killarney F36 at
    v90, which entry 91 then "fixed" by billing shake onto a surface that is not shake. So every drop
    leaves a receipt the report prints.
    """
    face_id: str
    designator: str
    edge_id: str
    edge_type: str
    dropped_SF: float
    reason: str


@dataclass(frozen=True)
class UnsupportedOperation:
    """FRAME ARC-06a (B1) — a confirmed repair event the facet's OWN roof-system package REFUSED, or a union that spans
    two materials, recorded instead of computed.

    Until ARC-06a such an event was computed with WOOD SHAKE's geometry (the claim-level profile) and billed as if it
    were a valid membrane repair. Now the facet's package is asked; when it refuses by name (MODBIT: "what a membrane
    valley repair disturbs has not been ruled on"), the component contributes NO area, NO lines and NO valley LF, the
    rest of the roof is computed exactly as before, and this receipt names the facet, the event, the system and the
    package's own words. Any entry makes the claim UNRESOLVED: comparison and report export refuse it (page 4)."""
    face_id: str
    designator: str
    component_type: str
    event: str
    system_id: str
    kind: str          # "PACKAGE_REFUSED" (the package raised NotImplementedError) | "SYSTEM_BOUNDARY" (cross-material union)
    reason: str


@dataclass(frozen=True)
class HeldOperation:
    """FRAME ARC-06a (E) — physical work the engine can LOCATE but may not PRICE OR SCOPE, because the owning roof
    system's package declares no rule for it and the owner has not ruled one. Nothing is billed for it; the measured
    basis is kept so the owner sees exactly what is held; any entry makes the claim UNRESOLVED (export refuses).
    The first and only kind today: eave ice & water on eaves whose facet's covering declares no
    `roof_eave_ice_and_water` operation (a MODBIT eave on a mixed roof)."""
    operation: str
    system_id: str
    basis: Tuple[Tuple[str, float], ...]       # (name, value) — e.g. (("eave_LF", 22.4),)
    edge_ids: Tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class RoofAssemblyResult:
    components: Tuple[ComponentAssembly, ...]
    aggregated_scope: Tuple[AggregatedScopeLine, ...]
    affected_SF_raw_total: float
    affected_SF_display_total: float
    selected_valley_LF_total: float
    derivation_breakdown: Tuple[Mapping[str, str], ...]
    deduped_edges: Tuple[EdgeContribution, ...]
    edge_scope_lines: Tuple[ScopeLine, ...]
    # v61 full slope replacement: facet designators by kind, so the report can label the two shake
    # lines ("Slope replacement (facets M, O)" vs "Slope repair (facets J, K, N)"). Empty when a
    # roof has no replacement (repair-only) or no repair (full replacement) — additive, default ().
    replacement_facets: Tuple[str, ...] = ()
    repair_facets: Tuple[str, ...] = ()
    # v65 structure separation: {structure_id: (AggregatedScopeLine, ...)} keyed by the <ROOF id="…">
    # each facet belongs to. Additive and default-empty. For a single-structure roof the ONE entry is
    # byte-identical to aggregated_scope (a lone structure shares no edge across a boundary, so its
    # per-structure dedup equals the global dedup). The report shows structure headings only when this
    # has 2+ entries; otherwise it renders exactly as before.
    aggregated_scope_by_structure: Tuple[Tuple[str, Tuple[AggregatedScopeLine, ...]], ...] = ()
    # v65: (structure_id, total ROOF facet count) for every structure in the geometry — the count the
    # report heading shows ("Dwelling — 14 facets"). From the parser, not from what was repaired, so it
    # reflects the structure's size. Empty/single-entry when the XML has no multi-ROOF nesting.
    structure_facet_counts: Tuple[Tuple[str, int], ...] = ()
    # v69: per-structure affected SF (for §2's per-structure dual) and the replacement/repair facet
    # labels grouped by structure (for §3's per-structure slope callouts). Additive; empty/one-entry
    # for a single-structure roof, where the report renders byte-identically to before.
    structure_affected_SF: Tuple[Tuple[str, float], ...] = ()
    replacement_facets_by_structure: Tuple[Tuple[str, Tuple[str, ...]], ...] = ()
    repair_facets_by_structure: Tuple[Tuple[str, Tuple[str, ...]], ...] = ()
    # v71 DEFECT 3: eave ICE & WATER metadata for the report — basis (code/existing), computed
    # coverage, exposed eave LF, layer count, and the soffit depth used (None when defaulted). None
    # when the user did not assert eave IWS. The report cites the basis and states the layer count;
    # the "defaulted" fact never reaches the report (the page-2 warning carries that).
    eave_iws: Optional[Mapping[str, object]] = None
    # v93: ONE VOTE PER TWO-FACET COMPONENT — (structure_id, category_id, component_id, operation) for every
    # TRANSITION_FLASH-emitting transition and every billed VALLEY_METAL valley. The operation is decided
    # HERE, where the component's own two facets are known (Joseph 2026-10-26, see _two_facet_operation);
    # comparison_caller turns the votes into build_comparison's required_operations. Additive, default ().
    two_facet_operations: Tuple[Tuple[str, str, str, Optional[str]], ...] = ()
    # FRAME v106.1: one entry per facet-band this claim DECLINED to scope because the facet is excluded.
    # Additive and default-empty, like every field above it: a claim that excludes nothing is byte-identical.
    # The report prints these, so an excluded facet is never a silent subtraction.
    system_boundary_disclosures: Tuple[SystemBoundaryDisclosure, ...] = ()
    # FRAME v104d (QA Q1 (a)): the affected SF PER ROOF SYSTEM — claim-level and per structure — summed from the SAME
    # components, in the same order, as affected_SF_raw_total and structure_affected_SF, so with one system each is
    # that figure exactly. A component's system is the material its engine stamped on its lines. A component with area
    # whose lines carry no single material is filed under "" (unattributed), and comparison_caller then falls back
    # to the claim-level figure (which raises on a mixed roof). Additive, default (). Read by comparison_caller, which
    # hands key_and_normalize {system_id: SF} so each field covering's dual uses ITS system's area.
    system_affected_SF: Tuple[Tuple[str, float], ...] = ()
    structure_system_affected_SF: Tuple[Tuple[str, Tuple[Tuple[str, float], ...]], ...] = ()
    # FRAME ARC-06a (B1): repair events the facet's own package refused, or unions spanning materials — NOT computed,
    # NOT billed. Additive, default (): a claim with none is byte-identical. Non-empty = the claim is UNRESOLVED and
    # page 4 refuses to export it (workbench_seam / the bridge carry these to the pages).
    unsupported_operations: Tuple[UnsupportedOperation, ...] = ()
    # FRAME ARC-06a (E): roof-level work held for an owner ruling (see HeldOperation). Additive, default ().
    held_operations: Tuple[HeldOperation, ...] = ()


mkframe_pts = _quiet_import_regression_symbol("mkframe_pts")
appurtenance_zone_geometry = _quiet_import_regression_symbol("appurtenance_zone_geometry")   # FRAME v102: the TYPE decides the zone
appurtenance_zone_holes = _quiet_import_regression_symbol("appurtenance_zone_holes")         # FRAME v103: a point zone is not carved by its own hole

_EDGE_DRIVEN_CATEGORIES = {
    "RIDGE_CAPS",
    "HIP_CAPS",
    "STARTER",
    "DRIP_EDGE",
    "STEP_FLASH",
    "ENDWALL_FLASH",
}

# ---- THE CROSS-COMPONENT APPURTENANCE DEDUPE SET — ONE DEFINITION, TWO CALL SITES ------------------
# FRAME v106.6b. This set decides which lines collapse to ONE when the user has linked several markers as
# one physical object. The rule it encodes, unchanged since the grouping build:
#
#   A COUNT OF THE PHYSICAL OBJECT DEDUPES. A QUANTITY OF MATERIAL DOES NOT.
#
# One chimney gets one flashing however many planes it penetrates, so CHIMNEY_FLASH is here. But the
# carved affected AREA, the APPURT_IWS and — new at v106.6b — the membrane LEG and the repair PATCH are
# quantities of material on each plane the object really does penetrate, so they are NOT here and must
# never be added. Deduping a material quantity under-scopes the claim invisibly; an over-scope is visible
# and correctable, an under-scope is not.
#
# WHY IT IS ONE NAME NOW. Until v106.6b this nine-id set existed as TWO identical literals 1,034 lines
# apart — one local to `assemble_full_roof_scope`, one module-level for `_aggregate_by_structure`. Adding
# SKYLIGHT_UNIT to one and not the other would make the whole-roof scope and the per-structure scope
# disagree, silently, on multi-structure claims only. Nothing linked them and nothing would have caught
# the drift, so the duplicate is removed rather than kept in sync by hand.
#
# THIS NAME IS AUTHORITATIVE. Both call sites read it and no other copy exists.
_APPURT_MATERIAL_CATEGORIES = {
    "CHIMNEY_FLASH", "SKYLIGHT_FLASH", "PIPE_JACK_FLASH", "BOX_VENT",
    "TURBINE_VENT", "VENT_CAP", "CHIMNEY_CHASE_COVER", "RIDGE_VENT", "UNMAPPED",
    # FRAME v106.6b: the skylight UNIT — its own detach-and-reset or replacement. One skylight is one
    # unit however many planes its curb crosses, so it is a count and it dedupes. Its sibling line, the
    # 4in membrane curb leg, bills MODBIT_FIELD_RR and is deliberately absent: that is material.
    "SKYLIGHT_UNIT",
}


def _shake_measurements_from_selection(confirmed_selection: Mapping[str, object]) -> Mapping[str, object]:
    # FRAME ARC-06a: the ONE claim-level profile read is roof_systems.claim_geometry_profile (identical logic). This
    # helper and the two below are byte-identical in module1_service.py and module2_assembly.py (appurtenance A8b).
    return _claim_geometry_profile(confirmed_selection)


def _facet_geometry_profile(face_id, confirmed_selection) -> Mapping[str, object]:
    """FRAME ARC-06a (B1): the profile the GEOMETRY of `face_id`'s repair events runs with — the facet's own package
    and profile (roof_systems.geometry_profile_for_facet). The claim-level profile when the facet's system is the
    claim profile's system (every single-system claim: unchanged); otherwise the facet's own. The SCOPE side
    (M1Interface.measured_profile) is untouched: it keeps the claim-level profile exactly as before. One registry
    function for both the diagram and the scope, so the diagram draws exactly what the scope computes."""
    return _geometry_profile_for_facet(face_id, confirmed_selection or {},
                                       _shake_measurements_from_selection(confirmed_selection or {}))


def _members_geometry_profile(member_face_ids, confirmed_selection, context) -> Mapping[str, object]:
    """FRAME ARC-06a (B1): the ONE profile a union across several facets (a merged slope) runs with. The members must
    carry one roof system (system_for_facets raises RegistryWiringError on a SYSTEM BOUNDARY) and, in a project, one
    profile; a union across materials is never computed with either side's geometry."""
    return _geometry_profile_for_facets([str(m) for m in member_face_ids], confirmed_selection or {},
                                        _shake_measurements_from_selection(confirmed_selection or {}), context)


def _unsupported_record(geom, face_id, component_type, event, confirmed_selection, exc, kind):
    """One UnsupportedOperation receipt — the facet, its event, the system it resolves to and the refusal's words."""
    fid = str(face_id)
    members = fid.split("+")
    designator = "+".join(str(getattr(geom.faces.get(m), "designator", "") or m) if m in geom.faces else m
                          for m in members)
    try:
        sid = system_for_facets(members, confirmed_selection) if len(members) > 1 else system_for_facet(fid, confirmed_selection)
    except _RegistryWiringError:
        sid = "+".join(str(system_for_facet(m, confirmed_selection)) for m in members)
    return UnsupportedOperation(face_id=fid, designator=designator, component_type=component_type, event=str(event),
                                system_id=str(sid), kind=kind, reason=str(exc) or type(exc).__name__)


# FRAME ARC-04a: `_iface_profile` RETIRED. It projected the measured profile onto M1Interface's three wood-shake fields
# with core-held 7.0 / 10.0 / 24.0 fallbacks. The interface now carries the resolved profile opaquely
# (`measured_profile=`), and the scoping package resolves its own dimensions and defaults (the wood-shake package's
# interface_profile — "all three, never a subset" is kept there).

def assemble_full_roof_scope(xml_text: str, confirmed_selection: Mapping[str, object]) -> RoofAssemblyResult:
    """Build full roof scope from confirmed selections using surfaced M1 interfaces."""
    geom = parse_eagleview_geometry(xml_text)
    notch_candidates = {tuple(c.source_ids): c for c in emit_notch_candidates(geom)}
    shake_measurements = _shake_measurements_from_selection(confirmed_selection)
    # v71 DEFECT 3: eave ICE & WATER. The assertion (page 2) fires it only when code and/or existing
    # is marked; the measured soffit depth (page 1) sets the coverage width and layer count. Both are
    # roof-level and are threaded onto the FACET interfaces only (eaves are per-facet perimeter edges,
    # never shared across facets, so no double count) — not the appurtenance host interfaces.
    _eave_iws = confirmed_selection.get("eave_iws")
    _eave_iws_basis = (_eave_iws if isinstance(_eave_iws, Mapping)
                       and (_eave_iws.get("code") or _eave_iws.get("existing")) else None)
    _soffit_depth = confirmed_selection.get("soffit_depth_in")
    if _soffit_depth in (None, "") and isinstance(shake_measurements, Mapping):
        _soffit_depth = shake_measurements.get("soffit_depth_in")
    selected_valley_ids = tuple(str(v) for v in confirmed_selection.get("selected_valley_ids", ()))
    selected_meta = selected_valley_handoff(xml_text, selected_valley_ids) if selected_valley_ids else {"selected_valley_LF_total": 0.0}
    selected_valley_lf = float(selected_meta["selected_valley_LF_total"])
    valley_lf_claimed: set[str] = set()
    # FRAME v106.4 — THE VALLEY FACET-PAIR MAP, computed ONCE here and reused by the operation vote below.
    # It was built at the vote site only; the boundary test needs it before the claim loops run, and a second
    # walk of emit_valley_candidates would be a second source for the same fact.
    _valley_pairs = {str(c.source_ids[0]): tuple(str(f) for f in c.params.get("bordering_roof_face_ids", ()))
                     for c in emit_valley_candidates(geom)}
    _boundary_valleys = _system_boundary_valley_ids(_valley_pairs, confirmed_selection)

    # --- PATH B: user-confirmed transition repair events (spec amendment v0.1) ---------------
    # The gate (exposed AND damaged) is enforced in transition_events at the DATA layer, so a
    # hand-crafted payload cannot bypass it. Only DETECTED transitions can be selected — the
    # three-condition detector is untouched and edge_total_LF is never user-edited.
    # Bands are precomputed per facet and handed to the SAME affected_area call as that facet's
    # valley events, so the zones UNION (never sum). No transition selected -> empty dict ->
    # every existing call is bit-for-bit unchanged and the anchor holds by construction.
    # BUILD 2b — PATH A IS NOW LIVE. This line used to be `transitions=[]`, hardcoded, so the >=95%
    # passive rule NEVER RAN on a real roof: Yager's L33 is swept 100% by the standard repair and was
    # being silently dropped. Both paths are evaluated now, each transition appearing exactly ONCE.
    # Facets the USER asserted are high (2-story). EagleView cannot tell us this — it gives roof
    # geometry, not wall heights — so it is an explicit assertion, and page 2 forces the decision.
    _high_slope = _high_slope_faces(confirmed_selection)

    active_transitions = _active_transitions(geom, confirmed_selection)
    bands_by_face = transition_bands_by_face(geom, confirmed_selection, shake_measurements) if active_transitions else {}
    # FRAME v106.3b — THE COURSED SIDE OF A SYSTEM BOUNDARY IS OPENED TOO, and its band joins the SAME dict,
    # so every rule below it applies unchanged: the incremental union-correct carve, the v72 skip for a facet
    # already fully replaced, the v106.1 disclosure for an excluded facet, and the per-facet component.
    #
    # JOSEPH, 2026-11-04, asked what a FLAT-ONLY replacement does at the transition area. Measured answer
    # before this: the membrane billed its 0.7608 SQ run up the slope and the shake side billed NOTHING —
    # yet 20.75 LF x 44 in of existing shake has to come off for that membrane to get under it. He ruled it
    # should be billed, with the same lines a transition band bills.
    #
    # AND IT IS THE SAME RULE, not a new one: transition_bands_by_face's v91 MEMBRANE branch already says
    # "the steep (UPPER) side is still opened — three courses lifted to tuck the membrane under", and Joseph
    # approved "the band still carves the untouched slope" on 2026-10-25. It never fired here only because
    # EagleView types these lines VALLEY, so the geometric detector never offers them.
    #
    # NOT SYMMETRIC WITH THE TIE-IN, and deliberately so. The membrane's own line fires when the MEMBRANE is
    # replaced; this band fires on the coursed side when the FLAT side is replaced. Both follow from one
    # physical fact: new membrane cannot get under courses that are still nailed down, while existing
    # membrane under courses nobody lifts simply stays. Replace the shake alone and neither fires — the
    # shake field already covers the courses it relays, which is Joseph's ruling of 2026-11-04 holding by
    # construction through the v72 skip below.
    for _vid, _band_face, _band_lf, _band_ft in _system_boundary_bands(
            geom, _boundary_valleys, _valley_pairs, confirmed_selection, shake_measurements):
        bands_by_face.setdefault(_band_face, []).append(
            system_boundary_band_for_face(geom, _band_face, _vid, _band_lf, _band_ft, shake_measurements))
    if bands_by_face:
        confirmed_selection = {**dict(confirmed_selection), "_transition_bands_by_face": bands_by_face}

    components: List[ComponentAssembly] = []
    breakdown: List[Mapping[str, str]] = []
    # FRAME v106.1 — the facets this claim does not scope, and the receipts for what was declined.
    _excluded = excluded_facets(confirmed_selection)
    _boundary_disclosures: List[SystemBoundaryDisclosure] = []
    # AN EXPLICIT REPAIR ON AN EXCLUDED FACET IS A CONTRADICTION, AND IT RAISES. A transition BAND reaching
    # an excluded facet is not user error — the band lands on both facets of a shared edge by itself, so that
    # case is disclosed below. But a valley repair, a full replacement or an appurtenance on an excluded facet
    # is the user asserting two incompatible things, and core will not pick one. Silently dropping the repair
    # would be an invisible under-scope; silently billing it is the F36 defect. So it stops and says which.
    if _excluded:
        # EACH LIST IS READ BY ITS OWN KEY. They genuinely differ — face_id, host_face_id, host_facet_id,
        # and notch_repairs carries a LIST of member_face_ids — so one hard-coded "face_id" would KeyError on
        # an appurtenance and silently miss a notch, billing shake on an excluded member. (QA wrote exactly
        # that bug first; the gate's selections were too simple to catch it.)
        _SCOPING_KEYS = (
            ("single_valley_repairs", "a valley repair", ("face_id",)),
            ("multi_valley_facets", "a multi-valley repair", ("face_id",)),
            ("replaced_facets", "a full replacement", ("face_id",)),
            ("penetration_appurtenance_repairs", "an appurtenance repair", ("host_face_id",)),
            ("user_appurtenance_repairs", "a user appurtenance", ("host_facet_id",)),
            ("notch_repairs", "a notch merge", ("member_face_ids",)),
            ("high_slope_facets", "a high-slope flag", ("face_id",)),
        )
        _asked: Dict[str, List[str]] = {}
        for _key, _label, _fields in _SCOPING_KEYS:
            for _it in (confirmed_selection.get(_key, ()) or ()):
                if isinstance(_it, str):
                    _ids = [_it]
                else:
                    _row = _as_mapping(_it)
                    _ids = []
                    for _f in _fields:
                        _v = _row.get(_f)
                        if _v is None:
                            continue
                        _ids.extend(_v if isinstance(_v, (list, tuple, set, frozenset)) else [_v])
                for _fid in (str(x) for x in _ids):
                    if _fid in _excluded:
                        _asked.setdefault(_fid, []).append(_label)
        if _asked:
            _detail = "; ".join(f"{f}: {', '.join(sorted(set(v)))}" for f, v in sorted(_asked.items()))
            raise ValueError(
                f"FRAME: {sorted(_asked)} are listed in excluded_facets but the selection also asks to scope "
                f"them ({_detail}). An excluded facet is not scoped at all. Fix: remove each facet from "
                f"excluded_facets, or remove the repair that scopes it.")

    _unsupported: List[UnsupportedOperation] = []   # FRAME ARC-06a (B1): refused events, never billed
    for item in confirmed_selection.get("single_valley_repairs", ()):  # type: ignore[union-attr]
        row = _as_mapping(item)
        face_id = str(row["face_id"])
        valley_id = str(row["valley_id"])
        _require_valley_borders_face(geom, valley_id, face_id)
        # FRAME ARC-06a (B1): the facet's OWN package computes its valley geometry. A package that refuses the event
        # (NotImplementedError, by name) leaves a receipt instead of a component, and gives back the valley LF it was
        # about to claim — so nothing of the refused event is billed and every other component is untouched.
        _claimed_before = set(valley_lf_claimed)
        try:
            valley_lf = _claim_valley_lf_once(geom, valley_id, selected_valley_ids, valley_lf_claimed,
                                              _boundary_valleys)
            affected = _single_valley_area(geom, face_id, valley_id, confirmed_selection)
            _gp = _facet_geometry_profile(face_id, confirmed_selection)
            _sv_edges = _face_edge_contributions(geom, face_id, (valley_id,), str(row.get("label", face_id)), _gp)
        except NotImplementedError as _e:
            valley_lf_claimed.clear(); valley_lf_claimed.update(_claimed_before)
            _unsupported.append(_unsupported_record(geom, face_id, "single_valley", f"VALLEY {valley_id}",
                                                    confirmed_selection, _e, "PACKAGE_REFUSED"))
            continue
        iface = build_m1_interface_for_face(
            geom,
            face_id,
            confirmed_valley_line_ids=(valley_id,),
            affected_SF=affected,
            valley_LF_in_scope=valley_lf,
            confirmed_appurtenance_candidates=(),
            shake_measurements=shake_measurements,
            facet_pitch_tier=_facet_pitch_tier(geom, face_id),
            high_slope_user_flag=(str(face_id) in _high_slope),
            # FRAME v106.3b: the repair's OWN valley, so a boundary at the other end of the facet is untouched.
            extra_edges=_system_boundary_edges(geom, face_id, (valley_id,), _boundary_valleys,
                                               _valley_pairs, confirmed_selection, shake_measurements),
            geometry_profile=_gp,   # FRAME ARC-06a (B1): edge contact runs the facet's own valley geometry
        )
        edge_contribs = _sv_edges
        components.append(_component(row, face_id, "single_valley", "derived", "fully_surfaced", "face, valley event, edges, and valley LF derived from parser/candidates", iface, edge_contribs, confirmed_selection=confirmed_selection))
        breakdown.append(_breakdown(components[-1]))

    for item in confirmed_selection.get("multi_valley_facets", ()):  # type: ignore[union-attr]
        row = _as_mapping(item)
        face_id = str(row["face_id"])
        valley_ids = tuple(str(v) for v in row.get("valley_ids", ()))
        for valley_id in valley_ids:
            _require_valley_borders_face(geom, valley_id, face_id)
        _claimed_before = set(valley_lf_claimed)   # FRAME ARC-06a (B1): see the single-valley loop
        try:
            valley_lf = sum(_claim_valley_lf_once(geom, valley_id, selected_valley_ids, valley_lf_claimed,
                                                  _boundary_valleys) for valley_id in valley_ids)
            affected = _multi_valley_union_area(geom, face_id, valley_ids, confirmed_selection, include_child_penetrations=bool(row.get("include_child_penetrations", True)))
            _gp = _facet_geometry_profile(face_id, confirmed_selection)
            _mv_edges = _face_edge_contributions(geom, face_id, valley_ids, str(row.get("label", face_id)), _gp)
        except NotImplementedError as _e:
            valley_lf_claimed.clear(); valley_lf_claimed.update(_claimed_before)
            _unsupported.append(_unsupported_record(geom, face_id, "multi_valley", "VALLEY " + ", ".join(valley_ids),
                                                    confirmed_selection, _e, "PACKAGE_REFUSED"))
            continue
        iface = build_m1_interface_for_face(
            geom,
            face_id,
            confirmed_valley_line_ids=valley_ids,
            affected_SF=affected,
            valley_LF_in_scope=valley_lf,
            confirmed_appurtenance_candidates=(),
            shake_measurements=shake_measurements,
            facet_pitch_tier=_facet_pitch_tier(geom, face_id),
            high_slope_user_flag=(str(face_id) in _high_slope),
            extra_edges=_system_boundary_edges(geom, face_id, valley_ids, _boundary_valleys,
                                               _valley_pairs, confirmed_selection, shake_measurements),
            geometry_profile=_gp,   # FRAME ARC-06a (B1)
        )
        edge_contribs = _mv_edges
        components.append(_component(row, face_id, "multi_valley", "derived", "fully_surfaced", "multi-valley union, edges, and non-duplicated selected valley LF derived from parser/candidates", iface, edge_contribs, confirmed_selection=confirmed_selection))
        breakdown.append(_breakdown(components[-1]))

    # --- PATH C: FULL SLOPE REPLACEMENT (v61) -------------------------------------------------
    # A facet marked for full replacement: the WHOLE facet (net of penetrations) comes off, billed in
    # SQUARES (a stripped slope is conventional square-based work; billing EA would claim the repair
    # labor premium a full slope does not involve). The perimeter falls out of the EXISTING edge rules
    # at 100% contact, deduped against an adjoining facet. VALLEY_METAL/IWS bill ONLY from
    # valley_LF_in_scope, so every valley on the facet's perimeter is claimed here (the whole valley
    # comes out — you cannot replace half a W-metal), deduped against any facet that also claims it.
    # Steep/high-slope and felt are area-driven and fire automatically on the full area. No facet
    # marked -> this loop is empty and every existing selection is bit-for-bit unchanged.
    _replaced_ids = {str(_as_mapping(_it)["face_id"]) for _it in confirmed_selection.get("replaced_facets", ())}
    if _replaced_ids:
        # MUTUAL EXCLUSION (rule 2): a facet cannot be replaced AND repaired. The UI clears the repair
        # selection; enforce it at the DATA layer so a hand-built payload cannot double-count a slope.
        for _it in (*confirmed_selection.get("single_valley_repairs", ()), *confirmed_selection.get("multi_valley_facets", ())):
            if str(_as_mapping(_it)["face_id"]) in _replaced_ids:
                raise ValueError(f"facet {_as_mapping(_it)['face_id']} is marked for BOTH replacement and repair")
    for item in confirmed_selection.get("replaced_facets", ()):
        row = _as_mapping(item)
        face_id = str(row["face_id"])
        if face_id not in geom.roof_faces:
            raise ValueError(f"replaced facet {face_id} is not a roof facet")
        label = str(row.get("label", face_id))
        affected = _replacement_facet_area(geom, face_id)
        valley_lf = sum(_claim_replacement_valley_lf(geom, vid, valley_lf_claimed, _boundary_valleys)
                        for vid in _facet_valley_ids(geom, face_id))
        iface = build_m1_interface_for_face(
            geom,
            face_id,
            confirmed_valley_line_ids=(),
            affected_SF=affected,
            valley_LF_in_scope=valley_lf,
            confirmed_appurtenance_candidates=(),
            shake_measurements=shake_measurements,
            facet_pitch_tier=_facet_pitch_tier(geom, face_id),
            high_slope_user_flag=(face_id in _high_slope),
            is_replacement=True,
            # FRAME v106.3b: a stripped facet takes its WHOLE perimeter, so EVERY boundary on it is in scope —
            # the same `_facet_valley_ids` the valley claim two lines above uses, for the same reason.
            extra_edges=_system_boundary_edges(geom, face_id, _facet_valley_ids(geom, face_id),
                                               _boundary_valleys, _valley_pairs, confirmed_selection,
                                               shake_measurements),
        )
        edge_contribs = _replacement_edge_contributions(geom, face_id, label)
        components.append(_component(row, face_id, "replacement", "derived", "fully_surfaced",
            "full slope replacement: whole facet net of penetrations, 100% perimeter contact, all valleys fully in scope", iface, edge_contribs, confirmed_selection=confirmed_selection))
        breakdown.append(_breakdown(components[-1]))

    for item in confirmed_selection.get("penetration_appurtenance_repairs", ()):  # type: ignore[union-attr]
        row = _as_mapping(item)
        penetration_id = str(row["penetration_face_id"])
        host_face_id = str(row.get("host_face_id") or _host_face_for_penetration(geom, penetration_id))
        candidate = _penetration_candidate_from_geom(geom, host_face_id, penetration_id)
        # FRAME v102: the TYPE decides the zone. The parser always measures a penetration as "dimensioned" (its
        # polygon); route it by the row's label, with the assembly's own unlabelled default (CHIMNEY), so only a
        # point category reroutes. Measured w/h ride along for APPURT_IWS (geometry_core.appurtenance_zone_geometry).
        candidate = Candidate(kind=candidate.kind, source_ids=candidate.source_ids, origin=candidate.origin,
            params={**candidate.params, "appurtenance_geometry": appurtenance_zone_geometry(
                candidate.params.get("appurtenance_geometry"), row.get("kind_label", "CHIMNEY"),
                row.get("other_category"))})   # FRAME v106.6g: routed by TYPE; no clearance resolved here
        _rfacets = set()
        for _it in confirmed_selection.get("single_valley_repairs", ()): _rfacets.add(str(_as_mapping(_it)["face_id"]))
        for _it in confirmed_selection.get("multi_valley_facets", ()): _rfacets.add(str(_as_mapping(_it)["face_id"]))
        for _it in confirmed_selection.get("notch_repairs", ()):
            for _m in _as_mapping(_it).get("member_face_ids", ()): _rfacets.add(str(_m))
        # In-field appurtenance dedup is union-not-sum: only the overlap with
        # already-scoped repair zones is subsumed. Any portion of the 21in
        # disturbance zone outside the host/merged-plane repair union still counts.
        # THE FAN CARVES. THE COVER DOES NOT. One authority for the question, imported from
        # shared_category_registry so the SCOPE and the DIAGRAM (module1_service) can never drift.
        # A cover-only power vent contributes ZERO affected area — the carve is the ONLY thing that
        # differs between the two operations; the material line below is identical for both.
        _carves = appurtenance_carves(row)
        _replaced_ids = {str(_as_mapping(_it)["face_id"]) for _it in confirmed_selection.get("replaced_facets", ())}
        try:   # FRAME ARC-06a (B1): its net area is deduped against the host's repair zone, which the package may refuse
            affected = _appurtenance_union_affected_area(geom, host_face_id, candidate, confirmed_selection, _carves, _replaced_ids, _rfacets)
        except NotImplementedError as _e:
            _unsupported.append(_unsupported_record(geom, host_face_id, "penetration_appurtenance",
                                                    f"APPURTENANCE {penetration_id} (deduped against a refused repair "
                                                    f"zone on its host)", confirmed_selection, _e, "PACKAGE_REFUSED"))
            continue
        appurt_candidate = _with_appurtenance_label(candidate, str(row.get("kind_label", "CHIMNEY")), str(row.get("group", penetration_id)), row.get("contacted"), row.get("size_class"), carves=_carves, other_label=row.get("other_label"), other_category=row.get("other_category"),
            operation=(row.get("operation") or row.get("skylight_operation") or row.get("power_vent_operation")),
            host_replaced=str(host_face_id) in _replaced_ids,
            shared_edge_ft=_group_shared_edge_ft(geom, row, penetration_id, host_face_id, confirmed_selection))
        iface = build_m1_interface_for_face(
            geom,
            host_face_id,
            confirmed_valley_line_ids=(),
            affected_SF=affected,
            valley_LF_in_scope=0.0,
            confirmed_appurtenance_candidates=(appurt_candidate,),
            shake_measurements=shake_measurements,
            # THE FACET IS host_face_id here, not the loop's `face_id` — reading the wrong variable
            # made a 7-9 appurtenance emit a ">12" steep charge and a high-slope charge nobody asserted.
            facet_pitch_tier=_facet_pitch_tier(geom, host_face_id),
            high_slope_user_flag=(str(host_face_id) in _high_slope),
        )
        edge_contribs = _face_edge_contributions(geom, host_face_id, (), str(row.get("label", host_face_id)), shake_measurements)
        components.append(_component(row, host_face_id, "penetration_appurtenance", "derived", "fully_surfaced", "host facet, appurtenance footprint, edges, and Appurt payload derived from parser/candidates", iface, edge_contribs, confirmed_selection=confirmed_selection))
        breakdown.append(_breakdown(components[-1]))

    for item in confirmed_selection.get("user_appurtenance_repairs", ()):  # type: ignore[union-attr]
        row = _as_mapping(item)
        if not bool(row.get("repair_event", True)):
            continue
        host_face_id = str(row["host_facet_id"])
        candidate = _user_appurtenance_candidate_from_row(row, confirmed_selection)
        _rfacets = set()
        for _it in confirmed_selection.get("single_valley_repairs", ()): _rfacets.add(str(_as_mapping(_it)["face_id"]))
        for _it in confirmed_selection.get("multi_valley_facets", ()): _rfacets.add(str(_as_mapping(_it)["face_id"]))
        for _it in confirmed_selection.get("notch_repairs", ()):
            for _m in _as_mapping(_it).get("member_face_ids", ()): _rfacets.add(str(_m))
        # THE FAN CARVES. THE COVER DOES NOT — same single authority as the XML-detected path above.
        # A user-placed power vent behaves identically to a detected one; nothing about the rule
        # depends on where the marker came from.
        _carves = appurtenance_carves(row)
        _replaced_ids = {str(_as_mapping(_it)["face_id"]) for _it in confirmed_selection.get("replaced_facets", ())}
        try:   # FRAME ARC-06a (B1): see the XML-detected appurtenance loop above
            affected = _appurtenance_union_affected_area(geom, host_face_id, candidate, confirmed_selection, _carves, _replaced_ids, _rfacets)
        except NotImplementedError as _e:
            _unsupported.append(_unsupported_record(geom, host_face_id, "user_appurtenance",
                                                    f"APPURTENANCE {row.get('designator') or row.get('label') or 'user'} "
                                                    f"(deduped against a refused repair zone on its host)",
                                                    confirmed_selection, _e, "PACKAGE_REFUSED"))
            continue
        appurt_candidate = _with_appurtenance_label(candidate, str(row.get("kind_label", "OTHER")), str(row.get("designator") or row.get("label") or "user"), row.get("contacted"), row.get("size_class"), carves=_carves, other_label=row.get("other_label"), other_category=row.get("other_category"),
            operation=(row.get("operation") or row.get("skylight_operation") or row.get("power_vent_operation")),
            host_replaced=str(host_face_id) in _replaced_ids)
        iface = build_m1_interface_for_face(
            geom,
            host_face_id,
            confirmed_valley_line_ids=(),
            affected_SF=affected,
            valley_LF_in_scope=0.0,
            confirmed_appurtenance_candidates=(appurt_candidate,),
            shake_measurements=shake_measurements,
            # THE FACET IS host_face_id here, not the loop's `face_id` — reading the wrong variable
            # made a 7-9 appurtenance emit a ">12" steep charge and a high-slope charge nobody asserted.
            facet_pitch_tier=_facet_pitch_tier(geom, host_face_id),
            high_slope_user_flag=(str(host_face_id) in _high_slope),
        )
        edge_contribs = _face_edge_contributions(geom, host_face_id, (), str(row.get("label", row.get("designator", host_face_id))), shake_measurements)
        components.append(_component(row, host_face_id, "user_appurtenance", "derived", "fully_surfaced", "host facet and user-entered appurtenance footprint supplied by confirmed selection", iface, edge_contribs, confirmed_selection=confirmed_selection))
        breakdown.append(_breakdown(components[-1]))

    for item in confirmed_selection.get("notch_repairs", ()):  # type: ignore[union-attr]
        row = _as_mapping(item)
        member_face_ids = tuple(str(v) for v in row["member_face_ids"])
        candidate = _require_notch_candidate(notch_candidates, member_face_ids)
        # FRAME ARC-06a (B1): a merge spanning materials is never computed with either side's geometry — it is a
        # SYSTEM_BOUNDARY receipt; one material, its own profile; a package refusal, a PACKAGE_REFUSED receipt.
        _nid = "+".join(member_face_ids)
        _claimed_before = set(valley_lf_claimed)
        try:
            _gp = _geometry_profile_for_facets(member_face_ids, confirmed_selection, shake_measurements,
                                              f"module2_assembly: the notch merge {_nid}")
        except Exception as _e:
            from project_config import ProjectConfigError as _PCE   # call time, as _component imports it
            if not isinstance(_e, (_RegistryWiringError, _PCE)):
                raise
            _unsupported.append(_unsupported_record(geom, _nid, "notch", "NOTCH MERGE " + _nid,
                                                    confirmed_selection, _e, "SYSTEM_BOUNDARY"))
            continue
        try:
            iface, edge_contribs = _build_m1_interface_for_notch(geom, candidate, selected_valley_ids, valley_lf_claimed, str(row.get("label", _nid)), confirmed_selection=confirmed_selection, override_valley_ids=row.get("valley_ids"), shake_measurements=shake_measurements, boundary_valleys=_boundary_valleys, geometry_profile=_gp)
        except NotImplementedError as _e:
            valley_lf_claimed.clear(); valley_lf_claimed.update(_claimed_before)
            _unsupported.append(_unsupported_record(geom, _nid, "notch", "NOTCH VALLEY " + _nid,
                                                    confirmed_selection, _e, "PACKAGE_REFUSED"))
            continue
        components.append(_component(row, "+".join(member_face_ids), "notch", "derived", "fully_surfaced", "merged facet, notch polygon, RIDGE anchor, VALLEY events, and edges derived from notch candidate", iface, edge_contribs, confirmed_selection=confirmed_selection))
        breakdown.append(_breakdown(components[-1]))

    # --- PATH B: carve the band on every facet the transition touches --------------------------
    # UNION, NEVER SUM. A facet that carries a VALLEY component already had its band unioned INTO
    # that component's affected_area call (the bands were threaded through the valley area helpers),
    # so it needs nothing more. Any OTHER facet the transition touches (e.g. Yager's P, which carries
    # only a chimney appurtenance) gets a transition component whose area is the band's INCREMENTAL
    # contribution: the facet's area WITH the band minus the same facet's area WITHOUT it, computed
    # over the identical set of that facet's other events. Overlap with an appurtenance (or anything
    # else already counted on that facet) therefore cancels out exactly — no double count.
    valley_threaded_faces = set()
    for item in confirmed_selection.get("single_valley_repairs", ()):  # type: ignore[union-attr]
        valley_threaded_faces.add(str(_as_mapping(item)["face_id"]))
    for item in confirmed_selection.get("multi_valley_facets", ()):    # type: ignore[union-attr]
        valley_threaded_faces.add(str(_as_mapping(item)["face_id"]))

    # v72 DEFECT 4: a transition band on a FULLY REPLACED facet lies inside a facet already 100%
    # scoped — exactly the appurtenance double-count fixed in v63, applied here to the transition path.
    # The band is UNIONED: it contributes NO incremental area and NO shakes (or the roof bills 186 EA
    # of shakes on a SQ replacement and gains +90.1632 SF). TRANSITION_FLASH and its underlayment still
    # fire — they are emitted at the ROOF level below, untouched by this skip.
    _replaced_band_ids = {str(_as_mapping(_it)["face_id"])
                          for _it in confirmed_selection.get("replaced_facets", ())}

    for face_id, bands in sorted(bands_by_face.items()):
        if face_id in valley_threaded_faces:
            continue                                   # band already unioned into the valley zone
        if str(face_id) in _replaced_band_ids:
            continue                                   # v72: band inside a fully-replaced facet -> unioned
        engine_face = geom.engine_facet(face_id)
        pens = _penetrations_with_user_footprints(geom, confirmed_selection, face_id)
        apps = _confirmed_appurtenance_geometries_for_face(geom, confirmed_selection, face_id)
        # FRAME v106.6c: this pair measures a transition band's INCREMENTAL area, differencing two carves of
        # the same facet. Both must name the facet's covering, and name the SAME one — a band's net area is
        # `area_with - area_without`, so if the two carves used different clearances the appurtenance zones
        # would not cancel and the band would absorb the difference as if it were band.
        _facet_sys = system_for_facet(face_id, confirmed_selection)
        _band_gp = _facet_geometry_profile(face_id, confirmed_selection)   # FRAME ARC-06a: the facet's own profile
        _p0, area_without = affected_area(
            engine_face.facet, [], appurtenances=apps, penetrations=pens,
            shake_measurements=_band_gp, facet_system_id=_facet_sys)
        _p1, area_with = affected_area(
            engine_face.facet, [], appurtenances=apps, penetrations=pens,
            shake_measurements=_band_gp, transition_bands=engine_bands(bands),
            facet_system_id=_facet_sys)
        net_area = max(0.0, float(area_with) - float(area_without))   # incremental, union-correct

        # FRAME v106.1 — AN EXCLUDED FACET TAKES NO BAND, AND LEAVES A RECEIPT. A transition's band lands on
        # BOTH its facets automatically; when one of them is not scoped by this claim, billing it is the
        # Killarney F36 defect (entry 115d): 5.6112 SF and 12 EA of wood shake carved onto a surface that is
        # not wood shake. Dropping it SILENTLY would be the opposite error and the worse one — this file's own
        # rule, written for appurtenance dedupe, is that an over-scope is visible and an under-scope is not —
        # so the drop is disclosed with the exact area it withheld.
        #
        # The check sits HERE, after net_area, and not at the top of the loop, so the disclosed figure is the
        # SAME arithmetic that would have billed it: one computation, then the decision. A separate helper
        # would be a second copy of the union-correct incremental carve, free to drift from this one.
        #
        # The scoped side is untouched: the roof-level TRANSITION_FLASH still bills at edge_total_LF, because
        # the trade doing the scoped side installs the flashing (Joseph, entry 104 — each side applies its own
        # termination).
        # ONE row per excluded FACET, not per edge: net_area is the facet's whole incremental carve for ALL
        # its bands together (Killarney F36 takes bands from both L24 and L34, totalling 5.6112 SF). A row per
        # edge would repeat that figure and read as twice the area withheld.
        if str(face_id) in _excluded:
            _lids = sorted({str(_as_mapping(_b)["edge_id"]) for _b in bands}, key=_id_sort_key)
            _boundary_disclosures.append(SystemBoundaryDisclosure(
                face_id=str(face_id),
                designator=str(geom.faces[face_id].designator or ""),
                edge_id=", ".join(_lids),
                edge_type=", ".join(sorted({str(geom.lines[l].type) for l in _lids if l in geom.lines})),
                dropped_SF=round(net_area, 4),
                reason="facet excluded from this scope: not the scoped roof system"))
            continue

        iface = build_m1_interface_for_face(
            geom,
            face_id,
            confirmed_valley_line_ids=(),
            affected_SF=net_area,
            valley_LF_in_scope=0.0,
            confirmed_appurtenance_candidates=(),
            shake_measurements=shake_measurements,
            facet_pitch_tier=_facet_pitch_tier(geom, face_id),
            high_slope_user_flag=(str(face_id) in _high_slope),
        )
        edge_ids = ", ".join(sorted({str(b["edge_id"]) for b in bands}))
        row = {"label": f"Transition {edge_ids} on {geom.faces[face_id].designator}", "face_id": face_id}
        components.append(_component(
            row, face_id, "transition_repair", "derived", "fully_surfaced",
            "user-confirmed transition repair event (exposed + damaged); band carved on both facets",
            iface, (), confirmed_selection=confirmed_selection))
        breakdown.append(_breakdown(components[-1]))

    # ONE TRANSITION_FLASH per transition, emitted at the ROOF level (never per facet), exactly as
    # edge_scope_lines are. This is the structural de-dupe: the transition has TWO facets but only
    # ONE flashing line, at edge_total_LF — the true geometric length.
    # Each active transition is handed to expand_scope with its REAL contact_LF and its selected
    # flag, so the frozen rule there decides: Path A (contact >= 95%) OR Path B (user-confirmed).
    # De-dupe is structural at both levels — one entry per transition here, one `if` there.
    transition_scope_lines: tuple = ()
    if active_transitions:
        selected_ids = set(selected_transition_repairs(confirmed_selection))
        metal_facts = transition_metal_facts(confirmed_selection)      # v91: what is AT each transition
        path_r_ids = {t.edge_id for t in path_r_transitions(geom, confirmed_selection)}   # v92 Path R
        valley_ids = [str(v) for v in (confirmed_selection.get("selected_valley_ids", ()) or ())]
        transitions_for_scope = [
            Transition(
                contact_LF=transition_contact_lf(geom, t, valley_ids, confirmed_selection),   # ARC-06a: per facet
                edge_total_LF=float(t.edge_total_LF),
                selected=t.edge_id in selected_ids,
                metal=metal_facts.get(str(t.edge_id)),               # None = never answered
                replaced=t.edge_id in path_r_ids,                    # v92: a facet is fully replaced
            )
            for t in active_transitions
        ]
        # FRAME v105.3: each transition's engine is ITS facets' roof system (they must agree — a boundary raises). The
        # transitions are grouped by system in first-appearance order, each group expanded once, and concatenated; with
        # one system that is one group, the same list in the same order. The expander treats transitions independently
        # (the flash probe below expands them one at a time).
        _trans_sys = [system_for_facets((t.face_a_id, t.face_b_id), confirmed_selection,
                                        f"module2_assembly: the roof-level transition {t.edge_id}")
                      for t in active_transitions]
        _trans_groups: Dict[str, List[Transition]] = {}
        for _sys, tr in zip(_trans_sys, transitions_for_scope):
            _trans_groups.setdefault(_sys, []).append(tr)
        transition_scope_lines = tuple(
            l for _sys, _trs in _trans_groups.items()
            for l in roof_system(_sys).expand_scope(M1Interface(transitions=_trs, measured_profile=shake_measurements),
                                                    repair_factor=1.0))
        # v93: which of these transitions actually BILL flashing — asked of the same emission authority, one
        # transition at a time, so a transition answered NONE / MEMBRANE (no flashing line) casts no vote.
        _flash_edges = [
            t for t, tr, _sys in zip(active_transitions, transitions_for_scope, _trans_sys)
            if any(l.category_id == "TRANSITION_FLASH" for l in roof_system(_sys).expand_scope(
                M1Interface(transitions=[tr], measured_profile=shake_measurements), repair_factor=1.0))]
    else:
        _flash_edges = []

    # ONE PHYSICAL OBJECT -> ONE MATERIAL LINE.
    # EagleView splits one physical chimney into one marker per facet it crosses. expand_scope
    # already dedupes appurtenances by `group` — but only WITHIN one M1Interface, and the assembly
    # gives every marker its OWN component/M1Interface, so that dedupe is never asked the question.
    # (That is why regression test 28 passed while two grouped markers still billed 2 flashings.)
    # The user links the markers of one physical object; the duplicate MATERIAL line is dropped here.
    #
    # CRITICAL — THE MATERIAL LINE ONLY:
    #   * the carved affected AREA stays per marker (the chimney really does penetrate both planes), and
    #   * APPURT_IWS stays per marker (both planes need ice & water).
    # Deduping either would silently UNDER-SCOPE the claim — invisible, and therefore worse than no
    # feature at all. An over-scope is visible and correctable; an under-scope is not.
    # The set itself is _APPURT_MATERIAL_CATEGORIES, defined once near the top of this module.
    _seen_appurt_groups: set = set()
    non_edge_lines: List[ScopeLine] = []
    all_edge_contribs: List[EdgeContribution] = []
    for comp in components:
        gid = next((a.group for a in comp.iface.appurts if a.group is not None), None)
        for line in comp.scope_lines:
            if line.category_id in _EDGE_DRIVEN_CATEGORIES:
                continue
            if gid is not None and line.category_id in _APPURT_MATERIAL_CATEGORIES:
                key = (gid, line.category_id)
                if key in _seen_appurt_groups:
                    continue                # same physical object -> its material line is already billed
                _seen_appurt_groups.add(key)
            non_edge_lines.append(line)
        # FRAME v105.3: stamp each edge contribution with its component's roof system, where the face id is in hand.
        if comp.edge_contributions:
            _csys = system_for_facet(comp.face_id, confirmed_selection)
            all_edge_contribs.extend(replace(c, system_id=_csys) for c in comp.edge_contributions)

    deduped_edge_contribs = _dedupe_edge_contributions(all_edge_contribs)
    deduped_edges = [Edge(c.edge_type, c.contact_LF, c.edge_total_LF) for c in deduped_edge_contribs]
    # Ridge vents adjust the CAPS on their own ridge (aluminum) or ride alongside them (shingle-over).
    # With no ridge marked, this is bit-for-bit the old single expand_scope call.
    edge_scope_lines = _edge_lines_with_ridge_vents(deduped_edge_contribs,
                                                    _ridge_vents(confirmed_selection))
    # v71 DEFECT 3: eave ICE & WATER at the ROOF level, from the DEDUPED eave contributions (the same
    # authority that bills STARTER, so it can never disagree and never double-counts). Fires only when
    # the user asserted code and/or existing AND there is exposed eave. Reuses the IWS id (registry
    # stays 29) so it folds into the IWS comparison total — exactly the Devore 537.16-vs-119.85 gap.
    eave_iws_lines: List[ScopeLine] = []
    eave_iws_meta = None
    _held: List[HeldOperation] = []
    if _eave_iws_basis:
        # FRAME ARC-06a (E): PER-EDGE OWNERSHIP. Every eave belongs to exactly ONE facet (eaves are per-facet perimeter
        # edges, never shared — see the threading note at the top of this function) and every deduped contribution is
        # stamped with that facet's roof system (v105.3). So the eave LF is grouped BY THE SYSTEM THAT OWNS THE EAVE,
        # and each group is answered by ITS OWN package's `roof_eave_ice_and_water` operation. A system whose package
        # declares no such operation (MODBIT) is NOT billed with another package's rule: its eaves are HELD for an
        # owner ruling (HeldOperation), and the claim is unresolved until then. With one system this is the same one
        # group, the same LF (same contributions, same order, same rounding) and the same single line as before.
        _eave_groups: Dict[str, List[EdgeContribution]] = {}
        for c in deduped_edge_contribs:
            if c.edge_type == "EAVE" and c.contact_LF > 0:
                _eave_groups.setdefault(str(c.system_id or ""), []).append(c)
        _billed_meta = []
        for _esys, _ecs in _eave_groups.items():
            _eave_lf = round(sum(c.contact_LF for c in _ecs), 2)
            if _eave_lf <= 0:
                continue
            if _esys and declares_operation(_esys, "roof_eave_ice_and_water"):
                _eave_op = require_operation(_esys, "roof_eave_ice_and_water")
                _cov, _layers, _defaulted, _eave_cite = _eave_op(_eave_lf, _soffit_depth, _eave_iws_basis)
                eave_iws_lines.append(ScopeLine("Ice & water barrier (eaves)", "IWS", _cov, "SF",
                                                "CONFIRM", _eave_cite))
                _billed_meta.append({
                    "eave_LF": _eave_lf, "coverage_SF": _cov, "layers": _layers,
                    "code": bool(_eave_iws_basis.get("code")),
                    "existing": bool(_eave_iws_basis.get("existing")),
                    "soffit_depth_in": (None if _defaulted else float(_soffit_depth)),
                    "citation": _eave_cite,
                })
            else:
                _held.append(HeldOperation(
                    operation="roof_eave_ice_and_water", system_id=_esys or "(unattributed)",
                    basis=(("eave_LF", float(_eave_lf)),),
                    edge_ids=tuple(sorted({str(c.line_id) for c in _ecs}, key=_id_sort_key)),
                    reason=(f"eave ice & water was asserted for this claim, but these {_eave_lf} LF of eave belong to "
                            f"facets covered by {_esys or 'an unattributed system'!r}, whose roof-system package "
                            f"declares no eave ice & water rule. Another covering's rule is never borrowed. "
                            f"Owner decision needed (ARC-06a Q-E1): what eave underlayment treatment, if any, this "
                            f"covering requires. Nothing was billed for these eaves.")))
        if len(_billed_meta) == 1:
            eave_iws_meta = _billed_meta[0]
        elif _billed_meta:   # two declaring packages, each billing ITS OWN eaves (not reachable with today's packages)
            eave_iws_meta = {**_billed_meta[0], "by_system": tuple(_billed_meta)}
    aggregated = _aggregate_lines([*non_edge_lines, *edge_scope_lines, *transition_scope_lines, *eave_iws_lines])
    aggregated_by_structure = _aggregate_by_structure(geom, components, confirmed_selection, active_transitions)
    _facet_counts: MutableMapping[str, int] = {}
    for _f in geom.roof_faces.values():
        _facet_counts[(getattr(_f, "structure_id", "") or "")] = _facet_counts.get((getattr(_f, "structure_id", "") or ""), 0) + 1
    structure_facet_counts = tuple(sorted(_facet_counts.items(), key=lambda kv: _struct_sort_key(kv[0])))
    raw_total = sum(comp.iface.affected_SF for comp in components)
    display_total = round(sum(round(comp.iface.affected_SF, 1) for comp in components), 1)
    _repl = tuple(c.label for c in components if c.component_type == "replacement")
    _rep = tuple(c.label for c in components if c.component_type in ("single_valley", "multi_valley"))
    # v69: per-structure exposure for the report's §2 dual and slope callouts. Purely additive — summed
    # from the SAME components already built; no scope number changes. Grouped by the structure each
    # facet belongs to (_structure_of_face), ordered by the ROOF id's trailing integer.
    _aff_by_struct: MutableMapping[str, float] = {}
    _repl_by_struct: MutableMapping[str, List[str]] = {}
    _rep_by_struct: MutableMapping[str, List[str]] = {}
    for c in components:
        sid = _structure_of_face(geom, c.face_id)
        _aff_by_struct[sid] = _aff_by_struct.get(sid, 0.0) + float(c.iface.affected_SF)
        if c.component_type == "replacement":
            _repl_by_struct.setdefault(sid, []).append(c.label)
        elif c.component_type in ("single_valley", "multi_valley"):
            _rep_by_struct.setdefault(sid, []).append(c.label)
    structure_affected_SF = tuple(sorted(_aff_by_struct.items(), key=lambda kv: _struct_sort_key(kv[0])))
    # FRAME v104d (QA Q1 (a)): the same sums, per roof system — the system is the material the engine stamped.
    # The claim-level sum uses sum() exactly as raw_total does (sum() is compensated, a += loop is not: on Killarney the
    # two differ in the last bit); the per-structure sums use += exactly as _aff_by_struct does.
    _aff_by_sys: MutableMapping[str, List[float]] = {}
    _aff_by_struct_sys: MutableMapping[str, MutableMapping[str, float]] = {}
    for c in components:
        _mats = {l.material_profile_id for l in c.scope_lines}
        _sysid = next(iter(_mats)) if len(_mats) == 1 and None not in _mats else ""
        if not _sysid and not float(c.iface.affected_SF):
            continue                                     # no area, no system: contributes nothing either way
        _sid = _structure_of_face(geom, c.face_id)
        _aff_by_sys.setdefault(_sysid, []).append(c.iface.affected_SF)
        _ss = _aff_by_struct_sys.setdefault(_sid, {})
        _ss[_sysid] = _ss.get(_sysid, 0.0) + float(c.iface.affected_SF)
    system_affected_SF = tuple(sorted((k, float(sum(v))) for k, v in _aff_by_sys.items()))
    structure_system_affected_SF = tuple((sid, tuple(sorted(v.items())))
                                         for sid, v in sorted(_aff_by_struct_sys.items(), key=lambda kv: _struct_sort_key(kv[0])))
    replacement_facets_by_structure = tuple((sid, tuple(v)) for sid, v in sorted(_repl_by_struct.items(), key=lambda kv: _struct_sort_key(kv[0])))
    repair_facets_by_structure = tuple((sid, tuple(v)) for sid, v in sorted(_rep_by_struct.items(), key=lambda kv: _struct_sort_key(kv[0])))
    # v63 DEFECT 3: the valley-LF total the header reports must be the SAME authority that bills the
    # metal. VALLEY_METAL is billed from valley_LF_in_scope, which a replaced facet claims for every
    # valley on it; the user-selected LF (selected_valley_lf) ignores replacement, so a full
    # replacement showed 0.00 in the page-2 header while the report billed 39.95. Report the billed
    # VALLEY_METAL quantity instead — identical to the selected LF on a repair-only roof (anchor: both
    # 134.03), correct on a replacement, and it can never disagree with the report line it comes from.
    _valley_lf_billed = round(float(sum(l.qty for l in aggregated if l.category_id == "VALLEY_METAL")), 2)
    # v93: the operation of each TWO-FACET component, from its OWN two facets (Joseph 2026-10-26).
    #   transitions: the candidate's face_a_id / face_b_id (transition_enumerator) — only those billing flashing
    #   valleys:     candidate_emitters.emit_valley_candidates' bordering_roof_face_ids — only valleys whose LF
    #                was claimed into VALLEY_METAL (valley_lf_claimed, the claim-once authority)
    _replaced = replaced_face_ids(confirmed_selection)
    # FRAME v106.4: built ONCE at the top of this function (the boundary test needs it before the claim
    # loops), so the vote reuses it rather than walking emit_valley_candidates a second time.
    two_facet_votes = [
        (_structure_of_face(geom, t.face_a_id), "TRANSITION_FLASH", str(t.edge_id),
         _two_facet_operation((t.face_a_id, t.face_b_id), _replaced))
        for t in _flash_edges]
    for vid in sorted(valley_lf_claimed, key=_id_sort_key):
        if float(geom.valley_lengths.get(vid, 0.0)) <= 0:
            continue
        pair = _valley_pairs.get(vid, ())
        two_facet_votes.append((_structure_of_face(geom, pair[0]) if pair else "", "VALLEY_METAL", vid,
                                _two_facet_operation(pair, _replaced)))
    return RoofAssemblyResult(
        components=tuple(components),
        aggregated_scope=tuple(aggregated),
        affected_SF_raw_total=float(raw_total),
        affected_SF_display_total=float(display_total),
        selected_valley_LF_total=_valley_lf_billed,
        derivation_breakdown=tuple(breakdown),
        deduped_edges=tuple(deduped_edge_contribs),
        edge_scope_lines=edge_scope_lines,
        replacement_facets=_repl,
        repair_facets=_rep,
        aggregated_scope_by_structure=aggregated_by_structure,
        structure_facet_counts=structure_facet_counts,
        structure_affected_SF=structure_affected_SF,
        system_affected_SF=system_affected_SF,
        structure_system_affected_SF=structure_system_affected_SF,
        replacement_facets_by_structure=replacement_facets_by_structure,
        repair_facets_by_structure=repair_facets_by_structure,
        eave_iws=eave_iws_meta,
        two_facet_operations=tuple(two_facet_votes),
        system_boundary_disclosures=tuple(_boundary_disclosures),
        unsupported_operations=tuple(_unsupported),   # FRAME ARC-06a (B1)
        held_operations=tuple(_held),                  # FRAME ARC-06a (E)
    )


def _two_facet_operation(pair, replaced) -> Optional[str]:
    """The operation of a TWO-FACET component (TRANSITION_FLASH, VALLEY_METAL) from its OWN two facets.

    Joseph, 2026-10-26: "If both facets of the transition flashing is being replaced, then the activity code
    would be replace. If one facet of the transition is set for replacement and the other facet set for
    repairs or is not affected, then the flashing would be R&R." / "Valley metal would be the same."
    Both slopes come off -> the metal comes off with them; removal is already in the tear-off -> REPLACE.
    One slope stays -> the metal must be carefully removed from the staying slope -> R&R (remove_existing).
    The test is BOTH FACETS REPLACED, not "neither facet repaired": an untouched facet is R&R exactly as a
    repaired one is. A component without exactly two facets cannot be decided here -> None (unresolved)."""
    pair = tuple(str(f) for f in (pair or ()))
    if len(pair) != 2 or pair[0] == pair[1]:
        return None
    return REPLACE if (pair[0] in replaced and pair[1] in replaced) else R_AND_R


def _component(row: Mapping[str, object], face_id: str, component_type: str, geometry_status: str, surface_status: str, reason: str, iface: M1Interface, edge_contribs: Sequence[EdgeContribution], *, confirmed_selection: Mapping[str, object]) -> ComponentAssembly:
    # FRAME v104b: the component's own facet decides its scope engine (v104a's system_for_facet). A notch's face_id is its
    # members joined ('F21+F22'), which no exception can name, so it takes the predominant / sole system.
    if PROJECT_CONFIG_KEY in (confirmed_selection or {}):
        # FRAME ARC-03a: the opaque material handoff, from THE one resolver — the same call that decides the engine
        # below. Legacy selections leave it None, so their interfaces are exactly what they were.
        from project_config import material_profile_for_facet
        iface = replace(iface, material_profile=material_profile_for_facet(face_id,
                                                                           confirmed_selection[PROJECT_CONFIG_KEY]))
    lines = tuple(roof_system(system_for_facet(face_id, confirmed_selection)).expand_scope(iface, repair_factor=1.0))
    # The steep line leaves expand_scope with no tier on it, so three tiers would merge into one.
    # Stamp the component's own tier here — the single place every component's lines are produced.
    lines = _stamp_steep_tier(lines, iface.facet_pitch_tier)
    return ComponentAssembly(
        label=str(row.get("label", face_id)),
        face_id=face_id,
        component_type=component_type,
        geometry_status=geometry_status,
        surface_status=surface_status,
        reason=reason,
        iface=iface,
        scope_lines=lines,
        edge_contributions=tuple(edge_contribs),
    )


def _breakdown(component: ComponentAssembly) -> Mapping[str, str]:
    return {
        "component": component.label,
        "geometry_status": component.geometry_status,
        "surface_status": component.surface_status,
        "reason": component.reason,
    }


_DIM_MIN_SF = 0.5  # footprint >= 0.5 SF => dimensional (carve); below => point (lay over)

def _polyarea_xy(poly) -> float:
    a = 0.0; n = len(poly)
    for i in range(n):
        x1, y1 = poly[i][0], poly[i][1]
        x2, y2 = poly[(i + 1) % n][0], poly[(i + 1) % n][1]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0

def _dimensional_pens(polys):
    return [p for p in polys if _polyarea_xy(p) >= _DIM_MIN_SF]


_ONE_SHAKE_SF = 1.0 / 2.25

def _filter_subshake_components(mask, gx, gy, threshold_sf: float = _ONE_SHAKE_SF):
    """Drop 4-connected mask components smaller than one replaceable shake."""
    src = np.asarray(mask, dtype=bool)
    out = np.zeros_like(src, dtype=bool)
    if src.size == 0 or len(gx) < 2 or len(gy) < 2:
        return out
    cell = float((gx[1] - gx[0]) * (gy[1] - gy[0]))
    visited = np.zeros_like(src, dtype=bool)
    rows, cols = src.shape
    for r in range(rows):
        for c in range(cols):
            if not src[r, c] or visited[r, c]:
                continue
            stack = [(r, c)]
            visited[r, c] = True
            cells = []
            while stack:
                cr, cc = stack.pop()
                cells.append((cr, cc))
                for nr, nc in ((cr - 1, cc), (cr + 1, cc), (cr, cc - 1), (cr, cc + 1)):
                    if 0 <= nr < rows and 0 <= nc < cols and src[nr, nc] and not visited[nr, nc]:
                        visited[nr, nc] = True
                        stack.append((nr, nc))
            if len(cells) * cell >= threshold_sf:
                for cr, cc in cells:
                    out[cr, cc] = True
    return out

def _confirmed_appurtenance_geometries_for_face(geom: EagleViewGeometry, confirmed_selection: Mapping[str, object], face_id: str):
    """Appurtenance rectangles already confirmed on this facet. Used ONLY to cancel overlap when
    measuring a transition band's incremental area, so nothing is ever counted twice."""
    out = []
    for item in confirmed_selection.get("penetration_appurtenance_repairs", ()) or ():
        row = _as_mapping(item)
        # A NON-CARVING appurtenance (cover-only power vent) disturbs nothing, so it must not cancel
        # any of a transition band's incremental area. Overlap is only subtracted for area that is
        # genuinely already counted elsewhere; a cover-only vent counts none. Same single authority
        # as the carve itself — if it does not carve, it does not cancel.
        if not appurtenance_carves(row):
            continue
        pen_id = str(row.get("penetration_face_id") or row.get("penetration_id") or "")
        if not pen_id:
            continue
        try:
            host = _host_face_for_penetration(geom, pen_id)
        except Exception:
            continue
        if str(host) != str(face_id):
            continue
        try:
            candidate = _penetration_candidate_from_geom(geom, host, pen_id)
            # FRAME v102: this list rebuilds the penetration candidate itself, so it routes it the same way the
            # assembly's penetration loop does — the band must cancel the zone the appurtenance actually claims.
            out.append(dict(appurtenance_zone_geometry(
                candidate.params["appurtenance_geometry"], row.get("kind_label", "CHIMNEY"),
                row.get("other_category"))))   # FRAME v106.6g: routed by TYPE; no clearance here
        except Exception:
            continue
    for row in _user_footprints_for_face(confirmed_selection, face_id) or ():
        if isinstance(row, dict) and {"cx", "cy", "w", "h"} <= set(row):
            out.append(dict(row))
    return out


# ================================ RIDGE VENTS ================================
# A RIDGE VENT IS NOT A REPAIR EVENT. Marking a ridge vented creates NO affected area, NO carve, NO
# shading and NO new repair event. It changes NOTHING about EA, SF, the shake count or the diagram's
# affected zones. It is a MATERIAL ITEM on a ridge run that is ALREADY IN SCOPE: ridge caps only bill
# where the affected area from the user's EXISTING repairs contacts the ridge (contact_LF > 0), and a
# vent only changes WHAT MATERIAL goes on that already-contacted run.
#
# THE TWO TYPES BEHAVE DIFFERENTLY (Joseph — binding):
#   SHINGLE-OVER = an ACCESSORY. The cap shakes lay OVER the vent, so the ridge STILL GETS ITS FULL
#                  CAPS. It ADDS a line and takes nothing away:   RIDGE_VENT = V, RIDGE_CAPS = C.
#   ALUMINUM     = a SUBSTITUTION. It is self-capping, so it REPLACES the caps on its own run:
#                                                                 RIDGE_VENT = V, RIDGE_CAPS = C - V.
# Modelling shingle-over as a substitution would silently DELETE caps the job actually needs.
#
# THE VENTED LF IS A USER INPUT. A vent may cover only part of a ridge, and we do not know WHERE on
# the ridge it sits, so V is defined as "the vent LF being replaced WITHIN THIS REPAIR". That
# sidesteps the positional problem and puts the judgement with the person looking at the roof.
VENT_SHINGLE_OVER = "SHINGLE_OVER"
VENT_ALUMINUM = "ALUMINUM"


def _ridge_vents(confirmed_selection: Mapping[str, object]) -> dict:
    """{edge_id: {"vent_type": ..., "vented_LF": float}} for ridges the user marked vented."""
    out: dict = {}
    for row in (confirmed_selection.get("ridge_vents", ()) or ()):
        if not isinstance(row, Mapping):
            continue
        edge_id = row.get("edge_id")
        vent_type = str(row.get("vent_type") or "").upper()
        try:
            vented = float(row.get("vented_LF") or 0.0)
        except (TypeError, ValueError):
            vented = 0.0
        if not edge_id or vent_type not in (VENT_SHINGLE_OVER, VENT_ALUMINUM) or vented <= 0:
            continue                       # never guess: an incomplete assertion creates nothing
        out[str(edge_id)] = {"vent_type": vent_type, "vented_LF": vented}
    return out


def _edge_lines_with_ridge_vents(contribs, ridge_vents: Mapping[str, Mapping[str, object]]):
    """Edge-driven scope lines, with any user-marked ridge vent applied.

    Expanded PER EDGE (the expander's edge loop already treats every edge independently, so this is
    identical to expanding them together) — which is what lets the caps be adjusted for ONE ridge
    without touching module2_scope_expansion.py at all. Same trick as v51's steep tier.
    """
    out = []
    for contrib in contribs:
        edge = Edge(contrib.edge_type, contrib.contact_LF, contrib.edge_total_LF)
        # FRAME v105.3: the edge's own roof system, stamped on the contribution at its component.
        if not contrib.system_id:
            raise RegistryWiringError(
                f"FRAME: edge {contrib.line_id}'s contribution carries no roof system — it must be stamped where its "
                f"component's face id is in hand (v105.3).")
        lines = list(roof_system(contrib.system_id).expand_scope(M1Interface(edges=[edge]), repair_factor=1.0))
        vent = ridge_vents.get(str(contrib.line_id)) if contrib.edge_type == "RIDGE" else None
        if not vent:
            out.extend(lines)
            continue

        # C = the CONTACTED cap run the engine already computed for THIS ridge.
        cap_line = next((l for l in lines if l.category_id == "RIDGE_CAPS"), None)
        contacted_caps = float(cap_line.qty) if cap_line else 0.0
        if contacted_caps <= 0:
            # No contact -> no caps -> this ridge is not in the repair at all, so it cannot be vented.
            out.extend(lines)
            continue

        # You cannot replace more vent than the ridge you are actually working on.
        vented = min(float(vent["vented_LF"]), contacted_caps)

        for line in lines:
            if line.category_id != "RIDGE_CAPS":
                out.append(line)
                continue
            if vent["vent_type"] == VENT_ALUMINUM:
                remaining = round(max(0.0, contacted_caps - vented), 2)
                if remaining > 0:
                    out.append(replace(line, qty=remaining))
                # V >= C -> the vent covers the whole contacted run: NO caps, and NO zero-qty line.
            else:
                out.append(line)          # SHINGLE-OVER: the caps lay over the vent — unchanged

        label = "Ridge vent (aluminum)" if vent["vent_type"] == VENT_ALUMINUM else "Ridge vent (shingle-over)"
        out.append(ScopeLine(label, "RIDGE_VENT", round(vented, 2), "LF", "CONFIRM",
                             "ventilation; mfr ridge vent"))
    return tuple(out)


# ============================ STEEP & HIGH-SLOPE (labor modifiers) ============================
# BOTH charges were DEAD CODE. module2_scope_expansion could emit them all along, but:
#   * facet_pitch_tier was NEVER computed -> STEEP CHARGE HAS NEVER FIRED, on a roof that is mostly
#     13/12-18/12. Yager has been silently under-scoped.
#   * high_slope_user_flag had NO UI -> HIGH-SLOPE CHARGE HAS NEVER FIRED.
#
# STEEP is pitch: derivable from the XML alone, so it is AUTO — the user confirms nothing.
# HIGH-SLOPE is a HEIGHT charge ("high roof, 2 story" — parser spec §category table). EagleView gives
# roof geometry, NOT wall heights or storey counts; it cannot be derived. It is a per-facet USER
# assertion, and page 2 now forces an explicit decision rather than letting it default to nothing.
STEEP_TIER_79 = "7-9"
STEEP_TIER_1012 = "10-12"
STEEP_TIER_GT12 = ">12"


def _steep_tier_for_pitch(pitch) -> Optional[str]:
    """The steep tier a facet's pitch falls in — read from the geometry, never re-measured.
    Below 7/12 there is no steep charge at all."""
    try:
        p = float(pitch)
    except (TypeError, ValueError):
        return None
    if p >= 13:
        return STEEP_TIER_GT12
    if p >= 10:
        return STEEP_TIER_1012
    if p >= 7:
        return STEEP_TIER_79
    return None


def _facet_pitch_tier(geom: EagleViewGeometry, face_id: str) -> Optional[str]:
    face = geom.faces.get(str(face_id))
    return _steep_tier_for_pitch(getattr(face, "pitch", None)) if face else None


def _high_slope_faces(confirmed_selection: Mapping[str, object]) -> set:
    """Facets the USER asserted are high (2-story). Only the user can know the storey count."""
    out = set()
    for item in (confirmed_selection.get("high_slope_facets", ()) or ()):
        if isinstance(item, Mapping):
            fid = item.get("face_id")
            if fid and item.get("high") is not False:
                out.add(str(fid))
        elif item:
            out.add(str(item))
    return out


def _stamp_steep_tier(lines, tier: Optional[str]):
    """Carry the TIER on the steep line itself, so the three tiers become three lines — exactly as
    carriers write them (spec fixture: STEEP_CHARGE SQ 6.45 (7-9), 55.27 (10-12), 1.40 (>12)).

    Done HERE rather than in module2_scope_expansion so that file stays BYTE-IDENTICAL: the tier is
    stamped onto the existing `xact_code` discriminator, which _aggregate_lines already keys on
    (the v48 chimney-size precedent). Same-tier components therefore MERGE; different tiers SPLIT.
    """
    if not tier:
        return lines
    out = []
    for line in lines:
        if line.category_id == "STEEP_CHARGE":
            out.append(replace(line, item=f"Steep charge ({tier})", xact_code=f"STEEP_{tier}"))
        else:
            out.append(line)
    return tuple(out)


def _transition_bands_for(confirmed_selection: Mapping[str, object], face_id: str):
    """Bands a user-confirmed transition carves on this facet. Empty when none is selected, so
    every existing call is bit-for-bit unchanged. Passing them INTO the same affected_area call as
    the valley events is what makes the zones UNION rather than sum."""
    cache = confirmed_selection.get("_transition_bands_by_face") if isinstance(confirmed_selection, dict) else None
    if not cache:
        return []
    return engine_bands(cache.get(face_id) or [])


def _encoding_b_candidate(geom: EagleViewGeometry, face_id: str) -> Optional[Candidate]:
    """The Encoding-B reframing candidate for a face with a self-bounding HIDDEN line, or None.

    Built on demand via the emitter's single authority. It is NOT one of the page-2 selectable notch
    candidates (those are Encoding A, two-face merges); it exists only to reframe this face's own valley
    sweep so the slit stops acting as a barrier. Yager has no self-bounding hidden line, so this is None
    for every Yager face — the anchor can never take the reframing branch."""
    return _emit_encoding_b_candidate(geom, str(face_id))


def _encoding_b_reframed_area(geom: EagleViewGeometry, b_cand: Candidate, valley_ids: Sequence[str], confirmed_selection: Mapping[str, object], shake_measurements) -> float:
    """Reframed affected area for an Encoding-B face's valleys, through the SAME ridge-anchored notch
    machinery Encoding A uses (one authority). Only the AREA is taken from the notch builder; the
    component's interface (pitch tier, edges, transitions) is still built by the plain path, so nothing
    face-level is lost. A throwaway `claimed` set and empty selected_valley_ids mean this call never
    claims valley LF — that is claimed once on the plain path."""
    iface, _edge_contribs = _build_m1_interface_for_notch(
        geom, b_cand, [], set(), "encoding_b_area",
        confirmed_selection=confirmed_selection, override_valley_ids=list(valley_ids),
        shake_measurements=shake_measurements)
    return float(iface.affected_SF)


def _single_valley_area(geom: EagleViewGeometry, face_id: str, valley_id: str, confirmed_selection: Mapping[str, object]) -> float:
    shake_measurements = _facet_geometry_profile(face_id, confirmed_selection)   # FRAME ARC-06a (B1): the facet's own
    b_cand = _encoding_b_candidate(geom, face_id)
    if b_cand is not None and not _transition_bands_for(confirmed_selection, face_id):
        # ENCODING B (v65): self-bounding HIDDEN line (slit around a lobe). Reframe the valley sweep so
        # the slit stops barriering the lobe-side zones. A face with a user-confirmed transition keeps
        # the plain path (its band is unioned in the face's own frame there, and the slit barely moves
        # the sweep on such a face).
        return _encoding_b_reframed_area(geom, b_cand, [valley_id], confirmed_selection, shake_measurements)
    engine_face = geom.engine_facet(face_id)
    valley_event = geom.valley_event_for_face(face_id, valley_id)
    _per_event, area = affected_area(engine_face.facet, [valley_event], penetrations=_penetrations_with_user_footprints(geom, confirmed_selection, face_id), shake_measurements=shake_measurements, transition_bands=_transition_bands_for(confirmed_selection, face_id))
    return float(area)


def _multi_valley_union_area(geom: EagleViewGeometry, face_id: str, valley_ids: Sequence[str], confirmed_selection: Mapping[str, object], include_child_penetrations: bool = True) -> float:
    shake_measurements = _facet_geometry_profile(face_id, confirmed_selection)   # FRAME ARC-06a (B1): the facet's own
    b_cand = _encoding_b_candidate(geom, face_id)
    if b_cand is not None and not _transition_bands_for(confirmed_selection, face_id):
        return _encoding_b_reframed_area(geom, b_cand, list(valley_ids), confirmed_selection, shake_measurements)
    engine_face = geom.engine_facet(face_id)
    valley_events = [geom.valley_event_for_face(face_id, valley_id) for valley_id in valley_ids]
    # uniform clipped exclusion: dimensional XML penetrations plus confirmed user dimensioned footprint holes
    _per_event, area = affected_area(engine_face.facet, valley_events, penetrations=_penetrations_with_user_footprints(geom, confirmed_selection, face_id), shake_measurements=shake_measurements, transition_bands=_transition_bands_for(confirmed_selection, face_id))
    return float(area)


def _notch_reframe_geometry(geom: EagleViewGeometry, candidate: Candidate, confirmed_selection: Mapping[str, object] | None, override_valley_ids=None):
    """The merged-facet reframing geometry for a notch/Encoding-B candidate: the ridge-anchored frame,
    the merged facet, the lobe notches, the reframed valley events, and the dimensional penetrations.
    ONE authority — `_build_m1_interface_for_notch` (which the SCOPE bills) and `encoding_b_zone` (which
    the DIAGRAM draws) both build their geometry here, so the picture can never disagree with the math."""
    anchor_line = geom.lines[str(candidate.params["anchor_line_id"])]
    frame_ids = tuple(str(pid) for pid in candidate.params["frame_point_ids"])
    frame = mkframe_pts(
        [geom.points[pid] for pid in frame_ids],
        geom.points[anchor_line.path[0]],
        geom.points[anchor_line.path[-1]],
    )
    facet = [tuple(float(v) for v in frame(geom.points[str(pid)])) for pid in candidate.params["merged_facet_point_ids"]]
    notches = [
        [tuple(float(v) for v in frame(geom.points[str(pid)])) for pid in notch_ids]
        for notch_ids in candidate.params["notch_polygon_point_ids"]
    ]
    valley_ids = tuple(str(v) for v in (override_valley_ids if override_valley_ids else candidate.params["bordering_valley_line_ids"]))
    valley_events = [_valley_event_for_notch(geom, candidate, frame, facet, valley_id) for valley_id in valley_ids]
    _notch_pens = []
    for _mfid in candidate.params["member_face_ids"]:
        for _pf in geom.penetration_faces.values():
            if getattr(_pf, "size", 0) > 0 and _host_face_for_penetration(geom, _pf.id) == str(_mfid):
                _poly = []
                for _lid in _pf.line_ids:
                    for _pid in geom.lines[_lid].path:
                        if _pid not in _poly: _poly.append(_pid)
                _notch_pens.append([tuple(float(v) for v in frame(geom.points[str(_pid)])) for _pid in _poly])
    _notch_pens.extend(_user_footprints_for_merged_members(geom, confirmed_selection or {}, candidate.params["member_face_ids"], frame))
    return frame, facet, notches, valley_ids, valley_events, _dimensional_pens(_notch_pens)


def encoding_b_zone(geom: EagleViewGeometry, face_id: str, valley_ids, confirmed_selection: Mapping[str, object] | None = None, shake_measurements=None):
    """Reframed ZONE for an Encoding-B face, from the SAME authority the scope bills. Returns
    (affected_SF, zone_mask, gx, gy, merged_facet) so the diagram can draw exactly what the scope
    counted. Returns None when the face is not Encoding-B (no self-bounding hidden line). Do NOT
    reimplement the reframing anywhere else — call this."""
    b_cand = _encoding_b_candidate(geom, str(face_id))
    if b_cand is None or _transition_bands_for(confirmed_selection or {}, str(face_id)):
        # Not Encoding-B, or a face carrying a transition (which the SCOPE keeps on the plain path) —
        # the same gate _single_valley_area/_multi_valley_union_area use, so the diagram never reframes
        # a facet the scope did not.
        return None
    vids = [str(v) for v in valley_ids] if valley_ids else None
    _frame, facet, notches, _vidt, valley_events, pens = _notch_reframe_geometry(geom, b_cand, confirmed_selection, override_valley_ids=vids)
    _per, affected, zone, gx, gy = affected_area(facet, valley_events, notches=notches, penetrations=pens, shake_measurements=shake_measurements, return_zone=True)
    return float(affected), zone, gx, gy, facet


def _build_m1_interface_for_notch(geom: EagleViewGeometry, candidate: Candidate, selected_valley_ids: Sequence[str], claimed: set[str], label: str, confirmed_selection: Mapping[str, object] | None = None, override_valley_ids=None, shake_measurements=None, boundary_valleys: frozenset = frozenset(), geometry_profile=None) -> Tuple[M1Interface, Tuple[EdgeContribution, ...]]:
    # FRAME ARC-06a (B1): the GEOMETRY runs with the merged members' own profile (geometry_profile); the interface
    # keeps the claim-level profile for the scope (measured_profile), exactly as before. None = the old single profile.
    _geo = shake_measurements if geometry_profile is None else geometry_profile
    frame, facet, notches, valley_ids, valley_events, pens = _notch_reframe_geometry(geom, candidate, confirmed_selection, override_valley_ids=override_valley_ids)
    _per_event, affected = affected_area(facet, valley_events, notches=notches, penetrations=pens, shake_measurements=_geo)
    edge_tuples_with_ids = _notch_outer_edge_tuples_with_ids(geom, candidate, frame)
    edge_tuples = [(a, b, edge_type, total_lf) for _line_id, a, b, edge_type, total_lf in edge_tuples_with_ids]
    edges, edge_contribs = _surface_physical_edges(facet, valley_events, edge_tuples_with_ids, label, _geo)
    valley_lf = sum(_claim_valley_lf_once(geom, valley_id, selected_valley_ids, claimed, boundary_valleys)
                    for valley_id in valley_ids)
    return M1Interface(affected_SF=float(affected), valley_LF_in_scope=float(valley_lf), edges=edges, appurts=[], transitions=[], measured_profile=shake_measurements), tuple(edge_contribs)


def _notch_outer_edge_tuples_with_ids(geom: EagleViewGeometry, candidate: Candidate, frame) -> List[Tuple[str, Tuple[float, float], Tuple[float, float], str, float]]:
    line_by_edge = {_edge_key(line.path[0], line.path[-1]): (line_id, line) for line_id, line in geom.lines.items()}
    ids = tuple(str(pid) for pid in candidate.params["merged_facet_point_ids"])
    out = []
    for a_id, b_id in zip(ids, list(ids[1:]) + [ids[0]]):
        line_id, line = line_by_edge[_edge_key(a_id, b_id)]
        out.append((
            line_id,
            tuple(float(v) for v in frame(geom.points[a_id])),
            tuple(float(v) for v in frame(geom.points[b_id])),
            line.type,
            _length_3d([geom.points[p] for p in line.path]),
        ))
    return out


def _valley_event_for_notch(geom: EagleViewGeometry, candidate: Candidate, frame, facet, line_id: str):
    line = geom.lines[line_id]
    a_id, b_id = line.path[0], line.path[-1]
    apex_id, start_id = (a_id, b_id) if geom.points[a_id][2] >= geom.points[b_id][2] else (b_id, a_id)
    start = np.array(frame(geom.points[start_id]), dtype=float)
    apex = np.array(frame(geom.points[apex_id]), dtype=float)
    fan = _notch_valley_fan(geom, candidate, frame, facet, line_id)
    return (tuple(float(v) for v in start), tuple(float(v) for v in apex), int(fan))


def _notch_valley_fan(geom: EagleViewGeometry, candidate: Candidate, frame, facet, line_id: str) -> int:
    from geometry_core import excluded_region_aware_notch_fan
    line = geom.lines[line_id]
    seg_a = tuple(float(v) for v in frame(geom.points[line.path[0]])[:2])
    seg_b = tuple(float(v) for v in frame(geom.points[line.path[-1]])[:2])
    holes = [[tuple(float(v) for v in frame(geom.points[pid])[:2]) for pid in poly]
             for poly in candidate.params["notch_polygon_point_ids"]]
    return excluded_region_aware_notch_fan(facet, holes, seg_a, seg_b)


def _face_edge_contributions(geom: EagleViewGeometry, face_id: str, valley_ids: Sequence[str], label: str, shake_measurements=None) -> Tuple[EdgeContribution, ...]:
    engine_face = geom.engine_facet(face_id)
    valley_events = [geom.valley_event_for_face(face_id, valley_id) for valley_id in valley_ids]
    tuples_with_ids = []
    for line_id, edge in zip(geom.faces[face_id].line_ids, engine_face.edges):
        a, b, edge_type, total_lf = edge
        tuples_with_ids.append((line_id, a, b, edge_type, total_lf))
    _edges, contribs = _surface_physical_edges(engine_face.facet, valley_events, tuples_with_ids, label, shake_measurements)
    return tuple(contribs)


def _surface_physical_edges(facet, valley_events, edge_tuples_with_ids, label: str, shake_measurements=None) -> Tuple[List[Edge], List[EdgeContribution]]:
    edges: List[Edge] = []
    contribs: List[EdgeContribution] = []
    for line_id, a, b, edge_type, total_lf in edge_tuples_with_ids:
        if edge_type == "VALLEY":
            continue
        single_edge = [(a, b, edge_type, total_lf)]
        contacts = edge_contacts(facet, valley_events, single_edge, res=0.04, shake_measurements=shake_measurements) if valley_events else {}
        contact_lf = float(contacts.get(edge_type, (0.0, total_lf))[0])
        total = float(contacts.get(edge_type, (contact_lf, total_lf))[1])
        edges.append(Edge(edge_type, contact_lf, total))
        contribs.append(EdgeContribution(str(line_id), str(edge_type), contact_lf, total, label))
    return edges, contribs


def _facet_valley_ids(geom: EagleViewGeometry, face_id: str) -> Tuple[str, ...]:
    """Every VALLEY line bordering this facet (line ids) — for full-slope replacement."""
    return tuple(lid for lid in geom.faces[face_id].line_ids
                 if lid in geom.lines and geom.lines[lid].type.upper() == "VALLEY")


def _claim_replacement_valley_lf(geom: EagleViewGeometry, valley_id: str, claimed: set,
                                 boundary_valleys: frozenset = frozenset()) -> float:
    """The WHOLE valley on a replaced facet's perimeter is in scope (you cannot replace half a
    W-metal), independent of the user's selected_valley_ids — but claimed ONCE, deduped against any
    adjoining facet (repair or replacement) that also claims it, exactly like _claim_valley_lf_once.

    FRAME v106.4: and a SYSTEM BOUNDARY valley is claimed by NEITHER side (_system_boundary_valley_ids).
    Which side claimed first used to decide whether a boundary valley was billed at all, because one
    system's engine bills from valley_LF_in_scope and the other's does not read it."""
    if valley_id in boundary_valleys:
        return 0.0
    if valley_id in claimed or valley_id not in geom.valley_lengths:
        return 0.0
    claimed.add(valley_id)
    return float(geom.valley_lengths[valley_id])


def _replacement_facet_area(geom: EagleViewGeometry, face_id: str) -> float:
    """Whole facet, net of penetrations >= 0.5 SF. The facet's surface area is EagleView's own
    unrounded_size (equal to the facet polygon area); penetrations are the same holes every carved
    zone excludes, subtracted here so a stripped slope is NET area — consistent with every other zone
    and with the roof-area convention the diagram uses. NO waste factor is added (rule 8)."""
    face = geom.roof_faces[face_id]
    gross = float(face.unrounded_size if face.unrounded_size is not None else (face.size or 0.0))
    engine_face = geom.engine_facet(face_id)

    def _poly_area(q):
        n = len(q)
        return abs(sum(q[i][0] * q[(i + 1) % n][1] - q[(i + 1) % n][0] * q[i][1] for i in range(n))) / 2.0

    pen = sum(_poly_area(p) for p in engine_face.penetrations if _poly_area(p) >= 0.5)
    return max(gross - pen, 0.0)


def _replacement_edge_contributions(geom: EagleViewGeometry, face_id: str, label: str) -> Tuple[EdgeContribution, ...]:
    """A stripped facet contacts its WHOLE perimeter, so every non-valley edge bills at 100% contact
    through the SAME edge machinery (ridge/hip/starter/step/drip + the §6 95% run + shared-run
    dedupe). Valley edges are excluded here — VALLEY_METAL/IWS bill from valley_LF_in_scope, never
    from edge contact. This writes no new perimeter rule; it feeds the existing one the physical
    truth for a full replacement (100% contact)."""
    engine_face = geom.engine_facet(face_id)
    contribs: List[EdgeContribution] = []
    for line_id, edge in zip(geom.faces[face_id].line_ids, engine_face.edges):
        _a, _b, edge_type, total_lf = edge
        if str(edge_type).upper() == "VALLEY":
            continue
        contribs.append(EdgeContribution(str(line_id), str(edge_type), float(total_lf), float(total_lf), label))
    return tuple(contribs)


def _dedupe_edge_contributions(contribs: Sequence[EdgeContribution]) -> Tuple[EdgeContribution, ...]:
    by_line: Dict[str, EdgeContribution] = {}
    for contrib in contribs:
        prior = by_line.get(contrib.line_id)
        if prior is None:
            by_line[contrib.line_id] = contrib
            continue
        # FRAME v105.3: two facets contributing ONE edge must carry ONE roof system. If they differ, the edge is a SYSTEM
        # BOUNDARY — what it bills is each system's own termination (Joseph, 2026-11-01), which core will not guess.
        if prior.system_id != contrib.system_id:
            raise RegistryWiringError(
                f"FRAME: edge {contrib.line_id} is shared by facets carrying DIFFERENT roof systems "
                f"({' / '.join(sorted((prior.system_id, contrib.system_id)))}). That edge is a SYSTEM BOUNDARY: what it "
                f"bills is each system's own termination, which core will not guess. (v105.3)")
        by_line[contrib.line_id] = EdgeContribution(
            line_id=contrib.line_id,
            edge_type=prior.edge_type,
            contact_LF=max(prior.contact_LF, contrib.contact_LF),
            edge_total_LF=max(prior.edge_total_LF, contrib.edge_total_LF),
            component=";".join(sorted(set(prior.component.split(";") + contrib.component.split(";")))),
            system_id=prior.system_id,
        )
    return tuple(sorted(by_line.values(), key=lambda c: _id_sort_key(c.line_id)))



def _appurtenance_union_affected_area(geom, host_face_id, candidate, confirmed_selection, carves, replaced_ids, repair_facet_ids):
    """The appurtenance's affected AREA under the union-not-sum rule (v56 transitions, v62 replacement).

    A cover that does not carve contributes 0. On a REPLACED facet the whole facet is already 100%
    scoped, so the footprint is UNIONED in and adds NO area (0) and NO shakes — exactly like a
    transition band unioned into a valley zone. Crucially this zeros only `iface.affected_SF` (the
    shake/felt driver); the Appurt's OWN affected_SF (built from the candidate) still drives APPURT_IWS
    and the material line, so a box vent on a stripped slope still bills its vent and its deck-level
    IWS. On a repair facet only the increment beyond the repair zone counts; otherwise the full
    footprint counts."""
    if not carves:
        return 0.0
    if host_face_id in replaced_ids:
        return 0.0
    if host_face_id in repair_facet_ids:
        return _appurtenance_net_affected_area(geom, host_face_id, candidate, confirmed_selection)[0]
    return _appurtenance_affected_area(geom, host_face_id, candidate, confirmed_selection)[0]


def _appurtenance_net_affected_area(geom: EagleViewGeometry, host_face_id: str, candidate: Candidate, confirmed_selection: Mapping[str, object]):
    shake_measurements = _facet_geometry_profile(host_face_id, confirmed_selection)   # FRAME ARC-06a (B1)
    merged_candidate = _merged_candidate_for_member_face(geom, host_face_id)
    if merged_candidate is not None:
        return _merged_appurtenance_net_affected_area(geom, merged_candidate, candidate, confirmed_selection)

    engine_face = geom.engine_facet(host_face_id)
    repair_events = []
    for item in confirmed_selection.get("single_valley_repairs", ()):
        row = _as_mapping(item)
        if str(row["face_id"]) == host_face_id:
            repair_events.append(geom.valley_event_for_face(host_face_id, str(row["valley_id"])))
    for item in confirmed_selection.get("multi_valley_facets", ()):
        row = _as_mapping(item)
        if str(row["face_id"]) == host_face_id:
            repair_events.extend(geom.valley_event_for_face(host_face_id, str(v)) for v in row.get("valley_ids", ()))

    _per_app, _app_area, app_zone, gx, gy = affected_area(
        engine_face.facet,
        [],
        appurtenances=[dict(candidate.params["appurtenance_geometry"])],
        facet_system_id=system_for_facet(host_face_id, confirmed_selection or {}),   # FRAME v106.6c
        penetrations=appurtenance_zone_holes(candidate.params["appurtenance_geometry"], _penetrations_with_user_footprints(geom, confirmed_selection, host_face_id)),  # FRAME v103: a point zone is not carved by its own hole
        return_zone=True,
        shake_measurements=shake_measurements,
    )
    if not repair_events:
        return float(_app_area), app_zone, gx, gy, host_face_id
    _per_repair, _repair_area, repair_zone, _gx, _gy = affected_area(
        engine_face.facet,
        repair_events,
        penetrations=_penetrations_with_user_footprints(geom, confirmed_selection, host_face_id),
        return_zone=True,
        shake_measurements=shake_measurements,
    )
    cell = float((gx[1] - gx[0]) * (gy[1] - gy[0]))
    net_zone = (np.asarray(app_zone, bool) & ~np.asarray(repair_zone, bool))
    net_zone = _filter_subshake_components(net_zone, gx, gy)
    return float(net_zone.sum() * cell), net_zone, gx, gy, host_face_id


def _merged_appurtenance_net_affected_area(geom: EagleViewGeometry, notch_candidate: Candidate, appurtenance_candidate: Candidate, confirmed_selection: Mapping[str, object]):
    shake_measurements = _members_geometry_profile(notch_candidate.params["member_face_ids"], confirmed_selection,
                                                   "an appurtenance carve on a merged slope")   # FRAME ARC-06a (B1)
    anchor_line = geom.lines[str(notch_candidate.params["anchor_line_id"])]
    frame_ids = tuple(str(pid) for pid in notch_candidate.params["frame_point_ids"])
    frame = mkframe_pts(
        [geom.points[pid] for pid in frame_ids],
        geom.points[anchor_line.path[0]],
        geom.points[anchor_line.path[-1]],
    )
    facet = [tuple(float(v) for v in frame(geom.points[str(pid)])) for pid in notch_candidate.params["merged_facet_point_ids"]]
    notches = [
        [tuple(float(v) for v in frame(geom.points[str(pid)])) for pid in notch_ids]
        for notch_ids in notch_candidate.params["notch_polygon_point_ids"]
    ]
    pens = []
    for member_face_id in notch_candidate.params["member_face_ids"]:
        member_face = geom.faces.get(str(member_face_id))
        for child_id in (member_face.children if member_face else []):
            pen_face = geom.penetration_faces.get(child_id)
            if pen_face is not None and getattr(pen_face, "size", 0) > 0:
                pens.append([tuple(float(v) for v in frame(geom.points[pid])) for pid in geom.ordered_face_point_ids(child_id)])
    pens.extend(_user_footprints_for_merged_members(geom, confirmed_selection, notch_candidate.params["member_face_ids"], frame))
    holes = _dimensional_pens(pens)
    app = _candidate_appurtenance_geometry_in_frame(geom, appurtenance_candidate, frame)
    _per_app, _app_area, app_zone, gx, gy = affected_area(
        facet, [], notches=notches, appurtenances=[app], penetrations=appurtenance_zone_holes(app, holes), return_zone=True,  # FRAME v103
        facet_system_id=system_for_facets(notch_candidate.params["member_face_ids"], confirmed_selection or {},
                                          "an appurtenance carve on a merged slope"),   # FRAME v106.6c: a point zone is not carved by its own hole
        shake_measurements=shake_measurements
    )

    member_set = {str(v) for v in notch_candidate.params.get("member_face_ids", ())}
    repair_masks = []
    for item in confirmed_selection.get("notch_repairs", ()):
        row = _as_mapping(item)
        if {str(v) for v in row.get("member_face_ids", ())} == member_set:
            valley_ids = tuple(str(v) for v in row.get("valley_ids", notch_candidate.params["bordering_valley_line_ids"]))
            valley_events = [_valley_event_for_notch(geom, notch_candidate, frame, facet, valley_id) for valley_id in valley_ids]
            _per_r, _area_r, z_r, _gx, _gy = affected_area(
                facet, valley_events, notches=notches, penetrations=holes, return_zone=True,
                shake_measurements=shake_measurements
            )
            repair_masks.append(np.asarray(z_r, bool))
    if not repair_masks:
        return float(_app_area), app_zone, gx, gy, "+".join(str(v) for v in notch_candidate.params["member_face_ids"])
    repair_union = np.logical_or.reduce(repair_masks)
    cell = float((gx[1] - gx[0]) * (gy[1] - gy[0]))
    net_zone = (np.asarray(app_zone, bool) & ~repair_union)
    net_zone = _filter_subshake_components(net_zone, gx, gy)
    return float(net_zone.sum() * cell), net_zone, gx, gy, "+".join(str(v) for v in notch_candidate.params["member_face_ids"])

def _appurtenance_affected_area(geom: EagleViewGeometry, host_face_id: str, candidate: Candidate, confirmed_selection: Mapping[str, object] | None = None):
    shake_measurements = _facet_geometry_profile(host_face_id, confirmed_selection or {})   # FRAME ARC-06a (B1)
    merged_candidate = _merged_candidate_for_member_face(geom, host_face_id)
    if merged_candidate is not None:
        return _merged_appurtenance_affected_area(geom, merged_candidate, candidate, confirmed_selection or {})

    engine_face = geom.engine_facet(host_face_id)
    _per_event, area, zone, gx, gy = affected_area(
        engine_face.facet,
        [],
        appurtenances=[dict(candidate.params["appurtenance_geometry"])],
        facet_system_id=system_for_facet(host_face_id, confirmed_selection or {}),   # FRAME v106.6c
        penetrations=appurtenance_zone_holes(candidate.params["appurtenance_geometry"], _penetrations_with_user_footprints(geom, confirmed_selection or {}, host_face_id)),  # FRAME v103: a point zone is not carved by its own hole
        return_zone=True,
        shake_measurements=shake_measurements,
    )
    return float(area), zone, gx, gy, host_face_id


def _merged_candidate_for_member_face(geom: EagleViewGeometry, face_id: str) -> Candidate | None:
    for candidate in emit_notch_candidates(geom):
        if str(face_id) in {str(v) for v in candidate.params.get("member_face_ids", ())}:
            return candidate
    return None


def _merged_appurtenance_affected_area(geom: EagleViewGeometry, notch_candidate: Candidate, appurtenance_candidate: Candidate, confirmed_selection: Mapping[str, object] | None = None):
    shake_measurements = _members_geometry_profile(notch_candidate.params["member_face_ids"], confirmed_selection,
                                                   "an appurtenance carve on a merged slope")   # FRAME ARC-06a (B1)
    anchor_line = geom.lines[str(notch_candidate.params["anchor_line_id"])]
    frame_ids = tuple(str(pid) for pid in notch_candidate.params["frame_point_ids"])
    frame = mkframe_pts(
        [geom.points[pid] for pid in frame_ids],
        geom.points[anchor_line.path[0]],
        geom.points[anchor_line.path[-1]],
    )
    facet = [tuple(float(v) for v in frame(geom.points[str(pid)])) for pid in notch_candidate.params["merged_facet_point_ids"]]
    notches = [
        [tuple(float(v) for v in frame(geom.points[str(pid)])) for pid in notch_ids]
        for notch_ids in notch_candidate.params["notch_polygon_point_ids"]
    ]
    pens = []
    for member_face_id in notch_candidate.params["member_face_ids"]:
        member_face = geom.faces.get(str(member_face_id))
        for child_id in (member_face.children if member_face else []):
            pen_face = geom.penetration_faces.get(child_id)
            if pen_face is not None and getattr(pen_face, "size", 0) > 0:
                pens.append([tuple(float(v) for v in frame(geom.points[pid])) for pid in geom.ordered_face_point_ids(child_id)])
    pens.extend(_user_footprints_for_merged_members(geom, confirmed_selection or {}, notch_candidate.params["member_face_ids"], frame))
    app = _candidate_appurtenance_geometry_in_frame(geom, appurtenance_candidate, frame)
    _per_event, area, zone, gx, gy = affected_area(
        facet,
        [],
        notches=notches,
        appurtenances=[app],
        facet_system_id=system_for_facets(notch_candidate.params["member_face_ids"], confirmed_selection or {},
                                          "an appurtenance carve on a merged slope"),   # FRAME v106.6c
        penetrations=appurtenance_zone_holes(app, _dimensional_pens(pens)),  # FRAME v103: a point zone is not carved by its own hole
        return_zone=True,
        shake_measurements=shake_measurements,
    )
    return float(area), zone, gx, gy, "+".join(str(v) for v in notch_candidate.params["member_face_ids"])


def _penetrations_with_user_footprints(geom: EagleViewGeometry, confirmed_selection: Mapping[str, object], face_id: str):
    """Return XML dimensional penetrations plus confirmed user dimensioned footprint holes in facet-local frame."""
    engine_face = geom.engine_facet(str(face_id))
    pens = list(_dimensional_pens(engine_face.penetrations))
    pens.extend(_user_footprints_for_face(confirmed_selection, str(face_id)))
    return _dimensional_pens(pens)


def _user_footprints_for_face(confirmed_selection: Mapping[str, object], face_id: str):
    out = []
    for item in confirmed_selection.get("user_appurtenance_repairs", ()):  # type: ignore[union-attr]
        row = _as_mapping(item)
        if str(row.get("host_facet_id")) != str(face_id):
            continue
        poly = _user_footprint_polygon_local(row)
        if poly is not None:
            out.append(poly)
    return out


def _user_footprints_for_merged_members(geom: EagleViewGeometry, confirmed_selection: Mapping[str, object], member_face_ids, frame):
    member_set = {str(v) for v in member_face_ids}
    out = []
    for item in confirmed_selection.get("user_appurtenance_repairs", ()):  # type: ignore[union-attr]
        row = _as_mapping(item)
        host_face_id = str(row.get("host_facet_id"))
        if host_face_id not in member_set:
            continue
        poly = _user_footprint_polygon_local(row)
        if poly is None:
            continue
        transformed = []
        for x, y in poly:
            pt3 = _face_local_point_to_3d(geom, host_face_id, float(x), float(y))
            transformed.append(tuple(float(v) for v in frame(pt3)))
        out.append(transformed)
    return out


def _user_footprint_polygon_local(row: Mapping[str, object]):
    """Raw dimensioned user footprint (not the 21in band) as a facet-local hole polygon."""
    shape = str(row.get("shape") or row.get("appurtenance_shape") or "point").lower()
    if shape != "dimensioned":
        return None
    position = row.get("position")
    if not isinstance(position, Mapping):
        return None
    try:
        cx = float(position["x"]); cy = float(position["y"])
        w = float(row.get("width", 0.0)); h = float(row.get("height", 0.0))
    except (TypeError, ValueError, KeyError):
        return None
    if not (w > 0 and h > 0 and w * h >= _DIM_MIN_SF):
        return None
    hw = w / 2.0; hh = h / 2.0
    return [(cx - hw, cy - hh), (cx + hw, cy - hh), (cx + hw, cy + hh), (cx - hw, cy + hh)]


def _user_appurtenance_candidate_from_row(row: Mapping[str, object],
                                          confirmed_selection: Mapping[str, object] | None = None) -> Candidate:
    # FRAME v106.6c: the selection is needed to route this row's zone by the HOST FACET's covering.
    # It defaults to None so the signature stays additive, and None resolves exactly as before:
    # system_for_facet falls through to the predominant system, then to the sole registered one.
    host_face_id = str(row["host_facet_id"])
    position = row.get("position")
    if not isinstance(position, Mapping):
        raise ValueError("user appurtenance requires position {x, y}")
    x = float(position["x"])
    y = float(position["y"])
    shape = str(row.get("shape") or row.get("appurtenance_shape") or "point").lower()
    if shape == "dimensioned":
        w = float(row.get("width", 0.0))
        h = float(row.get("height", 0.0))
        if not (w > 0 and h > 0):
            raise ValueError("dimensioned user appurtenance requires positive width and height")
        app_geom = {"cx": x, "cy": y, "w": w, "h": h, "kind": "dimensioned"}
    elif shape == "point":
        app_geom = {"cx": x, "cy": y, "kind": "point"}
    else:
        raise ValueError(f"unknown user appurtenance shape {shape!r}")
    return Candidate(
        kind="appurtenance",
        source_ids=(str(row.get("designator") or row.get("label") or "user"),),
        origin="user",
        confirmed=False,
        params={
            "host_facet_id": host_face_id,
            "position": {"x": x, "y": y},
            "width": app_geom.get("w"),
            "height": app_geom.get("h"),
            "appurtenance_shape": shape,
            # FRAME v102/v106.6g: the TYPE decides the zone, by its FLASHING METHOD and by nothing else.
            # A base-flashed type becomes a point carrying its own STANDARD FLASHING BASE, to which the
            # package adds its base allowance - not the 21" curb zone an earlier comment here named, and not
            # the declared shape. Everything else keeps app_geom exactly as built above (geometry_core).
            # The row's other_category is passed because a row saying OTHER names its real thing there, and
            # some categories (VENT_CAP) are reachable ONLY that way.
            "appurtenance_geometry": appurtenance_zone_geometry(
                app_geom, row.get("kind_label") or "OTHER",
                row.get("other_category")),   # FRAME v106.6g: routed by TYPE; no clearance resolved here
            "kind_label": str(row.get("kind_label") or "OTHER"),
            "designator": str(row.get("designator") or row.get("label") or "user"),
        },
    )


def _candidate_appurtenance_geometry_in_frame(geom: EagleViewGeometry, candidate: Candidate, frame) -> Mapping[str, float | str]:
    params = candidate.params
    if params.get("penetration_face_id"):
        # A merged plane re-measures the penetration in its own frame (always "dimensioned"). FRAME v102: the
        # candidate's geometry was routed BY TYPE where it was built, so a point-routed penetration keeps the
        # point zone here too — the type decides, never this re-measurement.
        app = _appurtenance_geometry_in_frame(geom, str(params["penetration_face_id"]), frame)
        # FRAME v106.6g: `app` here is a FRESH re-measurement of the penetration face, not the routed
        # candidate geometry, so spreading it carries none of the routing. The TYPE's standard flashing base
        # has to be taken from the routed geometry explicitly. QA swept for this pattern, saw this line, and
        # judged it safe because it spreads a dict - the dict it spreads is the wrong one. Yager's F71 on the
        # merged plane read 3.0976 SF, the bare clearance square, until this carried the base.
        _routed = params.get("appurtenance_geometry") or {}
        if _routed.get("kind") == "point":
            _out = {**app, "kind": "point"}
            if _routed.get("standard_base_in") is not None:
                _out["standard_base_in"] = float(_routed["standard_base_in"])
            return _out
        return app
    app = params.get("appurtenance_geometry")
    if not isinstance(app, Mapping):
        raise ValueError("appurtenance candidate missing appurtenance_geometry")
    host_face_id = str(params["host_facet_id"])
    center = _face_local_point_to_3d(geom, host_face_id, float(app["cx"]), float(app["cy"]))
    cx, cy = (float(v) for v in frame(center))
    if app.get("kind") == "point":
        # FRAME v106.6g: the TYPE's standard flashing base travels with the zone, so it must survive being
        # rebuilt in a facet frame. Dropping it silently reverts a merged-plane vent to the bare clearance
        # square - Yager's F71 read 3.0976 SF instead of 3.3856 until this line carried it. Same shape as
        # v106.6d's shared_edge_ft carry-through: a reader that reconstructs a record loses every field it
        # does not name.
        _out = {"cx": cx, "cy": cy, "kind": "point"}
        if app.get("standard_base_in") is not None:
            _out["standard_base_in"] = float(app["standard_base_in"])
        return _out
    return {"cx": cx, "cy": cy, "w": float(app["w"]), "h": float(app["h"]), "kind": "dimensioned"}


def _face_local_point_to_3d(geom: EagleViewGeometry, face_id: str, x_local: float, y_local: float):
    face = geom.faces[str(face_id)]
    point_ids = geom.ordered_face_point_ids(str(face_id))
    # FRAME v105.2: THE ONE anchor rule (eave, else ridge, else the first edge) — the rule every producer of
    # facet-local coordinates uses (face_frame, engine_facet, the layout's affine, page 2's tap). This reader used
    # EAVE-else-first, which mirrored a hand-placed point on a facet with a ridge and no eave.
    anchor_line_id = _frame_anchor_line(face.line_ids, geom.lines)
    anchor_path = geom.lines[anchor_line_id].path
    # FRAME v105.1: THE ONE fall-line basis (facet_basis.facet_frame_axes), flat facets included.
    origin, x_axis, up = facet_frame_axes([geom.points[pid] for pid in point_ids],
                                          geom.points[anchor_path[0]], geom.points[anchor_path[-1]])
    return origin + float(x_local) * x_axis + float(y_local) * up


def _appurtenance_geometry_in_frame(geom: EagleViewGeometry, penetration_id: str, frame) -> Mapping[str, float | str]:
    pts = [np.array(frame(geom.points[pid]), dtype=float) for pid in geom.ordered_face_point_ids(penetration_id)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return {
        "cx": float((min(xs) + max(xs)) / 2.0),
        "cy": float((min(ys) + max(ys)) / 2.0),
        "w": float(max(xs) - min(xs)),
        "h": float(max(ys) - min(ys)),
        "kind": "dimensioned",
    }


def _group_shared_edge_ft(geom, row, penetration_id, host_face_id, confirmed_selection) -> float:
    """How much of THIS marker's perimeter is the cut line EagleView made, not a chase wall (FRAME v106.6d).

    Summed over this marker's group-mates on ADJACENT facets, because one object may cross more than one
    ridge: a three-member chain A-B-C charges A for its overlap with B, C for its overlap with B, and B for
    both — so every cut line is charged exactly twice, once from each side, which is exactly how many
    phantom walls the split created.

    Only a LINKED group is corrected. The group id comes from the user's "Same physical item as..." link on
    page 2, the same authority that already decides the flashing dedupe, and an unlinked marker's group
    defaults to its own penetration id — so it has no mates and is corrected by nothing. Two separate
    chimneys either side of a ridge really do have four walls each."""
    # NO early return for "gid == own penetration id". It would be redundant under page 2's own convention,
    # which mints a group id as 'grp_' + the anchor's id (linkMarkers), so a group id never equals a member's
    # penetration id and an unlinked marker has no mate whose group matches — the loop below returns 0.0 on its
    # own. It would also be HARMFUL under the other convention a producer might reasonably pick: naming the
    # group after the anchor ("F68"). Under that convention the guard fires on the anchor and not on the
    # follower, so only ONE of the two phantom walls comes off and the correction silently halves. Deleting the
    # guard makes this helper correct under both conventions and keeps the symmetry the docstring promises.
    # Found by mutation: removing the guard changed nothing on any real claim, which is what proved it dead.
    gid = str(row.get("group", penetration_id))
    total = 0.0
    for other in confirmed_selection.get("penetration_appurtenance_repairs", ()) or ():
        o = _as_mapping(other)
        o_pen = str(o.get("penetration_face_id") or "")
        if not o_pen or o_pen == str(penetration_id):
            continue
        if str(o.get("group", o_pen)) != gid:
            continue
        total += shared_edge_overlap_ft(geom, str(host_face_id), str(o.get("host_face_id") or ""),
                                        str(penetration_id), o_pen)
    return total


def _with_appurtenance_label(candidate: Candidate, kind_label: str, group: Optional[str], contacted=None, size_class=None, carves: bool = True, other_label=None, other_category=None, operation=None, host_replaced: bool = False, shared_edge_ft: float = 0.0) -> Mapping[str, object]:
    params = dict(candidate.params)
    params["kind_label"] = kind_label
    if group is not None:
        params["group"] = group
    if contacted is not None:
        params["contacted"] = bool(contacted)
    if size_class not in (None, ""):
        params["size_class"] = str(size_class)
    # v71 DEFECT 2: a user-defined appurtenance (kind_label=OTHER) names itself with other_label; carry
    # it (and any explicit other_category) into the params module1_m2interface._surface_appurts reads,
    # so the engine bills the user's own words instead of the generic 'User-defined appurtenance'.
    if other_label not in (None, ""):
        params["other_label"] = str(other_label)
    if other_category not in (None, ""):
        params["other_category"] = str(other_category)
    # FRAME v106.6 — the SECOND assertion (skylight reset-vs-replace, power vent cover-vs-fan), carried to
    # the engine that bills the line. The assembly already reads this same key for the area carve, so the
    # picture and the line read ONE answer.
    if operation not in (None, ""):
        params["operation"] = str(operation)
    # FRAME v106.6d — the cut line this marker contributes that is not a wall. Always carried, including the
    # 0.0 case, so the engine reads one key rather than inferring an absent one.
    params["shared_edge_ft"] = float(shared_edge_ft or 0.0)
    # FRAME v106.6 — IS THE HOST FACET BEING REPLACED? Joseph, 2026-11-04: the repair patch is "only for
    # repairs, not for facet replacement. Replacement facet just gets the SQ."
    #
    # QA GOT THIS WRONG FIRST and the gate caught it: the engine read `iface.is_replacement`, which is FALSE
    # on an appurtenance component even when its host facet IS being replaced — only the replacement loop
    # sets that flag, and an appurtenance repair is its own component. The fact the rule needs is about the
    # HOST FACET, not about this component, so it is carried as its own fact under its own name rather than
    # borrowed from a flag that means something else.
    params["host_replaced"] = bool(host_replaced)
    if not carves:
        # A NON-CARVING appurtenance (today: a cover-only power attic vent) has NO disturbance
        # footprint at all, so it is handed to Module 2 with no appurtenance_geometry.
        # module1_m2interface._surface_appurts derives Appurt.affected_SF from exactly this key, so
        # dropping it yields affected_SF == 0 and APPURT_IWS — which fires only on affected_SF > 0 —
        # never triggers. THAT IS THE WHOLE MECHANISM: the geometry is absent because there is no
        # disturbance, and the ice & water falls out of the zero. No IWS special case exists, and
        # none may be added. module1_m2interface stays byte-identical.
        params.pop("appurtenance_geometry", None)
    return {"kind": candidate.kind, "source_ids": candidate.source_ids, "origin": candidate.origin, "confirmed": candidate.confirmed, "params": params}


# RFG FLCH< / RFG FLCH / RFG FLCH> are THREE DIFFERENT XACTIMATE LINE ITEMS AT THREE DIFFERENT PRICES.
# They cannot be billed as one line of qty 3. Derived here (from the code) so that
# module2_scope_expansion.py — which already stamps the code correctly — stays BYTE-IDENTICAL.
_XACT_SIZE_LABEL = {
    "RFG FLCH<": "Chimney flashing — Small (24x24)",
    "RFG FLCH":  "Chimney flashing — Average (32x36)",
    "RFG FLCH>": "Chimney flashing — Large (60x24)",
}


# Module-level copy of the appurtenance-material categories, so per-structure aggregation dedupes one
# physical object exactly the way the global loop does. Kept in sync with the local set in the assembly.


def _structure_of_face(geom: EagleViewGeometry, face_id: str) -> str:
    """The <ROOF id="…"> a component sits in. A notch label like 'F21+F22' takes its first member; an
    empty structure_id (no ROOF nesting in the XML) collapses to '' so a lone structure stays anonymous."""
    first = str(face_id).split("+")[0]
    face = geom.faces.get(first)
    return (getattr(face, "structure_id", "") or "") if face is not None else ""


def _aggregate_by_structure(geom: EagleViewGeometry, components, confirmed_selection, active_transitions) -> Tuple[Tuple[str, Tuple[AggregatedScopeLine, ...]], ...]:
    """Per-structure material lists, one aggregation per <ROOF id>. Reuses the SAME steps the global
    aggregation uses (appurtenance dedup, edge dedup + ridge vents, transition expansion, trade-order
    aggregation), scoped to each structure's own components. Physically separate structures share no
    edge, so per-structure edge dedup equals the global dedup — which is why the single-structure entry
    comes out byte-identical to aggregated_scope."""
    comps_by_structure: "MutableMapping[str, List]" = {}
    for comp in components:
        comps_by_structure.setdefault(_structure_of_face(geom, comp.face_id), []).append(comp)

    trans_by_structure: "MutableMapping[str, List]" = {}
    trans_sys_by_structure: "MutableMapping[str, List[str]]" = {}        # FRAME v105.3: each transition's roof system
    _profile = _shake_measurements_from_selection(confirmed_selection)   # v90: same profile the bands used
    if active_transitions:
        selected_ids = set(selected_transition_repairs(confirmed_selection))
        metal_facts = transition_metal_facts(confirmed_selection)      # v91: same reading as the roof level
        path_r_ids = {t.edge_id for t in path_r_transitions(geom, confirmed_selection)}   # v92 Path R
        valley_ids = [str(v) for v in (confirmed_selection.get("selected_valley_ids", ()) or ())]
        for t in active_transitions:
            sid = _structure_of_face(geom, t.face_a_id)
            trans_sys_by_structure.setdefault(sid, []).append(system_for_facets(
                (t.face_a_id, t.face_b_id), confirmed_selection, f"module2_assembly: the per-structure transition {t.edge_id}"))
            trans_by_structure.setdefault(sid, []).append(Transition(
                contact_LF=transition_contact_lf(geom, t, valley_ids, confirmed_selection),   # ARC-06a: per facet
                edge_total_LF=float(t.edge_total_LF),
                selected=t.edge_id in selected_ids,
                metal=metal_facts.get(str(t.edge_id)),
                replaced=t.edge_id in path_r_ids))

    out: List[Tuple[str, Tuple[AggregatedScopeLine, ...]]] = []
    for sid in sorted(comps_by_structure, key=_struct_sort_key):
        seen_appurt: set = set()
        non_edge: List[ScopeLine] = []
        edge_contribs: List[EdgeContribution] = []
        for comp in comps_by_structure[sid]:
            gid = next((a.group for a in comp.iface.appurts if a.group is not None), None)
            for line in comp.scope_lines:
                if line.category_id in _EDGE_DRIVEN_CATEGORIES:
                    continue
                if gid is not None and line.category_id in _APPURT_MATERIAL_CATEGORIES:
                    key = (gid, line.category_id)
                    if key in seen_appurt:
                        continue
                    seen_appurt.add(key)
                non_edge.append(line)
            # FRAME v105.3: stamped exactly as at the roof level — the component's face id is in hand.
            if comp.edge_contributions:
                _csys = system_for_facet(comp.face_id, confirmed_selection)
                edge_contribs.extend(replace(c, system_id=_csys) for c in comp.edge_contributions)
        deduped = _dedupe_edge_contributions(edge_contribs)
        edge_lines = _edge_lines_with_ridge_vents(deduped, _ridge_vents(confirmed_selection))
        # FRAME v105.3: grouped by roof system in first-appearance order, as at the roof level — one group, one list,
        # the same order, when there is one system.
        _groups: Dict[str, List[Transition]] = {}
        for _sys, tr in zip(trans_sys_by_structure.get(sid, ()), trans_by_structure.get(sid, ())):
            _groups.setdefault(_sys, []).append(tr)
        trans_lines = tuple(l for _sys, _trs in _groups.items()
                            for l in roof_system(_sys).expand_scope(M1Interface(transitions=_trs, measured_profile=_profile),
                                                                    repair_factor=1.0))
        out.append((sid, tuple(_aggregate_lines([*non_edge, *edge_lines, *trans_lines]))))
    return tuple(out)


def _struct_sort_key(sid: str):
    """Order structures by the trailing integer of the ROOF id when present (ROOF1, ROOF2, …), else name."""
    import re as _re
    m = _re.search(r"(\d+)$", str(sid))
    return (0, int(m.group(1))) if m else (1, str(sid))


def _aggregate_lines(lines: Iterable[ScopeLine]) -> List[AggregatedScopeLine]:
    """Merge scope lines into the material list.

    The key now includes `xact_code`, so lines that will be BILLED DIFFERENTLY are never merged.
    Same-code lines still merge exactly as before. Verified: CHIMNEY_FLASH is the ONLY category whose
    code varies (S/A/L); every other category emits a single code, so nothing else can split.

    FRAME v104c: across ROOF SYSTEMS, the category decides (shared_category_registry.material_splits — Joseph,
    2026-10-31). A SPLIT category's key carries the line's material, so two systems never merge; a MERGED category's
    does not, so two systems' lines merge exactly when they name the same product (the item text, already in the key —
    "one line only if it's genuinely the same product").
    """
    totals: MutableMapping[Tuple[str, str, str, Optional[str], str, Optional[str]], float] = {}
    items: MutableMapping[Tuple[str, str, str, Optional[str], str, Optional[str]], str] = {}
    cites: MutableMapping[Tuple[str, str, str, Optional[str], str, Optional[str]], List[str]] = {}
    mats: MutableMapping[Tuple[str, str, str, Optional[str], str, Optional[str]], set] = {}
    for line in lines:
        code = getattr(line, "xact_code", None)
        # v77 DEFECT 5 (Joseph, binding): GROUP BY THE USER'S LABEL. The item text (the user's own
        # label for a user-placed appurtenance, e.g. '6" pipe jack') now participates in the merge key,
        # matched on case and surrounding whitespace only — so two DIFFERENT labels never merge and two
        # IDENTICAL labels do. Standard categories emit a single stable item per (category, code), so
        # this is a no-op for them and every existing report stays byte-identical.
        item_key = str(getattr(line, "item", line.category_id) or line.category_id).strip().casefold()
        material = getattr(line, "material_profile_id", None)
        key = (line.category_id, line.unit, line.gate, code, item_key,
               material if material_splits(line.category_id) else None)
        totals[key] = totals.get(key, 0.0) + float(line.qty)
        # The citation is ADDITIVE METADATA, deliberately NOT part of the key — it must never split a
        # line. FRAME v104c (QA Q1, reversible): every DISTINCT citation the merged lines carry is kept, in first-seen
        # order, joined — never v98's first-wins setdefault, which silently dropped the others. A merged line exists
        # because each source requires it, and the supplement argues better citing every standard. Identical
        # citations collapse to one, so with one package every line is unchanged (measured: no key in the suite ever
        # received two different citations).
        _c = getattr(line, "citation", None)
        _cl = cites.setdefault(key, [])
        if _c not in (None, "") and _c not in _cl:
            _cl.append(_c)
        mats.setdefault(key, set()).add(material)
        # A split chimney line names its size, so a human reading the material list can tell the three
        # apart. A category with no code keeps its existing item text, unchanged.
        default_item = getattr(line, "item", line.category_id) or line.category_id
        items.setdefault(key, _XACT_SIZE_LABEL.get(code, default_item) if code else default_item)
    out = [AggregatedScopeLine(item=items[k], category_id=k[0], unit=k[1], gate=k[2],
                               qty=round(v, 4), xact_code=k[3],
                               citation=("; ".join(cites[k]) if cites.get(k) else None),
                               material_profile_id=(next(iter(mats[k])) if len(mats[k]) == 1 else None))
           for k, v in totals.items()]  # k = (category_id, unit, gate, xact_code, item_key, material-or-None)
    return sorted(out, key=_trade_order_key)


# THE ORDER AN ESTIMATE IS WRITTEN IN — not alphabetical, which buried the shakes in the middle and
# meant nothing to a roofer or an estimator. Defined ONCE, here. An unknown category falls to the end
# (never crashes, never drops a line); UNMAPPED is last of all, so anything unclassified is conspicuous.
#
# FRAME v98 (C-3a): "the field covering is written first" is a CORE rule; WHICH id is the field covering is the
# registered package's answer. So the order is a FUNCTION, called where it is used — a visibly lazy call site,
# not a module-level table (which would call the lookup at import: crashing before a package registers, or
# freezing one system's id once a second loads). Its derived rank and unknown-rank are computed from it per
# call too; none of the three exists at module level any more.
_CORE_TRADE_ORDER = (
    # 1. the field covering — prepended per call by _trade_order()
    # 2. roof covering / underlayment / trim
    "FIELD_TEAROFF", "FIELD_COVERING", "FIELD_FELT", "IWS", "APPURT_IWS",
    "STARTER", "DRIP_EDGE", "RIDGE_CAPS", "HIP_CAPS", "RIDGE_HIP_CAP", "GABLE_CORNICE",
    # 3. flashings
    "VALLEY_METAL", "STEP_FLASH", "TRANSITION_FLASH", "ENDWALL_FLASH",
    "CHIMNEY_FLASH", "SKYLIGHT_FLASH", "PIPE_JACK_FLASH",
    # 4. vents & other appurtenances
    "BOX_VENT", "TURBINE_VENT", "RIDGE_VENT", "VENT_CAP", "CHIMNEY_CHASE_COVER",
    # 5. labor & charges
    "GENERAL_LABOR", "STEEP_CHARGE", "HIGH_SLOPE_CHARGE",
    # 6. anything unclassified, last and conspicuous
    "UNMAPPED",
)


def _trade_order(system_id=None):
    """THE ORDER AN ESTIMATE IS WRITTEN IN: `system_id`'s field covering first, then the core order. Per call.

    FRAME v104c: per SYSTEM. The sort key passes each line's own system (line_system), so on a mixed roof each
    package's field covering ranks first. With no system given — only a reader asking for the canonical order, never
    the sort key — it is the sole category package's (bridge 4, narrowed: raises on two or more)."""
    if system_id is None:
        system_id = sole_category_package("module2_assembly._trade_order() with no system (a reader of the canonical order)")
    return (field_category_id(system_id),) + _CORE_TRADE_ORDER


def _trade_rank(system_id=None):
    """{category_id: rank}, with an unknown category falling to the end (rank == len(order)), never crashing."""
    order = _trade_order(system_id)
    return {cat: i for i, cat in enumerate(order)}, len(order)

# within STEEP_CHARGE the tiers read in slope order, the way a carrier writes them
_STEEP_TIER_RANK = {"STEEP_7-9": 0, "STEEP_10-12": 1, "STEEP_>12": 2}


def _trade_order_key(line: AggregatedScopeLine):
    # FRAME v98: resolved per call, never at import. FRAME v104c: per LINE — the line's own system decides whether
    # its category is that system's field covering. A MERGED category (FIELD_FELT, DRIP_EDGE, the charges) is a core
    # id by Joseph's ruling, and a package's field covering must be one it OWNS (register_package_categories), so a
    # merged line is never a field line and needs no system — which a line summed from two systems does not have.
    if material_splits(line.category_id):
        ranks, unknown = _trade_rank(line_system(line, "module2_assembly._trade_order_key: a line with no material"))
    else:
        ranks, unknown = {cat: i + 1 for i, cat in enumerate(_CORE_TRADE_ORDER)}, len(_CORE_TRADE_ORDER) + 1
    rank = ranks.get(line.category_id, unknown)
    tier = _STEEP_TIER_RANK.get(line.xact_code or "", 0)
    return (rank, line.category_id, tier, line.unit, line.gate, line.xact_code or "")


def _field_unit_order(by_unit):
    """[(qty, unit), ...] from {unit: [qty, ...]}: SQ first, then EA, then any other unit sorted — never trade order."""
    order = [u for u in ("SQ", "EA") if u in by_unit] + sorted(u for u in by_unit if u not in ("SQ", "EA"))
    return [((by_unit[u][0] if len(by_unit[u]) == 1 else round(sum(float(q) for q in by_unit[u]), 4)), u) for u in order]


def field_quantities_by_system(result):
    """THE PER-SYSTEM AUTHORITY for "how much field covering, in which unit" (FRAME v104d, ledger entry 92 §2).

    {system_id: [(qty, unit), ...]} — for each roof system with a field line, ITS field covering's figures, shaped
    exactly as field_quantities shapes one system's (SQ first, then EA, then any other unit). Systems in sorted id
    order; empty when there is no field line. A line is a field line when its category is ITS OWN system's field
    covering (per line, v104c); a merged category is a core id, never a field covering, so it needs no lookup."""
    by_system = {}
    for line in getattr(result, "aggregated_scope", None) or ():
        if not material_splits(line.category_id):
            continue
        sysid = line_system(line, "module2_assembly.field_quantities_by_system: a line with no material")
        if line.category_id == field_category_id(sysid):
            by_system.setdefault(sysid, {}).setdefault(str(line.unit), []).append(line.qty)
    return {sysid: _field_unit_order(by_system[sysid]) for sysid in sorted(by_system)}


def field_by_system_display(result):
    """FRAME ARC-06a r1: field_quantities_by_system's answer for a DISPLAY surface — [{system_id, label, figures}], each
    system's own figures under its own field category's display label (category_display_names: package content for a
    package id). For page 2's tile when a scope carries field covering from two or more systems (e.g. a MODBIT
    replacement whose tie-in bills wood-shake field on the shake side), where field_summary RAISES by design (v104d):
    nothing is summed and nothing is picked — the systems are shown side by side. Systems in sorted id order."""
    from category_display_names import category_display_name   # function-local: display vocabulary, read at call time
    return [{"system_id": sid, "label": str(category_display_name(field_category_id(sid)) or sid),
             "figures": [[float(q), str(u)] for q, u in figs]}
            for sid, figs in field_quantities_by_system(result).items()]


def field_quantities(result):
    """THE ONE AUTHORITY for "how much field covering, in which unit" on a scope RESULT (FRAME v98, C-4).

    [(qty, unit), ...] for the registered package's field category: the SQ line FIRST when one exists (a
    full-slope replacement, billed in squares), then the EA line (a localized repair, billed each) — a mixed
    claim carries both. Never raw aggregated_scope order, which is trade order and would make the primary
    figure depend on how the estimate happens to sort. Any other unit follows. Empty when there is no field line.

    FRAME v104d: it DELEGATES to field_quantities_by_system. With one system present it returns exactly that
    system's figures — its v104c value, byte for byte. With TWO OR MORE it RAISES (RegistryWiringError): a claim-level
    single figure has no meaning on a mixed roof, so it neither sums shake squares with another covering's nor picks
    one. Ask field_quantities_by_system instead. The return shape is unchanged (QA §2: it feeds page 2's live tile and
    page 3's comparison).

    Read (through field_summary below) by every copy that used to keep its own loop: pyodide_bridge.js
    _wb_scope_summary (page 2's tile, the LIVE path) and its twin, workbench_seam._receipt_totals,
    verification/workbench_server.py (dev server) and verification/bridge_contract_regression.py's mirror. module3_caller._shake_dual_from_lines is NOT this
    function — it reads serialized report lines; field_quantity_agreement_regression holds the two together."""
    by_system = field_quantities_by_system(result)
    if len(by_system) > 1:
        raise RegistryWiringError(
            f"FRAME v104d: module2_assembly.field_quantities — this scope has field covering from "
            f"{len(by_system)} roof systems ({list(by_system)}), and one claim-level figure would either sum two "
            f"different coverings or pick one. Fix: read module2_assembly.field_quantities_by_system(result), "
            f"which answers per system.")
    return next(iter(by_system.values()), [])


def field_summary(result):
    """The field-covering keys every display / receipt surface emits, shaped ONCE from field_quantities() so no
    surface hand-writes its own selection (FRAME v98, C-4/C-5/C-7):

      field_qty / field_unit           the primary figure — the SQ line when one exists, else the EA line
      field_qty_alt / field_unit_alt   the other field line on a mixed claim, else None
      legacy_total_EA                  total_EA's EXACT v97.1 value and semantics (C-5): the first field line in
                                       aggregated (trade) order, which sorts EA before SQ — so a replacement's SQ
                                       figure, as before. Kept bit-identical because the diagram's independently
                                       summed EA is cross-checked against it; the misleading name is a known-open.
      field_by_system                  FRAME v104d: {system_id: [[qty, unit], ...]}, field_quantities_by_system's
                                       answer in a JSON-plain shape — the per-system figures, beside the existing keys
                                       (which are unchanged). No surface reads it yet; the bridge is not edited.

    The existing keys are claim-level, so with two or more systems this RAISES through field_quantities (v104d)."""
    by_system = field_quantities_by_system(result)
    fq = field_quantities(result)
    prim = fq[0] if fq else (None, None)
    alt = fq[1] if len(fq) > 1 else (None, None)
    legacy = next((q for q, u in fq if u == "EA"), fq[0][0] if fq else None)
    return {"field_qty": float(prim[0]) if prim[0] is not None else None, "field_unit": prim[1],
            "field_qty_alt": float(alt[0]) if alt[0] is not None else None, "field_unit_alt": alt[1],
            "legacy_total_EA": legacy,
            "field_by_system": {sysid: [[q, u] for q, u in v] for sysid, v in by_system.items()}}


def _system_boundary_valley_ids(valley_pairs: Mapping[str, Sequence[str]], confirmed_selection) -> frozenset:
    """THE ONE test for "this valley sits on a SYSTEM BOUNDARY" (FRAME v106.4).

    A valley whose two bordering roof facets resolve to DIFFERENT roof systems is a boundary, and a boundary
    bills NO valley metal and NO valley underlayment from either side. Three things say so, and they agree:

      * Joseph's own ruling, recorded in the roadmap: Yager as a replacement billing 154.78 LF "instead of
        134.03" is a CONFIRMED OVER-BILL, and the 20.75 LF difference is exactly L30 + L36 + L45 + L49 — the
        four shake-to-MODBIT boundaries. So removing them is removing an over-bill, not creating a shortfall.
      * What is physically there. Joseph, on these very edges: "the last roofer decided it was better to put
        a membrane surface in this essentially dead valley area." There is no W-metal valley to bill.
      * The engine ALREADY encodes it elsewhere. `METAL_MEMBRANE` is documented as "flat-roof membrane runs
        up under the courses: it IS the flashing and the underlayment", and wood shake's own
        `transition_emits_underlayment` is literally `metal != METAL_MEMBRANE`. This extends that same rule
        from the transition path to the valley claim; it does not invent one.

    WHY THIS HAD TO BECOME A RULE (QA error 74). `valley_lf_claimed` claims each valley ONCE, for the first
    facet in LIST ORDER that touches it, and that facet's engine then bills from its own
    `valley_LF_in_scope`. At one package every claimer billed identically, so order never mattered. With a
    SECOND package whose engine does not read `valley_LF_in_scope` at all, the claim-once dedupe silently
    decided which system saw a boundary valley: MODBIT first and it was dropped (134.03), shake first and it
    was billed (154.78). Measured on Yager: string-sorted order gave 134.03, page 2's own `naturalCompare`
    order gave 154.78, and shuffles gave 141.15, 147.66 and 153.06. Both paths were affected — the
    replacement claim and, measured separately, the repair claim on all four boundaries.

    Deciding by rule makes it ORDER-INDEPENDENT. Canonicalising the iteration order instead would have kept
    first-claimer semantics as a hidden rule, which is the kind of decision-by-accident this codebase removes.

    ON A SINGLE-PACKAGE CLAIM THIS IS ALWAYS EMPTY: every facet resolves to the same system, so nothing
    changes for any claim that declares one covering or none — which is every saved claim and every frozen
    render.
    """
    out = set()
    for vid, faces in valley_pairs.items():
        if len(faces) < 2:
            continue
        if len({system_for_facet(f, confirmed_selection) for f in faces}) > 1:
            out.add(str(vid))
    return frozenset(out)


def _system_boundary_bands(geom: EagleViewGeometry, boundary_valleys: frozenset,
                           valley_pairs: Mapping[str, Sequence[str]], confirmed_selection,
                           shake_measurements=None):
    """Which COURSED facets have courses to lift, because the FLAT side of a boundary is being replaced.

    Yields (valley_id, coursed_face_id, edge_total_LF, extent_ft) — THE ONE place that decision is made.
    Returns nothing on a single-package claim (no boundaries) and nothing when no flat facet is replaced,
    so every saved claim and frozen render is untouched by construction, exactly as the edges are.

    WHICH SIDE IS COURSED is a registry fact, never an assumption about which way a roof slopes: the coursed
    side is the one whose package declares `course_top_ft`, and the flat side is the one that declares
    `tie_in_courses`. `system_boundary_tie_in_ft` composes exactly those two declarations, so asking it for
    the FLAT side's view returns a positive extent precisely when there is a coursed neighbour with courses
    to lift — and that same number is what the membrane's own tie-in line bills. One call, one number, two
    lines that cannot drift apart.

    A boundary with no flat side (shake meeting shake), or two flat sides (MODBIT meeting TPO), yields
    nothing: the first is not a boundary at all, and in the second neither package declares course geometry
    for the other to measure, so the extent is 0.0.
    """
    if not boundary_valleys:
        return
    replaced = {str(_as_mapping(_it)["face_id"])
                for _it in confirmed_selection.get("replaced_facets", ())}
    if not replaced:
        return
    for vid in sorted(boundary_valleys, key=_id_sort_key):
        faces = [str(f) for f in valley_pairs.get(str(vid), ())]
        if len(faces) < 2:
            continue
        total_lf = float(geom.valley_lengths.get(str(vid), 0.0))
        if total_lf <= 0:
            continue
        for flat_face in faces:
            if flat_face not in replaced:
                continue                      # the flat side must be the one being replaced
            for coursed_face in faces:
                if coursed_face == flat_face:
                    continue
                # THE v72 RULE, STATED HERE RATHER THAN RELIED ON DOWNSTREAM. A band on a facet that is
                # itself fully replaced lies inside a slope already 100% scoped, so it contributes nothing.
                # The band loop below would skip it anyway — but then this generator's output would not mean
                # "bands that get carved", and a reader (or a gate) could not tell the two apart. Stating it
                # here makes the yielded set the BILLED set.
                #
                # A VALLEY-THREADED FACET IS DELIBERATELY *NOT* FILTERED HERE, because that case is a UNION
                # and not a drop: a facet with its own valley repair has the band folded into that zone by
                # the loop below, and its area is still billed. Filtering it here would silently lose it.
                if coursed_face in replaced:
                    continue
                extent = float(system_boundary_tie_in_ft(
                    system_for_facet(flat_face, confirmed_selection),
                    system_for_facet(coursed_face, confirmed_selection), shake_measurements))
                if extent > 0:
                    yield str(vid), coursed_face, total_lf, extent


def _system_boundary_edges(geom: EagleViewGeometry, face_id: str, valley_ids: Sequence[str],
                           boundary_valleys: frozenset, valley_pairs: Mapping[str, Sequence[str]],
                           confirmed_selection, shake_measurements=None) -> Tuple[Edge, ...]:
    """THE ONE site that builds SYSTEM_BOUNDARY edges (FRAME v106.3b). Every boundary edge anywhere in a
    claim comes from here, so there is no second place that decides what a boundary is or how far it reaches.

    REPLACEMENT ONLY, and that is JOSEPH'S RULING of 2026-11-04, in his own words:

    > *"Even if the whole valley or boundary area is affected, if one side of the boundary is marked as a flat
    >  surface, but isn't being replaced, then the flat surface tie-in would still remain untouched. The flat
    >  surface system has to be being replaced in order to trigger replacing the tie-in."*

    So a REPAIR of the flat facet produces no boundary edge, however much of the boundary its zone covers.
    The reason is physical: the tie-in is part of INSTALLING the membrane. You only run new membrane up the
    slope and under the courses when you are laying new membrane; a patch repair does not lift the shake
    courses, and the membrane already under them stays — which is the same thing `METAL_MEMBRANE` has always
    encoded ("it IS the flashing and the underlayment"), and the same reason wood shake's
    `transition_emits_underlayment` is literally `metal != METAL_MEMBRANE`.

    **THE TEST LIVES HERE, NOT AT THE CALL SITES.** The three callers pass the valley ids their own component
    brought into scope — and they still do, because that part is also right: a repair at one valley does not
    disturb a boundary at the other end of a facet, and a replacement takes the whole perimeter (its caller
    passes `_facet_valley_ids`, exactly as the valley claim two lines above it does). But *whether the facet
    is being replaced at all* is one rule, and a rule enforced by call-site discipline is a rule a fourth
    caller gets wrong. QA built it the other way first and Joseph caught it: a MODBIT valley repair billed a
    0.0631 SQ tie-in that no one is installing.

    WHY IT CANNOT LIVE IN module1_m2interface, where the other edges are surfaced: that function receives
    `engine_face.edges` as (a, b, edge_type, total_LF) tuples with NO LINE IDENTITY. It can tell that an edge
    is a valley but never WHICH valley, and a system boundary is identified by line id. Only the assembly has
    the line ids, the boundary set and the registry together — so it builds these and passes them in.

    NOT DEDUPED, and that is the ruling rather than an oversight. Both facets of a boundary get an edge for
    it, because Joseph's ruling of 2026-11-01 is that each side applies its OWN standard termination and FRAME
    bills both. The two edges carry DIFFERENT `tie_in_extent_ft` — each side asks for its own — and on Yager
    the shake side's is 0.0, because a membrane declares no course geometry for shake to run under. Deduping
    them would be the pairwise thinking the ruling rejects.
    """
    if not boundary_valleys:
        return ()
    # JOSEPH'S RULING, 2026-11-04 — the one test, in the one place. `replaced_facets` is read the same way
    # the mutual-exclusion rule and `_replacement_edge_contributions` read it, so "being replaced" means
    # exactly what it means everywhere else in this file.
    if str(face_id) not in {str(_as_mapping(_it)["face_id"])
                            for _it in confirmed_selection.get("replaced_facets", ())}:
        return ()
    out: List[Edge] = []
    this_system = system_for_facet(face_id, confirmed_selection)
    for vid in valley_ids:
        vid = str(vid)
        if vid not in boundary_valleys:
            continue
        # `valley_pairs` is the map built ONCE at the top of assemble_full_roof_scope from
        # emit_valley_candidates' bordering_roof_face_ids — THE valley facet-pair source (v93). The boundary
        # set was derived from the same map, so a second walk here would be a second source for one fact,
        # which is the shape entry 124 was written about.
        others = [f for f in valley_pairs.get(vid, ()) if str(f) != str(face_id)]
        if not others:
            continue
        other_system = system_for_facet(str(others[0]), confirmed_selection)
        total_lf = float(geom.valley_lengths.get(vid, 0.0))
        if total_lf <= 0:
            continue
        # CONTACT EQUALS THE TOTAL, AND THAT IS A FACT OF THE THREE PATHS THAT REACH HERE, NOT AN ASSUMPTION.
        # Every one of them claims a WHOLE valley: a valley repair's zone is built from the valley event and
        # runs the full length of the line (measured: L30 1.72 LF -> 27.0 SF, L45 10.13 LF -> 101.2 SF, both
        # spanning the whole valley), a multi-valley repair is the same per valley, and a replacement takes
        # the facet's entire perimeter. There is no selection anywhere in the program for part of a valley.
        #
        # SO IT IS WRITTEN AS contact, AND THE ENGINE STILL APPLIES THE 95% CONTINUOUS-RUN RULE TO IT. The
        # pair is deliberately redundant TODAY, because a full-run quantity that is safe while every path
        # claims the whole run becomes an over-bill the moment a partial path exists — the same shape as
        # entry 124, where a dedupe that was safe at one answer became a decision at two. If a partial-valley
        # selection is ever added, the engine bills the part and the gate's invariant check fires, instead of
        # this quietly billing a whole boundary for a few feet of work.
        contact_lf = total_lf
        out.append(Edge(SYSTEM_BOUNDARY, contact_lf, total_lf,
                        boundary_system_id=str(other_system),
                        tie_in_extent_ft=float(system_boundary_tie_in_ft(this_system, other_system,
                                                                         shake_measurements))))
    return tuple(out)


def _claim_valley_lf_once(geom: EagleViewGeometry, valley_id: str, selected_valley_ids: Sequence[str],
                          claimed: set[str], boundary_valleys: frozenset = frozenset()) -> float:
    # FRAME v106.4: a SYSTEM BOUNDARY valley is claimed by neither side — see _system_boundary_valley_ids.
    # It is deliberately NOT added to `claimed`: it is not billed as a valley, so it casts no valley
    # operation vote either.
    if valley_id in boundary_valleys:
        return 0.0
    if valley_id not in selected_valley_ids or valley_id in claimed:
        return 0.0
    claimed.add(valley_id)
    return float(geom.valley_lengths[valley_id])


def _require_valley_borders_face(geom: EagleViewGeometry, valley_id: str, face_id: str) -> None:
    if valley_id not in geom.lines or geom.lines[valley_id].type.upper() != "VALLEY":
        raise ValueError(f"missing valley candidate {valley_id}")
    if valley_id not in geom.faces[face_id].line_ids:
        raise ValueError(f"{valley_id} does not border {face_id}")


def _host_face_for_penetration(geom: EagleViewGeometry, penetration_id: str) -> str:
    for face_id, face in geom.roof_faces.items():
        if penetration_id in face.children:
            return face_id
    raise ValueError(f"missing penetration host for {penetration_id}")


def _penetration_candidate_from_geom(geom: EagleViewGeometry, host_face_id: str, penetration_id: str) -> Candidate:
    if penetration_id not in geom.penetration_faces:
        raise ValueError(f"missing penetration candidate {penetration_id}")
    if penetration_id not in geom.faces[host_face_id].children:
        raise ValueError(f"penetration {penetration_id} is not hosted by {host_face_id}")
    return Candidate(
        kind="penetration",
        source_ids=(penetration_id,),
        origin="xml",
        params={
            "penetration_face_id": penetration_id,
            "host_facet_id": host_face_id,
            "appurtenance_geometry": dict(geom.penetration_appurtenance_for_face(host_face_id, penetration_id)),
        },
        confirmed=False,
    )


def _require_notch_candidate(candidates: Mapping[Tuple[str, ...], Candidate], member_face_ids: Tuple[str, ...]) -> Candidate:
    key = tuple(sorted(member_face_ids, key=_id_sort_key))
    candidate = candidates.get(key)
    if candidate is None:
        raise ValueError(f"missing notch candidate {key}")
    return candidate


def _as_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("confirmed selection entries must be mappings")
    return value


def _face_centroid_x(frame, geom: EagleViewGeometry, face_id: str) -> float:
    pts = [np.array(frame(geom.points[pid]), dtype=float) for pid in geom.ordered_face_point_ids(face_id)]
    return float(np.mean(pts, axis=0)[0])


def _cycle_edges(ids: Sequence[str]):
    return {_edge_key(a, b) for a, b in zip(ids, list(ids[1:]) + [ids[0]])}


def _edge_key(a: str, b: str) -> Tuple[str, str]:
    return tuple(sorted((a, b), key=_id_sort_key))  # type: ignore[return-value]


def _id_sort_key(value: str) -> Tuple[str, int]:
    prefix = "".join(ch for ch in value if not ch.isdigit())
    number = int("".join(ch for ch in value if ch.isdigit()) or "0")
    return (prefix, number)


def _length_3d(points: Sequence[Tuple[float, float, float]]) -> float:
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += float(np.linalg.norm(np.array(b, dtype=float) - np.array(a, dtype=float)))
    return total
