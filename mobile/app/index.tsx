/**
 * FormCheck - Entry Point / Router
 * Handles auth state and routes to appropriate screen
 */

import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Alert, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '../contexts/AuthContext';
import { testConnection } from '../lib/api';

export default function Index() {
  const router = useRouter();
  const { user, profile, loading: authLoading } = useAuth();
  const [apiConnected, setApiConnected] = useState<boolean | null>(null);
  const [checkingApi, setCheckingApi] = useState(true);

  // Check API connection on mount
  useEffect(() => {
    checkApiConnection();
  }, []);

  // Handle auth-based routing
  useEffect(() => {
    if (authLoading) return; // Wait for auth to initialize

    if (!user) {
      // Not logged in → go to login
      router.replace('/auth/login');
    } else if (!profile?.skill_level) {
      // Logged in but no profile → go to onboarding
      router.replace('/onboarding');
    } else {
        router.replace('/(tabs)');
    }
    // If user has profile, show the home screen (this component)
  }, [user, profile, authLoading]);
  
  const checkApiConnection = async () => {
    setCheckingApi(true);
    try {
      const connected = await testConnection();
      setApiConnected(connected);
      if (!connected) {
        Alert.alert(
          'API Not Connected',
          'Make sure your Python API is running and ngrok tunnel is active.\n\nRun: ./scripts/start-dev.sh',
          [{ text: 'Retry', onPress: checkApiConnection }]
        );
      }
    } catch (error) {
      setApiConnected(false);
    } finally {
      setCheckingApi(false);
    }
  };

  // Show loading while checking auth
  if (authLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#ff6b00" />
      </View>
    );
  }

  // If no user, we're redirecting - show nothing
  if (!user) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#ff6b00" />
      </View>
    );
  }

  // Main home screen for authenticated users
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>🏀 FormCheck</Text>
        <Text style={styles.subtitle}>Your AI Basketball Coach</Text>
        {profile?.full_name && (
          <Text style={styles.greeting}>Welcome back, {profile.full_name}!</Text>
        )}
      </View>

      <View style={styles.statusContainer}>
        <Text style={styles.statusLabel}>API Status:</Text>
        <View style={[
          styles.statusBadge,
          checkingApi && styles.statusBadgeLoading,
          apiConnected === true && styles.statusBadgeConnected,
          apiConnected === false && styles.statusBadgeDisconnected,
        ]}>
          <Text style={styles.statusText}>
            {checkingApi ? '⏳ Checking...' :
             apiConnected ? '✓ Connected' : '✗ Disconnected'}
          </Text>
        </View>
        <TouchableOpacity onPress={checkApiConnection} disabled={checkingApi}>
          <Text style={[styles.retryLink, checkingApi && styles.retryLinkDisabled]}>
            Retry
          </Text>
        </TouchableOpacity>
      </View>

      <View style={styles.content}>
        <TouchableOpacity
          style={[styles.mainButton, !apiConnected && styles.mainButtonDisabled]}
          onPress={() => router.push('/(tabs)/record')}
          disabled={!apiConnected}
        >
          <Text style={styles.mainButtonText}>📹 Record Session</Text>
        </TouchableOpacity>

        <View style={styles.infoBox}>
          <Text style={styles.infoText}>
            Get instant AI feedback on your shooting form
          </Text>
        </View>

        <View style={styles.featuresContainer}>
          <Text style={styles.featuresTitle}>What we analyze:</Text>
          <Text style={styles.featureItem}>✓ Elbow angle & release</Text>
          <Text style={styles.featureItem}>✓ Wrist position</Text>
          <Text style={styles.featureItem}>✓ Knee bend & power</Text>
          <Text style={styles.featureItem}>✓ Overall form rating</Text>
        </View>

        {/* Quick Stats */}
        {profile && (profile.total_sessions > 0 || profile.total_shots > 0) && (
          <View style={styles.statsContainer}>
            <Text style={styles.statsTitle}>Your Stats</Text>
            <View style={styles.statsRow}>
              <View style={styles.statItem}>
                <Text style={styles.statValue}>{profile.total_sessions}</Text>
                <Text style={styles.statLabel}>Sessions</Text>
              </View>
              <View style={styles.statItem}>
                <Text style={styles.statValue}>{profile.total_shots}</Text>
                <Text style={styles.statLabel}>Shots</Text>
              </View>
              <View style={styles.statItem}>
                <Text style={styles.statValue}>
                  {profile.total_shots > 0 
                    ? Math.round((profile.total_makes / profile.total_shots) * 100) 
                    : 0}%
                </Text>
                <Text style={styles.statLabel}>Accuracy</Text>
              </View>
            </View>
          </View>
        )}
      </View>

      <View style={styles.footer}>
        <TouchableOpacity onPress={() => router.push('/(tabs)/profile')}>
          <Text style={styles.footerLink}>Profile & Settings</Text>
        </TouchableOpacity>
        <Text style={styles.footerText}>MVP v1.0.0</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#000',
  },
  loadingText: {
    color: '#fff',
    marginTop: 10,
    fontSize: 16,
  },
  header: {
    paddingTop: 60,
    paddingBottom: 20,
    alignItems: 'center',
  },
  title: {
    fontSize: 48,
    fontWeight: 'bold',
    color: '#ff6b00',
  },
  subtitle: {
    fontSize: 18,
    color: '#fff',
    marginTop: 5,
  },
  greeting: {
    fontSize: 14,
    color: '#aaa',
    marginTop: 10,
  },
  statusContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 15,
    gap: 10,
  },
  statusLabel: {
    fontSize: 14,
    color: '#aaa',
  },
  statusBadge: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 12,
  },
  statusBadgeLoading: {
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
  },
  statusBadgeConnected: {
    backgroundColor: 'rgba(0, 200, 0, 0.2)',
  },
  statusBadgeDisconnected: {
    backgroundColor: 'rgba(200, 0, 0, 0.2)',
  },
  statusText: {
    fontSize: 12,
    color: '#fff',
    fontWeight: 'bold',
  },
  retryLink: {
    fontSize: 12,
    color: '#ff6b00',
    textDecorationLine: 'underline',
  },
  retryLinkDisabled: {
    opacity: 0.5,
  },
  content: {
    flex: 1,
    padding: 20,
    justifyContent: 'center',
  },
  mainButton: {
    backgroundColor: '#ff6b00',
    paddingVertical: 20,
    borderRadius: 15,
    alignItems: 'center',
    marginBottom: 30,
  },
  mainButtonDisabled: {
    backgroundColor: '#333',
    opacity: 0.5,
  },
  mainButtonText: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
  },
  infoBox: {
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    padding: 20,
    borderRadius: 10,
    marginBottom: 30,
  },
  infoText: {
    fontSize: 16,
    color: '#ddd',
    textAlign: 'center',
  },
  featuresContainer: {
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    padding: 20,
    borderRadius: 10,
    marginBottom: 20,
  },
  featuresTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 15,
  },
  featureItem: {
    fontSize: 16,
    color: '#ddd',
    marginBottom: 8,
  },
  statsContainer: {
    backgroundColor: 'rgba(255, 107, 0, 0.1)',
    padding: 20,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#ff6b00',
  },
  statsTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#ff6b00',
    marginBottom: 15,
    textAlign: 'center',
  },
  statsRow: {
    flexDirection: 'row',
    justifyContent: 'space-around',
  },
  statItem: {
    alignItems: 'center',
  },
  statValue: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
  },
  statLabel: {
    fontSize: 12,
    color: '#aaa',
    marginTop: 4,
  },
  footer: {
    padding: 20,
    alignItems: 'center',
    gap: 10,
  },
  footerLink: {
    fontSize: 14,
    color: '#ff6b00',
    textDecorationLine: 'underline',
  },
  footerText: {
    fontSize: 12,
    color: '#666',
  },
});