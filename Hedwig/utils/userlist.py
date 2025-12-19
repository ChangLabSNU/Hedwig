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

"""User list utilities for lookup and override handling."""

from typing import Dict, List, Optional
import os

import pandas as pd


def sanitize_user_name(name: str) -> str:
    """Normalize a user name for TSV storage."""
    if name is None:
        return 'Unknown'
    if not isinstance(name, str):
        name = str(name)
    return name.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ').strip()


def _log(logger, level: str, message: str) -> None:
    if logger:
        getattr(logger, level)(message)


def _read_userlist_file(
    path: Optional[str],
    logger,
    label: str,
    warn_missing: bool = False
) -> Optional[pd.DataFrame]:
    if not path:
        return None
    if not os.path.exists(path):
        if warn_missing:
            _log(logger, 'warning', f"{label} not found: {path}")
        return None
    try:
        df = pd.read_csv(path, sep='\t', dtype=str)
    except Exception as e:
        _log(logger, 'warning', f"Error loading {label} {path}: {e}")
        return None
    if not {'user_id', 'name'}.issubset(df.columns):
        _log(logger, 'warning', f"{label} missing required columns: {path}")
        return None
    return df


def load_user_lookup(
    userlist_file: Optional[str],
    override_file: Optional[str],
    logger=None
) -> Dict[str, str]:
    """Load user lookup table from TSV files."""
    base_df = _read_userlist_file(
        userlist_file,
        logger,
        "User list file",
        warn_missing=True
    )
    override_df = _read_userlist_file(
        override_file,
        logger,
        "Override file",
        warn_missing=False
    )

    if base_df is None and override_df is None:
        return {}

    if base_df is None:
        merged_df = override_df
    elif override_df is None:
        merged_df = base_df
    else:
        base_df = base_df.set_index('user_id')
        override_df = override_df.set_index('user_id')
        merged_df = override_df.combine_first(base_df).reset_index()

    if merged_df is None:
        return {}

    merged_df = merged_df.dropna(subset=['user_id', 'name'])
    merged_df['user_id'] = merged_df['user_id'].astype(str).str.strip()
    merged_df['name'] = merged_df['name'].astype(str).str.strip()
    return merged_df.set_index('user_id')['name'].to_dict()


def append_user_overrides(
    override_file: str,
    new_users: List[Dict[str, str]],
    logger=None
) -> int:
    """Append new user overrides to the configured override file."""
    if not override_file or not new_users:
        return 0

    existing_ids = set()
    if os.path.exists(override_file):
        try:
            existing_df = pd.read_csv(override_file, sep='\t', dtype=str)
            if 'user_id' in existing_df.columns:
                existing_ids = set(existing_df['user_id'].dropna().astype(str))
        except Exception as e:
            _log(logger, 'warning', f"Error reading override file {override_file}: {e}")

    to_append = [
        {
            'user_id': entry['user_id'],
            'name': sanitize_user_name(entry.get('name', 'Unknown'))
        }
        for entry in new_users
        if entry.get('user_id') and entry['user_id'] not in existing_ids
    ]
    if not to_append:
        return 0

    override_dir = os.path.dirname(override_file)
    if override_dir:
        os.makedirs(override_dir, exist_ok=True)

    write_header = not os.path.exists(override_file) or os.path.getsize(override_file) == 0
    with open(override_file, 'a', encoding='utf-8') as f:
        if write_header:
            f.write("user_id\tname\n")
        for entry in to_append:
            f.write(f"{entry['user_id']}\t{entry['name']}\n")

    _log(logger, 'info', f"Appended {len(to_append)} users to override file {override_file}")
    return len(to_append)
