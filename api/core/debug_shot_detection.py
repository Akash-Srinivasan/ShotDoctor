#!/usr/bin/env python3
"""
FormCheck - Shot Detection Debugger (Release-Backward Approach)

Visualizes what the shot detector "sees" to help tune detection parameters.

Usage:
    python debug_shot_detection.py video.mp4 --left
"""

import cv2
import numpy as np
import json
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, List
import time

try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Note: matplotlib not available - angle plots disabled")

# Import pose detector
try:
    from live_analysis import PoseDetector
except ImportError:
    print("Error: Could not import PoseDetector from live_analysis.py")
    sys.exit(1)


@dataclass
class FrameMetrics:
    """Metrics for a single frame."""
    frame_num: int
    timestamp_ms: float
    elbow_angle: Optional[float]
    wrist_height: Optional[float]
    wrist_above_shoulder: bool
    shoulder_y: Optional[float]
    elbow_y: Optional[float]
    wrist_y: Optional[float]


@dataclass 
class DetectedShot:
    """A detected shot with all debug info."""
    shot_num: int
    frame_start: int
    frame_end: int
    
    stance_idx: int
    load_idx: int
    mid1_idx: int
    mid2_idx: int
    mid3_idx: int
    mid4_idx: int
    release_idx: int
    followthrough_idx: int
    
    load_angle: float
    release_angle: float
    
    frame_metrics: List[FrameMetrics]


