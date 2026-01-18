/**
 * Supabase Client Configuration
 * Handles authentication and database operations
 */

import 'react-native-url-polyfill/auto';
import { createClient } from '@supabase/supabase-js';
import AsyncStorage from '@react-native-async-storage/async-storage';

// ============================================================================
// Configuration
// ============================================================================

const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;

// Validate environment variables at startup
if (!supabaseUrl || !supabaseAnonKey) {
  console.error('❌ Missing Supabase credentials in .env');
  console.error('   Required: EXPO_PUBLIC_SUPABASE_URL, EXPO_PUBLIC_SUPABASE_ANON_KEY');
  // Don't throw - allow app to start but show errors when used
}

// ============================================================================
// Client
// ============================================================================

export const supabase = createClient(
  supabaseUrl || 'https://placeholder.supabase.co',
  supabaseAnonKey || 'placeholder-key',
  {
    auth: {
      storage: AsyncStorage,
      autoRefreshToken: true,
      persistSession: true,
      detectSessionInUrl: false,
    },
  }
);

// ============================================================================
// Types
// ============================================================================

export type SkillLevel = 'beginner' | 'intermediate' | 'advanced';
export type ShootingHand = 'left' | 'right';
export type SubscriptionTier = 'free' | 'pro' | 'team';

export interface Profile {
  id: string;
  email: string;
  full_name: string | null;
  skill_level: SkillLevel | null;
  shooting_hand: ShootingHand;
  height_inches: number | null;
  focus_areas: string[] | null;
  primary_goal: string | null;
  preferred_distance: string | null;
  plays_organized: boolean;
  practice_frequency: string | null;
  notifications_enabled: boolean;
  subscription_tier: SubscriptionTier;
  subscription_expires_at: string | null;
  total_sessions: number;
  total_shots: number;
  total_makes: number;
  last_session_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Session {
  id: string;
  user_id: string;
  started_at: string;
  ended_at: string | null;
  shot_count: number;
  make_count: number;
  miss_count: number;
  shooting_percentage: number;
  average_form_rating: number | null;
  session_feedback: string | null;
  drill_suggestions: string[] | null;
  focus_area: string | null;
  location: string | null;
  notes: string | null;
  shooting_hand: string;
  duration_seconds: number | null;
  video_duration_seconds: number | null;
  created_at: string;
}

export interface Shot {
  id: string;
  session_id: string;
  user_id: string;
  shot_number: number;
  made: boolean | null;
  miss_type: string | null;
  elbow_angle_load: number;
  elbow_angle_release: number;
  wrist_height_release: number;
  knee_bend_load: number;
  form_rating: number | null;
  feedback: string;
  key_issue: string | null;
  quick_cue: string | null;
  thumbnail_url: string | null;
  created_at: string;
}

export interface UserStats {
  totalSessions: number;
  totalShots: number;
  totalMakes: number;
  avgShootingPercentage: number;
  avgFormRating: number;
}

// ============================================================================
// Database Helper Functions
// ============================================================================

export const db = {
  // --------------------------------------------------------------------------
  // Profile Operations
  // --------------------------------------------------------------------------
  
  /**
   * Get current user's profile
   */
  async getProfile(): Promise<Profile | null> {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return null;

    const { data, error } = await supabase
      .from('profiles')
      .select('*')
      .eq('id', user.id)
      .single();

    if (error) {
      console.error('Error fetching profile:', error);
      throw error;
    }
    return data as Profile;
  },

  /**
   * Update user profile
   */
  async updateProfile(updates: Partial<Profile>): Promise<Profile> {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) throw new Error('Not authenticated');

    const { data, error } = await supabase
      .from('profiles')
      .update({
        ...updates,
        updated_at: new Date().toISOString(),
      })
      .eq('id', user.id)
      .select()
      .single();

    if (error) {
      console.error('Error updating profile:', error);
      throw error;
    }
    return data as Profile;
  },

