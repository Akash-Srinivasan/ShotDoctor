/**
 * FormCheck API Client
 * Handles communication with the Python backend
 */

// ============================================================================
// Configuration
// ============================================================================

const API_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';
const API_TIMEOUT = 120000; // 2 minutes for video analysis

// ============================================================================
// Types
// ============================================================================

export interface ShotAnalysis {
  shot_number: number;
  made: boolean | null;
  miss_type: string | null;
  form_rating: number | null;
  feedback: string;
  key_issue: string | null;
  quick_cue: string | null;
  elbow_angle_load: number;
  elbow_angle_release: number;
  wrist_height_release: number;
  knee_bend_load: number;
  thumbnail: string; // Base64 encoded
}

export interface SessionSummary {
  total_shots: number;
  shots_made: number;
  shots_missed: number;
  shooting_percentage: number;
  average_form_rating: number;
  session_feedback: string;
  drill_suggestions: string[];
  shots: ShotAnalysis[];
}

export interface HealthResponse {
  status: string;
  modules_available: boolean;
  gemini_configured: boolean;
  database_available: boolean;
}

export interface ApiError extends Error {
  status?: number;
  code?: string;
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Create a timeout promise
 */
function timeout(ms: number): Promise<never> {
  return new Promise((_, reject) => {
    setTimeout(() => reject(new Error(`Request timed out after ${ms}ms`)), ms);
  });
}

/**
 * Make a fetch request with timeout
 */
async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs = API_TIMEOUT
): Promise<Response> {
  return Promise.race([
    fetch(url, options),
    timeout(timeoutMs),
  ]);
}

/**
 * Handle API response and throw on error
 */
async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}`;
    
    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorData.message || errorMessage;
    } catch {
      // Response wasn't JSON
      errorMessage = await response.text() || errorMessage;
    }

    const error: ApiError = new Error(errorMessage);
    error.status = response.status;
    throw error;
  }

  return response.json();
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * Test connection to the API server
 */
export async function testConnection(): Promise<boolean> {
  try {
    const response = await fetchWithTimeout(
      `${API_URL}/health`,
      { method: 'GET' },
      5000 // 5 second timeout for health check
    );
    
    const data = await handleResponse<HealthResponse>(response);
    
    // Check that required modules are available
    if (!data.modules_available) {
      console.warn('API connected but modules not available');
      return false;
    }
    
    if (!data.gemini_configured) {
      console.warn('API connected but Gemini not configured');
      // Still return true - API is reachable, just AI won't work
    }
    
    return true;
  } catch (error) {
    console.error('API connection test failed:', error);
    return false;
  }
}

/**
 * Get API health status with details
 */
export async function getHealthStatus(): Promise<HealthResponse | null> {
  try {
    const response = await fetchWithTimeout(
      `${API_URL}/health`,
      { method: 'GET' },
      5000
    );
    return handleResponse<HealthResponse>(response);
  } catch (error) {
    console.error('Health check failed:', error);
    return null;
  }
}

/**
 * Analyze a video for basketball shots
 */
export async function analyzeVideo(
  videoUri: string,
  shootingHand: 'left' | 'right' = 'right',
  playerId?: number
): Promise<SessionSummary> {
  // Create form data for file upload
  const formData = new FormData();
  
  // Get file info from URI
  const uriParts = videoUri.split('/');
  const fileName = uriParts[uriParts.length - 1] || 'video.mp4';
  
  // Determine mime type
  const extension = fileName.split('.').pop()?.toLowerCase() || 'mp4';
  const mimeTypes: Record<string, string> = {
    mp4: 'video/mp4',
    mov: 'video/quicktime',
    avi: 'video/x-msvideo',
    webm: 'video/webm',
  };
  const mimeType = mimeTypes[extension] || 'video/mp4';

  // Append file to form data
  // @ts-ignore - React Native's FormData accepts this format
  formData.append('file', {
    uri: videoUri,
    name: fileName,
    type: mimeType,
  });

  // Build URL with query params
  const params = new URLSearchParams({
    shooting_side: shootingHand,
  });
  
  if (playerId !== undefined) {
    params.append('player_id', playerId.toString());
  }

  const url = `${API_URL}/analyze?${params.toString()}`;

  console.log(`📤 Uploading video to ${url}`);
  console.log(`   File: ${fileName} (${mimeType})`);

  try {
    const response = await fetchWithTimeout(
      url,
      {
        method: 'POST',
        body: formData,
        headers: {
          // Don't set Content-Type - let fetch set it with boundary
          'Accept': 'application/json',
        },
      },
      API_TIMEOUT
    );

    const result = await handleResponse<SessionSummary>(response);
    
    console.log(`✅ Analysis complete: ${result.total_shots} shots detected`);
    
    return result;
  } catch (error) {
    console.error('Video analysis failed:', error);
    
    // Re-throw with more context
    if (error instanceof Error) {
      const apiError: ApiError = error;
      
      if (apiError.message.includes('timeout')) {
        throw new Error('Video analysis timed out. Try a shorter video.');
      }
      
      if (apiError.status === 404) {
        throw new Error('No shots detected in video. Make sure your full body is visible.');
      }
      
      if (apiError.status === 503) {
        throw new Error('Analysis service unavailable. Please try again later.');
      }
      
      throw apiError;
    }
    
    throw new Error('Unknown error during video analysis');
  }
}

/**
 * Get API info
 */
export async function getApiInfo(): Promise<{
  name: string;
  version: string;
  status: string;
  features: Record<string, boolean>;
} | null> {
  try {
    const response = await fetchWithTimeout(
      `${API_URL}/`,
      { method: 'GET' },
      5000
    );
    return handleResponse(response);
  } catch (error) {
    console.error('Failed to get API info:', error);
    return null;
  }
}

// ============================================================================
// Progress Tracking (for future WebSocket implementation)
// ============================================================================

export type AnalysisProgress = {
  stage: 'uploading' | 'detecting' | 'analyzing' | 'generating' | 'complete';
  progress: number; // 0-100
  message: string;
  shotsFound?: number;
  currentShot?: number;
};

export type ProgressCallback = (progress: AnalysisProgress) => void;

/**
 * Analyze video with progress updates
 * TODO: Implement WebSocket or SSE for real progress tracking
 */
export async function analyzeVideoWithProgress(
  videoUri: string,
  shootingHand: 'left' | 'right',
  onProgress: ProgressCallback,
  playerId?: number
): Promise<SessionSummary> {
  // Simulate progress stages while the actual request is happening
  // In a real implementation, this would use WebSockets or polling
  
  const progressStages: AnalysisProgress[] = [
    { stage: 'uploading', progress: 10, message: 'Uploading video...' },
    { stage: 'detecting', progress: 30, message: 'Detecting shots...' },
    { stage: 'analyzing', progress: 50, message: 'Analyzing form...' },
    { stage: 'generating', progress: 80, message: 'Generating feedback...' },
  ];

  // Start progress simulation
  let stageIndex = 0;
  const progressInterval = setInterval(() => {
    if (stageIndex < progressStages.length) {
      onProgress(progressStages[stageIndex]);
      stageIndex++;
    }
  }, 2500);

  try {
    const result = await analyzeVideo(videoUri, shootingHand, playerId);
    
    // Complete progress
    clearInterval(progressInterval);
    onProgress({
      stage: 'complete',
      progress: 100,
      message: 'Analysis complete!',
      shotsFound: result.total_shots,
    });
    
    return result;
  } catch (error) {
    clearInterval(progressInterval);
    throw error;
  }
}