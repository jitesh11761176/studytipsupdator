"""Prompt templates for SEO analysis and optimisation tasks."""

META_GENERATION_PROMPT = """Generate SEO meta data for the following WordPress post.

Title: {title}

Content excerpt:
{content}

Generate:
1. meta_title: Compelling SEO title, 50-60 characters, include primary keyword
2. meta_description: Engaging description, 150-160 characters, include CTA
3. slug: URL-friendly slug using primary keyword (lowercase, hyphens only)
4. focus_keyword: Primary target keyword
5. secondary_keywords: List of 3-5 related keywords

Return as JSON:
{{
  "meta_title": "...",
  "meta_description": "...",
  "slug": "...",
  "focus_keyword": "...",
  "secondary_keywords": ["...", "..."]
}}"""

SCHEMA_GENERATION_PROMPT = """Generate JSON-LD schema markup for a WordPress {post_type} page on studytips.in.

Content:
{content}

Generate appropriate schema:
- Article schema for blog posts
- FAQPage schema if FAQ content is present
- HowTo schema for how-to guides
- BreadcrumbList for navigation

Return valid JSON-LD wrapped in <script type="application/ld+json"> tags."""

KEYWORD_RESEARCH_PROMPT = """Conduct keyword research for studytips.in for the topic: {topic}

The site covers study tips, exam preparation, learning strategies, and student success in India.

Provide:
1. primary_keyword: Best target keyword (high volume, moderate competition)
2. secondary_keywords: 5-8 supporting keywords
3. long_tail_keywords: 5-8 long-tail variations (question-based preferred)
4. search_intent: informational/navigational/transactional
5. difficulty: estimated SEO difficulty (low/medium/high)
6. monthly_search_volume: Estimated range

Return as JSON:
{{
  "primary_keyword": "...",
  "secondary_keywords": ["...", "..."],
  "long_tail_keywords": ["...", "..."],
  "search_intent": "...",
  "difficulty": "...",
  "monthly_search_volume": "..."
}}"""

SEO_AUDIT_PROMPT = """Perform a page-level SEO audit for this URL on studytips.in.

URL: {url}

Page content (excerpt):
{content}

Evaluate:
1. Title tag optimisation (length, keyword placement)
2. Meta description (presence, length, engagement)
3. Header hierarchy (H1, H2, H3 usage)
4. Keyword density and placement
5. Internal linking
6. Image alt texts
7. Content depth and quality
8. Schema markup presence
9. URL structure
10. Mobile-friendliness signals

Return JSON:
{{
  "score": 0-100,
  "grade": "A/B/C/D/F",
  "issues": [{{"severity": "critical/warning/info", "issue": "...", "recommendation": "..."}}],
  "strengths": ["...", "..."],
  "quick_wins": ["...", "..."]
}}"""
