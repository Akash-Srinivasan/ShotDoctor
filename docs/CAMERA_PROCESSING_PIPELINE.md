# Camera Processing Pipeline

Technical reference for how FormCheck processes video from camera input through to shot analysis. Written for future development sessions to avoid re-reading the entire codebase.

---

## Architecture Overview

```
Video File
    |
    v
PoseDetector (MediaPipe)  -->  landmarks + visibility per frame
    |
    v
LiveShotDetector          -->  detects shots via release-backward algorithm
    |                          also detects camera angle per-shot
    v
ShotEvent (dataclass)     -->  frames, metrics, camera_angle
    |
    v
api/main.py /analyze      -->  angle-specific Gemini prompt
    |
    v
ShotAnalysis (JSON)       -->  sent to mobile app
```

## Key Files

| File | Role |
|------|------|
| `api/core/live_analysis.py` | PoseDetector, LiveShotDetector, ShotEvent, detect_camera_angle |
| `api/core/biomechanics.py` | OptimalRange constants, research-backed reference values |
| `api/main.py` | FastAPI endpoint, Gemini prompts, ShotAnalysis model, **server-side Supabase persistence** |
| `api/core/ball_tracker.py` | YOLO ball detection, CustomBallTracker, trajectory tracking |
| `api/core/rim_detector.py` | Rim position/size detection (Hough circles + YOLO + color), **active in production** |
| `api/core/rim_area_classifier.py` | Binary classifier for rim-area outcome frame crops (make/miss signal) |
| `mobile/lib/api.ts` | TypeScript ShotAnalysis interface, API client |
| `mobile/lib/supabase.ts` | Shot/Session DB types, createShots/createSession (fallback) |
| `mobile/app/(tabs)/record.tsx` | Video recording, upload, results display |
| `mobile/app/session/[id].tsx` | Session detail view, ShotCard with angle badge + metrics |
| `mobile/components/ErrorBoundary.tsx` | Crash recovery — wraps every screen for beta resilience |
| `api/core/test_camera_angle.py` | CLI test script for angle detection (`--shots` mode) |

---

## Shot Detection (LiveShotDetector)

**Location**: `api/core/live_analysis.py`, class `LiveShotDetector`

### Algorithm: Release-Backward

1. **Detect RELEASE**: elbow angle > 155 deg AND wrist above shoulder, sustained for `STABILITY_REQUIRED` (8) frames
2. **Look BACKWARD** in buffer to find LOAD: the frame with minimum elbow angle
3. **Extract 13 frames**: 2 pre-stance (footwork, 15 and 10 before load), stance (5 before load), dip (between stance and load), load, 4 evenly-spaced mid-points, release, 3 follow-through frames (3, 8, 15 after release)

### Buffers

All buffers are synchronized by index and trimmed together at `max_buffer` (180 frames):
- `frames_buffer` -- raw BGR frames (numpy arrays)
- `landmarks_buffer` -- dict of normalized (x, y) landmark positions
- `visibility_buffer` -- dict of per-landmark visibility scores (0-1)
- `elbow_angles` -- computed elbow angle per frame (or None)
- `wrist_heights` -- wrist Y position per frame

### Cooldown

`COOLDOWN_FRAMES = 45` -- minimum frames between shot detections to avoid double-counting the same motion.

---

## Camera Angle Detection

**Location**: `api/core/live_analysis.py`, methods on `LiveShotDetector`

### Approach: Per-Shot Detection

Camera angle is detected **during each shot's load-to-release window**, not from arbitrary frames at video start. This is more reliable because:
- The person is guaranteed to be in frame and in shooting pose
- MediaPipe has better landmark quality during active motion

### How It Works

1. `detect_angle_from_shot(load_idx, release_idx)` iterates landmarks from load to release
2. For each frame, `compute_shoulder_ratio(landmarks)` computes:
   ```
   ratio = shoulder_spread / torso_height
   ```
   where `shoulder_spread = abs(left_shoulder.x - right_shoulder.x)` and `torso_height = abs(avg_shoulder.y - avg_hip.y)`
3. Takes the **median** ratio across all frames in the window
4. `classify_angle(ratio)` classifies:
   - `ratio > 0.6` --> **front**
   - `ratio < 0.25` --> **side**
   - otherwise --> **angled**

