/**
 * Onboarding Survey Screen - FIXED
 * Collects user info: skill level, goals, preferences
 * 
 * FIXES:
 * - Added SafeAreaView for iOS notch/camera island
 * - Added KeyboardAvoidingView for better mobile experience
 * - Improved padding and layout
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  TouchableWithoutFeedback,
  Keyboard,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../contexts/AuthContext';
import { db } from '../lib/supabase';
import { router } from 'expo-router';

const SKILL_LEVELS = [
  { value: 'beginner', label: 'Beginner', description: 'New to basketball or working on fundamentals' },
  { value: 'intermediate', label: 'Intermediate', description: 'Comfortable shooting, working on consistency' },
  { value: 'advanced', label: 'Advanced', description: 'Experienced player refining technique' },
];

const FOCUS_AREAS = [
  { value: 'consistency', label: 'Consistency' },
  { value: 'form', label: 'Shooting Form' },
  { value: 'range', label: 'Shooting Range' },
  { value: 'accuracy', label: 'Accuracy' },
  { value: 'speed', label: 'Release Speed' },
  { value: 'arc', label: 'Shot Arc' },
];

const PRACTICE_FREQUENCIES = [
  { value: 'daily', label: 'Daily' },
  { value: 'few_times_week', label: 'Few times a week' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'occasionally', label: 'Occasionally' },
];

const DISTANCES = [
  { value: 'free_throw', label: 'Free Throw Line' },
  { value: 'mid_range', label: 'Mid-Range' },
  { value: 'three_point', label: 'Three-Point Line' },
];

export default function OnboardingScreen() {
  const { user, refreshProfile, forceClearSession } = useAuth();
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState(1);

  // Form data
  const [skillLevel, setSkillLevel] = useState<string | null>(null);
  const [shootingHand, setShootingHand] = useState<'left' | 'right'>('right');
  const [heightFeet, setHeightFeet] = useState('');
  const [heightInches, setHeightInches] = useState('');
  const [selectedFocusAreas, setSelectedFocusAreas] = useState<string[]>([]);
  const [primaryGoal, setPrimaryGoal] = useState('');
  const [preferredDistance, setPreferredDistance] = useState<string | null>(null);
  const [playsOrganized, setPlaysOrganized] = useState(false);
  const [practiceFrequency, setPracticeFrequency] = useState<string | null>(null);

  const toggleFocusArea = (area: string) => {
    if (selectedFocusAreas.includes(area)) {
      setSelectedFocusAreas(selectedFocusAreas.filter(a => a !== area));
    } else {
      setSelectedFocusAreas([...selectedFocusAreas, area]);
    }
  };

  const handleNext = () => {
    if (step === 1) {
      if (!skillLevel) {
        Alert.alert('Required', 'Please select your skill level');
        return;
      }
    } else if (step === 2) {
      if (selectedFocusAreas.length === 0) {
        Alert.alert('Required', 'Please select at least one focus area');
        return;
      }
    }
    setStep(step + 1);
  };

  const handleSubmit = async () => {
    if (!practiceFrequency) {
      Alert.alert('Required', 'Please select how often you practice');
      return;
    }

    setLoading(true);
    try {
      const heightInchesTotal = heightFeet && heightInches
        ? parseInt(heightFeet) * 12 + parseInt(heightInches)
        : null;

      await db.updateProfile({
        full_name: user?.user_metadata?.full_name || '',
        skill_level: skillLevel as any,
        shooting_hand: shootingHand,
        height_inches: heightInchesTotal,
        focus_areas: selectedFocusAreas,
        primary_goal: primaryGoal || null,
        preferred_distance: preferredDistance,
        plays_organized: playsOrganized,
        practice_frequency: practiceFrequency,
      });

      await refreshProfile();
      router.replace('/');
    } catch (error: any) {
      const errorMessage = error.message || 'Unknown error';
      
      // Check if it's an authentication error
      if (errorMessage.includes('authenticated') || 
          errorMessage.includes('Session') || 
          errorMessage.includes('JWT') ||
          errorMessage.includes('auth')) {
        Alert.alert(
          'Session Error',
          'Your session has expired or is invalid. Please sign in again.',
          [
            {
              text: 'Clear & Sign In',
              onPress: async () => {
                await forceClearSession();
                router.replace('/auth/login');
              },
            },
          ]
        );
      } else {
        Alert.alert('Error', 'Could not save profile: ' + errorMessage);
      }
    } finally {
      setLoading(false);
    }
  };

  if (step === 1) {
    return (
      <SafeAreaView style={styles.safeArea} edges={['top', 'bottom']}>
        <KeyboardAvoidingView 
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.container}
        >
          <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
            <ScrollView 
              style={styles.scrollView}
              contentContainerStyle={styles.content}
              keyboardShouldPersistTaps="handled"
            >
              <Text style={styles.title}>Hey, {user?.user_metadata?.full_name?.split(' ')[0] || 'there'}!</Text>
              <Text style={styles.subtitle}>Let's set up your profile</Text>
              <Text style={styles.stepIndicator}>Step 1 of 3</Text>

              <View style={styles.section}>
                <Text style={styles.label}>Skill Level</Text>
                {SKILL_LEVELS.map((level) => (
                  <TouchableOpacity
                    key={level.value}
                    style={[
                      styles.optionCard,
                      skillLevel === level.value && styles.optionCardSelected,
                    ]}
                    onPress={() => setSkillLevel(level.value)}
                  >
                    <Text style={[
                      styles.optionTitle,
                      skillLevel === level.value && styles.optionTextSelected,
                    ]}>
                      {level.label}
                    </Text>
                    <Text style={[
                      styles.optionDescription,
                      skillLevel === level.value && styles.optionTextSelected,
                    ]}>
                      {level.description}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              <View style={styles.section}>
                <Text style={styles.label}>Shooting Hand</Text>
                <View style={styles.toggleRow}>
                  <TouchableOpacity
                    style={[
                      styles.toggleButton,
                      shootingHand === 'left' && styles.toggleButtonActive,
                    ]}
                    onPress={() => setShootingHand('left')}
                  >
                    <Text style={[
                      styles.toggleText,
                      shootingHand === 'left' && styles.toggleTextActive,
                    ]}>
                      Left
                    </Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[
                      styles.toggleButton,
                      shootingHand === 'right' && styles.toggleButtonActive,
                    ]}
                    onPress={() => setShootingHand('right')}
                  >
                    <Text style={[
                      styles.toggleText,
                      shootingHand === 'right' && styles.toggleTextActive,
                    ]}>
                      Right
                    </Text>
                  </TouchableOpacity>
                </View>
              </View>

              <View style={styles.section}>
                <Text style={styles.label}>Height (Optional)</Text>
                <View style={styles.heightRow}>
                  <TextInput
                    style={[styles.input, styles.heightInput]}
                    placeholder="Feet"
                    placeholderTextColor="#666"
                    value={heightFeet}
                    onChangeText={setHeightFeet}
                    keyboardType="number-pad"
                    maxLength={1}
                    returnKeyType="next"
                  />
                  <Text style={styles.heightSeparator}>'</Text>
                  <TextInput
                    style={[styles.input, styles.heightInput]}
                    placeholder="Inches"
                    placeholderTextColor="#666"
                    value={heightInches}
                    onChangeText={setHeightInches}
                    keyboardType="number-pad"
                    maxLength={2}
                    returnKeyType="done"
                  />
                  <Text style={styles.heightSeparator}>"</Text>
                </View>
              </View>

              <TouchableOpacity style={styles.button} onPress={handleNext}>
                <Text style={styles.buttonText}>Next</Text>
              </TouchableOpacity>
            </ScrollView>
          </TouchableWithoutFeedback>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  if (step === 2) {
    return (
      <SafeAreaView style={styles.safeArea} edges={['top', 'bottom']}>
        <KeyboardAvoidingView 
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.container}
        >
          <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
            <ScrollView 
              style={styles.scrollView}
              contentContainerStyle={styles.content}
              keyboardShouldPersistTaps="handled"
            >
              <Text style={styles.title}>What are your goals?</Text>
              <Text style={styles.subtitle}>Select all that apply</Text>
              <Text style={styles.stepIndicator}>Step 2 of 3</Text>

              <View style={styles.section}>
                <Text style={styles.label}>Focus Areas</Text>
                <View style={styles.chipContainer}>
                  {FOCUS_AREAS.map((area) => (
                    <TouchableOpacity
                      key={area.value}
                      style={[
                        styles.chip,
                        selectedFocusAreas.includes(area.value) && styles.chipSelected,
                      ]}
                      onPress={() => toggleFocusArea(area.value)}
                    >
                      <Text style={[
                        styles.chipText,
                        selectedFocusAreas.includes(area.value) && styles.chipTextSelected,
                      ]}>
                        {area.label}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>

              <View style={styles.section}>
                <Text style={styles.label}>Primary Goal (Optional)</Text>
                <Text style={styles.helperText}>
                  What's your main focus right now?
                </Text>
                <TextInput
                  style={[styles.input, styles.textArea]}
                  placeholder="e.g., Improve consistency from the three-point line"
                  placeholderTextColor="#666"
                  value={primaryGoal}
                  onChangeText={setPrimaryGoal}
                  multiline
                  numberOfLines={3}
                  textAlignVertical="top"
                  returnKeyType="done"
                  blurOnSubmit={true}
                />
              </View>

              <View style={styles.buttonRow}>
                <TouchableOpacity
                  style={[styles.button, styles.buttonSecondary]}
                  onPress={() => setStep(1)}
                >
                  <Text style={styles.buttonSecondaryText}>Back</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.button} onPress={handleNext}>
                  <Text style={styles.buttonText}>Next</Text>
                </TouchableOpacity>
              </View>
            </ScrollView>
          </TouchableWithoutFeedback>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'bottom']}>
      <ScrollView 
        style={styles.scrollView}
        contentContainerStyle={styles.content}
      >
        <Text style={styles.title}>Almost done!</Text>
        <Text style={styles.subtitle}>Tell us about your practice</Text>
        <Text style={styles.stepIndicator}>Step 3 of 3</Text>

        <View style={styles.section}>
          <Text style={styles.label}>Preferred Shooting Distance</Text>
          {DISTANCES.map((distance) => (
            <TouchableOpacity
              key={distance.value}
              style={[
                styles.optionCard,
                preferredDistance === distance.value && styles.optionCardSelected,
              ]}
              onPress={() => setPreferredDistance(distance.value)}
            >
              <Text style={[
                styles.optionTitle,
                preferredDistance === distance.value && styles.optionTextSelected,
              ]}>
                {distance.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <View style={styles.section}>
          <Text style={styles.label}>How often do you practice?</Text>
          {PRACTICE_FREQUENCIES.map((freq) => (
            <TouchableOpacity
              key={freq.value}
              style={[
                styles.optionCard,
                practiceFrequency === freq.value && styles.optionCardSelected,
              ]}
              onPress={() => setPracticeFrequency(freq.value)}
            >
              <Text style={[
                styles.optionTitle,
                practiceFrequency === freq.value && styles.optionTextSelected,
              ]}>
                {freq.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <View style={styles.section}>
          <TouchableOpacity
            style={styles.checkboxRow}
            onPress={() => setPlaysOrganized(!playsOrganized)}
          >
            <View style={[styles.checkbox, playsOrganized && styles.checkboxChecked]}>
              {playsOrganized && <Text style={styles.checkmark}>✓</Text>}
            </View>
            <Text style={styles.checkboxLabel}>
              I play in organized basketball (league, team, etc.)
            </Text>
          </TouchableOpacity>
        </View>

        <View style={styles.buttonRow}>
          <TouchableOpacity
            style={[styles.button, styles.buttonSecondary]}
            onPress={() => setStep(2)}
          >
            <Text style={styles.buttonSecondaryText}>Back</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.button, loading && styles.buttonDisabled]}
            onPress={handleSubmit}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.buttonText}>Complete</Text>
            )}
          </TouchableOpacity>
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
  scrollView: {
    flex: 1,
  },
  content: {
    padding: 20,
    paddingBottom: 40,
  },
  title: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 10,
  },
  subtitle: {
    fontSize: 16,
    color: '#999',
    marginBottom: 10,
  },
  stepIndicator: {
    fontSize: 14,
    color: '#ff6b00',
    marginBottom: 30,
  },
  section: {
    marginBottom: 30,
  },
  label: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 15,
  },
  helperText: {
    fontSize: 14,
    color: '#999',
    marginBottom: 10,
  },
  input: {
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.2)',
    borderRadius: 10,
    padding: 15,
    fontSize: 16,
    color: '#fff',
  },
  textArea: {
    minHeight: 80,
    textAlignVertical: 'top',
  },
  optionCard: {
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    borderWidth: 2,
    borderColor: 'rgba(255, 255, 255, 0.1)',
    borderRadius: 10,
    padding: 15,
    marginBottom: 10,
  },
  optionCardSelected: {
    borderColor: '#ff6b00',
    backgroundColor: 'rgba(255, 107, 0, 0.1)',
  },
  optionTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 5,
  },
  optionDescription: {
    fontSize: 14,
    color: '#999',
  },
  optionTextSelected: {
    color: '#ff6b00',
  },
  toggleRow: {
    flexDirection: 'row',
    gap: 10,
  },
  toggleButton: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 10,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderWidth: 2,
    borderColor: 'rgba(255, 255, 255, 0.2)',
    alignItems: 'center',
  },
  toggleButtonActive: {
    backgroundColor: '#ff6b00',
    borderColor: '#ff6b00',
  },
  toggleText: {
    fontSize: 16,
    color: '#fff',
  },
  toggleTextActive: {
    fontWeight: 'bold',
  },
  heightRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  heightInput: {
    flex: 1,
    textAlign: 'center',
  },
  heightSeparator: {
    fontSize: 20,
    color: '#fff',
  },
  chipContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  chip: {
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 20,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.2)',
  },
  chipSelected: {
    backgroundColor: '#ff6b00',
    borderColor: '#ff6b00',
  },
  chipText: {
    fontSize: 14,
    color: '#fff',
  },
  chipTextSelected: {
    fontWeight: 'bold',
  },
  checkboxRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  checkbox: {
    width: 24,
    height: 24,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: 'rgba(255, 255, 255, 0.3)',
    marginRight: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },
  checkboxChecked: {
    backgroundColor: '#ff6b00',
    borderColor: '#ff6b00',
  },
  checkmark: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
  },
  checkboxLabel: {
    flex: 1,
    fontSize: 14,
    color: '#fff',
  },
  button: {
    backgroundColor: '#ff6b00',
    borderRadius: 10,
    padding: 15,
    alignItems: 'center',
    marginTop: 10,
    flex: 1,
  },
  buttonSecondary: {
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderWidth: 2,
    borderColor: '#ff6b00',
  },
  buttonSecondaryText: {
    color: '#ff6b00',
    fontSize: 16,
    fontWeight: 'bold',
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 10,
  },
});