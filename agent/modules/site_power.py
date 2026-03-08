"""Site Power module — deep site intelligence for studytips.in.

Combines crawling, auto-linking, draft management, page creation,
design analysis, and indexing into one powerful engine.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)

SITE_URL = "https://studytips.in"

# File extensions that are NOT pages — skip in missing-page detection
_MEDIA_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".avif", ".ico",
    ".bmp", ".tiff", ".tif",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".mp3", ".mp4", ".wav", ".ogg", ".webm", ".avi", ".mov",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".css", ".js", ".json", ".xml", ".woff", ".woff2", ".ttf", ".eot",
}


class SitePower:
    """All-in-one site intelligence engine for studytips.in.

    Args:
        brain_router: BrainRouter instance.
        config: AppConfig instance.
    """

    def __init__(self, brain_router: Any, config: Any) -> None:
        self.brain = brain_router
        self.config = config
        self._site_url = getattr(config.wp, "site_url", SITE_URL).rstrip("/")

    def _wp(self) -> Any:
        from agent.integrations.wordpress_api import WordPressClient
        return WordPressClient(config=self.config.wp)

    # ==================================================================
    # 1. DEEP SITE CRAWL
    # ==================================================================

    def deep_crawl(self, max_pages: int = 200) -> Dict[str, Any]:
        """Crawl the live site and collect all pages, posts, links, and issues.

        Returns a comprehensive map of the site with:
        - all_pages: published pages with metadata
        - all_posts: published posts with metadata
        - drafts: all draft pages and posts
        - internal_links: link graph (source→target)
        - external_links: outbound links
        - broken_links: links returning 4xx/5xx
        - orphan_pages: pages with no inbound internal links
        - missing_pages: links pointing to non-existent pages
        - nav_structure: current navigation/menu structure
        """
        wp = self._wp()

        # Fetch all content
        pages = self._fetch_all(wp, "pages", "publish")
        posts = self._fetch_all(wp, "posts", "publish")
        draft_pages = self._fetch_all(wp, "pages", "draft")
        draft_posts = self._fetch_all(wp, "posts", "draft")
        categories = wp.get_all_categories()

        # Build URL→content map
        url_map: Dict[str, Dict] = {}
        all_items = pages + posts + draft_pages + draft_posts
        for item in all_items:
            link = item.get("link", "").rstrip("/")
            if link:
                url_map[link] = item

        # Extract link graph
        internal_links: List[Dict[str, str]] = []
        external_links: List[Dict[str, str]] = []
        broken_links: List[Dict[str, Any]] = []
        all_target_urls: Set[str] = set()

        for item in pages + posts:
            content = item.get("content", {}).get("rendered", "")
            source_url = item.get("link", "").rstrip("/")
            hrefs = re.findall(r'href=["\']([^"\'#]+)["\']', content)

            for href in hrefs:
                if href.startswith(("mailto:", "tel:", "javascript:")):
                    continue
                full_url = urljoin(source_url + "/", href).rstrip("/")

                if self._is_internal(full_url):
                    internal_links.append({"source": source_url, "target": full_url})
                    all_target_urls.add(full_url)
                else:
                    external_links.append({"source": source_url, "target": full_url})

        # Find orphan pages (no inbound internal links)
        published_urls = {item.get("link", "").rstrip("/") for item in pages + posts}
        orphan_pages = [
            {"url": url, "title": url_map.get(url, {}).get("title", {}).get("rendered", url)}
            for url in published_urls
            if url and url not in all_target_urls and url.rstrip("/") != self._site_url
        ]

        # Find missing pages (internal links pointing to 404s)
        missing_pages: List[Dict[str, str]] = []
        for target in all_target_urls:
            if target not in published_urls and self._is_internal(target):
                # Skip media files, feeds, query strings, wp-admin, etc.
                parsed = urlparse(target)
                path = parsed.path.rstrip("/")
                ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
                if ext in _MEDIA_EXTENSIONS:
                    continue
                if any(seg in path for seg in ("/wp-content/", "/wp-admin/", "/wp-includes/", "/feed", "/wp-json/")):
                    continue
                if parsed.query:  # skip query-string URLs like ?p=123
                    continue
                slug = path.split("/")[-1]
                if not slug:  # homepage or empty
                    continue
                missing_pages.append({
                    "url": target,
                    "suggested_title": slug.replace("-", " ").replace("_", " ").title(),
                    "suggested_slug": slug,
                })

        return {
            "all_pages": self._simplify_list(pages),
            "all_posts": self._simplify_list(posts),
            "draft_pages": self._simplify_list(draft_pages),
            "draft_posts": self._simplify_list(draft_posts),
            "categories": [{"id": c["id"], "name": c["name"], "count": c.get("count", 0)} for c in categories],
            "internal_links": internal_links,
            "external_links": external_links[:50],
            "orphan_pages": orphan_pages,
            "missing_pages": missing_pages,
            "totals": {
                "published_pages": len(pages),
                "published_posts": len(posts),
                "drafts": len(draft_pages) + len(draft_posts),
                "internal_links": len(internal_links),
                "orphan_pages": len(orphan_pages),
                "missing_pages": len(missing_pages),
            },
        }

    # ==================================================================
    # 2. AUTO-LINK DRAFTS
    # ==================================================================

    def auto_link_drafts(self) -> List[Dict[str, Any]]:
        """Scan all draft pages/posts and SUGGEST internal links (without applying).

        For each draft:
        1. Analyse its content with LLM
        2. Find matching published pages by topic relevance
        3. Return link suggestions for human review

        Returns list of drafts with suggested links (not yet applied).
        """
        wp = self._wp()
        pages = self._fetch_all(wp, "pages", "publish")
        posts = self._fetch_all(wp, "posts", "publish")
        draft_pages = self._fetch_all(wp, "pages", "draft")
        draft_posts = self._fetch_all(wp, "posts", "draft")

        # Build reference of existing published content with topics
        published = []
        for item in pages + posts:
            title = item.get("title", {}).get("rendered", "")
            url = item.get("link", "")
            slug = item.get("slug", "")
            # Extract first 200 chars of text for topic matching
            raw_content = item.get("content", {}).get("rendered", "")
            text_preview = re.sub(r'<[^>]+>', '', raw_content)[:200].strip()
            published.append({
                "title": title,
                "url": url,
                "slug": slug,
                "topic_hint": text_preview[:100],
            })

        results = []
        for draft in draft_pages + draft_posts:
            draft_content = draft.get("content", {}).get("rendered", "")
            draft_title = draft.get("title", {}).get("rendered", "")
            draft_id = draft.get("id")
            draft_type = draft.get("type", "post")

            if not draft_content or len(draft_content) < 50:
                continue

            # Strip HTML to get plain text for analysis
            draft_text = re.sub(r'<[^>]+>', '', draft_content)[:3000]

            # Ask LLM to SUGGEST links (not insert them)
            prompt = (
                f"You are an SEO expert for studytips.in (an Indian educational website).\n\n"
                f"DRAFT TITLE: {draft_title}\n"
                f"DRAFT CONTENT (plain text):\n{draft_text}\n\n"
                f"AVAILABLE PUBLISHED PAGES:\n{json.dumps(published[:50], indent=1)}\n\n"
                "TASK: Suggest 2-5 internal links that should be inserted into this draft.\n\n"
                "STRICT RULES:\n"
                "1. ONLY suggest links to pages whose topic is DIRECTLY related to the draft content\n"
                "2. The draft must actually discuss or mention the topic of the target page\n"
                "3. Do NOT link to unrelated pages just because they exist on the same site\n"
                "4. For each link, explain the specific sentence/paragraph where it fits\n"
                "5. If fewer than 2 pages are genuinely relevant, suggest fewer (even 0 is fine)\n\n"
                "Return JSON array: [{\"target_url\": str, \"target_title\": str, "
                "\"anchor_text\": str, \"insert_near\": str (quote the sentence where this link fits), "
                "\"relevance_reason\": str}]\n"
                "Return ONLY the JSON array, no markdown."
            )

            try:
                brain_name = self.brain.route("seo_optimize", len(draft_content))
                raw = self.brain.generate(brain_name=brain_name, prompt=prompt)

                # Parse JSON
                raw = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
                raw = re.sub(r'\n?```\s*$', '', raw.strip())
                start = raw.find("[")
                end = raw.rfind("]") + 1
                if start >= 0 and end > start:
                    suggestions = json.loads(raw[start:end])
                else:
                    suggestions = []

                # Validate: only keep suggestions that point to real published URLs
                valid_urls = {p["url"].rstrip("/") for p in published}
                validated = []
                for s in suggestions:
                    target = s.get("target_url", "").rstrip("/")
                    if target in valid_urls:
                        validated.append(s)

                results.append({
                    "id": draft_id,
                    "title": draft_title,
                    "type": draft_type,
                    "suggestions": validated,
                    "status": "suggestions_ready" if validated else "no_relevant_links",
                })
            except Exception as exc:
                logger.warning("Auto-link analysis failed for draft %s: %s", draft_id, exc)
                results.append({
                    "id": draft_id,
                    "title": draft_title,
                    "type": draft_type,
                    "status": "error",
                    "error": str(exc),
                })

        return results

    def apply_link_suggestions(
        self, draft_id: int, draft_type: str, suggestions: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Apply approved link suggestions to a specific draft.

        Args:
            draft_id: WordPress post/page ID.
            draft_type: 'post' or 'page'.
            suggestions: List of approved link dicts with target_url, anchor_text, insert_near.

        Returns:
            Result dict with links_added count.
        """
        wp = self._wp()
        try:
            if draft_type == "page":
                item = wp._request("GET", f"pages/{draft_id}")
            else:
                item = wp._request("GET", f"posts/{draft_id}")
        except Exception as exc:
            return {"status": "error", "error": f"Could not fetch draft: {exc}"}

        content = item.get("content", {}).get("rendered", "")
        title = item.get("title", {}).get("rendered", "")
        links_added = 0

        # Ask LLM to insert the approved links
        links_json = json.dumps(suggestions, indent=1)
        prompt = (
            f"Insert these approved internal links into the HTML content.\n\n"
            f"LINKS TO INSERT:\n{links_json}\n\n"
            f"CURRENT HTML CONTENT:\n{content[:6000]}\n\n"
            "RULES:\n"
            "1. Insert each link as an <a href=\"...\"> tag using the anchor_text provided\n"
            "2. Place each link near the sentence indicated by 'insert_near'\n"
            "3. Keep ALL original content intact — only ADD anchor tags\n"
            "4. Return the COMPLETE updated HTML\n"
            "5. Do NOT wrap in code blocks\n"
        )

        try:
            brain_name = self.brain.route("seo_optimize", len(content))
            linked_content = self.brain.generate(brain_name=brain_name, prompt=prompt)
            linked_content = re.sub(r'^```(?:html)?\s*\n?', '', linked_content.strip())
            linked_content = re.sub(r'\n?```\s*$', '', linked_content.strip())

            orig_count = len(re.findall(r'<a\s', content))
            new_count = len(re.findall(r'<a\s', linked_content))
            links_added = max(0, new_count - orig_count)

            if links_added > 0:
                if draft_type == "page":
                    wp.update_page(draft_id, content=linked_content)
                else:
                    wp.update_post(draft_id, content=linked_content)

            return {
                "id": draft_id,
                "title": title,
                "links_added": links_added,
                "status": "applied" if links_added > 0 else "no_change",
            }
        except Exception as exc:
            return {"id": draft_id, "status": "error", "error": str(exc)}

    # ==================================================================
    # 3. DRAFT → NAV PLACEMENT
    # ==================================================================

    def place_drafts_in_nav(self) -> List[Dict[str, Any]]:
        """Analyse all drafts and suggest/execute correct navigation placement.

        For each draft page:
        1. Determine the best parent page (or top-level)
        2. Determine which nav tab/menu it belongs under
        3. Set the parent page relationship
        4. Suggest menu placement

        Returns list of placement decisions.
        """
        wp = self._wp()
        pages = self._fetch_all(wp, "pages", "publish")
        draft_pages = self._fetch_all(wp, "pages", "draft")

        if not draft_pages:
            return [{"status": "no_drafts", "message": "No draft pages found"}]

        # Build existing page tree
        page_tree = []
        for p in pages:
            page_tree.append({
                "id": p.get("id"),
                "title": p.get("title", {}).get("rendered", ""),
                "parent": p.get("parent", 0),
                "slug": p.get("slug", ""),
                "link": p.get("link", ""),
            })

        results = []
        for draft in draft_pages:
            draft_title = draft.get("title", {}).get("rendered", "")
            draft_content = draft.get("content", {}).get("rendered", "")[:2000]
            draft_id = draft.get("id")
            current_parent = draft.get("parent", 0)

            prompt = (
                f"Analyse this draft page for studytips.in and determine its correct navigation placement.\n\n"
                f"Draft page title: {draft_title}\n"
                f"Draft content preview: {draft_content[:1000]}\n\n"
                f"Existing site pages:\n{json.dumps(page_tree, indent=1)}\n\n"
                "Determine:\n"
                "1. The best parent page ID (or 0 for top-level)\n"
                "2. The menu section it belongs to (primary nav, footer, or sidebar)\n"
                "3. The menu_order (position within its section)\n\n"
                "Return JSON: {\"parent_id\": int, \"menu_section\": str, \"menu_order\": int, \"reasoning\": str}"
            )

            try:
                brain_name = self.brain.route("general", priority="speed")
                raw = self.brain.generate(brain_name=brain_name, prompt=prompt)

                # Parse JSON from response
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start >= 0:
                    placement = json.loads(raw[start:end])
                else:
                    placement = {"parent_id": 0, "menu_section": "primary", "menu_order": 0, "reasoning": raw}

                parent_id = int(placement.get("parent_id", 0))
                menu_order = int(placement.get("menu_order", 0))

                # Apply parent page if different from current
                if parent_id != current_parent:
                    wp.update_page(draft_id, parent=parent_id, menu_order=menu_order)

                results.append({
                    "draft_id": draft_id,
                    "title": draft_title,
                    "parent_id": parent_id,
                    "menu_section": placement.get("menu_section", "primary"),
                    "menu_order": menu_order,
                    "reasoning": placement.get("reasoning", ""),
                    "status": "placed",
                })
            except Exception as exc:
                logger.warning("Nav placement failed for draft %s: %s", draft_id, exc)
                results.append({
                    "draft_id": draft_id,
                    "title": draft_title,
                    "status": "error",
                    "error": str(exc),
                })

        return results

    # ==================================================================
    # 4. CREATE MISSING PAGES & INDEX
    # ==================================================================

    def create_missing_pages(self) -> List[Dict[str, Any]]:
        """Find all internal links pointing to non-existent pages, create them,
        and set up proper parent/nav relationships.

        Returns list of created pages.
        """
        crawl = self.deep_crawl()
        missing = crawl.get("missing_pages", [])
        existing_pages = crawl.get("all_pages", [])

        if not missing:
            return [{"status": "none_missing", "message": "All internal links resolve to existing pages"}]

        wp = self._wp()
        results = []

        for page_info in missing[:20]:  # Limit to 20 at a time
            title = page_info.get("suggested_title", "Untitled")
            slug = page_info.get("suggested_slug", "")
            url = page_info.get("url", "")

            # Use LLM to generate initial content
            prompt = (
                f"Create a comprehensive page for studytips.in with the title: '{title}'\n\n"
                f"This page was found as a broken internal link (URL: {url}).\n"
                f"The site is an Indian educational website about study tips and exam preparation.\n\n"
                "Write 500-800 words of high-quality, SEO-optimised HTML content.\n"
                "Include: H2 headings, bullet points, a CTA, and practical advice.\n"
                "Return only the HTML content (no markdown code blocks)."
            )

            try:
                brain_name = self.brain.route("create_content", priority="quality")
                content = self.brain.generate(brain_name=brain_name, prompt=prompt)

                # Clean markdown fencing if present
                content = re.sub(r'^```(?:html)?\s*\n?', '', content.strip())
                content = re.sub(r'\n?```\s*$', '', content.strip())

                # Determine best parent page
                parent_id = self._find_best_parent(title, existing_pages)

                # Create the page as draft
                created = wp.create_page(
                    title=title,
                    content=content,
                    parent=parent_id,
                    status="draft",
                )

                results.append({
                    "id": created.get("id"),
                    "title": title,
                    "slug": slug,
                    "parent_id": parent_id,
                    "status": "created_as_draft",
                    "link": created.get("link", ""),
                })
            except Exception as exc:
                logger.warning("Failed to create page '%s': %s", title, exc)
                results.append({
                    "title": title,
                    "slug": slug,
                    "status": "error",
                    "error": str(exc),
                })

        return results

    # ==================================================================
    # 5. DESIGN ANALYSIS (LIVE SITE)
    # ==================================================================

    def analyze_design(self) -> Dict[str, Any]:
        """Fetch the live site HTML/CSS and generate specific design improvement suggestions.

        Unlike the generic DesignManager, this actually inspects the real site.
        """
        issues = []
        suggestions = []

        # Fetch homepage
        try:
            resp = requests.get(self._site_url, timeout=15)
            html = resp.text
            load_time_ms = int(resp.elapsed.total_seconds() * 1000)
        except Exception as exc:
            return {"error": f"Could not fetch site: {exc}"}

        # Basic checks
        page_size_kb = round(len(html) / 1024, 1)
        if load_time_ms > 3000:
            issues.append(f"Homepage loads in {load_time_ms}ms (should be <2000ms)")
        if page_size_kb > 500:
            issues.append(f"Homepage size is {page_size_kb}KB (consider optimising)")

        # Check viewport meta
        if 'name="viewport"' not in html.lower():
            issues.append("Missing viewport meta tag — mobile users will have poor experience")

        # Check for lazy loading
        img_count = len(re.findall(r'<img\s', html))
        lazy_count = len(re.findall(r'loading=["\']lazy["\']', html))
        if img_count > 3 and lazy_count < img_count // 2:
            issues.append(f"Only {lazy_count}/{img_count} images use lazy loading")

        # Check heading structure
        h1_count = len(re.findall(r'<h1[\s>]', html))
        if h1_count == 0:
            issues.append("No H1 tag found on homepage")
        elif h1_count > 1:
            issues.append(f"Multiple H1 tags ({h1_count}) — should be exactly 1")

        # Check for critical CSS issues
        inline_css = len(re.findall(r'<style', html))
        css_links = len(re.findall(r'<link[^>]+stylesheet', html))
        if css_links > 8:
            issues.append(f"{css_links} CSS files loaded — consider combining/minimising")

        js_files = len(re.findall(r'<script[^>]+src=', html))
        if js_files > 10:
            issues.append(f"{js_files} JavaScript files — consider deferring non-critical scripts")

        # Check schema markup
        schema_blocks = len(re.findall(r'application/ld\+json', html))
        if schema_blocks == 0:
            issues.append("No JSON-LD schema markup found — hurts SEO rich results")

        # Check breadcrumbs
        if 'breadcrumb' not in html.lower():
            suggestions.append("Add breadcrumb navigation for better UX and SEO")

        # Check search
        if '<form' not in html.lower() or 'search' not in html.lower():
            suggestions.append("Add a prominent search bar for students to find content easily")

        # Use LLM for deeper design analysis with real HTML
        prompt = (
            f"You are a UX/UI expert reviewing studytips.in (an Indian educational website).\n\n"
            f"Page load time: {load_time_ms}ms\n"
            f"Page size: {page_size_kb}KB\n"
            f"Images: {img_count}, Lazy-loaded: {lazy_count}\n"
            f"CSS files: {css_links}, JS files: {js_files}\n"
            f"H1 tags: {h1_count}, Schema blocks: {schema_blocks}\n"
            f"Automated issues found: {json.dumps(issues)}\n\n"
            f"HTML head section:\n{html[:3000]}\n\n"
            "Provide 5-8 specific, actionable design improvements. For each:\n"
            "- What exactly to change\n"
            "- CSS/HTML code snippet if applicable\n"
            "- Expected impact (high/medium/low)\n\n"
            "Return JSON: {\"improvements\": [{\"title\": str, \"description\": str, "
            "\"code_snippet\": str, \"impact\": str, \"category\": str}]}"
        )

        try:
            brain_name = self.brain.route("design_update", priority="quality")
            raw = self.brain.generate(brain_name=brain_name, prompt=prompt)
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0:
                llm_analysis = json.loads(raw[start:end])
                suggestions.extend([
                    imp.get("title", "") for imp in llm_analysis.get("improvements", [])
                ])
            else:
                llm_analysis = {"raw": raw}
        except Exception as exc:
            logger.warning("Design LLM analysis failed: %s", exc)
            llm_analysis = {"error": str(exc)}

        return {
            "load_time_ms": load_time_ms,
            "page_size_kb": page_size_kb,
            "images": img_count,
            "css_files": css_links,
            "js_files": js_files,
            "automated_issues": issues,
            "suggestions": suggestions,
            "llm_analysis": llm_analysis,
        }

    # ==================================================================
    # 6. FULL SITE POWER REPORT
    # ==================================================================

    def full_power_report(self) -> Dict[str, Any]:
        """Generate a comprehensive site intelligence report combining all analyses.

        This is the main entry point for "check all the site".
        """
        report: Dict[str, Any] = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S")}

        # 1. Deep crawl
        try:
            crawl = self.deep_crawl()
            report["crawl"] = crawl
        except Exception as exc:
            report["crawl_error"] = str(exc)
            crawl = {}

        # 2. Design analysis
        try:
            design = self.analyze_design()
            report["design"] = design
        except Exception as exc:
            report["design_error"] = str(exc)

        # 3. Draft analysis
        drafts = crawl.get("draft_pages", []) + crawl.get("draft_posts", [])
        report["draft_summary"] = {
            "total_drafts": len(drafts),
            "draft_pages": len(crawl.get("draft_pages", [])),
            "draft_posts": len(crawl.get("draft_posts", [])),
            "items": [{"id": d.get("id"), "title": d.get("title"), "type": d.get("type", "post")} for d in drafts],
        }

        # 4. Recommendations
        recommendations = []
        totals = crawl.get("totals", {})

        if totals.get("orphan_pages", 0) > 0:
            recommendations.append({
                "priority": "high",
                "action": "fix_orphan_pages",
                "title": f"Fix {totals['orphan_pages']} orphan pages",
                "description": "These pages have no internal links pointing to them. Add internal links or include them in navigation.",
            })

        if totals.get("missing_pages", 0) > 0:
            recommendations.append({
                "priority": "high",
                "action": "create_missing_pages",
                "title": f"Create {totals['missing_pages']} missing pages",
                "description": "Internal links point to pages that don't exist yet. Create these pages to fix broken links.",
            })

        if totals.get("drafts", 0) > 0:
            recommendations.append({
                "priority": "medium",
                "action": "process_drafts",
                "title": f"Process {totals['drafts']} draft items",
                "description": "Auto-link these drafts to existing content and place them correctly in navigation.",
            })

        if crawl.get("orphan_pages"):
            recommendations.append({
                "priority": "medium",
                "action": "auto_link_orphans",
                "title": "Auto-link orphan pages",
                "description": "Insert internal links to orphan pages from related content.",
            })

        report["recommendations"] = recommendations

        # 5. Site health score
        issues_count = (
            totals.get("orphan_pages", 0) +
            totals.get("missing_pages", 0) +
            len(crawl.get("design", {}).get("automated_issues", []) if isinstance(crawl.get("design"), dict) else [])
        )
        report["health_score"] = max(0, 100 - issues_count * 5)

        return report

    # ==================================================================
    # 7. AUTO-FIX: One-click site improvements
    # ==================================================================

    def auto_fix_all(self) -> Dict[str, Any]:
        """Run all automated fixes in sequence:
        1. Auto-link drafts with internal links
        2. Place drafts under correct parent pages
        3. Create missing pages
        4. Return summary

        All changes are made as drafts for human review.
        """
        results: Dict[str, Any] = {}

        # Step 1: Suggest links for drafts (preview only, not applied)
        try:
            linked = self.auto_link_drafts()
            results["auto_link_suggestions"] = {
                "count": len([r for r in linked if r.get("status") == "suggestions_ready"]),
                "details": linked,
            }
        except Exception as exc:
            results["auto_link_error"] = str(exc)

        # Step 2: Place drafts in correct nav
        try:
            placed = self.place_drafts_in_nav()
            results["nav_placed"] = {
                "count": len([r for r in placed if r.get("status") == "placed"]),
                "details": placed,
            }
        except Exception as exc:
            results["nav_placement_error"] = str(exc)

        # Step 3: Create missing pages
        try:
            created = self.create_missing_pages()
            results["pages_created"] = {
                "count": len([r for r in created if r.get("status") == "created_as_draft"]),
                "details": created,
            }
        except Exception as exc:
            results["page_creation_error"] = str(exc)

        return results

    # ==================================================================
    # HELPERS
    # ==================================================================

    def _fetch_all(self, wp: Any, content_type: str, status: str) -> List[Dict]:
        """Fetch all items of a content type, paginating through all pages."""
        all_items: List[Dict] = []
        page = 1
        while True:
            try:
                if content_type == "pages":
                    batch = wp.get_pages(per_page=100, page=page, status=status)
                else:
                    batch = wp.get_posts(per_page=100, page=page, status=status)
                if not batch:
                    break
                all_items.extend(batch)
                if len(batch) < 100:
                    break
                page += 1
            except Exception:
                break
        return all_items

    def _is_internal(self, url: str) -> bool:
        """Check if a URL belongs to studytips.in."""
        parsed = urlparse(url)
        site_parsed = urlparse(self._site_url)
        return parsed.netloc == site_parsed.netloc or parsed.netloc == ""

    def _simplify_list(self, items: List[Dict]) -> List[Dict]:
        """Reduce WP API objects to essential fields."""
        return [
            {
                "id": item.get("id"),
                "title": item.get("title", {}).get("rendered", "") if isinstance(item.get("title"), dict) else item.get("title", ""),
                "slug": item.get("slug", ""),
                "link": item.get("link", ""),
                "status": item.get("status", ""),
                "parent": item.get("parent", 0),
                "type": item.get("type", ""),
            }
            for item in items
        ]

    def _find_best_parent(self, title: str, existing_pages: List[Dict]) -> int:
        """Use LLM to determine the best parent page for a new page."""
        if not existing_pages:
            return 0

        page_list = [{"id": p.get("id"), "title": p.get("title")} for p in existing_pages[:30]]
        prompt = (
            f"For a new page titled '{title}' on studytips.in, "
            f"which existing page should be its parent?\n\n"
            f"Existing pages: {json.dumps(page_list)}\n\n"
            "Return ONLY the parent page ID as an integer (0 if it should be top-level)."
        )

        try:
            brain_name = self.brain.route("general", priority="speed")
            raw = self.brain.generate(brain_name=brain_name, prompt=prompt).strip()
            # Extract first number from response
            match = re.search(r'\d+', raw)
            return int(match.group()) if match else 0
        except Exception:
            return 0
