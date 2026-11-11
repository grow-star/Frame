"""
core/contracts/project_config.py — the versioned ProjectConfig and THE material resolver (FRAME ARC-03a).
=========================================================================================================
ONE schema, ONE resolver. A project is declared once, at intake (page 1), and carried intact through page 2,
browser storage, the JavaScript bridge, the Python seam and the saved claim. This module owns the schema
(schema_version 1), its validation against the measured roof, and the single function that decides which material
profile — and therefore which roof-system package — a facet carries.

Shared core NAMES NO ROOF SYSTEM AND NO PACKAGE SETTING. Every system id and every setting name it handles is data:
the system ids come from the registry (core/registry/roof_systems.py), the setting names from each package's own
`profile_settings` declaration, and the setting values are checked by the package's own resolver.

PRECEDENCE (owner decision D1, ARC-03a assignment §2.2) — per facet, never once per claim:
    1. materials.by_facet[facet_id]          a facet exception
    2. materials.by_structure[structure_id]  the facet's <ROOF> structure, as the parser read it
    3. materials.default                     the declared project default profile
    4. otherwise MaterialDeclarationMissing  a named, user-actionable error. Never the unlabelled-profile claimant,
                                             never the first registered package, never a zero.
A ROOF SECTION level (between structure and facet) is RESERVED: the measurement input carries no reliable section
identity yet, so none is invented here. A `by_section` key is refused, by name, until a later slice defines it.

CANONICAL JSON (schema_version 1) — see ARC03a_Project_Config_and_Claim_Schema.md for the field-by-field contract:
    {
      "schema_version": 1,
      "project_id": "<stable id, created once>",
      "job_objective": "repair_analysis",
      "materials": {"default": "<profile_id>" | null,
                    "by_structure": {"<ROOF id>": "<profile_id>"},
                    "by_facet": {"<face id>": "<profile_id>"},
                    "profiles": {"<profile_id>": {"system_id": "<installed id>", "label": "<optional>",
                                                  "settings": {<the package's declared settings>},
                                                  "measurement_source": "USER_MEASURED" | "USER_SELECTED_PRESET"
                                                                         | "USER_DECLARED",
                                                  "preset_id": "<only with USER_SELECTED_PRESET>"}}},
      "source": {"kind": "EAGLEVIEW_XML", "record_id": "sha256:<hex of the XML text, UTF-8>",
                 "file_name": "<name>" | null, "facet_structures": {"<face id>": "<ROOF id or ''>"}},
      "selection": {...}        # ONLY in a saved claim / confirmed claim: the confirmed page-2 selection itself
    }
On a selection travelling to the engine the header rides under roof_systems.PROJECT_CONFIG_KEY ("project_config")
and carries no `selection` (the selection is the envelope it rides in).
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping

import roof_systems as _RS

SCHEMA_VERSION = 1
CLAIM_FORMAT = "frame-claim"
# The objectives the charter names. Only the existing repair-analysis path (with its optional carrier comparison)
# is selectable in ARC-03a; the other two are RESERVED for ARC-07 routing and are refused as "not yet available",
# never simulated.
JOB_OBJECTIVES = ("repair_analysis", "quick_estimate", "carrier_comparison")
SELECTABLE_JOB_OBJECTIVES = ("repair_analysis",)
MEASUREMENT_SOURCES = ("USER_MEASURED", "USER_SELECTED_PRESET", "USER_DECLARED")
SOURCE_KINDS = ("EAGLEVIEW_XML",)
RESERVED_MATERIAL_LEVELS = ("by_section",)

HEADER_KEYS = ("schema_version", "project_id", "job_objective", "materials", "source")
MATERIAL_KEYS = ("default", "by_structure", "by_facet", "profiles")
PROFILE_KEYS = ("system_id", "label", "settings", "measurement_source", "preset_id")
SOURCE_KEYS = ("kind", "record_id", "file_name", "facet_structures")


class ProjectConfigError(ValueError):
    """A ProjectConfig is malformed, inconsistent with the measured roof, or names something not installed. The
    message says what is wrong and how to fix it. Nothing is guessed."""


class MaterialDeclarationMissing(ProjectConfigError):
    """A facet that must be scoped has no declared material: no facet exception, no structure assignment and no
    project default. User-actionable: declare the roof system for the project (page 1), its structure, or the
    facet (page 2)."""


# --------------------------------------------------------------------------------------------- source identity
def source_record_id(xml_text: str) -> str:
    """The measurement record's identity: sha256 of the XML text exactly as received, UTF-8."""
    return "sha256:" + hashlib.sha256(str(xml_text).encode("utf-8")).hexdigest()


