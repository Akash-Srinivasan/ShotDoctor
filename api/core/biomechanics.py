#!/usr/bin/env python3
"""
FormCheck - Biomechanics Reference Module

Shooting form guidelines based on published sports science research.
No player-specific data - uses peer-reviewed biomechanics studies.

Research Sources:
- Miller, S. & Bartlett, R. (1996). The relationship between basketball shooting 
  kinematics, distance and playing position. Journal of Sports Sciences.
- Okazaki, V. et al. (2015). A review on the basketball jump shot. 
  Sports Biomechanics.
- Podmenik, N. et al. (2017). The effect of shooting range on basketball 
  jump shot kinematics. Kinesiology.
- Nakano, N. et al. (2020). Optimal release conditions for basketball 
  free throws. Journal of Sports Sciences.

This module provides:
1. Research-backed optimal ranges for shooting mechanics
2. Height-adjusted recommendations
3. Distance-based adjustments (free throw vs 3-point)
4. Self-comparison tools (user's makes vs misses)
"""

from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple
import numpy as np


# =============================================================================
# Research-Based Optimal Ranges
# =============================================================================

@dataclass
class OptimalRange:
    """Optimal range for a metric with research backing."""
    min_val: float
    max_val: float
    ideal: float
    unit: str
    research_note: str


# Entry angle research: 44-47° is optimal for highest make probability
# Source: Nakano et al. (2020), Miller & Bartlett (1996)
ENTRY_ANGLE = OptimalRange(
    min_val=42.0,
    max_val=50.0,
    ideal=45.5,
    unit="°",
    research_note="Research shows 44-47° entry angle maximizes margin for error at the rim"
)

# Release height research: Higher release = harder to block, but diminishing returns
# Source: Okazaki et al. (2015)
RELEASE_HEIGHT = OptimalRange(
    min_val=1.05,  # Normalized: 1.0 = shoulder height
    max_val=1.40,
    ideal=1.20,
    unit="× shoulder",
    research_note="Release point 10-30% above shoulder level is typical for efficient shooters"
)

# Elbow angle at set point (load position)
# Source: Multiple studies show 85-100° is common among accurate shooters
ELBOW_ANGLE_LOAD = OptimalRange(
    min_val=80.0,
    max_val=100.0,
    ideal=90.0,
    unit="°",
    research_note="85-95° elbow angle at set point allows efficient force transfer"
)

# Elbow angle at release
# Source: Full extension (170-180°) correlates with accuracy
ELBOW_ANGLE_RELEASE = OptimalRange(
    min_val=160.0,
    max_val=180.0,
    ideal=170.0,
    unit="°",
    research_note="Near-full elbow extension (165-175°) at release is optimal"
)

# Knee bend at load
# Source: Podmenik et al. (2017) - deeper for longer shots
KNEE_BEND_LOAD = OptimalRange(
    min_val=15.0,
    max_val=45.0,
    ideal=30.0,
    unit="°",
    research_note="20-35° knee bend provides power; increase for longer distances"
)

# Release time (catch to release)
# Source: Okazaki et al. (2015) - elite shooters: 0.4-0.7s
RELEASE_TIME = OptimalRange(
    min_val=0.35,
    max_val=0.80,
    ideal=0.55,
    unit="s",
    research_note="Elite catch-and-shoot: 0.4-0.6s; off-dribble may be longer"
)


# =============================================================================
# Distance-Based Adjustments
# =============================================================================

@dataclass
class DistanceProfile:
    """Shooting adjustments based on distance from basket."""
    name: str
    distance_feet: Tuple[float, float]  # (min, max) range
    
    # Adjustments to base optimal values
    knee_bend_adjustment: float  # Add to base knee bend
    release_height_adjustment: float  # Add to base release height
    arc_adjustment: float  # Add to base entry angle
    
    # Power requirements
    leg_power_emphasis: str  # "low", "medium", "high"
    
    notes: str


