export const CREW_NUTRITION_DRAFT_KEY = 'astra-bio.crew-nutrition-draft.v1';

/** Preserve the operator's current logs and their explicit sample provenance. */
export function readNutritionDraft() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(CREW_NUTRITION_DRAFT_KEY) || 'null');
    if (saved?.schema_version !== 1 || !Array.isArray(saved.profiles) || !Array.isArray(saved.entries)
      || !saved.complete_days || typeof saved.complete_days !== 'object') return null;
    if (!saved.profiles.every(profile => typeof profile?.profile_id === 'string' && profile.targets)) return null;
    return {...saved, sample: saved.sample?.sample_only === true ? saved.sample : null};
  } catch { return null; }
}

export function saveNutritionDraft(draft) {
  try { sessionStorage.setItem(CREW_NUTRITION_DRAFT_KEY, JSON.stringify({...draft, schema_version: 1})); }
  catch { /* Continue normally when browser storage is unavailable. */ }
}

/** Share known current records only; an added person never inherits another's labs. */
export function currentCrewState({profiles = [], entries = [], complete_days = {}, sample = null}) {
  const ids = new Set(profiles.map(profile => profile.profile_id));
  const example = sample?.sample_only === true ? sample : null;
  return {
    profiles,
    entries: entries.filter(entry => ids.has(entry.profile_id)),
    complete_days: Object.fromEntries(Object.entries(complete_days).filter(([key]) => ids.has(key.split(':')[0]))),
    blood_samples: (example?.blood_samples || []).filter(row => ids.has(row.profile_id)),
    conditions: Object.fromEntries(Object.entries(example?.conditions || {}).filter(([id]) => ids.has(id))),
    sample_only: !!example,
    scope: example?.scope || 'Operator-entered crew records; clinical context must be reviewed.',
    references: example?.references || {},
  };
}
