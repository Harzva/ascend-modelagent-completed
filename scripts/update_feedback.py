#!/usr/bin/env python3
"""Normalize a competition result snapshot into the server repair queue."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


SCHEMA_VERSION = "1.0"
QUEUE_SCHEMA = (
    "https://raw.githubusercontent.com/Harzva/ascend-modelagent-completed/"
    "main/schema/competition-feedback-v1.schema.json"
)
MISSING_FILES_RE = re.compile(r"作品仓库缺少必需文件\s*[：:]\s*(.+)")
PATH_RE = re.compile(r"(?:^|[、,，\s])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+)")


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=False)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def normalize_url(value: str) -> str:
    return value.strip().rstrip("/")


def repo_slug(project_url: str) -> str:
    parts = [part for part in urlparse(project_url).path.split("/") if part]
    if len(parts) < 2:
        raise ValueError(f"无法从项目地址解析仓库: {project_url}")
    return "/".join(parts[:2])


def repo_name(project_url: str) -> str:
    return repo_slug(project_url).split("/", 1)[1]


def stable_id(*parts: str) -> str:
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]
    return digest


def snapshot_state_hash(payload: dict) -> str:
    """Hash result state while ignoring the polling timestamp."""
    state = {
        "competition_id": str(payload["competition_id"]),
        "total_score": int(payload["total_score"]),
        "records": payload["records"],
    }
    encoded = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def archive_snapshot(payload: dict, repo_root: Path) -> Path:
    observed_at = datetime.fromisoformat(payload["observed_at"])
    filename = observed_at.strftime("%Y-%m-%dT%H%M%S%z.json")
    destination = repo_root / "feedback" / "snapshots" / filename
    atomic_write_json(destination, payload)
    return destination


def classify_reminder(project_url: str, reminder: str) -> dict:
    reminder = " ".join(reminder.split())
    missing = MISSING_FILES_RE.search(reminder)
    if missing:
        paths = sorted(set(PATH_RE.findall(" " + missing.group(1))))
        code = "missing_required_files"
        severity = "high"
    elif "hardware" in reminder.lower() and "npu" in reminder.lower():
        paths = ["README.md"]
        code = "missing_npu_metadata"
        severity = "high"
    elif "模型仓" in reminder and "代码仓" in reminder:
        paths = []
        code = "wrong_repository_type"
        severity = "critical"
    elif "公开" in reminder or "访问" in reminder or "403" in reminder:
        paths = []
        code = "repository_access_problem"
        severity = "critical"
    else:
        paths = []
        code = "competition_low_score_reminder"
        severity = "medium"
    return {
        "id": f"issue-{stable_id(normalize_url(project_url), reminder)}",
        "code": code,
        "severity": severity,
        "message": reminder,
        "paths": paths,
    }


def repair_contract(project_url: str, issues: list[dict]) -> dict:
    actions: list[str] = []
    verification: list[str] = []
    constraints = [
        "只修改 target_repository 指向的模型仓库",
        "不得输出或提交 token、Cookie、.env、访问文件、凭据或本机私有路径",
        "截图和验证证据必须来自真实适配过程或真实 NPU 运行，禁止伪造",
    ]
    for issue in issues:
        if issue["code"] == "missing_required_files":
            actions.append("补齐缺失的必需文件：" + "、".join(issue["paths"]))
            verification.append("确认模型仓库中可匿名访问全部必需文件")
            verification.append("基于真实 Model Agent/NPU 日志核验三张截图内容")
        elif issue["code"] == "missing_npu_metadata":
            actions.append("修复 README.md frontmatter，确保 hardware: NPU")
            verification.append("重新读取 README.md 并确认平台 NPU 元数据可识别")
        else:
            actions.append("按比赛低分提醒修复：" + issue["message"])
            verification.append("重新打开比赛查看结果，确认对应提醒消失")
    verification.append("修复推送后写入 feedback/receipts/<repo-name>.json")
    return {
        "target_repository": normalize_url(project_url),
        "actions": list(dict.fromkeys(actions)),
        "verification": list(dict.fromkeys(verification)),
        "constraints": constraints,
    }


def validate_snapshot(payload: dict) -> None:
    required = ["competition_id", "source_url", "observed_at", "total_score", "records"]
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError("快照缺少字段: " + ", ".join(missing))
    if not isinstance(payload["records"], list):
        raise ValueError("records 必须为数组")
    for index, record in enumerate(payload["records"]):
        for key in (
            "submission_number",
            "submitted_at",
            "model_id",
            "original_model_url",
            "project_url",
            "reminders",
        ):
            if key not in record:
                raise ValueError(f"records[{index}] 缺少字段 {key}")
        if not isinstance(record["reminders"], list):
            raise ValueError(f"records[{index}].reminders 必须为数组")


def update_feedback(payload: dict, repo_root: Path, dry_run: bool = False) -> dict:
    validate_snapshot(payload)
    feedback_dir = repo_root / "feedback"
    models_dir = feedback_dir / "models"
    old_queue = read_json(feedback_dir / "queue.json", {"items": []}) or {"items": []}
    old_latest = read_json(feedback_dir / "latest.json", {}) or {}
    state_hash = snapshot_state_hash(payload)
    if old_latest.get("state_hash") == state_hash:
        return old_queue
    open_items = {normalize_url(item["project_url"]): item for item in old_queue.get("items", [])}
    observed_projects: set[str] = set()
    latest_records: list[dict] = []

    for record in payload["records"]:
        project_url = normalize_url(record["project_url"])
        observed_projects.add(project_url)
        issues = [classify_reminder(project_url, text) for text in record["reminders"] if text.strip()]
        name = repo_name(project_url)
        model_path = models_dir / f"{name}.json"
        previous_model = read_json(model_path, {}) or {}

        latest_records.append(
            {
                "submission_number": record["submission_number"],
                "submitted_at": record["submitted_at"],
                "model_id": record["model_id"],
                "original_model_url": normalize_url(record["original_model_url"]),
                "project_url": project_url,
                "status": "needs_fix" if issues else "clean",
                "issues": issues,
            }
        )

        if issues:
            first_seen = previous_model.get("first_seen_at", payload["observed_at"])
            item = {
                "id": f"repair-{stable_id(project_url)}",
                "status": "open",
                "priority": max((issue["severity"] for issue in issues), key=("low", "medium", "high", "critical").index),
                "model_id": record["model_id"],
                "original_model_url": normalize_url(record["original_model_url"]),
                "project_url": project_url,
                "repo_slug": repo_slug(project_url),
                "submission_number": record["submission_number"],
                "submitted_at": record["submitted_at"],
                "first_seen_at": first_seen,
                "last_seen_at": payload["observed_at"],
                "issues": issues,
                "repair_contract": repair_contract(project_url, issues),
                "model_feedback_path": f"feedback/models/{name}.json",
                "receipt_path": f"feedback/receipts/{name}.json",
            }
            open_items[project_url] = item
            observation = {
                "observed_at": payload["observed_at"],
                "total_score": payload["total_score"],
                "issue_ids": [issue["id"] for issue in issues],
            }
            observations = previous_model.get("observations", [])
            if observation not in observations:
                observations.append(observation)
            model_doc = {
                "schema_version": SCHEMA_VERSION,
                "project_url": project_url,
                "model_id": record["model_id"],
                "status": "open",
                "first_seen_at": first_seen,
                "last_seen_at": payload["observed_at"],
                "resolved_at": None,
                "issues": issues,
                "repair_contract": item["repair_contract"],
                "observations": observations,
            }
            if not dry_run:
                atomic_write_json(model_path, model_doc)
        elif project_url in open_items:
            open_items.pop(project_url, None)
            if previous_model:
                previous_model.update(
                    {
                        "status": "resolved",
                        "last_seen_at": payload["observed_at"],
                        "resolved_at": payload["observed_at"],
                        "issues": [],
                    }
                )
                if not dry_run:
                    atomic_write_json(model_path, previous_model)

    items = sorted(
        open_items.values(),
        key=lambda item: (
            -("low", "medium", "high", "critical").index(item["priority"]),
            item["project_url"],
        ),
    )
    queue = {
        "$schema": QUEUE_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "competition_id": str(payload["competition_id"]),
        "generated_at": payload["observed_at"],
        "source": {
            "url": payload["source_url"],
            "total_score": int(payload["total_score"]),
            "submission_count": len(payload["records"]),
        },
        "summary": {
            "open_model_count": len(items),
            "open_issue_count": sum(len(item["issues"]) for item in items),
        },
        "items": items,
    }
    latest = {
        "schema_version": SCHEMA_VERSION,
        "competition_id": str(payload["competition_id"]),
        "state_hash": state_hash,
        "observed_at": payload["observed_at"],
        "total_score": int(payload["total_score"]),
        "submission_count": len(latest_records),
        "records": latest_records,
    }
    if not dry_run:
        atomic_write_json(feedback_dir / "queue.json", queue)
        atomic_write_json(feedback_dir / "latest.json", latest)
    return queue


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="规范化比赛结果快照 JSON")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--archive-snapshot",
        action="store_true",
        help="仅在比赛结果状态变化时归档输入快照",
    )
    args = parser.parse_args()
    payload = read_json(args.input)
    previous_latest = read_json(args.repo_root.resolve() / "feedback" / "latest.json", {}) or {}
    changed = previous_latest.get("state_hash") != snapshot_state_hash(payload)
    queue = update_feedback(payload, args.repo_root.resolve(), dry_run=args.dry_run)
    archived_snapshot = None
    if changed and args.archive_snapshot and not args.dry_run:
        archived_snapshot = archive_snapshot(payload, args.repo_root.resolve())
    print(
        json.dumps(
            {
                "open_model_count": queue["summary"]["open_model_count"],
                "open_issue_count": queue["summary"]["open_issue_count"],
                "queue": str(args.repo_root.resolve() / "feedback" / "queue.json"),
                "changed": changed,
                "archived_snapshot": str(archived_snapshot) if archived_snapshot else None,
                "dry_run": args.dry_run,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
