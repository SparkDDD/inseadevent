import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import pytz
import os
import time # Import time for rate limiting

MAIN_URL = "https://www.insead.edu/events/listing"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Add X-Requested-With header, crucial for AJAX requests
    "X-Requested-With": "XMLHttpRequest" 
}

AJAX_URL = "https://www.insead.edu/views/ajax"

# Airtable configuration
# It's highly recommended to use environment variables for sensitive data like API keys.
# Example: AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_BASE_ID = "appoz4aD0Hjolycwd"
AIRTABLE_TABLE_ID = "tblSvkrwpJlB4A195"
AIRTABLE_API_KEY = "patQklX1y11lFtFFY.74b2fc99a09edbf052f3ff8fcf378c3c3b09397f0683dd171b968ad747a4035b" # Consider using os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_API_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"
AIRTABLE_FIELDS = {
    'event': 'fldtf8ZLoMws7T2Kb',  # Text
    'Month & Day': 'fldbPvdBcLOYveRCb',  # Date
    'location': 'fld1oH8ryr7mPJyWM',  # Text
    'eventurl': 'fldGhcjpsG70VKrPd',  # URL
    'Added At': 'fldZ8o1YMKacrc2aG',  # Text
    'AsiaRelated': 'fldcMTZJFG4C6dJDw', # Checkbox
    'Event Unique ID': 'fldT2yKdU4FYHBAZp' # IMPORTANT: Replace fldXXXXXXX with the actual field ID for your new "Event Unique ID" field in Airtable.
}


def extract_dynamic_params():
    """
    Extracts the dynamic view_dom_id from the main events listing page.
    This ID is necessary for making subsequent AJAX requests.
    """
    try:
        res = requests.get(MAIN_URL, headers=HEADERS)
        res.raise_for_status() # Raise an exception for HTTP errors
        html = res.text
        dom_id_match = re.search(r'js-view-dom-id-([a-f0-9]+)', html)
        if dom_id_match:
            print(f"Successfully extracted view_dom_id: {dom_id_match.group(1)}")
            return dom_id_match.group(1)
        else:
            print("Error: Could not find view_dom_id in the main page HTML.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching main page to extract dynamic params: {e}")
        return None


def parse_date(date_str):
    """
    Parses various date string formats into ISO 8601 (YYYY-MM-DD) format.
    Handles single dates, date ranges, and abbreviated years.
    """
    if not date_str:
        return None

    # Clean up the date string by removing extra spaces and normalizing separators
    date_str = ' '.join(date_str.split())

    # Define date patterns and whether they represent a range
    date_patterns = [
        (r'(\d{1,2})\s+([A-Za-z]+)\s+\'?(\d{2})\s*-\s*\d{1,2}\s+[A-Za-z]+\s+\'?\d{2}', True, '%d %b %Y'), # 01 Mar '25 - 30 Nov '25
        (r'(\d{1,2})\s*-\s*(\d{1,2})\s+([A-Za-z]+)\s+\'?(\d{2})', True, '%d %b %Y'), # 04 - 25 Jun '25
        (r'(\d{1,2}\s+[A-Za-z]+\s+\d{4},\s+\d{1,2}:\d{2}\s+[ap]m)', False, '%d %B %Y, %I:%M %p'), # 10 June 2025, 1:00 pm
        (r'(\d{1,2}\s+[A-Za-z]+\s+\d{4})', False, '%d %B %Y'), # 10 June 2025
        (r'(\d{1,2}\s+[A-Za-z]+\s+\'?\d{2})', False, '%d %b %Y'), # 12 Jun '25 or 12 Jun 25
    ]

    for pattern, is_range, date_format in date_patterns:
        match = re.search(pattern, date_str)
        if match:
            try:
                # For date ranges, extract the start date
                if is_range:
                    if len(match.groups()) == 4: # Pattern like '04 - 25 Jun '25'
                        start_day = match.group(1)
                        month = match.group(3)
                        year = match.group(4)
                    else: # Pattern like '01 Mar '25 - 30 Nov '25'
                        start_day = match.group(1)
                        month = match.group(2)
                        year = match.group(3)
                    temp_date_str = f"{start_day} {month} 20{year}" # Assume '25 means 2025
                else:
                    temp_date_str = match.group(1)

                # Handle abbreviated year by replacing single quote with '20'
                if "'" in temp_date_str:
                    temp_date_str = temp_date_str.replace("'", "20")

                date_obj = datetime.strptime(temp_date_str, date_format)
                return date_obj.strftime('%Y-%m-%d')
            except ValueError:
                # If parsing fails for this pattern, try the next one
                continue
    print(f"Warning: Could not parse date string: '{date_str}'")
    return None


