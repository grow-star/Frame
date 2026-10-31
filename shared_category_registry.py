#!/usr/bin/env python3
"""Shared Category Registry v1 — canonical production home.

Authority: Wood_Shake_Shared_Category_Registry_v1.md. This module is shared
infrastructure for Module 3 keying/comparison and Carrier Parser Part B.
"""

import hashlib
from typing import Mapping, Optional

# v58: POWER_VENT added (28 -> 29 ids). v74: DEBRIS_DISPOSAL, ROOFER_LABOR, EQUIPMENT, FLUE_CAP added
# (29 -> 33 ids) — a controlled operation guarded by the hash below. The constant was literally named
# REGISTRY_28, which became a lie the moment a 29th id landed, so it is now REGISTRY, with REGISTRY_28
# kept as a DEPRECATED ALIAS so every existing import keeps working byte-for-byte. Do not add ids to
# the alias. The four v74 ids are RECEIVE-ONLY (recognised on the carrier side, never emitted by the
# required scope) — the GENERAL_LABOR precedent. See PART 2 of the v74 build.
#
# FRAME v97 (Migration Plan Amendment A2 §1): THE REGISTRY IS TWO-TIER.
#   CORE_REGISTRY   the vocabulary every roof system can use (32 ids). Changes only deliberately.
#   package ids     each roof-system package OWNS its own ids and registers them at import
#                   (register_package_categories). wood_shake owns exactly one: its field-covering id.
#   REGISTRY        the COMPOSITE: core ∪ every registered package, kept sorted, updated IN PLACE so every
#                   module that bound it at import (`from shared_category_registry import REGISTRY_28`) sees
#                   the same object. With only wood_shake loaded it is today's 33 ids, exactly.
# Three hashes replace one, all from the UNCHANGED registry_fingerprint():
#   CORE_REGISTRY_HASH (pinned below), each package's own hash (pinned by the package),
#   composite_registry_hash() (moves when a package is added — correctly and visibly).
# REGISTRY_HASH is the LEGACY anchor (72dc2aee…). The composite equals it with only wood_shake loaded; that
# equality is asserted permanently (two_tier_registry_regression), which keeps historical claims verifiable.
#
# BRIDGE 3 (Joseph 2026-10-29), retiring at Migration Plan step 4 with bridges 1 and 2: a package registers its
# ids by import side effect. The app imports its packages ONCE, in the bridge's shared boot helper, before any
# page Python runs. Read the registry before any package has registered and it RAISES (RegistryWiringError) —
# a short registry never fails quietly as a data problem downstream.
CORE_REGISTRY = (
    "APPURT_IWS","BOX_VENT","CHIMNEY_CHASE_COVER","CHIMNEY_FLASH","DEBRIS_DISPOSAL",
    "DRIP_EDGE","ENDWALL_FLASH","EQUIPMENT","FIELD_COVERING","FIELD_FELT",
    "FIELD_TEAROFF","FLUE_CAP","GABLE_CORNICE","GENERAL_LABOR","HIGH_SLOPE_CHARGE",
    "HIP_CAPS","IWS","PIPE_JACK_FLASH","POWER_VENT","RIDGE_CAPS",
    "RIDGE_HIP_CAP","RIDGE_VENT","ROOFER_LABOR","SKYLIGHT_FLASH",
    "STARTER","STEEP_CHARGE","STEP_FLASH","TRANSITION_FLASH","TURBINE_VENT",
    "UNMAPPED","VALLEY_METAL","VENT_CAP",
)
CORE_REGISTRY_SET = frozenset(CORE_REGISTRY)
CORE_REGISTRY_HASH = "7a86a944c0652eb49e15875e9d9adc1c4cc5bc4d53ba3d90bf18f7855ec32d62"
REGISTRY_HASH = "72dc2aee2f78e7e90eda4d4a1c437f4730c922255135371a390cf73931f83da6"   # LEGACY anchor (v74-v96)
LEGACY_REGISTRY_HASH = REGISTRY_HASH


def registry_fingerprint(ids):
    data = "".join(x + "\n" for x in sorted(set(ids)))
    return hashlib.sha256(data.encode()).hexdigest()


