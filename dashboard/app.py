"""Streamlit web dashboard for StudyTips AI Agent."""

from __future__ import annotations

import io
import json
import os
import sys

# Ensure the project root is in the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

st.set_page_config(
    page_title="StudyTips AI Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------------
# Custom CSS – dark-theme polish
# ------------------------------------------------------------------
st.markdown(
    """
    <style>
    .stApp { background-color: #0e1117; }
    .metric-card {
        background: #1c1f26;
        border-radius: 10px;
        padding: 1rem;
        border-left: 4px solid #4CAF50;
    }
    .brain-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        background: #2d3748;
        color: #68d391;
        margin-right: 4px;
    }
    .status-dot-green { color: #48bb78; font-size: 0.6rem; }
    .status-dot-red   { color: #fc8181; font-size: 0.6rem; }
    .diff-add { background: #1a4731; color: #68d391; }
    .diff-del { background: #4c1d1d; color: #fc8181; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------
# State helpers
# ------------------------------------------------------------------


def _get_agent() -> object:
    """Return a cached agent instance."""
    if "agent" not in st.session_state:
        from agent.core.orchestrator import StudyTipsAgent

        st.session_state.agent = StudyTipsAgent()
    return st.session_state.agent


def _get_brain_router():
    """Return the agent's brain router."""
    try:
        agent = _get_agent()
        return agent.brain  # type: ignore[attr-defined]
    except Exception:
        from agent.core.brain_router import BrainRouter
        return BrainRouter()


def _get_pending() -> list:
    return st.session_state.get("pending_actions", [])


def _get_content_processor():
    """Return a cached ContentProcessor."""
    if "content_processor" not in st.session_state:
        from agent.modules.content_processor import ContentProcessor
        try:
            brain = _get_brain_router()
        except Exception:
            brain = None
        wp = None
        try:
            from agent.core.config import load_config
            from agent.integrations.wordpress_api import WordPressClient
            cfg = load_config()
            if cfg.wp.username and cfg.wp.app_password:
                wp = WordPressClient(config=cfg.wp)
        except Exception:
            pass
        st.session_state.content_processor = ContentProcessor(brain_router=brain, wp_client=wp)
    return st.session_state.content_processor


# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------

with st.sidebar:
    st.title("🤖 StudyTips Agent")

    # Connection status indicator
    try:
        br = _get_brain_router()
        brains = br.list_brains()
        available_count = sum(1 for b in brains if b["available"])
        st.markdown(
            f'<span class="status-dot-green">●</span> **{available_count} brain(s) configured**',
            unsafe_allow_html=True,
        )
        if brains:
            # Build model picker options grouped like VS Code
            # Vendor icon map for Copilot models
            _vendor_icon = {
                "openai": "🤖", "azure openai": "🤖",
                "anthropic": "🟠", "google": "🔷",
                "xai": "⚡", "microsoft": "🪟",
            }

            def _brain_label(b: dict) -> str:
                model_id = b["model"]
                # For Copilot brains, detect vendor from model name
                if b["provider"] == "github_copilot":
                    if "claude" in model_id:
                        icon = "🟠"
                    elif "gemini" in model_id:
                        icon = "🔷"
                    elif "grok" in model_id:
                        icon = "⚡"
                    elif "raptor" in model_id or "oswe" in model_id:
                        icon = "🪟"
                    else:
                        icon = "🤖"
                    # Show display name from stored brain name
                    display = model_id
                    return f"{icon} {display}  [Copilot]"
                elif b["provider"] == "nvidia":
                    return f"🟢 {model_id}  [NVIDIA]"
                elif b["provider"] == "openrouter":
                    return f"🌐 {model_id}  [OpenRouter]"
                elif b["provider"] == "ollama":
                    return f"💻 {model_id}  [Local]"
                elif b["provider"] == "kimi":
                    return f"🌙 {model_id}  [Kimi]"
                elif b["provider"] == "github_models":
                    return f"🐙 {model_id}  [GitHub Models]"
                return f"🧠 {b['name']}  ({model_id})"

            available_brains = [b for b in brains if b["available"]]

            brain_options = ["🔀 Auto (smart routing)"]
            brain_name_map = {"🔀 Auto (smart routing)": None}
            for b in available_brains:
                lbl = _brain_label(b)
                brain_options.append(lbl)
                brain_name_map[lbl] = b["name"]

            st.markdown("**🧠 Active Brain**")

            prev_label = st.session_state.get("selected_brain_label", brain_options[0])
            if prev_label not in brain_options:
                prev_label = brain_options[0]

            selected_label = st.selectbox(
                "Choose brain",
                options=brain_options,
                index=brain_options.index(prev_label),
                label_visibility="collapsed",
                key="brain_selector",
            )
            st.session_state["selected_brain_label"] = selected_label
            chosen_brain = brain_name_map.get(selected_label)

            # Apply forced brain on the router
            try:
                agent = _get_agent()
                agent.brain.forced_brain = chosen_brain
            except Exception:
                pass

            if chosen_brain:
                matched = next((b for b in available_brains if b["name"] == chosen_brain), None)
                if matched:
                    ctx_k = matched["context_window"] // 1000
                    st.caption(f"🆓 free · {'⚡' * matched['speed_rating']} · {ctx_k}k ctx")
            else:
                # Count by provider
                _cop = sum(1 for b in available_brains if b["provider"] == "github_copilot")
                st.caption(f"Auto-routing · {_cop} Copilot + {available_count - _cop} other models")
    except Exception:
        st.markdown(
            '<span class="status-dot-red">●</span> No brains configured',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.subheader("Quick Actions")

    if st.button("🔍 SEO Audit", use_container_width=True):
        st.session_state["quick_prompt"] = "Run a full SEO audit of studytips.in"

    if st.button("📅 Content Calendar", use_container_width=True):
        st.session_state["quick_prompt"] = "Generate a 30-day content calendar"

    if st.button("📊 Analytics Report", use_container_width=True):
        st.session_state["quick_prompt"] = "Generate a monthly analytics report"

    if st.button("🏥 Health Check", use_container_width=True):
        st.session_state["quick_prompt"] = "Run a complete site health check"

    if st.button("💡 Topic Ideas", use_container_width=True):
        st.session_state["quick_prompt"] = "Suggest 10 trending blog post topics"

    if st.button("🔗 Stale Content", use_container_width=True):
        st.session_state["quick_prompt"] = "Find posts not updated in 6 months"

    st.markdown("---")
    st.subheader("⚡ Power Tools")

    if st.button("🕷️ Deep Crawl", use_container_width=True):
        st.session_state["quick_prompt"] = "Deep crawl the entire site — find all pages, orphans, missing pages, broken links"

    if st.button("🔗 Auto-Link Drafts", use_container_width=True):
        st.session_state["quick_prompt"] = "Auto-link all draft posts and pages with internal links to existing content"

    if st.button("🧭 Place Drafts in Nav", use_container_width=True):
        st.session_state["quick_prompt"] = "Analyse all draft pages and place them under the correct parent/navigation tab"

    if st.button("📄 Create Missing Pages", use_container_width=True):
        st.session_state["quick_prompt"] = "Find all internal links pointing to missing pages and create those pages"

    if st.button("🎨 Design Review", use_container_width=True):
        st.session_state["quick_prompt"] = "Analyse the live site design, CSS, speed, and UX — give specific improvements"

    if st.button("🚀 Auto-Fix All", use_container_width=True):
        st.session_state["quick_prompt"] = "Auto-fix everything: link drafts, place in nav, create missing pages"

    st.markdown("---")
    st.subheader("📚 Class Page Generator")
    st.caption("One-click beautiful pages")

    gen_class = st.selectbox("Select Class", list(range(1, 13)), index=2, key="sidebar_class_select")
    if st.button(f"✨ Generate Class {gen_class} Page", use_container_width=True):
        st.session_state["quick_prompt"] = f"Create a beautiful full-width page for Class {gen_class} Subjects and Topics — similar to the Class 1 page at https://studytips.in/class-1-subjects-and-topics/. Include all subjects (English, Mathematics, Hindi, EVS/Science, Computer, Social Science as applicable), with ALL chapter/topic lists for each subject, worksheets section, and study resources. Make it comprehensive and SEO-optimised."
        st.session_state["use_smart_generate"] = True

    st.markdown("---")
    st.caption("All actions create DRAFTS for your approval")

# ------------------------------------------------------------------
# Main content – tabs
# ------------------------------------------------------------------

st.title("StudyTips AI Agent Dashboard")
tabs = st.tabs([
    " Content Studio",
    "🔄 Page Updater",
    "⏳ Pending Actions",
    "📊 Site Stats",
    "⚡ Site Power",
    "⚙️ Settings",
])

# ==================================================================
# Tab 1: Content Studio  (Chat + Studio merged)
# ==================================================================
with tabs[0]:
    st.subheader("📤 Content Studio")
    st.caption("Upload content, add images, chat with AI to tweak, beautify, and publish — all in one place.")

    # ---- Agent command bar (handles sidebar quick actions) ---------
    default_prompt = st.session_state.pop("quick_prompt", "")
    agent_prompt = st.text_input(
        "🤖 Agent command",
        value=default_prompt,
        placeholder="e.g. Write a blog post about study tips for Class 10, Create a Class 5 page like Class 1…",
        key="studio_agent_cmd",
    )
    cmd_col1, cmd_col2 = st.columns([1, 1])
    with cmd_col1:
        exec_agent_btn = st.button("🚀 Execute Command", type="primary")
    with cmd_col2:
        gen_smart_btn = st.button("✨ Smart Generate (Beautiful Page)", type="secondary")

    # Auto-trigger smart generate from sidebar class page generator
    if st.session_state.pop("use_smart_generate", False) and agent_prompt:
        gen_smart_btn = True

    if agent_prompt and exec_agent_btn:
        agent = _get_agent()
        with st.spinner("Agent is working…"):
            try:
                result = agent.process_prompt(agent_prompt)
                st.session_state.setdefault("pending_actions", []).append(result)
                # If the agent produced draft content, load it into studio
                draft = result.get("results", {}).get("draft_content", "")
                if draft:
                    st.session_state["studio_result"] = {
                        "raw_text": draft,
                        "html_content": draft,
                        "suggested_title": result.get("results", {}).get("title", ""),
                        "suggested_slug": result.get("results", {}).get("slug", ""),
                        "suggested_meta_description": "",
                        "suggested_tags": [],
                        "suggested_headings": [],
                        "seo_score": 0,
                        "readability_score": 0,
                        "word_count": len(draft.split()),
                        "image_prompt": "",
                    }
                    st.success("✅ Content generated! Scroll down to review, tweak, and publish.")
                else:
                    st.info(f"Agent completed: **{result.get('intent', '')}**")
                    with st.expander("📋 Agent Output", expanded=True):
                        st.markdown(result.get("formatted_output", ""))
            except Exception as exc:
                st.error(f"Error: {exc}")

    if agent_prompt and gen_smart_btn:
        # Smart Generate: use the rich page prompt to create beautiful styled HTML
        with st.spinner("🎨 AI is generating a beautiful styled page…"):
            try:
                from agent.prompts.content_prompts import RICH_PAGE_PROMPT
                import re as _re

                brain = _get_brain_router()

                # Try to fetch a reference page for context
                reference_info = ""
                ref_url_match = _re.search(r'(?:like|similar to|same as|based on|copy)\s+(https?://\S+)', agent_prompt, _re.IGNORECASE)
                if ref_url_match:
                    try:
                        cp = _get_content_processor()
                        ref_data = cp.process_url(ref_url_match.group(1))
                        ref_html = ref_data.get("html_content", "") or ref_data.get("raw_text", "")
                        if ref_html:
                            reference_info = (
                                f"\n\nREFERENCE PAGE (use the same structure, style, and layout but adapt content):\n"
                                f"{ref_html[:8000]}\n"
                            )
                    except Exception:
                        pass

                if not reference_info:
                    # Check if user mentions a studytips.in page
                    ref_slug_match = _re.search(r'(?:like|similar to|same as)\s+(?:the\s+)?(?:class[\s-]?\d+|[\w-]+)\s*(?:page)?', agent_prompt, _re.IGNORECASE)
                    if ref_slug_match:
                        try:
                            slug = ref_slug_match.group(0).split("like")[-1].split("similar to")[-1].split("same as")[-1].strip()
                            slug = _re.sub(r'\s+', '-', slug.lower().strip()).rstrip('-page').strip('-')
                            cp = _get_content_processor()
                            ref_data = cp.process_url(f"https://studytips.in/{slug}/")
                            ref_html = ref_data.get("html_content", "") or ref_data.get("raw_text", "")
                            if ref_html:
                                reference_info = (
                                    f"\n\nREFERENCE PAGE from studytips.in/{slug}/ (replicate this structure and design):\n"
                                    f"{ref_html[:8000]}\n"
                                )
                        except Exception:
                            pass

                brain_name = brain.route("create_content", priority="quality")
                content = brain.generate(
                    brain_name=brain_name,
                    prompt=RICH_PAGE_PROMPT.format(
                        user_request=agent_prompt,
                        reference_info=reference_info,
                    ),
                )
                # Clean markdown fences if AI wrapped it
                content = _re.sub(r'^```(?:html)?\s*\n?', '', content.strip())
                content = _re.sub(r'\n?```\s*$', '', content.strip())

                # Extract title from content or prompt
                title_match = _re.search(r'<h1[^>]*>(.*?)</h1>', content, _re.IGNORECASE | _re.DOTALL)
                suggested_title = title_match.group(1).strip() if title_match else agent_prompt[:80]
                # Clean HTML tags from title
                suggested_title = _re.sub(r'<[^>]+>', '', suggested_title)
                suggested_slug = _re.sub(r'[^a-z0-9]+', '-', suggested_title.lower()).strip('-')

                st.session_state["studio_result"] = {
                    "raw_text": content,
                    "html_content": content,
                    "suggested_title": suggested_title,
                    "suggested_slug": suggested_slug,
                    "suggested_meta_description": "",
                    "suggested_tags": [],
                    "suggested_headings": [],
                    "seo_score": 0,
                    "readability_score": 0,
                    "word_count": len(content.split()),
                    "image_prompt": "",
                }
                st.success(f"✅ Beautiful page generated! **{suggested_title}** — Preview below, then publish.")
            except Exception as exc:
                st.error(f"Smart generate failed: {exc}")

    # ---- initialise session keys ----------------------------------
    if "studio_chat" not in st.session_state:
        st.session_state.studio_chat = []        # chat thread for tweaking
    if "studio_images" not in st.session_state:
        st.session_state.studio_images = []       # list of {name, url, id}

    # ---- 1. Content Input -----------------------------------------
    st.markdown("### 1️⃣ Add Content")
    input_mode = st.radio(
        "Input mode",
        ["📁 Upload File", "�️ Upload Images", "🔗 Paste URL", "✍️ Write / Paste Content"],
        horizontal=True,
    )

    raw_result: dict = {}

    if input_mode == "📁 Upload File":
        uploaded = st.file_uploader(
            "Upload PDF, CSV, Excel, or Word file",
            type=["pdf", "csv", "xlsx", "xls", "docx"],
            help="Drag and drop or click to browse",
        )
        if uploaded and st.button("🔍 Process File", type="primary"):
            cp = _get_content_processor()
            with st.spinner("Processing file…"):
                ext = uploaded.name.rsplit(".", 1)[-1].lower()
                if ext == "pdf":
                    raw_result = cp.process_pdf(io.BytesIO(uploaded.read()))
                elif ext == "csv":
                    raw_result = cp.process_csv(io.StringIO(uploaded.read().decode("utf-8", errors="replace")))
                elif ext in ("xlsx", "xls"):
                    raw_result = cp.process_excel(io.BytesIO(uploaded.read()))
                elif ext == "docx":
                    raw_result = cp.process_word(io.BytesIO(uploaded.read()))
                else:
                    st.error(f"Unsupported file type: {ext}")
            st.session_state["studio_result"] = raw_result

    elif input_mode == "🖼️ Upload Images":
        st.caption("Upload up to 50 images — AI will read & extract content from them using vision.")
        content_imgs = st.file_uploader(
            "Upload images (JPG, PNG, GIF, WebP)",
            type=["jpg", "jpeg", "png", "gif", "webp"],
            accept_multiple_files=True,
            key="content_image_uploader",
        )
        img_instruction = st.text_input(
            "What should AI do with these images?",
            placeholder="e.g. Extract all text, Create a blog post from these, Describe each image…",
            value="Extract all text and content from these images and create a well-structured blog post.",
        )
        if content_imgs and st.button("🔍 Process Images with AI", type="primary"):
            import base64 as _b64

            if len(content_imgs) > 50:
                st.warning("Maximum 50 images. Only the first 50 will be processed.")
                content_imgs = content_imgs[:50]

            # Build base64 data URIs for all images
            image_data_uris = []
            with st.spinner(f"Reading {len(content_imgs)} image(s)…"):
                for img_file in content_imgs:
                    img_bytes = img_file.read()
                    ext = img_file.name.rsplit(".", 1)[-1].lower()
                    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                                "gif": "image/gif", "webp": "image/webp"}
                    mime = mime_map.get(ext, "image/jpeg")
                    b64 = _b64.b64encode(img_bytes).decode("utf-8")
                    image_data_uris.append(f"data:{mime};base64,{b64}")

            # Send to AI with vision — process in batches of 5 for large uploads
            with st.spinner("AI is reading images…"):
                try:
                    brain = _get_brain_router()
                    all_extracted = []
                    batch_size = 5
                    prog = st.progress(0, text="Processing images…")
                    for batch_start in range(0, len(image_data_uris), batch_size):
                        batch = image_data_uris[batch_start:batch_start + batch_size]
                        batch_num = batch_start // batch_size + 1
                        total_batches = (len(image_data_uris) + batch_size - 1) // batch_size

                        vision_prompt = (
                            f"Image batch {batch_num}/{total_batches}.\n\n"
                            f"Instruction: {img_instruction}\n\n"
                            f"Extract ALL text, content, and information from these {len(batch)} image(s). "
                            f"Be thorough — capture headings, paragraphs, lists, tables, "
                            f"labels, captions, and any visible text. "
                            f"Output as clean, well-structured HTML."
                        )
                        brain_name = brain.route("create_content", 1000)
                        batch_result = brain.generate(
                            brain_name=brain_name,
                            prompt=vision_prompt,
                            images=batch,
                        )
                        all_extracted.append(batch_result)
                        prog.progress(
                            min((batch_start + batch_size) / len(image_data_uris), 1.0),
                            text=f"Batch {batch_num}/{total_batches} done",
                        )
                    prog.empty()

                    combined = "\n\n".join(all_extracted)
                    # Run analysis on extracted content
                    cp = _get_content_processor()
                    raw_result = cp.process_html(combined)
                    raw_result["html_content"] = combined
                    st.session_state["studio_result"] = raw_result
                    st.success(f"✅ Extracted content from {len(content_imgs)} image(s)!")
                except Exception as exc:
                    st.error(f"Image processing failed: {exc}")

    elif input_mode == "🔗 Paste URL":
        url_input = st.text_input("Paste a URL", placeholder="https://example.com/article")
        if url_input and st.button("🔍 Fetch & Analyse", type="primary"):
            cp = _get_content_processor()
            with st.spinner(f"Fetching {url_input}…"):
                raw_result = cp.process_url(url_input)
            st.session_state["studio_result"] = raw_result

    else:  # Write / Paste Content
        content_format = st.selectbox("Format", ["Plain Text", "Markdown", "HTML"])
        content_input = st.text_area(
            "Paste or write your content here",
            height=250,
            placeholder="Start typing or paste your content…",
        )
        if content_input and st.button("🔍 Analyse Content", type="primary"):
            cp = _get_content_processor()
            with st.spinner("Analysing…"):
                if content_format == "Markdown":
                    raw_result = cp.process_markdown(content_input)
                elif content_format == "HTML":
                    raw_result = cp.process_html(content_input)
                else:
                    raw_result = cp.process_text(content_input)
            st.session_state["studio_result"] = raw_result

    # ---- 2. Multi-Image Upload (up to 50) -------------------------
    st.markdown("### 2️⃣ Add Images (optional — up to 50)")
    img_files = st.file_uploader(
        "Upload images to WordPress Media",
        type=["jpg", "jpeg", "png", "gif", "webp", "svg"],
        accept_multiple_files=True,
        key="studio_img_uploader",
    )
    if img_files:
        if len(img_files) > 50:
            st.warning("Maximum 50 images allowed. Only the first 50 will be uploaded.")
            img_files = img_files[:50]

        if st.button(f"⬆️ Upload {len(img_files)} image(s) to Media", type="primary"):
            try:
                from agent.core.config import load_config
                from agent.integrations.wordpress_api import WordPressClient
                cfg = load_config()
                wp = WordPressClient(config=cfg.wp)
            except Exception as exc:
                st.error(f"WP connection failed: {exc}")
                wp = None

            if wp:
                prog = st.progress(0, text="Uploading images…")
                uploaded_imgs = []
                for idx, img_file in enumerate(img_files):
                    try:
                        img_bytes = img_file.read()
                        fname = img_file.name
                        media = wp.upload_media_bytes(
                            data=img_bytes,
                            filename=fname,
                            alt_text=fname.rsplit(".", 1)[0].replace("-", " ").replace("_", " "),
                            title=fname.rsplit(".", 1)[0].replace("-", " ").replace("_", " "),
                        )
                        uploaded_imgs.append({
                            "name": fname,
                            "url": media.get("source_url", ""),
                            "id": media.get("id", ""),
                        })
                    except Exception as exc:
                        st.warning(f"Failed to upload {img_file.name}: {exc}")
                    prog.progress((idx + 1) / len(img_files), text=f"Uploaded {idx+1}/{len(img_files)}")
                prog.empty()
                st.session_state.studio_images.extend(uploaded_imgs)
                st.success(f"✅ Uploaded {len(uploaded_imgs)} image(s) to WordPress Media!")

    # Show uploaded image gallery
    if st.session_state.studio_images:
        with st.expander(f"🖼️ Uploaded Images ({len(st.session_state.studio_images)})", expanded=False):
            cols_per_row = 4
            imgs = st.session_state.studio_images
            for row_start in range(0, len(imgs), cols_per_row):
                row_imgs = imgs[row_start:row_start + cols_per_row]
                cols = st.columns(cols_per_row)
                for ci, img_info in enumerate(row_imgs):
                    with cols[ci]:
                        st.image(img_info["url"], caption=img_info["name"], use_container_width=True)
                        st.code(img_info["url"], language=None)

            if st.button("🗑️ Clear image gallery"):
                st.session_state.studio_images = []
                st.rerun()

    # ---- 3. Analysis Results + Chat Tweaking ----------------------
    res = st.session_state.get("studio_result", {})
    if res:
        st.markdown("---")
        st.markdown("### 3️⃣ Content Analysis")

        col1, col2, col3 = st.columns(3)
        col1.metric("Word Count", res.get("word_count", 0))
        col2.metric("SEO Score", f"{res.get('seo_score', 0)}/100")
        col3.metric("Readability", f"{res.get('readability_score', 0)}/100")

        with st.expander("✏️ Edit SEO Fields", expanded=True):
            res["suggested_title"] = st.text_input(
                "Title", value=res.get("suggested_title", "")
            )
            res["suggested_slug"] = st.text_input(
                "Slug", value=res.get("suggested_slug", "")
            )
            res["suggested_meta_description"] = st.text_area(
                "Meta Description",
                value=res.get("suggested_meta_description", ""),
                height=80,
            )
            tags_val = ", ".join(res.get("suggested_tags", []))
            tags_input = st.text_input("Tags (comma-separated)", value=tags_val)
            res["suggested_tags"] = [t.strip() for t in tags_input.split(",") if t.strip()]

        if res.get("suggested_headings"):
            with st.expander("📑 Suggested Headings"):
                for h in res["suggested_headings"]:
                    level = h.get("level", "H2") if isinstance(h, dict) else "H2"
                    text = h.get("text", str(h)) if isinstance(h, dict) else str(h)
                    st.markdown(f"**{level}** — {text}")

        # -- Chat: tweak after analysis ---
        st.markdown("#### 💬 Tweak with AI (supports vision — attach images!)")
        st.caption("Ask the AI to adjust content, analyse images, change tone, add sections, etc.")

        # Display chat history
        for msg in st.session_state.studio_chat:
            with st.chat_message(msg["role"]):
                if msg.get("images"):
                    img_cols = st.columns(min(len(msg["images"]), 4))
                    for ic, iurl in enumerate(msg["images"]):
                        with img_cols[ic % len(img_cols)]:
                            st.image(iurl, width=150)
                st.markdown(msg["content"])

        # Chat input with optional image attachment
        chat_col_text, chat_col_img = st.columns([3, 1])
        with chat_col_text:
            tweak_prompt = st.text_input(
                "Message",
                placeholder="e.g. What's in this image? / Make content friendlier / Describe this screenshot…",
                key="studio_chat_input",
                label_visibility="collapsed",
            )
        with chat_col_img:
            chat_images = st.file_uploader(
                "Attach images",
                type=["jpg", "jpeg", "png", "gif", "webp"],
                accept_multiple_files=True,
                key="studio_chat_images",
                label_visibility="collapsed",
            )

        if st.button("💬 Send", key="studio_chat_send") and (tweak_prompt or chat_images):
            import base64 as _b64

            # Build image data URIs
            image_data_uris = []
            image_previews = []
            if chat_images:
                for img_file in chat_images[:5]:  # max 5 images per message
                    img_bytes = img_file.read()
                    # Detect mime type
                    ext = img_file.name.rsplit(".", 1)[-1].lower()
                    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                                "gif": "image/gif", "webp": "image/webp"}
                    mime = mime_map.get(ext, "image/jpeg")
                    b64 = _b64.b64encode(img_bytes).decode("utf-8")
                    data_uri = f"data:{mime};base64,{b64}"
                    image_data_uris.append(data_uri)
                    image_previews.append(data_uri)

            display_text = tweak_prompt or f"[Sent {len(chat_images)} image(s)]"
            st.session_state.studio_chat.append({
                "role": "user", "content": display_text,
                "images": image_previews,
            })

            with st.chat_message("assistant"):
                with st.spinner("AI is analysing…" if image_data_uris else "AI is tweaking…"):
                    try:
                        brain = _get_brain_router()
                        current = res.get("html_content", "") or res.get("raw_text", "")

                        if image_data_uris and not tweak_prompt:
                            # Just images — describe them
                            tweak_full_prompt = (
                                "Describe what you see in the attached image(s) in detail. "
                                "If it looks like a webpage or educational content, extract the key information."
                            )
                        elif image_data_uris:
                            # Images + text instruction
                            tweak_full_prompt = (
                                f"You are editing content for an educational WordPress blog.\n\n"
                                f"Current content:\n{current[:4000]}\n\n"
                                f"The user has attached image(s) and says: {tweak_prompt}\n\n"
                                f"Analyse the images and apply the user's instruction. "
                                f"Return the FULL updated content as clean HTML."
                            )
                        else:
                            # Text only — same as before
                            tweak_full_prompt = (
                                f"You are editing content for an educational WordPress blog.\n\n"
                                f"Current content:\n{current[:5000]}\n\n"
                                f"User instruction: {tweak_prompt}\n\n"
                                f"Apply the user's instruction to the content. "
                                f"Return the FULL updated content as clean HTML. "
                                f"Do NOT add explanations — just the updated HTML content."
                            )

                        brain_name = brain.route("create_content", len(current))
                        result_text = brain.generate(
                            brain_name=brain_name,
                            prompt=tweak_full_prompt,
                            images=image_data_uris if image_data_uris else None,
                        )

                        # If it looks like HTML content, update the studio result
                        if image_data_uris and not tweak_prompt:
                            reply = result_text  # Just show description
                        else:
                            res["html_content"] = result_text
                            res["raw_text"] = result_text
                            st.session_state["studio_result"] = res
                            reply = "✅ Content updated! Check the preview below."
                    except Exception as exc:
                        reply = f"❌ Failed: {exc}"
                st.markdown(reply)
            st.session_state.studio_chat.append({"role": "assistant", "content": reply})

        # -- Beautify + image generation ---
        st.markdown("---")
        st.markdown("### 4️⃣ Beautify & Images")

        beautify_col, restyle_col, img_toggle_col, gen_img_col = st.columns([1, 1, 1, 1])
        with beautify_col:
            do_beautify = st.button("✨ Beautify Content")
        with restyle_col:
            do_restyle = st.button("🎨 Restyle (Beautiful CSS)")
        with img_toggle_col:
            insert_images = st.checkbox("🖼️ Auto-insert AI images", value=True)
        with gen_img_col:
            gen_standalone = st.button("🖼️ Generate & Upload Images Only")

        if do_beautify:
            cp = _get_content_processor()
            with st.spinner("Beautifying & uploading images to WP Media…" if insert_images else "Beautifying…"):
                enhanced = cp.enhance_content(
                    res.get("raw_text", "") or res.get("html_content", ""),
                    insert_images=insert_images,
                )
            res["html_content"] = enhanced
            st.session_state["studio_result"] = res
            st.success("✅ Content beautified!" + (" Images uploaded to Media & linked." if insert_images else ""))

        if do_restyle:
            # Restyle: take existing content and wrap it in beautiful CSS
            with st.spinner("🎨 AI is restyling with beautiful CSS…"):
                try:
                    import re as _re
                    brain = _get_brain_router()
                    current = res.get("html_content", "") or res.get("raw_text", "")
                    restyle_prompt = (
                        "You are a web designer. Take the following HTML content and restyle it to look STUNNING.\n\n"
                        "ADD a <style> block at the top with modern CSS:\n"
                        "- Gradient hero section (blues/purples)\n"
                        "- Card-based layouts with CSS grid\n"
                        "- White cards with box-shadow and border-radius\n"
                        "- Hover effects (translateY)\n"
                        "- Colored left-border on h2 headings\n"
                        "- Clean typography (Arial/sans-serif)\n"
                        "- .container max-width 1200px centered\n"
                        "- Responsive @media queries\n"
                        "- Subject grids for card layouts\n"
                        "- Professional color scheme\n\n"
                        "Keep ALL the existing content text — only add/improve the HTML structure and CSS styling.\n"
                        "Do NOT remove any content. Wrap sections in proper containers.\n\n"
                        f"Current content:\n{current[:12000]}\n\n"
                        "Return ONLY the restyled HTML with embedded <style>. No markdown fences."
                    )
                    brain_name = brain.route("create_content", priority="quality")
                    restyled = brain.generate(brain_name=brain_name, prompt=restyle_prompt)
                    restyled = _re.sub(r'^```(?:html)?\s*\n?', '', restyled.strip())
                    restyled = _re.sub(r'\n?```\s*$', '', restyled.strip())
                    res["html_content"] = restyled
                    st.session_state["studio_result"] = res
                    st.success("✅ Content restyled with beautiful CSS!")
                except Exception as exc:
                    st.error(f"Restyle failed: {exc}")

        if gen_standalone:
            # Generate images via AI and upload to WP media without beautifying
            cp = _get_content_processor()
            content_text = res.get("raw_text", "") or res.get("html_content", "")
            with st.spinner("Generating image keywords & uploading to WP Media…"):
                try:
                    brain = _get_brain_router()
                    kw_prompt = (
                        "Given this content, suggest 5 image search keywords (one per line) "
                        "that would make great illustrations. Each keyword phrase should be "
                        "3-6 words, specific, and relevant.\n\n"
                        f"Content:\n{content_text[:3000]}\n\n"
                        "Output ONLY the keywords, one per line."
                    )
                    brain_name = brain.route("general", priority="speed")
                    kw_text = brain.generate(brain_name=brain_name, prompt=kw_prompt)
                    keywords_list = [kw.strip().strip("-").strip("0123456789.").strip()
                                     for kw in kw_text.strip().split("\n") if kw.strip()][:5]

                    if cp.wp_client and keywords_list:
                        gen_imgs = []
                        prog = st.progress(0, text="Generating images…")
                        for idx, kw in enumerate(keywords_list):
                            img_url = cp._download_and_upload_image(kw)
                            if img_url:
                                gen_imgs.append({"name": kw, "url": img_url, "id": ""})
                            prog.progress((idx + 1) / len(keywords_list), text=f"Image {idx+1}/{len(keywords_list)}")
                        prog.empty()
                        st.session_state.studio_images.extend(gen_imgs)
                        st.success(f"✅ Generated & uploaded {len(gen_imgs)} images!")
                    else:
                        st.warning("WP client not available or no keywords generated.")
                except Exception as exc:
                    st.error(f"Image generation failed: {exc}")

        # Insert uploaded images into content
        if st.session_state.studio_images and res.get("html_content"):
            with st.expander("📎 Insert uploaded images into content"):
                st.caption("Click to insert an image at the end of the content.")
                for img_info in st.session_state.studio_images:
                    ic1, ic2 = st.columns([3, 1])
                    with ic1:
                        st.text(f"{img_info['name']} — {img_info['url']}")
                    with ic2:
                        if st.button(f"Insert", key=f"ins_{img_info['url'][:30]}_{img_info.get('id','')}"):
                            figure_html = (
                                f'\n<figure class="wp-block-image size-large" style="margin:1.5em 0;">'
                                f'<img src="{img_info["url"]}" alt="{img_info["name"]}" '
                                f'loading="lazy" style="border-radius:8px;width:100%;height:auto;" />'
                                f'</figure>\n'
                            )
                            res["html_content"] = res["html_content"] + figure_html
                            st.session_state["studio_result"] = res
                            st.success(f"Inserted {img_info['name']}")
                            st.rerun()

        # Content preview — use iframe for full CSS rendering
        with st.expander("📄 Content Preview", expanded=True):
            preview_html = res.get("html_content", res.get("raw_text", ""))
            if "<style>" in preview_html or "<style " in preview_html:
                # Rich styled content — render in iframe for proper CSS isolation
                import base64 as _b64_prev
                full_html = (
                    '<!DOCTYPE html><html><head><meta charset="UTF-8">'
                    '<meta name="viewport" content="width=device-width,initial-scale=1.0">'
                    '</head><body>' + preview_html + '</body></html>'
                )
                b64_html = _b64_prev.b64encode(full_html.encode("utf-8")).decode("utf-8")
                st.components.v1.html(
                    f'<iframe src="data:text/html;base64,{b64_html}" '
                    f'style="width:100%;border:1px solid #333;border-radius:8px;" '
                    f'height="800" frameborder="0"></iframe>',
                    height=820,
                )
            else:
                st.markdown(preview_html, unsafe_allow_html=True)

        # -- Post-beautification chat ---
        st.markdown("---")
        st.markdown("### 5️⃣ Final Tweaks")
        st.caption("Chat with AI to make final adjustments before publishing.")

        final_tweak = st.text_input(
            "Quick tweak instruction",
            placeholder="e.g. Add a conclusion paragraph, fix heading 3 with better text…",
            key="final_tweak_input",
        )
        if final_tweak and st.button("🔧 Apply Tweak"):
            with st.spinner("Applying tweak…"):
                try:
                    brain = _get_brain_router()
                    current = res.get("html_content", "")
                    tweak_p = (
                        f"You are editing WordPress blog HTML content.\n\n"
                        f"Current content:\n{current[:5000]}\n\n"
                        f"User instruction: {final_tweak}\n\n"
                        f"Apply the instruction. Return ONLY the full updated HTML."
                    )
                    brain_name = brain.route("create_content", len(current))
                    tweaked = brain.generate(brain_name=brain_name, prompt=tweak_p)
                    res["html_content"] = tweaked
                    st.session_state["studio_result"] = res
                    st.success("✅ Tweak applied!")
                except Exception as exc:
                    st.error(f"Tweak failed: {exc}")

        # ---- 6. Publish -------------------------------------------
        st.markdown("---")
        st.markdown("### 6️⃣ Publish")
        target_url = st.text_input(
            "Target page URL (leave blank to create new)",
            placeholder="https://studytips.in/existing-page/",
        )
        pub_col1, pub_col2, pub_col3 = st.columns(3)
        with pub_col1:
            if st.button("📝 Save as Draft Post", type="primary", use_container_width=True):
                st.info("Draft post queued — approve in **Pending Actions** tab.")
                st.session_state.setdefault("pending_actions", []).append(
                    {
                        "intent": "create_content",
                        "action_id": "studio",
                        "formatted_output": f"**Content Studio Draft**\n\nTitle: {res.get('suggested_title')}\n\nSlug: {res.get('suggested_slug')}",
                        "results": {
                            "draft_content": res.get("html_content", ""),
                            "title": res.get("suggested_title", ""),
                            "slug": res.get("suggested_slug", ""),
                        },
                        "plan": [],
                    }
                )
        with pub_col2:
            if st.button("📄 Save as Draft Page (Elementor)", use_container_width=True):
                st.info("Draft page queued — approve in **Pending Actions** tab.")
                st.session_state.setdefault("pending_actions", []).append(
                    {
                        "intent": "create_page",
                        "action_id": "studio",
                        "formatted_output": f"**Content Studio Draft (Elementor Page)**\n\nTitle: {res.get('suggested_title')}\n\nSlug: {res.get('suggested_slug')}",
                        "results": {
                            "draft_content": res.get("html_content", ""),
                            "title": res.get("suggested_title", ""),
                            "slug": res.get("suggested_slug", ""),
                        },
                        "plan": [],
                    }
                )
        with pub_col3:
            publish_type = st.selectbox("Publish as", ["Post", "Page"], key="direct_pub_type", label_visibility="collapsed")
            if st.button("🚀 Publish Directly", use_container_width=True):
                with st.spinner("Publishing to WordPress…"):
                    try:
                        from agent.core.config import load_config
                        from agent.integrations.wordpress_api import WordPressClient
                        from agent.modules.content_processor import inline_css
                        cfg = load_config()
                        wp = WordPressClient(config=cfg.wp)
                        # Inline CSS so styles survive WordPress sanitization
                        publish_html = inline_css(res.get("html_content", ""))
                        if publish_type == "Page":
                            page_html = (
                                '<div style="padding:50px 120px;">'
                                + publish_html
                                + '</div>'
                            )
                            created = wp.create_page(
                                title=res.get("suggested_title", "Untitled"),
                                content=page_html,
                                slug=res.get("suggested_slug", ""),
                                status="draft",
                                template="elementor_header_footer",
                            )
                        else:
                            created = wp.create_post(
                                title=res.get("suggested_title", "Untitled"),
                                content=publish_html,
                                slug=res.get("suggested_slug", ""),
                                status="draft",
                            )
                        post_id = created.get("id")
                        if publish_type == "Page":
                            st.success(f"✅ Full-width Elementor page created! ID: **{post_id}**")
                        else:
                            st.success(f"✅ Draft post created! ID: **{post_id}**")
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.link_button("🔗 Preview", f"https://studytips.in/?p={post_id}&preview=true")
                        with c2:
                            st.link_button("✏️ Edit in WP", f"https://studytips.in/st-admin/post.php?post={post_id}&action=edit")
                        with c3:
                            if publish_type == "Page":
                                st.link_button("🎨 Edit with Elementor", f"https://studytips.in/st-admin/post.php?post={post_id}&action=elementor")
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"❌ Publish failed: {exc}")

        # Clear studio button
        st.markdown("---")
        csc1, csc2, csc3 = st.columns([1, 1, 2])
        with csc1:
            if st.button("🗑️ Clear Studio", use_container_width=True):
                st.session_state.pop("studio_result", None)
                st.session_state.studio_chat = []
                st.session_state.studio_images = []
                st.rerun()
        with csc2:
            if st.button("🗑️ Clear Chat Only", use_container_width=True):
                st.session_state.studio_chat = []
                st.rerun()

