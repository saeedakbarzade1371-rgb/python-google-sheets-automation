# Python Google Sheets Automation

<p align="center">

![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Status](https://img.shields.io/badge/Status-Active-success)
![Platform](https://img.shields.io/badge/Platform-Cross--Platform-lightgrey)

</p>

A Python application that synchronizes data from a REST API to Google Sheets while handling duplicate detection, record updates, input validation, and reliable HTTP communication.

---

## Screenshot

<p align="center">
<img src="assets/screenshot.png" width="900" alt="Application Screenshot">
</p>

---

## Demo

<p align="center">
<img src="assets/demo.gif" width="900" alt="Application Demo">
</p>

---

## Project Overview

This project demonstrates the implementation of a small but production-oriented automation workflow.

The application retrieves data from a REST API, validates the response, compares incoming records with existing spreadsheet data, and synchronizes only the required changes.

The implementation focuses on readability, maintainability, and reliability rather than framework complexity.

---

## Architecture

<p align="center">
<img src="assets/architecture.png" width="850" alt="Architecture Diagram">
</p>

---

## Workflow

```text
REST API
    │
    ▼
HTTP Client
    │
    ▼
Response Validation
    │
    ▼
Data Normalization
    │
    ▼
Duplicate Detection
    │
    ▼
Insert / Update Decision
    │
    ▼
Google Sheets
```

---

## Features

- Google Sheets integration using Service Account authentication
- REST API data retrieval
- Automatic retry strategy for transient failures
- Duplicate record detection
- Existing record updates
- Batch insertion
- Input validation
- Structured application logging
- Environment-based configuration
- Type hints and dataclasses

---

## Technology Stack

| Technology | Purpose |
|------------|----------|
| Python | Application |
| requests | HTTP client |
| urllib3 | Retry mechanism |
| gspread | Google Sheets integration |
| oauth2client | Authentication |
| python-dotenv | Environment configuration |

---

## Project Structure

```text
.
├── assets
│   ├── architecture.png
│   ├── demo.gif
│   └── screenshot.png
│
├── main.py
├── requirements.txt
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

---

## Installation

Clone the repository.

```bash
git clone https://github.com/saeedakbarzade1371-rgb/python-google-sheets-automation.git

cd python-google-sheets-automation
```

Create a virtual environment.

```bash
python -m venv venv
```

Windows

```bash
venv\Scripts\activate
```

Linux / macOS

```bash
source venv/bin/activate
```

Install dependencies.

```bash
pip install -r requirements.txt
```

---

## Configuration

Create a local `.env` file.

```env
GOOGLE_CREDENTIALS_FILE=credentials.json
GOOGLE_SHEET_NAME=Shopify_Orders_Sync
API_URL=https://fakestoreapi.com/products
API_TIMEOUT=15
```

Place the Google Service Account credentials file in the project root.

```
credentials.json
```

Both `.env` and `credentials.json` are excluded from version control.

---

## Running

```bash
python main.py
```

---

## Example Log

```text
2026-07-26 15:40:22 [INFO] Starting synchronization
2026-07-26 15:40:23 [INFO] Connected to Google Sheets
2026-07-26 15:40:24 [INFO] Retrieved 20 records
2026-07-26 15:40:24 [INFO] Inserted 20 records
2026-07-26 15:40:24 [INFO] Synchronization completed
```

---

## Future Improvements

- Unit tests
- GitHub Actions CI
- Docker support
- Automatic spreadsheet creation
- Multiple worksheet support
- Pydantic-based configuration validation

---

## License

This project is licensed under the MIT License.

---

## Author

**Saeed Akbarzade**

GitHub:
https://github.com/saeedakbarzade1371-rgb