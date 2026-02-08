from database import db

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    location = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True, nullable=False)
    language = db.Column(db.String(50))
    password = db.Column(db.String(100), nullable=False)