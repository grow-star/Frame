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

# =============================================================================================
# FRAME v106.6 — THE POST-LEGACY SHARED TIER, and why it is a third tier rather than more core
#
# Joseph ruled on 2026-11-04 that the flat-roof appurtenance detail is the FLAT FAMILY'S, not one
# package's: "your proposals are good for the MODBIT and really for TPO and EPDM as well." Two of the ids
# it needs belong to NO system — counterflashing is metal (Finding 4: metal belongs to no system, so it
# must MERGE with the steep side's) and a skylight's own detach-and-reset is not roofing material at all.
#
# A package may only `use` ids it does not own, and until now that meant CORE ids. But CORE CANNOT GROW.
# `two_tier_registry_regression` asserts, in its own words, "COMPOSITE == LEGACY 72dc2aee… with only
# wood_shake loaded — PERMANENT (historical receipts verifiable)", and `registry_page_drift_gate` asserts
# the same equality for the live pages. Those receipts have gone to carriers. Adding an id to CORE_REGISTRY
# would retire that guarantee to record a line item, which is the wrong trade and Joseph made the call:
# keep the anchor.
#
# SO THE SHARED TIER IS OWNERLESS, AND IT IS LAZY. A shared id enters the composite REGISTRY only when a
# registered package declares it uses it — exactly as a package's own ids do. With only wood_shake loaded
# no shared id is used, so the composite is bit-for-bit the legacy 72dc2aee and the permanent assertion
# stays literally true rather than being rewritten to stay true.
#
# WHAT BELONGS HERE, and what does not. A shared id is one that more than one package legitimately emits
# AND whose lines must MERGE across them — which is the same physical test as Finding 4: the part is metal,
# or it is not roofing material at all, so it carries no system in its text. A part made OF the membrane
# (a patch, a curb flashing, a parapet flash) is the owning package's, because a MODBIT patch and a TPO
# patch are different materials and must NOT merge. That is why MODBIT's patch id is not here.
SHARED_REGISTRY = (
    "COUNTERFLASHING",      # metal lapping over a membrane's vertical termination. NOT `FLCAP` — that is a
                            # coping cap for the TOP of a parapet (Joseph, 2026-11-01, correcting QA).
    "SKYLIGHT_UNIT",        # the skylight ITSELF: detach-and-reset, or replace when it is damaged. Joseph,
                            # 2026-11-04: a skylight gets no counterflashing because a 4in curb has no room
                            # for one, so the unit comes off instead. Not SKYLIGHT_FLASH, which is the
                            # coursed side's flashing KIT and a different part.
)
SHARED_REGISTRY_SET = frozenset(SHARED_REGISTRY)
_SHARED_IN_USE = set()    # shared ids some registered package declared — the ONLY route into REGISTRY

# The tier's WORDS live with its ids, and they are lazy in exactly the same way. QA put these in core's
# label map first and the page-drift gate caught it within the hour: with only wood shake loaded the label
# map then held two keys the registry did not, and "every page-side copy equals the composite registry" is
# the whole point of that gate. A label that exists for an id that does not is the same drift in miniature.
SHARED_DISPLAY_LABELS = {
    "COUNTERFLASHING": "Counterflashing",
    "SKYLIGHT_UNIT": "Skylight (detach and reset, or replace)",
}


def shared_labels_in_use():
    """{id: label} for the shared ids a registered package actually declared — empty when none has."""
    return {c: SHARED_DISPLAY_LABELS[c] for c in sorted(_SHARED_IN_USE) if c in SHARED_DISPLAY_LABELS}
CORE_REGISTRY_HASH = "7a86a944c0652eb49e15875e9d9adc1c4cc5bc4d53ba3d90bf18f7855ec32d62"
REGISTRY_HASH = "72dc2aee2f78e7e90eda4d4a1c437f4730c922255135371a390cf73931f83da6"   # LEGACY anchor (v74-v96)
LEGACY_REGISTRY_HASH = REGISTRY_HASH

