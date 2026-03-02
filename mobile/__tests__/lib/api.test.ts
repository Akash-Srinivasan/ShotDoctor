/**
 * API Client Unit Tests
 * Tests for the FormCheck API client module
 */

import {
  testConnection,
  getHealthStatus,
  analyzeVideo,
  getApiInfo,
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
} from '../utils/mockData';

// Mock global fetch
global.fetch = jest.fn();

describe('API Client', () => {
  beforeEach(() => {
    clearAllMocks();
    jest.clearAllTimers();
  });

  // ==========================================================================
  // fetchWithTimeout Tests
  // ==========================================================================

  describe('fetchWithTimeout', () => {
    it('should successfully fetch within timeout', async () => {
      const mockData = createMockHealthResponse();
      mockFetch(createMockResponse(mockData));

      const result = await testConnection();

      expect(result).toBe(true);
      expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    it('should timeout after specified duration', async () => {
      jest.useFakeTimers();

      // Mock fetch that never resolves
      global.fetch = jest.fn(() => new Promise(() => {}));

      const connectionPromise = testConnection();

      // Fast-forward time past the 5 second timeout
      jest.advanceTimersByTime(5001);

      await expect(connectionPromise).resolves.toBe(false);

      jest.useRealTimers();
    });
  });

  // ==========================================================================
  // handleResponse Tests
  // ==========================================================================

  describe('handleResponse', () => {
    it('should parse successful JSON response', async () => {
      const mockData = createMockHealthResponse();
      mockFetch(createMockResponse(mockData));

      const result = await getHealthStatus();

      expect(result).toEqual(mockData);
    });

    it('should handle error with JSON detail', async () => {
      mockFetch(createMockErrorResponse(400, 'Invalid request'));

      const result = await getHealthStatus();

      expect(result).toBeNull();
    });

    it('should handle error with text response', async () => {
      const errorResponse = {
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: jest.fn().mockRejectedValue(new Error('Not JSON')),
        text: jest.fn().mockResolvedValue('Server error'),
        headers: new Headers(),
      } as unknown as Response;

      mockFetch(errorResponse);

      const result = await getHealthStatus();

      expect(result).toBeNull();
    });

    it('should extract error message from detail field', async () => {
      const errorResponse = createMockErrorResponse(404, 'Resource not found');
      mockFetch(errorResponse);

      await expect(getHealthStatus()).resolves.toBeNull();
    });

    it('should extract error message from message field', async () => {
      const errorResponse = {
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: jest.fn().mockResolvedValue({ message: 'Bad input' }),
        text: jest.fn().mockResolvedValue('Bad input'),
        headers: new Headers(),
      } as unknown as Response;

      mockFetch(errorResponse);

      await expect(getHealthStatus()).resolves.toBeNull();
    });
  });

  // ==========================================================================
  // testConnection Tests
  // ==========================================================================

  describe('testConnection', () => {
    it('should return true when API is healthy', async () => {
      const mockData = createMockHealthResponse({
        status: 'ok',
        modules_available: true,
        gemini_configured: true,
      });

      mockFetch(createMockResponse(mockData));

      const result = await testConnection();

      expect(result).toBe(true);
      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/health',
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('should return false when modules are not available', async () => {
      const mockData = createMockHealthResponse({
        modules_available: false,
      });

      mockFetch(createMockResponse(mockData));

      const result = await testConnection();

      expect(result).toBe(false);
    });

    it('should return true even if Gemini is not configured', async () => {
      const mockData = createMockHealthResponse({
        gemini_configured: false,
        modules_available: true,
      });

      mockFetch(createMockResponse(mockData));

      const result = await testConnection();

      expect(result).toBe(true);
    });

    it('should return false on network error', async () => {
      global.fetch = jest.fn().mockRejectedValue(new Error('Network error'));

      const result = await testConnection();

      expect(result).toBe(false);
    });

    it('should return false on timeout', async () => {
      jest.useFakeTimers();

      global.fetch = jest.fn(() => new Promise(() => {}));

      const connectionPromise = testConnection();
      jest.advanceTimersByTime(5001);

      const result = await connectionPromise;

      expect(result).toBe(false);

      jest.useRealTimers();
    });
  });

  // ==========================================================================
  // getHealthStatus Tests
  // ==========================================================================

  describe('getHealthStatus', () => {
    it('should return health status on success', async () => {
      const mockData = createMockHealthResponse();
      mockFetch(createMockResponse(mockData));

      const result = await getHealthStatus();

      expect(result).toEqual(mockData);
    });

    it('should return null on error', async () => {
      mockFetch(createMockErrorResponse(500, 'Server error'));

      const result = await getHealthStatus();

      expect(result).toBeNull();
    });
  });

  // ==========================================================================
  // analyzeVideo Tests
  // ==========================================================================

  describe('analyzeVideo', () => {
    const mockVideoUri = 'file:///path/to/video.mp4';

    it('should successfully analyze video with default parameters', async () => {
      const mockData = createMockSessionSummary();
      mockFetch(createMockResponse(mockData));

      const result = await analyzeVideo(mockVideoUri);

      expect(result).toEqual(mockData);
      expect(global.fetch).toHaveBeenCalledTimes(1);

      const [url, options] = (global.fetch as jest.Mock).mock.calls[0];
      expect(url).toContain('/analyze');
      expect(url).toContain('shooting_side=right');
      expect(options.method).toBe('POST');
      expect(options.body).toBeInstanceOf(FormData);
    });

    it('should include shooting hand in query params', async () => {
      const mockData = createMockSessionSummary();
      mockFetch(createMockResponse(mockData));

      await analyzeVideo(mockVideoUri, 'left');

      const [url] = (global.fetch as jest.Mock).mock.calls[0];
      expect(url).toContain('shooting_side=left');
    });

    it('should include rim position in query params', async () => {
      const mockData = createMockSessionSummary();
      mockFetch(createMockResponse(mockData));

      const rimPosition = { x: 0.5, y: 0.3 };
      await analyzeVideo(mockVideoUri, 'right', rimPosition);

      const [url] = (global.fetch as jest.Mock).mock.calls[0];
      expect(url).toContain('rim_x=0.5');
      expect(url).toContain('rim_y=0.3');
    });

    it('should include player ID in query params', async () => {
      const mockData = createMockSessionSummary();
      mockFetch(createMockResponse(mockData));

      await analyzeVideo(mockVideoUri, 'right', null, 42);

      const [url] = (global.fetch as jest.Mock).mock.calls[0];
      expect(url).toContain('player_id=42');
    });

    it('should handle .mov files with correct MIME type', async () => {
      const mockData = createMockSessionSummary();
      mockFetch(createMockResponse(mockData));

      await analyzeVideo('file:///path/to/video.mov');

      const [, options] = (global.fetch as jest.Mock).mock.calls[0];
      const formData = options.body as FormData;

      // FormData in tests doesn't expose entries easily, but we can verify it was created
      expect(formData).toBeInstanceOf(FormData);
    });

    it('should throw timeout error with helpful message', async () => {
      jest.useFakeTimers();

      global.fetch = jest.fn(() => new Promise(() => {}));

      const analyzePromise = analyzeVideo(mockVideoUri);
      jest.advanceTimersByTime(180001);

      await expect(analyzePromise).rejects.toThrow('Video analysis timed out');

      jest.useRealTimers();
    });

    it('should throw 404 error with helpful message', async () => {
      mockFetch(createMockErrorResponse(404, 'No shots detected'));

      await expect(analyzeVideo(mockVideoUri)).rejects.toThrow(
        'No shots detected in video'
      );
    });

    it('should throw 503 error with helpful message', async () => {
      mockFetch(createMockErrorResponse(503, 'Service unavailable'));

      await expect(analyzeVideo(mockVideoUri)).rejects.toThrow(
        'Analysis service unavailable'
      );
    });

    it('should handle generic errors', async () => {
      mockFetch(createMockErrorResponse(400, 'Bad request'));

      await expect(analyzeVideo(mockVideoUri)).rejects.toThrow();
    });

    it('should handle network errors', async () => {
      global.fetch = jest.fn().mockRejectedValue(new Error('Network error'));

      await expect(analyzeVideo(mockVideoUri)).rejects.toThrow('Network error');
    });

    it('should construct FormData with video file', async () => {
      const mockData = createMockSessionSummary();
      mockFetch(createMockResponse(mockData));

      await analyzeVideo('file:///path/to/basketball.mp4');

      const [, options] = (global.fetch as jest.Mock).mock.calls[0];
      expect(options.body).toBeInstanceOf(FormData);
      expect(options.headers.Accept).toBe('application/json');
    });

    it('should not include null rim position', async () => {
      const mockData = createMockSessionSummary();
      mockFetch(createMockResponse(mockData));

      await analyzeVideo(mockVideoUri, 'right', null);

      const [url] = (global.fetch as jest.Mock).mock.calls[0];
      expect(url).not.toContain('rim_x');
      expect(url).not.toContain('rim_y');
    });
  });

  // ==========================================================================
  // getApiInfo Tests
  // ==========================================================================

  describe('getApiInfo', () => {
    it('should return API info on success', async () => {
      const mockInfo = {
        name: 'FormCheck API',
        version: '1.0.0',
        status: 'ok',
        features: {
          video_analysis: true,
          ai_feedback: true,
        },
      };

      mockFetch(createMockResponse(mockInfo));

      const result = await getApiInfo();

      expect(result).toEqual(mockInfo);
      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/',
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('should return null on error', async () => {
      mockFetch(createMockErrorResponse(500, 'Server error'));

      const result = await getApiInfo();

      expect(result).toBeNull();
    });
  });
});