def is_asia_related(location):
    """
    Checks if a location string contains keywords related to Asia.
    """
    if not location:
        return False
    asia_keywords = ['asia', 'singapore', 'china', 'japan', 'korea', 'india', 'indonesia', 'malaysia', 'thailand', 'vietnam']
    return any(keyword in location.lower() for keyword in asia_keywords)


def prepare_airtable_record(event_data):
    """
    Prepares event data into the dictionary format required by the Airtable API.
    """
    # Ensure 'Event Unique ID' field exists in AIRTABLE_FIELDS before accessing it
    if 'Event Unique ID' not in AIRTABLE_FIELDS:
        print("Error: 'Event Unique ID' field ID is missing in AIRTABLE_FIELDS. Please add it.")
        return None

    return {
        "fields": {
            AIRTABLE_FIELDS['event']: event_data.get('event', ''),
            AIRTABLE_FIELDS['Month & Day']: event_data.get('Month & Day'), # Can be None
            AIRTABLE_FIELDS['location']: event_data.get('location', ''),
            AIRTABLE_FIELDS['eventurl']: event_data.get('eventurl', ''),
            AIRTABLE_FIELDS['Added At']: event_data.get('Added At', ''),
            AIRTABLE_FIELDS['AsiaRelated']: event_data.get('AsiaRelated', False),
            AIRTABLE_FIELDS['Event Unique ID']: event_data.get('custom_unique_id', '') # Add the new custom unique ID field
        }
    }


def manage_airtable_record(record):
    """
    Checks if a record exists in Airtable by custom unique ID. If it exists, it updates it.
    If it doesn't exist, it creates a new record.
    Returns the Airtable record ID.
    """
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    custom_unique_id = record['fields'][AIRTABLE_FIELDS['Event Unique ID']]

    # Check if the event with this custom unique ID already exists in Airtable
    try:
        # We need to use the actual Airtable field name for the filter, not the internal key
        unique_id_field_name = [k for k, v in AIRTABLE_FIELDS.items() if v == AIRTABLE_FIELDS['Event Unique ID']][0]

        response = requests.get(AIRTABLE_API_URL, headers=headers, params={'filterByFormula': f"{{{unique_id_field_name}}}='{custom_unique_id}'"})
        response.raise_for_status()
        existing_records = response.json().get('records', [])

        if existing_records:
            record_id = existing_records[0]['id']
            # Update the existing record
            update_response = requests.patch(f"{AIRTABLE_API_URL}/{record_id}", headers=headers, json={"fields": record['fields']})
            update_response.raise_for_status()
            print(f"    ✓ Updated existing Airtable record with ID: {record_id} for Unique ID: {custom_unique_id}")
            return record_id
        else:
            # Create a new record
            create_response = requests.post(AIRTABLE_API_URL, headers=headers, json=record)
            create_response.raise_for_status()
            record_id = create_response.json()['id']
            print(f"    ✓ Created new Airtable record with ID: {record_id} for Unique ID: {custom_unique_id}")
            return record_id
    except requests.exceptions.RequestException as e:
        print(f"    ✗ Airtable API error for Unique ID {custom_unique_id}: {e}")
        return None


