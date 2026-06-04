# X:29 Companion — Developer Edition

**The architect's guide to the inner workings and future trajectory of the X:29 engine.**

This pipeline is a dual-mode data processing engine. Today it generates M3U playlists from OCR-extracted screenshots. Tomorrow, it is the analytical backbone for a long-term behavioral music study.

## 🧠 The Dual-Mode Database Architecture

The application uses a 14-column `songs_full_info.csv` as its active in-memory brain for the RapidFuzz matching engine. How that CSV is populated depends on the user:

### 1. The Power-User Workflow (Zero-Config Rich Analytics)
Place a real, scraped `songs_full_info.csv` containing actual SQLite data in the project root. **The application will natively load it into RAM on boot.** No UI import required.

All 14 columns (`Total Plays`, `Last Played Time`, `Date Added`, `Week/Month/Year Plays`) are preserved intact. When the Analytics Phase arrives, the historical data is already exactly where it needs to be.

### 2. The General Public Workflow (M3U Ingestion)
For users without a scraped database, the `/api/import_m3u` endpoint reconstructs a "dummy" `songs_full_info.csv` from a standard M3U backup. Analytic fields are zeroed out but the 14-column schema is strictly enforced, ensuring future analytics features gracefully degrade for public users without schema mismatches.

## 🗺️ Project Roadmap & Vision

### Phase A: OCR Pipeline (✅ Complete)
The current engine. Screenshot → OCR → Fuzzy Match → M3U Export. Universal player support, dark mode binarization, confidence scoring, and visual validation.

### Phase B: Behavioral Analytics (🔬 Next)
This is the real ambition. The X:29 ritual has generated ~3 months of timestamped musical snapshots from a library of ~3,700 songs. The next phase will mine this data:

- **Frequency Correlation**: Which songs appear disproportionately often at X:29? Is it random shuffle, or does listening behavior cluster around certain tracks?
- **Artist/Genre Heatmaps**: Time-of-day and day-of-week patterns. Do certain genres dominate mornings vs. late nights?
- **Historical Trend Lines**: How does the rotation evolve over weeks and months? Which songs enter, persist, and fade?
- **Timeframe-Sliced Analytics**: Drill into any ISO week or month to see the micro-snapshot of that period's listening identity.

### Phase C: M3U Haven Integration (🔗 Planned)
A companion application—**M3U Haven**—provides large-scale manipulation of M3U files. Future integration would allow bulk playlist surgery (merging, splitting, filtering, deduplication) directly from the X:29 output pipeline.

## 🛠️ Sprint Hardening & Technical Specs

- **Strict Pathing Limits**: `os.walk` capped at 150k files to accommodate massive screenshot libraries.
- **Tesseract Configuration**: `--oem 1 --psm 6`, tuned for uniform notification text blocks.
- **Visual Binarization**: Optimized histogram-based median brightness calculation. If `< 128` (dark mode), the image is inverted before OCR.
- **Universal OCR Anchor**: The player keyword is fully parameterized. Defaults to "Musicolet". Includes a **Fuzzy Anchor Gate** (tuned to 58%) to robustly catch the keyword despite stylistically diverse player fonts or mild read errors.
- **OCR Length Gate**: Tuned to **3 characters** to preserve extremely short artist or track names (e.g., "IU", "BTS") before database matching.
- **Crop Box Guard**: Evolves past the static box. Defaults to `(0, 174, 720, 528)` (720p), but the API accepts dynamic `CROP_PRESETS` (1080p, 1440p) or manual `[L, T, R, B]` override arrays for complete custom control. A `use_full_image` flag bypasses cropping altogether.
- **Security Sandboxing**:
  - `esc()` XSS helper for all DOM-injected content.
  - Path traversal guard on `/api/image`.
  - CORS restricted to `localhost:8080`.
- **Threading Stability**: Library cache wrapped in `threading.Lock` to prevent race conditions during reloads and imports.

## 🚀 Execution

```bash
# Start the full API & Frontend stack
python app.py

# Headless batch processing
python pipeline.py --no-ui --input "C:\Absolute\Path\To\Screenshots"

# Universal: Different player + full image scan
python pipeline.py --no-ui --anchor "Spotify" --full-image --input "C:\path\to\Screenshots"
```

*Architected for flawless execution and limitless analytic scalability.*
