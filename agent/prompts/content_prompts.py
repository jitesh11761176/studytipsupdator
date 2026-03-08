"""Prompt templates for content generation tasks."""

BLOG_POST_PROMPT = """You are an expert content writer for studytips.in, an Indian educational website.

Topic: {topic}
Target Keywords: {keywords}
Word Count: ~{word_count} words
Style: {style}
Target Audience: {audience}

Write a comprehensive, SEO-optimised blog post with:
- An engaging H1 title containing the primary keyword
- A compelling introduction (100-150 words) with a hook
- Well-structured body with H2 and H3 subheadings
- Practical, actionable tips relevant to Indian students
- Data/statistics where relevant
- FAQ section (optional but recommended)
- Strong conclusion with a call-to-action

Return as JSON:
{{
  "title": "...",
  "content": "... (full HTML content) ...",
  "meta_description": "... (150-160 chars) ...",
  "slug": "...",
  "tags": ["...", "..."],
  "focus_keyword": "..."
}}"""

CONTENT_UPDATE_PROMPT = """You are updating existing content on studytips.in.

Page Title: {title}
Update Instructions: {instructions}

Current Content (excerpt):
{current_content}

Please update the content according to the instructions while:
- Maintaining the existing structure and tone
- Improving SEO where possible
- Adding fresh, accurate information
- Keeping content relevant to Indian students

Return the complete updated HTML content."""

OUTLINE_PROMPT = """Create a detailed blog post outline for studytips.in.

Topic: {topic}
Target Keywords: {keywords}

Provide a comprehensive outline with:
- H1 title (SEO-optimised)
- Introduction notes (key points to cover)
- H2 sections (5-7 main sections)
  - H3 subsections where needed
  - Key points for each section
- Conclusion notes
- Suggested FAQ questions

Format as Markdown."""

CONTENT_CALENDAR_PROMPT = """Create a {days}-day content calendar for studytips.in.

Posts per week: {posts_per_week}
Focus Topics: {focus_topics}
Site niche: Study tips, exam prep, learning strategies, student productivity

For each post provide:
- date (YYYY-MM-DD)
- title (SEO-optimised)
- primary_keyword
- secondary_keywords (list)
- content_type (blog, guide, listicle, how-to, case-study)
- brief_outline (2-3 sentences)
- target_audience (e.g. Class 10 students, engineering aspirants)
- estimated_word_count

Return as a JSON array of post objects."""
