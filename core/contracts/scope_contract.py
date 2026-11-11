#!/usr/bin/env python3
"""
SCOPE CONTRACT — the Module 1 -> Module 2 interface types (FRAME v100, core)
===========================================================================
The types every module that hands geometry to scope expansion, or reads its lines, depends on: Edge, Appurt,
Transition, M1Interface (the Module 1 interface), ScopeLine (the output line), and the transition-metal
vocabulary (METAL_* / TRANSITION_METAL_VALUES). Moved here BYTE-FOR-BYTE from module2_scope_expansion.py, which
split in v100: these types stay in core, the wood-shake scoping (expand_scope and its constants) moved to
roof_systems/wood_shake/. No field, default or value changed.

FRAME ARC-04a: THIS MODULE NAMES NO MATERIAL. Until ARC-04a, M1Interface carried three wood-shake dimension fields
(shake_width_in / exposure_in / length_in) whose defaults read EXPOSURE_IN = 10.0 and SHAKE_WIDTH_IN = 7.0, defined
here — the logged known violation "wood-shake defaults on the core interface" (QA v100 Q1) — and this module also
held the three MEMBRANE_* flat-roof detail values. All of them left core:
  * the interface now carries the resolved MEASURED PROFILE opaquely (`measured_profile`); the wood-shake package
    reads its own setting names from it and supplies its own legacy defaults (7 in width, 10 in exposure, 24 in
    length) when a caller hands none — roof_systems/wood_shake/module2_scope_expansion.interface_profile;
  * the MEMBRANE_* values live, unchanged, in the package that reads them: roof_systems/modbit/modbit_scope_expansion.
"""
from dataclasses import dataclass, field
from typing import Mapping, Optional

# ---- v91: WHAT IS AT A TRANSITION (Joseph 2026-10-17 / 2026-10-25) -------------------------------
# ONE vocabulary. transition_events validates every payload row against it (the data layer is the
# enforcement point) and the emission below reads the same two predicates — so the UI, the gate and the
# scope cannot disagree about what an answer means. "There may not be any metal at all."
METAL_EXPOSED   = "EXPOSED"     # visible metal flashing (the only answer under which `damaged` means anything)
METAL_CONCEALED = "CONCEALED"   # metal under the courses — real, but hail cannot have struck it
METAL_NONE      = "NONE"        # no metal flashing at this transition
METAL_MEMBRANE  = "MEMBRANE"    # flat-roof membrane runs up under the courses: it IS the flashing and the underlayment
METAL_UNKNOWN   = "UNKNOWN"     # asked, and the user is not sure
TRANSITION_METAL_VALUES = (METAL_EXPOSED, METAL_CONCEALED, METAL_NONE, METAL_MEMBRANE, METAL_UNKNOWN)

# ---- FRAME v106.5: THE CONTINUOUS-METAL RULE, hoisted here as THE ONE COPY -----------------------
# "Metal that runs continuously rounds to the full run when the repair sweeps essentially all of it" —
# Module 2 §6. It is a REPAIR-PRACTICE rule, not a wood-shake one: it governs drip edge, continuous
# flashings and the passive transition path, and it reads the same whatever covering is underneath.
#
# IT EXISTED IN TWO COPIES, and the duplication was documented rather than fixed: wood shake's
# module2_scope_expansion ("§6 continuous-metal round-to-full-run rule") and transition_events, whose own
# comment read "same constant module2_scope_expansion uses; the rule is unchanged". A core module held a
# copy of a package's constant and said so. Both now import this one.
#
# WHY IT MOVED NOW: the MODBIT package needs it for the membrane's drip edge (v106.5), and a package
# cannot import another package. The choice was a THIRD copy or one home — and this codebase has collapsed
# five copies of the fall basis (v105.1), two anchor rules (v105.2) and two transition decisions (v106.3)
# for the same reason. scope_contract is the home because it is core, it already holds the scope
# vocabulary both callers import, and it introduces no new dependency for either.
#
# The VALUE is unchanged at 0.95, so no quantity moves: this is a move, not a rule change.
CAP_THRESHOLD = 0.95

# ---- FRAME ARC-04a: the v106.6 flat-roof detail values (MEMBRANE_LEG_FT, MEMBRANE_SKYLIGHT_CURB_FT,
# MEMBRANE_PATCH_BANDS) MOVED, unchanged in value and unit, to the one package that reads them:
# roof_systems/modbit/modbit_scope_expansion.py (their sourcing comments moved with them). No core module
# reads a membrane value.

