import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tickets.db")
engine_args = {"connect_args": {"check_same_thread": False}} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, **engine_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String(100), nullable=False)
    email = Column(String(200), nullable=False)
    subject = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(50), nullable=False, default="General")
    priority = Column(String(20), nullable=False, default="Medium")
    status = Column(String(20), nullable=False, default="Open")
    ai_summary = Column(Text, nullable=False, default="")
    suggested_reply = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Support Ticket Management System", version="1.0.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

class TicketCreate(BaseModel):
    customer_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=200)
    subject: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=5, max_length=5000)

class TicketUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None

VALID_STATUSES = {"Open", "In Progress", "Resolved", "Closed"}
VALID_PRIORITIES = {"Low", "Medium", "High", "Urgent"}
VALID_CATEGORIES = {"Technical", "Billing", "Account", "General"}

def analyze_ticket(subject: str, description: str):
    """Simple local analysis; no AI key is required to run the project."""
    text = f"{subject} {description}".lower()

    if any(word in text for word in ["payment", "invoice", "refund", "charged", "billing", "bill"]):
        category = "Billing"
    elif any(word in text for word in ["password", "login", "account", "locked", "sign in", "access"]):
        category = "Account"
    elif any(word in text for word in ["error", "bug", "crash", "not working", "failed", "slow", "server", "api"]):
        category = "Technical"
    else:
        category = "General"

    urgent_words = ["urgent", "critical", "outage", "cannot work", "production down", "security breach"]
    high_words = ["blocked", "failed", "not working", "unable to", "error", "crash"]
    if any(word in text for word in urgent_words):
        priority = "Urgent"
    elif any(word in text for word in high_words):
        priority = "High"
    elif any(word in text for word in ["question", "how do i", "information"]):
        priority = "Low"
    else:
        priority = "Medium"

    summary = (description.strip()[:220] + ("..." if len(description.strip()) > 220 else ""))
    reply = (
        f"Hello, thank you for contacting support about '{subject}'. "
        "We have recorded your request and will investigate it. "
        "If you have additional details or screenshots, please share them with us. "
        "We will update you when we have more information."
    )
    return category, priority, summary, reply

def ticket_dict(ticket):
    return {
        "id": ticket.id,
        "customer_name": ticket.customer_name,
        "email": ticket.email,
        "subject": ticket.subject,
        "description": ticket.description,
        "category": ticket.category,
        "priority": ticket.priority,
        "status": ticket.status,
        "ai_summary": ticket.ai_summary,
        "suggested_reply": ticket.suggested_reply,
        "created_at": ticket.created_at.isoformat() + "Z",
        "updated_at": ticket.updated_at.isoformat() + "Z",
    }

@app.get("/")
def home():
    return FileResponse("static/index.html")

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "AI Support Ticket Management System"}

@app.post("/api/tickets", status_code=201)
def create_ticket(payload: TicketCreate):
    category, priority, summary, reply = analyze_ticket(payload.subject, payload.description)
    db = SessionLocal()
    try:
        ticket = Ticket(
            customer_name=payload.customer_name.strip(),
            email=payload.email.strip(),
            subject=payload.subject.strip(),
            description=payload.description.strip(),
            category=category,
            priority=priority,
            status="Open",
            ai_summary=summary,
            suggested_reply=reply,
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        return ticket_dict(ticket)
    finally:
        db.close()

@app.get("/api/tickets")
def list_tickets(
    search: Optional[str] = Query(default=None, max_length=200),
    status: Optional[str] = None,
    category: Optional[str] = None,
):
    db = SessionLocal()
    try:
        query = db.query(Ticket)
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(
                (Ticket.subject.ilike(pattern)) |
                (Ticket.customer_name.ilike(pattern)) |
                (Ticket.email.ilike(pattern)) |
                (Ticket.description.ilike(pattern))
            )
        if status:
            if status not in VALID_STATUSES:
                raise HTTPException(status_code=400, detail="Invalid status filter")
            query = query.filter(Ticket.status == status)
        if category:
            if category not in VALID_CATEGORIES:
                raise HTTPException(status_code=400, detail="Invalid category filter")
            query = query.filter(Ticket.category == category)
        tickets = query.order_by(Ticket.created_at.desc()).all()
        return [ticket_dict(t) for t in tickets]
    finally:
        db.close()

@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: int):
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return ticket_dict(ticket)
    finally:
        db.close()

@app.patch("/api/tickets/{ticket_id}")
def update_ticket(ticket_id: int, payload: TicketUpdate):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Provide at least one field to update")
    if "status" in updates and updates["status"] not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(sorted(VALID_STATUSES))}")
    if "priority" in updates and updates["priority"] not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Priority must be one of: {', '.join(sorted(VALID_PRIORITIES))}")
    if "category" in updates and updates["category"] not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Category must be one of: {', '.join(sorted(VALID_CATEGORIES))}")

    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        for key, value in updates.items():
            setattr(ticket, key, value)
        ticket.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(ticket)
        return ticket_dict(ticket)
    finally:
        db.close()

@app.delete("/api/tickets/{ticket_id}", status_code=204)
def delete_ticket(ticket_id: int):
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        db.delete(ticket)
        db.commit()
    finally:
        db.close()

@app.get("/api/stats")
def stats():
    db = SessionLocal()
    try:
        tickets = db.query(Ticket).all()
        return {
            "total": len(tickets),
            "open": sum(t.status == "Open" for t in tickets),
            "in_progress": sum(t.status == "In Progress" for t in tickets),
            "resolved": sum(t.status == "Resolved" for t in tickets),
            "urgent": sum(t.priority == "Urgent" for t in tickets),
        }
    finally:
        db.close()
