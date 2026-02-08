from models.chat import Chat
from models.message import Message
from database import db
import logging

logging.basicConfig(level=logging.INFO)

def get_or_create_chat(chat_id):
    try:
        chat = Chat.query.filter_by(chat_id=str(chat_id)).first()
        if not chat:
            chat = Chat(chat_id=str(chat_id))
            db.session.add(chat)
            db.session.commit()
        return chat
    except Exception as e:
        db.session.rollback()
        logging.error(f"ERROR creating/getting chat: {e}")
        return None

def set_language(chat_id, lang):
    try:
        chat = get_or_create_chat(chat_id)
        chat.language = lang
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.error(f"ERROR set_language chat: {e}")

def get_language(chat_id):
    chat = get_or_create_chat(chat_id)
    if chat:
        return chat.language
    return "English"   # default

def save_message(chat_id, role, content):
    try:
        msg = Message(
            chat_id=str(chat_id),
            role=role,
            content=content
        )
        db.session.add(msg)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.error(f"ERROR saving message: {e}")

def get_recent_messages(chat_id, limit=10):
    try:
        return Message.query.filter_by(chat_id=str(chat_id))\
            .order_by(Message.timestamp.desc())\
            .limit(limit)\
            .all()
    except Exception as e:
        logging.error(f"ERROR getting recent messages: {e}")
        return []

def build_llm_history(chat_id, limit=10):
    try:
        messages = get_recent_messages(chat_id, limit)
        messages.reverse()   # oldest → newest

        history = []
        for m in messages:
            history.append({
                "role": "user" if m.role == "user" else "assistant",
                "content": m.content
            })
        return history
    except Exception as e:
        logging.error(f"ERROR building LLM history: {e}")
        return []
    
def clear_chat_history(chat_id):
    try:
        Message.query.filter_by(chat_id=str(chat_id)).delete()
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logging.error(f"DB ERROR clear_chat_history: {e}")
        return False