# ---- FRAME v106.3b: THE SYSTEM BOUNDARY, as an edge type -----------------------------------------
# An edge where the two bordering roof facets carry DIFFERENT roof systems. It is not a geometric kind the
# way EAVE or VALLEY is — EagleView cannot label it, because it exists only once a claim DECLARES two
# coverings — so it is created from `facet_systems` and from nothing else. On every single-package claim, and
# therefore on every saved claim and every frozen render, no edge of this type is ever constructed.
#
# WHY IT IS ITS OWN TYPE AND NOT A `VALLEY` CARRYING A FLAG. On Yager the four boundaries are VALLEY-typed
# lines, and every existing rule keyed on "VALLEY" would then see an edge it never saw before: the valley
# rules bill from `valley_LF_in_scope`, never from edge contact (module2_assembly's own comment), and
# v106.4 already ruled that a boundary valley bills NO valley metal and NO valley underlayment from either
# side. A distinct type is inert to every existing rule by construction, which is the only way to add this
# without re-auditing each of them.
SYSTEM_BOUNDARY = "SYSTEM_BOUNDARY"

# ---- Module 1 interface (read-only inputs; Module 2 §0) ----------------------
@dataclass
class Edge:
    edge_type: str          # EAVE RAKE RIDGE HIP VALLEY FLASHING STEPFLASH SYSTEM_BOUNDARY
    contact_LF: float
    edge_total_LF: float
    # FRAME v106.3b — set ONLY on a SYSTEM_BOUNDARY edge; None on every other edge, so every existing
    # Edge(type, contact, total) construction in the tree is unchanged and every saved claim keeps working.
    #
    # `boundary_system_id` is the system on the OTHER side. The package that reads it needs the identity,
    # not a measurement: it says so in its own line text, and a package with no boundary rule ignores it.
    #
    # `tie_in_extent_ft` is CORE'S MEASUREMENT of how far this side's material must run onto the other
    # side's surface — `roof_systems.system_boundary_tie_in_ft`, which composes the asking package's
    # manufacturer course count with the other package's own course geometry. Core measures; the package
    # decides whether and how to bill it, exactly as with contact_LF and the drip edge. 0.0 means "this side
    # terminates onto the other without running material up it" and is a real answer, not a gap — see that
    # function for both ways it arises.
    boundary_system_id: Optional[str] = None
    tie_in_extent_ft: float = 0.0

@dataclass
class Appurt:
    type: str               # CHIMNEY SKYLIGHT PIPE TURTLE TURBINE OTHER
    affected_SF: float = 0.0
    contacted: bool = True          # informational events do not enter the stream
    group: Optional[str] = None     # cross-facet grouping link (§4.1)
    size_class: Optional[str] = None  # chimney S/A/L -> Xactimate code
    # --- user-defined ("OTHER") appurtenances -------------------------------
    # Both default to None, so every existing construction is unchanged.
    other_label: Optional[str] = None     # the user's free-text name for the feature
    other_category: Optional[str] = None  # optional REGISTRY_28 id; None -> UNMAPPED (human review)
    # FRAME v106.6 — the MEASURED footprint, in feet. None on a point appurtenance and on every pre-v106.6
    # construction, so every existing Appurt(...) in the tree is unchanged.
    #
    # WHY IT HAS TO BE HERE. `affected_SF` is already derived from exactly these two numbers
    # (module1_m2interface._surface_appurts: w * h), but the PRODUCT cannot be un-multiplied, and the flat
    # family needs the two sides separately: a perimeter for the membrane leg, and Joseph's cut-back
    # (w + 1ft) x (h + 1ft) for the patch. A 1x9 chimney and a 3x3 chimney have the same 9 SF and very
    # different perimeters and cut-backs.
    #
    # It is a MEASUREMENT, not a zone: `appurtenance_zone_geometry` deliberately keeps the measured w/h even
    # when it routes a base-flashed type to a point zone, and its own docstring says why — "the zone is the
    # type's, the IWS is the measurement's". These fields are the measurement's side of that split.
    #   v106.6g: that zone is the TYPE'S STANDARD FLASHING BASE plus the package's allowance, not the "fixed
    # 21in zone" this comment used to name. The 21in was core's single hard-coded number before packages
    # owned their allowances, and a bare allowance square is now only the untyped hand-placed case. The split
    # this paragraph describes is unchanged; only the figure it quoted was stale.
    width_ft: Optional[float] = None
    height_ft: Optional[float] = None
    # FRAME v106.6 — a SECOND human assertion about this appurtenance, when its type has two operations and
    # they are different scope. Today that is the skylight on a membrane (detach-and-reset vs replace,
    # Joseph 2026-11-04) and the power vent (cover vs fan), whose answer the ASSEMBLY already reads off the
    # row for the area carve. Carrying it here lets the engine that BILLS the line read the same assertion
    # the assembly read, instead of inferring one. None means not stated, which is never guessed.
    operation: Optional[str] = None
    # FRAME v106.6 — is the facet this appurtenance sits on being fully replaced? The repair patch is
    # repair-only (Joseph, 2026-11-04), and `is_replacement` on the INTERFACE cannot answer it: an
    # appurtenance repair is its own component and that flag is False there even when the host facet is
    # replaced. This is the fact the rule actually needs, under its own name.
    host_replaced: bool = False
    # FRAME v106.6d: how much of THIS marker's perimeter is not a wall at all — the cut line where EagleView
    # split one physical appurtenance across a ridge. Defaults to 0.0, so every existing Appurt(...) in the
    # tree is unchanged and an unlinked marker is corrected by nothing. See
    # geometry_core.shared_edge_overlap_ft for why it is the OVERLAP and not either marker's own width.
    shared_edge_ft: float = 0.0