class RegistryWiringError(LookupError):
    """The category registry was read before any roof-system package registered its ids. This is a WIRING
    error, never a data error, and the message says how to fix it."""


def _no_package_error():
    return RegistryWiringError(
        "FRAME wiring: no roof-system package has registered its category ids with shared_category_registry, "
        "so the registry holds only the core vocabulary and would silently miss every package-owned id. This "
        "is missing wiring, not a data problem. Fix: import the installed packages' category modules (the "
        "bridge's shared boot helper does this for every page; a script must import one itself, e.g. any "
        "deploy/roof_systems/<system>/<system>_categories.py) before reading the registry.")


_PACKAGE_OWNED = {}       # system_id -> tuple of ids it owns
_PACKAGE_USES = {}        # system_id -> tuple of core ids it declares it uses
_PACKAGE_HASHES = {}      # system_id -> registry_fingerprint(owned ids)
_PACKAGE_FIELD = {}       # system_id -> its DECLARED field-covering id (FRAME v98)


def _guard():
    if not _PACKAGE_OWNED:
        raise _no_package_error()


class _CompositeList(list):
    """REGISTRY: a real list (and REGISTRY_28 is the SAME object), guarded so that reading it with no package
    registered raises instead of returning the short core-only list."""
    def __contains__(self, x): _guard(); return list.__contains__(self, x)
    def __iter__(self): _guard(); return list.__iter__(self)
    def __len__(self): _guard(); return list.__len__(self)
    def __getitem__(self, i): _guard(); return list.__getitem__(self, i)
    def __reversed__(self): _guard(); return list.__reversed__(self)
    def __eq__(self, o): _guard(); return list.__eq__(self, o)
    def __ne__(self, o): _guard(); return list.__ne__(self, o)
    def index(self, *a): _guard(); return list.index(self, *a)
    def count(self, x): _guard(); return list.count(self, x)
    def copy(self): _guard(); return list(list.__iter__(self))
    def __add__(self, o): _guard(); return list(list.__iter__(self)) + list(o)
    def __radd__(self, o): _guard(); return list(o) + list(list.__iter__(self))
    __hash__ = None


class _CompositeSet(set):
    """REGISTRY_SET: a real set, guarded the same way. The comparison/operator overrides matter because
    `plain_set <= REGISTRY_SET` calls this subclass's reflected method first."""
    def __contains__(self, x): _guard(); return set.__contains__(self, x)
    def __iter__(self): _guard(); return set.__iter__(self)
    def __len__(self): _guard(); return set.__len__(self)
    def __eq__(self, o): _guard(); return set.__eq__(self, o)
    def __ne__(self, o): _guard(); return set.__ne__(self, o)
    def __le__(self, o): _guard(); return set.__le__(self, o)
    def __lt__(self, o): _guard(); return set.__lt__(self, o)
    def __ge__(self, o): _guard(); return set.__ge__(self, o)
    def __gt__(self, o): _guard(); return set.__gt__(self, o)
    def __and__(self, o): _guard(); return set(set.__iter__(self)) & set(o)
    def __or__(self, o): _guard(); return set(set.__iter__(self)) | set(o)
    def __sub__(self, o): _guard(); return set(set.__iter__(self)) - set(o)
    def __xor__(self, o): _guard(); return set(set.__iter__(self)) ^ set(o)
    def __rand__(self, o): _guard(); return set(o) & set(set.__iter__(self))
    def __ror__(self, o): _guard(); return set(o) | set(set.__iter__(self))
    def __rsub__(self, o): _guard(); return set(o) - set(set.__iter__(self))
    def __rxor__(self, o): _guard(); return set(o) ^ set(set.__iter__(self))
    def issubset(self, o): _guard(); return set.issubset(self, o)
    def issuperset(self, o): _guard(); return set.issuperset(self, o)
    def isdisjoint(self, o): _guard(); return set.isdisjoint(self, o)
    def union(self, *o): _guard(); return set(set.__iter__(self)).union(*o)
    def intersection(self, *o): _guard(); return set(set.__iter__(self)).intersection(*o)
    def difference(self, *o): _guard(); return set(set.__iter__(self)).difference(*o)
    def copy(self): _guard(); return set(set.__iter__(self))
    __hash__ = None


