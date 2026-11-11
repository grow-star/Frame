// claim_codec.js — THE saved-claim codec (FRAME ARC-03a, r2). ONE format/version authority, imported by page 4 (Save)
// and page 1 (Load), so the two can never drift (they each held a copy of 'woodshake-claim' / 'v81' before).
//
// File format: { "format": "frame-claim", "schema_version": 1, "savedAt": ISO-8601, "state": {...} }
//   state.projectConfig   the canonical ProjectConfig (core/contracts/project_config.py) INCLUDING `selection`, the
//                         confirmed page-2 selection — the ONLY copy of the selection in the file
//   state.claimState      the confirmed claim minus its uiSelection (rebuilt on load from projectConfig)
//   state.page2Payload, state.page2Restore, state.carrierConfirmation, state.reportEvidence — as the pages keep them
// Photos are saved BY REFERENCE (name + caption, never bytes). Per-device branding is never read or written here.
//
// LOAD = VALIDATE EVERYTHING, THEN ONE COMMIT (ARC-03a r1 + r2; schema doc §4–§6):
//   1. decodeClaimText(): the envelope AND every browser-state invariant — the confirmed selection's page-2 shape,
//      the by-reference evidence shape, every cross-reference between the copies the pages read (one roof, one
//      project, one soffit, no second material authority) and (r2) page 2's workbench snapshot: readable by page 2,
//      and holding exactly the confirmed choices. Content the engine owns (profiles, systems, ids, geometry, the
//      selection's computability) is checked by THE Python validator, which the caller runs next (the bridge's
//      validateProjectConfig).
//   1b. verifyClaimLayout(obj, layout) (r2): with the layout THE bridge builds from the file's own XML, the file's
//      saved layout (if any) must be exactly it, and the snapshot must name only this roof's ids and rebuild exactly
//      the confirmed selection on it. The roof layout is DERIVED: a file's copy is never written; the verified layout
//      is the only one a load writes. Nothing is written until all of 1, the validator and 1b have passed.
//   2. applyClaimToSession(): a TRANSACTION over the claim keys —
//        stage   every new value under woodShakeWorkbench.claimLoadTxn.<key>   (no claim key touched)
//        commit  ONE setItem of the marker woodShakeWorkbench.claimLoadTxn       (the commit point)
//        settle  copy the staged values over the claim keys, then remove the staging and the marker
//      A failure while staging or at the commit (transient OR persistent — e.g. every setItem refused) removes the
//      staging and leaves every pre-existing key byte-identical: the load did not happen. After the commit the new
//      claim IS the active claim (it is durable in the staging keys); if settling cannot finish, the marker stays and
//      EVERY page finishes it before reading anything (settleOrStop) — or stops, showing why — so no page ever reads
//      a half-written claim.
// An old 'woodshake-claim' (v81) file is REFUSED with a clear message (owner waiver D9): no migration, no partial write,
// the file itself untouched.

export const CLAIM_FORMAT = 'frame-claim';
export const CLAIM_SCHEMA_VERSION = 1;
export const LEGACY_CLAIM_FORMATS = ['woodshake-claim'];
export const CLAIM_PREFIX = 'woodShakeWorkbench.';
export const PROJECT_CONFIG_SESSION_KEY = 'projectConfig';
export const PROJECT_CONFIG_SELECTION_KEY = 'project_config';   // where the header rides on a ui selection

const HEADER_KEYS = ['schema_version', 'project_id', 'job_objective', 'materials', 'source'];
const FILE_STATE_KEYS = ['projectConfig', 'claimState', 'page2Payload', 'page2Restore', 'carrierConfirmation',
                         'reportEvidence'];
// Every session key a load replaces (page2Selection is rebuilt from projectConfig.selection, as page 2 writes it).
export const CLAIM_SESSION_KEYS = ['projectConfig', 'claimState', 'page2Payload', 'page2Selection', 'page2Restore',
                                   'carrierConfirmation', 'reportEvidence'];

export class ClaimCodecError extends Error {}

function fail(message) { throw new ClaimCodecError(message + ' Your current claim is unchanged.'); }

function isObj(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }

export function canonical(v) {
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
  if (isObj(v)) return '{' + Object.keys(v).sort().map((k) => JSON.stringify(k) + ':' + canonical(v[k])).join(',') + '}';
  return JSON.stringify(v);
}

function readJson(storage, key) {
  const raw = storage.getItem(CLAIM_PREFIX + key);
  if (raw == null) return null;
  try { return JSON.parse(raw); } catch (_e) { return undefined; }   // undefined = present but unreadable
}

export function headerOf(projectConfig) {
  const out = {};
  for (const k of Object.keys(projectConfig || {})) if (k !== 'selection') out[k] = projectConfig[k];
  return out;
}

// ---------------------------------------------------------------------------------------------------- SAVE
// -> the claim object to write. Throws ClaimCodecError (nothing is written) when the session cannot be saved in the
// current format: no confirmed claim, no project configuration (a pre-ARC-03a session), or a declaration that
// changed after the scope was confirmed (stale work is never exported).
export function encodeClaim(storage, now = new Date()) {
  const claim = readJson(storage, 'claimState');
  if (!isObj(claim) || !isObj(claim.uiSelection)) {
    throw new ClaimCodecError('There is no confirmed claim in this session to save. Build the scope first.');
  }
  const header = readJson(storage, PROJECT_CONFIG_SESSION_KEY);
  if (!isObj(header)) {
    throw new ClaimCodecError('This claim has no project configuration (it was started before this version), so it '
      + 'cannot be saved in the current claim format. Start it from page 1 and declare the roof system.');
  }
  const carried = claim.uiSelection[PROJECT_CONFIG_SELECTION_KEY];
  if (!isObj(carried) || canonical(carried) !== canonical(header)) {
    throw new ClaimCodecError('The project’s roof-system declaration changed after the scope was confirmed. '
      + 'Return to page 2 and press Continue again so the scope is recomputed, then save.');
  }
  const selection = Object.assign({}, claim.uiSelection);
  delete selection[PROJECT_CONFIG_SELECTION_KEY];
  const claimRest = Object.assign({}, claim);
  delete claimRest.uiSelection;
  const state = { projectConfig: Object.assign({}, header, { selection }), claimState: claimRest };
  for (const k of ['page2Payload', 'page2Restore', 'carrierConfirmation', 'reportEvidence']) {
    let val = readJson(storage, k);
    if (val == null || val === undefined) continue;
    if (k === 'reportEvidence' && isObj(val) && Array.isArray(val.photos)) {
      val = Object.assign({}, val, {
        photos: val.photos.map((p) => ({ name: String((p && p.name) || ''), caption: String((p && p.caption) || '') }))
      });
    }
    if (k === 'page2Payload' && isObj(val) && 'roofData' in val) {   // r2: derived from the XML; rebuilt on load
      val = Object.assign({}, val);
      delete val.roofData;
    }
    state[k] = val;
  }
  const obj = { format: CLAIM_FORMAT, schema_version: CLAIM_SCHEMA_VERSION, savedAt: now.toISOString(), state };
  try { decodeClaimObject(obj); }   // the saver never writes a file the loader would refuse
  catch (e) {
    throw new ClaimCodecError('This session cannot be saved as a claim file: '
      + String(e && e.message ? e.message : e).replace(' Your current claim is unchanged.', '')
      + ' Return to page 2 and press Continue so the claim is confirmed again, then save.');
  }
  return obj;
}

