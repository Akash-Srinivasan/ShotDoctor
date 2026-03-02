#!/usr/bin/env python3
"""
Basketball shooting form analysis with improved ball tracking.
Uses shape analysis + temporal tracking to filter out false positives.

Usage:
    python test_tracking.py <video_path>
    python test_tracking.py <video_path> --left
    python test_tracking.py <video_path> --debug-ball  # Save ball detection debug video
"""

import sys
import cv2
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
import time
import urllib.request
import argparse

import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision


# ============================================================================
# Model Download
# ============================================================================

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
MODEL_PATH = Path(__file__).parent / "pose_landmarker.task"


def download_model():
    if MODEL_PATH.exists():
        print(f"✓ Model already downloaded")
        return
    
    print(f"Downloading pose model...")
    try:
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print(f"✓ Downloaded")
    except Exception as e:
        print(f"✗ Failed: {e}")
        print(f"Download manually: curl -o {MODEL_PATH} '{MODEL_URL}'")
        sys.exit(1)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class BallDetection:
    detected: bool
    center: Optional[Tuple[int, int]] = None
    radius: int = 0
    confidence: float = 0.0
    normalized_center: Optional[Tuple[float, float]] = None


@dataclass
class PoseFrame:
    frame_number: int
    timestamp_ms: float
    landmarks: Dict[str, Tuple[float, float, float]]
    visibility: Dict[str, float]
    ball: Optional[BallDetection] = None


@dataclass 
class JointAngles:
    elbow_angle: float
    knee_angle: float
    shoulder_angle: float


@dataclass
class FormMetrics:
    elbow_flare_degrees: float
    elbow_score: int
    release_height_ratio: float
    release_score: int
    knee_bend_angle: float
    base_score: int
    follow_through_score: int
    overall_score: int


@dataclass
class ShotAnalysis:
    shot_number: int
    start_frame: int
    end_frame: int
    release_frame: int
    phases: Dict[str, int]
    angles: JointAngles
    metrics: FormMetrics


# ============================================================================
# Landmark Names
# ============================================================================

LANDMARK_NAMES = {
    0: "nose",
    11: "left_shoulder", 12: "right_shoulder",
    13: "left_elbow", 14: "right_elbow",
    15: "left_wrist", 16: "right_wrist",
    23: "left_hip", 24: "right_hip",
    25: "left_knee", 26: "right_knee",
    27: "left_ankle", 28: "right_ankle",
}

KEY_LANDMARKS = list(LANDMARK_NAMES.values())


# ============================================================================
# Side Configuration
# ============================================================================

class SideConfig:
    def __init__(self, use_left: bool = False):
        self.use_left = use_left
        self.shooting_side = "left" if use_left else "right"
        self.guide_side = "right" if use_left else "left"
    
    def shooting(self, landmark: str) -> str:
        return f"{self.shooting_side}_{landmark}"
    
    def is_shooting_side(self, name: str) -> bool:
        return self.shooting_side in name


# ============================================================================
# Improved Ball Tracker
# ============================================================================

