import os
import json
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field
from elo.security import DEFAULT_KEY_DIR

logger = logging.getLogger("elo.pending_queue")

PENDING_DIR = DEFAULT_KEY_DIR / "pending"


@dataclass
class PendingTask:
    task_id: str
    target_node: str
    capability: str
    payload: dict
    created_at: float = field(default_factory=time.time)
    retries: int = 0
    ttl_s: int = 60

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "target_node": self.target_node,
            "capability": self.capability,
            "payload": self.payload,
            "created_at": self.created_at,
            "retries": self.retries,
            "ttl_s": self.ttl_s,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PendingTask":
        return cls(
            task_id=d["task_id"],
            target_node=d["target_node"],
            capability=d["capability"],
            payload=d["payload"],
            created_at=d["created_at"],
            retries=d.get("retries", 0),
            ttl_s=d.get("ttl_s", 60),
        )


class PendingQueue:
    def __init__(self, node_id: str = "default", pending_dir: Path = PENDING_DIR):
        self.pending_dir = pending_dir
        self.file_path = pending_dir / f"tasks_{node_id[:12]}.jsonl"
        self._init_dir()

    def _init_dir(self) -> None:
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.pending_dir.chmod(0o700)
        except NotImplementedError:
            pass
        if self.file_path.exists():
            try:
                self.file_path.chmod(0o600)
            except NotImplementedError:
                pass

    def enqueue(self, task_id: str, target: str, capability: str, payload: dict, ttl_s: int = 60) -> None:
        task = PendingTask(
            task_id=task_id,
            target_node=target,
            capability=capability,
            payload=payload,
            ttl_s=ttl_s
        )
        try:
            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(task.to_dict()) + "\n")
            try:
                self.file_path.chmod(0o600)
            except NotImplementedError:
                pass
        except Exception as e:
            logger.error("[pending] failed to enqueue task %s: %s", task_id, e)

    def load_all(self) -> list[PendingTask]:
        tasks = []
        if not self.file_path.exists():
            return tasks
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            d = json.loads(line)
                            tasks.append(PendingTask.from_dict(d))
                        except Exception:
                            pass
        except Exception as e:
            logger.error("[pending] failed to load tasks: %s", e)
        return tasks

    def save_all(self, tasks: list[PendingTask]) -> None:
        try:
            # Atomic rewrite
            temp_path = self.file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                for t in tasks:
                    f.write(json.dumps(t.to_dict()) + "\n")
            try:
                temp_path.chmod(0o600)
            except NotImplementedError:
                pass
            temp_path.replace(self.file_path)
        except Exception as e:
            logger.error("[pending] failed to save tasks: %s", e)