REGISTRY = _CompositeList(sorted(CORE_REGISTRY))
REGISTRY_28 = REGISTRY          # DEPRECATED ALIAS — the name is historical; there are 33 ids now.
REGISTRY_SET = _CompositeSet(CORE_REGISTRY)


def _rebuild():
    ids = sorted(CORE_REGISTRY_SET.union(*[set(v) for v in _PACKAGE_OWNED.values()]))
    list.__init__(REGISTRY, ids)                     # IN PLACE: every module's bound reference sees it
    set.clear(REGISTRY_SET); set.update(REGISTRY_SET, ids)


def register_package_categories(system_id, *, owns, uses=(), expected_hash=None, field_category=None):
    """Called BY a roof-system package, at its import, to declare the ids it OWNS (and the core ids it uses).

    RAISES (A2 §1.5): an owned id core already owns; an owned id another package owns; a different
    re-declaration by the same package; a used id that is not core; a package hash other than the one the
    package pinned. An identical re-declaration is idempotent.

    FRAME v98: `field_category` DECLARES which of the owned ids is the package's field covering (Package
    Contract §1 item 6). field_category_id() reads this declaration — never the number of ids a package owns.
    It must be one of `owns`. Optional here so a package that declares none still registers; asking it for
    its field covering then raises."""
    if not isinstance(system_id, str) or not system_id.strip():
        raise ValueError(f"system_id must be a non-empty string; got {system_id!r}")
    owned = tuple(sorted(set(owns)))
    used = tuple(sorted(set(uses)))
    if not owned:
        raise ValueError(f"{system_id}: a package must own at least one category id")
    for cid in owned + used:
        if not isinstance(cid, str) or not cid.strip() or cid != cid.strip():
            raise ValueError(f"{system_id}: category ids must be non-empty strings; got {cid!r}")
    core_clash = [c for c in owned if c in CORE_REGISTRY_SET]
    if core_clash:
        raise ValueError(f"{system_id}: cannot own {core_clash} — core already owns them. A package declares a "
                         f"core id in `uses`, it never re-owns it.")
    not_core = [c for c in used if c not in CORE_REGISTRY_SET]
    if not_core:
        raise ValueError(f"{system_id}: `uses` names {not_core}, which are not core ids. A package may use only "
                         f"core ids; ids it introduces go in `owns`.")
    if field_category is not None and field_category not in owned:
        raise ValueError(f"{system_id}: field_category {field_category!r} is not one of the ids it owns "
                         f"({list(owned)}); a package names its field covering among its own ids.")
    h = registry_fingerprint(owned)
    if expected_hash is not None and h != expected_hash:
        raise ValueError(f"{system_id}: owned-id hash {h} != the package's pinned {expected_hash}")
    prior = _PACKAGE_OWNED.get(system_id)
    if prior is not None:
        if prior == owned and _PACKAGE_USES.get(system_id) == used \
                and _PACKAGE_FIELD.get(system_id) == field_category:
            return h                                  # identical re-declaration: idempotent
        raise ValueError(f"{system_id}: already registered owning {list(prior)}; a different declaration "
                         f"({list(owned)}) is a conflicting registration.")
    for other, ids in _PACKAGE_OWNED.items():
        clash = sorted(set(ids) & set(owned))
        if clash:
            raise ValueError(f"{system_id}: cannot own {clash} — package {other!r} already owns them.")
    _PACKAGE_OWNED[system_id] = owned
    _PACKAGE_USES[system_id] = used
    _PACKAGE_HASHES[system_id] = h
    if field_category is not None:
        _PACKAGE_FIELD[system_id] = field_category
    _rebuild()
    return h


def registered_packages():
    return tuple(sorted(_PACKAGE_OWNED))


def package_registry_hash(system_id):
    """The pinned-able hash of the ids one package owns. RAISES (actionable) when that package is not loaded."""
    require_package(system_id)
    return _PACKAGE_HASHES[system_id]


def package_categories(system_id):
    require_package(system_id)
    return _PACKAGE_OWNED[system_id]


def composite_registry_hash():
    """registry_fingerprint(core ∪ every registered package). Equals REGISTRY_HASH with only wood_shake loaded."""
    _guard()
    return registry_fingerprint(list.__iter__(REGISTRY))


