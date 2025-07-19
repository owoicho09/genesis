# utils/all_date_parser.py

import re
from datetime import datetime, timedelta
import dateparser
from langchain.tools import tool

@tool
def parse_all_dates(prompt: str) -> dict:
    """
    Parses ANY type of date-related input from a prompt and returns
    start_date and end_date as datetime.date objects.

    Handles: 'from July 1 to July 5', 'in 3 days', 'for 5 days', 'starting August 3rd', etc.
    """
    now = datetime.now()
    prompt = prompt.lower().strip()

    def fallback_dates():
        return {
            "start_date": (now + timedelta(days=1)).date(),
            "end_date": (now + timedelta(days=6)).date()
        }

    # 1. Check for range: "from X to Y"
    range_match = re.search(r"from\s+(.*?)\s+to\s+(.*?)(\.|$)", prompt)
    if range_match:
        raw_start = range_match.group(1)
        raw_end = range_match.group(2)
        start = dateparser.parse(raw_start, settings={"PREFER_DATES_FROM": "future"})
        end = dateparser.parse(raw_end, settings={"PREFER_DATES_FROM": "future"})
        if start and end:
            return {"start_date": start.date(), "end_date": end.date()}

    # 2. Parse start date
    start_match = re.search(r"(start(?:ing)?|begin(?:ning)?|launch(?:ing)?(?: on)?)\s+(.*?)(?:\s+and|\,|\.|$)", prompt)
    start_date = None
    if start_match:
        raw_start = start_match.group(2)
        start_date = dateparser.parse(raw_start, settings={"PREFER_DATES_FROM": "future"})

    if not start_date:
        start_date = now + timedelta(days=1)

    # 3. Look for duration-based end (e.g., 'for 3 days', 'ending in 5 days', 'run for 1 week')
    dur_match = re.search(r"(for|ending in|run for|end after)\s+(\d+)\s+(day|days|week|weeks)", prompt)
    if dur_match:
        amount = int(dur_match.group(2))
        unit = dur_match.group(3)
        delta = timedelta(days=amount) if "day" in unit else timedelta(weeks=amount)
        return {
            "start_date": start_date.date(),
            "end_date": (start_date + delta).date()
        }

    # 4. Check for hardcoded end date
    end_match = re.search(r"end(?:ing)?(?: on)?\s+(.*?)(\.|$)", prompt)
    if end_match:
        raw_end = end_match.group(1)
        end_date = dateparser.parse(raw_end, settings={"PREFER_DATES_FROM": "future"})
        if end_date:
            return {
                "start_date": start_date.date(),
                "end_date": end_date.date()
            }

    # 5. Fallback: Default to 5-day campaign starting tomorrow
    return {
        "start_date": start_date.date(),
        "end_date": (start_date + timedelta(days=5)).date()
    }




