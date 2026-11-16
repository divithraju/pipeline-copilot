"""Sandboxed execution on DuckDB. The source file is loaded first, then external access is locked,
so spec expressions can never read other files or the network."""
import pathlib
import duckdb
from .compile import compile_sql, q
from .config import DATA_DIR
from .spec import Pipeline, Dedupe


def resolve(rel: str) -> pathlib.Path:
    p = (DATA_DIR / rel).resolve()
    if DATA_DIR not in p.parents:
        raise ValueError("path escapes data directory")
    if not p.is_file():
        raise FileNotFoundError(rel)
    return p


def open_source(path: pathlib.Path, fmt: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute("SET memory_limit='512MB'")
    con.execute("SET threads=2")
    fn = {"csv": "read_csv", "parquet": "read_parquet", "json": "read_json_auto"}[fmt]
    extra = ", header=true" if fmt == "csv" else ""
    con.execute(f"CREATE TABLE src AS SELECT * FROM {fn}(?{extra})", [str(path)])
    con.execute("SET enable_external_access=false")
    con.execute("SET lock_configuration=true")
    return con


def quality_report(con, p: Pipeline, rows_in: int) -> dict:
    cols = [r[0] for r in con.execute("DESCRIBE out").fetchall()]
    rows_out = con.execute("SELECT count(*) FROM out").fetchone()[0]
    nulls = {}
    if cols and rows_out:
        sel = ", ".join(f"sum(CASE WHEN {q(c)} IS NULL THEN 1 ELSE 0 END)" for c in cols)
        nulls = {c: round(n / rows_out, 4) for c, n in zip(cols, con.execute(f"SELECT {sel} FROM out").fetchone())}
    warnings = []
    if rows_out == 0:
        warnings.append("Output is empty. Check your filters.")
    for c, r in nulls.items():
        if r > 0.2:
            warnings.append(f"Column '{c}' is {r:.0%} null in the output.")
    for s in p.steps:
        if isinstance(s, Dedupe) and all(k in cols for k in s.keys):
            d = con.execute(f"SELECT count(*) - count(DISTINCT ({', '.join(q(k) for k in s.keys)})) FROM out").fetchone()[0]
            if d:
                warnings.append(f"{d} duplicate rows remain on keys {s.keys}.")
    return {"rows_in": rows_in, "rows_out": rows_out,
            "rows_dropped_pct": round(100 * (rows_in - rows_out) / rows_in, 2) if rows_in else 0,
            "null_rate": nulls, "warnings": warnings}


def run_pipeline(p: Pipeline, limit: int = 20) -> dict:
    con = open_source(resolve(p.source.path), p.source.format)
    rows_in = con.execute("SELECT count(*) FROM src").fetchone()[0]
    sql = compile_sql(p)
    con.execute(f"CREATE TABLE out AS {sql}")
    cur = con.execute(f"SELECT * FROM out LIMIT {int(limit)}")
    cols = [d[0] for d in cur.description]
    return {"sql": sql, "columns": cols, "preview": [list(r) for r in cur.fetchall()],
            "quality": quality_report(con, p, rows_in)}


def profile_file(rel: str, fmt: str = "csv") -> dict:
    con = open_source(resolve(rel), fmt)
    n = con.execute("SELECT count(*) FROM src").fetchone()[0]
    cols = []
    for name, typ, *_ in con.execute("DESCRIBE src").fetchall():
        nn, dist = con.execute(f"SELECT count(*) - count({q(name)}), count(DISTINCT {q(name)}) FROM src").fetchone()
        cols.append({"name": name, "type": typ, "null_rate": round(nn / n, 4) if n else 0, "distinct": dist})
    sample = con.execute("SELECT * FROM src LIMIT 5").fetchall()
    return {"rows": n, "columns": cols, "sample": [list(r) for r in sample]}
