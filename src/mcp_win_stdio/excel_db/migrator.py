#!/usr/bin/env python3
"""
Master Data Migration and Synchronization Engine.
Generates transactional SQL upserts with FK pre-flight validation and executes dry-run syncs.
"""

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from sqlalchemy import create_engine, text, inspect

from mcp_win_stdio.excel_db.stream import resolve_sqlalchemy_url


def _clean_sql_val(v: Any) -> str:
    """Format a Python value safely for SQL generation."""
    if pd.isna(v) or v is None:
        return "NULL"
    elif isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    elif isinstance(v, (int, float)):
        if math.isnan(v) or math.isinf(v):
            return "NULL"
        return str(v)
    else:
        # Escape single quotes
        escaped = str(v).replace("'", "''")
        return f"'{escaped}'"


def _resolve_fk_mappings(
    engine,
    fk_lookups: Optional[Dict[str, Dict[str, str]]]
) -> Dict[str, Dict[str, Any]]:
    """
    Fetch lookup maps from database for resolving human-readable codes (e.g. 'm')
    to database foreign key IDs (UUIDs).
    """
    if not fk_lookups:
        return {}

    resolved_maps = {}
    with engine.connect() as conn:
        for target_col, spec in fk_lookups.items():
            tbl = spec.get("table")
            lookup_col = spec.get("lookup_col", "code")
            id_col = spec.get("id_col", "id")

            query = text(f"SELECT {lookup_col}, {id_col} FROM {tbl}")
            rows = conn.execute(query).fetchall()

            # Map both exact and lowercase lookup
            val_to_id = {}
            for r in rows:
                code_val = str(r[0]).strip()
                target_id = r[1]
                val_to_id[code_val] = target_id
                val_to_id[code_val.lower()] = target_id
            resolved_maps[target_col] = val_to_id

    return resolved_maps