# FRAME v106.6f — THE HISTORICAL RECEIPT NOW STANDS ON ITS OWN DATA.
#
# A2 5.1 records Joseph's requirement 1 verbatim: "Preserve historical registry receipts so existing claims
# remain verifiable even after additional roofing packages are introduced." v97 met it by keeping the live
# composite EQUAL to 72dc2aee with only wood_shake loaded, and the note above this block says the lazy shared
# tier exists so that the assertion "stays literally true rather than being rewritten to stay true."
#
# That held for the event v97 was designed for — a PACKAGE being added — because a package's ids and the
# shared ids are both lazy. It cannot hold when the VOCABULARY grows. A new billable id is reachable with
# wood shake alone whichever tier it is put in: core is never lazy, and a shared or package-owned id enters
# the moment the package that bills it declares it. QA checked all three tiers before touching this.
#
# A2 5.1 anticipates exactly that and says what should happen: verifiability rests on "the core hash and the
# wood-shake package hash [being] each still pinned", and "the composite moving is the correct, visible
# signal that the vocabulary grew."
#
# So the receipt is pinned as DATA here, not as an equality with the live registry. LEGACY_REGISTRY_33 is the
# vocabulary of v74-v96 — the 33 ids any claim of that era was written against — and its fingerprint is
# 72dc2aee, permanently, however much the live registry grows afterwards. A historical claim stays verifiable
# because the list it was written against is still here to check against, which is what requirement 1 asks
# for. The live composite is then free to move, visibly, with its own pinned value.
#
# This is a STRONGER form of the same promise: the old assertion survived package growth only, and this one
# survives both. Nothing about any v74-v96 claim changes.
LEGACY_REGISTRY_33 = (
    "APPURT_IWS", "BOX_VENT", "CHIMNEY_CHASE_COVER", "CHIMNEY_FLASH", "DEBRIS_DISPOSAL",
    "DRIP_EDGE", "ENDWALL_FLASH", "EQUIPMENT", "FIELD_COVERING", "FIELD_FELT",
    "FIELD_TEAROFF", "FLUE_CAP", "GABLE_CORNICE", "GENERAL_LABOR", "HIGH_SLOPE_CHARGE",
    "HIP_CAPS", "IWS", "PIPE_JACK_FLASH", "POWER_VENT", "RIDGE_CAPS",
    "RIDGE_HIP_CAP", "RIDGE_VENT", "ROOFER_LABOR", "SHAKE_FIELD_RR", "SKYLIGHT_FLASH",
    "STARTER", "STEEP_CHARGE", "STEP_FLASH", "TRANSITION_FLASH", "TURBINE_VENT",
    "UNMAPPED", "VALLEY_METAL", "VENT_CAP",
)


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
    # FRAME v106.6: core, plus every registered package's OWN ids, plus only those SHARED ids a registered
    # package declared it uses. The shared tier is lazy by construction — with no package using one, the
    # composite is bit-for-bit what it was before the tier existed, which is what keeps the legacy anchor
    # literally true rather than restated.
    ids = sorted(CORE_REGISTRY_SET.union(_SHARED_IN_USE, *[set(v) for v in _PACKAGE_OWNED.values()]))
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
    # FRAME v106.6: a package may use a CORE id or a SHARED id. Anything else is still a wiring error, and
    # the message names both tiers so the fix is obvious — the old message said "core ids" and would now
    # send a reader looking in the wrong place.
    not_usable = [c for c in used if c not in CORE_REGISTRY_SET and c not in SHARED_REGISTRY_SET]
    if not_usable:
        raise ValueError(f"{system_id}: `uses` names {not_usable}, which are neither core ids nor shared ids "
                         f"(shared: {list(SHARED_REGISTRY)}). A package may use core or shared ids; ids it "
                         f"introduces go in `owns`.")
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
    _SHARED_IN_USE.update(c for c in used if c in SHARED_REGISTRY_SET)
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
    if (category_id in CORE_REGISTRY_SET or category_id in _SHARED_IN_USE
            or any(category_id in ids for ids in _PACKAGE_OWNED.values())):
        return category_id
    # A shared id NOT in use is deliberately invalid: it is vocabulary no loaded package emits, so a line
    # carrying it is a wiring error, not a mapping question. The message says so rather than sending the
    # reader to UNMAPPED.
    if category_id in SHARED_REGISTRY_SET:
        raise ValueError(f"category id {category_id!r} is a SHARED id, but no registered package declares it in "
                         f"`uses` (registered: {list(registered_packages())}). A shared id enters the registry "
                         f"only when a package says it emits it.")
    raise ValueError(f"category id {category_id!r} is in neither the core registry nor any registered package "
                     f"(registered: {list(registered_packages())}). Map it to UNMAPPED for human review, or load "
                     f"the package that owns it.")