### Confidence Scaling

Confidence represents how far the median ratio is from the nearest classification boundary, scaled to realistic ranges:

| Angle | Formula | Rationale |
|-------|---------|-----------|
| Front | `(ratio - 0.6) / 0.20` | Typical front ratio is 0.8+; hits 1.0 at 0.80 |
| Side | `(0.25 - ratio) / 0.15` | MediaPipe floor is ~0.05; hits 1.0 at 0.10 |
| Angled | `dist_to_nearest_edge / 0.175` | Peaks at midpoint of angled range |

### Important: MediaPipe Limitations

- **MediaPipe always places both shoulder landmarks**, even from pure side view. The far-side shoulder just overlaps with the near side, giving a low (but non-zero) ratio. This is why the side-view confidence denominator is 0.15 rather than 0.25.
- **Visibility scores are unreliable for side-view detection.** MediaPipe reports ~1.0 visibility for both shoulders even when one is fully occluded. Do not use visibility asymmetry as a signal.
- The standalone `detect_camera_angle(pose, cap, num_frames)` function still exists for quick first-N-frames detection but is **not used in production**. The per-shot method is the primary approach.

### Debug Output

When a shot is detected, `_save_debug_frame()` writes an annotated JPEG to `api/core/debug_frames/` with:
- Shoulder/hip landmarks drawn as colored circles
- Line between shoulders
- Camera angle, confidence, and ratio overlaid as text
- File named `shot_001_side.jpg`, etc.

---

## Make/Miss Detection Pipeline

**Location**: `api/main.py` (`analyze_make_miss()`, `analyze_shot_with_gemini()`) and `api/core/test_tracking.py` (`CustomBallTracker`, `RealTimeReleaseDetector`)

### 1. Ball Trajectory Tracking

`RealTimeReleaseDetector` fires on elbow extension (> 145 deg) + wrist apex (2+ frames descending). On release, `CustomBallTracker` runs YOLO ball detection frame-by-frame. Trajectories with >= 2 points are saved.

### 2. Trajectory Cleaning

Raw trajectories contain noise from false detections, reflections, and other objects. `_clean_trajectory()` and segment-based filtering in `analyze_make_miss()` split trajectories at "impossible jumps" (consecutive points > 5% of frame diagonal apart), producing clean contiguous segments. The segment whose closest point to the rim is smallest is selected for analysis.

**Log line**: `🧹 Trajectory cleaned: X → Y points (N segments found)`

### 3. Trajectory Extrapolation

When the clean segment doesn't reach the rim (closest point > 4x rim radius away) and has >= 5 points, a parabola is fitted using `numpy.polyfit(xs, ys, 2)` (same approach as avishah3 project, 95% accuracy claimed). Up to 40 predicted points are extrapolated toward the rim.

**Log line**: `🔮 Extrapolated N predicted points (parabola a=..., toward rim)`

### 4. Through-Hoop Detection

**New approach** (from bballvision/bolota.eu research): Above-below rim intersection test:
1. Find the LAST point above rim Y (within 3x rim-radius horizontally)
2. Find the FIRST point below rim Y after that
3. Interpolate a line between those two points
4. Calculate where the line crosses rim Y
5. If crossing X is within rim opening (2.5x rim-radius tolerance) → through-hoop = true

Falls back to old consecutive-frame method (checking for above→below crossing within 2x rim-radius horizontal window). Key improvement: works even with gaps in tracking data near the rim.

### 4b. Rim Detection & Sizing

**Location**: `api/main.py` (`_run_analysis()`), `api/core/rim_detector.py`

At the start of video processing (before the main frame loop), the `RimDetector` is activated to auto-calibrate rim dimensions:

1. Sample 5-8 frames from the first 2 seconds of video
2. Run Hough circle detection on each frame
3. If user provided `rim_x`/`rim_y`, filter detections to the one **closest** to the user-marked position (handles multi-rim courts)
4. Take the **median** width and center across successful detections
5. Require >= 3 agreeing frames for confidence

**Output**: `detected_rim_radius_px` (pixel-accurate rim radius) replaces the old hardcoded `frame_width * 0.02` guess. If detection fails, the 2% heuristic is used as fallback.

