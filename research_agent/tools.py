#!/usr/bin/env python3
"""CLI tools for the research agent. Called by Claude Code via Bash."""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import arxiv
import fitz  # pymupdf
import httpx

RESEARCH_NOTES_PATH = Path(__file__).parent / "research_notes.md"
CACHE_DIR = Path(__file__).parent / ".cache"
KB_PATH = Path(__file__).parent / "knowledge_base.json"
MAX_PAPER_CHARS = 20_000

SS_API_BASE = "https://api.semanticscholar.org/graph/v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_arxiv_id(arxiv_id_or_url: str) -> str:
    """Extract a clean arXiv ID from an ID or URL."""
    match = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", arxiv_id_or_url)
    if match:
        return match.group(1)
    return arxiv_id_or_url.strip()


def _cache_path_for(arxiv_id: str) -> Path:
    """Return the cache file path for a given arXiv ID."""
    safe_id = arxiv_id.replace("/", "_").replace(":", "_")
    return CACHE_DIR / f"{safe_id}.txt"


def _ss_request(url: str, params: dict, max_retries: int = 3) -> httpx.Response | None:
    """GET a Semantic Scholar endpoint with exponential backoff on 429."""
    for attempt in range(max_retries):
        try:
            resp = httpx.get(url, params=params, timeout=30.0)
            if resp.status_code == 429:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # 1s, 2s, 4s
                    continue
                print(
                    "Semantic Scholar rate limit (429) after retries. "
                    "Consider spacing calls or getting an API key: "
                    "https://www.semanticscholar.org/product/api#api-key-form"
                )
                return None
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as e:
            print(f"Semantic Scholar API error: {e.response.status_code} — {e.response.text[:200]}")
            return None
        except httpx.RequestError as e:
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            print(f"Request error: {e}")
            return None
    return None


def _parse_page_range(pages_str: str, total: int) -> tuple[int, int]:
    """Parse '3-7', '5', or 'all' into (start_idx, end_idx) 0-based, end exclusive."""
    if not pages_str or pages_str.lower() == "all":
        return 0, total
    if "-" in pages_str:
        a, b = pages_str.split("-", 1)
        return max(0, int(a) - 1), min(total, int(b))
    n = int(pages_str)
    return max(0, n - 1), min(total, n)


def _filter_cached_content(full_content: str, pages_str: str) -> str:
    """Filter cached paper content to a specified page range."""
    if not pages_str or pages_str.lower() == "all":
        return full_content

    first_page = re.search(r"--- Page 1 ---", full_content)
    if not first_page:
        return full_content

    header = full_content[: first_page.start()]
    body = full_content[first_page.start() :]

    # Split into per-page chunks; each starts with "--- Page N ---"
    page_chunks = re.split(r"(?=--- Page \d+ ---)", body)
    page_chunks = [c for c in page_chunks if c.strip()]

    total = len(page_chunks)
    start_idx, end_idx = _parse_page_range(pages_str, total)
    selected = page_chunks[start_idx:end_idx]

    return header + "".join(selected) + f"\n[Pages {pages_str} of {total} total]"


# ---------------------------------------------------------------------------
# arXiv search
# ---------------------------------------------------------------------------

def cmd_search(args: argparse.Namespace) -> None:
    """Search arXiv for papers."""
    sort_criterion = (
        arxiv.SortCriterion.Relevance
        if args.sort_by == "relevance"
        else arxiv.SortCriterion.SubmittedDate
    )

    client = arxiv.Client()
    search = arxiv.Search(
        query=args.query,
        max_results=args.max_results,
        sort_by=sort_criterion,
    )

    results = []
    for paper in client.results(search):
        entry = {
            "title": paper.title,
            "authors": ", ".join(a.name for a in paper.authors[:5]),
            "abstract": paper.summary[:500],
            "arxiv_id": paper.entry_id.split("/")[-1].split("v")[0],
            "pdf_url": paper.pdf_url,
            "published": paper.published.strftime("%Y-%m-%d"),
            "categories": paper.categories[:3],
        }
        if len(paper.authors) > 5:
            entry["authors"] += f" (+{len(paper.authors) - 5} more)"
        results.append(entry)

    if not results:
        print("No results found. Try a different query.")
    else:
        print(json.dumps(results, indent=2))


