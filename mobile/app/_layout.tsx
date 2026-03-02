/**
 * FormCheck - Root Layout
 * Wraps entire app with providers and handles navigation structure
 */

import { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { AuthProvider } from '../contexts/AuthContext';
import { FingerprintProvider } from '../contexts/FingerprintContext';
import { ErrorBoundary } from '../components/ErrorBoundary';
import * as SplashScreen from 'expo-splash-screen';

// Prevent splash screen from auto-hiding
SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  useEffect(() => {
    // Hide splash screen after a brief delay to allow auth to initialize
    const timer = setTimeout(() => {
      SplashScreen.hideAsync();
    }, 500);
    
    return () => clearTimeout(timer);
  }, []);

  return (
    <ErrorBoundary>
    <AuthProvider>
      <FingerprintProvider>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerStyle: {
            backgroundColor: '#000',
          },
          headerTintColor: '#fff',
          headerTitleStyle: {
            fontWeight: 'bold',
          },
          contentStyle: {
            backgroundColor: '#000',
          },
          animation: 'slide_from_right',
        }}
      >
        {/* Main entry point */}
        <Stack.Screen
          name="index"
          options={{
            title: 'FormCheck',
            headerShown: false,
          }}
        />
        
        {/* Auth screens */}
        <Stack.Screen
          name="auth/login"
          options={{
            title: 'Sign In',
            headerShown: false,
            animation: 'fade',
          }}
        />
        <Stack.Screen
          name="auth/signup"
          options={{
            title: 'Create Account',
            headerShown: false,
            animation: 'fade',
          }}
        />
        <Stack.Screen
          name="auth/forgot-password"
          options={{
            title: 'Reset Password',
            presentation: 'modal',
          }}
        />
        
        {/* Onboarding */}
        <Stack.Screen
          name="onboarding"
          options={{
            title: 'Setup',
            headerShown: false,
            gestureEnabled: false, // Prevent back gesture during onboarding
          }}
        />

        {/* Edit Preferences */}
        <Stack.Screen
          name="edit-preferences"
          options={{
            title: 'Edit Preferences',
            headerShown: false,
            presentation: 'modal',
          }}
        />
        
        {/* Session Detail */}
        <Stack.Screen
          name="session/[id]"
          options={{
            headerShown: false,
          }}
        />

        {/* Tab navigator */}
        <Stack.Screen
          name="(tabs)"
          options={{
            headerShown: false,
          }}
        />
      </Stack>
      </FingerprintProvider>
    </AuthProvider>
    </ErrorBoundary>
  );
}