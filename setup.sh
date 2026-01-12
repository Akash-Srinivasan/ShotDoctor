#!/bin/bash

# FormCheck Setup Script
# This script sets up the entire development environment

set -e  # Exit on error

echo "🏀 FormCheck - Development Setup"
echo "=================================="
echo ""

# Check if we're in the right directory
if [ ! -f "setup.sh" ]; then
    echo "❌ Please run this script from the FormCheck root directory"
    exit 1
fi

# Check Node.js
echo "📦 Checking Node.js..."
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found. Please install from https://nodejs.org"
    exit 1
fi
echo "✓ Node.js $(node --version)"

# Check Python
echo "📦 Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.10+"
    exit 1
fi
echo "✓ Python $(python3 --version)"

# Install ngrok if not present
echo "📦 Checking ngrok..."
if ! command -v ngrok &> /dev/null; then
    echo "📥 Installing ngrok..."
    if command -v brew &> /dev/null; then
        brew install ngrok/ngrok/ngrok
    else
        echo "⚠️  Please install Homebrew first: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        echo "Then run this script again"
        exit 1
    fi
fi
echo "✓ ngrok $(ngrok --version)"

# Setup Mobile App
echo ""
echo "📱 Setting up Mobile App..."
cd mobile
npm install
echo "✓ Mobile dependencies installed"
cd ..

# Setup Python API
echo ""
echo "🐍 Setting up Python API..."
cd api
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "✓ Python dependencies installed"
cd ..

# Create .env files if they don't exist
echo ""
echo "⚙️  Setting up environment files..."

if [ ! -f "api/.env" ]; then
    cat > api/.env << EOF
# Gemini API Key (get from https://makersuite.google.com/app/apikey)
GEMINI_API_KEY=your_gemini_api_key_here

# Supabase credentials (get from https://supabase.com/dashboard)
SUPABASE_URL=your_supabase_url_here
SUPABASE_ANON_KEY=your_supabase_anon_key_here
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key_here

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
EOF
    echo "✓ Created api/.env (please update with your keys)"
else
    echo "✓ api/.env already exists"
fi

if [ ! -f "mobile/.env" ]; then
    cat > mobile/.env << EOF
# Supabase Configuration
EXPO_PUBLIC_SUPABASE_URL=your_supabase_url_here
EXPO_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key_here

# API Configuration (will be updated by start-dev.sh with ngrok URL)
EXPO_PUBLIC_API_URL=http://localhost:8000
EOF
    echo "✓ Created mobile/.env (please update with your keys)"
else
    echo "✓ mobile/.env already exists"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Sign up for Supabase at https://supabase.com"
echo "2. Get your Gemini API key from https://makersuite.google.com/app/apikey"
echo "3. Update api/.env with your keys"
echo "4. Update mobile/.env with your Supabase URL and keys"
echo "5. Run './scripts/start-dev.sh' to start development"
echo ""