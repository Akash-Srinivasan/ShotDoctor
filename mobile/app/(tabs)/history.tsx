/**
 * History Screen - Peloton Style
 * Clean session list with bold numbers and minimal design
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../contexts/AuthContext';
import { db, type Session } from '../../lib/supabase';

type SortOption = 'recent' | 'accuracy' | 'shots';

export default function HistoryScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [sortBy, setSortBy] = useState<SortOption>('recent');

  useEffect(() => {
    loadSessions();
  }, []);

  const loadSessions = async () => {
    if (!user) return;

    try {
      setLoading(true);
      const allSessions = await db.getSessions(50);
      setSessions(allSessions);
    } catch (error) {
      console.error('Error loading sessions:', error);
      Alert.alert('Error', 'Could not load session history');
    } finally {
      setLoading(false);
    }
  };

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await loadSessions();
    setRefreshing(false);
  }, []);

  // Sort sessions
  const getSortedSessions = () => {
    return [...sessions].sort((a, b) => {
      switch (sortBy) {
        case 'recent':
          return new Date(b.started_at).getTime() - new Date(a.started_at).getTime();
        case 'accuracy':
          return b.shooting_percentage - a.shooting_percentage;
        case 'shots':
          return b.shot_count - a.shot_count;
        default:
          return 0;
      }
    });
  };

  const displayedSessions = getSortedSessions();

  // Calculate summary
  const totalShots = sessions.reduce((sum, s) => sum + s.shot_count, 0);
  const totalMakes = sessions.reduce((sum, s) => sum + s.make_count, 0);
  const avgAccuracy = totalShots > 0 ? (totalMakes / totalShots) * 100 : 0;

  if (loading) {
    return (
      <SafeAreaView style={styles.safeArea} edges={['top']}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#FF4D00" />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea} edges={['top']}>
      <View style={styles.container}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>History</Text>
          <Text style={styles.subtitle}>{sessions.length} sessions</Text>
        </View>

        {/* Summary Stats */}
        {sessions.length > 0 && (
          <View style={styles.summaryContainer}>
            <View style={styles.summaryCard}>
              <Text style={styles.summaryNumber}>{totalShots}</Text>
              <Text style={styles.summaryLabel}>TOTAL SHOTS</Text>
            </View>
            <View style={styles.summarySeparator} />
            <View style={styles.summaryCard}>
              <Text style={styles.summaryNumber}>{avgAccuracy.toFixed(0)}%</Text>
              <Text style={styles.summaryLabel}>ACCURACY</Text>
            </View>
          </View>
        )}

        {/* Sort Tabs */}
        <View style={styles.sortContainer}>
          <TouchableOpacity
            style={[styles.sortTab, sortBy === 'recent' && styles.sortTabActive]}
            onPress={() => setSortBy('recent')}
          >
            <Text style={[styles.sortText, sortBy === 'recent' && styles.sortTextActive]}>
              Recent
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.sortTab, sortBy === 'accuracy' && styles.sortTabActive]}
            onPress={() => setSortBy('accuracy')}
          >
            <Text style={[styles.sortText, sortBy === 'accuracy' && styles.sortTextActive]}>
              Best %
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.sortTab, sortBy === 'shots' && styles.sortTabActive]}
            onPress={() => setSortBy('shots')}
          >
            <Text style={[styles.sortText, sortBy === 'shots' && styles.sortTextActive]}>
              Most Shots
            </Text>
          </TouchableOpacity>
        </View>

        {/* Sessions List */}
        <ScrollView
          style={styles.sessionsList}
          contentContainerStyle={styles.sessionsListContent}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor="#FF4D00"
            />
          }
        >
          {displayedSessions.length === 0 ? (
            <View style={styles.emptyState}>
              <Ionicons name="bar-chart-outline" size={48} color="#333" style={styles.emptyIcon} />
              <Text style={styles.emptyTitle}>No Sessions Yet</Text>
              <Text style={styles.emptyText}>
                Start recording to see your session history
              </Text>
              <TouchableOpacity
                style={styles.emptyButton}
                onPress={() => router.push('/(tabs)/record')}
              >
                <Text style={styles.emptyButtonText}>Start First Session</Text>
              </TouchableOpacity>
            </View>
          ) : (
            displayedSessions.map((session) => (
              <SessionCard key={session.id} session={session} />
            ))
          )}
        </ScrollView>
      </View>
    </SafeAreaView>
  );
}

