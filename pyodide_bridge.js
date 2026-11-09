// Pyodide Bridge — loads the frozen Wood Shake engine into Pyodide and exposes
// browser-side async functions mirroring the old local-server endpoints.
// Serve over HTTP (not file://); browsers block fetch() of adjacent local files otherwise.

const PYODIDE_INDEX_URL = "https://cdn.jsdelivr.net/pyodide/v0.28.0/full/";
const PYODIDE_SCRIPT_URL = `${PYODIDE_INDEX_URL}pyodide.js`;

const ENGINE_FILES = [
  "core/roof_selection/candidate_display.py",
  "core/roof_selection/candidate_emitters.py",
  "core/roof_selection/candidate_model.py",
  "core/roof_selection/confirmation_builder.py",
  "core/geometry/eagleview_geometry_parser.py",
  "core/geometry/facet_basis.py",
  "appurtenance_types.py",                  // FRAME v106.6g: the appurtenance TYPE table (flashing method + standard base). Loaded BEFORE roof_systems and geometry_core, which both import it; depends on nothing itself
  "core/registry/roof_systems.py",          // FRAME v95: core's roof-system registry (geometry_core looks packages up here)
  "geometry_core.py",
  "roof_systems/wood_shake/wood_shake_geometry.py",   // FRAME v95: the wood-shake profile + valley strategy; registers at import
  "roof_systems/modbit/modbit_geometry.py",           // FRAME v106.4: the MODBIT profile + its valley REFUSAL; registers at import
  "roof_systems/modbit/modbit_scope_expansion.py",    // FRAME v106.4: MODBIT's scope engine (one field SQ line); asked for, never imported by core
  "module1_m2interface.py",
  "core/roof_selection/module1_selected_valley_handoff.py",
  "module1_service.py",
  "module1_yager_proof.py",
  "module2_assembly.py",
  "roof_systems/wood_shake/module2_scope_expansion.py",
  "core/contracts/scope_contract.py",
  "core/roof_selection/notch_candidate_emitter.py",
  "regression_test.py",
  "core/geometry/transition_enumerator.py",
  "transition_events.py",
  "workbench_diagram_data.py",
  "core/geometry/workbench_roof_layout.py",
  "workbench_seam.py",
  // Carrier / comparison engine (Build A — page 3 live comparison). Additive load only;
  // these files are byte-identical to the frozen engine.
  "shared_category_registry.py",
  "roof_systems/wood_shake/wood_shake_categories.py",   // FRAME v97: the category ids wood_shake OWNS; imported by the boot helper
  "roof_systems/wood_shake/wood_shake_content.py",    // FRAME v101: the package's words (labels, carrier vocabulary, repair entries, report text); imported by wood_shake_categories
  "roof_systems/modbit/modbit_categories.py",         // FRAME v106.4: the category ids modbit OWNS; imported by the boot helper
  "roof_systems/modbit/modbit_content.py",            // FRAME v106.4: modbit's words (label + carrier vocabulary; it declares NO report text — see its docstring); imported by modbit_categories
  "core/registry/package_content.py",                  // FRAME v101: core reads a package's words here, at call time (never imports the package)
  "module3_keying.py",
  "operation_dimension.py",
  "module3_comparison_oracle.py",
  "comparison_caller.py",
  "core/carrier/carrier_parser.py",          // v60: manual_carrier_entry imports consolidate_RR from here.
                                //      MUST load BEFORE manual_carrier_entry or the report dies with
                                //      ModuleNotFoundError at module-load time. Its only dependency is
                                //      shared_category_registry, already loaded above.
  "manual_carrier_entry.py",
  // Module 3 report engine (page 4). Additive load only; byte-identical to the frozen engine.
  "scope_argument_builder.py",
  "core/comparison/argument_caller.py",
  "repair_logic_library.py",
  "module3_render_engine.py",
  "module3_report_renderer.py",
  "core/reporting/module3_language_guard.py",
  "module3_caller.py",
  "category_display_names.py",
  "core/reporting/report_diagram_svg.py",
  // Layer A: raw carrier-estimate text -> structured header + line items (page 3 prefill).
  "carrier_layer_a.py",
  "appurtenance_review.py",
  "XML.txt",
];

let pyodideInstance = null;
let readyPromise = null;

function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (globalThis.loadPyodide) { resolve(); return; }
    const script = document.createElement("script");
    script.src = src; script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(script);
  });
}