def facet_structures_from_geometry(geom) -> dict:
    """{face_id: structure_id} for the roof's ROOF faces, from the PARSER's <ROOF> nesting (structure_id "" when the
    XML has no ROOF nesting). Deterministic: sorted by id. Never derived from a carrier estimate."""
    faces = getattr(geom, "roof_faces", None)
    if faces is None:
        raise ProjectConfigError("FRAME ARC-03a: facet_structures_from_geometry needs parsed EagleView geometry")
    return {str(fid): str(getattr(f, "structure_id", "") or "") for fid, f in sorted(faces.items(), key=_id_key)}


def build_source(xml_text: str, geom, file_name=None) -> dict:
    """The `source` block for a project measured from this XML (the shape page 1 builds in the browser)."""
    return {"kind": "EAGLEVIEW_XML", "record_id": source_record_id(xml_text),
            "file_name": None if file_name in (None, "") else str(file_name),
            "facet_structures": facet_structures_from_geometry(geom)}


def _id_key(item):
    v = str(item[0] if isinstance(item, tuple) else item)
    prefix = "".join(ch for ch in v if not ch.isdigit())
    digits = "".join(ch for ch in v if ch.isdigit())
    return (prefix, int(digits or "0"), v)


# ------------------------------------------------------------------------------------------------- validation
def _fail(msg):
    raise ProjectConfigError("FRAME ARC-03a ProjectConfig: " + msg)


def _require_mapping(v, where):
    if not isinstance(v, Mapping):
        _fail(f"{where} must be an object; got {type(v).__name__}")
    return v


def _unknown_keys(obj, allowed, where):
    extra = sorted(set(obj) - set(allowed))
    if extra:
        if where == "materials" and any(k in RESERVED_MATERIAL_LEVELS for k in extra):
            _fail(f"materials carries {extra}. The ROOF SECTION level is RESERVED: the measurement input has no "
                  f"reliable section identity yet, so ARC-03a does not implement it. Use by_structure or by_facet.")
        _fail(f"{where} carries unknown field(s) {extra}; schema_version {SCHEMA_VERSION} allows {list(allowed)}")


