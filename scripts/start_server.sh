#!/bin/bash
# scripts/start_server.sh
set -e

cd "$(dirname "$0")/.."

echo "🏥 XR Medical Training — Starting Server"
echo "────────────────────────────────────────"

# Check .env
if [ ! -f .env ]; then
  echo "⚠️  .env not found! Copying from .env.example..."
  cp .env.example .env
  echo "   → Edit .env and add your GEMINI_API_KEY before continuing"
  exit 1
fi

# Create logs and session dirs
mkdir -p logs sessions

# Install deps if needed
if ! python3 -c "import fastapi" 2>/dev/null; then
  echo "📦 Installing Python dependencies..."
  pip install -r requirements.txt
fi

echo "🚀 Starting FastAPI server..."
uvicorn backend.api.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --log-level info