class BallTracker:
    """
    Ball tracking using YOLOv8 object detection.
    Much more accurate than HSV color filtering.
    """

    def __init__(self):
        """Initialize YOLOv8 model."""
        try:
            from ultralytics import YOLO
            import torch

            print("Loading YOLOv8n model...")
            self.model = YOLO('yolov8n.pt')  # Auto-downloads if not present

            # Use GPU if available
            if torch.backends.mps.is_available():
                self.device = "mps"
                print("  Using Apple Silicon GPU (MPS)")
            elif torch.cuda.is_available():
                self.device = "cuda"
                print("  Using NVIDIA GPU (CUDA)")
            else:
                self.device = "cpu"
                print("  Using CPU")

            self.enabled = True
            print("✓ YOLOv8 loaded")
        except ImportError:
            print("⚠️  ultralytics not installed. Run: pip install ultralytics")
            print("   Falling back to wrist-based shot detection only.")
            self.model = None
            self.enabled = False
            self.device = "cpu"
        except Exception as e:
            print(f"⚠️  Could not load YOLOv8: {e}")
            self.model = None
            self.enabled = False
            self.device = "cpu"

        # COCO class 32 = "sports ball"
        self.ball_class = 32
        self.confidence_threshold = 0.15

        # Performance settings
        self.inference_size = 640
        self.use_half = self.device != "cpu"

        # For filtering detections
        self.wrist_pos: Optional[Tuple[int, int]] = None
        self.face_center: Optional[Tuple[int, int]] = None
        self.face_radius: int = 0

        # Shot flight tracking (same as CustomBallTracker)
        self.last_detection: Optional[BallDetection] = None
        self.in_flight = False
        self.flight_trajectory: List[Tuple[int, int]] = []
        self.all_flight_trajectories: List[List[Tuple[int, int]]] = []
        self.frames_since_release = 0
        self.max_flight_frames = 60  # ~2 sec at 30fps
        self.consecutive_misses = 0
        self.max_consecutive_misses = 10  # Allow more gaps with HSV fallback

        # HSV tracking for fallback
        self.use_hsv_fallback = True
        self.hsv_lower = np.array([5, 100, 100])   # Orange lower bound (default)
        self.hsv_upper = np.array([25, 255, 255])  # Orange upper bound (default)
        self.last_frame: Optional[np.ndarray] = None
        self.frame_height = 0
        self.frame_width = 0

        # Learned ball appearance from YOLO detections
        self.ball_profile_learned = False
        self.ball_hsv_samples: List[np.ndarray] = []  # Store HSV samples from YOLO detections
        self.ball_hsv_mean: Optional[np.ndarray] = None  # Mean HSV values
        self.ball_hsv_std: Optional[np.ndarray] = None   # Std dev for range calculation
        self.ball_radius_samples: List[int] = []  # Store radius samples
        self.ball_radius_mean: float = 0
        self.ball_radius_std: float = 0
        self.max_profile_samples = 15  # Number of YOLO detections to learn from

        # CSRT Tracker - follows ball between YOLO detections (handles motion blur)
        self.use_csrt_tracker = True
        self.csrt_tracker: Optional[cv2.Tracker] = None
        self.csrt_active = False
        self.csrt_bbox: Optional[Tuple[int, int, int, int]] = None  # x, y, w, h
        self.csrt_confidence_frames = 0  # Frames since last YOLO confirmation
        self.csrt_max_frames_without_yolo = 30  # Re-check with YOLO after this many frames
        self.csrt_consecutive_failures = 0
        self.csrt_max_failures = 5  # Re-initialize after this many failures

    def mark_release(self, wrist_pos: Optional[Tuple[int, int]] = None):
        """Called when shot detection identifies a release point.

        Args:
            wrist_pos: Pixel coordinates of wrist at release (more reliable than ball detection)
        """
        self.in_flight = True
        self.flight_trajectory = []
        self.frames_since_release = 0
        self.consecutive_misses = 0

        # Use wrist position as release point (much more reliable)
        if wrist_pos:
            self.flight_trajectory.append(wrist_pos)
        elif self.last_detection and self.last_detection.detected and self.last_detection.center:
            self.flight_trajectory.append(self.last_detection.center)

    def end_flight(self):
        """Called when flight tracking should end."""
        if self.in_flight and len(self.flight_trajectory) >= 2:
            self.all_flight_trajectories.append(self.flight_trajectory.copy())
        self.in_flight = False
        self.flight_trajectory = []
        self.frames_since_release = 0
        self.consecutive_misses = 0

    def _init_csrt_tracker(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]):
        """Initialize CSRT tracker with a bounding box from YOLO detection.

        Args:
            frame: Current video frame
            bbox: (x, y, w, h) bounding box of the ball
        """
        if not self.use_csrt_tracker:
            return

        # Create new CSRT tracker
        self.csrt_tracker = cv2.TrackerCSRT_create()
        success = self.csrt_tracker.init(frame, bbox)

        if success:
            self.csrt_active = True
            self.csrt_bbox = bbox
            self.csrt_confidence_frames = 0
            self.csrt_consecutive_failures = 0
        else:
            self.csrt_active = False
            self.csrt_tracker = None

    def _update_csrt_tracker(self, frame: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """Update CSRT tracker with new frame.

        Returns:
            (x, y, w, h) bounding box if tracking successful, None otherwise
        """
        if not self.csrt_active or self.csrt_tracker is None:
            return None

        success, bbox = self.csrt_tracker.update(frame)

        if success:
            # Convert to integers
            x, y, w, h = [int(v) for v in bbox]
            self.csrt_bbox = (x, y, w, h)
            self.csrt_confidence_frames += 1
            self.csrt_consecutive_failures = 0
            return (x, y, w, h)
        else:
            self.csrt_consecutive_failures += 1
            if self.csrt_consecutive_failures >= self.csrt_max_failures:
                self.csrt_active = False
                self.csrt_tracker = None
            return None

    def _reset_csrt_tracker(self):
        """Reset CSRT tracker state."""
        self.csrt_active = False
        self.csrt_tracker = None
        self.csrt_bbox = None
        self.csrt_confidence_frames = 0
        self.csrt_consecutive_failures = 0

    def _learn_ball_appearance(self, frame: np.ndarray, center: Tuple[int, int], radius: int):
        """Learn the ball's appearance from a YOLO detection.

        Samples the HSV color values from the detected ball region to build
        a profile for more accurate HSV fallback tracking.
        """
        if len(self.ball_hsv_samples) >= self.max_profile_samples:
            return  # Already learned enough

        cx, cy = center
        height, width = frame.shape[:2]

        # Extract the ball region (slightly smaller to avoid background)
        sample_radius = max(5, int(radius * 0.7))
        x1 = max(0, cx - sample_radius)
        y1 = max(0, cy - sample_radius)
        x2 = min(width, cx + sample_radius)
        y2 = min(height, cy + sample_radius)

        if x2 <= x1 or y2 <= y1:
            return

        # Extract region and convert to HSV
        ball_region = frame[y1:y2, x1:x2]
        if ball_region.size == 0:
            return

        hsv_region = cv2.cvtColor(ball_region, cv2.COLOR_BGR2HSV)

        # Create circular mask to sample only the ball
        mask = np.zeros((y2-y1, x2-x1), dtype=np.uint8)
        mask_cx, mask_cy = (x2-x1)//2, (y2-y1)//2
        cv2.circle(mask, (mask_cx, mask_cy), sample_radius, 255, -1)

        # Get HSV values within the ball
        hsv_values = hsv_region[mask > 0]
        if len(hsv_values) < 10:
            return

        # Store the mean HSV of this sample
        mean_hsv = np.mean(hsv_values, axis=0)
        self.ball_hsv_samples.append(mean_hsv)
        self.ball_radius_samples.append(radius)

        # Update the learned profile
        if len(self.ball_hsv_samples) >= 3:
            all_samples = np.array(self.ball_hsv_samples)
            self.ball_hsv_mean = np.mean(all_samples, axis=0)
            self.ball_hsv_std = np.std(all_samples, axis=0)

            # Update radius stats
            self.ball_radius_mean = np.mean(self.ball_radius_samples)
            self.ball_radius_std = np.std(self.ball_radius_samples)

            # Calculate adaptive HSV range (mean ± 2*std, with minimums)
            h_margin = max(15, self.ball_hsv_std[0] * 2.5)
            s_margin = max(40, self.ball_hsv_std[1] * 2.5)
            v_margin = max(40, self.ball_hsv_std[2] * 2.5)

            self.hsv_lower = np.array([
                max(0, self.ball_hsv_mean[0] - h_margin),
                max(30, self.ball_hsv_mean[1] - s_margin),
                max(30, self.ball_hsv_mean[2] - v_margin)
            ], dtype=np.uint8)

            self.hsv_upper = np.array([
                min(180, self.ball_hsv_mean[0] + h_margin),
                min(255, self.ball_hsv_mean[1] + s_margin),
                min(255, self.ball_hsv_mean[2] + v_margin)
            ], dtype=np.uint8)

            self.ball_profile_learned = True

            if len(self.ball_hsv_samples) == 3:
                print(f"  📊 Ball profile learned: HSV mean={self.ball_hsv_mean.astype(int)}, "
                      f"radius={self.ball_radius_mean:.0f}±{self.ball_radius_std:.0f}px")

    def get_trajectory(self) -> List[Tuple[int, int]]:
        """Get ball positions for trajectory visualization."""
        if self.in_flight:
            return self.flight_trajectory.copy()
        return []

    def get_all_trajectories(self) -> List[List[Tuple[int, int]]]:
        """Get all completed flight trajectories."""
        return self.all_flight_trajectories.copy()

    def get_predicted_trajectory(self, num_points: int = 20) -> List[Tuple[int, int]]:
        """Fit parabola to flight trajectory and predict future positions."""
        if len(self.flight_trajectory) < 5:
            return []

        xs = [p[0] for p in self.flight_trajectory]
        ys = [p[1] for p in self.flight_trajectory]

        try:
            coeffs = np.polyfit(xs, ys, 2)  # y = ax² + bx + c
            a, b, c = coeffs

            last_x = xs[-1]
            x_direction = 1 if len(xs) < 2 else (1 if xs[-1] > xs[-2] else -1)

            predicted = []
            for i in range(1, num_points + 1):
                pred_x = last_x + (i * 15 * x_direction)
                pred_y = int(a * pred_x * pred_x + b * pred_x + c)

                if pred_x < 0 or pred_x > 1920 or pred_y < 0 or pred_y > 1080:
                    break

                predicted.append((int(pred_x), pred_y))

            return predicted
        except:
            return []

    def _get_predicted_position(self) -> Optional[Tuple[int, int]]:
        """Get single predicted position for HSV search region."""
        predicted = self.get_predicted_trajectory(num_points=3)
        return predicted[0] if predicted else None

    def _hsv_fallback_detect(self, frame: np.ndarray) -> Optional[Tuple[int, int, int]]:
        """Use HSV color + shape detection as fallback when YOLO fails.

        Handles motion blur by:
        1. Using wider color range for blurred orange
        2. Accepting lower circularity (motion blur elongates the ball)
        3. Expanding search region based on consecutive misses

        Returns (center_x, center_y, radius) if found, None otherwise.
        """
        if not self.use_hsv_fallback or frame is None:
            return None

        # Get predicted position to define search region
        predicted_pos = self._get_predicted_position()

        # If no prediction but we have last detection, use velocity estimate
        if predicted_pos is None and self.last_detection and self.last_detection.center:
            if len(self.flight_trajectory) >= 2:
                # Estimate velocity from last two points
                p1 = self.flight_trajectory[-2]
                p2 = self.flight_trajectory[-1]
                vx = p2[0] - p1[0]
                vy = p2[1] - p1[1]
                # Predict next position (with gravity approximation)
                predicted_pos = (
                    int(p2[0] + vx * (self.consecutive_misses + 1)),
                    int(p2[1] + vy * (self.consecutive_misses + 1) + 2 * (self.consecutive_misses + 1))  # gravity
                )
            else:
                predicted_pos = self.last_detection.center

        # Convert to HSV
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Use learned ball color profile if available, otherwise use generic ranges
        if self.ball_profile_learned and self.ball_hsv_mean is not None:
            # Primary: Use learned HSV range (most accurate)
            # Also add a slightly wider version for motion blur
            h_extra = 10  # Extra hue margin for blur
            s_extra = 30  # Extra saturation margin (blur desaturates)
            v_extra = 30  # Extra value margin

            hsv_ranges = [
                (self.hsv_lower, self.hsv_upper),  # Learned range (primary)
                # Wider version for motion blur
                (np.array([
                    max(0, self.hsv_lower[0] - h_extra),
                    max(20, self.hsv_lower[1] - s_extra),
                    max(20, self.hsv_lower[2] - v_extra)
                ], dtype=np.uint8),
                np.array([
                    min(180, self.hsv_upper[0] + h_extra),
                    min(255, self.hsv_upper[1] + s_extra),
                    min(255, self.hsv_upper[2] + v_extra)
                ], dtype=np.uint8)),
            ]
        else:
            # Fallback: Generic orange basketball ranges
            hsv_ranges = [
                (self.hsv_lower, self.hsv_upper),  # Default orange
                (np.array([0, 80, 80]), np.array([20, 255, 255])),  # Wider orange/red
                (np.array([15, 50, 100]), np.array([35, 255, 255])),  # Yellow-orange (blur)
            ]

        # Combine masks from all color ranges
        combined_mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        for lower, upper in hsv_ranges:
            mask = cv2.inRange(hsv, lower, upper)
            combined_mask = cv2.bitwise_or(combined_mask, mask)

        mask = combined_mask

        # Expand search radius based on consecutive misses (uncertainty grows)
        base_search_radius = 100
        search_radius = base_search_radius + (self.consecutive_misses * 30)  # Expand 30px per miss
        search_radius = min(search_radius, 300)  # Cap at 300px

        # If we have a predicted position, focus search there
        if predicted_pos:
            px, py = predicted_pos
            # Clamp to frame bounds
            px = max(0, min(px, frame.shape[1] - 1))
            py = max(0, min(py, frame.shape[0] - 1))
            # Create region mask
            region_mask = np.zeros_like(mask)
            cv2.circle(region_mask, (px, py), search_radius, 255, -1)
            mask = cv2.bitwise_and(mask, region_mask)

        # Clean up mask - gentler morphology for motion blur
        kernel_small = np.ones((3, 3), np.uint8)
        kernel_large = np.ones((7, 7), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_small)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_large)  # Close gaps from blur

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return None

        # Ball size estimation - use learned profile if available
        if self.ball_profile_learned and self.ball_radius_mean > 0:
            # Use learned radius with margin for distance changes
            expected_radius = self.ball_radius_mean
            radius_tolerance = max(self.ball_radius_std * 3, expected_radius * 0.5)
            min_radius = max(5, expected_radius - radius_tolerance)
            max_radius = expected_radius + radius_tolerance
            min_area = int(np.pi * min_radius * min_radius * 0.5)  # Allow for blur
            max_area = int(np.pi * max_radius * max_radius * 2.0)  # Allow for blur expansion
        else:
            # Fallback to generic range
            min_area = 100
            max_area = 20000
            expected_radius = None

        # Find most likely ball contour
        best_match = None
        best_score = 0

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area or area > max_area:
                continue

            # Check circularity - lower threshold for motion blur
            perimeter = cv2.arcLength(contour, True)
            if perimeter == 0:
                continue
            circularity = 4 * np.pi * area / (perimeter * perimeter)

            # Motion blur elongates ball - accept lower circularity (0.3 instead of 0.5)
            if circularity < 0.3:
                continue

            # Get center and radius
            (cx, cy), radius = cv2.minEnclosingCircle(contour)
            cx, cy, radius = int(cx), int(cy), int(radius)

            # Score based on multiple factors
            score = 0.0

            # Circularity score (0-1)
            score += circularity * 0.3

            # Proximity to predicted position (0-1)
            if predicted_pos:
                dist = np.sqrt((cx - predicted_pos[0])**2 + (cy - predicted_pos[1])**2)
                proximity_score = max(0, 1 - dist / search_radius)
                score += proximity_score * 0.4

            # Size consistency with learned profile (weighted higher if profile learned)
            if self.ball_profile_learned and self.ball_radius_mean > 0:
                # Use learned profile - give strong weight
                size_diff = abs(radius - self.ball_radius_mean)
                tolerance = max(self.ball_radius_std * 2, 10)
                size_score = max(0, 1 - size_diff / tolerance)
                score += size_score * 0.3  # Higher weight for learned profile
            elif self.last_detection and self.last_detection.radius > 0:
                # Fallback to last detection
                size_ratio = radius / self.last_detection.radius
                if 0.5 < size_ratio < 2.0:
                    size_score = 1 - abs(1 - size_ratio)
                    score += size_score * 0.2

            if score > best_score:
                best_score = score
                best_match = (cx, cy, radius)

        return best_match

    def set_zones(self, landmarks: Dict[str, Tuple[float, float, float]],
                  width: int, height: int, shooting_side: str):
        """Set wrist position and face exclusion."""
        
        # Face exclusion
        nose = landmarks.get("nose")
        if nose:
            self.face_center = (int(nose[0] * width), int(nose[1] * height))
            left_sh = landmarks.get("left_shoulder")
            right_sh = landmarks.get("right_shoulder")
            if left_sh and right_sh:
                self.face_radius = int(abs(left_sh[0] - right_sh[0]) * width * 0.4)
            else:
                self.face_radius = 60
        
        # Wrist position
        wrist = landmarks.get(f"{shooting_side}_wrist")
        self.wrist_pos = (int(wrist[0] * width), int(wrist[1] * height)) if wrist else None
    
    def detect(self, frame: np.ndarray, landmarks: Dict = None,
               shooting_side: str = "right") -> BallDetection:
        """Detect basketball using CSRT tracker + YOLOv8 hybrid approach.

        Strategy:
        1. If CSRT tracker is active → use it (fast, handles motion blur)
        2. Periodically verify with YOLO or when CSRT fails
        3. Initialize CSRT when YOLO gets a good detection
        """

        if not self.enabled or self.model is None:
            return BallDetection(detected=False)

        height, width = frame.shape[:2]

        if landmarks:
            self.set_zones(landmarks, width, height, shooting_side)

        # Strategy 1: Try CSRT tracker first (if active and not needing verification)
        use_yolo = True
        csrt_detection = None

        if self.use_csrt_tracker and self.csrt_active:
            csrt_bbox = self._update_csrt_tracker(frame)

            if csrt_bbox is not None:
                x, y, w, h = csrt_bbox
                center_x = x + w // 2
                center_y = y + h // 2
                radius = max(w, h) // 2

                csrt_detection = {
                    'center': (center_x, center_y),
                    'radius': radius,
                    'confidence': 0.7,  # CSRT confidence marker
                    'normalized_center': (center_x / width, center_y / height),
                    'bbox': csrt_bbox
                }

                # Skip YOLO if CSRT is confident and hasn't been verified recently
                if self.csrt_confidence_frames < self.csrt_max_frames_without_yolo:
                    use_yolo = False

        # Strategy 2: Run YOLO (if needed)
        best_detection = None
        best_score = 0

        if use_yolo:
            results = self.model(
            frame,
            verbose=False,
            classes=[self.ball_class],
            device=self.device,
            imgsz=self.inference_size,
            half=self.use_half
        )
        
            # Process YOLO detections
            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue

                for i in range(len(boxes)):
                    conf = float(boxes.conf[i])
                    if conf < self.confidence_threshold:
                        continue

                    # Get bounding box
                    x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                    center_x = int((x1 + x2) / 2)
                    center_y = int((y1 + y2) / 2)
                    radius = int(max(x2 - x1, y2 - y1) / 2)
                    w, h = int(x2 - x1), int(y2 - y1)

                    # Skip if overlapping with face
                    if self.face_center:
                        dist_to_face = np.sqrt((center_x - self.face_center[0])**2 +
                                              (center_y - self.face_center[1])**2)
                        if dist_to_face < self.face_radius:
                            continue

                    # Score based on confidence and proximity to wrist
                    score = conf * 100

                    if self.wrist_pos:
                        dist_to_wrist = np.sqrt((center_x - self.wrist_pos[0])**2 +
                                               (center_y - self.wrist_pos[1])**2)
                        # Bonus for being near wrist (holding the ball)
                        if dist_to_wrist < 200:
                            score += (1 - dist_to_wrist / 200) * 50

                    if score > best_score:
                        best_score = score
                        best_detection = {
                            'center': (center_x, center_y),
                            'radius': radius,
                            'confidence': conf,
                            'normalized_center': (center_x / width, center_y / height),
                            'bbox': (int(x1), int(y1), w, h)
                        }

        # Strategy 3: Choose best detection (YOLO preferred over CSRT)
        final_detection = best_detection if best_detection else csrt_detection

        if final_detection:
            detection = BallDetection(
                detected=True,
                center=final_detection['center'],
                radius=final_detection['radius'],
                confidence=final_detection['confidence'],
                normalized_center=final_detection['normalized_center']
            )
            self.last_detection = detection
            self.last_frame = frame  # Store for HSV fallback
            self.frame_height, self.frame_width = height, width

            # If this was a YOLO detection (high confidence), initialize/update CSRT tracker
            if best_detection and best_detection['confidence'] > 0.25 and 'bbox' in best_detection:
                bbox = best_detection['bbox']
                # Initialize or re-initialize CSRT with fresh YOLO detection
                if not self.csrt_active or self.csrt_confidence_frames >= self.csrt_max_frames_without_yolo:
                    self._init_csrt_tracker(frame, bbox)
                self.csrt_confidence_frames = 0  # Reset verification counter

            # Learn ball appearance from YOLO detection (for better HSV fallback)
            if best_detection:  # Only learn from YOLO, not CSRT
                self._learn_ball_appearance(frame, best_detection['center'], best_detection['radius'])

            # Track flight trajectory if ball is in flight
            if self.in_flight:
                self.flight_trajectory.append(final_detection['center'])
                self.frames_since_release += 1
                self.consecutive_misses = 0  # Reset miss counter on detection
                if self.frames_since_release > self.max_flight_frames:
                    self.end_flight()

            return detection

        # YOLO failed - try HSV fallback if ball is in flight
        if self.in_flight and self.use_hsv_fallback:
            self.last_frame = frame
            self.frame_height, self.frame_width = height, width
            hsv_result = self._hsv_fallback_detect(frame)

            if hsv_result:
                cx, cy, radius = hsv_result
                detection = BallDetection(
                    detected=True,
                    center=(cx, cy),
                    radius=radius,
                    confidence=0.5,  # Lower confidence for HSV detection
                    normalized_center=(cx / width, cy / height)
                )
                self.last_detection = detection
                self.flight_trajectory.append((cx, cy))
                self.frames_since_release += 1
                self.consecutive_misses = 0

                if self.frames_since_release > self.max_flight_frames:
                    self.end_flight()

                return detection

        # No detection - if in flight, allow gaps but track misses
        if self.in_flight:
            self.frames_since_release += 1
            self.consecutive_misses += 1

            # End flight if too many consecutive misses OR timeout
            if self.consecutive_misses > self.max_consecutive_misses:
                self.end_flight()
            elif self.frames_since_release > self.max_flight_frames:
                self.end_flight()

        return BallDetection(detected=False)


