"""备份 / 恢复 CodeBase Agent 的数据（历史库 + 向量库）。

用法：
    python scripts/backup.py                 # 备份到 data/backups/<时间戳>/
    python scripts/backup.py --keep 7        # 只保留最近 7 份
    python scripts/backup.py --restore DIR   # 从备份目录恢复（先停止应用）

说明：
- history.db 用 SQLite 在线备份 API，应用运行时备份也安全。
- chroma 目录为尽力拷贝；应用运行时可能不一致，建议空闲或停止应用时备份。
"""

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import Settings


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def backup(settings: Settings, keep: int = 7) -> Path:
    data_dir = Path(settings.history_db).resolve().parent
    backups_dir = data_dir / "backups"
    dest = backups_dir / _ts()
    dest.mkdir(parents=True, exist_ok=True)

    manifest = {"created_at": datetime.now().isoformat(), "items": [], "warnings": []}

    src_db = Path(settings.history_db)
    if src_db.exists():
        out_db = dest / "history.db"
        con = sqlite3.connect(str(src_db))
        try:
            dst = sqlite3.connect(str(out_db))
            with dst:
                con.backup(dst)
            dst.close()
        finally:
            con.close()
        manifest["items"].append({"name": "history.db", "bytes": out_db.stat().st_size})

    chroma = Path(settings.chroma_persist_dir)
    if chroma.exists():
        try:
            shutil.copytree(chroma, dest / "chroma", dirs_exist_ok=True)
            manifest["items"].append({"name": "chroma", "bytes": _dir_size(dest / "chroma")})
        except Exception as exc:
            manifest["warnings"].append(f"chroma copy failed: {exc}")

    (dest / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    olds = sorted(
        (p for p in backups_dir.iterdir() if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )
    for old in olds[keep:]:
        shutil.rmtree(old, ignore_errors=True)

    return dest


def restore(settings: Settings, src: Path) -> None:
    src = Path(src)
    if not src.exists():
        raise SystemExit(f"backup not found: {src}")

    db = Path(settings.history_db)
    if (src / "history.db").exists():
        db.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / "history.db", db)

    chroma = Path(settings.chroma_persist_dir)
    if (src / "chroma").exists():
        if chroma.exists():
            shutil.rmtree(chroma)
        shutil.copytree(src / "chroma", chroma)

    print(f"restored from {src}")
    print("注意：恢复前应先停止应用（uvicorn），恢复后重启。")


def main() -> None:
    ap = argparse.ArgumentParser(description="备份/恢复 CodeBase Agent 数据")
    ap.add_argument("--restore", metavar="DIR", help="从指定备份目录恢复")
    ap.add_argument("--keep", type=int, default=7, help="保留最近 N 份备份（默认 7）")
    args = ap.parse_args()

    settings = Settings.load()
    if args.restore:
        restore(settings, Path(args.restore))
        return

    dest = backup(settings, keep=args.keep)
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    print(f"备份完成: {dest}")
    for item in manifest["items"]:
        print(f"  - {item['name']}: {item['bytes']} bytes")
    for warn in manifest.get("warnings", []):
        print(f"  ! {warn}")


if __name__ == "__main__":
    main()