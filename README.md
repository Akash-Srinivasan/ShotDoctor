# FormCheck

An AI-powered basketball shooting analysis platform that provides personalized coaching feedback by comparing a player's shooting form against their own optimal mechanics, not generic standards.

## Problem Statement

Existing shot tracking apps either:
- Provide generic coaching advice that doesn't account for individual biomechanics
- Require manual logging of makes/misses
- Lack real-time form analysis
- Don't scale coaching expertise to amateur players

FormCheck solves this by automatically detecting shots from video, analyzing form using computer vision, and providing personalized coaching through AI that learns each player's optimal form.

## Technical Architecture

### Core System Design

```
Mobile App (React Native/Expo)
    ↓
Video Upload → Cloud Processing Pipeline
    ↓
Computer Vision (MediaPipe) → Shot Detection
    ↓
Frame Analysis → Gemini Vision API
    ↓
Personalized Feedback → User
```

### Key Technical Decisions

**Shot Detection Algorithm: Release-Backward Approach**

Most shot detectors fail because they try to predict when a shot starts. We inverted the problem:

1. Detect the release point (elbow angle > 155°, wrist above shoulder) - this is unambiguous
2. Work backward to find the load point (minimum elbow angle in previous 60 frames)
3. Extract 8 equidistant frames capturing the full shooting motion

This eliminates false positives from dribbling and ensures we capture the actual shot mechanics.

**Self-Referential Coaching Model**

The system builds a profile of each player's successful shots:
- Tracks biomechanical metrics on makes vs misses
- Identifies personal optimal ranges for form metrics
- Provides feedback relative to the player's own patterns, not textbook form

This is critical because shooting form varies significantly based on height, strength, and individual biomechanics.

**Multi-Shot Session Analysis**

Rather than analyze individual shots in isolation, the system processes entire practice sessions:
- Detects all shots in a single video
- Identifies consistency patterns across attempts
- Generates session-level coaching with specific drill recommendations
- Provides visual shot gallery for quick review

## Technology Stack

### Mobile (SDK 54)
- **React Native + Expo**: Cross-platform development with OTA updates
- **expo-camera**: Video recording with configurable quality
- **expo-video**: Video playback during analysis
- **TypeScript**: Type safety for complex state management
- **Zustand**: Lightweight state management for session data

### Backend
- **FastAPI**: High-performance async API server
- **MediaPipe**: Google's pose estimation for biomechanics tracking
- **OpenCV**: Video processing and frame extraction
- **Gemini 2.0 Flash**: Vision model for form analysis
- **SQLite**: Local data persistence with migration path to PostgreSQL
- **Supabase (planned)**: Production database with row-level security

### Infrastructure
- **Python 3.10+**: Core analysis engine
- **ngrok**: Development tunnel for mobile testing
- **uvicorn**: ASGI server with auto-reload

## Project Structure

```
FormCheck/
├── api/                          # Python backend
│   ├── main.py                   # FastAPI server (multi-shot analysis)
│   ├── core/
│   │   ├── live_analysis.py      # Shot detection & pose tracking
│   │   ├── database.py           # SQLite data layer
│   │   └── biomechanics.py       # Form analysis algorithms
│   └── requirements.txt
├── mobile/                       # React Native app
│   ├── app/
│   │   ├── record.tsx            # Video capture & results UI
│   │   └── index.tsx             # Home dashboard
│   ├── components/
│   │   └── Camera.tsx            # Recording interface
│   └── lib/
│       ├── api.ts                # Backend client
│       └── supabase.ts           # Database client
└── docs/                         # Architecture docs
```

## Getting Started

### Prerequisites
- Python 3.10+ with virtual environment
- Node.js 18+
- Expo CLI
- iOS device with Expo Go (or Android)
- Gemini API key (free tier available)

### Backend Setup

```bash
cd api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Add your GEMINI_API_KEY

# Start server
python main.py
```

### Mobile Setup

```bash
cd mobile
npm install

# Configure environment
cp .env.example .env
# Add your API URL (use ngrok for local dev)

# Start development server
npx expo start
```

### Development Workflow

Terminal 1: Run API server
```bash
cd api && python main.py
```

Terminal 2: Expose API via ngrok
```bash
ngrok http 8000
# Copy HTTPS URL to mobile/.env
```

Terminal 3: Run mobile app
```bash
cd mobile && npx expo start
```

## Core Features

### Automatic Shot Detection
- Processes entire video to find all shooting attempts
- No manual logging required
- Handles various shooting styles and camera angles

### Form Analysis
Tracks key biomechanical metrics:
- Elbow angles (load position and release)
- Wrist height relative to body
- Knee bend at load
- Release consistency

### Personalized Coaching
- Compares current form against player's successful shots
- Identifies specific deviations causing misses
- Provides actionable cues (not generic advice)
- Suggests targeted drills based on patterns