# ==================================================================
# Tab 2: Page Updater
# ==================================================================
with tabs[1]:
    st.subheader("🔄 Page Updater")
    st.caption("Fetch an existing page by URL, view its content, and update/enhance it.")

    updater_url = st.text_input(
        "Page URL",
        placeholder="https://studytips.in/your-page/",
        key="updater_url",
    )

    if updater_url and st.button("📥 Fetch Page", type="primary"):
        with st.spinner("Fetching page…"):
            try:
                from agent.core.config import load_config
                from agent.modules.page_manager import PageManager

                config = load_config()
                pm = PageManager(brain_router=_get_brain_router(), config=config)
                page_data = pm.get_page_content(updater_url)
                st.session_state["updater_page"] = page_data
            except Exception as exc:  # noqa: BLE001
                st.error(f"Failed to fetch page: {exc}")

    page_data = st.session_state.get("updater_page", {})
    if page_data:
        if "error" in page_data:
            st.error(page_data["error"])
        else:
            st.success(f"✅ Fetched: **{page_data.get('title', '')}**")

            update_mode = st.radio(
                "Update mode",
                ["📝 Edit Content", "✨ Enhance with AI", "➕ Append Content", "🔄 Refresh SEO"],
                horizontal=True,
                key="update_mode",
            )

            current_content = page_data.get("content", "")

            if update_mode == "📝 Edit Content":
                edited = st.text_area(
                    "Edit content (HTML)",
                    value=current_content,
                    height=400,
                    key="updater_edit",
                )
                new_content = edited

            elif update_mode == "✨ Enhance with AI":
                st.info("AI will improve readability, headings, SEO, and structure.")
                enhance_instructions = st.text_input(
                    "Extra instructions (optional)",
                    placeholder="e.g. Add more examples, target Class 10 students",
                )
                updater_insert_imgs = st.checkbox("🖼️ Auto-insert images", value=True, key="updater_imgs")
                new_content = current_content
                if st.button("✨ Enhance Now"):
                    cp = _get_content_processor()
                    with st.spinner("Enhancing & generating images…" if updater_insert_imgs else "Enhancing…"):
                        new_content = cp.enhance_content(current_content, enhance_instructions, insert_images=updater_insert_imgs)
                    st.session_state["updater_new_content"] = new_content
                new_content = st.session_state.get("updater_new_content", current_content)

            elif update_mode == "➕ Append Content":
                append_text = st.text_area(
                    "Content to append",
                    height=200,
                    placeholder="New section to add at the end…",
                )
                new_content = current_content + "\n\n" + append_text

            else:  # Refresh SEO
                st.info("AI will re-optimise meta title, description, headings, and internal links.")
                new_content = current_content
                if st.button("🔄 Refresh SEO Now"):
                    cp = _get_content_processor()
                    with st.spinner("Optimising…"):
                        new_content = cp.enhance_content(
                            current_content,
                            "Re-optimise for SEO: improve headings, keyword density, internal link anchors.",
                        )
                    st.session_state["updater_new_content"] = new_content
                new_content = st.session_state.get("updater_new_content", current_content)

            # Diff viewer
            if new_content != current_content:
                with st.expander("📊 Diff View (Current vs Updated)", expanded=False):
                    try:
                        import diff_match_patch as dmp_module  # type: ignore[import-untyped]

                        dmp = dmp_module.diff_match_patch()
                        diffs = dmp.diff_main(current_content, new_content)
                        dmp.diff_cleanupSemantic(diffs)
                        diff_html = dmp.diff_prettyHtml(diffs)
                        st.markdown(diff_html, unsafe_allow_html=True)
                    except Exception:
                        import difflib
                        diff = difflib.unified_diff(
                            current_content.splitlines(keepends=True),
                            new_content.splitlines(keepends=True),
                            fromfile="current",
                            tofile="updated",
                        )
                        st.code("".join(diff))

            save_col, publish_col = st.columns(2)
            with save_col:
                if st.button("💾 Save as Draft", use_container_width=True):
                    st.session_state.setdefault("pending_actions", []).append(
                        {
                            "intent": "update_content",
                            "action_id": page_data.get("page_id", "updater"),
                            "formatted_output": f"**Update Draft**\n\nPage: {page_data.get('title', '')}\n\nURL: {updater_url}",
                            "results": {
                                "page_id": page_data.get("page_id"),
                                "updated_content": new_content,
                                "draft_content": new_content,
                            },
                            "plan": [],
                        }
                    )
                    st.success("Saved to Pending Actions for approval.")

