r"""
Creates a clean, production-ready source code zip archive outside the project folder.
Destination:
  1. c:\Users\Sakshi\Desktop\Naukri\v17\naukri-job\naukri-job.zip (directly outside inner project folder)
  2. c:\Users\Sakshi\Desktop\Naukri\v17\naukri-job.zip (in v17 root folder)

Strictly excludes:
  - Personal data & credentials: .env, data/sessions/*, data/resumes/*, data/users_store.json
  - Runtime caches: data/cache/*, data/config/runtime.json, data/config/*.bak
  - Dependency & build artifacts: node_modules, dist, __pycache__, .pytest_cache, .ruff_cache, tsconfig.tsbuildinfo
  - Version control & editor metadata: .git, .idea, .vscode, .agents, .mimosa, .gemini
"""
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Destination paths outside the project folder
DEST_ZIP_PARENT = PROJECT_ROOT.parent / "naukri-job.zip"
DEST_ZIP_V17 = PROJECT_ROOT.parent.parent / "naukri-job.zip"

EXCLUDE_DIRS = {
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".git",
    ".idea",
    ".vscode",
    ".agents",
    ".mimosa",
    ".gemini",
}

EXCLUDE_FILES = {
    ".env",
    "users_store.json",
    "runtime.json",
    "runtime.corrupt.bak",
    "tsconfig.tsbuildinfo",
}

EXCLUDE_EXTS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".log",
    ".bak",
    ".tmp",
    ".zip",
}

DATA_SUBDIRS_TO_KEEP_EMPTY = [
    "sessions",
    "resumes",
    "cache",
    "config",
]

def create_zip():
    print("=" * 75)
    print("NAUKRI & LINKEDIN AUTONOMOUS BOT — SOURCE CODE ARCHIVER")
    print("=" * 75)
    print(f"Source Root  : {PROJECT_ROOT}")
    print(f"Destination 1: {DEST_ZIP_PARENT}")
    print(f"Destination 2: {DEST_ZIP_V17}")
    print("-" * 75)

    t0 = time.time()
    file_count = 0
    total_bytes = 0

    # Ensure parent directories exist
    DEST_ZIP_PARENT.parent.mkdir(parents=True, exist_ok=True)
    DEST_ZIP_V17.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(DEST_ZIP_PARENT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(PROJECT_ROOT):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

            rel_root = Path(root).relative_to(PROJECT_ROOT)
            parts = rel_root.parts

            # Skip all runtime / user data files inside data/
            if len(parts) > 0 and parts[0] == "data":
                continue

            for file in files:
                file_path = Path(root) / file
                rel_path = rel_root / file
                ext = file_path.suffix.lower()

                # Skip sensitive or build files
                if file in EXCLUDE_FILES or ext in EXCLUDE_EXTS:
                    continue

                # Relative path inside zip, prefixed with 'naukri-job/'
                arcname = Path("naukri-job") / rel_path

                try:
                    zf.write(file_path, arcname=str(arcname))
                    file_count += 1
                    total_bytes += file_path.stat().st_size
                except Exception as e:
                    print(f"  Warning: could not add {file_path}: {e}")

        # Add clean placeholder .gitkeep files for data subdirectories
        for sub in DATA_SUBDIRS_TO_KEEP_EMPTY:
            keep_arcname = Path("naukri-job") / "data" / sub / ".gitkeep"
            zf.writestr(str(keep_arcname), "")
            file_count += 1

    # Also copy to DEST_ZIP_V17 so it's readily accessible in both parent directories
    shutil.copy2(DEST_ZIP_PARENT, DEST_ZIP_V17)

    elapsed = time.time() - t0
    zip_size_mb = DEST_ZIP_PARENT.stat().st_size / (1024 * 1024)
    orig_size_mb = total_bytes / (1024 * 1024)

    print("=" * 75)
    print("SUCCESS: Clean source code archive created successfully!")
    print(f"  Archive 1 (Parent Dir) : {DEST_ZIP_PARENT}")
    print(f"  Archive 2 (v17 Dir)    : {DEST_ZIP_V17}")
    print(f"  Total Files Included   : {file_count:,}")
    print(f"  Original Source Size   : {orig_size_mb:.2f} MB")
    print(f"  Compressed Zip Size    : {zip_size_mb:.2f} MB")
    print(f"  Time Taken             : {elapsed:.2f} seconds")
    print("=" * 75)
    print("Safety Verification:")
    print("  [x] node_modules & dist excluded")
    print("  [x] .env excluded (.env.example included)")
    print("  [x] Personal sessions & cookies excluded")
    print("  [x] Personal resumes excluded")
    print("  [x] User accounts database excluded")
    print("  [x] .git & editor metadata excluded")
    print("=" * 75)

if __name__ == "__main__":
    create_zip()
