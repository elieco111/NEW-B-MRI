from fastapi import FastAPI, Request, Form, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn
import secrets
from datetime import datetime
import json
import io
import sqlite3

# Import ReportLab for PDF creation
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

from database import get_db, init_db

app = FastAPI(title="B-MRI CoreFocus™ Platform")
templates = Jinja2Templates(directory="templates")

# Initialize SQLite database
init_db()

# Websocket manager for real-time live presentation
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.current_slide = 1
        self.votes = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        # Send current state
        await websocket.send_json({"type": "slide_change", "slide": self.current_slide})
        await websocket.send_json({"type": "vote_update", "votes": self.votes})

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

# CoreHeuristic AI Scan Engine
def run_core_heuristic(client_id, role, text):
    # Analyzes inputs and extracts focus points
    db = get_db()
    cursor = db.cursor()
    
    keywords = {
        "צוואר בקבוק": ("צוואר בקבוק בתהליכי קבלת החלטות", "נמצא חוסר סנכרון ועיכוב בקבלת החלטות שמוביל לחסימה ארגונית.", "strategic", 4),
        "רווח": ("מיקוד תמחור ורווחיות לא אופטימלית", "עלה פער ברווחיות וזיהוי מוצרים/שירותים מפסידים.", "strategic", 5),
        "תפעול": ("קושי סנכרון ממשק מכירות-תפעול", "פער משמעותי בין הבטחת המכירות לבין יכולת המסירה והביצוע של התפעול.", "strategic", 4),
        "שיווק": ("חוסר מיקוד שיווקי וקהל יעד לא מזוקק", "השאלונים מציפים חוסר בהירות אסטרטגית בניהול הלקוחות והצעת הערך.", "tactical", 3),
        "עומס": ("עומס ניהולי ועודף משימות טקטיות", "המנהלים מדווחים על קושי בזיקוק העיקר מהטפל בעקבות עומס פניות.", "tactical", 4),
    }

    found = False
    for word, (title, desc, f_type, confidence) in keywords.items():
        if word in text:
            cursor.execute("""
                INSERT INTO focus_points (client_id, title, description, type, confidence, source)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (client_id, title, f"הודגם מתוך שאלון {role}: '{text[:100]}...'", f_type, confidence, f"שאלון {role}"))
            found = True
            
    if not found:
        # Fallback focus point
        cursor.execute("""
            INSERT INTO focus_points (client_id, title, description, type, confidence, source)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (client_id, f"נושא דורש בירור - {role}", f"התקבלה תשובה מקיפה: '{text[:150]}'", "tactical", 3, f"שאלון {role}"))
        
    db.commit()
    db.close()


# Routes
@app.get("/")
def index():
    return RedirectResponse(url="/dashboard")

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM clients ORDER BY created_at DESC")
    clients = cursor.fetchall()
    
    # Calculate stats
    cursor.execute("SELECT COUNT(*) FROM questionnaires WHERE status='completed'")
    total_completed_q = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM decision_cards")
    total_decisions = cursor.fetchone()[0]
    
    db.close()
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "clients": clients,
        "total_completed_q": total_completed_q,
        "total_decisions": total_decisions
    })

@app.post("/client/create")
def create_client(name: str = Form(...), industry: str = Form(None)):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("INSERT INTO clients (name, industry, core_map) VALUES (?, ?, ?)", (name, industry, "[]"))
    client_id = cursor.lastrowid
    db.commit()
    db.close()
    return RedirectResponse(url=f"/client/{client_id}", status_code=303)

@app.get("/client/{client_id}", response_class=HTMLResponse)
def client_folder(client_id: int, request: Request):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM clients WHERE id=?", (client_id,))
    client = cursor.fetchone()
    
    active_functions = json.loads(client["core_map"]) if client["core_map"] else []
    
    # Get Questionnaires
    cursor.execute("SELECT * FROM questionnaires WHERE client_id=?", (client_id,))
    questionnaires = cursor.fetchall()
    
    # Get Focus Points
    cursor.execute("SELECT * FROM focus_points WHERE client_id=?", (client_id,))
    focus_points = cursor.fetchall()
    
    # Get Decision Cards
    cursor.execute("SELECT * FROM decision_cards WHERE client_id=?", (client_id,))
    decision_cards = cursor.fetchall()
    
    db.close()
    
    host_url = f"{request.url.scheme}://{request.url.netloc}"
    
    return templates.TemplateResponse("client_folder.html", {
        "request": request,
        "client": client,
        "active_functions": active_functions,
        "questionnaires": questionnaires,
        "focus_points": focus_points,
        "decision_cards": decision_cards,
        "host_url": host_url
    })

@app.post("/client/{client_id}/update_map")
def update_map(client_id: int, functions: list[str] = Form([])):
    db = get_db()
    cursor = db.cursor()
    
    # Save CoreMap JSON
    cursor.execute("UPDATE clients SET core_map=? WHERE id=?", (json.dumps(functions), client_id))
    
    # Create missing questionnaires
    for func in functions:
        cursor.execute("SELECT * FROM questionnaires WHERE client_id=? AND role=?", (client_id, func))
        if not cursor.fetchone():
            token = secrets.token_urlsafe(16)
            cursor.execute("INSERT INTO questionnaires (client_id, token, role) VALUES (?, ?, ?)", (client_id, token, func))
            
    db.commit()
    db.close()
    return RedirectResponse(url=f"/client/{client_id}", status_code=303)

@app.post("/client/{client_id}/add_focus")
def add_focus(client_id: int, title: str = Form(...), type: str = Form(...), confidence: int = Form(...), description: str = Form(...)):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO focus_points (client_id, title, description, type, confidence, source)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (client_id, title, description, type, confidence, "ידני (יועץ B-MRI)"))
    db.commit()
    db.close()
    return RedirectResponse(url=f"/client/{client_id}", status_code=303)

