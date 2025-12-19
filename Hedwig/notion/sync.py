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

"""Main synchronization module for Notion to Git"""

import os
from datetime import datetime
from typing import Optional, Dict, List, Set

import pandas as pd
from dateutil.parser import parse as parse8601
from tqdm import tqdm

from ..utils.config import Config
from ..utils.logging import setup_logger
from ..utils.git import GitManager
from ..utils.timezone import TimezoneManager
from .client import NotionClient
from .exporter import MarkdownExporter


class NotionSyncer:
    """Synchronize Notion pages to Git repository"""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize syncer with configuration

        Args:
            config_path: Path to configuration file
        """
        self.config = Config(config_path)
        self._setup_components()

    def _setup_components(self):
        """Initialize all components from configuration"""
        # Notion client
        # Support both new and old config structure
        notion_key = self.config.get('api.notion.api_key')
        if not notion_key:
            raise ValueError("Notion API key not found in config")

        self.notion_client = NotionClient(
            api_key=notion_key,
            api_version=self.config.get('api.notion.api_version', '2022-02-22'),
            page_size=self.config.get('api.notion.page_size', 100)
        )

        # Set environment variable for notion2md
        os.environ['NOTION_TOKEN'] = notion_key

        # Markdown exporter
        self.exporter = MarkdownExporter(
            dump_path_template=self.config.get('sync.markdown.dump_path_template', '{dump_dir}/{noteid_0}/{noteid_1}/{noteid_2}/{noteid}.md'),
            header_template=self.config.get('sync.markdown.header_template', '# {note[title]}\n- Page Location: {path}\n- Last Edited By: {note[last_edited_by]}\n- Updated: {note[last_edited_time]}\n')
        )

        # Git manager - will be initialized with quiet flag in sync()
        self.git_repo_path = self.config.get('paths.notes_repository')

        # Timezone
        self.timezone = TimezoneManager.get_configured_timezone(self.config)

    def sync(self, quiet: bool = False, verbose: bool = False) -> None:
        """Run the synchronization process

        Args:
            quiet: Suppress information messages and progress bar
            verbose: Enable verbose debug output
        """
        # Initialize git manager with quiet flag
        self.git_manager = GitManager(repo_path=self.git_repo_path, quiet=quiet)

        # Set up logging
        logger = setup_logger('Hedwig.notion.sync', quiet, verbose)
        start_time = TimezoneManager.now_local(self.config)

        # Load checkpoint
        checkpoint_file = self.config.get('paths.checkpoint_file')
        last_update = self._load_checkpoint(checkpoint_file, logger)

        # Get updated pages
        blacklist_file = self.config.get('paths.blacklist_file')
        blacklist = NotionClient.load_blacklist(blacklist_file)
        pages_df = self._get_updated_pages(last_update, blacklist, logger)

        if len(pages_df) == 0:
            logger.info('No updates found.')
            return

        # Ensure editor IDs from updates are present in the lookup table
        self.user_lookup = self._ensure_editor_lookup(pages_df, logger)
        pages_df = self._apply_user_lookup(pages_df)

        # Process pages
        dump_dir = self.config.get('paths.notes_repository')
        update_count = self._process_all_pages(pages_df, dump_dir, logger, quiet, verbose)

        if update_count == 0:
            logger.warning('No pages were successfully exported.')
            return

        logger.info(f'Successfully exported {update_count} pages.')

        # Commit changes
        self._commit_changes()

        # Save checkpoint
        self._save_checkpoint(checkpoint_file, start_time)
        logger.info(f'Saved checkpoint for {start_time.isoformat()}')

    def _load_checkpoint(self, checkpoint_file: str, logger) -> datetime:
        """Load the last update timestamp from checkpoint file"""
        try:
            with open(checkpoint_file, 'r') as f:
                last_update = parse8601(f.readline().strip())
            logger.info(f'Last update: {last_update}')
        except (FileNotFoundError, ValueError):
            # Use default lookback days when checkpoint is missing
            default_lookback_days = self.config.get('sync.default_lookback_days', 7)
            last_update = TimezoneManager.now_local(self.config) - pd.Timedelta(days=default_lookback_days)
            logger.info(f'No checkpoint found. Looking back {default_lookback_days} days to {last_update}')
        return last_update

    def _get_updated_pages(self, last_update: datetime, blacklist: set, logger) -> pd.DataFrame:
        """Retrieve and filter updated pages from Notion"""
        logger.debug(f'Retrieving objects modified since {last_update}')
        all_objects = self.notion_client.list_all_objects(since=last_update)
        logger.debug(f'Found {len(all_objects)} total objects')

        # Filter out blacklisted items
        filtered = all_objects[~all_objects['id'].isin(blacklist)]
        logger.debug(f'After blacklist filtering: {len(filtered)} objects')

        # Filter for pages only
        pages = filtered[filtered['object'] == 'page']
        logger.debug(f'After filtering for pages only: {len(pages)} pages')

        return pages

    def _process_all_pages(self, pages_df: pd.DataFrame, dump_dir: str,
                          logger, quiet: bool, verbose: bool) -> int:
        """Process all pages with or without progress bar"""
        update_count = 0
        total_pages = len(pages_df)

        if quiet:
            # Simple loop without progress bar
            for _, page_info in pages_df.iterrows():
                if self._process_single_page(page_info, dump_dir, logger):
                    update_count += 1
        else:
            # Switch to tqdm-compatible logging
            logger = setup_logger('Hedwig.notion.sync', quiet, verbose, use_tqdm=True)

            # Loop with progress bar
            with tqdm(total=total_pages, desc="Processing pages", unit="page") as pbar:
                for _, page_info in pages_df.iterrows():
                    pbar.set_postfix_str(f"{page_info['title'][:50]}...")
                    if self._process_single_page(page_info, dump_dir, logger):
                        update_count += 1
                    pbar.update(1)

            # Switch back to regular logging
            logger = setup_logger('Hedwig.notion.sync', quiet, verbose, use_tqdm=False)

        return update_count

    def _process_single_page(self, page_info: pd.Series, dump_dir: str, logger) -> bool:
        """Process a single Notion page"""
        page_id = page_info['id']
        logger.debug(f'Processing page {page_id}: {page_info["title"]}')

        try:
            # Get page path
            page_path = self.notion_client.get_page_path(page_id)

            # Export to markdown
            exported_path = self.exporter.export_page(
                page_id=page_id,
                page_info=page_info.to_dict(),
                page_path=page_path,
                dump_dir=dump_dir
            )

            logger.debug(f'Successfully exported to {exported_path}')
            return True

        except Exception as e:
            logger.error(f'Error exporting {page_id}: {e}')
            return False

    def _commit_changes(self) -> None:
        """Commit changes to git"""
        timestamp = TimezoneManager.format_local(self.config, '%Y-%m-%d %H:%M:%S')
        commit_message = self.config.get('sync.git_commit_template', 'Automated commit: {datetime}').format(datetime=timestamp)

        self.git_manager.add_all()
        self.git_manager.commit(commit_message)

    def _save_checkpoint(self, checkpoint_file: str, timestamp: datetime) -> None:
        """Save checkpoint timestamp"""
        with open(checkpoint_file, 'w') as f:
            f.write(timestamp.isoformat() + '\n')

    def sync_userlist(self, quiet: bool = False) -> None:
        """Sync user list from Notion to TSV file

        Args:
            quiet: Suppress informational messages
        """
        # Setup logging
        logger = setup_logger('Hedwig.notion.sync', quiet)

        # Get userlist file path from config
        userlist_file = self.config.get('paths.userlist_file')
        if not userlist_file:
            logger.error("No userlist_file configured in paths section")
            raise ValueError("Missing paths.userlist_file configuration")

        # Retrieve user list from Notion
        logger.info("Retrieving user list from Notion...")
        users = self.notion_client.list_all_users()

        # Convert to DataFrame
        notion_df = pd.DataFrame(users)
        notion_df = notion_df[['id', 'name']].rename(columns={'id': 'user_id'})

        # Check for override file
        override_file = self.config.get('paths.userlist_override_file')
        if override_file:
            if not os.path.exists(override_file):
                logger.error(f"Configured override file does not exist: {override_file}")
                raise FileNotFoundError(f"Override file not found: {override_file}")

            logger.info(f"Loading override users from {override_file}")
            try:
                # Read override file
                override_df = pd.read_csv(override_file, sep='\t', dtype=str)

                # Validate columns
                if not {'user_id', 'name'}.issubset(override_df.columns):
                    logger.warning(f"Override file {override_file} doesn't have expected columns")
                else:
                    # Merge with override taking priority
                    # First, set index for both dataframes
                    notion_df.set_index('user_id', inplace=True)
                    override_df.set_index('user_id', inplace=True)

                    # Combine: override values take precedence
                    merged_df = override_df.combine_first(notion_df).reset_index()

                    logger.info(f"Merged {len(override_df)} override users with {len(notion_df)} Notion users")
            except Exception as e:
                logger.error(f"Error reading override file: {e}")
                raise
        else:
            merged_df = notion_df

        # Write to TSV file
        logger.info(f"Writing {len(merged_df)} users to {userlist_file}")

        # Ensure directory exists
        userlist_dir = os.path.dirname(userlist_file)
        if userlist_dir:  # Only create directory if there is a directory component
            os.makedirs(userlist_dir, exist_ok=True)

        # Clean up names (replace tabs and newlines with spaces)
        merged_df['name'] = merged_df['name'].str.replace('[\t\n\r]', ' ', regex=True)

        # Write TSV file
        merged_df.to_csv(userlist_file, sep='\t', index=False, encoding='utf-8')

        if not quiet:
            print(f"Successfully synced {len(merged_df)} users to {userlist_file}")

    def _load_user_lookup(self, logger) -> Dict[str, str]:
        """Load user lookup table from TSV files."""
        userlist_file = self.config.get('paths.userlist_file')
        override_file = self.config.get('paths.userlist_override_file')

        base_df = None
        if userlist_file and os.path.exists(userlist_file):
            try:
                base_df = pd.read_csv(userlist_file, sep='\t', dtype=str)
                if not {'user_id', 'name'}.issubset(base_df.columns):
                    logger.warning(f"User list file missing required columns: {userlist_file}")
                    base_df = None
            except Exception as e:
                logger.warning(f"Error loading user list file {userlist_file}: {e}")
                base_df = None
        elif userlist_file:
            logger.warning(f"User list file not found: {userlist_file}")

        override_df = None
        if override_file and os.path.exists(override_file):
            try:
                override_df = pd.read_csv(override_file, sep='\t', dtype=str)
                if not {'user_id', 'name'}.issubset(override_df.columns):
                    logger.warning(f"Override file missing required columns: {override_file}")
                    override_df = None
            except Exception as e:
                logger.warning(f"Error loading override file {override_file}: {e}")
                override_df = None

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

        if merged_df is None or 'user_id' not in merged_df.columns or 'name' not in merged_df.columns:
            return {}

        merged_df = merged_df.dropna(subset=['user_id', 'name'])
        merged_df['user_id'] = merged_df['user_id'].astype(str).str.strip()
        merged_df['name'] = merged_df['name'].astype(str).str.strip()
        return merged_df.set_index('user_id')['name'].to_dict()

    @staticmethod
    def _sanitize_user_name(name: str) -> str:
        """Normalize a user name for TSV storage."""
        if name is None:
            return 'Unknown'
        if not isinstance(name, str):
            name = str(name)
        return name.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ').strip()

    def _extract_editor_ids(self, pages_df: pd.DataFrame) -> Set[str]:
        """Extract unique editor IDs from updated pages."""
        if 'last_edited_by' not in pages_df.columns:
            return set()
        series = pages_df['last_edited_by'].dropna()
        return set(series.astype(str).tolist())

    def _fetch_unknown_users(self, user_ids: List[str], logger) -> List[Dict[str, str]]:
        """Fetch user metadata for unknown user IDs."""
        fetched: List[Dict[str, str]] = []
        for user_id in user_ids:
            user_info = self.notion_client.get_user(user_id)
            if not user_info:
                logger.warning(f"Unable to retrieve user info for {user_id}")
                continue
            fetched.append({
                'user_id': user_info['id'],
                'name': self._sanitize_user_name(user_info.get('name', 'Unknown'))
            })
        return fetched

    def _append_user_overrides(self, override_file: str, new_users: List[Dict[str, str]], logger) -> None:
        """Append new user overrides to the configured override file."""
        if not new_users:
            return

        existing_ids: Set[str] = set()
        if os.path.exists(override_file):
            try:
                existing_df = pd.read_csv(override_file, sep='\t', dtype=str)
                if 'user_id' in existing_df.columns:
                    existing_ids = set(existing_df['user_id'].dropna().astype(str))
            except Exception as e:
                logger.warning(f"Error reading override file {override_file}: {e}")

        to_append = [entry for entry in new_users if entry['user_id'] not in existing_ids]
        if not to_append:
            return

        override_dir = os.path.dirname(override_file)
        if override_dir:
            os.makedirs(override_dir, exist_ok=True)

        write_header = not os.path.exists(override_file) or os.path.getsize(override_file) == 0
        with open(override_file, 'a', encoding='utf-8') as f:
            if write_header:
                f.write("user_id\tname\n")
            for entry in to_append:
                f.write(f"{entry['user_id']}\t{entry['name']}\n")

        logger.info(f"Appended {len(to_append)} users to override file {override_file}")

    def _ensure_editor_lookup(self, pages_df: pd.DataFrame, logger) -> Dict[str, str]:
        """Ensure editor IDs in updates are available in lookup tables."""
        user_lookup = self._load_user_lookup(logger)
        editor_ids = self._extract_editor_ids(pages_df)
        if not editor_ids:
            return user_lookup

        missing_ids = sorted(editor_ids - set(user_lookup.keys()))
        if not missing_ids:
            return user_lookup

        override_file = self.config.get('paths.userlist_override_file')
        if not override_file:
            logger.warning("Unknown editor IDs found but no userlist_override_file configured")
            return user_lookup

        logger.info(f"Fetching {len(missing_ids)} unknown editor IDs from Notion")
        fetched_users = self._fetch_unknown_users(missing_ids, logger)
        if not fetched_users:
            return user_lookup

        self._append_user_overrides(override_file, fetched_users, logger)
        return self._load_user_lookup(logger)

    def _apply_user_lookup(self, pages_df: pd.DataFrame) -> pd.DataFrame:
        """Replace editor IDs with names when possible."""
        if not getattr(self, 'user_lookup', None):
            return pages_df

        if 'last_edited_by' not in pages_df.columns:
            return pages_df

        def _map_user(value):
            if not isinstance(value, str):
                return value
            return self.user_lookup.get(value, value)

        pages_df = pages_df.copy()
        pages_df['last_edited_by'] = pages_df['last_edited_by'].apply(_map_user)
        return pages_df
