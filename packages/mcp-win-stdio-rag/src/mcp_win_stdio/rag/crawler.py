#!/usr/bin/env python3
"""
Playwright-powered Automated Section-Aware Documentation Crawler and Link Graph Builder.
Supports Single-Page API docs with Anchor ID deep-links (e.g. Zenodo, Slate, Redoc).
"""

import hashlib
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import networkx as nx
from playwright.async_api import async_playwright


def get_domain_hash(url: str) -> str:
    """Generate a stable folder hash for a target URL domain."""
    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path
    return hashlib.md5(domain.encode("utf-8")).hexdigest()[:12]


def normalize_canonical_url(url: str, base_url: str) -> str:
    """Normalize URL, enforce HTTPS, strip tracking params and URL fragments."""
    joined = urljoin(base_url, url)
    parsed = urlparse(joined)
    scheme = "https" if parsed.scheme in ("http", "https") else parsed.scheme
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    if not path:
        path = "/"
    return f"{scheme}://{netloc}{path}"


class AsyncPlaywrightCrawler:
    """Async Web Crawler with Section & Anchor-Aware Knowledge Graph Generation."""

    def __init__(self, target_url: str, max_depth: int = 2, max_pages: int = 40):
        self.target_url = target_url
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.domain = urlparse(target_url).netloc.lower()
        self.visited_urls: Set[str] = set()
        self.graph = nx.DiGraph()
        self.pages_data: List[Dict[str, Any]] = []

    def _is_same_domain(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.netloc.lower() == self.domain or not parsed.netloc

    async def crawl(self) -> Dict[str, Any]:
        """Crawl target site and extract section-aware chunks and deep-link anchors."""
        queue: List[Tuple[str, int, Optional[str]]] = [(self.target_url, 0, None)]
        total_sections_count = 0

        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless=True)
            except Exception as e:
                err_text = str(e)
                if "Executable doesn't exist" in err_text or "playwright install" in err_text:
                    import subprocess
                    import sys

                    sys.stderr.write("Playwright Chromium browser missing. Installing automatically...\n")
                    sys.stderr.flush()
                    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
                    browser = await p.chromium.launch(headless=True)
                else:
                    raise
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Antigravity-RAG-Crawler/1.0"
            )
            page = await context.new_page()

            while queue and len(self.visited_urls) < self.max_pages:
                current_url, depth, parent_url = queue.pop(0)
                norm_url = normalize_canonical_url(current_url, self.target_url)

                if norm_url in self.visited_urls or depth > self.max_depth:
                    continue

                self.visited_urls.add(norm_url)
                self.graph.add_node(norm_url, depth=depth)

                if parent_url:
                    self.graph.add_edge(parent_url, norm_url)

                try:
                    await page.goto(norm_url, timeout=18000, wait_until="domcontentloaded")
                    title = await page.title()

                    # Extract all sections with their anchor IDs via JavaScript DOM traversal
                    sections_data = await page.evaluate("""
                        () => {
                            const headings = Array.from(document.querySelectorAll('h1, h2, h3, h4, section[id], article[id]'));
                            const results = [];
                            
                            if (headings.length === 0) {
                                // Fallback for pages without standard headings
                                results.push({
                                    anchor_id: '',
                                    section_title: document.title || 'Main',
                                    text: document.body ? document.body.innerText.trim() : ''
                                });
                                return results;
                            }

                            for (let i = 0; i < headings.length; i++) {
                                const current = headings[i];
                                const anchor_id = current.id || current.getAttribute('name') || '';
                                const section_title = current.innerText.trim();
                                
                                // Collect text content between this heading and the next heading
                                let textContent = [];
                                let nextNode = current.nextElementSibling;
                                
                                while (nextNode && !['H1','H2','H3','H4','SECTION','ARTICLE'].includes(nextNode.tagName)) {
                                    if (nextNode.innerText && nextNode.innerText.trim()) {
                                        textContent.push(nextNode.innerText.trim());
                                    }
                                    nextNode = nextNode.nextElementSibling;
                                }

                                const sectionBody = textContent.join('\\n\\n').trim();
                                if (section_title || sectionBody) {
                                    results.push({
                                        anchor_id: anchor_id,
                                        section_title: section_title,
                                        text: sectionBody ? `${section_title}\\n\\n${sectionBody}` : section_title
                                    });
                                }
                            }
                            return results;
                        }
                    """)

                    # Extract internal links for continued crawling
                    hrefs = await page.eval_on_selector_all(
                        "a[href]", "elements => elements.map(el => el.getAttribute('href'))"
                    )

                    total_sections_count += len(sections_data)
                    page_info = {
                        "url": norm_url,
                        "title": title,
                        "depth": depth,
                        "parent": parent_url,
                        "sections": sections_data,
                        "sections_count": len(sections_data),
                    }
                    self.pages_data.append(page_info)

                    # Enqueue child links
                    if depth < self.max_depth:
                        for href in hrefs:
                            if not href or href.startswith(("javascript:", "mailto:", "tel:")) or href.startswith("#"):
                                continue
                            child_norm = normalize_canonical_url(href, norm_url)
                            if self._is_same_domain(child_norm) and child_norm not in self.visited_urls:
                                queue.append((child_norm, depth + 1, norm_url))

                except Exception as e:
                    self.pages_data.append(
                        {"url": norm_url, "title": f"Error loading {norm_url}", "error": str(e), "sections": []}
                    )

            await browser.close()

        tree_structure = nx.node_link_data(self.graph)
        is_single_page = len(self.visited_urls) == 1 and total_sections_count > 5

        return {
            "target_url": self.target_url,
            "total_pages_crawled": len(self.visited_urls),
            "total_sections_extracted": total_sections_count,
            "is_single_page_doc": is_single_page,
            "pages": self.pages_data,
            "site_graph": tree_structure,
        }