class CustomBallTracker:
    """
    Ball tracking using custom basketball-trained YOLO model with CSRT tracking
    and HSV color fallback for robust in-flight ball detection.

    Detection priority:
    1. CSRT tracker (fast, handles motion blur between YOLO frames)
    2. Custom YOLO model (accurate but slower)
    3. HSV color fallback (when both fail during flight)
    """

    def __init__(self, model_path: str = None):
        """Initialize custom basketball model with CSRT + HSV fallback."""
        try:
            from ultralytics import YOLO
            import torch

            if model_path is None:
                # Prefer trained basketball detector, fall back to generic
                best_path = Path(__file__).parent / "basketball_detector" / "yolov8_basketball" / "weights" / "best.pt"
                fallback_path = Path(__file__).parent / "ball_detector_model.pt"
                if best_path.exists():
                    model_path = str(best_path)
                elif fallback_path.exists():
                    model_path = str(fallback_path)
                else:
                    raise FileNotFoundError(f"No model found at {best_path} or {fallback_path}")

            print(f"Loading custom ball model: {model_path}")
            self.model = YOLO(model_path)

            # Resolve the ball class id from model names
            self.ball_class_id = None
            if hasattr(self.model, 'names'):
                for cls_id, name in self.model.names.items():
                    if name.lower() in ("ball", "basketball"):
                        self.ball_class_id = cls_id
                        break

            # Use GPU if available (MPS for Apple Silicon, CUDA for NVIDIA)
            if torch.backends.mps.is_available():
                self.device = "mps"
                print("  Using Apple Silicon GPU (MPS)")
            elif torch.cuda.is_available():
                self.device = "cuda"
                print("  Using NVIDIA GPU (CUDA)")
            else:
                self.device = "cpu"
                print("  Using CPU (slower)")

            self.enabled = True
            print("✓ Custom ball tracker loaded")
        except ImportError:
            print("⚠️  ultralytics not installed. Run: pip install ultralytics")
            self.model = None
            self.enabled = False
            self.device = "cpu"
            self.ball_class_id = None
        except Exception as e:
            print(f"⚠️  Could not load custom model: {e}")
            self.model = None
            self.enabled = False
            self.device = "cpu"
            self.ball_class_id = None

        self.confidence_threshold = 0.3
        self.last_detection: Optional[BallDetection] = None
        self.last_positions: List[Tuple[int, int]] = []

        # Performance settings
        self.inference_size = 640
        self.use_half = self.device != "cpu"

        # Shot flight tracking
        self.in_flight = False
        self.flight_trajectory: List[Tuple[int, int]] = []
        self.all_flight_trajectories: List[List[Tuple[int, int]]] = []
        self.frames_since_release = 0
        self.max_flight_frames = 60  # ~2 sec at 30fps
        self.consecutive_misses = 0
        self.max_consecutive_misses = 10  # Allow more gaps with CSRT+HSV

        # --- CSRT Tracker state ---
        self.csrt_tracker: Optional[cv2.Tracker] = None
        self.csrt_active = False
        self.csrt_bbox: Optional[Tuple[int, int, int, int]] = None
        self.csrt_confidence_frames = 0
        self.csrt_max_frames_without_yolo = 30
        self.csrt_consecutive_failures = 0
        self.csrt_max_failures = 5

        # --- HSV fallback state ---
        self.use_hsv_fallback = True
        self.hsv_lower = np.array([5, 100, 100], dtype=np.uint8)
        self.hsv_upper = np.array([25, 255, 255], dtype=np.uint8)

        # Learned ball appearance from YOLO detections
        self.ball_profile_learned = False
        self.ball_hsv_samples: List[np.ndarray] = []
        self.ball_hsv_mean: Optional[np.ndarray] = None
        self.ball_hsv_std: Optional[np.ndarray] = None
        self.ball_radius_samples: List[int] = []
        self.ball_radius_mean: float = 0
        self.ball_radius_std: float = 0
        self.max_profile_samples = 15

        # For filtering
        self.wrist_pos: Optional[Tuple[int, int]] = None
        self.face_center: Optional[Tuple[int, int]] = None
        self.face_radius: int = 0

    def reset(self):
        """Reset all per-session state while keeping the loaded YOLO model."""
        self.last_detection = None
        self.last_positions = []
        self.in_flight = False
        self.flight_trajectory = []
        self.all_flight_trajectories = []
        self.frames_since_release = 0
        self.consecutive_misses = 0
        self._reset_csrt_tracker()
        self.ball_profile_learned = False
        self.ball_hsv_samples = []
        self.ball_hsv_mean = None
        self.ball_hsv_std = None
        self.ball_radius_samples = []
        self.ball_radius_mean = 0
        self.ball_radius_std = 0
        self.hsv_lower = np.array([5, 100, 100], dtype=np.uint8)
        self.hsv_upper = np.array([25, 255, 255], dtype=np.uint8)
        self.wrist_pos = None
        self.face_center = None
        self.face_radius = 0

    # ------------------------------------------------------------------
    # CSRT tracker helpers
    # ------------------------------------------------------------------

    def _init_csrt_tracker(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]):
        """Initialize CSRT tracker with a bounding box from YOLO detection."""
        self.csrt_tracker = cv2.TrackerCSRT_create()
        success = self.csrt_tracker.init(frame, bbox)
        if success:
            self.csrt_active = True
            self.csrt_bbox = bbox
            self.csrt_confidence_frames = 0
            self.csrt_consecutive_failures = 0
        else:
            self._reset_csrt_tracker()

    def _update_csrt_tracker(self, frame: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """Update CSRT tracker. Returns (x, y, w, h) or None."""
        if not self.csrt_active or self.csrt_tracker is None:
            return None

        success, bbox = self.csrt_tracker.update(frame)
        if success:
            x, y, w, h = [int(v) for v in bbox]
            self.csrt_bbox = (x, y, w, h)
            self.csrt_confidence_frames += 1
            self.csrt_consecutive_failures = 0
            return (x, y, w, h)
        else:
            self.csrt_consecutive_failures += 1
            if self.csrt_consecutive_failures >= self.csrt_max_failures:
                self._reset_csrt_tracker()
            return None

    def _reset_csrt_tracker(self):
        """Reset CSRT tracker state."""
        self.csrt_active = False
        self.csrt_tracker = None
        self.csrt_bbox = None
        self.csrt_confidence_frames = 0
        self.csrt_consecutive_failures = 0

    # ------------------------------------------------------------------
    # HSV appearance learning + fallback detection
    # ------------------------------------------------------------------

    def _learn_ball_appearance(self, frame: np.ndarray, center: Tuple[int, int], radius: int):
        """Learn ball HSV profile from YOLO detections for better fallback."""
        if len(self.ball_hsv_samples) >= self.max_profile_samples:
            return

        cx, cy = center
        height, width = frame.shape[:2]

        sample_radius = max(5, int(radius * 0.7))
        x1, y1 = max(0, cx - sample_radius), max(0, cy - sample_radius)
        x2, y2 = min(width, cx + sample_radius), min(height, cy + sample_radius)
        if x2 <= x1 or y2 <= y1:
            return

        ball_region = frame[y1:y2, x1:x2]
        if ball_region.size == 0:
            return

        hsv_region = cv2.cvtColor(ball_region, cv2.COLOR_BGR2HSV)

        # Circular mask
        mask = np.zeros((y2 - y1, x2 - x1), dtype=np.uint8)
        cv2.circle(mask, ((x2 - x1) // 2, (y2 - y1) // 2), sample_radius, 255, -1)

        hsv_values = hsv_region[mask > 0]
        if len(hsv_values) < 10:
            return

        self.ball_hsv_samples.append(np.mean(hsv_values, axis=0))
        self.ball_radius_samples.append(radius)

        if len(self.ball_hsv_samples) >= 3:
            all_samples = np.array(self.ball_hsv_samples)
            self.ball_hsv_mean = np.mean(all_samples, axis=0)
            self.ball_hsv_std = np.std(all_samples, axis=0)
            self.ball_radius_mean = np.mean(self.ball_radius_samples)
            self.ball_radius_std = np.std(self.ball_radius_samples)

            h_margin = max(15, self.ball_hsv_std[0] * 2.5)
            s_margin = max(40, self.ball_hsv_std[1] * 2.5)
            v_margin = max(40, self.ball_hsv_std[2] * 2.5)

            self.hsv_lower = np.array([
                max(0, self.ball_hsv_mean[0] - h_margin),
                max(30, self.ball_hsv_mean[1] - s_margin),
                max(30, self.ball_hsv_mean[2] - v_margin)
            ], dtype=np.uint8)
            self.hsv_upper = np.array([
                min(180, self.ball_hsv_mean[0] + h_margin),
                min(255, self.ball_hsv_mean[1] + s_margin),
                min(255, self.ball_hsv_mean[2] + v_margin)
            ], dtype=np.uint8)

            self.ball_profile_learned = True
            if len(self.ball_hsv_samples) == 3:
                print(f"  📊 Ball profile learned: HSV mean={self.ball_hsv_mean.astype(int)}, "
                      f"radius={self.ball_radius_mean:.0f}±{self.ball_radius_std:.0f}px")

    def _get_predicted_position(self) -> Optional[Tuple[int, int]]:
        """Get single predicted position for HSV search region."""
        predicted = self.get_predicted_trajectory(num_points=3)
        if predicted:
            return predicted[0]

        # Velocity-based fallback
        if self.last_detection and self.last_detection.center and len(self.flight_trajectory) >= 2:
            p1 = self.flight_trajectory[-2]
            p2 = self.flight_trajectory[-1]
            vx = p2[0] - p1[0]
            vy = p2[1] - p1[1]
            n = self.consecutive_misses + 1
            return (int(p2[0] + vx * n), int(p2[1] + vy * n + 2 * n))

        if self.last_detection and self.last_detection.center:
            return self.last_detection.center
        return None

    def _hsv_fallback_detect(self, frame: np.ndarray) -> Optional[Tuple[int, int, int]]:
        """HSV color + shape fallback when YOLO and CSRT both fail.

        Returns (center_x, center_y, radius) if found, None otherwise.
        """
        if not self.use_hsv_fallback or frame is None:
            return None

        predicted_pos = self._get_predicted_position()

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        if self.ball_profile_learned and self.ball_hsv_mean is not None:
            h_extra, s_extra, v_extra = 10, 30, 30
            hsv_ranges = [
                (self.hsv_lower, self.hsv_upper),
                (np.array([max(0, int(self.hsv_lower[0]) - h_extra),
                           max(20, int(self.hsv_lower[1]) - s_extra),
                           max(20, int(self.hsv_lower[2]) - v_extra)], dtype=np.uint8),
                 np.array([min(180, int(self.hsv_upper[0]) + h_extra),
                           min(255, int(self.hsv_upper[1]) + s_extra),
                           min(255, int(self.hsv_upper[2]) + v_extra)], dtype=np.uint8)),
            ]
        else:
            hsv_ranges = [
                (self.hsv_lower, self.hsv_upper),
                (np.array([0, 80, 80]), np.array([20, 255, 255])),
                (np.array([15, 50, 100]), np.array([35, 255, 255])),
            ]

        combined_mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        for lower, upper in hsv_ranges:
            combined_mask = cv2.bitwise_or(combined_mask, cv2.inRange(hsv, lower, upper))
        mask = combined_mask

        # Expanding search radius based on consecutive misses
        search_radius = min(100 + self.consecutive_misses * 30, 300)

        if predicted_pos:
            px = max(0, min(predicted_pos[0], frame.shape[1] - 1))
            py = max(0, min(predicted_pos[1], frame.shape[0] - 1))
            region_mask = np.zeros_like(mask)
            cv2.circle(region_mask, (px, py), search_radius, 255, -1)
            mask = cv2.bitwise_and(mask, region_mask)

        kernel_small = np.ones((3, 3), np.uint8)
        kernel_large = np.ones((7, 7), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_small)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_large)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        if self.ball_profile_learned and self.ball_radius_mean > 0:
            expected_radius = self.ball_radius_mean
            tol = max(self.ball_radius_std * 3, expected_radius * 0.5)
            min_area = int(np.pi * max(5, expected_radius - tol) ** 2 * 0.5)
            max_area = int(np.pi * (expected_radius + tol) ** 2 * 2.0)
        else:
            min_area, max_area = 100, 20000

        best_match = None
        best_score = 0.0

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area or area > max_area:
                continue
            perimeter = cv2.arcLength(contour, True)
            if perimeter == 0:
                continue
            circularity = 4 * np.pi * area / (perimeter * perimeter)
            if circularity < 0.3:
                continue

            (cx, cy), radius = cv2.minEnclosingCircle(contour)
            cx, cy, radius = int(cx), int(cy), int(radius)

            score = circularity * 0.3
            if predicted_pos:
                dist = np.sqrt((cx - predicted_pos[0]) ** 2 + (cy - predicted_pos[1]) ** 2)
                score += max(0, 1 - dist / search_radius) * 0.4
            if self.ball_profile_learned and self.ball_radius_mean > 0:
                size_diff = abs(radius - self.ball_radius_mean)
                tolerance = max(self.ball_radius_std * 2, 10)
                score += max(0, 1 - size_diff / tolerance) * 0.3
            elif self.last_detection and self.last_detection.radius > 0:
                size_ratio = radius / self.last_detection.radius
                if 0.5 < size_ratio < 2.0:
                    score += (1 - abs(1 - size_ratio)) * 0.2

            if score > best_score:
                best_score = score
                best_match = (cx, cy, radius)

        return best_match

    # ------------------------------------------------------------------
    # Flight tracking
    # ------------------------------------------------------------------

    def mark_release(self, wrist_pos: Optional[Tuple[int, int]] = None):
        """Called when shot detection identifies a release point."""
        self.in_flight = True
        self.flight_trajectory = []
        self.frames_since_release = 0
        self.consecutive_misses = 0

        if wrist_pos:
            self.flight_trajectory.append(wrist_pos)
        elif self.last_detection and self.last_detection.detected and self.last_detection.center:
            self.flight_trajectory.append(self.last_detection.center)

    def end_flight(self):
        """Called when flight tracking should end."""
        if self.in_flight and len(self.flight_trajectory) >= 2:
            self.all_flight_trajectories.append(self.flight_trajectory.copy())
        self.in_flight = False
        self.flight_trajectory = []
        self.frames_since_release = 0
        self.consecutive_misses = 0

    # ------------------------------------------------------------------
    # Main detect — hybrid CSRT + YOLO + HSV
    # ------------------------------------------------------------------

    def detect(self, frame: np.ndarray, landmarks: Dict = None,
               shooting_side: str = "right") -> BallDetection:
        """Detect basketball using CSRT + custom YOLO + HSV hybrid approach.

        Strategy:
        1. CSRT active & fresh → use CSRT result (skip YOLO)
        2. CSRT fails or stale → run YOLO
        3. YOLO succeeds → (re)init CSRT with bbox
        4. Both fail during flight → HSV fallback
        """

        if not self.enabled or self.model is None:
            return BallDetection(detected=False)

        height, width = frame.shape[:2]

        # Update wrist / face filter zones from landmarks
        if landmarks:
            self._set_zones(landmarks, width, height, shooting_side)

        # --- Strategy 1: Try CSRT tracker first ---
        use_yolo = True
        csrt_detection = None

        if self.csrt_active:
            csrt_bbox = self._update_csrt_tracker(frame)
            if csrt_bbox is not None:
                x, y, w, h = csrt_bbox
                center_x = x + w // 2
                center_y = y + h // 2
                radius = max(w, h) // 2
                csrt_detection = {
                    'center': (center_x, center_y),
                    'radius': radius,
                    'confidence': 0.7,  # CSRT confidence marker
                    'normalized_center': (center_x / width, center_y / height),
                    'bbox': csrt_bbox,
                }
                # Skip YOLO if CSRT is still fresh
                if self.csrt_confidence_frames < self.csrt_max_frames_without_yolo:
                    use_yolo = False

        # --- Strategy 2: Run custom YOLO if needed ---
        best_detection = None
        best_score = 0.0

        if use_yolo:
            results = self.model(
                frame,
                verbose=False,
                device=self.device,
                imgsz=self.inference_size,
                half=self.use_half,
            )

            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue

                # Resolve ball class id dynamically if not cached
                if self.ball_class_id is None:
                    for cls_id, name in result.names.items():
                        if name.lower() in ("ball", "basketball"):
                            self.ball_class_id = cls_id
                            break

                for i in range(len(boxes)):
                    cls_id = int(boxes.cls[i])
                    conf = float(boxes.conf[i])

                    if self.ball_class_id is not None and cls_id != self.ball_class_id:
                        continue
                    if conf < self.confidence_threshold:
                        continue

                    x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                    center_x = int((x1 + x2) / 2)
                    center_y = int((y1 + y2) / 2)
                    radius = int(max(x2 - x1, y2 - y1) / 2)
                    w_box, h_box = int(x2 - x1), int(y2 - y1)

                    # Skip if overlapping with face
                    if self.face_center:
                        dist_to_face = np.sqrt((center_x - self.face_center[0]) ** 2 +
                                               (center_y - self.face_center[1]) ** 2)
                        if dist_to_face < self.face_radius:
                            continue

                    score = conf * 100

                    # Proximity bonus to wrist (ball being held)
                    if self.wrist_pos:
                        dist_to_wrist = np.sqrt((center_x - self.wrist_pos[0]) ** 2 +
                                                (center_y - self.wrist_pos[1]) ** 2)
                        if dist_to_wrist < 200:
                            score += (1 - dist_to_wrist / 200) * 50

                    # Temporal continuity bonus
                    if self.last_detection and self.last_detection.detected and self.last_detection.center:
                        dist_to_last = np.sqrt((center_x - self.last_detection.center[0]) ** 2 +
                                               (center_y - self.last_detection.center[1]) ** 2)
                        if dist_to_last < 150:
                            score += (1 - dist_to_last / 150) * 10

                    if score > best_score:
                        best_score = score
                        best_detection = {
                            'center': (center_x, center_y),
                            'radius': radius,
                            'confidence': conf,
                            'normalized_center': (center_x / width, center_y / height),
                            'bbox': (int(x1), int(y1), w_box, h_box),
                        }

        # --- Strategy 3: Choose best (YOLO preferred over CSRT) ---
        final_detection = best_detection if best_detection else csrt_detection

        if final_detection:
            detection = BallDetection(
                detected=True,
                center=final_detection['center'],
                radius=final_detection['radius'],
                confidence=final_detection['confidence'],
                normalized_center=final_detection['normalized_center'],
            )
            self.last_detection = detection
            self.last_positions.append(final_detection['center'])
            if len(self.last_positions) > 30:
                self.last_positions.pop(0)

            # (Re)init CSRT from fresh YOLO detection
            if best_detection and best_detection['confidence'] > 0.25 and 'bbox' in best_detection:
                if not self.csrt_active or self.csrt_confidence_frames >= self.csrt_max_frames_without_yolo:
                    self._init_csrt_tracker(frame, best_detection['bbox'])
                self.csrt_confidence_frames = 0

            # Learn ball appearance from YOLO detections only
            if best_detection:
                self._learn_ball_appearance(frame, best_detection['center'], best_detection['radius'])

            # Track flight
            if self.in_flight:
                self.flight_trajectory.append(final_detection['center'])
                self.frames_since_release += 1
                self.consecutive_misses = 0
                if self.frames_since_release > self.max_flight_frames:
                    self.end_flight()

            return detection

        # --- Strategy 4: HSV fallback during flight ---
        if self.in_flight and self.use_hsv_fallback:
            hsv_result = self._hsv_fallback_detect(frame)
            if hsv_result:
                cx, cy, radius = hsv_result
                detection = BallDetection(
                    detected=True,
                    center=(cx, cy),
                    radius=radius,
                    confidence=0.5,  # HSV confidence marker
                    normalized_center=(cx / width, cy / height),
                )
                self.last_detection = detection
                self.flight_trajectory.append((cx, cy))
                self.frames_since_release += 1
                self.consecutive_misses = 0
                if self.frames_since_release > self.max_flight_frames:
                    self.end_flight()
                return detection

        # No detection — track misses
        if self.in_flight:
            self.frames_since_release += 1
            self.consecutive_misses += 1
            if self.consecutive_misses > self.max_consecutive_misses:
                self.end_flight()
            elif self.frames_since_release > self.max_flight_frames:
                self.end_flight()

        return BallDetection(detected=False)

    # ------------------------------------------------------------------
    # Zone helpers (ported from BallTracker)
    # ------------------------------------------------------------------

    def _set_zones(self, landmarks: Dict[str, Tuple[float, float, float]],
                   width: int, height: int, shooting_side: str):
        """Set wrist position and face exclusion zone from pose landmarks."""
        nose = landmarks.get("nose")
        if nose:
            self.face_center = (int(nose[0] * width), int(nose[1] * height))
            left_sh = landmarks.get("left_shoulder")
            right_sh = landmarks.get("right_shoulder")
            if left_sh and right_sh:
                self.face_radius = int(abs(left_sh[0] - right_sh[0]) * width * 0.4)
            else:
                self.face_radius = 60

        wrist = landmarks.get(f"{shooting_side}_wrist")
        self.wrist_pos = (int(wrist[0] * width), int(wrist[1] * height)) if wrist else None

    # ------------------------------------------------------------------
    # Trajectory helpers
    # ------------------------------------------------------------------

    def get_trajectory(self) -> List[Tuple[int, int]]:
        """Get ball positions for trajectory visualization."""
        if self.in_flight:
            return self.flight_trajectory.copy()
        return []

    def get_all_trajectories(self) -> List[List[Tuple[int, int]]]:
        """Get all completed flight trajectories from this session."""
        return self.all_flight_trajectories.copy()

    def get_predicted_trajectory(self, num_points: int = 20) -> List[Tuple[int, int]]:
        """Fit parabola to flight trajectory and predict future positions."""
        if len(self.flight_trajectory) < 5:
            return []

        xs = [p[0] for p in self.flight_trajectory]
        ys = [p[1] for p in self.flight_trajectory]

        try:
            coeffs = np.polyfit(xs, ys, 2)
            a, b, c = coeffs
            last_x = xs[-1]
            x_direction = 1 if len(xs) < 2 else (1 if xs[-1] > xs[-2] else -1)

            predicted = []
            for i in range(1, num_points + 1):
                pred_x = last_x + (i * 15 * x_direction)
                pred_y = int(a * pred_x * pred_x + b * pred_x + c)
                if pred_x < 0 or pred_x > 1920 or pred_y < 0 or pred_y > 1080:
                    break
                predicted.append((int(pred_x), pred_y))
            return predicted
        except:
            return []

    def interpolate_trajectory(self) -> List[Tuple[int, int]]:
        """Fill gaps in trajectory using interpolation."""
        if len(self.flight_trajectory) < 2:
            return self.flight_trajectory.copy()

        xs = [p[0] for p in self.flight_trajectory]
        ys = [p[1] for p in self.flight_trajectory]

        import pandas as pd
        df = pd.DataFrame({'x': xs, 'y': ys})
        df = df.interpolate(method='linear')
        df = df.bfill().ffill()

        return [(int(row['x']), int(row['y'])) for _, row in df.iterrows()]


# ============================================================================
# Real-time Release Detector (for ball flight tracking)
# ============================================================================

class RealTimeReleaseDetector:
    """Detects shot releases in real-time by monitoring wrist apex (highest point)."""

    def __init__(self, shooting_side: str = "right"):
        self.shooting_side = shooting_side
        self.bent_threshold = 120  # Elbow bent (loading)
        self.extended_threshold = 145  # Elbow extended (lowered to catch low-arc shots)
        self.in_shooting_motion = False
        self.prev_angle: Optional[float] = None
        self.frames_since_release = 0
        self.cooldown_frames = 30

        # Track wrist height to find apex (true release point)
        self.wrist_heights: List[float] = []
        self.max_wrist_height = 0.0
        self.frames_past_apex = 0

    def _calc_elbow_angle(self, landmarks: Dict) -> Optional[float]:
        """Calculate elbow angle from landmarks."""
        shoulder = landmarks.get(f"{self.shooting_side}_shoulder")
        elbow = landmarks.get(f"{self.shooting_side}_elbow")
        wrist = landmarks.get(f"{self.shooting_side}_wrist")

        if not all([shoulder, elbow, wrist]):
            return None

        v1 = np.array([shoulder[0] - elbow[0], shoulder[1] - elbow[1]])
        v2 = np.array([wrist[0] - elbow[0], wrist[1] - elbow[1]])

        norm1, norm2 = np.linalg.norm(v1), np.linalg.norm(v2)
        if norm1 < 1e-6 or norm2 < 1e-6:
            return None

        cos_angle = np.dot(v1, v2) / (norm1 * norm2)
        return np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0)))

    def update(self, landmarks: Dict) -> bool:
        """Update with new frame landmarks. Returns True if release detected."""
        self.frames_since_release += 1

        angle = self._calc_elbow_angle(landmarks)
        wrist = landmarks.get(f"{self.shooting_side}_wrist")
        shoulder = landmarks.get(f"{self.shooting_side}_shoulder")
        nose = landmarks.get("nose")

        if angle is None or not wrist:
            self.prev_angle = None
            return False

        # Wrist height (inverted - lower Y = higher position)
        wrist_height = 1.0 - wrist[1]

        release_detected = False

        # Check for shooting motion start (elbow bent, wrist below shoulder)
        if not self.in_shooting_motion and angle < self.bent_threshold:
            if shoulder and wrist[1] > shoulder[1] * 0.9:
                self.in_shooting_motion = True
                self.wrist_heights = []
                self.max_wrist_height = 0.0
                self.frames_past_apex = 0

        # During shooting motion, track wrist height
        if self.in_shooting_motion:
            self.wrist_heights.append(wrist_height)

            # Update max height
            if wrist_height > self.max_wrist_height:
                self.max_wrist_height = wrist_height
                self.frames_past_apex = 0
            else:
                self.frames_past_apex += 1

            # Detect release: wrist has passed apex AND elbow is extended AND wrist is high enough
            wrist_above_nose = nose and wrist[1] < nose[1]
            wrist_above_shoulder = shoulder and wrist[1] < shoulder[1]
            elbow_extended = angle >= self.extended_threshold

            # Release when wrist starts descending from apex (2-3 frames past peak)
            # Accept wrist above shoulder as fallback for low-arc shots
            if self.frames_past_apex >= 2 and elbow_extended and (wrist_above_nose or wrist_above_shoulder):
                if self.frames_since_release >= self.cooldown_frames:
                    release_detected = True
                    self.frames_since_release = 0
                self.in_shooting_motion = False
                self.wrist_heights = []

            # Timeout if motion takes too long
            if len(self.wrist_heights) > 45:
                self.in_shooting_motion = False
                self.wrist_heights = []

        self.prev_angle = angle
        return release_detected