def fetch_events_from_ajax(view_dom_id, page=0):
    """
    Fetches events from the AJAX endpoint for a specific page.
    """
    libraries = "" # This might need to be dynamically extracted or kept empty if not critical
    params = {
        '_wrapper_format': 'drupal_ajax',
        'view_name': 'events_listing',
        'view_display_id': 'events_listing',
        'view_args': '',
        'view_path': '/events/listing',
        'view_base_path': 'events/listing',
        'view_dom_id': view_dom_id,
        'pager_element': 0,
        'page': page, # This 'page' parameter controls the AJAX pagination
        '_drupal_ajax': 1,
        'ajax_page_state[theme]': 'insead_core',
        'ajax_page_state[theme_token]': '',
        'ajax_page_state[libraries]': libraries
    }

    # Create a dynamic set of headers for this request
    dynamic_headers = HEADERS.copy()
    # Set the Referer header based on the current page for AJAX calls
    # Referer should typically match the page from which the AJAX call is initiated
    dynamic_headers["Referer"] = f"{MAIN_URL}?page={page}"

    try:
        # Changed to GET request based on network log analysis
        res = requests.get(AJAX_URL, headers=dynamic_headers, params=params) # Pass params as 'params' for GET
        res.raise_for_status()
        data = res.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching AJAX page {page}: {e}")
        return []
    except ValueError as e: # Catch JSON decoding errors
        print(f"Error decoding JSON response from AJAX page {page}: {e}. Response was: {res.text[:200]}...")
        return []

    events = []
    current_time = datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')

    for item in data:
        if 'data' in item and item['data']: # Ensure 'data' key exists and is not empty
            html_data = item['data']
            if isinstance(html_data, list):
                # Concatenate list of HTML strings if present
                html_data = ''.join([x for x in html_data if isinstance(x, str)])

            soup = BeautifulSoup(html_data, 'html.parser')
            for card in soup.select('.event-card-full'):
                title_tag = card.select_one('.h5__link.list-object__heading-link')
                title = title_tag.get_text(strip=True) if title_tag else ''
                link = title_tag['href'] if title_tag and title_tag.has_attr('href') else ''
                if link and not link.startswith('http'):
                    link = 'https://www.insead.edu' + link

                date_str = ''
                # Prioritize the more robust date container selector for AJAX calls
                date_container = card.select_one('.event__date-container__label')
                if date_container:
                    date_parts = [part.strip() for part in date_container.stripped_strings if part.strip() and part.strip() != '-']
                    date_str = ' '.join(date_parts)
                else: # Fallback to the other selector if the primary one isn't found
                    date_tag = card.select_one('.event-card-full__datetime .link')
                    if date_tag:
                        date_str = date_tag.get_text(strip=True)


                location_tag = card.select_one('.event-card-full__location .link')
                location = location_tag.get_text(strip=True) if location_tag else ''

                event_data = {
                    'event': title,
                    'Month & Day': parse_date(date_str),
                    'location': location,
                    'eventurl': link,
                    'Added At': current_time,
                    'AsiaRelated': is_asia_related(location)
                }
                # Generate a unique ID based on title and URL for Airtable
                if event_data['event'] and event_data['eventurl']:
                    # Normalize title for consistent unique ID generation (e.g., lowercase, remove non-alphanumeric)
                    normalized_title = re.sub(r'[^a-z0-9]', '', event_data['event'].lower())
                    event_data['custom_unique_id'] = f"{normalized_title}-{event_data['eventurl']}"
                else:
                    event_data['custom_unique_id'] = '' # Ensure it's not None if title/URL is missing

                if event_data['eventurl']: # Only add events with a valid URL
                    events.append(event_data)
    return events


def fetch_events_from_main_page():
    """
    Fetches events visible on the initial load of the main events listing page.
    """
    try:
        # Use existing HEADERS for main page GET request
        res = requests.get(MAIN_URL, headers=HEADERS)
        res.raise_for_status()
        html = res.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching main page for initial events: {e}")
        return []

    soup = BeautifulSoup(html, 'html.parser')
    events = []
    current_time = datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')

    for card in soup.select('.event-card-full'):
        title_tag = card.select_one('.h5__link.list-object__heading-link')
        title = title_tag.get_text(strip=True) if title_tag else ''
        link = title_tag['href'] if title_tag and title_tag.has_attr('href') else ''
        if link and not link.startswith('http'):
            link = 'https://www.insead.edu' + link

        date_str = ''
        # Prioritize the more robust date container selector for main page
        date_container = card.select_one('.event__date-container__label')
        if date_container:
            date_parts = [part.strip() for part in date_container.stripped_strings if part.strip() and part.strip() != '-']
            date_str = ' '.join(date_parts)
        else: # Fallback to the other selector if the primary one isn't found
            date_tag = card.select_one('.event-card-full__datetime .link')
            if date_tag:
                date_str = date_tag.get_text(strip=True)

        location_tag = card.select_one('.event-card-full__location .link')
        location = location_tag.get_text(strip=True) if location_tag else ''

        event_data = {
            'event': title,
            'Month & Day': parse_date(date_str),
            'location': location,
            'eventurl': link,
            'Added At': current_time,
            'AsiaRelated': is_asia_related(location)
        }
        # Generate a unique ID based on title and URL for Airtable
        if event_data['event'] and event_data['eventurl']:
            normalized_title = re.sub(r'[^a-z0-9]', '', event_data['event'].lower())
            event_data['custom_unique_id'] = f"{normalized_title}-{event_data['eventurl']}"
        else:
            event_data['custom_unique_id'] = '' # Ensure it's not None if title/URL is missing

        if event_data['eventurl']: # Only add events with a valid URL
            events.append(event_data)
    return events


