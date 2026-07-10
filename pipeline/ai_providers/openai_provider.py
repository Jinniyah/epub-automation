"""OpenAI-backed AIProvider -- ported from epub-renamer/ai_providers/
openai_provider.py (ADR-0003, ADR-0014).

Adapted from the original: the source tool read `OPENAI_API_KEY` from its
own `.env`-backed `config.py` module at import time. This project's key is
per-install and user-supplied via settings.json (ADR-0003), so the key is
passed explicitly to the constructor instead of read from a module-level
config -- a changed constraint (settings.json replaces .env as the config
source for the GUI/CLI-shared pipeline), not a redesign. The prompt,
JSON-parsing fallback, and model choice are otherwise unchanged.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from openai import OpenAI

from pipeline.ai_providers.base import AIProvider, parse_json_object

TEXT_SAMPLE_LENGTH = 5000

_PROMPT_TEMPLATE = """
You are a professional bibliographic metadata engine.

Your job is to normalize book metadata into clean fields for filename generation.

You MUST return ONLY valid JSON with exactly these fields:
- "title": the book's title ONLY, with NO series name, NO series number, NO
  character name, NO parentheses info, NO "Book 13".
- "author_first": the primary author's first name.
- "author_last": the primary author's last name.
- "series": the series name ONLY (e.g., "Kay Scarpetta", "Jack Reacher",
  "Nora Kelly"), or null if not part of a series.
- "series_number": the book's number in the series as an integer, or null
  if not part of a series.

### RULES ###
- You MAY use your general knowledge of published books and series.
- You MAY use the filename to infer series and series_number.
- You MUST remove all series-related text from the "title" field.
- If the filename contains series info (e.g., "(Nora Kelly)", "(Jack
  Reacher)", "(Book 13)"), extract it into "series" and "series_number".
- If the EPUB metadata contradicts known series information, prefer your
  general knowledge.
- If you truly cannot determine the series, return null for both fields.
- Respond ONLY with a single JSON object. No explanation, no prose.

### Examples of correct normalization ###

Input filename: "Trace_ Scarpetta (Book 13) (Kay Scarpetta)_nodrm.epub"
Output:
{{
  "title": "Trace",
  "author_first": "Patricia",
  "author_last": "Cornwell",
  "series": "Kay Scarpetta",
  "series_number": 13
}}

Input filename: "White Fire (Pendergast Book 13)_nodrm.epub"
Output:
{{
  "title": "White Fire",
  "author_first": "Douglas",
  "author_last": "Preston",
  "series": "Pendergast",
  "series_number": 13
}}

### Provided filename ###
{filename}

### Provided EPUB metadata ###
{metadata_json}

### Text sample ###
{text_sample}
"""

_RESULT_KEYS = ["title", "author_first", "author_last", "series", "series_number"]


class OpenAIProvider(AIProvider):
    """OpenAI-backed implementation of AIProvider."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("OpenAI API key is not set")
        self.client = OpenAI(api_key=api_key)

    def identify_book(
        self, filename: str, metadata: Dict[str, Any], text_sample: str
    ) -> Dict[str, Any]:
        prompt = _PROMPT_TEMPLATE.format(
            filename=filename,
            metadata_json=json.dumps(metadata, indent=2),
            text_sample=text_sample[:TEXT_SAMPLE_LENGTH],
        )

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )

        content = response.choices[0].message.content
        parsed = parse_json_object(content)

        for key in _RESULT_KEYS:
            parsed.setdefault(key, None)

        return parsed
