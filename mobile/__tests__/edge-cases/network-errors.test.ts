/**
 * Network Error / Bad API Response Edge Cases
 * Tests how the API client and database helpers handle every class of network
 * failure: timeouts, 4xx/5xx status codes, malformed JSON, and intermittent
 * connectivity issues.
 *
 * Follows the patterns established in __tests__/lib/api.test.ts and
 * __tests__/lib/supabase.test.ts.
 */

import {
  testConnection,
  getHealthStatus,
  analyzeVideo,
  getApiInfo,
  getFingerprint,
} from '../../lib/api';

import {
  createMockResponse,
  createMockErrorResponse,
  mockFetch,
  clearAllMocks,
} from '../utils/testHelpers';

import {
  createMockHealthResponse,
  createMockSessionSummary,
  createSupabaseError,
  createMockUser,
} from '../utils/mockData';

// ---------------------------------------------------------------------------
// Global fetch is mocked in setup.ts; keep a local reference for overriding
// ---------------------------------------------------------------------------

global.fetch = jest.fn();

// ---------------------------------------------------------------------------
// Supabase mock — mirrors the pattern in supabase.test.ts
// ---------------------------------------------------------------------------

const mockGetUser = jest.fn();
const mockFrom = jest.fn();
const mockSelect = jest.fn();
const mockEq = jest.fn();
const mockSingle = jest.fn();
const mockOrder = jest.fn();
const mockRange = jest.fn();

jest.mock('../../lib/supabase', () => {
  const actual = jest.requireActual('../../lib/supabase');
  return {
    ...actual,
    supabase: {
      auth: {
        getUser: () => mockGetUser(),
      },
      from: () => mockFrom(),
    },
  };
});

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  clearAllMocks();
  jest.clearAllTimers();

  // Default supabase chain
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
});

// ===========================================================================
// testConnection — health-check endpoint
// ===========================================================================

describe('testConnection network errors', () => {
  it('returns false on a complete network failure (fetch throws)', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('Network request failed'));

    const result = await testConnection();

    expect(result).toBe(false);
  });

  it('returns false on a 500 Internal Server Error', async () => {
    mockFetch(createMockErrorResponse(500, 'Internal Server Error'));

    const result = await testConnection();

    expect(result).toBe(false);
  });

  it('returns false on a 503 Service Unavailable', async () => {
    mockFetch(createMockErrorResponse(503, 'Service Unavailable'));

    const result = await testConnection();

    expect(result).toBe(false);
  });

  it('returns false when the server returns non-JSON', async () => {
    const malformedResponse = {
      ok: true,
      status: 200,
      statusText: 'OK',
      json: jest.fn().mockRejectedValue(new SyntaxError('Unexpected token')),
      text: jest.fn().mockResolvedValue('<html>Gateway error</html>'),
      headers: new Headers(),
    } as unknown as Response;

    mockFetch(malformedResponse);

    const result = await testConnection();

    expect(result).toBe(false);
  });

  it('returns false when modules_available is false', async () => {
    mockFetch(
      createMockResponse(
        createMockHealthResponse({ modules_available: false })
      )
    );

    const result = await testConnection();

    expect(result).toBe(false);
  });

  it('returns true even when gemini_configured is false (non-fatal)', async () => {
    mockFetch(
      createMockResponse(
        createMockHealthResponse({ gemini_configured: false, modules_available: true })
      )
    );

    const result = await testConnection();

    expect(result).toBe(true);
  });

  it('returns false on timeout (5 s health-check timeout)', async () => {
    jest.useFakeTimers();

    global.fetch = jest.fn(() => new Promise(() => {})); // never resolves

    const connectionPromise = testConnection();
    jest.advanceTimersByTime(5001);

    await expect(connectionPromise).resolves.toBe(false);

    jest.useRealTimers();
  });
});

// ===========================================================================
// getHealthStatus — returns null on any error
// ===========================================================================

