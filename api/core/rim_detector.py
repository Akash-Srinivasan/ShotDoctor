#!/usr/bin/env python3
"""
RimDetector - Basketball rim detection using computer vision.

This module provides rim detection capabilities for the FormCheck app.
It supports multiple detection methods and includes debugging/visualization tools.

Usage:
    python rim_detector.py video.mp4              # Run detection on video
    python rim_detector.py video.mp4 --debug      # Show debug visualization
    python rim_detector.py video.mp4 --method yolo  # Use YOLO instead of Hough
"""

import cv2
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict
import argparse
import sys
from pathlib import Path


@dataclass
class RimDetection:
    """Represents a detected rim."""
    x: int              # Top-left x
    y: int              # Top-left y
    width: int          # Bounding box width
    height: int         # Bounding box height
    confidence: float   # Detection confidence (0-1)
    method: str         # Detection method used
    center: Tuple[int, int] = None  # Center point

    def __post_init__(self):
        if self.center is None:
            self.center = (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def bbox(self) -> Tuple[int, int, int, int]:
        """Return (x, y, w, h) bounding box."""
        return (self.x, self.y, self.width, self.height)

    @property
    def area(self) -> int:
        """Return area of bounding box."""
        return self.width * self.height


class RimDetector:
    """
    Detect basketball rims in video frames.

    Supports multiple detection methods:
    - 'hough': OpenCV Hough Circle detection (fast, works for circular rims)
    - 'yolo': YOLOv8 object detection (more robust, requires ultralytics)
    - 'color': Color-based detection (for orange rims)
    - 'combined': Use multiple methods and merge results

    For debugging multiple rim scenarios, use detect_all() to get all
    detected rims, then use ball trajectory to determine the active rim.
    """

    def __init__(self, method: str = "hough", debug: bool = False):
        """
        Initialize rim detector.

        Args:
            method: Detection method ('hough', 'yolo', 'color', 'combined')
            debug: Enable debug output
        """
        self.method = method
        self.debug = debug
        self.yolo_model = None
        self.enabled = True

        # Hough circle parameters (tunable)
        self.hough_params = {
            'dp': 1.2,
            'min_dist': 100,
            'param1': 50,
            'param2': 30,
            'min_radius': 15,
            'max_radius': 150,
        }

        # Color detection parameters (for orange rims)
        self.orange_hsv_lower = np.array([5, 100, 100])
        self.orange_hsv_upper = np.array([25, 255, 255])

        # Load YOLO if requested
        if method in ['yolo', 'combined']:
            self._init_yolo()

    def _init_yolo(self):
        """Initialize YOLO model."""
        try:
            from ultralytics import YOLO
            self.yolo_model = YOLO('yolov8n.pt')
            if self.debug:
                print("✓ YOLOv8 loaded for rim detection")
        except ImportError:
            print("⚠️  YOLOv8 not available (pip install ultralytics)")
            self.yolo_model = None
            if self.method == 'yolo':
                print("   Falling back to Hough method")
                self.method = 'hough'

    def detect(self, frame: np.ndarray) -> Optional[RimDetection]:
        """
        Detect the most likely rim in a frame.

        Args:
            frame: BGR image (numpy array)

        Returns:
            RimDetection or None if no rim found
        """
        detections = self.detect_all(frame)
        if not detections:
            return None

        # Return highest confidence detection
        return max(detections, key=lambda d: d.confidence)

    def detect_all(self, frame: np.ndarray) -> List[RimDetection]:
        """
        Detect ALL rims in a frame (useful for multi-hoop scenarios).

        Args:
            frame: BGR image (numpy array)

        Returns:
            List of RimDetection objects
        """
        if self.method == 'hough':
            return self._detect_hough(frame)
        elif self.method == 'yolo':
            return self._detect_yolo(frame)
        elif self.method == 'color':
            return self._detect_color(frame)
        elif self.method == 'combined':
            return self._detect_combined(frame)
        else:
            return self._detect_hough(frame)

    def _detect_hough(self, frame: np.ndarray) -> List[RimDetection]:
        """Detect rims using Hough Circle detection."""
        detections = []

        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Apply blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (9, 9), 2)

        # Detect circles
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=self.hough_params['dp'],
            minDist=self.hough_params['min_dist'],
            param1=self.hough_params['param1'],
            param2=self.hough_params['param2'],
            minRadius=self.hough_params['min_radius'],
            maxRadius=self.hough_params['max_radius']
        )

        if circles is not None:
            circles = np.uint16(np.around(circles))
            for circle in circles[0]:
                x, y, r = circle
                # Convert to bounding box
                detections.append(RimDetection(
                    x=int(x - r),
                    y=int(y - r),
                    width=int(2 * r),
                    height=int(2 * r),
                    confidence=0.7,  # Hough doesn't give confidence, use default
                    method='hough',
                    center=(int(x), int(y))
                ))

        return detections

    def _detect_yolo(self, frame: np.ndarray) -> List[RimDetection]:
        """Detect rims using YOLO."""
        detections = []

        if self.yolo_model is None:
            return detections

        # Run YOLO - class 32 is sports ball, but we can also look for
        # general objects and filter by shape/position
        # Note: Standard YOLO doesn't have a "rim" class, so we detect
        # sports equipment and filter
        results = self.yolo_model(frame, verbose=False)

        for result in results:
            if result.boxes is None:
                continue

            for i in range(len(result.boxes)):
                conf = float(result.boxes.conf[i])
                cls = int(result.boxes.cls[i])

                # Class filtering - look for objects that could be hoops
                # 32: sports ball, 43: tennis racket (sometimes detects as sports equipment)
                # We'll use a more general approach and filter by aspect ratio
                x1, y1, x2, y2 = result.boxes.xyxy[i].tolist()
                w, h = x2 - x1, y2 - y1

                # Rim-like aspect ratio (roughly square to slightly wide)
                aspect_ratio = w / h if h > 0 else 0
                if 0.5 < aspect_ratio < 2.0 and conf > 0.3:
                    detections.append(RimDetection(
                        x=int(x1),
                        y=int(y1),
                        width=int(w),
                        height=int(h),
                        confidence=conf,
                        method='yolo'
                    ))

        return detections

    def _detect_color(self, frame: np.ndarray) -> List[RimDetection]:
        """Detect orange rims using color segmentation."""
        detections = []

        # Convert to HSV
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Create mask for orange color
        mask = cv2.inRange(hsv, self.orange_hsv_lower, self.orange_hsv_upper)

        # Morphological operations to clean up
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            area = cv2.contourArea(contour)

            # Filter by area (rim should be reasonably sized)
            if 500 < area < 50000:
                # Fit ellipse if possible (rims are roughly circular/elliptical)
                if len(contour) >= 5:
                    ellipse = cv2.fitEllipse(contour)
                    (cx, cy), (ma, MA), angle = ellipse

                    # Check circularity (ratio of minor to major axis)
                    if MA > 0 and ma / MA > 0.3:
                        x, y, w, h = cv2.boundingRect(contour)
                        detections.append(RimDetection(
                            x=x,
                            y=y,
                            width=w,
                            height=h,
                            confidence=min(area / 10000, 1.0),
                            method='color',
                            center=(int(cx), int(cy))
                        ))

        return detections

    def _detect_combined(self, frame: np.ndarray) -> List[RimDetection]:
        """Combine multiple detection methods."""
        all_detections = []

        # Run all methods
        all_detections.extend(self._detect_hough(frame))
        all_detections.extend(self._detect_color(frame))

        if self.yolo_model:
            all_detections.extend(self._detect_yolo(frame))

        # Merge overlapping detections
        merged = self._merge_detections(all_detections)

        return merged

    def _merge_detections(self, detections: List[RimDetection],
                          iou_threshold: float = 0.5) -> List[RimDetection]:
        """Merge overlapping detections using NMS-like approach."""
        if not detections:
            return []

        # Sort by confidence
        detections = sorted(detections, key=lambda d: d.confidence, reverse=True)

        merged = []
        used = set()

        for i, det in enumerate(detections):
            if i in used:
                continue

            # Find overlapping detections
            overlapping = [det]
            for j, other in enumerate(detections[i+1:], start=i+1):
                if j in used:
                    continue
                if self._iou(det.bbox, other.bbox) > iou_threshold:
                    overlapping.append(other)
                    used.add(j)

            # Merge by averaging
            if len(overlapping) > 1:
                avg_x = int(np.mean([d.x for d in overlapping]))
                avg_y = int(np.mean([d.y for d in overlapping]))
                avg_w = int(np.mean([d.width for d in overlapping]))
                avg_h = int(np.mean([d.height for d in overlapping]))
                max_conf = max(d.confidence for d in overlapping)
                merged.append(RimDetection(
                    x=avg_x, y=avg_y, width=avg_w, height=avg_h,
                    confidence=max_conf,
                    method='combined'
                ))
            else:
                merged.append(det)

            used.add(i)

        return merged

    def _iou(self, box1: Tuple[int, int, int, int],
             box2: Tuple[int, int, int, int]) -> float:
        """Calculate Intersection over Union."""
        x1, y1, w1, h1 = box1
        x2, y2, w2, h2 = box2

        # Calculate intersection
        xi1 = max(x1, x2)
        yi1 = max(y1, y2)
        xi2 = min(x1 + w1, x2 + w2)
        yi2 = min(y1 + h1, y2 + h2)

        if xi2 <= xi1 or yi2 <= yi1:
            return 0.0

        intersection = (xi2 - xi1) * (yi2 - yi1)
        union = w1 * h1 + w2 * h2 - intersection

        return intersection / union if union > 0 else 0.0

    def is_rim_visible_in_sequence(self, frames: List[np.ndarray],
                                    threshold: int = 1) -> bool:
        """
        Check if rim appears in at least `threshold` frames.

        Args:
            frames: List of BGR images
            threshold: Minimum number of frames with rim detection

        Returns:
            True if rim visible in enough frames
        """
        count = 0
        for frame in frames:
            if self.detect(frame) is not None:
                count += 1
                if count >= threshold:
                    return True
        return False

    def visualize(self, frame: np.ndarray,
                  detections: List[RimDetection] = None) -> np.ndarray:
        """
        Draw detections on frame for debugging.

        Args:
            frame: BGR image
            detections: List of detections (if None, will detect)

        Returns:
            Annotated frame
        """
        annotated = frame.copy()

        if detections is None:
            detections = self.detect_all(frame)

        colors = {
            'hough': (0, 255, 0),    # Green
            'yolo': (255, 0, 0),     # Blue
            'color': (0, 165, 255),  # Orange
            'combined': (255, 255, 0) # Cyan
        }

        for i, det in enumerate(detections):
            color = colors.get(det.method, (255, 255, 255))

            # Draw bounding box
            cv2.rectangle(
                annotated,
                (det.x, det.y),
                (det.x + det.width, det.y + det.height),
                color, 2
            )

            # Draw center point
            cv2.circle(annotated, det.center, 5, color, -1)

            # Draw label
            label = f"Rim {i+1} ({det.method}): {det.confidence:.2f}"
            cv2.putText(
                annotated, label,
                (det.x, det.y - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2
            )

        # Draw legend
        y = 30
        cv2.putText(annotated, f"Method: {self.method}", (10, y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(annotated, f"Detections: {len(detections)}", (10, y + 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        return annotated


def run_debug_video(video_path: str, method: str = "hough",
                    output_path: str = None, show: bool = True):
    """
    Run rim detection on a video with visualization.

    Args:
        video_path: Path to video file
        method: Detection method
        output_path: Optional path to save annotated video
        show: Show video in window
    """
    detector = RimDetector(method=method, debug=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video: {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"\n{'='*60}")
    print(f"  RIM DETECTOR DEBUG")
    print(f"{'='*60}")
    print(f"Video: {video_path}")
    print(f"Resolution: {width}x{height} @ {fps:.1f}fps")
    print(f"Frames: {total_frames}")
    print(f"Method: {method}")
    print(f"{'='*60}\n")

    # Setup video writer if output requested
    writer = None
    if output_path:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    frame_count = 0
    frames_with_rim = 0
    all_detections_count = []

    print("Processing... (Press 'q' to quit, 'p' to pause)")

    paused = False
    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1

            # Detect rims
            detections = detector.detect_all(frame)
            all_detections_count.append(len(detections))

            if detections:
                frames_with_rim += 1

            # Visualize
            annotated = detector.visualize(frame, detections)

            # Add frame counter
            cv2.putText(annotated, f"Frame: {frame_count}/{total_frames}",
                       (width - 200, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            # Write to output
            if writer:
                writer.write(annotated)

            # Show progress
            if frame_count % 30 == 0:
                pct = (frame_count / total_frames) * 100
                print(f"  {pct:.0f}% - Frame {frame_count}, Rims detected: {len(detections)}")

        # Display
        if show:
            cv2.imshow('Rim Detection Debug', annotated)

            key = cv2.waitKey(1 if not paused else 0) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('p'):
                paused = not paused
                print("PAUSED" if paused else "RESUMED")
            elif key == ord('n') and paused:
                # Next frame when paused
                paused = False
                continue

    cap.release()
    if writer:
        writer.release()
    cv2.destroyAllWindows()

    # Print summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"Total frames: {frame_count}")
    print(f"Frames with rim: {frames_with_rim} ({100*frames_with_rim/frame_count:.1f}%)")
    if all_detections_count:
        print(f"Avg detections per frame: {np.mean(all_detections_count):.2f}")
        print(f"Max detections in frame: {max(all_detections_count)}")
    if output_path:
        print(f"Output saved to: {output_path}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description='Basketball Rim Detection Debug Tool')
    parser.add_argument('video', help='Path to video file')
    parser.add_argument('--method', choices=['hough', 'yolo', 'color', 'combined'],
                       default='hough', help='Detection method')
    parser.add_argument('--output', '-o', help='Output video path')
    parser.add_argument('--no-show', action='store_true', help='Disable display window')

    args = parser.parse_args()

    if not Path(args.video).exists():
        print(f"Error: Video not found: {args.video}")
        sys.exit(1)

    run_debug_video(
        args.video,
        method=args.method,
        output_path=args.output,
        show=not args.no_show
    )


if __name__ == "__main__":
    main()
