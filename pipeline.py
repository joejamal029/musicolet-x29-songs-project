import os
import re
import csv
import shutil
import argparse
import threading
from datetime import datetime
from PIL import Image
import pytesseract
from rapidfuzz import process, fuzz

# Global Cache for library matching
_library_lock = threading.Lock()
_library_cache = []

# Musicolet Notification Area Default (720p base)
# (left, top, right, bottom)
CROP_BOX_DEFAULT = (0, 174, 720, 528)

# Preset Resolution Mappings (L, T, R, B)
# These are the standard bands for different device DPIs
CROP_PRESETS = {
    "default": (0, 174, 720, 528),      # 720p Original
    "1080p": (0, 261, 1080, 792),      # 1080p Scaled
    "1440p": (0, 413, 1440, 1254),     # 1440p / QuadHD
    "full": None                       # No crop
}

def _image_median_brightness(gray_image) -> float:
    """
    Compute median pixel brightness via histogram in O(256) time.
    Replaces statistics.median(list(gray.getdata())) which allocates ~55 MB
    and runs O(n log n) per 1080p image.
    """
    hist = gray_image.histogram()  # PIL C-level: list of 256 counts
    total = sum(hist)
    if total == 0:
        return 128.0
    half = total / 2.0
    cumulative = 0
    for brightness, count in enumerate(hist):
        cumulative += count
        if cumulative >= half:
            return float(brightness)
    return 128.0

_CROP_REF = (0, 174, 720, 528)   # 720p baseline for proportional scaling

def get_crop_box(img_width: int, img_height: int) -> tuple:
    """
    Scale the notification crop region proportionally to actual image dimensions.
    CROP_BOX is calibrated for 720p (720x1280). This scales it to any resolution.
    """
    scale_x = img_width  / 720.0
    scale_y = img_height / 1280.0
    return (
        0,
        int(_CROP_REF[1] * scale_y),
        img_width,                        # always full width — never crop right edge
        int(_CROP_REF[3] * scale_y),
    )


# Tesseract Configuration
OCR_CONFIG = r'--oem 1 --psm 6'

# C1 Fix: Auto-detect Tesseract securely, with a Windows fallback
tesseract_path = shutil.which("tesseract")
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
else:
    # Common Windows fallback
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

DB_CSV_PATH = "songs_full_info.csv"
M3U_TEMPLATE_PATH = "m3u_info.m3u"
OUTPUT_DIR = "output"