def validate_profile(profile_id, profile) -> dict:
    """Validate ONE declared profile and return the package-validated profile (the package's resolver output).

    The profile must name an INSTALLED system explicitly (no claimant fills a missing system_id), carry every setting
    that package declares (no package default fills a gap), use only that package's settings, label its provenance,
    and pass the package's own resolver. A profile labelled USER_SELECTED_PRESET must name a preset of that package
    and carry exactly that preset's settings — so a typed measurement cannot be relabelled as a preset."""
    where = f"materials.profiles[{profile_id!r}]"
    if not isinstance(profile_id, str) or not profile_id.strip():
        _fail(f"a profile id must be a non-empty string; got {profile_id!r}")
    p = _require_mapping(profile, where)
    _unknown_keys(p, PROFILE_KEYS, where)
    sid = p.get("system_id")
    if not isinstance(sid, str) or not sid.strip():
        _fail(f"{where} has no system_id. A schema_version {SCHEMA_VERSION} profile must name its roof system "
              f"explicitly; no package is assumed. Installed: {list(_RS.registered())}.")
    if sid not in _RS.registered():
        _fail(f"{where} names roof system {sid!r}, which is not installed (installed: {list(_RS.registered())}). "
              f"Fix: choose an installed roof system.")
    decl = _RS.profile_declaration(sid)
    if decl is None:
        _fail(f"{where}: roof system {sid!r} declares no profile settings, so it cannot be assigned in a "
              f"schema_version {SCHEMA_VERSION} project yet.")
    label = p.get("label")
    if label is not None and not isinstance(label, str):
        _fail(f"{where}.label must be a string when given")
    settings = _require_mapping(p.get("settings"), f"{where}.settings")
    declared = decl["settings"]
    extra = sorted(set(settings) - set(declared))
    if extra:
        _fail(f"{where}.settings carries {extra}, which roof system {sid!r} does not declare (it declares "
              f"{sorted(declared)}). No cross-package setting is accepted.")
    for name, spec in sorted(declared.items()):
        if name not in settings:
            _fail(f"{where}.settings is missing {name!r}. Every setting roof system {sid!r} declares must be chosen "
                  f"or entered by the user; none is filled from a package default.")
        v = settings[name]
        if v is None and not spec.get("nullable"):
            _fail(f"{where}.settings[{name!r}] is null; roof system {sid!r} requires a value.")
        if v is not None and spec.get("choices") is not None and v not in spec["choices"]:
            _fail(f"{where}.settings[{name!r}] = {v!r} is not one of {spec['choices']}.")
    src = p.get("measurement_source")
    if src not in MEASUREMENT_SOURCES:
        _fail(f"{where}.measurement_source must be one of {list(MEASUREMENT_SOURCES)}; got {src!r}")
    preset_id = p.get("preset_id")
    if src == "USER_SELECTED_PRESET":
        presets = decl.get("presets") or {}
        if preset_id not in presets:
            _fail(f"{where} is labelled USER_SELECTED_PRESET but names preset {preset_id!r}; roof system {sid!r} "
                  f"offers {sorted(presets)}.")
        want = presets[preset_id]["settings"]
        if {k: settings.get(k) for k in want} != want:
            _fail(f"{where} is labelled as preset {preset_id!r} but its settings differ from that preset "
                  f"({ {k: settings.get(k) for k in want} } vs {want}). Values the user entered are USER_MEASURED.")
    elif preset_id is not None:
        _fail(f"{where} names preset_id {preset_id!r} but is labelled {src}; only USER_SELECTED_PRESET names a preset.")
    try:
        resolved = _RS.get(sid).resolve_profile({**dict(settings), "system_id": sid})
    except ValueError as e:
        raise ProjectConfigError(f"FRAME ARC-03a ProjectConfig: {where} was refused by roof system {sid!r}: {e}") from e
    if dict(resolved).get("system_id") not in (None, sid):
        _fail(f"{where}: roof system {sid!r} resolved the profile as {dict(resolved).get('system_id')!r}")
    return dict(resolved)


