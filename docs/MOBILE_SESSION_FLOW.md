# Mobile Session Recording Flow

Technical reference for how the FormCheck mobile app handles video recording, analysis, and data persistence. Companion to `CAMERA_PROCESSING_PIPELINE.md` which covers the backend.

---

## Architecture Overview

```
User Action (Record/Upload)
    |
    v
RecordingCamera ──────────────> video URI
    |
    v
RimCalibrationOverlay ────────> rimPosition {x, y} or null
    |
    v
analyzeVideoFile()
    |
    ├──> db.createSession()     (Supabase - create placeholder)
    |
    ├──> analyzeVideoWithProgress()  (API call)
    |         |
    |         v
    |    POST /analyze ─────────> SessionSummary JSON
    |
    ├──> db.updateSession()     (Supabase - fill in results)
    |
    ├──> db.uploadThumbnail()   (Supabase Storage - per shot)
    |
    └──> db.createShots()       (Supabase - shot records)
    |
    v
Results View (inline in record.tsx)
    |
    v
Session Detail (session/[id].tsx via History tab)
```

---

## Key Files

| File | Role |
|------|------|
| `app/(tabs)/record.tsx` | Main orchestrator - state machine, API calls, results display |
| `app/(tabs)/history.tsx` | Session list view |
| `app/session/[id].tsx` | Session detail view (from history) |
| `components/Camera.tsx` | Video recording with expo-camera |
| `components/RimCalibrationOverlay.tsx` | Rim position selection UI |
| `components/ShotMarkerTimeline.tsx` | Shot markers on video timeline |
| `lib/api.ts` | API client, types (ShotAnalysis, SessionSummary) |
| `lib/supabase.ts` | Database client, types (Shot, Session, Profile) |
| `contexts/AuthContext.tsx` | User/profile state |

---

## State Machine (record.tsx)

The record screen uses multiple boolean states that control which view is rendered:

```
                                    ┌─────────────────┐
                                    │  Initial View   │
                                    │  (Start/Upload) │
                                    └────────┬────────┘
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    │                        │                        │
                    v                        v                        v
            ┌───────────────┐      ┌─────────────────┐      ┌─────────────────┐
            │ showCamera    │      │ handlePickVideo │      │ (already have   │
            │ = true        │      │ (ImagePicker)   │      │  result)        │
            └───────┬───────┘      └────────┬────────┘      └─────────────────┘
                    │                       │
                    └───────────┬───────────┘
                                │
                                v
                    ┌─────────────────────┐
                    │  showCalibration    │
                    │  = true             │
                    │  (RimCalibration)   │
                    └──────────┬──────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          v                    v                    v
    handleRimConfirm    handleRimSkip      handleRimNotVisible
    (rimPos set)        (rimPos null)      (rimPos null)
          │                    │                    │
          └────────────────────┼────────────────────┘
                               │
                               v
                    ┌─────────────────────┐
                    │  analyzing = true   │
                    │  (Loading View)     │
                    └──────────┬──────────┘
                               │
                               v
                    ┌─────────────────────┐
                    │  result != null     │
                    │  (Results View)     │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              v                v                v
       startNewRecording  startVideoUpload   (navigate away)
       (reset all state)  (reset all state)  (useFocusEffect
                                              resets on return)
```

### Render Priority

The render logic checks states in this order (first match wins):

```typescript
if (showCamera) return <RecordingCamera />;
if (showCalibration) return <RimCalibrationOverlay />;
if (analyzing) return <LoadingView />;
if (result) return <ResultsView />;
return <InitialView />;  // Start Recording / Upload buttons
```

### Key State Variables

| State | Type | Purpose |
|-------|------|---------|
| `showCamera` | boolean | Show camera recording UI |
| `showCalibration` | boolean | Show rim calibration overlay |
| `pendingVideoUri` | string \| null | Video awaiting calibration |
| `currentVideoUri` | string \| null | Video being analyzed/displayed |
| `rimPosition` | {x, y} \| null | Normalized rim coordinates (0-1) |
| `analyzing` | boolean | API call in progress |
| `result` | SessionSummary \| null | Analysis results |
| `analysisProgress` | AnalysisProgress | Stage, progress %, message |
| `sessionId` | string \| null | Supabase session ID |