DISTANCE_PROFILES = {
    "free_throw": DistanceProfile(
        name="Free Throw",
        distance_feet=(13, 15),
        knee_bend_adjustment=0,
        release_height_adjustment=0,
        arc_adjustment=0,
        leg_power_emphasis="low",
        notes="Rhythm and consistency matter most. No defender, so take your time."
    ),
    
    "paint": DistanceProfile(
        name="Paint / Close Range",
        distance_feet=(0, 8),
        knee_bend_adjustment=-5,  # Less knee bend needed
        release_height_adjustment=0.05,  # Higher release to avoid blocks
        arc_adjustment=3,  # Higher arc for touch
        leg_power_emphasis="low",
        notes="Focus on soft touch and high arc. Quick release to avoid contests."
    ),
    
    "midrange": DistanceProfile(
        name="Mid-Range",
        distance_feet=(8, 20),
        knee_bend_adjustment=5,
        release_height_adjustment=0,
        arc_adjustment=0,
        leg_power_emphasis="medium",
        notes="Balance of touch and power. Consistent mechanics crucial."
    ),
    
    "three_point": DistanceProfile(
        name="Three-Point Line",
        distance_feet=(22, 24),
        knee_bend_adjustment=8,
        release_height_adjustment=-0.03,  # Slightly lower is OK for power
        arc_adjustment=-1,  # Slightly flatter is efficient
        leg_power_emphasis="high",
        notes="Legs generate most of the power. Maintain consistent release point."
    ),
    
    "deep_three": DistanceProfile(
        name="Deep Three / Logo",
        distance_feet=(24, 35),
        knee_bend_adjustment=12,
        release_height_adjustment=-0.05,
        arc_adjustment=-2,
        leg_power_emphasis="high",
        notes="Maximum leg drive. May need to adjust set point lower for power."
    ),
}


def get_distance_profile(distance_feet: float) -> DistanceProfile:
    """Get the appropriate profile for a given distance."""
    for profile in DISTANCE_PROFILES.values():
        min_d, max_d = profile.distance_feet
        if min_d <= distance_feet <= max_d:
            return profile
    return DISTANCE_PROFILES["midrange"]  # Default


# =============================================================================
# Height-Based Adjustments
# =============================================================================

@dataclass
class HeightProfile:
    """Adjustments based on player height."""
    category: str
    height_range_inches: Tuple[int, int]
    
    # Recommendations
    release_speed: str  # "quick", "moderate", "deliberate"
    arc_emphasis: str  # "high", "standard", "can_be_lower"
    release_height_note: str
    
    # Adjustments
    arc_adjustment: float
    release_time_adjustment: float  # Negative = faster
    
    key_principles: List[str]


HEIGHT_PROFILES = {
    "compact": HeightProfile(
        category="Compact (under 5'8\")",
        height_range_inches=(0, 68),
        release_speed="quick",
        arc_emphasis="high",
        release_height_note="Maximize release height within your range",
        arc_adjustment=3,
        release_time_adjustment=-0.1,
        key_principles=[
            "Quick release reduces contest window",
            "Higher arc (48°+) clears defenders",
            "Strong legs compensate for height",
            "Consistent set point is crucial",
        ]
    ),
    
    "average": HeightProfile(
        category="Average (5'8\" - 6'2\")",
        height_range_inches=(68, 74),
        release_speed="moderate",
        arc_emphasis="standard",
        release_height_note="Standard release height works well",
        arc_adjustment=0,
        release_time_adjustment=0,
        key_principles=[
            "Most versatile height range",
            "Can use quick or traditional release",
            "Focus on consistency over speed",
            "Standard 45° arc is efficient",
        ]
    ),
    
    "tall": HeightProfile(
        category="Tall (6'2\" - 6'7\")",
        height_range_inches=(74, 79),
        release_speed="moderate",
        arc_emphasis="standard",
        release_height_note="Use your height - release above defenders",
        arc_adjustment=-1,
        release_time_adjustment=0.05,
        key_principles=[
            "Higher release point is an advantage",
            "Don't rush - use your height",
            "Can shoot over smaller defenders",
            "Efficient arc (44-46°) works well",
        ]
    ),
    
    "very_tall": HeightProfile(
        category="Very Tall (6'7\"+)",
        height_range_inches=(79, 100),
        release_speed="deliberate",
        arc_emphasis="can_be_lower",
        release_height_note="High release lets you shoot over anyone",
        arc_adjustment=-2,
        release_time_adjustment=0.1,
        key_principles=[
            "Maximize height advantage",
            "Release point should be very high",
            "Flatter arc is acceptable (43-45°)",
            "Focus on soft touch",
        ]
    ),
}


def get_height_profile(height_inches: int) -> HeightProfile:
    """Get profile for a given height."""
    for profile in HEIGHT_PROFILES.values():
        min_h, max_h = profile.height_range_inches
        if min_h <= height_inches < max_h:
            return profile
    return HEIGHT_PROFILES["average"]


# =============================================================================
# Self-Comparison Analysis (Core Feature)
# =============================================================================

