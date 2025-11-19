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

"""Structured JSONL logger for overview generation."""

from __future__ import annotations

import logging
from datetime import date as date_type
from pathlib import Path
from typing import Dict, Optional

from ..llm import LLMClient
from ..utils.config import Config


class StructuredLogger:
    """Generate machine-readable JSONL logs alongside overview summaries."""

    # Default prompt template for structured log generation
    DEFAULT_OVERVIEW_PROMPT_TEMPLATE = """\
You are an automated research note management program for {lab_info}.

The following includes the summaries of all latest changes (of {summary_range}) to research notes.
Transform them into structured machine-readable logs that can be ingested by downstream databases.
Summaries must be concise, factual, and free of decorative or conversational language.
Never omit impactful updates, experiment outcomes, blockers, or next steps.
Favor active tense so responsibility for each action remains clear.
When describing an update, omit the subject if it would be identical to the author; the author list already captures that attribution.
{language_specific_instructions}

Structured output requirements:
1. Respond **only** with JSON Lines (JSONL). Each line must be a standalone valid JSON object encoded in UTF-8, no extra prose or Markdown fencing.
2. Every JSON object must contain **only** the following keys:
   - `"date"`: string formatted as `YYYY-MM-DD` (use the target summary date for every entry).
   - `"authors"`: array of canonical English names responsible for the change (empty array if unknown).
  - `"summary_en"`: Concise English sentence(s) capturing the key updates, risks, and next steps in active voice.
  {language_summary_key_instruction}
3. Produce one JSON object per thematic cluster or notable change. Ensure all significant updates are included.
4. Keep both summaries strictly factual and aligned in meaning. No additional fields, metadata objects, MVP notes, or decorative content are allowed.

{context_information}
{language_instruction}
"""

    DEFAULT_CONTEXT_INFORMATION_PREFIX = """\
Use the following context information minimally and reference it only when necessary for clarity.
"""

    # Language-specific instructions for overview generation
    LANGUAGE_INSTRUCTIONS = {
        'ko': {
            'language_specific_instructions': 'Use canonical English names for every person (see the team roster below). If a canonical name is missing, transliterate to the best English equivalent and mention that uncertainty in the Korean summary text.\nUse English terminology for technical biology phrases (genes, assays, reagents, instruments, etc.) even inside the Korean summary so downstream systems can link them reliably.',
            'language_summary_key_instruction': '- `"summary_ko"`: Korean translation conveying the same facts with similar brevity and active tone while keeping technical biology terms in English.',
            'language_instruction': '**Important** Provide both Korean and English summaries as described, but preserve canonical English names exactly as listed.',
        },
    }

    def __init__(self, config: Config, summary_dir: Path):
        settings = config.get('overview.jsonl_output', {}) or {}
        self.enabled = bool(settings.get('enabled', False))
        self.logger = logging.getLogger('Hedwig.overview.structured_logger')
        self.config = config
        self.summary_dir = summary_dir
        self.payload_dir = summary_dir / '_structured_logger'
        self.output_suffix = settings.get('file_suffix', '-summary.jsonl')
        self.language = config.get('overview.language', 'ko').lower()
        self.lab_info = config.get(
            'overview.lab_info',
            "Seoul National University's QBioLab, which studies molecular biology using bioinformatics methodologies"
        )
        self.context_info_prefix = self.DEFAULT_CONTEXT_INFORMATION_PREFIX

        if not self.enabled:
            return

        if self.language not in self.LANGUAGE_INSTRUCTIONS:
            raise ValueError(
                f"Unsupported language for update logger: {self.language}. "
                f"Supported languages: {', '.join(self.LANGUAGE_INSTRUCTIONS.keys())}"
            )

        self.lang_instructions = self.LANGUAGE_INSTRUCTIONS[self.language]
        self.prompt_template = self.config.get('api.llm.jsonl_prompt_template', self.DEFAULT_OVERVIEW_PROMPT_TEMPLATE)
        self.weekday_config = self.config.get('api.llm.overview_weekday_config', {})
        self.default_weekday_config = {
            'monday': {'summary_range': 'last weekend', 'forthcoming_range': 'this week'},
            'tuesday': {'summary_range': 'yesterday', 'forthcoming_range': 'today'},
            'wednesday': {'summary_range': 'yesterday', 'forthcoming_range': 'today'},
            'thursday': {'summary_range': 'yesterday', 'forthcoming_range': 'today'},
            'friday': {'summary_range': 'yesterday', 'forthcoming_range': 'today'},
            'saturday': {'summary_range': 'yesterday', 'forthcoming_range': 'next week'},
            'sunday': None
        }
        self.weekday_names = list(self.default_weekday_config.keys())

        self.client = LLMClient(self.config)
        self.model = self.config.get('api.llm.jsonl_output_model', self.config.get('api.llm.overview_model', 'gemini-2.5-pro'))

    def generate_structured_output(self, user_input: str, target_date: date_type) -> None:
        """Generate JSONL logs from aggregated change summaries."""
        if not self.enabled:
            return

        if not user_input or not user_input.strip():
            self.logger.debug("Structured logger skipped due to empty input.")
            return

        prompt = self._get_prompt_for_date(target_date)
        if not prompt:
            self.logger.info("Structured logger skipped: no prompt available for target date.")
            return

        self._write_payload_file('prompt', prompt, target_date)
        self._write_payload_file('input', user_input, target_date)

        try:
            output = self.client.generate(prompt=prompt, user_input=user_input, model=self.model)
        except Exception as exc:
            self.logger.error(f"Structured logger generation failed: {exc}")
            return

        cleaned = self._clean_jsonl_output(output)
        if not cleaned:
            self.logger.info("Structured logger returned empty structured output.")
            return

        output_path = self._structured_output_path(target_date)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not cleaned.endswith("\n"):
            cleaned += "\n"
        output_path.write_text(cleaned, encoding='utf-8')
        self.logger.info("Structured JSONL log written to %s", output_path)

    def _build_prompt_for_weekday(self, weekday: int) -> str:
        """Build the structured logger prompt for the specified weekday."""
        if weekday < 0 or weekday >= len(self.weekday_names):
            return ''

        day_name = self.weekday_names[weekday]
        default_config = self.default_weekday_config.get(day_name)

        if default_config is None:
            return ''

        day_config = self.weekday_config.get(day_name, default_config)
        context_info = self._get_static_context_information()

        full_config = {
            **day_config,
            **self.lang_instructions,
            'forthcoming_range': day_config.get('forthcoming_range', 'upcoming period'),
            'lab_info': self.lab_info,
            'context_information': context_info
        }

        return self.prompt_template.format(**full_config)

    def _get_static_context_information(self) -> str:
        """Return context block derived only from the static plugin configuration."""
        static_config = self.config.get('overview.context_plugins.static', {})
        if not isinstance(static_config, dict):
            return ''

        if not static_config.get('enabled'):
            return ''

        content = static_config.get('content', '').strip()
        if not content:
            return ''

        separator = "" if self.context_info_prefix.endswith("\n") else "\n"
        return f"{self.context_info_prefix}{separator}{content}"

    def _get_prompt_for_date(self, target_date: date_type) -> str:
        weekday = target_date.weekday()
        return self._build_prompt_for_weekday(weekday)

    def _write_payload_file(self, kind: str, content: str, target_date: date_type) -> None:
        if not content:
            return

        path = self.payload_dir / target_date.strftime('%Y') / target_date.strftime('%m')
        path.mkdir(parents=True, exist_ok=True)
        filename = f"{target_date.strftime('%Y%m%d')}-{kind}.md"
        file_path = path / filename
        file_path.write_text(content, encoding='utf-8')
        self.logger.debug("Structured logger wrote %s", file_path)

    def _structured_output_path(self, target_date: date_type) -> Path:
        base_dir = self.summary_dir / target_date.strftime('%Y') / target_date.strftime('%m')
        filename = f"{target_date.strftime('%Y%m%d')}{self.output_suffix}"
        return base_dir / filename

    def structured_output_path(self, target_date: date_type) -> Optional[Path]:
        """Expose the structured output path for freshness checks."""
        if not self.enabled:
            return None
        return self._structured_output_path(target_date)

    def _clean_jsonl_output(self, data: Optional[str]) -> str:
        """Strip code fences and preamble text from JSONL responses."""
        if not data:
            return ""

        cleaned_lines = []
        started = False

        for raw_line in data.splitlines():
            line = raw_line.strip()

            if not line and not started:
                continue

            if line.startswith("```"):
                continue

            if not started:
                if not line.startswith("{"):
                    continue
                started = True

            cleaned_lines.append(line)

        return "\n".join(cleaned_lines).strip()
