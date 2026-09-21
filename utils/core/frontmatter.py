"""One place that turns a dict into a YAML frontmatter block.

Every corpus writer that built its own block with an f-string has eventually
produced invalid YAML. `precision_repair_kb` wrote
`f"keywords: [{', '.join(keywords)}]"`, which turns a block-style list into a
flow sequence full of `- ` entries; that single line left 1,074 of 6,741 corpus
files unparseable. The same shape waits in any `f'summary: "{text}"'` the moment
the text contains a quote, a backslash or a colon — and the values interpolated
this way are forum usernames and book titles, which nobody controls.

Nothing catches it downstream: the RAG indexer reads frontmatter with line
regexes rather than a parser, so retrieval keeps working while the block is
unreadable to everything that does parse it.

    >>> dump_frontmatter({"summary": 'He said "no"', "keywords": ["a", "b"]})
    '---\\nsummary: He said "no"\\nkeywords:\\n- a\\n- b\\n---\\n'
"""
from __future__ import annotations

from typing import Any, Mapping

import yaml


def dump_frontmatter(data: Mapping[str, Any]) -> str:
    """Render `data` as a complete `---`-fenced YAML block, trailing newline included.

    Key order is preserved rather than sorted: these blocks are read by people,
    and `title`/`summary` belong at the top.
    """
    body = yaml.safe_dump(
        dict(data),
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    return f"---\n{body}---\n"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """(frontmatter, body). Raises `yaml.YAMLError` if the block does not parse.

    Deliberately not returning `{}` on a parse error: treating a broken block as
    an absent one is what made `enrich_metadata` prepend a *second* block on top
    of the first, on 60 files in a single pass. A caller that wants to tolerate
    it must say so.
    """
    if not text.startswith("---\n"):
        return {}, text
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return {}, text
    data = yaml.safe_load(parts[1])
    if not isinstance(data, dict):
        data = {}
    return data, parts[2]