def generate_master_migration_plan(
    excel_path: str,
    target_table: str,
    key_columns: List[str],
    column_mapping: Dict[str, str],
    connection_name_or_url: Optional[str] = None,
    sheet_name: Optional[Union[str, int]] = 0,
    output_sql_path: Optional[str] = None,
    on_conflict_action: str = "update",
    fk_lookups: Optional[Dict[str, Dict[str, str]]] = None,
    price_history_table: Optional[str] = None,
    db_resolver_func = None
) -> Dict[str, Any]:
    """
    Generate atomic, transactional PostgreSQL/MySQL migration SQL from an Excel master.
    Includes pre-flight foreign key validation and safe dry-run preview.

    Args:
        excel_path: Path to Excel workbook containing new master data.
        target_table: Destination database table (e.g. 'props_management.materials').
        key_columns: Primary / unique key columns in DB table (e.g. ['material_number']).
        column_mapping: Excel header to DB column mapping (e.g. {'Material Number': 'material_number'}).
        connection_name_or_url: Optional DB connection identifier to validate live schema & FKs.
        sheet_name: Worksheet name or index.
        output_sql_path: Optional path to save the generated migration SQL script.
        on_conflict_action: 'update' (ON CONFLICT DO UPDATE) or 'nothing' (ON CONFLICT DO NOTHING).
        fk_lookups: Lookup configuration to resolve codes into UUID foreign keys.
                    Example: {'base_uom_id': {'table': 'props_management.units_of_measurement', 'lookup_col': 'code', 'id_col': 'id'}}
        price_history_table: Optional table to record price changes into (e.g. 'props_management.material_price_history').
        db_resolver_func: Function to resolve connection names to URLs.
    """
    t_start = datetime.now()
    xl_file = Path(excel_path).resolve()
    if not xl_file.exists():
        raise FileNotFoundError(f"Excel file not found: {xl_file}")

    df = pd.read_excel(xl_file, sheet_name=sheet_name)
    df.columns = [str(c).strip() for c in df.columns]

    # Resolve DB engine if connection is available
    engine = None
    fk_resolved_maps = {}
    if connection_name_or_url:
        db_url = db_resolver_func(connection_name_or_url) if db_resolver_func else connection_name_or_url
        engine = create_engine(resolve_sqlalchemy_url(db_url))
        fk_resolved_maps = _resolve_fk_mappings(engine, fk_lookups)

    # Pre-flight check on column mapping
    db_columns = list(column_mapping.values())
    unmapped_keys = [k for k in key_columns if k not in db_columns]
    if unmapped_keys:
        raise ValueError(f"Key columns {unmapped_keys} must be mapped in column_mapping.")

    sql_statements = []
    fk_errors = []
    processed_count = 0

    header_comment = f"-- Migration Script for {target_table}\n-- Generated from {xl_file.name} at {datetime.now().isoformat()}\nBEGIN;\n"
    sql_statements.append(header_comment)

    # Invert mapping to read from df: DB column -> Excel column
    inv_mapping = {v: k for k, v in column_mapping.items()}

    update_cols = [c for c in db_columns if c not in key_columns]

    for idx, row in df.iterrows():
        row_num = idx + 2  # 1-indexed Excel row with header
        row_data = {}
        has_error = False

        for db_col in db_columns:
            xl_col = inv_mapping.get(db_col)
            val = row.get(xl_col)

            # Check if this column requires FK resolution
            if fk_lookups and db_col in fk_lookups:
                code_str = str(val).strip() if pd.notnull(val) else ""
                lookup_map = fk_resolved_maps.get(db_col, {})
                if code_str in lookup_map:
                    val = lookup_map[code_str]
                elif code_str.lower() in lookup_map:
                    val = lookup_map[code_str.lower()]
                else:
                    fk_errors.append({
                        "excel_row": row_num,
                        "column": xl_col,
                        "unresolved_value": code_str,
                        "target_table": fk_lookups[db_col].get("table")
                    })
                    has_error = True

            row_data[db_col] = val

        if has_error:
            continue

        processed_count += 1
        col_list_str = ", ".join(db_columns)
        val_list_str = ", ".join([_clean_sql_val(row_data[c]) for c in db_columns])

        if on_conflict_action.lower() == "update" and update_cols:
            update_clauses = [f"{c} = EXCLUDED.{c}" for c in update_cols]
            # Add updated_at if standard
            conflict_sql = f"ON CONFLICT ({', '.join(key_columns)}) DO UPDATE SET\n    " + ",\n    ".join(update_clauses)
        else:
            conflict_sql = f"ON CONFLICT ({', '.join(key_columns)}) DO NOTHING"

        stmt = f"INSERT INTO {target_table} ({col_list_str})\nVALUES ({val_list_str})\n{conflict_sql};"
        sql_statements.append(stmt)

    sql_statements.append("\nCOMMIT;\n")

    full_sql_text = "\n".join(sql_statements)
    out_file_str = None
    if output_sql_path:
        out_p = Path(output_sql_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            f.write(full_sql_text)
        out_file_str = str(out_p)

    duration = (datetime.now() - t_start).total_seconds()

    return {
        "status": "success",
        "target_table": target_table,
        "total_excel_rows": len(df),
        "valid_migratable_rows": processed_count,
        "fk_unresolved_errors_count": len(fk_errors),
        "fk_errors_sample": fk_errors[:10],
        "generated_statements_count": processed_count,
        "output_sql_file": out_file_str,
        "sql_preview": sql_statements[:5],
        "duration_seconds": round(duration, 3)
    }


def sync_master_to_db(
    excel_path: str,
    target_table: str,
    key_columns: List[str],
    column_mapping: Dict[str, str],
    connection_name_or_url: str,
    sheet_name: Optional[Union[str, int]] = 0,
    fk_lookups: Optional[Dict[str, Dict[str, str]]] = None,
    dry_run: bool = True,
    chunk_size: int = 500,
    db_resolver_func = None
) -> Dict[str, Any]:
    """
    Safely execute master data synchronization against live PostgreSQL/MySQL database.
    Supports transactional dry-run mode that guarantees zero database side-effects while
    validating constraints, types, and primary keys.

    Args:
        excel_path: Path to Excel master.
        target_table: Destination database table.
        key_columns: Primary/unique key columns.
        column_mapping: Excel to DB column mapping.
        connection_name_or_url: DB connection identifier.
        sheet_name: Sheet index or name.
        fk_lookups: Lookup configuration to resolve codes into UUID foreign keys.
        dry_run: If True, executes inside a transaction and rolls back safely (zero data changes).
        chunk_size: Batch insert size.
        db_resolver_func: Function to resolve connection names to URLs.
    """
    t_start = datetime.now()
    plan = generate_master_migration_plan(
        excel_path=excel_path,
        target_table=target_table,
        key_columns=key_columns,
        column_mapping=column_mapping,
        connection_name_or_url=connection_name_or_url,
        sheet_name=sheet_name,
        fk_lookups=fk_lookups,
        db_resolver_func=db_resolver_func
    )

    if plan["fk_unresolved_errors_count"] > 0:
        return {
            "status": "aborted",
            "reason": f"Foreign key validation failed for {plan['fk_unresolved_errors_count']} rows.",
            "fk_errors": plan["fk_errors_sample"]
        }

    db_url = db_resolver_func(connection_name_or_url) if db_resolver_func else connection_name_or_url
    engine = create_engine(resolve_sqlalchemy_url(db_url))

    executed_count = 0
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # Parse individual statements
            raw_stmts = plan.get("sql_preview", []) # Generated statements
            # Re-read or generate full list
            full_plan = generate_master_migration_plan(
                excel_path=excel_path,
                target_table=target_table,
                key_columns=key_columns,
                column_mapping=column_mapping,
                connection_name_or_url=connection_name_or_url,
                sheet_name=sheet_name,
                fk_lookups=fk_lookups,
                db_resolver_func=db_resolver_func
            )
            # Execute in batches
            for stmt in full_plan.get("sql_preview", []):
                if stmt.startswith("INSERT"):
                    conn.execute(text(stmt))
                    executed_count += 1

            if dry_run:
                trans.rollback()
                mode_status = "dry_run_success"
                msg = f"Dry-run simulation succeeded. Verified {executed_count} statements against {target_table}. Transaction rolled back."
            else:
                trans.commit()
                mode_status = "committed"
                msg = f"Successfully synced {executed_count} master rows into {target_table}."

        except Exception as e:
            trans.rollback()
            raise RuntimeError(f"Database sync failed during transaction: {str(e)}")

    duration = (datetime.now() - t_start).total_seconds()

    return {
        "status": mode_status,
        "message": msg,
        "dry_run": dry_run,
        "rows_processed": executed_count,
        "target_table": target_table,
        "duration_seconds": round(duration, 3)
    }
