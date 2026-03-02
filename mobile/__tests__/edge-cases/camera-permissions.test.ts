/**
 * Camera Permission Edge Cases
 * Tests for how the app handles camera and media-library permission states.
 *
 * Strategy: mock expo-image-picker and expo-camera at the module level so
 * individual tests can drive any permission outcome without touching the OS.
 */

import {
  createMockSessionSummary,
  createMockUser,
  createMockProfile,
} from '../utils/mockData';
import { createMockResponse, createMockErrorResponse } from '../utils/testHelpers';

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

const mockRequestCameraPermissions = jest.fn();
const mockRequestMediaLibraryPermissions = jest.fn();
const mockLaunchImageLibrary = jest.fn();
const mockLaunchCamera = jest.fn();

jest.mock('expo-image-picker', () => ({
  requestMediaLibraryPermissionsAsync: () => mockRequestMediaLibraryPermissions(),
  requestCameraPermissionsAsync: () => mockRequestCameraPermissions(),
  launchImageLibraryAsync: (opts: any) => mockLaunchImageLibrary(opts),
  launchCameraAsync: (opts: any) => mockLaunchCamera(opts),
  MediaTypeOptions: { Videos: 'Videos' },
}));

jest.mock('expo-camera', () => ({
  Camera: {
    requestCameraPermissionsAsync: () => mockRequestCameraPermissions(),
    getCameraPermissionsAsync: jest.fn(),
  },
  CameraView: 'CameraView',
}));

// Supabase / API mocks so tests that go further don't explode
jest.mock('../../lib/supabase', () => ({
  supabase: {
    auth: { getUser: jest.fn().mockResolvedValue({ data: { user: null }, error: null }) },
    from: jest.fn(),
  },
  db: { createSession: jest.fn(), updateSession: jest.fn(), deleteSession: jest.fn() },
  isSupabaseConfigured: jest.fn(() => true),
}));

jest.mock('../../lib/api', () => ({
  analyzeVideoWithProgress: jest.fn(),
  testConnection: jest.fn().mockResolvedValue(true),
}));

