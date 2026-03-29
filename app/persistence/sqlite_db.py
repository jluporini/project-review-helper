import sqlite3
import os
from typing import List, Optional, Any
from ..models.entities import Project, Session

class SQLiteDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._initialize_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_db(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    code TEXT,
                    name TEXT,
                    description TEXT,
                    default_storage_root TEXT,
                    session_subpath_pattern TEXT,
                    active INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    project_id TEXT,
                    title TEXT,
                    description TEXT,
                    review_type TEXT,
                    tester_name TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    status TEXT,
                    storage_path TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY (project_id) REFERENCES projects (project_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS issues (
                    issue_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    title TEXT,
                    description TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    status TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id)
                )
            """)
            conn.commit()

    def save_project(self, project: Project):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO projects 
                (project_id, code, name, description, default_storage_root, session_subpath_pattern, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                project.project_id, project.code, project.name, project.description,
                project.default_storage_root, project.session_subpath_pattern,
                1 if project.active else 0, project.created_at, project.updated_at
            ))
            conn.commit()

    def get_projects(self) -> List[Project]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM projects WHERE active = 1")
            rows = cursor.fetchall()
            return [Project(**dict(row)) for row in rows]

    def save_session(self, session: Session):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO sessions 
                (session_id, project_id, title, description, review_type, tester_name, start_time, end_time, status, storage_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session.session_id, session.project_id, session.title, session.description,
                session.review_type, session.tester_name, session.start_time, session.end_time,
                session.status, session.storage_path, session.created_at, session.updated_at
            ))
            conn.commit()

    def get_session(self, session_id: str) -> Optional[Session]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            return Session(**dict(row)) if row else None

    def get_sessions_by_project(self, project_id: str) -> List[Session]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM sessions WHERE project_id = ? ORDER BY created_at DESC", (project_id,))
            rows = cursor.fetchall()
            return [Session(**dict(row)) for row in rows]

    def save_issue(self, issue: Any):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO issues 
                (issue_id, session_id, title, description, start_time, end_time, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                issue.issue_id, issue.session_id, issue.title, issue.description,
                issue.start_time, issue.end_time, issue.status, issue.created_at, issue.updated_at
            ))
            conn.commit()

    def get_issues_by_session(self, session_id: str) -> List[Any]:
        from ..models.entities import Issue
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM issues WHERE session_id = ? ORDER BY created_at ASC", (session_id,))
            rows = cursor.fetchall()
            return [Issue(**dict(row)) for row in rows]

    def delete_issue(self, issue_id: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM issues WHERE issue_id = ?", (issue_id,))
            conn.commit()

    def get_last_revision_number(self, project_id: str) -> int:
        """Finds the highest rev-XXXXXX number in the project's sessions."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT title FROM sessions WHERE project_id = ?", (project_id,))
            titles = [row['title'] for row in cursor.fetchall()]
            
            max_rev = 0
            import re
            for title in titles:
                match = re.search(r'rev-(\d+)', title)
                if match:
                    rev_num = int(match.group(1))
                    if rev_num > max_rev:
                        max_rev = rev_num
            return max_rev

    def close(self):
        # In this implementation, we open/close on every call, 
        # but we can force a GC or just ensure no persistent state exists.
        pass