def require_package(system_id):
    """RAISES with an actionable message when a package the caller needs has not registered."""
    if system_id not in _PACKAGE_OWNED:
        if not _PACKAGE_OWNED:
            raise _no_package_error()
        raise RegistryWiringError(
            f"FRAME wiring: roof-system package {system_id!r} has not registered its category ids "
            f"(registered: {list(registered_packages())}). This is missing wiring, not a data problem. Fix: "
            f"import {system_id}'s category module before reading its ids.")


def validate_category_id(category_id):
    """Return category_id if it is core or owned by a registered package; RAISE otherwise. UNMAPPED is a core
    id and is the legitimate catch-all for anything unrecognised."""
    _guard()
    if category_id in CORE_REGISTRY_SET or any(category_id in ids for ids in _PACKAGE_OWNED.values()):
        return category_id
    raise ValueError(f"category id {category_id!r} is in neither the core registry nor any registered package "
                     f"(registered: {list(registered_packages())}). Map it to UNMAPPED for human review, or load "
                     f"the package that owns it.")


assert registry_fingerprint(CORE_REGISTRY) == CORE_REGISTRY_HASH, "core registry changed without its hash"


# =============================================================================================
# FRAME v98 — "WHICH CATEGORY IS THE FIELD COVERING?" (A2 group A; v98 prompt C-1, C-2, C-3)
# =============================================================================================
# Core asks; the registered package answers. Resolved from the field id the package DECLARED when it registered
# (register_package_categories(field_category=...), QA v98 call 1) — at CALL time, never at import. Zero arguments (C-2): no call site has a system to pass, and
# an optional one would be the default-shaped shortcut this build removes.
#
# BRIDGE 4: with ONE package registered the answer is unambiguous; with zero there is none, and with two core
# MUST NOT PICK — both RAISE (C-3, the v97 precedent). Retires at the ScopeLine enrichment carrying
# material_profile_id (A1 §5, Roadmap §6), when a line states its own system — NOT at Migration Plan step 4
# with bridges 1-3.
def field_category_id():
    """The category id of the field covering, as DECLARED by the ONE registered roof-system package. RAISES
    (RegistryWiringError, actionable, never a default) on zero packages, on two or more, and when the one package
    declared no field category. It never infers the answer from how many ids a package owns (asphalt will own a
    field id AND DOUBLE_STARTER)."""
    pk = registered_packages()
    if not pk:
        raise RegistryWiringError(
            "FRAME wiring: field_category_id() was asked which category is the field covering, but no "
            "roof-system package has registered, so there is no answer. This is missing wiring, not a data "
            "problem. Fix: import the installed package's category module (the bridge's shared boot helper does "
            "this for every page) before computing scope, keying, comparisons or reports.")
    if len(pk) > 1:
        raise RegistryWiringError(
            f"FRAME bridge 4: {len(pk)} roof-system packages are registered ({list(pk)}), so 'which category is "
            f"the field covering?' has more than one answer and core will not pick one. This is the hard gate on "
            f"a second roofing package, not a data problem. Fix: take the field id from the line's own system "
            f"(ScopeLine.material_profile_id — bridge 4's retirement), not from this claim-level lookup.")
    if pk[0] not in _PACKAGE_FIELD:
        raise RegistryWiringError(
            f"FRAME wiring: package {pk[0]!r} registered its category ids but declared no field category, so the "
            f"registry cannot say which is its field covering. Fix: pass field_category=<its field id> to "
            f"register_package_categories in its category module (Package Contract §1 item 6).")
    return _PACKAGE_FIELD[pk[0]]