assert registry_fingerprint(CORE_REGISTRY) == CORE_REGISTRY_HASH, "core registry changed without its hash"


# =============================================================================================
# FRAME v104c — "WHICH CATEGORY IS THE FIELD COVERING?" is asked PER SYSTEM (bridge 4 narrowed)
# =============================================================================================
# v98 answered it once per claim, from the ONE registered package (bridge 4). A mixed roof has no single answer, so
# the question now names its system: field_category_id(system_id) reads the field id that package DECLARED when it
# registered (register_package_categories(field_category=...)). THE NO-ARGUMENT FORM IS GONE — a call that cannot say
# which system it means was the defect.
#
# Where the system comes from:
#   * a LINE in hand -> its own material, ScopeLine.material_profile_id (set by the engine that made it): line_system();
#   * NO line in hand (a carrier row, a category-keyed map, a serialized report line, a bare category id) ->
#     sole_category_package(), the CATEGORY registry's sole package. BRIDGE 4, NARROWED, NOT RETIRED: those sites are
#     an explicit, listed set (FRAME_v104c_Results.md), and with two packages each raises rather than pick.
# Why the CATEGORY registry and not roof_systems.sole_registered_system(): page 3 boots with the category module only
# and never loads the engine or the geometry, so the roof-system registry is EMPTY there (pinned in v104b). A resolver
# reading it would raise on every carrier row a user entered (FRAME v104c Q3).
def field_category_id(system_id):
    """The category id of `system_id`'s field covering, as that package DECLARED it. RAISES (RegistryWiringError,
    actionable, never a default) on an unregistered system, naming the registered ones, and when the package declared
    no field category. It never infers the answer from how many ids a package owns."""
    if system_id not in _PACKAGE_OWNED:
        raise RegistryWiringError(
            f"FRAME wiring: field_category_id({system_id!r}) — no roof-system package by that id has registered its "
            f"category ids (registered: {list(registered_packages())}). Fix: import that package's category module, or "
            f"pass the system the line actually belongs to (ScopeLine.material_profile_id).")
    if system_id not in _PACKAGE_FIELD:
        raise RegistryWiringError(
            f"FRAME wiring: package {system_id!r} registered its category ids but declared no field category, so the "
            f"registry cannot say which is its field covering. Fix: pass field_category=<its field id> to "
            f"register_package_categories in its category module (Package Contract §1 item 6).")
    return _PACKAGE_FIELD[system_id]


_DEFAULT_PACKAGE = None       # FRAME v106.4: set by roof_systems.register — see set_default_category_package


def set_default_category_package(system_id):
    """FRAME v106.4 — PUSHED DOWN from core/registry/roof_systems.py, so the claim is made ONCE.

    A package declares `claims_unlabelled_profiles=True` at ONE place, its roof-system registration. That
    declaration means "I own the pre-declaration case": a profile with no system_id, a claim with no
    predominant_system_id, and a LINE with no material_profile_id are the same case wearing three hats.
    `shared_category_registry` sits BELOW `roof_systems` in the import order and cannot ask it, so
    `roof_systems.register` tells it instead. The alternative — a second `claims_undeclared` flag on
    register_package_categories — would be the same declaration in two places, which is the defect this
    codebase keeps collapsing; and a package that set one and forgot the other would be silently wrong.

    At most one claimant exists: roof_systems.register enforces that before calling here.
    """
    global _DEFAULT_PACKAGE
    if system_id is not None and system_id not in _PACKAGE_OWNED:
        raise RegistryWiringError(
            f"FRAME wiring: {system_id!r} claims unlabelled profiles but has not registered its category ids. Fix: "
            f"call register_package_categories({system_id!r}, ...) before registering the roof system (a package's "
            f"geometry module imports its own categories module for exactly this reason).")
    _DEFAULT_PACKAGE = system_id


