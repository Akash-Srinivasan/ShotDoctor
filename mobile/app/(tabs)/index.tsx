/**
 * Home Screen — Personal Coaching Hub
 * Shows fingerprint-driven insights, trends, and coaching cues.
 */

import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../contexts/AuthContext';
import { useFingerprint } from '../../contexts/FingerprintContext';
import { ErrorBoundary } from '../../components/ErrorBoundary';
import { generateGreeting } from '../../lib/fingerprint-utils';
import { testConnection } from '../../lib/api';
import { db, type Session } from '../../lib/supabase';

function HomeScreen() {
  const router = useRouter();
  const { user, profile } = useAuth();
  const { fingerprint, loading: fpLoading, isReady, sessionsUntilReady, refreshFingerprint } = useFingerprint();
  const [apiConnected, setApiConnected] = useState<boolean | null>(null);
  const [checkingApi, setCheckingApi] = useState(true);
  const [lastSession, setLastSession] = useState<Session | null>(null);

  // Refresh data every time the home tab is focused
  useFocusEffect(
    useCallback(() => {
      checkApiConnection();
      loadLastSession();
      refreshFingerprint();
    }, [user?.id])
  );

  const checkApiConnection = async () => {
    setCheckingApi(true);
    try {
      const connected = await testConnection();
      setApiConnected(connected);
    } catch {
      setApiConnected(false);
    } finally {
      setCheckingApi(false);
    }
  };

  const loadLastSession = async () => {
    if (!user) return;
    try {
      const sessions = await db.getSessions(1);
      setLastSession(sessions.length > 0 ? sessions[0] : null);
    } catch {
      // ignore
    }
  };

  const greeting = generateGreeting(profile, fingerprint);

  return (
    <SafeAreaView style={styles.safeArea} edges={['top']}>
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        {/* Greeting */}
        <View style={styles.header}>
          <Text style={styles.greeting}>{greeting}</Text>
          {isReady && fingerprint?.trend_label && (
            <View style={styles.trendPill}>
              <Ionicons
                name={
                  fingerprint.trend_label === 'Improving' ? 'trending-up' :
                  fingerprint.trend_label === 'Off lately' ? 'trending-down' :
                  'remove-outline'
                }
                size={14}
                color={
                  fingerprint.trend_label === 'Improving' ? '#10B981' :
                  fingerprint.trend_label === 'Off lately' ? '#EF4444' :
                  '#888'
                }
              />
              <Text style={[
                styles.trendText,
                {
                  color: fingerprint.trend_label === 'Improving' ? '#10B981' :
                         fingerprint.trend_label === 'Off lately' ? '#EF4444' : '#888'
                }
              ]}>
                {fingerprint.trend_label}
              </Text>
            </View>
          )}
        </View>

        {/* ============================================================ */}
        {/* Fingerprint Ready: Focus Cues + Miss Tendency                */}
        {/* ============================================================ */}
        {isReady && fingerprint ? (
          <>
            {/* Today's Focus */}
            {fingerprint.cues.length > 0 && (
              <View style={styles.section}>
                <Text style={styles.sectionLabel}>TODAY'S FOCUS</Text>
                {fingerprint.cues.slice(0, 3).map((cue, i) => (
                  <View key={i} style={styles.cueCard}>
                    <View style={styles.cueNumber}>
                      <Text style={styles.cueNumberText}>{i + 1}</Text>
                    </View>
                    <Text style={styles.cueText}>{cue}</Text>
                  </View>
                ))}
              </View>
            )}

            {/* Miss Tendency */}
            {fingerprint.miss_tendency_cue ? (
              <View style={styles.missTendencyCard}>
                <Ionicons name="analytics-outline" size={16} color="#F59E0B" />
                <Text style={styles.missTendencyText}>{fingerprint.miss_tendency_cue}</Text>
              </View>
            ) : null}

            {/* Consistency note */}
            {fingerprint.consistency_note ? (
              <View style={styles.consistencyCard}>
                <Ionicons name="repeat-outline" size={14} color="#888" />
                <Text style={styles.consistencyText}>{fingerprint.consistency_note}</Text>
              </View>
            ) : null}
          </>
        ) : (
          /* ============================================================ */
          /* Pre-fingerprint: Progress card                               */
          /* ============================================================ */
          <View style={styles.progressCard}>
            {fpLoading ? (
              <ActivityIndicator size="small" color="#FF4D00" />
            ) : sessionsUntilReady > 0 ? (
              <>
                <Ionicons name="basketball-outline" size={32} color="#FF4D00" />
                <Text style={styles.progressTitle}>
                  {sessionsUntilReady === 3
                    ? 'Start building your shot profile'
                    : `${sessionsUntilReady} more session${sessionsUntilReady > 1 ? 's' : ''} to unlock coaching insights`}
                </Text>
                <View style={styles.progressBar}>
                  <View style={[styles.progressFill, { width: `${((3 - sessionsUntilReady) / 3) * 100}%` }]} />
                </View>
                <Text style={styles.progressSubtext}>
                  We learn your unique shooting signature after 3 sessions
                </Text>
              </>
            ) : (
              <>
                <Ionicons name="basketball-outline" size={32} color="#FF4D00" />
                <Text style={styles.progressTitle}>Record your first session</Text>
                <Text style={styles.progressSubtext}>
                  Get AI coaching feedback on every shot
                </Text>
              </>
            )}
          </View>
        )}

        {/* Start Recording CTA */}
        <TouchableOpacity
          style={[styles.ctaButton, !apiConnected && styles.ctaButtonDisabled]}
          onPress={() => router.push('/(tabs)/record')}
          disabled={!apiConnected}
          activeOpacity={0.8}
        >
          <Ionicons name="videocam" size={22} color="#FFF" />
          <Text style={styles.ctaText}>Start Recording</Text>
        </TouchableOpacity>

        {/* Last Session */}
        {lastSession && (
          <TouchableOpacity
            style={styles.lastSessionCard}
            activeOpacity={0.8}
            onPress={() => router.push(`/session/${lastSession.id}`)}
          >
            <View style={styles.lastSessionHeader}>
              <Text style={styles.lastSessionLabel}>LAST SESSION</Text>
              <Ionicons name="chevron-forward" size={16} color="#666" />
            </View>
            <View style={styles.lastSessionStats}>
              <View style={styles.lastSessionStat}>
                <Text style={styles.lastSessionValue}>
                  {lastSession.shooting_percentage.toFixed(0)}%
                </Text>
                <Text style={styles.lastSessionStatLabel}>Accuracy</Text>
              </View>
              <View style={styles.lastSessionDivider} />
              <View style={styles.lastSessionStat}>
                <Text style={styles.lastSessionValue}>{lastSession.shot_count}</Text>
                <Text style={styles.lastSessionStatLabel}>Shots</Text>
              </View>
              <View style={styles.lastSessionDivider} />
              <View style={styles.lastSessionStat}>
                <Text style={styles.lastSessionValue}>
                  {lastSession.average_form_rating ? lastSession.average_form_rating.toFixed(1) : '--'}
                </Text>
                <Text style={styles.lastSessionStatLabel}>Form</Text>
              </View>
            </View>
          </TouchableOpacity>
        )}

        {/* Quick Stats */}
        {profile && profile.total_sessions > 0 && (
          <View style={styles.quickStats}>
            <View style={styles.quickStat}>
              <Text style={styles.quickStatValue}>{profile.total_sessions}</Text>
              <Text style={styles.quickStatLabel}>SESSIONS</Text>
            </View>
            <View style={styles.quickStatDivider} />
            <View style={styles.quickStat}>
              <Text style={styles.quickStatValue}>{profile.total_shots}</Text>
              <Text style={styles.quickStatLabel}>SHOTS</Text>
            </View>
            <View style={styles.quickStatDivider} />
            <View style={styles.quickStat}>
              <Text style={styles.quickStatValue}>
                {profile.total_shots > 0
                  ? `${Math.round((profile.total_makes / profile.total_shots) * 100)}%`
                  : '0%'}
              </Text>
              <Text style={styles.quickStatLabel}>ACCURACY</Text>
            </View>
          </View>
        )}

        {/* API Status (small) */}
        <View style={styles.apiStatus}>
          <View style={[
            styles.apiDot,
            checkingApi && { backgroundColor: '#666' },
            apiConnected === true && { backgroundColor: '#10B981' },
            apiConnected === false && { backgroundColor: '#EF4444' },
          ]} />
          <Text style={styles.apiText}>
            {checkingApi ? 'Checking API...' : apiConnected ? 'API Connected' : 'API Disconnected'}
          </Text>
          {apiConnected === false && (
            <TouchableOpacity onPress={checkApiConnection}>
              <Text style={styles.apiRetry}>Retry</Text>
            </TouchableOpacity>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

export default function HomeScreenWithBoundary() {
  return (
    <ErrorBoundary screenName="Home">
      <HomeScreen />
    </ErrorBoundary>
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
    padding: 24,
    paddingBottom: 40,
  },

  // Header / Greeting
  header: {
    marginBottom: 24,
  },
  greeting: {
    fontSize: 28,
    fontWeight: '700',
    color: '#FFF',
    letterSpacing: -0.5,
    marginBottom: 8,
  },
  trendPill: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 6,
    backgroundColor: '#121212',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 100,
    borderWidth: 1,
    borderColor: '#1E1E1E',
  },
  trendText: {
    fontSize: 13,
    fontWeight: '600',
  },

  // Sections
  section: {
    marginBottom: 16,
  },
  sectionLabel: {
    fontSize: 11,
    color: '#666',
    fontWeight: '600',
    letterSpacing: 0.5,
    marginBottom: 10,
  },

  // Cue Cards
  cueCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#121212',
    borderRadius: 12,
    padding: 16,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#1E1E1E',
    gap: 12,
  },
  cueNumber: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: '#FF4D00',
    alignItems: 'center',
    justifyContent: 'center',
  },
  cueNumberText: {
    color: '#FFF',
    fontSize: 12,
    fontWeight: '700',
  },
  cueText: {
    flex: 1,
    fontSize: 15,
    color: '#FFF',
    fontWeight: '600',
  },

  // Miss Tendency
  missTendencyCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(245, 158, 11, 0.1)',
    borderRadius: 12,
    padding: 14,
    gap: 10,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: 'rgba(245, 158, 11, 0.2)',
  },
  missTendencyText: {
    flex: 1,
    fontSize: 14,
    color: '#F59E0B',
    fontWeight: '600',
  },

  // Consistency
  consistencyCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#121212',
    borderRadius: 12,
    padding: 14,
    gap: 8,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#1E1E1E',
  },
  consistencyText: {
    flex: 1,
    fontSize: 13,
    color: '#AAA',
    fontWeight: '600',
  },

  // Progress Card (pre-fingerprint)
  progressCard: {
    backgroundColor: '#121212',
    borderRadius: 12,
    padding: 28,
    alignItems: 'center',
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#1E1E1E',
    gap: 10,
  },
  progressTitle: {
    fontSize: 17,
    fontWeight: '700',
    color: '#FFF',
    textAlign: 'center',
  },
  progressBar: {
    width: '80%',
    height: 6,
    backgroundColor: '#2A2A2A',
    borderRadius: 3,
    overflow: 'hidden',
    marginVertical: 4,
  },
  progressFill: {
    height: '100%',
    backgroundColor: '#FF4D00',
    borderRadius: 3,
  },
  progressSubtext: {
    fontSize: 13,
    color: '#666',
    textAlign: 'center',
  },

  // CTA Button
  ctaButton: {
    backgroundColor: '#FF4D00',
    borderRadius: 100,
    paddingVertical: 18,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    marginBottom: 20,
  },
  ctaButtonDisabled: {
    backgroundColor: '#333',
    opacity: 0.5,
  },
  ctaText: {
    fontSize: 17,
    fontWeight: '700',
    color: '#FFF',
  },

  // Last Session
  lastSessionCard: {
    backgroundColor: '#121212',
    borderRadius: 12,
    padding: 20,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#1E1E1E',
  },
  lastSessionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  lastSessionLabel: {
    fontSize: 11,
    color: '#666',
    fontWeight: '600',
    letterSpacing: 0.5,
  },
  lastSessionStats: {
    flexDirection: 'row',
  },
  lastSessionStat: {
    flex: 1,
    alignItems: 'center',
  },
  lastSessionValue: {
    fontSize: 24,
    fontWeight: '700',
    color: '#FFF',
    marginBottom: 4,
    letterSpacing: -0.5,
  },
  lastSessionStatLabel: {
    fontSize: 11,
    color: '#666',
    fontWeight: '600',
  },
  lastSessionDivider: {
    width: 1,
    backgroundColor: '#1E1E1E',
  },

  // Quick Stats
  quickStats: {
    flexDirection: 'row',
    backgroundColor: '#121212',
    borderRadius: 12,
    padding: 20,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#1E1E1E',
  },
  quickStat: {
    flex: 1,
    alignItems: 'center',
  },
  quickStatValue: {
    fontSize: 22,
    fontWeight: '700',
    color: '#FFF',
    marginBottom: 4,
    letterSpacing: -0.5,
  },
  quickStatLabel: {
    fontSize: 10,
    color: '#666',
    fontWeight: '600',
    letterSpacing: 0.5,
  },
  quickStatDivider: {
    width: 1,
    backgroundColor: '#1E1E1E',
  },

  // API Status
  apiStatus: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingTop: 8,
  },
  apiDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#666',
  },
  apiText: {
    fontSize: 12,
    color: '#666',
  },
  apiRetry: {
    fontSize: 12,
    color: '#FF4D00',
    fontWeight: '600',
  },
});