# ==================================================================
# Tab 3: Pending Actions
# ==================================================================
with tabs[2]:
    st.subheader("Pending Actions Awaiting Approval")

    # Show last approval result (persists across reruns)
    if "last_approve_result" in st.session_state:
        r = st.session_state.pop("last_approve_result")
        if r.get("error"):
            st.error(f"❌ Publish failed: {r['error']}")
        else:
            post = r.get("post", {})
            post_id = post.get("id", "?")
            link = post.get("link", "")
            wp_status = post.get("status", "draft")
            pub_type = r.get("type", "post")
            if pub_type == "page":
                st.success(f"✅ Full-width Elementor **{wp_status}** page created — ID: **{post_id}**")
            else:
                st.success(f"✅ Draft **{wp_status}** post created — ID: **{post_id}**")
            if link or post_id:
                # For drafts, build the WP preview link
                if wp_status == "draft":
                    preview = f"https://studytips.in/?p={post_id}&preview=true"
                else:
                    preview = link or f"https://studytips.in/?p={post_id}"
                col_view, col_edit, col_elem = st.columns([1, 1, 1])
                with col_view:
                    st.link_button("🔗 View / Preview", preview)
                with col_edit:
                    st.link_button("✏️ Edit in WP", f"https://studytips.in/st-admin/post.php?post={post_id}&action=edit")
                with col_elem:
                    if pub_type == "page":
                        st.link_button("🎨 Edit with Elementor", f"https://studytips.in/st-admin/post.php?post={post_id}&action=elementor")

    pending = _get_pending()
    if not pending:
        st.info("No pending actions. Send a prompt in the Chat tab.")
    else:
        for i, action in enumerate(pending):
            with st.expander(
                f"[{action.get('intent', 'unknown')}] Action #{action.get('action_id', i)} — {action.get('created_at', '')}"
            ):
                st.markdown(action.get("formatted_output", "No output"))

                col_post, col_page, col_reject = st.columns(3)
                with col_post:
                    if st.button("📝 Approve as Post", key=f"approve_post_{i}", use_container_width=True):
                        try:
                            agent = _get_agent()
                            action["results"]["publish_as"] = "post"
                            exec_result = agent.execute_approved(action)
                            st.session_state["pending_actions"].remove(action)
                            pub = exec_result.get("published_post", {})
                            st.session_state["last_approve_result"] = {"post": pub, "type": "post"}
                        except Exception as exc:  # noqa: BLE001
                            st.session_state["last_approve_result"] = {"error": str(exc)}
                        st.rerun()
                with col_page:
                    if st.button("📄 Approve as Page", key=f"approve_page_{i}", use_container_width=True):
                        try:
                            agent = _get_agent()
                            action["results"]["publish_as"] = "page"
                            exec_result = agent.execute_approved(action)
                            st.session_state["pending_actions"].remove(action)
                            pub = exec_result.get("published_post", {})
                            st.session_state["last_approve_result"] = {"post": pub, "type": "page"}
                        except Exception as exc:  # noqa: BLE001
                            st.session_state["last_approve_result"] = {"error": str(exc)}
                        st.rerun()
                with col_reject:
                    if st.button("❌ Reject", key=f"reject_{i}", use_container_width=True):
                        agent = _get_agent()
                        agent.learn_from_rejection(action)
                        st.session_state["pending_actions"].remove(action)
                        st.warning("Rejected")
                        st.rerun()

