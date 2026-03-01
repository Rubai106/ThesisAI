"""Tool definitions and implementations for ThesisAI.

Each tool is exposed to the OpenAI function-calling API and also has a
local execution handler.  Tools cover web search, paper analysis,
experiment design, code generation, writing improvement, and viva prep.
"""

import json
import re
import textwrap
from typing import Any

import requests
from bs4 import BeautifulSoup

# ══════════════════════════════════════════════════════════════════
#  TOOL SCHEMAS  (OpenAI function-calling format)
# ══════════════════════════════════════════════════════════════════

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for academic papers, datasets, documentation, "
                "or technical information. Prefer arXiv, Google Scholar, IEEE, ACM. "
                "Returns a list of results with titles, snippets, and URLs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query string.",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return (default 5).",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_page",
            "description": (
                "Fetch and extract the main text content from a web page URL. "
                "Useful for reading full paper abstracts, documentation, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch.",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_paper",
            "description": (
                "Extract structured information from a paper given its text or URL. "
                "Returns: problem statement, methodology, dataset, evaluation metrics, "
                "key results, limitations, and contributions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "paper_text": {
                        "type": "string",
                        "description": "The full text or abstract of the paper to analyze.",
                    },
                    "paper_title": {
                        "type": "string",
                        "description": "Title of the paper (optional).",
                    },
                },
                "required": ["paper_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_papers",
            "description": (
                "Build a structured comparison table across multiple papers. "
                "Compares methodology, dataset, metrics, and results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "papers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "methodology": {"type": "string"},
                                "dataset": {"type": "string"},
                                "metrics": {"type": "string"},
                                "results": {"type": "string"},
                            },
                        },
                        "description": "Array of paper objects to compare.",
                    },
                },
                "required": ["papers"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_experiments",
            "description": (
                "Given a research topic or gap, propose experiment designs with "
                "baseline models, evaluation metrics, datasets, and risk analysis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The research topic or gap to address.",
                    },
                    "constraints": {
                        "type": "string",
                        "description": "Any constraints (compute, time, etc.).",
                    },
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_code",
            "description": (
                "Generate clean, well-commented Python code for a specified task "
                "(model training, data processing, evaluation, visualization, etc.)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "What the code should accomplish.",
                    },
                    "language": {
                        "type": "string",
                        "description": "Programming language (default: Python).",
                        "default": "python",
                    },
                },
                "required": ["task_description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "improve_writing",
            "description": (
                "Rewrite informal or rough text in academic style, improve "
                "clarity and coherence, and suggest citation placement."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to improve.",
                    },
                    "style": {
                        "type": "string",
                        "description": "Target style: 'academic', 'technical', 'concise'.",
                        "default": "academic",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_viva_questions",
            "description": (
                "Generate likely thesis defense/viva questions and suggest strong answers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "thesis_topic": {
                        "type": "string",
                        "description": "The thesis topic.",
                    },
                    "methodology": {
                        "type": "string",
                        "description": "The methodology used.",
                    },
                    "num_questions": {
                        "type": "integer",
                        "description": "Number of questions to generate (default 10).",
                        "default": 10,
                    },
                },
                "required": ["thesis_topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_citations",
            "description": (
                "Generate properly formatted academic citations/references from "
                "paper information. Supports APA, IEEE, and Harvard citation styles. "
                "Returns formatted citation strings ready for a bibliography."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "papers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "authors": {"type": "string"},
                                "year": {"type": "string"},
                                "venue": {"type": "string"},
                                "url": {"type": "string"},
                            },
                        },
                        "description": "Array of paper objects to cite.",
                    },
                    "style": {
                        "type": "string",
                        "description": "Citation style: 'apa', 'ieee', or 'harvard'. Default 'apa'.",
                        "default": "apa",
                    },
                },
                "required": ["papers"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "paraphrase_text",
            "description": (
                "Paraphrase the given text to avoid plagiarism while preserving meaning. "
                "Produces academic-quality rewritten text with a plagiarism-safe structure."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to paraphrase.",
                    },
                    "tone": {
                        "type": "string",
                        "description": "Target tone: 'formal', 'academic', 'simplified'. Default 'academic'.",
                        "default": "academic",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_abstract",
            "description": (
                "Generate a thesis abstract based on the topic, methodology, "
                "key findings, and conclusions. Produces a structured 150-300 word abstract."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The thesis topic.",
                    },
                    "methodology": {
                        "type": "string",
                        "description": "Research methodology used.",
                    },
                    "findings": {
                        "type": "string",
                        "description": "Key findings or expected results.",
                    },
                    "word_limit": {
                        "type": "integer",
                        "description": "Word limit for the abstract (default: 250).",
                        "default": 250,
                    },
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_research_timeline",
            "description": (
                "Generate a research timeline/schedule with milestones, "
                "deliverables, and deadlines based on the thesis topic and deadline."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The thesis topic.",
                    },
                    "deadline": {
                        "type": "string",
                        "description": "Final submission deadline.",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "When the work starts (default: now).",
                    },
                    "chapters": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of chapter titles.",
                    },
                },
                "required": ["topic", "deadline"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "Save important context to persistent memory: thesis topic, "
                "research area, methodology, discussed papers, decisions, or notes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "description": (
                            "Which memory field to update. Must be one of: "
                            "thesis_topic, research_area, methodology, paper, "
                            "decision, note."
                        ),
                    },
                    "value": {
                        "type": "string",
                        "description": "The value to store.",
                    },
                    "extra": {
                        "type": ["string", "null"],
                        "description": "Additional info (e.g. paper summary or URL). Optional.",
                        "default": "",
                    },
                },
                "required": ["field", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_thesis_outline",
            "description": (
                "Generate a complete thesis outline with chapter titles, "
                "section headings, and brief descriptions of what each section "
                "should contain. Based on the user's topic and research area."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The thesis topic.",
                    },
                    "research_area": {
                        "type": "string",
                        "description": "The research area or domain.",
                    },
                    "num_chapters": {
                        "type": "integer",
                        "description": "Number of chapters (default: 6).",
                        "default": 6,
                    },
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_chapter_draft",
            "description": (
                "Write a detailed first draft for a specific thesis chapter or "
                "section. Produces academic-quality prose with proper structure, "
                "placeholder citations [AuthorYear], and logical flow. "
                "The user can then refine and add their own data/results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter_title": {
                        "type": "string",
                        "description": "Title of the chapter (e.g. 'Literature Review', 'Methodology').",
                    },
                    "chapter_number": {
                        "type": "integer",
                        "description": "Chapter number.",
                    },
                    "thesis_topic": {
                        "type": "string",
                        "description": "The overall thesis topic for context.",
                    },
                    "key_points": {
                        "type": ["string", "null"],
                        "description": "Specific points, methods, or papers to cover in this chapter. Optional.",
                        "default": "",
                    },
                    "word_count_target": {
                        "type": "integer",
                        "description": "Approximate target word count (default: 2000).",
                        "default": 2000,
                    },
                },
                "required": ["chapter_title", "thesis_topic"],
            },
        },
    },
]


