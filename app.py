from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import os
import re
from threading import Thread

import json
import requests
from dotenv import load_dotenv
from google import genai
import base64
import uuid
from gtts import gTTS
from openai import OpenAI
load_dotenv()


app = Flask(__name__)
CORS(app)

# SQLite DB config

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///./database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
OPENAI_API_KEY=os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)
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
    if "message" in data:
        message=data["message"]
        chat_id = data["message"]["chat"]["id"]

        if "photo" in message:
            photos = message["photo"]
            file_id = photos[-1]["file_id"]  
            Thread(target=handle_crop_image, args=(chat_id, file_id)).start()
            return "OK"
        elif "text" in message:
            user_msg = data["message"].get("text", "")
            Thread(target=agrichat, args=(chat_id, user_msg)).start()
            return "OK"
        elif "voice" in message:
            file_id = message["voice"]["file_id"]
            Thread(target=process_audio, args=(chat_id, file_id, "ogg")).start()
            return "OK"

        elif "audio" in message:
            file_id = message["audio"]["file_id"]
            Thread(target=process_audio, args=(chat_id, file_id, "mp3")).start()
            return "OK"

        else:
            send_message(chat_id, "please send text or image or audio")
            return "OK"
    elif "edited_message" in data:
        chat_id = data["edited_message"]["chat"]["id"]
        send_message(chat_id, "please send new message.we are not process edited messages")
        return "OK"

def agrichat(chat_id,user_msg,system_prompt=None):
    if not user_msg:
        answer = "please enter message."
        send_message(chat_id, answer)
    else:
        send_message(chat_id, "bot is typing...")
        full_text=ask_llm(user_msg)
        # full_text=ask_llm_gpt(user_msg)
        # full_clean_text=clean_text_for_tts(full_text)
        # send_message(chat_id, full_clean_text)
        send_long_message(chat_id, full_text)
        # audio=text_to_voice(full_clean_text[:400])
        # send_voice(chat_id,audio)
        # if audio and os.path.exists(audio):
        #     os.remove(audio)
        # return "OK"
    
def process_audio(chat_id, file_id, ext):
    try:
        # 1. Download audio
        audio_file = download_file(file_id, ext)

        # 2. STT
        text = speech_to_text(audio_file)
        if not text.strip():
            send_message(chat_id, "⚠️ Could not understand audio.")
            return

        # 3. LLM
        answer = ask_llm(text)
        full_clean_text=clean_text_for_tts(answer)

        # 4. TTS
        tts_file = text_to_voice(full_clean_text)

        # 5. Send audio reply
        send_voice(chat_id, tts_file)
    except Exception as e:
        send_message(chat_id, f"⚠️ An error occurred while processing audio: {str(e)}")

    finally:
        # Cleanup
        for f in [locals().get("audio_file"), locals().get("tts_file")]:
            if f and os.path.exists(f):
                os.remove(f)


def ask_llm_gpt(user_msg, system_prompt=None):
    if not system_prompt:
        system_prompt =( "You are a friendly agricultural assistant. Offer practical, easy-to-understand advice in bullet points,"
        "focusing on farming techniques, crop care, and best practices.")

    try:
        # models=openai_client.models.list()
        # for model in models:
        #     print(model.id)
        response = openai_client.responses.create(
            model="gpt-5-nano",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ]
        )
        # print(response.output_text)
        return response.output_text

    except Exception as e:
        # print(str(e))
        return f"Sorry, no response. Error: {str(e)}"   

def ask_llm(user_msg,system_prompt=None):
        if not system_prompt:
            system_prompt ="you are a helpful agricultural expert.assist farmer in friendly way.Give short, clear answers unless more details are requested. Always use simple language that a farmer can easily understand. If the question is about crop diseases, provide clear symptoms and simple treatment steps. If the question is about farming techniques, give practical advice that can be easily implemented. Avoid technical jargon and keep the tone friendly and supportive.try to understand the farmer's needs and provide the most relevant information. try to give answer in bullet points if question is about steps or process. Always be concise and to the point."
        try:
            # models=client.models.list()
            # for model in models:
            #     print(model)
                # print(model.name)
            response =client.models.generate_content(
                    model="models/gemini-2.5-flash-lite",
                    contents=[
                        {"role": "user", "parts": [{"text": system_prompt}]},
                        {"role": "user", "parts": [{"text": user_msg}]}
                    ]
                )

            answer = response.text
            return answer
        except Exception as e:
            # print(f"response from gpt due to gemini fail {str(e)}")
            answer=ask_llm_gpt(user_msg)
            # answer = f"Sorry, no response.{str(e)}"
            return answer

