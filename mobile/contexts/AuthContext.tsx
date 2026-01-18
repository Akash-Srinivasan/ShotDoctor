/**
 * AuthContext - Authentication State Management
 * Provides user auth state, profile data, and auth operations throughout the app
 */

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { Alert } from 'react-native';
import { supabase, type Profile } from '../lib/supabase';
import type { Session, User } from '@supabase/supabase-js';

// ============================================================================
// Types
// ============================================================================

interface AuthState {
  user: User | null;
  session: Session | null;
  profile: Profile | null;
  loading: boolean;
  initialized: boolean;
}

interface AuthContextType extends AuthState {
  // Auth operations
  signUp: (email: string, password: string, fullName?: string) => Promise<{ error: Error | null }>;
  signIn: (email: string, password: string) => Promise<{ error: Error | null }>;
  signOut: () => Promise<void>;
  resetPassword: (email: string) => Promise<{ error: Error | null }>;
  updatePassword: (newPassword: string) => Promise<{ error: Error | null }>;
  
  // Profile operations
  refreshProfile: () => Promise<void>;
  updateProfile: (updates: Partial<Profile>) => Promise<{ error: Error | null }>;
  
  // Session helpers
  isSubscribed: boolean;
  subscriptionTier: 'free' | 'pro' | 'team';
  
  // Utilities
  forceClearSession: () => Promise<void>;
}

