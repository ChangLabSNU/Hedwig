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

"""Timezone utilities for consistent datetime handling across Hedwig"""

from datetime import datetime, timezone
from typing import Optional, Union

import pytz

from .config import Config


class TimezoneManager:
    """Centralized timezone management for consistent datetime operations"""

    @classmethod
    def get_configured_timezone(cls, config: Config) -> pytz.BaseTzInfo:
        """Get the configured timezone

        Args:
            config: Configuration object

        Returns:
            pytz timezone object

        Raises:
            ValueError: If timezone is not configured or invalid
        """
        tz_name = config.get('global.timezone')

        if not tz_name:
            raise ValueError("global.timezone must be configured")

        try:
            return pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            raise ValueError(f"Unknown timezone '{tz_name}' in global.timezone configuration")

    @classmethod
    def now_local(cls, config: Config) -> datetime:
        """Get current time in the configured local timezone

        Args:
            config: Configuration object

        Returns:
            Current datetime in configured timezone
        """
        tz = cls.get_configured_timezone(config)
        return datetime.now(tz)

    @classmethod
    def now_utc(cls) -> datetime:
        """Get current time in UTC

        Returns:
            Current datetime in UTC
        """
        return datetime.now(timezone.utc)

    @classmethod
    def to_local(cls, dt: datetime, config: Config) -> datetime:
        """Convert datetime to configured local timezone

        Args:
            dt: Datetime to convert
            config: Configuration object

        Returns:
            Datetime in configured timezone
        """
        tz = cls.get_configured_timezone(config)

        if dt.tzinfo is None:
            # Assume naive datetime is in UTC
            dt = pytz.UTC.localize(dt)

        return dt.astimezone(tz)

    @classmethod
    def to_utc(cls, dt: datetime) -> datetime:
        """Convert datetime to UTC

        Args:
            dt: Datetime to convert

        Returns:
            Datetime in UTC
        """
        if dt.tzinfo is None:
            # Assume naive datetime is in local system timezone
            dt = pytz.timezone('UTC').localize(dt)

        return dt.astimezone(timezone.utc)

    @classmethod
    def format_local(cls, config: Config, format_str: str = '%Y-%m-%d %H:%M:%S') -> str:
        """Format current time in configured local timezone

        Args:
            config: Configuration object
            format_str: strftime format string

        Returns:
            Formatted datetime string
        """
        return cls.now_local(config).strftime(format_str)

    @classmethod
    def format_utc(cls, format_str: str = '%Y-%m-%d %H:%M:%S UTC') -> str:
        """Format current time in UTC

        Args:
            format_str: strftime format string

        Returns:
            Formatted datetime string in UTC
        """
        return cls.now_utc().strftime(format_str)

    @classmethod
    def get_local_date(cls, config: Config) -> datetime:
        """Get current date in configured local timezone

        Args:
            config: Configuration object

        Returns:
            Date portion of current datetime in configured timezone
        """
        return cls.now_local(config).date()

    @classmethod
    def get_local_weekday(cls, config: Config) -> int:
        """Get current weekday in configured local timezone

        Args:
            config: Configuration object

        Returns:
            Weekday as integer (0=Monday, 6=Sunday)
        """
        return cls.now_local(config).weekday()


# Convenience functions for common operations
def get_timezone(config: Config) -> pytz.BaseTzInfo:
    """Convenience function to get configured timezone"""
    return TimezoneManager.get_configured_timezone(config)


def now_local(config: Config) -> datetime:
    """Convenience function for local time"""
    return TimezoneManager.now_local(config)


def now_utc() -> datetime:
    """Convenience function for UTC time"""
    return TimezoneManager.now_utc()


def format_local(config: Config, format_str: str = '%Y-%m-%d %H:%M:%S') -> str:
    """Convenience function to format local time"""
    return TimezoneManager.format_local(config, format_str)


def format_utc(format_str: str = '%Y-%m-%d %H:%M:%S UTC') -> str:
    """Convenience function to format UTC time"""
    return TimezoneManager.format_utc(format_str)