### Session Summaries
- Makes/misses tracking with shooting percentage
- Average form rating across all attempts
- Pattern analysis (consistency, common issues)
- Recommended drills addressing specific weaknesses

## API Endpoints

### `POST /analyze`
Analyzes a video containing multiple basketball shots.

**Request:**
- `file`: Video file (multipart/form-data)
- `shooting_side`: "left" or "right"
- `player_id`: Optional player identifier

**Response:**
```json
{
  "total_shots": 5,
  "shots_made": 3,
  "shooting_percentage": 60.0,
  "average_form_rating": 7.2,
  "session_feedback": "Consistent release point across all shots...",
  "drill_suggestions": [
    "Wall sits to build leg strength",
    "Form shooting from 3 feet"
  ],
  "shots": [
    {
      "shot_number": 1,
      "made": true,
      "form_rating": 8,
      "feedback": "Good knee bend, solid release",
      "quick_cue": "keep this rhythm",
      "thumbnail": "base64_encoded_image",
      "elbow_angle_load": 92,
      "elbow_angle_release": 168
    }
  ]
}
```

### `GET /health`
Health check endpoint returning system status.

## Technical Challenges & Solutions

### Challenge 1: Real-time Pose Detection on Mobile
**Problem:** MediaPipe requires significant compute. Running on-device would drain battery.

**Solution:** Hybrid approach - record on device, process on server. Future optimization could use edge models for preview.

### Challenge 2: Shot Detection Accuracy
**Problem:** Initial approach using elbow angle thresholds had 40% false positive rate from dribbling.

**Solution:** Inverted detection logic - find release first (unambiguous), then work backward. Reduced false positives to < 5%.

### Challenge 3: Coaching Personalization
**Problem:** Generic form advice (e.g., "90-degree elbow") doesn't work - players have different optimal mechanics based on height and strength.

**Solution:** Build per-player profile from successful shots. Compare misses to player's own makes, not textbook standards.

### Challenge 4: API Cost Management
**Problem:** Sending 8 frames per shot to Gemini at scale could be expensive.

**Solution:** 
- Compress frames to 400px height (reduces payload by 70%)
- Use Gemini Flash (cheaper, faster)
- Batch analysis for multi-shot sessions
- Cache results in database

## Development Decisions

### Why React Native over Native?
- Single codebase for iOS and Android
- Expo provides OTA updates (critical for rapid iteration)
- Easier to find contractors for v1 development
- Can still use native modules for performance-critical features

### Why FastAPI over Django/Flask?
- Native async support for video processing
- Automatic OpenAPI documentation
- Type validation with Pydantic
- Faster than Flask, simpler than Django for API-only service

### Why Gemini over GPT-4V?
- Better vision capabilities for sports analysis
- Lower cost per request
- Faster response times (critical for UX)
- More generous free tier for development

### Why SQLite Initially?
- Zero-configuration local development
- Sufficient for < 10k users
- Clear migration path to PostgreSQL (via Supabase)
- Reduces infrastructure complexity for MVP

## Performance Characteristics

- **Shot Detection:** ~100ms per frame, processes 30fps video
- **Single Shot Analysis:** 8-12 seconds (including Gemini API)
- **Multi-Shot Session:** 15-25 seconds per shot detected
- **API Response Size:** ~200KB for 5-shot session (with thumbnails)

## Roadmap

**Phase 1: MVP (Current)**
- Multi-shot session analysis
- Basic player profiles
- Session history
- Manual make/miss input

**Phase 2: Engagement**
- Automatic make/miss detection using rim tracking
- Progress tracking over time
- Streak and achievement system
- Social sharing

**Phase 3: Monetization**
- Freemium model (10 shots/week free)
- Pro tier ($9.99/mo): unlimited analysis
- Team tier ($29.99/mo): coach dashboard
- Stripe integration

**Phase 4: Scale**
- Real-time analysis (websockets)
- Video export with form overlays
- Advanced analytics (shot trajectory)
- Coach marketplace

## Known Limitations

1. **Lighting Dependency:** Pose detection accuracy drops in low light. Recommend outdoor or well-lit gym shooting.

2. **Camera Position:** Best results when camera is positioned 10-15 feet away at waist height. Too close or too far reduces accuracy.

3. **Clothing:** Loose clothing can obscure joint positions. Recommend form-fitting athletic wear.

4. **Processing Time:** Multi-shot analysis takes 60-90 seconds for 5 shots. Future optimization could parallelize Gemini calls.

## Contributing

This is a portfolio project demonstrating full-stack mobile development with AI integration. While not actively accepting contributions, feel free to fork for your own experiments.

## License

MIT License - see LICENSE file for details

## Contact

For inquiries about this project or collaboration opportunities, reach out via [your contact info].

---

**Note:** This is a working prototype demonstrating technical capabilities. Not production-ready without additional work on authentication, rate limiting, error handling, and infrastructure scaling.
