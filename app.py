from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)
CORS(app)

# SQLite DB config

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///./database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# User Model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    location = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True, nullable=False)
    language = db.Column(db.String(50))
    password = db.Column(db.String(100), nullable=False)

# Initialize DB
with app.app_context():
    db.create_all()

# Routes
@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    existing_user = User.query.filter_by(email=data['email']).first()
    if existing_user:
        return jsonify({'message': 'User already exists'}), 409

    new_user = User(
        name=data['name'],
        location=data['location'],
        email=data['email'],
        language=data['language'],
        password=data['password']
    )
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'Signup successful'}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(email=data['email']).first()

    if user and user.password == data['password']:
        return jsonify({'message': 'Login successful', 'name': user.name,'email':user.email}), 200
    return jsonify({'message': 'Invalid credentials'}), 401


@app.route('/profile', methods=['POST'])
def profile():
    data = request.json
    user = User.query.filter_by(email=data.get('email')).first()

    if user:
        return jsonify({
            'name': user.name,
            'email': user.email,
            'location': user.location,
            'language': user.language
        }), 200
    return jsonify({'message': 'User not found'}), 404




if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)), debug=True)