def fetch_all_events_hybrid():
    """
    Fetches events from both the main page and iterates through all AJAX pages.
    Deduplicates and merges event data.
    """
    events_dict = {}

    # 1. Fetch events from the main page first
    print("Fetching events from the main page...")
    main_page_events = fetch_events_from_main_page()
    for event in main_page_events:
        if event.get('eventurl') and event.get('event'):
            # Use a tuple of (event_title, event_url) as the unique key for in-memory deduplication
            unique_key = (event['event'], event['eventurl'])
            events_dict[unique_key] = event 
    print(f"Found {len(main_page_events)} events on the main page.")

    # 2. Extract dynamic parameters for AJAX pagination
    view_dom_id = extract_dynamic_params()
    if not view_dom_id:
        print("Cannot proceed with AJAX fetching due to missing view_dom_id.")
        return list(events_dict.values()) # Return only main page events if AJAX fails

    # 3. Fetch events from AJAX pages
    page = 1 # Start AJAX pagination from page 1, assuming page 0 content is similar to main page
    while True:
        print(f"Fetching events from AJAX page {page}...")
        ajax_events = fetch_events_from_ajax(view_dom_id, page)

        if not ajax_events:
            print(f"No more events found on AJAX page {page}. Stopping pagination.")
            break # No more events, stop pagination

        # Process events from the current AJAX page
        events_added_this_page = 0
        for event in ajax_events:
            if event.get('eventurl') and event.get('event'): # Ensure both title and URL are present
                unique_key = (event['event'], event['eventurl'])
                if unique_key not in events_dict:
                    # New event, add it
                    events_dict[unique_key] = event
                    events_added_this_page += 1
                else:
                    # Event already exists (based on title AND URL), intelligently merge missing data
                    existing_event = events_dict[unique_key]
                    for field_name, new_value in event.items():
                        # Update if existing value is None or empty, AND new_value is not None/empty
                        # Or if AsiaRelated is False (default) and a new source says True
                        if (existing_event.get(field_name) is None or existing_event.get(field_name) == '' or \
                            (field_name == 'AsiaRelated' and existing_event.get('AsiaRelated') is False)) \
                           and new_value is not None and new_value != '':
                            existing_event[field_name] = new_value

        print(f"Added {events_added_this_page} new unique events from AJAX page {page}.")

        # This stopping condition is crucial. If a page returns 0 new unique events,
        # it usually means we've reached the end of the unique paginated content.
        if events_added_this_page == 0:
             print("No new unique events found on this AJAX page. Assuming end of content.")
             break

        page += 1
        time.sleep(2) # Be polite and avoid overwhelming the server

    # Convert dictionary values back to a list
    return list(events_dict.values())


if __name__ == "__main__":
    print("Starting INSEAD Event Scraper...")

    # Call the hybrid function that fetches main page and iterates through all AJAX pages
    events = fetch_all_events_hybrid()

    print(f"\nFound a total of {len(events)} unique events. Processing for Airtable table {AIRTABLE_TABLE_ID}...")

    # IMPORTANT: You MUST replace 'fldXXXXXXX' in AIRTABLE_FIELDS['Event Unique ID']
    # with the actual field ID from your Airtable base for the "Event Unique ID" field.
    # Otherwise, Airtable updates will fail.
    if 'Event Unique ID' not in AIRTABLE_FIELDS or AIRTABLE_FIELDS['Event Unique ID'] == 'fldXXXXXXX':
        print("\nERROR: Please update 'AIRTABLE_FIELDS['Event Unique ID']' in the script with the actual field ID from your Airtable base.")
        print("This field is crucial for unique event identification in Airtable.")
    else:
        for i, event in enumerate(events, 1):
            airtable_record = prepare_airtable_record(event)

            # Ensure airtable_record is not None (e.g., if AIRTABLE_FIELDS was not correctly set up)
            if airtable_record is None:
                print(f"Skipping event {i} due to Airtable record preparation error.")
                continue

            print(f"\n{i}. Event Data (Airtable Format):")
            print(f"    Title: {airtable_record['fields'].get(AIRTABLE_FIELDS['event'], 'N/A')}")
            print(f"    Date: {airtable_record['fields'].get(AIRTABLE_FIELDS['Month & Day'], 'N/A')}")
            print(f"    Location: {airtable_record['fields'].get(AIRTABLE_FIELDS['location'], 'N/A')}")
            print(f"    URL: {airtable_record['fields'].get(AIRTABLE_FIELDS['eventurl'], 'N/A')}")
            print(f"    Added At: {airtable_record['fields'].get(AIRTABLE_FIELDS['Added At'], 'N/A')}")
            print(f"    Asia Related: {airtable_record['fields'].get(AIRTABLE_FIELDS['AsiaRelated'], 'N/A')}")
            print(f"    Event Unique ID: {airtable_record['fields'].get(AIRTABLE_FIELDS['Event Unique ID'], 'N/A')}")

            # Ensure eventurl and custom_unique_id are present before trying to manage in Airtable
            if airtable_record['fields'].get(AIRTABLE_FIELDS['eventurl']) and \
               airtable_record['fields'].get(AIRTABLE_FIELDS['Event Unique ID']):
                manage_airtable_record(airtable_record)
            else:
                print(f"    ✗ Skipping event due to missing URL or Custom Unique ID: {airtable_record['fields'].get(AIRTABLE_FIELDS['event'], 'N/A')}")

    print("\nScraping and Airtable synchronization complete!")
