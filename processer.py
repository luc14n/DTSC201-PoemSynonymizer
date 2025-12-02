class processor:
    def __init__(self):
        import json
        self.data = None
        self.words = []
        self.words_type = []
        self.thesaurus_key = None
        self.thesaurus_link = None
        self.gemini_key = None
        self.model = "gemini-2.5-flash-lite"

        self.load_thesaurus_cache_key()

        try:
            with open("config.json", "r", encoding="utf-8") as config_file:
                config = json.load(config_file)
            self.thesaurus_key = config.get("APIKeys", {}).get("thesaurus-key")
            self.thesaurus_link = config.get("APIKeys", {}).get("thesaurus-link")
            self.gemini_key = config.get("APIKeys", {}).get("gemini-key")
        except (FileNotFoundError, json.JSONDecodeError):
            self.thesaurus_key = None
            self.thesaurus_link = None
            self.gemini_key = None

    def process(self, input_data):
        # If caller sent a rebuild command, just rebuild the synonym string
        if isinstance(input_data, dict) and input_data.get("_rebuild"):
            return self.build_synonym_string()

        self.data = input_data
        self.find_type()

        for item in self.words_type:
            try:
                word, pos = item
            except Exception:
                word, pos = (str(item), None)

            # skip thesaurus calls for newline markers
            if word == "_newLine":
                continue

            thesaurus_data = self.get_or_fetch_thesaurus(word)

        results = self.build_synonym_string()
        return results

    def find_type(self, user_input=None):
        import json, requests, re

        print("\n\n\nPINGING GEMINI FOR WORD TYPES\n\n\n")

        # prefer explicit argument, otherwise use the instance data string
        text = user_input if user_input is not None else getattr(self, "data", "")
        if not text or not str(text).strip():
            self.words = []
            self.words_type = []
            return []

        # Tokenize and capture newlines as separate tokens
        # This will yield '\n' tokens as well as word tokens like "don't"
        tokens = re.findall(r"\n|\b\w+(?:'\w+)?\b", str(text))
        # map newline to the special marker _newLine
        words = [t if t != "\n" else "_newLine" for t in tokens]
        self.words = words

        if not words:
            self.words_type = []
            return []

        # local heuristic fallback for POS/type
        def _guess_type(w: str) -> str:
            lw = w.lower()
            if w == "_newLine":
                return "newline"
            if re.match(r'^\W+$', w):
                return "punctuation"
            if re.match(r'^[0-9]+(\.[0-9]+)?$', lw):
                return "numeral"
            pronouns = {"i","you","he","she","it","we","they","me","him","her","us","them","my","your","his","her","our","their","mine","yours"}
            determiners = {"the","a","an","this","that","these","those","some","any","each","every","no","my","your","its"}
            prepositions = {"in","on","at","for","to","from","by","with","about","of","into","over","under","between","among"}
            conjunctions = {"and","but","or","nor","so","yet","for"}
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
            # fallback to noun
            return "noun"

        # If no gemini key, fallback to local guessing
        if not getattr(self, "gemini_key", None):
            self.words_type = [(w, _guess_type(w)) for w in words]
            return self.words_type

        # Prompt: ask model to use the sentence context and return JSON array of [word, type]
        prompt = (
            "Using the sentence and the list of words provided, determine the **word type** (part of speech) "
            "for each word based on its usage in the sentence. Examples of types: noun, verb, adjective, adverb, "
            "pronoun, preposition, conjunction, determiner, numeral, punctuation, other. "
            "Return ONLY a JSON array of arrays in the same order as the words: "
            "[[\"original_word\",\"word_type\"], ...]. Do not include any extra text.\n\n"
            f"Sentence: {json.dumps(str(text))}\n"
            f"Words: {json.dumps(words)}\n\n"
            "Example output: [[\"run\",\"verb\"], [\"quick\",\"adjective\"], [\"the\",\"determiner\"]]"
        )

        url = f"https://generativelanguage.googleapis.com/v1beta2/models/{self.model}:generateText?key={self.gemini_key}"
        payload = {
            "prompt": {"text": prompt},
            "temperature": 0.0,
            "maxOutputTokens": 512,
        }
        headers = {"Content-Type": "application/json"}

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            resp_json = resp.json()

            # Extract text candidate from known response shapes
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
                    # normalize newline tokens from the model to our marker
                    if w == "\n" or w == "_newLine":
                        result.append(("_newLine", "newline"))
                    else:
                        result.append((w, t))
                else:
                    s = str(item)
                    if s == "\n" or s == "_newLine":
                        result.append(("_newLine", "newline"))
                    else:
                        result.append((s, _guess_type(s)))

        except Exception:
            # on any error, fallback to local guessing (including newlines)
            result = [(w, _guess_type(w)) for w in words]

        self.words_type = result
        return result

    def build_synonym_string(self):
        import random

        sentence = ""
        for item in getattr(self, "words_type", []):
            try:
                word, wtype = item
            except Exception:
                # unexpected shape, skip gracefully
                print(f"Warning: unexpected words_type item: {item}")
                continue

            # Handle explicit newline marker
            if word == "_newLine":
                # remove trailing space before newline, ensure newline present
                sentence = sentence.rstrip() + "\n"
                continue

            try:
                entry = self.get_or_fetch_thesaurus(word)
                if not entry:
                    raise ValueError("no thesaurus entry")

                # API may return a list of entry dicts or a single dict
                entries = entry if isinstance(entry, list) else [entry]

                # find entries that match the requested word type exactly
                matching = [e for e in entries if isinstance(e, dict) and e.get("fl") == wtype]

                if not matching:
                    print(f"Warning: no thesaurus entry for type '{wtype}' for word: {word}")
                    chosen = word
                else:
                    # Collect synonyms from matching entries (meta.syns is list of lists)
                    syn_candidates = []
                    for e in matching:
                        meta = e.get("meta", {}) if isinstance(e, dict) else {}
                        for syn_list in meta.get("syns", []):
                            if isinstance(syn_list, list):
                                syn_candidates.extend(syn_list)

                    # remove exact-case duplicates of the original word
                    syn_candidates = [s for s in syn_candidates if isinstance(s, str) and s.lower() != word.lower()]

                    if not syn_candidates:
                        print(f"Warning: no synonyms found for word '{word}' with type '{wtype}'")
                        chosen = word
                    else:
                        chosen = random.choice(syn_candidates)
                        # preserve capitalization of the original word
                        if word and word[0].isupper():
                            chosen = chosen.capitalize()

                # append with correct spacing rules
                if sentence and not sentence.endswith("\n"):
                    sentence += " " + chosen
                else:
                    sentence += chosen

            except Exception as exc:
                # fallback: keep original word and warn
                print(f"Warning: failed to get synonym for '{word}': {exc}")
                if sentence and not sentence.endswith("\n"):
                    sentence += " " + word
                else:
                    sentence += word

        self.synonym_sentence = sentence
        return sentence

    def _safe_filename(self, word: str) -> str:
        import re
        return re.sub(r'[^A-Za-z0-9._-]', '_', word.strip().lower())[:200]

    def get_or_fetch_thesaurus(self, word: str):
        import os, json
        if not word or not word.strip():
            return None

        cache_dir = os.path.abspath("thesaurus_cache")
        safe_name = self._safe_filename(word)
        file_path = os.path.join(cache_dir, f"{safe_name}.json")

        if os.path.exists(file_path):
            try:
                print("Using cached thesaurus data for:", word)
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                pass

        return self.call_thesaurus(word)

    def call_thesaurus(self, word: str):
        import os, json, requests
        if not self.thesaurus_link or not self.thesaurus_key:
            return None
        if not word or not word.strip():
            return None

        try:
            print("Fetching thesaurus data for:", word)
            url = self.thesaurus_link.format(word, self.thesaurus_key)
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()

            cache_dir = os.path.abspath("thesaurus_cache")
            os.makedirs(cache_dir, exist_ok=True)
            safe_name = self._safe_filename(word)
            file_path = os.path.join(cache_dir, f"{safe_name}.json")

            print("Caching thesaurus data for:", word)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            return data

        except requests.RequestException:
            return None
        except (json.JSONDecodeError, OSError):
            return None

    def load_thesaurus_cache_key(self):
        """
        Inspect `thesaurus_cache` on startup:
        - If `.meta.json` exists and contains `thesaurus_key`, use it.
        - Otherwise, if any `.json` files are present, set a sentinel `_cache_present`
          so the instance knows cached entries exist from a previous session.
        - Do nothing if a real key is already set.
        """
        import os, json

        # preserve explicit config key if already loaded
        if getattr(self, "thesaurus_key", None):
            return

        cache_dir = os.path.abspath("thesaurus_cache")
        if not os.path.isdir(cache_dir):
            return

        meta_path = os.path.join(cache_dir, ".meta.json")
        # prefer explicit meta file containing the original key
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as mf:
                    meta = json.load(mf)
                key = meta.get("thesaurus_key")
                if key:
                    self.thesaurus_key = key
                    return
            except Exception:
                pass

        # fallback: if any cached files exist, set a sentinel key
        try:
            for fname in os.listdir(cache_dir):
                if fname.endswith(".json") and fname != ".meta.json":
                    self.thesaurus_key = "_cache_present"
                    return
        except Exception:
            return