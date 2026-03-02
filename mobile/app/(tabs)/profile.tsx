/**
 * Profile Screen - Peloton Style
 * Clean profile with bold stats and minimal design
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  TextInput,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../contexts/AuthContext';
import { ErrorBoundary } from '../../components/ErrorBoundary';

function ProfileScreen() {
  const router = useRouter();
  const { user, profile, signOut, updateProfile, refreshProfile } = useAuth();
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);

  // Edit form state
  const [editedName, setEditedName] = useState(profile?.full_name || '');
  const [editedGoal, setEditedGoal] = useState(profile?.primary_goal || '');


  const handleSaveProfile = async () => {
    if (!editedName) {
      Alert.alert('Error', 'Name cannot be empty');
      return;
    }

    setSaving(true);
    try {
      const { error } = await updateProfile({
        full_name: editedName,
        primary_goal: editedGoal || null,
      });

      if (error) throw error;

      await refreshProfile();
      setEditing(false);
      Alert.alert('Success', 'Profile updated');
    } catch (error: any) {
      Alert.alert('Error', 'Could not update profile: ' + error.message);
    } finally {
      setSaving(false);
    }
  };

  const handleSignOut = () => {
    Alert.alert(
      'Sign Out',
      'Are you sure?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Sign Out',
          style: 'destructive',
          onPress: async () => {
            try {
              await signOut();
              router.replace('/auth/login');
            } catch (error) {
              Alert.alert('Error', 'Could not sign out');
            }
          },
        },
      ]
    );
  };

  if (!profile) {
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
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>Profile</Text>
          {!editing && (
            <TouchableOpacity onPress={() => setEditing(true)}>
              <Text style={styles.editButton}>Edit</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Profile Card */}
        <View style={styles.profileCard}>
          {editing ? (
            <>
              <View style={styles.inputGroup}>
                <Text style={styles.inputLabel}>NAME</Text>
                <TextInput
                  style={styles.input}
                  value={editedName}
                  onChangeText={setEditedName}
                  placeholder="Your name"
                  placeholderTextColor="#666"
                />
              </View>

              <View style={styles.inputGroup}>
                <Text style={styles.inputLabel}>GOAL</Text>
                <TextInput
                  style={[styles.input, styles.inputMultiline]}
                  value={editedGoal}
                  onChangeText={setEditedGoal}
                  placeholder="Your primary goal"
                  placeholderTextColor="#666"
                  multiline
                  numberOfLines={3}
                />
              </View>

              <View style={styles.editActions}>
                <TouchableOpacity
                  style={styles.cancelButton}
                  onPress={() => {
                    setEditedName(profile?.full_name || '');
                    setEditedGoal(profile?.primary_goal || '');
                    setEditing(false);
                  }}
                >
                  <Text style={styles.cancelButtonText}>Cancel</Text>
                </TouchableOpacity>
                
                <TouchableOpacity
                  style={[styles.saveButton, saving && styles.saveButtonDisabled]}
                  onPress={handleSaveProfile}
                  disabled={saving}
                >
                  {saving ? (
                    <ActivityIndicator color="#FFF" size="small" />
                  ) : (
                    <Text style={styles.saveButtonText}>Save</Text>
                  )}
                </TouchableOpacity>
              </View>
            </>
          ) : (
            <>
              <Text style={styles.profileName}>{profile.full_name}</Text>
              <Text style={styles.profileEmail}>{user?.email}</Text>
              
              <View style={styles.profileDetails}>
                <View style={styles.profileDetailRow}>
                  <Text style={styles.profileDetailLabel}>SKILL LEVEL</Text>
                  <Text style={styles.profileDetailValue}>
                    {profile.skill_level ? 
                      profile.skill_level.charAt(0).toUpperCase() + profile.skill_level.slice(1) 
                      : 'Not set'}
                  </Text>
                </View>
                
                <View style={styles.profileDetailRow}>
                  <Text style={styles.profileDetailLabel}>SHOOTING HAND</Text>
                  <Text style={styles.profileDetailValue}>
                    {profile.shooting_hand.charAt(0).toUpperCase() + profile.shooting_hand.slice(1)}
                  </Text>
                </View>
                
                {profile.height_inches && (
                  <View style={styles.profileDetailRow}>
                    <Text style={styles.profileDetailLabel}>HEIGHT</Text>
                    <Text style={styles.profileDetailValue}>
                      {Math.floor(profile.height_inches / 12)}'{profile.height_inches % 12}"
                    </Text>
                  </View>
                )}
              </View>

              {profile.primary_goal && (
                <View style={styles.goalCard}>
                  <Text style={styles.goalLabel}>GOAL</Text>
                  <Text style={styles.goalText}>{profile.primary_goal}</Text>
                </View>
              )}
            </>
          )}
        </View>

        {/* Lifetime Stats */}
        <View style={styles.statsSection}>
          <Text style={styles.sectionTitle}>Lifetime Stats</Text>
          
          <View style={styles.statsGrid}>
            <View style={styles.statBox}>
              <Text style={styles.statValue}>{profile.total_sessions}</Text>
              <Text style={styles.statLabel}>SESSIONS</Text>
            </View>
            
            <View style={styles.statBox}>
              <Text style={styles.statValue}>{profile.total_shots}</Text>
              <Text style={styles.statLabel}>SHOTS</Text>
            </View>
            
            <View style={styles.statBox}>
              <Text style={styles.statValue}>{profile.total_makes}</Text>
              <Text style={styles.statLabel}>MAKES</Text>
            </View>
            
            <View style={styles.statBox}>
              <Text style={styles.statValue}>
                {profile.total_shots > 0 
                  ? `${Math.round((profile.total_makes / profile.total_shots) * 100)}%`
                  : '0%'}
              </Text>
              <Text style={styles.statLabel}>ACCURACY</Text>
            </View>
          </View>
        </View>

        {/* Settings */}
        <View style={styles.settingsSection}>
          <Text style={styles.sectionTitle}>Settings</Text>
          
          <TouchableOpacity
            style={styles.settingRow}
            onPress={() => router.push('/edit-preferences')}
          >
            <Text style={styles.settingText}>Edit Preferences</Text>
            <Ionicons name="chevron-forward" size={18} color="#666" />
          </TouchableOpacity>
          
          <View style={styles.settingDivider} />
          
          <TouchableOpacity style={styles.settingRow}>
            <Text style={styles.settingText}>Notifications</Text>
            <Text style={styles.settingValue}>
              {profile.notifications_enabled ? 'On' : 'Off'}
            </Text>
          </TouchableOpacity>
          
          <View style={styles.settingDivider} />
          
          <TouchableOpacity style={styles.settingRow}>
            <Text style={styles.settingText}>Subscription</Text>
            <Text style={styles.settingValue}>
              {profile.subscription_tier === 'free' ? 'Free' : 
               profile.subscription_tier.toUpperCase()}
            </Text>
          </TouchableOpacity>
        </View>

        {/* Sign Out */}
        <TouchableOpacity style={styles.signOutButton} onPress={handleSignOut}>
          <Text style={styles.signOutText}>Sign Out</Text>
        </TouchableOpacity>

        {/* Version */}
        <Text style={styles.version}>FormCheck v1.0.0</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