async function fetchText(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to fetch ${path}: HTTP ${response.status}`);
  return response.text();
}

async function loadEngineFiles(pyodide) {
  for (const filename of ENGINE_FILES) {
    const text = await fetchText(filename);
    pyodide.FS.writeFile(filename.split('/').pop(), text);
  }
}

async function initializePythonHelpers(pyodide) {
  await pyodide.runPythonAsync(`
import json
from dataclasses import asdict, is_dataclass
# FRAME v97 BRIDGE 3: the app loads its roof-system packages ONCE, here, before any page's Python runs.
# Every page (1-4) boots through this helper. A package added later is its files + one line here.
import wood_shake_categories
# FRAME v106.4: the second package, by that same rule. Its categories module imports its content module, so
# this one line loads the label and the carrier vocabulary on every page, exactly as wood_shake's does. The
# GEOMETRY modules of both packages are imported by module1_service, not here.
import modbit_categories
# FRAME v106.6g2 / B2: the shared appurtenance-review authority, imported once here so
# every page's Python can reach it, by the same rule as the package category modules.
import appurtenance_review


def _wb_to_plain(obj):
    if is_dataclass(obj):
        return _wb_to_plain(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): _wb_to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_wb_to_plain(v) for v in obj]
    if hasattr(obj, "tolist"):
        return obj.tolist()
    return obj


def _wb_scope_summary(scope_result):
    # FRAME v98: the field covering comes from the ONE authority — module2_assembly.field_quantities, shaped by
    # field_summary. No loop over the scope lives here any more (v97.1's _wb_shake_ea read the first field line
    # and discarded its unit; page 2 printed a full replacement's 60.365 SQ as "60" under "Total shakes").
    from module2_assembly import field_summary
    plain = _wb_to_plain(scope_result)
    fs = field_summary(scope_result)
    # total_EA: EXACT v97.1 value and semantics (C-5) — additive change only; the misleading name is a known-open.
    v = fs["legacy_total_EA"]
    try:
        v = float(v) if v is not None else 0.0
        plain["total_EA"] = int(v) if v.is_integer() else v
    except (TypeError, ValueError):
        plain["total_EA"] = 0
    # what page 2 renders: the figure IN ITS OWN UNIT, primary (SQ when present) + the alternate on a mixed claim
    plain["field_qty"], plain["field_unit"] = fs["field_qty"], fs["field_unit"]
    plain["field_qty_alt"], plain["field_unit_alt"] = fs["field_qty_alt"], fs["field_unit_alt"]
    plain["total_SF"] = plain.get("affected_SF_display_total")
    plain["valley_LF"] = plain.get("selected_valley_LF_total")
    # Each ridge's CONTACTED length — the run the repair actually touches. It bounds the vent (you
    # cannot replace more vent than the ridge you are working on), and a ridge with ZERO contact is
    # not in the repair at all and cannot be marked vented. It depends on the user's SELECTION, not
    # on the geometry, so it can only come from the compute.
    plain["ridge_contacts"] = {
        str(c.line_id): round(float(c.contact_LF), 2)
        for c in getattr(scope_result, "deduped_edges", ()) or ()
        if c.edge_type == "RIDGE"
    }
    return plain
`);
}

async function boot() {
  await loadScript(PYODIDE_SCRIPT_URL);
  const pyodide = await globalThis.loadPyodide({ indexURL: PYODIDE_INDEX_URL });
  await pyodide.loadPackage(["numpy", "matplotlib"]);
  await loadEngineFiles(pyodide);
  await initializePythonHelpers(pyodide);
  pyodideInstance = pyodide;
  return pyodide;
}

export function ready() {
  if (!readyPromise) readyPromise = boot();
  return readyPromise;
}

async function runJson(pythonSource, globals = {}) {
  const pyodide = await ready();
  for (const [name, value] of Object.entries(globals)) pyodide.globals.set(name, value);
  try {
    const jsonText = await pyodide.runPythonAsync(pythonSource);
    return JSON.parse(jsonText);
  } finally {
    for (const name of Object.keys(globals)) {
      try { pyodide.globals.delete(name); } catch (_e) {}
    }
  }
}

export async function bundledXmlText() {
  await ready();
  return runJson(`
