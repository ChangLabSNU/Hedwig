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

"""Main overview generation module for creating overview summaries"""

from datetime import date as date_type
import re
from pathlib import Path
from typing import Optional, Dict

from ..utils.timezone import TimezoneManager
from .base import OverviewBase
from .context_plugins import ContextPluginRegistry


class OverviewGenerator(OverviewBase):
    """Generate overview summaries from individual change summaries"""

    # Default prompt template for overview generation
    DEFAULT_OVERVIEW_PROMPT_TEMPLATE = """\
You are an automated research note management program for {lab_info}.

The following includes the summaries of all latest changes (of {summary_range}) to research notes.
Write a brief overview summary of the changes in a bullet-point format, focusing on the most significant changes and their implications for the research.
Group similar changes together and highlight the most important updates.
Attribute the authors of the changes to the summaries unless the changes are just simple edits or formatting changes.
{language_specific_instructions}
Always put spaces around the Markdown bold syntax with asterisks to ensure proper rendering in Markdown.
Give some witty decorative words to the title.
Pick the single most valuable player (MVP) of the day based on the changes, and summarize their contributions in a single line at the end of the summary.
Add a playful and humorous conclusion sentence including emojis to the summary that cheers up the team that looking forward to {forthcoming_range}'s research.
Give the MVP announcement and conclusion sentence in a first-person perspective as if you are the author of the summary. {author_name_instruction}
When choosing the MVP, consider the impact in terms of biological significance and overall contribution to the research goals rather than simply writing complex notes.

{context_information}
{language_instruction}
"""

    DEFAULT_CONTEXT_INFORMATION_PREFIX = """\
Use the following context information minimally only at the appropriate places in the summary, and do not repeat the context information verbatim.
"""

    # Language-specific instructions for overview generation
    LANGUAGE_INSTRUCTIONS = {
        'ko': {
            'language_specific_instructions': 'Use the Korean suffix " 님"(including a preceding space) to author names when mentioning them, you can\'t use other suffixes.',
            'author_name_instruction': 'Your name is "큐비".',
            'language_instruction': '**Important** Always respond in Korean, regardless of the language of the input research notes or primary summary content.'
        },
        'en': {
            'language_specific_instructions': 'Use professional but friendly language when referring to authors.',
            'author_name_instruction': 'Your name is "Hedwig".',
            'language_instruction': '**Important** Always respond in English.'
        },
        'ja': {
            'language_specific_instructions': 'Use the Japanese suffix "さん" when referring to authors in a respectful manner.',
            'author_name_instruction': 'Your name is "ヘドウィグ".',
            'language_instruction': '**Important** Always respond in Japanese.'
        },
        'zh_CN': {
            'language_specific_instructions': 'Use appropriate honorifics when referring to authors (e.g., 老师 for senior researchers).',
            'author_name_instruction': 'Your name is "海德薇".',
            'language_instruction': '**Important** Always respond in Chinese (Simplified).'
        }
    }

    def __init__(self, config_path: Optional[str] = None, quiet: bool = False):
        """Initialize overview generator

        Args:
            config_path: Path to configuration file
            quiet: Suppress informational messages
        """
        super().__init__(
            config_path=config_path,
            quiet=quiet,
            logger_name='Hedwig.overview.generator',
            language_instructions=self.LANGUAGE_INSTRUCTIONS,
            context_prefix_config_key='api.llm.overview_context_information_prefix',
            default_context_prefix=self.DEFAULT_CONTEXT_INFORMATION_PREFIX
        )

        # Get model configuration
        self.model = self.config.get('api.llm.overview_model', 'gemini-2.5-pro')

        # Initialize context plugins
        self._initialize_context_plugins()

        # Prompt configuration (built lazily)
        self.prompt_template = self.config.get('api.llm.overview_prompt_template', self.DEFAULT_OVERVIEW_PROMPT_TEMPLATE)

    def _initialize_context_plugins(self):
        """Initialize context plugins from configuration"""
        # Import plugins to ensure they're registered
        from .context_plugins import weather  # noqa: F401
        from .context_plugins import calendar  # noqa: F401
        from .context_plugins import static  # noqa: F401
        from .context_plugins import date  # noqa: F401

        # Get context plugins configuration
        context_config = self.config.get('overview.context_plugins', {})

        # Add timezone to each plugin's config
        global_timezone = self.config.get('global.timezone', 'UTC')
        for plugin_name, plugin_config in context_config.items():
            if isinstance(plugin_config, dict) and 'timezone' not in plugin_config:
                plugin_config['timezone'] = global_timezone

        # Create plugin instances
        self.context_plugins = ContextPluginRegistry.create_plugins(
            context_config,
            logger=self.logger
        )

        if self.context_plugins:
            self.logger.info(f"Loaded {len(self.context_plugins)} context plugin(s)")

    def _get_context_information(self) -> str:
        """Gather context information from all enabled plugins

        Returns:
            Combined context string
        """
        if not self.context_plugins:
            return ""

        context_parts = []

        for plugin in self.context_plugins:
            try:
                context = plugin.get_context()
                if context:
                    context_parts.append(context)
            except Exception as e:
                self.logger.error(f"Error getting context from plugin '{plugin.name}': {e}")

        if not context_parts:
            return ""

        # Combine all context parts with double newlines
        return self.context_info_prefix + "\n\n".join(context_parts)

    def _build_prompt_for_weekday(self, weekday: int) -> str:
        """Construct the prompt for a given weekday using current context."""
        if weekday < 0 or weekday >= len(self.weekday_names):
            return ''

        day_name = self.weekday_names[weekday]
        default_config = self.default_weekday_config.get(day_name)

        if default_config is None:
            return ''

        day_config = self.weekday_config.get(day_name, default_config)
        context_info = self._get_context_information()

        full_config = {
            **day_config,
            **self.lang_instructions,
            'lab_info': self.lab_info,
            'context_information': context_info
        }

        return self.prompt_template.format(**full_config)

    def _prepare_llm_input(self, target_date: date_type) -> Optional[Dict[str, str]]:
        """Prepare the LLM input by gathering summaries and external content

        Args:
            target_date: Date being processed

        Returns:
            Dictionary with 'prompt' and 'user_input' keys, or None if no data available
        """
        full_input = self._get_llm_user_input(target_date)
        if not full_input:
            return None

        # Get the appropriate prompt for today
        current_weekday = TimezoneManager.get_local_weekday(self.config)
        selected_prompt = self._build_prompt_for_weekday(current_weekday)

        if not selected_prompt:
            # Sunday - no summary
            self.logger.info("No overview generated on Sunday")
            return None

        return {
            'prompt': selected_prompt,
            'user_input': full_input
        }

    def get_prompt_for_debugging(self, target_date: Optional[date_type] = None) -> Optional[Dict[str, str]]:
        """Get the prompt/input that would be sent to the LLM for debugging purposes"""
        resolved_date = self._resolve_target_date(target_date)

        # Use the common method to prepare LLM input
        return self._prepare_llm_input(resolved_date)

    def get_up_to_date_overview_path(self, target_date: Optional[date_type] = None) -> Optional[Path]:
        """Return the overview path for the target date if it's newer than its inputs."""
        resolved_date = self._resolve_target_date(target_date)
        date_str_for_file = resolved_date.strftime('%Y%m%d')
        base_dir = self._get_base_dir_for_date(resolved_date)
        overview_path = base_dir / f'{date_str_for_file}-overview.md'

        if not overview_path.exists():
            return None

        source_files = self._get_source_files(resolved_date)
        if not source_files:
            return None

        latest_source_mtime = max(path.stat().st_mtime for path in source_files)
        overview_mtime = overview_path.stat().st_mtime

        if overview_mtime < latest_source_mtime:
            return None

        return overview_path

    def generate(
        self,
        write_to_file: bool = True,
        target_date: Optional[date_type] = None
    ) -> Optional[str]:
        """Generate overview from individual summaries for a given date

        Args:
            write_to_file: Whether to write overview to file
            target_date: Optional date to process instead of today

        Returns:
            Generated overview text or None if no summaries found
        """
        self.logger.info("Starting overview generation...")

        # Determine which date we are generating for
        resolved_date = self._resolve_target_date(target_date)

        # Prepare LLM input using the common method
        llm_input = self._prepare_llm_input(resolved_date)

        if not llm_input:
            # Error already logged in _prepare_llm_input
            return None

        # Generate overview summary
        self.logger.info("Generating overview summary...")

        try:
            self.logger.info("Submitting overview prompt to LLM model '%s'", self.model)
            overview = self.llm_client.generate(
                prompt=llm_input['prompt'],
                user_input=llm_input['user_input'],
                model=self.model
            )
            self.logger.info("Overview summary generated successfully")

        except Exception as e:
            self.logger.error(f"Error generating overview summary: {e}")
            return None

        if not overview:
            self.logger.info("Overview summary is empty. Nothing to write.")
            return None

        overview = self._sanitize_overview(overview)

        if not overview:
            self.logger.info("Overview summary is empty after sanitization. Nothing to write.")
            return None

        # Write overview file
        if write_to_file:
            self._write_overview_to_file(overview, resolved_date)

        return overview

    def _write_overview_to_file(self, overview: str, target_date: date_type) -> str:
        """Write overview to structured file path

        Args:
            overview: Overview text
            target_date: Date associated with this overview

        Returns:
            Path to written file
        """
        year = target_date.strftime('%Y')
        month = target_date.strftime('%m')
        date_str_for_file = target_date.strftime('%Y%m%d')

        # Create directory structure
        output_dir = self.summary_dir / year / month
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create filename
        filename = f'{date_str_for_file}-overview.md'
        filepath = output_dir / filename

        # Write overview to file
        try:
            filepath.write_text(overview, encoding='utf-8')
            self.logger.info(f"Overview summary written to: {filepath}")
            return str(filepath)

        except Exception as e:
            self.logger.error(f"Error writing overview file: {e}")
            raise

    def _sanitize_overview(self, overview: str) -> str:
        """Normalize overview text by dropping stray code fences."""
        text = overview.strip()
        text = re.sub(r"```[^\n]*\n", "", text)
        text = text.replace("```", "")
        return text.strip()
