"""
轻量级异步任务管理器（SQLite 后端）。
用于将耗时较长的同步/异步操作转为「提交 → 轮询」模式，
避免反向代理（Nginx 等）因等待响应超时而返回 504。
使用 SQLite WAL 模式支持多 worker 并发读写。
"""

import asyncio
import time
import logging
import uuid
import threading
from enum import Enum
from typing import Any, Callable, Awaitable, Optional
from pathlib import Path
import sqlite3

logger = logging.getLogger(__name__)

_DB_PATH = str(Path(__file__).parent.parent / "task_store.db")


def _init_db() -> sqlite3.Connection:
    """创建数据库连接并初始化表结构。"""
    conn = sqlite3.connect(_DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending',
            progress INTEGER NOT NULL DEFAULT 0,
            result_path TEXT,
            result_filename TEXT,
            error TEXT,
            created_at REAL NOT NULL,
            finished_at REAL
        )
    """)
    conn.commit()
    return conn


# 模块级连接（每个 worker 进程各自持有）
_conn: Optional[sqlite3.Connection] = None
_lock = threading.Lock()


def _ensure_conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            _conn = _init_db()
        return _conn


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class TaskInfo:
    __slots__ = (
        "task_id", "status", "progress", "result_path",
        "result_filename", "error", "created_at", "finished_at",
        "_initialized",
    )

    def __init__(self, task_id: str):
        object.__setattr__(self, '_initialized', False)
        self.task_id = task_id
        self.status = TaskStatus.PENDING
        self.progress: int = 0          # 0~100
        self.result_path: Optional[str] = None
        self.result_filename: Optional[str] = None
        self.error: Optional[str] = None
        self.created_at = time.time()
        self.finished_at: Optional[float] = None
        object.__setattr__(self, '_initialized', True)

    def __setattr__(self, name: str, value: Any) -> None:
        object.__setattr__(self, name, value)
        if name != '_initialized' and object.__getattribute__(self, '_initialized'):
            _save_task(self)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "progress": self.progress,
            "result_filename": self.result_filename,
            "error": self.error,
        }


def _save_task(task_info: TaskInfo) -> None:
    conn = _ensure_conn()
    status_val = task_info.status.value if isinstance(task_info.status, TaskStatus) else task_info.status
    with _lock:
        conn.execute("""
            INSERT OR REPLACE INTO tasks (task_id, status, progress, result_path, result_filename, error, created_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_info.task_id,
            status_val,
            task_info.progress,
            task_info.result_path,
            task_info.result_filename,
            task_info.error,
            task_info.created_at,
            task_info.finished_at,
        ))
        conn.commit()


def _row_to_taskinfo(row: sqlite3.Row) -> TaskInfo:
    info = TaskInfo.__new__(TaskInfo)
    object.__setattr__(info, '_initialized', False)
    object.__setattr__(info, 'task_id', row['task_id'])
    object.__setattr__(info, 'status', TaskStatus(row['status']))
    object.__setattr__(info, 'progress', row['progress'])
    object.__setattr__(info, 'result_path', row['result_path'])
    object.__setattr__(info, 'result_filename', row['result_filename'])
    object.__setattr__(info, 'error', row['error'])
    object.__setattr__(info, 'created_at', row['created_at'])
    object.__setattr__(info, 'finished_at', row['finished_at'])
    object.__setattr__(info, '_initialized', True)
    return info


def create_task() -> TaskInfo:
    task_id = uuid.uuid4().hex[:12]
    info = TaskInfo(task_id)
    _save_task(info)
    return info


def get_task(task_id: str) -> Optional[TaskInfo]:
    conn = _ensure_conn()
    with _lock:
        row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if row is None:
        return None
    return _row_to_taskinfo(row)


def remove_task(task_id: str) -> None:
    conn = _ensure_conn()
    with _lock:
        conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
        conn.commit()


async def run_background(
    task_info: TaskInfo,
    coro_fn: Callable[..., Awaitable[Any]],
    **kwargs,
) -> None:
    """
    在后台执行协程函数，自动更新 TaskInfo 状态。
    coro_fn 需接受 task_info: TaskInfo 作为关键字参数。
    """
    task_info.status = TaskStatus.PROCESSING
    try:
        await coro_fn(task_info=task_info, **kwargs)
    except Exception as e:
        task_info.status = TaskStatus.FAILED
        task_info.error = str(e)
        task_info.finished_at = time.time()
        logger.exception(f"[TaskManager] 任务 {task_info.task_id} 失败: {e}")


def cleanup_old_tasks(max_age: float = 3600) -> None:
    """清理超过 max_age 秒的已完成/失败任务"""
    now = time.time()
    conn = _ensure_conn()
    with _lock:
        conn.execute(
            "DELETE FROM tasks WHERE finished_at IS NOT NULL AND (? - finished_at) > ?",
            (now, max_age),
        )
        conn.commit()