def get_full_library() -> list:
    global _library_cache
    if _library_cache:
        return _library_cache
    with _library_lock:
        # Double-checked locking: re-check after acquiring lock
        if _library_cache:
            return _library_cache
        if not os.path.exists(DB_CSV_PATH):
            return []
        temp = []
        with open(DB_CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # Skip header
            for row in reader:
                if len(row) >= 3:
                    title = row[1].strip()
                    artist = row[2].strip()
                    combined = f"{artist} - {title}" if artist else title
                    if combined:
                        temp.append(combined)
        _library_cache = temp
        print(f"[Library] Successfully loaded {len(_library_cache)} songs into memory.")
        if _library_cache:
            print(f"[Library] Sample (First 3): {', '.join(_library_cache[:3])}")
        else:
            print(f"[Library] WARNING: Library is empty! Please import an M3U file.")
    return _library_cache

def build_library_from_m3u(m3u_file_path: str):
    """
    Generate the database CSV and template M3U entirely from a user-provided M3U.
    Ensures backward compatibility with the 14-column songs_full_info.csv format
    so future analytics pivots still parse correctly.
    """
    if not os.path.exists(m3u_file_path):
        raise FileNotFoundError(f"Provided M3U file not found: {m3u_file_path}")
        
    # Copy to our standard template path if it's not already the template
    if os.path.abspath(m3u_file_path) != os.path.abspath(M3U_TEMPLATE_PATH):
        # Backup existing M3U template before overwriting (path mappings are irreplaceable)
        if os.path.exists(M3U_TEMPLATE_PATH):
            try:
                shutil.copy2(M3U_TEMPLATE_PATH, f"{M3U_TEMPLATE_PATH}.bak")
                print(f"[Library] Backed up M3U template to {M3U_TEMPLATE_PATH}.bak")
            except Exception as e:
                print(f"[Library] Warning: Failed to backup M3U template: {e}")
        shutil.copy2(m3u_file_path, M3U_TEMPLATE_PATH)

        
    # C3 Fix: Backup existing CSV to protect power users from accidental overwrite
    if os.path.exists(DB_CSV_PATH):
        try:
            shutil.copy2(DB_CSV_PATH, f"{DB_CSV_PATH}.bak")
            print(f"[Library] Created backup of existing database at {DB_CSV_PATH}.bak")
        except Exception as e:
            print(f"[Library] Warning: Failed to create database backup: {e}")
    
    # Standard 14 columns from original Musicolet export
    headers = [
        "System Path (ID)", "Title", "Artist", "Album", "Genre", 
        "Year", "Duration (ms)", "Date Added", "Total Plays", 
        "Last Played Time", "Week Plays", "Month Plays", 
        "Year Plays", "Phone Path"
    ]
    
    songs = []
    with open(m3u_file_path, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

        
    for i in range(len(lines) - 1):
        if lines[i].startswith("#EXTINF"):
            info_parts = lines[i].split(",", 1)
            
            # Parse duration — handle both standard and extended EXTINF formats
            # Standard:  #EXTINF:180,Title
            # Extended:  #EXTINF:-1 tvg-id="..." tvg-name="...",Title
            duration_raw = info_parts[0].replace("#EXTINF:", "").strip()
            # Duration is always the first token before any space or attribute
            duration_token = duration_raw.split()[0] if duration_raw else "0"
            try:
                float(duration_token)
                duration = duration_token
            except ValueError:
                duration = "0"
                
            display_text = info_parts[1].strip() if len(info_parts) > 1 else ""
            
            # Skip blank lines between EXTINF and path
            path_idx = i + 1
            while path_idx < len(lines) and not lines[path_idx].strip():
                path_idx += 1
            path = lines[path_idx].strip() if path_idx < len(lines) else ""
            if not path or path.startswith("#"):
                continue

            
            # Split Artist - Title
            if " - " in display_text:
                artist, title = display_text.split(" - ", 1)
            else:
                artist = ""
                title = display_text
                
            # Create a row matching the exact 14 columns
            row = [
                "",           # System Path (ID)
                title,        # Title
                artist,       # Artist
                "",           # Album
                "",           # Genre
                "0",          # Year
                duration,     # Duration (ms)
                "0",          # Date Added
                "0",          # Total Plays
                "0",          # Last Played Time
                "0",          # Week Plays
                "0",          # Month Plays
                "0",          # Year Plays
                path          # Phone Path
            ]
            songs.append(row)
            
    # Write the CSV
    with open(DB_CSV_PATH, "w", encoding="utf-8", newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(songs)
        
    print(f"[Library] Successfully rebuilt CSV from M3U with {len(songs)} rows.")
    
    # Force reload cache
    global _library_cache
    with _library_lock:
        _library_cache = []
    get_full_library()

# === FILE PARSING ===
def extract_time_from_filename(filename):
    """
    Extracts time from Android screenshot format: Screenshot_YYYYMMDD-HHMMSS.png
    """
    match = re.search(r'Screenshot_\d{8}-(\d{2})(\d{2})(\d{2})', filename)
    if match:
        h, m, s = match.groups()
        return f"{h}:{m}:{s}"
    return None

def extract_date_from_filename(filename):
    """
    Extracts date (YYYY, MM, DD) from Android screenshot format: Screenshot_YYYYMMDD-HHMMSS.png
    """
    match = re.search(r'Screenshot_(\d{4})(\d{2})(\d{2})-\d{6}', filename)
    if match:
        y, m, d = match.groups()
        return int(y), int(m), int(d)
    return None

def is_within_time_range(time_str):
    if not time_str:
        return False
    try:
        t = datetime.strptime(time_str, "%H:%M:%S").time()
        # check if minutes is between 28 and 31
        if 28 <= t.minute <= 31:
            return True
    except ValueError:
        pass
    return False

# === TIMEFRAME SCANNER ===
def scan_folder_for_timeframes(root_folder):
    """
    Recursively scans the root folder for valid Musicolet screenshots.
    Groups them tightly into a hierarchical tree: Year -> Month -> Week -> Files.
    Returns: A nested dictionary structure.
    """
    tree = {}
    MAX_FILES_SCANNED = 150_000
    total_scanned = 0

    # Recursively traverse directory
    for dirpath, _, filenames in os.walk(root_folder):
        total_scanned += len(filenames)
        if total_scanned > MAX_FILES_SCANNED:
            print(f"[Scanner] WARNING: Exceeded {MAX_FILES_SCANNED} files. Stopping scan.")
            break

        for f in filenames:
            if not f.lower().endswith((".png", ".jpg", ".jpeg")):
                continue
                
            # Filter by matching Time Range (the vital X:29 rule)
            capture_time = extract_time_from_filename(f)
            if not is_within_time_range(capture_time):
                continue
                
            # Extract Date for Grouping
            date_info = extract_date_from_filename(f)
            if not date_info:
                continue
                
            year, month, day = date_info
            
            # Use Python's built-in ISO calendar for strict standard weeks
            try:
                 date_obj = datetime(year, month, day)
                 iso_year, iso_week, iso_day = date_obj.isocalendar()
            except ValueError:
                 continue
                 
            # Name Formatting
            month_name = date_obj.strftime("%B") # e.g., 'May'
            
            # F11: Disambiguate ISO weeks crossing year boundaries
            if iso_year != year:
                week_name = f"Week {iso_week} (ISO {iso_year})"
            else:
                week_name = f"Week {iso_week}"
            
            absolute_path = os.path.join(dirpath, f)
            
            # Construct the nested dictionary
            if year not in tree:
                tree[year] = {}
            if month_name not in tree[year]:
                tree[year][month_name] = {}
            if week_name not in tree[year][month_name]:
                tree[year][month_name][week_name] = []
                
            tree[year][month_name][week_name].append({
                "filepath": absolute_path,
                "filename": f,
                "capture_time": capture_time,
                "date_object": date_obj.strftime("%Y-%m-%d") # for sorting if necessary
            })
            
    # F14: Sort: years ascending, months in calendar order, weeks ascending
    MONTH_ORDER = ["January","February","March","April","May","June",
                   "July","August","September","October","November","December"]
    sorted_tree = {}
    for year in sorted(tree.keys()):
        sorted_tree[year] = {}
        # Sort months according to MONTH_ORDER
        sorted_months = sorted(tree[year].keys(), key=lambda m: MONTH_ORDER.index(m) if m in MONTH_ORDER else 99)
        for month in sorted_months:
            sorted_tree[year][month] = {}
            # Sort weeks by the numeric week number inside the label
            sorted_weeks = sorted(tree[year][month].keys(), 
                                 key=lambda w: int(re.search(r'\d+', w).group()) if re.search(r'\d+', w) else 0)
            for week in sorted_weeks:
                # Sort files within each week chronologically by filename
                sorted_tree[year][month][week] = sorted(
                    tree[year][month][week],
                    key=lambda f: f['filename']
                )

    print(f"[Scanner] Hierarchy complete.")
    return sorted_tree

# === OCR CLEANER ===
def clean_ocr_string(s: str) -> str:
    """Clean OCR noise while preserving short artist names (IU, BTS, RM, DJ, etc.)"""
    # Strip known OCR garbage tokens (2-char combos that are never valid music tokens)
    s = re.sub(r'(?i)\b(ld|dl|hl|iq|jq|pl|ul|bl|hd|md|rd|id)\b', '', s)
    # Strip standalone digits (track numbers, timestamps)
    s = re.sub(r'\b\d{1,2}\b', '', s)
    # Strip repeated dots (ellipsis OCR noise)
    s = re.sub(r'\.\.+', '', s)
    # Collapse whitespace
    s = re.sub(r'\s{2,}', ' ', s).strip(' -_.,')
    # Title-case with apostrophe fix (str.title() breaks "don't" -> "Don'T")
    s = re.sub(r"[A-Za-z]+('[A-Za-z]+)?", lambda m: m.group(0).capitalize(), s)
    return s.strip()

def extract_song_info(ocr_text: str, anchor_keyword: str = "musicolet"):
    """
    Extracts the relevant text block below the provided anchor keyword from the OCR output.
    Returns a single concatenated string containing all potential song/artist tokens
    to be fed into the robust rapidfuzz token_set_ratio matcher.
    """
    lines = [l.strip() for l in ocr_text.splitlines() if l.strip()]
    anchor_lower = anchor_keyword.lower()
    
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if anchor_lower in line_lower or fuzz.partial_ratio(anchor_lower, line_lower) >= 58:
            # We found the anchor! Song info is typically BELOW the anchor.
            window = lines[i+1:i+6]
            
            clean = []
            for w in window:
                # F12: Keep ASCII music chars AND Unicode letters (CJK, Hangul, etc.), plus smart quotes
                w = re.sub(r"[^\w&'’.,?!()\- ]", "", w, flags=re.UNICODE)
                # Remove standalone digit-only tokens (track numbers)
                w = re.sub(r'^\d+$', '', w.strip())
                if w:
                    clean.append(w)
                    
            if not clean:
                return None
            
            # Since our entire library is now pre-loaded in memory, we no longer need 
            # to rely on brittle regex logic (like Title Case or ALL CAPS) to guess 
            # which line is the Artist and which is the Title.
            # We simply grab the top 3 relevant lines (typically Title, Artist, Album)
            # and join them. `rapidfuzz.token_set_ratio` does not care about word order 
            # or extra noise words, so it will perfectly intersect the tokens against the DB.
            target_lines = clean[:3]
            result = " ".join(target_lines)
            
            # Remove known OCR UI artifact headers
            result = re.sub(r'\b(Ld|Dl|Hd|Id|Rd|Md|ld|dl|hd|id)\b\s*-?\s*', '', result, flags=re.IGNORECASE)
            result = result.strip(" -")
            
            return result
    return None

# === MAIN PROCESSING PIPELINE ===
def process_groups(groups_dict: dict, anchor_keyword: str = "Musicolet", use_full_image: bool = False, crop_box_override=None):
    """
    Groups: { 'Year_Month_Week': [filepaths] }
    """
    db_songs = get_full_library()
    print(f"\n[Pipeline] Initializing OCR batch processing...")
    print(f"[Pipeline] Anchor: '{anchor_keyword}' | Library Size: {len(db_songs)} records")
    
    if not db_songs:
        print("[Pipeline] CRITICAL: Library is empty! Aborting processing to prevent zero-score spam.")
        return {}

    all_results = {}
    
    # Determine which crop to use for this batch
    effective_crop = None if use_full_image else (crop_box_override or CROP_BOX_DEFAULT)
    print(f"[Pipeline] Mode: {'Full Image' if not effective_crop else f'Cropped {effective_crop}'}")
    
    anchor_lower = anchor_keyword.lower()
    
    for group_name, file_paths in groups_dict.items():
        # F13: Sort results chronologically by filename within groups
        sorted_filepaths = sorted(file_paths, key=lambda p: os.path.basename(p))
        
        print(f"\n=== Processing Group: {group_name} ({len(sorted_filepaths)} files) ===")
        group_results = []
        processed_count = 0
        valid_anchor_count = 0
        
        for filepath in sorted_filepaths:
            if not os.path.exists(filepath):
                 print(f"[Pipeline] Warning: Selected file missing -> {filepath}")
                 continue
                 
            f = os.path.basename(filepath)
            capture_time = extract_time_from_filename(f)
            
            processed_count += 1
            print(f"\n[Pipeline] Image [{processed_count}/{len(sorted_filepaths)}]: {f}")
            print(f" -> Time '{capture_time}' is within target range. Running OCR...")
            
            # 2. Image Processing & OCR
            try:
                with Image.open(filepath) as img:
                    if not effective_crop:
                        cropped = img
                    else:
                        # Ensure crop box is within actual image bounds to prevent PIL errors
                        w, h = img.size
                        l, t, r, b = effective_crop
                        safe_crop = (min(l, w), min(t, h), min(r, w), min(b, h))
                        cropped = img.crop(safe_crop)
                    
                    # F06: Dark Mode Binarization Fix
                    gray = cropped.convert("L")
                    median_brightness = _image_median_brightness(gray)
                    threshold = 128
                    if median_brightness < threshold:
                        # Invert for dark backgrounds
                        bw = gray.point(lambda p: 0 if p > threshold else 255)
                    else:
                        bw = gray.point(lambda p: 255 if p > threshold else 0)

                    
                    # F05/F09: OCR Config & Timeout
                    try:
                        text = pytesseract.image_to_string(bw, config=OCR_CONFIG, timeout=15)
                    except Exception as ocr_exc:
                        print(f" -> OCR timeout/error on {f}: {ocr_exc}")
                        text = ""
            except Exception as e:
                text = ""
                print(f" -> Image Processing Error: {e}")
                
            text_lines_for_gate = [l.strip() for l in text.splitlines() if l.strip()]
            has_anchor = False
            for _gi, _gl in enumerate(text_lines_for_gate):
                _gll = _gl.lower()
                if anchor_lower in _gll or fuzz.partial_ratio(anchor_lower, _gll) >= 58:
                    has_anchor = True
                    break
                # Check adjacent lines joined (catches OCR line-break splits)
                if _gi + 1 < len(text_lines_for_gate):
                    _combined = (_gll + text_lines_for_gate[_gi + 1].lower()).replace(" ", "")
                    if fuzz.partial_ratio(anchor_lower, _combined) >= 58:
                        has_anchor = True
                        break

            
            if not has_anchor:
                 print(f" -> '{anchor_keyword}' keyword not found. Skipping.")
                 continue
                 
            valid_anchor_count += 1
            print(f" -> '{anchor_keyword}' keyword verified! Extracting info...")
                 
            # 3. Text Extraction
            extracted_song = extract_song_info(text, anchor_keyword)
            best_match = None
            score = 0
            if extracted_song:
                 cleaned_text = clean_ocr_string(extracted_song)
                 if len(cleaned_text) >= 3 and db_songs:
                      best_match, score, _ = process.extractOne(cleaned_text, db_songs, scorer=fuzz.token_set_ratio)
                 
                 # Robust Diagnostic Logging (A01 + B04)
                 print(f" -> OCR Extracted: '{cleaned_text}'")
                 if best_match:
                     print(f" -> Match Found: '{best_match}' (Confidence: {score:.1f}%)")
                 else:
                     print(f" -> No Match Found (Score: 0)")
            else:
                 extracted_song = "Error: Could not extract string"
                 print(" -> Error: Blank OCR string.")

                
            result_entry = {
                "filepath": filepath,
                "filename": f,
                "capture_time": capture_time,
                "extracted_text": extracted_song,
                "best_match": best_match,
                "score": score
            }
            # Only include results with a match or at least extractable text.
            # Score=0 + no match = extraction failed = unactionable noise card.
            if best_match is not None or (extracted_song and not extracted_song.startswith("Error:")):
                group_results.append(result_entry)
            else:
                print(f" -> Skipping noise card (no match, failed extraction): {f}")

            
        extraction_failures = valid_anchor_count - len(group_results)
        print(f"\n[Pipeline] Group '{group_name}': {len(group_results)} matched cards, "
              f"{processed_count - valid_anchor_count} skipped (no anchor), "
              f"{extraction_failures} skipped (extraction/match failed).")
        all_results[group_name] = group_results


    return all_results

# === M3U GENERATION ===
def get_m3u_mapping():
    """Reads the template M3U to map 'Artist - Title' -> 'Filepath' using correct notation."""
    mapping = {}
    if not os.path.exists(M3U_TEMPLATE_PATH):
        return mapping
        
    with open(M3U_TEMPLATE_PATH, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

        
    for i in range(len(lines) - 1):
        if lines[i].startswith("#EXTINF"):
            info_parts = lines[i].split(",", 1)
            if len(info_parts) == 2:
                # Assuming format is exact Artist - Title
                key = info_parts[1].strip()
                # Scan forward past blank lines to find the actual path
                path_idx = i + 1
                while path_idx < len(lines) and not lines[path_idx].strip():
                    path_idx += 1
                if path_idx < len(lines):
                    path = lines[path_idx].strip()
                    if path and not path.startswith("#"):
                        mapping[key] = (lines[i].strip(), path)
                    else:
                        print(f"[Mapping] Warning: Skipped entry with no valid path: {key!r}")

    return mapping

def generate_m3u_groups(grouped_matches, output_dir: str = None):

    """
    Accepts a dictionary: {"Group Name": ["Match 1", "Match 2"]}
    Generates multiple M3U files in the output directory.
    Returns a list of created files.
    """
    target_dir = output_dir if output_dir else OUTPUT_DIR
    mapping = get_m3u_mapping()
    os.makedirs(target_dir, exist_ok=True)
    output_paths = []

    
    for group_name, matches in grouped_matches.items():
        if not matches:
            continue
            
        # Clean group name for Windows filesystem
        safe_name = re.sub(r'[^a-zA-Z0-9_\- ]', '_', group_name)
        out_path = os.path.join(target_dir, f"{safe_name}.m3u")

        
        content = ["#EXTM3U\n"]
        
        # F16: Add case-insensitive lookup and unresolved summary
        unresolved = []
        for match in matches:
            if match in mapping:
                extinf, path = mapping[match]
                content.append(f"{extinf}\n")
                content.append(f"{path}\n")
            else:
                # Try case-insensitive lookup
                match_lower = match.lower()
                fallback = next((v for k, v in mapping.items() if k.lower() == match_lower), None)
                if fallback:
                    extinf, path = fallback
                    content.append(f"{extinf}\n")
                    content.append(f"{path}\n")
                else:
                    unresolved.append(match)
                    content.append(f"# UNRESOLVED (not in m3u template): {match}\n")

        if unresolved:
            print(f"[Export] WARNING: {len(unresolved)} songs not found in M3U template for group '{group_name}':")
            for u in unresolved:
                print(f"  - {u}")
        
        with open(out_path, "w", encoding="utf-8") as out:
            out.writelines(content)
        
        output_paths.append(os.path.abspath(out_path))
        print(f"[Export] Created M3U: {out_path}")
    
    return output_paths

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="X:29 Pipeline CLI")
    parser.add_argument("--input", type=str, help="Absolute path to the screenshots folder")
    parser.add_argument("--output", type=str, default="validated_songs.m3u", help="Output M3U filename")
    parser.add_argument("--anchor", type=str, default="Musicolet", help="The name of the music player to OCR anchor to")
    parser.add_argument("--full-image", action="store_true", help="Scan the full screenshot instead of the default notification crop box")
    parser.add_argument("--no-ui", action="store_true", help="Run headlessly without the Web UI")
    args = parser.parse_args()

    if args.no_ui and args.input:
        import sys
        print(f"[CLI] Scanning: {args.input}")
        tree = scan_folder_for_timeframes(args.input)

        # F08: Flatten tree into groups for CLI mode
        cli_groups = {}
        for year, months in tree.items():
            for month, weeks in months.items():
                for week, shots in weeks.items():
                    group_key = f"{year}_{month}_{week}"
                    cli_groups[group_key] = [s['filepath'] for s in shots]

        if not cli_groups:
            print("[CLI] No valid screenshots found.")
            sys.exit(0)

        total_files = sum(len(v) for v in cli_groups.values())
        print(f"[CLI] Found {total_files} files across {len(cli_groups)} groups.")

        # Process all groups
        all_results = process_groups(cli_groups, args.anchor, args.full_image)

        # Extract matches
        grouped_matches = {}
        for group_name, results in all_results.items():
            matches = [r['best_match'] for r in results if r['best_match']]
            if matches:
                grouped_matches[group_name] = matches

        if grouped_matches:
            out_paths = generate_m3u_groups(grouped_matches, output_dir=args.output)
            print(f"[CLI] Exported {len(out_paths)} M3U files:")

            for p in out_paths:
                print(f"  {p}")
        else:
            print("[CLI] No songs matched to export.")
    else:
        print("Please run 'python app.py' to start the Web UI, or use '--no-ui --input <path>' for CLI mode.")
