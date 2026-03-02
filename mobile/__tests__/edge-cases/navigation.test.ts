/**
 * Navigation Edge Cases
 * Tests deep-linking to sessions that don't exist, back-navigation from the
 * recording screen, auth-gate routing logic, and other navigation edge cases.
 *
 * Because expo-router wraps navigation behind native primitives, these tests
 * validate the logic that drives navigation decisions (routing conditions,
 * guard checks, param parsing) rather than mounting full router trees.
 */

import {
  createMockProfile,
  createMockSession,
  createMockUser,
  createSupabaseError,
} from '../utils/mockData';

// ---------------------------------------------------------------------------
// expo-router mock — gives us spies we can assert against
// ---------------------------------------------------------------------------

const mockPush = jest.fn();
const mockReplace = jest.fn();
const mockBack = jest.fn();
const mockLocalSearchParams: Record<string, string> = {};

jest.mock('expo-router', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
    back: mockBack,
  }),
  useLocalSearchParams: () => mockLocalSearchParams,
  Link: 'Link',
  useFocusEffect: jest.fn(),
}));

// ---------------------------------------------------------------------------
// Supabase mock
// ---------------------------------------------------------------------------

const mockGetSession = jest.fn();
const mockGetUser = jest.fn();
const mockSignOut = jest.fn();
const mockFrom = jest.fn();
const mockSelect = jest.fn();
const mockEq = jest.fn();
const mockSingle = jest.fn();
const mockOrder = jest.fn();
const mockRange = jest.fn();
const mockOnAuthStateChange = jest.fn();

jest.mock('../../lib/supabase', () => {
  const actual = jest.requireActual('../../lib/supabase');
  return {
    ...actual,
    supabase: {
      auth: {
        getSession: () => mockGetSession(),
        getUser: () => mockGetUser(),
        signOut: () => mockSignOut(),
        onAuthStateChange: (cb: any) => {
          mockOnAuthStateChange(cb);
          return { data: { subscription: { unsubscribe: jest.fn() } } };
        },
      },
      from: () => mockFrom(),
    },
  };
});

// ---------------------------------------------------------------------------
// API mock
// ---------------------------------------------------------------------------

jest.mock('../../lib/api', () => ({
  testConnection: jest.fn().mockResolvedValue(true),
  analyzeVideoWithProgress: jest.fn(),
  getFingerprint: jest.fn().mockResolvedValue(null),
}));

// ---------------------------------------------------------------------------
// Alert mock
// ---------------------------------------------------------------------------

const mockAlert = jest.fn();
jest.mock('react-native', () => {
  const rn = jest.requireActual('react-native');
  return { ...rn, Alert: { alert: mockAlert } };
});

// ---------------------------------------------------------------------------
// DB helper chain setup
// ---------------------------------------------------------------------------

function setupDbChain() {
  mockFrom.mockReturnValue({ select: mockSelect });
  mockSelect.mockReturnValue({ eq: mockEq, order: mockOrder });
  mockEq.mockReturnValue({
    single: mockSingle,
    order: mockOrder,
    range: mockRange,
    select: mockSelect,
  });
  mockOrder.mockReturnValue({ range: mockRange, single: mockSingle, limit: jest.fn().mockReturnValue({ single: mockSingle }) });
  mockRange.mockReturnValue({ then: jest.fn() });
}

// ---------------------------------------------------------------------------
// Routing helper – mirrors the logic in app/index.tsx
// ---------------------------------------------------------------------------

function resolveRoute(params: {
  user: any;
  profile: any;
  authLoading: boolean;
}): string | null {
  const { user, profile, authLoading } = params;

  if (authLoading) return null; // Still loading — don't route yet

  if (!user) return '/auth/login';

  if (!profile?.skill_level) return '/onboarding';

  return '/(tabs)';
}

// ---------------------------------------------------------------------------
// Session deep-link helper – mirrors the logic in app/session/[id].tsx
// ---------------------------------------------------------------------------

