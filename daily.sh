#!/bin/bash
# One day of experiment 2: resolve earlier games, freeze today's, have both arms answer, log and commit.
# The Jev key comes from AI_GATEWAY_API_KEY in the environment or this project's .env.
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
$PY resolve.py
$PY games.py --hours 30
if [ "$($PY -c "import json,glob;print(len(json.load(open(sorted(p for p in glob.glob('runs/games-2*.json') if 'resolved' not in p)[-1]))['games']))")" = "0" ]; then
  echo "no new games to answer"; exit 0
fi
$PY run.py --set games 2>&1 | grep -vE "Warning|falling back|Loading weights"
$PY log_day.py
$PY analyze_games.py || true
git add docs/GAMES-LOG.md && git commit -qm "Log a day of experiment 2" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>" && git log --oneline -1
