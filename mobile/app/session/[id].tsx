/**
 * Session Detail Screen
 * Shows session summary, AI feedback, drill suggestions, and individual shot cards
 */

import React, { useState, useEffect, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Image,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { db, type Session, type Shot } from '../../lib/supabase';
import { useFingerprint } from '../../contexts/FingerprintContext';
import { compareShotToSignature, getTopDeviations, type MetricDeviation } from '../../lib/fingerprint-utils';
import { ErrorBoundary } from '../../components/ErrorBoundary';

function SessionDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [shots, setShots] = useState<Shot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { fingerprint, isReady } = useFingerprint();

  // Session-level deviation comparison: average all shot metrics, compare to make signature
  const sessionDeviations = useMemo(() => {
    if (!isReady || !fingerprint?.make_signature || shots.length === 0) return [];

    // Average all shots' biomechanical metrics
    const metricKeys = Object.keys(fingerprint.make_signature);
    const avgMetrics: Record<string, any> = {};
    for (const key of metricKeys) {
      const values = shots.map(s => (s as any)[key]).filter((v: any) => v != null);
      if (values.length > 0) {
        avgMetrics[key] = values.reduce((a: number, b: number) => a + b, 0) / values.length;
      }
    }

    return compareShotToSignature(avgMetrics, fingerprint.make_signature);
  }, [shots, fingerprint, isReady]);

  const topSessionDeviations = useMemo(() => getTopDeviations(sessionDeviations, 3), [sessionDeviations]);

  useEffect(() => {
    if (id) loadSessionData();
  }, [id]);

  const loadSessionData = async () => {
    try {
      setLoading(true);
      const [sessionData, shotsData] = await Promise.all([
        db.getSession(id!),
        db.getShots(id!),
      ]);
      setSession(sessionData);
      setShots(shotsData);
    } catch (err) {
      console.error('Error loading session:', err);
      setError('Could not load session details');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#FF4D00" />
        </View>
      </SafeAreaView>
    );
  }

  if (error || !session) {
    return (
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        <View style={styles.loadingContainer}>
          <Text style={styles.errorText}>{error || 'Session not found'}</Text>
          <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
            <Text style={styles.backButtonText}>Go Back</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const date = new Date(session.started_at);
  const formattedDate = date.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  });
  const formattedTime = date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  });

  const accuracy = session.shooting_percentage;

  const getAccuracyColor = (acc: number) => {
    if (acc >= 70) return '#10B981';
    if (acc >= 50) return '#F59E0B';
    return '#EF4444';
  };

  return (
    <SafeAreaView style={styles.safeArea} edges={['top']}>
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.headerBack}>
            <Ionicons name="chevron-back" size={24} color="#FFF" />
          </TouchableOpacity>
          <View style={styles.headerInfo}>
            <Text style={styles.headerTitle}>Session Detail</Text>
            <Text style={styles.headerDate}>{formattedDate} at {formattedTime}</Text>
          </View>
        </View>

        {/* Summary Card */}
        <View style={styles.summaryCard}>
          <View style={styles.summaryRow}>
            {/* Accuracy Ring */}
            <View style={styles.accuracyWrapper}>
              <View style={[styles.accuracyRing, { borderColor: getAccuracyColor(accuracy) }]}>
                <Text style={styles.accuracyNumber}>{accuracy.toFixed(0)}</Text>
                <Text style={styles.accuracyPercent}>%</Text>
              </View>
              <Text style={styles.accuracyLabel}>ACCURACY</Text>
            </View>

            {/* Stats Grid */}
            <View style={styles.statsGrid}>
              <View style={styles.statItem}>
                <Text style={styles.statValue}>{session.shot_count}</Text>
                <Text style={styles.statLabel}>Shots</Text>
              </View>
              <View style={styles.statItem}>
                <Text style={[styles.statValue, { color: '#10B981' }]}>{session.make_count}</Text>
                <Text style={styles.statLabel}>Made</Text>
              </View>
              <View style={styles.statItem}>
                <Text style={[styles.statValue, { color: '#EF4444' }]}>{session.miss_count}</Text>
                <Text style={styles.statLabel}>Missed</Text>
              </View>
              <View style={styles.statItem}>
                <Text style={styles.statValue}>
                  {session.average_form_rating ? session.average_form_rating.toFixed(1) : '--'}
                </Text>
                <Text style={styles.statLabel}>Form</Text>
              </View>
            </View>
          </View>
        </View>

        {/* vs. Your Best Form (fingerprint comparison) */}
        {topSessionDeviations.length > 0 && (
          <View style={styles.comparisonCard}>
            <Text style={styles.comparisonTitle}>vs. Your Best Form</Text>
            {topSessionDeviations.map((dev, i) => (
              <View key={i} style={styles.deviationRow}>
                <View style={[
                  styles.deviationIndicator,
                  { backgroundColor: dev.severity === 'significant' ? '#EF4444' : '#F59E0B' },
                ]} />
                <View style={styles.deviationInfo}>
                  <Text style={styles.deviationLabel}>{dev.label}</Text>
                  <Text style={styles.deviationCue}>{dev.cue}</Text>
                </View>
              </View>
            ))}
          </View>
        )}

        {/* Session Feedback */}
        {session.session_feedback && (
          <View style={styles.feedbackCard}>
            <Text style={styles.cardTitle}>Coach's Assessment</Text>
            <Text style={styles.feedbackText}>{session.session_feedback}</Text>
          </View>
        )}

        {/* Drill Suggestions */}
        {session.drill_suggestions && session.drill_suggestions.length > 0 && (
          <View style={styles.drillsCard}>
            <Text style={styles.cardTitle}>Recommended Drills</Text>
            {session.drill_suggestions.map((drill, index) => (
              <View key={index} style={styles.drillItem}>
                <View style={styles.drillNumber}>
                  <Text style={styles.drillNumberText}>{index + 1}</Text>
                </View>
                <Text style={styles.drillText}>{drill}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Shot List */}
        {shots.length > 0 && (
          <View style={styles.shotsSection}>
            <Text style={styles.sectionTitle}>All Shots ({shots.length})</Text>
            {shots.map((shot) => (
              <ShotCard key={shot.id} shot={shot} fingerprint={fingerprint} isReady={isReady} />
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

export default function SessionDetailWithBoundary() {
  return (
    <ErrorBoundary screenName="Session Detail">
      <SessionDetailScreen />
    </ErrorBoundary>
  );
}

function ShotCard({ shot, fingerprint, isReady }: { shot: Shot; fingerprint: any; isReady: boolean }) {
  const shotDeviations = useMemo(() => {
    if (!isReady || !fingerprint?.make_signature) return [];
    return getTopDeviations(compareShotToSignature(shot as any, fingerprint.make_signature), 2);
  }, [shot, fingerprint, isReady]);

  const getMadeBadge = () => {
    if (shot.made === true) return { text: 'MADE', color: '#10B981' };
    if (shot.made === false) return { text: 'MISS', color: '#EF4444' };
    return { text: 'N/A', color: '#666' };
  };

  const badge = getMadeBadge();

  return (
    <View style={styles.shotCard}>
      <View style={styles.shotHeader}>
        {/* Thumbnail */}
        <View style={styles.shotThumbnailContainer}>
          {shot.thumbnail_url ? (
            <Image source={{ uri: shot.thumbnail_url }} style={styles.shotThumbnail} />
          ) : (
            <View style={styles.shotThumbnailFallback}>
              <Ionicons name="basketball-outline" size={24} color="#FF4D00" />
            </View>
          )}
        </View>

        {/* Shot Info */}
        <View style={styles.shotInfo}>
          <View style={styles.shotTitleRow}>
            <Text style={styles.shotTitle}>Shot {shot.shot_number}</Text>
            <View style={styles.shotBadges}>
              {shot.camera_angle && (
                <View style={styles.angleBadge}>
                  <Text style={styles.angleBadgeText}>{shot.camera_angle.toUpperCase()}</Text>
                </View>
              )}
              <View style={[styles.madeBadge, { backgroundColor: badge.color }]}>
                <Text style={styles.madeBadgeText}>{badge.text}</Text>
              </View>
            </View>
          </View>
          {shot.form_rating != null && (
            <View style={styles.ratingRow}>
              <Text style={styles.ratingLabel}>Form:</Text>
              <Text style={styles.ratingValue}>{shot.form_rating}/10</Text>
              <View style={styles.ratingBar}>
                <View
                  style={[
                    styles.ratingFill,
                    { width: `${shot.form_rating * 10}%` },
                    shot.form_rating >= 7
                      ? { backgroundColor: '#10B981' }
                      : shot.form_rating >= 5
                      ? { backgroundColor: '#F59E0B' }
                      : { backgroundColor: '#EF4444' },
                  ]}
                />
              </View>
            </View>
          )}
        </View>
      </View>

      {/* Feedback */}
      {shot.feedback && (
        <Text style={styles.shotFeedback}>{shot.feedback}</Text>
      )}

      {/* Key Issue + Quick Cue */}
      {(shot.key_issue || shot.quick_cue) && (
        <View style={styles.shotTips}>
          {shot.key_issue && shot.key_issue !== 'none' && (
            <View style={styles.tipCard}>
              <Text style={styles.tipLabel}>Focus Area</Text>
              <Text style={styles.tipText}>{shot.key_issue}</Text>
            </View>
          )}
          {shot.quick_cue && (
            <View style={[styles.tipCard, styles.cueCard]}>
              <Text style={[styles.tipLabel, { color: '#10B981' }]}>Quick Cue</Text>
              <Text style={styles.tipText}>"{shot.quick_cue}"</Text>
            </View>
          )}
        </View>
      )}

      {/* Per-shot deviation from make signature */}
      {shotDeviations.length > 0 && (
        <View style={styles.shotDeviations}>
          <Text style={styles.shotDeviationsLabel}>VS. YOUR BEST</Text>
          {shotDeviations.map((dev, i) => (
            <View key={i} style={styles.shotDeviationRow}>
              <View style={[
                styles.shotDeviationDot,
                { backgroundColor: dev.severity === 'significant' ? '#EF4444' : '#F59E0B' },
              ]} />
              <Text style={styles.shotDeviationText}>{dev.label}: {dev.cue}</Text>
            </View>
          ))}
        </View>
      )}

    </View>
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
    paddingBottom: 40,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  errorText: {
    color: '#EF4444',
    fontSize: 16,
    marginBottom: 20,
  },
  backButton: {
    backgroundColor: '#FF4D00',
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 100,
  },
  backButtonText: {
    color: '#FFF',
    fontWeight: '700',
    fontSize: 15,
  },

  // Header
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 20,
    paddingBottom: 16,
  },
  headerBack: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#1A1A1A',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  headerInfo: {
    flex: 1,
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: '700',
    color: '#FFF',
    letterSpacing: -0.5,
  },
  headerDate: {
    fontSize: 14,
    color: '#666',
    marginTop: 2,
  },

  // Summary Card
  summaryCard: {
    marginHorizontal: 20,
    marginBottom: 16,
    backgroundColor: '#121212',
    borderRadius: 16,
    padding: 20,
    borderWidth: 2,
    borderColor: '#FF4D00',
  },
  summaryRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  accuracyWrapper: {
    alignItems: 'center',
    marginRight: 24,
  },
  accuracyRing: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#1A1A1A',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
  },
  accuracyNumber: {
    fontSize: 26,
    fontWeight: '800',
    color: '#FFF',
  },
  accuracyPercent: {
    fontSize: 12,
    fontWeight: '700',
    color: '#888',
    marginTop: -4,
  },
  accuracyLabel: {
    fontSize: 10,
    color: '#666',
    fontWeight: '600',
    letterSpacing: 0.5,
    marginTop: 8,
  },
  statsGrid: {
    flex: 1,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  statItem: {
    width: '45%',
    alignItems: 'center',
  },
  statValue: {
    fontSize: 22,
    fontWeight: '700',
    color: '#FFF',
    letterSpacing: -0.5,
  },
  statLabel: {
    fontSize: 11,
    color: '#666',
    fontWeight: '600',
    letterSpacing: 0.5,
  },

  // Feedback Card
  feedbackCard: {
    marginHorizontal: 20,
    marginBottom: 16,
    backgroundColor: '#121212',
    borderRadius: 16,
    padding: 20,
    borderWidth: 1,
    borderColor: '#2A2A2A',
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#FF4D00',
    marginBottom: 12,
  },
  feedbackText: {
    fontSize: 15,
    color: '#CCC',
    lineHeight: 22,
  },

  // Drills Card
  drillsCard: {
    marginHorizontal: 20,
    marginBottom: 16,
    backgroundColor: '#121212',
    borderRadius: 16,
    padding: 20,
    borderWidth: 1,
    borderColor: '#2A2A2A',
  },
  drillItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  drillNumber: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: '#FF4D00',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
    marginTop: 1,
  },
  drillNumberText: {
    color: '#FFF',
    fontSize: 12,
    fontWeight: '700',
  },
  drillText: {
    flex: 1,
    fontSize: 14,
    color: '#CCC',
    lineHeight: 20,
  },

  // Shots Section
  shotsSection: {
    paddingHorizontal: 20,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#FFF',
    marginBottom: 16,
    letterSpacing: -0.3,
  },

  // Shot Card
  shotCard: {
    backgroundColor: '#121212',
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#2A2A2A',
    ...Platform.select({
      ios: {
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.2,
        shadowRadius: 4,
      },
      android: {
        elevation: 3,
      },
    }),
  },
  shotHeader: {
    flexDirection: 'row',
    marginBottom: 12,
  },
  shotThumbnailContainer: {
    marginRight: 12,
  },
  shotThumbnail: {
    width: 64,
    height: 85,
    borderRadius: 8,
    backgroundColor: '#1A1A1A',
  },
  shotThumbnailFallback: {
    width: 64,
    height: 85,
    borderRadius: 8,
    backgroundColor: '#1A1A1A',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#2A2A2A',
  },
  shotInfo: {
    flex: 1,
    justifyContent: 'center',
  },
  shotTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  shotTitle: {
    fontSize: 17,
    fontWeight: '700',
    color: '#FFF',
  },
  shotBadges: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  angleBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 8,
    backgroundColor: '#333',
    borderWidth: 1,
    borderColor: '#555',
  },
  angleBadgeText: {
    fontSize: 10,
    fontWeight: '600',
    color: '#AAA',
    letterSpacing: 0.5,
  },
  madeBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 10,
  },
  madeBadgeText: {
    fontSize: 11,
    fontWeight: '700',
    color: '#FFF',
    letterSpacing: 0.5,
  },
  ratingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  ratingLabel: {
    fontSize: 12,
    color: '#666',
    fontWeight: '600',
  },
  ratingValue: {
    fontSize: 13,
    color: '#FF4D00',
    fontWeight: '700',
  },
  ratingBar: {
    flex: 1,
    height: 4,
    backgroundColor: '#2A2A2A',
    borderRadius: 2,
    overflow: 'hidden',
  },
  ratingFill: {
    height: '100%',
    borderRadius: 2,
  },

  // Shot Feedback
  shotFeedback: {
    fontSize: 13,
    color: '#AAA',
    lineHeight: 19,
    marginBottom: 10,
  },

  // Tips
  shotTips: {
    gap: 8,
    marginBottom: 10,
  },
  tipCard: {
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
    padding: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(239, 68, 68, 0.2)',
  },
  cueCard: {
    backgroundColor: 'rgba(16, 185, 129, 0.1)',
    borderColor: 'rgba(16, 185, 129, 0.2)',
  },
  tipLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: '#EF4444',
    letterSpacing: 0.3,
    marginBottom: 4,
  },
  tipText: {
    fontSize: 13,
    color: '#CCC',
    lineHeight: 18,
  },

  // Comparison Card (session-level)
  comparisonCard: {
    marginHorizontal: 20,
    marginBottom: 16,
    backgroundColor: '#121212',
    borderRadius: 16,
    padding: 20,
    borderWidth: 1,
    borderColor: 'rgba(255, 77, 0, 0.3)',
  },
  comparisonTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#FF4D00',
    marginBottom: 14,
    letterSpacing: 0.3,
  },
  deviationRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 12,
    gap: 10,
  },
  deviationIndicator: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginTop: 6,
  },
  deviationInfo: {
    flex: 1,
  },
  deviationLabel: {
    fontSize: 12,
    fontWeight: '700',
    color: '#AAA',
    marginBottom: 2,
  },
  deviationCue: {
    fontSize: 14,
    color: '#FFF',
    fontWeight: '600',
    lineHeight: 20,
  },

  // Per-shot deviation
  shotDeviations: {
    backgroundColor: 'rgba(255, 77, 0, 0.06)',
    borderRadius: 8,
    padding: 10,
    borderWidth: 1,
    borderColor: 'rgba(255, 77, 0, 0.15)',
  },
  shotDeviationsLabel: {
    fontSize: 10,
    fontWeight: '700',
    color: '#FF4D00',
    letterSpacing: 0.5,
    marginBottom: 6,
  },
  shotDeviationRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 4,
  },
  shotDeviationDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
  },
  shotDeviationText: {
    flex: 1,
    fontSize: 12,
    color: '#CCC',
  },

});
