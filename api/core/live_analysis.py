#!/usr/bin/env python3
"""
FormCheck Live Analysis
Real-time basketball shot analysis with Gemini AI feedback.

Usage:
    export GEMINI_API_KEY="your-api-key"
    python live_analysis.py                    # Use webcam
    python live_analysis.py video.mp4          # Use video file
    python live_analysis.py --left video.mp4   # Left-handed mode
"""

import cv2
import numpy as np
import os
import sys
import time
import threading
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import base64
import json

# Local imports
try:
    from database import FormCheckDB, get_nba_context_for_prompt, PlayerRecord
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    print("⚠️  Database module not found - session data won't persist")

try:
    from nba_analysis import (
        compare_to_nba, 
        get_height_category, 
        parse_height,
        perform_local_analysis,
        format_local_analysis_for_prompt,
        NBA_PLAYERS,
        RimDetector,
        MakeMissTracker
    )
    NBA_ANALYSIS_AVAILABLE = True
except ImportError:
    NBA_ANALYSIS_AVAILABLE = False
    print("⚠️  NBA analysis module not found - local comparisons disabled")

# New: Biomechanics-based analysis (legally safe for commercial use)
try:
    from biomechanics import (
        analyze_player_form,
        generate_personalized_targets,
        generate_coaching_context,
        generate_form_feedback,
        get_height_profile,
        get_distance_profile,
        ELBOW_ANGLE_LOAD,
        ELBOW_ANGLE_RELEASE,
        RELEASE_HEIGHT,
    )
    BIOMECHANICS_AVAILABLE = True
except ImportError:
    BIOMECHANICS_AVAILABLE = False
    print("⚠️  Biomechanics module not found")

# Aggregate community data (premium feature)
try:
    from aggregate_data import generate_community_comparison
    AGGREGATE_AVAILABLE = True
except ImportError:
    AGGREGATE_AVAILABLE = False

# Visual feedback system
try:
    from visual_feedback import (
        FrameAnnotator,
        ComparisonGenerator,
        LiveFeedbackOverlay,
        ShotBreakdown,
        Colors,
        get_status_color
    )
    VISUAL_FEEDBACK_AVAILABLE = True
except ImportError:
    VISUAL_FEEDBACK_AVAILABLE = False
    print("⚠️  Visual feedback module not found - using basic display")

# ============================================================================
# Configuration
# ============================================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"  # Fast model for real-time

# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ShotEvent:
    """Represents a detected shot with frames for analysis."""
    shot_number: int
    timestamp: float
    # Multiple frames capturing the full shot motion
    frames: List[Tuple[str, np.ndarray]]  # List of (label, frame)
    elbow_angle_load: float
    elbow_angle_release: float
    wrist_height_release: float = 0.0
    knee_bend_load: float = 0.0
    # Filled in by Gemini
    made: Optional[bool] = None
    miss_type: Optional[str] = None  # "short-left", "long-right", etc.
    form_rating: Optional[int] = None  # 1-10
    feedback: Optional[str] = None
    key_issue: Optional[str] = None
    did_well: Optional[List[str]] = None
    quick_cue: Optional[str] = None  # 2-4 word reminder
    looks_like: Optional[str] = None  # "makes" or "misses"
    processing: bool = True

@dataclass
class PlayerProfile:
    """Player's self-reported context for personalized coaching."""
    skill_level: str = "intermediate"  # beginner, intermediate, advanced
    working_on: str = ""  # What they want to focus on
    limitations: str = ""  # Injuries or physical limitations
    height_inches: Optional[int] = None  # Player height for personalized advice
    
    def to_prompt_section(self) -> str:
        """Generate prompt section for player context."""
        level_guidelines = {
            "beginner": """- Use simple, non-technical language
- Focus on fundamentals: balance, basic form, consistency
- Be extra encouraging - building confidence matters
- Large tolerance for variation - don't nitpick
- One tip at a time, nothing overwhelming""",
            "intermediate": """- Can handle moderately technical cues
- Balance fundamentals with refinement
- Focus on consistency and repeatability
- Can mention 1-2 things to work on""",
            "advanced": """- Technical language is fine
- Focus on micro-adjustments and consistency
- Assume fundamentals are intentional choices
- Can discuss subtle pattern differences
- Reference specific metrics when helpful"""
        }
        
        section = f"""
═══════════════════════════════════════════════════════════════════════════════
PLAYER CONTEXT
═══════════════════════════════════════════════════════════════════════════════

Skill level: {self.skill_level.capitalize()}
"""
        if self.height_inches:
            feet = self.height_inches // 12
            inches = self.height_inches % 12
            section += f"Height: {feet}'{inches}\" ({self.height_inches} inches)\n"
            
        if self.working_on:
            section += f'Currently working on: "{self.working_on}"\n'
        if self.limitations:
            section += f'Physical considerations: "{self.limitations}"\n'
        
        section += f"""
COACHING GUIDELINES FOR THIS PLAYER:
{level_guidelines.get(self.skill_level, level_guidelines["intermediate"])}
"""
        if self.working_on:
            section += f"""
PRIORITY: Their stated goal is "{self.working_on}" - prioritize feedback 
related to this. If you notice something MAJOR outside their focus area, 
mention it briefly but keep main feedback on their goal.
"""
        return section

@dataclass 
class ShotMetrics:
    """Metrics for a single shot."""
    shot_number: int
    made: Optional[bool]
    elbow_load: float
    elbow_release: float
    wrist_height: float
    knee_bend: float

@dataclass
class LiveState:
    """Tracks live analysis state."""
    shots_made: int = 0
    shots_missed: int = 0
    total_shots: int = 0
    current_feedback: Optional[str] = None
    feedback_display_until: float = 0
    last_shot_result: Optional[bool] = None  # True=made, False=missed
    result_flash_until: float = 0
    
    # Shot history for context
    shot_history: List[dict] = field(default_factory=list)
    shot_metrics: List[ShotMetrics] = field(default_factory=list)
    all_feedback_given: List[str] = field(default_factory=list)
    
    # Visual feedback storage
    last_shot_frames: List[Tuple[str, np.ndarray]] = field(default_factory=list)
    last_shot_landmarks: List[Dict] = field(default_factory=list)
    last_shot_metrics: Optional[Dict] = None
    last_shot_issues: List[Dict] = field(default_factory=list)
    last_shot_annotated: Optional[np.ndarray] = None
    show_last_shot: bool = False  # Toggle with 'v' key
    
    def get_make_miss_patterns(self) -> dict:
        """Analyze patterns in makes vs misses."""
        makes = [s for s in self.shot_metrics if s.made == True]
        misses = [s for s in self.shot_metrics if s.made == False]
        
        def avg_metrics(shots):
            if not shots:
                return None
            return {
                "elbow_load": {
                    "avg": np.mean([s.elbow_load for s in shots]),
                    "min": min(s.elbow_load for s in shots),
                    "max": max(s.elbow_load for s in shots)
                },
                "elbow_release": {
                    "avg": np.mean([s.elbow_release for s in shots]),
                    "min": min(s.elbow_release for s in shots),
                    "max": max(s.elbow_release for s in shots)
                },
                "wrist_height": {
                    "avg": np.mean([s.wrist_height for s in shots]),
                },
                "knee_bend": {
                    "avg": np.mean([s.knee_bend for s in shots]),
                },
                "shot_numbers": [s.shot_number for s in shots]
            }
        
        return {
            "makes": avg_metrics(makes),
            "misses": avg_metrics(misses),
            "total_makes": len(makes),
            "total_misses": len(misses)
        }

# ============================================================================
# Gemini Client
# ============================================================================

