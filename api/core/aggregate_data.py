#!/usr/bin/env python3
"""
FormCheck - Aggregate Data Module

Anonymized, opt-in community data for comparisons.
This is YOUR proprietary data - legally clean.

Users can compare themselves to:
- "Shooters your height who hit 70%+ from this distance"
- "Players at your skill level"
- "Most improved this month"

Privacy: All data is anonymized and aggregated.
Users must opt-in to contribute.
"""

import sqlite3
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple
from pathlib import Path
import numpy as np
from datetime import datetime, timedelta


@dataclass
class AggregateProfile:
    """Aggregated stats for a segment of users."""
    segment_name: str
    sample_size: int
    
    # Performance
    avg_make_pct: float
    top_quartile_make_pct: float
    
    # Form metrics (averages)
    avg_elbow_load: float
    avg_elbow_release: float
    avg_wrist_height: float
    avg_knee_bend: float
    
    # Consistency (standard deviations)
    std_elbow_load: float
    std_wrist_height: float
    
    # Common patterns
    most_common_miss_type: Optional[str] = None
    most_common_strength: Optional[str] = None


class AggregateDataDB:
    """
    Database for anonymized aggregate user data.
    
    PRIVACY PRINCIPLES:
    - No individual user data exposed
    - Minimum segment size of 20 users
    - Only aggregated statistics stored
    - Users must opt-in
    """
    
    MIN_SEGMENT_SIZE = 20  # Minimum users for a segment to be queryable
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(Path.home() / ".formcheck" / "aggregate.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Aggregated segments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                
                -- Segment definition
                segment_type TEXT NOT NULL,  -- "height", "skill", "accuracy", "distance"
                segment_value TEXT NOT NULL,  -- e.g., "5'8-5'11", "intermediate", "70-80%"
                
                -- Sample info
                sample_size INTEGER DEFAULT 0,
                last_updated TIMESTAMP,
                
                -- Aggregated performance
                avg_make_pct REAL,
                top_quartile_make_pct REAL,
                
                -- Aggregated form
                avg_elbow_load REAL,
                avg_elbow_release REAL,
                avg_wrist_height REAL,
                avg_knee_bend REAL,
                
                -- Consistency
                std_elbow_load REAL,
                std_wrist_height REAL,
                
                -- Patterns
                common_miss_type TEXT,
                common_strength TEXT,
                
                UNIQUE(segment_type, segment_value)
            )
        """)
        
        # Contribution tracking (for opt-in users)
        # This tracks that a user contributed, not their actual data
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contributions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_hash TEXT NOT NULL,  -- Hashed user ID
                contributed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_count INTEGER DEFAULT 0,
                shot_count INTEGER DEFAULT 0
            )
        """)
        
        conn.commit()
        conn.close()
    
    def get_segment(self, segment_type: str, segment_value: str) -> Optional[AggregateProfile]:
        """
        Get aggregated data for a segment.
        Returns None if segment doesn't exist or has too few users.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM segments
            WHERE segment_type = ? AND segment_value = ?
            AND sample_size >= ?
        """, (segment_type, segment_value, self.MIN_SEGMENT_SIZE))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return AggregateProfile(
            segment_name=f"{segment_type}:{segment_value}",
            sample_size=row["sample_size"],
            avg_make_pct=row["avg_make_pct"] or 0,
            top_quartile_make_pct=row["top_quartile_make_pct"] or 0,
            avg_elbow_load=row["avg_elbow_load"] or 0,
            avg_elbow_release=row["avg_elbow_release"] or 0,
            avg_wrist_height=row["avg_wrist_height"] or 0,
            avg_knee_bend=row["avg_knee_bend"] or 0,
            std_elbow_load=row["std_elbow_load"] or 0,
            std_wrist_height=row["std_wrist_height"] or 0,
            most_common_miss_type=row["common_miss_type"],
            most_common_strength=row["common_strength"]
        )
    
    def get_comparison_segments(self, height_inches: int = None,
                                 skill_level: str = None,
                                 make_pct: float = None) -> List[AggregateProfile]:
        """
        Get relevant comparison segments for a user.
        """
        segments = []
        
        # Height segment
        if height_inches:
            height_segment = self._get_height_segment(height_inches)
            profile = self.get_segment("height", height_segment)
            if profile:
                segments.append(profile)
        
        # Skill segment
        if skill_level:
            profile = self.get_segment("skill", skill_level)
            if profile:
                segments.append(profile)
        
        # Accuracy segment
        if make_pct:
            acc_segment = self._get_accuracy_segment(make_pct)
            profile = self.get_segment("accuracy", acc_segment)
            if profile:
                segments.append(profile)
        
        return segments
    
    def _get_height_segment(self, height_inches: int) -> str:
        """Map height to segment."""
        if height_inches < 66:
            return "under_5-6"
        elif height_inches < 70:
            return "5-6_to_5-10"
        elif height_inches < 74:
            return "5-10_to_6-2"
        elif height_inches < 78:
            return "6-2_to_6-6"
        else:
            return "over_6-6"
    
    def _get_accuracy_segment(self, make_pct: float) -> str:
        """Map accuracy to segment."""
        if make_pct < 30:
            return "under_30"
        elif make_pct < 45:
            return "30_to_45"
        elif make_pct < 55:
            return "45_to_55"
        elif make_pct < 65:
            return "55_to_65"
        elif make_pct < 75:
            return "65_to_75"
        else:
            return "over_75"
    
    def compare_to_segment(self, user_metrics: Dict, segment: AggregateProfile) -> Dict:
        """
        Compare a user's metrics to a segment.
        """
        comparison = {
            "segment": segment.segment_name,
            "sample_size": segment.sample_size,
            "differences": {},
            "percentile_estimates": {},
            "insights": []
        }
        
        # Elbow comparison
        if user_metrics.get("elbow_load") and segment.avg_elbow_load:
            diff = user_metrics["elbow_load"] - segment.avg_elbow_load
            comparison["differences"]["elbow_load"] = diff
            
            # Estimate percentile using std dev (assumes normal distribution)
            if segment.std_elbow_load > 0:
                z = diff / segment.std_elbow_load
                percentile = self._z_to_percentile(z)
                comparison["percentile_estimates"]["elbow_load"] = percentile
        
        # Wrist height comparison
        if user_metrics.get("wrist_height") and segment.avg_wrist_height:
            diff = user_metrics["wrist_height"] - segment.avg_wrist_height
            comparison["differences"]["wrist_height"] = diff
            
            if segment.std_wrist_height > 0:
                z = diff / segment.std_wrist_height
                percentile = self._z_to_percentile(z)
                comparison["percentile_estimates"]["wrist_height"] = percentile
        
        # Make percentage comparison
        if user_metrics.get("make_pct") is not None:
            if user_metrics["make_pct"] > segment.top_quartile_make_pct:
                comparison["insights"].append(
                    f"Your accuracy is in the top 25% for this group"
                )
            elif user_metrics["make_pct"] > segment.avg_make_pct:
                comparison["insights"].append(
                    f"Your accuracy is above average for this group ({segment.avg_make_pct:.0f}%)"
                )
        
        return comparison
    
    def _z_to_percentile(self, z: float) -> int:
        """Convert z-score to percentile (approximation)."""
        # Simple approximation for standard normal
        from math import erf, sqrt
        percentile = 0.5 * (1 + erf(z / sqrt(2)))
        return int(percentile * 100)
    
    # =========================================================================
    # Data Contribution (for opted-in users)
    # =========================================================================
    
    def contribute_session_data(self, user_hash: str, session_data: Dict) -> bool:
        """
        Add anonymized session data to aggregates.
        
        session_data should contain:
        - height_inches (optional)
        - skill_level
        - shots: list of shot metrics
        - make_pct
        """
        # This would update the aggregate segments
        # In a real system, this would be a batch job, not real-time
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Track contribution (not the data itself)
        cursor.execute("""
            INSERT INTO contributions (user_hash, shot_count)
            VALUES (?, ?)
        """, (user_hash, len(session_data.get("shots", []))))
        
        conn.commit()
        conn.close()
        
        return True


