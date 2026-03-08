"""Multi-format content processor for StudyTips AI Agent.

Handles PDF, CSV, Excel, Word, HTML, Markdown, and plain-text inputs,
extracts structured data, and uses the LLM brain router to analyse and
enhance content for WordPress publishing.
"""

from __future__ import annotations

import io
import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EMPTY_RESULT: Dict[str, Any] = {
    "raw_text": "",
    "html_content": "",
    "suggested_title": "",
    "suggested_slug": "",
    "suggested_meta_description": "",
    "suggested_headings": [],
    "suggested_categories": [],
    "suggested_tags": [],
    "suggested_internal_links": [],
    "seo_score": 0,
    "readability_score": 0,
    "word_count": 0,
    "image_prompt": "",
}


def _word_count(text: str) -> int:
    return len(text.split())


def inline_css(html: str) -> str:
    """Convert <style> block CSS rules to inline style attributes.

    WordPress and many page builders strip <style> tags from content,
    which causes beautifully styled previews to appear as plain text.
    This function parses CSS rules and applies them directly as inline
    ``style`` attributes on matching HTML elements.

    Args:
        html: HTML string potentially containing ``<style>`` blocks.

    Returns:
        HTML with CSS applied as inline styles and ``<style>`` blocks removed.
    """
    if "<style" not in html:
        return html

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        style_tags = soup.find_all("style")
        if not style_tags:
            return html

        css_text = "\n".join(tag.string or "" for tag in style_tags)

        # Remove CSS comments
        css_text = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)

        # Flatten @media blocks: keep their inner rules (best-effort for inline)
        css_text = re.sub(
            r"@media[^{]*\{((?:[^{}]*\{[^{}]*\})*)\s*\}",
            r"\1",
            css_text,
            flags=re.DOTALL,
        )
        # Remove @keyframes and other @-rules entirely
        css_text = re.sub(
            r"@[\w-]+[^{]*\{(?:[^{}]*\{[^{}]*\})*\s*\}",
            "",
            css_text,
            flags=re.DOTALL,
        )

        # Parse selector { properties } pairs
        rule_re = re.compile(r"([^{}]+?)\s*\{([^{}]+?)\}", re.DOTALL)
        rules: list = []
        for match in rule_re.finditer(css_text):
            selectors_str = match.group(1).strip()
            properties = re.sub(r"\s+", " ", match.group(2).strip())
            if not properties.endswith(";"):
                properties += ";"

            for selector in selectors_str.split(","):
                selector = selector.strip()
                # Skip pseudo-classes / pseudo-elements (can't be inlined)
                if not selector or any(
                    p in selector
                    for p in (":hover", ":focus", ":active", "::before", "::after", ":nth", ":before", ":after")
                ):
                    continue
                rules.append((selector, properties))

        # Apply rules to matching elements (order preserved = cascade order)
        for selector, properties in rules:
            try:
                elements = soup.select(selector)
                for el in elements:
                    existing = el.get("style", "")
                    if existing and not existing.rstrip().endswith(";"):
                        existing = existing.rstrip() + "; "
                    el["style"] = ((existing + " " + properties) if existing else properties).strip()
            except Exception:  # noqa: BLE001
                continue  # skip invalid / unsupported selectors

        # Remove <style> tags (rules are now inlined)
        for tag in style_tags:
            tag.decompose()

        return str(soup)
    except Exception:  # noqa: BLE001
        return html


def _slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = slug.strip("-")
    return slug