def default_category_package():
    """The package that DECLARED it owns the undeclared case, or None."""
    return _DEFAULT_PACKAGE


def sole_category_package(context="a call with no line in hand"):
    """The category package a site with NO LINE resolves to — it holds no line and so cannot say which system it
    means.

    FRAME v106.4 — BRIDGE 4 RETIRED HERE. This raised whenever two or more packages were registered, which made it
    one of the hard gates on a second roofing package: measured, it took out `manual_carrier_entry` (five gates on
    its own), three sites in the report renderer and two in `module3_caller`. Most of those sites were asking the
    WRONG QUESTION — "which package?" when they only needed "is this category a field covering?" — and now use
    `field_category_ids()` membership instead. What remains is the genuinely line-less case: a line built OUTSIDE an
    engine (the assembly's eave-IWS and ridge-vent lines) carries no material_profile_id, and `line_system` falls
    back here.

    For that case the answer is the package that CLAIMED the undeclared case — the same declaration, pushed down
    from roof_systems (see set_default_category_package). CORE STILL NEVER PICKS: a package declared this.

    Zero packages RAISES. Two or more with NO claimant RAISES, naming them.
    """
    pk = registered_packages()
    if not pk:
        raise RegistryWiringError(
            f"FRAME wiring: {context} — no roof-system package has registered its category ids, so there is no "
            f"answer. This is missing wiring, not a data problem. Fix: import the installed package's category module "
            f"(the bridge's shared boot helper does this for every page).")
    if _DEFAULT_PACKAGE is not None:
        return _DEFAULT_PACKAGE
    if len(pk) > 1:
        raise RegistryWiringError(
            f"FRAME bridge 4: {context} — {len(pk)} roof-system packages are registered ({list(pk)}), NONE claims "
            f"unlabelled profiles, and this site has no line to say which one it means, so core will not pick. Fix: "
            f"give the site a line (ScopeLine.material_profile_id) or a system id, or have the predominant package "
            f"declare claims_unlabelled_profiles at registration. (v106.4)")
    return pk[0]


def line_system(line, context="a line with no material"):
    """The roof system a line belongs to: its own material_profile_id (a ScopeLine, an AggregatedScopeLine or its
    serialized dict). A line that carries none — built outside an engine, or saved by an older version — falls back
    like a line-less site (bridge 4, narrowed): with two packages it raises rather than pick."""
    mat = line.get("material_profile_id") if isinstance(line, Mapping) else getattr(line, "material_profile_id", None)
    return mat if mat not in (None, "") else sole_category_package(context)


def field_category_ids():
    """FRAME v104e: the set of EVERY registered system's declared field-covering id — "is this category a field
    covering?" answered WITHOUT PICKING A PACKAGE. _PACKAGE_FIELD, read across. It never raises on two or more
    packages (that is the point: bridge 4 retires at the sites that only ask this). With no package registered it
    RAISES, like every registry read (missing wiring, never an empty answer), and so it does when a registered package
    declared no field covering — the set would silently be incomplete (field_category_id raises there too)."""
    _guard()
    undeclared = sorted(sysid for sysid in _PACKAGE_OWNED if sysid not in _PACKAGE_FIELD)
    if undeclared:
        raise RegistryWiringError(
            f"FRAME wiring: field_category_ids() — package(s) {undeclared} registered their category ids but declared "
            f"no field category, so the set of field coverings would be incomplete. Fix: pass field_category=<its "
            f"field id> to register_package_categories in that package's category module (Package Contract §1 item 6).")
    return frozenset(_PACKAGE_FIELD.values())


