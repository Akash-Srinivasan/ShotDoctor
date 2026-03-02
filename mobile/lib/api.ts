/**
 * FormCheck API Client
 * Handles communication with the Python backend
 */

// ============================================================================
// Configuration
// ============================================================================

const API_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';
const API_TIMEOUT = 600000; // 10 minutes for video analysis (upload + multi-shot Gemini calls + retries)

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
  hip_angle_load: number;
  elbow_height_load: number;
  heel_height_release: number;
  trunk_lean_release: number;
  stance_width: number;
  shoulder_level_diff: number;
  elbow_lateral_offset: number;
  camera_angle: string | null; // "side", "front", "angled"
  thumbnail: string; // Base64 encoded
  timestamp: number; // seconds into video when shot detected
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

// Rim position for make/miss detection
export interface RimPosition {
  x: number; // Normalized 0-1
  y: number; // Normalized 0-1
}

/**
 * Analyze a video for basketball shots
 */
export interface UserContext {
  skill_level?: string;
  focus_areas?: string;
  height_inches?: number;
  user_id?: string;
}

export async function analyzeVideo(
  videoUri: string,
  shootingHand: 'left' | 'right' = 'right',
  rimPosition?: RimPosition | null,
  playerId?: number,
  sessionId?: string,
  userContext?: UserContext
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

  // Add rim position if provided
  if (rimPosition) {
    params.append('rim_x', rimPosition.x.toString());
    params.append('rim_y', rimPosition.y.toString());
  }

  if (playerId !== undefined) {
    params.append('player_id', playerId.toString());
  }

  if (sessionId) {
    params.append('session_id', sessionId);
  }

  // User context for personalized analysis
  if (userContext?.skill_level) {
    params.append('skill_level', userContext.skill_level);
  }
  if (userContext?.focus_areas) {
    params.append('focus_areas', userContext.focus_areas);
  }
  if (userContext?.height_inches) {
    params.append('height_inches', userContext.height_inches.toString());
  }
  if (userContext?.user_id) {
    params.append('user_id', userContext.user_id);
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
      
      if (apiError.message.includes('timed out')) {
        throw new Error('Video analysis timed out. The server may still be processing — check your History tab in a few minutes.');
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

// ============================================================================
// Shot Fingerprint
// ============================================================================

export interface ImprovementArea {
  metric: string;
  label: string;
  make_avg: number;
  miss_avg: number;
  delta: number;
  optimal: number;
  impact_score: number;
  insight: string;
  cue: string;
  direction: string;
}

export interface ShotFingerprint {
  session_count: number;
  total_shots: number;
  fingerprint_ready: boolean;
  make_signature: Record<string, { avg: number; std: number }>;
  miss_signature: Record<string, { avg: number; std: number }>;
  improvement_areas: ImprovementArea[];
  consistency: Record<string, number>;
  miss_distribution: Record<string, number>;
  trend: {
    shooting_pct: number[];
    form_rating: number[];
    direction: string;
  };
  cues: string[];
  miss_tendency_cue: string;
  trend_label: string;
  consistency_note: string;
}

/**
 * Get user's shot fingerprint
 */
export async function getFingerprint(userId: string): Promise<ShotFingerprint | null> {
  try {
    const response = await fetchWithTimeout(
      `${API_URL}/fingerprint/${userId}`,
      { method: 'GET' },
      10000
    );
    return handleResponse<ShotFingerprint>(response);
  } catch (error) {
    console.error('Fingerprint fetch failed:', error);
    return null;
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
// Progress Tracking (polling-based)
// ============================================================================

export type AnalysisProgress = {
  stage: 'uploading' | 'detecting' | 'analyzing' | 'generating' | 'complete';
  progress: number; // 0-100
  message: string;
  shotsFound?: number;
  currentShot?: number;
  frame?: number;
  totalFrames?: number;
};

export type ProgressCallback = (progress: AnalysisProgress) => void;

interface ApiProgressResponse {
  stage: string;
  progress: number;
  message: string;
  frame?: number;
  total_frames?: number;
  shots_found?: number;
  current_shot?: number;
}

/**
 * Poll the progress endpoint for a session
 */
async function getProgress(sessionId: string): Promise<ApiProgressResponse | null> {
  try {
    const response = await fetchWithTimeout(
      `${API_URL}/progress/${sessionId}`,
      { method: 'GET' },
      5000
    );
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}

/**
 * Map API stage names to client stage names
 */
function mapStage(apiStage: string): AnalysisProgress['stage'] {
  switch (apiStage) {
    case 'uploading': return 'uploading';
    case 'detecting': return 'detecting';
    case 'analyzing_shot': return 'analyzing';
    case 'generating_summary': return 'generating';
    case 'complete': return 'complete';
    default: return 'uploading';
  }
}

/**
 * Analyze video with real progress polling from the API
 */
export async function analyzeVideoWithProgress(
  videoUri: string,
  shootingHand: 'left' | 'right',
  onProgress: ProgressCallback,
  rimPosition?: RimPosition | null,
  playerId?: number,
  sessionId?: string,
  userContext?: UserContext
): Promise<SessionSummary> {
  // Start polling progress if we have a session ID
  let pollInterval: ReturnType<typeof setInterval> | null = null;

  if (sessionId) {
    pollInterval = setInterval(async () => {
      const progress = await getProgress(sessionId);
      if (progress && progress.stage !== 'unknown') {
        onProgress({
          stage: mapStage(progress.stage),
          progress: progress.progress,
          message: progress.message,
          shotsFound: progress.shots_found,
          currentShot: progress.current_shot,
          frame: progress.frame,
          totalFrames: progress.total_frames,
        });
      }
    }, 1500);
  }

  try {
    const result = await analyzeVideo(videoUri, shootingHand, rimPosition, playerId, sessionId, userContext);

    if (pollInterval) clearInterval(pollInterval);
    onProgress({
      stage: 'complete',
      progress: 100,
      message: 'Analysis complete!',
      shotsFound: result.total_shots,
    });

    return result;
  } catch (error) {
    // If the network dropped but server is still processing, keep polling
    // and wait for the result instead of crashing immediately
    if (sessionId && error instanceof Error &&
        (error.message.includes('Network request failed') || error.message.includes('timed out'))) {
      console.log('⚠️ Upload connection lost, but server may still be processing. Polling for result...');
      onProgress({
        stage: 'analyzing',
        progress: 50,
        message: 'Connection interrupted — waiting for server to finish...',
      });

      // Poll progress until complete or truly failed (up to 8 minutes)
      const maxWaitMs = 480000;
      const pollMs = 3000;
      const startTime = Date.now();

      while (Date.now() - startTime < maxWaitMs) {
        await new Promise(r => setTimeout(r, pollMs));
        try {
          const progress = await getProgress(sessionId);
          if (progress && progress.stage !== 'unknown') {
            onProgress({
              stage: mapStage(progress.stage),
              progress: progress.progress,
              message: progress.message,
              shotsFound: progress.shots_found,
              currentShot: progress.current_shot,
            });

            // If server finished, try fetching result one more time
            if (progress.stage === 'complete' || progress.progress >= 98) {
              try {
                // Small delay to let server finalize response
                await new Promise(r => setTimeout(r, 2000));
                // The result is already saved to DB by the server at this point,
                // so we can construct a minimal success response
                onProgress({
                  stage: 'complete',
                  progress: 100,
                  message: 'Analysis complete! Check your History tab.',
                  shotsFound: progress.shots_found,
                });
                if (pollInterval) clearInterval(pollInterval);
                // Return a signal that analysis succeeded but result was lost
                // The calling code should redirect to history
                throw new Error('ANALYSIS_COMPLETE_CONNECTION_LOST');
              } catch (retryError) {
                if (pollInterval) clearInterval(pollInterval);
                throw retryError;
              }
            }
          }
        } catch (pollError) {
          // Progress poll failed — server might be down
          if (pollError instanceof Error && pollError.message === 'ANALYSIS_COMPLETE_CONNECTION_LOST') {
            throw pollError;
          }
          console.log('Progress poll failed, retrying...', pollError);
        }
      }

      // Timed out waiting
      if (pollInterval) clearInterval(pollInterval);
      throw new Error('Analysis is still processing on the server. Check your History tab in a few minutes.');
    }

    if (pollInterval) clearInterval(pollInterval);
    throw error;
  }
}