class GeminiClient:
    """Async Gemini API client with personalized, pattern-based coaching."""
    
    def __init__(self, api_key: str, player_profile: PlayerProfile = None,
                 db: 'FormCheckDB' = None, player_id: int = None):
        self.api_key = api_key
        self.enabled = bool(api_key)
        self.player_profile = player_profile or PlayerProfile()
        self.feedback_history = []  # Track given feedback to avoid repetition
        
        # Database integration
        self.db = db
        self.player_id = player_id
        self.historical_patterns = None
        self.recent_feedback_from_db = []
        
        # Load historical data if available
        if db and player_id:
            self._load_historical_data()
        
        if not self.enabled:
            print("⚠️  GEMINI_API_KEY not set - feedback disabled")
            print("   Set it with: export GEMINI_API_KEY='your-key'")
        else:
            print("✓ Gemini API configured")
    
    def _load_historical_data(self):
        """Load player's historical patterns from database."""
        if self.db and self.player_id:
            self.historical_patterns = self.db.get_player_patterns(self.player_id)
            self.recent_feedback_from_db = self.db.get_recent_feedback(self.player_id, limit=15)
            
            if self.historical_patterns.get("makes"):
                print(f"✓ Loaded historical data: {len(self.recent_feedback_from_db)} previous feedbacks")
    
    def analyze_shot_async(self, shot: ShotEvent, state: LiveState, callback,
                           local_analysis: Dict = None):
        """Analyze shot in background thread."""
        if not self.enabled:
            shot.processing = False
            shot.feedback = "Set GEMINI_API_KEY for AI feedback"
            callback(shot)
            return
        
        thread = threading.Thread(
            target=self._analyze, 
            args=(shot, state, callback, local_analysis)
        )
        thread.daemon = True
        thread.start()
    
    def _build_prompt(self, shot: ShotEvent, state: LiveState, 
                      local_analysis: Dict = None) -> str:
        """Build the full coaching prompt with historical data and NBA context."""
        
        patterns = state.get_make_miss_patterns()
        
        prompt = """You are an elite basketball shooting coach analyzing video of a shot.

Your feedback style should be:
- SPECIFIC with measurements ("your elbow is 3 inches lower than your makes")
- VISUAL about miss direction ("missed short-right", "fell just over the front rim")
- KINESTHETIC with feel cues ("imagine your elbow finishing above your eyes")
- DIRECT and punchy, like a real coach courtside

═══════════════════════════════════════════════════════════════════════════════
CURRENT SHOT: #{shot_num}
═══════════════════════════════════════════════════════════════════════════════

MEASURED DATA:
- Elbow angle at load: {elbow_load:.0f}°
- Elbow angle at release: {elbow_release:.0f}°
- Wrist release height: {wrist_height:.2f} (1.0 = shoulder level, >1.0 = above shoulder)
- Knee bend at load: {knee_bend:.0f}°
""".format(
            shot_num=shot.shot_number,
            elbow_load=shot.elbow_angle_load,
            elbow_release=shot.elbow_angle_release,
            wrist_height=shot.wrist_height_release,
            knee_bend=shot.knee_bend_load
        )
        
        # Add LOCAL ANALYSIS section if available (biomechanics-based)
        if local_analysis and BIOMECHANICS_AVAILABLE:
            prompt += """
═══════════════════════════════════════════════════════════════════════════════
LOCAL ANALYSIS (computed before sending to you)
═══════════════════════════════════════════════════════════════════════════════
"""
            # Add height-based recommendations
            if local_analysis.get("height_profile"):
                hp = local_analysis["height_profile"]
                prompt += f"""
HEIGHT-BASED RECOMMENDATIONS ({hp.get('category', 'N/A')}):
- Recommended release speed: {hp.get('release_speed', 'moderate')}
- Arc emphasis: {hp.get('arc_emphasis', 'standard')}
- Key principles: {'; '.join(hp.get('key_principles', [])[:2])}
"""
            
            # Add comparison to research benchmarks
            if local_analysis.get("vs_research"):
                prompt += f"\nVS RESEARCH: {local_analysis['vs_research']}\n"
        
        # Add player context
        prompt += self.player_profile.to_prompt_section()
        
        # Add HISTORICAL patterns (from database - across all sessions)
        if self.historical_patterns and self.historical_patterns.get("makes"):
            hist = self.historical_patterns
            prompt += """
═══════════════════════════════════════════════════════════════════════════════
HISTORICAL DATA (from all previous sessions with this player)
═══════════════════════════════════════════════════════════════════════════════
"""
            if hist["makes"]:
                m = hist["makes"]
                prompt += f"""
THEIR LIFETIME MAKE AVERAGES:
- Elbow at load: {m['avg_elbow_load']:.0f}° (range: {m['elbow_range'][0]:.0f}-{m['elbow_range'][1]:.0f}° when data available)
- Elbow at release: {m['avg_elbow_release']:.0f}°
- Wrist height: {m['avg_wrist_height']:.2f}
- Knee bend: {m['avg_knee_bend']:.0f}°
""" if m['elbow_range'] else f"""
THEIR LIFETIME MAKE AVERAGES:
- Elbow at load: {m['avg_elbow_load']:.0f}°
- Elbow at release: {m['avg_elbow_release']:.0f}°
- Wrist height: {m['avg_wrist_height']:.2f}
- Knee bend: {m['avg_knee_bend']:.0f}°
"""
            
            if hist["miss_distribution"]:
                prompt += f"\nHISTORICAL MISS TENDENCIES: {hist['miss_distribution']}\n"
            
            if hist["common_issues"]:
                issues = [f"{issue} ({count}x)" for issue, count in hist["common_issues"][:3]]
                prompt += f"RECURRING ISSUES: {', '.join(issues)}\n"
            
            if hist["recent_sessions"]:
                recent = hist["recent_sessions"][0]
                prompt += f"LAST SESSION: {recent['pct']:.0f}% shooting, {recent['rating']:.1f}/10 avg form\n"
        
        # Add CURRENT SESSION patterns
        prompt += """
═══════════════════════════════════════════════════════════════════════════════
THIS SESSION'S PATTERNS
═══════════════════════════════════════════════════════════════════════════════
"""
        
        if patterns["makes"]:
            m = patterns["makes"]
            prompt += f"""
MAKES THIS SESSION (shots {', '.join(map(str, m['shot_numbers']))}):
- Elbow at load: {m['elbow_load']['avg']:.0f}° (range: {m['elbow_load']['min']:.0f}-{m['elbow_load']['max']:.0f}°)
- Elbow at release: {m['elbow_release']['avg']:.0f}°
- Wrist height: {m['wrist_height']['avg']:.2f}
- Knee bend: {m['knee_bend']['avg']:.0f}°
"""
        else:
            prompt += "\nNo makes yet this session - use historical data if available.\n"
        
        if patterns["misses"]:
            m = patterns["misses"]
            prompt += f"""
MISSES THIS SESSION (shots {', '.join(map(str, m['shot_numbers']))}):
- Elbow at load: {m['elbow_load']['avg']:.0f}°
- Elbow at release: {m['elbow_release']['avg']:.0f}°
- Wrist height: {m['wrist_height']['avg']:.2f}
- Knee bend: {m['knee_bend']['avg']:.0f}°
"""
        
        # Key differences
        if patterns["makes"] and patterns["misses"]:
            mk, ms = patterns["makes"], patterns["misses"]
            elbow_diff = mk["elbow_load"]["avg"] - ms["elbow_load"]["avg"]
            wrist_diff = mk["wrist_height"]["avg"] - ms["wrist_height"]["avg"]
            
            prompt += f"""
KEY DIFFERENCES (makes vs misses this session):
- Elbow is {abs(elbow_diff):.0f}° {"higher" if elbow_diff > 0 else "lower"} on makes
- Release point is {abs(wrist_diff):.2f} {"higher" if wrist_diff > 0 else "lower"} on makes
"""
        
        # Previous feedback (combine DB + current session)
        all_previous_feedback = self.recent_feedback_from_db + [f["feedback"] for f in self.feedback_history]
        if all_previous_feedback:
            prompt += """
═══════════════════════════════════════════════════════════════════════════════
PREVIOUS FEEDBACK (vary your coaching - don't repeat these points)
═══════════════════════════════════════════════════════════════════════════════
"""
            # Show unique recent feedback
            unique_feedback = list(dict.fromkeys(all_previous_feedback))[:8]
            for fb in unique_feedback:
                prompt += f"• {fb}\n"
        
        # Add biomechanics research context (replaces NBA player-specific data)
        prompt += """
═══════════════════════════════════════════════════════════════════════════════
SHOOTING BIOMECHANICS RESEARCH (for context when player has no pattern yet)
═══════════════════════════════════════════════════════════════════════════════

Research-backed optimal ranges (use only if player has insufficient data):
- Entry angle: 44-47° maximizes margin for error at the rim
- Elbow at set point: 85-95° allows efficient force transfer
- Elbow at release: 165-175° (near-full extension)
- Release height: 10-30% above shoulder level

Common miss patterns and likely causes:
- Short = insufficient leg power, rushed shot, low release point
- Long = overcompensating with arms, not using legs efficiently
- Left/Right = guide hand interference, poor alignment, fading on shot

Key principle: The "best" form is what's REPEATABLE for this individual.
Coach them to consistency with THEIR optimal form, not textbook ideals.
Use research ranges only when their form deviates significantly or they're new.
"""
        
        # Task
        prompt += """
═══════════════════════════════════════════════════════════════════════════════
ANALYSIS TASK
═══════════════════════════════════════════════════════════════════════════════

Look at the 7 frames showing: Stance → Load → Rising → Release → Follow-through

ANALYZE:
1. Did the shot go in? If missed, WHERE did it miss? (short/long, left/right)
2. How does this compare to THEIR historical makes and this session's patterns?
3. What's the ONE thing that would help most right now?

YOUR FEEDBACK STYLE:
❌ Bad: "Try to keep your elbow tucked"
✅ Good: "You're pushing it - elbow at 82° but your makes are at 93°. Get under it."

❌ Bad: "Your release could be higher"  
✅ Good: "Release dropped - you're at shoulder level but nail shots at forehead. Finish high."

❌ Bad: "Good shot" (too vague)
✅ Good: "That's your shot! Elbow 94°, release on point. Remember this feel."

Use THEIR specific numbers. Reference THEIR makes. Give ONE clear fix with a FEEL cue.
If they're doing well, reinforce it specifically.

Respond in JSON:
{
    "made": true/false,
    "miss_type": "short-left" / "short-right" / "long-left" / "long-right" / "front-rim" / "back-rim" / null if made,
    "form_rating": 1-10 (10 = matches their best shots perfectly),
    "looks_like": "makes" / "misses" / "new",
    "feedback": "Your punchy, specific coaching tip with a feel cue - max 25 words",
    "key_issue": "The single biggest thing to fix (or 'none' if shot was good)",
    "did_well": ["specific thing 1", "specific thing 2"],
    "quick_cue": "2-4 word reminder they can repeat (e.g., 'elbow up, snap through')"
}
"""
        return prompt
    
    def _analyze(self, shot: ShotEvent, state: LiveState, callback, 
                 local_analysis: Dict = None):
        """Send frames to Gemini and get feedback."""
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(GEMINI_MODEL)
            
            # Encode all frames as base64
            frames_data = []
            for label, frame in shot.frames:
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                b64 = base64.b64encode(buffer).decode('utf-8')
                frames_data.append({"label": label, "data": b64})
            
            # Build prompt (include local analysis if available)
            prompt = self._build_prompt(shot, state, local_analysis)
            
            # Build content with images
            content = [prompt]
            for fd in frames_data:
                content.append({
                    "mime_type": "image/jpeg",
                    "data": fd["data"]
                })
            
            response = model.generate_content(content)
            
            # Parse response
            text = response.text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            result = json.loads(text)
            shot.made = result.get("made", None)
            shot.miss_type = result.get("miss_type", None)
            shot.form_rating = result.get("form_rating", None)
            shot.feedback = result.get("feedback", "Keep shooting!")
            shot.key_issue = result.get("key_issue", None)
            shot.did_well = result.get("did_well", [])
            shot.quick_cue = result.get("quick_cue", None)
            shot.looks_like = result.get("looks_like", "new")
            
            # Track feedback to avoid repetition
            self.feedback_history.append({
                "shot": shot.shot_number,
                "feedback": shot.feedback
            })
            
        except ImportError:
            shot.feedback = "Install: pip install google-generativeai"
        except Exception as e:
            shot.feedback = f"Analysis error: {str(e)[:50]}"
            print(f"Gemini error: {e}")
        
        shot.processing = False
        callback(shot)
    
    def generate_session_summary(self, state: LiveState) -> dict:
        """Generate overall session summary with grade and insights."""
        if not self.enabled or state.total_shots == 0:
            return {
                "grade": "N/A",
                "summary": "No shots analyzed",
                "pain_points": [],
                "strengths": [],
                "drill": ""
            }
        
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(GEMINI_MODEL)
            
            patterns = state.get_make_miss_patterns()
            shooting_pct = (state.shots_made / state.total_shots * 100) if state.total_shots > 0 else 0
            
            # Compile shot-by-shot summary
            shots_detail = ""
            all_miss_types = []
            all_form_ratings = []
            all_key_issues = []
            
            for h in state.shot_history:
                shots_detail += f"\nShot {h['number']}: {'Made' if h['made'] else 'Missed'}"
                if h.get('miss_type'):
                    shots_detail += f" ({h['miss_type']})"
                    all_miss_types.append(h['miss_type'])
                if h.get('form_rating'):
                    shots_detail += f" [Form: {h['form_rating']}/10]"
                    all_form_ratings.append(h['form_rating'])
                if h.get('feedback'):
                    shots_detail += f"\n  Feedback: {h['feedback']}"
                if h.get('key_issue') and h['key_issue'].lower() != 'none':
                    shots_detail += f"\n  Key issue: {h['key_issue']}"
                    all_key_issues.append(h['key_issue'])
            
            # Miss type analysis
            miss_analysis = ""
            if all_miss_types:
                miss_counts = Counter(all_miss_types)
                miss_analysis = f"\nMiss tendencies: {dict(miss_counts)}"
            
            avg_form = sum(all_form_ratings) / len(all_form_ratings) if all_form_ratings else 0
            
            prompt = f"""You are a basketball coach providing an end-of-session summary.

{self.player_profile.to_prompt_section()}

═══════════════════════════════════════════════════════════════════════════════
SESSION STATISTICS
═══════════════════════════════════════════════════════════════════════════════

Total shots: {state.total_shots}
Made: {state.shots_made}
Missed: {state.shots_missed}
Shooting %: {shooting_pct:.1f}%
Average Form Rating: {avg_form:.1f}/10
{miss_analysis}

═══════════════════════════════════════════════════════════════════════════════
SHOT-BY-SHOT BREAKDOWN
═══════════════════════════════════════════════════════════════════════════════
{shots_detail}

═══════════════════════════════════════════════════════════════════════════════
RECURRING ISSUES
═══════════════════════════════════════════════════════════════════════════════
{', '.join(all_key_issues) if all_key_issues else 'None noted'}

═══════════════════════════════════════════════════════════════════════════════
PATTERNS DISCOVERED
═══════════════════════════════════════════════════════════════════════════════
"""
            
            if patterns["makes"]:
                m = patterns["makes"]
                prompt += f"""
Their makes averaged:
- Elbow at load: {m['elbow_load']['avg']:.0f}°
- Elbow at release: {m['elbow_release']['avg']:.0f}°
- Wrist height: {m['wrist_height']['avg']:.2f}
- Knee bend: {m['knee_bend']['avg']:.0f}°
"""
            
            if patterns["misses"]:
                m = patterns["misses"]
                prompt += f"""
Their misses averaged:
- Elbow at load: {m['elbow_load']['avg']:.0f}°
- Elbow at release: {m['elbow_release']['avg']:.0f}°
- Wrist height: {m['wrist_height']['avg']:.2f}
- Knee bend: {m['knee_bend']['avg']:.0f}°
"""
            
            prompt += f"""
═══════════════════════════════════════════════════════════════════════════════
YOUR TASK
═══════════════════════════════════════════════════════════════════════════════

Provide a personalized session summary. Remember:
- Grade based on THEIR progress and consistency, not absolute standards
- A beginner shooting 40% with improving form might get a B
- An advanced player shooting 70% but inconsistent might get a B-
- Factor in whether they improved during the session

Respond in this exact JSON format:
{{
    "grade": "A/A-/B+/B/B-/C+/C/C-/D/F",
    "grade_explanation": "One sentence explaining the grade",
    "summary": "2-3 sentence overall assessment - encouraging but honest",
    "top_strength": "The ONE thing they do best",
    "strengths": ["Other things they do well"],
    "main_focus": "The ONE thing that would help most",
    "other_areas": ["Other areas to work on"],
    "drill": "One specific drill to address their main focus area",
    "encouragement": "A brief motivating closing message"
}}
"""
            
            response = model.generate_content(prompt)
            
            text = response.text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            return json.loads(text)
            
        except Exception as e:
            print(f"Summary error: {e}")
            return {
                "grade": "N/A",
                "summary": f"Could not generate summary: {str(e)[:50]}",
                "strengths": [],
                "pain_points": [],
                "drill": ""
            }