// ============================================================================
// Context
// ============================================================================

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// ============================================================================
// Provider
// ============================================================================

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    session: null,
    profile: null,
    loading: true,
    initialized: false,
  });

  // --------------------------------------------------------------------------
  // Initialize auth state
  // --------------------------------------------------------------------------
  
  useEffect(() => {
    // Get initial session
    const initializeAuth = async () => {
      try {
        const { data: { session }, error } = await supabase.auth.getSession();
        
        if (error) {
          console.error('Error getting session:', error);
          // Clear potentially invalid session
          await supabase.auth.signOut();
          setState(prev => ({ ...prev, loading: false, initialized: true }));
          return;
        }

        if (session?.user) {
          // Validate session by trying to get user
          const { data: { user }, error: userError } = await supabase.auth.getUser();
          
          if (userError || !user) {
            // Session is invalid (user deleted, expired, etc.)
            console.warn('Invalid session detected, clearing...', userError);
            await supabase.auth.signOut();
            setState({
              user: null,
              session: null,
              profile: null,
              loading: false,
              initialized: true,
            });
            return;
          }

          // Session is valid, fetch profile
          const profile = await fetchProfile(session.user.id);
          setState({
            user: session.user,
            session,
            profile,
            loading: false,
            initialized: true,
          });
        } else {
          setState(prev => ({ 
            ...prev, 
            loading: false, 
            initialized: true 
          }));
        }
      } catch (error) {
        console.error('Auth initialization error:', error);
        // Clear potentially corrupted state
        await supabase.auth.signOut();
        setState(prev => ({ 
          ...prev, 
          user: null,
          session: null,
          profile: null,
          loading: false, 
          initialized: true 
        }));
      }
    };

    initializeAuth();

    // Listen for auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, session) => {
        console.log('Auth state change:', event);
        
        if (event === 'SIGNED_IN' && session?.user) {
          const profile = await fetchProfile(session.user.id);
          setState({
            user: session.user,
            session,
            profile,
            loading: false,
            initialized: true,
          });
        } else if (event === 'SIGNED_OUT') {
          setState({
            user: null,
            session: null,
            profile: null,
            loading: false,
            initialized: true,
          });
        } else if (event === 'TOKEN_REFRESHED' && session) {
          setState(prev => ({
            ...prev,
            session,
            user: session.user,
          }));
        } else if (event === 'USER_UPDATED' && session?.user) {
          const profile = await fetchProfile(session.user.id);
          setState(prev => ({
            ...prev,
            user: session.user,
            profile,
          }));
        }
      }
    );

    return () => {
      subscription.unsubscribe();
    };
  }, []);

  // --------------------------------------------------------------------------
  // Helper functions
  // --------------------------------------------------------------------------
  
  const fetchProfile = async (userId: string): Promise<Profile | null> => {
    try {
      const { data, error } = await supabase
        .from('profiles')
        .select('*')
        .eq('id', userId)
        .single();

      if (error) {
        // Profile doesn't exist yet - that's OK for new users
        if (error.code === 'PGRST116') {
          return null;
        }
        console.error('Error fetching profile:', error);
        return null;
      }

      return data as Profile;
    } catch (error) {
      console.error('Error fetching profile:', error);
      return null;
    }
  };

  // --------------------------------------------------------------------------
  // Auth operations
  // --------------------------------------------------------------------------
  
  const signUp = useCallback(async (
    email: string, 
    password: string, 
    fullName?: string
  ): Promise<{ error: Error | null }> => {
    try {
      setState(prev => ({ ...prev, loading: true }));

      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: {
            full_name: fullName || '',
          },
        },
      });

      if (error) {
        setState(prev => ({ ...prev, loading: false }));
        return { error };
      }

      // If email confirmation is required
      if (data.user && !data.session) {
        setState(prev => ({ ...prev, loading: false }));
        Alert.alert(
          'Check Your Email',
          'We sent you a confirmation link. Please check your email to complete sign up.'
        );
        return { error: null };
      }

      // If auto-confirmed (for development)
      if (data.session && data.user) {
        // Profile will be created by database trigger or we create it here
        const profile = await fetchProfile(data.user.id);
        setState({
          user: data.user,
          session: data.session,
          profile,
          loading: false,
          initialized: true,
        });
      }

      return { error: null };
    } catch (error) {
      setState(prev => ({ ...prev, loading: false }));
      return { error: error as Error };
    }
  }, []);

  const signIn = useCallback(async (
    email: string, 
    password: string
  ): Promise<{ error: Error | null }> => {
    try {
      setState(prev => ({ ...prev, loading: true }));

      const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (error) {
        setState(prev => ({ ...prev, loading: false }));
        return { error };
      }

      if (data.session && data.user) {
        const profile = await fetchProfile(data.user.id);
        setState({
          user: data.user,
          session: data.session,
          profile,
          loading: false,
          initialized: true,
        });
      }

      return { error: null };
    } catch (error) {
      setState(prev => ({ ...prev, loading: false }));
      return { error: error as Error };
    }
  }, []);

  const signOut = useCallback(async (): Promise<void> => {
    try {
      setState(prev => ({ ...prev, loading: true }));
      await supabase.auth.signOut();
      setState({
        user: null,
        session: null,
        profile: null,
        loading: false,
        initialized: true,
      });
    } catch (error) {
      console.error('Sign out error:', error);
      setState(prev => ({ ...prev, loading: false }));
    }
  }, []);

  const resetPassword = useCallback(async (
    email: string
  ): Promise<{ error: Error | null }> => {
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: 'formcheck://reset-password',
      });
      
      if (error) {
        return { error };
      }

      Alert.alert(
        'Check Your Email',
        'We sent you a password reset link. Please check your email.'
      );
      
      return { error: null };
    } catch (error) {
      return { error: error as Error };
    }
  }, []);

  const updatePassword = useCallback(async (
    newPassword: string
  ): Promise<{ error: Error | null }> => {
    try {
      const { error } = await supabase.auth.updateUser({
        password: newPassword,
      });
      
      return { error: error || null };
    } catch (error) {
      return { error: error as Error };
    }
  }, []);

  // --------------------------------------------------------------------------
  // Profile operations
  // --------------------------------------------------------------------------
  
  const refreshProfile = useCallback(async (): Promise<void> => {
    if (!state.user) return;
    
    const profile = await fetchProfile(state.user.id);
    setState(prev => ({ ...prev, profile }));
  }, [state.user]);

  const updateProfile = useCallback(async (
    updates: Partial<Profile>
  ): Promise<{ error: Error | null }> => {
    // Double-check authentication state
    const { data: { user }, error: authError } = await supabase.auth.getUser();
    
    if (authError || !user) {
      // Session is invalid, clear state and return error
      console.error('Session validation failed in updateProfile:', authError);
      await supabase.auth.signOut();
      setState({
        user: null,
        session: null,
        profile: null,
        loading: false,
        initialized: true,
      });
      return { error: new Error('Session expired. Please log in again.') };
    }

    try {
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
        // Check if it's an auth error
        if (error.message?.includes('JWT') || error.message?.includes('auth')) {
          await supabase.auth.signOut();
          setState({
            user: null,
            session: null,
            profile: null,
            loading: false,
            initialized: true,
          });
          return { error: new Error('Session expired. Please log in again.') };
        }
        return { error };
      }

      setState(prev => ({ ...prev, profile: data as Profile }));
      return { error: null };
    } catch (error) {
      return { error: error as Error };
    }
  }, []);

  // --------------------------------------------------------------------------
  // Utilities
  // --------------------------------------------------------------------------
  
  const forceClearSession = useCallback(async (): Promise<void> => {
    try {
      console.log('🧹 Force clearing all session data...');
      
      // Sign out from Supabase (clears AsyncStorage)
      await supabase.auth.signOut();
      
      // Clear local state
      setState({
        user: null,
        session: null,
        profile: null,
        loading: false,
        initialized: true,
      });
      
      console.log('✅ Session cleared successfully');
    } catch (error) {
      console.error('Error clearing session:', error);
      // Force clear state even if signOut fails
      setState({
        user: null,
        session: null,
        profile: null,
        loading: false,
        initialized: true,
      });
    }
  }, []);

  // --------------------------------------------------------------------------
  // Computed values
  // --------------------------------------------------------------------------
  
  const isSubscribed = state.profile?.subscription_tier !== 'free' && 
    state.profile?.subscription_expires_at !== null &&
    new Date(state.profile?.subscription_expires_at || 0) > new Date();

  const subscriptionTier = state.profile?.subscription_tier || 'free';

  // --------------------------------------------------------------------------
  // Context value
  // --------------------------------------------------------------------------
  
  const value: AuthContextType = {
    ...state,
    signUp,
    signIn,
    signOut,
    resetPassword,
    updatePassword,
    refreshProfile,
    updateProfile,
    isSubscribed,
    subscriptionTier,
    forceClearSession,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

// ============================================================================
// Hook
// ============================================================================

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  
  return context;
}

// ============================================================================
// Higher-order component for protected screens (optional utility)
// ============================================================================

export function withAuth<P extends object>(
  Component: React.ComponentType<P>
): React.FC<P> {
  return function ProtectedComponent(props: P) {
    const { user, loading } = useAuth();
    
    if (loading) {
      return null; // Or a loading component
    }
    
    if (!user) {
      return null; // Router will redirect
    }
    
    return <Component {...props} />;
  };
}