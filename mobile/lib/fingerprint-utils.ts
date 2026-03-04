/**
 * Fingerprint Utilities
 * Pure client-side functions for shot signature comparison and coaching insights
 */

import type { ShotFingerprint } from './api';
import type { Session, Profile } from './supabase';

// ============================================================================
// Constants (replicated from api/main.py lines 205-247)
// ============================================================================

export const METRIC_LABELS: Record<string, string> = {
  elbow_angle_load: 'Elbow Set Point',
  elbow_angle_release: 'Elbow Extension',
  wrist_height_release: 'Release Height',
  knee_bend_load: 'Knee Bend',
  hip_angle_load: 'Hip Angle',
  elbow_height_load: 'Elbow Height',
  heel_height_release: 'Heel Rise',
  trunk_lean_release: 'Trunk Lean',
  stance_width: 'Stance Width',
  shoulder_level_diff: 'Shoulder Level',
  elbow_lateral_offset: 'Elbow Alignment',
};

export const CUE_TEMPLATES: Record<string, { low: string; high: string }> = {
  elbow_angle_release: {
    low: 'Extend your elbow fully at release — finish with your arm straight',
    high: "Don't overextend your elbow — snap your wrist to finish the shot",
  },
  trunk_lean_release: {
    low: "Keep your chest upright through the release — don't lean forward",
    high: "You're falling backward — keep your torso centered over your hips at release",
  },
  knee_bend_load: {
    low: 'Bend your knees deeper before shooting — sit into your legs',
    high: "Don't over-bend your knees — stay in an athletic stance",
  },
  hip_angle_load: {
    low: 'Hinge at your hips more — sit into your shot like sitting in a chair',
    high: "You're sitting too deep — stay more upright at the set point",
  },
  heel_height_release: {
    low: 'Push off the balls of your feet at release — transfer leg power upward',
    high: "You're jumping too high — focus on controlled lift, push energy into the shot",
  },
  wrist_height_release: {
    low: 'Release the ball higher — finish with your hand above your eyes',
    high: 'Release height is good — focus on other mechanics',
  },
  elbow_angle_load: {
    low: 'Bring the ball higher to your set point — elbow at forehead level',
    high: 'Compact your set point — keep your shooting elbow tighter to your body',
  },
  elbow_height_load: {
    low: 'Raise your shooting elbow higher at the set point — aim for eye level',
    high: 'Your elbow is too high at the set point — lower it slightly for comfort',
  },
  stance_width: {
    low: 'Widen your stance to shoulder width for a stable base',
    high: 'Narrow your stance to shoulder width — too wide limits your power transfer',
  },
  elbow_lateral_offset: {
    low: 'Tuck your shooting elbow in — align it under the ball',
    high: 'Elbow alignment is solid — keep it tucked',
  },
  shoulder_level_diff: {
    low: 'Your shooting shoulder is dropping — keep both shoulders level at release',
    high: 'Your shooting shoulder is rising too high — relax it to stay level',
  },
};

// Metrics excluded from shot-to-signature comparison (style preferences, not scored)
export const EXCLUDED_METRICS = new Set(['dip_depth']);

// ============================================================================
// Types
// ============================================================================

export type Severity = 'minor' | 'notable' | 'significant';
export type Direction = 'low' | 'high';

export interface MetricDeviation {
  metric: string;
  label: string;
  shotValue: number;
  makeAvg: number;
  makeStd: number;
  zScore: number;
  direction: Direction;
  cue: string;
  severity: Severity;
}

// ============================================================================
// Core Functions
// ============================================================================

/**
 * Compare a shot's metrics to the user's make signature.
 * Returns deviations sorted by absolute z-score (most significant first).
 */
export function compareShotToSignature(
  shot: Record<string, any>,
  makeSignature: Record<string, { avg: number; std: number }>
): MetricDeviation[] {
  const deviations: MetricDeviation[] = [];

  for (const metric in makeSignature) {
    if (EXCLUDED_METRICS.has(metric)) continue;
    const shotValue = shot[metric];
    if (shotValue === null || shotValue === undefined) continue;

    const { avg: makeAvg, std: makeStd } = makeSignature[metric];
    const zScore = (shotValue - makeAvg) / Math.max(makeStd, 0.01);

    const direction: Direction = zScore < 0 ? 'low' : 'high';
    const absZ = Math.abs(zScore);
    let severity: Severity;
    if (absZ > 1.5) {
      severity = 'significant';
    } else if (absZ > 1.0) {
      severity = 'notable';
    } else {
      severity = 'minor';
    }

    const cueTemplate = CUE_TEMPLATES[metric];
    const cue = cueTemplate ? cueTemplate[direction] : 'Focus on consistency';
    const label = METRIC_LABELS[metric] || metric;

    deviations.push({
      metric,
      label,
      shotValue,
      makeAvg,
      makeStd,
      zScore,
      direction,
      cue,
      severity,
    });
  }

  return deviations.sort((a, b) => Math.abs(b.zScore) - Math.abs(a.zScore));
}

/**
 * Get top N deviations, filtering to notable/significant only.
 */
export function getTopDeviations(
  deviations: MetricDeviation[],
  limit: number = 3
): MetricDeviation[] {
  return deviations
    .filter(d => d.severity === 'notable' || d.severity === 'significant')
    .slice(0, limit);
}

/**
 * Generate session insight comparing to fingerprint trends.
 * Returns a 1-liner like "5% above your recent average" or null.
 */
export function generateSessionInsight(
  session: Session,
  fingerprint: ShotFingerprint | null
): string | null {
  if (!fingerprint || !fingerprint.fingerprint_ready) return null;
  if (!fingerprint.trend || fingerprint.trend.shooting_pct.length === 0) return null;

  const sessionPct = session.shooting_percentage;
  const trendPcts = fingerprint.trend.shooting_pct;
  const avgPct = trendPcts.reduce((sum: number, pct: number) => sum + pct, 0) / trendPcts.length;

  const diff = sessionPct - avgPct;
  const absDiff = Math.abs(diff);

  if (absDiff < 3) {
    return 'On par with your recent average';
  } else if (diff > 0) {
    return `${Math.round(absDiff)}% above your recent average`;
  } else {
    return `${Math.round(absDiff)}% below your recent average`;
  }
}

/**
 * Generate contextual greeting based on fingerprint state and trends.
 */
export function generateGreeting(
  profile: Profile | null,
  fingerprint: ShotFingerprint | null
): string {
  const name = profile?.full_name?.split(' ')[0] || 'Shooter';

  if (!fingerprint || !fingerprint.fingerprint_ready) {
    return `Welcome, ${name}`;
  }

  const trend = fingerprint.trend_label;

  if (trend === 'Improving') {
    return `Nice progress, ${name}!`;
  } else if (trend === 'Off lately') {
    return `Let's get back on track, ${name}`;
  } else if (trend === 'Consistent') {
    return `Stay locked in, ${name}`;
  } else {
    return `Welcome back, ${name}`;
  }
}
