# python
"""
Refactored processor module for Poem Synonymizer.

Provides a single class `processor` that:
- Tokenizes input (preserving newlines as `_newLine` markers).
- Determines word types (local heuristics or external model when configured).
- Fetches / caches thesaurus entries.
- Builds a synonymized string while respecting newline markers.

The implementation uses type hints, logging, and defensive error handling.
"""

from __future__ import annotations
from typing import Any, List, Tuple, Optional
import json
import os
import re
import logging

logger = logging.getLogger(__name__)
DEFAULT_MODEL = "gemini-2.5-flash-lite"
THESAURUS_CACHE_DIR = "thesaurus_cache"
CONFIG_PATH = "config.json"
NEWLINE_MARKER = "_newLine"


class processor:
    """
    Processor for converting an input string into a synonymized output.

    Attributes:
        data: Last raw input string submitted.
        words: Token list derived from the input (with newline markers).
        words_type: List of (word, type) pairs matching `words`.
        thesaurus_key: API key or sentinel indicating cache presence.
        thesaurus_link: URL template for thesaurus lookup, expects format(word, key).
        gemini_key: Optional API key for external POS tagging.
        model: External model name used for POS tagging.
    """

    def __init__(self) -> None:
        self.data: Optional[str] = None
        self.words: List[str] = []
        self.words_type: List[Tuple[str, str]] = []
        self.thesaurus_key: Optional[str] = None
        self.thesaurus_link: Optional[str] = None
        self.gemini_key: Optional[str] = None
        self.model: str = DEFAULT_MODEL
        self.synonym_sentence: str = ""

        # Try to initialize keys from caches/configs
        self.load_thesaurus_cache_key()
        self._load_config_keys(CONFIG_PATH)

    # ---------- Public API ----------

    def process(self, input_data: Any) -> str:
        """
        Main entry point.

        If `input_data` is a dict with a truthy `_rebuild` key, immediately
        calls `build_synonym_string()` and returns that result (no network calls).
        Otherwise runs the full flow: set data -> find types -> fetch thesaurus -> build result.
        """
        # Early return for rebuild command (only rebuild string)
        if isinstance(input_data, dict) and input_data.get("_rebuild"):
            logger.debug("Received rebuild command; rebuilding synonym string.")
            return self.build_synonym_string()

        # Regular full processing
        self.data = str(input_data) if input_data is not None else ""
        self.find_type()

        # Pre-fetch thesaurus entries where appropriate (skip newline markers)
        for item in self.words_type:
            try:
                word, _ = item
            except Exception:
                logger.warning("Skipping malformed words_type entry: %s", item)
                continue

            if word == NEWLINE_MARKER:
                continue

            try:
                self.get_or_fetch_thesaurus(word)
            except Exception:
                # Don't fail processing just because a fetch failed; build_synonym_string will handle missing entries.
                logger.exception("Thesaurus fetch failed for word: %s", word)

        return self.build_synonym_string()

    # ---------- Tokenization & Type Detection ----------

    def find_type(self, user_input: Optional[str] = None) -> List[Tuple[str, str]]:
        """
        Tokenize input and determine word types.

        Improvements:
        - Avoid calling `resp.raise_for_status()` so requests won't raise an HTTPError
          that can include the raw URL\+key in tracebacks.
        - Log a sanitized URL (API key masked) when the remote service returns an error.
        - Track repeated failures and disable external tagging after a threshold,
          falling back to local heuristics.
        """
        import requests

        text = user_input if user_input is not None else (self.data or "")
        if not text or not str(text).strip():
            self.words = []
            self.words_type = []
            return []

        tokens = re.findall(r"\n|\b\w+(?:'\w+)?\b", str(text))
        self.words = [t if t != "\n" else NEWLINE_MARKER for t in tokens]

        if not self.words:
            self.words_type = []
            return []

        def _guess_type(w: str) -> str:
            lw = w.lower()
            if w == NEWLINE_MARKER:
                return "newline"
            if re.match(r'^\W+$', w):
                return "punctuation"
            if re.match(r'^[0-9]+(\.[0-9]+)?$', lw):
                return "numeral"
            pronouns = {"i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them", "my", "your",
                        "his", "our", "their", "mine", "yours"}
            determiners = {"the", "a", "an", "this", "that", "these", "those", "some", "any", "each", "every", "no",
                           "its"}
            prepositions = {"in", "on", "at", "for", "to", "from", "by", "with", "about", "of", "into", "over", "under",
                            "between", "among"}
            conjunctions = {"and", "but", "or", "nor", "so", "yet", "for"}
            if lw in pronouns:
                return "pronoun"
            if lw in determiners:
                return "determiner"
            if lw in prepositions:
                return "preposition"
            if lw in conjunctions:
                return "conjunction"
            if lw.endswith("ly"):
                return "adverb"
            if lw.endswith("ing") or lw.endswith("ed") or lw.endswith("s"):
                return "verb"
            return "noun"

        # If no remote model configured, use local guesses
        if not getattr(self, "gemini_key", None):
            self.words_type = [(w, _guess_type(w)) for w in self.words]
            return self.words_type

        # Prepare prompt and request
        prompt = (
            "Using the sentence and the list of words provided, determine the word type (part of speech) "
            "for each word based on its usage in the sentence. Return ONLY a JSON array of arrays in the same order "
            "as the words: [[\"original_word\",\"word_type\"], ...].\n\n"
            f"Sentence: {json.dumps(str(text))}\n"
            f"Words: {json.dumps(self.words)}\n"
        )

        url = f"https://generativelanguage.googleapis.com/v1beta2/models/{self.model}:generateText?key={self.gemini_key}"
        payload = {"prompt": {"text": prompt}, "temperature": 0.0, "maxOutputTokens": 512}
        headers = {"Content-Type": "application/json"}

        # failure tracking to auto-disable noisy external calls
        self._gemini_failures = getattr(self, "_gemini_failures", 0)
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            # If non-2xx, log sanitized info and fall back
            if resp.status_code >= 400:
                # mask key in URL for logging
                masked_url = re.sub(r"([?&]key=)[^&]+", r"\1***", url)
                logger.error("External POS tagging returned %s for URL: %s", resp.status_code, masked_url)
                logger.debug("Remote response body: %s", resp.text[:1000])
                self._gemini_failures += 1
                # disable gemini after repeated failures to avoid spam and sensitive traces
                if self._gemini_failures >= 3:
                    logger.info("Disabling external POS tagging after %d failures", self._gemini_failures)
                    self.gemini_key = None
                # fallback to local heuristics
                result = [(w, _guess_type(w)) for w in self.words]
                self.words_type = result
                return result

            # Successful response path
            resp_json = resp.json()
            text_out = None
            if isinstance(resp_json, dict):
                candidates = resp_json.get("candidates") or resp_json.get("outputs") or []
                if candidates and isinstance(candidates, list):
                    first = candidates[0]
                    text_out = first.get("content") or first.get("output") or first.get("text")
                if text_out is None:
                    text_out = resp_json.get("output") or resp_json.get("content") or None
            if not text_out:
                text_out = resp.text

            parsed = json.loads(text_out)
            result = []
            for item in parsed:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    w = str(item[0])
                    t = str(item[1])
                    if w == "\n" or w == NEWLINE_MARKER:
                        result.append((NEWLINE_MARKER, "newline"))
                    else:
                        result.append((w, t))
                else:
                    s = str(item)
                    if s == "\n" or s == NEWLINE_MARKER:
                        result.append((NEWLINE_MARKER, "newline"))
                    else:
                        result.append((s, _guess_type(s)))

            # reset failure counter on success
            self._gemini_failures = 0
        except Exception:
            logger.exception("External POS tagging failed; falling back to local heuristics.")
            self._gemini_failures += 1
            if self._gemini_failures >= 3:
                logger.info("Disabling external POS tagging after %d consecutive exceptions", self._gemini_failures)
                self.gemini_key = None
            result = [(w, _guess_type(w)) for w in self.words]

        self.words_type = result
        return result

    # ---------- Output Construction ----------

    def build_synonym_string(self) -> str:
        """
        Build and return the synonymized sentence using `self.words_type`.
        Respects `NEWLINE_MARKER` entries by inserting literal newlines without extra spaces.
        """
        import random

        sentence_parts: List[str] = []
        for item in getattr(self, "words_type", []):
            try:
                word, wtype = item
            except Exception:
                logger.warning("Skipping unexpected words_type item: %s", item)
                continue

            if word == NEWLINE_MARKER:
                # Ensure no trailing space before newline and append newline as its own segment
                if sentence_parts and sentence_parts[-1].endswith(" "):
                    sentence_parts[-1] = sentence_parts[-1].rstrip()
                sentence_parts.append("\n")
                continue

            chosen_word = word  # default to original

            try:
                entry = self.get_or_fetch_thesaurus(word)
                if entry:
                    entries = entry if isinstance(entry, list) else [entry]
                    matching = [e for e in entries if isinstance(e, dict) and e.get("fl") == wtype]

                    if matching:
                        syn_candidates: List[str] = []
                        for e in matching:
                            meta = e.get("meta", {}) if isinstance(e, dict) else {}
                            for syn_list in meta.get("syns", []):
                                if isinstance(syn_list, list):
                                    syn_candidates.extend([s for s in syn_list if isinstance(s, str)])
                        # remove exact-case duplicates
                        syn_candidates = [s for s in syn_candidates if s.lower() != word.lower()]

                        if syn_candidates:
                            chosen_word = random.choice(syn_candidates)
                            # preserve capitalization
                            if word and word[0].isupper():
                                chosen_word = chosen_word.capitalize()
                        else:
                            logger.debug("No synonym candidates for '%s' of type '%s'", word, wtype)
                    else:
                        logger.debug("No thesaurus entries match type '%s' for '%s'", wtype, word)
                else:
                    logger.debug("No thesaurus data for '%s'", word)
            except Exception:
                logger.exception("Failed to select synonym for '%s'", word)
                chosen_word = word

            # Manage spacing: newline segments stand alone; otherwise join with spaces
            if sentence_parts:
                last = sentence_parts[-1]
                if last == "\n":
                    sentence_parts.append(chosen_word)
                else:
                    sentence_parts.append(" " + chosen_word)
            else:
                sentence_parts.append(chosen_word)

        # Join parts into final string, then normalize sequences of spaces/newlines
        sentence = "".join(sentence_parts)
        # Remove any accidental space before newlines
        sentence = re.sub(r" +\n", "\n", sentence)
        self.synonym_sentence = sentence
        return sentence

    # ---------- Thesaurus helpers ----------

    def _safe_filename(self, word: str) -> str:
        """Return a filesystem-safe lowercase filename for caching."""
        return re.sub(r'[^A-Za-z0-9._-]', '_', word.strip().lower())[:200]

    def get_or_fetch_thesaurus(self, word: str) -> Any:
        """
        Return cached thesaurus data for `word` if present; otherwise call the remote API.
        Returns None on failure or if no valid API config is present.
        """
        if not word or not word.strip():
            return None

        cache_dir = os.path.abspath(THESAURUS_CACHE_DIR)
        os.makedirs(cache_dir, exist_ok=True)
        safe_name = self._safe_filename(word)
        file_path = os.path.join(cache_dir, f"{safe_name}.json")

        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as fh:
                    logger.debug("Using cached thesaurus data for: %s", word)
                    return json.load(fh)
            except Exception:
                logger.exception("Failed to read cache for: %s", word)
                # If cache invalid, fall through to attempt remote fetch

        return self.call_thesaurus(word)

    def call_thesaurus(self, word: str) -> Any:
        """
        Call the external thesaurus API using `thesaurus_link` and `thesaurus_key`.
        Caches successful responses. Returns None on failure.
        """
        import requests

        if not self.thesaurus_link or not self.thesaurus_key:
            logger.debug("No thesaurus link/key configured; skipping remote call for: %s", word)
            return None
        if not word or not word.strip():
            return None

        try:
            url = self.thesaurus_link.format(word, self.thesaurus_key)
            logger.debug("Fetching thesaurus data for: %s", word)
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()

            cache_dir = os.path.abspath(THESAURUS_CACHE_DIR)
            os.makedirs(cache_dir, exist_ok=True)
            safe_name = self._safe_filename(word)
            file_path = os.path.join(cache_dir, f"{safe_name}.json")

            with open(file_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            logger.debug("Cached thesaurus data for: %s", word)
            return data
        except Exception:
            logger.exception("Thesaurus API call failed for: %s", word)
            return None

    # ---------- Configuration helpers ----------

    def _load_config_keys(self, path: str) -> None:
        """Load API keys from a config file if available; fails silently on parse errors."""
        try:
            with open(path, "r", encoding="utf-8") as config_file:
                cfg = json.load(config_file)
            self.thesaurus_key = cfg.get("APIKeys", {}).get("thesaurus-key") or self.thesaurus_key
            self.thesaurus_link = cfg.get("APIKeys", {}).get("thesaurus-link") or self.thesaurus_link
            self.gemini_key = cfg.get("APIKeys", {}).get("gemini-key") or self.gemini_key
        except Exception:
            logger.debug("No config file loaded or parse error: %s", path)

    def load_thesaurus_cache_key(self) -> None:
        """
        Inspect `THESAURUS_CACHE_DIR` on startup:
        - If `.meta.json` contains `thesaurus_key`, use it.
        - Otherwise, if any `.json` files are present, set a sentinel `_cache_present`.
        """
        if getattr(self, "thesaurus_key", None):
            return

        cache_dir = os.path.abspath(THESAURUS_CACHE_DIR)
        if not os.path.isdir(cache_dir):
            return

        meta_path = os.path.join(cache_dir, ".meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as mf:
                    meta = json.load(mf)
                key = meta.get("thesaurus_key")
                if key:
                    self.thesaurus_key = key
                    return
            except Exception:
                logger.debug("Failed to read .meta.json in cache directory.")

        try:
            for fname in os.listdir(cache_dir):
                if fname.endswith(".json") and fname != ".meta.json":
                    self.thesaurus_key = "_cache_present"
                    return
        except Exception:
            logger.debug("Error enumerating cache directory.")