#!/bin/bash
cd "$(dirname "$0")/backend"
source venv/bin/activate
python knowledge_worker.py "$@"
