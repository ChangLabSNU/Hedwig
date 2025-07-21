#
# Copyright (c) 2025 Seoul National University
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Calendar context plugin for overview generation"""

from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta, timezone
import os
import re
import requests
import pytz

from .base import ContextPlugin
from .registry import ContextPluginRegistry


class CalendarContextPlugin(ContextPlugin):
    """Provides calendar context information from iCal/CalDAV sources"""

    def __init__(self, config: Dict[str, Any], logger=None):
        super().__init__(config, logger)

        self.calendars = config.get('calendars', [])
        self.days_before = config.get('days_before', 0)
        self.days_after = config.get('days_after', 0)

        # Get timezone from config, default to UTC if not specified
        tz_name = config.get('timezone', 'UTC')
        try:
            self.timezone = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            self.logger.warning(f"Unknown timezone '{tz_name}', using UTC")
            self.timezone = pytz.UTC

        if not self.calendars:
            self.logger.warning("Calendar plugin: no calendars configured")
            self.enabled = False

    @property
    def name(self) -> str:
        return "calendar"

    def get_context(self) -> Optional[str]:
        """Get calendar context information

        Returns:
            Calendar context string or None if failed
        """
        if not self.is_enabled():
            return None

        context_parts = []

        for calendar in self.calendars:
            if not calendar.get('enabled', True):
                continue

            calendar_name = calendar.get('name', 'Calendar')
            calendar_type = calendar.get('type', 'ical')

            try:
                if calendar_type == 'ical':
                    context = self._get_ical_context(calendar)
                elif calendar_type == 'caldav':
                    context = self._get_caldav_context(calendar)
                else:
                    self.logger.warning(f"Unknown calendar type: {calendar_type}")
                    continue

                if context:
                    context_parts.append(context)

            except Exception as e:
                self.logger.error(f"Failed to get context from calendar '{calendar_name}': {e}")

        if not context_parts:
            return None

        return "\n\n".join(context_parts)

    def _get_ical_context(self, calendar_config: Dict[str, Any]) -> Optional[str]:
        """Get context from iCal URL

        Args:
            calendar_config: Calendar configuration

        Returns:
            Context string or None
        """
        url = calendar_config.get('url')
        if not url:
            self.logger.warning("iCal calendar missing URL")
            return None

        calendar_name = calendar_config.get('name', 'Calendar')

        # Fetch iCal data
        ical_data = self._fetch_ical_data(url)
        if not ical_data:
            return None

        # Parse events
        events = self._parse_ical_data(ical_data)
        if not events:
            return None

        # Filter relevant events
        relevant_events = self._filter_relevant_events(events)

        # Format as context
        return self._format_calendar_context(relevant_events, calendar_name)

    def _get_caldav_context(self, calendar_config: Dict[str, Any]) -> Optional[str]:
        """Get context from CalDAV server

        Args:
            calendar_config: Calendar configuration

        Returns:
            Context string or None
        """
        try:
            # Import caldav library (optional dependency)
            import caldav
        except ImportError:
            self.logger.error("CalDAV support requires 'caldav' package. Install with: pip install caldav")
            return None

        url = calendar_config.get('url')
        if not url:
            self.logger.warning("CalDAV calendar missing URL")
            return None

        calendar_name = calendar_config.get('name', 'Calendar')
        username = calendar_config.get('username') or os.getenv('CALDAV_USERNAME')
        password = calendar_config.get('password') or os.getenv('CALDAV_PASSWORD')

        try:
            # Connect to CalDAV server
            if username and password:
                client = caldav.DAVClient(url=url, username=username, password=password)
            else:
                client = caldav.DAVClient(url=url)

            principal = client.principal()

            # Get calendar URL if not directly provided
            calendar_url = calendar_config.get('calendar_url')
            if calendar_url:
                calendar = caldav.Calendar(client=client, url=calendar_url)
            else:
                # Try to get the default calendar
                calendars = principal.calendars()
                if not calendars:
                    self.logger.warning(f"No calendars found for {calendar_name}")
                    return None
                calendar = calendars[0]  # Use first calendar

            # Calculate date range
            now = datetime.now(self.timezone)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start_date = today_start - timedelta(days=self.days_before)
            end_date = today_start + timedelta(days=self.days_after + 1)

            # Search for events
            events = []
            try:
                # Search for events in the date range
                results = calendar.date_search(
                    start=start_date,
                    end=end_date,
                    expand=True
                )

                for event in results:
                    # Parse VEVENT from CalDAV response
                    ical_data = event.data
                    if ical_data:
                        parsed_events = self._parse_ical_data(ical_data)
                        events.extend(parsed_events)

            except Exception as e:
                self.logger.error(f"Error searching CalDAV calendar: {e}")
                return None

            if not events:
                return None

            # Convert to our event format and filter
            relevant_events = self._filter_relevant_events(events)

            # Format as context
            return self._format_calendar_context(relevant_events, calendar_name)

        except Exception as e:
            self.logger.error(f"CalDAV error for {calendar_name}: {e}")
            return None

    def _fetch_ical_data(self, url: str) -> Optional[str]:
        """Fetch iCal data from URL

        Args:
            url: URL to fetch iCal data from

        Returns:
            iCal data as string or None if failed
        """
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching iCal data: {e}")
            return None

    def _parse_ical_data(self, ical_data: str) -> List[Dict[str, str]]:
        """Parse iCal data and extract events

        Args:
            ical_data: Raw iCal data

        Returns:
            List of event dictionaries
        """
        events = []

        # Split into individual events
        event_pattern = re.compile(r'BEGIN:VEVENT(.*?)END:VEVENT', re.DOTALL)
        event_matches = event_pattern.findall(ical_data)

        for event_text in event_matches:
            event = self._parse_ical_event(event_text)
            if event:
                events.append(event)

        return events

    def _parse_ical_event(self, event_text: str) -> Optional[Dict[str, str]]:
        """Parse a single VEVENT from iCal format

        Args:
            event_text: Text of a single VEVENT

        Returns:
            Dictionary with event details or None if parsing fails
        """
        event = {}

        # Extract basic fields
        for line in event_text.split('\n'):
            if line.startswith('SUMMARY:'):
                event['summary'] = line[8:].strip()
            elif line.startswith('DTSTART'):
                # Handle different date formats
                if ':' in line:
                    event['start'] = line.split(':', 1)[1].strip()
                else:
                    event['start'] = line[7:].strip()
            elif line.startswith('DTEND'):
                if ':' in line:
                    event['end'] = line.split(':', 1)[1].strip()
                else:
                    event['end'] = line[5:].strip()
            elif line.startswith('DESCRIPTION:'):
                event['description'] = line[12:].strip()
            elif line.startswith('LOCATION:'):
                event['location'] = line[9:].strip()

        # Must have at least summary and start date
        if 'summary' in event and 'start' in event:
            return event

        return None

    def _parse_ical_datetime(self, dt_string: str, tz_info: Optional[timezone] = None) -> datetime:
        """Parse iCal datetime string to datetime object

        Args:
            dt_string: iCal datetime string (e.g., "20250101T090000Z" or "20250101")
            tz_info: Timezone info if not UTC

        Returns:
            datetime object
        """
        # Remove timezone identifier if present
        dt_string = dt_string.split(':')[-1]

        # Check if it's a date-only format
        if len(dt_string) == 8 and 'T' not in dt_string:
            # Date only format: YYYYMMDD
            dt = datetime.strptime(dt_string, '%Y%m%d')
            # Set to midnight in the given timezone or local timezone
            if tz_info:
                dt = dt.replace(tzinfo=tz_info)
            else:
                dt = dt.replace(hour=0, minute=0, second=0)
        elif dt_string.endswith('Z'):
            # UTC format: YYYYMMDDTHHMMSSZ
            dt = datetime.strptime(dt_string, '%Y%m%dT%H%M%SZ')
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            # Local time format: YYYYMMDDTHHMMSS
            dt = datetime.strptime(dt_string, '%Y%m%dT%H%M%S')
            if tz_info:
                dt = dt.replace(tzinfo=tz_info)

        return dt

    def _filter_relevant_events(self, events: List[Dict[str, str]]) -> List[Tuple[datetime, Dict[str, str]]]:
        """Filter events within the relevant time window

        Args:
            events: List of parsed events

        Returns:
            List of (datetime, event) tuples sorted by date
        """
        now = datetime.now(self.timezone)
        # For date comparison, use start of day to include all-day events
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_window = today_start - timedelta(days=self.days_before)
        end_window = today_start + timedelta(days=self.days_after + 1)  # +1 to include the last day fully

        relevant_events = []

        for event in events:
            try:
                event_dt = self._parse_ical_datetime(event['start'])

                # Convert to UTC for comparison if needed
                if event_dt.tzinfo is None:
                    event_dt = event_dt.replace(tzinfo=timezone.utc)
                elif event_dt.tzinfo != timezone.utc:
                    event_dt = event_dt.astimezone(timezone.utc)

                if start_window <= event_dt <= end_window:
                    relevant_events.append((event_dt, event))
            except Exception as e:
                self.logger.error(f"Error parsing event date: {e}")
                continue

        # Sort by date
        relevant_events.sort(key=lambda x: x[0])

        return relevant_events

    def _format_calendar_context(self, events: List[Tuple[datetime, Dict[str, str]]],
                                calendar_name: str) -> Optional[str]:
        """Format events as context text

        Args:
            events: List of (datetime, event) tuples
            calendar_name: Name of the calendar for display

        Returns:
            Formatted context string or None if no events
        """
        if not events:
            return None

        now = datetime.now(self.timezone)
        context_lines = [f"Upcoming events from {calendar_name}:"]

        # Group events by relative time periods
        today_events = []
        this_week_events = []
        next_week_events = []
        later_events = []

        for event_dt, event in events:
            days_diff = (event_dt.date() - now.date()).days

            if days_diff < 0:
                continue  # Skip past events
            elif days_diff == 0:
                today_events.append((event_dt, event))
            elif days_diff <= 7:
                this_week_events.append((event_dt, event))
            elif days_diff <= 14:
                next_week_events.append((event_dt, event))
            else:
                later_events.append((event_dt, event))

        # Format each group
        if today_events:
            context_lines.append("\nToday:")
            for dt, event in today_events:
                context_lines.append(f"  - {event['summary']}")

        if this_week_events:
            context_lines.append("\nThis week:")
            for dt, event in this_week_events:
                date_str = dt.strftime("%a %d")
                context_lines.append(f"  - {date_str}: {event['summary']}")

        if next_week_events:
            context_lines.append("\nNext week:")
            for dt, event in next_week_events:
                date_str = dt.strftime("%a %d")
                context_lines.append(f"  - {date_str}: {event['summary']}")

        if later_events and len(later_events) <= 5:
            context_lines.append("\nLater:")
            for dt, event in later_events[:5]:
                date_str = dt.strftime("%b %d")
                context_lines.append(f"  - {date_str}: {event['summary']}")

        return "\n".join(context_lines)


# Register the plugin
ContextPluginRegistry.register("calendar", CalendarContextPlugin)