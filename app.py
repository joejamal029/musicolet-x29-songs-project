from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image
import io
import os
import pathlib
import uvicorn
import mimetypes
import pipeline
import traceback
import logging
from contextlib import asynccontextmanager

mimetypes.init()
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/javascript", ".js")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Fail fast with a clear message if Tesseract is not available."""
    import subprocess
    try:
        # F21: Tesseract startup health check
        cmd = pipeline.pytesseract.pytesseract.tesseract_cmd
        result = subprocess.run(
            [cmd, "--version"],
            capture_output=True, text=True, timeout=5
        )
        print(f"[Startup] Tesseract OK: {result.stdout.splitlines()[0]}")
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"[Startup] FATAL: Tesseract not found at configured path.")
        print(f"  Path: {pipeline.pytesseract.pytesseract.tesseract_cmd}")
        print(f"  Error: {e}")
        print(f"  Fix: Install Tesseract and update tesseract_cmd in pipeline.py")
        print(f"{'='*60}\n")
    yield

app = FastAPI(title="X:29 Companion", lifespan=lifespan)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"!!! GLOBAL EXCEPTION: {exc}")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": str(exc)},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _safe_image_path(requested_path: str) -> str:
    """
    Validates image path safety:
    1. Must have an image file extension.
    2. Must be an absolute path with no relative traversal components.
    3. Must exist and be a file.
    """
    # Reject explicit traversal attempts
    if ".." in pathlib.Path(requested_path).parts:
        raise ValueError(f"Path traversal detected: {requested_path}")
    p = pathlib.Path(requested_path).resolve()
    if p.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
        raise ValueError(f"Invalid file type: {p.suffix}")
    if not p.exists():
        raise FileNotFoundError(str(p))
    if not p.is_file():
        raise ValueError(f"Path is not a file: {p}")
    return str(p)

def _safe_m3u_path(requested_path: str) -> str:
    """Validates the M3U path is within the project root directory."""
    project_root = pathlib.Path(__file__).parent.resolve()
    p = pathlib.Path(requested_path).resolve()
    if not str(p).startswith(str(project_root)):
        raise ValueError(
            f"M3U file must be located in the project directory ({project_root}). "
            f"Use /api/list_m3u_files to see available files."
        )
    if p.suffix.lower() != '.m3u':
        raise ValueError(f"File must have .m3u extension. Got: {p.suffix}")
    if not p.exists():
        raise FileNotFoundError(str(p))
    return str(p)


class ScanRequest(BaseModel):
    input_folder: str

from typing import Optional, List

class RunRequest(BaseModel):
    groups: dict[str, list[str]]
    anchor_keyword: str = "Musicolet"
    use_full_image: bool = False
    crop_mode: str = "default"
    custom_crop: Optional[List[int]] = None # [L, T, R, B]

class M3URequest(BaseModel):
    grouped_matches: dict[str, list[str]]

class ImportM3URequest(BaseModel):
    m3u_path: str

@app.get("/", response_class=HTMLResponse)
def read_root():
    root_dir = pathlib.Path(__file__).parent.resolve()
    index_path = root_dir / "frontend" / "index.html"
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"!!! Error reading index.html: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/static/style.css")
async def get_css():
    return FileResponse("frontend/style.css", media_type="text/css")

@app.get("/static/script.js")
async def get_js():
    return FileResponse("frontend/script.js", media_type="application/javascript")

@app.post("/api/scan_folder")
def scan_folder(req: ScanRequest):
    if not os.path.exists(req.input_folder):
        raise HTTPException(status_code=400, detail="Path does not exist")
    if not os.path.isdir(req.input_folder):
        raise HTTPException(status_code=400, detail="Path exists but is not a directory. Please provide a folder path, not a file path.")

    try:
        tree = pipeline.scan_folder_for_timeframes(req.input_folder)
        return {"status": "success", "tree": tree}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/run_pipeline")
def run_pipeline(req: RunRequest):
    if not req.groups:
        raise HTTPException(status_code=400, detail="No groups selected.")
    try:
        # Resolve effective crop box from request
        crop_box = None
        if not req.use_full_image:
            if req.crop_mode == "custom" and req.custom_crop and len(req.custom_crop) == 4:
                crop_box = tuple(req.custom_crop)
            else:
                crop_box = pipeline.CROP_PRESETS.get(req.crop_mode, pipeline.CROP_BOX_DEFAULT)

        results = pipeline.process_groups(
            req.groups, 
            req.anchor_keyword, 
            req.use_full_image, 
            crop_box_override=crop_box
        )
        return {"status": "success", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/library")
def get_library():
    try:
        library = pipeline.get_full_library()
        return {"library": library}
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/list_m3u_files")
def list_m3u_files():
    """Returns a list of all M3U files in the project root suitable for importing."""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        m3u_files = []
        for file in os.listdir(base_dir):
            if file.lower().endswith('.m3u'):
                file_path = os.path.join(base_dir, file)
                if os.path.isfile(file_path):
                    m3u_files.append({
                        "name": file,
                        "path": file_path
                    })
        return {"m3u_files": m3u_files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reload_library")
def reload_library():
    """F10: Force reload the song library from CSV."""
    pipeline._library_cache = []
    library = pipeline.get_full_library()
    return {"status": "reloaded", "count": len(library)}

@app.post("/api/import_m3u")
def import_m3u(req: ImportM3URequest):
    try:
        try:
            safe_path = _safe_m3u_path(req.m3u_path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="M3U file not found in project directory.")
        
        pipeline.build_library_from_m3u(safe_path)
        library = pipeline.get_full_library()
        return {"status": "success", "count": len(library)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate_m3u")
def generate_m3u(req: M3URequest):
    try:
        out_paths = pipeline.generate_m3u_groups(req.grouped_matches)
        return {"status": "success", "output_paths": out_paths, "count": len(out_paths)}
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/image")
def get_image(path: str, processed: bool = False, use_full_image: bool = False, 
              crop_mode: str = "default", l: int = None, t: int = None, r: int = None, b: int = None):
    try:
        # F17: Path Security
        path = _safe_image_path(path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Image not found")

    if processed:
        try:
            with Image.open(path) as img:
                if use_full_image:
                    cropped = img
                else:
                    # Resolve crop box
                    if l is not None and t is not None and r is not None and b is not None:
                        crop_box = (l, t, r, b)
                    else:
                        crop_box = pipeline.CROP_PRESETS.get(crop_mode, pipeline.CROP_BOX_DEFAULT)
                    
                    if crop_box:
                        w, h = img.size
                        cl, ct, cr, cb = crop_box
                        safe_crop = (min(cl, w), min(ct, h), min(cr, w), min(cb, h))
                        cropped = img.crop(safe_crop)
                    else:
                        cropped = img
                
                # F06: Dark Mode Preview Fix (sync with pipeline)
                gray = cropped.convert("L")
                median_brightness = pipeline._image_median_brightness(gray)
                threshold = 128
                if median_brightness < threshold:
                    bw = gray.point(lambda p: 0 if p > threshold else 255)
                else:
                    bw = gray.point(lambda p: 255 if p > threshold else 0)

                
                buf = io.BytesIO()
                bw.save(buf, format="PNG")
                buf.seek(0)
                return StreamingResponse(buf, media_type="image/png")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Image processing failed: {e}")
    
    return FileResponse(path)

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=False)