---

## Data Flow: API Response to Supabase

### 1. Create Session (before API call)

```typescript
const session = await db.createSession({
  shooting_hand: shootingSide,
  focus_area: profile?.focus_areas?.[0],
});
// Returns: { id, user_id, started_at, shot_count: 0, ... }
```

### 2. API Analysis

```typescript
const analysis = await analyzeVideoWithProgress(
  uri,
  shootingSide,
  onProgress,    // Updates analysisProgress state
  rimPosition,   // null if not set
  undefined,     // playerId (unused)
  sessionId      // For progress polling
);
// Returns: SessionSummary
```

### 3. Update Session (after API returns)

```typescript
await db.updateSession(sessionId, {
  ended_at: new Date().toISOString(),
  shot_count: analysis.total_shots,
  make_count: analysis.shots_made,
  miss_count: analysis.shots_missed,
  shooting_percentage: analysis.shooting_percentage,
  average_form_rating: analysis.average_form_rating,
  session_feedback: analysis.session_feedback,
  drill_suggestions: analysis.drill_suggestions,
});
```

### 4. Upload Thumbnails + Create Shots

```typescript
const shotRecords = await Promise.all(
  analysis.shots.map(async (shot) => {
    // Upload thumbnail to Supabase Storage
    const thumbnailUrl = await db.uploadThumbnail(
      sessionId,
      shot.shot_number,
      shot.thumbnail  // base64
    );

    return {
      session_id: sessionId,
      shot_number: shot.shot_number,
      made: shot.made,
      miss_type: shot.miss_type,
      elbow_angle_load: shot.elbow_angle_load,
      elbow_angle_release: shot.elbow_angle_release,
      wrist_height_release: shot.wrist_height_release,
      knee_bend_load: shot.knee_bend_load,
      form_rating: shot.form_rating,
      feedback: shot.feedback,
      key_issue: shot.key_issue,
      quick_cue: shot.quick_cue,
      camera_angle: shot.camera_angle,
      thumbnail_url: thumbnailUrl,
    };
  })
);

await db.createShots(shotRecords);
```

---

## Type Mapping: API → Supabase

| API (ShotAnalysis) | Supabase (Shot) | Notes |
|--------------------|-----------------|-------|
| `shot_number` | `shot_number` | Direct |
| `made` | `made` | boolean \| null |
| `miss_type` | `miss_type` | string \| null |
| `form_rating` | `form_rating` | number \| null |
| `feedback` | `feedback` | string |
| `key_issue` | `key_issue` | string \| null |
| `quick_cue` | `quick_cue` | string \| null |
| `elbow_angle_load` | `elbow_angle_load` | number |
| `elbow_angle_release` | `elbow_angle_release` | number |
| `wrist_height_release` | `wrist_height_release` | number |
| `knee_bend_load` | `knee_bend_load` | number |
| `camera_angle` | `camera_angle` | string \| null |
| `thumbnail` (base64) | `thumbnail_url` (URL) | Uploaded to Storage |
| `timestamp` | - | Not persisted |

---

## Components

### RecordingCamera

**Location**: `components/Camera.tsx`

- Uses `expo-camera` for video recording
- Manages camera permissions
- Returns video URI via `onVideoRecorded` callback
- Has cancel button via `onCancel`

### RimCalibrationOverlay

**Location**: `components/RimCalibrationOverlay.tsx`

- Displays first frame of video as background
- User taps to mark rim position
- Normalizes tap coordinates to 0-1 range
- Three exit paths:
  - `onConfirm(position)` — rim marked
  - `onSkip()` — user skipped
  - `onRimNotVisible()` — rim not in frame
- `onChangeVideo()` — select different video

### ShotMarkerTimeline

**Location**: `components/ShotMarkerTimeline.tsx`