# ==================================================================
# Tab 4: Site Stats
# ==================================================================
with tabs[3]:
    st.subheader("Site Statistics Overview")

    if st.button("🔄 Refresh Stats"):
        st.session_state.pop("site_stats", None)

    if "site_stats" not in st.session_state:
        with st.spinner("Fetching site statistics…"):
            try:
                from agent.core.config import load_config
                from agent.integrations.wordpress_api import WordPressClient

                config = load_config()
                wp = WordPressClient(config=config.wp)
                site_map = wp.get_full_site_map()
                st.session_state["site_stats"] = site_map
            except Exception as exc:  # noqa: BLE001
                st.session_state["site_stats"] = {"error": str(exc)}

    stats = st.session_state.get("site_stats", {})

    if "error" in stats:
        st.error(
            f"Could not fetch stats: {stats['error']}\n\nEnsure WP credentials are set in .env"
        )
    else:
        totals = stats.get("totals", {})
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Posts", totals.get("posts", 0))
        c2.metric("Pages", totals.get("pages", 0))
        c3.metric("Categories", totals.get("categories", 0))
        c4.metric("Tags", totals.get("tags", 0))

        if stats.get("categories"):
            st.subheader("Categories")
            cat_data = [
                {"Name": c.get("name", ""), "Posts": c.get("count", 0)}
                for c in stats["categories"][:10]
            ]
            st.dataframe(cat_data, use_container_width=True)

    # Brain usage stats
    st.markdown("---")
    st.subheader("🧠 Brain Usage Statistics")
    try:
        br = _get_brain_router()
        brain_stats = br.get_brain_stats()
        if brain_stats:
            rows = [
                {
                    "Brain": name,
                    "Calls": s["call_count"],
                    "Failures": s["failure_count"],
                    "Avg Response (s)": s["avg_response_time"],
                    "Total Tokens": s["total_tokens"],
                }
                for name, s in brain_stats.items()
            ]
            st.dataframe(rows, use_container_width=True)
        else:
            st.info("No brain usage data yet.")
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not load brain stats: {exc}")

