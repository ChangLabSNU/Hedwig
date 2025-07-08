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

"""General LLM client for Hedwig package"""

import os
from openai import OpenAI
import tiktoken

from .utils.config import Config


class LLMClient:
    """General LLM client for text generation"""

    def __init__(self, config: Config):
        """Initialize LLM client

        Args:
            config: Configuration object
        """
        self.config = config

        # Get API configuration
        api_key = self._get_api_key()
        api_url = config.get('api.llm.url', 'https://generativelanguage.googleapis.com/v1beta/openai/')

        # Initialize OpenAI client
        self.client = OpenAI(api_key=api_key, base_url=api_url)

        # Initialize tokenizer
        encoding_name = config.get('api.llm.tokenizer_encoding', 'o200k_base')
        self.tokenizer = tiktoken.get_encoding(encoding_name)

    def _get_api_key(self) -> str:
        """Get API key from config or environment"""
        # Try config first
        api_key = self.config.get('api.llm.key')
        if api_key:
            return api_key

        # Try environment variables
        for env_var in ['GEMINI_API_KEY', 'OPENAI_API_KEY']:
            api_key = os.environ.get(env_var)
            if api_key:
                return api_key

        # Try loading from .env file
        try:
            import dotenv
            env_values = dotenv.dotenv_values()
            for key in ['GEMINI_API_KEY', 'OPENAI_API_KEY']:
                if key in env_values:
                    return env_values[key]
        except ImportError:
            pass

        raise ValueError("No API key found. Set GEMINI_API_KEY or configure api.llm.key")

    def generate(self,
                 prompt: str,
                 user_input: str,
                 model: str,
                 temperature: float = 0.7,
                 max_tokens: int = 32768,
                 top_p: float = 1.0) -> str:
        """Generate text using the LLM

        Args:
            prompt: System prompt
            user_input: User input text
            model: Model name to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            top_p: Top-p sampling parameter

        Returns:
            Generated text
        """
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {
                    'role': 'system',
                    'content': [{
                        'type': 'text',
                        'text': prompt,
                    }]
                },
                {
                    'role': 'user',
                    'content': [{
                        'type': 'text',
                        'text': user_input,
                    }]
                }
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            response_format={'type': 'text'}
        )

        return response.choices[0].message.content

    def count_tokens(self, text: str) -> int:
        """Count tokens in text

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        return len(self.tokenizer.encode(text))