# FormCheck Deployment Guide

Technical reference for deploying the FormCheck API to Railway and mobile app to App Stores.

---

## Current Deployment Status

| Component | Status | Platform |
|-----------|--------|----------|
| **Backend API** | ✅ Deployed | Railway |
| **Database** | ✅ Configured | Supabase |
| **Storage** | ✅ Configured | Supabase Storage |
| **iOS App** | ⏳ Pending | App Store |
| **Android App** | ⏳ Pending | Play Store |

---

## Backend API (Railway)

### Architecture

```
Mobile App
    │
    ▼ HTTPS
┌─────────────────────────────────────┐
│         Railway (Docker)            │
│  ┌───────────────────────────────┐  │
│  │  FastAPI + Uvicorn (4 workers)│  │
│  │  - MediaPipe (pose detection) │  │
│  │  - YOLO (ball tracking)       │  │
│  │  - Gemini API (AI feedback)   │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│           Supabase                  │
│  - PostgreSQL (sessions, shots)     │
│  - Storage (thumbnails)             │
│  - Auth (user accounts)             │
└─────────────────────────────────────┘
```

### Key Files

| File | Purpose |
|------|---------|
| `api/Dockerfile` | Container build instructions |
| `api/railway.toml` | Railway deployment config |
| `api/Procfile` | Process start command |
| `api/requirements.txt` | Python dependencies |
| `api/main.py` | FastAPI application |

### Dockerfile

```dockerfile
FROM python:3.11-slim

# System dependencies for OpenCV and MediaPipe
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxcb1 \
    libx11-6 \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

### railway.toml

```toml
[build]
builder = "dockerfile"

[deploy]
startCommand = "python main.py"
healthcheckPath = "/health"
healthcheckTimeout = 300
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

### Environment Variables (Railway Dashboard)

