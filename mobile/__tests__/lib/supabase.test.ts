/**
 * Supabase Client Unit Tests
 * Tests for database operations and authentication
 */

import { db, isSupabaseConfigured, getCurrentUserId } from '../../lib/supabase';
import {
  createMockProfile,
  createMockSession,
  createMockShot,
  createMockUserStats,
  createSupabaseResponse,
  createSupabaseError,
  createMockUser,
} from '../utils/mockData';

// Mock Supabase client
const mockSelect = jest.fn();
const mockInsert = jest.fn();
const mockUpdate = jest.fn();
const mockDelete = jest.fn();
const mockEq = jest.fn();
const mockOrder = jest.fn();
const mockRange = jest.fn();
const mockSingle = jest.fn();
const mockLimit = jest.fn();
const mockFrom = jest.fn();
const mockGetUser = jest.fn();
const mockUpload = jest.fn();
const mockGetPublicUrl = jest.fn();

jest.mock('../../lib/supabase', () => {
  const actual = jest.requireActual('../../lib/supabase');

  return {
    ...actual,
    supabase: {
      auth: {
        getUser: () => mockGetUser(),
      },
      from: () => mockFrom(),
      storage: {
        from: () => ({
          upload: mockUpload,
          getPublicUrl: mockGetPublicUrl,
        }),
      },
    },
  };
});

