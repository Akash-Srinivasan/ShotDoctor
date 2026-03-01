/**
 * RimCalibrationOverlay Component
 * Allows user to tap on screen to mark rim position for accurate make/miss detection
 *
 * The rim position is stored as normalized coordinates (0-1 range) relative to
 * the video dimensions, making it work across different screen sizes.
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Dimensions,
  GestureResponderEvent,
  Platform,
  Image,
  ScrollView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { VideoView, useVideoPlayer } from 'expo-video';

export interface RimPosition {
  x: number; // Normalized 0-1
  y: number; // Normalized 0-1
}

interface RimCalibrationOverlayProps {
  onConfirm: (position: RimPosition) => void;
  onRimNotVisible: () => void;  // User indicates rim is not in frame
  onSkip: () => void;           // User skips calibration entirely
  onChangeVideo: () => void;    // User wants to select a different video
  videoUri?: string | null;     // Video URI to show as background
}

const SCREEN_WIDTH = Dimensions.get('window').width;

export function RimCalibrationOverlay({
  onConfirm,
  onRimNotVisible,
  onSkip,
  onChangeVideo,
  videoUri,
}: RimCalibrationOverlayProps) {
  const [rimPosition, setRimPosition] = useState<RimPosition | null>(null);

  // Video player paused at first frame
  const player = useVideoPlayer(videoUri || '', (p) => {
    p.pause();
    p.currentTime = 0;
  });

  // Calculate overlay dimensions (9:16 portrait aspect ratio)
  const overlayWidth = SCREEN_WIDTH * 0.9;
  const overlayHeight = overlayWidth * (16 / 9);

  const handleTap = (event: GestureResponderEvent) => {
    const { locationX, locationY } = event.nativeEvent;

    // Convert to normalized coordinates (0-1 range)
    const normalizedX = locationX / overlayWidth;
    const normalizedY = locationY / overlayHeight;

    // Clamp values to 0-1 range
    setRimPosition({
      x: Math.max(0, Math.min(1, normalizedX)),
      y: Math.max(0, Math.min(1, normalizedY)),
    });
  };

  const handleConfirm = () => {
    if (rimPosition) {
      onConfirm(rimPosition);
    }
  };

  const handleReset = () => {
    setRimPosition(null);
  };

  // Convert normalized position back to pixel position for marker display
  const markerPixelX = rimPosition ? rimPosition.x * overlayWidth : 0;
  const markerPixelY = rimPosition ? rimPosition.y * overlayHeight : 0;

  return (
    <ScrollView
      style={styles.scrollView}
      contentContainerStyle={styles.container}
      showsVerticalScrollIndicator={false}
    >
      {/* Change Video Button */}
      <TouchableOpacity style={styles.changeVideoButton} onPress={onChangeVideo}>
        <Ionicons name="arrow-back" size={20} color="#FF4D00" />
        <Text style={styles.changeVideoText}>Change Video</Text>
      </TouchableOpacity>

      <View style={styles.header}>
        <Text style={styles.title}>Mark the Rim</Text>
        <Text style={styles.subtitle}>
          Tap on the center of the basketball rim
        </Text>
      </View>

      {/* Tap Area */}
      <View
        style={[
          styles.tapArea,
          { width: overlayWidth, height: overlayHeight },
        ]}
        onStartShouldSetResponder={() => true}
        onResponderRelease={handleTap}
      >
        {/* Video Background */}
        {videoUri && (
          <VideoView
            player={player}
            style={StyleSheet.absoluteFill}
            nativeControls={false}
            contentFit="cover"
          />
        )}

        {/* Grid lines for guidance */}
        <View style={styles.gridContainer}>
          <View style={[styles.gridLineHorizontal, { top: '33%' }]} />
          <View style={[styles.gridLineHorizontal, { top: '66%' }]} />
          <View style={[styles.gridLineVertical, { left: '33%' }]} />
          <View style={[styles.gridLineVertical, { left: '66%' }]} />
        </View>

        {/* Rim Marker */}
        {rimPosition && (
          <View
            style={[
              styles.rimMarker,
              {
                left: markerPixelX - 30,
                top: markerPixelY - 30,
              },
            ]}
          >
            <View style={styles.rimMarkerOuter}>
              <View style={styles.rimMarkerInner}>
                <Ionicons name="basketball-outline" size={24} color="#FF4D00" />
              </View>
            </View>
            <Text style={styles.rimMarkerLabel}>RIM</Text>
          </View>
        )}

        {/* Tap Hint */}
        {!rimPosition && (
          <View style={styles.tapHint}>
            <Ionicons name="finger-print-outline" size={48} color="rgba(255, 255, 255, 0.5)" />
            <Text style={styles.tapHintText}>Tap to mark rim position</Text>
          </View>
        )}
      </View>

      {/* Instructions */}
      <View style={styles.instructions}>
        <View style={styles.instructionItem}>
          <Ionicons name="checkmark-circle" size={20} color="#10B981" />
          <Text style={styles.instructionText}>Position should be center of rim</Text>
        </View>
        <View style={styles.instructionItem}>
          <Ionicons name="checkmark-circle" size={20} color="#10B981" />
          <Text style={styles.instructionText}>Rim stays in same position during video</Text>
        </View>
      </View>

      {/* Action Buttons */}
      <View style={styles.buttonContainer}>
        {rimPosition ? (
          <>
            <TouchableOpacity
              style={styles.resetButton}
              onPress={handleReset}
            >
              <Ionicons name="refresh" size={20} color="#FF4D00" />
              <Text style={styles.resetButtonText}>Reset</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.confirmButton}
              onPress={handleConfirm}
            >
              <Ionicons name="checkmark" size={20} color="#FFF" />
              <Text style={styles.confirmButtonText}>Confirm Position</Text>
            </TouchableOpacity>
          </>
        ) : (
          <View style={styles.optionsContainer}>
            <TouchableOpacity
              style={styles.rimNotVisibleButton}
              onPress={onRimNotVisible}
            >
              <Ionicons name="eye-off-outline" size={20} color="#888" />
              <Text style={styles.rimNotVisibleText}>Rim not visible in video</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.skipButton}
              onPress={onSkip}
            >
              <Text style={styles.skipButtonText}>Skip for now</Text>
            </TouchableOpacity>
          </View>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scrollView: {
    flex: 1,
    backgroundColor: '#000',
  },
  container: {
    flexGrow: 1,
    backgroundColor: '#000',
    alignItems: 'center',
    justifyContent: 'flex-start',
    padding: 20,
    paddingTop: 10,
    paddingBottom: 40,
  },
  changeVideoButton: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    paddingVertical: 8,
    paddingHorizontal: 4,
    marginBottom: 10,
    gap: 6,
  },
  changeVideoText: {
    fontSize: 16,
    color: '#FF4D00',
    fontWeight: '500',
  },
  header: {
    alignItems: 'center',
    marginBottom: 24,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: '#FFF',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: '#888',
    textAlign: 'center',
  },
  tapArea: {
    backgroundColor: '#111',
    borderRadius: 16,
    borderWidth: 2,
    borderColor: '#333',
    borderStyle: 'dashed',
    overflow: 'hidden',
    position: 'relative',
  },
  gridContainer: {
    ...StyleSheet.absoluteFillObject,
  },
  gridLineHorizontal: {
    position: 'absolute',
    left: 0,
    right: 0,
    height: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
  },
  gridLineVertical: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    width: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
  },
  tapHint: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  tapHintText: {
    fontSize: 14,
    color: 'rgba(255, 255, 255, 0.5)',
    marginTop: 12,
  },
  rimMarker: {
    position: 'absolute',
    alignItems: 'center',
  },
  rimMarkerOuter: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: 'rgba(255, 77, 0, 0.2)',
    borderWidth: 2,
    borderColor: '#FF4D00',
    justifyContent: 'center',
    alignItems: 'center',
    ...Platform.select({
      ios: {
        shadowColor: '#FF4D00',
        shadowOffset: { width: 0, height: 0 },
        shadowOpacity: 0.5,
        shadowRadius: 10,
      },
      android: {
        elevation: 8,
      },
    }),
  },
  rimMarkerInner: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(255, 77, 0, 0.3)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  rimMarkerLabel: {
    fontSize: 10,
    fontWeight: '700',
    color: '#FF4D00',
    marginTop: 4,
    letterSpacing: 1,
  },
  instructions: {
    marginTop: 24,
    marginBottom: 24,
  },
  instructionItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
    gap: 8,
  },
  instructionText: {
    fontSize: 14,
    color: '#888',
  },
  buttonContainer: {
    width: '100%',
  },
  optionsContainer: {
    width: '100%',
    gap: 12,
  },
  rimNotVisibleButton: {
    backgroundColor: '#1a1a1a',
    borderWidth: 1,
    borderColor: '#333',
    borderRadius: 12,
    paddingVertical: 16,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 10,
  },
  rimNotVisibleText: {
    fontSize: 16,
    fontWeight: '500',
    color: '#888',
  },
  skipButton: {
    backgroundColor: 'transparent',
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: 'center',
  },
  skipButtonText: {
    fontSize: 14,
    color: '#555',
    textDecorationLine: 'underline',
  },
  resetButton: {
    flex: 1,
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: '#FF4D00',
    borderRadius: 12,
    paddingVertical: 16,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
  },
  resetButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FF4D00',
  },
  confirmButton: {
    flex: 2,
    backgroundColor: '#FF4D00',
    borderRadius: 12,
    paddingVertical: 16,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
  },
  confirmButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFF',
  },
});
