import requests
import json
import os
from typing import Any, Optional

class processor:
    def __init__(self):
        # Initialize any required attributes here
        self.data = None
        self.words = []
        self.uniqueWords = []
        self.thesaurus_key = None
        self.thesaurus_link = None

        try:
            with open("config.json") as config_file:
                config = json.load(config_file)
            self.thesaurus_key = config.get("APIKeys", {}).get("thesaurus-key")
            self.thesaurus_link = config.get("APIKeys", {}).get("thesaurus-link")
        except (FileNotFoundError, json.JSONDecodeError):
            self.thesaurus_key = None

    def process(self, input_data):
        self.data = input_data
        self.get_words()
        self.find_repeats()

        for word in self.uniqueWords:
            thesaurus_data = self.get_or_fetch_thesaurus(word)
            return thesaurus_data  # For demonstration, return the first thesaurus data found

    def get_words(self):
        if self.data is None:
            return []
        # Example processing: split input data into words
        self.words = self.data.split()

    def find_repeats(self):
        if self.words is None:
            return []

        self.uniqueWords.clear()

        for word in self.words:
            if self.uniqueWords.count(word) == 0:
                self.uniqueWords.append(word)

    def _safe_filename(self, word: str) -> str:
        import re
        return re.sub(r'[^A-Za-z0-9._-]', '_', word.strip().lower())[:200]

    def get_or_fetch_thesaurus(self, word: str) -> Optional[Any]:
        import os, json
        if not word or not word.strip():
            return None

        cache_dir = os.path.abspath("thesaurus_cache")
        safe_name = self._safe_filename(word)
        file_path = os.path.join(cache_dir, f"{safe_name}.json")

        # Return cached file if present and valid
        if os.path.exists(file_path):
            try:
                print("Using cached thesaurus data for:", word)
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                # corrupted or unreadable cache — fall through to re-fetch
                pass

        # Not cached or invalid — fetch (call_thesaurus writes the cache on success)
        return self.call_thesaurus(word)

    def call_thesaurus(self, word: str) -> Optional[Any]:
        if not self.thesaurus_link or not self.thesaurus_key:
            return None
        if not word or not word.strip():
            return None

        try:
            print("Fetching thesaurus data for:", word)

            # build URL
            url = self.thesaurus_link.format(word, self.thesaurus_key)

            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()

            # ensure cache dir exists
            cache_dir = os.path.abspath("thesaurus_cache")
            os.makedirs(cache_dir, exist_ok=True)

            # use helper to get a safe filename
            safe_name = self._safe_filename(word)
            file_path = os.path.join(cache_dir, f"{safe_name}.json")

            print("Caching thesaurus data for:", word)
            # write permanent JSON file
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            return data

        except requests.RequestException:
            return None
        except (json.JSONDecodeError, OSError):
            return None