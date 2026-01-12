#!/bin/bash

# FormCheck Development Start Script
# Starts the API server and ngrok tunnel, then launches mobile app

set -e

echo "🏀 FormCheck - Starting Development Environment"
echo "==============================================="
echo ""

# Kill any existing processes on our ports
echo "🧹 Cleaning up existing processes..."
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
pkill -f "ngrok http" 2>/dev/null || true

# Start Python API
echo "🐍 Starting Python API..."
cd api
source venv/bin/activate
python main.py &
API_PID=$!
cd ..

# Wait for API to be ready
echo "⏳ Waiting for API to start..."
sleep 3

# Check if API is running
if ! curl -s http://localhost:8000/health > /dev/null; then
    echo "❌ API failed to start. Check api/logs for errors."
    kill $API_PID 2>/dev/null || true
    exit 1
fi
echo "✓ API running at http://localhost:8000"

# Start ngrok tunnel
echo "🌐 Starting ngrok tunnel..."
ngrok http 8000 > /dev/null &
NGROK_PID=$!

# Wait for ngrok to start
sleep 3

# Get ngrok public URL
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | python3 -c "import sys, json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])" 2>/dev/null || echo "")

if [ -z "$NGROK_URL" ]; then
    echo "❌ Failed to get ngrok URL"
    kill $API_PID $NGROK_PID 2>/dev/null || true
    exit 1
fi

echo "✓ ngrok tunnel: $NGROK_URL"

# Update mobile .env with ngrok URL
echo "📝 Updating mobile/.env with ngrok URL..."
if [ -f "mobile/.env" ]; then
    # Update or add EXPO_PUBLIC_API_URL
    if grep -q "EXPO_PUBLIC_API_URL=" mobile/.env; then
        sed -i.bak "s|EXPO_PUBLIC_API_URL=.*|EXPO_PUBLIC_API_URL=$NGROK_URL|" mobile/.env
    else
        echo "EXPO_PUBLIC_API_URL=$NGROK_URL" >> mobile/.env
    fi
    rm mobile/.env.bak 2>/dev/null || true
fi

echo ""
echo "✅ Development Environment Ready!"
echo "=================================="
echo ""
echo "📱 API: http://localhost:8000"
echo "🌐 Public URL: $NGROK_URL"
echo "🔍 ngrok Dashboard: http://localhost:4040"
echo ""
echo "To start the mobile app, run in a new terminal:"
echo "  cd mobile"
echo "  npx expo start"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Trap Ctrl+C to cleanup
trap "echo ''; echo '🛑 Stopping services...'; kill $API_PID $NGROK_PID 2>/dev/null || true; exit 0" INT

# Keep script running
wait $API_PID