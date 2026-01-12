"""
FormCheck Database Module
SQLite database for storing player profiles, sessions, and shots
"""

import sqlite3
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict
from datetime import datetime
import json

# Database location
DB_DIR = Path.home() / ".formcheck"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "formcheck.db"

@dataclass
class PlayerRecord:
    """Player profile record."""
    id: int
    name: str
    email: Optional[str] = None
    skill_level: str = "intermediate"
    working_on: Optional[str] = None
    limitations: Optional[str] = None
    height_inches: Optional[int] = None
    total_shots: int = 0
    total_makes: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class FormCheckDB:
    """Database handler for FormCheck."""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Players table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                skill_level TEXT DEFAULT 'intermediate',
                working_on TEXT,
                limitations TEXT,
                height_inches INTEGER,
                total_shots INTEGER DEFAULT 0,
                total_makes INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                shot_count INTEGER DEFAULT 0,
                make_count INTEGER DEFAULT 0,
                focus_area TEXT,
                notes TEXT,
                grade TEXT,
                summary TEXT,
                FOREIGN KEY (player_id) REFERENCES players(id)
            )
        """)
        
        # Shots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                player_id INTEGER NOT NULL,
                shot_number INTEGER NOT NULL,
                made INTEGER,
                miss_type TEXT,
                elbow_angle_load REAL,
                elbow_angle_release REAL,
                wrist_height_release REAL,
                knee_bend_load REAL,
                form_rating INTEGER,
                feedback TEXT,
                key_issue TEXT,
                quick_cue TEXT,
                did_well TEXT,
                looks_like TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id),
                FOREIGN KEY (player_id) REFERENCES players(id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def create_player(self, name: str, skill_level: str = "intermediate",
                     working_on: str = None, limitations: str = None,
                     height_inches: int = None, email: str = None) -> int:
        """Create a new player."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO players (name, email, skill_level, working_on, limitations, height_inches)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, email, skill_level, working_on, limitations, height_inches))
        
        player_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return player_id
    
    def get_player(self, player_id: int) -> Optional[PlayerRecord]:
        """Get player by ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM players WHERE id = ?", (player_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return PlayerRecord(
            id=row[0], name=row[1], email=row[2], skill_level=row[3],
            working_on=row[4], limitations=row[5], height_inches=row[6],
            total_shots=row[7], total_makes=row[8],
            created_at=row[9], updated_at=row[10]
        )
    
    def list_players(self, limit: int = 10) -> List[PlayerRecord]:
        """List all players."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM players ORDER BY updated_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        
        return [
            PlayerRecord(
                id=row[0], name=row[1], email=row[2], skill_level=row[3],
                working_on=row[4], limitations=row[5], height_inches=row[6],
                total_shots=row[7], total_makes=row[8],
                created_at=row[9], updated_at=row[10]
            )
            for row in rows
        ]
    
    def get_or_create_default_player(self) -> PlayerRecord:
        """Get or create default player."""
        players = self.list_players(limit=1)
        if players:
            return players[0]
        
        player_id = self.create_player("Player 1")
        return self.get_player(player_id)
    
    def create_session(self, player_id: int, focus_area: str = None) -> int:
        """Create a new session."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO sessions (player_id, focus_area)
            VALUES (?, ?)
        """, (player_id, focus_area))
        
        session_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return session_id
    
    def end_session(self, session_id: int, grade: str = None, summary: str = None):
        """End a session."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE sessions 
            SET ended_at = CURRENT_TIMESTAMP, grade = ?, summary = ?
            WHERE id = ?
        """, (grade, summary, session_id))
        
        conn.commit()
        conn.close()
    
    def record_shot(self, session_id: int, shot_data: Dict):
        """Record a shot."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get player_id from session
        cursor.execute("SELECT player_id FROM sessions WHERE id = ?", (session_id,))
        player_id = cursor.fetchone()[0]
        
        # Convert list to JSON string
        did_well_json = json.dumps(shot_data.get('did_well', [])) if shot_data.get('did_well') else None
        
        cursor.execute("""
            INSERT INTO shots (
                session_id, player_id, shot_number, made, miss_type,
                elbow_angle_load, elbow_angle_release, wrist_height_release, knee_bend_load,
                form_rating, feedback, key_issue, quick_cue, did_well, looks_like
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id, player_id, shot_data.get('shot_number'),
            shot_data.get('made'), shot_data.get('miss_type'),
            shot_data.get('elbow_angle_load'), shot_data.get('elbow_angle_release'),
            shot_data.get('wrist_height_release'), shot_data.get('knee_bend_load'),
            shot_data.get('form_rating'), shot_data.get('feedback'),
            shot_data.get('key_issue'), shot_data.get('quick_cue'),
            did_well_json, shot_data.get('looks_like')
        ))
        
        # Update session shot count
        cursor.execute("""
            UPDATE sessions 
            SET shot_count = shot_count + 1,
                make_count = make_count + CASE WHEN ? = 1 THEN 1 ELSE 0 END
            WHERE id = ?
        """, (shot_data.get('made', 0), session_id))
        
        conn.commit()
        conn.close()
    
    def update_player_stats(self, player_id: int):
        """Update player's total stats."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE players
            SET total_shots = (SELECT COUNT(*) FROM shots WHERE player_id = ?),
                total_makes = (SELECT COUNT(*) FROM shots WHERE player_id = ? AND made = 1),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (player_id, player_id, player_id))
        
        conn.commit()
        conn.close()
    
    def get_player_patterns(self, player_id: int) -> Dict:
        """Get player's shooting patterns."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get makes averages
        cursor.execute("""
            SELECT 
                AVG(elbow_angle_load) as avg_elbow_load,
                AVG(elbow_angle_release) as avg_elbow_release,
                AVG(wrist_height_release) as avg_wrist_height,
                AVG(knee_bend_load) as avg_knee_bend,
                MIN(elbow_angle_load) as min_elbow,
                MAX(elbow_angle_load) as max_elbow
            FROM shots
            WHERE player_id = ? AND made = 1
        """, (player_id,))
        
        makes_row = cursor.fetchone()
        
        makes = None
        if makes_row and makes_row[0] is not None:
            makes = {
                'avg_elbow_load': makes_row[0],
                'avg_elbow_release': makes_row[1],
                'avg_wrist_height': makes_row[2],
                'avg_knee_bend': makes_row[3],
                'elbow_range': (makes_row[4], makes_row[5]) if makes_row[4] else None
            }
        
        # Get miss distribution
        cursor.execute("""
            SELECT miss_type, COUNT(*) as count
            FROM shots
            WHERE player_id = ? AND made = 0 AND miss_type IS NOT NULL
            GROUP BY miss_type
            ORDER BY count DESC
        """, (player_id,))
        
        miss_dist = dict(cursor.fetchall())
        
        # Get common issues
        cursor.execute("""
            SELECT key_issue, COUNT(*) as count
            FROM shots
            WHERE player_id = ? AND key_issue IS NOT NULL AND key_issue != 'none'
            GROUP BY key_issue
            ORDER BY count DESC
            LIMIT 5
        """, (player_id,))
        
        common_issues = cursor.fetchall()
        
        # Get recent sessions
        cursor.execute("""
            SELECT 
                id,
                CAST(make_count AS REAL) / NULLIF(shot_count, 0) * 100 as pct,
                (SELECT AVG(form_rating) FROM shots WHERE session_id = sessions.id) as avg_rating
            FROM sessions
            WHERE player_id = ? AND shot_count > 0
            ORDER BY started_at DESC
            LIMIT 5
        """, (player_id,))
        
        recent_sessions = [
            {'id': row[0], 'pct': row[1] or 0, 'rating': row[2] or 0}
            for row in cursor.fetchall()
        ]
        
        conn.close()
        
        return {
            'makes': makes,
            'miss_distribution': miss_dist,
            'common_issues': common_issues,
            'recent_sessions': recent_sessions
        }
    
    def get_recent_feedback(self, player_id: int, limit: int = 10) -> List[str]:
        """Get recent feedback given to player."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT feedback
            FROM shots
            WHERE player_id = ? AND feedback IS NOT NULL
            ORDER BY created_at DESC
            LIMIT ?
        """, (player_id, limit))
        
        feedback = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        return feedback


def get_nba_context_for_prompt(player_height_inches: Optional[int]) -> str:
    """
    Get NBA context for prompt.
    This is a placeholder - the actual implementation would have more data.
    """
    if not player_height_inches:
        return ""
    
    feet = player_height_inches // 12
    inches = player_height_inches % 12
    
    if player_height_inches < 70:  # Under 5'10"
        category = "guard"
    elif player_height_inches < 78:  # 5'10" - 6'6"
        category = "wing"
    else:  # 6'6"+
        category = "big"
    
    return f"""
Height Category: {category} ({feet}'{inches}")
Typical shooting style for this height:
- Release point should be adjusted for body proportions
- Shorter players often need higher arc
- Taller players can shoot from higher release point
"""