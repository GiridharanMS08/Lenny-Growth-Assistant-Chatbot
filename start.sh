#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
(cd backend && uvicorn app.main:app --reload) &
trap 'kill $!' EXIT
cd frontend
npm install
npm run dev
