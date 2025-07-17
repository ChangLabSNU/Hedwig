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
from typing import Dict, Any, List, Generator, Optional, Set
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
            Hierarchical path string (e.g., "Workspace / Parent / Page")
        """
        path_parts = []
        current_page_id = page_id

        try:
            while current_page_id:
                page = self.client.pages.retrieve(page_id=current_page_id)

                # Extract the page title
                title_property = page.get("properties", {}).get("title", {})
                if title_property.get("type") == "title" and title_property.get("title"):
                    path_parts.append(title_property["title"][0]["plain_text"])

                parent = page.get("parent", {})
                parent_type = parent.get("type")

                if parent_type == "page_id":
                    current_page_id = parent.get("page_id")
                elif parent_type == "database_id":
                    # If the parent is a database, get the database title
                    database_id = parent.get("database_id")
                    database = self.client.databases.retrieve(database_id=database_id)
                    db_title = database.get("title", [])
                    if db_title:
                        path_parts.append(db_title[0]["plain_text"])
                    current_page_id = None
                elif parent_type == "workspace":
                    path_parts.append("Workspace")
                    current_page_id = None
                else:
                    current_page_id = None

        except Exception as e:
            return f"An error occurred: {e}"

        return " / ".join(reversed(path_parts[1:]))

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
