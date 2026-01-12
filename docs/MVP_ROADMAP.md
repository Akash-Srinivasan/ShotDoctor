# FormCheck MVP - Product Roadmap

## Executive Summary

**Product**: AI basketball shooting coach that learns YOUR optimal form
**Target**: Amateur basketball players who want to improve their shot
**Differentiator**: Self-referential coaching (compares to YOUR makes, not generic advice)
**Business Model**: Freemium subscription

---

## Current State (Prototype)

### What We Have
- ✅ Pose detection (MediaPipe)
- ✅ Shot detection algorithm (release-backward, 8 frames)
- ✅ AI coaching via Gemini API
- ✅ Local SQLite database
- ✅ Visual feedback system
- ✅ Biomechanics research module
- ✅ Make/miss tracking with rim detection

### What's Missing for MVP
- ❌ Mobile app (iOS/Android)
- ❌ Cloud backend
- ❌ User authentication
- ❌ Payment/subscription system
- ❌ Onboarding flow
- ❌ Offline capability
- ❌ Social features

---

## MVP Feature Set

### Core (Must Have)
| Feature | Description | Priority |
|---------|-------------|----------|
| Record shot | Capture video of shooting session | P0 |
| Auto-detect shots | Find shots in video automatically | P0 |
| AI feedback | Get coaching on each shot | P0 |
| Make/miss logging | Track accuracy over time | P0 |
| Progress dashboard | See improvement trends | P0 |
| User accounts | Sign up, log in | P0 |

### Important (Should Have)
| Feature | Description | Priority |
|---------|-------------|----------|
| Shot library | Review past shots with annotations | P1 |
| Focus areas | Set goals (elbow, release, etc.) | P1 |
| Session summaries | End-of-session report | P1 |
| Offline mode | Record now, analyze later | P1 |
| Push notifications | Reminders, streak tracking | P1 |

### Nice to Have (Could Have)
| Feature | Description | Priority |
|---------|-------------|----------|
| Live feedback | Real-time overlay during recording | P2 |
| Social sharing | Share progress clips | P2 |
| Leaderboards | Compare with friends | P2 |
| Coach mode | Send feedback to players | P2 |
| Team management | For coaches with multiple players | P2 |

---

## Technical Architecture

### Option A: React Native + Cloud (Recommended for MVP)

```
┌─────────────────────────────────────────────────────────────┐
│                      MOBILE APP                              │
│                   (React Native)                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Camera    │  │  Local DB   │  │   UI Components     │  │
│  │  Recording  │  │  (SQLite)   │  │  (Progress, Feed)   │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTPS
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      CLOUD BACKEND                           │
│                    (Node.js / Python)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │    Auth     │  │  Video      │  │   AI Analysis       │  │
│  │  (Firebase) │  │  Processing │  │   (Gemini API)      │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Payments   │  │  Database   │  │   File Storage      │  │
│  │  (Stripe)   │  │ (PostgreSQL)│  │   (S3/GCS)          │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Pros**: 
- Single codebase for iOS + Android
- Faster iteration
- Large ecosystem
- Good for MVP speed

**Cons**:
- Performance limitations for real-time video
- May need native modules for camera

### Option B: Native Apps + Cloud

```
┌──────────────────┐     ┌──────────────────┐
│    iOS App       │     │   Android App    │
│    (Swift)       │     │    (Kotlin)      │
└────────┬─────────┘     └────────┬─────────┘
         │                        │
         └──────────┬─────────────┘
                    │ HTTPS
                    ▼
         ┌─────────────────────┐
         │   Cloud Backend     │
         │   (Same as above)   │
         └─────────────────────┘
```

**Pros**:
- Best performance
- Full platform capabilities
- Better camera/video handling

**Cons**:
- 2x development effort
- Slower iteration
- Higher cost

### Recommendation: Hybrid Approach

**Phase 1 (MVP)**: React Native for fast launch
**Phase 2 (Scale)**: Native modules for performance-critical features
**Phase 3 (Growth)**: Full native if needed

---

## Cloud Infrastructure

### Services Needed

| Service | Provider Options | Est. Cost/Month |
|---------|-----------------|-----------------|
| **Hosting** | AWS / GCP / Vercel | $50-200 |
| **Database** | Supabase / PlanetScale / RDS | $25-100 |
| **Auth** | Firebase Auth / Auth0 / Clerk | $0-50 |
| **Storage** | S3 / GCS / Cloudflare R2 | $20-100 |
| **AI API** | Gemini API | $100-500 |
| **Payments** | Stripe | 2.9% + $0.30/txn |
| **Analytics** | Mixpanel / Amplitude | $0-100 |
| **Push** | Firebase / OneSignal | $0-50 |

**Estimated MVP infrastructure**: $200-500/month at launch

### Recommended Stack

```yaml
Frontend:
  - React Native (Expo for faster dev)
  - TypeScript
  - React Query (data fetching)
  - Zustand (state management)

