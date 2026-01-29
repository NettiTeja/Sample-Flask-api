from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import os

import json
import requests
from dotenv import load_dotenv
from google import genai
load_dotenv()


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


GENAI_API_KEY = os.getenv("GEMINI_API_KEY")
# genai.configure(api_key=GENAI_API_KEY)
client = genai.Client(api_key=GENAI_API_KEY)

# Load the Gemini Pro model

model_list = []
# iter the models
# for model in client.models.list():
#     # We filter for 'gemini' models to keep the list relevant
#     print("name", model.name) # e.g. "models/gemini-1.5-flash"
#     print("display_name", model.display_name)
#     print("description", model.description)
#     print("------")

@app.route('/chat', methods=['POST'])
def chat():
    try:
        # model = genai.GenerativeModel("gemini-1.5-flash")
        data = request.get_json()
        user_prompt = data.get("prompt", "")
        system_prompt = data.get("system_prompt", "You are a helpful assistant.")

        if not user_prompt:
            return jsonify({"error": "Missing prompt"}), 400

        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[
                {"role": "user", "parts": [{"text": system_prompt}]},
                {"role": "user", "parts": [{"text": user_prompt}]}
            ]
        )

        return jsonify({"reply": response.text})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    data = request.json
    chat_id = data["message"]["chat"]["id"]
    user_msg = data["message"].get("text", "")
    system_prompt = "You are an expert agricultural assistant."
    if not user_msg:
        answer = "please enter message."
    else:
        try:
            response =client.models.generate_content(
                    model="gemini-flash-latest",
                    contents=[
                        {"role": "user", "parts": [{"text": system_prompt}]},
                        {"role": "user", "parts": [{"text": user_msg}]}
                    ]
                )

            answer = response.text
        except Exception as e:
            answer = "Sorry, no response."

    # Send back to Telegram
    requests.post(
        f"{TELEGRAM_URL}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": answer
        }
    )
    return "OK"





if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)), debug=True)