@dataclass
class Transition:
    contact_LF: float
    edge_total_LF: float
    # PATH B (spec amendment: Transition Repair Events v0.1). A DETECTED transition the user
    # confirmed — via the exposed+damaged gate — as a repair event in its own right. Defaults to
    # False, so every existing construction and every existing test is unchanged.
    selected: bool = False
    # v92 PATH R: at least one facet of this transition is fully replaced (the tear-off takes it). Defaults
    # to False, so every existing construction is unchanged.
    replaced: bool = False
    # v91: what is AT this transition — one of TRANSITION_METAL_VALUES, or None (never asked). Defaults to
    # None, so every existing construction emits exactly what it emitted in v90.
    metal: Optional[str] = None

@dataclass
class M1Interface:
    """One confirmed valley-side or per-slope union from Module 1."""
    affected_SF: float = 0.0
    valley_LF_in_scope: float = 0.0
    edges: list = field(default_factory=list)            # list[Edge]
    appurts: list = field(default_factory=list)          # list[Appurt] (confirmed only)
    transitions: list = field(default_factory=list)      # list[Transition]
    facet_pitch_tier: Optional[str] = None               # one of STEEP_TIERS or None
    high_slope_user_flag: bool = False                   # §7 user confirm
    is_replacement: bool = False                          # v61 §facet-replacement: bill SQ, not EA
    # FRAME ARC-03a: the OPAQUE material-aware handoff — {"profile_id", "system_id", "profile"} for the facet this
    # interface scopes, set by the assembly from the project's ONE resolver (core/contracts/project_config.py) when
    # the claim is a schema_version 1 project; None for every historical/legacy selection, so every existing
    # construction is unchanged. Core reads nothing inside it; a package may.
    material_profile: Optional[Mapping[str, object]] = None
    # FRAME ARC-04a: the claim's RESOLVED MEASURED PROFILE (its package's resolve_profile output, e.g. the job's
    # measured shake width / exposure / length), handed to the scoping package OPAQUELY. It replaces the three
    # wood-shake fields this interface carried until ARC-04a (shake_width_in = 7.0 / exposure_in = 10.0 /
    # length_in = 24.0), which were the transitional projection of that same mapping. Core reads nothing inside
    # it and supplies no default; None means "no profile handed", and the package that scopes this interface
    # applies its OWN legacy default (the wood-shake package: interface_profile). A package that has no use for it
    # (a membrane) ignores it, exactly as it ignored the three fields.
    measured_profile: Optional[Mapping[str, object]] = None

# ---- output line -------------------------------------------------------------
@dataclass
class ScopeLine:
    item: str
    category_id: str
    qty: float
    unit: str
    gate: str               # AUTO | CONFIRM
    citation: str
    xact_code: Optional[str] = None
    # FRAME v104c: the roof system whose ENGINE produced this line — set by that package's expand_scope, never by
    # core (a line's material comes from the engine that made it). Optional with a None default, so every existing
    # construction and every saved claim keeps working; a line built outside an engine (the assembly's eave-IWS and
    # ridge-vent lines) carries None and falls back like a line-less site (shared_category_registry.line_system).
    material_profile_id: Optional[str] = None

    def key(self):
        return (self.category_id, round(self.qty, 2), self.unit, self.gate)
