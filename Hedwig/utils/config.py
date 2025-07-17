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

"""Configuration management for Hedwig"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import pytz


class Config:
    """Configuration manager for Hedwig"""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize configuration from YAML file

        Args:
            config_path: Path to configuration file. If None, looks for config.yml
                        in common locations.
        """
        self.config_path = self._find_config_file(config_path)
        self.data = self._load_config()

    def _find_config_file(self, config_path: Optional[str]) -> Path:
        """Find configuration file in various locations"""
        if config_path:
            path = Path(config_path)
            if path.exists():
                return path
            raise FileNotFoundError(f"Config file not found: {config_path}")

        # Look for config in common locations
        search_paths = [
            Path.cwd() / "config.yml",
            Path.cwd() / "qbio" / "config.yml",
            Path.home() / ".config" / "hedwig" / "config.yml",
            Path("/etc/hedwig/config.yml"),
        ]

        for path in search_paths:
            if path.exists():
                return path

        raise FileNotFoundError(
            "No config.yml found. Searched in: " +
            ", ".join(str(p) for p in search_paths)
        )

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation

        Args:
            key: Configuration key (e.g., 'notion.api_key')
            default: Default value if key not found

        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self.data

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def __getitem__(self, key: str) -> Any:
        """Get configuration section"""
        return self.data[key]

    @property
    def notion(self) -> Dict[str, Any]:
        """Get Notion configuration section (now under api.notion)"""
        # Support both new and old structure
        api_config = self.data.get('api', {})
        if 'notion' in api_config:
            return api_config['notion']
        # Fallback to old structure
        return self.data.get('notion', {})

    @property
    def sync(self) -> Dict[str, Any]:
        """Get sync configuration section"""
        return self.data.get('sync', {})

    @property
    def output(self) -> Dict[str, Any]:
        """Get output configuration section"""
        return self.data.get('output', {})

    @property
    def markdown(self) -> Dict[str, Any]:
        """Get markdown configuration section"""
        return self.data.get('markdown', {})

    @property
    def git(self) -> Dict[str, Any]:
        """Get git configuration section"""
        return self.data.get('git', {})

    def validate_config(self) -> List[Tuple[str, str]]:
        """Validate configuration and return list of issues

        Returns:
            List of (severity, message) tuples where severity is 'error', 'warning', or 'info'
        """
        issues = []

        # Validate required sections
        issues.extend(self._validate_paths())
        issues.extend(self._validate_global_settings())
        issues.extend(self._validate_api_config())
        issues.extend(self._validate_messaging_config())
        issues.extend(self._validate_change_summary_config())
        issues.extend(self._validate_overview_config())

        return issues

    def _validate_paths(self) -> List[Tuple[str, str]]:
        """Validate paths configuration"""
        issues = []
        paths = self.data.get('paths', {})

        if not paths:
            issues.append(('error', 'Missing required section: paths'))
            return issues

        # Required paths
        required_paths = {
            'notes_repository': 'Git repository for Notion pages',
            'change_summary_output': 'Directory for generated summaries',
            'checkpoint_file': 'Checkpoint file for sync tracking'
        }

        for path_key, description in required_paths.items():
            path_value = paths.get(path_key)
            if not path_value:
                issues.append(('error', f'Missing required path: {path_key} ({description})'))
            elif isinstance(path_value, str):
                path_obj = Path(path_value)
                if path_key == 'notes_repository':
                    if not path_obj.exists():
                        issues.append(('warning', f'Notes repository path does not exist: {path_value}'))
                    elif not (path_obj / '.git').exists():
                        issues.append(('warning', f'Notes repository is not a git repository: {path_value}'))
                elif path_key == 'change_summary_output':
                    parent_dir = path_obj.parent
                    if not parent_dir.exists():
                        issues.append(('warning', f'Parent directory for change_summary_output does not exist: {parent_dir}'))
                elif path_key == 'checkpoint_file':
                    parent_dir = path_obj.parent
                    if not parent_dir.exists():
                        issues.append(('warning', f'Parent directory for checkpoint_file does not exist: {parent_dir}'))

        # Optional paths validation
        optional_paths = ['blacklist_file', 'userlist_file', 'userlist_override_file']
        for path_key in optional_paths:
            path_value = paths.get(path_key)
            if path_value and isinstance(path_value, str):
                path_obj = Path(path_value)
                parent_dir = path_obj.parent
                if not parent_dir.exists():
                    issues.append(('warning', f'Parent directory for {path_key} does not exist: {parent_dir}'))

        return issues

    def _validate_global_settings(self) -> List[Tuple[str, str]]:
        """Validate global settings"""
        issues = []
        global_config = self.data.get('global', {})

        if not global_config:
            issues.append(('error', 'Missing required section: global'))
            return issues

        # Validate timezone
        timezone = global_config.get('timezone')
        if not timezone:
            issues.append(('error', 'Missing required setting: global.timezone'))
        else:
            try:
                pytz.timezone(timezone)
            except pytz.UnknownTimeZoneError:
                issues.append(('error', f'Invalid timezone: {timezone}. Use a valid timezone like "Asia/Seoul"'))

        return issues

    def _validate_api_config(self) -> List[Tuple[str, str]]:
        """Validate API configuration"""
        issues = []
        api_config = self.data.get('api', {})

        if not api_config:
            issues.append(('error', 'Missing required section: api'))
            return issues

        # Validate Notion API
        notion_config = api_config.get('notion', {})
        if not notion_config:
            issues.append(('error', 'Missing required section: api.notion'))
        else:
            api_key = notion_config.get('api_key')
            if not api_key:
                # Check environment variable
                if not os.getenv('NOTION_API_KEY'):
                    issues.append(('error', 'Missing Notion API key. Set api.notion.api_key in config or NOTION_API_KEY environment variable'))
            elif not api_key.startswith('secret_'):
                issues.append(('warning', 'Notion API key should start with "secret_"'))

        # Validate LLM API
        llm_config = api_config.get('llm', {})
        if not llm_config:
            issues.append(('error', 'Missing required section: api.llm'))
        else:
            # Check for API key in config or environment
            api_key = llm_config.get('key')
            has_env_key = os.getenv('GEMINI_API_KEY') or os.getenv('OPENAI_API_KEY')
            if not api_key and not has_env_key:
                issues.append(('error', 'Missing LLM API key. Set api.llm.key in config or GEMINI_API_KEY/OPENAI_API_KEY environment variable'))

            # Validate models
            diff_model = llm_config.get('diff_summarization_model')
            overview_model = llm_config.get('overview_model')
            if not diff_model:
                issues.append(('warning', 'Missing api.llm.diff_summarization_model, using default'))
            if not overview_model:
                issues.append(('warning', 'Missing api.llm.overview_model, using default'))

        return issues

    def _validate_messaging_config(self) -> List[Tuple[str, str]]:
        """Validate messaging configuration"""
        issues = []
        messaging_config = self.data.get('messaging', {})

        if not messaging_config:
            issues.append(('info', 'No messaging configuration found. Summary posting will be skipped.'))
            return issues

        active_platform = messaging_config.get('active')
        if not active_platform:
            issues.append(('warning', 'No active messaging platform specified'))
            return issues

        # Validate Slack configuration if active
        if active_platform == 'slack':
            slack_config = messaging_config.get('slack', {})
            if not slack_config:
                issues.append(('error', 'Slack is active but messaging.slack section is missing'))
            else:
                token = slack_config.get('token')
                if not token:
                    if not os.getenv('SLACK_TOKEN'):
                        issues.append(('error', 'Missing Slack token. Set messaging.slack.token in config or SLACK_TOKEN environment variable'))
                elif not token.startswith(('xoxb-', 'xoxp-')):
                    issues.append(('warning', 'Slack token should start with "xoxb-" or "xoxp-"'))

                channel_id = slack_config.get('channel_id')
                if not channel_id:
                    issues.append(('warning', 'Missing messaging.slack.channel_id. You will need to specify channel when posting.'))
        else:
            issues.append(('warning', f'Unknown messaging platform: {active_platform}. Only "slack" is currently supported.'))

        return issues

    def _validate_change_summary_config(self) -> List[Tuple[str, str]]:
        """Validate change summary configuration"""
        issues = []
        change_summary_config = self.data.get('change_summary', {})

        # Validate max_age_by_weekday
        weekday_config = change_summary_config.get('max_age_by_weekday', {})
        if weekday_config:
            valid_weekdays = {'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'}
            for weekday, days in weekday_config.items():
                if weekday not in valid_weekdays:
                    issues.append(('warning', f'Invalid weekday in max_age_by_weekday: {weekday}'))
                elif not isinstance(days, (int, float)) or days <= 0:
                    issues.append(('warning', f'Invalid max_age value for {weekday}: {days}. Should be a positive number.'))

        # Validate max_diff_length
        max_diff_length = change_summary_config.get('max_diff_length')
        if max_diff_length is not None and (not isinstance(max_diff_length, int) or max_diff_length <= 0):
            issues.append(('warning', f'Invalid max_diff_length: {max_diff_length}. Should be a positive integer.'))

        return issues

    def _validate_overview_config(self) -> List[Tuple[str, str]]:
        """Validate overview configuration"""
        issues = []
        overview_config = self.data.get('overview', {})

        # Validate language
        language = overview_config.get('language', 'ko')
        valid_languages = {'ko', 'en', 'ja', 'zh_CN'}
        if language not in valid_languages:
            issues.append(('warning', f'Invalid overview language: {language}. Valid options: {valid_languages}'))

        # Validate context plugins
        context_plugins = overview_config.get('context_plugins', {})
        for plugin_name, plugin_config in context_plugins.items():
            if not isinstance(plugin_config, dict):
                issues.append(('error', f'Invalid configuration for context plugin "{plugin_name}": must be a dictionary'))
                continue

            # Validate weather plugin specifically
            if plugin_name == 'weather' and plugin_config.get('enabled', False):
                if not plugin_config.get('latitude'):
                    issues.append(('warning', 'Weather plugin enabled but latitude is not set'))
                if not plugin_config.get('longitude'):
                    issues.append(('warning', 'Weather plugin enabled but longitude is not set'))
                if not plugin_config.get('city_name'):
                    issues.append(('info', 'Weather plugin: city_name not set, will use "the location"'))

        return issues
