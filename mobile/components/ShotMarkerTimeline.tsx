/**
 * ShotMarkerTimeline - Timeline showing shot markers
 * Displays a horizontal bar with colored dots for each shot
 * Green = made, Red = missed, Gray = unknown
 * Tap a marker to seek the video to that timestamp
 *
 * When tapped, seeks to a point BEFORE the release to show
 * the stance and loading phases of the shooting motion.
 */

import React from 'react';
import { View, TouchableOpacity, StyleSheet } from 'react-native';
import type { ShotAnalysis } from '../lib/api';

// How many seconds before the release point to seek
// This allows users to see stance and loading phases before the shot
// Shot detection captures: stance (5 frames before load) -> load -> mids -> release
// At 30fps, this is roughly: 0.17s (stance to load) + 0.33s+ (load to release) = ~0.5s+
// We use 1.5 seconds to give a comfortable view of the entire shooting motion
const PRE_SHOT_OFFSET_SECONDS = 1.5;

interface ShotMarkerTimelineProps {
  shots: ShotAnalysis[];
  videoDuration: number; // total video duration in seconds
  onSeek: (timestamp: number) => void;
}

export function ShotMarkerTimeline({ shots, videoDuration, onSeek }: ShotMarkerTimelineProps) {
  if (shots.length === 0 || videoDuration <= 0) {
    return null;
  }

  return (
    <View style={styles.container}>
      <View style={styles.timeline}>
        {shots.map((shot) => {
          // Calculate position as percentage of timeline width
          // The marker is positioned at the release point
          const position = Math.min((shot.timestamp / videoDuration) * 100, 100);

          // Determine marker color based on shot result
          let markerColor = '#888'; // gray for unknown
          if (shot.made === true) {
            markerColor = '#00ff00'; // green for made
          } else if (shot.made === false) {
            markerColor = '#ff4444'; // red for missed
          }

          return (
            <TouchableOpacity
              key={shot.shot_number}
              style={[
                styles.marker,
                {
                  left: `${position}%`,
                  backgroundColor: markerColor,
                },
              ]}
              onPress={() => {
                // Seek to a point BEFORE the release to show stance and loading phases
                // Ensure we don't seek before the start of the video
                const seekTime = Math.max(0, shot.timestamp - PRE_SHOT_OFFSET_SECONDS);
                onSeek(seekTime);
              }}
              activeOpacity={0.7}
            />
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  timeline: {
    height: 20,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderRadius: 10,
    position: 'relative',
  },
  marker: {
    position: 'absolute',
    width: 16,
    height: 16,
    borderRadius: 8,
    top: 2,
    marginLeft: -8, // center the marker on its position
    borderWidth: 2,
    borderColor: '#fff',
  },
});
