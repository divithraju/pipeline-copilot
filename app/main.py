import json, uuid
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError
from . import codegen, engine, planner
from .config import MAX_UPLOAD_MB, UPLOAD_DIR
from .spec import Pipeline

app = FastAPI(title="PipelineCopilot", version="0.1.0")


class PlanReq(BaseModel):
    request: str
    source_path: str
    format: str = "csv"


def _pipeline(spec: dict) -> Pipeline:
    try:
        return Pipeline.model_validate(spec)
    except ValidationError as e:
        raise HTTPException(422, json.loads(e.json()))


@app.get("/")
def index():
    return FileResponse("web/index.html")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in {"csv", "parquet", "json"}:
        raise HTTPException(400, "Upload a .csv, .parquet or .json file")
    data = await file.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File larger than {MAX_UPLOAD_MB} MB")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    rel = f"uploads/{uuid.uuid4().hex}.{ext}"
    (UPLOAD_DIR.parent / rel).write_bytes(data)
    return {"source_path": rel, "format": ext, "profile": engine.profile_file(rel, ext)}


@app.post("/api/plan")
def plan(req: PlanReq):
    try:
        profile = engine.profile_file(req.source_path, req.format)
        return planner.plan(req.request, req.source_path, req.format, profile).model_dump()
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(422, str(e))


@app.post("/api/run")
def run(spec: dict):
    try:
        return engine.run_pipeline(_pipeline(spec))
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(422, str(e))
    except Exception as e:  # DuckDB binder/runtime errors (unknown column, bad expression...)
        raise HTTPException(422, f"Pipeline failed: {e}")


@app.post("/api/codegen")
def gen(spec: dict):
    p = _pipeline(spec)
    return {"python": codegen.python_script(p), "airflow_dag": codegen.airflow_dag(p)}