def validate_header(cfg) -> dict:
    """Shape-validate a ProjectConfig header (no geometry needed). Returns a deep copy. Raises ProjectConfigError."""
    c = _require_mapping(cfg, "project_config")
    _unknown_keys(c, HEADER_KEYS + ("selection",), "project_config")
    ver = c.get("schema_version")
    if isinstance(ver, bool) or not isinstance(ver, int):
        _fail(f"schema_version must be the integer {SCHEMA_VERSION}; got {ver!r}")
    if ver != SCHEMA_VERSION:
        _fail(f"schema_version {ver} is not supported by this build (it reads schema_version {SCHEMA_VERSION}). "
              f"A newer file needs a newer build; nothing was interpreted.")
    pid = c.get("project_id")
    if not isinstance(pid, str) or not pid.strip():
        _fail("project_id must be a non-empty string, created once at intake")
    obj = c.get("job_objective")
    if obj not in JOB_OBJECTIVES:
        _fail(f"job_objective must be one of {list(JOB_OBJECTIVES)}; got {obj!r}")
    if obj not in SELECTABLE_JOB_OBJECTIVES:
        _fail(f"job_objective {obj!r} is reserved for a later slice (ARC-07) and is not available in this build; "
              f"available: {list(SELECTABLE_JOB_OBJECTIVES)}")
    m = _require_mapping(c.get("materials"), "materials")
    _unknown_keys(m, MATERIAL_KEYS, "materials")
    profiles = _require_mapping(m.get("profiles"), "materials.profiles")
    if not profiles:
        _fail("materials.profiles is empty: a project must declare at least one material profile")
    for pid_, prof in profiles.items():
        validate_profile(pid_, prof)
    default = m.get("default")
    if default is not None and default not in profiles:
        _fail(f"materials.default names profile {default!r}, which is not in materials.profiles ({sorted(profiles)})")
    for level in ("by_structure", "by_facet"):
        mp = _require_mapping(m.get(level, {}), f"materials.{level}")
        for k, v in mp.items():
            if not isinstance(k, str) or (level == "by_facet" and not k.strip()):
                _fail(f"materials.{level} keys must be non-empty id strings; got {k!r}")
            if v not in profiles:
                _fail(f"materials.{level}[{k!r}] names profile {v!r}, which is not in materials.profiles "
                      f"({sorted(profiles)})")
    s = _require_mapping(c.get("source"), "source")
    _unknown_keys(s, SOURCE_KEYS, "source")
    if s.get("kind") not in SOURCE_KINDS:
        _fail(f"source.kind must be one of {list(SOURCE_KINDS)}; got {s.get('kind')!r}")
    rid = s.get("record_id")
    if not isinstance(rid, str) or not rid.startswith("sha256:") or len(rid) != 71:
        _fail(f"source.record_id must be 'sha256:<64 hex>' of the measurement XML; got {rid!r}")
    if s.get("file_name") is not None and not isinstance(s.get("file_name"), str):
        _fail("source.file_name must be a string or null")
    fs = _require_mapping(s.get("facet_structures"), "source.facet_structures")
    if not fs:
        _fail("source.facet_structures is empty: the source must identify the roof's facets")
    for k, v in fs.items():
        if not isinstance(k, str) or not k.strip() or not isinstance(v, str):
            _fail(f"source.facet_structures must map face id -> structure id string; got {k!r}: {v!r}")
    return copy.deepcopy(dict(c))


