#!/bin/bash
echo "Running admin init..."
python /app/scripts/init_admin.py
echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