import json
json.dumps(open("XML.txt", "r", encoding="utf-8").read())
`);
}

export async function roofLayout(xmlText) {
  return runJson(`
import json
from workbench_roof_layout import build_roof_layout
json.dumps(build_roof_layout(xml_text))
`, { xml_text: xmlText });
}

export async function scopeFromSelection(xmlText, uiSelection) {
  return runJson(`
import json
from workbench_seam import build_scope_from_ui_selection
ui_selection = json.loads(ui_selection_json)
result = build_scope_from_ui_selection(xml_text, ui_selection)
json.dumps(_wb_scope_summary(result))
`, { xml_text: xmlText, ui_selection_json: JSON.stringify(uiSelection || {}) });
}

export async function diagramData(xmlText, uiSelection) {
  return runJson(`
import json
from workbench_diagram_data import build_diagram_data
ui_selection = json.loads(ui_selection_json)
json.dumps(build_diagram_data(xml_text, ui_selection))
`, { xml_text: xmlText, ui_selection_json: JSON.stringify(uiSelection || {}) });
}

export async function workbenchUpdate(xmlText, uiSelection = {}) {
  return runJson(`
import json
from workbench_seam import build_scope_from_ui_selection
from workbench_diagram_data import build_diagram_data
from appurtenance_review import review_report
ui_selection = json.loads(ui_selection_json)
scope = build_scope_from_ui_selection(xml_text, ui_selection)
diagram = build_diagram_data(xml_text, ui_selection)
# FRAME v106.6g2 / B2 - the item-specific size/label review, from the ONE shared authority. It is
# RECOMPUTED here from the current xml and selection on every update, never read from a stored flag,
# so a page that has gone stale cannot report "nothing pending". The whole selection is handed over,
# bare, exactly as the two calls above receive it.
review = review_report(xml_text, ui_selection)
# ONE SERIALISER, USED EVERYWHERE. This function used to hand-build a SECOND, divergent scope dict
# with only three keys - so ridge_contacts (which _wb_scope_summary builds correctly) never reached
# the UI, every ridge read a contact of 0, and the "this ridge is not in the repair" guard fired on
# every ridge. THE DATA WAS ALWAYS THERE; the bridge simply never shipped it on the path page 2 uses.
#
# This is the THIRD time a duplicated serialisation path has silently dropped a field (v42: the
# diagram path dropped transition_repairs; the same build: total_SF came from a stale source). The
# duplicate is deleted rather than patched: workbenchUpdate now returns the canonical summary, so a
# field added to _wb_scope_summary is automatically available to every caller. A regression locks
# field parity so the two can never diverge again.
json.dumps({
    "scope": _wb_scope_summary(scope),
    "diagram": diagram,
    "reviews": review.as_dict(),
})
`, { xml_text: xmlText, ui_selection_json: JSON.stringify(uiSelection || {}) });
}

export async function yagerUiSelection(xmlText) {
  return runJson(`
import json
from module1_yager_proof import YAGER_CONFIRMED_SELECTION
from workbench_seam import _ui_selection_from_confirmed_selection
selection = _ui_selection_from_confirmed_selection(YAGER_CONFIRMED_SELECTION, xml_text=xml_text)
json.dumps(selection)
`, { xml_text: xmlText });
}

export async function yagerScope(xmlText) {
  const uiSelection = await yagerUiSelection(xmlText);
  return scopeFromSelection(xmlText, uiSelection);
}

// --- Build A: carrier / comparison engine (page 3) -------------------------
// requiredScope: the confirmed-selection scope (same call page 2 uses), so page 3
// can display and verify the required numbers reproduce page 2's.
// transitionStates: which detected transitions are ACTIVE and by which path — PATH_A (auto,
// swept >=95%), PATH_B (user-asserted), or BOTH. The ENGINE decides; the UI only draws it.
export async function transitionStates(xmlText, uiSelection) {
  return runJson(`
import json
from workbench_seam import transition_states
json.dumps(_wb_to_plain(transition_states(xml_text, json.loads(ui_selection_json))))
`, { xml_text: xmlText, ui_selection_json: JSON.stringify(uiSelection || {}) });
}

export async function requiredScope(xmlText, uiSelection) {
  return scopeFromSelection(xmlText, uiSelection);
}

// buildCarrierSummary: carrier_scope_summary from confirmed manual-entry rows.
export async function buildCarrierSummary(rows) {
  return runJson(`
