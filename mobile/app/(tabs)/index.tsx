/**
 * Home Screen (Tab)
 * Main dashboard with stats, quick actions, and API status
 */

import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Alert, ActivityIndicator, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useAuth } from '../../contexts/AuthContext';
import { testConnection } from '../../lib/api';

export default function HomeScreen() {
  const router = useRouter();
  const { profile } = useAuth();
  const [apiConnected, setApiConnected] = useState<boolean | null>(null);
  const [checkingApi, setCheckingApi] = useState(true);

  // Check API connection on mount
  useEffect(() => {
    checkApiConnection();
  }, []);

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

  return (
    <SafeAreaView style={styles.safeArea} edges={['top']}>
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>🏀 FormCheck</Text>
          <Text style={styles.subtitle}>Your AI Basketball Coach</Text>
          {profile?.full_name && (
            <Text style={styles.greeting}>Welcome back, {profile.full_name}!</Text>
          )}
        </View>

        {/* API Status */}
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

        {/* Main Action Button */}
        <TouchableOpacity
          style={[styles.mainButton, !apiConnected && styles.mainButtonDisabled]}
          onPress={() => router.push('/record')}
          disabled={!apiConnected}
        >
          <Text style={styles.mainButtonText}>🎥 Start Recording</Text>
        </TouchableOpacity>

        {/* Features Info */}
        <View style={styles.infoBox}>
          <Text style={styles.infoTitle}>What we analyze:</Text>
          <Text style={styles.featureItem}>✓ Elbow angle & release</Text>
          <Text style={styles.featureItem}>✓ Wrist position</Text>
          <Text style={styles.featureItem}>✓ Knee bend & power</Text>
          <Text style={styles.featureItem}>✓ Overall form rating</Text>
        </View>

        {/* Quick Actions */}
        <View style={styles.quickActions}>
          <TouchableOpacity
            style={styles.quickActionButton}
            onPress={() => router.push('/history')}
          >
            <Text style={styles.quickActionEmoji}>📊</Text>
            <Text style={styles.quickActionText}>View History</Text>
          </TouchableOpacity>
          
          <TouchableOpacity
            style={styles.quickActionButton}
            onPress={() => router.push('/profile')}
          >
            <Text style={styles.quickActionEmoji}>👤</Text>
            <Text style={styles.quickActionText}>My Profile</Text>
          </TouchableOpacity>
        </View>

        {/* Tips Section */}
        <View style={styles.tipsBox}>
          <Text style={styles.tipsTitle}>💡 Pro Tips</Text>
          <Text style={styles.tipText}>• Record with full body visible</Text>
          <Text style={styles.tipText}>• Good lighting helps accuracy</Text>
          <Text style={styles.tipText}>• Take multiple shots in one video</Text>
          <Text style={styles.tipText}>• Practice consistently for best results</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#000',
  },
  container: {
    flex: 1,
  },
  content: {
    padding: 20,
    paddingBottom: 40,
  },
  header: {
    alignItems: 'center',
    marginBottom: 20,
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
    marginBottom: 20,
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
  statsContainer: {
    backgroundColor: 'rgba(255, 107, 0, 0.1)',
    padding: 20,
    borderRadius: 15,
    borderWidth: 1,
    borderColor: '#ff6b00',
    marginBottom: 20,
  },
  statsTitle: {
    fontSize: 18,
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
    fontSize: 28,
    fontWeight: 'bold',
    color: '#fff',
  },
  statLabel: {
    fontSize: 12,
    color: '#aaa',
    marginTop: 4,
  },
  mainButton: {
    backgroundColor: '#ff6b00',
    paddingVertical: 20,
    borderRadius: 15,
    alignItems: 'center',
    marginBottom: 20,
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
    borderRadius: 15,
    marginBottom: 20,
  },
  infoTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 12,
  },
  featureItem: {
    fontSize: 15,
    color: '#ddd',
    marginBottom: 8,
  },
  quickActions: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 20,
  },
  quickActionButton: {
    flex: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    padding: 15,
    borderRadius: 15,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
  },
  quickActionEmoji: {
    fontSize: 32,
    marginBottom: 8,
  },
  quickActionText: {
    fontSize: 14,
    color: '#fff',
    fontWeight: '600',
  },
  tipsBox: {
    backgroundColor: 'rgba(255, 107, 0, 0.05)',
    padding: 20,
    borderRadius: 15,
    borderWidth: 1,
    borderColor: 'rgba(255, 107, 0, 0.3)',
  },
  tipsTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#ff6b00',
    marginBottom: 12,
  },
  tipText: {
    fontSize: 14,
    color: '#ddd',
    marginBottom: 6,
    lineHeight: 20,
  },
});