**Multi-rim handling**: When the user has calibrated a rim position, `detect_all()` returns ALL detected circles, but only the one nearest to the user's marked point (within 20% of frame diagonal) is used. This prevents confusion from background hoops.

### 5. Classification Thresholds

| Check | Threshold | Result |
|-------|-----------|--------|
| Through-hoop + ball near rim | `min_dist < make_threshold * 3` | `made=True`, conf >= 0.65 |
| Close + descending | `min_dist < rim_radius * 1.5` | `made=True`, conf >= 0.50 |
| Near miss | `min_dist < rim_radius * 4.0` | `made=False` with directional miss_type |
| Far from rim | Beyond near_threshold | `made=None` |

Key params: `rim_radius` = auto-detected via RimDetector (Hough circles from early video frames), with `frame_width * 0.02` fallback. `make_threshold = rim_radius * 1.5`, `near_threshold = rim_radius * 4.0`

### 6. Camera Angle Confidence

Trajectory analysis is 2D — reliability depends on camera perspective. Confidence multiplier applied to ALL trajectory results:
- **Side**: ×1.0 (full arc visible, crossing clearly detectable)
- **Angled**: ×0.7 (depth partially compressed)
- **Front**: ×0.4 (depth fully compressed, can't distinguish through-hoop from near-miss)

This naturally shifts the tiered decision system toward trusting Gemini for front/angled views.

### 7. Gemini Vision

Same three prompt branches (A: trajectory guidance, B: rim only, C: no rim). **New**: Outcome frames are now **cropped around the rim area** (~15% of frame in each direction) before sending to Gemini. This gives Gemini a zoomed-in view of ball-rim interaction instead of a tiny ball in a wide-angle shot. Prompt updated to inform Gemini that frames are cropped.

### 8. Tiered Decision Hierarchy

**Active strategy: H** (raw-trajectory-first). Strategy K (with rim-area classifier) is logged for comparison but not yet active.

**Strategy H (active):**
```
Tier 1: No rim position → null (can't judge)
Tier 2: Trajectory + Gemini AGREE → use their answer (highest confidence)
Tier 3: High-confidence trajectory (≥65%) → trust trajectory over Gemini
Tier 4: Medium trajectory (≥45%) + Gemini null → use trajectory
Tier 5: Gemini has opinion + trajectory missing/weak → trust Gemini
Tier 6: Both unclear → null
```

**Strategy K (logged, pending validation):**
```
Tier 1: No rim position → null
Tier 2: Trajectory + classifier AGREE → use their answer (highest confidence)
Tier 3: High-confidence trajectory (≥65%) → trust trajectory
Tier 4: High-confidence classifier (≥70%) → can override weak trajectory
Tier 5: Trajectory + Gemini agree → use their answer
Tier 6: Gemini has opinion → trust Gemini
Tier 7: Both unclear → null
```

Strategy K adds the rim-area classifier as a 3rd signal. The classifier is especially valuable during **occlusion** (ball hidden behind rim/net) when trajectory data is incomplete but the classifier can still see net movement.

### 9. Rim-Area Classifier

**Location**: `api/core/rim_area_classifier.py`, integrated via `_shared_rim_classifier` in `api/main.py`

A YOLOv8n-cls binary classifier trained on Roboflow `basketball-lhqoe` dataset crops:

- **Input**: 128x128 crops centered on the detected rim bounding box, from outcome frames
- **Classes**: `ball_through_hoop` vs `ball_not_through_hoop`
- **Multi-frame voting**: Runs on all outcome frame crops for a shot
  - >= 2 frames show "through" with conf > 0.6 → `made=True`
  - 0 frames show "through" → `made=False`
  - Otherwise → `made=None` (unclear)
- **Performance**: ~10-20MB loaded, ~5ms per crop, ~30ms total per shot (batch of ~14 crops)
- **Occlusion-aware**: When trajectory has gaps from occlusion, classifier gets more weight in Strategy K since it can detect net movement even when ball tracking fails

### 10. Diagnostic Logging

Every shot logs the decision chain:
- `🧹 Trajectory cleaned: X → Y points (N segments found)`
- `🔮 Extrapolated N predicted points ...` (when triggered)
- `📐 analyze_make_miss: ...` (now includes `angle=side (×1.0)`)
- `📊 Shot #N decision: gemini_raw=..., trajectory=..., final=..., source=...` (now shows tier-based source labels like `agreement`, `trajectory-high-conf`, `gemini-primary`, etc.)

Check Railway logs for these lines to debug make/miss accuracy.

---

## Angle-Specific Gemini Prompts

**Location**: `api/main.py`, inside `analyze_shot_with_gemini()`

The Gemini prompt changes based on `shot_event.camera_angle`:

### Side View
- Tells Gemini all angle metrics are **reliable**
- Includes optimal ranges: elbow load 50-70 deg, release 130-165 deg, knee 95-115 deg
- Focus areas: shot sequencing (legs-to-arms), follow-through, arc, balance, release timing
- Explicitly says: "Do NOT comment on elbow alignment or guide hand"

### Front View
- Tells Gemini angle measurements are **UNRELIABLE** from this perspective
- Focus areas: elbow alignment (tucked vs flared), ball path, stance width, shoulder symmetry, landing
- Explicitly says: "Do NOT comment on specific angle values"

### Angled
- Notes angles are **approximate**
- Lets Gemini comment on whatever it can clearly observe

### Motion Quality Analysis (All Views)

All prompts now include motion quality metrics (hitch count, smoothness, pocket sweep, dip depth) and instruct Gemini to look for:
- **Hitches/stutters** in the shooting motion (pauses during the upward phase)
- **Shooting pocket path** (whether the ball goes straight up or sweeps laterally)
- **Dip depth** (how deep the ball drops before the set point)
- **Footwork patterns** (1-step, 2-step, shuffle, jump stop — from pre-stance frames)
- **Off-hand/guide hand interference** (thumb coming forward — from follow-through frames)

Per-shot feedback is no longer limited to 15 words — Gemini now provides 1-2 sentence coaching feedback.

---

## Biomechanics Reference Ranges

**Location**: `api/core/biomechanics.py`

Based on Cabarkapa et al. (2022) and related research. All values use `OptimalRange(min_val, max_val, ideal, unit)`.

All 11 metrics are computed in `_create_shot_from_release()` and wired through the full pipeline (ShotEvent → ShotAnalysis → Supabase → mobile UI). Side-view metrics are only computed when `camera_angle in ('side', 'angled')`. Front-view metrics are only computed when `camera_angle in ('front', 'angled')`.

### Side-View Metrics (PRIMARY — computed for side + angled views)

| Metric | Field | Min | Ideal | Max | Unit | Method | Notes |
|--------|-------|-----|-------|-----|------|--------|-------|
| Elbow angle (load) | `elbow_angle_load` | 50 | 60 | 70 | deg | elbow angle tracking | Interior angle at set point |
| Elbow angle (release) | `elbow_angle_release` | 130 | 150 | 165 | deg | elbow angle tracking | NOT full extension |
| Knee bend (load) | `knee_bend_load` | 95 | 107 | 115 | deg | `_calculate_knee_bend` | Interior knee angle |
| Release height | `wrist_height_release` | 1.05 | 1.20 | 1.40 | x shoulder | `_calculate_wrist_height` | Wrist height normalized to torso |
| Hip angle (load) | `hip_angle_load` | 120 | 132 | 145 | deg | `_calculate_hip_angle` | Shoulder-hip-knee angle at load |
| Elbow height (load) | `elbow_height_load` | 0.8 | 0.95 | 1.1 | normalized | `_calculate_elbow_height` | 0=hip, 1=shoulder level |
| Heel height (release) | `heel_height_release` | 0.05 | 0.10 | 0.15 | normalized | `_calculate_heel_height` | Ankle rise from load to release / torso height |
| Trunk lean (release) | `trunk_lean_release` | -3 | 0 | 3 | deg | `_calculate_trunk_lean` | Degrees from vertical; negative = forward lean |

### Front-View Metrics (SUPPLEMENTARY — computed for front + angled views)

| Metric | Field | Optimal Range | Unit | Method | Notes |
|--------|-------|---------------|------|--------|-------|
| Stance width | `stance_width` | 0.9 – 1.2 | ratio | `_calculate_stance_width` | Ankle spread / shoulder width |
| Shoulder level diff | `shoulder_level_diff` | 0.0 – 0.1 | ratio | `_calculate_shoulder_level_diff` | Shooting shoulder Y diff / torso height; positive = shooting shoulder higher |
| Elbow lateral offset | `elbow_lateral_offset` | 0.0 – 0.15 | ratio | `_calculate_elbow_lateral_offset` | Elbow X offset from shoulder / shoulder width; 0 = directly under |

### Motion Quality Metrics (ALL VIEWS — computed for every shot)

| Metric | Field | Optimal Range | Unit | Method | Notes |
|--------|-------|---------------|------|--------|-------|
| Hitch count | `hitch_count` | 0 | count | `_calculate_hitch_metrics` | Number of velocity reversals during upward phase; 0 = smooth |
| Hitch severity | `hitch_severity` | 0.0 | ratio | `_calculate_hitch_metrics` | Max wrist drop during hitch / torso height |
| Motion smoothness | `motion_smoothness` | 1.0–1.3 | ratio | `_calculate_hitch_metrics` | Actual path length / straight-line distance; 1.0 = perfect |
| Pocket lateral sweep | `pocket_lateral_sweep` | 0.0–0.05 | ratio | `_calculate_pocket_sweep` | Max horizontal wrist deviation / shoulder width |
| Dip depth | `dip_depth` | 0.0–0.3 | ratio | `_calculate_dip_depth` | How far wrist goes below hip / torso height; 0 = no dip |

### Metric Calculation Details

All metric methods live on `LiveShotDetector` in `api/core/live_analysis.py`.

**Hip angle** (`_calculate_hip_angle`): Interior angle at hip joint (shoulder → hip → knee). Measured at the load frame. Lower values mean the player is sitting deeper into the shot.

**Elbow height** (`_calculate_elbow_height`): Elbow Y position normalized to torso. 0 = hip level, 1 = shoulder level. Measured at the load frame. Values above 1.0 mean the elbow is above the shoulder.

**Heel height** (`_calculate_heel_height`): Takes BOTH load and release landmarks. Computes the ankle Y rise from load to release, normalized by torso height. Positive values mean the player got up on their toes at release.

**Trunk lean** (`_calculate_trunk_lean`): Angle of the hip-to-shoulder vector from vertical, in degrees. 0 = perfectly upright. Negative = leaning forward. Measured at the release frame.

**Stance width** (`_calculate_stance_width`): Horizontal distance between ankles divided by shoulder width. Only meaningful from the front view where both ankles are visible.

**Shoulder level diff** (`_calculate_shoulder_level_diff`): Difference in Y position between the shooting and non-shooting shoulder, normalized by torso height. Positive = shooting shoulder is higher (expected during release).

**Elbow lateral offset** (`_calculate_elbow_lateral_offset`): How far the shooting elbow is from directly under the shooting shoulder, normalized by shoulder width. 0 = perfectly tucked, higher = more flared.

**Hitch detection** (`_calculate_hitch_metrics`): Tracks wrist Y velocity frame-by-frame from load to release. A hitch is detected when upward velocity reverses (wrist drops back down) then resumes upward. Returns count of hitches, severity of worst hitch (normalized by torso height), and overall path smoothness ratio.

**Pocket lateral sweep** (`_calculate_pocket_sweep`): Tracks wrist X position from stance to release. Computes the maximum horizontal deviation from the straight line connecting start and end positions, normalized by shoulder width. Higher values indicate the ball sweeps sideways on the way up.

**Dip depth** (`_calculate_dip_depth`): Finds the lowest wrist Y position between stance and load frames. Measures how far below hip level the wrist drops, normalized by torso height. A deeper dip means the ball drops lower before coming up to the set point.

---

## Data Flow: API to Mobile

### ShotEvent (Python dataclass)
Produced by `LiveShotDetector._create_shot_from_release()`. Contains raw frames and computed metrics. Lives only during the `/analyze` request.

### ShotAnalysis (Pydantic model / JSON response)
Returned by the `/analyze` endpoint. Fields:
```
shot_number, made, miss_type, form_rating, feedback, key_issue, quick_cue,
elbow_angle_load, elbow_angle_release, wrist_height_release, knee_bend_load,
hip_angle_load, elbow_height_load, heel_height_release, trunk_lean_release,
stance_width, shoulder_level_diff, elbow_lateral_offset,
hitch_count, hitch_severity, motion_smoothness, pocket_lateral_sweep, dip_depth,
camera_angle, thumbnail (base64), timestamp
```

### Shot (Supabase table)
Persisted to `shots` table. Same fields as ShotAnalysis but with:
- `thumbnail_url` instead of `thumbnail` (uploaded to Supabase storage)
- `camera_angle` column (TEXT, nullable)
- `session_id` and `user_id` foreign keys
- All 11 metric columns (REAL DEFAULT 0.0)

**Primary write path**: API server writes directly using `supabase-py` with `service_role` key after analysis completes. Mobile client only writes as a fallback if `server_persisted` is false.

### Session (Supabase table)
Created by mobile client before analysis (placeholder), updated by API server after analysis with final stats (shot_count, make_count, shooting_percentage, etc.) and session-level Gemini feedback.

---

## Test Script

**Location**: `api/core/test_camera_angle.py`

```bash
# Quick first-N-frames check (uses standalone detect_camera_angle)
python test_camera_angle.py video.mp4

# Frame-by-frame ratio analysis
python test_camera_angle.py video.mp4 --verbose

# Full shot detection with per-shot angle + debug frame output
python test_camera_angle.py video.mp4 --shots

# Left-handed shooter
python test_camera_angle.py video.mp4 --shots --side left
```

The `--shots` mode runs the full `LiveShotDetector` pipeline and saves annotated frames to `api/core/debug_frames/`.

---

## Shot Fingerprint System

**Location**: `api/main.py` — `_compute_fingerprint()`, `GET /fingerprint/{user_id}`

The fingerprint is a computed profile of a user's shooting mechanics, built from all their historical shot data in Supabase. It activates after 3 sessions (minimum ~15 shots).

### What it computes

- **Make/miss signatures**: Average + standard deviation of each metric, split by made=true vs made=false
- **Improvement areas**: Ranked by impact score = `(|make_avg - miss_avg| / optimal_range_span) * miss_frequency`, normalized 0-1
- **Consistency scores**: Per-metric, based on relative standard deviation (lower std = higher score)
- **Miss distribution**: Counts of miss_type values (e.g., "short-right": 8)
- **Trend**: Shooting % and form rating over last 5 sessions, with direction ("improving", "declining", "stable")
- **Coaching cues**: Plain-language cues derived from `CUE_TEMPLATES` lookup, based on whether the user's miss average is above or below their make average for each metric

### How it's used

1. **In Gemini prompts**: When `user_id` is provided to `/analyze`, the fingerprint is fetched and injected into per-shot and session summary prompts. Gemini compares the current shot to the user's make signature rather than just optimal ranges.
2. **In the mobile profile**: `GET /fingerprint/{user_id}` returns pre-generated coaching cues, miss tendency, trend label, and consistency note. The profile screen shows these as "Focus On" cards — never raw numbers.

### Cue generation

`CUE_TEMPLATES` in `api/main.py` maps each metric to a "low" and "high" coaching cue. Direction is determined by comparing the user's miss average to their make average for that metric. Top 3 improvement areas by impact score are surfaced as cues.

### Mobile display

- **Before 3 sessions**: Placeholder with session progress counter ("2/3 sessions")
- **After 3 sessions**: Numbered "Focus On" cue cards, miss tendency badge, trend indicator (arrow + label), optional consistency note

## User Context in Analysis

**Location**: `api/main.py` `/analyze` endpoint params

The `/analyze` endpoint accepts optional user context:
- `skill_level` — adjusts Gemini's coaching tone (beginner=simple, advanced=technical)
- `focus_areas` — prioritizes feedback on stated goals
- `height_inches` — included in player profile context
- `user_id` — triggers fingerprint lookup for personalized feedback

The mobile app sends these from the authenticated user's profile via `UserContext` in `mobile/lib/api.ts`.

## Progress Polling

**Important**: The API runs with `workers=1` so that in-memory `_analysis_progress` dict is shared across all requests. Multi-worker would require Redis or similar shared state.