  // --------------------------------------------------------------------------
  // Session Operations
  // --------------------------------------------------------------------------
  
  /**
   * Get user's sessions with pagination
   */
  async getSessions(limit = 10, offset = 0): Promise<Session[]> {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return [];

    const { data, error } = await supabase
      .from('sessions')
      .select('*')
      .eq('user_id', user.id)
      .order('started_at', { ascending: false })
      .range(offset, offset + limit - 1);

    if (error) {
      console.error('Error fetching sessions:', error);
      throw error;
    }
    return data as Session[];
  },

  /**
   * Get session by ID
   */
  async getSession(sessionId: string): Promise<Session> {
    const { data, error } = await supabase
      .from('sessions')
      .select('*')
      .eq('id', sessionId)
      .single();

    if (error) {
      console.error('Error fetching session:', error);
      throw error;
    }
    return data as Session;
  },

  /**
   * Create a new session
   */
  async createSession(sessionData: {
    shooting_hand: string;
    focus_area?: string;
    location?: string;
  }): Promise<Session> {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) throw new Error('Not authenticated');

    const { data, error } = await supabase
      .from('sessions')
      .insert({
        user_id: user.id,
        started_at: new Date().toISOString(),
        shot_count: 0,
        make_count: 0,
        miss_count: 0,
        shooting_percentage: 0,
        ...sessionData,
      })
      .select()
      .single();

