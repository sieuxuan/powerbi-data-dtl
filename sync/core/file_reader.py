"""Đọc file Excel/CSV local và chuẩn hóa dữ liệu đầu vào."""

from __future__ import annotations

import hashlib
from itertools import islice
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import FileOptions

if TYPE_CHECKING:
    import pandas as pd


SUPPORTED_EXTENSIONS = {".xlsx", ".xlsm", ".xls", ".xlsb", ".csv", ".tsv"}
HTML_PREFIXES = (b"<!doctype html", b"<html")


class FileReaderError(RuntimeError):
    """Raised when a local tabular file cannot be read."""


@dataclass(frozen=True)
class FileReadResult:
    dataframe: "pd.DataFrame"
    file_path: Path
    file_hash: str
    row_count: int
    columns: list[str]


def read_tabular_file(
    path: str | Path,
    options: FileOptions,
    nrows: int | None = None,
    file_hash: str | None = None,
    fast_sample: bool = False,
) -> FileReadResult:
    """Read an Excel/CSV file into a cleaned pandas DataFrame."""
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        raise FileReaderError(f"File not found: {file_path}")
    if not file_path.is_file():
        raise FileReaderError(f"Path is not a file: {file_path}")

    extension = file_path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise FileReaderError(f"Unsupported file extension: {extension}")
    _reject_html_file(file_path)

    try:
        import pandas as pd
    except ImportError as exc:
        raise FileReaderError("pandas is required. Install dependencies with: pip install -r requirements.txt") from exc

    if extension in {".csv", ".tsv"}:
        dataframe = _read_csv(pd, file_path, options, extension, nrows)
    else:
        dataframe = _read_excel(pd, file_path, options, extension, nrows, fast_sample=fast_sample)

    dataframe = _apply_column_renames(
        _drop_skipped_columns(_clean_dataframe(dataframe), options.skip_columns),
        options.column_renames,
    )
    return FileReadResult(
        dataframe=dataframe,
        file_path=file_path,
        file_hash=file_hash or calculate_md5(file_path),
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


def _reject_html_file(path: Path) -> None:
    """Reject saved login/error pages before pandas tries to parse them as data files."""
    with path.open("rb") as file_handle:
        sample = file_handle.read(1024).lstrip().lower()
    if any(sample.startswith(prefix) for prefix in HTML_PREFIXES) or b"<html" in sample[:256]:
        raise FileReaderError(
            f"File is not a real Excel/CSV file: {path}. "
            "It looks like an HTML login/error page. For SharePoint/OneDrive, create a downloadable sharing link "
            "or use the local synced OneDrive file path."
        )


def _read_excel(
    pd: Any,
    path: Path,
    options: FileOptions,
    extension: str,
    nrows: int | None = None,
    *,
    fast_sample: bool = False,
) -> "pd.DataFrame":
    """Read an Excel workbook with fast engine fallback."""
    if fast_sample and nrows is not None and _can_use_fast_excel_sample(options):
        try:
            return _read_excel_sample_with_calamine(pd, path, options, nrows)
        except Exception:
            pass

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


def _can_use_fast_excel_sample(options: FileOptions) -> bool:
    """Return whether direct calamine sample reading can preserve expected options."""
    return not options.usecols and not options.skip_rows


def _read_excel_sample_with_calamine(pd: Any, path: Path, options: FileOptions, nrows: int) -> "pd.DataFrame":
    """Read a small Excel sample directly through python-calamine."""
    from python_calamine import load_workbook

    workbook = load_workbook(str(path))
    sheet_value = options.sheet
    sheet = workbook.get_sheet_by_index(sheet_value) if isinstance(sheet_value, int) else workbook.get_sheet_by_name(str(sheet_value))
    header_row = max(0, int(options.header_row or 0))
    rows = list(islice(sheet.iter_rows(), header_row + 1 + max(0, int(nrows))))
    if len(rows) <= header_row:
        return pd.DataFrame()
    header = list(rows[header_row])
    width = len(header)
    data = [_fit_row_width(list(row), width) for row in rows[header_row + 1 :]]
    return pd.DataFrame(data, columns=header)


def _fit_row_width(row: list[Any], width: int) -> list[Any]:
    """Pad or trim a row to match the header width."""
    if len(row) >= width:
        return row[:width]
    return [*row, *([None] * (width - len(row)))]


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