// ---------------------------------------------------------------------------------------------------- LOAD
export function decodeClaimText(text) {
  let obj;
  try { obj = JSON.parse(text); }
  catch (_e) { fail('This file could not be read as a claim (it is not valid JSON).'); }
  return decodeClaimObject(obj);
}

// ------------------------------------------------------------------------------------------- import invariants
// The CONFIRMED selection page 2 emits for a declared project (page2.html buildUiSelection): these keys, always.
const SELECTION_ARRAYS = ['valley_intersections', 'appurtenances', 'notches', 'user_appurtenance_repairs',
                          'transition_repairs', 'high_slope_facets', 'ridge_vents', 'replaced_facets'];
const SELECTION_REQUIRED = SELECTION_ARRAYS.concat(['eave_iws', 'soffit_depth_in', 'xml_text']);
// Optional: appurtenance_reviews (absent = no confirmations, as page 2 reads a pre-B2 snapshot) and excluded_facets
// (absent = none). Anything else — above all a second material authority — is refused.
const SELECTION_OPTIONAL = ['appurtenance_reviews', 'excluded_facets'];
const LEGACY_MATERIAL_SELECTION_KEYS = ['predominant_system_id', 'facet_systems', 'shake_measurements',
                                        'shakeMeasurements', 'shake_profile'];
const EVIDENCE_KEYS = ['photos', 'attachments'];

function sameStringSet(a, b) {
  const x = Array.from(new Set((a || []).map(String))).sort();
  const y = Array.from(new Set((b || []).map(String))).sort();
  return x.length === y.length && x.every((v, i) => v === y[i]);
}

function checkSelection(sel, xmlText) {
  const where = 'the confirmed roof selection';
  const legacy = LEGACY_MATERIAL_SELECTION_KEYS.filter((k) => k in sel);
  if (legacy.length) fail('This claim file is not valid — ' + where + ' carries a second material authority (' + legacy.join(', ') + ').');
  const missing = SELECTION_REQUIRED.filter((k) => !(k in sel));
  if (missing.length) fail('This claim file is incomplete — ' + where + ' is missing ' + missing.join(', ') + '.');
  const extra = Object.keys(sel).filter((k) => !SELECTION_REQUIRED.includes(k) && !SELECTION_OPTIONAL.includes(k));
  if (extra.length) fail('This claim file is not valid — ' + where + ' carries unexpected fields (' + extra.join(', ') + ').');
  for (const k of SELECTION_ARRAYS.concat(['appurtenance_reviews'])) {
    if (!(k in sel)) continue;
    if (!Array.isArray(sel[k]) || sel[k].some((r) => !isObj(r))) {
      fail('This claim file is not valid — ' + where + ': ' + k + ' must be a list of records.');
    }
  }
  if ('excluded_facets' in sel && (!Array.isArray(sel.excluded_facets)
      || sel.excluded_facets.some((f) => typeof f !== 'string' || !f))) {
    fail('This claim file is not valid — ' + where + ': excluded_facets must be a list of facet ids.');
  }
  if (sel.eave_iws !== null && !isObj(sel.eave_iws)) fail('This claim file is not valid — ' + where + ': eave_iws must be a record or null.');
  if (sel.soffit_depth_in !== null && (typeof sel.soffit_depth_in !== 'number' || !Number.isFinite(sel.soffit_depth_in))) {
    fail('This claim file is not valid — ' + where + ': soffit_depth_in must be a number or null.');
  }
  if (sel.xml_text !== xmlText) fail('This claim file is inconsistent — ' + where + ' was made on a different measurement of the roof than the claim.');
}

function checkEvidence(ev) {
  const extra = Object.keys(ev).filter((k) => !EVIDENCE_KEYS.includes(k));
  if (extra.length) fail('This claim file is not valid — the report evidence carries unexpected fields (' + extra.join(', ') + ').');
  if ('photos' in ev) {
    if (!Array.isArray(ev.photos)) fail('This claim file is not valid — photos must be a list of photo references (name and caption), never image data.');
    for (const p of ev.photos) {
      const keys = isObj(p) ? Object.keys(p).sort() : ['?'];
      if (keys.join(',') !== 'caption,name' || typeof p.name !== 'string' || typeof p.caption !== 'string') {
        fail('This claim file is not valid — a photo must be exactly a name and a caption (photos are saved by reference only, never image data).');
      }
    }
  }
  if ('attachments' in ev) {
    if (!Array.isArray(ev.attachments)) fail('This claim file is not valid — attachments must be a list.');
    for (const a of ev.attachments) {
      const keys = isObj(a) ? Object.keys(a).sort() : ['?'];
      if (keys.join(',') !== 'included,label' || typeof a.label !== 'string' || typeof a.included !== 'boolean') {
        fail('This claim file is not valid — an attachment must be exactly a label and an included flag.');
      }
    }
  }
}

// ======================================================================= page 2's workbench snapshot (ARC-03a r2)
// state.page2Restore is page 2's RAW workbench (page2.html savePage2RestoreSnapshot), which page 2 deserialises
// (restorePage2FromSnapshot) and from which it rebuilds the selection (buildUiSelection) when the user goes back to it.
// A loaded file may therefore only carry a snapshot that (a) page 2 can read without an exception and (b) rebuilds
// EXACTLY the confirmed selection — projectConfig.selection, the one authority. Anything else is refused before any
// write. Two levels, both before the commit:
//   decodeClaimObject  -> readSnapshot + snapshotMatchesSelection: every field's shape, and every relation to the
//                         confirmed selection that needs no geometry (valley picks, transition facts, ridge vents,
//                         high-slope / replaced / excluded facets, repair-event definitions, user items, review keys,
//                         eave ice & water).
//   verifyClaimLayout  -> on page 1, with the roof layout THE bridge builds from the file's own XML: every id in the
//                         snapshot is on this roof, and the selection page 2 would rebuild from it on this roof — valley
//                         intersections vs notches, appurtenance rows with their hosts, labels and chimney sizes, user
//                         rows, replaced-slope labels — equals the confirmed selection.
// No geometry is computed here: every geometric fact is read from the bridge's layout, as page 2 reads it.
const SNAPSHOT_KEYS = ['xmlText', 'computeMode', 'shakeMeasurements', 'nextUserAppNumber', 'selectedValleys',
                       'penetrationDefinitions', 'transitionRepairs', 'appurtGroups', 'appurtSizes', 'ridgeVents',
                       'highSlopeFacets', 'noHighSlope', 'replacedFacets', 'predominantSystem', 'facetSystems',
                       'excludedFacets', 'userAppurtenances', 'reviewConfirmations', 'eaveIws', 'savedAt'];
