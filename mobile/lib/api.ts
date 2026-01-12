/**
 * API Client for FormCheck
 * Communicates with the FastAPI backend (via ngrok in dev)
 */

const API_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';

console.log('🔗 API URL configured:', API_URL);

export interface ShotFrame {
  label: string;
  image_base64: string;
  frame_number: number;
}

export interface AnalyzeResponse {
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
  frames?: ShotFrame[];
}

/**
 * Check API health
 */
export async function checkHealth(): Promise<{
  status: string;
  modules_available: boolean;
  gemini_configured: boolean;
  database_available: boolean;
}> {
  try {
    console.log('🔍 Checking API health at:', `${API_URL}/health`);
    
    const response = await fetch(`${API_URL}/health`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
    });
    
    console.log('📡 Health check response status:', response.status);
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error('❌ Health check failed:', errorText);
      throw new Error(`API health check failed: ${response.status}`);
    }
    
    const data = await response.json();
    console.log('✓ API is healthy:', data);
    return data;
  } catch (error: any) {
    console.error('❌ Health check error:', error.message);
    throw new Error(`Cannot connect to API at ${API_URL}. Make sure your API is running and ngrok URL is correct in .env`);
  }
}

/**
 * Upload and analyze a video
 */
export async function analyzeVideo(
  videoUri: string,
  shootingSide: 'left' | 'right' = 'right',
  playerId?: number
): Promise<AnalyzeResponse> {
  try {
    // Create form data
    const formData = new FormData();
    
    // Add video file
    const filename = videoUri.split('/').pop() || 'video.mp4';
    formData.append('file', {
      uri: videoUri,
      type: 'video/mp4',
      name: filename,
    } as any);
    
    // Add parameters as query string
    const params = new URLSearchParams({
      shooting_side: shootingSide,
    });
    
    if (playerId) {
      params.append('player_id', playerId.toString());
    }
    
    const url = `${API_URL}/analyze?${params.toString()}`;
    console.log('📤 Uploading video to:', url);
    console.log('📹 Video URI:', videoUri);
    console.log('🤚 Shooting side:', shootingSide);
    
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
      headers: {
        'Accept': 'application/json',
      },
    });
    
    console.log('📡 Analyze response status:', response.status);
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
      console.error('❌ API error:', errorData);
      
      // Handle specific errors
      if (response.status === 404) {
        throw new Error('No shot detected in video. Make sure you capture a clear shooting motion with your full body visible.');
      }
      
      throw new Error(errorData.detail || `API error: ${response.status}`);
    }
    
    const data = await response.json();
    console.log('✓ Analysis complete:', {
      made: data.made,
      rating: data.form_rating,
      feedback: data.feedback?.substring(0, 50) + '...',
      frames: data.frames?.length || 0,
    });
    
    return data;
  } catch (error: any) {
    console.error('❌ Analyze video error:', error);
    throw error;
  }
}

/**
 * Test API connection
 */
export async function testConnection(): Promise<boolean> {
  try {
    const health = await checkHealth();
    return health.status === 'healthy';
  } catch (error) {
    console.error('❌ API connection failed:', error);
    return false;
  }
}