# ==================================================================
# Tab 5: Site Power
# ==================================================================
with tabs[4]:
    st.subheader("⚡ Site Power Tools")
    st.caption(
        "Deep site intelligence for studytips.in — crawl, auto-link, fix drafts, "
        "create missing pages, and analyse design. All changes are created as DRAFTS."
    )

    power_tabs = st.tabs(["🕷️ Deep Crawl", "🔗 Auto-Link", "🧭 Nav Placement", "📄 Missing Pages", "🎨 Design", "🚀 Auto-Fix All"])

    # --- Deep Crawl ---
    with power_tabs[0]:
        st.markdown("### 🕷️ Deep Site Crawl")
        st.markdown("Scan the entire site: find all pages, posts, drafts, orphans, broken internal links, and missing pages.")
        if st.button("🔍 Start Deep Crawl", key="power_crawl_btn", use_container_width=True):
            with st.spinner("Crawling studytips.in — this may take a minute…"):
                try:
                    from agent.modules.site_power import SitePower
                    _cfg = _get_agent().config
                    _br = _get_brain_router()
                    power = SitePower(brain_router=_br, config=_cfg)
                    crawl_result = power.deep_crawl()
                    st.session_state["power_crawl"] = crawl_result
                except Exception as _e:
                    st.error(f"Crawl failed: {_e}")

        if "power_crawl" in st.session_state:
            cr = st.session_state["power_crawl"]
            totals = cr.get("totals", {})
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("Pages", totals.get("published_pages", 0))
            c2.metric("Posts", totals.get("published_posts", 0))
            c3.metric("Drafts", totals.get("drafts", 0))
            c4.metric("Internal Links", totals.get("internal_links", 0))
            c5.metric("Orphan Pages", totals.get("orphan_pages", 0))
            c6.metric("Missing Pages", totals.get("missing_pages", 0))

            if cr.get("orphan_pages"):
                with st.expander(f"🔴 Orphan Pages ({len(cr['orphan_pages'])})"):
                    for op in cr["orphan_pages"]:
                        st.write(f"• **{op.get('title', 'Untitled')}** — {op.get('url', '')}")

            if cr.get("missing_pages"):
                with st.expander(f"🟡 Missing Pages ({len(cr['missing_pages'])})"):
                    for mp in cr["missing_pages"]:
                        st.write(f"• **{mp.get('suggested_title', '')}** — `{mp.get('url', '')}`")

            if cr.get("draft_pages") or cr.get("draft_posts"):
                all_drafts = cr.get("draft_pages", []) + cr.get("draft_posts", [])
                with st.expander(f"📝 Drafts ({len(all_drafts)})"):
                    for d in all_drafts:
                        st.write(f"• [{d.get('type', 'post')}] **{d.get('title', 'Untitled')}** (ID: {d.get('id')})")

    # --- Auto-Link ---
    with power_tabs[1]:
        st.markdown("### 🔗 Auto-Link Drafts")
        st.markdown("Scan all draft pages/posts and **preview** suggested internal links before applying. Only relevant topics are suggested.")
        if st.button("🔍 Analyse Drafts for Links", key="power_autolink_btn", use_container_width=True):
            with st.spinner("Analysing drafts for relevant internal links…"):
                try:
                    from agent.modules.site_power import SitePower
                    _cfg = _get_agent().config
                    _br = _get_brain_router()
                    power = SitePower(brain_router=_br, config=_cfg)
                    link_results = power.auto_link_drafts()
                    st.session_state["power_autolink"] = link_results
                    # Reset approvals
                    st.session_state.pop("autolink_approved", None)
                except Exception as _e:
                    st.error(f"Auto-link analysis failed: {_e}")

        if "power_autolink" in st.session_state:
            lr = st.session_state["power_autolink"]
            has_suggestions = [r for r in lr if r.get("status") == "suggestions_ready"]
            no_links = [r for r in lr if r.get("status") == "no_relevant_links"]

            if not has_suggestions and not no_links:
                st.info("No drafts found to analyse.")
            else:
                if no_links:
                    st.caption(f"⏭️ {len(no_links)} draft(s) have no relevant pages to link to")

                for idx, draft_result in enumerate(has_suggestions):
                    draft_title = draft_result.get("title", "Untitled")
                    draft_id = draft_result.get("id")
                    draft_type = draft_result.get("type", "post")
                    suggestions = draft_result.get("suggestions", [])

                    with st.expander(f"📝 {draft_title} — {len(suggestions)} link(s) suggested", expanded=True):
                        approved_links = []
                        for si, sug in enumerate(suggestions):
                            cb_key = f"link_{draft_id}_{si}"
                            checked = st.checkbox(
                                f"🔗 **{sug.get('anchor_text', '')}** → [{sug.get('target_title', '')}]({sug.get('target_url', '')})",
                                value=True,
                                key=cb_key,
                            )
                            st.caption(f"  Reason: {sug.get('relevance_reason', '')}")
                            st.caption(f"  Insert near: _{sug.get('insert_near', '')[:100]}_")
                            if checked:
                                approved_links.append(sug)

                        if st.button(f"✅ Apply {len(approved_links)} Link(s)", key=f"apply_links_{draft_id}", use_container_width=True, disabled=len(approved_links) == 0):
                            with st.spinner(f"Inserting links into '{draft_title}'…"):
                                try:
                                    from agent.modules.site_power import SitePower
                                    _cfg = _get_agent().config
                                    _br = _get_brain_router()
                                    power = SitePower(brain_router=_br, config=_cfg)
                                    result = power.apply_link_suggestions(draft_id, draft_type, approved_links)
                                    if result.get("status") == "applied":
                                        st.success(f"✅ {result.get('links_added', 0)} links inserted into '{draft_title}'!")
                                    elif result.get("status") == "no_change":
                                        st.warning("Links could not be inserted (content may have changed).")
                                    else:
                                        st.error(f"Error: {result.get('error', 'Unknown')}")
                                except Exception as _e:
                                    st.error(f"Apply failed: {_e}")

                for r in lr:
                    if r.get("status") == "error":
                        st.error(f"❌ **{r.get('title', 'Unknown')}** — {r.get('error', 'failed')}")

    # --- Nav Placement ---
    with power_tabs[2]:
        st.markdown("### 🧭 Draft Navigation Placement")
        st.markdown("Analyse each draft page and set the correct parent page + menu position automatically.")
        if st.button("🧭 Place All Drafts", key="power_nav_btn", use_container_width=True):
            with st.spinner("Analysing drafts for navigation placement…"):
                try:
                    from agent.modules.site_power import SitePower
                    _cfg = _get_agent().config
                    _br = _get_brain_router()
                    power = SitePower(brain_router=_br, config=_cfg)
                    nav_results = power.place_drafts_in_nav()
                    st.session_state["power_nav"] = nav_results
                except Exception as _e:
                    st.error(f"Nav placement failed: {_e}")

        if "power_nav" in st.session_state:
            nr = st.session_state["power_nav"]
            for r in nr:
                if r.get("status") == "placed":
                    st.write(f"✅ **{r.get('title')}** → parent #{r.get('parent_id', 0)}, {r.get('menu_section', 'primary')} menu")
                    if r.get("reasoning"):
                        st.caption(r["reasoning"])
                elif r.get("status") == "no_drafts":
                    st.info(r.get("message", "No draft pages found"))
                else:
                    st.write(f"❌ **{r.get('title', 'Unknown')}** — {r.get('error', 'failed')}")

    # --- Missing Pages ---
    with power_tabs[3]:
        st.markdown("### 📄 Create Missing Pages")
        st.markdown("Find internal links pointing to non-existent pages, create them with AI-generated content, and set correct parent pages.")
        if st.button("📄 Find & Create Missing Pages", key="power_missing_btn", use_container_width=True):
            with st.spinner("Finding missing pages and creating content…"):
                try:
                    from agent.modules.site_power import SitePower
                    _cfg = _get_agent().config
                    _br = _get_brain_router()
                    power = SitePower(brain_router=_br, config=_cfg)
                    missing_results = power.create_missing_pages()
                    st.session_state["power_missing"] = missing_results
                except Exception as _e:
                    st.error(f"Page creation failed: {_e}")

        if "power_missing" in st.session_state:
            mr = st.session_state["power_missing"]
            created = [r for r in mr if r.get("status") == "created_as_draft"]
            if created:
                st.success(f"✅ {len(created)} pages created as drafts")
            for r in mr:
                if r.get("status") == "created_as_draft":
                    st.write(f"✅ **{r.get('title')}** (ID: {r.get('id')}) — parent #{r.get('parent_id', 0)}")
                elif r.get("status") == "none_missing":
                    st.info(r.get("message", "All links resolve correctly"))
                else:
                    st.write(f"❌ **{r.get('title', 'Unknown')}** — {r.get('error', 'failed')}")

    # --- Design Analysis ---
    with power_tabs[4]:
        st.markdown("### 🎨 Live Design Analysis")
        st.markdown("Fetch the actual studytips.in homepage and analyse CSS, speed, UX, and structure.")
        if st.button("🎨 Analyse Design", key="power_design_btn", use_container_width=True):
            with st.spinner("Fetching and analysing live site…"):
                try:
                    from agent.modules.site_power import SitePower
                    _cfg = _get_agent().config
                    _br = _get_brain_router()
                    power = SitePower(brain_router=_br, config=_cfg)
                    design_results = power.analyze_design()
                    st.session_state["power_design"] = design_results
                except Exception as _e:
                    st.error(f"Design analysis failed: {_e}")

        if "power_design" in st.session_state:
            dr = st.session_state["power_design"]
            if "error" in dr:
                st.error(dr["error"])
            else:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Load Time", f"{dr.get('load_time_ms', '?')}ms")
                c2.metric("Page Size", f"{dr.get('page_size_kb', '?')}KB")
                c3.metric("Images", dr.get("images", 0))
                c4.metric("CSS/JS Files", f"{dr.get('css_files', 0)}/{dr.get('js_files', 0)}")

                if dr.get("automated_issues"):
                    st.markdown("#### 🔴 Issues Found")
                    for issue in dr["automated_issues"]:
                        st.warning(issue)

                if dr.get("suggestions"):
                    st.markdown("#### 💡 Suggestions")
                    for sug in dr["suggestions"]:
                        st.info(sug)

                llm = dr.get("llm_analysis", {})
                if isinstance(llm, dict) and llm.get("improvements"):
                    st.markdown("#### 🤖 AI Design Recommendations")
                    for imp in llm["improvements"]:
                        with st.expander(f"{'🔴' if imp.get('impact') == 'high' else '🟡' if imp.get('impact') == 'medium' else '🟢'} {imp.get('title', 'Improvement')}"):
                            st.markdown(imp.get("description", ""))
                            if imp.get("code_snippet"):
                                st.code(imp["code_snippet"], language="css")

    # --- Auto-Fix All ---
    with power_tabs[5]:
        st.markdown("### 🚀 Auto-Fix Everything")
        st.markdown(
            "One-click: auto-link all drafts, place them in correct navigation, "
            "and create any missing pages. All changes are drafts."
        )
        st.warning("⚠️ This runs multiple operations and may take several minutes.")
        if st.button("🚀 Run Auto-Fix All", key="power_autofix_btn", type="primary", use_container_width=True):
            with st.spinner("Running full auto-fix pipeline…"):
                try:
                    from agent.modules.site_power import SitePower
                    _cfg = _get_agent().config
                    _br = _get_brain_router()
                    power = SitePower(brain_router=_br, config=_cfg)
                    fix_results = power.auto_fix_all()
                    st.session_state["power_autofix"] = fix_results
                except Exception as _e:
                    st.error(f"Auto-fix failed: {_e}")

        if "power_autofix" in st.session_state:
            fr = st.session_state["power_autofix"]

            al = fr.get("auto_linked", {})
            np_ = fr.get("nav_placed", {})
            pc = fr.get("pages_created", {})

            c1, c2, c3 = st.columns(3)
            c1.metric("Drafts Linked", al.get("count", 0))
            c2.metric("Drafts Placed", np_.get("count", 0))
            c3.metric("Pages Created", pc.get("count", 0))

            if al.get("details"):
                with st.expander("🔗 Auto-Link Details"):
                    for r in al["details"]:
                        st.write(f"{'✅' if r.get('status') == 'updated' else '⏭️'} {r.get('title', '')} — {r.get('links_added', 0)} links")

            if np_.get("details"):
                with st.expander("🧭 Navigation Placement Details"):
                    for r in np_["details"]:
                        st.write(f"{'✅' if r.get('status') == 'placed' else '❌'} {r.get('title', '')} → parent #{r.get('parent_id', 0)}")

            if pc.get("details"):
                with st.expander("📄 Created Pages"):
                    for r in pc["details"]:
                        st.write(f"{'✅' if r.get('status') == 'created_as_draft' else '❌'} {r.get('title', '')} (ID: {r.get('id', '?')})")

            for err_key in ["auto_link_error", "nav_placement_error", "page_creation_error"]:
                if fr.get(err_key):
                    st.error(f"{err_key}: {fr[err_key]}")

# ==================================================================
# Tab 6: Settings
# ==================================================================
with tabs[5]:
    st.subheader("⚙️ Settings")

    try:
        br = _get_brain_router()
        brains = br.list_brains()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not load brain router: {exc}")
        brains = []
        br = None

    # ==================================================================
    # Quick Add Models
    # ==================================================================
    st.markdown("### 🚀 Quick Add Models")
    st.caption("Add pre-configured models with one click. API keys are resolved automatically from environment variables.")

    try:
        from agent.core.config import load_config as _load_cfg
        _cfg = _load_cfg()
    except Exception:
        _cfg = None

    # Group presets by provider family
    _preset_groups = {
        "🖥️ NVIDIA Models": {
            k: v for k, v in br.get_preset_models().items() if v["provider"] == "nvidia"
        } if br else {},
        "🎓 GitHub Student Pack Models": {
            k: v for k, v in br.get_preset_models().items() if v["provider"] == "github_models"
        } if br else {},
        "🌐 OpenRouter Models": {
            k: v for k, v in br.get_preset_models().items() if v["provider"] == "openrouter"
        } if br else {},
    }

    _active_brain_names = {b["name"] for b in brains}

    for group_label, group_presets in _preset_groups.items():
        if not group_presets:
            continue
        st.markdown(f"#### {group_label}")
        _cols = st.columns(3)
        for idx, (preset_name, preset_meta) in enumerate(group_presets.items()):
            with _cols[idx % 3]:
                already_added = preset_name in _active_brain_names
                status_icon = "🟢" if already_added else "➕"
                cost_badge = {"free": "🆓", "low": "💚", "medium": "💛", "high": "🔴"}.get(
                    preset_meta.get("cost_tier", "medium"), "💛"
                )
                speed_stars = "⚡" * int(preset_meta.get("speed_rating", 3))
                ctx_k = int(preset_meta.get("context_window", 8192)) // 1000
                best_for_str = ", ".join(preset_meta.get("best_for", [])[:2])

                st.markdown(
                    f"""
                    <div style="background:#1c1f26;border-radius:8px;padding:10px;margin-bottom:8px;
                                border-left:3px solid {'#48bb78' if already_added else '#4a90d9'}">
                    <b>{status_icon} {preset_name}</b><br>
                    <small><code>{preset_meta['model']}</code></small><br>
                    <small>{cost_badge} {preset_meta.get('cost_tier','?')} &nbsp;|&nbsp; {speed_stars} &nbsp;|&nbsp; {ctx_k}k ctx</small><br>
                    <small>🎯 {best_for_str}</small>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if already_added:
                    st.success("Already added", icon="✅")
                else:
                    if st.button(f"➕ Add", key=f"quick_add_{preset_name}"):
                        if br:
                            try:
                                br.add_preset(preset_name)
                                st.success(f"✅ '{preset_name}' added!")
                                st.rerun()
                            except Exception as exc:  # noqa: BLE001
                                st.error(str(exc))

    # ==================================================================
    # GitHub Copilot Login
    # ==================================================================
    st.markdown("---")
    st.markdown("### 🤖 GitHub Copilot Login")
    st.caption(
        "Sign in with your GitHub account to use Copilot models (gpt-4o, o3-mini, claude-3.5-sonnet). "
        "Works just like VS Code — no token copy-pasting needed."
    )

    _gh_token = os.environ.get("GITHUB_COPILOT_TOKEN", "")

    # Treat obvious placeholder values as empty
    try:
        from agent.integrations.copilot_auth import is_real_github_token
        _token_is_real = is_real_github_token(_gh_token)
    except Exception:
        _token_is_real = bool(_gh_token)

    if _gh_token and _token_is_real:
        _masked_gh = f"…{_gh_token[-4:]}"
        st.success(f"✅ Connected to GitHub Copilot  (token: `{_masked_gh}`)")
        _col_test_cop, _col_logout_cop = st.columns(2)
        with _col_test_cop:
            if st.button("🧪 Test Copilot Connection", key="copilot_test_btn"):
                with st.spinner("Testing Copilot API…"):
                    try:
                        from agent.integrations.copilot_auth import get_token as _gct
                        _tok = _gct()
                        if not _tok:
                            st.error("❌ Could not obtain a Copilot token. Try logging in again.")
                        else:
                            import requests as _req
                            _r = _req.post(
                                "https://api.githubcopilot.com/chat/completions",
                                headers={
                                    "Authorization": f"Bearer {_tok}",
                                    "Accept": "application/json",
                                    "Content-Type": "application/json",
                                    "Editor-Version": "vscode/1.90.0",
                                },
                                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
                                timeout=15,
                            )
                            if _r.status_code in (200, 201):
                                st.success("✅ Copilot API is working!")
                            else:
                                st.error(f"❌ Copilot API returned {_r.status_code}: {_r.text[:200]}")
                    except Exception as _e:
                        st.error(f"❌ {_e}")
        with _col_logout_cop:
            if st.button("🚪 Disconnect", key="copilot_logout_btn"):
                os.environ.pop("GITHUB_COPILOT_TOKEN", None)
                from agent.integrations.copilot_auth import _token_manager
                _token_manager.invalidate()
                # Remove from .env
                try:
                    from agent.integrations.copilot_auth import ENV_FILE
                    if ENV_FILE.exists():
                        _lines = ENV_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
                        ENV_FILE.write_text(
                            "".join(l for l in _lines if not l.startswith("GITHUB_COPILOT_TOKEN=")),
                            encoding="utf-8",
                        )
                except Exception:
                    pass
                st.warning("Disconnected from GitHub Copilot.")
                st.rerun()
    elif _gh_token and not _token_is_real:
        st.warning(
            "⚠️ A placeholder value is stored for `GITHUB_COPILOT_TOKEN`. "
            "Please use the **Login with GitHub** button below to connect."
        )
    else:
        st.info(
            "Not connected. Click **Login** to open GitHub in your browser "
            "and authorise with a one-time code."
        )
        if st.button("🔑 Login with GitHub", type="primary", key="copilot_login_btn"):
            with st.spinner("Starting device flow…"):
                try:
                    from agent.integrations.copilot_auth import request_device_code
                    _dc = request_device_code()
                    st.session_state["copilot_device_data"] = _dc
                except Exception as _e:
                    st.error(f"Failed to start login: {_e}")

        # Show the user_code once device flow has started
        if "copilot_device_data" in st.session_state:
            _dc = st.session_state["copilot_device_data"]
            _uri = _dc.get("verification_uri", "https://github.com/login/device")
            _code = _dc.get("user_code", "")

            import webbrowser as _wb
            _wb.open(_uri)

            st.markdown(
                f"""
                <div style="background:#1c1f26;border-radius:10px;padding:20px;text-align:center;border:2px solid #4CAF50;">
                <h3 style="color:#68d391">Your one-time code</h3>
                <h1 style="letter-spacing:8px;color:#fff">{_code}</h1>
                <p>Visit <a href="{_uri}" target="_blank">{_uri}</a> and enter the code above.</p>
                <p style="color:#888;font-size:0.85rem">Browser should have opened automatically.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button("✅ I've authorised — complete login", key="copilot_poll_btn"):
                with st.spinner("Checking authorisation…"):
                    try:
                        from agent.integrations.copilot_auth import (
                            poll_for_token, get_copilot_token,
                            save_github_token_to_env, _token_manager,
                        )
                        _gh_tok = poll_for_token(
                            _dc["device_code"],
                            interval=int(_dc.get("interval", 5)),
                            expires_in=int(_dc.get("expires_in", 900)),
                        )
                        get_copilot_token(_gh_tok)   # validate subscription
                        save_github_token_to_env(_gh_tok)
                        _token_manager.invalidate()
                        del st.session_state["copilot_device_data"]
                        # Auto-sync all Copilot models immediately after login
                        try:
                            _br2 = _get_brain_router()
                            _synced = _br2.sync_copilot_brains(_gh_tok)
                            st.success(f"✅ GitHub Copilot connected! {len(_synced)} models synced. Reloading…")
                        except Exception:
                            st.success("✅ GitHub Copilot connected! Reloading…")
                        st.rerun()
                    except Exception as _e:
                        st.error(f"Login failed: {_e}")

    # Sync models button when already connected
    if _gh_token and _token_is_real:
        st.markdown("---")
        _sync_col, _sync_info = st.columns([1, 3])
        with _sync_col:
            if st.button("🔄 Sync All Copilot Models", key="copilot_sync_btn", use_container_width=True):
                with st.spinner("Fetching model list from GitHub Copilot…"):
                    try:
                        _br3 = _get_brain_router()
                        _synced = _br3.sync_copilot_brains(_gh_token)
                        st.success(f"✅ {len(_synced)} Copilot models added to brain selector!")
                        st.rerun()
                    except Exception as _se:
                        st.error(f"Sync failed: {_se}")
        with _sync_info:
            st.caption("Pulls the full model list from your Copilot account — same models as VS Code's model picker (GPT-4.1, Claude Sonnet/Opus, Gemini, Grok, etc.)")

    # ==================================================================
    # API Keys
    # ==================================================================
    st.markdown("---")
    st.markdown("### 🔑 API Keys")
    st.caption(
        "Set or update API keys for each provider. Keys are masked for security. "
        "⚠️ Keys saved here are applied to the current process only — add them to your `.env` file for persistence across restarts."
    )

    def _mask_key(key: str) -> str:
        """Return masked key showing only last 4 characters."""
        if not key:
            return "*(not set)*"
        return f"…{key[-4:]}"

    _key_providers = [
        ("NVIDIA API Key", "NVIDIA_API_KEY", "nvapi-…"),
        ("OpenRouter API Key", "OPENROUTER_API_KEY", "sk-or-…"),
        ("GitHub Token", "GITHUB_TOKEN", "ghp_…"),
        ("Kimi API Key", "KIMI_API_KEY", "sk-…"),
        ("Ollama Host", "OLLAMA_HOST", "http://localhost:11434"),
    ]

    for label, env_var, placeholder in _key_providers:
        current_val = os.environ.get(env_var, "")
        col_lbl, col_val, col_inp, col_save, col_test = st.columns([2, 1, 3, 1, 1])
        with col_lbl:
            st.write(f"**{label}**")
        with col_val:
            st.caption(_mask_key(current_val))
        with col_inp:
            new_val = st.text_input(
                label,
                type="password",
                placeholder=placeholder,
                label_visibility="collapsed",
                key=f"apikey_input_{env_var}",
            )
        with col_save:
            if st.button("💾", key=f"apikey_save_{env_var}", help="Save key to environment"):
                if new_val:
                    os.environ[env_var] = new_val
                    # Invalidate cached clients so they pick up the new key
                    if br:
                        br.clear_client_cache()
                    st.success("Saved!")
                    st.rerun()
        with col_test:
            if st.button("🧪", key=f"apikey_test_{env_var}", help="Test connection"):
                test_val = new_val or current_val
                if not test_val:
                    st.warning("No key set.")
                else:
                    with st.spinner("Testing…"):
                        _ok = False
                        try:
                            if env_var == "NVIDIA_API_KEY":
                                from agent.integrations.nvidia_client import NvidiaClient
                                _c = NvidiaClient(api_key=test_val)
                                _c.chat_completion(
                                    messages=[{"role": "user", "content": "Hi"}],
                                    model="nvidia/llama-3.1-nemotron-70b-instruct",
                                    max_tokens=5,
                                )
                                _ok = True
                            elif env_var == "OPENROUTER_API_KEY":
                                from agent.integrations.openrouter_client import OpenRouterClient
                                _c = OpenRouterClient(api_key=test_val)
                                _c.chat_completion(
                                    messages=[{"role": "user", "content": "Hi"}],
                                    model="openai/gpt-4o-mini",
                                    max_tokens=5,
                                )
                                _ok = True
                            elif env_var == "GITHUB_TOKEN":
                                from agent.integrations.github_models_client import GitHubModelsClient
                                _c = GitHubModelsClient(token=test_val)
                                _c.chat_completion(
                                    messages=[{"role": "user", "content": "Hi"}],
                                    model="gpt-4o-mini",
                                    max_tokens=5,
                                )
                                _ok = True
                            elif env_var == "KIMI_API_KEY":
                                from agent.integrations.kimi_client import KimiClient
                                _c = KimiClient(api_key=test_val)
                                _c.chat_completion(
                                    messages=[{"role": "user", "content": "Hi"}],
                                    max_tokens=5,
                                )
                                _ok = True
                            elif env_var == "OLLAMA_HOST":
                                import requests as _req
                                _r = _req.get(f"{test_val}/api/tags", timeout=5)
                                _ok = _r.status_code == 200
                        except Exception as _exc:  # noqa: BLE001
                            st.error(f"❌ {_exc}")
                    if _ok:
                        st.success("✅ Connection OK!")

    # ==================================================================
    # Active Models
    # ==================================================================
    st.markdown("---")
    st.markdown("### 📋 Active Models")

    if st.button("🧪 Test All Models", key="test_all_models"):
        if br:
            _results = {}
            with st.spinner("Testing all models…"):
                for _b in brains:
                    _results[_b["name"]] = br.test_brain(_b["name"])
            for _name, _ok in _results.items():
                if _ok:
                    st.success(f"✅ {_name}")
                else:
                    st.error(f"❌ {_name}")

    if brains:
        for b in brains:
            avail_icon = "🟢" if b["available"] else "🔴"
            key_icon = "🔑" if b.get("api_key_set") else "⚠️"
            with st.expander(
                f"{avail_icon} **{b['name']}** — {b['provider']} / `{b['model']}`"
            ):
                col_info, col_actions = st.columns([2, 1])
                with col_info:
                    st.write(f"**Cost tier:** {b['cost_tier']}")
                    st.write(f"**Speed rating:** {'⚡' * b['speed_rating']}")
                    st.write(f"**Context window:** {b['context_window']:,} tokens")
                    st.write(f"**Best for:** {', '.join(b['best_for']) or 'general'}")
                    st.write(f"**API key:** {key_icon} {'Set' if b.get('api_key_set') else 'Not set'}")
                with col_actions:
                    if st.button(f"🧪 Test", key=f"test_{b['name']}"):
                        with st.spinner(f"Testing {b['name']}…"):
                            ok = br.test_brain(b["name"])
                        if ok:
                            st.success("✅ Brain is working!")
                        else:
                            st.error("❌ Brain failed the test.")

                    new_key = st.text_input(
                        "New API Key",
                        type="password",
                        key=f"key_{b['name']}",
                        placeholder="Paste new API key…",
                    )
                    if new_key and st.button("💾 Update Key", key=f"save_key_{b['name']}"):
                        try:
                            br.update_brain_api_key(b["name"], new_key)
                            st.success("API key updated!")
                        except Exception as exc:  # noqa: BLE001
                            st.error(str(exc))

                    if st.button(f"🗑️ Remove", key=f"remove_{b['name']}"):
                        br.remove_brain(b["name"])
                        st.warning(f"Brain '{b['name']}' removed.")
                        st.rerun()

    # ==================================================================
    # Add New Model (manual)
    # ==================================================================
    st.markdown("---")
    st.markdown("#### ➕ Add New Model (Manual)")

    with st.form("add_brain_form"):
        col_a, col_b = st.columns(2)
        with col_a:
            new_name = st.text_input("Display Name *", placeholder="my_claude")
            new_provider = st.selectbox(
                "Provider *",
                ["openrouter", "ollama", "nvidia", "github_models", "kimi", "github_copilot", "openai", "custom"],
            )
            new_model = st.text_input("Model ID *", placeholder="anthropic/claude-3-haiku")
            new_api_key = st.text_input("API Key / Host URL", type="password")
        with col_b:
            new_cost = st.selectbox("Cost Tier", ["free", "low", "medium", "high"])
            new_speed = st.slider("Speed Rating", 1, 5, 3)
            new_ctx = st.number_input("Context Window (tokens)", value=8192, step=1024)
            new_best_for = st.multiselect(
                "Best For",
                [
                    "create_content", "update_content", "seo_optimize", "site_audit",
                    "content_plan", "analytics", "bulk_update", "keyword_research",
                    "general", "quick_tasks", "summarize", "technical_tasks",
                    "long_context", "code_generation", "classify",
                ],
            )

        submitted = st.form_submit_button("➕ Add Brain", type="primary")
        if submitted:
            if not new_name or not new_model:
                st.error("Display Name and Model ID are required.")
            else:
                try:
                    br.add_brain(
                        name=new_name,
                        provider=new_provider,
                        model=new_model,
                        api_key=new_api_key,
                        best_for=new_best_for,
                        cost_tier=new_cost,
                        speed_rating=new_speed,
                        context_window=int(new_ctx),
                    )
                    st.success(f"✅ Brain '{new_name}' added successfully!")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Failed to add brain: {exc}")

    # ---- Auto-detect Ollama ----
    st.markdown("---")
    st.markdown("#### 🔍 Auto-detect Local Ollama Models")
    if st.button("🔍 Scan Ollama"):
        try:
            import subprocess
            result_proc = subprocess.run(
                ["ollama", "list"], capture_output=True, text=True, timeout=10
            )
            if result_proc.returncode == 0:
                lines = result_proc.stdout.strip().splitlines()
                if len(lines) > 1:
                    st.markdown("**Available Ollama models:**")
                    for line in lines[1:]:  # skip header
                        cols = line.split()
                        if cols:
                            model_name = cols[0]
                            st.write(f"• `{model_name}`")
                else:
                    st.info("No Ollama models installed.")
            else:
                st.warning("Ollama not running or not installed.")
        except Exception as exc:  # noqa: BLE001
            st.warning(f"Could not run ollama list: {exc}")

    # ---- WordPress Connection ----
    st.markdown("---")
    st.markdown("### 🌐 WordPress Connection")
    if st.button("🧪 Test WordPress Connection"):
        with st.spinner("Testing connection…"):
            try:
                from agent.core.config import load_config
                from agent.integrations.wordpress_api import WordPressClient

                config = load_config()
                wp = WordPressClient(config=config.wp)
                site_map = wp.get_full_site_map()
                totals = site_map.get("totals", {})
                st.success(
                    f"✅ Connected! Posts: {totals.get('posts', 0)}, Pages: {totals.get('pages', 0)}"
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"❌ Connection failed: {exc}")

    # ---- Agent Preferences ----
    st.markdown("---")
    st.markdown("### 🎛️ Agent Preferences")
    try:
        from agent.core.config import load_config
        config = load_config()
        st.write(f"**Default post status:** `{config.agent.default_post_status}`")
        st.write(f"**Content language:** `{config.agent.content_language}`")
        st.write(f"**Agent mode:** `{config.agent.mode}`")
        st.write(f"**Memory DB:** `{config.agent.memory_db_path}`")
        st.write(f"**Custom brains DB:** `{config.agent.custom_brains_db_path}`")
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not load config: {exc}")

