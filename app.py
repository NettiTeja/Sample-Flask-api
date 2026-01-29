from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import os
from threading import Thread

import json
import requests
from dotenv import load_dotenv
from google import genai
import base64
import uuid
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
client = genai.Client(api_key=GENAI_API_KEY)


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
    message=data.get("message", {})
    
    if "photo" in message:
        photos = message["photo"]
        file_id = photos[-1]["file_id"]  
        Thread(target=handle_crop_image, args=(chat_id, file_id)).start()
        return "OK"
    elif "text" in message:
        Thread(target=agrichat, args=(chat_id, user_msg)).start()
        return "OK"

    else:
        send_message(chat_id, "please send text or image.")
        return "OK"

def agrichat(chat_id,user_msg,system_prompt=None):
    if not system_prompt:
        system_prompt = "You are an expert agricultural assistant.try to give short answers.until unless asked for more details."
    if not user_msg:
        answer = "please enter message."
    else:
        try:
            send_message(chat_id, "bot is typing...")
            response =client.models.generate_content(
                    model="gemini-flash-latest",
                    contents=[
                        {"role": "user", "parts": [{"text": system_prompt}]},
                        {"role": "user", "parts": [{"text": user_msg}]}
                    ]
                )

            answer = response.text
            print("Generated Answer:", answer)
        except Exception as e:
            answer = "Sorry, no response."
    send_message(chat_id, answer)




# ---------------- TELEGRAM UTILS ---------------- #

def send_message(chat_id, text):
    requests.post(
        f"{TELEGRAM_URL}/sendMessage",
        json={"chat_id": chat_id, "text": text}
    )

def download_image(file_id):
    """
    Downloads image from Telegram and saves using UUID
    """
    filename = f"crop_{uuid.uuid4().hex}.jpg"
    print("Downloading image with file_id:", file_id)

    file_info = requests.get(
        f"{TELEGRAM_URL}/getFile",
        params={"file_id": file_id}
    ).json()

    file_path = file_info["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

    image_bytes = requests.get(file_url).content

    with open(filename, "wb") as f:
        f.write(image_bytes)

    return filename

# ---------------- GEMINI IMAGE ANALYSIS ---------------- #

def image_to_base64(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def analyze_crop_image(image_path):
    image_base64 = image_to_base64(image_path)
    print("Image converted to base64.",image_base64[:30])  # Print first 30 chars for verification

    system_prompt = """
    You are an agricultural expert.
    Analyze the crop image and reply STRICTLY in this format:

    Crop:
    Disease:
    Confidence (0-100):
    Symptoms:
    Treatment (simple farmer-friendly steps):
    """
    try:
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {"text": system_prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": image_base64
                            }
                        }
                    ]
                }
            ]
        )

        return response.text
    except Exception as e:
        print("Error during image analysis:", str(e))
        return "Error analyzing image."
# ---------------- IMAGE HANDLER ---------------- #

def handle_crop_image(chat_id, file_id):
    image_path = None
    try:
        send_message(chat_id, "📸 Image received. Analyzing crop disease, please wait...")

        image_path = download_image(file_id)

        analysis = analyze_crop_image(image_path)
        print("Analysis Result:", analysis)

        send_message(chat_id, f"🌾 Crop Disease Analysis\n\n{analysis}")

    except Exception as e:
        send_message(
            chat_id,
            "⚠️ Unable to analyze the image.\nPlease send a clear close-up photo of the affected leaf."
        )

    finally:
        # Cleanup temp file
        if image_path and os.path.exists(image_path):
            os.remove(image_path)






if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)), debug=True)