def validate_project_config(cfg, *, xml_text=None, geometry=None, selection=None) -> dict:
    """FULL validation of a ProjectConfig header: shape, profiles (through each package's resolver), and — when the
    roof is given — its identity against THIS measurement: the source record id must match the XML, the facet ->
    structure map must equal the parser's, and every by_structure / by_facet key must name a structure / ROOF facet
    of this roof. With `selection`, exclusions are checked: a facet exception on an excluded facet is refused (an
    override never silently puts an excluded facet back in scope), and every in-scope roof facet must resolve.
    Returns the validated header (deep copy, without `selection`)."""
    c = validate_header(cfg)
    c.pop("selection", None)
    if geometry is None and xml_text is not None:
        from eagleview_geometry_parser import parse_eagleview_geometry
        geometry = parse_eagleview_geometry(xml_text)
    if xml_text is not None and c["source"]["record_id"] != source_record_id(xml_text):
        _fail(f"source.record_id {c['source']['record_id'][:19]}… does not identify this XML "
              f"({source_record_id(xml_text)[:19]}…). The project was declared for a different measurement.")
    if geometry is not None:
        parsed = facet_structures_from_geometry(geometry)
        declared = dict(c["source"]["facet_structures"])
        if declared != parsed:
            missing = sorted(set(parsed) - set(declared), key=_id_key)
            unknown = sorted(set(declared) - set(parsed), key=_id_key)
            moved = sorted((f for f in set(parsed) & set(declared) if parsed[f] != declared[f]), key=_id_key)
            _fail(f"source.facet_structures does not match the parser's facets for this roof "
                  f"(missing {missing}, not on this roof {unknown}, structure differs {moved}).")
        structures = {s for s in parsed.values() if s}
        for sid in c["materials"].get("by_structure", {}):
            if sid not in structures:
                _fail(f"materials.by_structure names structure {sid!r}, which this roof does not have "
                      f"(its structures: {sorted(structures)}).")
        for fid in c["materials"].get("by_facet", {}):
            if fid not in parsed:
                _fail(f"materials.by_facet names {fid!r}, which is not a roof facet of this roof.")
    if selection is not None:
        excluded = _RS.excluded_facets(selection)
        clash = sorted(excluded & set(c["materials"].get("by_facet", {})), key=_id_key)
        if clash:
            _fail(f"{clash} are excluded from this scope AND carry a facet material exception. An override cannot "
                  f"put an excluded facet back in scope. Fix: remove the exception, or include the facet.")
        # EVERY roof facet must resolve — excluded ones included. An exclusion takes a facet out of the SCOPE, not out
        # of the roof: the assembly still asks an excluded facet's covering where it borders a scoped one (a system
        # boundary), exactly as it always has, so an excluded facet resolves by structure / default like any other
        # (it may not carry a facet exception — refused above). Undeclared is refused HERE, before anything computes.
        facets = sorted(c["source"]["facet_structures"], key=_id_key)
        undeclared = [f for f in facets if _resolve_or_none(f, c) is None]
        if undeclared:
            ex = [f for f in undeclared if f in excluded]
            raise MaterialDeclarationMissing(
                f"FRAME ARC-03a: no roof system is declared for {undeclared}"
                + (f" (excluded from the scope but still on the roof: {ex})" if ex else "")
                + ". Nothing is assumed. Fix: declare the project's roof system on page 1 or assign the structure; "
                  "a scoped facet may instead take a facet exception on page 2.")
    return c


# --------------------------------------------------------------------------------------------- THE RESOLVER
def structure_for_facet(facet_id, project_config) -> str:
    """The facet's <ROOF> structure id, from the project's parser-provided source map. A facet the source does not
    identify RAISES with a precise diagnostic; nothing is fabricated."""
    fs = ((project_config or {}).get("source") or {}).get("facet_structures")
    if not isinstance(fs, Mapping):
        _fail("source.facet_structures is missing, so no facet can be placed on a structure")
    fid = str(facet_id)
    if fid not in fs:
        _fail(f"facet {fid!r} is not in this project's measurement source (source.facet_structures), so its "
              f"structure cannot be determined. Nothing is guessed: re-declare the project from this XML.")
    return str(fs[fid])


def resolve_material_for_facet(facet_id, structure_id, project_config):
    """THE material resolver. -> (profile_id, system_id, validated_profile). Precedence, per facet:
    by_facet -> by_structure -> default -> MaterialDeclarationMissing. Never a claimant, never registration order.
    `structure_id` may be None/"" only when no structure assignment could apply; if the project assigns structures
    and the facet's structure is unknown, it RAISES rather than skip the structure level."""
    m = (project_config or {}).get("materials")
    if not isinstance(m, Mapping):
        _fail("materials is missing")
    profiles = m.get("profiles") or {}
    fid = str(facet_id)
    pid = (m.get("by_facet") or {}).get(fid)
    if pid is None:
        by_structure = m.get("by_structure") or {}
        if by_structure and structure_id in (None, ""):
            _fail(f"facet {fid!r} has no structure in the measurement source, but this project assigns materials by "
                  f"structure ({sorted(by_structure)}). Its structure cannot be determined, so the structure level "
                  f"cannot be applied. Fix: assign facet {fid!r} on page 2.")
        pid = by_structure.get(str(structure_id)) if structure_id not in (None, "") else None
    if pid is None:
        pid = m.get("default")
    if pid is None:
        raise MaterialDeclarationMissing(
            f"FRAME ARC-03a: facet {fid!r} (structure {structure_id or 'none'}) has no declared roof system — no "
            f"facet exception, no structure assignment and no project default. Nothing is assumed. Fix: declare the "
            f"project's roof system on page 1, or assign this structure / facet.")
    if pid not in profiles:
        _fail(f"facet {fid!r} resolves to profile {pid!r}, which is not in materials.profiles ({sorted(profiles)})")
    resolved = validate_profile(pid, profiles[pid])
    return pid, profiles[pid]["system_id"], resolved