# =============================================================================
# Comparison Report Generator
# =============================================================================

def generate_community_comparison(
    user_metrics: Dict,
    height_inches: int = None,
    skill_level: str = None,
    make_pct: float = None
) -> Dict:
    """
    Generate a comparison report against community data.
    
    Returns insights like:
    - "Your release is higher than 75% of players your height"
    - "Shooters in your accuracy range average 91° elbow at load"
    """
    
    db = AggregateDataDB()
    segments = db.get_comparison_segments(height_inches, skill_level, make_pct)
    
    if not segments:
        return {
            "available": False,
            "message": "Not enough community data for comparison yet. "
                       "Keep shooting and check back later!"
        }
    
    report = {
        "available": True,
        "comparisons": [],
        "insights": [],
        "how_you_rank": {}
    }
    
    for segment in segments:
        comparison = db.compare_to_segment(user_metrics, segment)
        report["comparisons"].append(comparison)
        report["insights"].extend(comparison.get("insights", []))
        
        # Add ranking info
        for metric, percentile in comparison.get("percentile_estimates", {}).items():
            if metric not in report["how_you_rank"]:
                report["how_you_rank"][metric] = []
            report["how_you_rank"][metric].append({
                "segment": segment.segment_name,
                "percentile": percentile
            })
    
    return report