describe('getHealthStatus network errors', () => {
  it('returns null on network failure', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('No internet'));

    const result = await getHealthStatus();

    expect(result).toBeNull();
  });

  it('returns null on 400 Bad Request', async () => {
    mockFetch(createMockErrorResponse(400, 'Bad Request'));

    const result = await getHealthStatus();

    expect(result).toBeNull();
  });

  it('returns null on 401 Unauthorized', async () => {
    mockFetch(createMockErrorResponse(401, 'Unauthorized'));

    const result = await getHealthStatus();

    expect(result).toBeNull();
  });

  it('returns null on 404 Not Found', async () => {
    mockFetch(createMockErrorResponse(404, 'Not Found'));

    const result = await getHealthStatus();

    expect(result).toBeNull();
  });

  it('returns null on 429 Too Many Requests', async () => {
    mockFetch(createMockErrorResponse(429, 'Too Many Requests'));

    const result = await getHealthStatus();

    expect(result).toBeNull();
  });

  it('returns null on health-check timeout', async () => {
    jest.useFakeTimers();

    global.fetch = jest.fn(() => new Promise(() => {}));

    const healthPromise = getHealthStatus();
    jest.advanceTimersByTime(5001);

    const result = await healthPromise;

    expect(result).toBeNull();

    jest.useRealTimers();
  });
});

// ===========================================================================
// analyzeVideo — critical path, many failure modes
// ===========================================================================

describe('analyzeVideo network errors', () => {
  const VIDEO_URI = 'file:///path/to/session.mp4';

  it('throws a user-friendly timeout message when analysis times out', async () => {
    jest.useFakeTimers();

    global.fetch = jest.fn(() => new Promise(() => {}));

    const analyzePromise = analyzeVideo(VIDEO_URI);
    jest.advanceTimersByTime(600001); // 10 min API_TIMEOUT + 1 ms

    await expect(analyzePromise).rejects.toThrow('Video analysis timed out');

    jest.useRealTimers();
  });

  it('throws a "no shots detected" message on 404', async () => {
    mockFetch(createMockErrorResponse(404, 'No shots found'));

    await expect(analyzeVideo(VIDEO_URI)).rejects.toThrow(
      'No shots detected in video'
    );
  });

  it('throws "analysis service unavailable" on 503', async () => {
    mockFetch(createMockErrorResponse(503, 'Service unavailable'));

    await expect(analyzeVideo(VIDEO_URI)).rejects.toThrow(
      'Analysis service unavailable'
    );
  });

  it('throws on 400 Bad Request with the server error message', async () => {
    mockFetch(createMockErrorResponse(400, 'Invalid video format'));

    await expect(analyzeVideo(VIDEO_URI)).rejects.toThrow();
  });

  it('throws on 500 Internal Server Error', async () => {
    mockFetch(createMockErrorResponse(500, 'Server exploded'));

    await expect(analyzeVideo(VIDEO_URI)).rejects.toThrow();
  });

  it('propagates network errors thrown by fetch', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('Network error'));

    await expect(analyzeVideo(VIDEO_URI)).rejects.toThrow('Network error');
  });

  it('throws on malformed (non-JSON) success response', async () => {
    const badResponse = {
      ok: true,
      status: 200,
      statusText: 'OK',
      json: jest.fn().mockRejectedValue(new SyntaxError('Unexpected end of JSON')),
      text: jest.fn().mockResolvedValue('not json'),
      headers: new Headers(),
    } as unknown as Response;

    mockFetch(badResponse);

    await expect(analyzeVideo(VIDEO_URI)).rejects.toThrow();
  });

  it('handles an abrupt connection reset (empty response body)', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('Connection reset'));

    await expect(analyzeVideo(VIDEO_URI)).rejects.toThrow('Connection reset');
  });

  it('succeeds on a valid response after a previous failure', async () => {
    const successData = createMockSessionSummary();

    // First call fails
    global.fetch = jest
      .fn()
      .mockRejectedValueOnce(new Error('Temporary error'))
      .mockResolvedValueOnce(createMockResponse(successData) as unknown as Response);

    // First attempt
    await expect(analyzeVideo(VIDEO_URI)).rejects.toThrow('Temporary error');

    // Second attempt succeeds (simulating a retry in the UI)
    const result = await analyzeVideo(VIDEO_URI);
    expect(result.total_shots).toBe(successData.total_shots);
  });

  it('includes error status code on HTTP errors (ApiError.status)', async () => {
    mockFetch(createMockErrorResponse(422, 'Unprocessable Entity'));

    let caughtError: any;
    try {
      await analyzeVideo(VIDEO_URI);
    } catch (err: any) {
      caughtError = err;
    }

    expect(caughtError).toBeDefined();
    expect(caughtError.status).toBe(422);
  });

  it('sends the correct Accept: application/json header', async () => {
    mockFetch(createMockResponse(createMockSessionSummary()));

    await analyzeVideo(VIDEO_URI);

    const [, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(options.headers.Accept).toBe('application/json');
  });

  it('uses POST method', async () => {
    mockFetch(createMockResponse(createMockSessionSummary()));

    await analyzeVideo(VIDEO_URI);

    const [, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(options.method).toBe('POST');
  });
});