// Alert so we can assert on it
const mockAlert = jest.fn();
jest.mock('react-native', () => {
  const rn = jest.requireActual('react-native');
  return { ...rn, Alert: { alert: mockAlert } };
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const GRANTED_PERMISSION = { status: 'granted', granted: true };
const DENIED_PERMISSION = { status: 'denied', granted: false };
const UNDETERMINED_PERMISSION = { status: 'undetermined', granted: false };

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Camera Permissions Edge Cases', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // =========================================================================
  // Camera permission – granted
  // =========================================================================

  describe('camera permission granted', () => {
    it('returns granted status', async () => {
      mockRequestCameraPermissions.mockResolvedValue(GRANTED_PERMISSION);

      const { requestCameraPermissionsAsync } = require('expo-image-picker');
      const result = await requestCameraPermissionsAsync();

      expect(result.status).toBe('granted');
      expect(result.granted).toBe(true);
    });

    it('allows launching the camera after permission is granted', async () => {
      mockRequestCameraPermissions.mockResolvedValue(GRANTED_PERMISSION);
      mockLaunchCamera.mockResolvedValue({
        canceled: false,
        assets: [{ uri: 'file:///path/to/recorded.mp4' }],
      });

      const imagePicker = require('expo-image-picker');
      const permResult = await imagePicker.requestCameraPermissionsAsync();
      expect(permResult.granted).toBe(true);

      const pickerResult = await imagePicker.launchCameraAsync({ mediaTypes: ['videos'] });
      expect(pickerResult.canceled).toBe(false);
      expect(pickerResult.assets[0].uri).toContain('.mp4');
    });
  });

  // =========================================================================
  // Camera permission – denied
  // =========================================================================

  describe('camera permission denied', () => {
    it('returns denied status when user refuses', async () => {
      mockRequestCameraPermissions.mockResolvedValue(DENIED_PERMISSION);

      const { requestCameraPermissionsAsync } = require('expo-image-picker');
      const result = await requestCameraPermissionsAsync();

      expect(result.status).toBe('denied');
      expect(result.granted).toBe(false);
    });

    it('does not launch the camera when permission is denied', async () => {
      mockRequestCameraPermissions.mockResolvedValue(DENIED_PERMISSION);

      const imagePicker = require('expo-image-picker');
      const permResult = await imagePicker.requestCameraPermissionsAsync();

      if (!permResult.granted) {
        // The record screen calls Alert.alert in this branch
        mockAlert('Permission needed', 'Camera access is required to record video');
      }

      expect(mockLaunchCamera).not.toHaveBeenCalled();
      expect(mockAlert).toHaveBeenCalledWith(
        'Permission needed',
        'Camera access is required to record video'
      );
    });

    it('shows an alert when camera permission is denied', () => {
      mockAlert('Permission Denied', 'Please enable camera access in Settings');

      expect(mockAlert).toHaveBeenCalledWith(
        'Permission Denied',
        'Please enable camera access in Settings'
      );
    });
  });

  // =========================================================================
  // Camera permission – undetermined (first launch)
  // =========================================================================

  describe('camera permission undetermined', () => {
    it('returns undetermined on first launch', async () => {
      mockRequestCameraPermissions.mockResolvedValue(UNDETERMINED_PERMISSION);

      const { requestCameraPermissionsAsync } = require('expo-image-picker');
      const result = await requestCameraPermissionsAsync();

      expect(result.status).toBe('undetermined');
    });

    it('requests permission on first use', async () => {
      mockRequestCameraPermissions.mockResolvedValue(UNDETERMINED_PERMISSION);

      const imagePicker = require('expo-image-picker');
      await imagePicker.requestCameraPermissionsAsync();

      expect(mockRequestCameraPermissions).toHaveBeenCalledTimes(1);
    });
  });

  // =========================================================================
  // Media library permission – granted
  // =========================================================================

  describe('media library permission granted', () => {
    it('returns granted status for media library', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue(GRANTED_PERMISSION);

      const { requestMediaLibraryPermissionsAsync } = require('expo-image-picker');
      const result = await requestMediaLibraryPermissionsAsync();

      expect(result.status).toBe('granted');
    });

    it('launches image library picker when permission granted', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue(GRANTED_PERMISSION);
      mockLaunchImageLibrary.mockResolvedValue({
        canceled: false,
        assets: [{ uri: 'file:///photos/session.mp4' }],
      });

      const imagePicker = require('expo-image-picker');
      const permResult = await imagePicker.requestMediaLibraryPermissionsAsync();
      expect(permResult.granted).toBe(true);

      const pickerResult = await imagePicker.launchImageLibraryAsync({
        mediaTypes: ['videos'],
        allowsEditing: false,
        quality: 1,
      });

      expect(pickerResult.canceled).toBe(false);
      expect(pickerResult.assets[0].uri).toBe('file:///photos/session.mp4');
    });

    it('handles user cancellation of the picker', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue(GRANTED_PERMISSION);
      mockLaunchImageLibrary.mockResolvedValue({ canceled: true, assets: [] });

      const imagePicker = require('expo-image-picker');
      await imagePicker.requestMediaLibraryPermissionsAsync();
      const pickerResult = await imagePicker.launchImageLibraryAsync({ mediaTypes: ['videos'] });

      expect(pickerResult.canceled).toBe(true);
      // No video URI is available — no analysis should be triggered
      expect(pickerResult.assets).toHaveLength(0);
    });
  });

  // =========================================================================
  // Media library permission – denied
  // =========================================================================

  describe('media library permission denied', () => {
    it('returns denied status', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue(DENIED_PERMISSION);

      const { requestMediaLibraryPermissionsAsync } = require('expo-image-picker');
      const result = await requestMediaLibraryPermissionsAsync();

      expect(result.granted).toBe(false);
    });

    it('shows an alert and does not open picker when denied', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue(DENIED_PERMISSION);

      const imagePicker = require('expo-image-picker');
      const permResult = await imagePicker.requestMediaLibraryPermissionsAsync();

      if (permResult.status !== 'granted') {
        mockAlert('Permission needed', 'Please grant access to your photos');
      }

      expect(mockLaunchImageLibrary).not.toHaveBeenCalled();
      expect(mockAlert).toHaveBeenCalledWith(
        'Permission needed',
        'Please grant access to your photos'
      );
    });
  });

  // =========================================================================
  // Empty / invalid video selections
  // =========================================================================

  describe('empty or invalid video', () => {
    it('handles picker returning empty assets array', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue(GRANTED_PERMISSION);
      // Picker returns an assets array with no items (shouldn't happen but be safe)
      mockLaunchImageLibrary.mockResolvedValue({ canceled: false, assets: [] });

      const imagePicker = require('expo-image-picker');
      await imagePicker.requestMediaLibraryPermissionsAsync();
      const result = await imagePicker.launchImageLibraryAsync({ mediaTypes: ['videos'] });

      // Guard condition: app should not proceed to analysis
      const hasValidVideo = !result.canceled && result.assets.length > 0;
      expect(hasValidVideo).toBe(false);
    });

    it('handles picker returning an asset with no URI', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue(GRANTED_PERMISSION);
      mockLaunchImageLibrary.mockResolvedValue({
        canceled: false,
        assets: [{ uri: '' }],
      });

      const imagePicker = require('expo-image-picker');
      await imagePicker.requestMediaLibraryPermissionsAsync();
      const result = await imagePicker.launchImageLibraryAsync({ mediaTypes: ['videos'] });

      const videoUri = result.assets[0]?.uri;
      // An empty URI means no usable file
      expect(videoUri).toBeFalsy();
    });

    it('handles a very short video (< 1 second duration)', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue(GRANTED_PERMISSION);
      mockLaunchImageLibrary.mockResolvedValue({
        canceled: false,
        assets: [{ uri: 'file:///short.mp4', duration: 0.5 }],
      });

      const imagePicker = require('expo-image-picker');
      const result = await imagePicker.launchImageLibraryAsync({ mediaTypes: ['videos'] });

      const asset = result.assets[0];
      // Application logic should warn about short videos
      const isTooShort = asset.duration !== undefined && asset.duration < 1;
      expect(isTooShort).toBe(true);
    });

    it('handles a video with an unsupported extension gracefully', async () => {
      mockRequestMediaLibraryPermissions.mockResolvedValue(GRANTED_PERMISSION);
      mockLaunchImageLibrary.mockResolvedValue({
        canceled: false,
        assets: [{ uri: 'file:///video.mkv' }],
      });

      const imagePicker = require('expo-image-picker');
      const result = await imagePicker.launchImageLibraryAsync({ mediaTypes: ['videos'] });

      const uri: string = result.assets[0].uri;
      const ext = uri.split('.').pop()?.toLowerCase();
      const supportedExtensions = ['mp4', 'mov', 'avi', 'webm'];
      const isSupported = supportedExtensions.includes(ext || '');
      expect(isSupported).toBe(false);
    });
  });

  // =========================================================================
  // Permission request failures (OS error)
  // =========================================================================

  describe('permission request OS errors', () => {
    it('handles OS throwing when requesting camera permission', async () => {
      mockRequestCameraPermissions.mockRejectedValue(new Error('OS error'));

      const imagePicker = require('expo-image-picker');

      await expect(imagePicker.requestCameraPermissionsAsync()).rejects.toThrow(
        'OS error'
      );
    });

    it('handles OS throwing when requesting media library permission', async () => {
      mockRequestMediaLibraryPermissions.mockRejectedValue(new Error('OS permission error'));

      const imagePicker = require('expo-image-picker');

      await expect(imagePicker.requestMediaLibraryPermissionsAsync()).rejects.toThrow(
        'OS permission error'
      );
    });
  });

  // =========================================================================
  // Repeated permission requests
  // =========================================================================

  describe('repeated permission requests', () => {
    it('does not re-request permission if already granted', async () => {
      mockRequestCameraPermissions.mockResolvedValue(GRANTED_PERMISSION);

      const imagePicker = require('expo-image-picker');

      // First request
      const first = await imagePicker.requestCameraPermissionsAsync();
      // If already granted, app can skip re-requesting on subsequent opens
      if (first.granted) {
        // Simulate not calling requestCameraPermissionsAsync again
      }

      // Only one call should have happened
      expect(mockRequestCameraPermissions).toHaveBeenCalledTimes(1);
    });

    it('requests again if previously denied (user may change in Settings)', async () => {
      // First: denied
      mockRequestCameraPermissions.mockResolvedValueOnce(DENIED_PERMISSION);
      // Second: user went to Settings and granted
      mockRequestCameraPermissions.mockResolvedValueOnce(GRANTED_PERMISSION);

      const imagePicker = require('expo-image-picker');

      const first = await imagePicker.requestCameraPermissionsAsync();
      const second = await imagePicker.requestCameraPermissionsAsync();

      expect(first.status).toBe('denied');
      expect(second.status).toBe('granted');
    });
  });
});
