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

"""Notion API client wrapper"""

import json
import uuid
from typing import Dict, Any, List, Generator, Optional, Set, Tuple
from datetime import datetime
from urllib.parse import urlencode

import requests
import pandas as pd
from dateutil.parser import parse as parse8601
from notion_client import Client


class NotionClient:
    """Wrapper for Notion API operations"""

    def __init__(self, api_key: str, api_version: str = '2022-02-22', page_size: int = 100):
        """Initialize Notion client

        Args:
            api_key: Notion API key
            api_version: Notion API version
            page_size: Default page size for paginated requests
        """
        self.api_key = api_key
        self.api_version = api_version
        self.page_size = page_size
        self.client = Client(auth=api_key)

        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Notion-Version': api_version,
            'Accept': 'application/json',
        }

    def call_paginated(self, url: str, method: str = 'POST', **payload) -> Generator[List[Dict], None, None]:
        """Make paginated API calls to Notion

        Args:
            url: API endpoint URL
            method: HTTP method (POST or GET)
            **payload: Request payload

        Yields:
            List of results from each page
        """
        payload.setdefault('page_size', self.page_size)

        while True:
            if method == 'POST':
                response = requests.request('POST', url, json=payload, headers=self.headers)
            else:
                url += '?' + urlencode(payload)
                response = requests.request('GET', url, headers=self.headers)

            res = json.loads(response.text)
            yield res['results']

            if res['has_more']:
                payload['start_cursor'] = res['next_cursor']
            else:
                break

    def list_all_objects(self, since: Optional[datetime] = None) -> pd.DataFrame:
        """List all objects from Notion, optionally filtered by last edit time

        Args:
            since: Only return objects edited after this time

        Returns:
            DataFrame with object information
        """
        sort_order = {
            'direction': 'descending',
            'timestamp': 'last_edited_time'
        }
        results = self.call_paginated(
            'https://api.notion.com/v1/search',
            sort=sort_order
        )

        endofframe = False
        objects = []

        # Retrieve and filter objects
        for entries in results:
            if since is not None:
                matching = [
                    ent for ent in entries
                    if parse8601(ent['last_edited_time']) >= since
                ]
                if len(matching) < len(entries):
                    endofframe = True
            else:
                matching = entries

            objects.extend(matching)
            if endofframe:  # Stop looking for pages outside the time range
                break

        # Process and normalize the retrieved objects
        attributes = ['id', 'object', 'created_time', 'last_edited_time',
                     'created_by', 'last_edited_by', 'title', 'url']
        records = []

        for obj in objects:
            title = self._extract_title(obj)
            records.append([
                obj['id'], obj['object'], obj['created_time'], obj['last_edited_time'],
                obj['created_by']['id'], obj['last_edited_by']['id'], title,
                obj['url']
            ])

        return pd.DataFrame(records, columns=attributes)

    def get_page_path(self, page_id: str) -> str:
        """Get hierarchical path of a Notion page

        Args:
            page_id: Notion page ID

        Returns:
            Hierarchical path string (e.g., "Parent / Page")
        """
        path_parts = []
        current_id = page_id

        try:
            while current_id:
                # Get the title and parent info for the current item
                title, parent_type, parent_id = self._get_item_info(current_id)

                # Add title to path
                if title:
                    path_parts.append(title)

                # Determine next item to process based on parent type
                if parent_type == "workspace":
                    # Stop at workspace level (don't include "Workspace" in path)
                    break
                elif parent_type in ("page_id", "database_id"):
                    current_id = parent_id
                else:
                    # Unknown parent type or no parent
                    break

        except Exception as e:
            return f"An error occurred: {e}"

        return " / ".join(reversed(path_parts))

    def _get_item_info(self, item_id: str) -> Tuple[str, str, Optional[str]]:
        """Extract title and parent information from a Notion page or database

        Args:
            item_id: ID of the page or database

        Returns:
            Tuple of (title, parent_type, parent_id)
        """
        # Try to retrieve as a page first
        try:
            page = self.client.pages.retrieve(page_id=item_id)
            title = self._extract_page_title(page)
            parent = page.get("parent", {})
            return title, parent.get("type", ""), parent.get(parent.get("type", ""))
        except:
            # If page retrieval fails, try as a database
            try:
                database = self.client.databases.retrieve(database_id=item_id)
                title = self._extract_database_title(database)
                parent = database.get("parent", {})
                return title, parent.get("type", ""), parent.get(parent.get("type", ""))
            except:
                # If both fail, return minimal info
                return f"Untitled ({item_id[:8]})", "", None

    def _extract_page_title(self, page: Dict[str, Any]) -> str:
        """Extract title from a Notion page

        Args:
            page: Notion page object

        Returns:
            Page title or fallback string
        """
        # First, try to find title in properties (works for database items)
        properties = page.get("properties", {})
        for _, prop_value in properties.items():
            if prop_value.get("type") == "title" and prop_value.get("title"):
                return prop_value["title"][0]["plain_text"]

        # Fallback to page title (for regular pages)
        if "title" in page:
            title_items = page.get("title", [])
            if title_items:
                return title_items[0].get("plain_text", "")

        # Final fallback
        return f"Untitled ({page.get('id', 'unknown')[:8]})"

    def _extract_database_title(self, database: Dict[str, Any]) -> str:
        """Extract title from a Notion database

        Args:
            database: Notion database object

        Returns:
            Database title or fallback string
        """
        title_items = database.get("title", [])
        if title_items:
            return title_items[0]["plain_text"]
        return f"Untitled Database ({database.get('id', 'unknown')[:8]})"

    @staticmethod
    def _extract_title(obj: Dict[str, Any]) -> str:
        """Extract title from Notion object

        Args:
            obj: Notion object

        Returns:
            Title string
        """
        if 'title' in obj:
            return ''.join([
                op['text']['content']
                for op in obj['title']
                if op['type'] == 'text'
            ])

        if 'properties' in obj:
            for _, values in obj['properties'].items():
                if values['id'] == 'title' and 'title' in values:
                    return ''.join([
                        op['text']['content']
                        for op in values['title']
                        if op['type'] == 'text'
                    ])

        return 'Untitled object ' + obj['id']

    @staticmethod
    def load_blacklist(path: Optional[str]) -> Set[str]:
        """Load blacklisted page IDs from file

        Args:
            path: Path to blacklist file (None if not configured)

        Returns:
            Set of blacklisted page IDs
        """
        if path is None:
            return set()

        blacklist = set()
        try:
            with open(path, 'r') as f:
                for line in f:
                    pid = line.split()[0]
                    if pid:
                        blacklist.add(str(uuid.UUID(pid)))
        except FileNotFoundError:
            return set()
        return blacklist

    def list_all_users(self) -> List[Dict[str, str]]:
        """Retrieve all users from Notion workspace

        Returns:
            List of dictionaries containing user information (id and name)
        """
        users = []

        # Get users through paginated API calls
        results = self.call_paginated(
            'https://api.notion.com/v1/users',
            method='GET'
        )

        for page_users in results:
            for user in page_users:
                user_info = {
                    'id': user['id'],
                    'name': user.get('name', 'Unknown'),
                    'type': user.get('type', 'unknown')
                }

                # For bot users, include bot owner information if available
                if user.get('type') == 'bot' and 'bot' in user:
                    bot_info = user['bot']
                    if 'owner' in bot_info and bot_info['owner'].get('type') == 'user':
                        user_info['name'] = f"{user_info['name']} (Bot)"

                users.append(user_info)

        return users