- Displays shot markers on video timeline
- Each marker shows shot number and made/miss indicator
- Tap marker to seek video via `onSeek(timestamp)`
- Positioned below video player in results view

---

## Progress Polling

The API supports real-time progress updates via polling:

```typescript
// In api.ts
export async function analyzeVideoWithProgress(
  videoUri: string,
  shootingHand: 'left' | 'right',
  onProgress: ProgressCallback,
  rimPosition?: RimPosition | null,
  playerId?: number,
  sessionId?: string
): Promise<SessionSummary>
```

Progress stages:
1. `uploading` (0-10%)
2. `detecting` (10-75%) — scanning frames for shots
3. `analyzing` (75-90%) — Gemini processing each shot
4. `generating` (90-99%) — session summary
5. `complete` (100%)

The progress is polled every 1.5 seconds from `GET /progress/{sessionId}`.

---

## Session Detail (History View)

**Location**: `app/session/[id].tsx`

Loads session and shots from Supabase (not from API):

```typescript
const [sessionData, shotsData] = await Promise.all([
  db.getSession(id),
  db.getShots(id),
]);
```

Displays:
- Session summary stats
- Drill suggestions
- Session feedback
- Shot cards with:
  - Thumbnail (from `thumbnail_url`)
  - Camera angle badge
  - Made/miss badge
  - Form rating bar
  - Feedback text
  - Metric pills (elbow angles, wrist height, knee bend)

---

## Navigation Reset Behavior

When user navigates away from results and returns (e.g., Home → Record tab), the screen resets to initial state via `useFocusEffect`:

```typescript
useFocusEffect(
  useCallback(() => {
    // On focus: reset if we had results when we left
    if (hadResultOnBlur.current) {
      setResult(null);
      setCurrentVideoUri(null);
      // ... reset other state
      hadResultOnBlur.current = false;
    }

    return () => {
      // On blur: remember if showing results
      if (result && !analyzing) {
        hadResultOnBlur.current = true;
      }
    };
  }, [result, analyzing])
);
```

This ensures "Start Recording" from Home always starts fresh.

---

## Error Handling

### Thumbnail Upload Failure

```typescript
try {
  thumbnailUrl = await db.uploadThumbnail(...);
} catch (thumbErr) {
  console.warn(`Thumbnail upload failed for shot ${shot.shot_number}:`, thumbErr);
  // thumbnailUrl stays null, shot still saved
}
```

**Common issue**: `Bucket not found` error means the `thumbnails` bucket doesn't exist in Supabase Storage. Create it via Dashboard or SQL.

### Database Save Failure

```typescript
try {
  await db.createShots(shotRecords);
} catch (dbError) {
  console.warn('Could not save session to database:', dbError);
  // Analysis still displayed, just not persisted
}
```

### API Failure

Caught in main try/catch, sets `error` state, displays error message to user.

---

## Supabase Schema Requirements

### Tables

```sql
-- sessions
id UUID PRIMARY KEY
user_id UUID REFERENCES auth.users
started_at TIMESTAMPTZ
ended_at TIMESTAMPTZ
shot_count INTEGER
make_count INTEGER
miss_count INTEGER
shooting_percentage REAL
average_form_rating REAL
session_feedback TEXT
drill_suggestions TEXT[]
shooting_hand TEXT
focus_area TEXT
-- ... other fields

-- shots
id UUID PRIMARY KEY
session_id UUID REFERENCES sessions ON DELETE CASCADE
user_id UUID REFERENCES auth.users
shot_number INTEGER
made BOOLEAN
miss_type TEXT
elbow_angle_load REAL
elbow_angle_release REAL
wrist_height_release REAL
knee_bend_load REAL
form_rating REAL
feedback TEXT
key_issue TEXT
quick_cue TEXT
camera_angle TEXT
thumbnail_url TEXT
created_at TIMESTAMPTZ
```

### Storage

Bucket: `thumbnails` (public)

File path pattern: `{user_id}/{session_id}/shot_{number}.jpg`
