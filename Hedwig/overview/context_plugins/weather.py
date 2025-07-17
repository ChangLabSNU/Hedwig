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

"""Weather context plugin for overview generation"""

from typing import Optional, Dict, Any
import requests

from .base import ContextPlugin
from .registry import ContextPluginRegistry


class WeatherContextPlugin(ContextPlugin):
    """Provides weather context information for overview generation"""

    def __init__(self, config: Dict[str, Any], logger=None):
        super().__init__(config, logger)
        self.latitude = config.get('latitude')
        self.longitude = config.get('longitude')
        self.city_name = config.get('city_name', 'the location')

        if not self.latitude or not self.longitude:
            self.logger.warning("Weather plugin: latitude/longitude not configured")
            self.enabled = False

    @property
    def name(self) -> str:
        return "weather"

    def get_context(self) -> Optional[str]:
        """Get weather context information

        Returns:
            Weather context string or None if failed
        """
        if not self.is_enabled():
            return None

        try:
            weather_data = self._fetch_weather_data()
            if not weather_data:
                return None

            return self._format_weather_context(weather_data)

        except Exception as e:
            self.logger.error(f"Failed to get weather context: {e}")
            return None

    def _fetch_weather_data(self) -> Optional[Dict[str, Any]]:
        """Fetch weather data from Open-Meteo API

        Returns:
            Weather data dict or None if failed
        """
        base_url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "daily": "weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "auto",
            "past_days": 1
        }

        try:
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching weather data: {e}")
            return None

    def _format_weather_context(self, weather_data: Dict[str, Any]) -> str:
        """Format weather data into context string

        Args:
            weather_data: Raw weather data from API

        Returns:
            Formatted weather context
        """
        daily = weather_data.get('daily', {})
        dates = daily.get('time', [])
        max_temps = daily.get('temperature_2m_max', [])
        min_temps = daily.get('temperature_2m_min', [])
        precipitation = daily.get('precipitation_sum', [])
        weather_codes = daily.get('weathercode', [])

        if len(dates) < 3:
            return None

        # Get weather descriptions
        weather_descriptions = [self._get_weather_description(code) for code in weather_codes]

        # Format context
        context_lines = [f"Weather context for {self.city_name}:"]

        labels = ['Yesterday', 'Today', 'Tomorrow']
        for i, label in enumerate(labels):
            if i < len(dates):
                desc = weather_descriptions[i] if i < len(weather_descriptions) else "Unknown"
                temp_range = f"{min_temps[i]:.1f}°C - {max_temps[i]:.1f}°C" if i < len(min_temps) else "N/A"
                precip = f"{precipitation[i]:.1f}mm" if i < len(precipitation) and precipitation[i] > 0 else "No rain"

                context_lines.append(f"- {label}: {desc}, {temp_range}, {precip}")

        return "\n".join(context_lines)

    def _get_weather_description(self, code: int) -> str:
        """Convert weather code to description

        Args:
            code: WMO weather code

        Returns:
            Weather description
        """
        # Simplified weather code mapping
        weather_codes = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Foggy",
            48: "Depositing rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            71: "Slight snow",
            73: "Moderate snow",
            75: "Heavy snow",
            80: "Slight rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            85: "Slight snow showers",
            86: "Heavy snow showers",
            95: "Thunderstorm",
            96: "Thunderstorm with slight hail",
            99: "Thunderstorm with heavy hail"
        }

        return weather_codes.get(code, "Unknown")


# Register the plugin
ContextPluginRegistry.register("weather", WeatherContextPlugin)