Backend:
  - Node.js + Express or FastAPI (Python)
  - PostgreSQL (Supabase)
  - Redis (caching, queues)

Infrastructure:
  - Vercel (API hosting)
  - Supabase (DB + Auth + Storage)
  - Stripe (payments)
  - Gemini API (AI)

Video Processing:
  - FFmpeg (frame extraction)
  - MediaPipe (pose detection) - run on device or cloud
  - Cloud GPU (if needed for scale)
```

---

## Data Model

### Core Entities

```sql
-- Users
users (
  id UUID PRIMARY KEY,
  email VARCHAR UNIQUE,
  name VARCHAR,
  height_inches INT,
  shooting_hand VARCHAR, -- 'left' | 'right'
  skill_level VARCHAR,   -- 'beginner' | 'intermediate' | 'advanced'
  subscription_tier VARCHAR, -- 'free' | 'pro' | 'team'
  subscription_expires_at TIMESTAMP,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)

-- Sessions (shooting practice)
sessions (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users,
  started_at TIMESTAMP,
  ended_at TIMESTAMP,
  location VARCHAR,
  shot_count INT,
  make_count INT,
  focus_area VARCHAR,
  notes TEXT
)

-- Individual shots
shots (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES sessions,
  user_id UUID REFERENCES users,
  shot_number INT,
  made BOOLEAN,
  miss_type VARCHAR, -- 'short' | 'long' | 'left' | 'right'
  
  -- Metrics
  elbow_angle_load FLOAT,
  elbow_angle_release FLOAT,
  knee_bend FLOAT,
  wrist_height FLOAT,
  
  -- AI Analysis
  form_rating INT, -- 1-10
  feedback TEXT,
  key_issue VARCHAR,
  cue VARCHAR,
  
  -- Media
  video_url VARCHAR,
  thumbnail_url VARCHAR,
  frames_json JSONB, -- annotated frame URLs
  
  created_at TIMESTAMP
)

-- User's optimal form (learned from their makes)
user_form_profile (
  user_id UUID PRIMARY KEY REFERENCES users,
  
  -- Optimal values (calculated from makes)
  optimal_elbow_load FLOAT,
  optimal_elbow_release FLOAT,
  optimal_knee_bend FLOAT,
  optimal_wrist_height FLOAT,
  
  -- Consistency metrics
  elbow_load_std FLOAT,
  elbow_release_std FLOAT,
  
  -- Sample size
  total_makes INT,
  last_updated TIMESTAMP
)