# ---------------------------------------------------------------------------
# Paper reading with caching and page targeting
# ---------------------------------------------------------------------------

def cmd_read(args: argparse.Namespace) -> None:
    """Download and read a paper from arXiv, using cache when available."""
    arxiv_id = _extract_arxiv_id(args.arxiv_id)
    cache_file = _cache_path_for(arxiv_id)
    pages_str = getattr(args, "pages", None)

    # Check cache first
    if cache_file.exists():
        full_content = cache_file.read_text(encoding="utf-8")
        content = _filter_cached_content(full_content, pages_str) if pages_str else full_content
        if len(content) > MAX_PAPER_CHARS:
            content = (
                content[:MAX_PAPER_CHARS]
                + f"\n\n[... TRUNCATED at {MAX_PAPER_CHARS} chars. "
                f"Full paper: {len(full_content)} chars. (cached) ...]"
            )
        print(content)
        return

    client = arxiv.Client()
    search = arxiv.Search(id_list=[arxiv_id])
    results = list(client.results(search))

    if not results:
        print(f"Paper not found: {arxiv_id}")
        return

    paper = results[0]

    response = httpx.get(paper.pdf_url, follow_redirects=True, timeout=60.0)
    if response.status_code != 200:
        print(f"Failed to download PDF (status {response.status_code})")
        return

    doc = fitz.open(stream=response.content, filetype="pdf")
    full_text = []
    for page_num, page in enumerate(doc):
        text = page.get_text()
        if text.strip():
            full_text.append(f"--- Page {page_num + 1} ---\n{text}")
    doc.close()

    header = (
        f"Title: {paper.title}\n"
        f"Authors: {', '.join(a.name for a in paper.authors)}\n"
        f"Published: {paper.published.strftime('%Y-%m-%d')}\n"
        f"arXiv ID: {arxiv_id}\n"
        f"Total Pages: {len(full_text)}\n"
        f"{'=' * 60}\n\n"
    )

    full_content = header + "\n".join(full_text)

    # Always cache the full document
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(full_content, encoding="utf-8")

    # Apply page filter for output
    if pages_str:
        start_idx, end_idx = _parse_page_range(pages_str, len(full_text))
        selected = full_text[start_idx:end_idx]
        output_content = (
            header
            + "\n".join(selected)
            + f"\n[Pages {pages_str} of {len(full_text)} total]"
        )
    else:
        output_content = full_content

    if len(output_content) > MAX_PAPER_CHARS:
        output_content = (
            output_content[:MAX_PAPER_CHARS]
            + f"\n\n[... TRUNCATED at {MAX_PAPER_CHARS} chars. "
            f"Full paper: {len(full_content)} chars. ...]"
        )

    print(output_content)


# ---------------------------------------------------------------------------
# Cache management CLI
# ---------------------------------------------------------------------------

