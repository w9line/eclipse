import os
import re
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from . import models, schemas, database, git_utils, scanner_wrapper
from .database import SessionLocal, engine
import csv
import io
import json
from datetime import datetime
from fastapi.responses import StreamingResponse

models.Base.metadata.create_all(bind=engine)
app = FastAPI(title="Eclipse API")
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"]
)

def get_db():
    db = SessionLocal()
    try: 
        yield db
    finally: 
        db.close()

REPOS_DIR = Path("repos").absolute()
REPOS_DIR.mkdir(exist_ok=True)

def extract_repo_name(url_or_path: str, is_url: bool) -> str:
    if is_url:
        parsed = urlparse(url_or_path)
        path = parsed.path.rstrip('/')
        name = path.split('/')[-1]
        if name.endswith('.git'):
            name = name[:-4]
        name = re.sub(r'[^\w\-.]', '_', name)
        return name or 'repo'
    else:
        return Path(url_or_path).name

def get_unique_repo_path(base_name: str) -> Path:
    dest_path = REPOS_DIR / base_name
    if not dest_path.exists():
        return dest_path
    counter = 1
    while True:
        new_path = REPOS_DIR / f"{base_name}_{counter}"
        if not new_path.exists():
            return new_path
        counter += 1

@app.post("/api/repos", response_model=schemas.RepositoryOut)
def add_repository(repo: schemas.RepositoryCreate, db: Session = Depends(get_db)):
    repo_name = extract_repo_name(repo.path, repo.is_url)
    
    if repo.is_url:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / repo_name
            try:
                git_utils.clone_repo(repo.path, tmp_path)
            except subprocess.CalledProcessError as e:
                raise HTTPException(status_code=400, detail=f"Не удалось клонировать: {e}")
            
            dest_path = get_unique_repo_path(repo_name)
            shutil.move(str(tmp_path), str(dest_path))
            source_url = repo.path
    else:
        local_path = Path(repo.path).absolute()
        if not local_path.exists(): 
            raise HTTPException(status_code=400, detail="Путь не найден")
        
        dest_path = get_unique_repo_path(repo_name)
        shutil.copytree(str(local_path), str(dest_path))
        source_url = None

    existing_repo = db.query(models.Repository).filter(
        models.Repository.path == str(dest_path)
    ).first()
    
    if existing_repo:
        return existing_repo

    db_repo = models.Repository(
        name=dest_path.name,
        path=str(dest_path), 
        source_url=source_url
    )
    db.add(db_repo)
    db.commit()
    db.refresh(db_repo)
    return db_repo

@app.get("/api/repos", response_model=List[schemas.RepositoryOut])
def list_repositories(db: Session = Depends(get_db)):
    return db.query(models.Repository).all()