# ============================================================================
# Pose and Ball Detection
# ============================================================================

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
MODEL_PATH = os.path.join(os.path.dirname(__file__), "pose_landmarker.task")

LANDMARK_NAMES = {
    0: "nose",
    11: "left_shoulder", 12: "right_shoulder",
    13: "left_elbow", 14: "right_elbow",
    15: "left_wrist", 16: "right_wrist",
    23: "left_hip", 24: "right_hip",
    25: "left_knee", 26: "right_knee",
    27: "left_ankle", 28: "right_ankle",
}

def download_model():
    """Download pose landmarker model if needed."""
    if os.path.exists(MODEL_PATH):
        return
    
    print("Downloading pose model...")
    try:
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print("✓ Downloaded")
    except Exception as e:
        print(f"✗ Failed: {e}")
        print(f"Download manually: curl -o {MODEL_PATH} '{MODEL_URL}'")
        sys.exit(1)

class PoseDetector:
    """MediaPipe Tasks API pose detection."""
    
    def __init__(self):
        download_model()
        
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.detector = vision.PoseLandmarker.create_from_options(options)
        self.frame_count = 0
    
    def detect(self, frame: np.ndarray) -> Tuple[Dict, Dict]:
        """Returns (landmarks, visibility) dicts."""
        import mediapipe as mp
        
        # Convert to RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        
        # Detect with timestamp
        self.frame_count += 1
        timestamp_ms = int(self.frame_count * 33.33)  # Assume ~30fps
        
        try:
            results = self.detector.detect_for_video(mp_image, timestamp_ms)
        except Exception as e:
            return {}, {}
        
        landmarks = {}
        visibility = {}
        
        if results.pose_landmarks and len(results.pose_landmarks) > 0:
            pose = results.pose_landmarks[0]
            for idx, name in LANDMARK_NAMES.items():
                if idx < len(pose):
                    lm = pose[idx]
                    landmarks[name] = (lm.x, lm.y, lm.z)
                    visibility[name] = lm.visibility
        
        return landmarks, visibility
    
    def close(self):
        """Clean up detector."""
        if hasattr(self, 'detector'):
            self.detector.close()