// Session Card Component
function SessionCard({ session }: { session: Session }) {
  const date = new Date(session.started_at);
  const formattedDate = date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });
  const formattedTime = date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  });

  const accuracy = session.shooting_percentage;

  return (
    <TouchableOpacity style={styles.sessionCard} activeOpacity={0.8}>
      <View style={styles.sessionHeader}>
        <View>
          <Text style={styles.sessionDate}>{formattedDate}</Text>
          <Text style={styles.sessionTime}>{formattedTime}</Text>
        </View>
        
        {/* Accuracy Circle */}
        <View style={styles.accuracyContainer}>
          <Text style={styles.accuracyNumber}>{accuracy.toFixed(0)}</Text>
          <Text style={styles.accuracyPercent}>%</Text>
        </View>
      </View>

      <View style={styles.sessionDivider} />

      <View style={styles.sessionStats}>
        <View style={styles.sessionStat}>
          <Text style={styles.sessionStatValue}>{session.shot_count}</Text>
          <Text style={styles.sessionStatLabel}>Shots</Text>
        </View>
        
        <View style={styles.sessionStatDivider} />
        
        <View style={styles.sessionStat}>
          <Text style={styles.sessionStatValue}>{session.make_count}</Text>
          <Text style={styles.sessionStatLabel}>Made</Text>
        </View>
        
        <View style={styles.sessionStatDivider} />
        
        <View style={styles.sessionStat}>
          <Text style={styles.sessionStatValue}>
            {session.average_form_rating ? session.average_form_rating.toFixed(1) : '--'}
          </Text>
          <Text style={styles.sessionStatLabel}>Form</Text>
        </View>
      </View>
    </TouchableOpacity>
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
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  
  // Header
  header: {
    padding: 24,
    paddingBottom: 16,
  },
  title: {
    fontSize: 32,
    fontWeight: '700',
    color: '#FFF',
    letterSpacing: -1,
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 15,
    color: '#666',
  },
  
  // Summary
  summaryContainer: {
    flexDirection: 'row',
    marginHorizontal: 24,
    marginBottom: 24,
    backgroundColor: '#121212',
    borderRadius: 12,
    padding: 20,
    borderWidth: 1,
    borderColor: '#1E1E1E',
  },
  summaryCard: {
    flex: 1,
    alignItems: 'center',
  },
  summaryNumber: {
    fontSize: 36,
    fontWeight: '700',
    color: '#FFF',
    letterSpacing: -1,
    marginBottom: 4,
  },
  summaryLabel: {
    fontSize: 11,
    color: '#666',
    fontWeight: '600',
    letterSpacing: 0.5,
  },
  summarySeparator: {
    width: 1,
    backgroundColor: '#1E1E1E',
    marginHorizontal: 20,
  },
  
  // Sort Tabs
  sortContainer: {
    flexDirection: 'row',
    paddingHorizontal: 24,
    marginBottom: 20,
    gap: 8,
  },
  sortTab: {
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 100,
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: '#2A2A2A',
  },
  sortTabActive: {
    backgroundColor: '#FFF',
    borderColor: '#FFF',
  },
  sortText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#666',
  },
  sortTextActive: {
    color: '#000',
  },
  
  // Sessions List
  sessionsList: {
    flex: 1,
  },
  sessionsListContent: {
    padding: 24,
    paddingTop: 0,
  },
  
  // Session Card
  sessionCard: {
    backgroundColor: '#121212',
    borderRadius: 12,
    padding: 20,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#1E1E1E',
  },
  sessionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  sessionDate: {
    fontSize: 17,
    fontWeight: '700',
    color: '#FFF',
    marginBottom: 4,
  },
  sessionTime: {
    fontSize: 13,
    color: '#666',
  },
  
  // Accuracy Circle
  accuracyContainer: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#1E1E1E',
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    borderWidth: 2,
    borderColor: '#FF4D00',
  },
  accuracyNumber: {
    fontSize: 20,
    fontWeight: '700',
    color: '#FFF',
    letterSpacing: -0.5,
  },
  accuracyPercent: {
    fontSize: 11,
    fontWeight: '700',
    color: '#666',
    marginLeft: 2,
  },
  
  // Session Stats
  sessionDivider: {
    height: 1,
    backgroundColor: '#1E1E1E',
    marginBottom: 16,
  },
  sessionStats: {
    flexDirection: 'row',
  },
  sessionStat: {
    flex: 1,
    alignItems: 'center',
  },
  sessionStatValue: {
    fontSize: 24,
    fontWeight: '700',
    color: '#FFF',
    marginBottom: 4,
    letterSpacing: -0.5,
  },
  sessionStatLabel: {
    fontSize: 11,
    color: '#666',
    fontWeight: '600',
    letterSpacing: 0.5,
  },
  sessionStatDivider: {
    width: 1,
    backgroundColor: '#1E1E1E',
    marginHorizontal: 16,
  },
  
  // Empty State
  emptyState: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 80,
  },
  emptyIcon: {
    marginBottom: 24,
  },
  emptyTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#FFF',
    marginBottom: 8,
  },
  emptyText: {
    fontSize: 15,
    color: '#666',
    textAlign: 'center',
    marginBottom: 32,
  },
  emptyButton: {
    backgroundColor: '#FF4D00',
    borderRadius: 100,
    paddingVertical: 16,
    paddingHorizontal: 32,
  },
  emptyButtonText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#FFF',
  },
});