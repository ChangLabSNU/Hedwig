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

from pathlib import Path
from typing import Optional

from ..utils.config import Config
from ..utils.logging import setup_logger
from ..utils.timezone import TimezoneManager
from ..llm import LLMClient
from .context_plugins import ContextPluginRegistry


class OverviewGenerator:
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
        self.config = Config(config_path)
        self.quiet = quiet
        self.logger = setup_logger('Hedwig.overview.generator', quiet=quiet)

        # Initialize LLM client
        self.llm_client = LLMClient(self.config)

        # Get configuration
        self.summary_dir = Path(self.config.get('paths.change_summary_output', '/path/to/change-summaries'))

        # Get model configuration
        self.model = self.config.get('api.llm.overview_model', 'gemini-2.5-pro')

        # Language configuration
        self.language = self.config.get('overview.language', 'ko').lower()
        if self.language not in self.LANGUAGE_INSTRUCTIONS:
            raise ValueError(f"Unsupported language: {self.language}. Supported languages: {', '.join(self.LANGUAGE_INSTRUCTIONS.keys())}")

        # Lab information configuration
        self.lab_info = self.config.get('overview.lab_info',
                                  "Seoul National University's QBioLab, which studies molecular biology using bioinformatics methodologies")

        # Context information prefix configuration
        self.context_info_prefix = self.config.get('api.llm.overview_context_information_prefix',
                                                   self.DEFAULT_CONTEXT_INFORMATION_PREFIX)

        # Initialize context plugins
        self._initialize_context_plugins()

        # Load prompts
        self._load_prompts()

    def _initialize_context_plugins(self):
        """Initialize context plugins from configuration"""
        # Import plugins to ensure they're registered
        from .context_plugins import weather  # noqa: F401
        from .context_plugins import calendar  # noqa: F401
        from .context_plugins import static  # noqa: F401

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

    def _load_prompts(self):
        """Load prompts from configuration or use defaults"""
        # Get language-specific instructions
        lang_instructions = self.LANGUAGE_INSTRUCTIONS[self.language]

        # Check if custom prompt template is configured
        custom_template = self.config.get('api.llm.overview_prompt_template')

        # Default weekday configurations
        default_weekday_config = {
            'monday': {'summary_range': 'last weekend', 'forthcoming_range': 'this week'},
            'tuesday': {'summary_range': 'yesterday', 'forthcoming_range': 'today'},
            'wednesday': {'summary_range': 'yesterday', 'forthcoming_range': 'today'},
            'thursday': {'summary_range': 'yesterday', 'forthcoming_range': 'today'},
            'friday': {'summary_range': 'yesterday', 'forthcoming_range': 'today'},
            'saturday': {'summary_range': 'yesterday', 'forthcoming_range': 'next week'},
            'sunday': None  # No summary on Sunday
        }

        # Get weekday-specific configurations
        weekday_config = self.config.get('api.llm.overview_weekday_config', {})

        # Build prompts for each weekday
        self.prompts = {}
        template = custom_template if custom_template else self.DEFAULT_OVERVIEW_PROMPT_TEMPLATE

        for day, default_config in default_weekday_config.items():
            day_index = list(default_weekday_config.keys()).index(day)

            if default_config is None:
                self.prompts[day_index] = ''
            else:
                # Merge configurations
                day_config = weekday_config.get(day, default_config)
                # Get context information
                context_info = self._get_context_information()
                # Add language-specific instructions, lab info, and context to the configuration
                full_config = {
                    **day_config,
                    **lang_instructions,
                    'lab_info': self.lab_info,
                    'context_information': context_info
                }
                self.prompts[day_index] = template.format(**full_config)

    def generate(self, write_to_file: bool = True) -> Optional[str]:
        """Generate overview from today's individual summaries

        Args:
            write_to_file: Whether to write overview to file

        Returns:
            Generated overview text or None if no summaries found
        """
        self.logger.info("Starting overview generation...")

        now = TimezoneManager.now_local(self.config)
        year = now.strftime('%Y')
        month = now.strftime('%m')
        date_str = now.strftime('%Y%m%d')

        # Check for individual summary file
        indiv_filename = f'{date_str}-indiv.md'
        indiv_filepath = self.summary_dir / year / month / indiv_filename

        self.logger.info(f"Checking for individual summary file: {indiv_filepath}")

        if not indiv_filepath.exists():
            self.logger.info("Individual summary file does not exist. Nothing to process.")
            return None

        # Read individual summaries
        try:
            content = indiv_filepath.read_text(encoding='utf-8').strip()

            if not content:
                self.logger.info("Individual summary file is empty. Nothing to process.")
                return None

            self.logger.info(f"Found individual summary file with {len(content)} characters")

        except Exception as e:
            self.logger.error(f"Error reading individual summary file: {e}")
            return None

        # Generate overview summary
        self.logger.info("Generating overview summary...")

        # Get the appropriate prompt for today
        current_weekday = TimezoneManager.get_local_weekday(self.config)
        selected_prompt = self.prompts[current_weekday]

        if not selected_prompt:
            # Sunday - no summary
            self.logger.info("No overview generated on Sunday")
            return None

        try:
            overview = self.llm_client.generate(
                prompt=selected_prompt,
                user_input=content,
                model=self.model
            )
            self.logger.info("Overview summary generated successfully")

        except Exception as e:
            self.logger.error(f"Error generating overview summary: {e}")
            return None

        if not overview:
            self.logger.info("Overview summary is empty. Nothing to write.")
            return None

        # Write overview file
        if write_to_file:
            self._write_overview_to_file(overview, date_str)

        return overview

    def _write_overview_to_file(self, overview: str, date_str: str) -> str:
        """Write overview to structured file path

        Args:
            overview: Overview text
            date_str: Date string in YYYYMMDD format

        Returns:
            Path to written file
        """
        now = TimezoneManager.now_local(self.config)
        year = now.strftime('%Y')
        month = now.strftime('%m')

        # Create directory structure
        output_dir = self.summary_dir / year / month
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create filename
        filename = f'{date_str}-overview.md'
        filepath = output_dir / filename

        # Write overview to file
        try:
            filepath.write_text(overview, encoding='utf-8')
            self.logger.info(f"Overview summary written to: {filepath}")
            return str(filepath)

        except Exception as e:
            self.logger.error(f"Error writing overview file: {e}")
            raise
