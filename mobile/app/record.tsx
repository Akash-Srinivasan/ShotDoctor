import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ActivityIndicator, ScrollView, TouchableOpacity, Image, Alert } from 'react-native';
import { VideoView, useVideoPlayer } from 'expo-video';
import * as ImagePicker from 'expo-image-picker';
import { RecordingCamera } from '../components/Camera';
import { analyzeVideo, type SessionSummary } from '../lib/api';

export default function RecordScreen() {
  const [showCamera, setShowCamera] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<SessionSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [shootingSide, setShootingSide] = useState<'left' | 'right'>('right');
  const [currentVideoUri, setCurrentVideoUri] = useState<string | null>(null);
  const [analysisProgress, setAnalysisProgress] = useState('Uploading video...');
  
  // Video players
  const previewPlayer = useVideoPlayer(currentVideoUri || '', (player) => {
    player.loop = true;
    player.play();
  });
  
  const replayPlayer = useVideoPlayer(currentVideoUri || '', (player) => {
    player.loop = false;
  });

  const handleVideoRecorded = async (uri: string) => {
    console.log('📹 Video recorded:', uri);
    setShowCamera(false);
    setCurrentVideoUri(uri);
    await analyzeVideoFile(uri);
  };

  const handlePickVideo = async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission needed', 'Please grant access to your photos');
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['videos'],
      allowsEditing: false,
      quality: 1,
    });

    if (!result.canceled && result.assets[0]) {
      const uri = result.assets[0].uri;
      console.log('📁 Video selected:', uri);
      setCurrentVideoUri(uri);
      await analyzeVideoFile(uri);
    }
  };

  const analyzeVideoFile = async (uri: string) => {
    setAnalyzing(true);
    setError(null);
    setResult(null);
    setAnalysisProgress('Uploading video...');

    try {
      // Simulate progress updates
      setTimeout(() => setAnalysisProgress('Detecting shots...'), 2000);
      setTimeout(() => setAnalysisProgress('Analyzing form...'), 5000);
      setTimeout(() => setAnalysisProgress('Generating feedback...'), 8000);
      
      console.log('📤 Sending to API for analysis...');
      const analysis = await analyzeVideo(uri, shootingSide);
      console.log('✓ Analysis complete:', analysis);
      setResult(analysis);
    } catch (err: any) {
      console.error('❌ Analysis error:', err);
      setError(err.message || 'Failed to analyze video');
    } finally {
      setAnalyzing(false);
    }
  };

  const handleCancel = () => {
    setShowCamera(false);
  };

  const startNewRecording = () => {
    setResult(null);
    setError(null);
    setCurrentVideoUri(null);
    setShowCamera(true);
  };

  const startVideoUpload = () => {
    setResult(null);
    setError(null);
    setCurrentVideoUri(null);
    handlePickVideo();
  };

  if (showCamera) {
    return (
      <RecordingCamera
        onVideoRecorded={handleVideoRecorded}
        onCancel={handleCancel}
      />
    );
  }

  if (analyzing) {
    return (
      <View style={styles.container}>
        {currentVideoUri && (
          <View style={styles.videoPreviewContainer}>
            <VideoView
              player={previewPlayer}
              style={styles.videoPreview}
              nativeControls={false}
              contentFit="contain"
            />
          </View>
        )}

        <ActivityIndicator size="large" color="#ff6b00" style={styles.loader} />
        <Text style={styles.analyzingText}>{analysisProgress}</Text>
        <Text style={styles.analyzingSubtext}>
          This may take 30-90 seconds
        </Text>
        <Text style={styles.analyzingNote}>
          • Scanning entire video{'\n'}
          • Detecting all shots{'\n'}
          • Measuring form metrics{'\n'}
          • Getting AI coaching
        </Text>
      </View>
    );
  }

  if (result) {
    const goodShots = result.shots.filter(s => s.form_rating && s.form_rating >= 7).length;
    const needsWork = result.shots.filter(s => s.form_rating && s.form_rating < 7).length;

    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.resultContainer}>
        {/* Video Replay */}
        {currentVideoUri && (
          <View style={styles.videoReplayContainer}>
            <Text style={styles.videoReplayLabel}>Session Video</Text>
            <VideoView
              player={replayPlayer}
              style={styles.videoReplay}
              nativeControls={true}
              contentFit="contain"
            />
          </View>
        )}

        {/* Session Stats */}
        <View style={styles.statsCard}>
          <Text style={styles.statsTitle}>Session Summary</Text>
          
          <View style={styles.statRow}>
            <Text style={styles.statLabel}>Shots Taken:</Text>
            <Text style={styles.statValue}>{result.total_shots}</Text>
          </View>
          
          <View style={styles.statRow}>
            <Text style={styles.statLabel}>Made:</Text>
            <Text style={[styles.statValue, styles.statMade]}>{result.shots_made}</Text>
          </View>
          
          <View style={styles.statRow}>
            <Text style={styles.statLabel}>Missed:</Text>
            <Text style={[styles.statValue, styles.statMissed]}>{result.shots_missed}</Text>
          </View>
          
          <View style={styles.statRow}>
            <Text style={styles.statLabel}>Shooting %:</Text>
            <Text style={styles.statValue}>{result.shooting_percentage.toFixed(1)}%</Text>
          </View>
          
          <View style={styles.statRow}>
            <Text style={styles.statLabel}>Avg Form:</Text>
            <Text style={styles.statValue}>{result.average_form_rating.toFixed(1)}/10</Text>
          </View>
        </View>

        {/* Session Feedback */}
        <View style={styles.feedbackCard}>
          <Text style={styles.feedbackLabel}>💬 Coach's Assessment</Text>
          <Text style={styles.feedbackText}>{result.session_feedback}</Text>
        </View>

        {/* All Shots */}
        <View style={styles.shotsCard}>
          <Text style={styles.shotsTitle}>📸 All Shots ({result.total_shots})</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.shotsScroll}>
            {result.shots.map((shot) => (
              <View key={shot.shot_number} style={styles.shotItem}>
                <Image 
                  source={{ uri: `data:image/jpeg;base64,${shot.thumbnail}` }}
                  style={styles.shotThumbnail}
                />
                <View style={[
                  styles.shotBadge,
                  shot.made ? styles.shotBadgeMade : styles.shotBadgeMissed
                ]}>
                  <Text style={styles.shotBadgeText}>
                    {shot.made ? '✓' : '✗'}
                  </Text>
                </View>
                <Text style={styles.shotNumber}>Shot {shot.shot_number}</Text>
                {shot.form_rating && (
                  <Text style={styles.shotRating}>{shot.form_rating}/10</Text>
                )}
                {shot.quick_cue && (
                  <Text style={styles.shotCue}>{shot.quick_cue}</Text>
                )}
              </View>
            ))}
          </ScrollView>
        </View>

        {/* Form Analysis */}
        {(goodShots > 0 || needsWork > 0) && (
          <View style={styles.formCard}>
            <Text style={styles.formTitle}>📊 Form Breakdown</Text>
            {goodShots > 0 && (
              <View style={styles.formRow}>
                <Text style={styles.formLabel}>✓ Good form:</Text>
                <Text style={styles.formValue}>{goodShots} shots</Text>
              </View>
            )}
            {needsWork > 0 && (
              <View style={styles.formRow}>
                <Text style={styles.formLabel}>→ Needs work:</Text>
                <Text style={styles.formValue}>{needsWork} shots</Text>
              </View>
            )}
          </View>
        )}

        {/* Drill Suggestions */}
        {result.drill_suggestions.length > 0 && (
          <View style={styles.drillsCard}>
            <Text style={styles.drillsTitle}>🏋️ Recommended Drills</Text>
            {result.drill_suggestions.map((drill, index) => (
              <View key={index} style={styles.drillItem}>
                <Text style={styles.drillNumber}>{index + 1}</Text>
                <Text style={styles.drillText}>{drill}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Action Buttons */}
        <TouchableOpacity style={styles.recordButton} onPress={startNewRecording}>
          <Text style={styles.recordButtonText}>📹 Record New Session</Text>
        </TouchableOpacity>
        
        <TouchableOpacity style={styles.uploadButton} onPress={startVideoUpload}>
          <Text style={styles.uploadButtonText}>📁 Upload Video</Text>
        </TouchableOpacity>
      </ScrollView>
    );
  }

  if (error) {
    return (
      <View style={styles.container}>
        <Text style={styles.errorTitle}>❌ Error</Text>
        <Text style={styles.errorText}>{error}</Text>
        <TouchableOpacity style={styles.retryButton} onPress={startNewRecording}>
          <Text style={styles.retryButtonText}>Try Again</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // Welcome screen
  return (
    <View style={styles.container}>
      <View style={styles.welcomeContainer}>
        <Text style={styles.title}>🏀 FormCheck</Text>
        <Text style={styles.subtitle}>AI Basketball Coach</Text>
        
        <View style={styles.infoBox}>
          <Text style={styles.infoTitle}>New: Multi-Shot Analysis</Text>
          <Text style={styles.infoText}>• Record multiple shots in one video</Text>
          <Text style={styles.infoText}>• Get analysis for each shot</Text>
          <Text style={styles.infoText}>• Session summary with drills</Text>
        </View>

        <View style={styles.toggleContainer}>
          <Text style={styles.toggleLabel}>Shooting Hand:</Text>
          <View style={styles.toggleButtons}>
            <TouchableOpacity
              style={[styles.toggleButton, shootingSide === 'left' && styles.toggleButtonActive]}
              onPress={() => setShootingSide('left')}
            >
              <Text style={[styles.toggleButtonText, shootingSide === 'left' && styles.toggleButtonTextActive]}>
                Left
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.toggleButton, shootingSide === 'right' && styles.toggleButtonActive]}
              onPress={() => setShootingSide('right')}
            >
              <Text style={[styles.toggleButtonText, shootingSide === 'right' && styles.toggleButtonTextActive]}>
                Right
              </Text>
            </TouchableOpacity>
          </View>
        </View>

        <TouchableOpacity style={styles.startButton} onPress={startNewRecording}>
          <Text style={styles.startButtonText}>📹 Record Session</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.uploadButtonMain} onPress={startVideoUpload}>
          <Text style={styles.uploadButtonMainText}>📁 Upload Video</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000',
  },
  welcomeContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  title: {
    fontSize: 48,
    fontWeight: 'bold',
    color: '#ff6b00',
    marginBottom: 10,
  },
  subtitle: {
    fontSize: 20,
    color: '#fff',
    marginBottom: 40,
  },
  infoBox: {
    backgroundColor: 'rgba(255, 107, 0, 0.1)',
    padding: 20,
    borderRadius: 10,
    marginBottom: 30,
    width: '100%',
    borderWidth: 1,
    borderColor: '#ff6b00',
  },
  infoTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#ff6b00',
    marginBottom: 15,
  },
  infoText: {
    fontSize: 16,
    color: '#ddd',
    marginBottom: 8,
  },
  toggleContainer: {
    marginBottom: 30,
    alignItems: 'center',
  },
  toggleLabel: {
    fontSize: 16,
    color: '#fff',
    marginBottom: 10,
  },
  toggleButtons: {
    flexDirection: 'row',
    gap: 10,
  },
  toggleButton: {
    paddingVertical: 10,
    paddingHorizontal: 30,
    borderRadius: 20,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderWidth: 2,
    borderColor: 'rgba(255, 255, 255, 0.3)',
  },
  toggleButtonActive: {
    backgroundColor: '#ff6b00',
    borderColor: '#ff6b00',
  },
  toggleButtonText: {
    fontSize: 16,
    color: '#fff',
  },
  toggleButtonTextActive: {
    fontWeight: 'bold',
  },
  startButton: {
    backgroundColor: '#ff6b00',
    paddingVertical: 15,
    paddingHorizontal: 40,
    borderRadius: 30,
    marginBottom: 15,
    width: '100%',
    alignItems: 'center',
  },
  startButtonText: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#fff',
  },
  uploadButtonMain: {
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    paddingVertical: 15,
    paddingHorizontal: 40,
    borderRadius: 30,
    borderWidth: 2,
    borderColor: '#ff6b00',
    width: '100%',
    alignItems: 'center',
  },
  uploadButtonMainText: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#ff6b00',
  },
  videoPreviewContainer: {
    width: '90%',
    aspectRatio: 9/16,
    backgroundColor: '#111',
    borderRadius: 10,
    overflow: 'hidden',
    marginBottom: 20,
  },
  videoPreview: {
    flex: 1,
  },
  loader: {
    marginVertical: 20,
  },
  analyzingText: {
    fontSize: 20,
    color: '#fff',
    marginTop: 20,
    fontWeight: 'bold',
  },
  analyzingSubtext: {
    fontSize: 14,
    color: '#999',
    marginTop: 10,
  },
  analyzingNote: {
    fontSize: 14,
    color: '#aaa',
    marginTop: 20,
    textAlign: 'left',
    lineHeight: 24,
  },
  resultContainer: {
    padding: 20,
  },
  videoReplayContainer: {
    marginBottom: 20,
  },
  videoReplayLabel: {
    fontSize: 16,
    color: '#fff',
    marginBottom: 10,
    fontWeight: 'bold',
  },
  videoReplay: {
    width: '100%',
    aspectRatio: 9/16,
    backgroundColor: '#111',
    borderRadius: 10,
  },
  statsCard: {
    backgroundColor: 'rgba(255, 107, 0, 0.1)',
    padding: 20,
    borderRadius: 10,
    marginBottom: 15,
    borderWidth: 1,
    borderColor: '#ff6b00',
  },
  statsTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#ff6b00',
    marginBottom: 15,
  },
  statRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  statLabel: {
    fontSize: 16,
    color: '#ddd',
  },
  statValue: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#fff',
  },
  statMade: {
    color: '#00ff00',
  },
  statMissed: {
    color: '#ff6666',
  },
  feedbackCard: {
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    padding: 20,
    borderRadius: 10,
    marginBottom: 15,
  },
  feedbackLabel: {
    fontSize: 16,
    color: '#ff6b00',
    marginBottom: 10,
    fontWeight: 'bold',
  },
  feedbackText: {
    fontSize: 16,
    color: '#fff',
    lineHeight: 24,
  },
  shotsCard: {
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    padding: 15,
    borderRadius: 10,
    marginBottom: 15,
  },
  shotsTitle: {
    fontSize: 16,
    color: '#ff6b00',
    marginBottom: 15,
    fontWeight: 'bold',
  },
  shotsScroll: {
    marginHorizontal: -5,
  },
  shotItem: {
    marginRight: 10,
    alignItems: 'center',
    position: 'relative',
  },
  shotThumbnail: {
    width: 100,
    height: 133,
    borderRadius: 8,
    backgroundColor: '#222',
  },
  shotBadge: {
    position: 'absolute',
    top: 5,
    right: 5,
    width: 24,
    height: 24,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },
  shotBadgeMade: {
    backgroundColor: '#00ff00',
  },
  shotBadgeMissed: {
    backgroundColor: '#ff0000',
  },
  shotBadgeText: {
    color: '#000',
    fontSize: 14,
    fontWeight: 'bold',
  },
  shotNumber: {
    fontSize: 12,
    color: '#aaa',
    marginTop: 5,
  },
  shotRating: {
    fontSize: 11,
    color: '#ff6b00',
    fontWeight: 'bold',
  },
  shotCue: {
    fontSize: 10,
    color: '#999',
    textAlign: 'center',
    marginTop: 2,
  },
  formCard: {
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    padding: 15,
    borderRadius: 10,
    marginBottom: 15,
  },
  formTitle: {
    fontSize: 16,
    color: '#ff6b00',
    marginBottom: 10,
    fontWeight: 'bold',
  },
  formRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  formLabel: {
    fontSize: 14,
    color: '#ddd',
  },
  formValue: {
    fontSize: 14,
    color: '#fff',
    fontWeight: 'bold',
  },
  drillsCard: {
    backgroundColor: 'rgba(255, 107, 0, 0.1)',
    padding: 20,
    borderRadius: 10,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#ff6b00',
  },
  drillsTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#ff6b00',
    marginBottom: 15,
  },
  drillItem: {
    flexDirection: 'row',
    marginBottom: 12,
  },
  drillNumber: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: '#ff6b00',
    color: '#fff',
    textAlign: 'center',
    lineHeight: 24,
    fontWeight: 'bold',
    marginRight: 10,
  },
  drillText: {
    flex: 1,
    fontSize: 14,
    color: '#fff',
    lineHeight: 24,
  },
  recordButton: {
    backgroundColor: '#ff6b00',
    padding: 15,
    borderRadius: 10,
    alignItems: 'center',
    marginBottom: 10,
  },
  recordButtonText: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#fff',
  },
  uploadButton: {
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    padding: 15,
    borderRadius: 10,
    alignItems: 'center',
    borderWidth: 2,
    borderColor: '#ff6b00',
  },
  uploadButtonText: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#ff6b00',
  },
  errorTitle: {
    fontSize: 32,
    color: '#ff0000',
    marginBottom: 20,
  },
  errorText: {
    fontSize: 16,
    color: '#fff',
    textAlign: 'center',
    marginBottom: 30,
    paddingHorizontal: 20,
  },
  retryButton: {
    backgroundColor: '#ff6b00',
    paddingVertical: 15,
    paddingHorizontal: 40,
    borderRadius: 30,
  },
  retryButtonText: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#fff',
  },
});