const USER_APP_KEYS = ['designator', 'hostFacetId', 'type', 'repairEvent', 'shape', 'width', 'height', 'sharedPoint',
                       'localPosition', 'confirmed', 'lastCarvedSF', 'otherLabel', 'otherCategory'];
const USER_APP_REQUIRED = ['designator', 'hostFacetId', 'type', 'repairEvent', 'shape', 'sharedPoint', 'confirmed'];
const PENETRATION_DEFINITION_KEYS = ['type', 'repairEvent', 'otherLabel', 'otherCategory', 'operation'];

// ---- page2.html's own readers, copied VERBATIM (claim_import_integrity_regression.py compares the source text, so a
// change on page 2 that is not made here fails the suite instead of drifting).
const TRANSITION_METAL = ['EXPOSED', 'CONCEALED', 'NONE', 'MEMBRANE', 'UNKNOWN'];
const POINT_APPURTENANCE_TYPES = ['PIPE', 'TURTLE', 'TURBINE', 'POWER_VENT'];
    function readTransitionFact(v) {
      const o = (v && typeof v === 'object') ? v : {};
      let metal = (typeof o.metal === 'string' && o.metal) ? o.metal : null;
      if (metal !== null && !TRANSITION_METAL.includes(metal)) return null;
      if (metal === null && o.exposed === true) metal = 'EXPOSED';
      if (metal === null) return null;
      if (o.damaged === true && metal !== 'EXPOSED') return null;
      return { metal, damaged: metal === 'EXPOSED' && o.damaged === true };
    }
    function isPowerVentType(type) {
      return String(type || '').toUpperCase() === 'POWER_VENT';
    }
    function isDimensionedAppurtenanceType(type) {
      return !POINT_APPURTENANCE_TYPES.includes(String(type || '').toUpperCase());
    }
    function isUserAppComplete(item) {
      if (!item || !item.type || (item.repairEvent !== true && item.repairEvent !== false) || !item.hostFacetId || !item.confirmed) return false;
      // OTHER must carry the user's label before it counts as defined (see isPenetrationDefined).
      if (String(item.type).toUpperCase() === 'OTHER' && !String(item.otherLabel || '').trim()) return false;
      if (isDimensionedAppurtenanceType(item.type)) {
        return Number(item.width) > 0 && Number(item.height) > 0;
      }
      return true;
    }
    function suggestSizeFromArea(areaSF) {
      const a = Number(areaSF) || 0;
      if (a <= 4.0) return 'S';
      if (a <= 8.0) return 'A';
      return 'L';                       // anything above 8.0 — including above 10.0 — is Large
    }
    function typeDisplayLabel(value, otherLabel) {
      // The user's own label is what shows for an OTHER item — never the raw word "OTHER".
      if (String(value || '').toUpperCase() === 'OTHER' && otherLabel && String(otherLabel).trim()) {
        return String(otherLabel).trim();
      }
      const map = { CHIMNEY: 'Chimney', SKYLIGHT: 'Skylight', PIPE: 'Pipe jack',
                    TURTLE: 'Box / turtle vent', TURBINE: 'Turbine vent',
                    POWER_VENT: 'Power attic vent', OTHER: 'Other' };
      return map[String(value || '').toUpperCase()] || String(value || 'Appurtenance');
    }
    function naturalCompare(a, b) {
      return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
    }
// ---- end of the verbatim copies

const isId = (v) => typeof v === 'string' && v.length > 0;
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const isStr = (v) => typeof v === 'string';
const isPoint = (v) => Array.isArray(v) && v.length === 2 && isNum(v[0]) && isNum(v[1]);

function snapInvalid(what) { fail('This claim file is not valid — its page-2 workbench snapshot ' + what + '.'); }
function snapDiffers(what) {
  fail('This claim file is inconsistent — its page-2 workbench snapshot does not match the confirmed selection ('
    + what + '), so going back to page 2 would show — and recompute — a different claim.');
}

function snapPairs(snap, key, readValue) {   // [[id, value], …] — the shape page 2 writes for every Map it keeps
  if (!(key in snap)) return new Map();
  const v = snap[key];
  if (!Array.isArray(v)) snapInvalid(key + ' is not a list of [id, value] pairs');
  const out = new Map();
  for (const p of v) {
    if (!Array.isArray(p) || p.length !== 2 || !isId(p[0])) snapInvalid(key + ' is not a list of [id, value] pairs');
    if (out.has(p[0])) snapInvalid(key + ' names ' + p[0] + ' twice');
    const val = readValue(p[1]);
    if (val === null) snapInvalid(key + ' holds an unreadable value for ' + p[0]);
    out.set(p[0], val);
  }
  return out;
}

function snapIds(snap, key) {
  if (!(key in snap)) return [];
  const v = snap[key];
  if (!Array.isArray(v) || !v.every(isId)) snapInvalid(key + ' is not a list of ids');
  if (new Set(v).size !== v.length) snapInvalid(key + ' names an id twice');
  return v;
}

