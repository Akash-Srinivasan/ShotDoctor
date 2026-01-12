import React, { useState } from 'react';
import { View, Text, StyleSheet, ActivityIndicator, ScrollView, TouchableOpacity, Image, Alert } from 'react-native';
import { VideoView, useVideoPlayer } from 'expo-video';
import * as ImagePicker from 'expo-image-picker';
import { RecordingCamera } from '../components/Camera';
import { analyzeVideo, type AnalyzeResponse } from '../lib/api';

export default function RecordScreen() {
  const [showCamera, setShowCamera] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [shootingSide, setShootingSide] = useState<'left' | 'right'>('right');
  const [currentVideoUri, setCurrentVideoUri] = useState<string | null>(null);
  
  // CRITICAL: Call ALL hooks at top level, before any conditionals
  // Video players for preview and replay
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
    // Request permission
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission needed', 'Please grant access to your photos to upload videos');
      return;
    }

    // Pick video - FIXED: Use array instead of MediaTypeOptions
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

    try {
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

  // All hooks are called above - now we can have conditionals

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
        {/* Video Preview while analyzing */}
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
        <Text style={styles.analyzingText}>Analyzing your shot...</Text>
        <Text style={styles.analyzingSubtext}>
          This may take 30-60 seconds
        </Text>
        <Text style={styles.analyzingNote}>
          • Detecting your shooting motion{'\n'}
          • Measuring form metrics{'\n'}
          • Getting AI coaching feedback
        </Text>
      </View>
    );
  }

  if (result) {
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.resultContainer}>
        {/* Video Replay */}
        {currentVideoUri && (
          <View style={styles.videoReplayContainer}>
            <Text style={styles.videoReplayLabel}>Your Shot</Text>
            <VideoView
              player={replayPlayer}
              style={styles.videoReplay}
              nativeControls={true}
              contentFit="contain"
            />
          </View>
        )}

        {/* Result Badge */}
        <View style={[
          styles.resultBadge,
          result.made ? styles.resultBadgeMade : styles.resultBadgeMissed
        ]}>
          <Text style={styles.resultBadgeText}>
            {result.made ? '✓ MADE' : '✗ MISSED'}
          </Text>
          {result.miss_type && (
            <Text style={styles.missType}>({result.miss_type})</Text>
          )}
        </View>

        {/* Form Rating */}
        {result.form_rating && (
          <View style={styles.ratingContainer}>
            <Text style={styles.ratingLabel}>Form Rating</Text>
            <Text style={styles.ratingValue}>{result.form_rating}/10</Text>
          </View>
        )}

        {/* Feedback */}
        <View style={styles.feedbackContainer}>
          <Text style={styles.feedbackLabel}>💬 Coach's Feedback</Text>
          <Text style={styles.feedbackText}>{result.feedback}</Text>
        </View>

        {/* Quick Cue */}
        {result.quick_cue && (
          <View style={styles.cueContainer}>
            <Text style={styles.cueLabel}>🎯 Remember</Text>
            <Text style={styles.cueText}>"{result.quick_cue}"</Text>
          </View>
        )}

        {/* Key Issue */}
        {result.key_issue && result.key_issue.toLowerCase() !== 'none' && (
          <View style={styles.issueContainer}>
            <Text style={styles.issueLabel}>→ Fix</Text>
            <Text style={styles.issueText}>{result.key_issue}</Text>
          </View>
        )}

        {/* Shot Frames Section */}
        {result.frames && result.frames.length > 0 && (
          <View style={styles.framesContainer}>
            <Text style={styles.framesLabel}>📸 Shot Breakdown</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              {result.frames.map((frame, index) => (
                <View key={index} style={styles.frameItem}>
                  <Image 
                    source={{ uri: `data:image/jpeg;base64,${frame.image_base64}` }} 
                    style={styles.frameImage} 
                  />
                  <Text style={styles.frameLabel}>{frame.label.replace(/_/g, ' ')}</Text>
                </View>
              ))}
            </ScrollView>
          </View>
        )}

        {/* Metrics */}
        <View style={styles.metricsContainer}>
          <Text style={styles.metricsLabel}>📊 Metrics</Text>
          <View style={styles.metricRow}>
            <Text style={styles.metricLabel}>Elbow Load:</Text>
            <Text style={styles.metricValue}>{result.elbow_angle_load.toFixed(0)}°</Text>
          </View>
          <View style={styles.metricRow}>
            <Text style={styles.metricLabel}>Elbow Release:</Text>
            <Text style={styles.metricValue}>{result.elbow_angle_release.toFixed(0)}°</Text>
          </View>
          <View style={styles.metricRow}>
            <Text style={styles.metricLabel}>Wrist Height:</Text>
            <Text style={styles.metricValue}>{result.wrist_height_release.toFixed(2)}</Text>
          </View>
          <View style={styles.metricRow}>
            <Text style={styles.metricLabel}>Knee Bend:</Text>
            <Text style={styles.metricValue}>{result.knee_bend_load.toFixed(0)}°</Text>
          </View>
        </View>

        {/* Action Buttons */}
        <TouchableOpacity style={styles.recordButton} onPress={startNewRecording}>
          <Text style={styles.recordButtonText}>📹 Record Another Shot</Text>
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

  // Default view - start recording or upload
  return (
    <View style={styles.container}>
      <View style={styles.welcomeContainer}>
        <Text style={styles.title}>🏀 FormCheck</Text>
        <Text style={styles.subtitle}>AI Basketball Coach</Text>
        
        <View style={styles.infoBox}>
          <Text style={styles.infoTitle}>How it works:</Text>
          <Text style={styles.infoText}>1. Record or upload a shot video</Text>
          <Text style={styles.infoText}>2. Our AI analyzes your form</Text>
          <Text style={styles.infoText}>3. Get instant coaching feedback</Text>
        </View>

        {/* Shooting Side Toggle */}
        <View style={styles.toggleContainer}>
          <Text style={styles.toggleLabel}>Shooting Hand:</Text>
          <View style={styles.toggleButtons}>
            <TouchableOpacity
              style={[
                styles.toggleButton,
                shootingSide === 'left' && styles.toggleButtonActive
              ]}
              onPress={() => setShootingSide('left')}
            >
              <Text style={[
                styles.toggleButtonText,
                shootingSide === 'left' && styles.toggleButtonTextActive
              ]}>
                Left
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[
                styles.toggleButton,
                shootingSide === 'right' && styles.toggleButtonActive
              ]}
              onPress={() => setShootingSide('right')}
            >
              <Text style={[
                styles.toggleButtonText,
                shootingSide === 'right' && styles.toggleButtonTextActive
              ]}>
                Right
              </Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Primary Action - Record */}
        <TouchableOpacity style={styles.startButton} onPress={startNewRecording}>
          <Text style={styles.startButtonText}>📹 Record Shot</Text>
        </TouchableOpacity>

        {/* Secondary Action - Upload */}
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
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    padding: 20,
    borderRadius: 10,
    marginBottom: 30,
    width: '100%',
  },
  infoTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#fff',
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
  resultBadge: {
    padding: 20,
    borderRadius: 10,
    alignItems: 'center',
    marginBottom: 20,
  },
  resultBadgeMade: {
    backgroundColor: 'rgba(0, 200, 0, 0.2)',
  },
  resultBadgeMissed: {
    backgroundColor: 'rgba(200, 0, 0, 0.2)',
  },
  resultBadgeText: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#fff',
  },
  missType: {
    fontSize: 16,
    color: '#aaa',
    marginTop: 5,
  },
  ratingContainer: {
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    padding: 20,
    borderRadius: 10,
    alignItems: 'center',
    marginBottom: 20,
  },
  ratingLabel: {
    fontSize: 16,
    color: '#aaa',
    marginBottom: 5,
  },
  ratingValue: {
    fontSize: 36,
    fontWeight: 'bold',
    color: '#ff6b00',
  },
  feedbackContainer: {
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
    fontSize: 18,
    color: '#fff',
    lineHeight: 26,
  },
  cueContainer: {
    backgroundColor: 'rgba(255, 107, 0, 0.1)',
    padding: 15,
    borderRadius: 10,
    marginBottom: 15,
    borderLeftWidth: 4,
    borderLeftColor: '#ff6b00',
  },
  cueLabel: {
    fontSize: 14,
    color: '#ff6b00',
    marginBottom: 5,
  },
  cueText: {
    fontSize: 20,
    color: '#fff',
    fontStyle: 'italic',
  },
  issueContainer: {
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    padding: 15,
    borderRadius: 10,
    marginBottom: 15,
  },
  issueLabel: {
    fontSize: 14,
    color: '#aaa',
    marginBottom: 5,
  },
  issueText: {
    fontSize: 16,
    color: '#fff',
  },
  framesContainer: {
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    padding: 15,
    borderRadius: 10,
    marginBottom: 15,
  },
  framesLabel: {
    fontSize: 16,
    color: '#ff6b00',
    marginBottom: 15,
    fontWeight: 'bold',
  },
  frameItem: {
    marginRight: 10,
    alignItems: 'center',
  },
  frameImage: {
    width: 120,
    height: 160,
    borderRadius: 8,
    backgroundColor: '#222',
  },
  frameLabel: {
    fontSize: 12,
    color: '#aaa',
    marginTop: 5,
  },
  metricsContainer: {
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    padding: 20,
    borderRadius: 10,
    marginBottom: 20,
  },
  metricsLabel: {
    fontSize: 16,
    color: '#ff6b00',
    marginBottom: 15,
    fontWeight: 'bold',
  },
  metricRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  metricLabel: {
    fontSize: 14,
    color: '#aaa',
  },
  metricValue: {
    fontSize: 14,
    color: '#fff',
    fontWeight: 'bold',
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