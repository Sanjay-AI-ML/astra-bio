export const crewNutrients = ['energy', 'protein', 'vitamin_c'];

/** Validate reviewed planning inputs without inferring targets from lab examples. */
export function validateCrewRoster(profiles, requireReviewed = true) {
  if (!Array.isArray(profiles) || profiles.length < 1 || profiles.length > 12) return 'Use between 1 and 12 crew profiles.';
  const ids = new Set();
  for (const profile of profiles) {
    if (!profile || typeof profile !== 'object' || typeof profile.profile_id !== 'string' || !profile.profile_id.trim() || ids.has(profile.profile_id)) return 'Each crew profile needs a unique stable ID.';
    ids.add(profile.profile_id);
    if (typeof profile.name !== 'string' || !profile.name.trim()) return 'Give each crew profile a name.';
    for (const nutrient of crewNutrients) {
      const value = profile.targets?.[nutrient];
      if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return 'Give each crew member positive energy, protein and vitamin C targets.';
    }
    if (profile.age != null && (!Number.isInteger(profile.age) || profile.age < 0)) return 'Age must be a nonnegative integer or left blank.';
    if (profile.sex != null && !['unspecified', 'male', 'female'].includes(profile.sex)) return 'Choose a supported reference sex or leave it unspecified.';
    if (requireReviewed && profile.targets_reviewed !== true) return 'Review each person’s planning targets before replanning.';
  }
  return '';
}

export function crewRosterSignature(profiles = []) {
  return JSON.stringify(profiles.map(profile => [profile.profile_id, profile.name,
    ...crewNutrients.map(nutrient => Number(profile.targets?.[nutrient]))]));
}
