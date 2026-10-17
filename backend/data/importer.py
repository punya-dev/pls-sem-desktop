"""
Data Importer Module (DAT-01, DAT-02, DAT-08).
Provides robust tabular data ingestion for CSV, TSV, TXT, and Excel (.xlsx, .xls):
- Flexible ImportSettings (delimiters, European decimals, encodings, missing codes)
- Raw file preview (first N lines with auto-detection guesses)
- Safe parsing with non-numeric cell tracking and automatic role assignment
- Header de-duplication, whitespace trimming, BOM stripping
"""

import io
import csv
import re
from typing import List, Dict, Any, Optional, Tuple, Union
import pandas as pd
import numpy as np
from pydantic import BaseModel, Field, ConfigDict


class ImportSettings(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    delimiter: Optional[str] = "auto"  # "auto", ",", ";", "\t", " ", or custom
    quote_char: str = '"'
    decimal: str = "."  # "." or ","
    thousands: Optional[str] = None  # None, ",", ".", " "
    encoding: str = "utf-8"  # "utf-8", "utf-8-sig", "latin-1", "cp1252"
    header: bool = True
    skip_rows: int = 0
    missing_codes: List[str] = Field(
        default_factory=lambda: ["-99", "NA", "N/A", "null", "NULL", "NaN", "nan", "."]
    )
    treat_dot_as_missing: bool = True
    sheet: Optional[Union[str, int]] = 0


def detect_file_encoding(raw_bytes: bytes) -> str:
    """Heuristic encoding detection: utf-8, utf-8-sig, cp1252, latin-1."""
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        raw_bytes.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        raw_bytes.decode("cp1252")
        return "cp1252"
    except UnicodeDecodeError:
        return "latin-1"


def detect_delimiter(sample_text: str) -> str:
    """Sniffs standard tabular delimiters: comma, semicolon, tab, pipe, space."""
    # Count occurrences in first few lines
    lines = [line for line in sample_text.splitlines() if line.strip()][:10]
    if not lines:
        return ","

    candidates = [";", ",", "\t", "|"]
    counts = {c: 0 for c in candidates}
    for line in lines:
        for c in candidates:
            counts[c] += line.count(c)

    best_char = max(counts, key=counts.get)
    if counts[best_char] > 0:
        return best_char

    # Fallback to csv.Sniffer
    try:
        dialect = csv.Sniffer().sniff(sample_text[:4096], delimiters=";,\t| ")
        return dialect.delimiter
    except Exception:
        return ","


def raw_file_preview(file_bytes: bytes, n_lines: int = 50, encoding: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns the first n_lines of raw unparsed text along with detected delimiter and encoding.
    (DAT-08: Raw file preview without parsing).
    """
    detected_encoding = encoding or detect_file_encoding(file_bytes)
    try:
        text = file_bytes.decode(detected_encoding, errors="replace")
    except Exception:
        detected_encoding = "latin-1"
        text = file_bytes.decode("latin-1", errors="replace")

    lines = text.splitlines()
    preview_lines = lines[:n_lines]
    sample_block = "\n".join(preview_lines[:20])
    detected_delim = detect_delimiter(sample_block)

    return {
        "raw_lines": preview_lines,
        "total_lines_approx": len(lines),
        "detected_delimiter": detected_delim,
        "detected_encoding": detected_encoding,
    }


def clean_column_names(columns: List[str]) -> List[str]:
    """Strips whitespace, replaces empty names, and de-duplicates column names."""
    cleaned = []
    seen: Dict[str, int] = {}
    for i, col in enumerate(columns):
        c = str(col).strip()
        if not c or c.lower() == "unnamed":
            c = f"Col_{i + 1}"
        # Normalize internal whitespace
        c = re.sub(r"\s+", "_", c)
        if c in seen:
            seen[c] += 1
            c = f"{c}_{seen[c]}"
        else:
            seen[c] = 1
        cleaned.append(c)
    return cleaned


def parse_dataframe(file_bytes: bytes, filename: str, settings: Optional[ImportSettings] = None) -> Tuple[pd.DataFrame, Dict[str, Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Parses file bytes into a clean DataFrame based on ImportSettings.
    Returns:
    (df, column_metadata, issues, settings_used)
    """
    s = settings or ImportSettings()
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    issues: List[Dict[str, Any]] = []

    # 1. Parse into initial DataFrame
    if ext in ["xlsx", "xls"]:
        sheet_name = s.sheet if s.sheet is not None else 0
        df_raw = pd.read_excel(
            io.BytesIO(file_bytes),
            sheet_name=sheet_name,
            header=0 if s.header else None,
            skiprows=s.skip_rows if s.skip_rows > 0 else None,
        )
        settings_used = {
            "format": "excel",
            "sheet": sheet_name,
            "skip_rows": s.skip_rows,
            "header": s.header,
        }
    else:
        encoding = s.encoding
        if not encoding or encoding == "auto":
            encoding = detect_file_encoding(file_bytes)

        try:
            sample_str = file_bytes[:8192].decode(encoding, errors="replace")
        except Exception:
            encoding = "latin-1"
            sample_str = file_bytes[:8192].decode(encoding, errors="replace")

        delimiter = s.delimiter
        if not delimiter or delimiter == "auto":
            delimiter = detect_delimiter(sample_str)

        # Python engine handles multi-character or flexible delimiters
        df_raw = pd.read_csv(
            io.BytesIO(file_bytes),
            delimiter=delimiter,
            encoding=encoding,
            header=0 if s.header else None,
            skiprows=s.skip_rows if s.skip_rows > 0 else None,
            quotechar=s.quote_char or '"',
            dtype=str,  # read as string first to safely track non-numeric entries and missing codes
            na_filter=False,  # we handle missing codes explicitly below
        )
        settings_used = {
            "format": "csv",
            "delimiter": delimiter,
            "encoding": encoding,
            "quote_char": s.quote_char,
            "decimal": s.decimal,
            "thousands": s.thousands,
            "skip_rows": s.skip_rows,
            "header": s.header,
        }

    # 2. Clean and de-duplicate column names
    raw_cols = [str(c) for c in df_raw.columns]
    cleaned_cols = clean_column_names(raw_cols)
    df_raw.columns = cleaned_cols

    # 3. Process missing values and data types per column
    missing_set = set(str(c).strip() for c in s.missing_codes)
    if s.treat_dot_as_missing:
        missing_set.add(".")
    missing_set.add("")

    column_metadata: Dict[str, Dict[str, Any]] = {}
    parsed_columns: Dict[str, pd.Series] = {}

    for col in df_raw.columns:
        series_str = df_raw[col].astype(str).str.strip()

        # Check for missing values
        is_missing = series_str.isin(missing_set)

        # Value cleaning for decimals and thousands
        clean_vals = series_str.copy()
        clean_vals[is_missing] = None

        if s.thousands:
            clean_vals = clean_vals.str.replace(s.thousands, "", regex=False)
        if s.decimal and s.decimal != ".":
            clean_vals = clean_vals.str.replace(s.decimal, ".", regex=False)

        # Attempt numeric conversion
        converted_num = pd.to_numeric(clean_vals, errors="coerce")
        non_null_original = clean_vals.dropna()
        non_null_converted = converted_num.dropna()

        num_valid_conversions = len(non_null_converted)
        num_expected_non_null = len(non_null_original)

        if num_expected_non_null == 0:
            # Entirely empty or missing column
            parsed_columns[col] = pd.Series(np.nan, index=df_raw.index, dtype=float)
            column_metadata[col] = {
                "role": "ignore",
                "scale_min": None,
                "scale_max": None,
                "reverse_coded": False,
                "label": col,
            }
        elif num_valid_conversions == num_expected_non_null:
            # 100% clean numeric column -> default indicator
            parsed_columns[col] = converted_num
            scale_min = float(converted_num.min()) if num_valid_conversions > 0 else None
            scale_max = float(converted_num.max()) if num_valid_conversions > 0 else None
            column_metadata[col] = {
                "role": "indicator",
                "scale_min": scale_min,
                "scale_max": scale_max,
                "reverse_coded": False,
                "label": col,
            }
        elif num_valid_conversions / num_expected_non_null >= 0.80:
            # Mostly numeric (>= 80%), with some dirty non-numeric cells
            # Find dirty rows for diagnostics
            dirty_mask = non_null_original.index.difference(non_null_converted.index)
            dirty_samples = [
                {"row": int(idx) + 1, "value": str(df_raw.loc[idx, col])}
                for idx in dirty_mask[:10]
            ]
            issues.append({
                "code": "NON_NUMERIC_CELLS_CONVERTED_TO_MISSING",
                "severity": "warning",
                "target": {"type": "column", "id": col},
                "message": f"Column '{col}' contained {len(dirty_mask)} non-numeric cell(s) converted to missing (NaN).",
                "advice": "Verify source data for typographical errors or unintended text characters.",
                "details": {
                    "count": len(dirty_mask),
                    "samples": dirty_samples,
                },
            })
            parsed_columns[col] = converted_num
            scale_min = float(converted_num.min()) if len(non_null_converted) > 0 else None
            scale_max = float(converted_num.max()) if len(non_null_converted) > 0 else None
            column_metadata[col] = {
                "role": "indicator",
                "scale_min": scale_min,
                "scale_max": scale_max,
                "reverse_coded": False,
                "label": col,
            }
        else:
            # Mostly non-numeric string column (e.g. IDs, categories, names) -> assign 'id' or 'group'
            parsed_columns[col] = series_str
            role = "id" if col.lower() in ["id", "case_id", "respondent_id", "row_id"] else "group"
            column_metadata[col] = {
                "role": role,
                "scale_min": None,
                "scale_max": None,
                "reverse_coded": False,
                "label": col,
            }

    df_clean = pd.DataFrame(parsed_columns, index=df_raw.index)
    return df_clean, column_metadata, issues, settings_used


def preview_import_data(file_bytes: bytes, filename: str, settings: Optional[ImportSettings] = None, n_preview: int = 50) -> Dict[str, Any]:
    """
    Preview import with given settings: returns head rows, dtypes, issues, settings used.
    (DAT-02 & DAT-08).
    """
    df, col_meta, issues, settings_used = parse_dataframe(file_bytes, filename, settings)
    head_df = df.head(n_preview)

    columns_info = []
    for c in df.columns:
        s = df[c]
        dtype = "numeric" if pd.api.types.is_numeric_dtype(s) else "text"
        n_missing = int(s.isna().sum())
        columns_info.append({
            "name": c,
            "dtype": dtype,
            "role": col_meta.get(c, {}).get("role", "indicator"),
            "n_missing": n_missing,
            "pct_missing": round(n_missing / len(df) * 100, 2) if len(df) > 0 else 0.0,
            "scale_min": col_meta.get(c, {}).get("scale_min"),
            "scale_max": col_meta.get(c, {}).get("scale_max"),
        })

    # Convert records with None for NaN for clean JSON serialization
    preview_rows = head_df.astype(object).where(pd.notnull(head_df), None).to_dict(orient="records")

    return {
        "filename": filename,
        "n_rows": len(df),
        "n_cols": len(df.columns),
        "columns": columns_info,
        "preview_rows": preview_rows,
        "issues": issues,
        "settings_used": settings_used,
    }
