# Menu Pipeline (GUI + CLI)

A simple Windows/Linux tool that turns a Popmenu “media library” page into a fast **parse → fix → paste** workflow.

- **GUI**: double-click and go — no command line needed.
- **Single EXE**: teammates can run it without installing Python.
- **Only one output file**: `no_matches.txt` (everything else runs in memory).
- **Hotkeys**:  
  - **DOWN** → paste display name & load clipboard with the grouped base  
  - **UP** → append last clipboard base to `no_matches.txt`  
  - **F8** → quit

> Works even if you copy the **entire page HTML**; the parser handles titles and original image filenames.  
> The clipboard “base” preserves `-` and `_`, and only removes deduplicators like `(1)`, `- Copy`, `copy 2`, etc.

---

## Download

Grab the latest **MenuPipeline.exe** from **Releases**.

---

## How to use (GUI)

1. Open **Menu Pipeline** (double-click the EXE).
2. Click **Browse…** and select your exported Media Library **HTML** (or save the page as “Web page, HTML only” and choose that file).
3. Pick where to save **`no_matches.txt`** (default: Documents).
4. Choose **Dry run** (preview only) or **Interactive**.
5. Click **Start**.
6. Focus the target app/site field and use the hotkeys: **DOWN/UP/F8**.

**Notes**
- On Windows 11, SmartScreen may warn (unsigned binary). Click **More info → Run anyway**.
- If Defender’s Controlled Folder Access is on, choose a writable folder (e.g., Documents) for `no_matches.txt`.

---

## CLI (power users)

```bash
# parse + fix + paste in-memory (only writes no_matches.txt)
python menu_pipeline.py run --html path/to/page.html

# dry-run (no keystrokes; prints actions)
python menu_pipeline.py run --html path/to/page.html --dry-run

# legacy steps
python menu_pipeline.py parse --html page.html --out names.txt
python menu_pipeline.py fix --input names.txt --out-display dish_names.txt --out-keys dish_names2.txt
python menu_pipeline.py paste --dir .
