#!/usr/bin/env python3
"""
FormCheck API - Multi-shot video analysis
Processes ALL shots in a video and returns session summary
"""

import os
import sys
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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
db = FormCheckDB() if MODULES_AVAILABLE else None

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
    thumbnail: str  # Base64 encoded thumbnail (release frame)

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

class HealthResponse(BaseModel):
    status: str
    modules_available: bool
    gemini_configured: bool
    database_available: bool

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

# Analyze entire video with multiple shots
@app.post("/analyze", response_model=SessionSummary)
async def analyze_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    shooting_side: str = "right",
    player_id: Optional[int] = None
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
        # Save uploaded file
        suffix = Path(file.filename).suffix if file.filename else ".mp4"
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        content = await file.read()
        temp_file.write(content)
        temp_file.close()
        video_path = temp_file.name
        
        print(f"\n{'='*60}")
        print(f"📹 Processing video: {file.filename} ({len(content)} bytes)")
        print(f"{'='*60}\n")
        
        # Initialize components
        pose = PoseDetector()
        shot_detector = LiveShotDetector(shooting_side)
        
        # Get player profile
        player_profile = PlayerProfile()
        if player_id and db:
            player = db.get_player(player_id)
            if player:
                player_profile = PlayerProfile(
                    skill_level=player.skill_level,
                    working_on=player.working_on or "",
                    limitations=player.limitations or "",
                    height_inches=player.height_inches
                )
        
        # Process video to find ALL shots
        import cv2
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail="Could not open video file")
        
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        detected_shots = []
        frame_count = 0
        
        print(f"🎬 Video info: {total_frames} frames @ {fps:.1f} fps")
        print(f"⏱️  Duration: {total_frames/fps:.1f} seconds")
        print(f"🔍 Scanning for shots...\n")
        
        # Process ALL frames to find ALL shots
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            
            # Show progress every 100 frames
            if frame_count % 100 == 0:
                progress = (frame_count / total_frames) * 100
                print(f"   Processing: {progress:.0f}% ({frame_count}/{total_frames} frames)")
            
            # Detect pose
            landmarks, visibility = pose.detect(frame)
            
            # Detect shot
            shot = shot_detector.update(frame, landmarks, visibility)
            if shot:
                shot.shot_number = len(detected_shots) + 1
                detected_shots.append(shot)
                print(f"\n✓ Shot #{shot.shot_number} detected at frame {frame_count}")
                print(f"   Elbow: {shot.elbow_angle_load:.0f}° → {shot.elbow_angle_release:.0f}°\n")
        
        cap.release()
        pose.close()
        
        # Cleanup temp file
        background_tasks.add_task(os.unlink, video_path)
        
        if not detected_shots:
            raise HTTPException(
                status_code=404,
                detail="No shots detected. Make sure video shows clear shooting motions with full body visible."
            )
        
        print(f"\n{'='*60}")
        print(f"🎯 Found {len(detected_shots)} shot(s) - Analyzing with Gemini...")
        print(f"{'='*60}\n")
        
        # Analyze each shot with Gemini
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
        
        analyzed_shots = []
        
        for idx, shot_event in enumerate(detected_shots, 1):
            print(f"🤖 Analyzing shot {idx}/{len(detected_shots)}...")
            
            # Build prompt for individual shot
            prompt = f"""You are analyzing shot #{idx} from a basketball practice session.

Shot metrics:
- Elbow at load: {shot_event.elbow_angle_load:.0f}°
- Elbow at release: {shot_event.elbow_angle_release:.0f}°
- Wrist height: {shot_event.wrist_height_release:.2f}
- Knee bend: {shot_event.knee_bend_load:.0f}°

Provide BRIEF analysis in JSON:
{{
    "made": true/false,
    "miss_type": "short-left" / "short-right" / "long-left" / "long-right" / null,
    "form_rating": 1-10,
    "feedback": "Brief feedback - max 15 words",
    "key_issue": "Main issue or 'none'",
    "quick_cue": "2-4 word cue"
}}
"""
            
            # Encode frames
            content_for_gemini = [prompt]
            for label, frame_img in shot_event.frames:
                _, buffer = cv2.imencode('.jpg', frame_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
                b64 = base64.b64encode(buffer).decode('utf-8')
                content_for_gemini.append({
                    "mime_type": "image/jpeg",
                    "data": b64
                })
            
            # Get Gemini response
            response = model.generate_content(content_for_gemini)
            text = response.text.strip()
            
            # Parse JSON
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            result = json.loads(text)
            
            # Create thumbnail from release frame (frame index 6)
            release_frame = shot_event.frames[6][1] if len(shot_event.frames) > 6 else shot_event.frames[-1][1]
            height, width = release_frame.shape[:2]
            target_height = 200
            target_width = int(width * (target_height / height))
            resized = cv2.resize(release_frame, (target_width, target_height))
            _, buffer = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, 80])
            thumbnail_b64 = base64.b64encode(buffer).decode('utf-8')
            
            # Add to results
            analyzed_shots.append(ShotAnalysis(
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
                thumbnail=thumbnail_b64
            ))
            
            print(f"   ✓ Shot {idx}: {result.get('made', 'unknown')} - {result.get('feedback', '')[:40]}...")
        
        # Calculate session stats
        makes = sum(1 for s in analyzed_shots if s.made)
        misses = sum(1 for s in analyzed_shots if s.made == False)
        total = len(analyzed_shots)
        shooting_pct = (makes / total * 100) if total > 0 else 0
        
        ratings = [s.form_rating for s in analyzed_shots if s.form_rating]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0
        
        print(f"\n{'='*60}")
        print(f"📊 Session Stats: {makes}/{total} made ({shooting_pct:.1f}%)")
        print(f"⭐ Average form rating: {avg_rating:.1f}/10")
        print(f"{'='*60}\n")
        
        # Generate session-level feedback with Gemini
        print(f"🤖 Generating session summary...")
        
        session_prompt = f"""You analyzed {total} basketball shots. Provide a session summary.

Stats:
- Made: {makes}/{total} ({shooting_pct:.1f}%)
- Average form rating: {avg_rating:.1f}/10

Individual shot feedback:
{chr(10).join(f"Shot {s.shot_number}: {s.feedback}" for s in analyzed_shots)}

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
        
        summary_response = model.generate_content(session_prompt)
        summary_text = summary_response.text.strip()
        
        if "```json" in summary_text:
            summary_text = summary_text.split("```json")[1].split("```")[0]
        elif "```" in summary_text:
            summary_text = summary_text.split("```")[1].split("```")[0]
        
        summary_result = json.loads(summary_text)
        
        print(f"✓ Session summary generated\n")
        
        # Return complete session summary
        return SessionSummary(
            total_shots=total,
            shots_made=makes,
            shots_missed=misses,
            shooting_percentage=shooting_pct,
            average_form_rating=avg_rating,
            session_feedback=summary_result.get("session_feedback", ""),
            drill_suggestions=summary_result.get("drill_suggestions", []),
            shots=analyzed_shots
        )
        
    except HTTPException:
        raise
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
    port = int(os.getenv("API_PORT", 8000))
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
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )