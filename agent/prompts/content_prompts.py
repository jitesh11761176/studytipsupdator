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

RICH_PAGE_PROMPT = """You are a professional web designer and content creator for studytips.in, an Indian educational website.

Create a COMPLETE, BEAUTIFUL, PRODUCTION-READY HTML page for the following request:

{user_request}

{reference_info}

CRITICAL DESIGN REQUIREMENTS:
1. Include a <style> block at the top with ALL CSS — the page must look stunning with ZERO external dependencies
2. Use modern CSS: gradients, grid/flexbox layouts, card designs, hover effects, rounded corners, box shadows
3. Color scheme: Use a professional gradient hero (blues/purples work great), white cards, clean typography
4. Layout: Full-width hero section → Subject/topic cards in grid → Detailed topic lists in styled cards → CTA sections
5. Mobile responsive using CSS media queries
6. Container max-width: 1200px, centered

CONTENT STRUCTURE:
- Hero section with gradient background, large heading, descriptive paragraph
- Subject grid with icon-style cards (use emoji as icons: 📘📐📖🌿💻🎨)
- Individual topic sections with bullet lists inside styled cards
- Each section should have a colored left-border heading
- Worksheets/resources section
- Conclusion/CTA section
- Internal links where relevant (use studytips.in paths)

CSS MUST INCLUDE:
- body styling (font-family, margin, background)
- .container (max-width, margin auto, padding)
- .hero (gradient background, centered text, white color, border-radius, padding 60-80px)
- .section (margin-top)
- .section h2 (colored left border, padding-left)
- .subject-grid (CSS grid, auto-fit, minmax 220px)
- .card (white bg, padding, border-radius, box-shadow, hover transform)
- ul li (margin-bottom for readability)
- Responsive @media query for mobile

CONTENT QUALITY:
- Write comprehensive, accurate educational content (not placeholder text!)
- Include ALL relevant topics/chapters for the subject/class
- Hindi content should be in Devanagari script where appropriate
- SEO-optimised headings and content
- Minimum 1500 words of actual content
- Add internal link suggestions to related pages on studytips.in

OUTPUT: Return ONLY the complete HTML with embedded <style> block. No markdown, no code fences, no explanations.
Start directly with <style> and end with the last </div>. Do NOT include <!DOCTYPE>, <html>, <head>, or <body> tags since this goes inside WordPress."""

SMART_CONTENT_PROMPT = """You are an expert content creator for studytips.in, an Indian educational website.

The user wants: {user_request}

Generate BEAUTIFUL, STYLED HTML content that looks professional and modern.
Include a <style> block with embedded CSS for:
- Gradient hero sections
- Card-based layouts with grid
- Hover effects
- Clean typography
- Responsive design
- Colored section borders

The content must be:
- Comprehensive and accurate (not placeholder)
- SEO-optimised with proper headings (H1, H2, H3)
- At least 1000-1500 words
- Visually stunning with cards, grids, gradients
- Ready to paste into WordPress/Elementor

OUTPUT: Return ONLY HTML with embedded <style>. No markdown fences, no explanations.
Start with <style> tag directly."""
