#!/usr/bin/env python3
"""
FormCheck API - Multi-shot video analysis
Processes ALL shots in a video and returns session summary
"""

import os
import sys
import time
from pathlib import Path
from typing import Optional, List
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import tempfile
import json
import base64

# Load environment variables
load_dotenv()

# Add core directory to path
core_dir = Path(__file__).parent / "core"
sys.path.insert(0, str(core_dir))

# Import existing modules
try:
    from live_analysis import (
        PoseDetector,
        LiveShotDetector,
        GeminiClient,
        PlayerProfile,
        ShotEvent,
        LiveState
    )
    from database import FormCheckDB
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Warning: Could not import core modules: {e}")
    MODULES_AVAILABLE = False

# Ball tracking for programmatic make/miss detection
try:
    from test_tracking import CustomBallTracker, RealTimeReleaseDetector
    BALL_TRACKING_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Warning: Could not import ball tracking: {e}")
    BALL_TRACKING_AVAILABLE = False

# Initialize FastAPI
app = FastAPI(
    title="FormCheck API",
    description="Multi-shot basketball analysis API",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
db = FormCheckDB() if MODULES_AVAILABLE else None

# Official Supabase client (proxy bug fixed in v2.28.0+)
from supabase import create_client, Client

_supabase_client: Optional[Client] = None
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        print("✓ Supabase client initialized (official supabase-py)")
    except Exception as e:
        print(f"⚠️  Supabase client initialization failed: {e}")
        _supabase_client = None
else:
    print("⚠️  Supabase credentials not set — fingerprint and server-side persistence disabled")

# In-memory progress tracking for active analyses
# Key: session_id, Value: {stage, progress, message, frame, total_frames, shots_found}
_analysis_progress: dict = {}

# Pre-load ball tracker once at startup (YOLO model load + MPS warmup is slow)
_shared_ball_tracker = None
if BALL_TRACKING_AVAILABLE:
    try:
        import numpy as np
        _shared_ball_tracker = CustomBallTracker()
        # Warm up MPS/CUDA with a dummy inference so the first request isn't slow
        dummy = np.zeros((480, 640, 3), dtype=np.uint8)
        _shared_ball_tracker.model(dummy, verbose=False, device=_shared_ball_tracker.device,
                                   imgsz=_shared_ball_tracker.inference_size)
        print("✓ Ball tracker pre-loaded and GPU warmed up")
    except Exception as e:
        print(f"⚠️  Ball tracker pre-load failed: {e}")
        _shared_ball_tracker = None

# Models
class ShotFrame(BaseModel):
    """Individual frame from shot analysis"""
    label: str
    image_base64: str
    frame_number: int

class ShotAnalysis(BaseModel):
    """Analysis for a single shot"""
    shot_number: int
    made: Optional[bool]
    miss_type: Optional[str]
    form_rating: Optional[int]
    feedback: str
    key_issue: Optional[str]
    quick_cue: Optional[str]
    elbow_angle_load: float
    elbow_angle_release: float
    wrist_height_release: float
    knee_bend_load: float
    hip_angle_load: float = 0.0
    elbow_height_load: float = 0.0
    heel_height_release: float = 0.0
    trunk_lean_release: float = 0.0
    stance_width: float = 0.0
    shoulder_level_diff: float = 0.0
    elbow_lateral_offset: float = 0.0
    hitch_count: int = 0
    hitch_severity: float = 0.0
    motion_smoothness: float = 1.0
    pocket_lateral_sweep: float = 0.0
    dip_depth: float = 0.0
    camera_angle: Optional[str] = None  # "side", "front", "angled"
    thumbnail: str  # Base64 encoded thumbnail (release frame)
    timestamp: float  # seconds into video when shot detected

class SessionSummary(BaseModel):
    """Summary of entire shooting session"""
    total_shots: int
    shots_made: int
    shots_missed: int
    shooting_percentage: float
    average_form_rating: float
    session_feedback: str
    drill_suggestions: List[str]
    shots: List[ShotAnalysis]
    server_persisted: bool = False  # True if server wrote to DB (client can skip)

class HealthResponse(BaseModel):
    status: str
    modules_available: bool
    gemini_configured: bool
    database_available: bool

class ProgressResponse(BaseModel):
    stage: str  # uploading, detecting, analyzing_shot, generating_summary, complete
    progress: int  # 0-100
    message: str
    frame: Optional[int] = None
    total_frames: Optional[int] = None
    shots_found: Optional[int] = None
    current_shot: Optional[int] = None

# ============================================================================
# Shot Fingerprint System
# ============================================================================

# Cue templates: metric → coaching language
CUE_TEMPLATES = {
    "elbow_angle_release": {"low": "Extend your elbow fully on release", "high": "Don't overextend — snap the wrist instead"},
    "trunk_lean_release": {"low": "Stay tall through your release", "high": "Lean into your shot slightly"},
    "knee_bend_load": {"low": "Bend your knees more at the set point", "high": "Don't over-bend — stay athletic"},
    "hip_angle_load": {"low": "Sit into your shot more", "high": "Stay more upright at the set point"},
    "heel_height_release": {"low": "Get up on your toes at release", "high": "Stay grounded — don't jump too much"},
    "wrist_height_release": {"low": "Get the ball higher at release", "high": "Release point is good — focus elsewhere"},
    "elbow_angle_load": {"low": "Bring the ball up higher to your set point", "high": "Keep a tighter set point"},
    "elbow_height_load": {"low": "Raise your elbow higher at the set point", "high": "Elbow height is good"},
    "stance_width": {"low": "Widen your stance slightly", "high": "Narrow your stance to shoulder width"},
    "elbow_lateral_offset": {"low": "Tuck your elbow in", "high": "Elbow alignment is solid"},
    "shoulder_level_diff": {"low": "Keep your shoulders level", "high": "Keep your shoulders level"},
}

# Metric labels for display
METRIC_LABELS = {
    "elbow_angle_load": "Elbow Set Point",
    "elbow_angle_release": "Elbow Extension",
    "wrist_height_release": "Release Height",
    "knee_bend_load": "Knee Bend",
    "hip_angle_load": "Hip Angle",
    "elbow_height_load": "Elbow Height",
    "heel_height_release": "Heel Rise",
    "trunk_lean_release": "Trunk Lean",
    "stance_width": "Stance Width",
    "shoulder_level_diff": "Shoulder Level",
    "elbow_lateral_offset": "Elbow Alignment",
}

# Optimal values for impact scoring
OPTIMAL_VALUES = {
    "elbow_angle_load": (50, 70),
    "elbow_angle_release": (130, 165),
    "wrist_height_release": (0.9, 1.3),
    "knee_bend_load": (95, 115),
    "hip_angle_load": (120, 145),
    "elbow_height_load": (0.8, 1.1),
    "heel_height_release": (0.05, 0.15),
    "trunk_lean_release": (-3, 3),
    "stance_width": (0.9, 1.2),
    "shoulder_level_diff": (0.0, 0.1),
    "elbow_lateral_offset": (0.0, 0.15),
}

ALL_METRICS = list(METRIC_LABELS.keys())

class ShotFingerprint(BaseModel):
    session_count: int
    total_shots: int
    fingerprint_ready: bool
    make_signature: dict = {}
    miss_signature: dict = {}
    improvement_areas: list = []
    consistency: dict = {}
    miss_distribution: dict = {}
    trend: dict = {}
    cues: List[str] = []
    miss_tendency_cue: str = ""
    trend_label: str = ""
    consistency_note: str = ""


def _persist_session_results(
    session_id: str,
    user_id: str,
    session_summary: SessionSummary,
    started_at: str
) -> bool:
    """
    Persist session results to Supabase (server-side).

    Returns True if successful, False otherwise.
    This runs in a try/except so DB failures don't crash the API response.
    """
    if not _supabase_client or not session_id or not user_id:
        return False

    try:
        persist_start = time.time()

        # 1. Update session with final stats
        session_update = {
            "ended_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "shot_count": session_summary.total_shots,
            "make_count": session_summary.shots_made,
            "miss_count": session_summary.shots_missed,
            "shooting_percentage": session_summary.shooting_percentage,
            "average_form_rating": session_summary.average_form_rating,
            "session_feedback": session_summary.session_feedback,
            "drill_suggestions": session_summary.drill_suggestions,
        }

        _supabase_client.table("sessions").update(session_update).eq("id", session_id).execute()
        print(f"✓ Server: Updated session {session_id}")

        # 2. Batch insert all shots
        shots_data = []
        for shot in session_summary.shots:
            shot_row = {
                "session_id": session_id,
                "user_id": user_id,
                "shot_number": shot.shot_number,
                "made": shot.made,
                "miss_type": shot.miss_type,
                "elbow_angle_load": shot.elbow_angle_load,
                "elbow_angle_release": shot.elbow_angle_release,
                "wrist_height_release": shot.wrist_height_release,
                "knee_bend_load": shot.knee_bend_load,
                "hip_angle_load": shot.hip_angle_load,
                "elbow_height_load": shot.elbow_height_load,
                "heel_height_release": shot.heel_height_release,
                "trunk_lean_release": shot.trunk_lean_release,
                "stance_width": shot.stance_width,
                "shoulder_level_diff": shot.shoulder_level_diff,
                "elbow_lateral_offset": shot.elbow_lateral_offset,
                "form_rating": shot.form_rating,
                "feedback": shot.feedback,
                "key_issue": shot.key_issue,
                "quick_cue": shot.quick_cue,
                "camera_angle": shot.camera_angle,
                "thumbnail_url": None,  # Client may upload thumbnails separately
            }
            shots_data.append(shot_row)

        if shots_data:
            _supabase_client.table("shots").insert(shots_data).execute()
            print(f"✓ Server: Inserted {len(shots_data)} shots")

        # 3. Update user profile stats
        # Get current profile
        profile_resp = _supabase_client.table("profiles").select("total_sessions, total_shots, total_makes").eq("id", user_id).single().execute()
        current_profile = profile_resp.data if profile_resp.data else {}

        profile_update = {
            "total_sessions": (current_profile.get("total_sessions", 0) or 0) + 1,
            "total_shots": (current_profile.get("total_shots", 0) or 0) + session_summary.total_shots,
            "total_makes": (current_profile.get("total_makes", 0) or 0) + session_summary.shots_made,
            "last_session_at": started_at,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        }
        _supabase_client.table("profiles").update(profile_update).eq("id", user_id).execute()
        print(f"✓ Server: Updated profile stats for user {user_id}")

        persist_duration = time.time() - persist_start
        print(f"✅ Server-side persistence complete ({persist_duration:.2f}s)")
        return True

    except Exception as e:
        print(f"❌ Server-side persistence failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def _compute_fingerprint(user_id: str) -> dict:
    """Compute shot fingerprint from Supabase data."""
    import statistics

    if not _supabase_client:
        return {"fingerprint_ready": False, "session_count": 0, "total_shots": 0}

    # Get session count
    sessions_resp = _supabase_client.table("sessions").select("id, shooting_percentage, average_form_rating, started_at").eq("user_id", user_id).order("started_at", desc=True).execute()
    sessions = sessions_resp.data or []
    session_count = len(sessions)

    # Get all shots
    shots_resp = _supabase_client.table("shots").select("*").eq("user_id", user_id).execute()
    all_shots = shots_resp.data or []
    total_shots = len(all_shots)

    if session_count < 3 or total_shots < 15:
        return {
            "fingerprint_ready": False,
            "session_count": session_count,
            "total_shots": total_shots,
        }

    # Split into makes and misses
    makes = [s for s in all_shots if s.get("made") is True]
    misses = [s for s in all_shots if s.get("made") is False]

    def calc_signature(shots_list):
        sig = {}
        for metric in ALL_METRICS:
            values = [s.get(metric, 0) or 0 for s in shots_list if s.get(metric) is not None]
            if len(values) >= 3:
                avg = statistics.mean(values)
                std = statistics.stdev(values) if len(values) > 1 else 0.0
                sig[metric] = {"avg": round(avg, 2), "std": round(std, 2)}
        return sig

    make_sig = calc_signature(makes) if len(makes) >= 3 else {}
    miss_sig = calc_signature(misses) if len(misses) >= 3 else {}

    # Compute improvement areas
    improvement_areas = []
    for metric in ALL_METRICS:
        if metric not in make_sig or metric not in miss_sig:
            continue
        make_avg = make_sig[metric]["avg"]
        miss_avg = miss_sig[metric]["avg"]
        delta = abs(make_avg - miss_avg)

        opt = OPTIMAL_VALUES.get(metric, (0, 1))
        opt_span = max(abs(opt[1] - opt[0]), 0.01)

        miss_freq = len(misses) / max(total_shots, 1)
        raw_impact = (delta / opt_span) * miss_freq

        # Determine cue direction
        direction = "low" if miss_avg < make_avg else "high"
        cue_template = CUE_TEMPLATES.get(metric, {})
        cue = cue_template.get(direction, "")

        # Generate insight
        label = METRIC_LABELS.get(metric, metric.replace("_", " "))
        if delta > 0.5:
            insight = f"Your {label.lower()} differs by {delta:.1f} between makes and misses"
        else:
            insight = f"Minor difference in {label.lower()}"

        improvement_areas.append({
            "metric": metric,
            "label": label,
            "make_avg": round(make_avg, 2),
            "miss_avg": round(miss_avg, 2),
            "delta": round(delta, 2),
            "optimal": round((opt[0] + opt[1]) / 2, 2),
            "impact_score": round(raw_impact, 4),
            "insight": insight,
            "cue": cue,
            "direction": direction,
        })

    # Normalize impact scores to 0-1
    max_impact = max((a["impact_score"] for a in improvement_areas), default=1) or 1
    for area in improvement_areas:
        area["impact_score"] = round(area["impact_score"] / max_impact, 2)

    # Sort by impact
    improvement_areas.sort(key=lambda x: x["impact_score"], reverse=True)

    # Consistency scores (all shots, not just makes)
    consistency = {}
    for metric in ALL_METRICS:
        values = [s.get(metric, 0) or 0 for s in all_shots if s.get(metric) is not None]
        if len(values) >= 5:
            std = statistics.stdev(values)
            opt = OPTIMAL_VALUES.get(metric, (0, 100))
            opt_span = max(abs(opt[1] - opt[0]), 0.01)
            # Lower relative std = more consistent (score 0-1)
            relative_std = std / opt_span
            score = max(0, min(1, 1 - relative_std))
            consistency[metric] = round(score, 2)

    # Miss distribution
    miss_distribution = {}
    for s in misses:
        mt = s.get("miss_type")
        if mt:
            miss_distribution[mt] = miss_distribution.get(mt, 0) + 1

    # Trend (last 5 sessions)
    recent_sessions = sessions[:5]
    trend_pcts = [s.get("shooting_percentage", 0) or 0 for s in reversed(recent_sessions)]
    trend_ratings = [s.get("average_form_rating", 0) or 0 for s in reversed(recent_sessions)]

    direction = "stable"
    if len(trend_pcts) >= 3:
        first_half = statistics.mean(trend_pcts[:len(trend_pcts)//2])
        second_half = statistics.mean(trend_pcts[len(trend_pcts)//2:])
        if second_half - first_half > 5:
            direction = "improving"
        elif first_half - second_half > 5:
            direction = "declining"

    trend = {
        "shooting_pct": [round(p, 1) for p in trend_pcts],
        "form_rating": [round(r, 1) for r in trend_ratings],
        "direction": direction,
    }

    # Generate coaching cues
    cues = [a["cue"] for a in improvement_areas[:3] if a.get("cue")]

    # Miss tendency cue
    miss_tendency_cue = ""
    if miss_distribution:
        top_miss = max(miss_distribution, key=miss_distribution.get)
        miss_tendency_cue = f"Your misses tend to go {top_miss}"

    # Trend label
    trend_labels = {"improving": "Improving", "declining": "Off lately", "stable": "Consistent"}
    trend_label = trend_labels.get(direction, "Consistent")

    # Consistency note
    consistency_note = ""
    if consistency:
        most_consistent = max(consistency, key=consistency.get)
        least_consistent = min(consistency, key=consistency.get)
        mc_label = METRIC_LABELS.get(most_consistent, most_consistent)
        lc_label = METRIC_LABELS.get(least_consistent, least_consistent)
        if consistency[most_consistent] > 0.8:
            consistency_note = f"Your {mc_label.lower()} is very consistent"
        elif consistency[least_consistent] < 0.4:
            consistency_note = f"Your {lc_label.lower()} varies a lot — focus on repeating the same motion"

    return {
        "session_count": session_count,
        "total_shots": total_shots,
        "fingerprint_ready": True,
        "make_signature": make_sig,
        "miss_signature": miss_sig,
        "improvement_areas": improvement_areas,
        "consistency": consistency,
        "miss_distribution": miss_distribution,
        "trend": trend,
        "cues": cues,
        "miss_tendency_cue": miss_tendency_cue,
        "trend_label": trend_label,
        "consistency_note": consistency_note,
    }


# Skeleton connections for overlay
SKELETON_CONNECTIONS = [
    # Torso
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    # Left arm
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    # Right arm
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
    # Left leg
    ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"),
    # Right leg
    ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"),
]

def draw_skeleton(frame, landmarks, visibility):
    """
    Draw skeleton overlay on frame.

    Args:
        frame: BGR image (numpy array)
        landmarks: Dict of landmark positions (normalized 0-1 coordinates)
        visibility: Dict of landmark visibility scores (0-1)

    Returns:
        Annotated frame with skeleton overlay
    """
    import cv2
    import numpy as np

    if not landmarks:
        return frame

    annotated = frame.copy()
    height, width = frame.shape[:2]

    # Use bright cyan color for visibility
    line_color = (255, 255, 0)  # Cyan in BGR
    point_color = (0, 255, 255)  # Yellow in BGR

    # Draw connections (lines between joints)
    for start_name, end_name in SKELETON_CONNECTIONS:
        start_lm = landmarks.get(start_name)
        end_lm = landmarks.get(end_name)
        start_vis = visibility.get(start_name, 0)
        end_vis = visibility.get(end_name, 0)

        # Only draw if both landmarks are visible
        if start_lm and end_lm and start_vis > 0.5 and end_vis > 0.5:
            # Convert normalized coords to pixel coords
            start_x = int(start_lm[0] * width)
            start_y = int(start_lm[1] * height)
            end_x = int(end_lm[0] * width)
            end_y = int(end_lm[1] * height)

            # Draw line
            cv2.line(annotated, (start_x, start_y), (end_x, end_y), line_color, 2)

    # Draw landmark points (circles at joints)
    for name, lm in landmarks.items():
        vis = visibility.get(name, 0)
        if vis > 0.5:
            # Convert normalized coords to pixel coords
            x = int(lm[0] * width)
            y = int(lm[1] * height)

            # Draw circle
            cv2.circle(annotated, (x, y), 4, point_color, -1)

    return annotated

def _clean_trajectory(trajectory, max_jump_px=80):
    """
    Remove noise from ball trajectory by filtering out impossible jumps.

    A basketball in flight follows a smooth parabolic arc. Any point that
    jumps more than max_jump_px from its predecessor is likely a false detection
    (reflection, other object, tracker glitch).

    Returns a cleaned trajectory with only physically plausible consecutive points.
    """
    if len(trajectory) < 2:
        return trajectory

    cleaned = [trajectory[0]]
    for i in range(1, len(trajectory)):
        prev = cleaned[-1]
        curr = trajectory[i]
        dx = abs(curr[0] - prev[0])
        dy = abs(curr[1] - prev[1])
        jump = (dx ** 2 + dy ** 2) ** 0.5
        if jump <= max_jump_px:
            cleaned.append(curr)
        # else: skip this noisy point

    return cleaned


def _find_longest_clean_segment(trajectory, max_jump_px=80):
    """
    Split trajectory at large jumps and return the longest contiguous segment.
    This handles cases where the tracker picks up the ball, loses it (noise),
    and then picks it up again later — we want the best continuous run.
    """
    if len(trajectory) < 2:
        return trajectory

    segments = []
    current_seg = [trajectory[0]]

    for i in range(1, len(trajectory)):
        prev = current_seg[-1]
        curr = trajectory[i]
        jump = ((curr[0] - prev[0]) ** 2 + (curr[1] - prev[1]) ** 2) ** 0.5
        if jump <= max_jump_px:
            current_seg.append(curr)
        else:
            if len(current_seg) >= 2:
                segments.append(current_seg)
            current_seg = [curr]

    if len(current_seg) >= 2:
        segments.append(current_seg)

    if not segments:
        return trajectory  # fallback to original if nothing survives

    # Return the segment that gets closest to the rim (not just longest)
    return max(segments, key=lambda s: len(s))


def analyze_make_miss(trajectory, rim_x, rim_y, frame_width, frame_height, camera_angle="side", skip_cleaning=False):
    """
    Determine make/miss from ball flight trajectory relative to user-calibrated rim.

    Uses the "above-below rim intersection" method:
    1. Clean noisy trajectory data (remove impossible jumps)
    2. Find last point above rim and first point below rim
    3. Interpolate crossing point and check if it passes through rim bounds
    4. Fall back to closest-point analysis if no crossing detected

    Camera angle affects confidence:
    - Side view: full confidence (ball moves across screen, crossing is visible)
    - Angled view: reduced confidence (depth partially compressed)
    - Front view: heavily reduced (can't distinguish through-hoop from near-miss)

    Args:
        trajectory: List[(x, y)] pixel coordinates of ball during flight
        rim_x, rim_y: Normalized 0-1 rim position from user calibration
        frame_width, frame_height: Video dimensions in pixels
        camera_angle: "side", "front", or "angled"

    Returns:
        dict with keys: made (bool|None), confidence (float), miss_type (str|None)
    """
    import numpy as np

    # Camera angle confidence multiplier — trajectory analysis is 2D,
    # so it's most reliable from side view where the ball's full arc is visible.
    angle_multipliers = {"side": 1.0, "angled": 0.7, "front": 0.4}
    angle_mult = angle_multipliers.get(camera_angle, 0.7)

    if len(trajectory) < 2:
        return {"made": None, "confidence": 0.0, "miss_type": None}

    rim_px = int(rim_x * frame_width)
    rim_py = int(rim_y * frame_height)

    # Estimate rim radius as ~2% of frame width
    rim_radius = int(frame_width * 0.02)

    # --- Step 1: Optionally clean trajectory by finding best contiguous segment ---
    raw_len = len(trajectory)
    if skip_cleaning:
        print(f"      🧹 Trajectory cleaning SKIPPED ({raw_len} points, raw)")
    else:
        frame_diag = (frame_width ** 2 + frame_height ** 2) ** 0.5
        max_jump = max(80, int(frame_diag * 0.05))

        segments = []
        current_seg = [trajectory[0]]
        for i in range(1, len(trajectory)):
            prev = current_seg[-1]
            curr = trajectory[i]
            jump = ((curr[0] - prev[0]) ** 2 + (curr[1] - prev[1]) ** 2) ** 0.5
            if jump <= max_jump:
                current_seg.append(curr)
            else:
                if len(current_seg) >= 2:
                    segments.append(current_seg)
                current_seg = [curr]
        if len(current_seg) >= 2:
            segments.append(current_seg)

        if segments:
            def seg_rim_dist(seg):
                return min(((p[0] - rim_px) ** 2 + (p[1] - rim_py) ** 2) ** 0.5 for p in seg)
            trajectory = min(segments, key=seg_rim_dist)

        print(f"      🧹 Trajectory cleaned: {raw_len} → {len(trajectory)} points "
              f"({len(segments)} segments found, max_jump={max_jump}px)")

    if len(trajectory) < 2:
        return {"made": None, "confidence": 0.0, "miss_type": None}

    # --- Step 1b: Trajectory extrapolation (avishah3 approach) ---
    # If the clean segment doesn't reach the rim area, fit a parabola and
    # predict where the ball would go. This handles the case where the
    # tracker loses the ball mid-flight before reaching the rim.
    extrapolated = False
    closest_to_rim_in_seg = min(
        ((p[0] - rim_px) ** 2 + (p[1] - rim_py) ** 2) ** 0.5 for p in trajectory
    )
    if len(trajectory) >= 5 and closest_to_rim_in_seg > rim_radius * 4:
        # Trajectory doesn't get near the rim — try extrapolation
        try:
            xs = [p[0] for p in trajectory]
            ys = [p[1] for p in trajectory]
            coeffs = np.polyfit(xs, ys, 2)  # y = ax² + bx + c
            a, b, c = coeffs

            # Only extrapolate if parabola opens downward (a > 0 means
            # y increases = ball goes down, which is correct for a shot arc
            # since y=0 is top of frame)
            last_x = xs[-1]
            x_dir = 1 if xs[-1] >= xs[0] else -1
            # Determine direction toward rim
            if abs(rim_px - last_x) > 10:
                x_dir = 1 if rim_px > last_x else -1

            predicted_pts = []
            for step in range(1, 40):
                pred_x = last_x + (step * 10 * x_dir)
                pred_y = int(a * pred_x * pred_x + b * pred_x + c)
                if pred_x < 0 or pred_x > frame_width or pred_y < 0 or pred_y > frame_height:
                    break
                predicted_pts.append((int(pred_x), pred_y))
                # Stop if we've passed well below the rim
                if pred_y > rim_py + rim_radius * 5:
                    break

            if predicted_pts:
                trajectory = trajectory + predicted_pts
                extrapolated = True
                print(f"      🔮 Extrapolated {len(predicted_pts)} predicted points "
                      f"(parabola a={a:.6f}, toward rim)")
        except Exception:
            pass  # polyfit can fail with bad data

    # --- Step 2: Find closest point to rim ---
    min_dist = float('inf')
    closest_idx = 0
    for i, (bx, by) in enumerate(trajectory):
        dist = ((bx - rim_px) ** 2 + (by - rim_py) ** 2) ** 0.5
        if dist < min_dist:
            min_dist = dist
            closest_idx = i

    closest_x, closest_y = trajectory[closest_idx]

    # Check if ball is descending when near the rim
    descending_near_rim = False
    if closest_idx > 0:
        prev_y = trajectory[closest_idx - 1][1]
        descending_near_rim = closest_y > prev_y  # y increases downward

    # --- Step 3: Above-below rim intersection test ---
    # Find the last point above rim and first point below rim
    # This is more robust than checking consecutive frames
    last_above_idx = None
    first_below_idx = None

    # Wider horizontal window for crossing check (3 rim radii)
    hoop_horizontal_window = rim_radius * 3.0

    for i, (bx, by) in enumerate(trajectory):
        if by <= rim_py and abs(bx - rim_px) < hoop_horizontal_window:
            last_above_idx = i

    if last_above_idx is not None:
        for i in range(last_above_idx + 1, len(trajectory)):
            bx, by = trajectory[i]
            if by >= rim_py:
                first_below_idx = i
                break

    through_hoop = False
    crossing_x_at_rim = None
    if last_above_idx is not None and first_below_idx is not None:
        # Interpolate: where does the line from last_above to first_below
        # cross rim_y? Check if that x is within rim bounds.
        ax, ay = trajectory[last_above_idx]
        bx_pt, by_pt = trajectory[first_below_idx]

        dy_span = by_pt - ay
        if abs(dy_span) > 0:
            t = (rim_py - ay) / dy_span  # 0..1 interpolation factor
            crossing_x_at_rim = ax + t * (bx_pt - ax)

            # Check if crossing x falls within rim opening
            # Rim diameter is roughly 2x rim_radius, with some tolerance
            rim_tolerance = rim_radius * 2.5
            if abs(crossing_x_at_rim - rim_px) < rim_tolerance:
                through_hoop = True

    # Also check the old consecutive-frame method as backup
    if not through_hoop:
        for i in range(len(trajectory) - 1):
            bx1, by1 = trajectory[i]
            bx2, by2 = trajectory[i + 1]
            if by1 <= rim_py and by2 >= rim_py:
                if abs(bx1 - rim_px) < hoop_horizontal_window and abs(bx2 - rim_px) < hoop_horizontal_window:
                    through_hoop = True
                    break

    # --- Step 4: Classification ---
    dx = closest_x - rim_px
    dy = closest_y - rim_py

    # Slightly wider thresholds now that trajectory is cleaned
    make_threshold = rim_radius * 1.5   # Ball center within ~1.5 rim radii = plausible make
    near_threshold = rim_radius * 4.0   # Within 4 radii = near miss

    crossing_info = ""
    if crossing_x_at_rim is not None:
        crossing_info = f", crossing_x={crossing_x_at_rim:.0f} (rim_x={rim_px}, tol=±{rim_radius * 2.5:.0f})"

    print(f"      📐 analyze_make_miss: closest=({closest_x:.0f},{closest_y:.0f}) idx={closest_idx}, "
          f"dist={min_dist:.0f}px, dx={dx:.0f}, dy={dy:.0f}")
    print(f"      📐 rim_radius={rim_radius}px, make_thresh={make_threshold:.0f}px, near_thresh={near_threshold:.0f}px")
    print(f"      📐 through_hoop={through_hoop}, descending={descending_near_rim}, angle={camera_angle} (×{angle_mult})"
          f"{crossing_info}")
    if last_above_idx is not None:
        print(f"      📐 last_above=idx{last_above_idx} {trajectory[last_above_idx]}, "
              f"first_below={'idx' + str(first_below_idx) + ' ' + str(trajectory[first_below_idx]) if first_below_idx else 'none'}")

    if through_hoop and min_dist < make_threshold * 3:
        confidence = max(0.65, 1.0 - (min_dist / (make_threshold * 3)) * 0.35) * angle_mult
        print(f"      ✅ MADE via through-hoop (conf={confidence:.0%})")
        return {"made": True, "confidence": confidence, "miss_type": None}

    if min_dist < make_threshold and descending_near_rim:
        confidence = max(0.50, 1.0 - (min_dist / make_threshold) * 0.50) * angle_mult
        print(f"      ✅ MADE via close+descending (conf={confidence:.0%})")
        return {"made": True, "confidence": confidence, "miss_type": None}

    # Near the rim but didn't go through — likely a miss
    if min_dist < near_threshold:
        if abs(dx) > abs(dy):
            lr = "left" if dx < 0 else "right"
            sl = "short" if dy > 0 else "long"
        else:
            sl = "short" if dy > 0 else "long"
            lr = "left" if dx < 0 else "right"
        miss_type = f"{sl}-{lr}"
        confidence = max(0.4, 1.0 - (min_dist / near_threshold) * 0.6) * angle_mult
        print(f"      ❌ MISSED: {miss_type} (conf={confidence:.0%})")
        return {"made": False, "confidence": confidence, "miss_type": miss_type}

    print(f"      ❓ UNCLEAR: ball never got close to rim (min_dist={min_dist:.0f}px > near_thresh={near_threshold:.0f}px)")
    return {"made": None, "confidence": 0.2 * angle_mult, "miss_type": None}


# Fingerprint endpoint
@app.get("/fingerprint/{user_id}", response_model=ShotFingerprint)
async def get_fingerprint(user_id: str):
    """Compute and return user's shot fingerprint."""
    if not _supabase_client:
        raise HTTPException(status_code=503, detail="Supabase not configured")
    try:
        data = _compute_fingerprint(user_id)
        return ShotFingerprint(**data)
    except Exception as e:
        print(f"Fingerprint error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Fingerprint computation failed: {str(e)}")


# Health check
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check if the API is running"""
    return HealthResponse(
        status="healthy",
        modules_available=MODULES_AVAILABLE,
        gemini_configured=bool(GEMINI_API_KEY),
        database_available=db is not None
    )

@app.get("/progress/{session_id}", response_model=ProgressResponse)
async def get_progress(session_id: str):
    """Get analysis progress for a session."""
    if session_id in _analysis_progress:
        return ProgressResponse(**_analysis_progress[session_id])
    return ProgressResponse(
        stage="unknown",
        progress=0,
        message="No active analysis found for this session",
    )

# Analyze entire video with multiple shots
@app.post("/analyze", response_model=SessionSummary)
async def analyze_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    shooting_side: str = "right",
    player_id: Optional[int] = None,
    rim_x: Optional[float] = None,  # Normalized 0-1 x coordinate of rim
    rim_y: Optional[float] = None,  # Normalized 0-1 y coordinate of rim
    session_id: Optional[str] = None,  # For progress tracking
    skill_level: Optional[str] = "intermediate",
    focus_areas: Optional[str] = None,
    height_inches: Optional[int] = None,
    user_id: Optional[str] = None,  # For fingerprint + history lookup
):
    """
    Analyze ALL shots in a video.
    
    Returns session summary with:
    - All detected shots
    - Makes/misses count
    - Session-level feedback
    - Drill suggestions
    """
    if not MODULES_AVAILABLE:
        raise HTTPException(status_code=503, detail="Analysis modules not available")
    
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY not configured")
    
    try:
        # Progress tracking helper
        def update_progress(stage: str, progress: int, message: str, **kwargs):
            if session_id:
                _analysis_progress[session_id] = {
                    "stage": stage,
                    "progress": progress,
                    "message": message,
                    **kwargs,
                }

        update_progress("uploading", 5, "Receiving video...")

        # Save uploaded file
        suffix = Path(file.filename).suffix if file.filename else ".mp4"
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        content = await file.read()
        temp_file.write(content)
        temp_file.close()
        video_path = temp_file.name

        # Run blocking video processing in a thread so the event loop
        # stays free to serve /progress polls while analysis runs.
        import asyncio

        def _blocking_analyze():
            return _run_analysis(
                video_path=video_path,
                filename=file.filename,
                shooting_side=shooting_side,
                rim_x=rim_x,
                rim_y=rim_y,
                session_id=session_id,
                skill_level=skill_level,
                focus_areas=focus_areas,
                height_inches=height_inches,
                user_id=user_id,
                update_progress=update_progress,
            )

        result = await asyncio.to_thread(_blocking_analyze)

        # Clean up progress entry after a short delay
        def _cleanup_progress(sid: str):
            import time as _t
            _t.sleep(30)
            _analysis_progress.pop(sid, None)
        if session_id:
            background_tasks.add_task(_cleanup_progress, session_id)

        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Analysis error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


def _run_analysis(
    video_path: str,
    filename: str,
    shooting_side: str,
    rim_x: Optional[float],
    rim_y: Optional[float],
    session_id: Optional[str],
    skill_level: Optional[str],
    focus_areas: Optional[str],
    height_inches: Optional[int],
    user_id: Optional[str],
    update_progress,
) -> SessionSummary:
    """Blocking video analysis — runs in a thread via asyncio.to_thread."""
    try:
        print(f"\n{'='*60}")
        print(f"📹 Processing video: {filename} ({os.path.getsize(video_path)} bytes)")
        if rim_x is not None and rim_y is not None:
            print(f"🎯 Rim position: ({rim_x:.3f}, {rim_y:.3f})")
        else:
            print(f"🎯 Rim position: not specified (make/miss less accurate)")
        print(f"{'='*60}\n")
        
        # Initialize components
        pose = PoseDetector()
        shot_detector = LiveShotDetector(shooting_side)

        # Reuse pre-loaded ball tracker (model already on GPU)
        ball_tracker = None
        release_detector = None
        if _shared_ball_tracker is not None:
            try:
                _shared_ball_tracker.reset()
                ball_tracker = _shared_ball_tracker
                release_detector = RealTimeReleaseDetector(shooting_side)
                print("✓ Ball tracking enabled (pre-loaded model)")
            except Exception as e:
                print(f"⚠️  Ball tracking reset failed: {e}")
                ball_tracker = None
                release_detector = None

        # Get player profile — prefer query params from mobile, fallback to DB
        player_profile = PlayerProfile(
            skill_level=skill_level or "intermediate",
            working_on=focus_areas or "",
            height_inches=height_inches,
        )

        # Fetch fingerprint for prompt injection (if user has enough data)
        fingerprint_data = None
        if user_id and _supabase_client:
            try:
                fingerprint_data = _compute_fingerprint(user_id)
                if fingerprint_data and fingerprint_data.get("fingerprint_ready"):
                    print(f"✓ Fingerprint loaded: {fingerprint_data['total_shots']} shots across {fingerprint_data['session_count']} sessions")
            except Exception as fp_err:
                print(f"⚠️  Fingerprint fetch failed: {fp_err}")
        
        # Process video to find ALL shots
        import cv2
        import time as _time
        cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():
            raise HTTPException(status_code=400, detail="Could not open video file")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print(f"🎬 Video info: {total_frames} frames @ {fps:.1f} fps ({width}x{height})")
        print(f"⏱️  Duration: {total_frames/fps:.1f} seconds")
        print(f"🔍 Scanning for shots...\n")

        update_progress("detecting", 10, "Scanning for shots...",
                        frame=0, total_frames=total_frames, shots_found=0)

        # Initialize Gemini client upfront so we can analyze shots as they're found
        from google import genai
        from google.genai import types
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)

        rim_position_available = rim_x is not None and rim_y is not None

        analyzed_shots = []
        release_frame_numbers = []
        pending_shots = []  # Queue shots for deferred analysis after ball tracking
        gemini_futures = []  # (shot_idx, Future) for parallel Gemini calls
        frame_count = 0
        shot_count = 0
        ball_tracking_frames = 0
        outcome_frames_buffer = {}  # {shot_count: [(frame_img, ball_center, frame_num), ...]}
        active_outcome_captures = []  # [(shot_idx, start_frame, end_frame)]

        from concurrent.futures import ThreadPoolExecutor
        gemini_executor = ThreadPoolExecutor(max_workers=3)

        def _select_outcome_frames(raw_outcomes, rim_x, rim_y, fw, fh):
            """Return all outcome frames for Gemini. No filtering, no cropping.

            Trajectory analysis handles make/miss when ball tracking is good.
            Gemini only matters when tracking fails — so give it every frame
            in chronological order and let it watch the full sequence.
            Cost difference is negligible (~$0.0004/shot on Gemini Flash).
            """
            if not raw_outcomes:
                return []
            return [(img, frame_num) for img, _, frame_num in raw_outcomes]

        # Collect strategy results per shot for session-level summary
        _strategy_log = []  # [(shot_idx, strat_a, strat_b, strat_c, strat_d, strat_e, strat_f)]

        # Helper: analyze a single shot with Gemini
        def analyze_shot_with_gemini(shot_event, shot_timestamp, shot_landmarks, shot_visibility, shot_frame_num, shot_idx, outcome_frames=None):
            """Build prompt, call Gemini, return ShotAnalysis."""
            # Programmatic make/miss from ball trajectory
            traj_result = None       # raw trajectory (PRIMARY — used for decisions)
            traj_result_clean = None # cleaned trajectory (logged for comparison only)
            if rim_position_available and ball_tracker:
                all_traj = ball_tracker.get_all_trajectories()
                print(f"   🔍 Shot #{shot_idx} trajectory lookup: {len(all_traj)} trajectories available, {len(release_frame_numbers)} releases detected")
                # Match closest trajectory to this shot
                if all_traj and release_frame_numbers:
                    best_idx = None
                    best_dist = float('inf')
                    for i, rel_frame in enumerate(release_frame_numbers):
                        dist = abs(rel_frame - shot_frame_num)
                        if dist < best_dist and i < len(all_traj):
                            best_dist = dist
                            best_idx = i
                    if best_idx is not None and best_dist < 60:
                        trajectory = all_traj[best_idx]
                        rim_px = int(rim_x * width)
                        rim_py = int(rim_y * height)
                        print(f"   🔍 Matched trajectory #{best_idx}: {len(trajectory)} points, release_frame_dist={best_dist}")
                        print(f"   🔍 Rim position: ({rim_px}, {rim_py}), trajectory points: {[(int(x), int(y)) for x, y in trajectory[:8]]}" + ("..." if len(trajectory) > 8 else ""))
                        if len(trajectory) >= 2:
                            cam_angle = shot_event.camera_angle or "side"
                            # Raw trajectory is PRIMARY (89% accuracy on side view)
                            traj_result = analyze_make_miss(trajectory, rim_x, rim_y, width, height, camera_angle=cam_angle, skip_cleaning=True)
                            made_str = "MADE" if traj_result["made"] else ("MISSED" if traj_result["made"] is False else "UNCLEAR")
                            print(f"   🎯 Trajectory (raw): {made_str} (confidence: {traj_result['confidence']:.0%})"
                                  + (f" [{traj_result['miss_type']}]" if traj_result.get('miss_type') else ""))
                            # Cleaned trajectory for comparison logging only
                            traj_result_clean = analyze_make_miss(trajectory, rim_x, rim_y, width, height, camera_angle=cam_angle, skip_cleaning=False)
                        else:
                            print(f"   ⚠️ Trajectory too short ({len(trajectory)} points), skipping analysis")
                    elif best_idx is not None:
                        print(f"   ⚠️ Closest trajectory too far from shot (dist={best_dist} frames, max=60)")
                    else:
                        print(f"   ⚠️ No trajectory match found")
                else:
                    print(f"   ⚠️ No trajectories or releases to match against")

            # Build Gemini prompt
            if traj_result and traj_result["confidence"] >= 0.5 and traj_result["made"] is not None:
                made_word = "MADE" if traj_result["made"] else "MISSED"
                miss_info = f" ({traj_result['miss_type']})" if traj_result.get("miss_type") else ""
                make_miss_instruction = f"""Ball trajectory tracking detected this shot was {made_word}{miss_info} with {traj_result['confidence']:.0%} confidence.
The rim was marked at ({rim_x:.2f}, {rim_y:.2f}).
Use this as strong guidance but verify against what you see in the frames.
- Set made={"true" if traj_result["made"] else "false"} unless you clearly see otherwise
- If the tracking result contradicts the frames, trust the frames"""
            elif rim_position_available:
                outcome_hint = ""
                if outcome_frames:
                    outcome_hint = f"\n{len(outcome_frames)} OUTCOME FRAMES are included after the form frames — these show the ball AFTER release, near the rim. Use these as your PRIMARY evidence for made/missed."
                make_miss_instruction = f"""The user marked the rim position at ({rim_x:.2f}, {rim_y:.2f}) in normalized coordinates.{outcome_hint}
Your DEFAULT answer is made=null unless you have CLEAR visual evidence.
- made=true ONLY if you clearly see the ball pass through the rim opening from above to below
- made=false if you clearly see the ball hit the rim and bounce away, hit the backboard and miss, or miss the rim area entirely
- made=null if the outcome is unclear, the ball leaves the frame, or you cannot see the rim area
Do NOT infer a make from a good-looking arc alone. A high arc does NOT mean the shot went in.
When in doubt, return made=null."""
            else:
                make_miss_instruction = """No rim position was provided and no ball trajectory data is available.
You MUST set made=null and miss_type=null. Do NOT guess whether the shot was made or missed.
This is a strict requirement — always return made=null when rim position is unknown."""

            # Build angle-specific metrics and instructions
            cam_angle = shot_event.camera_angle or "side"

            if cam_angle == "side":
                metrics_block = f"""Shot metrics (SIDE VIEW — angles are reliable):
**PRIMARY METRICS:**
- Elbow at load: {shot_event.elbow_angle_load:.0f}° (optimal: 50-70°)
- Elbow at release: {shot_event.elbow_angle_release:.0f}° (optimal: 130-165°)
- Wrist height at release: {shot_event.wrist_height_release:.2f}
- Knee bend at load: {shot_event.knee_bend_load:.0f}° (optimal: 95-115°)
- Hip angle at load: {shot_event.hip_angle_load:.0f}° (optimal: 120-145°)
- Elbow height at load: {shot_event.elbow_height_load:.2f} (0=hip, 1=shoulder, optimal: 0.8-1.1)
- Heel height at release: {shot_event.heel_height_release:.2f} (optimal: 0.05-0.15, higher = more lift)
- Trunk lean at release: {shot_event.trunk_lean_release:.1f}° (optimal: -3 to 3°, negative = forward lean)

**MOTION QUALITY METRICS:**
- Hitch count: {shot_event.hitch_count} (optimal: 0 — any hitch means a pause/stutter in the upward motion)
- Motion smoothness: {shot_event.motion_smoothness:.2f} (optimal: 1.0-1.3, higher = jerkier motion)
- Pocket lateral sweep: {shot_event.pocket_lateral_sweep:.3f} (optimal: 0.0-0.05, higher = ball sweeps sideways to set point)
- Dip depth: {shot_event.dip_depth:.3f} (0 = no dip below hip, higher = deeper dip)

From this side view, focus on: shot sequencing (legs-to-arms), follow-through, arc, balance, release timing, and shooting pocket path.
Look for: hitches/stutters in the upward motion, how deep the ball dips before coming up, and whether the pocket path is straight.
Do NOT comment on elbow alignment or guide hand — those are not visible from the side."""

            elif cam_angle == "front":
                metrics_block = f"""Shot metrics (FRONT VIEW — angle measurements are UNRELIABLE from this view):
- Elbow at load: {shot_event.elbow_angle_load:.0f}° (NOT reliable from front — do not comment on specific angle values)
- Elbow at release: {shot_event.elbow_angle_release:.0f}° (NOT reliable from front)
- Wrist height at release: {shot_event.wrist_height_release:.2f}
- Knee bend at load: {shot_event.knee_bend_load:.0f}° (NOT reliable from front)

**SUPPLEMENTARY METRICS (front-view specific):**
- Stance width: {shot_event.stance_width:.2f} (ratio of ankle spread to shoulder width, optimal: 0.9-1.2)
- Shoulder level diff: {shot_event.shoulder_level_diff:.2f} (positive = shooting shoulder higher, optimal: 0.0-0.1)
- Elbow lateral offset: {shot_event.elbow_lateral_offset:.2f} (0 = tucked, optimal: 0.0-0.15)

**MOTION QUALITY METRICS:**
- Hitch count: {shot_event.hitch_count} (optimal: 0)
- Motion smoothness: {shot_event.motion_smoothness:.2f} (optimal: 1.0-1.3)
- Pocket lateral sweep: {shot_event.pocket_lateral_sweep:.3f} (optimal: 0.0-0.05)
- Dip depth: {shot_event.dip_depth:.3f} (0 = no dip below hip)

From this front view, focus on: elbow alignment (tucked vs flared), ball path (straight vs drifting), stance width, shoulder symmetry, landing position, off-hand/guide hand interference, and footwork pattern.
Look for: off-hand thumb coming forward during release, footwork type (1-step, 2-step, shuffle, or jump stop), and whether the pocket path sweeps laterally.
Do NOT comment on specific angle values — they are inaccurate from the front."""

            else:  # angled
                metrics_block = f"""Shot metrics (ANGLED VIEW — angles are approximate):
- Elbow at load: {shot_event.elbow_angle_load:.0f}° (approximate)
- Elbow at release: {shot_event.elbow_angle_release:.0f}° (approximate)
- Wrist height at release: {shot_event.wrist_height_release:.2f}
- Knee bend at load: {shot_event.knee_bend_load:.0f}° (approximate)
- Hip angle at load: {shot_event.hip_angle_load:.0f}° (approximate, optimal: 120-145°)
- Elbow height at load: {shot_event.elbow_height_load:.2f} (approximate)
- Heel height at release: {shot_event.heel_height_release:.2f} (approximate)
- Trunk lean at release: {shot_event.trunk_lean_release:.1f}° (approximate)
- Stance width: {shot_event.stance_width:.2f} (approximate)
- Shoulder level diff: {shot_event.shoulder_level_diff:.2f} (approximate)
- Elbow lateral offset: {shot_event.elbow_lateral_offset:.2f} (approximate)

**MOTION QUALITY METRICS:**
- Hitch count: {shot_event.hitch_count} (optimal: 0)
- Motion smoothness: {shot_event.motion_smoothness:.2f} (optimal: 1.0-1.3)
- Pocket lateral sweep: {shot_event.pocket_lateral_sweep:.3f} (optimal: 0.0-0.05)
- Dip depth: {shot_event.dip_depth:.3f} (0 = no dip below hip)

From this angled view, you can assess both form mechanics and alignment, but angle measurements are approximate.
Look for: footwork pattern, off-hand interference, shooting pocket path, hitches in the motion, and follow-through quality. Comment on what you can clearly observe."""

            # Build player context section
            player_context = player_profile.to_prompt_section() if player_profile.skill_level != "intermediate" or player_profile.working_on or player_profile.height_inches else ""

            # Build fingerprint context for personalized feedback
            fingerprint_context = ""
            if fingerprint_data and fingerprint_data.get("fingerprint_ready"):
                fp = fingerprint_data
                make_sig = fp.get("make_signature", {})
                miss_sig = fp.get("miss_signature", {})
                improvements = fp.get("improvement_areas", [])

                sig_lines = []
                for metric, vals in make_sig.items():
                    miss_vals = miss_sig.get(metric, {})
                    label = metric.replace("_", " ")
                    sig_lines.append(f"  {label}: make avg={vals.get('avg', 0):.1f}, miss avg={miss_vals.get('avg', 0):.1f}")

                imp_lines = []
                for i, area in enumerate(improvements[:3]):
                    imp_lines.append(f"  {i+1}. {area.get('label', area.get('metric', ''))} — {area.get('insight', '')}")

                fingerprint_context = f"""
USER'S SHOT FINGERPRINT (from {fp['total_shots']} previous shots):
{chr(10).join(sig_lines)}

TOP IMPROVEMENT AREAS (auto-detected from their data):
{chr(10).join(imp_lines)}

Compare this shot to THEIR make signature, not just optimal ranges.
If this shot matches their miss signature on a top improvement area, flag it.
Your feedback must be in coaching cue language (e.g., "extend your elbow more")
— never cite raw numbers to the user.
"""

            prompt = f"""You are analyzing shot #{shot_idx} from a basketball practice session.
Camera angle: {cam_angle}
{player_context}
{metrics_block}

{make_miss_instruction}
{fingerprint_context}
Provide BRIEF analysis in JSON:
{{
    "made": true/false/null,
    "miss_type": "short-left" / "short-right" / "long-left" / "long-right" / null,
    "form_rating": 1-10,
    "feedback": "1-2 sentence coaching feedback — specific and actionable",
    "key_issue": "Main issue or 'none'",
    "quick_cue": "2-4 word cue"
}}
"""

            # Encode form frames as image parts
            content_for_gemini = [prompt]
            for label, frame_img in shot_event.frames:
                _, buffer = cv2.imencode('.jpg', frame_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
                content_for_gemini.append(
                    types.Part.from_bytes(data=bytes(buffer), mime_type="image/jpeg")
                )

            # Add outcome frames for make/miss determination
            # Always send all frames, uncropped. Trajectory handles make/miss when
            # tracking is good. Gemini only matters when tracking fails — and that's
            # exactly when we DON'T have ball position data to crop around.
            if outcome_frames:
                content_for_gemini.append(types.Part.from_text(text=
                    f"\n--- OUTCOME FRAMES ({len(outcome_frames)} frames in chronological order after release) ---\n"
                    "Watch this sequence like a mini-video. Look for the ball approaching the rim and "
                    "whether it passes through the hoop or misses."
                ))
                for outcome_entry in outcome_frames:
                    outcome_img = outcome_entry[0]
                    _, buffer = cv2.imencode('.jpg', outcome_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    content_for_gemini.append(
                        types.Part.from_bytes(data=bytes(buffer), mime_type="image/jpeg")
                    )

            # Call Gemini with retry for rate limits
            for _attempt in range(3):
                try:
                    response = gemini_client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=content_for_gemini,
                    )
                    text = response.text.strip()
                    break
                except Exception as _e:
                    if "429" in str(_e) and _attempt < 2:
                        wait = 10 * (_attempt + 1)
                        print(f"   ⏳ Rate limited, waiting {wait}s...")
                        _time.sleep(wait)
                    else:
                        raise

            # Parse JSON response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            result = json.loads(text)

            # --- Multi-strategy comparison logging ---
            # traj_result = raw trajectory (PRIMARY)
            # traj_result_clean = cleaned trajectory (comparison only)

            gemini_made = result.get("made")

            # Raw trajectory inputs (PRIMARY)
            tr_made = traj_result["made"] if traj_result else None
            tr_conf = traj_result["confidence"] if traj_result else 0.0
            tr_meaningful = tr_made is not None and tr_conf >= 0.45

            # Cleaned trajectory inputs (comparison only)
            tc_made = traj_result_clean["made"] if traj_result_clean else None
            tc_conf = traj_result_clean["confidence"] if traj_result_clean else 0.0
            tc_meaningful = tc_made is not None and tc_conf >= 0.45

            # --- Strategy A: Gemini-only ---
            strat_a = gemini_made

            # --- Strategy B: Cleaned-trajectory-only ---
            strat_b = tc_made if tc_meaningful else None

            # --- Strategy C: Gemini-first + cleaned-traj fallback ---
            strat_c = gemini_made if gemini_made is not None else (tc_made if tc_meaningful else None)

            # --- Strategy D: Cleaned-trajectory-first ---
            if not rim_position_available:
                strat_d = None
            elif tc_meaningful and gemini_made is not None and tc_made == gemini_made:
                strat_d = tc_made
            elif tc_meaningful and tc_conf >= 0.65:
                strat_d = tc_made
            elif tc_meaningful and gemini_made is None:
                strat_d = tc_made
            elif gemini_made is not None:
                strat_d = gemini_made
            else:
                strat_d = None

            # --- Strategy E: Agreement-only (cleaned) ---
            strat_e = tc_made if (tc_meaningful and gemini_made is not None and tc_made == gemini_made) else None

            # --- Strategy F: Raw-trajectory-only ---
            strat_f = tr_made if tr_meaningful else None

            # --- Strategy G: Gemini-first + raw-traj fallback ---
            strat_g = gemini_made if gemini_made is not None else (tr_made if tr_meaningful else None)

            # --- Strategy H: Raw-trajectory-first (ACTIVE — 75% across 28 test shots) ---
            # Uses raw trajectory when confident, falls back to Gemini.
            # Side view: raw traj leads (89% accurate when it has data)
            # Front view: traj is null → Gemini handles it (67-86%)
            if not rim_position_available:
                strat_h = None
            elif tr_meaningful and gemini_made is not None and tr_made == gemini_made:
                strat_h = tr_made  # agreement
            elif tr_meaningful and tr_conf >= 0.65:
                strat_h = tr_made  # high-conf raw trajectory
            elif tr_meaningful and gemini_made is None:
                strat_h = tr_made  # medium traj, gemini null
            elif gemini_made is not None:
                strat_h = gemini_made  # traj absent/weak, use Gemini
            else:
                strat_h = None

            # --- Strategy I: Agreement-only (raw) ---
            strat_i = tr_made if (tr_meaningful and gemini_made is not None and tr_made == gemini_made) else None

            # --- Strategy J: Gemini + raw-traj-confirm ---
            if gemini_made is not None:
                if tr_meaningful and tr_conf >= 0.65 and tr_made != gemini_made:
                    strat_j = None
                else:
                    strat_j = gemini_made
            elif tr_meaningful:
                strat_j = tr_made
            else:
                strat_j = None

            # *** ACTIVE STRATEGY: H (raw-trajectory-first) ***
            active_strategy = "H"
            final_made = strat_h
            result["made"] = final_made

            if not rim_position_available:
                result["made"] = None
                result["miss_type"] = None

            # --- Diagnostic logging: all strategies ---
            def _fmt(val):
                if val is True: return "MAKE"
                if val is False: return "MISS"
                return "null"

            tr_summary = "none"
            if traj_result:
                tr_str = "MADE" if traj_result["made"] else ("MISSED" if traj_result["made"] is False else "UNCLEAR")
                tr_summary = f"{tr_str} {traj_result['confidence']:.0%}"
            tc_summary = "none"
            if traj_result_clean:
                tc_str = "MADE" if traj_result_clean["made"] else ("MISSED" if traj_result_clean["made"] is False else "UNCLEAR")
                tc_summary = f"{tc_str} {traj_result_clean['confidence']:.0%}"

            print(f"   ┌──────────────────────────────────────────────────────────────")
            print(f"   │ 📊 Shot #{shot_idx} — Strategy Comparison")
            print(f"   │ Inputs: gemini={_fmt(gemini_made)}, raw_traj={tr_summary}, clean_traj={tc_summary}")
            print(f"   │")
            print(f"   │ CLEANED TRAJ:                    RAW TRAJ:")
            print(f"   │ A) Gemini-only:     {_fmt(strat_a):<6}       F) Raw-traj-only:    {_fmt(strat_f)}")
            print(f"   │ B) Clean-traj-only: {_fmt(strat_b):<6}       G) Gem1st+raw:       {_fmt(strat_g)}")
            print(f"   │ C) Gem1st+clean:    {_fmt(strat_c):<6}       H) Raw-traj-first:   {_fmt(strat_h)} {'←ACT' if active_strategy=='H' else ''}")
            print(f"   │ D) Clean-traj-1st:  {_fmt(strat_d):<6}       I) Agree(raw):       {_fmt(strat_i)}")
            print(f"   │ E) Agree(clean):    {_fmt(strat_e):<6}       J) Gem+raw-confirm:  {_fmt(strat_j)}")
            print(f"   │")
            print(f"   │ ➡️  ACTIVE ({active_strategy}): {_fmt(final_made)}")
            print(f"   └──────────────────────────────────────────────────────────────")

            _strategy_log.append((shot_idx, strat_a, strat_b, strat_c, strat_d, strat_e, strat_f, strat_g, strat_h, strat_i, strat_j))

            # Create thumbnail with skeleton overlay
            # Use the release frame (index 14 in 20-frame layout) for thumbnail
            release_frame_idx = next((i for i, (label, _) in enumerate(shot_event.frames) if 'Release' in label), len(shot_event.frames) - 1)
            rel_frame = shot_event.frames[release_frame_idx][1]
            if shot_landmarks and shot_visibility:
                rel_frame = draw_skeleton(rel_frame, shot_landmarks, shot_visibility)

            fh, fw = rel_frame.shape[:2]
            target_h = 480
            target_w = int(fw * (target_h / fh))
            resized = cv2.resize(rel_frame, (target_w, target_h))
            _, buffer = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, 85])
            thumbnail_b64 = base64.b64encode(buffer).decode('utf-8')

            print(f"   ✓ Shot {shot_idx}: {result.get('made', 'unknown')} - {result.get('feedback', '')[:40]}...")

            return ShotAnalysis(
                shot_number=shot_event.shot_number,
                made=result.get("made"),
                miss_type=result.get("miss_type"),
                form_rating=result.get("form_rating"),
                feedback=result.get("feedback", ""),
                key_issue=result.get("key_issue"),
                quick_cue=result.get("quick_cue"),
                elbow_angle_load=shot_event.elbow_angle_load,
                elbow_angle_release=shot_event.elbow_angle_release,
                wrist_height_release=shot_event.wrist_height_release,
                knee_bend_load=shot_event.knee_bend_load,
                hip_angle_load=shot_event.hip_angle_load,
                elbow_height_load=shot_event.elbow_height_load,
                heel_height_release=shot_event.heel_height_release,
                trunk_lean_release=shot_event.trunk_lean_release,
                stance_width=shot_event.stance_width,
                shoulder_level_diff=shot_event.shoulder_level_diff,
                elbow_lateral_offset=shot_event.elbow_lateral_offset,
                hitch_count=shot_event.hitch_count,
                hitch_severity=shot_event.hitch_severity,
                motion_smoothness=shot_event.motion_smoothness,
                pocket_lateral_sweep=shot_event.pocket_lateral_sweep,
                dip_depth=shot_event.dip_depth,
                camera_angle=shot_event.camera_angle,
                thumbnail=thumbnail_b64,
                timestamp=shot_timestamp,
            )

        # ---- Main frame processing loop ----
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1

            # Show progress every 100 frames
            if frame_count % 100 == 0:
                progress = (frame_count / total_frames) * 100
                flight_status = " | 🏀 Tracking ball" if (ball_tracker and ball_tracker.in_flight) else ""
                print(f"   Processing: {progress:.0f}% ({frame_count}/{total_frames} frames){flight_status}")

                # Map frame progress to 10-80% range (leave room for Gemini collection + summary)
                scaled_progress = 10 + int((frame_count / total_frames) * 70)
                shot_info = f" ({shot_count} shots found)" if shot_count > 0 else ""
                update_progress("detecting", scaled_progress,
                                f"Processing frames... {progress:.0f}%{shot_info}",
                                frame=frame_count, total_frames=total_frames,
                                shots_found=shot_count)

            # Detect pose
            landmarks, visibility = pose.detect(frame)

            # Ball tracking: only run YOLO when ball is in flight (after release)
            if ball_tracker and release_detector and landmarks:
                if release_detector.update(landmarks):
                    wrist = landmarks.get(f"{shooting_side}_wrist")
                    wrist_pos = None
                    if wrist:
                        wrist_pos = (int(wrist[0] * width), int(wrist[1] * height))
                    ball_tracker.mark_release(wrist_pos)
                    release_frame_numbers.append(frame_count)
                    print(f"   🏀 Release detected at frame {frame_count} — tracking ball flight...")
                # Only track ball during flight to avoid slowing down the whole video
                was_in_flight = ball_tracker.in_flight
                if ball_tracker.in_flight:
                    ball_tracker.detect(frame, landmarks, shooting_side)
                    ball_tracking_frames += 1
                if was_in_flight and not ball_tracker.in_flight:
                    traj = ball_tracker.get_all_trajectories()
                    last_traj_len = len(traj[-1]) if traj else 0
                    print(f"   🏀 Ball flight ended at frame {frame_count} — {last_traj_len} trajectory points captured")

            # Capture outcome frames in fixed window (release + 20 to release + 75)
            # Every 4th frame ≈ 15 frames in this window for denser coverage
            for cap_shot_idx, cap_start, cap_end in active_outcome_captures:
                if cap_start <= frame_count <= cap_end and frame_count % 4 == 0:
                    ball_center = None
                    ball_status = "no_tracker"
                    if ball_tracker:
                        if ball_tracker.in_flight and ball_tracker.last_detection and ball_tracker.last_detection.detected:
                            ball_center = ball_tracker.last_detection.center
                            ball_status = f"tracked({ball_center[0]:.0f},{ball_center[1]:.0f})"
                        elif ball_tracker.in_flight:
                            ball_status = "in_flight_no_detection"
                        else:
                            ball_status = "flight_ended"
                    small = cv2.resize(frame, (640, int(640 * height / width)))
                    if cap_shot_idx not in outcome_frames_buffer:
                        outcome_frames_buffer[cap_shot_idx] = []
                    outcome_frames_buffer[cap_shot_idx].append((small, ball_center, frame_count))
                    print(f"   📸 Outcome frame for shot #{cap_shot_idx}: frame={frame_count}, ball={ball_status}")

            # Clean up expired outcome captures
            active_outcome_captures = [(si, s, e) for si, s, e in active_outcome_captures if frame_count <= e]

            # Detect shot — queue for deferred analysis (wait for ball tracking)
            shot = shot_detector.update(frame, landmarks, visibility)
            if shot:
                shot_count += 1
                shot.shot_number = shot_count
                shot_timestamp = frame_count / fps
                print(f"\n✓ Shot #{shot_count} detected at frame {frame_count} ({shot_timestamp:.2f}s)")
                print(f"   Elbow: {shot.elbow_angle_load:.0f}° → {shot.elbow_angle_release:.0f}°")
                # Queue shot — don't analyze yet, wait for ball flight to complete
                pending_shots.append((shot, shot_timestamp, landmarks.copy(), visibility.copy(), frame_count, shot_count))
                # Register fixed outcome frame capture window (only if rim is marked)
                if rim_position_available:
                    active_outcome_captures.append((shot_count, frame_count + 20, frame_count + 75))
                    print(f"   📹 Outcome capture window: frames {frame_count + 20}-{frame_count + 75}")

            # Submit pending shots once outcome window has closed
            if pending_shots:
                oldest_frame = pending_shots[0][4]
                outcome_done = frame_count > oldest_frame + 80  # outcome window ends at +75, +5 buffer
                no_tracker = not ball_tracker

                if outcome_done or no_tracker:
                    trigger_reason = "outcome_window_closed" if outcome_done else "no_tracker"
                    flight_status = "in_flight" if (ball_tracker and ball_tracker.in_flight) else "flight_ended" if ball_tracker else "no_tracker"
                    print(f"   ⏰ Submitting pending shots: trigger={trigger_reason}, ball_tracker={flight_status}, waited={frame_count - oldest_frame} frames")

                    if ball_tracker and ball_tracker.in_flight:
                        ball_tracker.end_flight()

                    for pending in pending_shots:
                        p_shot, p_ts, p_lm, p_vis, p_frame, p_idx = pending
                        raw_outcomes = outcome_frames_buffer.pop(p_idx, [])
                        ball_detected_count = sum(1 for _, bc, _ in raw_outcomes if bc is not None)
                        print(f"   📦 Shot #{p_idx}: {len(raw_outcomes)} raw outcome frames, {ball_detected_count} with ball position")
                        selected_outcome = _select_outcome_frames(
                            raw_outcomes,
                            rim_x, rim_y, width, height
                        )
                        print(f"🤖 Submitting shot #{p_idx} to Gemini (parallel, {len(selected_outcome)} outcome frames)...")
                        future = gemini_executor.submit(
                            analyze_shot_with_gemini,
                            p_shot, p_ts, p_lm, p_vis, p_frame, p_idx, selected_outcome
                        )
                        gemini_futures.append((p_idx, future))
                    pending_shots.clear()

        # End any remaining flight
        if ball_tracker and ball_tracker.in_flight:
            ball_tracker.end_flight()

        # Submit any remaining pending shots (detected near end of video)
        if pending_shots:
            if ball_tracker and ball_tracker.in_flight:
                ball_tracker.end_flight()
            for pending in pending_shots:
                p_shot, p_ts, p_lm, p_vis, p_frame, p_idx = pending
                selected_outcome = _select_outcome_frames(
                    outcome_frames_buffer.pop(p_idx, []),
                    rim_x, rim_y, width, height
                )
                print(f"🤖 Submitting shot #{p_idx} to Gemini (end of video, {len(selected_outcome)} outcome frames)...")
                future = gemini_executor.submit(
                    analyze_shot_with_gemini,
                    p_shot, p_ts, p_lm, p_vis, p_frame, p_idx, selected_outcome
                )
                gemini_futures.append((p_idx, future))
            pending_shots.clear()

        cap.release()
        pose.close()

        # Collect all parallel Gemini results
        total_futures = len(gemini_futures)
        print(f"\n⏳ Waiting for {total_futures} Gemini analysis results...")
        update_progress("analyzing_shot", 82, f"Analyzing {total_futures} shots...",
                        shots_found=shot_count)
        for i, (shot_idx, future) in enumerate(gemini_futures):
            try:
                shot_analysis = future.result(timeout=60)
                analyzed_shots.append(shot_analysis)
                collect_progress = 82 + int((i + 1) / max(total_futures, 1) * 10)
                update_progress("analyzing_shot", collect_progress,
                                f"Analyzed shot {i + 1}/{total_futures}...",
                                shots_found=shot_count, current_shot=shot_idx)
            except Exception as e:
                print(f"   ❌ Shot #{shot_idx} Gemini analysis failed: {e}")
        gemini_executor.shutdown(wait=False)

        # Sort by shot number since parallel execution may return out of order
        analyzed_shots.sort(key=lambda s: s.shot_number)

        if ball_tracker:
            all_traj = ball_tracker.get_all_trajectories()
            print(f"\n🏀 Ball tracking: {len(all_traj)} trajectories, {ball_tracking_frames} frames tracked")

        # Cleanup temp file
        try:
            os.unlink(video_path)
        except OSError:
            pass

        if not analyzed_shots:
            raise HTTPException(
                status_code=404,
                detail="No shots detected. Make sure video shows clear shooting motions with full body visible."
            )
        
        # Calculate session stats (handle null/unknown makes)
        makes = sum(1 for s in analyzed_shots if s.made is True)
        misses = sum(1 for s in analyzed_shots if s.made is False)
        unknown = sum(1 for s in analyzed_shots if s.made is None)
        total = len(analyzed_shots)

        # Calculate shooting percentage only from known shots
        known_shots = makes + misses
        shooting_pct = (makes / known_shots * 100) if known_shots > 0 else 0

        if unknown > 0:
            print(f"⚠️  {unknown} shot(s) have unknown make/miss (rim not visible)")
        
        ratings = [s.form_rating for s in analyzed_shots if s.form_rating]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0
        
        print(f"\n{'='*60}")
        if unknown > 0:
            print(f"📊 Session Stats: {makes}/{known_shots} made ({shooting_pct:.1f}%) - {unknown} unknown")
        else:
            print(f"📊 Session Stats: {makes}/{total} made ({shooting_pct:.1f}%)")
        print(f"⭐ Average form rating: {avg_rating:.1f}/10")
        print(f"{'='*60}")

        # --- Session-level strategy comparison ---
        if _strategy_log:
            def _count(results):
                m = sum(1 for r in results if r is True)
                x = sum(1 for r in results if r is False)
                n = sum(1 for r in results if r is None)
                return f"{m} makes, {x} misses, {n} null"

            def _s(v):
                if v is True: return "MAKE"
                if v is False: return "MISS"
                return "null"

            print(f"\n┌───────────────────────────────────────────────────────────────────────────────────────────")
            print(f"│ 🏀 SESSION STRATEGY COMPARISON ({len(_strategy_log)} shots)")
            print(f"│")
            print(f"│  Shot#  A:Gem  B:CTrj  C:G+CT  D:CT1st  E:AgC  F:RTrj  G:G+RT  H:RT1st  I:AgR  J:G+RC")
            print(f"│  ─────  ─────  ──────  ──────  ───────  ─────  ──────  ──────  ───────  ─────  ──────")
            for entry in _strategy_log:
                si = entry[0]
                vals = entry[1:]
                cols = "  ".join(f"{_s(v):<5}" for v in vals)
                print(f"│  #{si:<4}  {cols}")
            print(f"│")
            print(f"│  TOTALS:                CLEANED TRAJ                          RAW TRAJ")
            print(f"│  A) Gemini-only:         {_count([s[1] for s in _strategy_log])}")
            print(f"│  B) Clean-traj-only:     {_count([s[2] for s in _strategy_log])}")
            print(f"│  C) Gem1st+clean:        {_count([s[3] for s in _strategy_log])}")
            print(f"│  D) Clean-traj-first:    {_count([s[4] for s in _strategy_log])}")
            print(f"│  E) Agree(clean):        {_count([s[5] for s in _strategy_log])}")
            print(f"│  F) Raw-traj-only:       {_count([s[6] for s in _strategy_log])}")
            print(f"│  G) Gem1st+raw:          {_count([s[7] for s in _strategy_log])}")
            print(f"│  H) Raw-traj-first:      {_count([s[8] for s in _strategy_log])}")
            print(f"│  I) Agree(raw):          {_count([s[9] for s in _strategy_log])}")
            print(f"│  J) Gem+raw-confirm:     {_count([s[10] for s in _strategy_log])}")
            print(f"└───────────────────────────────────────────────────────────────────────────────────────────")
        print()
        
        # Generate session-level feedback with Gemini
        update_progress("generating_summary", 92,
                        f"Generating session summary for {total} shots...",
                        shots_found=total)
        print(f"🤖 Generating session summary...")
        
        # Build stats description for session prompt
        if unknown > 0:
            stats_desc = f"Made: {makes}/{known_shots} known shots ({shooting_pct:.1f}%), {unknown} shots had unclear outcome"
        else:
            stats_desc = f"Made: {makes}/{total} ({shooting_pct:.1f}%)"

        # Build fingerprint summary context
        session_fp_context = ""
        if fingerprint_data and fingerprint_data.get("fingerprint_ready"):
            fp = fingerprint_data
            trend = fp.get("trend", {})
            miss_dist = fp.get("miss_distribution", {})
            improvements = fp.get("improvement_areas", [])

            trend_dir = trend.get("direction", "stable")
            miss_parts = [f"{k}: {v}" for k, v in miss_dist.items()] if miss_dist else []

            session_fp_context = f"""
HISTORICAL CONTEXT:
- Trend: User is {trend_dir} over last sessions
- Miss tendencies: {', '.join(miss_parts) if miss_parts else 'not enough data'}
- Top improvement areas: {', '.join(a.get('label', '') for a in improvements[:3])}

Write session feedback as coaching cues, not statistics.
Good: "Focus on extending your elbow fully - that's the biggest difference in your makes vs misses"
Bad: "Your elbow extension averages 148.7 on makes vs 125.3 on misses"
"""

        session_prompt = f"""You analyzed {total} basketball shots. Provide a session summary.
{player_profile.to_prompt_section() if player_profile.skill_level != "intermediate" or player_profile.working_on else ""}
Stats:
- {stats_desc}
- Average form rating: {avg_rating:.1f}/10

Individual shot feedback:
{chr(10).join(f"Shot {s.shot_number}: {s.feedback}" for s in analyzed_shots)}
{session_fp_context}
Provide session summary in JSON:
{{
    "session_feedback": "2-3 sentence overall assessment focusing on patterns and progress",
    "drill_suggestions": ["Drill 1 (specific)", "Drill 2 (specific)", "Drill 3 (specific)"]
}}

Focus on:
- Consistency patterns
- Most common issues
- Specific actionable drills (not generic)
"""
        
        summary_response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=session_prompt,
        )
        summary_text = summary_response.text.strip()
        
        if "```json" in summary_text:
            summary_text = summary_text.split("```json")[1].split("```")[0]
        elif "```" in summary_text:
            summary_text = summary_text.split("```")[1].split("```")[0]
        
        summary_result = json.loads(summary_text)
        
        print(f"✓ Session summary generated\n")

        update_progress("complete", 100, "Analysis complete!",
                        shots_found=total)

        # Build complete session summary
        session_summary = SessionSummary(
            total_shots=total,
            shots_made=makes,
            shots_missed=misses,
            shooting_percentage=shooting_pct,
            average_form_rating=avg_rating,
            session_feedback=summary_result.get("session_feedback", ""),
            drill_suggestions=summary_result.get("drill_suggestions", []),
            shots=analyzed_shots,
            server_persisted=False,
        )

        # Attempt server-side persistence (non-blocking — don't fail response if DB write fails)
        if session_id and user_id:
            # We need started_at from the session — try to fetch it or use current time
            started_at = None
            if _supabase_client:
                try:
                    session_resp = _supabase_client.table("sessions").select("started_at").eq("id", session_id).single().execute()
                    started_at = session_resp.data.get("started_at") if session_resp.data else None
                except Exception:
                    pass
            if not started_at:
                started_at = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

            persistence_success = _persist_session_results(
                session_id=session_id,
                user_id=user_id,
                session_summary=session_summary,
                started_at=started_at
            )
            session_summary.server_persisted = persistence_success
        else:
            print("⚠️  Skipping server-side persistence (no session_id or user_id)")

        return session_summary

    except Exception as e:
        print(f"❌ Analysis error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

# Root endpoint
@app.get("/")
async def root():
    return {
        "name": "FormCheck API",
        "version": "2.0.0",
        "status": "running",
        "features": {
            "multi_shot_analysis": True,
            "session_summary": True,
            "drill_suggestions": True
        }
    }

if __name__ == "__main__":
    # Railway provides PORT, fallback to API_PORT or 8000
    port = int(os.environ.get("PORT", os.environ.get("API_PORT", 8000)))
    host = os.getenv("API_HOST", "0.0.0.0")

    print("🏀 FormCheck API v2.0.0 - Multi-Shot Analysis")
    print("=" * 60)
    print(f"🚀 Starting server on {host}:{port}")
    print(f"📖 Docs: http://localhost:{port}/docs")
    print(f"💚 Health: http://localhost:{port}/health")
    print("=" * 60)
    print("Features:")
    print("  • Multi-shot video analysis")
    print("  • Session summaries")
    print("  • Drill suggestions")
    print("=" * 60)

    # No reload in production, workers handled by uvicorn
    is_production = os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("PORT")
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=not is_production,
        workers=1,  # Single worker so in-memory progress tracking works across requests
        log_level="info"
    )