import json
from manual_carrier_entry import build_carrier_summary_from_manual_entry
rows = json.loads(rows_json)
summary = build_carrier_summary_from_manual_entry(rows)
json.dumps(_wb_to_plain(summary))
`, { rows_json: JSON.stringify(rows || []) });
}

// buildScopeComparison: the real comparison. module2_result is a Python object that
// cannot cross the JS boundary, so assemble -> carrier-summary -> compare all run in
// one Python execution from (xmlText, uiSelection, carrierRows). Returns the status,
// required totals (for page-2 verification), and the scope_comparison lines page 3 renders.
export async function buildScopeComparison(xmlText, uiSelection, carrierRows) {
  return runJson(`
import json
from workbench_seam import build_scope_from_ui_selection
from manual_carrier_entry import build_carrier_summary_from_manual_entry
from comparison_caller import build_scope_comparison

ui_selection = json.loads(ui_selection_json)
rows = json.loads(rows_json)
module2_result = build_scope_from_ui_selection(xml_text, ui_selection)
carrier_summary = build_carrier_summary_from_manual_entry(rows) if rows else None
result = build_scope_comparison(module2_result, carrier_summary)

req = result.get("required") or {}
out = {
    "status": result["status"],
    "required_totals": _wb_to_plain(result.get("required_totals")),
    "required_shake": _wb_to_plain(req.get("SHAKE_FIELD_RR")),
    "carrier_parser_status": (carrier_summary or {}).get("parser_status"),
    "duplicate_comparison_categories": list((carrier_summary or {}).get("duplicate_comparison_categories", []) or []),
    "scope_comparison": _wb_to_plain(result.get("scope_comparison")),
}
json.dumps(out)
`, { xml_text: xmlText, ui_selection_json: JSON.stringify(uiSelection || {}), rows_json: JSON.stringify(carrierRows || []) });
}

// buildModule3Report: the FULL Module 3 report pipeline in ONE Python execution.
// module2_result / carrier_summary are Python objects that cannot cross the JS boundary, so
// assemble -> carrier-summary -> comparison -> argument -> module3 inputs -> render -> to_html
// all run server-side here. Nothing is reimplemented in JS; page 4 only displays the HTML.
// carrierRows == null/[] -> REQUIRED_SCOPE_ONLY mode (no carrier estimate was provided).
export async function buildModule3Report(xmlText, uiSelection, carrierRows, vci, opts = {}) {
  // Report branding is PER-DEVICE, not per-claim: the logo + "Prepared by" text are stored in
  // localStorage on page 1 (deliberately separate from the sessionStorage claim state, so a claim
  // reset never wipes them). Read them here and carry them to the renderer as a base64 data URI +
  // free text. Absent -> the header degrades to the plain title + attribution line.
  let brandLogo = "", brandPreparedBy = "";
  try { brandLogo = localStorage.getItem("woodShakeBranding.logoDataUri") || ""; } catch (e) {}
  try { brandPreparedBy = localStorage.getItem("woodShakeBranding.preparedBy") || ""; } catch (e) {}
  return runJson(`
import json
from workbench_seam import build_scope_from_ui_selection
from manual_carrier_entry import build_carrier_summary_from_manual_entry
from comparison_caller import build_scope_comparison
from argument_caller import build_scope_argument
from module3_caller import build_module3_inputs, render_module3_report
from module3_language_guard import safe_export
from workbench_roof_layout import build_roof_layout
from workbench_diagram_data import build_diagram_data
from report_diagram_svg import build_report_diagram_svg
from module3_report_renderer import to_html
from appurtenance_review import export_review_gate, clear_resolved_questions

ui_selection = json.loads(ui_selection_json)
rows = json.loads(rows_json)
vci = json.loads(vci_json)
opts = json.loads(opts_json)
photos = opts.get("photos") or []
attachments = opts.get("attachments") or []
reference_tags = opts.get("reference_tags") or ["CSSB", "IRC R905.8"]
claim_name = opts.get("claim_name") or "Wood Shake Repair"