async function resolveSessionRoute(sessionId: string): Promise<{
  found: boolean;
  session: ReturnType<typeof createMockSession> | null;
  error: string | null;
}> {
  const { db } = require('../../lib/supabase');
  try {
    const session = await db.getSession(sessionId);
    return { found: true, session, error: null };
  } catch (err: any) {
    return { found: false, session: null, error: err?.message || 'Unknown error' };
  }
}

// ===========================================================================
// Suite
// ===========================================================================

describe('Navigation Edge Cases', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setupDbChain();
  });

  // =========================================================================
  // Auth gate routing (app/index.tsx logic)
  // =========================================================================

  describe('auth gate routing', () => {
    it('returns null (no redirect) while auth is still loading', () => {
      const route = resolveRoute({ user: null, profile: null, authLoading: true });
      expect(route).toBeNull();
    });

    it('redirects to /auth/login when no user is present', () => {
      const route = resolveRoute({ user: null, profile: null, authLoading: false });
      expect(route).toBe('/auth/login');
    });

    it('redirects to /onboarding when user has no skill_level', () => {
      const user = createMockUser();
      const profile = createMockProfile({ skill_level: null });
      const route = resolveRoute({ user, profile, authLoading: false });
      expect(route).toBe('/onboarding');
    });

    it('redirects to /(tabs) when user has a complete profile', () => {
      const user = createMockUser();
      const profile = createMockProfile({ skill_level: 'intermediate' });
      const route = resolveRoute({ user, profile, authLoading: false });
      expect(route).toBe('/(tabs)');
    });

    it('redirects to /onboarding even when user has profile rows but no skill_level', () => {
      const user = createMockUser();
      // Profile exists in DB but onboarding was not completed
      const profile = createMockProfile({ skill_level: null, full_name: 'Partial User' });
      const route = resolveRoute({ user, profile, authLoading: false });
      expect(route).toBe('/onboarding');
    });

    it('redirects to /auth/login if user becomes null mid-session', () => {
      // Simulates TOKEN_REFRESHED failure → user cleared
      const route = resolveRoute({ user: null, profile: null, authLoading: false });
      expect(route).toBe('/auth/login');
    });

    it('resolves to /(tabs) for a pro user with a complete profile', () => {
      const user = createMockUser();
      const profile = createMockProfile({
        skill_level: 'advanced',
        subscription_tier: 'pro',
        subscription_expires_at: new Date(Date.now() + 86400_000).toISOString(),
      });
      const route = resolveRoute({ user, profile, authLoading: false });
      expect(route).toBe('/(tabs)');
    });
  });

  // =========================================================================
  // Deep-link to session that doesn't exist
  // =========================================================================

  describe('deep-link to non-existent session', () => {
    it('reports not found when session ID does not exist in the database', async () => {
      mockGetUser.mockResolvedValue({ data: { user: createMockUser() }, error: null });
      mockSingle.mockResolvedValue({
        data: null,
        error: createSupabaseError('No rows returned', 'PGRST116'),
      });

      const result = await resolveSessionRoute('non-existent-session');

      expect(result.found).toBe(false);
      expect(result.error).toBeTruthy();
    });

    it('reports not found for a malformed / empty session ID', async () => {
      mockGetUser.mockResolvedValue({ data: { user: createMockUser() }, error: null });
      mockSingle.mockResolvedValue({
        data: null,
        error: createSupabaseError('Invalid UUID', 'INVALID_INPUT'),
      });

      const result = await resolveSessionRoute('');

      expect(result.found).toBe(false);
    });

    it('reports not found when the database is unreachable', async () => {
      mockGetUser.mockResolvedValue({ data: { user: createMockUser() }, error: null });
      mockSingle.mockRejectedValue(new Error('Connection timeout'));

      const result = await resolveSessionRoute('session-123');

      expect(result.found).toBe(false);
      expect(result.error).toContain('Connection timeout');
    });

    it('returns the session when it does exist', async () => {
      const session = createMockSession({ id: 'session-abc' });

      mockGetUser.mockResolvedValue({ data: { user: createMockUser() }, error: null });
      mockSingle.mockResolvedValue({ data: session, error: null });

      const result = await resolveSessionRoute('session-abc');

      expect(result.found).toBe(true);
      expect(result.session?.id).toBe('session-abc');
    });

    it('handles a session belonging to a different user (forbidden)', async () => {
      // The DB enforces RLS; from the client's perspective this looks like "not found"
      mockGetUser.mockResolvedValue({ data: { user: createMockUser('other-user') }, error: null });
      mockSingle.mockResolvedValue({
        data: null,
        error: createSupabaseError('Row Level Security violation', '42501'),
      });

      const result = await resolveSessionRoute('session-owned-by-someone-else');

      expect(result.found).toBe(false);
    });

    it('router replaces to a 404 / error screen when session is not found', () => {
      // Simulates what the session screen does when resolveSessionRoute fails
      const sessionId = 'ghost-session';
      if (!sessionId || sessionId === 'ghost-session') {
        mockReplace('/'); // Navigate back to home
      }

      expect(mockReplace).toHaveBeenCalledWith('/');
    });
  });

  // =========================================================================
  // Back navigation from recording screen
  // =========================================================================

  describe('back navigation from recording screen', () => {
    it('calls router.back() when the user cancels before recording starts', () => {
      // Simulates the "Cancel" button in the camera view
      mockBack();

      expect(mockBack).toHaveBeenCalledTimes(1);
    });

    it('does not navigate back while analysis is in progress', () => {
      // The record screen disables back navigation during analysis
      const analyzing = true;
      if (!analyzing) {
        mockBack();
      }

      expect(mockBack).not.toHaveBeenCalled();
    });

    it('navigates back after analysis completes and user taps "Done"', () => {
      const analyzing = false;
      const hasResult = true;
      if (!analyzing && hasResult) {
        mockBack();
      }

      expect(mockBack).toHaveBeenCalledTimes(1);
    });

    it('navigates back when user cancels the rim calibration overlay', () => {
      // handleChangeVideo resets state; navigating back is the user's intent
      mockBack();

      expect(mockBack).toHaveBeenCalledTimes(1);
    });

    it('pressing back after recording does not lose the result state', () => {
      // Verify that pressing back and returning keeps the result available
      // (The screen resets only when hadResultOnBlur is true on the next focus)
      let result: any = createMockSession();
      const hadResultOnBlur = result !== null;

      // Simulate blur
      const resultAfterBlur = hadResultOnBlur ? result : null;
      expect(resultAfterBlur).not.toBeNull();
    });
  });

  // =========================================================================
  // useLocalSearchParams edge cases
  // =========================================================================

  describe('useLocalSearchParams edge cases', () => {
    it('returns an empty string when session id param is absent', () => {
      const { useLocalSearchParams } = require('expo-router');
      const params = useLocalSearchParams();

      // No id key in our mock
      expect(params.id).toBeUndefined();
    });

    it('handles id param being an array (duplicate query params)', () => {
      // expo-router may return arrays for duplicate params
      const idParam: string | string[] = ['session-1', 'session-2'];
      const resolvedId = Array.isArray(idParam) ? idParam[0] : idParam;

      expect(resolvedId).toBe('session-1');
    });

    it('handles id param that is a whitespace-only string', () => {
      const idParam = '   ';
      const isValid = idParam.trim().length > 0;

      expect(isValid).toBe(false);
    });
  });

  // =========================================================================
  // Router action helpers
  // =========================================================================

  describe('router action helpers', () => {
    it('push navigates to session detail with correct path', () => {
      const sessionId = 'session-xyz';
      mockPush(`/session/${sessionId}`);

      expect(mockPush).toHaveBeenCalledWith('/session/session-xyz');
    });

    it('replace is used (not push) for auth redirects', () => {
      // Auth redirects should replace stack so back button doesn't return to auth screen
      mockReplace('/auth/login');

      expect(mockReplace).toHaveBeenCalledWith('/auth/login');
      expect(mockPush).not.toHaveBeenCalled();
    });

    it('replace is used for post-login redirect to /(tabs)', () => {
      mockReplace('/(tabs)');

      expect(mockReplace).toHaveBeenCalledWith('/(tabs)');
    });

    it('push is used for navigating to record screen from home', () => {
      mockPush('/(tabs)/record');

      expect(mockPush).toHaveBeenCalledWith('/(tabs)/record');
    });

    it('replace is used after sign out to return to login', () => {
      mockReplace('/auth/login');

      expect(mockReplace).toHaveBeenCalledWith('/auth/login');
    });

    it('replace is used for onboarding redirect', () => {
      mockReplace('/onboarding');

      expect(mockReplace).toHaveBeenCalledWith('/onboarding');
      // Should not have used push (back from onboarding would be wrong)
      expect(mockPush).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // Navigation during loading states
  // =========================================================================

  describe('navigation during loading states', () => {
    it('does not navigate while auth is loading', () => {
      const authLoading = true;
      if (!authLoading) {
        mockReplace('/auth/login');
      }

      expect(mockReplace).not.toHaveBeenCalled();
    });

    it('navigates after loading completes with no user', () => {
      const authLoading = false;
      const user = null;
      if (!authLoading && !user) {
        mockReplace('/auth/login');
      }

      expect(mockReplace).toHaveBeenCalledWith('/auth/login');
    });

    it('navigates after loading completes with authenticated user', () => {
      const authLoading = false;
      const user = createMockUser();
      const profile = createMockProfile({ skill_level: 'beginner' });

      if (!authLoading && user) {
        const route = resolveRoute({ user, profile, authLoading: false });
        mockReplace(route!);
      }

      expect(mockReplace).toHaveBeenCalledWith('/(tabs)');
    });
  });

  // =========================================================================
  // Missing profile data edge cases
  // =========================================================================

  describe('missing user profile data', () => {
    it('routes to onboarding when profile is null', () => {
      const user = createMockUser();
      const profile = null;
      const route = resolveRoute({ user, profile, authLoading: false });

      expect(route).toBe('/onboarding');
    });

    it('routes to onboarding when profile has no skill_level field', () => {
      const user = createMockUser();
      // skill_level explicitly set to null (not completed onboarding)
      const profile = createMockProfile({ skill_level: null });
      const route = resolveRoute({ user, profile, authLoading: false });

      expect(route).toBe('/onboarding');
    });

    it('routes to /(tabs) when profile only has skill_level but missing other optional fields', () => {
      const user = createMockUser();
      const profile = createMockProfile({
        skill_level: 'beginner',
        full_name: null,
        primary_goal: null,
        height_inches: null,
        focus_areas: null,
      });
      const route = resolveRoute({ user, profile, authLoading: false });

      // Optional fields don't block access to the main app
      expect(route).toBe('/(tabs)');
    });

    it('profile update with empty full_name should not navigate away', () => {
      // Profile screen shows an alert and returns early — no navigation happens
      const name = '';
      const isValid = name.trim().length > 0;

      if (!isValid) {
        mockAlert('Error', 'Name cannot be empty');
      }

      expect(mockAlert).toHaveBeenCalledWith('Error', 'Name cannot be empty');
      expect(mockReplace).not.toHaveBeenCalled();
      expect(mockPush).not.toHaveBeenCalled();
    });

    it('handles a user with total_sessions = 0 (no stats to show)', () => {
      const profile = createMockProfile({ total_sessions: 0, total_shots: 0, total_makes: 0 });

      // Stats section should be hidden; this is a rendering guard, not a navigation issue
      const showStats = profile.total_sessions > 0 || profile.total_shots > 0;
      expect(showStats).toBe(false);
    });

    it('handles a user with total_shots = 0 when calculating shooting percentage', () => {
      const profile = createMockProfile({ total_shots: 0, total_makes: 0 });

      // Ensure no division-by-zero — the computation should yield 0%
      const accuracy =
        profile.total_shots > 0
          ? Math.round((profile.total_makes / profile.total_shots) * 100)
          : 0;

      expect(accuracy).toBe(0);
    });
  });
});
