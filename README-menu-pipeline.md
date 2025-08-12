# Menu Pipeline (GUI + CLI)

A single tool that runs your **parse → fix → paste** workflow on Windows and Linux. Non‑technical users can just **double‑click** to open a small window. Advanced users can still use the CLI.

## Double‑click GUI
1. Open **Menu Pipeline**.
2. Pick the exported **media-library HTML**.
3. (Optional) Choose where to save **no_matches.txt**.
4. Choose **Dry run** (preview) or **Interactive**.
5. Click **Start**.

**Interactive keys** (when focused on your target app/site):  
- **DOWN** → paste display name & set clipboard to grouped base  
- **UP** → append last base to `no_matches.txt`  
- **F8** → quit

> Only `no_matches.txt` is written to disk. Everything else can run in-memory.

## CLI (for power users)

```bash
# parse + fix + paste in-memory (only no_matches.txt is written)
python menu_pipeline.py run --html test.html
python menu_pipeline.py run --html test.html --no-matches ./no_matches.txt

# dry-run (no keystrokes; prints what would happen)
python menu_pipeline.py run --html test.html --dry-run

# legacy steps
python menu_pipeline.py parse --html test.html --out names.txt
python menu_pipeline.py fix --input names.txt --out-display dish_names.txt --out-keys dish_names2.txt
python menu_pipeline.py paste --dir .
```

## Build single-file executables

> PyInstaller does **not** cross-compile. Build on the target OS.

**Windows**
```bat
py -m pip install -U pip pyinstaller -r requirements.txt
py -m PyInstaller --onefile --windowed menu_pipeline.py -n MenuPipeline
dist\MenuPipeline.exe
```

**Linux**
```bash
python3 -m pip install -U pip pyinstaller -r requirements.txt
python3 -m PyInstaller --onefile --windowed menu_pipeline.py -n menu-pipeline
./dist/menu-pipeline
```

### Notes
- On Linux, interactive keystrokes need an **X11** session (Wayland can block them). Dry run works everywhere.
- If keystrokes don't paste, click the field you want to paste into, then press **DOWN**.