# FRAME v106.6g2 / B2 - THE EXPORT BACKSTOP, FIRST, BEFORE ANYTHING IS BUILT. The reviews are
# RECOMPUTED from this xml and this selection: not read from a flag page 2 set, not inferred from
# whether a citation happens to contain a warning. So a claim reached straight from stored session
# data, a bypassed Continue handler, an old snapshot or a tampered confirmation all arrive here and
# are all refused the same way. Nothing is rendered on the blocked path - there is no projection, no
# html, and therefore nothing to print or download, never a partial report.
_review = export_review_gate(xml_text, ui_selection)
if _review.get("blocked"):
    _result = {
        "mode": None, "status": None, "gated": True, "exported": False,
        "blocked": True, "blocked_reason": "APPURTENANCE_REVIEW_UNRESOLVED",
        "review": _review,
        "unresolved_ids": _review.get("unresolved_ids") or [],
        "unresolved_reasons": [i.get("reason_text") for i in (_review.get("unresolved") or [])],
        "html": "", "lines": [], "language_gate_hard": [],
        "sections": [], "carrier_parser_status": None,
        "duplicate_comparison_categories": [],
    }
else:
    module2_result = build_scope_from_ui_selection(xml_text, ui_selection)
    # Every relevant item is explicitly confirmed or corrected, so the internal question has been
    # ANSWERED and must not appear in a document a carrier reads. Presentation only: citations lose
    # that one clause; quantities, categories, units and the CONFIRM tier are untouched.
    _cleared = clear_resolved_questions(module2_result)
    module1_result = {"affected_SF": module2_result.affected_SF_raw_total}

    # v87: an estimate with carrier lines but ZERO in-scope ROOF lines is still a COMPARISON — every
    # required item reads as missing — not a degrade to REQUIRED_SCOPE_ONLY. page 4 passes
    # comparison_intended from page 3's mode (the single authority). With no in-scope rows,
    # build_carrier_summary_from_manual_entry([]) yields a present-but-empty summary, which
    # build_scope_comparison turns into the all-missing comparison. With no estimate at all (repair-scope),
    # comparison_intended is false -> carrier_summary stays None -> REQUIRED_SCOPE_ONLY, unchanged.
    carrier_summary = (build_carrier_summary_from_manual_entry(rows)
                       if (rows or opts.get("comparison_intended")) else None)

    comparison = build_scope_comparison(module2_result, carrier_summary)
    argument = build_scope_argument(module1_result, module2_result, comparison, carrier_summary, vci,
                                    photos=photos, attachments=attachments,
                                    reference_tags=reference_tags)["argument_pack"]
    # The report's picture AND its percentage come from the SAME layout + diagram data the page-2 totals
    # come from — never re-derived, never a placeholder. Failure to draw must not cost the report.
    _diagram = None
    _svg = ""
    try:
        _layout = build_roof_layout(xml_text)
        _diagram = build_diagram_data(xml_text, ui_selection)
        _svg = build_report_diagram_svg(_layout, _diagram)
    except Exception:
        _diagram = None
        _svg = ""
    _pct = ((_diagram or {}).get("summary") or {}).get("pct_of_roof")

    projection = build_module3_inputs(module1_result, module2_result, comparison, argument, vci,
                                      carrier_summary, photos=photos, attachments=attachments,
                                      reference_tags=reference_tags, diagram_pct=_pct)
    if _svg:
        projection["inputs"]["P3"]["diagram_svg"] = _svg

    rendered = render_module3_report(projection)
    mode = projection["sc"]["mode"]

    # The measured shake profile drives §3's shake-count derivation (per-shake coverage + shakes/SQ).
    # It rides along in the ui_selection the scope was built from — the SAME measurements Module 2 used —
    # so the derivation is never on the defaults. Presentation only; no computed value depends on it.
    shake_measurements = ui_selection.get("shake_measurements") or ui_selection.get("shake_profile") or {}
    # Per-device branding (base64 logo + typed attribution), read from localStorage above. Presentation only.
    logo_data_uri = brand_logo or None
    prepared_by = brand_prepared_by or None

    # The §10.5 language guard governs export — we call it, never bypass or duplicate it.
    export = safe_export(projection["inputs"]["P3"],
                         review=_review,
                         render_fn=lambda: to_html(rendered, mode, claim_name,
                                                   {"kind": "PRODUCTION", "detail": "live claim"},
                                                   logo_data_uri=logo_data_uri,
                                                   prepared_by=prepared_by,
                                                   shake_measurements=shake_measurements))

    lines = ((comparison.get("scope_comparison") or {}).get("lines")) or []
    out = {
        "mode": mode,
        "status": comparison["status"],
        "carrier_parser_status": (carrier_summary or {}).get("parser_status"),
        "duplicate_comparison_categories": list((carrier_summary or {}).get("duplicate_comparison_categories", []) or []),
        "gated": bool(rendered.get("gated")),
        "sections": sorted(rendered.get("sections") or []),
        "exported": bool(export["exported"]),
        "language_gate_hard": list(export["gate"]["hard"]),
        "html": export["artifact"] if export["exported"] else "",
        "lines": _wb_to_plain(lines),
        "blocked": False,
        "review": _review,
        "review_questions_cleared": _cleared,
    }
    _result = out