def cmd_cache(args: argparse.Namespace) -> None:
    """Manage the paper cache."""
    action = args.action

    if action == "stats":
        if not CACHE_DIR.exists():
            print(json.dumps({"files": 0, "total_bytes": 0, "total_mb": 0.0}))
            return
        files = list(CACHE_DIR.glob("*.txt"))
        total_bytes = sum(f.stat().st_size for f in files)
        print(json.dumps({
            "files": len(files),
            "total_bytes": total_bytes,
            "total_mb": round(total_bytes / (1024 * 1024), 2),
        }, indent=2))

    elif action == "list":
        if not CACHE_DIR.exists():
            print(json.dumps([]))
            return
        files = sorted(CACHE_DIR.glob("*.txt"), key=lambda f: f.stat().st_mtime, reverse=True)
        entries = []
        for f in files:
            entries.append({
                "arxiv_id": f.stem,
                "size_kb": round(f.stat().st_size / 1024, 1),
                "cached_at": datetime.fromtimestamp(
                    f.stat().st_mtime, tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M"),
            })
        print(json.dumps(entries, indent=2))

    elif action == "clear":
        if not CACHE_DIR.exists():
            print("Cache directory does not exist. Nothing to clear.")
            return
        files = list(CACHE_DIR.glob("*.txt"))
        for f in files:
            f.unlink()
        print(f"Cleared {len(files)} cached papers.")


# ---------------------------------------------------------------------------
# Semantic Scholar search — with retry on 429
# ---------------------------------------------------------------------------

def cmd_search_ss(args: argparse.Namespace) -> None:
    """Search Semantic Scholar for papers."""
    params = {
        "query": args.query,
        "limit": min(args.max_results, 100),
        "fields": "title,authors,year,abstract,citationCount,influentialCitationCount,venue,externalIds,tldr",
    }
    if args.year:
        params["year"] = args.year

    resp = _ss_request(f"{SS_API_BASE}/paper/search", params)
    if resp is None:
        return

    papers = resp.json().get("data", [])
    if not papers:
        print("No results found on Semantic Scholar.")
        return

    results = []
    for p in papers:
        entry = {
            "title": p.get("title", ""),
            "authors": ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:5]),
            "year": p.get("year"),
            "venue": p.get("venue", ""),
            "citation_count": p.get("citationCount", 0),
            "influential_citations": p.get("influentialCitationCount", 0),
            "paper_id": p.get("paperId", ""),
        }

        ext_ids = p.get("externalIds") or {}
        if ext_ids.get("ArXiv"):
            entry["arxiv_id"] = ext_ids["ArXiv"]
        if ext_ids.get("DOI"):
            entry["doi"] = ext_ids["DOI"]

        tldr = p.get("tldr")
        if tldr and isinstance(tldr, dict):
            entry["tldr"] = tldr.get("text", "")

        entry["abstract"] = (p.get("abstract") or "")[:400]
        results.append(entry)

    print(json.dumps(results, indent=2))


# ---------------------------------------------------------------------------
# Citation graph traversal — with retry on 429
# ---------------------------------------------------------------------------