    if (error) {
      console.error('Error creating session:', error);
      throw error;
    }
    return data as Session;
  },

  /**
   * Update session (when analysis completes)
   */
  async updateSession(
    sessionId: string, 
    updates: {
      ended_at?: string;
      shot_count: number;
      make_count: number;
      miss_count: number;
      shooting_percentage: number;
      average_form_rating?: number;
      session_feedback?: string;
      drill_suggestions?: string[];
      duration_seconds?: number;
      video_duration_seconds?: number;
    }
  ): Promise<Session> {
    const { data, error } = await supabase
      .from('sessions')
      .update(updates)
      .eq('id', sessionId)
      .select()
      .single();

    if (error) {
      console.error('Error updating session:', error);
      throw error;
    }
    
    // Update user's profile stats after session update
    await this.updateUserStats();
    
    return data as Session;
  },

  /**
   * Delete a session and its shots
   */
  async deleteSession(sessionId: string): Promise<void> {
    // Shots will be cascade deleted if FK is set up properly
    const { error } = await supabase
      .from('sessions')
      .delete()
      .eq('id', sessionId);

    if (error) {
      console.error('Error deleting session:', error);
      throw error;
    }
    
    await this.updateUserStats();
  },

  // --------------------------------------------------------------------------
  // Shot Operations
  // --------------------------------------------------------------------------
  
  /**
   * Get shots for a session
   */
  async getShots(sessionId: string): Promise<Shot[]> {
    const { data, error } = await supabase
      .from('shots')
      .select('*')
      .eq('session_id', sessionId)
      .order('shot_number', { ascending: true });

    if (error) {
      console.error('Error fetching shots:', error);
      throw error;
    }
    return data as Shot[];
  },

  /**
   * Create shots in batch
   */
  async createShots(
    shots: Array<{
      session_id: string;
      shot_number: number;
      made: boolean | null;
      miss_type: string | null;
      elbow_angle_load: number;
      elbow_angle_release: number;
      wrist_height_release: number;
      knee_bend_load: number;
      form_rating: number | null;
      feedback: string;
      key_issue: string | null;
      quick_cue: string | null;
      thumbnail_url: string | null;
    }>
  ): Promise<Shot[]> {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) throw new Error('Not authenticated');

    // Add user_id to each shot
    const shotsWithUserId = shots.map(shot => ({
      ...shot,
      user_id: user.id,
    }));

    const { data, error } = await supabase
      .from('shots')
      .insert(shotsWithUserId)
      .select();

    if (error) {
      console.error('Error creating shots:', error);
      throw error;
    }
    return data as Shot[];
  },

  // --------------------------------------------------------------------------
  // Stats Operations
  // --------------------------------------------------------------------------
  
  /**
   * Get user stats (aggregated from sessions)
   */
  async getUserStats(): Promise<UserStats> {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) {
      return {
        totalSessions: 0,
        totalShots: 0,
        totalMakes: 0,
        avgShootingPercentage: 0,
        avgFormRating: 0,
      };
    }

    const { data, error } = await supabase
      .from('sessions')
      .select('shot_count, make_count, shooting_percentage, average_form_rating')
      .eq('user_id', user.id);

    if (error) {
      console.error('Error fetching user stats:', error);
      throw error;
    }

    if (!data || data.length === 0) {
      return {
        totalSessions: 0,
        totalShots: 0,
        totalMakes: 0,
        avgShootingPercentage: 0,
        avgFormRating: 0,
      };
    }

    const totalSessions = data.length;
    const totalShots = data.reduce((sum, s) => sum + (s.shot_count || 0), 0);
    const totalMakes = data.reduce((sum, s) => sum + (s.make_count || 0), 0);
    const avgShootingPercentage = totalShots > 0 ? (totalMakes / totalShots) * 100 : 0;
    
    const ratingsData = data.filter(s => s.average_form_rating != null);
    const avgFormRating = ratingsData.length > 0
      ? ratingsData.reduce((sum, s) => sum + (s.average_form_rating || 0), 0) / ratingsData.length
      : 0;

    return {
      totalSessions,
      totalShots,
      totalMakes,
      avgShootingPercentage,
      avgFormRating,
    };
  },

  /**
   * Update user profile stats from sessions
   * Called after session create/update/delete
   */
  async updateUserStats(): Promise<void> {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return;

    try {
      const stats = await this.getUserStats();
      
      // Get most recent session date
      const { data: recentSession } = await supabase
        .from('sessions')
        .select('started_at')
        .eq('user_id', user.id)
        .order('started_at', { ascending: false })
        .limit(1)
        .single();

      await supabase
        .from('profiles')
        .update({
          total_sessions: stats.totalSessions,
          total_shots: stats.totalShots,
          total_makes: stats.totalMakes,
          last_session_at: recentSession?.started_at || null,
          updated_at: new Date().toISOString(),
        })
        .eq('id', user.id);
    } catch (error) {
      console.error('Error updating user stats:', error);
      // Don't throw - this is a background update
    }
  },

  // --------------------------------------------------------------------------
  // Storage Operations
  // --------------------------------------------------------------------------
  
  /**
   * Upload thumbnail image and return URL
   */
  async uploadThumbnail(
    sessionId: string,
    shotNumber: number,
    base64Data: string
  ): Promise<string | null> {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return null;

    try {
      // Convert base64 to blob
      const byteCharacters = atob(base64Data);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      const blob = new Blob([byteArray], { type: 'image/jpeg' });

      const fileName = `${user.id}/${sessionId}/shot_${shotNumber}.jpg`;
      
      const { data, error } = await supabase.storage
        .from('thumbnails')
        .upload(fileName, blob, {
          contentType: 'image/jpeg',
          upsert: true,
        });

      if (error) {
        console.error('Error uploading thumbnail:', error);
        return null;
      }

      // Get public URL
      const { data: { publicUrl } } = supabase.storage
        .from('thumbnails')
        .getPublicUrl(fileName);

      return publicUrl;
    } catch (error) {
      console.error('Error in uploadThumbnail:', error);
      return null;
    }
  },
};

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Check if Supabase is properly configured
 */
export function isSupabaseConfigured(): boolean {
  return Boolean(supabaseUrl && supabaseAnonKey);
}

/**
 * Get the current user ID (if authenticated)
 */
export async function getCurrentUserId(): Promise<string | null> {
  const { data: { user } } = await supabase.auth.getUser();
  return user?.id || null;
}