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

"""Pipeline module for running the complete briefing generation workflow"""

import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from .change_summary.generator import ChangeSummaryGenerator
from .overview.generator import OverviewGenerator
from .overview.external_content import ExternalContentManager
from .overview.structured_logger import StructuredLogger
from .messaging.manager import MessageManager
from .utils.config import Config
from .utils.logging import setup_logger
from .utils.timezone import TimezoneManager


class SummarizerPipeline:
    """Orchestrates the complete summarizer pipeline"""

    def __init__(self, config_path: Optional[str] = None, quiet: bool = False):
        """Initialize the summarizer pipeline

        Args:
            config_path: Path to configuration file
            quiet: Suppress informational messages
        """
        self.config = Config(config_path)
        self.quiet = quiet
        self.logger = setup_logger('Hedwig.pipeline', quiet=quiet)

        # Get summary output directory
        self.summary_dir = Path(self.config.get('paths.change_summary_output', '/path/to/change-summaries'))

        # Get pipeline configuration
        self.title_format = self.config.get('pipeline.title_format', 'QBio Research {date}')

    def _logical_today(self) -> datetime.date:
        """Return the logical 'today' anchored to global.logical_day_start."""
        now_local = TimezoneManager.now_local(self.config)
        logical_start = self.config.get('global.logical_day_start', 4)
        try:
            logical_hour = int(logical_start)
            if logical_hour < 0 or logical_hour > 23:
                logical_hour = 4
        except (TypeError, ValueError):
            logical_hour = 4

        boundary = now_local.replace(hour=logical_hour, minute=0, second=0, microsecond=0)
        if now_local < boundary:
            return (now_local.date() - datetime.timedelta(days=1))
        return now_local.date()

    def get_date_paths(self) -> Tuple[Path, Path, datetime.date]:
        """Get the date-based file paths for today

        Returns:
            Tuple of (individual_file, overview_file, today_date)
        """
        today = self._logical_today()
        year = today.strftime('%Y')
        month = today.strftime('%m')
        date_str = today.strftime('%Y%m%d')

        base_dir = self.summary_dir / year / month

        individual_file = base_dir / f"{date_str}-indiv.md"
        overview_file = base_dir / f"{date_str}-overview.md"

        return individual_file, overview_file, today

    def _load_external_content(self, target_date: datetime.date) -> Dict[str, str]:
        """Fetch external content for the target date if available."""
        try:
            manager = ExternalContentManager(self.config, self.summary_dir)
            return manager.fetch_all_content(target_date.strftime('%Y-%m-%d'))
        except Exception as exc:
            self.logger.error(f"Failed to load external content: {exc}")
            return {}

    def run(self, post_summary: bool = True) -> bool:
        """Run the complete summarizer pipeline

        Args:
            post_summary: Whether to post generated summaries to messaging platforms.

        Returns:
            True if successful, False otherwise
        """
        self.logger.info("Starting summarizer pipeline")

        try:
            # Get today's file paths
            individual_file, overview_file, today = self.get_date_paths()
            yesterday = today - datetime.timedelta(days=1)

            # Format title with yesterday's date
            title = self.title_format.format(date=yesterday.strftime('%Y-%m-%d'))

            self.logger.info(f"Expected individual file: {individual_file}")
            self.logger.info(f"Expected overview file: {overview_file}")

            # Step 1: Generate change summaries
            self.logger.info("=" * 60)
            self.logger.info("STEP 1: Generating individual change summaries")
            self.logger.info("=" * 60)

            try:
                change_generator = ChangeSummaryGenerator(self.config.config_path, quiet=self.quiet)
                summaries = change_generator.generate(write_to_file=True)

                if not summaries:
                    self.logger.warning("No summaries were generated")
                else:
                    self.logger.info(f"Generated {len(summaries)} summaries")

            except Exception as e:
                self.logger.error(f"Failed to generate change summaries: {e}")
                return False

            external_content = self._load_external_content(today)
            has_individual_summary = individual_file.exists()

            # If there is truly nothing to process, stop early without treating it as an error.
            if not has_individual_summary and not external_content:
                self.logger.info("No individual summaries or external content found for today. Stopping pipeline.")
                return True

            if not has_individual_summary and external_content:
                self.logger.info("No individual summaries generated, but external content exists. Continuing pipeline.")

            # Step 2: Generate structured daily summary log (if enabled)
            self.logger.info("=" * 60)
            self.logger.info("STEP 2: Generating structured daily summary log")
            self.logger.info("=" * 60)

            try:
                structured_logger = StructuredLogger(self.config.config_path, quiet=self.quiet)
                structured_output = structured_logger.generate(write_to_file=True, target_date=today)
                if structured_output:
                    self.logger.info("Structured JSONL log generated successfully.")
                else:
                    self.logger.info("Structured JSONL log generation skipped or produced no output.")

            except Exception as e:
                self.logger.error(f"Failed to generate structured daily summary log: {e}")
                return False

            # Step 3: Generate overview
            self.logger.info("=" * 60)
            self.logger.info("STEP 3: Generating overview summary")
            self.logger.info("=" * 60)

            try:
                overview_generator = OverviewGenerator(self.config.config_path, quiet=self.quiet)
                overview = overview_generator.generate(write_to_file=True, target_date=today)

                if not overview:
                    self.logger.warning("No overview was generated")

            except Exception as e:
                self.logger.error(f"Failed to generate overview: {e}")
                return False

            # Check if overview file was generated
            if not overview_file.exists():
                self.logger.info("No overview file generated (possibly Sunday or no content). Stopping pipeline.")
                return True  # This is not an error

            # Step 4: Post to messaging platform
            self.logger.info("=" * 60)
            self.logger.info("STEP 4: Posting to messaging platform")
            self.logger.info("=" * 60)

            if not post_summary:
                self.logger.info("Posting skipped because --no-posting was provided.")
            elif not individual_file.exists():
                self.logger.info("No individual summary file available for posting. Skipping messaging step.")
            else:
                try:
                    manager = MessageManager(self.config.config_path, quiet=self.quiet)

                    # Check if messaging is configured
                    if not manager.consumer_name:
                        self.logger.warning("No messaging platform configured. Skipping posting step.")
                        return True

                    self.logger.info("Posting with:")
                    self.logger.info(f"  summary-file: {individual_file}")
                    self.logger.info(f"  overview-file: {overview_file}")
                    self.logger.info(f"  title: {title}")

                    result = manager.post_summary(
                        markdown_file=str(individual_file),
                        message_file=str(overview_file),
                        title=title,
                        channel_override=None
                    )

                    if result.success:
                        self.logger.info(f"Successfully posted summary via {manager.consumer_name}")
                        if result.url:
                            self.logger.info(f"Summary URL: {result.url}")
                    else:
                        self.logger.error(f"Failed to post summary: {result.error}")
                        return False

                except Exception as e:
                    self.logger.error(f"Failed to post summary: {e}")
                    return False

            # Success
            self.logger.info("=" * 60)
            self.logger.info("ALL STEPS COMPLETED SUCCESSFULLY")
            self.logger.info("=" * 60)
            self.logger.info("Summarizer pipeline finished successfully!")
            return True

        except KeyboardInterrupt:
            self.logger.info("Process interrupted by user")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error in pipeline: {e}")
            return False
