import sqlite3
import json
import os

DB_PATH = "bmri_corefocus.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Clients Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        industry TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        core_map TEXT
    )
    """)
    
    # Questionnaires Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS questionnaires (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        token TEXT UNIQUE,
        role TEXT,
        status TEXT DEFAULT 'pending',
        responses TEXT,
        completed_at TIMESTAMP,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )
    """)
    
    # Focus Points Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS focus_points (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        title TEXT,
        description TEXT,
        type TEXT, -- tactical / strategic
        confidence INTEGER, -- 1 to 5
        source TEXT,
        status TEXT DEFAULT 'suggested', -- suggested / approved
        score REAL DEFAULT 0.0,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )
    """)
    
    # Decision Cards Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS decision_cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        focus_point_id INTEGER,
        title TEXT,
        alternatives TEXT, -- JSON list of alternatives
        outcome TEXT,
        context TEXT,
        evidence TEXT,
        dependencies TEXT,
        objections TEXT,
        resources TEXT,
        final_decision TEXT,
        execution_plan TEXT, -- JSON for 30/60/90
        FOREIGN KEY (client_id) REFERENCES clients(id),
        FOREIGN KEY (focus_point_id) REFERENCES focus_points(id)
    )
    """)
    
    # Live Sessions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS live_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        current_slide INTEGER DEFAULT 1,
        active_votes TEXT, -- JSON representation of votes
        is_active BOOLEAN DEFAULT 0,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )
    """)
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