describe('Supabase Client', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    // Setup default mock chain
    mockFrom.mockReturnValue({
      select: mockSelect,
      insert: mockInsert,
      update: mockUpdate,
      delete: mockDelete,
    });

    mockSelect.mockReturnValue({ eq: mockEq, order: mockOrder });
    mockInsert.mockReturnValue({ select: mockSelect });
    mockUpdate.mockReturnValue({ eq: mockEq });
    mockDelete.mockReturnValue({ eq: mockEq });

    mockEq.mockReturnValue({
      select: mockSelect,
      single: mockSingle,
      order: mockOrder,
      range: mockRange,
      limit: mockLimit,
    });

    mockOrder.mockReturnValue({
      range: mockRange,
      limit: mockLimit,
      single: mockSingle,
    });

    mockRange.mockReturnValue({ then: jest.fn() });
    mockLimit.mockReturnValue({ single: mockSingle });
  });

  // ==========================================================================
  // Profile Operations
  // ==========================================================================

  describe('db.getProfile', () => {
    it('should return user profile when authenticated', async () => {
      const mockUser = createMockUser();
      const mockProfile = createMockProfile();

      mockGetUser.mockResolvedValue({ data: { user: mockUser }, error: null });
      mockSingle.mockResolvedValue(createSupabaseResponse(mockProfile));

      const result = await db.getProfile();

      expect(result).toEqual(mockProfile);
      expect(mockFrom).toHaveBeenCalledWith('profiles');
      expect(mockSelect).toHaveBeenCalledWith('*');
      expect(mockEq).toHaveBeenCalledWith('id', mockUser.id);
    });

    it('should return null when not authenticated', async () => {
      mockGetUser.mockResolvedValue({ data: { user: null }, error: null });

      const result = await db.getProfile();

      expect(result).toBeNull();
    });

    it('should throw error on database failure', async () => {
      const mockUser = createMockUser();
      mockGetUser.mockResolvedValue({ data: { user: mockUser }, error: null });
      mockSingle.mockResolvedValue(
        createSupabaseResponse(null, createSupabaseError('Database error'))
      );

      await expect(db.getProfile()).rejects.toThrow();
    });
  });

  describe('db.updateProfile', () => {
    it('should update profile successfully', async () => {
      const mockUser = createMockUser();
      const mockProfile = createMockProfile({ full_name: 'Updated Name' });

      mockGetUser.mockResolvedValue({ data: { user: mockUser }, error: null });
      mockSingle.mockResolvedValue(createSupabaseResponse(mockProfile));

      const updates = { full_name: 'Updated Name' };
      const result = await db.updateProfile(updates);

      expect(result).toEqual(mockProfile);
      expect(mockUpdate).toHaveBeenCalledWith(
        expect.objectContaining({
          full_name: 'Updated Name',
          updated_at: expect.any(String),
        })
      );
      expect(mockEq).toHaveBeenCalledWith('id', mockUser.id);
    });

    it('should throw error when not authenticated', async () => {
      mockGetUser.mockResolvedValue({ data: { user: null }, error: null });

      await expect(db.updateProfile({ full_name: 'Test' })).rejects.toThrow(
        'Not authenticated'
      );
    });

    it('should throw error on database failure', async () => {
      const mockUser = createMockUser();
      mockGetUser.mockResolvedValue({ data: { user: mockUser }, error: null });
      mockSingle.mockResolvedValue(
        createSupabaseResponse(null, createSupabaseError('Update failed'))
      );

      await expect(db.updateProfile({ full_name: 'Test' })).rejects.toThrow();
    });
  });

  // ==========================================================================
  // Session Operations
  // ==========================================================================

  describe('db.getSessions', () => {
    it('should return paginated sessions', async () => {
      const mockUser = createMockUser();
      const mockSessions = [
        createMockSession({ id: 'session-1' }),
        createMockSession({ id: 'session-2' }),
      ];

      mockGetUser.mockResolvedValue({ data: { user: mockUser }, error: null });
      mockRange.mockResolvedValue(createSupabaseResponse(mockSessions));

      const result = await db.getSessions(10, 0);

      expect(result).toEqual(mockSessions);
      expect(mockEq).toHaveBeenCalledWith('user_id', mockUser.id);
      expect(mockOrder).toHaveBeenCalledWith('started_at', { ascending: false });
      expect(mockRange).toHaveBeenCalledWith(0, 9);
    });

    it('should return empty array when not authenticated', async () => {
      mockGetUser.mockResolvedValue({ data: { user: null }, error: null });

      const result = await db.getSessions();

      expect(result).toEqual([]);
    });

    it('should handle custom pagination', async () => {
      const mockUser = createMockUser();
      mockGetUser.mockResolvedValue({ data: { user: mockUser }, error: null });
      mockRange.mockResolvedValue(createSupabaseResponse([]));

      await db.getSessions(5, 10);

      expect(mockRange).toHaveBeenCalledWith(10, 14);
    });
  });

  describe('db.getSession', () => {
    it('should return session by ID', async () => {
      const mockSession = createMockSession();
      mockSingle.mockResolvedValue(createSupabaseResponse(mockSession));

      const result = await db.getSession('session-123');

      expect(result).toEqual(mockSession);
      expect(mockEq).toHaveBeenCalledWith('id', 'session-123');
    });

    it('should throw error on database failure', async () => {
      mockSingle.mockResolvedValue(
        createSupabaseResponse(null, createSupabaseError('Not found'))
      );

      await expect(db.getSession('invalid-id')).rejects.toThrow();
    });
  });

  describe('db.createSession', () => {
    it('should create new session successfully', async () => {
      const mockUser = createMockUser();
      const mockSession = createMockSession();

      mockGetUser.mockResolvedValue({ data: { user: mockUser }, error: null });
      mockSingle.mockResolvedValue(createSupabaseResponse(mockSession));

      const result = await db.createSession({
        shooting_hand: 'right',
        focus_area: 'shooting',
      });

      expect(result).toEqual(mockSession);
      expect(mockInsert).toHaveBeenCalledWith(
        expect.objectContaining({
          user_id: mockUser.id,
          shooting_hand: 'right',
          focus_area: 'shooting',
          shot_count: 0,
          make_count: 0,
          miss_count: 0,
          shooting_percentage: 0,
        })
      );
    });

    it('should throw error when not authenticated', async () => {
      mockGetUser.mockResolvedValue({ data: { user: null }, error: null });

      await expect(
        db.createSession({ shooting_hand: 'right' })
      ).rejects.toThrow('Not authenticated');
    });
  });

  describe('db.updateSession', () => {
    it('should update session successfully', async () => {
      const mockSession = createMockSession();
      mockSingle.mockResolvedValue(createSupabaseResponse(mockSession));

      // Mock updateUserStats
      const mockUser = createMockUser();
      mockGetUser.mockResolvedValue({ data: { user: mockUser }, error: null });
      mockRange.mockResolvedValue(createSupabaseResponse([]));

      const updates = {
        shot_count: 10,
        make_count: 7,
        miss_count: 3,
        shooting_percentage: 70,
      };

      const result = await db.updateSession('session-123', updates);

      expect(result).toEqual(mockSession);
      expect(mockUpdate).toHaveBeenCalledWith(updates);
      expect(mockEq).toHaveBeenCalledWith('id', 'session-123');
    });
  });

  describe('db.deleteSession', () => {
    it('should delete session successfully', async () => {
      mockEq.mockResolvedValue(createSupabaseResponse(null));

      // Mock updateUserStats
      const mockUser = createMockUser();
      mockGetUser.mockResolvedValue({ data: { user: mockUser }, error: null });
      mockRange.mockResolvedValue(createSupabaseResponse([]));

      await db.deleteSession('session-123');

      expect(mockDelete).toHaveBeenCalled();
      expect(mockEq).toHaveBeenCalledWith('id', 'session-123');
    });

    it('should throw error on database failure', async () => {
      mockEq.mockResolvedValue(
        createSupabaseResponse(null, createSupabaseError('Delete failed'))
      );

      await expect(db.deleteSession('session-123')).rejects.toThrow();
    });
  });

  // ==========================================================================
  // Shot Operations
  // ==========================================================================

  describe('db.getShots', () => {
    it('should return shots for session', async () => {
      const mockShots = [
        createMockShot({ shot_number: 1 }),
        createMockShot({ shot_number: 2 }),
      ];

      mockOrder.mockResolvedValue(createSupabaseResponse(mockShots));

      const result = await db.getShots('session-123');

      expect(result).toEqual(mockShots);
      expect(mockEq).toHaveBeenCalledWith('session_id', 'session-123');
      expect(mockOrder).toHaveBeenCalledWith('shot_number', { ascending: true });
    });

    it('should throw error on database failure', async () => {
      mockOrder.mockResolvedValue(
        createSupabaseResponse(null, createSupabaseError('Query failed'))
      );

      await expect(db.getShots('session-123')).rejects.toThrow();
    });
  });

  describe('db.createShots', () => {
    it('should create shots in batch', async () => {
      const mockUser = createMockUser();
      const mockShots = [
        createMockShot({ shot_number: 1 }),
        createMockShot({ shot_number: 2 }),
      ];

      mockGetUser.mockResolvedValue({ data: { user: mockUser }, error: null });
      mockSelect.mockResolvedValue(createSupabaseResponse(mockShots));

      const shotsData = [
        {
          session_id: 'session-123',
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
          thumbnail_url: null,
        },
        {
          session_id: 'session-123',
          shot_number: 2,
          made: false,
          miss_type: 'short',
          elbow_angle_load: 85,
          elbow_angle_release: 40,
          wrist_height_release: 2.0,
          knee_bend_load: 105,
          hip_angle_load: 0,
          elbow_height_load: 0,
          heel_height_release: 0,
          trunk_lean_release: 0,
          stance_width: 0,
          shoulder_level_diff: 0,
          elbow_lateral_offset: 0,
          form_rating: 7.0,
          feedback: 'More arc needed',
          key_issue: 'Low release',
          quick_cue: 'Extend higher',
          camera_angle: 'side',
          thumbnail_url: null,
        },
      ];

      const result = await db.createShots(shotsData);

      expect(result).toEqual(mockShots);
      expect(mockInsert).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({
            user_id: mockUser.id,
            shot_number: 1,
          }),
          expect.objectContaining({
            user_id: mockUser.id,
            shot_number: 2,
          }),
        ])
      );
    });

    it('should throw error when not authenticated', async () => {
      mockGetUser.mockResolvedValue({ data: { user: null }, error: null });

      await expect(db.createShots([])).rejects.toThrow('Not authenticated');
    });
  });

  // ==========================================================================
  // Stats Operations
  // ==========================================================================

  describe('db.getUserStats', () => {
    it('should calculate stats from sessions', async () => {
      const mockUser = createMockUser();
      const mockSessionsData = [
        {
          shot_count: 10,
          make_count: 7,
          shooting_percentage: 70,
          average_form_rating: 8.5,
        },
        {
          shot_count: 5,
          make_count: 3,
          shooting_percentage: 60,
          average_form_rating: 7.5,
        },
      ];

      mockGetUser.mockResolvedValue({ data: { user: mockUser }, error: null });
      mockEq.mockResolvedValue(createSupabaseResponse(mockSessionsData));

      const result = await db.getUserStats();

      expect(result).toEqual({
        totalSessions: 2,
        totalShots: 15,
        totalMakes: 10,
        avgShootingPercentage: (10 / 15) * 100,
        avgFormRating: (8.5 + 7.5) / 2,
      });
    });

    it('should return zeros when not authenticated', async () => {
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

    it('should return zeros when no sessions exist', async () => {
      const mockUser = createMockUser();
      mockGetUser.mockResolvedValue({ data: { user: mockUser }, error: null });
      mockEq.mockResolvedValue(createSupabaseResponse([]));

      const result = await db.getUserStats();

      expect(result).toEqual({
        totalSessions: 0,
        totalShots: 0,
        totalMakes: 0,
        avgShootingPercentage: 0,
        avgFormRating: 0,
      });
    });

    it('should handle null form ratings', async () => {
      const mockUser = createMockUser();
      const mockSessionsData = [
        {
          shot_count: 10,
          make_count: 7,
          shooting_percentage: 70,
          average_form_rating: null,
        },
        {
          shot_count: 5,
          make_count: 3,
          shooting_percentage: 60,
          average_form_rating: 8.0,
        },
      ];

      mockGetUser.mockResolvedValue({ data: { user: mockUser }, error: null });
      mockEq.mockResolvedValue(createSupabaseResponse(mockSessionsData));

      const result = await db.getUserStats();

      expect(result.avgFormRating).toBe(8.0);
    });
  });

  describe('db.updateUserStats', () => {
    it('should update profile with calculated stats', async () => {
      const mockUser = createMockUser();
      mockGetUser.mockResolvedValue({ data: { user: mockUser }, error: null });

      // Mock getUserStats data
      mockEq.mockResolvedValueOnce(createSupabaseResponse([
        {
          shot_count: 10,
          make_count: 7,
          shooting_percentage: 70,
          average_form_rating: 8.0,
        },
      ]));

      // Mock most recent session
      mockSingle.mockResolvedValueOnce(createSupabaseResponse({
        started_at: '2026-01-24T10:00:00Z',
      }));

      // Mock profile update
      mockEq.mockResolvedValueOnce(createSupabaseResponse(null));

      await db.updateUserStats();

      expect(mockUpdate).toHaveBeenCalledWith(
        expect.objectContaining({
          total_sessions: 1,
          total_shots: 10,
          total_makes: 7,
        })
      );
    });

    it('should not throw error on failure', async () => {
      const mockUser = createMockUser();
      mockGetUser.mockResolvedValue({ data: { user: mockUser }, error: null });
      mockEq.mockResolvedValue(
        createSupabaseResponse(null, createSupabaseError('Update failed'))
      );

      // Should not throw
      await expect(db.updateUserStats()).resolves.toBeUndefined();
    });
  });

  // ==========================================================================
  // Storage Operations
  // ==========================================================================

  describe('db.uploadThumbnail', () => {
    it('should upload thumbnail and return URL', async () => {
      const mockUser = createMockUser();
      mockGetUser.mockResolvedValue({ data: { user: mockUser }, error: null });

      const base64Data = btoa('fake-image-data');
      mockUpload.mockResolvedValue({ data: {}, error: null });
      mockGetPublicUrl.mockReturnValue({
        data: { publicUrl: 'https://example.com/thumbnail.jpg' },
      });

      const result = await db.uploadThumbnail('session-123', 1, base64Data);

      expect(result).toBe('https://example.com/thumbnail.jpg');
      expect(mockUpload).toHaveBeenCalledWith(
        `${mockUser.id}/session-123/shot_1.jpg`,
        expect.any(Blob),
        expect.objectContaining({
          contentType: 'image/jpeg',
          upsert: true,
        })
      );
    });

    it('should return null when not authenticated', async () => {
      mockGetUser.mockResolvedValue({ data: { user: null }, error: null });

      const result = await db.uploadThumbnail('session-123', 1, 'base64data');

      expect(result).toBeNull();
    });

    it('should return null on upload error', async () => {
      const mockUser = createMockUser();
      mockGetUser.mockResolvedValue({ data: { user: mockUser }, error: null });
      mockUpload.mockResolvedValue({
        data: null,
        error: createSupabaseError('Upload failed'),
      });

      const result = await db.uploadThumbnail('session-123', 1, 'base64data');

      expect(result).toBeNull();
    });
  });

  // ==========================================================================
  // Utility Functions
  // ==========================================================================

  describe('isSupabaseConfigured', () => {
    it('should return true when configured', () => {
      // Environment variables are set in setup.ts
      const result = isSupabaseConfigured();

      expect(result).toBe(true);
    });
  });

  describe('getCurrentUserId', () => {
    it('should return user ID when authenticated', async () => {
      const mockUser = createMockUser('user-456');
      mockGetUser.mockResolvedValue({ data: { user: mockUser }, error: null });

      const result = await getCurrentUserId();

      expect(result).toBe('user-456');
    });

    it('should return null when not authenticated', async () => {
      mockGetUser.mockResolvedValue({ data: { user: null }, error: null });

      const result = await getCurrentUserId();

      expect(result).toBeNull();
    });
  });
});