@dataclass
class FormAnalysis:
    """Analysis of a player's form based on their own data."""
    
    # Optimal values discovered from THEIR makes
    optimal_elbow_load: Optional[float] = None
    optimal_elbow_release: Optional[float] = None
    optimal_wrist_height: Optional[float] = None
    optimal_knee_bend: Optional[float] = None
    
    # Consistency metrics (standard deviation)
    elbow_load_consistency: Optional[float] = None
    wrist_height_consistency: Optional[float] = None
    
    # Patterns
    primary_miss_cause: Optional[str] = None
    strongest_aspect: Optional[str] = None
    
    # How their optimal compares to research
    vs_research: Dict[str, str] = None


def analyze_player_form(
    makes: List[Dict],
    misses: List[Dict],
    height_inches: Optional[int] = None
) -> FormAnalysis:
    """
    Analyze a player's shooting form based on their make/miss data.
    This is the core differentiator - personalized to THEIR mechanics.
    """
    
    analysis = FormAnalysis()
    
    if not makes:
        return analysis
    
    # Calculate optimal values from makes
    analysis.optimal_elbow_load = np.mean([s.get("elbow_load", 0) for s in makes if s.get("elbow_load")])
    analysis.optimal_elbow_release = np.mean([s.get("elbow_release", 0) for s in makes if s.get("elbow_release")])
    analysis.optimal_wrist_height = np.mean([s.get("wrist_height", 0) for s in makes if s.get("wrist_height")])
    analysis.optimal_knee_bend = np.mean([s.get("knee_bend", 0) for s in makes if s.get("knee_bend")])
    
    # Calculate consistency (lower = more consistent = better)
    elbow_loads = [s.get("elbow_load", 0) for s in makes if s.get("elbow_load")]
    if len(elbow_loads) > 1:
        analysis.elbow_load_consistency = np.std(elbow_loads)
    
    wrist_heights = [s.get("wrist_height", 0) for s in makes if s.get("wrist_height")]
    if len(wrist_heights) > 1:
        analysis.wrist_height_consistency = np.std(wrist_heights)
    
    # Analyze misses to find patterns
    if misses:
        miss_elbow = np.mean([s.get("elbow_load", 0) for s in misses if s.get("elbow_load")])
        miss_wrist = np.mean([s.get("wrist_height", 0) for s in misses if s.get("wrist_height")])
        
        # What's the biggest difference between makes and misses?
        elbow_diff = abs(analysis.optimal_elbow_load - miss_elbow) if analysis.optimal_elbow_load else 0
        wrist_diff = abs(analysis.optimal_wrist_height - miss_wrist) if analysis.optimal_wrist_height else 0
        
        if elbow_diff > wrist_diff * 20:  # Scale wrist since it's smaller numbers
            analysis.primary_miss_cause = "elbow_position"
        elif wrist_diff > 0.05:
            analysis.primary_miss_cause = "release_height"
        else:
            # Check miss types
            miss_types = [s.get("miss_type") for s in misses if s.get("miss_type")]
            if miss_types:
                from collections import Counter
                most_common = Counter(miss_types).most_common(1)[0][0]
                analysis.primary_miss_cause = f"trajectory ({most_common})"
    
    # Compare to research benchmarks
    analysis.vs_research = {}
    
    if analysis.optimal_elbow_load:
        if ELBOW_ANGLE_LOAD.min_val <= analysis.optimal_elbow_load <= ELBOW_ANGLE_LOAD.max_val:
            analysis.vs_research["elbow_load"] = "within_optimal"
        elif analysis.optimal_elbow_load < ELBOW_ANGLE_LOAD.min_val:
            analysis.vs_research["elbow_load"] = "below_optimal"
        else:
            analysis.vs_research["elbow_load"] = "above_optimal"
    
    if analysis.optimal_wrist_height:
        if RELEASE_HEIGHT.min_val <= analysis.optimal_wrist_height <= RELEASE_HEIGHT.max_val:
            analysis.vs_research["release_height"] = "within_optimal"
        elif analysis.optimal_wrist_height < RELEASE_HEIGHT.min_val:
            analysis.vs_research["release_height"] = "below_optimal"
        else:
            analysis.vs_research["release_height"] = "above_optimal"
    
    # Find strongest aspect (most consistent)
    if analysis.elbow_load_consistency and analysis.wrist_height_consistency:
        if analysis.elbow_load_consistency < 5:  # Very consistent
            analysis.strongest_aspect = "elbow_consistency"
        if analysis.wrist_height_consistency < 0.05:
            analysis.strongest_aspect = "release_point_consistency"
    
    return analysis


