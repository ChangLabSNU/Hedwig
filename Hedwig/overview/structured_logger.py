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

import json
from datetime import date as date_type
from pathlib import Path
from typing import Dict, Optional

from .base import OverviewBase


class StructuredLogger(OverviewBase):
    """Generate machine-readable JSONL logs alongside overview summaries."""

    # Default prompt template for structured log generation
    DEFAULT_OVERVIEW_PROMPT_TEMPLATE = """\
You are an automated research note management program for {lab_intro}.

The following includes the summaries of all latest changes to research notes.
Transform them into structured machine-readable logs that can be ingested by downstream databases.
Summaries must be concise, factual, and free of decorative or conversational language.
Never omit impactful updates, experiment outcomes, blockers, or next steps.
Favor active tense so responsibility for each action remains clear.
When describing an update, omit the subject if it would be identical to the author; the author list already captures that attribution.
{language_specific_instructions}

Structured output requirements:
1. Respond **only** with JSON Lines (JSONL). Each line must be a standalone valid JSON object encoded in UTF-8, no extra prose or Markdown fencing.
2. Every JSON object must contain **only** the following keys:
   - `"authors"`: array of canonical English names responsible for the change (empty array if unknown).
   - `"source"`: array of strings identifying the origins of the update. For research note entries, read the `Document ID: <MMDD-n>` bullet and emit `notion:<MMDD-n>`. For Slack inputs, use `slack:` plus the nearest preceding level-3 heading (channel name). For GitLab inputs, use `gitlab:` plus the nearest preceding level-3 heading (project name). Never emit raw UUID values. If no source is available, use `["unknown"]`.
   - `"summary_en"`: Concise English sentence(s) capturing the key updates, risks, and next steps in active voice.
   {language_summary_key_instruction}
3. Produce one JSON object per thematic cluster or notable change, grouping closely related issues within the same project into a single summarized entry. Ensure all significant updates are included.
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
        'en': {
            'language_specific_instructions': '',
            'language_summary_key_instruction': '',
            'language_instruction': '',
        },
        'ja': {
            'language_specific_instructions': 'Use canonical English names for every person (see the team roster below). If a canonical name is missing, transliterate to the best English equivalent and mention that uncertainty in the Japanese summary text.\nUse English terminology for technical biology phrases (genes, assays, reagents, instruments, etc.) even inside the Japanese summary so downstream systems can link them reliably.',
            'language_summary_key_instruction': '- `"summary_ja"`: Japanese translation conveying the same facts with similar brevity and active tone while keeping technical biology terms in English.',
            'language_instruction': '**Important** Provide both Japanese and English summaries as described, but preserve canonical English names exactly as listed.',
        },
        'zh_CN': {
            'language_specific_instructions': 'Use canonical English names for every person (see the team roster below). If a canonical name is missing, transliterate to the best English equivalent and mention that uncertainty in the Simplified Chinese summary text.\nUse English terminology for technical biology phrases (genes, assays, reagents, instruments, etc.) even inside the Simplified Chinese summary so downstream systems can link them reliably.',
            'language_summary_key_instruction': '- `"summary_zh"`: Simplified Chinese translation conveying the same facts with similar brevity and active tone while keeping technical biology terms in English.',
            'language_instruction': '**Important** Provide both Simplified Chinese and English summaries as described, but preserve canonical English names exactly as listed.',
        },
        'zh_TW': {
            'language_specific_instructions': 'Use canonical English names for every person (see the team roster below). If a canonical name is missing, transliterate to the best English equivalent and mention that uncertainty in the Traditional Chinese summary text.\nUse English terminology for technical biology phrases (genes, assays, reagents, instruments, etc.) even inside the Traditional Chinese summary so downstream systems can link them reliably.',
            'language_summary_key_instruction': '- `"summary_zh"`: Traditional Chinese translation conveying the same facts with similar brevity and active tone while keeping technical biology terms in English.',
            'language_instruction': '**Important** Provide both Traditional Chinese and English summaries as described, but preserve canonical English names exactly as listed.',
        }
    }

    def __init__(self, config_path: Optional[str] = None, quiet: bool = False):
        super().__init__(
            config_path=config_path,
            quiet=quiet,
            logger_name='Hedwig.overview.structured_logger',
            language_instructions=self.LANGUAGE_INSTRUCTIONS,
            default_context_prefix=self.DEFAULT_CONTEXT_INFORMATION_PREFIX
        )

        self.enabled = True
        self.output_suffix = '-daily.jsonl'

        self.prompt_template = self.config.get('api.llm.jsonl_prompt_template', self.DEFAULT_OVERVIEW_PROMPT_TEMPLATE)
        self.model = self.config.get('api.llm.jsonl_output_model', self.config.get('api.llm.overview_model', 'gemini-2.5-pro'))

    def generate(
        self,
        write_to_file: bool = True,
        target_date: Optional[date_type] = None
    ) -> Optional[str]:
        """Generate structured JSONL logs for the specified date."""
        resolved_date = self._resolve_target_date(target_date)
        llm_input = self._prepare_llm_input(resolved_date)
        if not llm_input:
            return None

        try:
            self.logger.info("Submitting structured log prompt to LLM model '%s'", self.model)
            output = self.llm_client.generate(
                prompt=llm_input['prompt'],
                user_input=llm_input['user_input'],
                model=self.model
            )
        except Exception as exc:
            self.logger.error(f"Structured logger generation failed: {exc}")
            return None

        cleaned = self._clean_jsonl_output(output)
        if not cleaned:
            self.logger.info("Structured logger returned empty structured output.")
            return None

        normalized = self._normalize_unicode(cleaned)
        if not normalized:
            self.logger.info("Structured logger returned only invalid/empty JSON lines.")
            return None

        if write_to_file:
            self._write_structured_output(normalized, resolved_date)

        return normalized

    def _build_prompt(self) -> str:
        """Build the structured logger prompt for a single-day window."""
        context_info = self._get_static_context_information()

        full_config = {
            **self.lang_instructions,
            'lab_intro': self.lab_intro,
            'context_information': context_info
        }

        return self.prompt_template.format(**full_config)

    def _get_static_context_information(self) -> str:
        """Return context block derived from static_context.lab_status."""
        content = self.config.get('static_context.lab_status', '')
        if not isinstance(content, str):
            return ''
        content = content.strip()
        if not content:
            return ''

        separator = "" if self.context_info_prefix.endswith("\n") else "\n"
        return f"{self.context_info_prefix}{separator}{content}"

    def _get_prompt_for_date(self, target_date: date_type) -> str:
        return self._build_prompt()

    def _structured_output_path(self, target_date: date_type) -> Path:
        base_dir = self.summary_dir / target_date.strftime('%Y') / target_date.strftime('%m')
        filename = f"{target_date.strftime('%Y%m%d')}{self.output_suffix}"
        return base_dir / filename

    def structured_output_path(self, target_date: date_type) -> Optional[Path]:
        """Expose the structured output path for freshness checks."""
        return self._structured_output_path(target_date)

    def _prepare_llm_input(self, target_date: date_type) -> Optional[Dict[str, str]]:
        """Assemble the prompt and aggregated summaries for the target date."""
        user_input = self._get_llm_user_input(target_date)
        if not user_input:
            return None

        prompt = self._get_prompt_for_date(target_date)
        if not prompt:
            self.logger.info("Structured logger skipped: no prompt available for target date.")
            return None

        return {
            'prompt': prompt,
            'user_input': user_input
        }

    def _write_structured_output(self, data: str, target_date: date_type) -> None:
        output_path = self._structured_output_path(target_date)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not data.endswith("\n"):
            data += "\n"
        output_path.write_text(data, encoding='utf-8')
        self.logger.info("Structured JSONL log written to %s", output_path)

    def _get_up_to_date_structured_log_path(self, target_date: date_type) -> Optional[Path]:
        """Return structured log path if it exists and is newer than all source files."""
        if not self.enabled:
            return None

        structured_path = self.structured_output_path(target_date)
        if not structured_path or not structured_path.exists():
            return None

        source_files = self._get_source_files(target_date)
        if not source_files:
            return None

        latest_source_mtime = max(path.stat().st_mtime for path in source_files)
        if structured_path.stat().st_mtime >= latest_source_mtime:
            return structured_path

        return None

    def is_up_to_date(self, target_date: Optional[date_type] = None) -> bool:
        """Check whether the structured JSONL log is current for the given date."""
        resolved_date = self._resolve_target_date(target_date)
        return self._get_up_to_date_structured_log_path(resolved_date) is not None

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

    def _normalize_unicode(self, data: str) -> str:
        """Decode unicode escapes in JSONL entries while preserving structure."""
        if not data:
            return ""

        normalized_lines = []
        for line in data.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            try:
                obj = json.loads(stripped)
                normalized_lines.append(json.dumps(obj, ensure_ascii=False))
            except json.JSONDecodeError:
                # Keep original line if it can't be parsed
                normalized_lines.append(stripped)

        return "\n".join(normalized_lines).strip()
