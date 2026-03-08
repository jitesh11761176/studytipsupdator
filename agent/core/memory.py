"""Self-learning memory system for StudyTips AI Agent using SQLite.

Stores interaction logs, style preferences, content performance metrics,
site knowledge, and winning strategies to enable continuous improvement.
"""

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional


class AgentMemory:
    """SQLite-backed memory for self-learning agent behaviour.

    Tables:
        action_log: Every agent interaction.
        style_preferences: Learned writing style patterns.
        content_performance: Post performance metrics.
        site_knowledge: Facts about the site.
        winning_strategies: Strategies with positive outcomes.
    """

    def __init__(self, db_path: str = "data/memory.db") -> None:
        """Initialise the memory store and create tables if needed.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create all required tables if they do not already exist."""
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS action_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at  TEXT    NOT NULL,
                    prompt      TEXT    NOT NULL,
                    intent      TEXT    NOT NULL,
                    plan        TEXT,
                    results     TEXT,
                    approved    INTEGER DEFAULT NULL
                );

                CREATE TABLE IF NOT EXISTS style_preferences (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    key         TEXT    NOT NULL UNIQUE,
                    value       TEXT    NOT NULL,
                    updated_at  TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS content_performance (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id      TEXT    NOT NULL UNIQUE,
                    url          TEXT,
                    keywords     TEXT,
                    views        INTEGER DEFAULT 0,
                    position     REAL    DEFAULT 0,
                    bounce_rate  REAL    DEFAULT 0,
                    updated_at   TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS site_knowledge (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic      TEXT    NOT NULL,
                    fact       TEXT    NOT NULL,
                    source     TEXT,
                    created_at TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS winning_strategies (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_type  TEXT    NOT NULL,
                    description    TEXT    NOT NULL,
                    success_count  INTEGER DEFAULT 1,
                    created_at     TEXT    NOT NULL,
                    updated_at     TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS custom_brains (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    name           TEXT    NOT NULL UNIQUE,
                    provider       TEXT    NOT NULL,
                    model          TEXT    NOT NULL,
                    api_key        TEXT    NOT NULL DEFAULT '',
                    best_for       TEXT    NOT NULL DEFAULT '[]',
                    cost_tier      TEXT    NOT NULL DEFAULT 'medium',
                    speed_rating   INTEGER NOT NULL DEFAULT 3,
                    context_window INTEGER NOT NULL DEFAULT 8192,
                    created_at     TEXT    NOT NULL,
                    updated_at     TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS brain_usage_stats (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    brain_name     TEXT    NOT NULL,
                    logged_at      TEXT    NOT NULL,
                    success        INTEGER NOT NULL DEFAULT 1,
                    response_time  REAL    NOT NULL DEFAULT 0,
                    tokens         INTEGER NOT NULL DEFAULT 0
                );
                """
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_interaction(
        self,
        prompt: str,
        intent: str,
        plan: Optional[List[Dict[str, Any]]] = None,
        results: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Log an agent interaction and return the new action log row ID.

        Args:
            prompt: The original user prompt.
            intent: Classified intent type.
            plan: Step-by-step action plan (JSON-serialisable).
            results: Execution results (JSON-serialisable).

        Returns:
            The auto-generated action_log row id.
        """
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO action_log (created_at, prompt, intent, plan, results) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    now,
                    prompt,
                    intent,
                    json.dumps(plan) if plan is not None else None,
                    json.dumps(results) if results is not None else None,
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def record_feedback(
        self,
        action_id: int,
        approved: bool,
        feedback: str = "",
    ) -> None:
        """Record human approval or rejection for a logged action.

        Args:
            action_id: The action_log row id to update.
            approved: True if the action was approved.
            feedback: Optional free-text feedback from the user.
        """
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE action_log SET approved = ? WHERE id = ?",
                (1 if approved else 0, action_id),
            )

        if feedback:
            self.add_site_knowledge(
                topic="user_feedback",
                fact=feedback,
                source=f"action_log:{action_id}",
            )

    def get_style_guide(self) -> Dict[str, str]:
        """Return the current learned style preferences as a dict.

        Returns:
            Mapping of style key -> value.
        """
        with self._get_connection() as conn:
            rows = conn.execute("SELECT key, value FROM style_preferences").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def set_style_preference(self, key: str, value: str) -> None:
        """Upsert a style preference entry.

        Args:
            key: Style preference key (e.g. 'tone', 'avg_word_count').
            value: The preference value.
        """
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO style_preferences (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, value, now),
            )

    def get_winning_strategies(self, strategy_type: str) -> List[Dict[str, Any]]:
        """Return strategies that have been successful for a given type.

        Args:
            strategy_type: The type of strategy to query (e.g. 'content', 'seo').

        Returns:
            List of strategy dicts ordered by success_count descending.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM winning_strategies WHERE strategy_type = ? "
                "ORDER BY success_count DESC",
                (strategy_type,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_winning_strategy(
        self, strategy_type: str, description: str
    ) -> None:
        """Record or reinforce a winning strategy.

        Args:
            strategy_type: Category of strategy.
            description: Human-readable description of what worked.
        """
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            existing = conn.execute(
                "SELECT id, success_count FROM winning_strategies "
                "WHERE strategy_type = ? AND description = ?",
                (strategy_type, description),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE winning_strategies SET success_count = ?, updated_at = ? "
                    "WHERE id = ?",
                    (existing["success_count"] + 1, now, existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO winning_strategies "
                    "(strategy_type, description, success_count, created_at, updated_at) "
                    "VALUES (?, ?, 1, ?, ?)",
                    (strategy_type, description, now, now),
                )

    def update_content_performance(
        self,
        post_id: str,
        metrics: Dict[str, Any],
    ) -> None:
        """Update tracked performance metrics for a post.

        Args:
            post_id: WordPress post/page ID.
            metrics: Dict that may contain: url, keywords, views, position, bounce_rate.
        """
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            existing = conn.execute(
                "SELECT id FROM content_performance WHERE post_id = ?", (post_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE content_performance SET "
                    "url=COALESCE(?, url), "
                    "keywords=COALESCE(?, keywords), "
                    "views=COALESCE(?, views), "
                    "position=COALESCE(?, position), "
                    "bounce_rate=COALESCE(?, bounce_rate), "
                    "updated_at=? "
                    "WHERE post_id=?",
                    (
                        metrics.get("url"),
                        metrics.get("keywords"),
                        metrics.get("views"),
                        metrics.get("position"),
                        metrics.get("bounce_rate"),
                        now,
                        post_id,
                    ),
                )
            else:
                conn.execute(
                    "INSERT INTO content_performance "
                    "(post_id, url, keywords, views, position, bounce_rate, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        post_id,
                        metrics.get("url", ""),
                        metrics.get("keywords", ""),
                        metrics.get("views", 0),
                        metrics.get("position", 0),
                        metrics.get("bounce_rate", 0),
                        now,
                    ),
                )

    def add_site_knowledge(
        self, topic: str, fact: str, source: str = ""
    ) -> None:
        """Add a new fact to the site knowledge base.

        Args:
            topic: Category or topic the fact relates to.
            fact: The fact text.
            source: Where this fact came from (URL, action log id, etc.).
        """
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO site_knowledge (topic, fact, source, created_at) VALUES (?, ?, ?, ?)",
                (topic, fact, source, now),
            )

    def get_site_knowledge(self, topic: str) -> List[Dict[str, Any]]:
        """Retrieve all knowledge facts for a given topic.

        Args:
            topic: The topic to query.

        Returns:
            List of fact dicts.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM site_knowledge WHERE topic = ? ORDER BY created_at DESC",
                (topic,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_recent_interactions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the most recent logged interactions.

        Args:
            limit: Maximum number of rows to return.

        Returns:
            List of action_log dicts.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM action_log ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Custom brains persistence
    # ------------------------------------------------------------------

    def save_custom_brain(self, brain_dict: Dict[str, Any]) -> None:
        """Persist a custom brain definition to the database.

        Args:
            brain_dict: Brain definition with keys: name, provider, model,
                api_key, best_for (list), cost_tier, speed_rating, context_window.
        """
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO custom_brains
                    (name, provider, model, api_key, best_for, cost_tier,
                     speed_rating, context_window, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    provider=excluded.provider,
                    model=excluded.model,
                    api_key=excluded.api_key,
                    best_for=excluded.best_for,
                    cost_tier=excluded.cost_tier,
                    speed_rating=excluded.speed_rating,
                    context_window=excluded.context_window,
                    updated_at=excluded.updated_at
                """,
                (
                    brain_dict["name"],
                    brain_dict["provider"],
                    brain_dict["model"],
                    brain_dict.get("api_key", ""),
                    json.dumps(brain_dict.get("best_for", [])),
                    brain_dict.get("cost_tier", "medium"),
                    brain_dict.get("speed_rating", 3),
                    brain_dict.get("context_window", 8192),
                    now,
                    now,
                ),
            )

    def load_custom_brains(self) -> List[Dict[str, Any]]:
        """Load all custom brain definitions from the database.

        Returns:
            List of brain definition dicts.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM custom_brains ORDER BY created_at ASC"
            ).fetchall()
        result = []
        for row in rows:
            brain = dict(row)
            try:
                brain["best_for"] = json.loads(brain.get("best_for", "[]"))
            except (json.JSONDecodeError, TypeError):
                brain["best_for"] = []
            result.append(brain)
        return result

    def delete_custom_brain(self, name: str) -> None:
        """Delete a custom brain from the database.

        Args:
            name: Brain name to delete.
        """
        with self._get_connection() as conn:
            conn.execute("DELETE FROM custom_brains WHERE name = ?", (name,))

    # ------------------------------------------------------------------
    # Brain usage statistics
    # ------------------------------------------------------------------

    def log_brain_usage(
        self,
        brain_name: str,
        success: bool,
        response_time: float = 0.0,
        tokens: int = 0,
    ) -> None:
        """Record a single LLM invocation for statistics tracking.

        Args:
            brain_name: The brain that was called.
            success: Whether the call succeeded.
            response_time: Elapsed time in seconds.
            tokens: Approximate token count used.
        """
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO brain_usage_stats (brain_name, logged_at, success, response_time, tokens) "
                "VALUES (?, ?, ?, ?, ?)",
                (brain_name, now, 1 if success else 0, response_time, tokens),
            )

    def get_brain_stats(self) -> Dict[str, Any]:
        """Return aggregated usage statistics per brain.

        Returns:
            Dict mapping brain_name -> stats dict with call_count, failure_count,
            avg_response_time, total_tokens.
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    brain_name,
                    COUNT(*)                     AS call_count,
                    SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failure_count,
                    AVG(response_time)           AS avg_response_time,
                    SUM(tokens)                  AS total_tokens
                FROM brain_usage_stats
                GROUP BY brain_name
                """
            ).fetchall()
        return {
            row["brain_name"]: {
                "call_count": row["call_count"],
                "failure_count": row["failure_count"],
                "avg_response_time": round(row["avg_response_time"] or 0.0, 3),
                "total_tokens": row["total_tokens"] or 0,
            }
            for row in rows
        }