# ONE trailing expression, in both paths: Pyodide's runPythonAsync returns the last expression's
# value and runJson JSON.parses it, so a module that ends on a statement returns None.
json.dumps(_result)
`, {
    xml_text: xmlText,
    ui_selection_json: JSON.stringify(uiSelection || {}),
    rows_json: JSON.stringify(carrierRows || []),
    vci_json: JSON.stringify(vci || {}),
    opts_json: JSON.stringify(opts || {}),
    brand_logo: brandLogo,
    brand_prepared_by: brandPreparedBy,
  });
}

// parseCarrierEstimate: LAYER A. Raw estimate text (from pdf.js on page 1) -> claim header +
// line items + proposed categories. Never fabricates: unfound header fields come back blank and
// an unmappable line comes back with category null + needs_mapping true. Empty/garbage text ->
// status TEXT_LAYER_ABSENT so page 3 can degrade to manual entry.
export async function parseCarrierEstimate(estimateText) {
  return runJson(`
import json
from carrier_layer_a import parse_carrier_estimate_text
json.dumps(_wb_to_plain(parse_carrier_estimate_text(estimate_text)))
`, { estimate_text: estimateText || "" });
}

// v73 DEFECT 1: the ONE operation authority, reachable from the manual entry paths. page 3 calls this
// on the description the user types (add AND edit) instead of hard-coding R&R — no second derivation.
export async function proposeOperation(description) {
  return runJson(`
import json
from carrier_layer_a import propose_operation
json.dumps(propose_operation(description))
`, { description: description || "" });
}

// v73 DEFECT 2: the hand-entry unit dropdown is DERIVED from the parser's own _UNITS list, so the
// dropdown and the parser cannot drift. Adding a unit to carrier_layer_a._UNITS makes it selectable.
export async function carrierUnitList() {
  return runJson(`
import json
from carrier_layer_a import UNIT_LIST
json.dumps(list(UNIT_LIST))
`, {});
}

// v75: which carrier categories resolve to MORE THAN ONE operation (Detach & Reset + new material),
// so page 3 can flag the ambiguity for review BEFORE the report is delivered. One authority: the same
// _partition_operations the approved side uses.
export async function mixedOperationCategories(rows) {
  return runJson(`
import json
from manual_carrier_entry import mixed_operation_categories
json.dumps(mixed_operation_categories(rows))
`, { rows: rows || [] });
}

// FRAME v105.5: which roof systems (coverings) are installed — the ONE place page 2 learns the list, so no
// JavaScript ever names a covering. Asks roof_systems.registered() after importing the engine path page 2
// computes through (workbench_seam), so exactly the packages that path registers are listed. Each row takes
// its package's own display label for its field covering where it declares one, else the bare id.
// -> [{system_id, label}], sorted by system_id. With one package installed: exactly one row.
export async function registeredRoofSystems() {
  return runJson(`
import json
import workbench_seam  # noqa: F401 — page 2's engine path; importing it registers the installed roof systems
import roof_systems as _RS
import shared_category_registry as _R
import package_content as _PC
_labels = _PC.display_labels()
_rows = []
for _sid in sorted(_RS.registered()):
    try:
        _label = _labels.get(_R.field_category_id(_sid)) or _sid
    except Exception:
        _label = _sid
    _rows.append({"system_id": _sid, "label": str(_label)})
json.dumps(_rows)
`, {});
}

globalThis.WoodShakePyodideBridge = {
  ready, bundledXmlText, roofLayout, scopeFromSelection, diagramData,
  workbenchUpdate, yagerUiSelection, yagerScope,
  requiredScope, buildCarrierSummary, buildScopeComparison, buildModule3Report, transitionStates,
  parseCarrierEstimate, registeredRoofSystems,
};