def generate_personalized_targets(
    analysis: FormAnalysis,
    height_inches: Optional[int] = None,
    distance_feet: Optional[float] = None
) -> Dict:
    """
    Generate personalized target metrics for a player.
    Combines their optimal form with research-backed adjustments.
    """
    
    targets = {}
    
    # Start with their personal optimal values
    if analysis.optimal_elbow_load:
        targets["elbow_load"] = {
            "target": analysis.optimal_elbow_load,
            "range": (analysis.optimal_elbow_load - 5, analysis.optimal_elbow_load + 5),
            "source": "your_makes"
        }
    else:
        targets["elbow_load"] = {
            "target": ELBOW_ANGLE_LOAD.ideal,
            "range": (ELBOW_ANGLE_LOAD.min_val, ELBOW_ANGLE_LOAD.max_val),
            "source": "research_baseline"
        }
    
    if analysis.optimal_wrist_height:
        targets["wrist_height"] = {
            "target": analysis.optimal_wrist_height,
            "range": (analysis.optimal_wrist_height - 0.05, analysis.optimal_wrist_height + 0.05),
            "source": "your_makes"
        }
    else:
        targets["wrist_height"] = {
            "target": RELEASE_HEIGHT.ideal,
            "range": (RELEASE_HEIGHT.min_val, RELEASE_HEIGHT.max_val),
            "source": "research_baseline"
        }
    
    # Apply height adjustments
    if height_inches:
        height_profile = get_height_profile(height_inches)
        targets["arc_adjustment"] = height_profile.arc_adjustment
        targets["release_speed"] = height_profile.release_speed
        targets["height_principles"] = height_profile.key_principles
    
    # Apply distance adjustments
    if distance_feet:
        dist_profile = get_distance_profile(distance_feet)
        
        # Adjust knee bend for distance
        base_knee = analysis.optimal_knee_bend or KNEE_BEND_LOAD.ideal
        targets["knee_bend"] = {
            "target": base_knee + dist_profile.knee_bend_adjustment,
            "source": "distance_adjusted",
            "note": dist_profile.notes
        }
    
    return targets


# =============================================================================
# Feedback Generation
# =============================================================================

def generate_form_feedback(
    current_shot: Dict,
    player_analysis: FormAnalysis,
    height_inches: Optional[int] = None,
    distance_feet: Optional[float] = None
) -> Dict:
    """
    Generate feedback for a shot based on player's personal optimal form
    and research-backed principles.
    """
    
    feedback = {
        "comparisons": [],
        "suggestions": [],
        "positive": [],
        "research_context": []
    }
    
    # Compare to personal optimal
    if player_analysis.optimal_elbow_load:
        current_elbow = current_shot.get("elbow_load", 0)
        diff = current_elbow - player_analysis.optimal_elbow_load
        
        if abs(diff) > 5:
            if diff > 0:
                feedback["comparisons"].append(
                    f"Elbow {diff:.0f}° more extended than your makes ({player_analysis.optimal_elbow_load:.0f}°)"
                )
                feedback["suggestions"].append("Tighter gather at set point")
            else:
                feedback["comparisons"].append(
                    f"Elbow {abs(diff):.0f}° more bent than your makes ({player_analysis.optimal_elbow_load:.0f}°)"
                )
                feedback["suggestions"].append("Extend slightly more at set point")
        else:
            feedback["positive"].append("Elbow position matches your makes")
    
    if player_analysis.optimal_wrist_height:
        current_wrist = current_shot.get("wrist_height", 0)
        diff = current_wrist - player_analysis.optimal_wrist_height
        
        if abs(diff) > 0.08:
            if diff < 0:
                feedback["comparisons"].append(
                    f"Release point lower than your makes ({player_analysis.optimal_wrist_height:.2f})"
                )
                feedback["suggestions"].append("Finish higher - extend through the ball")
            else:
                feedback["positive"].append("High release point")
        else:
            feedback["positive"].append("Release height consistent with your makes")
    
    # Add research context
    current_elbow = current_shot.get("elbow_load", 0)
    if current_elbow:
        if current_elbow < ELBOW_ANGLE_LOAD.min_val - 5:
            feedback["research_context"].append(
                f"Research suggests {ELBOW_ANGLE_LOAD.min_val:.0f}-{ELBOW_ANGLE_LOAD.max_val:.0f}° "
                f"elbow at set point is optimal"
            )
    
    # Height-specific feedback
    if height_inches:
        profile = get_height_profile(height_inches)
        if profile.arc_emphasis == "high":
            feedback["research_context"].append(
                "For your height, higher arc helps clear defenders"
            )
    
    return feedback


