/**
 * Mock Data Factories
 * Factory functions to create test data
 */

import type {
  ShotAnalysis,
  SessionSummary,
  HealthResponse
} from '../../lib/api';

import type {
  Profile,
  Session,
  Shot,
  UserStats,
} from '../../lib/supabase';

// ============================================================================
// API Mock Data
// ============================================================================

export const createMockShotAnalysis = (
  overrides?: Partial<ShotAnalysis>
): ShotAnalysis => ({
  shot_number: 1,
  made: true,
  miss_type: null,
  form_rating: 8.5,
  feedback: 'Good shooting form with solid follow-through',
  key_issue: null,
  quick_cue: 'Keep your elbow in',
  elbow_angle_load: 90,
  elbow_angle_release: 45,
  wrist_height_release: 2.1,
  knee_bend_load: 110,
  hip_angle_load: 0,
  elbow_height_load: 0,
  heel_height_release: 0,
  trunk_lean_release: 0,
  stance_width: 0,
  shoulder_level_diff: 0,
  elbow_lateral_offset: 0,
  camera_angle: 'side',
  thumbnail: 'base64encodedimage',
  timestamp: 5.2,
  ...overrides,
});

export const createMockSessionSummary = (
  overrides?: Partial<SessionSummary>
): SessionSummary => ({
  total_shots: 10,
  shots_made: 7,
  shots_missed: 3,
  shooting_percentage: 70,
  average_form_rating: 8.2,
  session_feedback: 'Great session! Your form is improving.',
  drill_suggestions: [
    'Practice free throws with emphasis on follow-through',
    'Work on consistent release point',
  ],
  shots: [
    createMockShotAnalysis({ shot_number: 1, made: true, timestamp: 5.2 }),
    createMockShotAnalysis({ shot_number: 2, made: false, timestamp: 10.5, miss_type: 'short' }),
    createMockShotAnalysis({ shot_number: 3, made: true, timestamp: 15.8 }),
  ],
  ...overrides,
});

export const createMockHealthResponse = (
  overrides?: Partial<HealthResponse>
): HealthResponse => ({
  status: 'ok',
  modules_available: true,
  gemini_configured: true,
  database_available: true,
  ...overrides,
});

// ============================================================================
// Supabase Mock Data
// ============================================================================

export const createMockProfile = (
  overrides?: Partial<Profile>
): Profile => ({
  id: 'user-123',
  email: 'test@example.com',
  full_name: 'Test User',
  skill_level: 'intermediate',
  shooting_hand: 'right',
  height_inches: 72,
  focus_areas: ['shooting', 'form'],
  primary_goal: 'Improve shooting percentage',
  preferred_distance: 'mid-range',
  plays_organized: true,
  practice_frequency: '3-4 times per week',
  notifications_enabled: true,
  subscription_tier: 'free',
  subscription_expires_at: null,
  total_sessions: 5,
  total_shots: 50,
  total_makes: 35,
  last_session_at: '2026-01-24T10:00:00Z',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-24T10:00:00Z',
  ...overrides,
});

export const createMockSession = (
  overrides?: Partial<Session>
): Session => ({
  id: 'session-123',
  user_id: 'user-123',
  started_at: '2026-01-24T10:00:00Z',
  ended_at: '2026-01-24T10:30:00Z',
  shot_count: 10,
  make_count: 7,
  miss_count: 3,
  shooting_percentage: 70,
  average_form_rating: 8.2,
  session_feedback: 'Great session!',
  drill_suggestions: ['Practice free throws'],
  focus_area: 'shooting',
  location: 'Home gym',
  notes: 'Felt good today',
  shooting_hand: 'right',
  duration_seconds: 1800,
  video_duration_seconds: 30,
  created_at: '2026-01-24T10:00:00Z',
  ...overrides,
});

export const createMockShot = (
  overrides?: Partial<Shot>
): Shot => ({
  id: 'shot-123',
  session_id: 'session-123',
  user_id: 'user-123',
  shot_number: 1,
  made: true,
  miss_type: null,
  elbow_angle_load: 90,
  elbow_angle_release: 45,
  wrist_height_release: 2.1,
  knee_bend_load: 110,
  hip_angle_load: 0,
  elbow_height_load: 0,
  heel_height_release: 0,
  trunk_lean_release: 0,
  stance_width: 0,
  shoulder_level_diff: 0,
  elbow_lateral_offset: 0,
  form_rating: 8.5,
  feedback: 'Good form',
  key_issue: null,
  quick_cue: 'Keep elbow in',
  camera_angle: 'side',
  thumbnail_url: 'https://example.com/thumbnail.jpg',
  created_at: '2026-01-24T10:05:00Z',
  ...overrides,
});

export const createMockUserStats = (
  overrides?: Partial<UserStats>
): UserStats => ({
  totalSessions: 5,
  totalShots: 50,
  totalMakes: 35,
  avgShootingPercentage: 70,
  avgFormRating: 8.2,
  ...overrides,
});

// ============================================================================
// Supabase Response Mocks
// ============================================================================

/**
 * Create a mock Supabase response
 */
export const createSupabaseResponse = <T>(data: T, error: any = null) => ({
  data,
  error,
});

/**
 * Create a mock Supabase error
 */
export const createSupabaseError = (message: string, code?: string) => ({
  message,
  code,
  details: message,
  hint: null,
});

/**
 * Create a mock authenticated user
 */
export const createMockUser = (id = 'user-123') => ({
  id,
  email: 'test@example.com',
  app_metadata: {},
  user_metadata: {},
  aud: 'authenticated',
  created_at: '2026-01-01T00:00:00Z',
});