def resolve_facet(facet_id, project_config):
    """resolve_material_for_facet with the facet's structure taken from the project's source map."""
    return resolve_material_for_facet(facet_id, structure_for_facet(facet_id, project_config), project_config)


MEMBER_JOIN = "+"   # how the assembly names a merged (notch) component: its member face ids joined ('F21+F22')


def resolve_facet_or_members(facet_id, project_config):
    """resolve_facet for a facet id, or — for a merged component the assembly names by its members joined with '+'
    (a notch: 'F21+F22') — each member resolved on its own. The members must carry ONE profile; members on
    different profiles sit on a material boundary, which core refuses rather than guess (as system_for_facets
    refuses a merge spanning systems). Returns (profile_id, system_id, validated_profile)."""
    fid = str(facet_id)
    fs = ((project_config or {}).get("source") or {}).get("facet_structures") or {}
    if fid in fs or MEMBER_JOIN not in fid:
        return resolve_facet(fid, project_config)
    per = [(m, resolve_facet(m, project_config)) for m in fid.split(MEMBER_JOIN)]
    distinct = {r[0] for _m, r in per}
    if len(distinct) != 1:
        _fail(f"merged component {fid!r} spans facets carrying DIFFERENT material profiles ("
              + ", ".join(f"{m}: {r[0]} ({r[1]})" for m, r in per)
              + "). That is a material boundary, which core will not guess.")
    return per[0][1]


def _resolve_or_none(facet_id, cfg):
    try:
        return resolve_facet(facet_id, cfg)
    except MaterialDeclarationMissing:
        return None


def resolve_all(project_config, facet_ids) -> dict:
    """{facet_id: (profile_id, system_id)} for the given facets, each resolved on its own."""
    return {str(f): resolve_facet(f, project_config)[:2] for f in facet_ids}


def material_profile_for_facet(facet_id, project_config) -> dict:
    """The OPAQUE material-aware handoff for M1Interface.material_profile: which profile this facet carries, whose
    package owns it, and that package's validated profile. Core reads nothing inside it."""
    pid, sid, resolved = resolve_facet_or_members(facet_id, project_config)
    return {"profile_id": pid, "system_id": sid, "profile": resolved}


# ------------------------------------------------------------------------------ TRANSITIONAL legacy projection
def legacy_profile_projection(project_config, in_scope_facets):
    """TRANSITIONAL (retires with ARC-06a's per-facet geometry and ARC-04a's M1Interface clean-up). The protected
    single-system engine paths still read ONE claim-level profile (confirmed_selection["shake_measurements"]): the
    disturbance geometry (B1), the transition tie-in, the M1Interface legacy fields and the report's derivation text.
    This projects it from the project's DECLARED profiles only:
      * the profile of the package that owns unlabelled (pre-ProjectConfig) profiles — the package whose settings
        those legacy paths were written for — when an in-scope facet carries it, as {settings, system_id,
        measurement_source}. It is the USER'S declared profile, never a package default;
      * None when no in-scope facet carries that package (the legacy paths then behave exactly as for a historical
        claim without a profile — the B1 defect, tracked by facet_system_dispatch_gate.py, unchanged);
      * a REFUSAL when in-scope facets carry two profiles of that package with different settings: one claim-level
        profile cannot represent them, and choosing one would silently bill the other's facets by it. Per-facet
        geometry is ARC-06a."""
    owner = _RS.unlabelled_profile_owner()   # identifies the legacy paths' package; it selects nothing per facet
    if owner is None:
        return None
    used = {}
    for f in in_scope_facets:
        pid, sid, _resolved = resolve_facet(f, project_config)
        if sid == owner:
            used.setdefault(pid, []).append(str(f))
    if not used:
        return None
    profiles = project_config["materials"]["profiles"]
    distinct = {json.dumps(profiles[p]["settings"], sort_keys=True) for p in used}
    if len(distinct) > 1:
        raise ProjectConfigError(
            f"FRAME ARC-03a: in-scope facets carry {len(used)} {owner!r} profiles with DIFFERENT settings "
            f"({ {p: used[p] for p in sorted(used)} }). The engine's claim-level geometry reads one profile, so it "
            f"cannot bill them separately yet (per-facet geometry is ARC-06a). Fix: use one profile for these facets.")
    pid = sorted(used)[0]
    prof = profiles[pid]
    return {**dict(prof["settings"]), "system_id": owner, "measurement_source": prof["measurement_source"]}


