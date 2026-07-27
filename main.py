import os
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# --- Configuration & Setup ---
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

CREDENTIALS_FILE = Path(os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"))
SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Shopify_Orders_Sync")
API_URL = os.getenv("API_URL", "https://fakestoreapi.com/products")
API_TIMEOUT = int(os.getenv("API_TIMEOUT", 15))

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
HEADERS = (
    "ID",
    "Title",
    "Category",
    "Price",
    "Last Synced"
)

# Constants for validation
DEFAULT_TITLE = "Unknown"
DEFAULT_CATEGORY = "Unknown"
DEFAULT_PRICE = 0.0
HEADER_ID_COLUMN = "ID"


@dataclass(slots=True)
class SheetRow:
    """Represents a normalized row in the Google Sheet."""
    row_number: int
    id: str
    title: str
    category: str
    price: float
    timestamp: str


@dataclass(slots=True)
class ApiRecord:
    """Normalized record from the external API, ready for sync."""
    id: str
    title: str
    category: str
    price: float
    sync_time: str


def get_requests_session() -> requests.Session:
    """Create a robust requests session with retry configuration."""
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def authenticate_google_sheets() -> Optional[gspread.Worksheet]:
    """Securely connect to Google account and access the spreadsheet."""
    if not CREDENTIALS_FILE.exists():
        logger.error(f"Credentials file not found at: {CREDENTIALS_FILE}")
        return None

    try:
        creds = Credentials.from_service_account_file(
            str(CREDENTIALS_FILE),
            scopes=SCOPE
        )
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).sheet1
        logger.info("Successfully connected to Google Sheets.")
        return sheet
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(f"Spreadsheet '{SHEET_NAME}' not found.")
        return None
    except Exception:
        logger.exception("Unexpected error connecting to Google Sheets.")
        return None


def ensure_header(sheet: gspread.Worksheet) -> None:
    """
    Check if the header row exists and matches standard headers.
    If missing or altered, force update row 1 directly without shifting down.
    """
    try:
        first_row = sheet.row_values(1)
        padded = first_row + [''] * (len(HEADERS) - len(first_row))
        
        if padded[:len(HEADERS)] != list(HEADERS):
            logger.info("Header missing or altered. Forcing standard headers in Row 1.")
            cells = [gspread.Cell(row=1, col=i+1, value=h) for i, h in enumerate(HEADERS)]
            sheet.update_cells(cells, value_input_option="USER_ENTERED")
    except Exception:
        logger.exception("Failed to ensure header row.")
        raise


def get_existing_data(sheet: gspread.Worksheet) -> Tuple[Dict[str, SheetRow], int, List[int]]:
    """
    Read all rows, parse valid data starting from row 2, detect stray/orphaned rows 
    (rows with data in columns B-E but missing an ID in column A), and determine 
    the exact next available row for new insertions.
    """
    all_values = sheet.get_all_values()
    existing = {}
    stray_rows = []
    
    for idx, row in enumerate(all_values, start=1):
        if idx > 1:
            padded = row + [''] * (len(HEADERS) - len(row))
            has_id = bool(padded[0].strip())
            has_other_data = any(str(cell).strip() for cell in padded[1:])
            
            if has_id:
                row_id = padded[0].strip()
                try:
                    price_val = float(padded[3]) if padded[3] else DEFAULT_PRICE
                except (ValueError, TypeError):
                    price_val = DEFAULT_PRICE

                existing[row_id] = SheetRow(
                    row_number=idx,
                    id=row_id,
                    title=padded[1].strip(),
                    category=padded[2].strip(),
                    price=price_val,
                    timestamp=padded[4].strip()
                )
            elif has_other_data:
                # Track orphaned/stray rows that have data without a valid ID
                stray_rows.append(idx)
            
    # Calculate next insert row strictly from valid existing rows or default to 2
    if existing:
        next_insert_row = max(row.row_number for row in existing.values()) + 1
    else:
        next_insert_row = 2
        
    return existing, next_insert_row, stray_rows


def normalize_api_item(item: Dict[str, any], sync_time: str) -> Optional[ApiRecord]:
    """
    Validate and transform an API record into an ApiRecord.
    Fields are stripped and defaults are applied for missing or invalid data.
    """
    raw_id = item.get('id')
    if raw_id is None:
        logger.warning(f"Skipped record with missing ID: {item}")
        return None

    item_id = str(raw_id).strip()
    if not item_id:
        logger.warning("Skipped record with empty ID after conversion.")
        return None

    title = item.get('title')
    if not title:
        logger.warning(f"Missing 'title' for ID {item_id}. Setting to '{DEFAULT_TITLE}'.")
        title = DEFAULT_TITLE
    title = str(title).strip()

    category = item.get('category', DEFAULT_CATEGORY)
    category = str(category).strip()

    try:
        price = float(item.get('price', DEFAULT_PRICE))
    except (ValueError, TypeError):
        logger.warning(f"Invalid price format for ID {item_id}. Setting to {DEFAULT_PRICE}")
        price = DEFAULT_PRICE

    return ApiRecord(
        id=item_id,
        title=title,
        category=category,
        price=price,
        sync_time=sync_time
    )


