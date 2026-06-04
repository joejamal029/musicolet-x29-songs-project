# X:29 Companion

**X:29 Companion** is a locally-hosted OCR pipeline and web application that turns timestamped Android screenshots into perfectly formatted M3U playlists.

## The Story Behind "X:29"

The number **29** has followed me through life in ways that stopped feeling like coincidence a long time ago. My national ID ends in 29. I entered high school ranked 29th—and left ranked 29th. Six years ago, when I first got a phone, I noticed I kept catching the clock at **X:29**—12:29, 17:29, 03:29—at random, unplanned moments throughout the day.

I decided to lean into it. Every time I saw X:29, I'd take a screenshot—a random snapshot of that exact moment of my existence. What was on-screen, what I was doing, what was playing.

In late 2023, I intentionally focused this ritual on **music**. Whatever was playing on my phone at X:29, I'd capture it in a playlist. No curation, no choosing favorites—just whatever happened to be on at that exact moment. Over three months, I compiled a raw, unfiltered musical diary. A document of my listening life at the mercy of a clock.

The result was ~20,000 screenshots spanning years of this ritual, with roughly 60% containing active music playback. I envisioned a way to automate the extraction of those songs into playlists. I didn't know how at the time, but I knew it was possible. **X:29 Companion** is that vision realized.

## ✨ Key Features

- **Automated Timeframe Scanning**: Recursively scans Android screenshot folders and groups images into a strict calendar hierarchy (Year → Month → ISO Week), sorted chronologically.
- **Advanced OCR Engine**: 
  - Dynamically extracts artist and title from Android notification-area text using a configurable player keyword anchor.
  - Features **Dark Mode Binarization**—automatically detects and inverts dark-background images for high OCR accuracy regardless of OS theme.
  - Robust text handling: supports ALL-CAPS artists, short names (IU, BTS, 10cm), title-casing with apostrophes, and international Unicode characters (CJK, Hangul, accented Latin).
- **Universal Player Support**: Not limited to any single music player. Type any player name (Spotify, Poweramp, Musicolet) and the engine adapts. Defaults to Musicolet.
- **Fuzzy Database Matching**: Compares cleaned OCR text against an in-memory library using token-set-ratio matching (`rapidfuzz`) to resolve the exact local audio file path.
- **Visual Validation UI**: A modern, glassmorphism-styled web interface for reviewing OCR "vision previews", verifying match confidence scores, manually correcting matches, and removing false positives.
- **Confidence Score Sorting**: Instantly sort results by lowest confidence to surface weak matches for correction, or revert to chronological order—without losing any manual edits.
- **Bulk M3U Export**: Generates relative-path `.m3u` playlists grouped by capture timeframe, with case-insensitive fallbacks and unresolved-song reporting.
- **Headless CLI Mode**: Process thousands of images silently from the terminal.

## 🛠️ Technology Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn
- **Image Processing & OCR**: Pillow (PIL), PyTesseract (`--oem 1 --psm 6`)
- **Text Matching**: RapidFuzz
- **Frontend**: Vanilla JavaScript, HTML5, CSS3 (Custom Glass-Morphism Design System)

## 📋 Prerequisites

1. **Python 3.10+**
2. **Tesseract OCR Engine**:
   - Must be installed on your system.
   - For Windows, download from [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki).
   - The pipeline auto-detects Tesseract via `PATH`. If not found, it falls back to the standard Windows install location.

## 🚀 Installation & Setup

1. **Clone or download the repository.**
2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Prepare your Library**:
   You need an M3U backup of your music library. Export one from your music player app and place the `.m3u` file in the project root folder.
4. **Start the Web Server**:
   ```bash
   python app.py
   ```
5. **Access the UI**: Open `http://localhost:8080` in your browser.

## 🎮 Usage Guide

### Phase 1: Initial Library Setup
1. **Export from Phone**: In your music player app, export a full backup M3U playlist of your entire library and place that file in the project root.
2. **Start the Web Server**: `python app.py`
3. **Import to Pipeline**: At `http://localhost:8080`, select your `.m3u` file from the dropdown and click **Import M3U**.

### Phase 2: Processing Screenshots

#### Universal Adaptability & OCR Region Options
By default, the system extracts text from a specific bounding box `(0, 174, 720, 528)` optimized for standard Android notification-area screenshots on 720p screens.

To accommodate different devices or layouts, the web interface provides a flexible **Crop Mode** dropdown:

1. **Default (720p)**: The standard crop box optimized for 720p displays.
2. **1080p / 1440p Resolution**: Scaled preset crop boxes designed for higher pixel-density displays.
3. **Scan Full Image**: Bypasses the crop entirely and scans the whole screenshot. Slightly slower, but universally compatible regardless of scaling.
4. **Custom Dimensions**: Allows you to enter exact `Left`, `Top`, `Right`, and `Bottom` pixel coordinates to perfectly wrap your specific music player's notification area.

#### Processing Steps
1. Input the absolute path to your `Screenshots` folder and click **Scan Folder**.
2. Select Years, Months, or Weeks from the generated tree.
3. Click **Process Selected**. The app crops, OCRs, and fuzzy-matches the songs.
4. Review the cards. Use the dropdown to manually correct any wrong matches.
5. Click **Export to M3U** to generate playlist files in the `output/` directory.

### CLI Mode (Headless)
```bash
python pipeline.py --no-ui --input "C:\path\to\Screenshots"

# With a different music player
python pipeline.py --no-ui --anchor "Spotify" --full-image --input "C:\path\to\Screenshots"
```

## 🔐 Security & Constraints
- **Local Sandbox**: CORS locked to `localhost:8080`.
- **Path Traversal Defense**: The `/api/image` endpoint validates against arbitrary file reads.
- **XSS Protection**: All dynamically rendered data is securely escaped.

---
*Built to bring order to spontaneous musical discoveries.*
