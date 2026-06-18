import os
import io
import uuid
import json
import threading
from typing import Dict, List
from contextlib import asynccontextmanager

import re
from pathlib import Path
from urllib.parse import quote
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse

env_path = Path(__file__).parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

from models import (
    Chat, ChatEvaluation, EvaluationRequest,
    GoodExample, MessageRole
)
from parser import parse_file, get_employees, filter_chats_for_employee
from evaluator import evaluate_chats_batch
from exporter import export_to_excel
from learning import (
    add_good_example, get_good_examples,
    delete_good_example, format_examples_for_prompt
)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

uploaded_files: Dict[str, str] = {}
parsed_chats: Dict[str, List[Chat]] = {}
evaluation_results: Dict[str, List[ChatEvaluation]] = {}
evaluation_chats: Dict[str, List[Chat]] = {}

eval_tasks: Dict[str, dict] = {}


def _safe_filename(name: str) -> str:
    return re.sub(r'[^\w\-.]', '_', name, flags=re.ASCII)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Сервис оценки чатов", lifespan=lifespan)

@app.middleware("http")
async def no_cache_middleware(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Файл не выбран")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".txt", ".xml"):
        raise HTTPException(status_code=400, detail="Поддерживаются только файлы TXT и XML")

    file_id = str(uuid.uuid4())[:8]
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    uploaded_files[file_id] = file_path

    try:
        chats = parse_file(file_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка парсинга файла: {str(e)}")

    if not chats:
        raise HTTPException(status_code=400, detail="Не удалось найти диалоги в файле. Проверьте формат файла.")

    parsed_chats[file_id] = chats
    employees = get_employees(chats)

    emp_info = []
    for emp in employees:
        emp_chats = filter_chats_for_employee(chats, emp)
        emp_info.append({"name": emp, "chat_count": len(emp_chats)})

    return {
        "file_id": file_id,
        "filename": file.filename,
        "total_chats": len(chats),
        "employees": employees,
        "employee_info": emp_info
    }


@app.get("/api/employees/{file_id}")
async def get_employees_list(file_id: str):
    if file_id not in parsed_chats:
        raise HTTPException(status_code=404, detail="Файл не найден. Загрузите файл заново.")

    chats = parsed_chats[file_id]
    employees = get_employees(chats)

    result = []
    for emp in employees:
        emp_chats = filter_chats_for_employee(chats, emp)
        result.append({
            "name": emp,
            "chat_count": len(emp_chats)
        })

    return {"employees": result}


@app.post("/api/evaluate")
async def evaluate(request: EvaluationRequest):
    file_id = request.file_id
    employee_name = request.employee_name
    max_chats = request.max_chats
    use_ai = request.use_ai

    if file_id not in parsed_chats:
        raise HTTPException(status_code=404, detail="Файл не найден. Загрузите файл заново.")

    chats = parsed_chats[file_id]
    filtered = filter_chats_for_employee(chats, employee_name, max_chats)

    if not filtered:
        raise HTTPException(status_code=400, detail=f"Нет диалогов для сотрудника: {employee_name}")

    session_id = str(uuid.uuid4())[:8]
    evaluation_chats[session_id] = filtered

    eval_tasks[session_id] = {
        "status": "running",
        "current": 0,
        "total": len(filtered),
        "error": None,
    }

    def run_eval():
        try:
            evaluations = evaluate_chats_batch(filtered, use_ai=use_ai)
            evaluation_results[session_id] = evaluations
            eval_tasks[session_id]["status"] = "done"
        except Exception as e:
            eval_tasks[session_id]["status"] = "error"
            eval_tasks[session_id]["error"] = str(e)

    thread = threading.Thread(target=run_eval, daemon=True)
    thread.start()

    return {
        "task_id": session_id,
        "total": len(filtered),
        "employee_name": employee_name,
    }


@app.get("/api/ai-usage")
async def ai_usage():
    from ai_evaluator import get_usage_stats
    return get_usage_stats()


@app.get("/api/evaluate/{task_id}/progress")
async def evaluate_progress(task_id: str):
    if task_id not in eval_tasks:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    task = eval_tasks[task_id]
    if task["status"] == "running":
        return {"status": "running", "current": 0, "total": task["total"]}
    elif task["status"] == "done":
        return {"status": "done", "current": task["total"], "total": task["total"]}
    else:
        return {"status": "error", "error": task.get("error", "Unknown error")}


@app.get("/api/results/{session_id}")
async def get_results(session_id: str):
    if session_id not in evaluation_results:
        raise HTTPException(status_code=404, detail="Результаты не найдены")
    return {"results": [ev.model_dump() for ev in evaluation_results[session_id]]}


@app.get("/api/dashboard")
async def dashboard():
    from collections import Counter, defaultdict

    all_evals = []
    for evals in evaluation_results.values():
        all_evals.extend(evals)

    if not all_evals:
        return {"total_evaluations": 0}

    emp_scores = defaultdict(list)
    score_dist = Counter()
    date_scores = defaultdict(list)
    weakness_counter = Counter()

    for ev in all_evals:
        emp_scores[ev.employee_name].append(ev.total_score)
        score_dist[ev.total_score] += 1
        if ev.date:
            date_scores[ev.date].append(ev.total_score)
        for w in ev.weaknesses:
            weakness_counter[w] += 1

    employees = []
    for name, scores in emp_scores.items():
        employees.append({
            "name": name,
            "avg_score": round(sum(scores) / len(scores), 1),
            "total": len(scores),
            "critical": sum(1 for s in scores if s == 0),
            "excellent": sum(1 for s in scores if s == 100),
        })
    employees.sort(key=lambda x: x["avg_score"], reverse=True)

    sorted_dates = sorted(date_scores.keys())
    dynamics = [
        {"date": d, "avg_score": round(sum(date_scores[d]) / len(date_scores[d]), 1), "count": len(date_scores[d])}
        for d in sorted_dates
    ]

    top_weaknesses = [
        {"text": w, "count": c}
        for w, c in weakness_counter.most_common(10)
    ]

    return {
        "total_evaluations": len(all_evals),
        "total_employees": len(emp_scores),
        "employees": employees,
        "score_distribution": {
            "critical": score_dist.get(0, 0),
            "satisfactory": score_dist.get(30, 0),
            "excellent": score_dist.get(100, 0),
        },
        "dynamics": dynamics,
        "top_weaknesses": top_weaknesses,
    }


@app.get("/api/chats/{session_id}")
async def get_session_chats(session_id: str):
    if session_id not in evaluation_chats:
        raise HTTPException(status_code=404, detail="Чаты не найдены")
    return {"chats": [c.model_dump() for c in evaluation_chats[session_id]]}


@app.get("/api/chat/{session_id}/{chat_id}")
async def get_chat_detail(session_id: str, chat_id: str):
    if session_id not in evaluation_chats:
        raise HTTPException(status_code=404, detail="Сессия не найдена")

    chats = evaluation_chats[session_id]
    for chat in chats:
        if chat.id == chat_id:
            return {"chat": chat.model_dump()}

    raise HTTPException(status_code=404, detail="Диалог не найден")


@app.post("/api/mark-good/{session_id}/{chat_id}")
async def mark_as_good(session_id: str, chat_id: str):
    if session_id not in evaluation_chats:
        raise HTTPException(status_code=404, detail="Сессия не найдена")

    chats = evaluation_chats[session_id]
    for chat in chats:
        if chat.id == chat_id:
            example = add_good_example(chat)
            return {"status": "ok", "example": example.model_dump()}

    raise HTTPException(status_code=404, detail="Диалог не найден")


@app.get("/api/good-examples")
async def list_good_examples():
    examples = get_good_examples()
    return {"examples": [ex.model_dump() for ex in examples]}


@app.delete("/api/good-examples/{example_id}")
async def remove_good_example(example_id: str):
    success = delete_good_example(example_id)
    if not success:
        raise HTTPException(status_code=404, detail="Пример не найден")
    return {"status": "ok"}


@app.get("/api/export/{session_id}")
async def export_results(session_id: str, filter: str = "all"):
    if session_id not in evaluation_results:
        raise HTTPException(status_code=404, detail="Результаты не найдены")

    if session_id not in evaluation_chats:
        raise HTTPException(status_code=404, detail="Чаты не найдены")

    evaluations = evaluation_results[session_id]
    chats = evaluation_chats[session_id]
    employee_name = evaluations[0].employee_name if evaluations else "Unknown"

    filter_label = ""
    if filter == "good":
        evaluations = [e for e in evaluations if e.total_score == 100]
        filter_label = " — отличные диалоги"
    elif filter == "bad":
        evaluations = [e for e in evaluations if e.total_score == 0]
        filter_label = " — критичные диалоги"
    elif filter == "medium":
        evaluations = [e for e in evaluations if e.total_score == 30]
        filter_label = " — удовлетворительные диалоги"

    if not evaluations:
        raise HTTPException(status_code=404, detail="Нет диалогов с выбранным фильтром")

    chat_ids = {e.chat_id for e in evaluations}
    chats = [c for c in chats if c.id in chat_ids]

    surname = employee_name.split()[0] if employee_name else "Unknown"
    type_labels = {"good": "хорошие", "bad": "плохие", "medium": "удовлетворительные", "all": "все"}
    type_label = type_labels.get(filter, "все")

    try:
        excel_data = export_to_excel(evaluations, chats, employee_name + filter_label, filter_type=filter)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка создания Excel: {str(e)}")

    filename = f"{surname}_{type_label}_{len(evaluations)}.xlsx"
    filename_ascii = f"export_{filter}_{len(evaluations)}.xlsx"

    return StreamingResponse(
        io.BytesIO(excel_data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename_ascii}\"; filename*=UTF-8''{quote(filename)}"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
