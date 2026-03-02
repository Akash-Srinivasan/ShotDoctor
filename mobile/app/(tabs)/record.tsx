/**
 * Record Screen - FIXED
 * Video recording and analysis with database integration
 * 
 * FIXES:
 * - Fixed video player cleanup with proper error handling
 * - Fixed ScrollView style issue (removed layout props from style prop)
 * - Added SafeAreaView for iOS notch/camera island support
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useFocusEffect } from 'expo-router';
import {
  View,
  Text,
  StyleSheet,
  ActivityIndicator,
  ScrollView,
  TouchableOpacity,
  Image,
  Alert,
  Modal,
  Dimensions,
  Animated,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { VideoView, useVideoPlayer } from 'expo-video';
import * as ImagePicker from 'expo-image-picker';
import { RecordingCamera } from '../../components/Camera';
import { ShotMarkerTimeline } from '../../components/ShotMarkerTimeline';
import { RimCalibrationOverlay, type RimPosition } from '../../components/RimCalibrationOverlay';
import { analyzeVideoWithProgress, type SessionSummary, type AnalysisProgress, type ShotAnalysis, type UserContext } from '../../lib/api';
import { useAuth } from '../../contexts/AuthContext';
import { useFingerprint } from '../../contexts/FingerprintContext';
import { ErrorBoundary } from '../../components/ErrorBoundary';
import { db } from '../../lib/supabase';

function RecordScreen() {
  // Auth context
  const { user, profile } = useAuth();
  const { refreshFingerprint } = useFingerprint();
  
  // UI State
  const [showCamera, setShowCamera] = useState(false);
  const [showCalibration, setShowCalibration] = useState(false);
  const [pendingVideoUri, setPendingVideoUri] = useState<string | null>(null);
  const [rimPosition, setRimPosition] = useState<RimPosition | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<SessionSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [shootingSide, setShootingSide] = useState<'left' | 'right'>(
    profile?.shooting_hand || 'right'
  );
  const [currentVideoUri, setCurrentVideoUri] = useState<string | null>(null);
  const [analysisProgress, setAnalysisProgress] = useState<AnalysisProgress>({
    stage: 'uploading',
    progress: 0,
    message: 'Preparing...',
  });
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [videoDuration, setVideoDuration] = useState<number>(0);

  // Shot detail modal state
  const [selectedShot, setSelectedShot] = useState<ShotAnalysis | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [modalAnimation] = useState(new Animated.Value(0));

  // Update shooting side from profile when it loads
  useEffect(() => {
    if (profile?.shooting_hand) {
      setShootingSide(profile.shooting_hand);
    }
  }, [profile?.shooting_hand]);

  // Track if we've left this screen while showing results
  const hadResultOnBlur = useRef(false);

  // Reset state when returning to this screen after viewing results
  // This ensures "Start Recording" from Home always starts fresh
  useFocusEffect(
    useCallback(() => {
      // On focus: if we previously had results and left, reset now
      if (hadResultOnBlur.current) {
        setResult(null);
        setError(null);
        setCurrentVideoUri(null);
        setRimPosition(null);
        setShowCamera(false);
        setShowCalibration(false);
        hadResultOnBlur.current = false;
      }

      // On blur: remember if we had results showing
      return () => {
        if (result && !analyzing) {
          hadResultOnBlur.current = true;
        }
      };
    }, [result, analyzing])
  );

  // Video players
  const previewPlayer = useVideoPlayer(currentVideoUri || '', (player) => {
    player.loop = true;
    player.play();
  });

  const replayPlayer = useVideoPlayer(currentVideoUri || '', (player) => {
    player.loop = false;
  });

  // Cleanup on unmount - pause players when component unmounts
  useEffect(() => {
    return () => {
      // Cleanup: pause both players on unmount
      try {
        if (previewPlayer && previewPlayer.playing) {
          previewPlayer.pause();
        }
        if (replayPlayer && replayPlayer.playing) {
          replayPlayer.pause();
        }
      } catch (error) {
        // Ignore cleanup errors
        console.log('Player cleanup error (safe to ignore):', error);
      }
    };
  }, [previewPlayer, replayPlayer]);

  // Track video duration from replay player
  useEffect(() => {
    if (replayPlayer && replayPlayer.duration > 0) {
      setVideoDuration(replayPlayer.duration);
    }
  }, [replayPlayer, replayPlayer?.duration]);

  // Seek handler for timeline markers
  const handleTimelineSeek = useCallback((timestamp: number) => {
    if (replayPlayer) {
      replayPlayer.currentTime = timestamp;
      replayPlayer.play();
    }
  }, [replayPlayer]);

  // Open shot detail modal with animation
  const openShotModal = useCallback((shot: ShotAnalysis) => {
    setSelectedShot(shot);
    setModalVisible(true);
    Animated.spring(modalAnimation, {
      toValue: 1,
      useNativeDriver: true,
      tension: 50,
      friction: 7,
    }).start();
  }, [modalAnimation]);

  // Close shot detail modal with animation
  const closeShotModal = useCallback(() => {
    Animated.timing(modalAnimation, {
      toValue: 0,
      duration: 200,
      useNativeDriver: true,
    }).start(() => {
      setModalVisible(false);
      setSelectedShot(null);
    });
  }, [modalAnimation]);

  // Handle video from camera - show calibration first
  const handleVideoRecorded = useCallback(async (uri: string) => {
    console.log('📹 Video recorded:', uri);
    setShowCamera(false);
    setPendingVideoUri(uri);
    setShowCalibration(true);
  }, []);

  // Handle rim calibration confirmation
  const handleRimConfirm = useCallback(async (position: RimPosition) => {
    console.log('🎯 Rim position set:', position);
    setRimPosition(position);
    setShowCalibration(false);
    if (pendingVideoUri) {
      setCurrentVideoUri(pendingVideoUri);
      await analyzeVideoFile(pendingVideoUri, position);
    }
  }, [pendingVideoUri, shootingSide, user]);

  // Handle rim calibration skip
  const handleRimSkip = useCallback(async () => {
    console.log('⏭️ Rim calibration skipped');
    setRimPosition(null);
    setShowCalibration(false);
    if (pendingVideoUri) {
      setCurrentVideoUri(pendingVideoUri);
      await analyzeVideoFile(pendingVideoUri, null);
    }
  }, [pendingVideoUri, shootingSide, user]);

  // Handle rim not visible in video
  const handleRimNotVisible = useCallback(async () => {
    console.log('👁️ Rim marked as not visible');
    setRimPosition(null);
    setShowCalibration(false);
    if (pendingVideoUri) {
      setCurrentVideoUri(pendingVideoUri);
      // Pass null - backend will know to not guess make/miss
      await analyzeVideoFile(pendingVideoUri, null);
    }
  }, [pendingVideoUri, shootingSide, user]);

  // Handle change video - go back to select a different video
  const handleChangeVideo = useCallback(() => {
    console.log('🔄 Changing video');
    setPendingVideoUri(null);
    setCurrentVideoUri(null);
    setRimPosition(null);
    setShowCalibration(false);
  }, []);

  // Handle video from library - show calibration first
  const handlePickVideo = useCallback(async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission needed', 'Please grant access to your photos');
      return;
    }

    const pickerResult = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['videos'],
      allowsEditing: false,
      quality: 1,
    });

    if (!pickerResult.canceled && pickerResult.assets[0]) {
      const uri = pickerResult.assets[0].uri;
      console.log('📁 Video selected:', uri);
      setPendingVideoUri(uri);
      setShowCalibration(true);
    }
  }, []);

  // Core analysis function
  const analyzeVideoFile = async (uri: string, rimPos: RimPosition | null = null) => {
    setAnalyzing(true);
    setError(null);
    setResult(null);
    setAnalysisProgress({
      stage: 'uploading',
      progress: 10,
      message: 'Uploading video...',
    });

    let newSessionId: string | null = null;

    try {
      // Create session in database (if user is logged in)
      if (user) {
        try {
          const session = await db.createSession({
            shooting_hand: shootingSide,
            focus_area: profile?.focus_areas?.[0] || undefined,
          });
          newSessionId = session.id;
          setSessionId(session.id);
        } catch (dbError) {
          console.warn('Could not create session in database:', dbError);
          // Continue without database - analysis still works
        }
      }

      // Build user context for personalized analysis
      const userContext: UserContext = {
        skill_level: profile?.skill_level || undefined,
        focus_areas: profile?.focus_areas?.join(', ') || undefined,
        height_inches: profile?.height_inches || undefined,
        user_id: user?.id || undefined,
      };

      // Call API with real progress polling
      console.log('📤 Sending to API for analysis...');
      console.log('🎯 Rim position:', rimPos ? `(${rimPos.x.toFixed(3)}, ${rimPos.y.toFixed(3)})` : 'not set');
      const analysis = await analyzeVideoWithProgress(
        uri,
        shootingSide,
        (progress) => setAnalysisProgress(progress),
        rimPos,
        undefined,
        newSessionId || undefined,
        userContext
      );
      console.log('✅ Analysis complete:', analysis.total_shots, 'shots');

      // Save results to database
      if (user && newSessionId) {
        try {
          if (analysis.server_persisted) {
            // Server already wrote session + shots — just upload thumbnails
            console.log('✓ Server persisted results — skipping client DB writes');
            for (const shot of analysis.shots) {
              if (shot.thumbnail) {
                try {
                  await db.uploadThumbnail(newSessionId!, shot.shot_number, shot.thumbnail);
                } catch (thumbErr) {
                  console.warn(`Thumbnail upload failed for shot ${shot.shot_number}:`, thumbErr);
                }
              }
            }
          } else {
            // Fallback: server didn't persist, write everything client-side
            console.log('⚠️ Server did not persist — writing client-side');
            await db.updateSession(newSessionId, {
              ended_at: new Date().toISOString(),
              shot_count: analysis.total_shots,
              make_count: analysis.shots_made,
              miss_count: analysis.shots_missed,
              shooting_percentage: analysis.shooting_percentage,
              average_form_rating: analysis.average_form_rating,
              session_feedback: analysis.session_feedback,
              drill_suggestions: analysis.drill_suggestions,
            });

            const shotRecords = await Promise.all(
              analysis.shots.map(async (shot) => {
                let thumbnailUrl: string | null = null;
                if (shot.thumbnail) {
                  try {
                    thumbnailUrl = await db.uploadThumbnail(
                      newSessionId!,
                      shot.shot_number,
                      shot.thumbnail
                    );
                  } catch (thumbErr) {
                    console.warn(`Thumbnail upload failed for shot ${shot.shot_number}:`, thumbErr);
                  }
                }
                return {
                  session_id: newSessionId!,
                  shot_number: shot.shot_number,
                  made: shot.made,
                  miss_type: shot.miss_type,
                  elbow_angle_load: shot.elbow_angle_load,
                  elbow_angle_release: shot.elbow_angle_release,
                  wrist_height_release: shot.wrist_height_release,
                  knee_bend_load: shot.knee_bend_load,
                  hip_angle_load: shot.hip_angle_load,
                  elbow_height_load: shot.elbow_height_load,
                  heel_height_release: shot.heel_height_release,
                  trunk_lean_release: shot.trunk_lean_release,
                  stance_width: shot.stance_width,
                  shoulder_level_diff: shot.shoulder_level_diff,
                  elbow_lateral_offset: shot.elbow_lateral_offset,
                  form_rating: shot.form_rating,
                  feedback: shot.feedback,
                  key_issue: shot.key_issue,
                  quick_cue: shot.quick_cue,
                  camera_angle: shot.camera_angle,
                  thumbnail_url: thumbnailUrl,
                };
              })
            );

            await db.createShots(shotRecords);
          }
          console.log('💾 Session saved to database');

          // Refresh fingerprint in background so home screen shows updated data
          refreshFingerprint().catch(() => {});
        } catch (dbError) {
          console.warn('Could not save session to database:', dbError);
          // Don't fail the whole analysis if DB save fails
        }
      }

      setResult(analysis);
      setAnalysisProgress({
        stage: 'complete',
        progress: 100,
        message: 'Analysis complete!',
        shotsFound: analysis.total_shots,
      });

    } catch (err: unknown) {
      console.error('❌ Analysis error:', err);
      const errorMessage = err instanceof Error ? err.message : 'Failed to analyze video';

      // Server finished but connection was lost — redirect to history
      const isConnectionLost = err instanceof Error && err.message === 'ANALYSIS_COMPLETE_CONNECTION_LOST';
      if (isConnectionLost) {
        setAnalysisProgress({
          stage: 'complete',
          progress: 100,
          message: 'Analysis complete! Redirecting...',
        });
        // Session data was saved server-side, navigate to history
        router.push('/(tabs)/history');
        return;
      }

      setError(errorMessage);

      // Only clean up the session if it was NOT a timeout/connection issue
      // These mean the API may still be running — the session could be populated later
      const isServerStillProcessing = err instanceof Error &&
        (err.message.includes('timed out') || err.message.includes('still processing'));
      if (newSessionId && user && !isServerStillProcessing) {
        try {
          await db.deleteSession(newSessionId);
        } catch {
          // Ignore cleanup errors
        }
      }
    } finally {
      setAnalyzing(false);
    }
  };

  const handleCancel = useCallback(() => {
    setShowCamera(false);
  }, []);

  const startNewRecording = useCallback(() => {
    setResult(null);
    setError(null);
    setCurrentVideoUri(null);
    setPendingVideoUri(null);
    setRimPosition(null);
    setSessionId(null);
    setShowCamera(true);
  }, []);

  const startVideoUpload = useCallback(() => {
    setResult(null);
    setError(null);
    setCurrentVideoUri(null);
    setPendingVideoUri(null);
    setRimPosition(null);
    setSessionId(null);
    handlePickVideo();
  }, [handlePickVideo]);

  // ============================================================================
  // Render: Camera
  // ============================================================================

  if (showCamera) {
    return (
      <RecordingCamera
        onVideoRecorded={handleVideoRecorded}
        onCancel={handleCancel}
      />
    );
  }

  // ============================================================================
  // Render: Rim Calibration
  // ============================================================================

  if (showCalibration) {
    return (
      <SafeAreaView style={styles.safeArea} edges={['top', 'bottom']}>
        <RimCalibrationOverlay
          onConfirm={handleRimConfirm}
          onRimNotVisible={handleRimNotVisible}
          onSkip={handleRimSkip}
          onChangeVideo={handleChangeVideo}
          videoUri={pendingVideoUri}
        />
      </SafeAreaView>
    );
  }

  // ============================================================================
  // Render: Analyzing
  // ============================================================================
  
  if (analyzing) {
    return (
      <SafeAreaView style={styles.safeArea} edges={['top', 'bottom']}>
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
        
        <Text style={styles.analyzingText}>{analysisProgress.message}</Text>
        
        {/* Progress bar */}
        <View style={styles.progressBarContainer}>
          <View 
            style={[
              styles.progressBar, 
              { width: `${analysisProgress.progress}%` }
            ]} 
          />
        </View>
        
        <Text style={styles.analyzingSubtext}>
          {analysisProgress.frame && analysisProgress.totalFrames
            ? `Frame ${analysisProgress.frame} / ${analysisProgress.totalFrames}`
            : 'This may take 30-90 seconds'}
          {analysisProgress.shotsFound ? ` — ${analysisProgress.shotsFound} shot${analysisProgress.shotsFound !== 1 ? 's' : ''} found` : ''}
        </Text>
        
        <Text style={styles.analyzingNote}>
          • Scanning entire video{'\n'}
          • Detecting all shots{'\n'}
          • Measuring form metrics{'\n'}
          • Getting AI coaching
        </Text>
        </View>
      </SafeAreaView>
    );
  }

  // ============================================================================
  // Render: Results
  // ============================================================================
  
  if (result) {
    const goodShots = result.shots.filter(s => s.form_rating && s.form_rating >= 7).length;
    const needsWork = result.shots.filter(s => s.form_rating && s.form_rating < 7).length;

    return (
      <SafeAreaView style={styles.safeArea} edges={['top', 'bottom']}>
        <ScrollView style={styles.scrollViewContainer} contentContainerStyle={styles.resultContainer}>
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
            {/* Shot Marker Timeline */}
            <ShotMarkerTimeline
              shots={result.shots}
              videoDuration={videoDuration}
              onSeek={handleTimelineSeek}
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

          {/* Only show make/miss stats if rim was tracked */}
          {(result.shots_made > 0 || result.shots_missed > 0) ? (
            <>
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
            </>
          ) : (
            <View style={styles.statRow}>
              <Text style={styles.statLabel}>Accuracy:</Text>
              <Text style={[styles.statValue, { color: '#888' }]}>N/A (no rim marked)</Text>
            </View>
          )}

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
          <Text style={styles.shotsSubtitle}>Tap to expand</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.shotsScroll}>
            {result.shots.map((shot) => (
              <TouchableOpacity
                key={shot.shot_number}
                style={styles.shotItem}
                onPress={() => openShotModal(shot)}
                activeOpacity={0.7}
              >
                <Image
                  source={{ uri: `data:image/jpeg;base64,${shot.thumbnail}` }}
                  style={styles.shotThumbnail}
                />
                <View
                  style={[
                    styles.shotBadge,
                    shot.made === true ? styles.shotBadgeMade :
                    shot.made === false ? styles.shotBadgeMissed :
                    styles.shotBadgeUnknown,
                  ]}
                >
                  <Text style={styles.shotBadgeText}>
                    {shot.made === true ? '✓' : shot.made === false ? '✗' : '?'}
                  </Text>
                </View>
                <View style={styles.expandIndicator}>
                  <Text style={styles.expandIndicatorText}>+</Text>
                </View>
                <Text style={styles.shotNumber}>Shot {shot.shot_number}</Text>
                {shot.camera_angle && (
                  <Text style={styles.shotAngleLabel}>{shot.camera_angle.toUpperCase()}</Text>
                )}
                {shot.form_rating && (
                  <Text style={styles.shotRating}>{shot.form_rating}/10</Text>
                )}
              </TouchableOpacity>
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

      {/* Shot Detail Modal */}
      <Modal
        visible={modalVisible}
        transparent={true}
        animationType="fade"
        onRequestClose={closeShotModal}
      >
        <View style={styles.modalOverlay}>
          {/* Backdrop - tap to close */}
          <TouchableOpacity
            style={StyleSheet.absoluteFill}
            activeOpacity={1}
            onPress={closeShotModal}
          />

          {/* Modal Content */}
          {selectedShot && (
            <View style={styles.modalContent}>
              {/* Close Button */}
              <TouchableOpacity style={styles.modalCloseButton} onPress={closeShotModal}>
                <Text style={styles.modalCloseText}>✕</Text>
              </TouchableOpacity>

              <ScrollView
                contentContainerStyle={styles.modalScrollContent}
                showsVerticalScrollIndicator={true}
              >
                {/* Full Size Image */}
                <Image
                  source={{ uri: `data:image/jpeg;base64,${selectedShot.thumbnail}` }}
                  style={styles.modalImage}
                  resizeMode="contain"
                />

                {/* Shot Header */}
                <View style={styles.modalHeader}>
                  <Text style={styles.modalTitle}>Shot {selectedShot.shot_number}</Text>
                  <View style={styles.modalBadges}>
                    {selectedShot.camera_angle && (
                      <View style={styles.modalAngleBadge}>
                        <Text style={styles.modalAngleText}>
                          {selectedShot.camera_angle.toUpperCase()}
                        </Text>
                      </View>
                    )}
                    <View
                      style={[
                        styles.modalResultBadge,
                        selectedShot.made === true ? styles.modalBadgeMade :
                        selectedShot.made === false ? styles.modalBadgeMissed :
                        styles.modalBadgeUnknown,
                      ]}
                    >
                      <Text style={styles.modalResultText}>
                        {selectedShot.made === true ? 'MADE' :
                         selectedShot.made === false ? 'MISSED' : 'N/A'}
                      </Text>
                    </View>
                  </View>
                </View>

                {/* Form Rating */}
                {selectedShot.form_rating && (
                  <View style={styles.modalRatingContainer}>
                    <Text style={styles.modalRatingLabel}>Form Rating</Text>
                    <View style={styles.modalRatingBar}>
                      <View
                        style={[
                          styles.modalRatingFill,
                          { width: `${selectedShot.form_rating * 10}%` },
                          selectedShot.form_rating >= 7
                            ? styles.ratingGood
                            : selectedShot.form_rating >= 5
                            ? styles.ratingOkay
                            : styles.ratingPoor,
                        ]}
                      />
                    </View>
                    <Text style={styles.modalRatingValue}>{selectedShot.form_rating}/10</Text>
                  </View>
                )}

                {/* Key Issue */}
                {selectedShot.key_issue && selectedShot.key_issue !== 'none' && (
                  <View style={styles.modalIssueCard}>
                    <Text style={styles.modalIssueLabel}>Area to Fix</Text>
                    <Text style={styles.modalIssueText}>{selectedShot.key_issue}</Text>
                  </View>
                )}

                {/* Quick Cue */}
                {selectedShot.quick_cue && (
                  <View style={styles.modalCueCard}>
                    <Text style={styles.modalCueLabel}>Quick Cue</Text>
                    <Text style={styles.modalCueText}>"{selectedShot.quick_cue}"</Text>
                  </View>
                )}

                {/* Feedback */}
                {selectedShot.feedback && (
                  <View style={styles.modalFeedbackCard}>
                    <Text style={styles.modalFeedbackLabel}>Coach Feedback</Text>
                    <Text style={styles.modalFeedbackText}>{selectedShot.feedback}</Text>
                  </View>
                )}
              </ScrollView>
            </View>
          )}
        </View>
      </Modal>
      </SafeAreaView>
    );
  }

  // ============================================================================
  // Render: Error
  // ============================================================================
  
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

  // ============================================================================
  // Render: Record Screen (Camera-Centric Design)
  // ============================================================================

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'bottom']}>
      <ScrollView
        style={styles.recordScrollView}
        contentContainerStyle={styles.recordScrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <View style={styles.recordHeader}>
          <Text style={styles.recordHeaderTitle}>Record Session</Text>
          <Text style={styles.recordHeaderSubtitle}>Analyze your shooting form</Text>
        </View>

        {/* Camera Viewfinder Area */}
        <View style={styles.viewfinderContainer}>
          {/* Viewfinder Frame */}
          <View style={styles.viewfinder}>
            {/* Corner Brackets */}
            <View style={[styles.cornerBracket, styles.cornerTopLeft]} />
            <View style={[styles.cornerBracket, styles.cornerTopRight]} />
            <View style={[styles.cornerBracket, styles.cornerBottomLeft]} />
            <View style={[styles.cornerBracket, styles.cornerBottomRight]} />

            {/* Center Target */}
            <View style={styles.targetContainer}>
              <View style={styles.targetRing}>
                <View style={styles.targetCenter} />
              </View>
              <Text style={styles.targetText}>Position yourself in frame</Text>
            </View>
          </View>

          {/* Recording Tips */}
          <View style={styles.tipsBanner}>
            <Text style={styles.tipsBannerText}>Full body visible  |  Good lighting  |  Stable camera</Text>
          </View>
        </View>

        {/* Shooting Hand Toggle */}
        <View style={styles.handToggleContainer}>
          <Text style={styles.handToggleLabel}>Shooting Hand</Text>
          <View style={styles.handToggleButtons}>
            <TouchableOpacity
              style={[
                styles.handToggleButton,
                shootingSide === 'left' && styles.handToggleButtonActive,
              ]}
              onPress={() => setShootingSide('left')}
            >
              <Text
                style={[
                  styles.handToggleText,
                  shootingSide === 'left' && styles.handToggleTextActive,
                ]}
              >
                LEFT
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[
                styles.handToggleButton,
                shootingSide === 'right' && styles.handToggleButtonActive,
              ]}
              onPress={() => setShootingSide('right')}
            >
              <Text
                style={[
                  styles.handToggleText,
                  shootingSide === 'right' && styles.handToggleTextActive,
                ]}
              >
                RIGHT
              </Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Main Record Button */}
        <TouchableOpacity style={styles.mainRecordButton} onPress={startNewRecording}>
          <View style={styles.recordButtonOuter}>
            <View style={styles.recordButtonInner}>
              <View style={styles.recordButtonCenter} />
            </View>
          </View>
          <Text style={styles.mainRecordText}>TAP TO RECORD</Text>
        </TouchableOpacity>

        {/* Upload Option */}
        <TouchableOpacity style={styles.uploadOption} onPress={startVideoUpload}>
          <View style={styles.uploadIconContainer}>
            <Text style={styles.uploadIcon}>📁</Text>
          </View>
          <Text style={styles.uploadOptionText}>Upload existing video</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

