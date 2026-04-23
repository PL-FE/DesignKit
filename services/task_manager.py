"""
轻量级异步任务管理器。
用于将耗时较长的同步/异步操作转为「提交 → 轮询」模式，
避免反向代理（Nginx 等）因等待响应超时而返回 504。
"""

import asyncio
import time
import logging
import uuid
from enum import Enum
from typing import Any, Callable, Awaitable, Optional

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class TaskInfo:
    __slots__ = (
        "task_id", "status", "progress", "result_path",
        "result_filename", "error", "created_at", "finished_at",
    )

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.status = TaskStatus.PENDING
        self.progress: int = 0          # 0~100
        self.result_path: Optional[str] = None
        self.result_filename: Optional[str] = None
        self.error: Optional[str] = None
        self.created_at = time.time()
        self.finished_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "progress": self.progress,
            "result_filename": self.result_filename,
            "error": self.error,
        }


# 全局任务存储（单进程内有效，多 worker 部署需换 Redis 等）
_tasks: dict[str, TaskInfo] = {}


def create_task() -> TaskInfo:
    task_id = uuid.uuid4().hex[:12]
    info = TaskInfo(task_id)
    _tasks[task_id] = info
    return info


def get_task(task_id: str) -> Optional[TaskInfo]:
    return _tasks.get(task_id)


def remove_task(task_id: str) -> None:
    _tasks.pop(task_id, None)


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
    to_remove = [
        tid for tid, t in _tasks.items()
        if t.finished_at and (now - t.finished_at) > max_age
    ]
    for tid in to_remove:
        _tasks.pop(tid, None)