def fetch_data(session: requests.Session, sync_time: str) -> List[ApiRecord]:
    """Fetch data from API endpoint, normalize and return as ApiRecord list."""
    try:
        response = session.get(API_URL, timeout=API_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list):
            logger.error(f"Unexpected API response format. Expected list, got {type(data).__name__}.")
            return []

        records = []
        for item in data:
            record = normalize_api_item(item, sync_time)
            if record:
                records.append(record)
        logger.info(f"Fetched {len(records)} valid records from API.")
        
        return records
    except requests.exceptions.Timeout:
        logger.error(f"API request timed out after {API_TIMEOUT} seconds.")
    except requests.exceptions.RequestException:
        logger.exception("Failed to fetch data from API due to network/HTTP error.")
    except ValueError:
        logger.exception("Failed to parse JSON response from API.")
    return []


def rows_equal(old: SheetRow, new: ApiRecord) -> bool:
    """
    Compare existing sheet row with incoming API record.
    Returns False if data differs OR if the timestamp (Last Synced) is missing.
    """
    return (
        old.id == new.id and
        old.title == new.title and
        old.category == new.category and
        old.price == new.price and
        bool(old.timestamp.strip())
    )


def classify_changes(api_records: List[ApiRecord], existing_map: Dict[str, SheetRow], next_insert_row: int):
    """
    Compare API records with sheet data and classify into inserts/updates/skipped.
    Calculates exact target row numbers for new inserts starting from next_insert_row.
    """
    to_insert = []
    updates = []
    skipped = 0
    invalid = 0

    current_insert_row = next_insert_row

    for record in api_records:
        new_row = [record.id, record.title, record.category, record.price, record.sync_time]
        if record.id in existing_map:
            old_row = existing_map[record.id]
            if rows_equal(old_row, record):
                skipped += 1
            else:
                updates.append((old_row.row_number, new_row))
        else:
            to_insert.append((current_insert_row, new_row))
            current_insert_row += 1

    return to_insert, updates, skipped, invalid


def apply_changes(sheet: gspread.Worksheet, to_insert: list, updates: list, stray_rows: list) -> None:
    """Batch write new records, update existing records, and clear stray/orphaned rows."""
    cells_to_update = []

    # Clear any stray rows (rows with data in columns B-E but missing an ID in column A)
    for row_num in stray_rows:
        for col_idx in range(1, len(HEADERS) + 1):
            cells_to_update.append(
                gspread.Cell(row=row_num, col=col_idx, value="")
            )
        logger.info(f"Clearing orphaned stray data at row {row_num}.")

    for row_num, row_vals in to_insert:
        for col_idx, value in enumerate(row_vals, start=1):
            cells_to_update.append(
                gspread.Cell(row=row_num, col=col_idx, value=value)
            )

    for row_num, row_vals in updates:
        for col_idx, value in enumerate(row_vals, start=1):
            cells_to_update.append(
                gspread.Cell(row=row_num, col=col_idx, value=value)
            )

    if cells_to_update:
        sheet.update_cells(cells_to_update, value_input_option="USER_ENTERED")

    if stray_rows:
        logger.info(f"Cleared {len(stray_rows)} stray/orphaned rows.")
    if to_insert:
        logger.info(f"Inserted {len(to_insert)} new records.")
    if updates:
        logger.info(f"Updated {len(updates)} records/timestamps.")


def format_sheet(sheet: gspread.Worksheet) -> None:
    """
    Apply visual formatting to the Google Sheet for better readability.
    Centers all text, ensures data rows are NOT bold, and styles the header row.
    """
    try:
        # Format Header (Row 1): Light gray background, bold text, centered
        sheet.format("A1:E1", {
            "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
            "textFormat": {"bold": True, "fontSize": 11}
        })

        # Format Data Rows (Row 2 to 1000): Center alignment, explicit bold=False to clear stuck formatting
        sheet.format("A2:E1000", {
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
            "textFormat": {"bold": False}
        })
        
        logger.info("Visual formatting applied to the sheet successfully.")
    except Exception:
        logger.exception("Failed to apply formatting to the sheet.")


def sync_data_to_sheet(sheet: gspread.Worksheet, api_data: List[ApiRecord]) -> None:
    """Main sync logic: ensure header, classify changes, apply updates, and format UI."""
    if not sheet or not api_data:
        logger.warning("Sheet or data is missing. Sync aborted.")
        return

    try:
        ensure_header(sheet)
        existing_map, next_insert_row, stray_rows = get_existing_data(sheet)
        to_insert, updates, skipped, invalid = classify_changes(api_data, existing_map, next_insert_row)
        
        apply_changes(sheet, to_insert, updates, stray_rows)
        format_sheet(sheet)

        logger.info(
            f"Sync summary: Inserted={len(to_insert)}, Updated={len(updates)}, "
            f"Skipped={skipped}, Invalid={invalid}"
        )

    except gspread.exceptions.APIError:
        logger.exception("Google Sheets API Error during sync.")
    except Exception:
        logger.exception("Unexpected error during data synchronization.")


def main() -> None:
    logger.info("=== Starting Sync Process ===")

    sheet = authenticate_google_sheets()
    if not sheet:
        logger.error("Aborting process due to authentication failure.")
        return

    sync_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    with get_requests_session() as session:
        api_records = fetch_data(session, sync_time)

    if api_records:
        sync_data_to_sheet(sheet, api_records)
    else:
        logger.warning("No valid data received from API. Sheet remains unchanged.")

    logger.info("=== Process Finished ===")


if __name__ == "__main__":
    main()