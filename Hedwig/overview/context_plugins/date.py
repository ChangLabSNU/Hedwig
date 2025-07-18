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

"""Date context plugin for providing current date and weekday information."""

from typing import Optional, Dict, Any
from datetime import datetime
import pytz

from .base import ContextPlugin
from .registry import ContextPluginRegistry


class DateContextPlugin(ContextPlugin):
    """Context plugin that provides current date and weekday information."""

    def __init__(self, config: Dict[str, Any], logger=None):
        super().__init__(config, logger)

        # Get timezone from config, default to UTC if not specified
        tz_name = config.get('timezone', 'UTC')
        try:
            self.timezone = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            self.logger.warning(f"Unknown timezone '{tz_name}', using UTC")
            self.timezone = pytz.UTC

    @property
    def name(self) -> str:
        return "date"

    def get_context(self) -> Optional[str]:
        """Return the current date and weekday information.

        Returns:
            Date string, or None if disabled
        """
        if not self.enabled:
            return None

        now = datetime.now(self.timezone)

        # Simple format: "2025-07-19 (Friday)"
        date_str = now.strftime('%Y-%m-%d (%A)')

        return f"Today: {date_str}"


# Register the plugin
ContextPluginRegistry.register("date", DateContextPlugin)