// -> the snapshot as page 2 holds it after restorePage2FromSnapshot, or a refusal. Every field page 2 reads is checked
// for the shape page 2 reads it in; an absent field reads as empty, exactly as page 2 reads it.
function readSnapshot(snap, xmlText) {
  const extra = Object.keys(snap).filter((k) => !SNAPSHOT_KEYS.includes(k));
  if (extra.length) snapInvalid('carries unexpected fields (' + extra.join(', ') + ')');
  if (snap.xmlText !== xmlText) {
    fail('This claim file is inconsistent — its page-2 snapshot was made on a different measurement of the roof.');
  }
  if ((snap.predominantSystem != null) || (Array.isArray(snap.facetSystems) && snap.facetSystems.length)
      || ('facetSystems' in snap && !Array.isArray(snap.facetSystems)) || snap.shakeMeasurements != null) {
    fail('This claim file is not valid — its page-2 snapshot carries a second material authority.');
  }
  if ('computeMode' in snap && snap.computeMode !== 'live' && snap.computeMode !== 'manual') snapInvalid('has an unknown compute mode');
  if ('nextUserAppNumber' in snap && !(Number.isInteger(snap.nextUserAppNumber) && snap.nextUserAppNumber >= 1)) {
    snapInvalid('has an unreadable next user-item number');
  }
  if ('noHighSlope' in snap && typeof snap.noHighSlope !== 'boolean') snapInvalid('has an unreadable high-slope answer');
  if ('savedAt' in snap && !isStr(snap.savedAt)) snapInvalid('has an unreadable time stamp');

  const valleys = snapPairs(snap, 'selectedValleys', (faces) =>
    (Array.isArray(faces) && faces.every(isId) && new Set(faces).size === faces.length) ? new Set(faces) : null);
  const transitions = snapPairs(snap, 'transitionRepairs', (f) => (isObj(f) ? readTransitionFact(f) : null));
  const groups = snapPairs(snap, 'appurtGroups', (g) => (isId(g) ? g : null));
  const sizes = snapPairs(snap, 'appurtSizes', (s) => (isId(s) ? s : null));
  const ridges = snapPairs(snap, 'ridgeVents', (r) => (isObj(r) && Object.keys(r).length === 2 && isId(r.vent_type)
    && isNum(r.vented_LF) && r.vented_LF > 0) ? { vent_type: r.vent_type, vented_LF: r.vented_LF } : null);
  const high = snapIds(snap, 'highSlopeFacets');
  const replaced = snapIds(snap, 'replacedFacets');
  const excluded = snapIds(snap, 'excludedFacets');
  if (snap.noHighSlope === true && high.length) snapInvalid('both dismisses high-slope charges and marks facets as 2-story');

  const defs = new Map();
  if ('penetrationDefinitions' in snap) {
    if (!isObj(snap.penetrationDefinitions)) snapInvalid('penetrationDefinitions is not a record');
    for (const [id, d] of Object.entries(snap.penetrationDefinitions)) {
      const ok = isObj(d) && Object.keys(d).every((k) => PENETRATION_DEFINITION_KEYS.includes(k))
        && (!('type' in d) || isStr(d.type)) && (!('otherLabel' in d) || isStr(d.otherLabel))
        && (!('otherCategory' in d) || isStr(d.otherCategory)) && (!('operation' in d) || isStr(d.operation))
        && (!('repairEvent' in d) || d.repairEvent === true || d.repairEvent === false || d.repairEvent === null);
      if (!ok || !id) snapInvalid('holds an unreadable definition for penetration ' + id);
      defs.set(id, { type: d.type || '', repairEvent: d.repairEvent === undefined ? null : d.repairEvent,
                     otherLabel: d.otherLabel || '', otherCategory: d.otherCategory || '', operation: d.operation || '' });
    }
  }

  const items = [];
  if ('userAppurtenances' in snap) {
    if (!Array.isArray(snap.userAppurtenances)) snapInvalid('userAppurtenances is not a list');
    const seen = new Set();
    for (const it of snap.userAppurtenances) {
      const ok = isObj(it) && Object.keys(it).every((k) => USER_APP_KEYS.includes(k))
        && USER_APP_REQUIRED.every((k) => k in it)
        && isStr(it.designator) && /^U[0-9]+$/.test(it.designator) && isId(it.hostFacetId) && isStr(it.type)
        && (it.repairEvent === true || it.repairEvent === false || it.repairEvent === null)
        && (it.shape === 'dimensioned' || it.shape === 'point') && isPoint(it.sharedPoint)
        && typeof it.confirmed === 'boolean'
        && (it.width == null || isNum(it.width)) && (it.height == null || isNum(it.height))
        && (it.localPosition == null || (isObj(it.localPosition) && isNum(it.localPosition.x) && isNum(it.localPosition.y)))
        && (it.lastCarvedSF == null || isNum(it.lastCarvedSF))
        && (!('otherLabel' in it) || isStr(it.otherLabel)) && (!('otherCategory' in it) || isStr(it.otherCategory))
        && (!it.confirmed || isObj(it.localPosition));          // a placed item has engine coordinates
      if (!ok) snapInvalid('holds an unreadable user-defined item');
      if (seen.has(it.designator)) snapInvalid('names user-defined item ' + it.designator + ' twice');
      seen.add(it.designator);
      items.push(it);
    }
  }

  let reviews = [];
  if ('reviewConfirmations' in snap) {
    const r = snap.reviewConfirmations;
    if (!Array.isArray(r) || !r.every((k) => isStr(k) && /^[0-9a-f]{32}$/i.test(k))) snapInvalid('holds an unreadable review answer');
    reviews = r.map((k) => k.toLowerCase());
  }
  let eave = null;
  if ('eaveIws' in snap && snap.eaveIws !== null) {
    const e = snap.eaveIws;
    if (!isObj(e) || Object.keys(e).length !== 2 || typeof e.code !== 'boolean' || typeof e.existing !== 'boolean'
        || !(e.code || e.existing)) snapInvalid('holds an unreadable eave ice & water answer');
    eave = { code: e.code, existing: e.existing };
  }
  return { valleys, transitions, groups, sizes, ridges, high, replaced, excluded, defs, items, reviews, eave };
}

function sortedCanon(rows) { return (rows || []).map(canonical).sort(); }
function sameRows(a, b) {
  const x = sortedCanon(a), y = sortedCanon(b);
  return x.length === y.length && x.every((v, i) => v === y[i]);
}
function withoutKeys(row, keys) {
  const o = Object.assign({}, row);
  for (const k of keys) delete o[k];
  return o;
}
// The user row userAppRowsForEngine() emits for a complete item, minus what only the geometry decides (size_class).
function userRowFor(it, view) {
  const row = {
    designator: it.designator, host_facet_id: it.hostFacetId,
    position: { x: Number(it.localPosition.x), y: Number(it.localPosition.y) },
    shape: it.shape, kind_label: String(it.type || 'OTHER').toUpperCase(), repair_event: it.repairEvent === true,
    group: view.groups.get(String(it.designator)) || String(it.designator)
  };
  if (it.shape === 'dimensioned') { row.width = Number(it.width); row.height = Number(it.height); }
  if (String(it.type || '').toUpperCase() === 'OTHER') {
    row.other_label = String(it.otherLabel || '').trim();
    row.other_category = String(it.otherCategory || '').trim() || null;
  }
  return row;
}

