"""
Sync all historical applications to Google Sheet.
Usage:
    python sync_to_sheet.py
"""
import sys
from common.google_sheet import sync_all_history_to_sheet, GOOGLE_SHEET_URL, get_webhook_url

if __name__ == "__main__":
    url = get_webhook_url()
    if not url:
        print("=" * 60)
        print("GOOGLE_SHEET_WEBHOOK_URL is not set yet in .env!")
        print("=" * 60)
        print("Follow these 3 simple steps to connect your Google Sheet:")
        print("1. Open your sheet: " + GOOGLE_SHEET_URL)
        print("2. In the top menu, click Extensions > Apps Script")
        print("3. See GOOGLE_SHEET_SETUP.md for the quick 5-line script.")
        print("=" * 60)
        sys.exit(1)

    print("Connecting to Google Sheet...")
    success = sync_all_history_to_sheet()
    if success:
        print("\nAll applications successfully synced to your Google Sheet!")
        print(f"Open sheet: {GOOGLE_SHEET_URL}")
