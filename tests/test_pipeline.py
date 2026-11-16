import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from app import engine, planner
from app.compile import compile_sql
from app.main import app
from app.spec import Pipeline

SPEC = {"name": "monthly_revenue", "source": {"path": "examples/orders.csv", "format": "csv"}, "steps": [
    {"type": "dedupe", "keys": ["order_id"]},
    {"type": "filter", "expr": "lower(status) = 'completed' AND amount IS NOT NULL"},
    {"type": "derive", "name": "month", "expr": "strftime(CAST(order_date AS DATE), '%Y-%m')"},
    {"type": "aggregate", "group_by": ["country", "month"],
     "metrics": [{"name": "revenue", "expr": "sum(amount)"}, {"name": "orders", "expr": "count(*)"}]}]}


def test_compile_and_run():
    p = Pipeline.model_validate(SPEC)
    assert "QUALIFY" in compile_sql(p)
    res = engine.run_pipeline(p, limit=5)
    q = res["quality"]
    assert q["rows_in"] == 66 and q["rows_out"] > 0
    assert res["columns"] == ["country", "month", "revenue", "orders"]


def test_dedupe_removes_duplicates():
    spec = {**SPEC, "steps": [{"type": "dedupe", "keys": ["order_id"]}]}
    res = engine.run_pipeline(Pipeline.model_validate(spec))
    assert res["quality"]["rows_out"] == 60 and res["quality"]["warnings"] == []


@pytest.mark.parametrize("bad", [
    "1=1; DROP TABLE src", "x IN (SELECT 1)", "read_csv('/etc/passwd')", "a -- comment", "getenv('HOME') = ''"])
def test_unsafe_expressions_rejected(bad):
    with pytest.raises(ValidationError):
        Pipeline.model_validate({**SPEC, "steps": [{"type": "filter", "expr": bad}]})


@pytest.mark.parametrize("path", ["../secret.csv", "/etc/passwd", "http://x.com/a.csv"])
def test_bad_source_path_rejected(path):
    with pytest.raises(ValidationError):
        Pipeline.model_validate({**SPEC, "source": {"path": path}})


def test_bad_identifier_rejected():
    with pytest.raises(ValidationError):
        Pipeline.model_validate({**SPEC, "steps": [{"type": "select", "columns": ["a; drop"]}]})


def test_planner_repairs_invalid_output():
    calls = []
    def fake(messages):
        calls.append(messages)
        import json
        return "not json" if len(calls) == 1 else json.dumps(SPEC)
    p = planner.plan("monthly revenue", "examples/orders.csv", "csv", {}, call=fake)
    assert p.name == "monthly_revenue" and len(calls) == 2


def test_api_run_and_codegen():
    c = TestClient(app)
    r = c.post("/api/run", json=SPEC)
    assert r.status_code == 200 and r.json()["quality"]["rows_out"] > 0
    g = c.post("/api/codegen", json=SPEC).json()
    assert "duckdb" in g["python"] and "DAG" in g["airflow_dag"]
    bad = c.post("/api/run", json={**SPEC, "steps": [{"type": "filter", "expr": "nope > 1"}]})
    assert bad.status_code == 422


def test_rename_and_select_reorder():
    spec = {**SPEC, "steps": [
        {"type": "rename", "mapping": {"customer_id": "customer", "amount": "total"}},
        {"type": "select", "columns": ["order_id", "customer", "total"]}]}
    res = engine.run_pipeline(Pipeline.model_validate(spec))
    assert res["columns"] == ["order_id", "customer", "total"] and res["quality"]["rows_out"] == 66


def test_all_step_types_run():
    spec = {**SPEC, "steps": [
        {"type": "cast", "column": "amount", "to": "DECIMAL(18,2)"},
        {"type": "derive", "name": "status_clean", "expr": "lower(status)"},
        {"type": "dedupe", "keys": ["order_id"], "order_by": "order_date DESC"},
        {"type": "select", "columns": ["order_id", "status_clean", "amount"]}]}
    assert engine.run_pipeline(Pipeline.model_validate(spec))["quality"]["rows_out"] == 60
