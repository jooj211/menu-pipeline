#!/usr/bin/env python3
"""
menu_pipeline.py — Cross-platform GUI/CLI for the Popmenu media-library pipeline.

Subcommands (CLI):
  parse   -> reads an HTML file and extracts names to names.txt
  fix     -> cleans names.txt into dish_names.txt (display) and dish_names2.txt (canonical keys)
  all     -> parse + fix (writes files)
  paste   -> interactive helper that reads dish_names/dish_names2/names from disk
  run     -> parse + fix + paste fully in-memory; ONLY writes no_matches.txt

GUI mode:
  - Double-click the app (or run with no arguments) to open a simple window.
  - Choose HTML, choose where to save no_matches.txt, pick Dry run or Interactive, click Start.
  - In interactive mode: DOWN = paste display & load clipboard; UP = append last clipboard to no_matches.txt; F8 = quit.

Notes:
  - Only the file 'no_matches.txt' is persisted; all other steps can run in-memory.
  - For Linux interactive mode, X11 sessions work best (Wayland may block simulated keystrokes).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable, List

# ------------------------- common helpers -------------------------


def native_join(lines: List[str]) -> str:
    return os.linesep.join(lines) + os.linesep if lines else ""


def split_camel(s: str) -> str:
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    s = re.sub(r"([A-Z])([A-Z][a-z])", r"\1 \2", s)
    s = re.sub(r"([0-9])([A-Za-z])", r"\1 \2", s)
    s = re.sub(r"([A-Za-z])([0-9])", r"\1 \2", s)
    return " ".join(s.replace("_", " ").replace("-", " ").split())


def strip_ext(s: str) -> str:
    return re.sub(r"\.[A-Za-z0-9]+$", "", s)


VIEW_TOKENS_RE = re.compile(
    r"(?:Top|Straight|Macro|Side|Angle|Left|Right|Front|Back|[0-9]{1,3})$", re.I
)


def remove_counters_views(s: str) -> str:
    s = re.sub(r"\(\d+\)$", "", s).strip()
    while True:
        new = VIEW_TOKENS_RE.sub("", s).strip(" _-")
        if new == s:
            break
        s = new
    return s


def canonical_key(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def strip_deduplicators(s: str) -> str:
    """
    Remove OS-style duplicate suffixes at the end like "(1)", "- Copy", "copy 2".
    Preserves hyphens/underscores and everything else.
    """
    import re

    # e.g., "filename (1)"
    s = re.sub(r"\s*\(\d+\)$", "", s, flags=re.I)
    # e.g., " - Copy", " - Copy (2)", " copy 3"
    s = re.sub(r"[\s_-]*copy(?:\s*(?:\(\d+\)|\d+))?$", "", s, flags=re.I)
    # optional Portuguese variant
    s = re.sub(r"[\s_-]*c[oó]pia(?:\s*(?:\(\d+\)|\d+))?$", "", s, flags=re.I)
    return s.strip()


# ------------------------- parse -------------------------


def parse_html(html_text: str) -> List[str]:
    names: list[str] = []
    try:
        import re
        from urllib.parse import urlparse

        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(html_text, "html.parser")

        def add_name(n: str):
            n = n.strip()
            if n:
                names.append(n)

        # Prefer file names from <img>/<source> (src & srcset)
        urls = set()

        for img in soup.find_all("img"):
            for attr in ("src", "data-src", "data-original", "data-lazy-src"):
                url = img.get(attr)
                if url:
                    urls.add(url)
            srcset = img.get("srcset")
            if srcset:
                first = srcset.split(",")[0].strip().split(" ")[0]
                if first:
                    urls.add(first)

        for src in soup.find_all("source"):
            for attr in ("src", "srcset"):
                url = src.get(attr)
                if url:
                    first = url.split(",")[0].strip().split(" ")[0]
                    urls.add(first)

        for url in urls:
            try:
                path = urlparse(url).path
            except Exception:
                path = url
            seg = path.split("/")[-1].split("?")[0].split("#")[0]
            if seg:
                add_name(seg)

        # Also include visible titles as secondary signal
        for div in soup.select('div[data-cy^="media-tile-image-title-"]'):
            h6 = div.find("h6")
            if h6:
                add_name(h6.get_text(strip=True))

        # De-dup, preserve order
        seen, uniq = set(), []
        for n in names:
            if n not in seen:
                seen.add(n)
                uniq.append(n)
        return uniq

    except Exception:
        # Regex fallback
        import re

        out = []
        for m in re.findall(
            r"<img[^>]+src=[\'\"]([^\'\"]+)[\'\"]", html_text, flags=re.I
        ):
            seg = m.split("/")[-1].split("?")[0].split("#")[0]
            if seg:
                out.append(seg)

        pattern = re.compile(
            r'data-cy="media-tile-image-title-[^"]*".*?<h6[^>]*>(.*?)</h6>',
            re.DOTALL | re.IGNORECASE,
        )
        out += [re.sub(r"\s+", " ", m.strip()) for m in pattern.findall(html_text)]
        return list(dict.fromkeys(out))


def cmd_parse(args: argparse.Namespace) -> int:
    html_path = Path(args.html).expanduser().resolve()
    out_path = (
        Path(args.out).expanduser().resolve()
        if args.out
        else html_path.with_name("names.txt")
    )
    if not html_path.exists():
        print(f"[parse] Error: {html_path} not found", file=sys.stderr)
        return 2
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    names = parse_html(html)
    out_path.write_text(native_join(names), encoding="utf-8")
    print(f"[parse] Extracted {len(names)} unique names -> {out_path}")
    return 0


# ------------------------- fix -------------------------


def fix_names(raw_lines: List[str]) -> tuple[list[str], list[str]]:
    candidates = []
    for line in raw_lines:
        base = strip_ext(line)
        base = remove_counters_views(base)
        disp = split_camel(base)
        disp = re.sub(r"^\W*\d+\W*", "", disp).strip()
        candidates.append(disp if disp else base)

    seen = set()
    display = []
    for d in candidates:
        key = re.sub(r"\s+", " ", d.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        display.append(d)

    keys = [canonical_key(d) for d in display]
    return display, keys


def cmd_fix(args: argparse.Namespace) -> int:
    in_path = (
        Path(args.input).expanduser().resolve()
        if args.input
        else Path("names.txt").resolve()
    )
    out_disp = (
        Path(args.out_display).expanduser().resolve()
        if args.out_display
        else in_path.with_name("dish_names.txt")
    )
    out_keys = (
        Path(args.out_keys).expanduser().resolve()
        if args.out_keys
        else in_path.with_name("dish_names2.txt")
    )
    if not in_path.exists():
        print(f"[fix] Error: {in_path} not found", file=sys.stderr)
        return 2
    raw = [
        ln.strip()
        for ln in in_path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    display, keys = fix_names(raw)
    out_disp.write_text(native_join(display), encoding="utf-8")
    out_keys.write_text(native_join(keys), encoding="utf-8")
    print(f"[fix] Wrote {len(display)} display names -> {out_disp}")
    print(f"[fix] Wrote {len(keys)} keys          -> {out_keys}")
    return 0


# ------------------------- grouping helpers -------------------------


def derive_group_bases(raw_lines: Iterable[str]) -> dict[str, str]:
    from collections import defaultdict

    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    best_group_base: dict[str, str] = {}

    def strip_ext_and_counters(name: str) -> str:
        base = re.sub(r"\.[A-Za-z0-9]+$", "", name.strip())
        base = strip_deduplicators(base)  # only dedupers
        return base

    def strip_view_suffixes(base: str) -> str:
        y = base.strip()
        while True:
            new = VIEW_TOKENS_RE.sub("", y).rstrip(" _-")  # only at end
            if new == y:
                break
            y = new
        return y

    for raw in raw_lines:
        b0 = strip_ext_and_counters(raw)
        gb = strip_view_suffixes(b0)
        k = canonical_key(gb)
        if k:
            counts[k][gb] += 1  # keep original '-'/'_' in the value

    for k, bucket in counts.items():
        best = max(bucket.items(), key=lambda kv: (kv[1], -len(kv[0])))
        best_group_base[k] = best[0]
    return best_group_base


def paste_session(
    display: List[str],
    keys: List[str],
    raw_lines: List[str],
    no_match_path: Path,
    dry_run: bool,
    log_fn=None,
) -> int:
    """
    Runs the interactive/dry-run paste loop.
    - log_fn(msg) is an optional callback used by the GUI to mirror logs into the UI.
    """

    def log(msg: str):
        print(msg)
        if log_fn:
            try:
                log_fn(msg)
            except Exception:
                pass

    # dry-run path: no GUI deps, just log the sequence and quit
    if dry_run:
        if len(keys) != len(display):
            keys = [canonical_key(d) for d in display]
        groupbase = derive_group_bases(raw_lines)

        def groupbase_for_key(k: str, display_text: str) -> str:
            if k in groupbase:
                return groupbase[k]
            compact = re.sub(r"[^A-Za-z0-9]+", "", split_camel(display_text))
            return compact or display_text

        log(f"[dry] Using no_matches at: {no_match_path}")
        for idx, (k, d) in enumerate(zip(keys, display), start=1):
            gb = groupbase_for_key(k, d)
            log(
                f"[dry {idx}/{len(display)}] would paste display='{d}' | clipboard='{gb}'"
            )
        return 0

    try:
        import pyautogui as ag  # type: ignore
        import pyperclip  # type: ignore
        from pynput import keyboard  # type: ignore
    except Exception as e:
        log(
            "[paste] Missing runtime dependencies (pyautogui, pyperclip, pynput). Install them to use 'paste'."
        )
        log(f"Error detail: {e}")
        return 2

    if len(keys) != len(display):
        keys = [canonical_key(d) for d in display]

    groupbase = derive_group_bases(raw_lines)

    def groupbase_for_key(k: str, display_text: str) -> str:
        if k in groupbase:
            return groupbase[k]
        compact = re.sub(r"[^A-Za-z0-9]+", "", split_camel(display_text))
        return compact or display_text

    idx = 0
    last_clip = ""

    def paste_and_prepare_clipboard():
        nonlocal idx, last_clip
        if idx >= len(display):
            log("Done.")
            return
        display_text = display[idx]
        key = keys[idx]

        ag.hotkey("ctrl", "a")
        ag.typewrite(display_text, interval=0.0)

        gb = groupbase_for_key(key, display_text)
        try:
            pyperclip.copy(gb)
        except Exception as e:
            log(f"[paste] clipboard error: {e}")
        last_clip = gb
        idx += 1
        log(
            f"[{idx}/{len(display)}] pasted display='{display_text}' | clipboard='{gb}'"
        )

    def log_previous_to_nomatch():
        nonlocal last_clip
        if not last_clip:
            return
        with no_match_path.open("a", encoding="utf-8") as f:
            f.write(last_clip + os.linesep)
        log(f"[log] appended to {no_match_path}: {last_clip}")

    def on_press(key):  # pragma: no cover (interactive)
        nonlocal idx
        try:
            if key == keyboard.Key.down:
                paste_and_prepare_clipboard()
            elif key == keyboard.Key.up:
                log_previous_to_nomatch()
            elif key == keyboard.Key.f8:
                log("Exiting.")
                return False
        except Exception as e:
            log(f"Error: {e}")
            return False

    log(f"Ready. Using no_matches at: {no_match_path}")
    log("Use DOWN to paste & load clipboard, UP to log previous, F8 to quit.")
    try:
        from pynput import keyboard  # type: ignore

        with keyboard.Listener(on_press=on_press) as listener:  # pragma: no cover
            listener.join()
    except KeyboardInterrupt:
        pass
    return 0


# ------------------------- paste (file-based) -------------------------


def cmd_paste(args: argparse.Namespace) -> int:
    base_dir = Path(args.dir).expanduser().resolve() if args.dir else Path.cwd()
    disp_file = base_dir / "dish_names.txt"
    keys_file = base_dir / "dish_names2.txt"
    raw_file = base_dir / "names.txt"
    no_match = (
        Path(args.no_matches).expanduser().resolve()
        if args.no_matches
        else (base_dir / "no_matches.txt")
    )

    if not disp_file.exists():
        print("[paste] dish_names.txt not found. Run 'fix' first.", file=sys.stderr)
        return 2
    display = [
        l.strip()
        for l in disp_file.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    if not display:
        print("[paste] dish_names.txt is empty.", file=sys.stderr)
        return 2

    if keys_file.exists():
        keys = [
            l.strip()
            for l in keys_file.read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
    else:
        keys = [canonical_key(d) for d in display]

    raw_lines = (
        [
            l.strip()
            for l in raw_file.read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        if raw_file.exists()
        else []
    )
    return paste_session(display, keys, raw_lines, no_match, args.dry_run)


# ------------------------- all (parse + fix) -------------------------


def cmd_all(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = Path(args.html).expanduser().resolve()
    names_path = out_dir / "names.txt"
    r1 = cmd_parse(argparse.Namespace(html=str(html_path), out=str(names_path)))
    if r1 != 0:
        return r1
    r2 = cmd_fix(
        argparse.Namespace(
            input=str(names_path),
            out_display=str(out_dir / "dish_names.txt"),
            out_keys=str(out_dir / "dish_names2.txt"),
        )
    )
    return r2


# ------------------------- run (parse + fix + paste in-memory) -------------------------


def cmd_run(args: argparse.Namespace) -> int:
    if not args.html and not args.input:
        print("[run] Provide --html (preferred) or --input names.txt", file=sys.stderr)
        return 2

    raw_lines: List[str]
    if args.html:
        html_path = Path(args.html).expanduser().resolve()
        if not html_path.exists():
            print(f"[run] Error: {html_path} not found", file=sys.stderr)
            return 2
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        raw_lines = parse_html(html)
    else:
        in_path = Path(args.input).expanduser().resolve()
        if not in_path.exists():
            print(f"[run] Error: {in_path} not found", file=sys.stderr)
            return 2
        raw_lines = [
            ln.strip()
            for ln in in_path.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]

    display, keys = fix_names(raw_lines)
    no_match = (
        Path(args.no_matches).expanduser().resolve()
        if args.no_matches
        else Path.cwd() / "no_matches.txt"
    )
    print(
        f"[run] Prepared {len(display)} display names in memory; no intermediate files will be written."
    )
    return paste_session(display, keys, raw_lines, no_match, args.dry_run)


# ------------------------- GUI (double-click fallback) -------------------------


def launch_gui():  # pragma: no cover
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("Menu Pipeline")
    root.geometry("600x460")
    root.resizable(False, False)  # fixed-size window
    root.attributes(
        "-topmost", True
    )  # <-- keep the window always on top (like Sticky Notes)

    html_path = tk.StringVar()
    default_nomatch = Path.home() / "Documents" / "no_matches.txt"
    no_matches_path = tk.StringVar(value=str(default_nomatch))
    dry_run_var = tk.BooleanVar(value=True)

    def choose_html():
        f = filedialog.askopenfilename(
            title="Choose Popmenu media-library HTML",
            filetypes=[("HTML files", "*.html;*.htm"), ("All files", "*.*")],
        )
        if f:
            html_path.set(f)

    def choose_no_matches():
        f = filedialog.asksaveasfilename(
            title="Where to save no_matches.txt",
            initialdir=str(default_nomatch.parent),
            defaultextension=".txt",
            initialfile="no_matches.txt",
            filetypes=[("Text", "*.txt"), ("All files", "*.*")],
        )
        if f:
            no_matches_path.set(f)

    frm = ttk.Frame(root, padding=12)
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text="1) Choose your exported media-library HTML file:").pack(
        anchor="w"
    )
    row1 = ttk.Frame(frm)
    row1.pack(fill="x", pady=4)
    ttk.Entry(row1, textvariable=html_path).pack(side="left", fill="x", expand=True)
    ttk.Button(row1, text="Browse…", command=choose_html).pack(side="left", padx=6)

    ttk.Label(frm, text="2) Pick where to save no_matches.txt:").pack(
        anchor="w", pady=(8, 0)
    )
    row2 = ttk.Frame(frm)
    row2.pack(fill="x", pady=4)
    ttk.Entry(row2, textvariable=no_matches_path).pack(
        side="left", fill="x", expand=True
    )
    ttk.Button(row2, text="Browse…", command=choose_no_matches).pack(
        side="left", padx=6
    )

    dry = ttk.Checkbutton(
        frm,
        text="Dry run (no keystrokes; just preview the sequence)",
        variable=dry_run_var,
    )
    dry.pack(anchor="w", pady=(8, 8))

    log = tk.Text(frm, height=12, wrap="word", state="disabled")
    log.pack(fill="both", expand=True, pady=(6, 0))

    def append_log(text):
        # Safe to call from main thread only; use thread-safe wrapper below otherwise
        log.configure(state="normal")
        log.insert("end", text + "\n")
        log.see("end")
        log.configure(state="disabled")

    def log_threadsafe(msg: str):
        # Ensure updates come back to the Tk mainloop thread
        root.after(0, append_log, msg)

    btns = ttk.Frame(frm)
    btns.pack(fill="x", pady=10)
    start_btn = ttk.Button(btns, text="Start", width=18)
    start_btn.pack(side="right")

    def run_pipeline():
        if not html_path.get():
            messagebox.showerror("Missing file", "Please choose the HTML file first.")
            return
        start_btn.configure(state="disabled")
        # log_threadsafe("Running… this window may minimize for interactive mode.")
        minimize = False
        """ minimize = not dry_run_var.get()
        if minimize:
            root.iconify() """

        try:
            # Build in-memory data using cmd_run parts manually, so we can pass our logger into paste_session
            # Parse and fix in memory
            html = Path(html_path.get()).read_text(encoding="utf-8", errors="ignore")
            raw_lines = parse_html(html)
            display, keys = fix_names(raw_lines)
            no_match = Path(
                no_matches_path.get()
                if no_matches_path.get()
                else (Path.cwd() / "no_matches.txt")
            )

            # Launch paste session with GUI logger
            paste_session(
                display,
                keys,
                raw_lines,
                no_match,
                dry_run_var.get(),
                log_fn=log_threadsafe,
            )
            log_threadsafe("Done.")
        except Exception as e:
            log_threadsafe(f"Error: {e}")
        finally:
            start_btn.configure(state="normal")
            if minimize:
                root.deiconify()

    start_btn.configure(
        command=lambda: threading.Thread(target=run_pipeline, daemon=True).start()
    )
    # Seed instructions
    append_log(
        "Instructions:\n• Dry run prints each step.\n• Interactive mode uses DOWN/UP/F8 inside your target app or site.\n  - DOWN: paste display name & load clipboard with base\n  - UP:   append last base to no_matches.txt\n  - F8:   quit\n"
    )
    root.mainloop()


# ------------------------- CLI -------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="menu-pipeline", description="Popmenu media-library extraction pipeline"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("parse", help="Extract names from an HTML file to names.txt")
    ps.add_argument(
        "--html",
        required=True,
        help="Path to Popmenu 'media library' HTML (e.g., test.html)",
    )
    ps.add_argument("--out", help="Output path for names.txt (default: alongside HTML)")
    ps.set_defaults(func=cmd_parse)

    fx = sub.add_parser(
        "fix", help="Clean names.txt into dish_names.txt + dish_names2.txt"
    )
    fx.add_argument("--input", help="Path to names.txt (default: ./names.txt)")
    fx.add_argument("--out-display", help="Output path for dish_names.txt")
    fx.add_argument("--out-keys", help="Output path for dish_names2.txt")
    fx.set_defaults(func=cmd_fix)

    al = sub.add_parser("all", help="parse + fix in one shot")
    al.add_argument(
        "--html",
        required=True,
        help="Path to Popmenu 'media library' HTML (e.g., test.html)",
    )
    al.add_argument(
        "--out-dir",
        help="Directory to place names.txt, dish_names.txt, dish_names2.txt (default: CWD)",
    )
    al.set_defaults(func=cmd_all)

    pa = sub.add_parser(
        "paste",
        help="Interactive helper to paste display names and set clipboard to best base (file-based)",
    )
    pa.add_argument(
        "--dir",
        help="Directory containing dish_names.txt, dish_names2.txt, names.txt (default: CWD)",
    )
    pa.add_argument(
        "--no-matches", help="Path to no_matches.txt (default: ./no_matches.txt)"
    )
    pa.add_argument(
        "--dry-run", action="store_true", help="Do not send keystrokes; print only"
    )
    pa.set_defaults(func=cmd_paste)

    rn = sub.add_parser(
        "run", help="parse + fix + paste in-memory; ONLY writes no_matches.txt"
    )
    rn.add_argument("--html", help="Path to Popmenu 'media library' HTML (preferred)")
    rn.add_argument(
        "--input", help="Alternative: a prebuilt names.txt to avoid parsing HTML"
    )
    rn.add_argument(
        "--no-matches", help="Path to no_matches.txt (default: ./no_matches.txt)"
    )
    rn.add_argument(
        "--dry-run", action="store_true", help="Do not send keystrokes; print only"
    )
    rn.set_defaults(func=cmd_run)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raise SystemExit(main())
    else:
        launch_gui()