# ============================================================================
# Pose Extraction
# ============================================================================

class PoseExtractor:
    def __init__(self, use_custom_tracker: bool = False, frame_skip: int = 1):
        download_model()

        base_options = python.BaseOptions(model_asset_path=str(MODEL_PATH))
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.detector = vision.PoseLandmarker.create_from_options(options)

        # Choose ball tracker
        self.use_custom_tracker = use_custom_tracker
        self.frame_skip = max(1, frame_skip)  # Ensure at least 1
        if use_custom_tracker:
            self.ball_tracker = CustomBallTracker()
        else:
            self.ball_tracker = BallTracker()
    
    def extract_from_video(self, video_path: str, debug_ball: bool = False, 
                            shooting_side: str = "right") -> Tuple[List[PoseFrame], dict]:
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        video_info = {"fps": fps, "total_frames": total_frames,
                      "duration": total_frames / fps if fps > 0 else 0,
                      "width": width, "height": height}
        
        print(f"Video: {video_path}")
        print(f"  Resolution: {width}x{height}, FPS: {fps:.1f}, Duration: {video_info['duration']:.1f}s")
        print()
        
        # Debug video writer
        debug_writer = None
        if debug_ball:
            tracker_suffix = "_custom" if self.use_custom_tracker else "_yolo"
            debug_path = str(Path(video_path).stem) + f"_ball_debug{tracker_suffix}.mp4"
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            debug_writer = cv2.VideoWriter(debug_path, fourcc, fps, (width, height))
            print(f"  Writing ball debug video to: {debug_path}")
        
        poses = []
        frame_number = 0
        frames_with_pose = 0
        frames_with_ball = 0
        frames_with_ball_yolo = 0
        frames_with_ball_csrt = 0
        frames_with_ball_hsv = 0
        releases_detected = 0

        # Real-time release detector for ball flight tracking
        release_detector = RealTimeReleaseDetector(shooting_side)

        print("Extracting poses and tracking ball...")
        start_time = time.time()

        last_ball_detection = BallDetection(detected=False)
        last_landmarks = {}
        last_visibility = {}

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Calculate timestamp for this frame
            timestamp_ms = int((frame_number / fps) * 1000) if fps > 0 else frame_number * 33

            # Skip frames for faster processing (but still need all for debug video)
            process_this_frame = (frame_number % self.frame_skip == 0)

            if process_this_frame:
                # First get pose landmarks
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

                landmarks = {}
                visibility = {}

                try:
                    detection_result = self.detector.detect_for_video(mp_image, timestamp_ms)

                    if detection_result.pose_landmarks and len(detection_result.pose_landmarks) > 0:
                        pose_landmarks = detection_result.pose_landmarks[0]

                        for idx, name in LANDMARK_NAMES.items():
                            if idx < len(pose_landmarks):
                                lm = pose_landmarks[idx]
                                landmarks[name] = (lm.x, lm.y, lm.z)
                                visibility[name] = lm.visibility if hasattr(lm, 'visibility') else 1.0

                        frames_with_pose += 1
                except:
                    pass

                # Detect shot release for flight tracking (works with both trackers)
                if landmarks:
                    if release_detector.update(landmarks):
                        # Get wrist position for better trajectory start
                        wrist = landmarks.get(f"{shooting_side}_wrist")
                        wrist_pos = None
                        if wrist:
                            wrist_pos = (int(wrist[0] * width), int(wrist[1] * height))
                        self.ball_tracker.mark_release(wrist_pos)
                        releases_detected += 1
                        print(f"  🏀 Release detected at frame {frame_number}")

                # Now detect ball with pose context
                ball_detection = self.ball_tracker.detect(frame, landmarks, shooting_side)
                if ball_detection.detected:
                    frames_with_ball += 1
                    # Track detection source by confidence:
                    # YOLO: > 0.7, CSRT: 0.7, HSV: 0.5
                    if ball_detection.confidence > 0.7:
                        frames_with_ball_yolo += 1
                    elif ball_detection.confidence == 0.7:
                        frames_with_ball_csrt += 1
                    else:
                        frames_with_ball_hsv += 1

                # Cache for skipped frames
                last_ball_detection = ball_detection
                last_landmarks = landmarks
                last_visibility = visibility
            else:
                # Use cached data for skipped frames
                landmarks = last_landmarks
                visibility = last_visibility
                ball_detection = last_ball_detection
            
            # Debug visualization
            if debug_writer:
                debug_frame = frame.copy()

                # Show tracker type
                tracker_label = "CUSTOM" if self.use_custom_tracker else "YOLO"
                cv2.putText(debug_frame, f"Tracker: {tracker_label}", (10, 60),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 165, 0), 2)

                # Show flight status (works with both trackers now)
                if hasattr(self.ball_tracker, 'in_flight') and self.ball_tracker.in_flight:
                    cv2.putText(debug_frame, "IN FLIGHT", (10, 90),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    # Draw flight trajectory (cyan/yellow gradient line)
                    trajectory = self.ball_tracker.get_trajectory()
                    if len(trajectory) > 1:
                        for i in range(1, len(trajectory)):
                            # Color fades from cyan to yellow along trajectory
                            progress = i / len(trajectory)
                            color = (0, int(255 * (1 - progress * 0.5)), 255)
                            thickness = max(2, 4 - i // 5)  # Thicker at start
                            cv2.line(debug_frame, trajectory[i-1], trajectory[i], color, thickness)
                        # Draw start point (release)
                        cv2.circle(debug_frame, trajectory[0], 8, (255, 0, 255), -1)
                        cv2.putText(debug_frame, "RELEASE",
                                   (trajectory[0][0] + 10, trajectory[0][1]),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 255), 1)

                    # Draw predicted trajectory (magenta dashed line)
                    if hasattr(self.ball_tracker, 'get_predicted_trajectory'):
                        predicted = self.ball_tracker.get_predicted_trajectory()
                        if predicted and len(trajectory) > 0:
                            # Connect last known position to first prediction
                            last_known = trajectory[-1]
                            cv2.line(debug_frame, last_known, predicted[0], (255, 0, 255), 2)
                            # Draw predicted path
                            for i in range(1, len(predicted)):
                                # Dashed effect - draw every other segment
                                if i % 2 == 0:
                                    cv2.line(debug_frame, predicted[i-1], predicted[i], (255, 0, 255), 2)
                                cv2.circle(debug_frame, predicted[i], 3, (255, 0, 255), -1)
                            cv2.putText(debug_frame, "PREDICTED",
                                       (predicted[-1][0] + 5, predicted[-1][1]),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 255), 1)

                # Also draw previous completed trajectories (faded)
                if hasattr(self.ball_tracker, 'all_flight_trajectories'):
                    for traj in self.ball_tracker.all_flight_trajectories:
                        if len(traj) > 1:
                            for i in range(1, len(traj)):
                                cv2.line(debug_frame, traj[i-1], traj[i], (100, 100, 100), 1)

                # Draw wrist position (cyan dot) - only for standard tracker
                if hasattr(self.ball_tracker, 'wrist_pos') and self.ball_tracker.wrist_pos:
                    cv2.circle(debug_frame, self.ball_tracker.wrist_pos, 8, (255, 255, 0), -1)

                # Draw search region when in flight (shows where HSV fallback is looking)
                if hasattr(self.ball_tracker, 'in_flight') and self.ball_tracker.in_flight:
                    predicted_pos = self.ball_tracker._get_predicted_position()
                    if predicted_pos:
                        # Calculate search radius (same logic as in _hsv_fallback_detect)
                        base_radius = 100
                        search_radius = base_radius + (self.ball_tracker.consecutive_misses * 30)
                        search_radius = min(search_radius, 300)
                        # Draw search region (dashed circle in orange)
                        cv2.circle(debug_frame, predicted_pos, search_radius, (0, 165, 255), 1)
                        cv2.circle(debug_frame, predicted_pos, 5, (0, 165, 255), -1)  # Center dot
                        cv2.putText(debug_frame, f"SEARCH r={search_radius}",
                                   (predicted_pos[0] + 10, predicted_pos[1] - 10),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 165, 255), 1)

                # Draw detected ball with detection source indicator
                if ball_detection.detected and ball_detection.center:
                    # Color based on detection method:
                    # Green = YOLO (>0.7), Cyan = CSRT (0.7), Yellow = HSV (<=0.5)
                    if ball_detection.confidence > 0.7:
                        box_color = (0, 255, 0)  # Green for YOLO
                        detection_label = "YOLO"
                    elif ball_detection.confidence == 0.7:
                        box_color = (255, 255, 0)  # Cyan for CSRT
                        detection_label = "CSRT"
                    else:
                        box_color = (0, 255, 255)  # Yellow for HSV
                        detection_label = "HSV"

                    cv2.circle(debug_frame, ball_detection.center, ball_detection.radius, box_color, 3)
                    cv2.putText(debug_frame, f"{detection_label} {ball_detection.confidence:.0%}",
                               (ball_detection.center[0] - 30, ball_detection.center[1] - ball_detection.radius - 5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 2)

                # Show CSRT tracker status
                if hasattr(self.ball_tracker, 'csrt_active') and self.ball_tracker.csrt_active:
                    cv2.putText(debug_frame, f"CSRT: {self.ball_tracker.csrt_confidence_frames}f",
                               (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)

                # Show frame number and ball status with detection source
                if ball_detection.detected:
                    if ball_detection.confidence > 0.7:
                        status, color = "BALL (YOLO)", (0, 255, 0)
                    elif ball_detection.confidence == 0.7:
                        status, color = "BALL (CSRT)", (255, 255, 0)
                    else:
                        status, color = "BALL (HSV)", (0, 255, 255)
                else:
                    status = "No ball"
                    color = (100, 100, 100)
                cv2.putText(debug_frame, f"Frame {frame_number}: {status}", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                # Show consecutive misses counter during flight
                if hasattr(self.ball_tracker, 'in_flight') and self.ball_tracker.in_flight:
                    misses = self.ball_tracker.consecutive_misses
                    if misses > 0:
                        cv2.putText(debug_frame, f"Misses: {misses}/{self.ball_tracker.max_consecutive_misses}",
                                   (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 100, 255), 2)

                debug_writer.write(debug_frame)
            
            poses.append(PoseFrame(
                frame_number=frame_number,
                timestamp_ms=timestamp_ms,
                landmarks=landmarks,
                visibility=visibility,
                ball=ball_detection
            ))
            
            frame_number += 1
            if frame_number % 30 == 0:
                print(f"  Processed {frame_number}/{total_frames}...", end='\r')
        
        if debug_writer:
            debug_writer.release()

        elapsed = time.time() - start_time
        print(f"  Processed {frame_number} frames in {elapsed:.1f}s")
        print(f"  Pose: {frames_with_pose}/{frame_number} ({100*frames_with_pose/max(1,frame_number):.0f}%)")
        if self.ball_tracker.enabled:
            tracker_name = "Custom" if self.use_custom_tracker else "YOLOv8+CSRT"
            print(f"  Ball ({tracker_name}): {frames_with_ball}/{frame_number} ({100*frames_with_ball/max(1,frame_number):.0f}%)")
            print(f"    - YOLO detections: {frames_with_ball_yolo}")
            print(f"    - CSRT tracking:   {frames_with_ball_csrt}")
            print(f"    - HSV fallback:    {frames_with_ball_hsv}")
            print(f"  Releases detected: {releases_detected}")
            if hasattr(self.ball_tracker, 'all_flight_trajectories'):
                trajectories = len(self.ball_tracker.all_flight_trajectories)
                print(f"  Flight trajectories captured: {trajectories}")
        else:
            print(f"  Ball: disabled (install ultralytics for YOLO detection)")
        print()
        
        cap.release()
        return poses, video_info
    
    def close(self):
        self.detector.close()


# ============================================================================
# Shot Detection
# ============================================================================

class ShotDetector:
    """
    Detect shots using ELBOW ANGLE transition:
    - Load: Elbow bent (triangle shape, ~60-100°)
    - Release: Elbow extended (straight line, ~150-180°)
    
    Also validates:
    - Pose must be stable (not just entering frame)
    - Wrist should be relatively high during release
    """
    
    def __init__(self, side_config: SideConfig):
        self.side = side_config
        self.min_shot_frames = 15
        self.min_frames_between_shots = 30
        self.stability_frames = 15  # Require this many frames of stable tracking
    
    def detect_shots(self, poses: List[PoseFrame]) -> List[Tuple[int, int, int]]:
        """Detect shots by finding elbow extension events."""
        
        if len(poses) < self.min_shot_frames:
            return [(0, len(poses) - 1, len(poses) // 2)]
        
        # Calculate elbow angles over time
        elbow_angles = self._calculate_elbow_angles(poses)
        
        # Find frames where pose is stable (good tracking)
        stable_frames = self._find_stable_frames(poses)
        
        # Find release points (elbow goes from bent to extended)
        releases = self._find_elbow_extensions(elbow_angles, stable_frames, poses)
        
        print(f"  Found {len(releases)} elbow extension events (potential releases)")
        
        if not releases:
            # Fallback to wrist peaks
            print("  Falling back to wrist peak detection...")
            releases = self._find_wrist_peaks(poses, stable_frames)
            print(f"  Found {len(releases)} wrist peaks")
        
        if not releases:
            return [(0, len(poses) - 1, len(poses) // 2)]
        
        # Build shot segments
        shots = []
        for release_frame in releases:
            start, end = self._expand_to_shot_segment(elbow_angles, release_frame, len(poses))
            
            if shots and start <= shots[-1][1]:
                start = shots[-1][1] + 1
            
            if end - start >= self.min_shot_frames:
                shots.append((start, end, release_frame))
        
        return shots if shots else [(0, len(poses) - 1, len(poses) // 2)]
    
    def _calculate_elbow_angles(self, poses: List[PoseFrame]) -> List[Optional[float]]:
        """Calculate elbow angle for each frame."""
        
        shoulder_name = self.side.shooting("shoulder")
        elbow_name = self.side.shooting("elbow")
        wrist_name = self.side.shooting("wrist")
        
        angles = []
        
        for pose in poses:
            shoulder = pose.landmarks.get(shoulder_name)
            elbow = pose.landmarks.get(elbow_name)
            wrist = pose.landmarks.get(wrist_name)
            
            if shoulder and elbow and wrist:
                angle = self._angle_between_points(shoulder, elbow, wrist)
                angles.append(angle)
            else:
                angles.append(None)
        
        return angles
    
    def _angle_between_points(self, p1, p2, p3) -> float:
        """Calculate angle at p2 between p1-p2-p3."""
        v1 = np.array([p1[0] - p2[0], p1[1] - p2[1]])
        v2 = np.array([p3[0] - p2[0], p3[1] - p2[1]])
        
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        
        if norm1 < 1e-6 or norm2 < 1e-6:
            return 0.0
        
        cos_angle = np.dot(v1, v2) / (norm1 * norm2)
        angle = np.arccos(np.clip(cos_angle, -1.0, 1.0))
        return np.degrees(angle)
    
    def _find_stable_frames(self, poses: List[PoseFrame]) -> set:
        """Find frames where pose tracking is stable."""
        
        stable = set()
        consecutive_good = 0
        
        key_landmarks = [
            self.side.shooting("shoulder"),
            self.side.shooting("elbow"),
            self.side.shooting("wrist"),
            self.side.shooting("hip")
        ]
        
        for i, pose in enumerate(poses):
            # Check if key landmarks are present and visible
            all_present = True
            for lm_name in key_landmarks:
                lm = pose.landmarks.get(lm_name)
                vis = pose.visibility.get(lm_name, 0)
                if not lm or vis < 0.5:
                    all_present = False
                    break
            
            if all_present:
                consecutive_good += 1
                if consecutive_good >= self.stability_frames:
                    stable.add(i)
            else:
                consecutive_good = 0
        
        return stable
    
    def _find_elbow_extensions(self, angles: List[Optional[float]], 
                                stable: set, poses: List[PoseFrame]) -> List[int]:
        """Find frames where elbow extends from bent to straight (release)."""
        
        releases = []
        
        # Smooth angles
        smoothed = self._smooth_angles(angles, window=5)
        
        # Parameters for shot detection
        bent_threshold = 120  # Elbow is "bent" below this angle
        extended_threshold = 150  # Elbow is "extended" above this angle
        
        wrist_name = self.side.shooting("wrist")
        shoulder_name = self.side.shooting("shoulder")
        
        in_shooting_motion = False
        motion_start = 0
        
        for i in range(1, len(smoothed)):
            if smoothed[i] is None or smoothed[i-1] is None:
                in_shooting_motion = False
                continue
            
            # Skip if not stable
            if i not in stable:
                in_shooting_motion = False
                continue
            
            curr_angle = smoothed[i]
            prev_angle = smoothed[i-1]
            
            # Detect start of shooting motion (elbow is bent)
            if not in_shooting_motion and curr_angle < bent_threshold:
                in_shooting_motion = True
                motion_start = i
            
            # Detect release (elbow extends past threshold)
            if in_shooting_motion and prev_angle < extended_threshold and curr_angle >= extended_threshold:
                # Validate: wrist should be above shoulder
                pose = poses[i]
                wrist = pose.landmarks.get(wrist_name)
                shoulder = pose.landmarks.get(shoulder_name)
                
                if wrist and shoulder and wrist[1] < shoulder[1]:  # Lower Y = higher position
                    # Valid release
                    if not releases or i - releases[-1] >= self.min_frames_between_shots:
                        releases.append(i)
                
                in_shooting_motion = False
        
        return releases
    
    def _find_wrist_peaks(self, poses: List[PoseFrame], stable: set) -> List[int]:
        """Fallback: find wrist height peaks."""
        
        wrist_name = self.side.shooting("wrist")
        shoulder_name = self.side.shooting("shoulder")
        
        # Get wrist heights (inverted Y)
        heights = []
        for pose in poses:
            wrist = pose.landmarks.get(wrist_name)
            heights.append(1.0 - wrist[1] if wrist else None)
        
        # Smooth
        smoothed = self._smooth_angles(heights, window=7)
        
        # Find peaks
        peaks = []
        for i in range(3, len(smoothed) - 3):
            if smoothed[i] is None or i not in stable:
                continue
            
            is_peak = True
            for offset in [-3, -2, -1, 1, 2, 3]:
                if smoothed[i + offset] is not None and smoothed[i + offset] >= smoothed[i]:
                    is_peak = False
                    break
            
            if is_peak:
                # Validate: wrist above shoulder
                pose = poses[i]
                wrist = pose.landmarks.get(wrist_name)
                shoulder = pose.landmarks.get(shoulder_name)
                
                if wrist and shoulder and wrist[1] < shoulder[1]:
                    if not peaks or i - peaks[-1] >= self.min_frames_between_shots:
                        peaks.append(i)
        
        return peaks
    
    def _smooth_angles(self, values: List[Optional[float]], window: int) -> List[Optional[float]]:
        """Smooth values with gaps."""
        result = []
        half = window // 2
        
        for i in range(len(values)):
            if values[i] is None:
                result.append(None)
                continue
            
            nearby = []
            for j in range(max(0, i - half), min(len(values), i + half + 1)):
                if values[j] is not None:
                    nearby.append(values[j])
            
            result.append(np.mean(nearby) if nearby else None)
        
        return result
    
    def _expand_to_shot_segment(self, angles: List[Optional[float]], 
                                 release_idx: int, total_frames: int) -> Tuple[int, int]:
        """Expand from release to full shot segment."""
        
        # Find start: go back to where elbow was most bent
        start = max(0, release_idx - 45)
        min_angle = float('inf')
        load_frame = start
        
        for i in range(release_idx - 1, start, -1):
            if angles[i] is not None and angles[i] < min_angle:
                min_angle = angles[i]
                load_frame = i
        
        start = max(0, load_frame - 5)
        
        # End: include follow-through
        end = min(total_frames - 1, release_idx + 25)
        
        return start, end
    
    def find_shot_phases(self, poses: List[PoseFrame], release_idx: int) -> Dict[str, int]:
        """Find key phases within a shot using elbow angle."""
        n = len(poses)
        release_frame = min(release_idx, n - 1)
        
        # Find load phase (where elbow is most bent before release)
        shoulder_name = self.side.shooting("shoulder")
        elbow_name = self.side.shooting("elbow")
        wrist_name = self.side.shooting("wrist")
        
        min_angle = float('inf')
        load_frame = 0
        
        for i, pose in enumerate(poses[:release_frame + 1]):
            shoulder = pose.landmarks.get(shoulder_name)
            elbow = pose.landmarks.get(elbow_name)
            wrist = pose.landmarks.get(wrist_name)
            
            if shoulder and elbow and wrist:
                angle = self._angle_between_points(shoulder, elbow, wrist)
                if angle < min_angle:
                    min_angle = angle
                    load_frame = i
        
        return {
            "stance": 0,
            "load": load_frame,
            "release": release_frame,
            "follow_through": min(n - 1, release_frame + (n - release_frame) // 2)
        }


# ============================================================================
# Form Analysis
# ============================================================================

class FormAnalyzer:
    def __init__(self, side_config: SideConfig):
        self.side = side_config
    
    def analyze_shot(self, poses: List[PoseFrame], phases: Dict[str, int]) -> Tuple[JointAngles, FormMetrics]:
        release = poses[phases["release"]] if phases["release"] < len(poses) else poses[-1]
        load = poses[phases["load"]] if phases["load"] < len(poses) else poses[0]
        follow = poses[phases["follow_through"]] if phases["follow_through"] < len(poses) else poses[-1]
        
        angles = self._calc_angles(release, load)
        metrics = self._calc_metrics(release, load, follow, angles)
        return angles, metrics
    
    def _calc_angles(self, release: PoseFrame, load: PoseFrame) -> JointAngles:
        def angle(p1, p2, p3):
            if not all([p1, p2, p3]):
                return 0.0
            v1 = np.array([p1[0] - p2[0], p1[1] - p2[1]])
            v2 = np.array([p3[0] - p2[0], p3[1] - p2[1]])
            n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
            if n1 < 1e-6 or n2 < 1e-6:
                return 0.0
            cos_a = np.dot(v1, v2) / (n1 * n2)
            return np.degrees(np.arccos(np.clip(cos_a, -1.0, 1.0)))
        
        rl, ll = release.landmarks, load.landmarks
        
        elbow_angle = angle(rl.get(self.side.shooting("shoulder")),
                           rl.get(self.side.shooting("elbow")),
                           rl.get(self.side.shooting("wrist")))
        
        knee_angle = angle(ll.get(self.side.shooting("hip")),
                          ll.get(self.side.shooting("knee")),
                          ll.get(self.side.shooting("ankle")))
        
        shoulder_angle = angle(rl.get(self.side.shooting("hip")),
                              rl.get(self.side.shooting("shoulder")),
                              rl.get(self.side.shooting("elbow")))
        
        return JointAngles(elbow_angle, knee_angle, shoulder_angle)
    
    def _calc_metrics(self, release: PoseFrame, load: PoseFrame, follow: PoseFrame, angles: JointAngles) -> FormMetrics:
        # Elbow flare
        shoulder = release.landmarks.get(self.side.shooting("shoulder"))
        elbow = release.landmarks.get(self.side.shooting("elbow"))
        elbow_flare = 0.0
        if shoulder and elbow:
            dx = elbow[0] - shoulder[0]
            dy = elbow[1] - shoulder[1]
            elbow_flare = max(0, abs(np.degrees(np.arctan2(dx, dy))) - 10)
        elbow_score = max(0, 100 - int(elbow_flare * 5))
        
        # Release height
        wrist = release.landmarks.get(self.side.shooting("wrist"))
        nose = release.landmarks.get("nose")
        hip = release.landmarks.get(self.side.shooting("hip"))
        release_height = 0.0
        if wrist and nose and hip:
            body_h = abs(nose[1] - hip[1])
            if body_h > 0.01:
                release_height = (nose[1] - wrist[1]) / body_h
        
        if release_height > 0.15: release_score = 95
        elif release_height > 0.05: release_score = 85
        elif release_height > -0.05: release_score = 70
        elif release_height > -0.15: release_score = 50
        else: release_score = 30
        
        # Knee bend
        ka = angles.knee_angle
        if ka < 1: base_score = 50
        elif 110 <= ka <= 140: base_score = 100
        elif 100 <= ka <= 150: base_score = 80
        elif 90 <= ka <= 160: base_score = 60
        else: base_score = 40
        
        # Follow through
        rw = release.landmarks.get(self.side.shooting("wrist"))
        fw = follow.landmarks.get(self.side.shooting("wrist"))
        if rw and fw:
            movement = abs(fw[1] - rw[1])
            if movement > 0.05: follow_score = 90
            elif movement > 0.02: follow_score = 70
            else: follow_score = 50
        else:
            follow_score = 50
        
        overall = int(elbow_score * 0.30 + release_score * 0.25 + base_score * 0.25 + follow_score * 0.20)
        
        return FormMetrics(elbow_flare, elbow_score, release_height, release_score,
                          angles.knee_angle, base_score, follow_score, overall)


# ============================================================================
# Video Annotation
# ============================================================================

class VideoAnnotator:
    CONNECTIONS = [
        ("left_shoulder", "right_shoulder"),
        ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
        ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
        ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"),
        ("left_hip", "right_hip"),
        ("left_hip", "left_knee"), ("left_knee", "left_ankle"),
        ("right_hip", "right_knee"), ("right_knee", "right_ankle"),
    ]
    
    def __init__(self, side: SideConfig):
        self.side = side
    
    def create_annotated_video(self, input_path: str, poses: List[PoseFrame],
                               shots: List[ShotAnalysis], output_path: str) -> str:
        cap = cv2.VideoCapture(input_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        out = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))
        
        frame_to_shot = {}
        for shot in shots:
            for f in range(shot.start_frame, shot.end_frame + 1):
                frame_to_shot[f] = shot
        
        frame_num = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            if frame_num < len(poses):
                pose = poses[frame_num]
                shot = frame_to_shot.get(frame_num)
                
                if pose.ball and pose.ball.detected and pose.ball.center:
                    cv2.circle(frame, pose.ball.center, pose.ball.radius, (0, 255, 255), 2)
                
                self._draw_skeleton(frame, pose, w, h)
                
                if shot:
                    self._draw_metrics(frame, shot, frame_num, w, h)
                else:
                    cv2.rectangle(frame, (10, 10), (200, 45), (40, 40, 40), -1)
                    cv2.putText(frame, "Waiting...", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 150, 150), 1)
            
            out.write(frame)
            frame_num += 1
        
        cap.release()
        out.release()
        return output_path
    
    def _draw_skeleton(self, frame, pose: PoseFrame, w: int, h: int):
        if not pose.landmarks:
            return
        
        for s, e in self.CONNECTIONS:
            p1, p2 = pose.landmarks.get(s), pose.landmarks.get(e)
            if not p1 or not p2:
                continue
            if pose.visibility.get(s, 0) < 0.5 or pose.visibility.get(e, 0) < 0.5:
                continue
            
            pt1 = (int(p1[0] * w), int(p1[1] * h))
            pt2 = (int(p2[0] * w), int(p2[1] * h))
            
            is_arm = self.side.is_shooting_side(s) and self.side.is_shooting_side(e) and \
                     ("elbow" in s or "wrist" in s or "elbow" in e or "wrist" in e)
            
            color = (0, 165, 255) if is_arm else (0, 255, 128)
            cv2.line(frame, pt1, pt2, color, 3 if is_arm else 2)
        
        for name, coords in pose.landmarks.items():
            if name not in KEY_LANDMARKS or pose.visibility.get(name, 0) < 0.5:
                continue
            pt = (int(coords[0] * w), int(coords[1] * h))
            is_key = name in [self.side.shooting("wrist"), self.side.shooting("elbow")]
            cv2.circle(frame, pt, 8 if is_key else 5, (0, 165, 255) if is_key else (255, 255, 255), -1)
    
    def _draw_metrics(self, frame, shot: ShotAnalysis, frame_num: int, w: int, h: int):
        m = shot.metrics
        rel_frame = frame_num - shot.start_frame
        rel_release = shot.release_frame - shot.start_frame
        
        if rel_frame <= shot.phases["load"]:
            phase, color = "STANCE", (200, 200, 200)
        elif rel_frame <= rel_release:
            phase, color = "SHOOTING", (0, 165, 255)
        else:
            phase, color = "FOLLOW THROUGH", (0, 255, 128)
        
        cv2.rectangle(frame, (10, 10), (280, 45), (40, 40, 40), -1)
        cv2.putText(frame, f"SHOT {shot.shot_number} - {phase}", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
        
        bx = w - 170
        cv2.rectangle(frame, (bx, 10), (w - 10, 125), (40, 40, 40), -1)
        
        sc = (0, 255, 0) if m.overall_score >= 80 else (0, 200, 255) if m.overall_score >= 60 else (0, 0, 255)
        cv2.putText(frame, f"Score: {m.overall_score}", (bx + 10, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.75, sc, 2)
        
        def mc(v): return (0, 255, 0) if v >= 70 else (0, 0, 255)
        cv2.putText(frame, f"Elbow: {m.elbow_score}", (bx + 10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.45, mc(m.elbow_score), 1)
        cv2.putText(frame, f"Release: {m.release_score}", (bx + 10, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.45, mc(m.release_score), 1)
        cv2.putText(frame, f"Base: {m.base_score}", (bx + 10, 96), cv2.FONT_HERSHEY_SIMPLEX, 0.45, mc(m.base_score), 1)
        cv2.putText(frame, f"Follow: {m.follow_through_score}", (bx + 10, 114), cv2.FONT_HERSHEY_SIMPLEX, 0.45, mc(m.follow_through_score), 1)


# ============================================================================
# Results Printing
# ============================================================================

def print_results(shots: List[ShotAnalysis]):
    for shot in shots:
        m = shot.metrics
        print(f"\n{'='*50}")
        print(f"  SHOT {shot.shot_number}")
        print(f"{'='*50}")
        
        bar = "█" * (m.overall_score // 4) + "░" * (25 - m.overall_score // 4)
        print(f"  Score: {m.overall_score}/100  [{bar}]")
        
        grade = "A" if m.overall_score >= 90 else "B" if m.overall_score >= 80 else "C" if m.overall_score >= 70 else "D" if m.overall_score >= 60 else "F"
        print(f"  Grade: {grade}")
        
        print(f"\n  {'✓' if m.elbow_score >= 70 else '✗'} Elbow: {m.elbow_score} (flare: {m.elbow_flare_degrees:.1f}°)")
        print(f"  {'✓' if m.release_score >= 70 else '✗'} Release: {m.release_score} (height: {m.release_height_ratio:.2f})")
        print(f"  {'✓' if m.base_score >= 70 else '✗'} Base: {m.base_score} (knee: {m.knee_bend_angle:.1f}°)")
        print(f"  {'✓' if m.follow_through_score >= 70 else '✗'} Follow: {m.follow_through_score}")
    
    if len(shots) > 1:
        scores = [s.metrics.overall_score for s in shots]
        print(f"\n{'='*50}")
        print(f"  SUMMARY ({len(shots)} shots)")
        print(f"{'='*50}")
        print(f"  Average: {sum(scores)/len(scores):.0f}")
        print(f"  Best: Shot #{scores.index(max(scores))+1} ({max(scores)})")
        print(f"  Consistency: {100 - (max(scores) - min(scores))}%")
        
        avgs = {
            "Elbow": sum(s.metrics.elbow_score for s in shots) / len(shots),
            "Release": sum(s.metrics.release_score for s in shots) / len(shots),
            "Base": sum(s.metrics.base_score for s in shots) / len(shots),
            "Follow": sum(s.metrics.follow_through_score for s in shots) / len(shots),
        }
        worst = min(avgs.items(), key=lambda x: x[1])
        if worst[1] < 70:
            print(f"\n  🎯 Focus on: {worst[0]} ({worst[1]:.0f}/100)")


# ============================================================================
# Main
# ============================================================================

def run(video_path: str, use_left: bool = False, debug_ball: bool = False,
        use_custom_tracker: bool = False, frame_skip: int = 1):
    print()
    print("╔════════════════════════════════════════════════════╗")
    print("║    FORMCHECK v3.1 - Elbow Angle Shot Detection 🏀    ║")
    print("╚════════════════════════════════════════════════════╝")
    print()

    side = SideConfig(use_left)
    print(f"Tracking: {side.shooting_side.upper()} hand")
    if use_custom_tracker:
        print(f"Ball Tracker: CUSTOM (basketball-trained model)")
    else:
        print(f"Ball Tracker: YOLO (yolov8n - sports ball)")
    if frame_skip > 1:
        print(f"Frame Skip: Processing every {frame_skip} frames (faster)")
    print()

    extractor = PoseExtractor(use_custom_tracker=use_custom_tracker, frame_skip=frame_skip)
    detector = ShotDetector(side)
    analyzer = FormAnalyzer(side)
    annotator = VideoAnnotator(side)
    
    try:
        poses, info = extractor.extract_from_video(video_path, debug_ball, side.shooting_side)
        
        if sum(1 for p in poses if p.landmarks) == 0:
            print("⚠️ No poses detected!")
            return
        
        print("Detecting shots...")
        segments = detector.detect_shots(poses)
        print(f"  Found {len(segments)} shot(s)")
        
        shots = []
        for i, (start, end, release) in enumerate(segments):
            print(f"  Shot {i+1}: frames {start}-{end}, release at {release}")
            shot_poses = poses[start:end+1]
            phases = detector.find_shot_phases(shot_poses, release - start)
            angles, metrics = analyzer.analyze_shot(shot_poses, phases)
            shots.append(ShotAnalysis(i+1, start, end, release, phases, angles, metrics))
        
        print_results(shots)
        
        out_path = str(Path(video_path).stem) + "_annotated.mp4"
        print(f"\nCreating: {out_path}")
        annotator.create_annotated_video(video_path, poses, shots, out_path)
        print(f"✓ Done!")
        
    finally:
        extractor.close()


def main():
    parser = argparse.ArgumentParser(description="Basketball shooting form analyzer")
    parser.add_argument("video", help="Video file path")
    parser.add_argument("--left", "-l", action="store_true", help="Track left hand")
    parser.add_argument("--debug-ball", action="store_true", help="Save ball detection debug video")
    parser.add_argument("--custom-tracker", "-c", action="store_true",
                       help="Use custom basketball-trained model instead of YOLO")
    parser.add_argument("--frame-skip", "-s", type=int, default=1,
                       help="Process every Nth frame (default: 1, higher = faster)")
    parser.add_argument("--fast", "-f", action="store_true",
                       help="Fast mode: skip every other frame (same as --frame-skip 2)")
    args = parser.parse_args()

    if not Path(args.video).exists():
        print(f"Error: {args.video} not found")
        sys.exit(1)

    frame_skip = 2 if args.fast else args.frame_skip
    run(args.video, args.left, args.debug_ball, args.custom_tracker, frame_skip)


if __name__ == "__main__":
    main()