class ShotDetectionDebugger:
    """
    Debug shot detector using release-backward approach.
    
    Logic:
    1. Detect RELEASE: elbow > 155° AND wrist above shoulder
    2. Look BACKWARD to find LOAD: minimum elbow angle
    3. Capture more frames between load and release
    """
    
    def __init__(self, shooting_side: str = "right", output_dir: str = "debug_output"):
        self.side = shooting_side
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Buffers
        self.frames_buffer = []
        self.metrics_buffer: List[FrameMetrics] = []
        self.max_buffer = 200
        
        # State
        self.stability_count = 0
        
        # Thresholds
        self.STABILITY_REQUIRED = 8
        self.RELEASE_ANGLE = 155
        self.MIN_SHOT_FRAMES = 10
        self.COOLDOWN_FRAMES = 45
        
        # Tracking
        self.last_shot_frame = -100
        self.shots: List[DetectedShot] = []
        self.shot_count = 0
        
        print(f"Shot Detection Debugger")
        print(f"  Side: {shooting_side}")
        print(f"  Output: {self.output_dir}")
        print(f"  Release threshold: >{self.RELEASE_ANGLE}°")
    
    def process_frame(self, frame: np.ndarray, landmarks: Dict, visibility: Dict, 
                      frame_num: int, timestamp_ms: float) -> Optional[DetectedShot]:
        """Process a frame and return DetectedShot if shot completed."""
        
        # Extract key points
        shoulder = landmarks.get(f"{self.side}_shoulder")
        elbow = landmarks.get(f"{self.side}_elbow")
        wrist = landmarks.get(f"{self.side}_wrist")
        
        # Calculate metrics
        elbow_angle = None
        wrist_height = None
        wrist_above_shoulder = False
        
        if all([shoulder, elbow, wrist]):
            elbow_angle = self._calculate_angle(shoulder, elbow, wrist)
            wrist_height = wrist[1]
            wrist_above_shoulder = wrist[1] < shoulder[1]
            
            vis_ok = all(visibility.get(f"{self.side}_{j}", 0) > 0.5 
                        for j in ["shoulder", "elbow", "wrist"])
            if vis_ok:
                self.stability_count += 1
            else:
                self.stability_count = 0
        else:
            self.stability_count = 0
        
        # Create metrics record
        metrics = FrameMetrics(
            frame_num=frame_num,
            timestamp_ms=timestamp_ms,
            elbow_angle=elbow_angle,
            wrist_height=wrist_height,
            wrist_above_shoulder=wrist_above_shoulder,
            shoulder_y=shoulder[1] if shoulder else None,
            elbow_y=elbow[1] if elbow else None,
            wrist_y=wrist[1] if wrist else None
        )
        
        # Store in buffers
        self.frames_buffer.append(frame.copy())
        self.metrics_buffer.append(metrics)
        self._trim_buffer()
        
        # IMPORTANT: Get current index AFTER trim
        current_idx = len(self.frames_buffer) - 1
        
        # Need stability and cooldown
        if self.stability_count < self.STABILITY_REQUIRED:
            return None
        
        if current_idx - self.last_shot_frame < self.COOLDOWN_FRAMES:
            return None
        
        # DETECT RELEASE: elbow extended AND wrist above shoulder
        if elbow_angle and elbow_angle > self.RELEASE_ANGLE and wrist_above_shoulder:
            print(f"  [Frame {frame_num}] Release detected - elbow at {elbow_angle:.0f}°")
            shot = self._create_shot(current_idx, elbow_angle)
            if shot:
                self.last_shot_frame = current_idx
                return shot
        
        return None
    
    def _calculate_angle(self, p1, p2, p3) -> float:
        """Calculate angle at p2."""
        v1 = np.array([p1[0] - p2[0], p1[1] - p2[1]])
        v2 = np.array([p3[0] - p2[0], p3[1] - p2[1]])
        cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
        return np.degrees(np.arccos(np.clip(cos_angle, -1, 1)))
    
    def _create_shot(self, release_idx: int, release_angle: float) -> Optional[DetectedShot]:
        """
        Create shot by working backward from release.
        
        Frame distribution - 8 frames total:
        - Stance: 5 frames before load
        - Load: minimum elbow angle
        - Mid1-Mid4: 4 equidistant frames (20%, 40%, 60%, 80%)
        - Release: trigger frame (155°+)
        - FollowThrough: 5 frames after release
        """
        self.shot_count += 1
        
        # Search backward for LOAD (minimum elbow angle)
        search_start = max(0, release_idx - 60)
        
        load_idx = release_idx
        min_angle = float('inf')
        
        for i in range(search_start, release_idx):
            if i < len(self.metrics_buffer):
                m = self.metrics_buffer[i]
                if m.elbow_angle and m.elbow_angle < min_angle:
                    min_angle = m.elbow_angle
                    load_idx = i
        
        # Validate minimum distance
        shot_duration = release_idx - load_idx
        if shot_duration < self.MIN_SHOT_FRAMES:
            print(f"    Shot rejected: only {shot_duration} frames between load and release")
            self.shot_count -= 1
            return None
        
        print(f"    Load at idx {load_idx} ({min_angle:.0f}°), {shot_duration} frames to release")
        
        # Calculate 4 equidistant frames between load and release
        mid1_idx = load_idx + int(shot_duration * 0.20)
        mid2_idx = load_idx + int(shot_duration * 0.40)
        mid3_idx = load_idx + int(shot_duration * 0.60)
        mid4_idx = load_idx + int(shot_duration * 0.80)
        
        # Stance: 5 frames before load
        stance_idx = max(0, load_idx - 5)
        
        # Follow-through: 5 frames after release (reduced from 12)
        followthrough_idx = min(release_idx + 5, len(self.frames_buffer) - 1)
        
        # Clamp all indices
        def clamp(i):
            return max(0, min(i, len(self.frames_buffer) - 1))
        
        stance_idx = clamp(stance_idx)
        load_idx = clamp(load_idx)
        mid1_idx = clamp(mid1_idx)
        mid2_idx = clamp(mid2_idx)
        mid3_idx = clamp(mid3_idx)
        mid4_idx = clamp(mid4_idx)
        release_idx = clamp(release_idx)
        followthrough_idx = clamp(followthrough_idx)
        
        # Get frame metrics for shot window
        window_start = max(0, stance_idx - 10)
        window_end = min(len(self.metrics_buffer), followthrough_idx + 10)
        shot_metrics = self.metrics_buffer[window_start:window_end]
        
        shot = DetectedShot(
            shot_num=self.shot_count,
            frame_start=window_start,
            frame_end=window_end,
            stance_idx=stance_idx,
            load_idx=load_idx,
            mid1_idx=mid1_idx,
            mid2_idx=mid2_idx,
            mid3_idx=mid3_idx,
            mid4_idx=mid4_idx,
            release_idx=release_idx,
            followthrough_idx=followthrough_idx,
            load_angle=min_angle,
            release_angle=release_angle,
            frame_metrics=shot_metrics
        )
        
        # Save debug output
        self._save_shot_debug(shot)
        
        self.shots.append(shot)
        return shot
    
    def _save_shot_debug(self, shot: DetectedShot):
        """Save all debug info for a shot."""
        shot_dir = self.output_dir / f"shot_{shot.shot_num}"
        shot_dir.mkdir(exist_ok=True)
        
        key_frames = [
            ("1_Stance", shot.stance_idx),
            ("2_Load", shot.load_idx),
            ("3_Mid1", shot.mid1_idx),
            ("4_Mid2", shot.mid2_idx),
            ("5_Mid3", shot.mid3_idx),
            ("6_Mid4", shot.mid4_idx),
            ("7_Release", shot.release_idx),
            ("8_FollowThrough", shot.followthrough_idx),
        ]
        
        print(f"\n  Saving shot {shot.shot_num} to {shot_dir}")
        print(f"    Frames: stance={shot.stance_idx}, load={shot.load_idx}, " +
              f"mids=[{shot.mid1_idx},{shot.mid2_idx},{shot.mid3_idx},{shot.mid4_idx}], " +
              f"release={shot.release_idx}, follow={shot.followthrough_idx}")
        print(f"    Angles: load={shot.load_angle:.0f}°, release={shot.release_angle:.0f}°")
        
        for name, idx in key_frames:
            if 0 <= idx < len(self.frames_buffer):
                frame = self.frames_buffer[idx].copy()
                metrics = self.metrics_buffer[idx] if idx < len(self.metrics_buffer) else None
                
                # Add annotation
                h, w = frame.shape[:2]
                cv2.rectangle(frame, (5, 5), (350, 100), (0, 0, 0), -1)
                cv2.rectangle(frame, (5, 5), (350, 100), (255, 255, 255), 1)
                
                cv2.putText(frame, f"{name}", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.putText(frame, f"Buffer idx: {idx}", (10, 55),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                
                if metrics:
                    cv2.putText(frame, f"Frame: {metrics.frame_num}", (150, 55),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                    if metrics.elbow_angle:
                        cv2.putText(frame, f"Elbow: {metrics.elbow_angle:.0f} deg", (10, 80),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                    cv2.putText(frame, f"Wrist above: {metrics.wrist_above_shoulder}", (180, 80),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                
                cv2.imwrite(str(shot_dir / f"{name}.jpg"), frame)
        
        # Save metrics JSON
        metrics_data = {
            "shot_num": shot.shot_num,
            "key_frames": {
                "stance": shot.stance_idx,
                "load": shot.load_idx,
                "mid1": shot.mid1_idx,
                "mid2": shot.mid2_idx,
                "mid3": shot.mid3_idx,
                "mid4": shot.mid4_idx,
                "release": shot.release_idx,
                "followthrough": shot.followthrough_idx,
            },
            "angles": {
                "load": shot.load_angle,
                "release": shot.release_angle,
            },
            "thresholds": {
                "release_angle": self.RELEASE_ANGLE,
                "min_shot_frames": self.MIN_SHOT_FRAMES,
            },
            "frame_metrics": [
                {
                    "frame": m.frame_num,
                    "elbow_angle": m.elbow_angle,
                    "wrist_height": m.wrist_height,
                    "wrist_above_shoulder": m.wrist_above_shoulder,
                }
                for m in shot.frame_metrics
            ]
        }
        
        with open(shot_dir / "metrics.json", "w") as f:
            json.dump(metrics_data, f, indent=2)
        
        # Create angle plot
        if MATPLOTLIB_AVAILABLE:
            self._create_angle_plot(shot, shot_dir)
    
    def _create_angle_plot(self, shot: DetectedShot, shot_dir: Path):
        """Create visualization of elbow angle over time."""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
        
        frames = [m.frame_num for m in shot.frame_metrics]
        angles = [m.elbow_angle for m in shot.frame_metrics]
        wrist_heights = [m.wrist_height for m in shot.frame_metrics]
        
        # Plot elbow angle
        ax1.plot(frames, angles, 'b-', linewidth=2, label='Elbow Angle')
        ax1.axhline(y=self.RELEASE_ANGLE, color='green', linestyle='--', 
                   label=f'Release threshold ({self.RELEASE_ANGLE}°)')
        
        # Mark key frames (8 total now)
        key_frames = {
            'Stance': (shot.stance_idx, 'red', 's', 100),
            'Load': (shot.load_idx, 'blue', 'o', 150),
            'Mid1 (20%)': (shot.mid1_idx, 'cyan', '^', 80),
            'Mid2 (40%)': (shot.mid2_idx, 'lime', '^', 80),
            'Mid3 (60%)': (shot.mid3_idx, 'yellow', '^', 80),
            'Mid4 (80%)': (shot.mid4_idx, 'orange', '^', 80),
            'Release': (shot.release_idx, 'green', 'o', 150),
            'Follow': (shot.followthrough_idx, 'purple', 'D', 100),
        }
        
        for name, (buf_idx, color, marker, size) in key_frames.items():
            relative_idx = buf_idx - shot.frame_start + 10
            if 0 <= relative_idx < len(shot.frame_metrics):
                m = shot.frame_metrics[relative_idx]
                if m.elbow_angle:
                    ax1.axvline(x=m.frame_num, color=color, alpha=0.3, linestyle=':')
                    ax1.scatter([m.frame_num], [m.elbow_angle], color=color, 
                               s=size, zorder=5, marker=marker, edgecolors='black')
                    ax1.annotate(name, (m.frame_num, m.elbow_angle), 
                                textcoords="offset points", xytext=(5, 5), fontsize=8)
        
        ax1.set_ylabel('Elbow Angle (degrees)')
        ax1.set_title(f'Shot {shot.shot_num} - Frame Selection\n' +
                     f'Load={shot.load_angle:.0f}° → Release={shot.release_angle:.0f}°')
        ax1.legend(loc='upper left', fontsize=8)
        ax1.grid(True, alpha=0.3)
        ax1.set_ylim(40, 190)
        
        # Plot wrist height
        ax2.plot(frames, wrist_heights, 'r-', linewidth=2, label='Wrist Y (lower = higher on screen)')
        ax2.set_ylabel('Wrist Y Position')
        ax2.set_xlabel('Frame Number')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        ax2.invert_yaxis()
        
        plt.tight_layout()
        plt.savefig(shot_dir / "angle_plot.png", dpi=150)
        plt.close()
        
        print(f"    Saved angle plot")
    
    def _trim_buffer(self):
        """Trim buffers to max size."""
        while len(self.frames_buffer) > self.max_buffer:
            self.frames_buffer.pop(0)
            self.metrics_buffer.pop(0)
            if self.last_shot_frame > 0:
                self.last_shot_frame -= 1


def main():
    """Run shot detection debugger on a video."""
    if len(sys.argv) < 2:
        print("""
Shot Detection Debugger

Usage:
    python debug_shot_detection.py <video_file> [--left|--right]

Output:
    debug_output/shot_X/
        - 8 annotated key frame images
        - angle_plot.png
        - metrics.json

Frame distribution:
    1. Stance (5 frames before load)
    2. Load (min elbow angle)
    3. Mid1 (20% load→release)
    4. Mid2 (40% load→release)
    5. Mid3 (60% load→release)
    6. Mid4 (80% load→release)
    7. Release (elbow > 155°)
    8. FollowThrough (+5 frames)

Examples:
    python debug_shot_detection.py video.mp4 --left
    python debug_shot_detection.py video.mp4 --right
""")
        return
    
    video_path = sys.argv[1]
    side = "right"
    
    for arg in sys.argv[2:]:
        if arg == "--left":
            side = "left"
        elif arg == "--right":
            side = "right"
    
    print(f"\nProcessing: {video_path}")
    print(f"Shooting side: {side}")
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open {video_path}")
        return
    
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    print(f"Video: {total_frames} frames @ {fps:.1f} fps")
    print(f"Duration: {total_frames/fps:.1f} seconds\n")
    
    # Initialize
    pose = PoseDetector()
    debugger = ShotDetectionDebugger(side)
    
    frame_num = 0
    
    print("Processing frames...")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_num += 1
        timestamp_ms = (frame_num / fps) * 1000
        
        landmarks, visibility = pose.detect(frame)
        
        shot = debugger.process_frame(frame, landmarks, visibility, frame_num, timestamp_ms)
        
        if shot:
            print(f"\n✓ Shot {shot.shot_num} saved\n")
        
        if frame_num % 200 == 0:
            print(f"  Frame {frame_num}/{total_frames} ({100*frame_num/total_frames:.0f}%)")
    
    cap.release()
    pose.close()
    
    print(f"\n{'='*50}")
    print(f"Done! Found {debugger.shot_count} shots")
    print(f"Output: {debugger.output_dir}")


if __name__ == "__main__":
    main()