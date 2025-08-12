#!/usr/bin/env bash
set -euo pipefail
python3 -m pip install -U pip pyinstaller -r requirements.txt
python3 -m PyInstaller --onefile --windowed menu_pipeline.py -n menu-pipeline
echo "Built ./dist/menu-pipeline"