# =============================================================================================
# POWER ATTIC VENT — ONE TYPE, TWO OPERATIONS. **THE FAN CARVES. THE COVER DOES NOT.**
# =============================================================================================
# Binding domain rule (Joseph). A roof-mount power attic vent is detected by EagleView as an
# ordinary PENETRATION, and carriers write it as its own line — Devore's Travelers estimate has
# "12. R&R Roof mount power attic vent  1.00 EA" listed SEPARATELY from
# '11. Exhaust cap - through roof - up to 4"  4.00 EA'. They are NOT the same item and must never
# be conflated: mapping the power vent to VENT_CAP would mis-compare against the carrier.
#
# The two operations differ in EXACTLY ONE THING — whether the shake field is disturbed:
#
#   COVER ONLY   POWER_VENT 1 EA.  ZERO affected area. Nothing is carved. The cover lifts off the
#                                  existing curb; the surrounding shakes are never opened.
#   FAN / UNIT   POWER_VENT 1 EA.  NORMAL footprint carve, exactly like any other appurtenance —
#                                  the unit comes out of the deck, so the field around it is opened.
#
# THIS IS NOT AN ACCESSORY/REPAIR DISTINCTION. It is two operations on ONE type. Both emit the same
# material line; only the carve differs.
#
# APPURT_IWS MUST FALL OUT FOR FREE. module2_scope_expansion emits APPURT_IWS only when the
# appurtenance's affected_SF > 0. A cover-only vent is therefore given NO appurtenance geometry at
# all, so its affected_SF is 0 and the ice & water simply never fires. There is NO if-statement
# suppressing IWS anywhere, and there must never be one: if you find yourself writing one, the
# carve has been modelled in the wrong place.
#
# WHY THE PREDICATE LIVES HERE: the carve is decided in TWO independent places — module2_assembly
# (the SCOPE) and module1_service (the DIAGRAM). This project has shipped the same bug five times by
# letting two consumers each hold their own copy of a rule; the v56 transition-band bug was exactly
# that. One authority, imported by both. This module is the shared vocabulary, it is imported
# everywhere already, and it depends on nothing (hashlib only), so it cannot create a cycle.
POWER_VENT_CATEGORY = "POWER_VENT"
POWER_VENT_COVER = "COVER"          # cover only  -> carves NOTHING
POWER_VENT_FAN = "FAN"              # fan / full unit -> normal footprint carve
POWER_VENT_OPERATIONS = (POWER_VENT_COVER, POWER_VENT_FAN)

# What page 2 may send, normalized. Anything else is not a recognised assertion.
_POWER_VENT_OPERATION_ALIASES = {
    "COVER": POWER_VENT_COVER, "COVER_ONLY": POWER_VENT_COVER, "COVER ONLY": POWER_VENT_COVER,
    "FAN": POWER_VENT_FAN, "UNIT": POWER_VENT_FAN, "FAN_UNIT": POWER_VENT_FAN,
    "FAN / FULL UNIT": POWER_VENT_FAN, "FULL_UNIT": POWER_VENT_FAN, "FULL UNIT": POWER_VENT_FAN,
}


def is_power_vent(row: Optional[Mapping[str, object]]) -> bool:
    """True when this confirmed-selection row is a power attic vent."""
    if not isinstance(row, Mapping):
        return False
    return str(row.get("kind_label") or row.get("type") or "").strip().upper() == POWER_VENT_CATEGORY


def power_vent_operation(row: Optional[Mapping[str, object]]) -> Optional[str]:
    """The normalized operation on a power-vent row, or None if it is not a power vent / not stated.

    NEVER GUESSES. Page 2 makes the choice REQUIRED, so an unstated operation means the payload did
    not come from the UI. See appurtenance_carves for what an unstated operation does."""
    if not is_power_vent(row):
        return None
    raw = str(row.get("operation") or row.get("power_vent_operation") or "").strip().upper()
    return _POWER_VENT_OPERATION_ALIASES.get(raw)


def appurtenance_carves(row: Optional[Mapping[str, object]]) -> bool:
    """Does this appurtenance row disturb the shake field?

    THE ONLY PLACE THIS QUESTION IS ANSWERED. Both the scope (module2_assembly) and the diagram
    (module1_service) import this, so the picture cannot disagree with the numbers.

    Everything carves except a power attic vent whose operation is COVER ONLY.

    FAIL-SAFE ON AN UNSTATED OPERATION: a power-vent row with no recognised operation CARVES. Page 2
    makes the choice required, so this only happens to a hand-built payload — and carving is the
    conservative branch, because it is the one the reviewer can see in the diagram and challenge. The
    dangerous default would be to silently carve nothing and quietly under-scope the claim."""
    if not is_power_vent(row):
        return True
    return power_vent_operation(row) != POWER_VENT_COVER