# ══════════════════════════════════════════════════════════════════
#  TOOL IMPLEMENTATIONS
# ══════════════════════════════════════════════════════════════════

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _web_search(query: str, num_results: int = 5) -> str:
    """Perform a DuckDuckGo HTML search and return results."""
    try:
        url = "https://html.duckduckgo.com/html/"
        resp = requests.post(
            url, data={"q": query}, headers=_HEADERS, timeout=15
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        results = []
        for i, item in enumerate(soup.select(".result")):
            if i >= num_results:
                break
            title_el = item.select_one(".result__title a")
            snippet_el = item.select_one(".result__snippet")
            if title_el:
                title = title_el.get_text(strip=True)
                link = title_el.get("href", "")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                results.append(
                    {"title": title, "url": link, "snippet": snippet}
                )

        if not results:
            return json.dumps({"message": "No results found.", "results": []})
        return json.dumps({"results": results}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": f"Search failed: {exc}"})


def _fetch_page(url: str) -> str:
    """Fetch and extract main text from a URL."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove scripts, styles, navs
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # Collapse whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Truncate to ~8000 chars to stay within context
        if len(text) > 8000:
            text = text[:8000] + "\n\n[...truncated]"
        return json.dumps({"url": url, "content": text}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": f"Fetch failed: {exc}"})


def _compare_papers(papers: list[dict]) -> str:
    """Build a Markdown comparison table."""
    if not papers:
        return json.dumps({"error": "No papers provided."})

    cols = ["Title", "Methodology", "Dataset", "Metrics", "Results"]
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = [header, sep]
    for p in papers:
        row = "| " + " | ".join(
            [
                p.get("title", "N/A"),
                p.get("methodology", "N/A"),
                p.get("dataset", "N/A"),
                p.get("metrics", "N/A"),
                p.get("results", "N/A"),
            ]
        ) + " |"
        rows.append(row)
    return "\n".join(rows)


# ── Dispatch ─────────────────────────────────────────────────────

def execute_tool(name: str, arguments: dict[str, Any], memory_manager=None) -> str:
    """Route a tool call to the correct handler and return a string result."""

    if name == "web_search":
        return _web_search(
            query=arguments["query"],
            num_results=arguments.get("num_results", 5),
        )

    if name == "fetch_page":
        return _fetch_page(url=arguments["url"])

    if name == "compare_papers":
        return _compare_papers(papers=arguments["papers"])

    # Tools that are handled by the LLM itself (the model generates the
    # content and we just acknowledge the call).
    if name in (
        "analyze_paper",
        "suggest_experiments",
        "generate_code",
        "improve_writing",
        "generate_viva_questions",
        "generate_thesis_outline",
        "write_chapter_draft",
        "generate_citations",
        "paraphrase_text",
        "generate_abstract",
        "generate_research_timeline",
    ):
        # These are "thinking" tools — the LLM produces the output as part
        # of its response.  We return a confirmation so the model can
        # proceed with its chain-of-thought.
        return json.dumps({"status": "ok", "note": f"Processed by model: {name}"})

    if name == "save_memory" and memory_manager is not None:
        field = arguments.get("field", "").lower().strip()
        value = arguments.get("value", "") or ""
        extra = arguments.get("extra") or ""

        # Fuzzy-match common model hallucinations to valid fields
        _FIELD_ALIASES = {
            "thesis_topic": "thesis_topic",
            "thesis_type": "thesis_topic",
            "topic": "thesis_topic",
            "thesis": "thesis_topic",
            "research_area": "research_area",
            "area": "research_area",
            "research": "research_area",
            "methodology": "methodology",
            "method": "methodology",
            "paper": "paper",
            "papers": "paper",
            "decision": "decision",
            "note": "note",
            "notes": "note",
        }
        field = _FIELD_ALIASES.get(field, field)

        if field == "thesis_topic":
            memory_manager.set_thesis_topic(value)
        elif field == "research_area":
            memory_manager.set_research_area(value)
        elif field == "methodology":
            memory_manager.set_methodology(value)
        elif field == "paper":
            memory_manager.add_paper(title=value, summary=extra)
        elif field == "decision":
            memory_manager.add_decision(value)
        elif field == "note":
            memory_manager.add_note(value)
        else:
            # Fall back to saving as a note
            memory_manager.add_note(f"[{field}] {value}")
        return json.dumps({"status": "saved", "field": field, "value": value})

    return json.dumps({"error": f"Unknown tool: {name}"})