// Geometry-free relations between the snapshot and the ONE confirmed selection. Each says: page 2, restored from this
// snapshot, holds exactly the confirmed choices — no fewer (a lost selection) and no more (an invented one).
function snapshotMatchesSelection(view, sel) {
  // valley picks: each pick (valley, facet) is a confirmed intersection, or lies on a confirmed notch; every confirmed
  // intersection is picked; every notch valley is picked on at least one of the notch's facets.
  const picks = [];
  for (const [v, faces] of view.valleys) for (const f of faces) picks.push([v, f]);
  const inter = new Set(sel.valley_intersections.map((r) => String(r.valley_id) + '\u0000' + String(r.face_id)));
  const notches = sel.notches.map((n) => ({ valleys: (n.valley_ids || []).map(String), members: (n.member_face_ids || []).map(String) }));
  for (const [v, f] of picks) {
    if (!inter.has(v + '\u0000' + f) && !notches.some((n) => n.valleys.includes(v) && n.members.includes(f))) {
      snapDiffers('valley ' + v + ' is picked on facet ' + f + ', which the confirmed selection does not repair');
    }
  }
  const pickSet = new Set(picks.map(([v, f]) => v + '\u0000' + f));
  for (const key of inter) if (!pickSet.has(key)) snapDiffers('a confirmed valley repair is not picked: valley ' + key.replace('\u0000', ' on facet '));
  for (const n of notches) {
    for (const v of n.valleys) {
      if (!n.members.some((f) => pickSet.has(v + '\u0000' + f))) snapDiffers('confirmed notch valley ' + v + ' is not picked');
    }
  }
  // every recorded transition answer (damage claim or not) — transitionRepairRows() sends them all
  const trRows = Array.from(view.transitions.entries()).map(([edge_id, f]) => ({ edge_id, metal: f.metal, damaged: f.damaged }));
  if (!sameRows(trRows, sel.transition_repairs)) snapDiffers('different transition answers');
  const ridgeRows = Array.from(view.ridges.entries()).map(([edge_id, r]) => ({ edge_id, vent_type: r.vent_type, vented_LF: r.vented_LF }));
  if (!sameRows(ridgeRows, sel.ridge_vents)) snapDiffers('different ridge vents');
  if (!sameRows(view.high.map((id) => ({ face_id: id, high: true })), sel.high_slope_facets)) snapDiffers('different 2-story facets');
  if (!sameStringSet(view.replaced, sel.replaced_facets.map((r) => r && r.face_id))) snapDiffers('different replaced slopes');
  if (!sameStringSet(view.excluded, sel.excluded_facets || [])) {
    fail('This claim file is inconsistent — its page-2 snapshot and the confirmed selection exclude different facets.');
  }
  if (!sameStringSet(view.reviews, (sel.appurtenance_reviews || []).map((r) => r && String(r.key || '').toLowerCase()))
      || (sel.appurtenance_reviews || []).some((r) => !isObj(r) || r.decision !== 'CONFIRMED')) {
    snapDiffers('different appurtenance review answers');
  }
  if (canonical(view.eave) !== canonical(sel.eave_iws)) snapDiffers('a different eave ice & water answer');
  // XML penetrations: a repair-event definition for exactly the confirmed rows, with the same answers
  const repairDefs = Array.from(view.defs.entries()).filter(([, d]) => d.repairEvent === true && d.type).map(([id]) => id);
  if (!sameStringSet(repairDefs, sel.appurtenances.map((r) => r && r.penetration_face_id))) {
    snapDiffers('different penetrations marked as repair events');
  }
  for (const r of sel.appurtenances) {
    const d = view.defs.get(String(r.penetration_face_id));
    const want = { kind_label: String(d.type).toUpperCase(), group: view.groups.get(String(r.penetration_face_id)) || String(r.penetration_face_id), contacted: true };
    if (want.kind_label === 'OTHER') { want.other_label = String(d.otherLabel || '').trim(); want.other_category = String(d.otherCategory || '').trim() || null; }
    if (isPowerVentType(d.type)) want.operation = String(d.operation || '').toUpperCase();
    const got = {};
    for (const k of Object.keys(want)) got[k] = r[k];
    if (canonical(got) !== canonical(want)) snapDiffers('penetration ' + r.penetration_face_id + ' is described differently');
  }
  // user-defined items: the complete ones are exactly the confirmed user rows, field for field
  const complete = view.items.filter(isUserAppComplete);
  if (!sameStringSet(complete.map((it) => it.designator), sel.user_appurtenance_repairs.map((r) => r && r.designator))) {
    snapDiffers('different user-defined repair items');
  }
  for (const it of complete) {
    const r = sel.user_appurtenance_repairs.find((x) => x.designator === it.designator);
    if (canonical(userRowFor(it, view)) !== canonical(withoutKeys(r, ['size_class']))) {
      snapDiffers('user-defined item ' + it.designator + ' is described differently');
    }
  }
}

// A snapshot may be absent: page 2 then starts EMPTY (restorePage2FromSnapshot finds nothing to restore). That equals
// the confirmed claim only when the confirmed selection is empty too, so an absent snapshot is accepted only then.
function selectionIsEmpty(sel) {
  return SELECTION_ARRAYS.every((k) => sel[k].length === 0) && sel.eave_iws === null
    && !(sel.excluded_facets || []).length && !(sel.appurtenance_reviews || []).length;
}