// ===========================================================================
// getApiInfo — informational endpoint
// ===========================================================================

describe('getApiInfo network errors', () => {
  it('returns null on network error', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('DNS failure'));

    const result = await getApiInfo();

    expect(result).toBeNull();
  });

  it('returns null on 500 error', async () => {
    mockFetch(createMockErrorResponse(500, 'Server error'));

    const result = await getApiInfo();

    expect(result).toBeNull();
  });

  it('returns null on timeout', async () => {
    jest.useFakeTimers();

    global.fetch = jest.fn(() => new Promise(() => {}));

    const infoPromise = getApiInfo();
    jest.advanceTimersByTime(5001);

    const result = await infoPromise;

    expect(result).toBeNull();

    jest.useRealTimers();
  });
});

// ===========================================================================
// getFingerprint — shot fingerprint endpoint
// ===========================================================================

describe('getFingerprint network errors', () => {
  it('returns null on network error', async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error('No connection'));

    const result = await getFingerprint('user-123');

    expect(result).toBeNull();
  });

  it('returns null on 404 (fingerprint not ready yet)', async () => {
    mockFetch(createMockErrorResponse(404, 'Not found'));

    const result = await getFingerprint('user-123');

    expect(result).toBeNull();
  });

  it('returns null on 500 server error', async () => {
    mockFetch(createMockErrorResponse(500, 'Server error'));

    const result = await getFingerprint('user-123');

    expect(result).toBeNull();
  });

  it('returns null on timeout (10 s)', async () => {
    jest.useFakeTimers();

    global.fetch = jest.fn(() => new Promise(() => {}));

    const fingerprintPromise = getFingerprint('user-123');
    jest.advanceTimersByTime(10001);

    const result = await fingerprintPromise;

    expect(result).toBeNull();

    jest.useRealTimers();
  });

  it('includes the userId in the request URL', async () => {
    const fingerprintData = {
      session_count: 3,
      total_shots: 30,
      fingerprint_ready: true,
      make_signature: {},
      miss_signature: {},
      improvement_areas: [],
      consistency: {},
      miss_distribution: {},
      trend: { shooting_pct: [], form_rating: [], direction: 'improving' },
      cues: [],
      miss_tendency_cue: '',
      trend_label: '',
      consistency_note: '',
    };

    mockFetch(createMockResponse(fingerprintData));

    await getFingerprint('user-456');

    const [url] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toContain('user-456');
  });
});

// ===========================================================================
// Supabase DB failures surfaced through the db helper
// ===========================================================================