# ------------------------------------------------------------------------------- the carry onto the engine
# Selection keys that are a SECOND material authority. A schema_version 1 selection carries none of them: its
# materials live in the project header only. (The transitional claim-level projection is derived below, by the
# engine side, never sent by a page.)
LEGACY_MATERIAL_KEYS = (_RS.PREDOMINANT_SYSTEM_KEY, _RS.FACET_SYSTEMS_KEY,
                        "shake_measurements", "shakeMeasurements", "shake_profile")


def carry_to_engine(selection, *, xml_text=None, geometry=None) -> dict:
    """The keys a schema_version 1 selection adds to the engine's confirmed selection — THE one carry, shared by the
    scope seam (workbench_seam) and the diagram conversion (workbench_diagram_data) so the two cannot drift:
      * PROJECT_CONFIG_KEY: the fully validated header (against this XML, its parser facets and the exclusions);
      * excluded_facets, exactly as given (the callers validate them against this roof through the registry, as
        before — validate_roof_system_selection — and they must be facets of the project's measurement source);
      * the transitional claim-level profile projection, only when an in-scope facet carries a profile of the
        package the legacy paths were written for (legacy_profile_projection).
    A selection that also carries a legacy material key is REFUSED (two authorities). Every in-scope roof facet must
    resolve, or MaterialDeclarationMissing is raised before anything is computed."""
    sel = selection or {}
    clash = [k for k in LEGACY_MATERIAL_KEYS if k in sel]
    if clash:
        _fail(f"the selection carries a project_config AND the legacy material key(s) {clash}. A schema_version "
              f"{SCHEMA_VERSION} project has ONE material authority; nothing is merged. Fix: remove {clash}.")
    header = validate_project_config(sel.get(_RS.PROJECT_CONFIG_KEY), xml_text=xml_text, geometry=geometry,
                                     selection=sel)
    excluded = _RS.excluded_facets(sel)
    unknown_excl = sorted(excluded - set(header["source"]["facet_structures"]), key=_id_key)
    if unknown_excl:
        _fail(f"excluded_facets names {unknown_excl}, which are not roof facets of this project's measurement.")
    out = {_RS.PROJECT_CONFIG_KEY: header}
    if _RS.EXCLUDED_FACETS_KEY in sel:
        out[_RS.EXCLUDED_FACETS_KEY] = list(sel[_RS.EXCLUDED_FACETS_KEY])
    in_scope = [f for f in sorted(header["source"]["facet_structures"], key=_id_key) if f not in excluded]
    projection = legacy_profile_projection(header, in_scope)
    if projection is not None:
        out["shake_measurements"] = projection
    return out


# ------------------------------------------------------------------------------------------- canonical form
def canonical_json(obj) -> str:
    """Canonical JSON (sorted keys, no whitespace) — the form the digests and the equivalence tests compare."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def header_of(cfg) -> dict:
    """The header (no `selection`) — the shape that rides on a selection under PROJECT_CONFIG_KEY."""
    return {k: copy.deepcopy(cfg[k]) for k in HEADER_KEYS if k in cfg}