-- Subscriptions
subscriptions (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users,
  stripe_customer_id VARCHAR,
  stripe_subscription_id VARCHAR,
  tier VARCHAR,
  status VARCHAR, -- 'active' | 'canceled' | 'past_due'
  current_period_start TIMESTAMP,
  current_period_end TIMESTAMP
)
```

---

## Subscription Tiers

### Free Tier
- 10 shots/week with AI feedback
- Basic progress tracking
- 7-day history
- Ads shown

### Pro Tier ($9.99/month or $79.99/year)
- Unlimited shots
- Full AI feedback
- Unlimited history
- Shot library with video
- Advanced analytics
- Export data
- No ads
- Priority support

### Team Tier ($29.99/month)
- Everything in Pro
- Up to 15 players
- Coach dashboard
- Team analytics
- Bulk feedback
- Video sharing

---

## Development Phases

### Phase 1: Foundation (Weeks 1-4)
**Goal**: Basic app that can record and analyze shots

- [ ] Set up React Native project (Expo)
- [ ] Implement camera recording
- [ ] Set up Supabase (DB + Auth)
- [ ] Basic user registration/login
- [ ] Upload video to cloud storage
- [ ] Backend API for video processing
- [ ] Integrate existing shot detection (port to cloud)
- [ ] Integrate Gemini API
- [ ] Display feedback in app

**Deliverable**: App that records video → uploads → shows AI feedback

### Phase 2: Core Experience (Weeks 5-8)
**Goal**: Polished shooting experience

- [ ] Session flow (start/end session)
- [ ] Make/miss input (tap to log result)
- [ ] Real-time shot counter
- [ ] Session summary screen
- [ ] Basic progress dashboard
- [ ] Shot history list
- [ ] User profile/settings
- [ ] Onboarding flow

**Deliverable**: Complete session experience with history

### Phase 3: Monetization (Weeks 9-10)
**Goal**: Payment system working

- [ ] Stripe integration
- [ ] Subscription management
- [ ] Paywall UI
- [ ] Free tier limits
- [ ] Receipt/billing history
- [ ] Restore purchases

**Deliverable**: Users can subscribe and pay

### Phase 4: Polish & Launch (Weeks 11-12)
**Goal**: App store ready

- [ ] App store assets (screenshots, video)
- [ ] Privacy policy, terms of service
- [ ] Analytics integration
- [ ] Crash reporting (Sentry)
- [ ] Performance optimization
- [ ] Beta testing (TestFlight / Play Console)
- [ ] App store submission

**Deliverable**: Live in App Store and Play Store

---

## API Endpoints

### Auth
```
POST /auth/register        - Create account
POST /auth/login           - Sign in
POST /auth/logout          - Sign out
POST /auth/forgot-password - Reset password
GET  /auth/me              - Get current user
```

### Sessions
```
POST   /sessions              - Start new session
PATCH  /sessions/:id          - Update session (end it)
GET    /sessions              - List user's sessions
GET    /sessions/:id          - Get session details
DELETE /sessions/:id          - Delete session
```

### Shots
```
POST   /shots                 - Create shot (upload video)
GET    /shots                 - List shots (with filters)
GET    /shots/:id             - Get shot details
PATCH  /shots/:id             - Update shot (made/missed)
DELETE /shots/:id             - Delete shot
```

### Analysis
```
POST /analyze/video           - Submit video for processing
GET  /analyze/status/:job_id  - Check processing status
GET  /analyze/result/:job_id  - Get analysis results
```

### User
```
GET   /user/profile           - Get profile
PATCH /user/profile           - Update profile
GET   /user/stats             - Get overall stats
GET   /user/form-profile      - Get learned optimal form
```

### Subscription
```
POST /subscription/create-checkout  - Start Stripe checkout
POST /subscription/webhook          - Stripe webhook
GET  /subscription/status           - Get subscription status
POST /subscription/cancel           - Cancel subscription
```

---

## Video Processing Pipeline

```
┌──────────────┐
│ Mobile App   │
│ Records Video│
└──────┬───────┘
       │ Upload (chunks for large files)
       ▼
┌──────────────┐
│ Cloud Storage│
│ (S3/GCS)     │
└──────┬───────┘
       │ Trigger
       ▼
┌──────────────┐
│ Processing   │
│ Queue (SQS)  │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────┐
│         Video Processor              │
│                                      │
│  1. Download video                   │
│  2. Extract frames (FFmpeg)          │
│  3. Run pose detection (MediaPipe)   │
│  4. Detect shots (our algorithm)     │
│  5. For each shot:                   │
│     - Extract key frames             │
│     - Calculate metrics              │
│     - Send to Gemini for feedback    │
│  6. Store results in DB              │
│  7. Generate annotated frames        │
│  8. Upload to storage                │
│  9. Notify app (push/websocket)      │
│                                      │
└──────────────────────────────────────┘
```

### Processing Time Estimates
- 1 minute video ≈ 30-60 seconds processing
- ~$0.01-0.05 per video (compute + API)

---

## Mobile App Screens

### Core Screens
1. **Splash/Loading**
2. **Onboarding** (3-4 screens explaining value prop)
3. **Sign Up / Login**
4. **Home Dashboard**
   - Recent sessions
   - Quick stats (make %, streak)
   - Start session button
5. **Recording Screen**
   - Camera view
   - Shot counter
   - Make/Miss buttons
   - End session button
6. **Processing Screen**
   - Upload progress
   - Analysis progress
7. **Session Summary**
   - Stats for session
   - Key feedback
   - List of shots
8. **Shot Detail**
   - Video playback
   - Annotated frames
   - AI feedback
   - Metrics
9. **History**
   - Calendar view
   - Session list
   - Filters
10. **Progress**
    - Charts (accuracy over time)
    - Form metrics trends
    - Achievements
11. **Profile/Settings**
    - Account info
    - Subscription status
    - Preferences
    - Log out

### Wireframe Flow
```
Splash → Onboarding → Sign Up → Home
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
                 Record       History       Progress
                    │             │             
                    ▼             ▼             
                Processing   Shot Detail       
                    │                          
                    ▼                          
                Summary                        