# =============================================================================
# Prompt Generation for AI Coach
# =============================================================================

def generate_coaching_context(
    player_analysis: FormAnalysis,
    height_inches: Optional[int] = None,
    distance_feet: Optional[float] = None
) -> str:
    """
    Generate context for the AI coaching prompt based on
    player's personal data and research principles.
    """
    
    context = """
═══════════════════════════════════════════════════════════════════════════════
PLAYER'S PERSONAL OPTIMAL FORM (from their makes)
═══════════════════════════════════════════════════════════════════════════════
"""
    
    if player_analysis.optimal_elbow_load:
        context += f"- Elbow at load: {player_analysis.optimal_elbow_load:.0f}°"
        if player_analysis.vs_research.get("elbow_load") == "within_optimal":
            context += " (matches research optimal)\n"
        else:
            context += f" (research suggests {ELBOW_ANGLE_LOAD.min_val:.0f}-{ELBOW_ANGLE_LOAD.max_val:.0f}°)\n"
    
    if player_analysis.optimal_wrist_height:
        context += f"- Release height: {player_analysis.optimal_wrist_height:.2f}\n"
    
    if player_analysis.optimal_knee_bend:
        context += f"- Knee bend: {player_analysis.optimal_knee_bend:.0f}°\n"
    
    if player_analysis.elbow_load_consistency:
        consistency = "very consistent" if player_analysis.elbow_load_consistency < 5 else \
                      "consistent" if player_analysis.elbow_load_consistency < 10 else "variable"
        context += f"- Form consistency: {consistency}\n"
    
    if player_analysis.primary_miss_cause:
        context += f"- Primary miss pattern: {player_analysis.primary_miss_cause}\n"
    
    # Height context
    if height_inches:
        profile = get_height_profile(height_inches)
        context += f"""
HEIGHT CONSIDERATIONS ({profile.category}):
- Recommended release speed: {profile.release_speed}
- Arc emphasis: {profile.arc_emphasis}
- Key principles: {'; '.join(profile.key_principles[:2])}
"""
    
    # Distance context
    if distance_feet:
        dist_profile = get_distance_profile(distance_feet)
        context += f"""
DISTANCE CONSIDERATIONS ({dist_profile.name}):
- Leg power: {dist_profile.leg_power_emphasis}
- Note: {dist_profile.notes}
"""
    
    context += """
COACHING APPROACH:
- Compare current shot to THIS PLAYER'S makes, not generic ideals
- Reference research only when their form deviates significantly from optimal
- Focus on consistency with their personal optimal form
- One actionable cue at a time
"""
    
    return context


# =============================================================================
# CLI Testing
# =============================================================================

if __name__ == "__main__":
    print("Biomechanics Reference Module")
    print("=" * 50)
    
    # Test with sample data
    sample_makes = [
        {"elbow_load": 92, "elbow_release": 168, "wrist_height": 1.18, "knee_bend": 28},
        {"elbow_load": 90, "elbow_release": 170, "wrist_height": 1.20, "knee_bend": 30},
        {"elbow_load": 91, "elbow_release": 167, "wrist_height": 1.17, "knee_bend": 27},
        {"elbow_load": 93, "elbow_release": 169, "wrist_height": 1.19, "knee_bend": 29},
    ]
    
    sample_misses = [
        {"elbow_load": 85, "elbow_release": 160, "wrist_height": 1.10, "miss_type": "short-right"},
        {"elbow_load": 88, "elbow_release": 162, "wrist_height": 1.12, "miss_type": "short-left"},
    ]
    
    analysis = analyze_player_form(sample_makes, sample_misses, height_inches=70)
    
    print("\nPlayer Analysis:")
    print(f"  Optimal elbow load: {analysis.optimal_elbow_load:.1f}°")
    print(f"  Optimal release height: {analysis.optimal_wrist_height:.2f}")
    print(f"  Primary miss cause: {analysis.primary_miss_cause}")
    print(f"  vs Research: {analysis.vs_research}")
    
    print("\nPersonalized Targets:")
    targets = generate_personalized_targets(analysis, height_inches=70, distance_feet=22)
    for key, val in targets.items():
        if isinstance(val, dict):
            print(f"  {key}: {val.get('target', val)}")
        else:
            print(f"  {key}: {val}")
    
    print("\nCoaching Context:")
    print(generate_coaching_context(analysis, height_inches=70, distance_feet=22))