import os, pathlib

DATA_DIR = pathlib.Path(os.getenv("DATA_DIR", "data")).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
PLANNER_MODEL = os.getenv("PLANNER_MODEL", "claude-sonnet-5-5")
