#!/bin/bash
# ==============================================
# Rift Engine — Push to GitHub
# Run this script from inside the rift-engine folder
# ==============================================

echo "=== Pushing Rift Engine to GitHub ==="
echo ""

# Make sure we're in the right directory
cd "$(dirname "$0")"

# Initialize git if needed
if [ ! -d ".git" ]; then
    echo "Initializing git repo..."
    git init
    git branch -M main
fi

# Set remote
git remote remove origin 2>/dev/null
git remote add origin https://github.com/becastil/rift-engine.git

# Stage all files
echo "Staging files..."
git add -A

# Commit
echo "Creating commit..."
git commit -m "Initial commit: Rift Engine MVP

Complete project skeleton with simulation engine, scrapers,
database schema, FastAPI server, and web UI.

Features:
- Hand-tuned probability simulation engine
- CommunityDragon + Oracle's Elixir scrapers
- SQLite warehouse with 7-table schema
- FastAPI REST API
- Dark-themed web UI with Chart.js gold curves"

# Force push (overwrites the README-only commit on GitHub)
echo "Pushing to GitHub..."
git push -u origin main --force

echo ""
echo "=== Done! Check https://github.com/becastil/rift-engine ==="
