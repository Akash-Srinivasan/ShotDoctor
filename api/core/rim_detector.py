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

        # Color detection parameters for rim (orange to red)
        # Two ranges needed because red wraps around H=0/180 in HSV
        # Very low S/V thresholds: gym rims can appear washed-out (S~30-40)
        # under dim or fluorescent lighting
        self.rim_hsv_ranges = [
            (np.array([0, 25, 40]), np.array([30, 255, 255])),    # red → orange → yellow
            (np.array([170, 25, 40]), np.array([180, 255, 255])), # deep red wrap-around
        ]
        # Legacy single range (used by _detect_color full-frame method)
        self.orange_hsv_lower = np.array([0, 25, 40])
        self.orange_hsv_upper = np.array([30, 255, 255])

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

    def detect_near_point(self, frame: np.ndarray, center: Tuple[int, int],
                          min_radius_frac: float = 0.03,
                          max_radius_frac: float = 0.20) -> List[RimDetection]:
        """
        Detect rims near a point using orange/red color contour detection,
        with Hough circle fallback if color finds nothing.

        Crops ~20% of frame dimensions around `center`, finds orange/red contours,
        fits ellipses, and returns detections. Works for both front-view (circular)
        and side-view (elliptical) rims.

        Args:
            frame: BGR image (numpy array)
            center: (x, y) pixel coordinates to search around
            min_radius_frac: Minimum rim radius as fraction of frame width
            max_radius_frac: Maximum rim radius as fraction of frame width

        Returns:
            List of RimDetection objects sorted by size (largest first),
            with coordinates in full-frame space.
        """
        h, w = frame.shape[:2]
        cx, cy = center

        # Crop region: 30% of frame dimensions around the point
        crop_half_w = int(w * 0.15)
        crop_half_h = int(h * 0.15)
        x1 = max(0, cx - crop_half_w)
        y1 = max(0, cy - crop_half_h)
        x2 = min(w, cx + crop_half_w)
        y2 = min(h, cy + crop_half_h)
        crop = frame[y1:y2, x1:x2]

        if crop.size == 0:
            return []

        # --- Primary: Color contour detection ---
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

        # Combine multiple HSV ranges (orange + red wrap-around)
        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for lower, upper in self.rim_hsv_ranges:
            mask |= cv2.inRange(hsv, lower, upper)

        # Clean up mask (small kernel to preserve thin rim contours)
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        min_dim = int(w * min_radius_frac * 2)  # minimum diameter in pixels
        max_dim = int(w * max_radius_frac * 2)  # maximum diameter in pixels

        # Scan a horizontal band around the user mark for the rim.
        # The rim is a thin orange band at the user's Y position — find its
        # horizontal extent to measure the diameter.
        crop_h, crop_w = crop.shape[:2]
        crop_cy = crop_h // 2  # user mark is at crop center

        # Try narrow band first (±25px). If it finds no orange, widen to ±50px.
        # The wider band catches the top/bottom arcs of the rim ring when the
        # net occludes the center (common on front-view shots).
        for band_half in (25, 50):
            band_top = max(0, crop_cy - band_half)
            band_bot = min(crop_h, crop_cy + band_half)
            band_mask = mask[band_top:band_bot, :]
            if np.count_nonzero(band_mask) >= 5:
                break

        # Log color detection diagnostics
        total_orange = int(np.count_nonzero(mask))
        band_orange = int(np.count_nonzero(band_mask))
        print(f"   🎨 Color scan: {total_orange} orange px in crop, {band_orange} in band (±{band_half}px)")

        # Find orange columns in the band, then measure the rim diameter.
        #
        # Key insight: the rim can appear as TWO separate orange runs in the
        # horizontal band — the left and right arcs of the circle — with a gap
        # in the middle (the rim interior / net). A single-run approach picks
        # only one arc and gets half the diameter. Instead:
        #   1. Split into contiguous runs (gap > 5px = separate segment)
        #   2. Keep only runs whose center is within max_radius of crop center
        #      (filters out distant orange objects like posts or backboard frame)
        #   3. Span from leftmost to rightmost kept run = rim diameter
        orange_cols = np.where(band_mask.any(axis=0))[0]

        if len(orange_cols) >= 5:  # need at least a few pixels
            # Build contiguous runs (gap > 5px = separate segment)
            runs = []
            run_start = int(orange_cols[0])
            prev_col = int(orange_cols[0])
            for col in orange_cols[1:]:
                col = int(col)
                if col - prev_col > 5:
                    runs.append((run_start, prev_col))
                    run_start = col
                prev_col = col
            runs.append((run_start, prev_col))

            # Strategy: find the most SYMMETRIC pair of runs about the crop center.
            #
            # The rim's left and right arcs appear equidistant from center.
            # Other orange objects (ball, posts, backboard frame) are off-center
            # and would form an asymmetric pair. If no good symmetric pair is
            # found, fall back to the single run closest to center.
            crop_center_x = crop_w // 2
            half_max = max_dim // 2

            # Filter to runs within max_radius of crop center
            nearby_runs = [r for r in runs
                           if abs((r[0] + r[1]) // 2 - crop_center_x) <= half_max]
            if not nearby_runs:
                nearby_runs = [min(runs, key=lambda r: abs((r[0] + r[1]) // 2 - crop_center_x))]

            left_runs = [r for r in nearby_runs if (r[0] + r[1]) // 2 <  crop_center_x]
            right_runs = [r for r in nearby_runs if (r[0] + r[1]) // 2 >= crop_center_x]

            left_col, right_col = None, None

            if left_runs and right_runs:
                # Try every (left, right) combination; pick most symmetric pair
                # whose combined span is within the allowed rim diameter range.
                best_score = float('inf')
                for lr in left_runs:
                    for rr in right_runs:
                        span = rr[1] - lr[0]
                        if not (min_dim <= span <= max_dim):
                            continue
                        ld = crop_center_x - (lr[0] + lr[1]) // 2
                        rd = (rr[0] + rr[1]) // 2 - crop_center_x
                        score = abs(ld - rd)  # 0 = perfectly symmetric
                        if score < best_score:
                            best_score = score
                            left_col, right_col = lr[0], rr[1]

            if left_col is None:
                # No valid symmetric pair — use single run closest to center
                valid = [r for r in nearby_runs if min_dim <= r[1] - r[0] <= max_dim]
                best_run = min(valid or nearby_runs,
                               key=lambda r: abs((r[0] + r[1]) // 2 - crop_center_x))
                left_col, right_col = best_run

            rim_width = right_col - left_col
            print(f"   🎨 Runs: {len(runs)} total, {len(nearby_runs)} nearby, "
                  f"span {left_col}-{right_col} (width={rim_width}px)")

            if min_dim <= rim_width <= max_dim:
                # Rim center in crop coords
                rcx = (left_col + right_col) // 2
                rcy = crop_cy

                # Full-frame coords
                fx = left_col + x1
                fy = band_top + y1
                fcx = rcx + x1
                fcy = rcy + y1
                fh = band_bot - band_top

                # Orange density in the band region
                band_region = mask[band_top:band_bot, left_col:right_col+1]
                orange_density = np.count_nonzero(band_region) / max(band_region.size, 1)

                return [RimDetection(
                    x=fx,
                    y=fy,
                    width=rim_width,
                    height=fh,
                    confidence=orange_density,
                    method='color_contour',
                    center=(fcx, fcy)
                )]

        # --- Fallback: Hough circles on the crop ---
        # Color detection failed (non-orange rim, bad lighting, etc.)
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (9, 9), 2)

        min_r = max(8, int(w * min_radius_frac))
        max_r = int(w * max_radius_frac)

        # Tuned params for small crops: lower param2 for sensitivity,
        # lower minDist since crop is small
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=max(min_r, 30),
            param1=50,
            param2=25,  # slightly more sensitive than full-frame (30)
            minRadius=min_r,
            maxRadius=max_r,
        )

        if circles is None:
            return []

        circles = np.around(circles[0]).astype(int)
        # Pick the circle closest to the center of the crop AND closest to
        # expected rim size. Without size weighting, large circles (backboard,
        # net area) beat correctly-sized rim circles just because their center
        # is slightly nearer to the user mark.
        crop_cx = cx - x1
        crop_cy = cy - y1
        expected_r = max(min_r, int(w * 0.025))  # ~2.5% of frame width as baseline
        circles_sorted = sorted(circles, key=lambda c: (
            (int(c[0]) - crop_cx) ** 2 + (int(c[1]) - crop_cy) ** 2
            + (int(c[2]) - expected_r) ** 2 * 4  # penalize circles far from expected rim size
        ))

        detections = []
        for circle in circles_sorted[:3]:  # consider top 3 closest
            lx, ly, r = int(circle[0]), int(circle[1]), int(circle[2])
            fx, fy = lx + x1, ly + y1

            detections.append(RimDetection(
                x=max(0, fx - r),
                y=max(0, fy - r),
                width=2 * r,
                height=2 * r,
                confidence=0.5,  # lower confidence since no color confirmation
                method='hough_fallback',
                center=(fx, fy)
            ))

        return detections

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
            circles = np.around(circles[0]).astype(int)
            for circle in circles:
                x, y, r = int(circle[0]), int(circle[1]), int(circle[2])
                # Convert to bounding box (clamp to avoid negatives)
                detections.append(RimDetection(
                    x=max(0, x - r),
                    y=max(0, y - r),
                    width=2 * r,
                    height=2 * r,
                    confidence=0.7,  # Hough doesn't give confidence, use default
                    method='hough',
                    center=(x, y)
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