class BallDetector:
    """YOLO-based ball detection."""
    
    def __init__(self):
        try:
            from ultralytics import YOLO
            self.model = YOLO('yolov8n.pt')
            self.enabled = True
            print("✓ YOLOv8 loaded for ball tracking")
        except:
            self.model = None
            self.enabled = False
            print("⚠️  YOLOv8 not available - ball tracking disabled")
    
    def detect(self, frame: np.ndarray, wrist_pos: Optional[Tuple[int, int]] = None) -> Optional[Tuple[int, int, int]]:
        """Returns (center_x, center_y, radius) or None."""
        if not self.enabled:
            return None
        
        results = self.model(frame, verbose=False, classes=[32], conf=0.05)
        
        best = None
        best_score = 0
        
        for result in results:
            if result.boxes is None:
                continue
            for i in range(len(result.boxes)):
                conf = float(result.boxes.conf[i])
                x1, y1, x2, y2 = result.boxes.xyxy[i].tolist()
                cx, cy = int((x1+x2)/2), int((y1+y2)/2)
                radius = int(max(x2-x1, y2-y1)/2)
                
                score = conf * 100
                if wrist_pos:
                    dist = np.sqrt((cx - wrist_pos[0])**2 + (cy - wrist_pos[1])**2)
                    if dist < 150:
                        score += 80 * (1 - dist/150)
                    elif dist > 300 and conf < 0.25:
                        continue
                
                if score > best_score:
                    best_score = score
                    best = (cx, cy, radius)
        
        return best

# ============================================================================
# Shot Detector
# ============================================================================

class LiveShotDetector:
    """
    Detects shots using release-backward approach.
    
    Logic:
    1. Detect RELEASE: elbow > 155° AND wrist above shoulder
    2. Look BACKWARD to find LOAD: minimum elbow angle
    3. Capture more frames between load and release (the actual shooting motion)
    """
    
    def __init__(self, shooting_side: str = "right"):
        self.side = shooting_side
        
        # Buffers
        self.frames_buffer = []
        self.landmarks_buffer = []
        self.elbow_angles = []
        self.wrist_heights = []
        self.max_buffer = 180
        
        # Detection state
        self.stability_count = 0
        self.STABILITY_REQUIRED = 8
        
        # Thresholds
        self.RELEASE_ANGLE = 155  # Triggers shot detection
        self.MIN_SHOT_FRAMES = 10
        
        # Cooldown
        self.last_shot_frame = -100
        self.COOLDOWN_FRAMES = 45
    
    def update(self, frame: np.ndarray, landmarks: Dict, visibility: Dict) -> Optional[ShotEvent]:
        """Process frame and return ShotEvent if shot detected."""
        
        # Extract key points
        shoulder = landmarks.get(f"{self.side}_shoulder")
        elbow = landmarks.get(f"{self.side}_elbow")
        wrist = landmarks.get(f"{self.side}_wrist")
        
        # Calculate metrics
        elbow_angle = None
        wrist_y = None
        wrist_above_shoulder = False
        
        if all([shoulder, elbow, wrist]):
            elbow_angle = self._calculate_angle(shoulder, elbow, wrist)
            wrist_y = wrist[1]
            wrist_above_shoulder = wrist[1] < shoulder[1]
            
            vis_ok = all(visibility.get(f"{self.side}_{j}", 0) > 0.5 
                        for j in ["shoulder", "elbow", "wrist"])
            if vis_ok:
                self.stability_count += 1
            else:
                self.stability_count = 0
        else:
            self.stability_count = 0
        
        # Store in buffers
        self.frames_buffer.append(frame.copy())
        self.landmarks_buffer.append(landmarks.copy() if landmarks else {})
        self.elbow_angles.append(elbow_angle)
        self.wrist_heights.append(wrist_y)
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
            shot = self._create_shot_from_release(current_idx)
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
    
    def _create_shot_from_release(self, release_idx: int) -> Optional[ShotEvent]:
        """
        Work backward from release to find load and create shot event.
        
        Frame distribution - 7 frames total:
        - Stance: 5 frames before load
        - Load: minimum elbow angle (deepest bend)
        - Mid1-Mid4: 4 equidistant frames between load and release
        - Release: trigger frame (155°+)
        - FollowThrough: 5 frames after release
        """
        # Search backward for LOAD (minimum elbow angle)
        search_start = max(0, release_idx - 60)
        
        load_idx = release_idx
        min_angle = float('inf')
        
        for i in range(search_start, release_idx):
            if self.elbow_angles[i] and self.elbow_angles[i] < min_angle:
                min_angle = self.elbow_angles[i]
                load_idx = i
        
        # Validate minimum distance
        shot_duration = release_idx - load_idx
        if shot_duration < self.MIN_SHOT_FRAMES:
            return None
        
        # Calculate 4 equidistant frames between load and release
        # Positions: 20%, 40%, 60%, 80% of the way from load to release
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
        
        # Build frames list (8 frames total for more coverage)
        frames = [
            ("1_Stance", self.frames_buffer[stance_idx]),
            ("2_Load", self.frames_buffer[load_idx]),
            ("3_Mid1", self.frames_buffer[mid1_idx]),
            ("4_Mid2", self.frames_buffer[mid2_idx]),
            ("5_Mid3", self.frames_buffer[mid3_idx]),
            ("6_Mid4", self.frames_buffer[mid4_idx]),
            ("7_Release", self.frames_buffer[release_idx]),
            ("8_FollowThrough", self.frames_buffer[followthrough_idx]),
        ]
        
        # Debug output
        release_angle = self.elbow_angles[release_idx] if release_idx < len(self.elbow_angles) else 0
        
        print(f"   Frames: stance={stance_idx}, load={load_idx}, mids=[{mid1_idx},{mid2_idx},{mid3_idx},{mid4_idx}], release={release_idx}, follow={followthrough_idx}")
        print(f"   Angles: load={min_angle:.0f}°, release={release_angle:.0f}°")
        print(f"   Shot duration: {shot_duration} frames")
        
        # Calculate metrics
        load_landmarks = self.landmarks_buffer[load_idx]
        release_landmarks = self.landmarks_buffer[release_idx]
        
        knee_bend = self._calculate_knee_bend(load_landmarks)
        wrist_height = self._calculate_wrist_height(release_landmarks)
        
        return ShotEvent(
            shot_number=0,
            timestamp=time.time(),
            frames=frames,
            elbow_angle_load=min_angle,
            elbow_angle_release=release_angle or 170,
            wrist_height_release=wrist_height,
            knee_bend_load=knee_bend
        )
    
    def _calculate_knee_bend(self, landmarks: Dict) -> float:
        """Calculate knee bend angle."""
        hip = landmarks.get(f"{self.side}_hip")
        knee = landmarks.get(f"{self.side}_knee")
        ankle = landmarks.get(f"{self.side}_ankle")
        
        if not all([hip, knee, ankle]):
            return 0.0
        
        return self._calculate_angle(hip, knee, ankle)
    
    def _calculate_wrist_height(self, landmarks: Dict) -> float:
        """Calculate normalized wrist height (relative to body)."""
        wrist = landmarks.get(f"{self.side}_wrist")
        hip = landmarks.get(f"{self.side}_hip")
        shoulder = landmarks.get(f"{self.side}_shoulder")
        
        if not all([wrist, hip, shoulder]):
            return 0.0
        
        body_height = abs(shoulder[1] - hip[1])
        if body_height < 0.01:
            return 0.0
        
        wrist_from_hip = hip[1] - wrist[1]
        return wrist_from_hip / body_height
    
    def _trim_buffer(self):
        """Keep buffer at max size."""
        while len(self.frames_buffer) > self.max_buffer:
            self.frames_buffer.pop(0)
            self.landmarks_buffer.pop(0)
            self.elbow_angles.pop(0)
            self.wrist_heights.pop(0)
            if self.last_shot_frame > 0:
                self.last_shot_frame -= 1
    
    def get_current_angle(self) -> Optional[float]:
        """Get most recent elbow angle."""
        if self.elbow_angles and self.elbow_angles[-1]:
            return self.elbow_angles[-1]
        return None

