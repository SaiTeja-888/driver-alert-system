import sqlite3
from datetime import datetime
from config import DATABASE_PATH

class Database:
    def __init__(self):
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(DATABASE_PATH)
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executescript("""
                CREATE TABLE IF NOT EXISTS drivers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    license_number TEXT UNIQUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    driver_id INTEGER,
                    start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    end_time DATETIME,
                    avg_score REAL,
                    FOREIGN KEY(driver_id) REFERENCES drivers(id)
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    event_type TEXT,
                    severity TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    alert_message TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    file_path TEXT,
                    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
            """)
            conn.commit()

            # Insert default driver if none exists
            cursor.execute("SELECT count(*) as count FROM drivers")
            if cursor.fetchone()['count'] == 0:
                cursor.execute("INSERT INTO drivers (name, license_number) VALUES ('Default Driver', 'DEF12345')")
                conn.commit()

    def create_session(self, driver_id=1):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO sessions (driver_id) VALUES (?)", (driver_id,))
            conn.commit()
            return cursor.lastrowid

    def log_event(self, session_id, event_type, severity):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO events (session_id, event_type, severity) VALUES (?, ?, ?)",
                (session_id, event_type, severity)
            )
            conn.commit()

    def log_alert(self, session_id, alert_message):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO alerts (session_id, alert_message) VALUES (?, ?)",
                (session_id, alert_message)
            )
            conn.commit()

    def get_recent_events(self, limit=50):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM events ORDER BY timestamp DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            stats = {}
            cursor.execute("SELECT count(*) as count FROM events WHERE event_type='DROWSINESS'")
            stats['drowsiness'] = cursor.fetchone()['count']
            cursor.execute("SELECT count(*) as count FROM events WHERE event_type='PHONE_USAGE'")
            stats['phone_usage'] = cursor.fetchone()['count']
            cursor.execute("SELECT count(*) as count FROM events WHERE event_type='DISTRACTION'")
            stats['distraction'] = cursor.fetchone()['count']
            cursor.execute("SELECT count(*) as count FROM events WHERE event_type='YAWNING'")
            stats['yawning'] = cursor.fetchone()['count']
            return stats

db = Database()