export default function RecordScreenWithBoundary() {
  return (
    <ErrorBoundary>
      <RecordScreen />
    </ErrorBoundary>
  );
}

// ============================================================================
// Styles
// ============================================================================

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#000',
  },
  container: {
    flex: 1,
    backgroundColor: '#000',
    justifyContent: 'center',
    alignItems: 'center',
  },
  scrollViewContainer: {
    flex: 1,
    backgroundColor: '#000',
  },
  // ============================================================================
  // Record Screen (Camera-Centric) Styles
  // ============================================================================
  recordScrollView: {
    flex: 1,
    backgroundColor: '#000',
  },
  recordScrollContent: {
    paddingHorizontal: 20,
    paddingTop: 10,
    paddingBottom: 40,
  },
  recordHeader: {
    alignItems: 'center',
    marginBottom: 15,
  },
  recordHeaderTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#FF4D00',
  },
  recordHeaderSubtitle: {
    fontSize: 14,
    color: '#888',
    marginTop: 4,
  },
  viewfinderContainer: {
    alignItems: 'center',
    marginBottom: 20,
  },
  viewfinder: {
    width: '100%',
    aspectRatio: 4 / 3,
    backgroundColor: '#0a0a0a',
    borderRadius: 20,
    borderWidth: 2,
    borderColor: '#333',
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
    position: 'relative',
  },
  cornerBracket: {
    position: 'absolute',
    width: 40,
    height: 40,
    borderColor: '#FF4D00',
  },
  cornerTopLeft: {
    top: 15,
    left: 15,
    borderTopWidth: 3,
    borderLeftWidth: 3,
    borderTopLeftRadius: 8,
  },
  cornerTopRight: {
    top: 15,
    right: 15,
    borderTopWidth: 3,
    borderRightWidth: 3,
    borderTopRightRadius: 8,
  },
  cornerBottomLeft: {
    bottom: 15,
    left: 15,
    borderBottomWidth: 3,
    borderLeftWidth: 3,
    borderBottomLeftRadius: 8,
  },
  cornerBottomRight: {
    bottom: 15,
    right: 15,
    borderBottomWidth: 3,
    borderRightWidth: 3,
    borderBottomRightRadius: 8,
  },
  targetContainer: {
    alignItems: 'center',
  },
  targetRing: {
    width: 60,
    height: 60,
    borderRadius: 30,
    borderWidth: 2,
    borderColor: 'rgba(255, 77, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  targetCenter: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: '#FF4D00',
  },
  targetText: {
    marginTop: 12,
    fontSize: 14,
    color: '#666',
    fontWeight: '500',
  },
  tipsBanner: {
    marginTop: 12,
    paddingVertical: 8,
    paddingHorizontal: 16,
    backgroundColor: 'rgba(255, 77, 0, 0.1)',
    borderRadius: 20,
  },
  tipsBannerText: {
    fontSize: 11,
    color: '#888',
    textAlign: 'center',
  },
  handToggleContainer: {
    alignItems: 'center',
    marginBottom: 25,
  },
  handToggleLabel: {
    fontSize: 13,
    color: '#666',
    marginBottom: 10,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  handToggleButtons: {
    flexDirection: 'row',
    backgroundColor: '#1a1a1a',
    borderRadius: 25,
    padding: 4,
  },
  handToggleButton: {
    paddingVertical: 10,
    paddingHorizontal: 30,
    borderRadius: 20,
  },
  handToggleButtonActive: {
    backgroundColor: '#FF4D00',
  },
  handToggleText: {
    fontSize: 13,
    color: '#666',
    fontWeight: '600',
    letterSpacing: 1,
  },
  handToggleTextActive: {
    color: '#fff',
  },
  mainRecordButton: {
    alignItems: 'center',
    marginBottom: 20,
  },
  recordButtonOuter: {
    width: 90,
    height: 90,
    borderRadius: 45,
    borderWidth: 4,
    borderColor: '#FF4D00',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 10,
  },
  recordButtonInner: {
    width: 74,
    height: 74,
    borderRadius: 37,
    backgroundColor: 'rgba(255, 77, 0, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  recordButtonCenter: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#FF4D00',
  },
  mainRecordText: {
    fontSize: 14,
    color: '#FF4D00',
    fontWeight: 'bold',
    letterSpacing: 2,
  },
  uploadOption: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
  },
  uploadIconContainer: {
    width: 28,
    height: 28,
    borderRadius: 14,
    borderWidth: 2,
    borderColor: '#444',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 10,
  },
  uploadIcon: {
    fontSize: 16,
    color: '#666',
    fontWeight: 'bold',
  },
  uploadOptionText: {
    fontSize: 14,
    color: '#666',
  },
  videoPreviewContainer: {
    width: '90%',
    aspectRatio: 9 / 16,
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
  progressBarContainer: {
    width: '80%',
    height: 6,
    backgroundColor: 'rgba(255, 255, 255, 0.2)',
    borderRadius: 3,
    marginTop: 15,
    overflow: 'hidden',
  },
  progressBar: {
    height: '100%',
    backgroundColor: '#ff6b00',
    borderRadius: 3,
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
    aspectRatio: 9 / 16,
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
  shotBadgeUnknown: {
    backgroundColor: '#888',
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
  shotAngleLabel: {
    fontSize: 9,
    color: '#888',
    fontWeight: '600',
    letterSpacing: 0.5,
    marginTop: 2,
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
  // Modal styles
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.9)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalContent: {
    width: Dimensions.get('window').width * 0.92,
    maxHeight: Dimensions.get('window').height * 0.85,
    backgroundColor: '#1a1a1a',
    borderRadius: 20,
    overflow: 'hidden',
  },
  modalScrollContent: {
    padding: 20,
    paddingBottom: 40,
  },
  modalCloseButton: {
    position: 'absolute',
    top: 0,
    right: 0,
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 10,
  },
  modalCloseText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
  },
  modalImage: {
    width: '100%',
    height: 350,
    borderRadius: 12,
    backgroundColor: '#222',
    marginBottom: 20,
    marginTop: 30,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
  },
  modalBadges: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  modalAngleBadge: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 12,
    backgroundColor: '#333',
    borderWidth: 1,
    borderColor: '#555',
  },
  modalAngleText: {
    fontSize: 11,
    fontWeight: '600',
    color: '#aaa',
    letterSpacing: 0.5,
  },
  modalTitle: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#fff',
  },
  modalResultBadge: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
  },
  modalBadgeMade: {
    backgroundColor: '#00cc00',
  },
  modalBadgeMissed: {
    backgroundColor: '#cc0000',
  },
  modalBadgeUnknown: {
    backgroundColor: '#666',
  },
  modalResultText: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 14,
  },
  modalRatingContainer: {
    marginBottom: 20,
  },
  modalRatingLabel: {
    fontSize: 14,
    color: '#aaa',
    marginBottom: 8,
  },
  modalRatingBar: {
    height: 8,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderRadius: 4,
    overflow: 'hidden',
    marginBottom: 8,
  },
  modalRatingFill: {
    height: '100%',
    borderRadius: 4,
  },
  ratingGood: {
    backgroundColor: '#00cc00',
  },
  ratingOkay: {
    backgroundColor: '#ff6b00',
  },
  ratingPoor: {
    backgroundColor: '#cc0000',
  },
  modalRatingValue: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#ff6b00',
    textAlign: 'right',
  },
  modalDetailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.1)',
  },
  modalDetailLabel: {
    fontSize: 14,
    color: '#aaa',
  },
  modalDetailValue: {
    fontSize: 14,
    color: '#fff',
    fontWeight: '600',
  },
  modalMetricsCard: {
    backgroundColor: 'rgba(255, 107, 0, 0.1)',
    padding: 15,
    borderRadius: 12,
    marginBottom: 15,
    borderWidth: 1,
    borderColor: 'rgba(255, 107, 0, 0.3)',
  },
  modalMetricsTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#ff6b00',
    marginBottom: 12,
  },
  modalMetricRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  modalMetricLabel: {
    fontSize: 14,
    color: '#ddd',
  },
  modalMetricValue: {
    fontSize: 14,
    color: '#fff',
    fontWeight: '600',
  },
  modalIssueCard: {
    backgroundColor: 'rgba(255, 0, 0, 0.1)',
    padding: 15,
    borderRadius: 12,
    marginBottom: 15,
    borderWidth: 1,
    borderColor: 'rgba(255, 0, 0, 0.3)',
  },
  modalIssueLabel: {
    fontSize: 14,
    fontWeight: 'bold',
    color: '#ff6666',
    marginBottom: 8,
  },
  modalIssueText: {
    fontSize: 14,
    color: '#fff',
    lineHeight: 20,
  },
  modalCueCard: {
    backgroundColor: 'rgba(0, 200, 0, 0.1)',
    padding: 15,
    borderRadius: 12,
    marginBottom: 15,
    borderWidth: 1,
    borderColor: 'rgba(0, 200, 0, 0.3)',
  },
  modalCueLabel: {
    fontSize: 14,
    fontWeight: 'bold',
    color: '#00cc00',
    marginBottom: 8,
  },
  modalCueText: {
    fontSize: 18,
    color: '#fff',
    fontStyle: 'italic',
    lineHeight: 24,
  },
  modalFeedbackCard: {
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    padding: 15,
    borderRadius: 12,
    marginBottom: 15,
  },
  modalFeedbackLabel: {
    fontSize: 14,
    fontWeight: 'bold',
    color: '#aaa',
    marginBottom: 8,
  },
  modalFeedbackText: {
    fontSize: 14,
    color: '#fff',
    lineHeight: 22,
  },
  // Shots card subtitle and expand indicator
  shotsSubtitle: {
    fontSize: 12,
    color: '#666',
    marginBottom: 10,
  },
  expandIndicator: {
    position: 'absolute',
    bottom: 45,
    right: 5,
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: 'rgba(255, 107, 0, 0.9)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  expandIndicatorText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: 'bold',
  },
});