# =============================================================================
# Example Data (for development/testing)
# =============================================================================

def seed_example_data():
    """Seed example aggregate data for testing."""
    
    db = AggregateDataDB()
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    
    example_segments = [
        # Height segments
        ("height", "5-10_to_6-2", 150, 52.3, 68.1, 91.2, 168.5, 1.18, 28.5, 4.2, 0.08, "short", "consistency"),
        ("height", "under_5-6", 45, 48.5, 62.0, 89.5, 165.2, 1.12, 32.1, 5.1, 0.10, "short-left", "quick_release"),
        ("height", "6-2_to_6-6", 82, 55.1, 71.2, 92.8, 170.1, 1.25, 26.2, 3.8, 0.07, "long", "high_release"),
        
        # Skill segments
        ("skill", "beginner", 200, 38.2, 52.0, 88.5, 162.3, 1.08, 25.5, 8.5, 0.15, "short", None),
        ("skill", "intermediate", 350, 52.1, 67.5, 91.0, 168.0, 1.17, 28.0, 4.5, 0.09, "short-right", "consistency"),
        ("skill", "advanced", 120, 64.5, 78.2, 92.5, 172.1, 1.22, 30.2, 3.2, 0.06, "long", "form_consistency"),
        
        # Accuracy segments
        ("accuracy", "45_to_55", 180, 50.0, 54.5, 90.5, 166.8, 1.15, 27.5, 5.0, 0.10, "short", None),
        ("accuracy", "55_to_65", 140, 60.0, 64.5, 91.5, 169.2, 1.19, 29.0, 4.0, 0.08, "short-right", "elbow_consistency"),
        ("accuracy", "65_to_75", 85, 70.0, 74.5, 92.2, 171.0, 1.21, 30.5, 3.5, 0.07, "long", "form_consistency"),
        ("accuracy", "over_75", 35, 78.5, 82.0, 92.8, 173.5, 1.23, 31.0, 3.0, 0.06, "back-rim", "consistency"),
    ]
    
    for seg in example_segments:
        cursor.execute("""
            INSERT OR REPLACE INTO segments (
                segment_type, segment_value, sample_size,
                avg_make_pct, top_quartile_make_pct,
                avg_elbow_load, avg_elbow_release, avg_wrist_height, avg_knee_bend,
                std_elbow_load, std_wrist_height,
                common_miss_type, common_strength, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, seg)
    
    conn.commit()
    conn.close()
    print(f"Seeded {len(example_segments)} example segments")


# =============================================================================
# CLI Testing
# =============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        seed_example_data()
    else:
        # Test comparison
        print("Testing Community Comparison")
        print("=" * 50)
        
        # First seed some data
        seed_example_data()
        
        # Then test comparison
        user_metrics = {
            "elbow_load": 93,
            "elbow_release": 170,
            "wrist_height": 1.20,
            "knee_bend": 29,
            "make_pct": 58
        }
        
        report = generate_community_comparison(
            user_metrics,
            height_inches=71,  # 5'11"
            skill_level="intermediate",
            make_pct=58
        )
        
        if report["available"]:
            print("\nComparison Report:")
            print(f"  Segments compared: {len(report['comparisons'])}")
            
            for comp in report["comparisons"]:
                print(f"\n  {comp['segment']} (n={comp['sample_size']}):")
                for metric, pct in comp.get("percentile_estimates", {}).items():
                    print(f"    {metric}: {pct}th percentile")
            
            if report["insights"]:
                print("\n  Insights:")
                for insight in report["insights"]:
                    print(f"    • {insight}")
        else:
            print(report["message"])