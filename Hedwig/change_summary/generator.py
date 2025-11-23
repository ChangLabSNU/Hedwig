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

"""Main change summary generation module"""

from typing import List, Optional, Dict, Tuple
from pathlib import Path
import os
import pandas as pd
from datetime import datetime, timedelta

from ..utils.config import Config
from ..utils.logging import setup_logger
from ..utils.timezone import TimezoneManager
from ..llm import LLMClient
from .diff_analyzer import DiffAnalyzer


class ChangeSummaryGenerator:
    """Generate change summaries for research note changes"""

    # Default metadata format template
    METAINFO_FORMAT = """\
- Title: {Title}
- Path: {Page Location}
- Editors: {Editors}
"""

    # Default prompt for diff summarization
    DEFAULT_DIFF_SUMMARY_PROMPT = """\
You are an automated research note management program for Seoul National University's QBioLab, which studies molecular biology using bioinformatics methodologies.

The following shows recent changes to a specific page of research notes in Markdown format as a unified diff.

Please analyze the classification of changes, project name, and major change details. Summarize the content and organize it in the following Markdown format.
For the changes that are only formatting, simple edits, or metadata-only updates, classify them as "minor" clearly.
Format the summary as follows:

- Subject: (Estimated one-line topic of the page, written to the extent that it can be estimated)
- Classification: (Considering the amount and nature of changes, a comprehensive classification that reflects the nature such as "minor", "idea", "protocol", "experiment", "analysis", "composite", etc.)
- Major Details:
  - (Briefly summarize the modifications and their intentions in a 4-line list so that others can understand at a glance what content has been changed; only reference existing content and include only added, deleted, or changed content)
  - (2nd item)
  - (3rd item)
  - (4th item)

**Important** Always respond in English, regardless of the language of the input research notes or diff content.
"""

    def __init__(self, config_path: Optional[str] = None, quiet: bool = False):
        """Initialize change summary generator

        Args:
            config_path: Path to configuration file
            quiet: Suppress informational messages
        """
        self.config = Config(config_path)
        self.quiet = quiet
        self.logger = setup_logger('Hedwig.change_summary.generator', quiet=quiet)

        # Load user lookup table
        self.user_lookup = self._load_user_lookup()
        self.auto_sync_userlist = self.config.get('change_summary.auto_sync_userlist', True)
        self.has_synced = False  # Track if we've already synced in this session

        # Initialize components
        self.llm_client = LLMClient(self.config)
        self.diff_analyzer = DiffAnalyzer(
            repo_path=self.config.get('paths.notes_repository', '/path/to/noterepo'),
            quiet=quiet,
            user_lookup=self.user_lookup,
            unknown_user_callback=self._handle_unknown_user
        )

        # Get configuration
        self.summary_dir = Path(self.config.get('paths.change_summary_output', '/path/to/change-summaries'))
        self.max_diff_length = self.config.get('change_summary.max_diff_length', 12800)

        # Get model configuration
        self.model = self.config.get('api.llm.diff_summarization_model', 'gemini-2.5-flash')

        # Get prompt configuration
        self.prompt = self.config.get('api.llm.diff_summary_prompt', self.DEFAULT_DIFF_SUMMARY_PROMPT)

    def _get_logical_day_start_hour(self) -> int:
        """Return the configured logical day start hour (0-23)."""
        value = self.config.get('change_summary.logical_day_start', 4)
        try:
            hour = int(value)
            if 0 <= hour < 24:
                return hour
            self.logger.warning("Invalid logical_day_start '%s'; falling back to 4.", value)
        except (TypeError, ValueError):
            self.logger.warning("Unable to parse logical_day_start '%s'; falling back to 4.", value)
        return 4

    def _determine_time_window(self) -> Tuple[datetime, datetime, datetime, datetime]:
        """Compute the 24h window anchored to the configured logical day start."""
        now_local = TimezoneManager.now_local(self.config)
        logical_start_hour = self._get_logical_day_start_hour()

        window_end_local = now_local.replace(
            hour=logical_start_hour,
            minute=0,
            second=0,
            microsecond=0
        )

        # If we've passed today's logical start, anchor to it; otherwise use yesterday's
        if now_local < window_end_local:
            window_end_local -= timedelta(days=1)

        window_start_local = window_end_local - timedelta(hours=24)

        window_start_utc = TimezoneManager.to_utc(window_start_local)
        window_end_utc = TimezoneManager.to_utc(window_end_local)

        return window_start_local, window_end_local, window_start_utc, window_end_utc

    def _load_user_lookup(self) -> Dict[str, str]:
        """Load user lookup table from TSV file

        Returns:
            Dictionary mapping user IDs to names
        """
        userlist_file = self.config.get('paths.userlist_file')
        if not userlist_file or not os.path.exists(userlist_file):
            self.logger.warning(f"User list file not found: {userlist_file}")
            return {}

        try:
            # Read the TSV file
            df = pd.read_csv(userlist_file, sep='\t', dtype=str)

            # Create lookup dictionary
            if 'user_id' in df.columns and 'name' in df.columns:
                user_lookup = df.set_index('user_id')['name'].to_dict()
                self.logger.info(f"Loaded {len(user_lookup)} users from {userlist_file}")
                return user_lookup
            else:
                self.logger.warning(f"User list file missing required columns: {userlist_file}")
                return {}
        except Exception as e:
            self.logger.error(f"Error loading user list: {e}")
            return {}

    def _handle_unknown_user(self, user_id: str) -> Optional[str]:
        """Handle unknown user ID by syncing user list once

        Args:
            user_id: User ID not found in lookup table

        Returns:
            User name if found after sync, None otherwise
        """
        # Only sync once per session
        if not self.auto_sync_userlist or self.has_synced:
            return None

        # Check if this user is already in our lookup (might have been loaded after previous metadata extraction)
        if user_id in self.user_lookup:
            return self.user_lookup[user_id]

        self.logger.info(f"Unknown user ID '{user_id}' found, syncing user list...")
        self.has_synced = True

        try:
            # Sync and reload user list
            from ..notion.sync import NotionSyncer
            syncer = NotionSyncer(config_path=self.config.config_path)
            syncer.sync_userlist(quiet=True)

            # Reload the user lookup table
            new_lookup = self._load_user_lookup()
            if new_lookup:
                self.user_lookup = new_lookup
                self.diff_analyzer.user_lookup = new_lookup

                if user_id in new_lookup:
                    self.logger.info(f"User '{user_id}' found after sync: {new_lookup[user_id]}")
                    return new_lookup[user_id]
                else:
                    self.logger.warning(f"User '{user_id}' still not found after sync")
        except Exception as e:
            self.logger.error(f"Failed to sync user list: {e}")

        return None


    def _process_single_diff(
        self,
        diff: str,
        index: int,
        time_window: Optional[Tuple[datetime, datetime]] = None
    ) -> Optional[str]:
        """Process a single diff and generate summary

        Args:
            diff: The diff content
            index: The index of the diff (for logging)
            max_age_seconds: Maximum age for editor tracking

        Returns:
            Formatted summary or None if processing failed
        """
        try:
            # Extract metadata
            metadata = self.diff_analyzer.extract_metadata(diff, time_window=time_window)
            self.logger.info(f'Processing note {metadata["Title"]} in {metadata.get("Page Location", "unknown")}...')

            # Generate summary
            diff_text = diff[:self.max_diff_length] if len(diff) > self.max_diff_length else diff
            summary = self.llm_client.generate(
                prompt=self.prompt,
                user_input=diff_text,
                model=self.model
            )

            # Format with metadata
            meta_formatted = self.METAINFO_FORMAT.format(**metadata)
            full_summary = meta_formatted + summary

            return full_summary

        except Exception as e:
            self.logger.error(f"Error processing diff {index}: {e}")
            return None

    def _process_diffs(
        self,
        diffs: List[str],
        time_window: Optional[Tuple[datetime, datetime]] = None
    ) -> List[str]:
        """Process a list of diffs and generate summaries

        Args:
            diffs: List of diff contents
            max_age_seconds: Maximum age for editor tracking

        Returns:
            List of generated summaries
        """
        summaries = []
        for i, diff in enumerate(diffs):
            summary = self._process_single_diff(diff, i, time_window=time_window)
            if summary:
                summaries.append(summary)
        return summaries

    def generate(self, write_to_file: bool = True) -> List[str]:
        """Generate summaries for recent changes

        Args:
            write_to_file: Whether to write summaries to file

        Returns:
            List of generated summaries
        """
        self.logger.info("Starting summary generation...")

        window_start_local, window_end_local, window_start_utc, window_end_utc = self._determine_time_window()
        self.logger.info(
            "Processing window: %s to %s (24h fixed)",
            window_start_local.strftime('%Y-%m-%d %H:%M %Z'),
            window_end_local.strftime('%Y-%m-%d %H:%M %Z')
        )

        diffs = self.diff_analyzer.get_diffs_between(window_start_utc, window_end_utc)

        if not diffs:
            self.logger.info("No recent commits to process.")
            return []

        self.logger.info(f"Found {len(diffs)} diffs to process")

        # Process diffs
        summaries = self._process_diffs(diffs, time_window=(window_start_utc, window_end_utc))
        self.logger.info(f"Generated {len(summaries)} summaries")

        # Write summaries to file
        if summaries and write_to_file:
            self._write_summaries_to_file(summaries, window_end_local)

        return summaries

    def _write_summaries_to_file(self, summaries: List[str], window_end_local: datetime) -> str:
        """Write summaries to structured file path

        Args:
            summaries: List of summary texts
            window_end_local: End of the processed window in local time

        Returns:
            Path to written file
        """
        year = window_end_local.strftime('%Y')
        month = window_end_local.strftime('%m')
        date_str = window_end_local.strftime('%Y%m%d')

        # Create directory structure
        output_dir = self.summary_dir / year / month
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create filename
        filename = f'{date_str}-indiv.md'
        filepath = output_dir / filename

        # Write summaries to file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# Daily Summary - {date_str}\n\n")
            f.write(f"Generated on: {window_end_local.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n")

            non_minor_count = 0
            for i, summary in enumerate(summaries):
                # Skip minor changes
                if '\n- Classification: minor' in summary:
                    self.logger.info(f"Skipping minor summary {i + 1}")
                    continue

                if non_minor_count > 0:
                    f.write("\n---\n\n")

                # Extract subject from summary
                subject_title = self._extract_subject(summary, i + 1)

                # Remove the Subject line from summary to avoid duplication
                filtered_summary = self._remove_subject_line(summary)

                f.write(f"## {subject_title}\n\n")
                f.write(filtered_summary)
                f.write("\n")

                non_minor_count += 1

        self.logger.info(f"Summaries written to: {filepath}")
        return str(filepath)

    def _extract_subject(self, summary: str, index: int) -> str:
        """Extract subject from summary text

        Args:
            summary: Summary text
            index: Summary index (for fallback)

        Returns:
            Subject title
        """
        lines = summary.split('\n')
        for line in lines:
            if line.strip().startswith('- Subject:'):
                return line.strip()[10:].strip()  # Remove "- Subject: " prefix
        return f"Summary {index}"  # Fallback

    def _remove_subject_line(self, summary: str) -> str:
        """Remove subject line from summary to avoid duplication

        Args:
            summary: Summary text

        Returns:
            Summary without subject line
        """
        lines = summary.split('\n')
        filtered_lines = [line for line in lines if not line.strip().startswith('- Subject:')]
        return '\n'.join(filtered_lines)
