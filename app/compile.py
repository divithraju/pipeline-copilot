"""Deterministic spec → DuckDB SQL (a chain of CTEs). No LLM involved here."""
from .spec import Pipeline


def q(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def compile_sql(p: Pipeline) -> str:
    ctes, prev = ["s0 AS (SELECT * FROM src)"], "s0"
    for i, s in enumerate(p.steps, 1):
        name = f"s{i}"
        if s.type == "filter":
            body = f"SELECT * FROM {prev} WHERE {s.expr}"
        elif s.type == "select":
            body = f"SELECT {', '.join(q(c) for c in s.columns)} FROM {prev}"
        elif s.type == "rename":
            body = f"SELECT * RENAME ({', '.join(f'{q(a)} AS {q(b)}' for a, b in s.mapping.items())}) FROM {prev}"
        elif s.type == "cast":
            body = f"SELECT * REPLACE (CAST({q(s.column)} AS {s.to}) AS {q(s.column)}) FROM {prev}"
        elif s.type == "derive":
            body = f"SELECT *, ({s.expr}) AS {q(s.name)} FROM {prev}"
        elif s.type == "dedupe":
            order = f" ORDER BY {s.order_by}" if s.order_by else ""
            body = (f"SELECT * FROM {prev} QUALIFY row_number() OVER "
                    f"(PARTITION BY {', '.join(q(k) for k in s.keys)}{order}) = 1")
        else:  # aggregate
            sel = [q(g) for g in s.group_by] + [f"({m.expr}) AS {q(m.name)}" for m in s.metrics]
            grp = f" GROUP BY {', '.join(q(g) for g in s.group_by)}" if s.group_by else ""
            body = f"SELECT {', '.join(sel)} FROM {prev}{grp}"
        ctes.append(f"{name} AS ({body})")
        prev = name
    return "WITH " + ",\n".join(ctes) + f"\nSELECT * FROM {prev}"
