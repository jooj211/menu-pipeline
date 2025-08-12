@echo off
setlocal
py -m pip install -U pip pyinstaller -r requirements.txt
py -m PyInstaller --onefile --windowed menu_pipeline.py -n MenuPipeline
echo Built dist\MenuPipeline.exe