def summarize_llm_text(llm_text):
    system_prompt="you are a good farmer friendly summarizer.generate speech friendly summary.Always summarize in spoken friendly language.summarize content perfectly without loosing important data."
    prompt=f"please summarize this text in farmer-friendly         : {llm_text}"
    answer=ask_llm(prompt,system_prompt)
    return answer

def text_to_voice(text):
    filename=f"tts_{uuid.uuid4().hex}.mp3"
    tts=gTTS(text=text,slow=False)
    tts.save(filename)
    return filename

def speech_to_text(audio_path):
    """
    Replace this with:
    - Vosk
    - Whisper API
    - Any STT you choose
    """
    print(f"STT processing: {audio_path}")
    return "Explain rice cultivation steps"

def send_voice(chat_id, audio_file):
    with open(audio_file, "rb") as voice_file:
        requests.post(
            f"{TELEGRAM_URL}/sendVoice",
            data={"chat_id": chat_id},
            files={"voice": voice_file}
        )

def send_long_message(chat_id, text, chunk_size=3500):
    for i in range(0, len(text), chunk_size):
        part = text[i:i + chunk_size]
        send_message(chat_id, part)


def send_message(chat_id, text):
    res=requests.post(
        f"{TELEGRAM_URL}/sendMessage",
        json={"chat_id": chat_id, "text": text}
    )
    # print("Message sent:", res.status_code, res.text)

import re

def clean_text_for_tts(text):
    # Normalize whitespace
    text = text.replace("\r", " ").replace("\n", " ")

    # Remove markdown bullets (*, -, •)
    text = re.sub(r"[\*\-•]+", " ", text)

    # Remove markdown emphasis (**bold**, __bold__)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)

    # Remove inline code/backticks
    text = re.sub(r"`(.*?)`", r"\1", text)

    # Remove extra punctuation used only for formatting
    text = re.sub(r"[:]{2,}", ".", text)

    # Replace list-style colons with pauses
    text = re.sub(r":", ". ", text)

    # Normalize ranges (2-5 → 2 to 5)
    text = re.sub(r"(\d+)\s*-\s*(\d+)", r"\1 to \2", text)

    # Remove multiple spaces
    text = re.sub(r"\s+", " ", text)

    # Clean leftover symbols
    text = re.sub(r"[^\w\s.,]", "", text)

    return text.strip()

def download_file(file_id, ext):
    filename = f"audio_{uuid.uuid4().hex}.{ext}"

    file_info = requests.get(
        f"{TELEGRAM_URL}/getFile",
        params={"file_id": file_id}
    ).json()

    path = file_info["result"]["file_path"]
    url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{path}"

    with open(filename, "wb") as f:
        f.write(requests.get(url).content)

    return filename


def download_image(file_id):
    """
    Downloads image from Telegram and saves using UUID
    """
    filename = f"crop_{uuid.uuid4().hex}.jpg"
    # print("Downloading image with file_id:", file_id)

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
    # print("Image converted to base64.",image_base64[:30])  # Print first 30 chars for verification

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
        # print("Error during image analysis:", str(e))
        return f"Error analyzing image: {str(e)}"
# ---------------- IMAGE HANDLER ---------------- #

def handle_crop_image(chat_id, file_id):
    image_path = None
    try:
        send_message(chat_id, "📸 Image received. Analyzing crop disease, please wait...")

        image_path = download_image(file_id)

        analysis = analyze_crop_image(image_path)
        # print("Analysis Result:", analysis)

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