// Envelope validation + every browser-state invariant. The project's CONTENT (profiles, systems, ids, exclusions
// against the roof, every facet declared, the XML's identity, the selection being computable) is checked by THE
// Python validator, never re-implemented here — this codec resolves no material.
export function decodeClaimObject(obj) {
  if (!isObj(obj)) fail('This is not a claim file.');
  if (LEGACY_CLAIM_FORMATS.includes(obj.format)) {
    fail('This claim was saved by an earlier version of the tool (format "' + obj.format + '", version '
      + String(obj.version || 'unknown') + '). This version saves and opens only the current claim format ('
      + CLAIM_FORMAT + ' schema ' + CLAIM_SCHEMA_VERSION + ') and does not convert older files. Your file has not '
      + 'been changed; re-enter the claim from page 1 to continue it here.');
  }
  if (obj.format !== CLAIM_FORMAT) fail('This is not a claim file for this tool.');
  const ver = obj.schema_version;
  if (typeof ver !== 'number' || !Number.isInteger(ver)) fail('This claim file has no valid schema_version.');
  if (ver > CLAIM_SCHEMA_VERSION) {
    fail('This claim was saved by a newer version of the tool (schema ' + ver + '); this version reads schema '
      + CLAIM_SCHEMA_VERSION + '. Nothing was interpreted.');
  }
  if (ver !== CLAIM_SCHEMA_VERSION) fail('This claim file has an unsupported schema_version (' + ver + ').');
  const state = obj.state;
  if (!isObj(state)) fail('This claim file is incomplete or corrupt — it has no state.');
  const extra = Object.keys(state).filter((k) => !FILE_STATE_KEYS.includes(k));
  if (extra.length) fail('This claim file carries unexpected data (' + extra.join(', ') + ').');
  const pc = state.projectConfig;
  if (!isObj(pc)) fail('This claim file is incomplete — the project configuration is missing.');
  for (const k of HEADER_KEYS) {
    if (!(k in pc)) fail('This claim file is incomplete — the project configuration has no ' + k + '.');
  }
  if (pc.schema_version !== ver) fail('This claim file is inconsistent — its project schema_version differs from the file’s.');
  if (typeof pc.project_id !== 'string' || !pc.project_id.trim()) fail('This claim file is incomplete — the project has no id.');
  if (!isObj(pc.materials) || !isObj(pc.materials.profiles)) fail('This claim file is incomplete — the material profiles are missing.');
  if (!isObj(pc.source) || !isObj(pc.source.facet_structures)) fail('This claim file is incomplete — the measurement source is missing.');
  if (!isObj(pc.selection)) fail('This claim file is incomplete or corrupt — the roof selection is missing.');
  if (PROJECT_CONFIG_SELECTION_KEY in pc.selection) fail('This claim file is corrupt — the selection carries a second project configuration.');
  const cs = state.claimState;
  if (!isObj(cs) || typeof cs.xmlText !== 'string' || !cs.xmlText.trim()) {
    fail('This claim file is incomplete or corrupt — the roof measurement is missing.');
  }
  if ('uiSelection' in cs) fail('This claim file is corrupt — it carries a second copy of the selection.');
  if (cs.shakeMeasurements != null) fail('This claim file is not valid — the claim carries a second material profile (shakeMeasurements).');
  checkSelection(pc.selection, cs.xmlText);
  for (const k of ['page2Payload', 'page2Restore', 'carrierConfirmation', 'reportEvidence']) {
    if (k in state && !isObj(state[k])) fail('This claim file is corrupt — ' + k + ' is not an object.');
  }
  // ---- page 2's intake record: ONE project, ONE roof, ONE soffit (required — page 1 always writes it)
  const pay = state.page2Payload;
  if (!isObj(pay)) fail('This claim file is incomplete — the page-2 intake record is missing.');
  if (pay.projectId !== pc.project_id) {
    fail('This claim file is inconsistent — its page-2 intake belongs to project ' + JSON.stringify(pay.projectId)
      + ', not to this claim’s project ' + JSON.stringify(pc.project_id) + '.');
  }
  if (pay.xmlText !== cs.xmlText) fail('This claim file is inconsistent — its page-2 intake holds a different measurement of the roof than the claim.');
  if ('shakeMeasurements' in pay) fail('This claim file is not valid — the page-2 intake carries a second material profile (shakeMeasurements).');
  const paySoffit = pay.soffitDepthIn === undefined ? null : pay.soffitDepthIn;
  if (paySoffit !== pc.selection.soffit_depth_in) fail('This claim file is inconsistent — the page-2 intake and the confirmed selection disagree on the soffit depth.');
  if ('roofData' in pay) {
    // A DERIVED display copy of the XML (the bridge's roofLayout). It is never written to the session from a file
    // (sessionWritesFor leaves it out); page 1 checks a present copy against the bridge's own layout of this XML
    // (verifyClaimLayout). Here, the geometry-free part: one facet per measured facet, each in its structure.
    const facets = isObj(pay.roofData) && Array.isArray(pay.roofData.facets) ? pay.roofData.facets : null;
    const fs = pc.source.facet_structures;
    const ok = facets && facets.length === Object.keys(fs).length
      && facets.every((f) => isObj(f) && Object.prototype.hasOwnProperty.call(fs, String(f.facet_id))
                             && String(f.structure_id || '') === fs[String(f.facet_id)]);
    if (!ok) fail('This claim file is inconsistent — its page-2 roof layout does not match the project’s measured facets.');
  }
  if ('estimateText' in pay && !isStr(pay.estimateText)) fail('This claim file is not valid — the page-2 intake’s estimate text is unreadable.');
  if ('estimateText' in cs && !isStr(cs.estimateText)) fail('This claim file is not valid — the claim’s estimate text is unreadable.');
  if ('carrierEstimatePresent' in cs && typeof cs.carrierEstimatePresent !== 'boolean') fail('This claim file is not valid — the claim’s estimate flag is unreadable.');
  // ---- page 2's workbench snapshot (ARC-03a r2): readable by page 2, and rebuilding exactly the confirmed selection.
  const snap = state.page2Restore;
  if (isObj(snap)) snapshotMatchesSelection(readSnapshot(snap, cs.xmlText), pc.selection);
  else if (!selectionIsEmpty(pc.selection)) {
    fail('This claim file is incomplete — it has no page-2 workbench snapshot, so page 2 would open empty instead of '
      + 'showing the confirmed selection. Re-save the claim from the current tool.');
  }
  const cc = state.carrierConfirmation;
  if (isObj(cc)) {
    if ('vci' in cc && !isObj(cc.vci)) fail('This claim file is not valid — the claim header must be a record.');
    for (const k of ['rows', 'displayRows']) {
      if (k in cc && (!Array.isArray(cc[k]) || cc[k].some((r) => !isObj(r)))) fail('This claim file is not valid — carrier ' + k + ' must be a list of records.');
    }
  }
  if (isObj(state.reportEvidence)) checkEvidence(state.reportEvidence);
  return obj;
}

// The session writes a validated claim produces: key -> JSON string. Pure; nothing is written here.
export function sessionWritesFor(obj) {
  const st = obj.state;
  const header = headerOf(st.projectConfig);
  const uiSelection = Object.assign({}, st.projectConfig.selection, { [PROJECT_CONFIG_SELECTION_KEY]: header });
  const claimState = Object.assign({}, st.claimState, { uiSelection });
  const writes = {
    projectConfig: JSON.stringify(header),
    claimState: JSON.stringify(claimState),
    page2Selection: JSON.stringify(uiSelection),
  };
  for (const k of ['page2Restore', 'carrierConfirmation', 'reportEvidence']) {
    if (st[k] !== undefined) writes[k] = JSON.stringify(st[k]);
  }
  // ARC-03a r2: the roof layout is DERIVED — a file's copy is never written. The only layout a load writes is the one
  // the bridge built from this file's own XML and verifyClaimLayout() accepted; without it the session carries none,
  // and page 1 rebuilds it from the XML through the bridge before showing the roof.
  const payload = Object.assign({}, st.page2Payload);
  delete payload.roofData;
  if (VERIFIED_LAYOUT.has(obj)) payload.roofData = VERIFIED_LAYOUT.get(obj);
  writes.page2Payload = JSON.stringify(payload);
  const ev = st.reportEvidence;
  const pending = (ev && Array.isArray(ev.photos)) ? ev.photos.map((p) => p.name || '(unnamed photo)') : [];
  writes.loadNotice = JSON.stringify({ fromVersion: CLAIM_FORMAT + ' schema ' + obj.schema_version,
    runningVersion: CLAIM_FORMAT + ' schema ' + CLAIM_SCHEMA_VERSION, versionMismatch: false, photosPending: pending });
  return writes;
}

// ============================================================= the roof layout and the snapshot ON THIS ROOF (r2)
// page2Payload.roofData is a DERIVED display copy of the XML (the bridge's roofLayout). A file's copy is never written
// to the session: sessionWritesFor() leaves it out, and the only layout a load writes is the one page 1 has the
// bridge build from the file's own XML, after verifyClaimLayout() has accepted the file against it. Page 1 calls this
// between THE Python validator and the commit; it refuses (nothing written):
//   * a file whose own roofData is not exactly that layout (an altered or foreign copy is never shown as this roof);
//   * a snapshot naming a valley, facet, penetration, transition or ridge that is not on this roof;
//   * a snapshot from which page 2, on this roof, would rebuild a selection other than the confirmed one.
const VERIFIED_LAYOUT = new WeakMap();

