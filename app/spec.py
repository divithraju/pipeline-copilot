"""Pipeline spec: a small, validated, declarative language the LLM must emit.
The LLM never writes executable code, only this spec. A deterministic compiler turns it into SQL."""
import re
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field, field_validator

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
# Scalar expressions only: no subqueries, no file/network functions, no DDL/DML, no statement separators.
BAD_EXPR = re.compile(
    r"(;|--|/\*|\b(select|drop|delete|insert|update|attach|detach|copy|install|load|pragma|create|alter|"
    r"export|import|call|set|glob|getenv|system|read_\w+|http\w*|union|with)\b)", re.I)


def check_ident(v: str) -> str:
    if not IDENT.match(v):
        raise ValueError(f"invalid identifier: {v!r}")
    return v


def check_expr(v: str) -> str:
    if len(v) > 500 or BAD_EXPR.search(v):
        raise ValueError(f"unsafe or too long expression: {v!r}")
    return v


class Source(BaseModel):
    path: str
    format: Literal["csv", "parquet", "json"] = "csv"

    @field_validator("path")
    @classmethod
    def no_traversal(cls, v):
        if ".." in v or v.startswith(("/", "~")) or "://" in v:
            raise ValueError("source path must be relative to the data directory")
        return v


class Filter(BaseModel):
    type: Literal["filter"]
    expr: str
    _e = field_validator("expr")(check_expr)


class Select(BaseModel):
    type: Literal["select"]
    columns: list[str]
    _c = field_validator("columns")(lambda v: [check_ident(x) for x in v])


class Rename(BaseModel):
    type: Literal["rename"]
    mapping: dict[str, str]

    @field_validator("mapping")
    @classmethod
    def ok(cls, v):
        for a, b in v.items():
            check_ident(a), check_ident(b)
        return v


class Cast(BaseModel):
    type: Literal["cast"]
    column: str
    to: Literal["INTEGER", "BIGINT", "DOUBLE", "DECIMAL(18,2)", "VARCHAR", "DATE", "TIMESTAMP", "BOOLEAN"]
    _c = field_validator("column")(check_ident)


class Derive(BaseModel):
    type: Literal["derive"]
    name: str
    expr: str
    _n = field_validator("name")(check_ident)
    _e = field_validator("expr")(check_expr)


class Dedupe(BaseModel):
    type: Literal["dedupe"]
    keys: list[str]
    order_by: str | None = None   # keep the first row per key after ordering, e.g. "order_date DESC"
    _k = field_validator("keys")(lambda v: [check_ident(x) for x in v])

    @field_validator("order_by")
    @classmethod
    def ob(cls, v):
        return check_expr(v) if v else v


class Metric(BaseModel):
    name: str
    expr: str
    _n = field_validator("name")(check_ident)
    _e = field_validator("expr")(check_expr)


class Aggregate(BaseModel):
    type: Literal["aggregate"]
    group_by: list[str]
    metrics: list[Metric]
    _g = field_validator("group_by")(lambda v: [check_ident(x) for x in v])


Step = Annotated[Union[Filter, Select, Rename, Cast, Derive, Dedupe, Aggregate], Field(discriminator="type")]


class Pipeline(BaseModel):
    name: str
    source: Source
    steps: list[Step] = Field(min_length=1, max_length=20)
    _n = field_validator("name")(check_ident)
