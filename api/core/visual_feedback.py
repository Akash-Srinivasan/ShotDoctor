#!/usr/bin/env python3
"""
FormCheck - Visual Feedback System

Generates annotated images and overlays for visual coaching feedback:
- Joint angle annotations
- Trajectory overlays
- Problem area highlighting
- Side-by-side comparisons
- "Pro tips" style cards with illustrations
"""

import cv2
import numpy as np
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
from pathlib import Path
import math


# =============================================================================
# Color Schemes
# =============================================================================

class Colors:
    """Color palette for visual feedback."""
    # Status colors
    GOOD = (0, 200, 100)       # Green
    WARNING = (0, 180, 255)    # Orange
    BAD = (0, 80, 255)         # Red
    NEUTRAL = (200, 200, 200)  # Gray
    
    # UI colors
    PRIMARY = (255, 165, 0)    # Orange (brand color)
    SECONDARY = (100, 100, 100)
    TEXT_DARK = (40, 40, 40)
    TEXT_LIGHT = (255, 255, 255)
    BACKGROUND = (30, 30, 30)
    CARD_BG = (245, 245, 245)
    
    # Body part colors
    SHOOTING_ARM = (0, 165, 255)   # Orange
    GUIDE_ARM = (255, 200, 100)    # Light blue
    LEGS = (100, 255, 100)         # Green
    TORSO = (200, 200, 200)        # Gray


@dataclass
class AnnotationConfig:
    """Configuration for visual annotations."""
    # Thresholds for good/warning/bad
    elbow_load_ideal: Tuple[float, float] = (85, 95)
    elbow_release_ideal: Tuple[float, float] = (160, 175)
    wrist_height_ideal: Tuple[float, float] = (1.1, 1.3)
    knee_bend_ideal: Tuple[float, float] = (20, 35)
    
    # Visual settings
    line_thickness: int = 2
    font_scale: float = 0.6
    angle_arc_radius: int = 40
    show_ideal_ghost: bool = True


# =============================================================================
# Angle Drawing Utilities
# =============================================================================

def draw_angle_arc(frame: np.ndarray, center: Tuple[int, int], 
                   p1: Tuple[int, int], p2: Tuple[int, int],
                   angle: float, color: Tuple[int, int, int],
                   radius: int = 40, thickness: int = 2,
                   show_value: bool = True) -> np.ndarray:
    """
    Draw an angle arc at a joint with the angle value.
    """
    # Calculate angles for the arc
    angle1 = math.atan2(p1[1] - center[1], p1[0] - center[0])
    angle2 = math.atan2(p2[1] - center[1], p2[0] - center[0])
    
    start_angle = math.degrees(angle1)
    end_angle = math.degrees(angle2)
    
    # Draw arc
    cv2.ellipse(frame, center, (radius, radius), 0, 
                start_angle, end_angle, color, thickness)
    
    # Draw angle value
    if show_value:
        mid_angle = (angle1 + angle2) / 2
        text_x = int(center[0] + (radius + 20) * math.cos(mid_angle))
        text_y = int(center[1] + (radius + 20) * math.sin(mid_angle))
        
        # Background for text
        text = f"{angle:.0f}°"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(frame, (text_x - 5, text_y - th - 5), 
                     (text_x + tw + 5, text_y + 5), color, -1)
        cv2.putText(frame, text, (text_x, text_y), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, Colors.TEXT_LIGHT, 2)
    
    return frame


def get_status_color(value: float, ideal_range: Tuple[float, float]) -> Tuple[int, int, int]:
    """Get color based on how close value is to ideal range."""
    min_ideal, max_ideal = ideal_range
    
    if min_ideal <= value <= max_ideal:
        return Colors.GOOD
    elif min_ideal - 10 <= value <= max_ideal + 10:
        return Colors.WARNING
    else:
        return Colors.BAD


# =============================================================================
# Frame Annotation
# =============================================================================