@app.delete("/api/repos/{repo_id}")
def delete_repository(repo_id: int, db: Session = Depends(get_db)):
    repo = db.query(models.Repository).filter(models.Repository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Репозиторий не найден")
    
    repo_path = Path(repo.path)
    if repo_path.exists():
        shutil.rmtree(repo_path)
    
    db.delete(repo)
    db.commit()
    return {"status": "удалён"}

@app.get("/api/repos/{repo_id}/tree")
def get_repo_tree(repo_id: int, db: Session = Depends(get_db)):
    repo = db.query(models.Repository).filter(models.Repository.id == repo_id).first()
    if not repo: 
        raise HTTPException(status_code=404, detail="Репозиторий не найден")
    repo_path = Path(repo.path)
    if not repo_path.exists(): 
        raise HTTPException(status_code=404, detail="Путь отсутствует")
    return git_utils.build_tree(repo_path)

def perform_scan(scan_id: int, repo_path: Path, target_path: str, commit_hash: str):
    db = SessionLocal()
    try:
        db_scan = db.query(models.Scan).filter(models.Scan.id == scan_id).first()
        findings = scanner_wrapper.run_scan(repo_path, target_path, commit_hash)
        
        for f in findings:
            db.add(models.Finding(scan_id=scan_id, **f))
        
        db_scan.status = "completed"
        db_scan.completed_at = func.now()
        db_scan.findings_count = len(findings)
        db.commit()
    except Exception as e:
        db_scan = db.query(models.Scan).filter(models.Scan.id == scan_id).first()
        if db_scan:
            db_scan.status = "failed"
            db_scan.error_message = str(e)
            db.commit()
    finally:
        db.close()

@app.post("/api/scans", response_model=schemas.ScanOut)
def start_scan(
    repo_id: int, 
    target_path: str = "", 
    commit_hash: str = "", 
    background_tasks: BackgroundTasks = None, 
    db: Session = Depends(get_db)
):
    repo = db.query(models.Repository).filter(models.Repository.id == repo_id).first()
    if not repo: 
        raise HTTPException(status_code=404, detail="Репозиторий не найден")
    
    db_scan = models.Scan(repo_id=repo_id, target_path=target_path, status="в процессе")
    db.add(db_scan)
    db.commit()
    db.refresh(db_scan)
    
    background_tasks.add_task(perform_scan, db_scan.id, Path(repo.path), target_path, commit_hash)
    return db_scan

@app.get("/api/scans/{scan_id}", response_model=schemas.ScanOut)
def get_scan_status(scan_id: int, db: Session = Depends(get_db)):
    scan = db.query(models.Scan).filter(models.Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Скан не найден")
    return scan

@app.get("/api/scans/{scan_id}/findings", response_model=List[schemas.FindingOut])
def get_scan_findings(
    scan_id: int, 
    category: Optional[str] = None, 
    severity: Optional[str] = None, 
    db: Session = Depends(get_db)
):
    query = db.query(models.Finding).filter(models.Finding.scan_id == scan_id)
    if category: 
        query = query.filter(models.Finding.category == category)
    if severity: 
        query = query.filter(models.Finding.severity == severity)
    return query.all()

@app.get("/api/repos/{repo_id}/file")
def get_file_content(repo_id: int, path: str, db: Session = Depends(get_db)):
    repo = db.query(models.Repository).filter(models.Repository.id == repo_id).first()
    if not repo: 
        raise HTTPException(status_code=404, detail="Репозиторий не найден")
    
    full_path = Path(repo.path) / path
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    try:
        content = full_path.read_text(encoding="utf-8", errors="replace")
        return {"content": content}
    except Exception:
        return {"content": "[Бинарный файл]"}

@app.get("/api/repos/{repo_id}/commits")
def get_repo_commits(repo_id: int, limit: int = 50, db: Session = Depends(get_db)):
    repo = db.query(models.Repository).filter(models.Repository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Репозиторий не найден")
    
    repo_path = Path(repo.path)
    if not repo_path.exists():
        raise HTTPException(status_code=404, detail="Путь к репозиторию отсутствует")

    try:
        result = subprocess.run(
            ["git", "log", f"--max-count={limit}", "--pretty=format:%H|%s|%an|%ad", "--date=short"],
            cwd=str(repo_path),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30  
        )
        
        commits = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 3)
            if len(parts) != 4:
                continue
            commit_hash, message, author, date = parts
            commits.append({
                "hash": commit_hash,
                "message": message,
                "author": author,
                "date": date
            })
        return commits
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Превышено время выполнения команды Git")
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Ошибка выполнения команды Git: {e.stderr}")

@app.get("/api/scans/{scan_id}/export/json")
def export_findings_json(scan_id: int, db: Session = Depends(get_db)):
    scan = db.query(models.Scan).filter(models.Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Скан не найден")
    
    findings = db.query(models.Finding).filter(models.Finding.scan_id == scan_id).all()
    repo = db.query(models.Repository).filter(models.Repository.id == scan.repo_id).first()
    
    stats = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        if f.severity in stats:
            stats[f.severity] += 1
    
    data = {
        "report": {
            "tool": "Eclipse",
            "version": "1.3.0",
            "generated_at": datetime.now().isoformat(),
        },
        "scan": {
            "id": scan_id,
            "repository": repo.name if repo else "Неизвестно",
            "source_url": repo.source_url if repo else None,
            "started_at": scan.started_at.isoformat() if scan.started_at else None,
            "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
            "status": scan.status,
        },
        "summary": {
            "total_findings": len(findings),
            "by_severity": stats,
        },
        "findings": [
            {
                "id": f.id,
                "severity": f.severity,
                "category": f.category,
                "kind": f.kind,
                "path": f.path,
                "source": f.source,
                "excerpt": f.excerpt,
                "hint": f.hint,
                "line_start": f.start,
                "line_end": f.end,
            }
            for f in findings
        ]
    }
    
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    
    return StreamingResponse(
        io.StringIO(json_str),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=eclipse-report-{scan_id}.json"
        }
    )

@app.get("/api/scans/{scan_id}/export/csv")
def export_findings_csv(scan_id: int, db: Session = Depends(get_db)):
    scan = db.query(models.Scan).filter(models.Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Скан не найден")
    
    findings = db.query(models.Finding).filter(models.Finding.scan_id == scan_id).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        "ID", "Серьёзность", "Категория", "Тип", "Путь", 
        "Источник", "Фрагмент", "Рекомендация", "Строка (начало)", "Строка (конец)"
    ])
    
    for f in findings:
        writer.writerow([
            f.id,
            f.severity,
            f.category,
            f.kind,
            f.path,
            f.source,
            f.excerpt.replace('\n', ' ').replace('\r', '')[:200],
            f.hint or "",
            f.start,
            f.end
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=eclipse-report-{scan_id}.csv"
        }
    )

@app.get("/api/scans/{scan_id}/export/markdown")
def export_findings_markdown(scan_id: int, db: Session = Depends(get_db)):
    scan = db.query(models.Scan).filter(models.Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Скан не найден")
    
    findings = db.query(models.Finding).filter(models.Finding.scan_id == scan_id).all()
    repo = db.query(models.Repository).filter(models.Repository.id == scan.repo_id).first()
    
    by_severity = {"critical": [], "high": [], "medium": [], "low": []}
    for f in findings:
        if f.severity in by_severity:
            by_severity[f.severity].append(f)
    
    md = f"""# Отчёт Eclipse

## Обзор

| Поле | Значение |
|-------|-------|
| **Репозиторий** | {repo.name if repo else 'Неизвестно'} |
| **Источник** | {repo.source_url or repo.path if repo else 'Н/Д'} |
| **Дата сканирования** | {scan.started_at.strftime('%Y-%m-%d %H:%M') if scan.started_at else 'Н/Д'} |
| **Статус** | {scan.status} |
| **Всего находок** | {len(findings)} |

## Сводка по уровням серьёзности

| Уровень | Количество | Процент |
|----------|-------|------------|
| 3-Критический | {len(by_severity['critical'])} | {len(by_severity['critical']) * 100 // max(len(findings), 1)}% |
| 2-Высокий | {len(by_severity['high'])} | {len(by_severity['high']) * 100 // max(len(findings), 1)}% |
| 1-Средний | {len(by_severity['medium'])} | {len(by_severity['medium']) * 100 // max(len(findings), 1)}% |
| 0-Низкий | {len(by_severity['low'])} | {len(by_severity['low']) * 100 // max(len(findings), 1)}% |

---

"""
    
    severity_emoji = {
        "critical": "3",
        "high": "2", 
        "medium": "1",
        "low": "0"
    }
    
    for severity in ["critical", "high", "medium", "low"]:
        if not by_severity[severity]:
            continue
        
        md += f"\n## {severity_emoji[severity]} {severity.capitalize()} находки ({len(by_severity[severity])})\n\n"
        
        for i, f in enumerate(by_severity[severity], 1):
            source_info = f"коммит `{f.source[:7]}`" if f.source != "workdir" else "текущие файлы"
            
            md += f"""### {i}. {f.kind}

- **Серьёзность:** {severity.capitalize()}
- **Категория:** {f.category}
- **Файл:** {f.excerpt[:300]}{'...' if len(f.excerpt) > 300 else ''}



"""
            if f.hint:
                md += f"> **Рекомендация:** {f.hint}\n\n"
            
            md += "---\n\n"
    
    md += f"""

---

*Отчёт сгенерирован инструментом Eclipse {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
    
    return StreamingResponse(
        io.StringIO(md),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=eclipse-report-{scan_id}.md"
        }
    )

@app.get("/api/scans/{scan_id}/export/html")
def export_findings_html(scan_id: int, db: Session = Depends(get_db)):
    scan = db.query(models.Scan).filter(models.Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Скан не найден")
    
    findings = db.query(models.Finding).filter(models.Finding.scan_id == scan_id).all()
    repo = db.query(models.Repository).filter(models.Repository.id == scan.repo_id).first()
    
    by_severity = {"critical": [], "high": [], "medium": [], "low": []}
    for f in findings:
        if f.severity in by_severity:
            by_severity[f.severity].append(f)
    
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Отчёт Eclipse — {repo.name if repo else 'Скан'}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0a0a;
            color: #e5e5e5;
            line-height: 1.6;
            padding: 2rem;
        }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        h1 {{ font-size: 1.75rem; margin-bottom: 1.5rem; }}
        h2 {{ font-size: 1.25rem; margin: 2rem 0 1rem; border-bottom: 1px solid #333; padding-bottom: 0.5rem; }}
        h3 {{ font-size: 1rem; margin: 1rem 0 0.5rem; }}
        
        .summary {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .stat {{
            background: #111;
            border: 1px solid #222;
            border-radius: 8px;
            padding: 1rem;
            text-align: center;
        }}
        .stat-value {{ font-size: 2rem; font-weight: bold; }}
        .stat-label {{ font-size: 0.75rem; color: #888; text-transform: uppercase; }}
        
        .stat.critical .stat-value {{ color: #fff; }}
        .stat.high .stat-value {{ color: #d4d4d4; }}
        .stat.medium .stat-value {{ color: #a3a3a3; }}
        .stat.low .stat-value {{ color: #737373; }}
        
        .finding {{
            background: #111;
            border: 1px solid #222;
            border-radius: 8px;
            margin-bottom: 1rem;
            overflow: hidden;
        }}
        .finding-header {{
            padding: 1rem;
            display: flex;
            align-items: center;
            gap: 1rem;
            border-bottom: 1px solid #222;
        }}
        .finding-body {{ padding: 1rem; }}
        
        .badge {{
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .badge.critical {{ background: #333; color: #fff; border: 1px solid #555; }}
        .badge.high {{ background: transparent; color: #d4d4d4; border: 1px solid #444; }}
        .badge.medium {{ background: transparent; color: #a3a3a3; border: 1px solid #333; }}
        .badge.low {{ background: transparent; color: #737373; border: 1px solid #222; }}
        
        .meta {{ font-size: 0.8rem; color: #888; }}
        .meta code {{ background: #1a1a1a; padding: 0.125rem 0.375rem; border-radius: 4px; }}
        
        pre {{
            background: #000;
            border: 1px solid #222;
            border-radius: 4px;
            padding: 1rem;
            overflow-x: auto;
            font-size: 0.8rem;
            color: #a3a3a3;
            margin: 0.5rem 0;
        }}
        
        .hint {{
            background: #1a1a1a;
            border-left: 3px solid #444;
            padding: 0.75rem 1rem;
            font-size: 0.85rem;
            color: #888;
            margin-top: 0.5rem;
        }}
        
        .footer {{
            margin-top: 3rem;
            padding-top: 1rem;
            border-top: 1px solid #222;
            font-size: 0.8rem;
            color: #555;
            text-align: center;
        }}
        
        table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
        th, td {{ padding: 0.5rem; text-align: left; border-bottom: 1px solid #222; }}
        th {{ color: #888; font-weight: 500; font-size: 0.8rem; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Eclipse</h1>
        
        <table>
            <tr><th>Репозиторий</th><td>{repo.name if repo else 'Неизвестно'}</td></tr>
            <tr><th>Источник</th><td>{repo.source_url or repo.path if repo else 'Н/Д'}</td></tr>
            <tr><th>Дата сканирования</th><td>{scan.started_at.strftime('%Y-%m-%d %H:%M') if scan.started_at else 'Н/Д'}</td></tr>
            <tr><th>Статус</th><td>{scan.status}</td></tr>
        </table>
        
        <div class="summary">
            <div class="stat critical">
                <div class="stat-value">{len(by_severity['critical'])}</div>
                <div class="stat-label">Критические</div>
            </div>
            <div class="stat high">
                <div class="stat-value">{len(by_severity['high'])}</div>
                <div class="stat-label">Высокие</div>
            </div>
            <div class="stat medium">
                <div class="stat-value">{len(by_severity['medium'])}</div>
                <div class="stat-label">Средние</div>
            </div>
            <div class="stat low">
                <div class="stat-value">{len(by_severity['low'])}</div>
                <div class="stat-label">Низкие</div>
            </div>
        </div>
"""
    
    for severity in ["critical", "high", "medium", "low"]:
        if not by_severity[severity]:
            continue
        
        html += f'<h2>{severity.capitalize()} ({len(by_severity[severity])})</h2>\n'
        
        for f in by_severity[severity]:
            source_info = f'коммит <code>{f.source[:7]}</code>' if f.source != "workdir" else "текущие файлы"
            excerpt_escaped = (f.excerpt[:300] + ('...' if len(f.excerpt) > 300 else '')).replace('<', '&lt;').replace('>', '&gt;')
            
            html += f"""
        <div class="finding">
            <div class="finding-header">
                <span class="badge {f.severity}">{f.severity}</span>
                <strong>{f.kind}</strong>
                <span class="meta" style="margin-left: auto;">{f.category}</span>
            </div>
            <div class="finding-body">
                <div class="meta">
                    <code>{f.path}</code> · {source_info}
                </div>
                <pre>{excerpt_escaped}</pre>
                {'<div class="hint">💡 ' + f.hint + '</div>' if f.hint else ''}
            </div>
        </div>
"""
    
    html += f"""
        <div class="footer">
            Сгенерировано Eclipse · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>
    </div>
</body>
</html>
"""
    
    return StreamingResponse(
        io.StringIO(html),
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=eclipse-report-{scan_id}.html"
        }
    )