export function verifyClaimLayout(obj, layout) {
  if (!isObj(layout) || !Array.isArray(layout.facets) || !layout.facets.length) {
    fail('The claim’s roof measurement could not be laid out, so the claim cannot be checked.');
  }
  const st = obj.state;
  const pay = st.page2Payload;
  if ('roofData' in pay && canonical(pay.roofData) !== canonical(layout)) {
    fail('This claim file is inconsistent — its saved roof layout is not the layout of its own roof measurement '
      + '(the copy was altered, or made by a different build). Re-save the claim from the current tool.');
  }
  const sel = st.projectConfig.selection;
  if (isObj(st.page2Restore)) snapshotMatchesRoof(readSnapshot(st.page2Restore, st.claimState.xmlText), sel, layout);
  VERIFIED_LAYOUT.set(obj, layout);
  return obj;
}

function snapshotMatchesRoof(view, sel, layout) {
  const list = (k) => (Array.isArray(layout[k]) ? layout[k] : []);
  const facets = new Map(list('facets').map((f) => [String(f.facet_id), f]));
  const valleyIds = new Set(list('valleys').map((v) => String(v.valley_id)));
  const transitionIds = new Set(list('transitions').map((t) => String(t.edge_id)));
  const ridgeIds = new Set(list('ridges').map((r) => String(r.edge_id)));
  const pens = list('penetrations');
  const penIds = new Set(pens.map((p) => String(p.penetration_id || '')));
  const notOnRoof = (what) => fail('This claim file is inconsistent — its page-2 workbench snapshot names ' + what
    + ', which is not on this roof.');
  for (const [v, faces] of view.valleys) {
    if (!valleyIds.has(v)) notOnRoof('valley ' + v);
    for (const f of faces) if (!facets.has(f)) notOnRoof('facet ' + f);
  }
  for (const id of view.transitions.keys()) if (!transitionIds.has(id)) notOnRoof('transition ' + id);
  for (const id of view.ridges.keys()) if (!ridgeIds.has(id)) notOnRoof('ridge ' + id);
  for (const id of view.defs.keys()) if (!penIds.has(id)) notOnRoof('penetration ' + id);
  for (const id of view.high.concat(view.replaced, view.excluded)) if (!facets.has(id)) notOnRoof('facet ' + id);
  for (const it of view.items) if (!facets.has(it.hostFacetId)) notOnRoof('host facet ' + it.hostFacetId);
  const markerIds = new Set(Array.from(penIds).concat(view.items.map((it) => it.designator)));
  for (const id of view.groups.keys()) if (!markerIds.has(id)) notOnRoof('appurtenance ' + id);

  // Compared field for field, except `label`: a label is display text page 2 derives from the roof, not a choice —
  // the snapshot holds none, and the engine reads the confirmed selection's own.
  const rebuilt = selectionFromSnapshot(view, layout, facets);
  const unlabelled = (rows) => (rows || []).map((r) => (isObj(r) ? withoutKeys(r, ['label']) : r));
  for (const k of ['valley_intersections', 'notches', 'appurtenances', 'user_appurtenance_repairs', 'replaced_facets']) {
    if (!sameRows(unlabelled(rebuilt[k]), unlabelled(sel[k]))) snapDiffers('on this roof it rebuilds different ' + k.replace(/_/g, ' '));
  }
}

// What page 2's buildUiSelection() rebuilds, on this roof, for the snapshot-derived keys — the same steps in the same
// order (valley picks -> merged-slope notches; replaced facets drop their picks; XML penetrations in layout order;
// complete user items; chimney size = the override for the group's signature, else the size its combined footprint
// suggests). The geometry is the bridge's layout, read exactly as page 2 reads it.
function selectionFromSnapshot(view, layout, facets) {
  const slopes = Array.isArray(layout.merged_slopes) ? layout.merged_slopes : [];
  const faceLabel = (id) => { const f = facets.get(String(id)); return (f && (f.designator || f.facet_id)) || String(id); };
  const valley_intersections = [];
  const collectedBySlope = new Map();
  const slopeForPick = (faceId, valleyId) => slopes.find((slope) => {
    const members = Array.isArray(slope.member_face_ids) ? slope.member_face_ids.map(String) : [];
    const valleys = Array.isArray(slope.valley_line_ids) ? slope.valley_line_ids.map(String) : [];
    return members.includes(String(faceId)) && valleys.includes(String(valleyId));
  });
  const sortedIds = Array.from(view.valleys.keys()).filter((v) => view.valleys.get(v).size).sort(naturalCompare);
  for (const valleyId of sortedIds) {
    for (const faceId of Array.from(view.valleys.get(valleyId)).sort(naturalCompare)) {
      const slope = slopeForPick(faceId, valleyId);
      if (slope) {
        const key = (slope.member_face_ids || []).map(String).sort(naturalCompare).join('+');
        if (!collectedBySlope.has(key)) {
          collectedBySlope.set(key, { member_face_ids: (slope.member_face_ids || []).map(String), valley_ids: new Set() });
        }
        collectedBySlope.get(key).valley_ids.add(String(valleyId));
      } else {
        valley_intersections.push({ face_id: faceId, valley_id: valleyId, claim_valley_lf: true });
      }
    }
  }
  const notches = [];
  for (const entry of collectedBySlope.values()) {
    notches.push({ label: `Notch ${entry.member_face_ids.join('+')}`, member_face_ids: entry.member_face_ids,
                   valley_ids: Array.from(entry.valley_ids).sort(naturalCompare) });
  }
  const replaced_facets = Array.from(view.replaced).sort(naturalCompare)
    .map((id) => ({ face_id: String(id), label: `Slope ${faceLabel(id)}` }));
  const replacedIds = new Set(replaced_facets.map((r) => r.face_id));

  // appurtenance markers, groups and chimney sizes, as page 2 keys them
  const markers = [];
  for (const pen of (Array.isArray(layout.penetrations) ? layout.penetrations : [])) {
    const id = String(pen.penetration_id || '');
    const def = view.defs.get(id);
    if (!def || !def.type) continue;
    markers.push({ id, kind: 'xml', areaSF: Number(pen.area_SF || 0) });
  }
  for (const it of view.items) {
    if (!it.type || !it.hostFacetId) continue;
    markers.push({ id: String(it.designator), kind: 'user',
                   areaSF: it.shape === 'dimensioned' ? Number(it.width || 0) * Number(it.height || 0) : 0 });
  }
  const groupMembers = (mid) => {
    const gid = view.groups.get(String(mid)) || null;
    if (!gid) return [String(mid)];
    const out = [];
    for (const [m, g] of view.groups.entries()) if (g === gid) out.push(m);
    return out.length ? out.sort(naturalCompare) : [String(mid)];
  };
  const markerArea = (mid) => { const m = markers.find((x) => x.id === String(mid)); return m ? m.areaSF : 0; };
  const chimneySize = (mid) => view.sizes.get(groupMembers(mid).slice().sort(naturalCompare).join('+'))
    || suggestSizeFromArea(groupMembers(mid).map(markerArea).reduce((a, b) => a + b, 0));

  const appurtenances = [];
  for (const pen of (Array.isArray(layout.penetrations) ? layout.penetrations : [])) {
    const id = String(pen.penetration_id || '');
    const def = view.defs.get(id) || { type: '', repairEvent: null, otherLabel: '', otherCategory: '', operation: '' };
    if (def.repairEvent !== true || !def.type) continue;
    const host = String(pen.host_facet_id || '');
    const userType = def.type || 'Appurtenance';
    const row = { label: `${typeDisplayLabel(userType, def.otherLabel)} on ${faceLabel(host)}`, host_face_id: host,
                  penetration_face_id: id, kind_label: String(userType).toUpperCase(),
                  group: view.groups.get(id) || id, contacted: true };
    if (String(userType).toUpperCase() === 'CHIMNEY') row.size_class = chimneySize(id);
    if (String(userType).toUpperCase() === 'OTHER') {
      row.other_label = String(def.otherLabel || '').trim();
      row.other_category = String(def.otherCategory || '').trim() || null;
    }
    if (isPowerVentType(userType)) row.operation = String(def.operation || '').toUpperCase();
    appurtenances.push(row);
  }
  const user_appurtenance_repairs = view.items.filter(isUserAppComplete).map((it) => {
    const row = userRowFor(it, view);
    if (String(it.type || '').toUpperCase() === 'CHIMNEY') row.size_class = chimneySize(it.designator);
    return row;
  });
  return {
    valley_intersections: valley_intersections.filter((r) => !replacedIds.has(String(r.face_id))),
    notches: notches.filter((n) => !(n.member_face_ids || []).some((m) => replacedIds.has(String(m)))),
    appurtenances, user_appurtenance_repairs, replaced_facets
  };
}

