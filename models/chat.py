from database import db

class Chat(db.Model):
    __tablename__ = "chats"

    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.String(50), unique=True, nullable=False)
    language = db.Column(db.String(10), default="english")