@app.post("/client/{client_id}/delete_focus/{focus_id}")
def delete_focus(client_id: int, focus_id: int):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM focus_points WHERE id=? AND client_id=?", (focus_id, client_id))
    db.commit()
    db.close()
    return RedirectResponse(url=f"/client/{client_id}", status_code=303)

@app.post("/client/{client_id}/add_decision")
def add_decision(client_id: int, title: str = Form(...), outcome: str = Form(...), execution_plan: str = Form(...)):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO decision_cards (client_id, title, outcome, execution_plan)
        VALUES (?, ?, ?, ?)
    """, (client_id, title, outcome, execution_plan))
    db.commit()
    db.close()
    return RedirectResponse(url=f"/client/{client_id}", status_code=303)

@app.get("/q/{token}", response_class=HTMLResponse)
def get_questionnaire(token: str, request: Request):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM questionnaires WHERE token=?", (token,))
    q = cursor.fetchone()
    db.close()
    
    if not q:
        return HTMLResponse("הקישור אינו בתוקף.", status_code=404)
        
    return templates.TemplateResponse("questionnaire.html", {"request": request, "questionnaire": q})

@app.post("/q/{token}/submit")
def submit_questionnaire(token: str, q1: str = Form(...), q2: str = Form(...), q3: str = Form(...)):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM questionnaires WHERE token=?", (token,))
    q = cursor.fetchone()
    
    if not q:
        return HTMLResponse("הקישור אינו בתוקף.", status_code=404)
        
    responses = {"q1": q1, "q2": q2, "q3": q3}
    cursor.execute("""
        UPDATE questionnaires 
        SET status='completed', responses=?, completed_at=?
        WHERE token=?
    """, (json.dumps(responses), datetime.now().isoformat(), token))
    db.commit()
    
    # Process with CoreHeuristic engine
    combined_text = f"{q1} {q2} {q3}"
    run_core_heuristic(q["client_id"], q["role"], combined_text)
    
    db.close()
    return RedirectResponse(url=f"/q/{token}", status_code=303)

# Live presentation pathways
@app.get("/live/present", response_class=HTMLResponse)
def live_present(request: Request):
    return templates.TemplateResponse("live_present.html", {"request": request})

@app.get("/live/join", response_class=HTMLResponse)
def live_join(request: Request):
    return templates.TemplateResponse("live_join.html", {"request": request})

@app.get("/live/vote", response_class=HTMLResponse)
def live_vote(name: str, role: str, request: Request):
    return templates.TemplateResponse("live_vote.html", {"request": request, "name": name, "role": role})

# ReportLab PDF Generation
@app.get("/client/{client_id}/generate_pdf")
def generate_pdf(client_id: int):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM clients WHERE id=?", (client_id,))
    client = cursor.fetchone()
    
    cursor.execute("SELECT * FROM focus_points WHERE client_id=?", (client_id,))
    focus_points = cursor.fetchall()
    
    cursor.execute("SELECT * FROM decision_cards WHERE client_id=?", (client_id,))
    decision_cards = cursor.fetchall()
    db.close()

    # Create a clean binary stream
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=LETTER, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
    story = []

    # Palette
    COLOR_PRIMARY = HexColor("#1A1A1A")
    COLOR_BLUE = HexColor("#3A5268")
    COLOR_RED = HexColor("#E63946")
    COLOR_GREEN = HexColor("#A8D92E")

    styles = getSampleStyleSheet()
    
    # Custom Hebrew supported fonts (using standard fallbacks)
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        textColor=COLOR_PRIMARY,
        alignment=TA_CENTER,
        spaceAfter=20
    )
    
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        textColor=HexColor('#333333'),
        alignment=TA_RIGHT,
        spaceAfter=10
    )

    header_style = ParagraphStyle(
        'Header',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        textColor=COLOR_BLUE,
        alignment=TA_RIGHT,
        spaceAfter=12
    )

    # Document Header
    story.append(Paragraph("B-MRI | CoreFocus™ Strategic Summary", title_style))
    story.append(Paragraph(f"חברה / לקוח: {client['name']}", header_style))
    story.append(Spacer(1, 15))

    story.append(Paragraph("1. מוקדי חסימה והזדמנויות (CoreHeuristic™ Findings)", header_style))
    for idx, f in enumerate(focus_points):
        point_text = f"<b>{f['title']}</b> ({f['type']})<br/>{f['description']}"
        story.append(Paragraph(point_text, body_style))
        story.append(Spacer(1, 5))
        
    story.append(Spacer(1, 15))

    story.append(Paragraph("2. כרטיסי הכרעה ותוכנית עבודה 30/60/90", header_style))
    for d in decision_cards:
        decision_text = f"<b>החלטה: {d['title']}</b><br/>תוצאה מצופה: {d['outcome']}<br/>תוכנית פעולה:<br/>{d['execution_plan']}"
        story.append(Paragraph(decision_text, body_style))
        story.append(Spacer(1, 10))

    doc.build(story)
    pdf_buffer.seek(0)
    
    return StreamingResponse(pdf_buffer, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=bmri-corefocus-{client_id}.pdf"
    })

# Websocket endpoint for presenter and viewers
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data_str = await websocket.receive_text()
            data = json.loads(data_str)
            
            if data["type"] == "slide_change":
                manager.current_slide = data["slide"]
                await manager.broadcast({"type": "slide_change", "slide": manager.current_slide})
                
            elif data["type"] == "submit_vote":
                option = data["option"]
                manager.votes[option] = manager.votes.get(option, 0) + 1
                await manager.broadcast({"type": "vote_update", "votes": manager.votes})
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=4000, reload=True)
