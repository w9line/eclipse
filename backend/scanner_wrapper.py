import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from core_scanner import ScanConfig, scan_repository


def run_scan(repo_path: Path, target_path: str = "", commit_hash: str = "") -> list:

    cfg = ScanConfig(
        repo_path=repo_path,
        scan_history=True,
        history_commit_limit=100,  
        # max_file_size=1_000_000,   
        entropy_threshold=4.5,     
    )
    
    result = scan_repository(cfg)
    findings = result.findings
    
    if target_path:
        findings = [f for f in findings if f.path.startswith(target_path)]
    
    if commit_hash:
        findings = [f for f in findings if f.source == commit_hash or f.source == "workdir"]
    
    return [f.__dict__ for f in findings]