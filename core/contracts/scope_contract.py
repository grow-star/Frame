#!/usr/bin/env python3
"""
SCOPE CONTRACT — the Module 1 -> Module 2 interface types (FRAME v100, core)
===========================================================================
The types every module that hands geometry to scope expansion, or reads its lines, depends on: Edge, Appurt,
Transition, M1Interface (the Module 1 interface), ScopeLine (the output line), and the transition-metal
vocabulary (METAL_* / TRANSITION_METAL_VALUES). Moved here BYTE-FOR-BYTE from module2_scope_expansion.py, which
split in v100: these types stay in core, the wood-shake scoping (expand_scope and its constants) moved to
roof_systems/wood_shake/. No field, default or value changed.

M1Interface's two dimensional defaults (shake_width_in / exposure_in) read EXPOSURE_IN / SHAKE_WIDTH_IN, so those
two constants moved with it (lines below, byte-identical). LOGGED KNOWN VIOLATION — "wood-shake defaults on the core
interface" (QA v100 Q1): 4 purity sites (the 2 definitions + the 2 defaults). They retire with the M1Interface
enrichment that retires bridge 4, when the interface carries the line's own material profile. A second roof system
needs no edit here: it constructs M1Interface with its own values and never reads these defaults.
"""
from dataclasses import dataclass, field
from typing import Optional

EXPOSURE_IN      = 10.0     # default 24" shake exposure
SHAKE_WIDTH_IN   = 7.0      # default measured average width

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

# ---- Module 1 interface (read-only inputs; Module 2 §0) ----------------------
@dataclass
class Edge:
    edge_type: str          # EAVE RAKE RIDGE HIP VALLEY FLASHING STEPFLASH
    contact_LF: float
    edge_total_LF: float

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
    shake_width_in: float = SHAKE_WIDTH_IN
    exposure_in: float = EXPOSURE_IN
    length_in: float = 24.0                               # v90: first consumer is the transition tie-in extent
    is_replacement: bool = False                          # v61 §facet-replacement: bill SQ, not EA

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