def cmd_citations(args: argparse.Namespace) -> None:
    """Get citations and/or references for a paper via Semantic Scholar."""
    paper_id = args.paper_id

    # Auto-prefix arXiv IDs
    if re.match(r"^\d{4}\.\d{4,5}$", paper_id):
        paper_id = f"ArXiv:{paper_id}"

    fields = "title,authors,year,citationCount,externalIds,venue"
    result = {}

    directions = []
    if args.direction in ("citing", "both"):
        directions.append(("citations", "citingPaper"))
    if args.direction in ("references", "both"):
        directions.append(("references", "citedPaper"))

    for endpoint, paper_key in directions:
        resp = _ss_request(
            f"{SS_API_BASE}/paper/{paper_id}/{endpoint}",
            {"fields": fields, "limit": min(args.max_results, 100)},
        )
        if resp is None:
            result[endpoint] = {"error": "Request failed (rate limit or network error)"}
            continue

        entries = []
        for item in resp.json().get("data", []):
            p = item.get(paper_key, {})
            if not p or not p.get("title"):
                continue
            entry = {
                "title": p.get("title", ""),
                "authors": ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:3]),
                "year": p.get("year"),
                "citation_count": p.get("citationCount", 0),
                "venue": p.get("venue", ""),
                "paper_id": p.get("paperId", ""),
            }
            ext_ids = p.get("externalIds") or {}
            if ext_ids.get("ArXiv"):
                entry["arxiv_id"] = ext_ids["ArXiv"]
            entries.append(entry)

        entries.sort(key=lambda e: e.get("citation_count", 0), reverse=True)
        result[endpoint] = entries

    print(json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# Structured knowledge base
# ---------------------------------------------------------------------------

def _load_kb() -> dict:
    if KB_PATH.exists():
        return json.loads(KB_PATH.read_text(encoding="utf-8"))
    return {"papers": {}, "meta": {"created": datetime.now(timezone.utc).isoformat()}}


def _save_kb(kb: dict) -> None:
    kb["meta"]["updated"] = datetime.now(timezone.utc).isoformat()
    KB_PATH.write_text(json.dumps(kb, indent=2, ensure_ascii=False), encoding="utf-8")


def cmd_kb(args: argparse.Namespace) -> None:
    """Manage the structured knowledge base."""
    action = args.kb_action
    kb = _load_kb()

    if action == "add":
        paper_id = args.paper_id
        entry = {
            "title": args.title or "",
            "authors": args.authors or "",
            "year": args.year or "",
            "tags": [t.strip() for t in (args.tags or "").split(",") if t.strip()],
            "key_findings": args.key_findings or "",
            "relevance_score": float(args.relevance_score) if args.relevance_score else 0.0,
            "connections": [c.strip() for c in (args.connections or "").split(",") if c.strip()],
            "notes": args.notes or "",
            "added": datetime.now(timezone.utc).isoformat(),
        }

        kb["papers"][paper_id] = entry

        # Add bidirectional connections
        for conn_id in entry["connections"]:
            if conn_id in kb["papers"]:
                conn_paper = kb["papers"][conn_id]
                if paper_id not in conn_paper.get("connections", []):
                    conn_paper.setdefault("connections", []).append(paper_id)

        _save_kb(kb)
        print(f"Added paper '{entry['title']}' ({paper_id}) to knowledge base.")

    elif action == "search":
        query = (args.search_query or "").lower()
        if not query:
            print("Please provide a search query with --query.")
            return

        matches = []
        for pid, p in kb["papers"].items():
            searchable = " ".join([
                p.get("title", ""),
                p.get("key_findings", ""),
                " ".join(p.get("tags", [])),
                p.get("notes", ""),
            ]).lower()
            if query in searchable:
                matches.append({"paper_id": pid, **p})

        if matches:
            print(json.dumps(matches, indent=2))
        else:
            print(f"No papers matching '{query}' in knowledge base.")

    elif action == "list":
        if not kb["papers"]:
            print("Knowledge base is empty.")
            return
        entries = []
        for pid, p in kb["papers"].items():
            entries.append({
                "paper_id": pid,
                "title": p.get("title", ""),
                "tags": p.get("tags", []),
                "relevance_score": p.get("relevance_score", 0),
                "connections": p.get("connections", []),
            })
        entries.sort(key=lambda e: e.get("relevance_score", 0), reverse=True)
        print(json.dumps(entries, indent=2))

    elif action == "connections":
        paper_id = args.paper_id
        if not paper_id:
            print("Please provide --paper-id.")
            return
        if paper_id not in kb["papers"]:
            print(f"Paper '{paper_id}' not found in knowledge base.")
            return
        paper = kb["papers"][paper_id]
        connected = []
        for cid in paper.get("connections", []):
            if cid in kb["papers"]:
                cp = kb["papers"][cid]
                connected.append({"paper_id": cid, "title": cp.get("title", ""), "tags": cp.get("tags", [])})
            else:
                connected.append({"paper_id": cid, "title": "(not in KB)", "tags": []})
        print(json.dumps({
            "paper_id": paper_id,
            "title": paper.get("title", ""),
            "connections": connected,
        }, indent=2))

    elif action == "export":
        if not kb["papers"]:
            print("Knowledge base is empty.")
            return
        lines = ["# Research Knowledge Base\n"]
        lines.append(f"*Exported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*\n")
        lines.append(f"**Total papers**: {len(kb['papers'])}\n")

        tag_groups: dict[str, list] = {}
        for pid, p in kb["papers"].items():
            for tag in (p.get("tags") or ["untagged"]):
                tag_groups.setdefault(tag, []).append((pid, p))

        for tag in sorted(tag_groups.keys()):
            lines.append(f"\n## {tag}\n")
            for pid, p in tag_groups[tag]:
                lines.append(f"### {p.get('title', pid)}")
                lines.append(f"- **ID**: {pid}")
                lines.append(f"- **Authors**: {p.get('authors', 'N/A')}")
                lines.append(f"- **Year**: {p.get('year', 'N/A')}")
                lines.append(f"- **Relevance**: {p.get('relevance_score', 'N/A')}/10")
                if p.get("key_findings"):
                    lines.append(f"- **Key Findings**: {p['key_findings']}")
                if p.get("connections"):
                    lines.append(f"- **Connected to**: {', '.join(p['connections'])}")
                if p.get("notes"):
                    lines.append(f"- **Notes**: {p['notes']}")
                lines.append("")

        print("\n".join(lines))


# ---------------------------------------------------------------------------
# Legacy: note command
# ---------------------------------------------------------------------------

def cmd_note(args: argparse.Namespace) -> None:
    """Append a paper entry to research_notes.md."""
    notes_path = RESEARCH_NOTES_PATH

    if notes_path.exists():
        existing = notes_path.read_text(encoding="utf-8")
        if args.arxiv_id in existing:
            print(f"Paper {args.arxiv_id} already in research notes. Skipping.")
            return
    else:
        existing = ""

    if not existing:
        existing = "# Research Notes\n\n"

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    entry = f"""## Paper: {args.title}
- **arXiv**: https://arxiv.org/abs/{args.arxiv_id}
- **Date Reviewed**: {today}
- **Authors**: {args.authors}
- **Summary**: {args.summary}
- **Key Findings**:
{args.key_findings}
- **Relevance to Project**: [{args.relevance}] - {args.relevance_explanation}
- **Ideas for Our Project**:
{args.ideas}

---

"""

    notes_path.write_text(existing + entry, encoding="utf-8")
    print(f"Added '{args.title}' ({args.arxiv_id}) to research notes.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Research agent tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # search (arXiv)
    p_search = subparsers.add_parser("search", help="Search arXiv")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--max-results", type=int, default=10)
    p_search.add_argument("--sort-by", choices=["relevance", "date"], default="relevance")
    p_search.set_defaults(func=cmd_search)

    # search-ss (Semantic Scholar)
    p_ss = subparsers.add_parser("search-ss", help="Search Semantic Scholar")
    p_ss.add_argument("query", help="Search query")
    p_ss.add_argument("--max-results", type=int, default=10)
    p_ss.add_argument("--year", help="Year filter, e.g. '2023' or '2023-2024'")
    p_ss.set_defaults(func=cmd_search_ss)

    # read
    p_read = subparsers.add_parser("read", help="Read a paper (cached)")
    p_read.add_argument("arxiv_id", help="arXiv ID or URL")
    p_read.add_argument(
        "--pages",
        help="Page range to extract, e.g. '4-8', '5', or 'all' (default: all, truncated to 20k chars)",
        default=None,
    )
    p_read.set_defaults(func=cmd_read)

    # citations
    p_cite = subparsers.add_parser("citations", help="Get citations/references via Semantic Scholar")
    p_cite.add_argument("paper_id", help="arXiv ID or Semantic Scholar paper ID")
    p_cite.add_argument("--direction", choices=["citing", "references", "both"], default="both")
    p_cite.add_argument("--max-results", type=int, default=20)
    p_cite.set_defaults(func=cmd_citations)

    # cache
    p_cache = subparsers.add_parser("cache", help="Manage paper cache")
    p_cache.add_argument("action", choices=["stats", "list", "clear"])
    p_cache.set_defaults(func=cmd_cache)

    # kb (knowledge base)
    p_kb = subparsers.add_parser("kb", help="Structured knowledge base")
    p_kb.add_argument("kb_action", choices=["add", "search", "list", "connections", "export"])
    p_kb.add_argument("--paper-id")
    p_kb.add_argument("--title")
    p_kb.add_argument("--authors")
    p_kb.add_argument("--year")
    p_kb.add_argument("--tags", help="Comma-separated tags")
    p_kb.add_argument("--key-findings")
    p_kb.add_argument("--relevance-score", type=float)
    p_kb.add_argument("--connections", help="Comma-separated paper IDs this paper connects to")
    p_kb.add_argument("--notes")
    p_kb.add_argument("--query", dest="search_query", help="Search query for kb search")
    p_kb.set_defaults(func=cmd_kb)

    # note (legacy)
    p_note = subparsers.add_parser("note", help="Add paper to research notes (legacy)")
    p_note.add_argument("--title", required=True)
    p_note.add_argument("--arxiv-id", required=True)
    p_note.add_argument("--authors", required=True)
    p_note.add_argument("--summary", required=True)
    p_note.add_argument("--key-findings", required=True)
    p_note.add_argument("--relevance", required=True, choices=["High", "Medium", "Low"])
    p_note.add_argument("--relevance-explanation", required=True)
    p_note.add_argument("--ideas", required=True)
    p_note.set_defaults(func=cmd_note)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