// ------------------------------------------------------------------------------------------ the transaction
export const CLAIM_TXN_KEY = 'claimLoadTxn';                 // the commit marker
const TXN_STAGE = CLAIM_TXN_KEY + '.';                       // staged values: woodShakeWorkbench.claimLoadTxn.<key>
const TXN_KEYS = CLAIM_SESSION_KEYS.concat(['loadNotice']);  // every key a load owns

export class ClaimSettlePending extends ClaimCodecError {}

function clearStaging(storage) {
  for (const k of TXN_KEYS) {
    try { storage.removeItem(CLAIM_PREFIX + TXN_STAGE + k); } catch (_e) { /* inactive without the marker */ }
  }
}

function unchanged(e) {
  return new ClaimCodecError('The claim could not be written to this browser session (' + (e && e.message ? e.message : e)
    + '). Free some browser storage (close other tabs of this tool, or clear this site’s data) and load the file '
    + 'again. Your current claim is unchanged.');
}

// Load a VALIDATED claim. Throws ClaimCodecError (nothing changed) or ClaimSettlePending (committed — the file's claim
// is now the active claim — but not yet settled; every page will finish it before reading).
export function applyClaimToSession(storage, obj) {
  const writes = sessionWritesFor(obj);
  // An earlier load that committed but never settled IS the active claim: finish it before replacing it.
  if (storage.getItem(CLAIM_PREFIX + CLAIM_TXN_KEY) !== null) settleClaimLoad(storage);
  clearStaging(storage);                                     // leftovers of an earlier, failed staging
  try {                                                      // STAGE — no claim key is touched
    for (const [k, v] of Object.entries(writes)) storage.setItem(CLAIM_PREFIX + TXN_STAGE + k, v);
  } catch (e) {
    clearStaging(storage);
    throw unchanged(e);
  }
  try {                                                      // COMMIT — one setItem; it either happens or it does not
    storage.setItem(CLAIM_PREFIX + CLAIM_TXN_KEY, JSON.stringify({ v: 1, keys: Object.keys(writes) }));
  } catch (e) {
    clearStaging(storage);
    throw unchanged(e);
  }
  settleClaimLoad(storage);                                  // SETTLE — may leave the load pending, never half-read
}

// Finish a committed load: the staged values replace the claim keys. Idempotent; safe to retry after any failure.
// -> true when it settled a load, false when none was pending. Throws ClaimSettlePending when it cannot finish.
export function settleClaimLoad(storage) {
  const raw = storage.getItem(CLAIM_PREFIX + CLAIM_TXN_KEY);
  if (raw === null) return false;
  let marker = null;
  try { marker = JSON.parse(raw); } catch (_e) { marker = null; }
  if (!isObj(marker) || marker.v !== 1 || !Array.isArray(marker.keys) || marker.keys.some((k) => !TXN_KEYS.includes(k))) {
    throw new ClaimSettlePending('A claim load in this browser tab was interrupted and its record is unreadable, so '
      + 'nothing can be shown safely. Close this tab, open the tool in a new tab and load the claim file again.');
  }
  const staged = {};
  for (const k of marker.keys) {
    const v = storage.getItem(CLAIM_PREFIX + TXN_STAGE + k);
    if (v === null) {
      throw new ClaimSettlePending('A claim load in this browser tab was interrupted and is incomplete, so nothing can '
        + 'be shown safely. Close this tab, open the tool in a new tab and load the claim file again.');
    }
    staged[k] = v;
  }
  try {
    for (const k of TXN_KEYS) storage.removeItem(CLAIM_PREFIX + k);   // superseded at the commit; frees space first
    for (const k of marker.keys) storage.setItem(CLAIM_PREFIX + k, staged[k]);
  } catch (e) {
    throw new ClaimSettlePending('The claim file was accepted, but this browser could not finish storing it ('
      + (e && e.message ? e.message : e) + '). Nothing is shown until it can. Free some browser storage and reload '
      + 'this page — the load then finishes by itself.');
  }
  clearStaging(storage);
  storage.removeItem(CLAIM_PREFIX + CLAIM_TXN_KEY);
  return true;
}

// Every page calls this (through a dynamic import, only when the marker exists) BEFORE reading any claim key. If the
// pending load cannot be finished it shows why and throws, so the page's own code never runs on a half-written claim.
export function settleOrStop(storage, doc) {
  try { return settleClaimLoad(storage); }
  catch (e) {
    try {
      const box = doc.createElement('div');
      box.setAttribute('role', 'alert');
      box.setAttribute('data-claim-load-pending', '');
      box.style.cssText = 'position:fixed;inset:0;z-index:99999;background:#fff;color:#7a1b1b;padding:32px;font:16px system-ui,sans-serif;';
      box.textContent = e && e.message ? e.message : String(e);
      (doc.body || doc.documentElement).appendChild(box);
    } catch (_e) { /* the throw below still stops the page */ }
    throw e;
  }
}