def system_for_field_category(category_id):
    """FRAME v104e: the system that DECLARES `category_id` as its field covering, or None when it is not a field
    covering — "whose?", for the per-system figures. _PACKAGE_FIELD, inverted; one id belongs to at most one package
    (ownership is exclusive), so this never picks and never raises on two or more packages. With no package
    registered it RAISES, like every registry read."""
    _guard()
    return next((sysid for sysid, fid in _PACKAGE_FIELD.items() if fid == category_id), None)


# FRAME v104c — MERGE OR SPLIT ACROSS ROOF SYSTEMS (Joseph, 2026-10-31; ledger entry 89). A property of the CATEGORY,
# declared once, here, beside the ids. It decides only whether a line's MATERIAL joins the aggregation key; the item
# text is ALWAYS in the key (v77: group by the user's label), and Joseph: "one line only if it's genuinely the same
# product". So a MERGED category sums two systems' lines only when they name the same product; a SPLIT category keeps
# two systems apart even when their text matches. A category a package OWNS always splits (two packages cannot own one
# id). ANY SHARED ID WITHOUT A RULING SPLITS (QA v104c Q2): an unruled merge would silently sum two physical
# materials; an unruled split only shows a line a user can combine — wrong in the recoverable direction. Declared
# against the core ids directly — never by growing a package's USES (that moves its hash).
#
# FRAME v104d — JOSEPH'S RULINGS (ledger entry 93): every emitted unruled id MERGES, "merge like kind" — "IWS is the
# same no matter what roof surface. Step flashing merge. ... Metals are metals. ... Ridge vent merge. Why? Ridge and
# hip caps are different than ridge vent." The principle behind the whole table: material joins the key only for the
# roof surface itself and the pieces CUT FROM IT (field, tear-off, starter, ridge/hip caps); a manufactured part that
# sits on the roof (a vent, a flashing, a metal) is like kind across coverings. Labour is ruled as a kind
# (ROOFER_LABOR named). FRAME v104e (ledger entry 98): DEBRIS_DISPOSAL, EQUIPMENT and FLUE_CAP are ruled MERGE too,
# completing the table — inert today (no scope emitter reaches them, and carrier rows never enter _aggregate_lines).
# THE DEFAULT STAYS SPLIT: material_splits reads the MERGED list, so a future core id defaults to split, never to a
# silent sum of two physical materials.
MATERIAL_MERGED_CATEGORIES = frozenset({
    "APPURT_IWS", "BOX_VENT", "CHIMNEY_CHASE_COVER",
    "CHIMNEY_FLASH", "DEBRIS_DISPOSAL", "DRIP_EDGE", "ENDWALL_FLASH",
    "EQUIPMENT", "FIELD_FELT", "FLUE_CAP", "GABLE_CORNICE", "GENERAL_LABOR",
    "HIGH_SLOPE_CHARGE", "IWS", "PIPE_JACK_FLASH",
    "POWER_VENT", "RIDGE_VENT", "ROOFER_LABOR",
    "SKYLIGHT_FLASH", "STEEP_CHARGE", "STEP_FLASH",
    "TRANSITION_FLASH", "TURBINE_VENT", "UNMAPPED",
    "VALLEY_METAL", "VENT_CAP",
})
MATERIAL_SPLIT_CATEGORIES = frozenset({"RIDGE_CAPS", "HIP_CAPS", "RIDGE_HIP_CAP", "STARTER", "FIELD_TEAROFF",
                                       "FIELD_COVERING"})


def material_splits(category_id):
    """True when a line's material joins the aggregation key for `category_id` (two systems stay apart)."""
    return category_id not in MATERIAL_MERGED_CATEGORIES


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