describe('Supabase database error handling', () => {
  // Import the db helper after mocks are in place
  const { db } = require('../../lib/supabase');

  beforeEach(() => {
    jest.clearAllMocks();

    mockFrom.mockReturnValue({
      select: mockSelect,
    });
    mockSelect.mockReturnValue({ eq: mockEq });
    mockEq.mockReturnValue({ single: mockSingle, order: mockOrder });
    mockOrder.mockReturnValue({ range: mockRange, single: mockSingle, limit: jest.fn().mockReturnValue({ single: mockSingle }) });
    mockRange.mockReturnValue({ then: jest.fn() });
  });

  it('getSession throws when the database returns an error', async () => {
    mockSingle.mockResolvedValue({
      data: null,
      error: createSupabaseError('Connection timeout', 'TIMEOUT'),
    });

    await expect(db.getSession('session-123')).rejects.toThrow();
  });

  it('getShots throws on query failure', async () => {
    mockOrder.mockResolvedValue({
      data: null,
      error: createSupabaseError('Query failed'),
    });

    await expect(db.getShots('session-123')).rejects.toThrow();
  });

  it('createSession throws when not authenticated', async () => {
    mockGetUser.mockResolvedValue({ data: { user: null }, error: null });

    await expect(
      db.createSession({ shooting_hand: 'right' })
    ).rejects.toThrow('Not authenticated');
  });

  it('updateProfile throws when not authenticated', async () => {
    mockGetUser.mockResolvedValue({ data: { user: null }, error: null });

    await expect(
      db.updateProfile({ full_name: 'Ghost' })
    ).rejects.toThrow('Not authenticated');
  });

  it('createShots throws when not authenticated', async () => {
    mockGetUser.mockResolvedValue({ data: { user: null }, error: null });

    await expect(db.createShots([])).rejects.toThrow('Not authenticated');
  });

  it('getSessions returns empty array when not authenticated', async () => {
    mockGetUser.mockResolvedValue({ data: { user: null }, error: null });

    const result = await db.getSessions();

    expect(result).toEqual([]);
  });

  it('getUserStats returns zeros when not authenticated', async () => {
    mockGetUser.mockResolvedValue({ data: { user: null }, error: null });

    const result = await db.getUserStats();

    expect(result).toEqual({
      totalSessions: 0,
      totalShots: 0,
      totalMakes: 0,
      avgShootingPercentage: 0,
      avgFormRating: 0,
    });
  });

  it('uploadThumbnail returns null when not authenticated', async () => {
    mockGetUser.mockResolvedValue({ data: { user: null }, error: null });

    const result = await db.uploadThumbnail('session-123', 1, 'base64data');

    expect(result).toBeNull();
  });

  it('updateUserStats does not throw on failure (background update)', async () => {
    const user = createMockUser();
    mockGetUser.mockResolvedValue({ data: { user }, error: null });
    // Simulate the inner getUserStats call failing
    mockEq.mockResolvedValue({
      data: null,
      error: createSupabaseError('Stats query failed'),
    });

    await expect(db.updateUserStats()).resolves.toBeUndefined();
  });
});

// ===========================================================================
// Concurrent / race-condition scenarios
// ===========================================================================

describe('concurrent request handling', () => {
  it('handles multiple simultaneous analyzeVideo calls gracefully', async () => {
    const successData = createMockSessionSummary();

    // Both succeed
    global.fetch = jest.fn().mockResolvedValue(createMockResponse(successData) as unknown as Response);

    const [r1, r2] = await Promise.all([
      analyzeVideo('file:///v1.mp4'),
      analyzeVideo('file:///v2.mp4'),
    ]);

    expect(r1.total_shots).toBe(successData.total_shots);
    expect(r2.total_shots).toBe(successData.total_shots);
  });

  it('handles one of two concurrent requests failing', async () => {
    const successData = createMockSessionSummary();

    global.fetch = jest
      .fn()
      .mockResolvedValueOnce(createMockResponse(successData) as unknown as Response)
      .mockRejectedValueOnce(new Error('Network error'));

    const results = await Promise.allSettled([
      analyzeVideo('file:///v1.mp4'),
      analyzeVideo('file:///v2.mp4'),
    ]);

    const [first, second] = results;
    expect(first.status).toBe('fulfilled');
    expect(second.status).toBe('rejected');
  });
});