class FrameAnnotator:
    """Annotates video frames with form analysis."""
    
    def __init__(self, config: AnnotationConfig = None):
        self.config = config or AnnotationConfig()
    
    def annotate_shot_frame(self, frame: np.ndarray, landmarks: Dict,
                           metrics: Dict, phase: str = "release") -> np.ndarray:
        """
        Annotate a single frame with form analysis.
        
        Args:
            frame: Video frame
            landmarks: Pose landmarks (normalized 0-1)
            metrics: Shot metrics dict with elbow_load, elbow_release, etc.
            phase: "load", "release", or "follow_through"
        """
        annotated = frame.copy()
        h, w = frame.shape[:2]
        
        # Convert landmarks to pixel coordinates
        px_landmarks = {}
        for name, pos in landmarks.items():
            px_landmarks[name] = (int(pos[0] * w), int(pos[1] * h))
        
        # Draw skeleton with color coding
        self._draw_annotated_skeleton(annotated, px_landmarks, metrics, phase)
        
        # Draw angle annotations
        self._draw_angle_annotations(annotated, px_landmarks, metrics, phase)
        
        # Draw metrics panel
        self._draw_metrics_panel(annotated, metrics, phase)
        
        return annotated
    
    def _draw_annotated_skeleton(self, frame: np.ndarray, landmarks: Dict,
                                  metrics: Dict, phase: str):
        """Draw skeleton with color-coded body parts."""
        
        # Define connections with colors
        connections = [
            # Shooting arm (orange)
            (("right_shoulder", "right_elbow"), Colors.SHOOTING_ARM),
            (("right_elbow", "right_wrist"), Colors.SHOOTING_ARM),
            # Guide arm
            (("left_shoulder", "left_elbow"), Colors.GUIDE_ARM),
            (("left_elbow", "left_wrist"), Colors.GUIDE_ARM),
            # Torso
            (("left_shoulder", "right_shoulder"), Colors.TORSO),
            (("left_shoulder", "left_hip"), Colors.TORSO),
            (("right_shoulder", "right_hip"), Colors.TORSO),
            (("left_hip", "right_hip"), Colors.TORSO),
            # Legs
            (("left_hip", "left_knee"), Colors.LEGS),
            (("left_knee", "left_ankle"), Colors.LEGS),
            (("right_hip", "right_knee"), Colors.LEGS),
            (("right_knee", "right_ankle"), Colors.LEGS),
        ]
        
        for (start, end), color in connections:
            if start in landmarks and end in landmarks:
                cv2.line(frame, landmarks[start], landmarks[end], color, 3)
        
        # Draw joints
        for name, pos in landmarks.items():
            # Highlight shooting arm joints
            if "right_" in name and any(j in name for j in ["shoulder", "elbow", "wrist"]):
                cv2.circle(frame, pos, 8, Colors.SHOOTING_ARM, -1)
                cv2.circle(frame, pos, 8, Colors.TEXT_LIGHT, 2)
            else:
                cv2.circle(frame, pos, 5, Colors.TEXT_LIGHT, -1)
    
    def _draw_angle_annotations(self, frame: np.ndarray, landmarks: Dict,
                                 metrics: Dict, phase: str):
        """Draw angle arcs and values at joints."""
        
        # Elbow angle
        if all(k in landmarks for k in ["right_shoulder", "right_elbow", "right_wrist"]):
            if phase == "load":
                angle = metrics.get("elbow_load", 0)
                color = get_status_color(angle, self.config.elbow_load_ideal)
            else:
                angle = metrics.get("elbow_release", 0)
                color = get_status_color(angle, self.config.elbow_release_ideal)
            
            if angle > 0:
                draw_angle_arc(
                    frame,
                    landmarks["right_elbow"],
                    landmarks["right_shoulder"],
                    landmarks["right_wrist"],
                    angle, color,
                    radius=self.config.angle_arc_radius
                )
        
        # Knee angle (for load phase)
        if phase == "load" and all(k in landmarks for k in ["right_hip", "right_knee", "right_ankle"]):
            knee_angle = metrics.get("knee_bend", 0)
            if knee_angle > 0:
                color = get_status_color(knee_angle, self.config.knee_bend_ideal)
                draw_angle_arc(
                    frame,
                    landmarks["right_knee"],
                    landmarks["right_hip"],
                    landmarks["right_ankle"],
                    knee_angle, color,
                    radius=30
                )
    
    def _draw_metrics_panel(self, frame: np.ndarray, metrics: Dict, phase: str):
        """Draw a metrics panel on the frame."""
        h, w = frame.shape[:2]
        
        # Panel background
        panel_w, panel_h = 200, 120
        panel_x, panel_y = 10, 10
        
        overlay = frame.copy()
        cv2.rectangle(overlay, (panel_x, panel_y), 
                     (panel_x + panel_w, panel_y + panel_h),
                     (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        # Title
        cv2.putText(frame, phase.upper(), (panel_x + 10, panel_y + 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, Colors.PRIMARY, 2)
        
        # Metrics
        y = panel_y + 50
        metrics_to_show = [
            ("Elbow", metrics.get("elbow_load" if phase == "load" else "elbow_release", 0), "°"),
            ("Release Ht", metrics.get("wrist_height", 0), ""),
        ]
        
        if phase == "load":
            metrics_to_show.append(("Knee Bend", metrics.get("knee_bend", 0), "°"))
        
        for label, value, unit in metrics_to_show:
            if value:
                text = f"{label}: {value:.0f}{unit}" if unit == "°" else f"{label}: {value:.2f}"
                cv2.putText(frame, text, (panel_x + 10, y),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, Colors.TEXT_LIGHT, 1)
                y += 22


# =============================================================================
# Comparison Views
# =============================================================================

class ComparisonGenerator:
    """Generates side-by-side and overlay comparisons."""
    
    def __init__(self):
        self.annotator = FrameAnnotator()
    
    def create_side_by_side(self, user_frame: np.ndarray, user_landmarks: Dict,
                            user_metrics: Dict,
                            reference_frame: np.ndarray = None,
                            reference_landmarks: Dict = None,
                            reference_metrics: Dict = None,
                            reference_label: str = "IDEAL") -> np.ndarray:
        """
        Create side-by-side comparison of user shot vs reference.
        If no reference provided, creates annotated user frame with ideal overlay.
        """
        h, w = user_frame.shape[:2]
        
        # Annotate user frame
        user_annotated = self.annotator.annotate_shot_frame(
            user_frame, user_landmarks, user_metrics, "release"
        )
        
        if reference_frame is not None:
            # Resize reference to match
            ref_h, ref_w = reference_frame.shape[:2]
            scale = h / ref_h
            reference_resized = cv2.resize(reference_frame, (int(ref_w * scale), h))
            
            # Annotate reference
            ref_annotated = self.annotator.annotate_shot_frame(
                reference_resized, reference_landmarks, reference_metrics, "release"
            )
            
            # Create side-by-side
            combined = np.hstack([user_annotated, ref_annotated])
            
            # Add labels
            cv2.putText(combined, "YOUR SHOT", (20, h - 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, Colors.PRIMARY, 2)
            cv2.putText(combined, reference_label, (w + 20, h - 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, Colors.GOOD, 2)
        else:
            combined = user_annotated
        
        return combined
    
    def create_improvement_highlight(self, frame: np.ndarray, landmarks: Dict,
                                      metrics: Dict, issues: List[Dict]) -> np.ndarray:
        """
        Highlight specific areas that need improvement.
        
        issues: List of dicts with 'body_part', 'message', 'severity'
        """
        annotated = frame.copy()
        h, w = frame.shape[:2]
        
        # Convert landmarks
        px_landmarks = {}
        for name, pos in landmarks.items():
            px_landmarks[name] = (int(pos[0] * w), int(pos[1] * h))
        
        # Draw skeleton first
        self.annotator._draw_annotated_skeleton(annotated, px_landmarks, metrics, "release")
        
        # Highlight problem areas
        for issue in issues:
            body_part = issue.get("body_part", "")
            severity = issue.get("severity", "warning")  # "warning" or "error"
            message = issue.get("message", "")
            
            color = Colors.BAD if severity == "error" else Colors.WARNING
            
            # Find the landmark for this body part
            landmark_key = None
            if "elbow" in body_part.lower():
                landmark_key = "right_elbow"
            elif "wrist" in body_part.lower() or "release" in body_part.lower():
                landmark_key = "right_wrist"
            elif "knee" in body_part.lower():
                landmark_key = "right_knee"
            elif "shoulder" in body_part.lower():
                landmark_key = "right_shoulder"
            
            if landmark_key and landmark_key in px_landmarks:
                pos = px_landmarks[landmark_key]
                
                # Draw attention circle
                cv2.circle(annotated, pos, 35, color, 3)
                cv2.circle(annotated, pos, 40, color, 2)
                
                # Draw callout line and text
                text_x = pos[0] + 60
                text_y = pos[1] - 30
                
                cv2.line(annotated, pos, (text_x - 10, text_y + 10), color, 2)
                
                # Text background
                (tw, th), _ = cv2.getTextSize(message, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(annotated, (text_x - 5, text_y - th - 5),
                             (text_x + tw + 5, text_y + 5), color, -1)
                cv2.putText(annotated, message, (text_x, text_y),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, Colors.TEXT_LIGHT, 1)
        
        return annotated


# =============================================================================
# Pro Tips Card Generator
# =============================================================================

class ProTipCard:
    """Generates "Pro Tips" style coaching cards."""
    
    @staticmethod
    def create_tip_card(title: str, tip_text: str, 
                        illustration_type: str = "elbow",
                        width: int = 400, height: int = 500) -> np.ndarray:
        """
        Create a coaching tip card with illustration.
        
        illustration_type: "elbow", "knee", "release", "follow_through"
        """
        # Create card background
        card = np.ones((height, width, 3), dtype=np.uint8) * 255
        
        # Yellow header
        header_height = 60
        cv2.rectangle(card, (0, 0), (width, header_height), Colors.PRIMARY, -1)
        
        # Header text
        cv2.putText(card, "Pro Tips", (15, 40),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, Colors.TEXT_DARK, 2)
        
        # Illustration area (placeholder - would use actual images)
        illust_y = header_height + 20
        illust_h = 200
        cv2.rectangle(card, (20, illust_y), (width - 20, illust_y + illust_h),
                     (240, 240, 240), -1)
        
        # Draw simple illustration based on type
        ProTipCard._draw_illustration(card, illustration_type, 
                                       (20, illust_y, width - 40, illust_h))
        
        # Title
        title_y = illust_y + illust_h + 40
        cv2.putText(card, title, (20, title_y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, Colors.TEXT_DARK, 2)
        
        # Tip text (wrap)
        text_y = title_y + 30
        words = tip_text.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + " " + word if current_line else word
            (tw, _), _ = cv2.getTextSize(test_line, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            if tw < width - 40:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        
        for line in lines[:6]:  # Max 6 lines
            cv2.putText(card, line.strip(), (20, text_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, Colors.SECONDARY, 1)
            text_y += 22
        
        return card
    
    @staticmethod
    def _draw_illustration(card: np.ndarray, illust_type: str, 
                           bounds: Tuple[int, int, int, int]):
        """Draw a simple illustration of the body part."""
        x, y, w, h = bounds
        cx, cy = x + w // 2, y + h // 2
        
        if illust_type == "elbow":
            # Draw arm showing elbow angle
            shoulder = (cx - 60, cy - 40)
            elbow = (cx, cy + 20)
            wrist = (cx + 50, cy - 50)
            
            cv2.line(card, shoulder, elbow, Colors.TEXT_DARK, 8)
            cv2.line(card, elbow, wrist, Colors.TEXT_DARK, 8)
            cv2.circle(card, elbow, 12, Colors.PRIMARY, -1)
            
            # Angle arc
            cv2.ellipse(card, elbow, (30, 30), 0, -120, -20, Colors.PRIMARY, 3)
            
        elif illust_type == "knee":
            # Draw leg showing knee bend
            hip = (cx, cy - 60)
            knee = (cx - 20, cy + 20)
            ankle = (cx - 10, cy + 80)
            
            cv2.line(card, hip, knee, Colors.TEXT_DARK, 8)
            cv2.line(card, knee, ankle, Colors.TEXT_DARK, 8)
            cv2.circle(card, knee, 12, Colors.PRIMARY, -1)
            
        elif illust_type == "release":
            # Draw release point
            body_base = (cx, cy + 60)
            shoulder = (cx, cy)
            hand = (cx + 30, cy - 70)
            ball = (cx + 40, cy - 90)
            
            cv2.line(card, body_base, shoulder, Colors.TEXT_DARK, 8)
            cv2.line(card, shoulder, hand, Colors.TEXT_DARK, 8)
            cv2.circle(card, ball, 20, Colors.PRIMARY, -1)
            
            # Arrow showing upward release
            cv2.arrowedLine(card, (cx + 60, cy - 40), (cx + 60, cy - 100),
                           Colors.GOOD, 3, tipLength=0.3)
            
        elif illust_type == "follow_through":
            # Draw gooseneck follow through
            shoulder = (cx - 30, cy + 20)
            elbow = (cx + 20, cy - 30)
            wrist = (cx + 50, cy - 60)
            fingers = (cx + 60, cy - 30)
            
            cv2.line(card, shoulder, elbow, Colors.TEXT_DARK, 8)
            cv2.line(card, elbow, wrist, Colors.TEXT_DARK, 8)
            cv2.line(card, wrist, fingers, Colors.TEXT_DARK, 6)
            
            # "Gooseneck" curve
            cv2.ellipse(card, wrist, (15, 15), 0, 0, 120, Colors.PRIMARY, 3)


# =============================================================================
# Shot Breakdown View
# =============================================================================

class ShotBreakdown:
    """Creates multi-frame breakdown of a shot."""
    
    def __init__(self):
        self.annotator = FrameAnnotator()
    
    def create_breakdown(self, frames: List[Tuple[str, np.ndarray]],
                         landmarks_list: List[Dict],
                         metrics: Dict,
                         issues: List[Dict] = None) -> np.ndarray:
        """
        Create a breakdown showing key frames of the shot.
        
        frames: List of (label, frame) tuples
        landmarks_list: Landmarks for each frame
        metrics: Overall shot metrics
        issues: List of issues to highlight
        """
        # Select key frames: Load, Release, Follow-through
        key_indices = [1, 5, 6]  # Based on 7-frame capture
        key_frames = []
        
        for i, idx in enumerate(key_indices):
            if idx < len(frames):
                label, frame = frames[idx]
                lm = landmarks_list[idx] if idx < len(landmarks_list) else {}
                
                # Determine phase
                if i == 0:
                    phase = "load"
                elif i == 1:
                    phase = "release"
                else:
                    phase = "follow_through"
                
                # Annotate
                annotated = self.annotator.annotate_shot_frame(frame, lm, metrics, phase)
                
                # Resize for layout
                h, w = annotated.shape[:2]
                target_h = 300
                scale = target_h / h
                resized = cv2.resize(annotated, (int(w * scale), target_h))
                
                # Add phase label
                cv2.putText(resized, phase.replace("_", " ").upper(), (10, 25),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, Colors.PRIMARY, 2)
                
                key_frames.append(resized)
        
        # Combine horizontally
        if key_frames:
            # Pad to same width
            max_w = max(f.shape[1] for f in key_frames)
            padded = []
            for f in key_frames:
                if f.shape[1] < max_w:
                    pad = np.zeros((f.shape[0], max_w - f.shape[1], 3), dtype=np.uint8)
                    f = np.hstack([f, pad])
                padded.append(f)
            
            breakdown = np.hstack(padded)
            
            # Add issues panel below if provided
            if issues:
                issues_panel = self._create_issues_panel(breakdown.shape[1], issues)
                breakdown = np.vstack([breakdown, issues_panel])
            
            return breakdown
        
        return np.zeros((300, 800, 3), dtype=np.uint8)
    
    def _create_issues_panel(self, width: int, issues: List[Dict]) -> np.ndarray:
        """Create panel showing issues to work on."""
        height = 80 + 25 * min(len(issues), 3)
        panel = np.ones((height, width, 3), dtype=np.uint8) * 30
        
        # Header
        cv2.putText(panel, "AREAS TO IMPROVE", (20, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, Colors.WARNING, 2)
        
        # Issues
        y = 60
        for issue in issues[:3]:
            severity = issue.get("severity", "warning")
            color = Colors.BAD if severity == "error" else Colors.WARNING
            
            cv2.circle(panel, (30, y - 5), 5, color, -1)
            cv2.putText(panel, issue.get("message", ""), (45, y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, Colors.TEXT_LIGHT, 1)
            y += 25
        
        return panel


# =============================================================================
# Feedback Overlay for Live Video
# =============================================================================

class LiveFeedbackOverlay:
    """Real-time feedback overlay for live video."""
    
    def __init__(self):
        self.current_feedback = None
        self.feedback_start_time = 0
        self.feedback_duration = 5.0  # seconds
    
    def set_feedback(self, feedback: Dict, timestamp: float):
        """Set current feedback to display."""
        self.current_feedback = feedback
        self.feedback_start_time = timestamp
    
    def draw(self, frame: np.ndarray, current_time: float) -> np.ndarray:
        """Draw feedback overlay on frame."""
        if self.current_feedback is None:
            return frame
        
        elapsed = current_time - self.feedback_start_time
        if elapsed > self.feedback_duration:
            self.current_feedback = None
            return frame
        
        h, w = frame.shape[:2]
        
        # Fade out effect
        alpha = 1.0 if elapsed < self.feedback_duration - 1 else (self.feedback_duration - elapsed)
        
        # Draw feedback card at bottom
        card_h = 120
        card_y = h - card_h - 20
        
        overlay = frame.copy()
        
        # Card background
        cv2.rectangle(overlay, (20, card_y), (w - 20, card_y + card_h),
                     Colors.BACKGROUND, -1)
        
        # Result indicator
        made = self.current_feedback.get("made")
        if made is True:
            cv2.rectangle(overlay, (20, card_y), (30, card_y + card_h),
                         Colors.GOOD, -1)
            result_text = "MADE"
            result_color = Colors.GOOD
        elif made is False:
            cv2.rectangle(overlay, (20, card_y), (30, card_y + card_h),
                         Colors.BAD, -1)
            miss_type = self.current_feedback.get("miss_type", "")
            result_text = f"MISSED ({miss_type})" if miss_type else "MISSED"
            result_color = Colors.BAD
        else:
            result_text = ""
            result_color = Colors.NEUTRAL
        
        # Blend
        cv2.addWeighted(overlay, alpha * 0.9, frame, 1 - alpha * 0.9, 0, frame)
        
        # Text
        if result_text:
            cv2.putText(frame, result_text, (45, card_y + 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, result_color, 2)
        
        # Form rating
        rating = self.current_feedback.get("form_rating")
        if rating:
            cv2.putText(frame, f"Form: {rating}/10", (45, card_y + 55),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, Colors.TEXT_LIGHT, 1)
        
        # Main feedback
        feedback_text = self.current_feedback.get("feedback", "")
        if feedback_text:
            # Wrap text
            max_chars = 60
            lines = [feedback_text[i:i+max_chars] for i in range(0, len(feedback_text), max_chars)]
            y = card_y + 80
            for line in lines[:2]:
                cv2.putText(frame, line, (45, y),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, Colors.TEXT_LIGHT, 1)
                y += 20
        
        # Quick cue
        quick_cue = self.current_feedback.get("quick_cue")
        if quick_cue:
            cue_text = f'"{quick_cue}"'
            (tw, th), _ = cv2.getTextSize(cue_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.putText(frame, cue_text, (w - tw - 40, card_y + 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, Colors.PRIMARY, 2)
        
        return frame


# =============================================================================
# Export Functions
# =============================================================================

def save_annotated_shot(output_path: str, frame: np.ndarray, landmarks: Dict,
                        metrics: Dict, feedback: Dict = None):
    """Save an annotated shot image."""
    annotator = FrameAnnotator()
    annotated = annotator.annotate_shot_frame(frame, landmarks, metrics, "release")
    
    if feedback:
        # Add feedback text at bottom
        h, w = annotated.shape[:2]
        cv2.rectangle(annotated, (0, h - 60), (w, h), (0, 0, 0), -1)
        cv2.putText(annotated, feedback.get("feedback", ""), (10, h - 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, Colors.TEXT_LIGHT, 1)
    
    cv2.imwrite(output_path, annotated)
    return output_path


def generate_session_report(output_dir: str, shots: List[Dict]) -> str:
    """Generate a visual report of a shooting session."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Create summary image
    summary_h, summary_w = 800, 1200
    summary = np.ones((summary_h, summary_w, 3), dtype=np.uint8) * 255
    
    # Header
    cv2.rectangle(summary, (0, 0), (summary_w, 80), Colors.PRIMARY, -1)
    cv2.putText(summary, "SESSION REPORT", (20, 55),
               cv2.FONT_HERSHEY_SIMPLEX, 1.5, Colors.TEXT_DARK, 3)
    
    # Stats
    total = len(shots)
    made = sum(1 for s in shots if s.get("made"))
    pct = made / total * 100 if total else 0
    
    cv2.putText(summary, f"Shots: {total}  |  Made: {made}  |  {pct:.0f}%",
               (20, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.8, Colors.TEXT_DARK, 2)
    
    # TODO: Add shot thumbnails, charts, etc.
    
    report_path = output_path / "session_report.jpg"
    cv2.imwrite(str(report_path), summary)
    
    return str(report_path)


# =============================================================================
# CLI Testing
# =============================================================================

if __name__ == "__main__":
    print("Visual Feedback System")
    print("=" * 40)
    
    # Test tip card generation
    card = ProTipCard.create_tip_card(
        title="Elbow Position",
        tip_text="Focus on keeping your elbow tucked under the ball at the set point. "
                 "Imagine your elbow, wrist, and the ball forming a straight line to the basket.",
        illustration_type="elbow"
    )
    
    cv2.imwrite("/tmp/test_tip_card.jpg", card)
    print("Created test tip card: /tmp/test_tip_card.jpg")
    
    # Test with dummy data
    dummy_frame = np.ones((480, 640, 3), dtype=np.uint8) * 100
    dummy_landmarks = {
        "right_shoulder": (0.4, 0.3),
        "right_elbow": (0.45, 0.45),
        "right_wrist": (0.55, 0.25),
        "left_shoulder": (0.3, 0.3),
        "left_elbow": (0.25, 0.45),
        "left_wrist": (0.2, 0.5),
        "right_hip": (0.4, 0.6),
        "left_hip": (0.3, 0.6),
        "right_knee": (0.4, 0.75),
        "right_ankle": (0.4, 0.9),
        "left_knee": (0.3, 0.75),
        "left_ankle": (0.3, 0.9),
    }
    dummy_metrics = {
        "elbow_load": 88,
        "elbow_release": 165,
        "wrist_height": 1.2,
        "knee_bend": 28,
    }
    
    annotator = FrameAnnotator()
    annotated = annotator.annotate_shot_frame(dummy_frame, dummy_landmarks, dummy_metrics, "release")
    cv2.imwrite("/tmp/test_annotated.jpg", annotated)
    print("Created test annotated frame: /tmp/test_annotated.jpg")
    
    # Test improvement highlight
    issues = [
        {"body_part": "elbow", "message": "Elbow 5° too low", "severity": "warning"},
        {"body_part": "release", "message": "Release point dropped", "severity": "error"},
    ]
    
    comp = ComparisonGenerator()
    highlighted = comp.create_improvement_highlight(dummy_frame, dummy_landmarks, dummy_metrics, issues)
    cv2.imwrite("/tmp/test_highlighted.jpg", highlighted)
    print("Created test highlighted frame: /tmp/test_highlighted.jpg")
    
    print("\nDone!")