| Variable | Description |
|----------|-------------|
| `GOOGLE_API_KEY` | Gemini API key for AI feedback |
| `PORT` | Auto-set by Railway (don't change) |

### Important: PORT Handling

Railway provides `PORT` as an environment variable. The `main.py` reads it at runtime:

```python
port = int(os.environ.get("PORT", os.environ.get("API_PORT", 8000)))
```

**Do NOT** use `$PORT` in shell commands (Docker CMD) - it won't expand. Always read via Python `os.environ.get()`.

### Deployment Commands

```bash
# Navigate to API folder
cd /path/to/FormCheckApp/api

# Login to Railway
railway login

# Initialize project (first time)
railway init

# Link to service
railway service

# Deploy
railway up

# View logs
railway logs

# Set environment variables
railway variables set GOOGLE_API_KEY=your_key_here

# Get public URL
railway domain

# Stop service (to save costs)
railway down
```

### Testing the Deployment

```bash
# Health check
curl https://YOUR-APP.up.railway.app/health

# Expected response:
# {"status":"healthy","modules_available":true,"gemini_configured":true,"database_available":true}

# Root endpoint
curl https://YOUR-APP.up.railway.app/

# Expected response:
# {"name":"FormCheck API","version":"2.0.0","status":"running",...}
```

### Cost Management

Railway charges for **uptime**, not just processing.

**To reduce costs:**

1. **Scale to zero** (recommended):
   - Railway Dashboard → Service → Settings → Scaling
   - Enable "Scale to zero after inactivity"
   - ~10-15 sec cold start on first request

2. **Manual stop** when not testing:
   ```bash
   railway down
   ```

**Estimated costs:**
- Idle: ~$5-10/month
- Active (100 users/day): ~$20-50/month

### Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| `libxcb.so.1 not found` | Missing system deps | Add to Dockerfile apt-get |
| `$PORT is not a valid integer` | Shell variable not expanded | Use `python main.py` which reads PORT via os.environ |
| `modules_available: false` | Import error | Check `railway logs` for specific error |
| Health check timeout | Slow startup | Increase `healthcheckTimeout` in railway.toml |

---

## Mobile App Deployment

### Prerequisites

| Requirement | iOS | Android |
|-------------|-----|---------|
| Developer Account | Apple Developer ($99/year) | Google Play ($25 one-time) |
| Build Tool | EAS Build | EAS Build |
| Certificates | Auto-managed by EAS | Auto-managed by EAS |

### Setup EAS

```bash
cd /path/to/FormCheckApp/mobile

# Install EAS CLI
npm install -g eas-cli

# Login
eas login

# Configure project
eas build:configure
```

### Configure app.json

```json
{
  "expo": {
    "name": "FormCheck",
    "slug": "formcheck",
    "version": "1.0.0",
    "ios": {
      "bundleIdentifier": "com.formcheck.app",
      "supportsTablet": false
    },
    "android": {
      "package": "com.formcheck.app",
      "adaptiveIcon": {
        "foregroundImage": "./assets/adaptive-icon.png",
        "backgroundColor": "#000000"
      }
    }
  }
}
```

### Update API URL for Production

In `mobile/.env`:
```
EXPO_PUBLIC_API_URL=https://YOUR-APP.up.railway.app
EXPO_PUBLIC_SUPABASE_URL=your_supabase_url
EXPO_PUBLIC_SUPABASE_ANON_KEY=your_supabase_key
```

### Build Commands

```bash
# iOS build
eas build --platform ios

# Android build
eas build --platform android

# Both platforms
eas build --platform all
```

### Submit to Stores

```bash
# iOS (App Store)
eas submit --platform ios

# Android (Play Store)
eas submit --platform android
```

### App Store Requirements Checklist

#### Assets Needed

- [ ] **App Icon** (1024x1024, no transparency for iOS)
- [ ] **Adaptive Icon** (1024x1024, for Android)
- [ ] **Splash Screen** (1284x2778 recommended)
- [ ] **Screenshots** (6.7", 6.5", 5.5" for iOS; phone + tablet for Android)
- [ ] **App Preview Video** (optional but recommended)

#### Content Needed

- [ ] **App Name**: FormCheck
- [ ] **Subtitle**: AI Basketball Shooting Coach
- [ ] **Description**: 4000 chars max, highlight features
- [ ] **Keywords**: basketball, shooting, form, coach, AI, training
- [ ] **Privacy Policy URL**: Required
- [ ] **Support URL**: Required
- [ ] **Marketing URL**: Optional

#### Privacy & Compliance

- [ ] **Privacy Policy**: Must cover camera usage, data collection
- [ ] **Camera Permission Text**: "FormCheck uses the camera to record your shooting form for AI analysis"
- [ ] **Age Rating**: Complete questionnaire (likely 4+)
- [ ] **Export Compliance**: Standard encryption declaration

### Privacy Policy Template

Create at `https://yoursite.com/privacy` or use a generator:

```
Key points to cover:
- Camera usage (for recording shooting form)
- Video processing (sent to server for AI analysis)
- Data storage (Supabase, thumbnails)
- Third-party services (Gemini AI, Supabase)
- Data retention policy
- User rights (deletion, export)
- Contact information
```

---

## Remaining Steps for Launch

### High Priority

- [ ] Generate app icon (1024x1024)
- [ ] Create splash screen
- [ ] Write privacy policy
- [ ] Create Apple Developer account
- [ ] Create Google Play Developer account
- [ ] Build and test on physical devices
- [ ] Capture App Store screenshots

### Medium Priority

- [ ] Set up error monitoring (Sentry)
- [ ] Set up analytics (Mixpanel/Amplitude)
- [ ] Create support email
- [ ] Write App Store description
- [ ] Create app preview video

### Pre-Launch Testing

- [ ] Test full flow: record → analyze → view results
- [ ] Test on multiple devices (iPhone, Android)
- [ ] Test with poor network conditions
- [ ] Test error states
- [ ] Test with long videos (2+ minutes)
- [ ] Verify Supabase RLS policies

---

## Quick Reference

### Railway Commands
```bash
railway login          # Authenticate
railway up             # Deploy
railway logs           # View logs
railway down           # Stop service
railway variables set KEY=value  # Set env var
railway domain         # Get/create public URL
```

### EAS Commands
```bash
eas login              # Authenticate
eas build:configure    # Setup project
eas build --platform ios      # Build iOS
eas build --platform android  # Build Android
eas submit --platform ios     # Submit to App Store
eas submit --platform android # Submit to Play Store
eas credentials        # Manage signing credentials
```

### Useful URLs
- Railway Dashboard: https://railway.app/dashboard
- Supabase Dashboard: https://supabase.com/dashboard
- EAS Dashboard: https://expo.dev
- App Store Connect: https://appstoreconnect.apple.com
- Google Play Console: https://play.google.com/console

---

*Last Updated: February 2025*