# ============================================================================
# Visualization
# ============================================================================

class LiveVisualizer:
    """Draws overlays on live video."""
    
    POSE_CONNECTIONS = [
        ("left_shoulder", "right_shoulder"),
        ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
        ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
        ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"),
        ("left_hip", "right_hip"),
        ("left_hip", "left_knee"), ("left_knee", "left_ankle"),
        ("right_hip", "right_knee"), ("right_knee", "right_ankle"),
    ]
    
    def __init__(self, shooting_side: str = "right"):
        self.side = shooting_side
    
    def draw(self, frame: np.ndarray, landmarks: Dict, 
             ball_pos: Optional[Tuple[int, int, int]],
             elbow_angle: Optional[float],
             state: LiveState) -> np.ndarray:
        """Draw all overlays on frame."""
        
        h, w = frame.shape[:2]
        
        # Draw skeleton
        self._draw_skeleton(frame, landmarks, w, h)
        
        # Draw ball
        if ball_pos:
            cx, cy, r = ball_pos
            cv2.circle(frame, (cx, cy), r, (0, 255, 255), 3)
        
        # Draw elbow angle
        if elbow_angle:
            self._draw_elbow_angle(frame, landmarks, elbow_angle, w, h)
        
        # Draw stats (top-left)
        self._draw_stats(frame, state, elbow_angle)
        
        # Draw feedback (bottom)
        if state.current_feedback and time.time() < state.feedback_display_until:
            self._draw_feedback(frame, state.current_feedback, w, h)
        
        return frame
    
    def _draw_skeleton(self, frame, landmarks, w, h):
        """Draw pose skeleton."""
        # Draw connections
        for start, end in self.POSE_CONNECTIONS:
            p1 = landmarks.get(start)
            p2 = landmarks.get(end)
            if p1 and p2:
                pt1 = (int(p1[0] * w), int(p1[1] * h))
                pt2 = (int(p2[0] * w), int(p2[1] * h))
                
                # Highlight shooting arm
                if self.side in start or self.side in end:
                    if "shoulder" in start or "elbow" in start or "wrist" in start:
                        cv2.line(frame, pt1, pt2, (0, 165, 255), 3)
                        continue
                
                cv2.line(frame, pt1, pt2, (0, 255, 0), 2)
        
        # Draw joints
        for name, pos in landmarks.items():
            pt = (int(pos[0] * w), int(pos[1] * h))
            cv2.circle(frame, pt, 5, (255, 255, 255), -1)
    
    def _draw_elbow_angle(self, frame, landmarks, angle, w, h):
        """Draw elbow angle arc and value."""
        elbow = landmarks.get(f"{self.side}_elbow")
        if not elbow:
            return
        
        pt = (int(elbow[0] * w), int(elbow[1] * h))
        
        # Color based on angle
        if angle < 100:
            color = (0, 255, 255)  # Yellow - loaded
        elif angle > 150:
            color = (0, 255, 0)  # Green - extended
        else:
            color = (255, 165, 0)  # Orange - mid
        
        cv2.putText(frame, f"{angle:.0f}", (pt[0] + 15, pt[1] - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 3)
        cv2.putText(frame, f"{angle:.0f}", (pt[0] + 15, pt[1] - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    
    def _draw_stats(self, frame, state: LiveState, elbow_angle: Optional[float]):
        """Draw shot statistics."""
        y = 40
        
        # Shot counter with flash effect
        made_color = (255, 255, 255)
        missed_color = (255, 255, 255)
        
        if time.time() < state.result_flash_until:
            if state.last_shot_result:
                made_color = (0, 255, 0)  # Green flash
            else:
                missed_color = (0, 0, 255)  # Red flash
        
        # Made
        text = f"Made: {state.shots_made}"
        cv2.putText(frame, text, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 4)
        cv2.putText(frame, text, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 1.0, made_color, 2)
        
        # Missed
        text = f"Missed: {state.shots_missed}"
        cv2.putText(frame, text, (20, y + 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 4)
        cv2.putText(frame, text, (20, y + 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, missed_color, 2)
        
        # Elbow angle indicator
        if elbow_angle:
            text = f"Elbow: {elbow_angle:.0f}"
            cv2.putText(frame, text, (20, y + 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 3)
            cv2.putText(frame, text, (20, y + 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
    
    def _draw_feedback(self, frame, feedback: str, w: int, h: int):
        """Draw feedback text at bottom."""
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.9
        thickness = 2
        
        # Word wrap
        words = feedback.split()
        lines = []
        line = ""
        for word in words:
            test = f"{line} {word}".strip()
            if cv2.getTextSize(test, font, scale, thickness)[0][0] < w - 40:
                line = test
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)
        
        # Draw background
        total_height = len(lines) * 40 + 20
        cv2.rectangle(frame, (0, h - total_height), (w, h), (0, 0, 0), -1)
        cv2.rectangle(frame, (0, h - total_height), (w, h), (50, 50, 50), 2)
        
        # Draw text
        for i, line in enumerate(lines):
            text_w = cv2.getTextSize(line, font, scale, thickness)[0][0]
            x = (w - text_w) // 2
            y = h - total_height + 35 + i * 40
            cv2.putText(frame, line, (x, y), font, scale, (255, 255, 255), thickness)

# ============================================================================
# Onboarding
# ============================================================================

def run_onboarding(db: 'FormCheckDB' = None) -> Tuple[PlayerProfile, Optional[int]]:
    """Interactive onboarding to get player context."""
    print("\n" + "━"*60)
    print("  FORMCHECK - Setup")
    print("━"*60)
    
    player_id = None
    
    # Check for existing players if database available
    if db:
        players = db.list_players()
        if players:
            print("\n📋 Existing players:")
            for p in players[:5]:
                pct = (p.total_makes / p.total_shots * 100) if p.total_shots > 0 else 0
                height_str = ""
                if p.height_inches:
                    feet = p.height_inches // 12
                    inches = p.height_inches % 12
                    height_str = f" ({feet}'{inches}\")"
                print(f"   [{p.id}] {p.name}{height_str} - {p.total_shots} shots ({pct:.0f}%)")
            
            print("\nSelect player number, or [N]ew player, or [S]kip:")
            choice = input("> ").strip().lower()
            
            if choice.isdigit():
                player_id = int(choice)
                player = db.get_player(player_id)
                if player:
                    print(f"\n✓ Welcome back, {player.name}!")
                    profile = PlayerProfile(
                        skill_level=player.skill_level,
                        working_on=player.working_on or "",
                        limitations=player.limitations or "",
                        height_inches=player.height_inches
                    )
                    
                    # Ask if they want to update focus
                    print(f"\nLast focus: {player.working_on or 'None set'}")
                    print("Working on something different today? (Enter to keep, or type new focus)")
                    new_focus = input("> ").strip()
                    if new_focus:
                        profile.working_on = new_focus
                    
                    return profile, player_id
            elif choice == 's' or choice == 'skip':
                player = db.get_or_create_default_player()
                return PlayerProfile(), player.id
    
    # New player flow
    print("\n👤 Let's set up your profile")
    
    # Name
    print("\nYour name (or press Enter for 'Player 1'):")
    name = input("> ").strip() or "Player 1"
    
    # Height - important for personalized advice
    print("\nYour height? (e.g., '5 10', '5'10', or '70' for inches)")
    print("  This helps us give advice tailored to your body type")
    height_input = input("> ").strip()
    height_inches = None
    if height_input and NBA_ANALYSIS_AVAILABLE:
        height_inches = parse_height(height_input)
        if height_inches:
            feet = height_inches // 12
            inches = height_inches % 12
            height_cat = get_height_category(height_inches)
            print(f"  ✓ Got it: {feet}'{inches}\" - {height_cat['category']} category")
    
    # Skill level
    print("\nSkill level? [B]eginner / [I]ntermediate / [A]dvanced")
    print("  B = New to basketball or working on fundamentals")
    print("  I = Comfortable shooting, working on consistency") 
    print("  A = Experienced player refining technique")
    
    level_input = input("> ").strip().lower()
    skill_map = {
        'b': 'beginner', 'beginner': 'beginner',
        'i': 'intermediate', 'intermediate': 'intermediate', '': 'intermediate',
        'a': 'advanced', 'advanced': 'advanced',
    }
    skill_level = skill_map.get(level_input, 'intermediate')
    
    # What they're working on
    print("\nWhat are you working on? (or press Enter to skip)")
    print("  Examples: 'more arc', 'consistency', 'quicker release', 'range'")
    working_on = input("> ").strip()
    
    # Limitations
    print("\nAny injuries or limitations? (or press Enter to skip)")
    limitations = input("> ").strip()
    
    # Create player in database
    if db:
        player_id = db.create_player(
            name=name,
            skill_level=skill_level,
            working_on=working_on,
            limitations=limitations,
            height_inches=height_inches
        )
        print(f"\n✓ Profile created! (ID: {player_id})")
    
    profile = PlayerProfile(
        skill_level=skill_level,
        working_on=working_on,
        limitations=limitations,
        height_inches=height_inches
    )
    
    print("\n" + "━"*60)
    print(f"  ✓ Ready! Coaching as: {skill_level.capitalize()}")
    if height_inches:
        print(f"  ✓ Height: {height_inches // 12}'{height_inches % 12}\"")
    if working_on:
        print(f"  ✓ Focus area: {working_on}")
    print("━"*60)
    
    return profile, player_id


# ============================================================================
# Main Application
# ============================================================================

class LiveAnalyzer:
    """Main application class."""
    
    def __init__(self, source=0, shooting_side="right", skip_onboarding=False,
                 player_id: int = None, debug_frames: bool = False, auto_show: bool = True):
        self.source = source
        self.side = shooting_side
        self.debug_frames = debug_frames  # Save frames sent to Gemini
        self.auto_show_analysis = auto_show  # Auto-show annotated shot after each analysis
        
        # Initialize components
        print("\n" + "="*60)
        print("  FORMCHECK - AI Basketball Coach")
        print("="*60 + "\n")
        
        # Initialize database
        self.db = None
        self.player_id = player_id
        self.session_id = None
        
        if DB_AVAILABLE:
            self.db = FormCheckDB()
        
        # Get player profile
        if skip_onboarding:
            self.player_profile = PlayerProfile()
            if self.db:
                player = self.db.get_or_create_default_player()
                self.player_id = player.id
        else:
            self.player_profile, self.player_id = run_onboarding(self.db)
        
        # Start a new session in DB
        if self.db and self.player_id:
            self.session_id = self.db.create_session(
                self.player_id,
                focus_area=self.player_profile.working_on
            )
            print(f"📝 Session #{self.session_id} started")
        
        self.pose = PoseDetector()
        self.ball = BallDetector()
        self.shot_detector = LiveShotDetector(shooting_side)
        self.visualizer = LiveVisualizer(shooting_side)
        self.gemini = GeminiClient(
            GEMINI_API_KEY, 
            self.player_profile,
            db=self.db,
            player_id=self.player_id
        )
        
        # Initialize rim detection and make/miss tracking
        self.rim_detector = None
        self.make_miss_tracker = None
        if NBA_ANALYSIS_AVAILABLE:
            self.rim_detector = RimDetector()
            self.make_miss_tracker = MakeMissTracker(self.rim_detector)
            print("✓ Rim detection enabled for make/miss tracking")
        
        self.state = LiveState()
        self.frame_count = 0
        
        print(f"\nShooting side: {shooting_side.upper()}")
        print("Press 'q' to quit, 's' to switch hands, 'v' to view last shot, 'p' to save shot")
        print("      Click on the video window first, then press keys\n")
    
    def on_shot_analyzed(self, shot: ShotEvent):
        """Callback when Gemini returns analysis."""
        # Update make/miss counts
        if shot.made is not None:
            if shot.made:
                self.state.shots_made += 1
                self.state.last_shot_result = True
            else:
                self.state.shots_missed += 1
                self.state.last_shot_result = False
            self.state.result_flash_until = time.time() + 1.0
        
        # Track metrics for pattern analysis
        self.state.shot_metrics.append(ShotMetrics(
            shot_number=shot.shot_number,
            made=shot.made,
            elbow_load=shot.elbow_angle_load,
            elbow_release=shot.elbow_angle_release,
            wrist_height=shot.wrist_height_release,
            knee_bend=shot.knee_bend_load
        ))
        
        # Build history record
        shot_record = {
            "number": shot.shot_number,
            "made": shot.made,
            "miss_type": shot.miss_type,
            "form_rating": shot.form_rating,
            "feedback": shot.feedback,
            "key_issue": shot.key_issue,
            "did_well": shot.did_well,
            "quick_cue": shot.quick_cue,
            "looks_like": shot.looks_like
        }
        self.state.shot_history.append(shot_record)
        
        # Record to database
        if self.db and self.session_id:
            self.db.record_shot(self.session_id, {
                "shot_number": shot.shot_number,
                "made": shot.made,
                "miss_type": shot.miss_type,
                "form_rating": shot.form_rating,
                "elbow_angle_load": shot.elbow_angle_load,
                "elbow_angle_release": shot.elbow_angle_release,
                "wrist_height_release": shot.wrist_height_release,
                "knee_bend_load": shot.knee_bend_load,
                "feedback": shot.feedback,
                "key_issue": shot.key_issue,
                "quick_cue": shot.quick_cue,
                "did_well": shot.did_well,
                "looks_like": shot.looks_like
            })
        
        if shot.feedback:
            self.state.current_feedback = shot.feedback
            self.state.feedback_display_until = time.time() + 5.0
            self.state.all_feedback_given.append(shot.feedback)
        
        # Generate annotated visual feedback
        if VISUAL_FEEDBACK_AVAILABLE and shot.frames:
            self._generate_shot_visualization(shot)
        
        # Print results with enhanced formatting
        if shot.made:
            result_str = "✅ MADE"
        elif shot.made is False:
            miss_desc = f"({shot.miss_type})" if shot.miss_type else ""
            result_str = f"❌ MISSED {miss_desc}"
        else:
            result_str = "???"
        
        rating_str = f"[Form: {shot.form_rating}/10]" if shot.form_rating else ""
        pattern_str = f"(looks like your {shot.looks_like})" if shot.looks_like and shot.looks_like != "new" else ""
        
        print(f"\n  Shot {shot.shot_number}: {result_str} {rating_str} {pattern_str}")
        print(f"  💬 {shot.feedback}")
        
        if shot.quick_cue:
            print(f"  🎯 Cue: \"{shot.quick_cue}\"")
        
        if shot.did_well:
            print(f"  ✓ Good: {', '.join(shot.did_well[:2])}")
        
        if shot.key_issue and shot.key_issue.lower() != "none":
            print(f"  → Fix: {shot.key_issue}")
        
        print("  📸 Press 'v' to view annotated shot breakdown")
        
        # Auto-show the annotated shot window if enabled
        if hasattr(self, 'auto_show_analysis') and self.auto_show_analysis:
            if self.state.last_shot_annotated is not None:
                self.state.show_last_shot = True
        
        print()
    
    def _generate_shot_visualization(self, shot: ShotEvent):
        """Generate annotated visualization of the shot."""
        try:
            # Store frames and create annotated version
            self.state.last_shot_frames = shot.frames.copy() if shot.frames else []
            
            # Get metrics dict
            metrics = {
                "elbow_load": shot.elbow_angle_load,
                "elbow_release": shot.elbow_angle_release,
                "wrist_height": shot.wrist_height_release,
                "knee_bend": shot.knee_bend_load,
                "form_rating": shot.form_rating,
                "made": shot.made,
                "miss_type": shot.miss_type
            }
            self.state.last_shot_metrics = metrics
            
            # Build issues list from feedback
            issues = []
            if shot.key_issue and shot.key_issue.lower() != "none":
                # Determine which body part
                issue_lower = shot.key_issue.lower()
                if "elbow" in issue_lower:
                    body_part = "elbow"
                elif "release" in issue_lower or "wrist" in issue_lower:
                    body_part = "release"
                elif "knee" in issue_lower or "leg" in issue_lower:
                    body_part = "knee"
                else:
                    body_part = "elbow"  # Default
                
                severity = "error" if not shot.made else "warning"
                issues.append({
                    "body_part": body_part,
                    "message": shot.key_issue[:30],  # Truncate for display
                    "severity": severity
                })
            
            self.state.last_shot_issues = issues
            
            # Create annotated frame from release frame
            if shot.frames and len(shot.frames) > 4:
                # Get release frame (index 4-5 in 7-frame sequence)
                label, release_frame = shot.frames[5] if len(shot.frames) > 5 else shot.frames[-1]
                
                # Get landmarks from shot detector's buffer if available
                # For now, we'll run pose detection on the release frame
                landmarks, _ = self.pose.detect(release_frame)
                
                if landmarks:
                    annotator = FrameAnnotator()
                    
                    if issues:
                        # Create highlighted version
                        comp = ComparisonGenerator()
                        annotated = comp.create_improvement_highlight(
                            release_frame, landmarks, metrics, issues
                        )
                    else:
                        # Create standard annotated version
                        annotated = annotator.annotate_shot_frame(
                            release_frame, landmarks, metrics, "release"
                        )
                    
                    # Add shot result header
                    h, w = annotated.shape[:2]
                    header_h = 50
                    header = np.zeros((header_h, w, 3), dtype=np.uint8)
                    
                    if shot.made:
                        cv2.rectangle(header, (0, 0), (w, header_h), (0, 100, 0), -1)
                        result_text = f"SHOT #{shot.shot_number} - MADE"
                    else:
                        cv2.rectangle(header, (0, 0), (w, header_h), (0, 0, 100), -1)
                        miss_str = f" ({shot.miss_type})" if shot.miss_type else ""
                        result_text = f"SHOT #{shot.shot_number} - MISSED{miss_str}"
                    
                    cv2.putText(header, result_text, (15, 35),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
                    
                    if shot.form_rating:
                        rating_text = f"Form: {shot.form_rating}/10"
                        cv2.putText(header, rating_text, (w - 150, 35),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    
                    annotated = np.vstack([header, annotated])
                    
                    # Add feedback footer
                    if shot.feedback:
                        footer_h = 60
                        footer = np.zeros((footer_h, w, 3), dtype=np.uint8)
                        footer[:] = (30, 30, 30)
                        
                        # Truncate feedback if needed
                        feedback_text = shot.feedback[:80] + "..." if len(shot.feedback) > 80 else shot.feedback
                        cv2.putText(footer, feedback_text, (15, 35),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                        
                        if shot.quick_cue:
                            cue_text = f'Cue: "{shot.quick_cue}"'
                            cv2.putText(footer, cue_text, (w - 250, 35),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)
                        
                        annotated = np.vstack([annotated, footer])
                    
                    self.state.last_shot_annotated = annotated
                    
        except Exception as e:
            print(f"Warning: Could not generate shot visualization: {e}")
    
    def run(self):
        """Main loop."""
        cap = cv2.VideoCapture(self.source)
        
        if not cap.isOpened():
            print(f"Error: Could not open video source: {self.source}")
            return
        
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_time = 1.0 / fps
        
        print(f"Video source opened: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} @ {fps:.0f}fps")
        print("Running...\n")
        
        while True:
            start_time = time.time()
            self.frame_count += 1
            
            ret, frame = cap.read()
            if not ret:
                if isinstance(self.source, str):
                    # Video file ended
                    break
                continue
            
            # Detect pose
            landmarks, visibility = self.pose.detect(frame)
            
            # Detect ball
            wrist = landmarks.get(f"{self.side}_wrist")
            wrist_px = None
            if wrist:
                h, w = frame.shape[:2]
                wrist_px = (int(wrist[0] * w), int(wrist[1] * h))
            ball_pos = self.ball.detect(frame, wrist_px)
            
            # Detect rim (for make/miss tracking)
            rim_bbox = None
            if self.rim_detector:
                rim_bbox = self.rim_detector.detect(frame)
                
                # Track ball trajectory for make/miss
                if ball_pos and self.make_miss_tracker:
                    ball_center = (ball_pos[0], ball_pos[1])
                    make_miss_result = self.make_miss_tracker.update(ball_center, self.frame_count)
                    
                    if make_miss_result:
                        # Store result for next shot analysis
                        self._last_make_miss = make_miss_result
            
            # Detect shot
            shot_event = self.shot_detector.update(frame, landmarks, visibility)
            if shot_event:
                self.state.total_shots += 1
                shot_event.shot_number = self.state.total_shots
                
                # Perform local biomechanics analysis (research-based, not NBA player comparisons)
                local_analysis = None
                print(f"\n🏀 Shot #{shot_event.shot_number} detected!")
                print(f"   Elbow: {shot_event.elbow_angle_load:.0f}° → {shot_event.elbow_angle_release:.0f}°")
                print(f"   Wrist height: {shot_event.wrist_height_release:.2f} | Knee bend: {shot_event.knee_bend_load:.0f}°")
                
                if BIOMECHANICS_AVAILABLE:
                    # Get height-based recommendations
                    height_profile = None
                    if self.player_profile.height_inches:
                        height_profile = get_height_profile(self.player_profile.height_inches)
                    
                    # Check vs research benchmarks
                    vs_research = {}
                    elbow_load = shot_event.elbow_angle_load
                    if ELBOW_ANGLE_LOAD.min_val <= elbow_load <= ELBOW_ANGLE_LOAD.max_val:
                        vs_research["elbow"] = "optimal"
                    elif elbow_load < ELBOW_ANGLE_LOAD.min_val:
                        vs_research["elbow"] = "below_optimal"
                    else:
                        vs_research["elbow"] = "above_optimal"
                    
                    local_analysis = {
                        "height_profile": {
                            "category": height_profile.category if height_profile else "N/A",
                            "release_speed": height_profile.release_speed if height_profile else "moderate",
                            "arc_emphasis": height_profile.arc_emphasis if height_profile else "standard",
                            "key_principles": height_profile.key_principles if height_profile else [],
                        } if height_profile else None,
                        "vs_research": vs_research
                    }
                    
                    # Show research-based feedback
                    if vs_research.get("elbow") == "optimal":
                        print(f"   ✓ Elbow angle within research optimal range (85-95°)")
                    elif vs_research.get("elbow") == "below_optimal":
                        print(f"   📊 Elbow more bent than research optimal (85-95°)")
                
                print(f"   Sending {len(shot_event.frames)} frames to Gemini...")
                
                # Save frames if debug mode enabled
                if self.debug_frames and shot_event.frames:
                    debug_dir = Path("debug_frames")
                    debug_dir.mkdir(exist_ok=True)
                    shot_dir = debug_dir / f"shot_{shot_event.shot_number}"
                    shot_dir.mkdir(exist_ok=True)
                    
                    print(f"   💾 Saving {len(shot_event.frames)} frames to {shot_dir}/")
                    for i, (label, frame_img) in enumerate(shot_event.frames):
                        filename = shot_dir / f"{i}_{label.replace(' ', '_')}.jpg"
                        cv2.imwrite(str(filename), frame_img)
                    print(f"   ✓ Frames saved for debugging")
                
                # Send to Gemini for analysis (pass state and local analysis)
                self.gemini.analyze_shot_async(
                    shot_event, 
                    self.state, 
                    self.on_shot_analyzed,
                    local_analysis=local_analysis
                )
            
            # Get current elbow angle
            elbow_angle = self.shot_detector.get_current_angle()
            
            # Draw visualization
            frame = self.visualizer.draw(frame, landmarks, ball_pos, elbow_angle, self.state)
            
            # Draw rim if detected
            if rim_bbox:
                x, y, w, h = rim_bbox
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 165, 255), 2)
                cv2.putText(frame, "RIM", (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)
            
            # Show last shot annotated view if toggled
            if self.state.show_last_shot and self.state.last_shot_annotated is not None:
                # Show annotated shot in separate window
                cv2.imshow('Last Shot Analysis', self.state.last_shot_annotated)
            
            # Display
            cv2.imshow('FormCheck Live', frame)
            
            # Handle keyboard
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                # Switch hands
                self.side = "left" if self.side == "right" else "right"
                self.shot_detector = LiveShotDetector(self.side)
                self.visualizer = LiveVisualizer(self.side)
                print(f"Switched to {self.side.upper()} hand")
            elif key == ord('v'):
                # Toggle last shot view
                self.state.show_last_shot = not self.state.show_last_shot
                if self.state.show_last_shot:
                    if self.state.last_shot_annotated is not None:
                        print("📸 Showing last shot analysis (press 'v' to hide)")
                    else:
                        print("No shot analyzed yet")
                        self.state.show_last_shot = False
                else:
                    cv2.destroyWindow('Last Shot Analysis')
                    print("Hiding shot analysis")
            elif key == ord('p'):
                # Save annotated shot as PNG
                if self.state.last_shot_annotated is not None:
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    filename = f"shot_{self.state.total_shots}_{timestamp}.png"
                    cv2.imwrite(filename, self.state.last_shot_annotated)
                    print(f"💾 Saved: {filename}")
                else:
                    print("No shot to save yet")
            
            # Maintain frame rate
            elapsed = time.time() - start_time
            if elapsed < frame_time:
                time.sleep(frame_time - elapsed)
        
        cap.release()
        cv2.destroyAllWindows()
        self.pose.close()
        
        # Generate and print session summary
        self._print_session_summary()
    
    def _print_session_summary(self):
        """Generate and print comprehensive session summary."""
        print("\n" + "="*60)
        print("  SESSION COMPLETE")
        print("="*60)
        
        # Basic stats
        print(f"\n📊 STATS")
        print(f"   Total shots: {self.state.total_shots}")
        print(f"   Made: {self.state.shots_made}")
        print(f"   Missed: {self.state.shots_missed}")
        if self.state.total_shots > 0:
            pct = 100 * self.state.shots_made / self.state.total_shots
            print(f"   Shooting %: {pct:.1f}%")
        
        # Form ratings
        ratings = [h.get('form_rating') for h in self.state.shot_history if h.get('form_rating')]
        if ratings:
            avg_rating = sum(ratings) / len(ratings)
            print(f"   Avg Form Rating: {avg_rating:.1f}/10")
        
        # Miss patterns
        miss_types = [h.get('miss_type') for h in self.state.shot_history if h.get('miss_type')]
        if miss_types:
            miss_counts = Counter(miss_types)
            most_common = miss_counts.most_common(1)[0]
            print(f"   Most common miss: {most_common[0]} ({most_common[1]}x)")
        
        # Show patterns discovered
        patterns = self.state.get_make_miss_patterns()
        if patterns["makes"] and patterns["misses"]:
            print(f"\n📈 YOUR PATTERNS")
            m, x = patterns["makes"], patterns["misses"]
            print(f"   Makes:  elbow {m['elbow_load']['avg']:.0f}°, release {m['wrist_height']['avg']:.2f}")
            print(f"   Misses: elbow {x['elbow_load']['avg']:.0f}°, release {x['wrist_height']['avg']:.2f}")
            
            # Key difference
            elbow_diff = m['elbow_load']['avg'] - x['elbow_load']['avg']
            if abs(elbow_diff) > 3:
                print(f"   💡 Your elbow is {abs(elbow_diff):.0f}° {'higher' if elbow_diff > 0 else 'lower'} when you make shots")
        
        # Quick cues that were given
        cues = [h.get('quick_cue') for h in self.state.shot_history if h.get('quick_cue')]
        if cues:
            print(f"\n🎯 CUES TO REMEMBER")
            # Show unique cues
            unique_cues = list(dict.fromkeys(cues))[:3]
            for cue in unique_cues:
                print(f"   • \"{cue}\"")
        
        # Get AI summary if available
        grade = None
        summary_text = None
        
        if self.gemini.enabled and self.state.total_shots > 0:
            print("\n⏳ Generating AI summary...")
            summary = self.gemini.generate_session_summary(self.state)
            
            grade = summary.get('grade', 'N/A')
            print(f"\n🎯 GRADE: {grade}")
            if summary.get('grade_explanation'):
                print(f"   {summary['grade_explanation']}")
            
            if summary.get('summary'):
                summary_text = summary['summary']
                print(f"\n📝 SUMMARY")
                print(f"   {summary_text}")
            
            if summary.get('top_strength'):
                print(f"\n💪 TOP STRENGTH")
                print(f"   {summary['top_strength']}")
            
            if summary.get('strengths'):
                print(f"\n✅ OTHER STRENGTHS")
                for s in summary['strengths'][:3]:
                    print(f"   • {s}")
            
            if summary.get('main_focus'):
                print(f"\n🎯 MAIN FOCUS AREA")
                print(f"   {summary['main_focus']}")
            
            if summary.get('other_areas'):
                print(f"\n📋 ALSO WORK ON")
                for a in summary['other_areas'][:2]:
                    print(f"   • {a}")
            
            if summary.get('drill'):
                print(f"\n🏋️ RECOMMENDED DRILL")
                print(f"   {summary['drill']}")
            
            if summary.get('encouragement'):
                print(f"\n🌟 {summary['encouragement']}")
        
        # Save session to database
        if self.db and self.session_id:
            self.db.end_session(self.session_id, grade=grade, summary=summary_text)
            self.db.update_player_stats(self.player_id)
            print(f"\n💾 Session saved to database")
            
            # Show historical comparison if available
            if self.player_id:
                hist_patterns = self.db.get_player_patterns(self.player_id)
                if hist_patterns.get("recent_sessions") and len(hist_patterns["recent_sessions"]) > 1:
                    print(f"\n📊 PROGRESS")
                    sessions = hist_patterns["recent_sessions"]
                    if len(sessions) >= 2:
                        current_pct = sessions[0]["pct"]
                        prev_pct = sessions[1]["pct"]
                        diff = current_pct - prev_pct
                        trend = "↑" if diff > 0 else "↓" if diff < 0 else "→"
                        print(f"   This session: {current_pct:.0f}% | Last session: {prev_pct:.0f}% {trend}")
        
        print("\n" + "="*60 + "\n")

# ============================================================================
# Entry Point
# ============================================================================

def main():
    # Parse arguments
    source = 0  # Default to webcam
    shooting_side = "right"
    skip_onboarding = False
    player_id = None
    debug_frames = False
    auto_show = True
    
    args = sys.argv[1:]
    
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--left":
            shooting_side = "left"
        elif arg == "--right":
            shooting_side = "right"
        elif arg == "--skip-onboarding" or arg == "--skip":
            skip_onboarding = True
        elif arg == "--player" or arg == "-p":
            if i + 1 < len(args):
                player_id = int(args[i + 1])
                i += 1
        elif arg == "--debug":
            debug_frames = True
        elif arg == "--no-auto":
            auto_show = False
        elif arg == "--help" or arg == "-h":
            print("""
FormCheck - AI Basketball Coach

Usage:
    python live_analysis.py [options] [video_file]

Options:
    --left              Left-handed shooting
    --right             Right-handed shooting (default)
    --skip-onboarding   Skip the player profile setup
    --player ID, -p ID  Use existing player profile by ID
    --debug             Save frames sent to Gemini (debug_frames/ folder)
    --no-auto           Don't auto-show annotated shot after analysis
    -h, --help          Show this help message

Keyboard Controls (while video window is in focus):
    v       View/hide annotated shot breakdown
    p       Save annotated shot as PNG
    s       Switch shooting hand
    q       Quit

Database Commands:
    python database.py list-players        List all players
    python database.py player-stats ID     Show player statistics

Examples:
    python live_analysis.py                    # Webcam, right-handed
    python live_analysis.py video.mp4 --left   # Video file, left-handed
    python live_analysis.py --player 1         # Use player ID 1
    python live_analysis.py --skip             # Skip onboarding
    python live_analysis.py --debug video.mp4  # Save frames for debugging

Environment:
    GEMINI_API_KEY      Your Gemini API key for AI feedback

Data Storage:
    ~/.formcheck/formcheck.db    SQLite database for persistent data
""")
            return
        elif not arg.startswith("-"):
            source = arg  # Video file path
        i += 1
    
    # Run analyzer
    analyzer = LiveAnalyzer(source, shooting_side, skip_onboarding, player_id, debug_frames, auto_show)
    analyzer.run()


if __name__ == "__main__":
    main()