export default function ProfileScreenWithBoundary() {
  return (
    <ErrorBoundary>
      <ProfileScreen />
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
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  
  // Header
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 24,
  },
  title: {
    fontSize: 32,
    fontWeight: '700',
    color: '#FFF',
    letterSpacing: -1,
  },
  editButton: {
    fontSize: 15,
    color: '#FF4D00',
    fontWeight: '600',
  },
  
  // Profile Card
  profileCard: {
    backgroundColor: '#121212',
    borderRadius: 12,
    padding: 24,
    marginBottom: 24,
    borderWidth: 1,
    borderColor: '#1E1E1E',
  },
  profileName: {
    fontSize: 24,
    fontWeight: '700',
    color: '#FFF',
    marginBottom: 4,
    letterSpacing: -0.5,
  },
  profileEmail: {
    fontSize: 15,
    color: '#666',
    marginBottom: 24,
  },
  profileDetails: {
    gap: 16,
  },
  profileDetailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  profileDetailLabel: {
    fontSize: 11,
    color: '#666',
    fontWeight: '600',
    letterSpacing: 0.5,
  },
  profileDetailValue: {
    fontSize: 15,
    color: '#FFF',
    fontWeight: '600',
  },
  goalCard: {
    marginTop: 20,
    paddingTop: 20,
    borderTopWidth: 1,
    borderTopColor: '#1E1E1E',
  },
  goalLabel: {
    fontSize: 11,
    color: '#666',
    fontWeight: '600',
    letterSpacing: 0.5,
    marginBottom: 8,
  },
  goalText: {
    fontSize: 15,
    color: '#FFF',
    lineHeight: 22,
  },
  
  // Editing
  inputGroup: {
    marginBottom: 20,
  },
  inputLabel: {
    fontSize: 11,
    color: '#666',
    fontWeight: '600',
    letterSpacing: 0.5,
    marginBottom: 8,
  },
  input: {
    backgroundColor: '#1E1E1E',
    borderRadius: 8,
    padding: 16,
    fontSize: 15,
    color: '#FFF',
    borderWidth: 1,
    borderColor: '#2A2A2A',
  },
  inputMultiline: {
    minHeight: 80,
    textAlignVertical: 'top',
  },
  editActions: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 8,
  },
  cancelButton: {
    flex: 1,
    backgroundColor: 'transparent',
    borderRadius: 100,
    paddingVertical: 14,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#2A2A2A',
  },
  cancelButtonText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#FFF',
  },
  saveButton: {
    flex: 1,
    backgroundColor: '#FF4D00',
    borderRadius: 100,
    paddingVertical: 14,
    alignItems: 'center',
  },
  saveButtonDisabled: {
    opacity: 0.5,
  },
  saveButtonText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#FFF',
  },
  
  // Stats Section
  statsSection: {
    marginBottom: 32,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#FFF',
    marginBottom: 16,
    letterSpacing: 0.5,
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  statBox: {
    flex: 1,
    minWidth: '47%',
    backgroundColor: '#121212',
    borderRadius: 12,
    padding: 20,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#1E1E1E',
  },
  statValue: {
    fontSize: 32,
    fontWeight: '700',
    color: '#FFF',
    marginBottom: 4,
    letterSpacing: -1,
  },
  statLabel: {
    fontSize: 11,
    color: '#666',
    fontWeight: '600',
    letterSpacing: 0.5,
  },
  
  // Settings Section
  settingsSection: {
    backgroundColor: '#121212',
    borderRadius: 12,
    padding: 24,
    marginBottom: 24,
    borderWidth: 1,
    borderColor: '#1E1E1E',
  },
  settingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
  },
  settingText: {
    fontSize: 15,
    color: '#FFF',
    fontWeight: '600',
  },
  settingValue: {
    fontSize: 15,
    color: '#666',
  },
  settingDivider: {
    height: 1,
    backgroundColor: '#1E1E1E',
    marginVertical: 4,
  },
  
  // Sign Out
  signOutButton: {
    backgroundColor: 'transparent',
    borderRadius: 100,
    paddingVertical: 16,
    alignItems: 'center',
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#2A2A2A',
  },
  signOutText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#FFF',
  },
  
  // Version
  version: {
    fontSize: 13,
    color: '#666',
    textAlign: 'center',
  },
});