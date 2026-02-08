from database import db
from datetime import datetime

class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(10))   # user / bot
    content = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