class ContentProcessor:
    """Process multiple content formats into structured WordPress-ready content.

    Args:
        brain_router: BrainRouter instance for LLM calls (optional — analysis
            and enhancement features are disabled when None).
    """

    def __init__(self, brain_router: Optional[Any] = None, wp_client: Optional[Any] = None) -> None:
        self.brain = brain_router
        self.wp_client = wp_client

    # ------------------------------------------------------------------
    # Format-specific processors
    # ------------------------------------------------------------------

    def process_pdf(self, file: Any) -> Dict[str, Any]:
        """Extract text from a PDF file and analyse it.

        Args:
            file: File-like object or path to a PDF.

        Returns:
            Structured content dict.
        """
        try:
            import PyPDF2  # type: ignore[import-untyped]

            reader = PyPDF2.PdfReader(file)
            pages_text = [page.extract_text() or "" for page in reader.pages]
            raw_text = "\n\n".join(pages_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PDF extraction failed: %s", exc)
            raw_text = ""

        return self._build_result(raw_text)

    def process_url(self, url: str) -> Dict[str, Any]:
        """Fetch a URL, scrape its text, and analyse the content.

        Args:
            url: Page URL to scrape.

        Returns:
            Structured content dict.
        """
        try:
            import requests
            from bs4 import BeautifulSoup

            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            # Remove script/style tags
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            raw_text = soup.get_text(separator="\n", strip=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("URL fetch failed for %s: %s", url, exc)
            raw_text = ""

        return self._build_result(raw_text)

    def process_csv(self, file: Any) -> Dict[str, Any]:
        """Parse a CSV file and generate tabular content.

        Args:
            file: File-like object or path to a CSV.

        Returns:
            Structured content dict (html_content contains an HTML table).
        """
        try:
            import pandas as pd  # type: ignore[import-untyped]

            df = pd.read_csv(file)
            raw_text = df.to_string(index=False)
            html_content = df.to_html(index=False, border=0, classes="wp-table")
        except Exception as exc:  # noqa: BLE001
            logger.warning("CSV processing failed: %s", exc)
            raw_text = ""
            html_content = ""

        result = self._build_result(raw_text)
        if html_content:
            result["html_content"] = html_content
        return result

    def process_excel(self, file: Any) -> Dict[str, Any]:
        """Parse an Excel file and generate formatted table content.

        Args:
            file: File-like object or path to an .xlsx file.

        Returns:
            Structured content dict.
        """
        try:
            import pandas as pd

            xl = pd.ExcelFile(file)
            parts: List[str] = []
            html_parts: List[str] = []
            for sheet_name in xl.sheet_names:
                df = xl.parse(sheet_name)
                parts.append(f"## {sheet_name}\n{df.to_string(index=False)}")
                html_parts.append(
                    f"<h2>{sheet_name}</h2>"
                    + df.to_html(index=False, border=0, classes="wp-table")
                )
            raw_text = "\n\n".join(parts)
            html_content = "\n".join(html_parts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Excel processing failed: %s", exc)
            raw_text = ""
            html_content = ""

        result = self._build_result(raw_text)
        if html_content:
            result["html_content"] = html_content
        return result

    def process_word(self, file: Any) -> Dict[str, Any]:
        """Parse a .docx file, preserve formatting, and convert to WordPress HTML.

        Args:
            file: File-like object or path to a .docx file.

        Returns:
            Structured content dict.
        """
        try:
            from docx import Document  # type: ignore[import-untyped]

            doc = Document(file)
            parts: List[str] = []
            html_parts: List[str] = []
            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    continue
                style = para.style.name if para.style else ""
                if style.startswith("Heading 1"):
                    parts.append(f"# {text}")
                    html_parts.append(f"<h1>{text}</h1>")
                elif style.startswith("Heading 2"):
                    parts.append(f"## {text}")
                    html_parts.append(f"<h2>{text}</h2>")
                elif style.startswith("Heading 3"):
                    parts.append(f"### {text}")
                    html_parts.append(f"<h3>{text}</h3>")
                else:
                    parts.append(text)
                    html_parts.append(f"<p>{text}</p>")

            raw_text = "\n\n".join(parts)
            html_content = "\n".join(html_parts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Word processing failed: %s", exc)
            raw_text = ""
            html_content = ""

        result = self._build_result(raw_text)
        if html_content:
            result["html_content"] = html_content
        return result

    def process_html(self, html_content: str) -> Dict[str, Any]:
        """Parse raw HTML, clean it, and optimise for WordPress.

        Args:
            html_content: Raw HTML string.

        Returns:
            Structured content dict.
        """
        clean_html = html_content
        raw_text = html_content
        try:
            import html2text  # type: ignore[import-untyped]
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html_content, "lxml")
            for tag in soup(["script", "style"]):
                tag.decompose()
            clean_html = str(soup.body or soup)

            h = html2text.HTML2Text()
            h.ignore_links = False
            raw_text = h.handle(clean_html)
        except Exception as exc:  # noqa: BLE001
            logger.warning("HTML processing failed: %s", exc)

        result = self._build_result(raw_text)
        result["html_content"] = clean_html
        return result

    def process_markdown(self, md_content: str) -> Dict[str, Any]:
        """Convert Markdown to WordPress HTML with proper formatting.

        Args:
            md_content: Markdown string.

        Returns:
            Structured content dict.
        """
        try:
            import markdown as md_lib  # type: ignore[import-untyped]

            html_content = md_lib.markdown(
                md_content,
                extensions=["tables", "fenced_code", "toc"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Markdown conversion failed: %s", exc)
            html_content = f"<pre>{md_content}</pre>"

        result = self._build_result(md_content)
        result["html_content"] = html_content
        return result

    def process_text(self, text: str) -> Dict[str, Any]:
        """Process plain text, add structure, headings, and formatting.

        Args:
            text: Plain text content.

        Returns:
            Structured content dict.
        """
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        html_parts = [f"<p>{p}</p>" for p in paragraphs]
        html_content = "\n".join(html_parts)

        result = self._build_result(text)
        result["html_content"] = html_content
        return result

    # ------------------------------------------------------------------
    # LLM-powered analysis and enhancement
    # ------------------------------------------------------------------

    def analyze_content(self, text: str) -> Dict[str, Any]:
        """Use the LLM to analyse content and return SEO/readability suggestions.

        Args:
            text: Content text to analyse.

        Returns:
            Dict with title, slug, meta description, headings, categories, tags,
            internal link suggestions, SEO score, readability score, content
            quality score.
        """
        if not self.brain:
            return {}

        prompt = (
            "Analyse the following content for an educational WordPress site (studytips.in). "
            "Return ONLY a valid JSON object with these keys:\n"
            "- suggested_title (SEO-optimised string)\n"
            "- suggested_slug (URL-friendly slug)\n"
            "- suggested_meta_description (max 160 chars)\n"
            "- suggested_headings (list of {level, text} objects)\n"
            "- suggested_categories (list of category name strings)\n"
            "- suggested_tags (list of tag strings)\n"
            "- seo_score (integer 0-100)\n"
            "- readability_score (integer 0-100)\n"
            "- content_quality_score (integer 0-100)\n\n"
            f"Content:\n{text[:4000]}"
        )

        try:
            brain_name = self.brain.route("seo_optimize", len(text))
            raw = self.brain.generate(brain_name=brain_name, prompt=prompt)
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0:
                return json.loads(raw[start:end])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Content analysis failed: %s", exc)
        return {}

    def enhance_content(self, text: str, instructions: str = "", insert_images: bool = True) -> str:
        """Use the LLM to enhance and beautify content.

        Improvements include: better readability, engaging subheadings, bullet
        points, tables, transition sentences, SEO optimisation, optional
        FAQ section, and auto-inserted relevant images.

        Args:
            text: Original content text.
            instructions: Optional extra enhancement instructions.
            insert_images: Whether to auto-insert images between sections.

        Returns:
            Enhanced HTML content string.
        """
        if not self.brain:
            return text

        image_instruction = ""
        if insert_images:
            image_instruction = (
                "\n\nIMPORTANT — Image Placeholders:\n"
                "After every 2-3 sections (H2/H3), insert an image placeholder tag like this:\n"
                '  [IMG: concise search keywords for a relevant educational image]\n'
                "Example: [IMG: student studying with laptop at desk]\n"
                "Insert 3-5 image placeholders spread throughout the content. "
                "The keywords should be specific and relevant to the surrounding section content. "
                "Do NOT use generic terms. Match the topic of the section above the image.\n"
            )

        prompt = (
            "Enhance and beautify the following content for an educational WordPress blog. "
            "Improve readability, add engaging subheadings, use bullet points and tables where "
            "appropriate, add transition sentences, optimise for SEO, and add a FAQ section if "
            "relevant. Return the enhanced content as clean WordPress-compatible HTML.\n"
        )
        prompt += image_instruction
        if instructions:
            prompt += f"\nAdditional instructions: {instructions}\n"
        prompt += f"\nContent:\n{text[:6000]}"

        try:
            brain_name = self.brain.route("create_content", len(text))
            enhanced = self.brain.generate(brain_name=brain_name, prompt=prompt)

            if insert_images:
                enhanced = self._replace_image_placeholders(enhanced)

            return enhanced
        except Exception as exc:  # noqa: BLE001
            logger.warning("Content enhancement failed: %s", exc)
            return text

    def _download_and_upload_image(self, keywords: str) -> Optional[str]:
        """Download a royalty-free image and upload to WordPress media.

        Args:
            keywords: Search keywords for the image.

        Returns:
            WordPress media URL on success, or None.
        """
        import os
        import tempfile
        from urllib.parse import quote

        import requests as _requests

        wp = self.wp_client
        if wp is None:
            return None

        query = quote(keywords)
        search_url = (
            f"https://pixabay.com/api/?key=46498498-a8059f97a3b3dea32c3a8b3a7"
            f"&q={query}&image_type=photo&orientation=horizontal"
            f"&per_page=3&safesearch=true"
        )
        try:
            resp = _requests.get(search_url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", [])
            if not hits:
                return None
            img_download_url = hits[0].get("webformatURL", "")
            if not img_download_url:
                return None
        except Exception as exc:
            logger.warning("Pixabay search failed for '%s': %s", keywords, exc)
            return None

        try:
            img_resp = _requests.get(img_download_url, timeout=20)
            img_resp.raise_for_status()
            content_type = img_resp.headers.get("Content-Type", "image/jpeg")
            ext = ".jpg"
            if "png" in content_type:
                ext = ".png"
            elif "webp" in content_type:
                ext = ".webp"
        except Exception as exc:
            logger.warning("Image download failed for '%s': %s", keywords, exc)
            return None

        tmp_path = None
        try:
            slug = re.sub(r'[^\w]+', '-', keywords.lower()).strip('-')[:60]
            fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix=f"st-{slug}-")
            os.close(fd)
            with open(tmp_path, "wb") as f:
                f.write(img_resp.content)

            media = wp.upload_media(
                file_path=tmp_path,
                alt_text=keywords,
                title=keywords,
            )
            return media.get("source_url", None)
        except Exception as exc:
            logger.warning("WP media upload failed for '%s': %s", keywords, exc)
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def _replace_image_placeholders(self, html: str) -> str:
        """Replace [IMG: ...] placeholders with WordPress-hosted images.

        Downloads royalty-free images, uploads them to the WordPress
        media library, and uses the resulting media URL in the HTML.

        Args:
            html: HTML string containing [IMG: keywords] placeholders.

        Returns:
            HTML with placeholders replaced by <figure> elements.
        """
        import re as _re

        def _make_figure(match: _re.Match) -> str:
            keywords = match.group(1).strip()
            alt_text = keywords.replace('"', '&quot;')

            img_url = self._download_and_upload_image(keywords)
            if not img_url:
                return (
                    f'\n<!-- image upload failed for: {alt_text} -->\n'
                )

            return (
                f'\n<figure class="wp-block-image size-large" style="margin:1.5em 0;">'
                f'<img src="{img_url}" alt="{alt_text}" '
                f'width="800" height="450" loading="lazy" '
                f'style="border-radius:8px;width:100%;height:auto;" />'
                f'<figcaption style="text-align:center;font-size:0.85em;color:#666;">'
                f'{keywords}</figcaption>'
                f'</figure>\n'
            )

        return _re.sub(r'\[IMG:\s*([^\]]+)\]', _make_figure, html)

    def generate_featured_image_prompt(self, title: str, content: str) -> str:
        """Generate a DALL-E/Stable Diffusion prompt for a featured image.

        Args:
            title: Post/page title.
            content: Content excerpt for context.

        Returns:
            Image generation prompt string.
        """
        if not self.brain:
            return f"Educational illustration for: {title}"

        prompt = (
            f"Create a concise, vivid image generation prompt (max 100 words) for a featured "
            f"image for this educational blog post.\n\n"
            f"Title: {title}\n"
            f"Content excerpt: {content[:500]}\n\n"
            "The image should look professional, suitable for an educational website, bright "
            "and engaging. Output ONLY the image prompt, nothing else."
        )

        try:
            brain_name = self.brain.route("general", priority="speed")
            return self.brain.generate(brain_name=brain_name, prompt=prompt).strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Image prompt generation failed: %s", exc)
            return f"Educational illustration for: {title}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_result(self, raw_text: str) -> Dict[str, Any]:
        """Build a base result dict from raw text, optionally running LLM analysis.

        Args:
            raw_text: Extracted plain text.

        Returns:
            Populated result dict.
        """
        result: Dict[str, Any] = dict(_EMPTY_RESULT)
        result["raw_text"] = raw_text
        result["word_count"] = _word_count(raw_text)

        # Basic HTML if not overridden by caller
        paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
        result["html_content"] = "\n".join(f"<p>{p}</p>" for p in paragraphs)

        if raw_text and self.brain:
            analysis = self.analyze_content(raw_text)
            if analysis:
                result["suggested_title"] = analysis.get("suggested_title", "")
                result["suggested_slug"] = analysis.get(
                    "suggested_slug",
                    _slugify(analysis.get("suggested_title", "")),
                )
                result["suggested_meta_description"] = analysis.get(
                    "suggested_meta_description", ""
                )
                result["suggested_headings"] = analysis.get("suggested_headings", [])
                result["suggested_categories"] = analysis.get("suggested_categories", [])
                result["suggested_tags"] = analysis.get("suggested_tags", [])
                result["seo_score"] = int(analysis.get("seo_score", 0))
                result["readability_score"] = int(analysis.get("readability_score", 0))

            result["image_prompt"] = self.generate_featured_image_prompt(
                title=result.get("suggested_title", "Educational post"),
                content=raw_text,
            )
        elif raw_text:
            # Derive a minimal title from the first non-empty line
            first_line = next((l.strip() for l in raw_text.splitlines() if l.strip()), "")
            result["suggested_title"] = first_line[:80]
            result["suggested_slug"] = _slugify(first_line[:80])

        return result
