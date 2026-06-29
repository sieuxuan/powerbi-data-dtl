"""Đọc file Excel/CSV local và chuẩn hóa dữ liệu đầu vào."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import FileOptions

if TYPE_CHECKING:
    import pandas as pd


SUPPORTED_EXTENSIONS = {".xlsx", ".xlsm", ".xls", ".xlsb", ".csv", ".tsv"}


class FileReaderError(RuntimeError):
    """Raised when a local tabular file cannot be read."""


@dataclass(frozen=True)
class FileReadResult:
    dataframe: "pd.DataFrame"
    file_path: Path
    file_hash: str
    row_count: int
    columns: list[str]


def read_tabular_file(path: str | Path, options: FileOptions, nrows: int | None = None) -> FileReadResult:
    """Read an Excel/CSV file into a cleaned pandas DataFrame."""
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        raise FileReaderError(f"File not found: {file_path}")
    if not file_path.is_file():
        raise FileReaderError(f"Path is not a file: {file_path}")

    extension = file_path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise FileReaderError(f"Unsupported file extension: {extension}")

    try:
        import pandas as pd
    except ImportError as exc:
        raise FileReaderError("pandas is required. Install dependencies with: pip install -r requirements.txt") from exc

    if extension in {".csv", ".tsv"}:
        dataframe = _read_csv(pd, file_path, options, extension, nrows)
    else:
        dataframe = _read_excel(pd, file_path, options, extension, nrows)

    dataframe = _apply_column_renames(
        _drop_skipped_columns(_clean_dataframe(dataframe), options.skip_columns),
        options.column_renames,
    )
    return FileReadResult(
        dataframe=dataframe,
        file_path=file_path,
        file_hash=calculate_md5(file_path),
        row_count=len(dataframe),
        columns=[str(column) for column in dataframe.columns],
    )


def calculate_md5(path: Path) -> str:
    """Calculate an MD5 hash for a file."""
    digest = hashlib.md5()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(pd: Any, path: Path, options: FileOptions, extension: str, nrows: int | None = None) -> "pd.DataFrame":
    """Read a CSV or TSV file."""
    delimiter = options.delimiter
    if extension == ".tsv" and (delimiter is None or delimiter == ","):
        delimiter = "\t"

    return pd.read_csv(
        path,
        encoding=options.encoding or "utf-8",
        sep=delimiter or ",",
        header=options.header_row,
        skiprows=options.skip_rows or None,
        usecols=options.usecols,
        nrows=nrows,
    )


def _read_excel(pd: Any, path: Path, options: FileOptions, extension: str, nrows: int | None = None) -> "pd.DataFrame":
    """Read an Excel workbook with fast engine fallback."""
    common_kwargs = {
        "sheet_name": options.sheet,
        "header": options.header_row,
        "skiprows": options.skip_rows or None,
        "usecols": options.usecols,
        "nrows": nrows,
    }

    engines: list[str | None]
    if extension == ".xls":
        engines = ["calamine", "xlrd", None]
    elif extension in {".xlsx", ".xlsm", ".xlsb"}:
        engines = ["calamine", "openpyxl", None]
    else:
        engines = ["calamine", None]

    last_error: Exception | None = None
    for engine in engines:
        try:
            kwargs = dict(common_kwargs)
            if engine is not None:
                kwargs["engine"] = engine
            return pd.read_excel(path, **kwargs)
        except Exception as exc:  # pandas raises engine-specific exceptions.
            last_error = exc

    raise FileReaderError(f"Could not read Excel file {path}: {last_error}") from last_error


def _clean_dataframe(dataframe: "pd.DataFrame") -> "pd.DataFrame":
    """Normalize headers and remove fully empty rows."""
    cleaned = _drop_empty_edge_columns(dataframe.copy())
    cleaned.columns = _dedupe_columns([_clean_header(column, index) for index, column in enumerate(cleaned.columns)])
    cleaned = cleaned.dropna(how="all")
    return cleaned


def _apply_column_renames(dataframe: "pd.DataFrame", column_renames: dict[str, str]) -> "pd.DataFrame":
    """Apply user-provided column names after header cleanup."""
    if not column_renames:
        return dataframe
    rename_map = {str(source).strip(): str(target).strip() for source, target in column_renames.items() if str(source).strip() and str(target).strip()}
    renamed = dataframe.rename(columns={column: rename_map[column] for column in dataframe.columns if column in rename_map})
    renamed.columns = _dedupe_columns([str(column).strip() or f"column_{index + 1}" for index, column in enumerate(renamed.columns)])
    return renamed


def _drop_skipped_columns(dataframe: "pd.DataFrame", skip_columns: list[str]) -> "pd.DataFrame":
    """Drop columns selected out during mapping after header cleanup."""
    skipped = {str(column).strip() for column in skip_columns if str(column).strip()}
    if not skipped:
        return dataframe
    return dataframe.drop(columns=[column for column in dataframe.columns if str(column).strip() in skipped])


def _drop_empty_edge_columns(dataframe: "pd.DataFrame") -> "pd.DataFrame":
    """Remove fully empty columns at the beginning and end of a DataFrame."""
    if dataframe.empty and not list(dataframe.columns):
        return dataframe
    first = 0
    last = len(dataframe.columns) - 1
    while first <= last and _is_empty_edge_column(dataframe, first):
        first += 1
    while last >= first and _is_empty_edge_column(dataframe, last):
        last -= 1
    if first > last:
        return dataframe.iloc[:, 0:0]
    return dataframe.iloc[:, first : last + 1]


def _is_empty_edge_column(dataframe: "pd.DataFrame", index: int) -> bool:
    """Return whether a column has no header and no data values."""
    column_name = dataframe.columns[index]
    header = str(column_name).strip()
    unnamed_header = not header or header.lower().startswith("unnamed:") or header.lower() == "nan"
    return unnamed_header and bool(dataframe.iloc[:, index].isna().all())


def _clean_header(column: object, index: int) -> str:
    """Convert a raw column header to a readable string."""
    value = str(column).strip()
    if not value or value.lower().startswith("unnamed:"):
        return f"column_{index + 1}"
    return value


def _dedupe_columns(columns: list[str]) -> list[str]:
    """Ensure column names are unique."""
    seen: dict[str, int] = {}
    result: list[str] = []
    for column in columns:
        count = seen.get(column, 0) + 1
        seen[column] = count
        result.append(column if count == 1 else f"{column}_{count}")
    return result