```

---

## Cost Projections

### Development Costs

| Role | Duration | Cost |
|------|----------|------|
| Mobile Dev (React Native) | 3 months | $15-30k |
| Backend Dev | 2 months | $10-20k |
| Design (UI/UX) | 1 month | $5-10k |
| QA/Testing | 1 month | $3-5k |
| **Total** | | **$33-65k** |

*Or solo/small team: 3-4 months full-time*

### Monthly Operating Costs (at scale)

| Users | Infrastructure | AI API | Total |
|-------|---------------|--------|-------|
| 100 | $100 | $50 | $150 |
| 1,000 | $200 | $300 | $500 |
| 10,000 | $500 | $2,000 | $2,500 |
| 100,000 | $2,000 | $15,000 | $17,000 |

### Revenue Projections

| Users | Free | Pro ($10/mo) | Revenue |
|-------|------|--------------|---------|
| 1,000 | 900 | 100 | $1,000/mo |
| 10,000 | 8,500 | 1,500 | $15,000/mo |
| 100,000 | 85,000 | 15,000 | $150,000/mo |

*Assuming 10% conversion to paid*

---

## Launch Checklist

### Pre-Launch
- [ ] Beta test with 20-50 users
- [ ] Fix critical bugs
- [ ] Performance testing
- [ ] Security audit
- [ ] Legal review (terms, privacy)
- [ ] Set up customer support (email, chat)
- [ ] Prepare marketing materials
- [ ] Set up analytics

### App Store Requirements
- [ ] App icons (all sizes)
- [ ] Screenshots (6.5", 5.5" iPhone, Android)
- [ ] App preview video
- [ ] Description and keywords
- [ ] Privacy policy URL
- [ ] Support URL
- [ ] Age rating questionnaire
- [ ] Export compliance

### Launch Day
- [ ] Submit to App Store (allow 1-3 days review)
- [ ] Submit to Play Store (allow 1-7 days review)
- [ ] Monitor crash reports
- [ ] Monitor server load
- [ ] Respond to reviews
- [ ] Social media announcement

---

## Success Metrics

### North Star
**Weekly Active Users (WAU)** who complete at least 1 session

### Key Metrics
| Metric | Target (Month 1) | Target (Month 6) |
|--------|------------------|------------------|
| Downloads | 1,000 | 20,000 |
| WAU | 300 | 5,000 |
| Sessions/user/week | 2 | 3 |
| Free→Pro conversion | 5% | 10% |
| Churn (Pro) | <10%/mo | <5%/mo |
| App Store rating | 4.0+ | 4.5+ |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Pose detection accuracy | High | Test extensively, allow manual correction |
| Processing costs too high | High | Optimize pipeline, cache results |
| Gemini API changes/pricing | Medium | Abstract AI layer, have backup (Claude, GPT) |
| Low conversion to paid | High | A/B test pricing, add value to Pro |
| App store rejection | Medium | Follow guidelines carefully, have backup plan |
| Competition | Medium | Focus on self-referential USP |

---

## Next Steps

1. **Validate demand**: Landing page + waitlist
2. **Choose tech stack**: React Native + Supabase recommended
3. **Design MVP screens**: Figma mockups
4. **Build Phase 1**: 4 weeks to basic recording + analysis
5. **Beta test**: Get 20 users, iterate
6. **Build Phase 2-4**: Complete MVP
7. **Launch**: App stores
8. **Iterate**: Based on user feedback

---

## Resources

### Tutorials & Docs
- [React Native](https://reactnative.dev/)
- [Expo](https://docs.expo.dev/)
- [Supabase](https://supabase.com/docs)
- [Stripe React Native](https://stripe.com/docs/payments/accept-a-payment?platform=react-native)
- [MediaPipe](https://developers.google.com/mediapipe)

### Similar Apps to Study
- HomeCourt (basketball)
- OnForm (golf)
- Sprocket (cycling)
- Hudl (team sports)

### Potential Partners
- Basketball training facilities
- Youth basketball leagues
- Basketball YouTubers/influencers
- High school/college programs

---

*Document Version: 1.0*
*Last Updated: January 2025*
