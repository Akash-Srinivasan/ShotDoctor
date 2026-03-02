# FormCheck - Project Handoff Documentation

> **Last Updated:** January 30, 2026
> **Project Status:** MVP Development - Beta Testing
> **Version:** 2.0.0

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Project Overview](#project-overview)
3. [Architecture](#architecture)
4. [File Structure](#file-structure)
5. [How the Code Works](#how-the-code-works)
6. [Current Status](#current-status)
7. [Known Issues & Fixes](#known-issues--fixes)
8. [Completed Fixes](#completed-fixes)
9. [Future Roadmap](#future-roadmap)
10. [Setup Instructions](#setup-instructions)
11. [Technical Debt](#technical-debt)
12. [Recommendations](#recommendations)

---

## Executive Summary

FormCheck is an **AI-powered basketball shooting coach** mobile app that analyzes shooting form through video analysis. Users record themselves shooting, and the app provides real-time feedback on form, tracks statistics, and offers personalized drill recommendations.

### Key Technologies
| Component | Technology |
|-----------|------------|
| Mobile App | React Native 0.81 + Expo SDK 54 |
| Backend API | Python FastAPI |
| Pose Detection | Google MediaPipe |
| Ball Tracking | Custom YOLOv8 + CSRT + HSV hybrid |
| AI Coaching | Google Gemini 2.0 Flash (`google-genai` SDK) |
| Database | Supabase (PostgreSQL) |
| Storage | Supabase Storage (shot thumbnails) |
| Authentication | Supabase Auth |

### Project Health
| Metric | Status |
|--------|--------|
| Critical Bugs | ✅ 0 (all resolved) |
| Major Issues | 🟡 2 (Gemini rate limits, async processing) |
| Minor Issues | 🟡 8 (code quality) |
| Test Coverage | 🟢 126 mobile tests |
| Documentation | 🟢 Up to date |

---

## Project Overview

### What It Does

1. **User records a shooting session** (single shot or multiple shots in one video)
2. **User calibrates rim position** (optional tap-to-set overlay on first frame)
3. **Backend processes the video:**
   - MediaPipe detects body pose landmarks (33 key points)
   - Custom algorithm detects individual shots using wrist trajectory
   - Calculates form metrics (elbow angle, knee bend, wrist height)
   - Custom YOLO ball tracker detects ball flight after release
   - Trajectory analysis determines make/miss using calibrated rim position
   - Gemini AI generates personalized coaching feedback per shot
   - Gemini generates session-level summary and drill suggestions
4. **App displays results:**
   - Per-shot analysis with skeleton-overlay thumbnails
   - Make/miss badges (green/red/gray) with miss direction
   - Session statistics (makes/misses, shooting %)
   - Form ratings and improvement cues
   - Drill recommendations
5. **Results persist to Supabase:**
   - Session record with stats, feedback, drill suggestions
   - Individual shot records with metrics, feedback, thumbnail URLs
   - Thumbnails uploaded to Supabase Storage
   - Viewable later from session detail screen via History tab

### Target Users
- Basketball players (recreational to competitive)
- Coaches wanting to track player progress
- Parents helping kids improve

### Monetization (Planned)
- **Free tier:** 3 sessions/month, basic feedback
- **Pro tier ($9.99/mo):** Unlimited sessions, advanced analytics
- **Team tier ($29.99/mo):** Multi-player tracking, team analytics

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        MOBILE APP                                │
│                   (React Native + Expo)                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │  Auth    │  │  Record  │  │  Results │  │  Profile │        │
│  │  Screens │  │  Screen  │  │  Display │  │  Screen  │        │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘        │
│       │             │             │             │                │
│       └─────────────┴──────┬──────┴─────────────┘                │
│                            │                                     │
│                    ┌───────┴───────┐                            │
│                    │  AuthContext  │                            │
│                    │  (React Ctx)  │                            │
│                    └───────┬───────┘                            │
└────────────────────────────┼────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
     ┌────────────┐  ┌────────────┐  ┌────────────┐
     │  Supabase  │  │  FastAPI   │  │   Ngrok    │
     │   Auth     │  │  Backend   │  │  (Tunnel)  │
     │            │  │            │  │            │
     └─────┬──────┘  └─────┬──────┘  └────────────┘
           │               │
           ▼               ▼
     ┌────────────┐  ┌────────────────────────────┐
     │  Supabase  │  │      VIDEO PROCESSING      │
     │  Database  │  │  ┌──────────────────────┐  │
     │            │  │  │   MediaPipe Pose     │  │
     │  - profiles│  │  │   (33 landmarks)     │  │
     │  - sessions│  │  └──────────┬───────────┘  │
     │  - shots   │  │             │              │
     └────────────┘  │  ┌──────────▼───────────┐  │
                     │  │  Shot Detection      │  │
                     │  │  (wrist trajectory)  │  │
                     │  └──────────┬───────────┘  │
                     │             │              │
                     │  ┌──────────▼───────────┐  │
                     │  │  Form Metrics        │  │
                     │  │  (angles, heights)   │  │
                     │  └──────────┬───────────┘  │
                     │             │              │
                     │  ┌──────────▼───────────┐  │
                     │  │  Gemini AI           │  │
                     │  │  (coaching feedback) │  │
                     │  └──────────────────────┘  │
                     └────────────────────────────┘
```

### Data Flow

```
1. User → Record Video → Calibrate Rim (optional) → Upload to API
2. API → Extract Frames → MediaPipe Pose Detection (every frame)
3. Pose Data → Shot Detection (wrist trajectory) → Identify Individual Shots
4. Release detected → Ball Tracker (CSRT + YOLO + HSV) tracks flight
5. Trajectory + Rim Position → Programmatic Make/Miss classification
6. Per-Shot → Gemini AI → Form feedback, rating, key issue, quick cue
7. All Shots → Gemini AI → Session summary + drill suggestions
8. Results → Return to App → Save to Supabase + Upload thumbnails to Storage
9. User → History tab → Tap session → Session detail with all shot data
```

---

## File Structure

```
FormCheckApp/
├── mobile/                              # React Native Expo App
│   ├── app/                             # Expo Router pages
│   │   ├── _layout.tsx                  # Root layout with AuthProvider + all routes
│   │   ├── index.tsx                    # Entry point / home dashboard
│   │   ├── onboarding.tsx               # 3-step new user setup flow
│   │   ├── edit-preferences.tsx         # Edit preferences modal
│   │   ├── (tabs)/                      # Tab navigator
│   │   │   ├── _layout.tsx              # Tab bar config (Home, Record, History, Profile)
│   │   │   ├── index.tsx                # Home tab — stats, quick actions
│   │   │   ├── record.tsx               # Record tab — camera, analysis, results
│   │   │   ├── history.tsx              # History tab — session list with sort/filter
│   │   │   └── profile.tsx              # Profile tab — user info, settings, sign out
│   │   ├── session/
│   │   │   └── [id].tsx                 # Session detail — shots, feedback, drills
│   │   └── auth/
│   │       ├── login.tsx                # Sign in
│   │       ├── signup.tsx               # Create account
│   │       └── forgot-password.tsx      # Password reset
│   │
│   ├── components/
│   │   ├── Camera.tsx                   # Video recording with expo-camera
│   │   ├── RimCalibrationOverlay.tsx    # Tap-to-set rim position overlay
│   │   └── ShotMarkerTimeline.tsx       # Interactive shot markers on video timeline
│   │
│   ├── contexts/
│   │   └── AuthContext.tsx              # Auth state management + profile
│   │
│   ├── lib/
│   │   ├── api.ts                       # Backend API client (analyzeVideo, health)
│   │   └── supabase.ts                  # Supabase client (db ops, storage, types)
│   │
│   ├── __tests__/                       # 126 Jest tests
│   │   ├── lib/api.test.ts              # 38 API client tests
│   │   ├── lib/supabase.test.ts         # 26 Supabase client tests
│   │   ├── components/ShotMarkerTimeline.test.tsx   # 31 tests
│   │   └── components/RimCalibrationOverlay.test.tsx # 31 tests
│   │
│   ├── FORMCHECK_HANDOFF.md             # This document
│   ├── TESTING_SETUP.md                 # Test infrastructure docs
│   ├── package.json
│   └── tsconfig.json
│
├── api/                                 # Python FastAPI Server
│   ├── main.py                          # API endpoints + video processing pipeline
│   ├── .env                             # Environment variables
│   ├── core/
│   │   ├── live_analysis.py             # Pose detection, shot detection, Gemini client
│   │   ├── test_tracking.py             # CustomBallTracker (YOLO+CSRT+HSV), ReleaseDetector
│   │   ├── rim_detector.py              # Rim detection (Hough, color, YOLO methods)
│   │   ├── biomechanics.py              # Research-backed form guidelines
│   │   ├── visual_feedback.py           # Debug visualization overlays
│   │   ├── database.py                  # FormCheckDB (player profiles)
│   │   ├── basketball_detector/         # Custom YOLOv8 trained model + dataset
│   │   │   └── yolov8_basketball/weights/best.pt
│   │   └── train_basketball_yolo.py     # YOLO training script
│   │
│   └── venv/                            # Python virtual environment
```

---

## How the Code Works

### Mobile App Flow

#### 1. Authentication (`AuthContext.tsx`)
```typescript
// Manages global auth state
const AuthContext = createContext<AuthContextType>();

// Provides: user, profile, loading, signIn, signOut, etc.
export function AuthProvider({ children }) {
  // Listens to Supabase auth state changes
  supabase.auth.onAuthStateChange((event, session) => {
    // Updates state, fetches profile
  });
}
```

#### 2. App Entry (`index.tsx`)
```typescript
export default function Index() {
  const { user, profile, loading } = useAuth();
  
  // Routing logic:
  // - No user → /auth/login
  // - No profile → /onboarding  
  // - Has profile → Show home screen
}
```

#### 3. Recording (`record.tsx`)
```typescript
// States: idle → recording → uploading → analyzing → results
const [analyzing, setAnalyzing] = useState(false);
const [result, setResult] = useState<SessionSummary | null>(null);

// Flow:
// 1. User records video or picks from library
// 2. Video uploaded to API via FormData
// 3. API returns SessionSummary with all shots
// 4. Results saved to Supabase
// 5. UI displays shot thumbnails, stats, feedback
```

### Backend Processing

#### 1. API Endpoint (`main.py`)
```python
@app.post("/analyze")
async def analyze_video(file: UploadFile, shooting_side: str = "right"):
    # 1. Save uploaded video to temp file
    # 2. Initialize ShootingFormAnalyzer
    # 3. Process all frames
    # 4. Return SessionSummary JSON
```

#### 2. Shot Detection Algorithm (`live_analysis.py`)

The algorithm uses a **"release-backward" approach**:

```python
class ShootingFormAnalyzer:
    def detect_shots(self):
        # 1. Track wrist Y position over time
        # 2. Find "release points" (local minima in wrist height)
        # 3. For each release, look backward to find "load" position
        # 4. Extract shot window: load_frame → release_frame
        
    def calculate_metrics(self, shot_window):
        # At LOAD position:
        #   - Elbow angle (should be ~90°)
        #   - Knee bend angle (should be ~140-160°)
        
        # At RELEASE position:
        #   - Elbow angle (should be ~160-180°)
        #   - Wrist height relative to shoulder
```

**Key Detection Logic:**
```python
def _find_release_points(self):
    """Find frames where wrist is at lowest point (release moment)"""
    for i in range(window, len(wrist_heights) - window):
        # Check if this is a local minimum
        if wrist_heights[i] == min(wrist_heights[i-window:i+window+1]):
            # Verify sufficient upward motion after (follow-through)
            if wrist_heights[i+window] - wrist_heights[i] > threshold:
                release_points.append(i)
```

#### 3. Ball Tracking (`CustomBallTracker` in `test_tracking.py`)

The ball tracker uses a 3-tier hybrid approach for robust in-flight ball detection:

```python
class CustomBallTracker:
    """
    Detection priority:
    1. CSRT tracker (fast, handles motion blur between YOLO frames)
    2. Custom YOLOv8 model (accurate but slower, trained on basketball dataset)
    3. HSV color fallback (when both fail during flight)
    """

    def detect(self, frame, landmarks, shooting_side):
        # 1. Try CSRT update (fast — ~1ms)
        # 2. If CSRT fails/stale → run YOLO inference (~20ms)
        # 3. If YOLO succeeds → re-init CSRT with new bbox
        # 4. Both fail → HSV color + shape fallback

    def mark_release(self, wrist_pos):
        # Called by RealTimeReleaseDetector when shot released
        # Starts in_flight mode → begins tracking ball trajectory

    def end_flight(self):
        # Saves trajectory to all_flight_trajectories
        # Trajectory used by analyze_make_miss() for make/miss detection
```

**Key design:** The tracker is pre-loaded once at server startup (YOLO model load + MPS/CUDA warmup takes ~60s). Each request calls `reset()` to clear per-session state while reusing the loaded model.

**Make/miss detection:** `analyze_make_miss()` in `main.py` compares the ball flight trajectory against the user-calibrated rim position:
- Ball descending near rim center → Made (confidence based on proximity)
- Ball near rim but not through → Miss with direction (short/long, left/right)
- No rim data → Always returns `made=null` (Gemini prompt enforces this)

#### 4. AI Feedback (Google GenAI SDK)

Uses the new `google-genai` SDK (not deprecated `google-generativeai`):

```python
from google import genai
from google.genai import types

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Per-shot analysis with image frames
response = gemini_client.models.generate_content(
    model="gemini-2.0-flash",
    contents=[prompt_text, types.Part.from_bytes(data=jpg_bytes, mime_type="image/jpeg")]
)

# Returns JSON: {made, miss_type, form_rating, feedback, key_issue, quick_cue}
```

Shots are analyzed inline during video processing (not batched at the end) to naturally space Gemini requests and avoid rate limiting.

### Database Schema

```sql
-- User profiles (extends Supabase auth.users)
profiles (
  id UUID PRIMARY KEY,           -- Links to auth.users
  email TEXT,
  full_name TEXT,
  skill_level TEXT,              -- beginner/intermediate/advanced
  shooting_hand TEXT,            -- left/right
  height_inches INTEGER,
  subscription_tier TEXT,        -- free/pro/team
  total_sessions INTEGER,
  total_shots INTEGER,
  total_makes INTEGER
)

-- Practice sessions
sessions (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES profiles,
  started_at TIMESTAMP,
  shot_count INTEGER,
  make_count INTEGER,
  shooting_percentage DECIMAL,
  average_form_rating DECIMAL,
  session_feedback TEXT,         -- AI-generated summary
  drill_suggestions TEXT[]       -- Recommended drills
)

-- Individual shots
shots (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES sessions,
  shot_number INTEGER,
  made BOOLEAN,
  elbow_angle_load DECIMAL,
  elbow_angle_release DECIMAL,
  wrist_height_release DECIMAL,
  knee_bend_load DECIMAL,
  form_rating INTEGER,           -- 1-10
  feedback TEXT,                 -- AI feedback
  quick_cue TEXT,                -- One-liner tip
  thumbnail_url TEXT
)
```

---

## Current Status

### What's Working ✅
- [x] Video recording and upload
- [x] MediaPipe pose detection (33 landmarks)
- [x] Shot detection algorithm (release-backward via wrist trajectory)
- [x] Form metric calculations (elbow angles, knee bend, wrist height)
- [x] Custom YOLO ball tracking (CSRT + YOLO + HSV hybrid)
- [x] Programmatic make/miss detection (ball trajectory + user-calibrated rim)
- [x] Gemini AI per-shot feedback (google-genai SDK)
- [x] Gemini AI session summary + drill suggestions
- [x] Skeleton-overlay thumbnails per shot
- [x] Thumbnail upload to Supabase Storage
- [x] Session + shot persistence to Supabase
- [x] Session detail screen with full shot breakdown
- [x] Session history with sort/filter
- [x] User authentication (sign up, sign in, forgot password)
- [x] User onboarding (3-step flow)
- [x] User profile with stats
- [x] Rim calibration overlay (tap-to-set)
- [x] Shot marker timeline on video replay
- [x] 126 Jest tests across 4 test suites

### Known Issues 🟡

| # | Issue | Impact | Status |
|---|-------|--------|--------|
| 1 | Gemini rate limiting (429) | Analysis fails if too many rapid requests | Mitigated with retry + backoff; may need queue |
| 2 | Blocking I/O in async endpoint | API handles one video at a time | Use `asyncio.to_thread()` or background queue |
| 3 | Simulated progress bar | Progress stages are time-based, not real | Implement WebSocket/SSE for real progress |
| 4 | `live_analysis.py` is 2000+ lines | Hard to maintain | Split into separate modules |
| 5 | Console.log in production | Noise in logs | Replace with structured logging |
| 6 | No subscription/payment | All users have full access | Implement RevenueCat |

### Recently Resolved ✅

| Issue | Resolution |
|-------|-----------|
| App won't compile (duplicate exports) | Merged into single component |
| AuthProvider not wrapping app | Fixed in `_layout.tsx` |
| Router undefined error | Added `useRouter()` hook |
| No session history screen | Built history tab with sort/filter |
| No session detail screen | Built `session/[id].tsx` with full shot data |
| No thumbnail persistence | Thumbnails upload to Supabase Storage via `base64-arraybuffer` |
| YOLO model loaded every request (1+ min delay) | Pre-loaded at startup with GPU warmup |
| `google-generativeai` SDK deprecated | Migrated to `google-genai` SDK |
| Gemini guessing make/miss without rim data | Prompt now forces `made=null` when no rim |
| Ball tracking running every frame (slow) | Only tracks during ball flight |
| Blob constructor fails in React Native | Replaced with `base64-arraybuffer` decode |
| Video player cleanup on unmount | Added useEffect cleanup |
| No request timeout in API client | Added 3-minute AbortController timeout |

---

## Future Roadmap

### Phase 1: MVP Stability ✅ COMPLETE
- [x] Fix all critical bugs
- [x] Auth flow (sign up, sign in, forgot password)
- [x] Session history screen with sort/filter
- [x] Session detail screen with shot cards
- [x] User profile/settings screen
- [x] Supabase schema + persistence
- [x] Thumbnail persistence to Supabase Storage
- [x] 126 Jest tests

### Phase 2: Current — Beta Polish
- [ ] Resolve Gemini rate limiting (implement request queue or switch tier)
- [x] Real-time analysis progress (polling-based frame progress)
- [ ] API-side Supabase persistence (save results server-side so client timeout doesn't lose data)
- [ ] Async video processing (background queue)
- [ ] Test on physical iOS and Android devices
- [ ] Supabase Storage bucket policies for thumbnails
- [ ] Shot comparison (before/after overlays)
- [ ] Error boundaries in React

### Phase 3: Launch Prep
- [ ] Subscription/payment (RevenueCat)
- [ ] Push notifications
- [ ] App Store assets and listing
- [ ] Privacy policy, terms of service
- [ ] Beta testing (TestFlight/Internal Testing)
- [ ] Sentry error tracking
- [ ] Structured logging (replace console.log)

### Phase 4: Growth Features (Post-Launch)
- [ ] Social features (share achievements)
- [ ] Leaderboards
- [ ] Coaching marketplace
- [ ] Team management
- [ ] Advanced analytics dashboard
- [ ] Video library / cloud storage
- [ ] Offline mode with sync

### Phase 5: AI Enhancements
- [ ] Real-time feedback (live camera overlay)
- [ ] Voice coaching during practice
- [ ] Personalized training plans
- [ ] Progress prediction
- [ ] Form comparison with pros

---

## Potential Features

Ideas for future development, organized by category. None of these are committed — they represent directions the product could go.

### Analytics & Progress Tracking
- **Trend charts** — shooting % and form rating over time (weekly/monthly graphs)
- **Streak tracking** — consecutive makes, consecutive sessions, practice streaks
- **Heat maps** — miss direction distribution (short-left, long-right, etc.) visualized on a court diagram
- **Personal bests** — track and surface records (best session %, longest streak, highest form rating)
- **Form metric trends** — show how elbow angle, knee bend, etc. change across sessions
- **Session comparison** — side-by-side view of two sessions to see improvement

### Video & Replay
- **Slow-motion replay** — frame-by-frame scrubbing on shot detail screen
- **Side-by-side comparison** — overlay two shots (current vs personal best, or vs pro reference)
- **Annotated video export** — share a clip with skeleton overlay + form notes baked in
- **Cloud video storage** — save full session videos to Supabase Storage, replay later
- **Shot arc visualization** — draw the ball flight arc on the video frame

### AI Coaching
- **Real-time audio cues** — voice feedback during live recording ("bend your knees more")
- **Personalized training plans** — multi-week programs generated from form analysis history
- **Progress predictions** — "at your current improvement rate, you'll hit 60% in 2 weeks"
- **Pro form comparison** — overlay your skeleton against a pro shooter's form
- **Pre-shot routine analysis** — detect and score consistency of setup/dribble patterns
- **Fatigue detection** — track form degradation over long sessions

### Social & Community
- **Share session cards** — export a styled summary image to Instagram/Twitter
- **Leaderboards** — weekly/monthly accuracy rankings (opt-in, by skill level)
- **Challenges** — "100 shots in a week" or "improve 5% this month"
- **Coach mode** — a coach account that can view multiple players' sessions
- **Team dashboard** — aggregate stats for a team, identify who needs what drills

### Gamification
- **Badges/achievements** — "First session", "50% shooter", "10-session streak"
- **XP/levels** — earn experience from sessions, level up your profile
- **Daily goals** — configurable targets (shots per day, sessions per week)

### Hardware & Platform
- **Apple Watch companion** — start/stop recording, see quick stats on wrist
- **Multi-camera support** — front + side angle for 3D pose reconstruction
- **Smart hoop integration** — pull make/miss data from connected rims (e.g., HomeCourtAI, SIQ)
- **Offline mode** — record and analyze locally, sync when back online

### Monetization
- **Free tier** — 3 sessions/month, basic feedback
- **Pro tier ($9.99/mo)** — unlimited sessions, full analytics, trend charts, video export
- **Team tier ($29.99/mo)** — multi-player tracking, coach dashboard, team analytics
- **One-time purchase** — lifetime Pro access option

---

## Setup Instructions

### Prerequisites
- Node.js 20.19+ 
- Python 3.10+
- Expo CLI (`npm install -g expo-cli`)
- Supabase account
- Google Cloud account (for Gemini API)
- ngrok account (for local development)

### Backend Setup

```bash
# 1. Navigate to backend directory
cd backend

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file
cat > .env << EOF
GEMINI_API_KEY=your_gemini_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
EOF

# 5. Start the server
uvicorn main:app --host 0.0.0.0 --port 8000

# 6. In another terminal, start ngrok
ngrok http 8000
# Copy the https URL (e.g., https://abc123.ngrok.io)
```

### Mobile App Setup

```bash
# 1. Navigate to mobile directory
cd mobile

# 2. Install dependencies
npm install

# 3. Create .env file
cat > .env << EOF
EXPO_PUBLIC_API_URL=https://your-ngrok-url.ngrok.io
EXPO_PUBLIC_SUPABASE_URL=your_supabase_url
EXPO_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
EOF

# 4. Fix any version mismatches
npx expo install --fix

# 5. Check for issues
npx expo-doctor

# 6. Start development server
npx expo start --clear
```

### Supabase Setup

1. Create new Supabase project
2. Go to SQL Editor
3. Paste and run `supabase-schema.sql`
4. Go to Authentication → Settings
5. Enable Email provider
6. Copy project URL and anon key to `.env` files

### Testing the Full Stack

```bash
# Terminal 1: Backend
cd backend && uvicorn main:app --port 8000

# Terminal 2: ngrok
ngrok http 8000

# Terminal 3: Mobile
cd mobile && npx expo start

# Scan QR code with Expo Go app
# Test login → record → analyze flow
```

---

## Technical Debt

### High Priority
1. **Monolithic `live_analysis.py`** (2000+ lines) - Split into pose_detector, shot_detector, gemini_client modules
2. **Blocking API** - Video processing blocks the event loop; use `asyncio.to_thread()` or Celery
3. **No API tests** - 126 mobile tests exist, but zero API/backend tests
4. **Gemini rate limiting** - 429 errors during multi-shot analysis; need request queue or higher tier
5. **No error tracking** - Add Sentry or similar for production

### Medium Priority
1. **No CI/CD** - Set up GitHub Actions for test + lint on PR
2. **No linting** - Add ESLint + Prettier for mobile, flake8/black for API
3. **Supabase Storage policies** - Ensure `thumbnails` bucket has proper RLS policies
4. **Shared ball tracker is not thread-safe** - Single `_shared_ball_tracker` instance; fine for single-user but breaks with concurrent requests
5. **No structured logging** - Replace `print()` with Python `logging` module

### Low Priority
1. **Magic numbers** - Extract thresholds to constants (rim_radius %, make_threshold, etc.)
2. **Inconsistent naming** - `test_tracking.py` should be renamed (it's not just tests)
3. **Bundle size** - Analyze and optimize mobile JS bundle
4. **Accessibility** - Add screen reader labels to mobile UI
5. **API docs** - FastAPI auto-generates Swagger at `/docs`, but descriptions are minimal

---

## Recommendations

### Immediate Actions (Before Testing)
1. Apply the fixed files from this review
2. Run `npx expo install --fix`
3. Run `npx expo-doctor`
4. Test auth flow end-to-end
5. Test video recording and analysis

### Before Beta Launch
1. Split `live_analysis.py` into modules
2. Implement proper async video processing
3. Add error boundaries in React
4. Set up proper logging
5. Add basic unit tests for shot detection

### Before Production Launch
1. Implement subscription system
2. Set up error tracking (Sentry)
3. Add analytics (Mixpanel/Amplitude)
4. Performance testing
5. Security audit
6. Load testing for API

### Architecture Improvements
1. Consider moving video processing to cloud (AWS Lambda, Cloud Run)
2. Add job queue for background processing (Celery, Bull)
3. Implement caching for Gemini responses
4. Add CDN for thumbnail storage
5. Consider GraphQL for flexible data fetching

---

## Contact & Resources

### Documentation
- [Expo Documentation](https://docs.expo.dev)
- [Supabase Documentation](https://supabase.com/docs)
- [MediaPipe Pose](https://developers.google.com/mediapipe/solutions/vision/pose_landmarker)
- [Gemini AI](https://ai.google.dev/docs)

### Key Files to Review
1. `live_analysis.py` - Core algorithm (understand shot detection)
2. `main.py` - API structure
3. `AuthContext.tsx` - Auth state management
4. `record.tsx` - Main user flow

---

*This document should be updated as the project evolves. Last review: January 30, 2026*
