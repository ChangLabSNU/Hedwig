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

"""Common helpers shared between overview-related generators."""

from __future__ import annotations

from copy import deepcopy
from datetime import date as date_type, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..llm import LLMClient
from ..utils.config import Config
from ..utils.logging import setup_logger
from ..utils.timezone import TimezoneManager
from .external_content import ExternalContentManager


class OverviewBase:
    """Base class that provides config, logging, and content helpers."""

    DEFAULT_LAB_INTRO = (
        "Seoul National University's QBioLab, which studies molecular biology using "
        "bioinformatics methodologies"
    )

    DEFAULT_WEEKDAY_CONFIG = {
        'monday': {'summary_range': 'last weekend', 'forthcoming_range': 'this week'},
        'tuesday': {'summary_range': 'yesterday', 'forthcoming_range': 'today'},
        'wednesday': {'summary_range': 'yesterday', 'forthcoming_range': 'today'},
        'thursday': {'summary_range': 'yesterday', 'forthcoming_range': 'today'},
        'friday': {'summary_range': 'yesterday', 'forthcoming_range': 'today'},
        'saturday': {'summary_range': 'yesterday', 'forthcoming_range': 'next week'},
        'sunday': None
    }

    def __init__(
        self,
        config_path: Optional[str] = None,
        quiet: bool = False,
        logger_name: str = 'Hedwig.overview.base',
        language_instructions: Optional[Dict[str, Dict[str, Any]]] = None,
        context_prefix_config_key: Optional[str] = None,
        default_context_prefix: Optional[str] = None
    ):
        self.config = Config(config_path)
        self.quiet = quiet
        self.logger = setup_logger(logger_name, quiet=quiet)
        self.summary_dir = Path(self.config.get('paths.change_summary_output', '/path/to/change-summaries'))
        self.external_content_manager = ExternalContentManager(self.config, self.summary_dir)
        self.llm_client = LLMClient(self.config)

        self.language = self.config.get('overview.language', 'ko').lower()
        self.lang_instructions: Dict[str, Any] = {}
        if language_instructions:
            if self.language not in language_instructions:
                raise ValueError(
                    f"Unsupported language for overview outputs: {self.language}. "
                    f"Supported languages: {', '.join(language_instructions.keys())}"
                )
            self.lang_instructions = language_instructions[self.language]

        self.lab_intro = self.config.get('static_context.lab_intro', self.DEFAULT_LAB_INTRO)

        context_default = default_context_prefix or ""
        if context_prefix_config_key:
            self.context_info_prefix = self.config.get(
                context_prefix_config_key,
                context_default
            )
        else:
            self.context_info_prefix = context_default

        self.weekday_config = self.config.get('api.llm.overview_weekday_config', {})
        self.default_weekday_config = deepcopy(self.DEFAULT_WEEKDAY_CONFIG)
        self.weekday_names = list(self.default_weekday_config.keys())

    def _resolve_target_date(self, target_date: Optional[date_type]) -> date_type:
        """Return the provided date or the logical day anchored to configured start."""
        if target_date:
            return target_date

        now_local = TimezoneManager.now_local(self.config)
        logical_start = self.config.get('global.logical_day_start', 4)
        try:
            logical_hour = int(logical_start)
            if logical_hour < 0 or logical_hour > 23:
                logical_hour = 4
        except (TypeError, ValueError):
            logical_hour = 4

        logical_boundary = now_local.replace(
            hour=logical_hour,
            minute=0,
            second=0,
            microsecond=0
        )

        if now_local < logical_boundary:
            return (now_local - timedelta(days=1)).date()

        return now_local.date()

    def _get_base_dir_for_date(self, target_date: date_type) -> Path:
        """Return YYYY/MM directory for the given date."""
        year = target_date.strftime('%Y')
        month = target_date.strftime('%m')
        return self.summary_dir / year / month

    def _get_individual_summary_path(self, target_date: date_type) -> Path:
        """Return the individual summary path for the target date."""
        date_str_for_file = target_date.strftime('%Y%m%d')
        return self._get_base_dir_for_date(target_date) / f'{date_str_for_file}-indiv.md'

    def _get_source_files(self, target_date: date_type) -> Optional[List[Path]]:
        """Return the list of files that feed into downstream overview outputs."""
        indiv_filepath = self._get_individual_summary_path(target_date)
        source_files: List[Path] = []
        if indiv_filepath.exists():
            source_files.append(indiv_filepath)

        if self.external_content_manager and self.external_content_manager.sources:
            date_str_for_file = target_date.strftime('%Y%m%d')
            base_dir = self._get_base_dir_for_date(target_date)
            for source in self.external_content_manager.sources:
                suffix = source.get('file_suffix')
                if not suffix:
                    continue

                candidate = base_dir / f'{date_str_for_file}{suffix}'
                if candidate.exists():
                    source_files.append(candidate)
                elif source.get('required', False):
                    return None

        if not source_files:
            return None

        return source_files

    def _get_llm_user_input(self, target_date: date_type) -> Optional[str]:
        """Return the concatenated individual summary and external content."""
        indiv_filepath = self._get_individual_summary_path(target_date)
        self.logger.info(f"Checking for individual summary file: {indiv_filepath}")

        content = ""
        if indiv_filepath.exists():
            try:
                content = indiv_filepath.read_text(encoding='utf-8').strip()

                if content:
                    self.logger.info(f"Found individual summary file with {len(content)} characters")
                else:
                    self.logger.info("Individual summary file is empty.")

            except Exception as exc:
                self.logger.error(f"Error reading individual summary file: {exc}")
        else:
            self.logger.info("Individual summary file does not exist.")

        self.logger.info("Checking for external content sources...")
        external_content = self.external_content_manager.fetch_all_content(
            target_date.strftime('%Y-%m-%d')
        )

        full_input = content
        formatted_external = ""

        if external_content:
            self.logger.info(f"Found external content from {len(external_content)} source(s)")
            formatted_external = self.external_content_manager.format_content_for_prompt(external_content)
            if not full_input:
                formatted_external = formatted_external.lstrip("\n")
            full_input = (full_input + "\n\n" if full_input else "") + formatted_external
        else:
            self.logger.info("No external content found.")

        if not full_input:
            self.logger.info("No summary content or external content available. Nothing to process.")
            return None

        return full_input
