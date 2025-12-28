import subprocess
from pathlib import Path


def clone_repo(url: str, dest: Path) -> None:
    subprocess.run(
        ["git", "clone", "--no-single-branch", url, str(dest)],
        check=True,
        timeout=600
    )
    subprocess.run(
        ["git", "fetch", "--all"],
        cwd=str(dest),
        check=True,
        timeout=300
    )


def build_tree(root: Path, current: Path = None) -> dict:
    if current is None:
        current = root
    
    rel_path = str(current.relative_to(root)) if current != root else ""
    node = {
        "name": current.name, 
        "path": rel_path, 
        "type": "dir" if current.is_dir() else "file"
    }
    
    if current.is_dir():
        try:
            children = []
            for child in sorted(current.iterdir()):
                if _should_skip_path(child):
                    continue
                children.append(build_tree(root, child))
            node["children"] = children
        except PermissionError:
            node["children"] = []
    return node


def _should_skip_path(path: Path) -> bool:
    if ".git" in path.parts:
        return True
    if "__pycache__" in path.parts:
        return True
    if "node_modules" in path.parts:
        return True
    if ".venv" in path.parts or "venv" in path.parts:
        return True
    
    meta_ok = {".docx", ".xlsx", ".pptx", ".pdf", ".jpg", ".jpeg", ".png"}
    binary_suffixes = {
        ".pyc", ".so", ".dll", ".exe", ".zip", ".tar", ".gz", ".7z",
        ".mp3", ".mp4", ".avi", ".mov", ".ogg", ".ico", ".woff", ".woff2"
    }
    suffix = path.suffix.lower()
    return suffix in binary_suffixes and suffix not in meta_ok