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
    low: 'Extend your elbow fully on release',
    high: "Don't overextend — snap the wrist instead",
  },
  trunk_lean_release: {
    low: 'Stay tall through your release',
    high: 'Lean into your shot slightly',
  },
  knee_bend_load: {
    low: 'Bend your knees more at the set point',
    high: "Don't over-bend — stay athletic",
  },
  hip_angle_load: {
    low: 'Sit into your shot more',
    high: 'Stay more upright at the set point',
  },
  heel_height_release: {
    low: 'Get up on your toes at release',
    high: "Stay grounded — don't jump too much",
  },
  wrist_height_release: {
    low: 'Get the ball higher at release',
    high: 'Release point is good — focus elsewhere',
  },
  elbow_angle_load: {
    low: 'Bring the ball up higher to your set point',
    high: 'Keep a tighter set point',
  },
  elbow_height_load: {
    low: 'Raise your elbow higher at the set point',
    high: 'Elbow height is good',
  },
  stance_width: {
    low: 'Widen your stance slightly',
    high: 'Narrow your stance to shoulder width',
  },
  elbow_lateral_offset: {
    low: 'Tuck your elbow in',
    high: 'Elbow alignment is solid',
  },
  shoulder_level_diff: {
    low: 'Keep your shoulders level',
    high: 'Keep your shoulders level',
  },
};

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