# =============================================================================================
# FRAME v106.6 — THE SKYLIGHT'S OWN OPERATION, on the POWER_VENT pattern and deliberately not a new one
#
# Joseph, 2026-11-04: "Skylight doesn't get counterflashing… there's not typically room. A skylight curb is
# minimum 4", so either skylight needs detached & Reset or replaced depending on if there's damage to the
# skylight." So on a membrane the skylight UNIT comes off instead of being counterflashed — and whether it
# goes back on or is replaced is a DAMAGE judgement FRAME cannot see.
#
# This is the same shape the power vent already has, and the same reasoning applies word for word: one
# appurtenance type, two operations, and a SECOND human assertion that materially changes the scope, so it
# is never automatic. Reusing that shape rather than inventing a second one is the point (the sidewall
# ruling's own note: "Do not invent a second mechanism for this").
SKYLIGHT_CATEGORY = "SKYLIGHT"
SKYLIGHT_RESET = "RESET"            # detach and reset — the skylight is sound
SKYLIGHT_REPLACE = "REPLACE"        # the skylight itself is damaged
SKYLIGHT_OPERATIONS = (SKYLIGHT_RESET, SKYLIGHT_REPLACE)

_SKYLIGHT_OPERATION_ALIASES = {
    "RESET": SKYLIGHT_RESET, "D&R": SKYLIGHT_RESET, "DR": SKYLIGHT_RESET,
    "DETACH_AND_RESET": SKYLIGHT_RESET, "DETACH & RESET": SKYLIGHT_RESET,
    "DETACH AND RESET": SKYLIGHT_RESET, "DETACHED & RESET": SKYLIGHT_RESET,
    "REPLACE": SKYLIGHT_REPLACE, "REPLACEMENT": SKYLIGHT_REPLACE, "NEW": SKYLIGHT_REPLACE,
}


def is_skylight(row):
    """Is this appurtenance row a skylight? Reads the same key the carve test reads, so one payload shape."""
    if not isinstance(row, Mapping):
        return False
    return str(row.get("kind_label") or row.get("type") or "").strip().upper() == SKYLIGHT_CATEGORY


def skylight_operation(row):
    """The normalized operation on a skylight row, or None when it is not a skylight / not stated.

    NEVER GUESSES, and unlike the power vent there is no fail-safe branch to fall back on: a power vent that
    does not say carves, because carving is the conservative answer. A skylight that does not say has no
    conservative answer — reset and replace are different materials, not different areas — so the caller
    emits the line at CONFIRM with the operation unstated rather than picking one."""
    if not is_skylight(row):
        return None
    raw = str(row.get("operation") or row.get("skylight_operation") or "").strip().upper()
    return _SKYLIGHT_OPERATION_ALIASES.get(raw)


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


def user_category_or_unmapped(other_category):
    """A user-supplied OTHER category, validated against this registry — or UNMAPPED for human review.

    THE ONE COPY OF THIS RULE. page2.html states the contract in its own words, beside the list of
    categories it offers: "The engine still validates against REGISTRY_28, so this is purely a UI guard
    - no engine change." The coursed side did validate; the membrane side did not, and emitted whatever
    string the payload carried as a category id. Measured on v106.6f: a MODBIT facet given
    other_category "totally bogus !!" billed a line whose category_id WAS "totally bogus !!", which the
    comparison then has to match and the report has to print. The coursed side routed the same payload
    to UNMAPPED, which UNMAPPED_REVIEW surfaces for a human.

    WHICH AUTHORITY, and why this one: REGISTRY is the LIVE composite, not a frozen list. With both
    packages registered it carries 37 ids including MODBIT_FIELD_RR and MODBIT_PATCH, so validating a
    membrane facet's category against it cannot wrongly reject a category MODBIT itself owns. A package
    that registers new ids widens this check by registering, not by editing it.

    This is deliberately NOT per-package behaviour. What a covering does when disturbed is the package's
    business; what counts as a category id at all is the registry's, and two packages answering it
    differently is the divergence this function exists to end."""
    cat = str(other_category).strip() if other_category else ""
    return cat if cat in REGISTRY else "UNMAPPED"
