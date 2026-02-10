from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import os
import re
from threading import Thread,Lock

import json
import requests
from dotenv import load_dotenv
from google import genai
import base64
import uuid
from gtts import gTTS
from openai import OpenAI
import logging
from services.chat_service import (
    save_message,
    get_language,
    set_language,
    build_llm_history,clear_chat_history
)
from services.language_service import detect_language, map_to_gtts_lang

from models.user import User

load_dotenv()


app = Flask(__name__)
CORS(app)

# SQLite DB config
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///./telebotdatabase.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {"check_same_thread": False}
}
logging.basicConfig(level=logging.INFO)
GENAI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GENAI_API_KEY)
OPENAI_API_KEY=os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

from database import db
db.init_app(app)

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
            model="models/gemini-2.5-flash-lite",
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
    # data = request.json
    data = request.get_json()

    # print("=== TELEGRAM JSON START ===")
    # print(json.dumps(data,ensure_ascii=False))
    # print("=== TELEGRAM JSON END ===")

    if "message" in data:
        message=data["message"]
        chat_id = data["message"]["chat"]["id"]

        if "photo" in message:
            photos = message["photo"]
            file_id = photos[-1]["file_id"]  
            user_msg=message.get("caption", "Analyze image")
            Thread(target=handle_crop_image, args=(user_msg,chat_id, file_id)).start()
            return "OK"
        elif "text" in message:
            user_msg = data["message"].get("text", "")
            Thread(target=agrichat, args=(chat_id, user_msg)).start()
            return "OK"
        elif "voice" in message:
            file_id = message["voice"]["file_id"]
            Thread(target=process_audio, args=(chat_id, file_id, "ogg")).start()
            logging.info(f"voice_file_id:{file_id}")
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
    
    # elif "inline_query" in data:
    #     inline = data["inline_query"]
    #     print("Received inline query:", inline)
    #     print("Inline query:", inline["query"])
    #     return "OK"
    else:
        return "OK"

def agrichat(chat_id,user_msg,system_prompt=None):
    if not user_msg.strip():
        answer = "please enter message."
        send_message(chat_id, answer)
    else:
        with app.app_context():
        # language command
            cmd = user_msg.strip().lower()
            if cmd == "/start":
                send_message(
                    chat_id,
                    "👋 Welcome to AgroBot!\n\n"
                    "I help farmers with crop diseases, cultivation tips, and farming advice.\n\n"
                    "Commands:\n"
                    "/help - Show help\n"
                    "/clear_history - Clear chat memory\n"
                    "/lang_hindi - Change language to hindi\n"
                    "/lang_telugu - Change language to telugu\n"
                    "/lang_tamil - Change language to tamil\n"
                    "/lang_bengali - Change language to bengali\n\n"
                    "Just send your farming question or crop image."
                )
                return
            

            if cmd == "/help":
                send_message(
                    chat_id,
                    "Help Menu\n\n"
                    "You can:\n"
                    "• Ask farming questions\n"
                    "• Send crop images\n\n"

                    "Commands:\n"
                    "/lang_english - Change language to English\n"
                    "/lang_hindi - Change language to Hindi\n"
                    "/lang_telugu - Change language to Telugu\n"
                    "/lang_tamil - Change language to Tamil\n"
                    "/lang_bengali - Change language to Bengali\n"
                    "/clear_history - Clear chat memory"
                )
                return

            # ---------------- /clear_history ----------------
            if cmd == "/clear_history":
                from services.chat_service import clear_chat_history
                ok = clear_chat_history(chat_id)
                if ok:
                    send_message(chat_id, "🧹 Chat history cleared!")
                else:
                    send_message(chat_id, "⚠️ Failed to clear history.")
                return


            if user_msg.startswith("/lang"):
                lang = user_msg.split("_")[-1]
                set_language(chat_id, lang)
                send_message(chat_id, f"Language set to {lang}")
                return
            lang = get_language(chat_id)
            history = build_llm_history(chat_id, limit=3)
            save_message(chat_id, "user", user_msg)
            send_message(chat_id, "bot is typing...")
            full_text=ask_llm(user_msg,language=lang,history=history)
            # full_text=ask_llm_gpt(user_msg,language=lang,history=history)
            # full_clean_text=clean_text_for_tts(full_text)
            # send_message(chat_id, full_clean_text)
            send_long_message(chat_id, full_text)
            save_message(chat_id, "bot", full_text)
            # audio=text_to_voice(full_clean_text[:400])
            # send_voice(chat_id,audio)
            # if audio and os.path.exists(audio):
            #     os.remove(audio)
            # return "OK"
    
def process_audio(chat_id, file_id, ext):
    try:
        with app.app_context():
            # 1. Download audio
            audio_file = download_file(file_id, ext)

            # 2. STT
            text = speech_to_text(audio_file)
            if not text.strip():
                send_message(chat_id, "⚠️ Could not understand audio.")
                return

            # 3. LLM
            answer = text
            save_message(chat_id, "user", "user sent some voice file")
            save_message(chat_id, "bot", answer)
            # full_clean_text=clean_text_for_tts(answer)
            answer=clean_llm_text(answer)
            # 4. TTS
            logging.info(f"tts started")
            tts_file = text_to_voice(answer)
            if tts_file:
                logging.info(f"tts success")
                # 5. Send audio reply
                send_voice(chat_id, tts_file)
            else:
                logging.info(f"tts fail so send text as backup instead of audio")
                send_long_message(chat_id, answer)
    except Exception as e:
        logging.error(f"Error processing audio: {str(e)}")
        send_message(chat_id, f"⚠️ An error occurred while processing audio: {str(e)}")

    finally:
        # Cleanup
        for f in [locals().get("audio_file"), locals().get("tts_file")]:
            if f and os.path.exists(f):
                os.remove(f)


def ask_llm_gpt(user_msg, system_prompt=None,language="English",history=[]):
    if not system_prompt:
        system_prompt =f"""You are a friendly agricultural assistant. Offer practical, easy-to-understand advice in bullet points,
        focusing on farming techniques, crop care, and best practices.Answer in language:{language}"""

    try:
        # models=openai_client.models.list()
        # for model in models:
        #     print(model.id)
        messages = [{"role":"system","content":system_prompt}]
        messages.extend(history)
        messages.append({"role":"user","content":user_msg})
        response = openai_client.responses.create(
            model="gpt-5-nano",
            input=messages
        )
            # input=[
            #     {"role": "system", "content": system_prompt},
            #     {"role": "user", "content": user_msg}
            # ]
        # print(response.output_text)
        return response.output_text

    except Exception as e:
        logging.error(f"no response gpt failed {str(e)}")
        return f"Sorry, no response. Error: {str(e)}"   

def ask_llm(user_msg,system_prompt=None,language="English",history=[]):
        if not system_prompt:
            system_prompt =f"""you are a helpful agricultural expert.assist farmer in friendly way.Give short, 
            clear answers unless more details are requested. Always use simple language that a farmer can easily 
            understand. If the question is about crop diseases, provide clear symptoms and simple treatment steps. 
            If the question is about farming techniques, give practical advice that can be easily implemented. 
            Avoid technical jargon and keep the tone friendly and supportive.try to understand the farmer's needs and provide 
            the most relevant information. try to give answer in bullet points if question is about steps or process. 
            Always be concise and to the point. Answer in language:{language}"""
        try:
            # models=client.models.list()
            # for model in models:
            #     print(model)
                # print(model.name)
            contents = []

            contents.append({
                "role": "user",
                "parts": [{"text": system_prompt}]
            })

            for msg in history:
                contents.append({
                    "role": "user" if msg["role"] == "user" else "model",
                    "parts": [{"text": msg["content"]}]
                })

            contents.append({
                "role": "user",
                "parts": [{"text": user_msg}]
            })
            response =client.models.generate_content(
                    model="models/gemini-2.5-flash-lite",
                    contents=contents
                )
                    # contents=[
                    #     {"role": "user", "parts": [{"text": system_prompt}]},
                    #     {"role": "user", "parts": [{"text": user_msg}]}
                    # ]

            answer = response.text
            return answer
        except Exception as e:
            logging.error(f"response from gpt due to gemini fail {str(e)}")
            answer=ask_llm_gpt(user_msg,language=language,history=history)
            # answer = f"Sorry, no response.{str(e)}"
            return answer

def summarize_llm_text(llm_text):
    system_prompt="you are a good farmer friendly summarizer.generate speech friendly summary.Always summarize in spoken friendly language.summarize content perfectly without loosing important data."
    prompt=f"please summarize this text in farmer-friendly         : {llm_text}"
    answer=ask_llm(prompt,system_prompt)
    return answer

gtts_lock = Lock()
def text_to_voice(text):
    print("text",text)
    lang = detect_language(text)
    print("lang",lang)
    gtts_lang = map_to_gtts_lang(lang)
    print("gtts lang",gtts_lang)
    filename=f"tts_{uuid.uuid4().hex}.mp3"
    try:
        with gtts_lock:
            tts=gTTS(text=text,lang=gtts_lang,slow=False)
            tts.save(filename)
        return filename
    except Exception as e:
        logging.info(f"tts fail to convert audio")
        return None





def speech_to_text(audio_path):
    system_prompt = """
    You are a friendly agricultural assistant.Give a feasible answer to the question mentioned in audio.
    Analyze the audio and answer the question present in that audio.
    Identify the user's language and respond in the SAME language
    AND in its NATIVE SCRIPT,Do NOT use romanized text.
    user can ask in below languages ,you should reply in same user language.
    Always use native writing system.
    Use simple and speakable words.
    Give short bullet-point answers.
    treat the text in audio as question and answer that question.
    Do not add headings.
    give the answer to the question mentioned in audio.
    user languge:te
    """
    try:
        with open(audio_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()

        response = client.models.generate_content(
            model="models/gemini-2.5-flash-lite",
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {"text": system_prompt},
                        {
                            "inline_data": {
                                "mime_type": "audio/ogg",
                                "data": audio_b64
                            }
                        }
                    ]
                }
            ]
        )

        return response.text.strip()

    except Exception as e:
        # print("Gemini STT failed:", e)
        logging.error(f"Error during Gemini STT failed: {str(e)}")
        return ""



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

def clean_llm_text(text):
    return re.sub(r'^[\s\*\-\•]+\s*', '', text, flags=re.MULTILINE).strip()

def clean_text_for_tts(text):

    text = text.replace("\r", " ").replace("\n", " ")

    # Remove bullets only at line start
    text = re.sub(r"^\s*[\*\-•]\s*", "", text, flags=re.MULTILINE)

    # Remove markdown bold
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)

    # Remove backticks
    text = re.sub(r"`(.*?)`", r"\1", text)

    # Replace colon with pause
    text = re.sub(r":", ". ", text)

    # Normalize ranges
    text = re.sub(r"(\d+)\s*-\s*(\d+)", r"\1 to \2", text)

    # Remove extra spaces
    text = re.sub(r"\s+", " ", text)

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

def analyze_crop_image(image_path,user_msg,language="english"):
    image_base64 = image_to_base64(image_path)
    # print("Image converted to base64.",image_base64[:30])  # Print first 30 chars for verification

    system_prompt = f"""
    You are an agricultural expert.
    Analyze the crop image and reply STRICTLY in this format:

    Crop:
    Disease:
    Confidence (0-100):
    Symptoms:
    Treatment (simple farmer-friendly steps):
    Answer in language:{language}
    """
    try:
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {"text": system_prompt},
                        {"text": user_msg},
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
        logging.error(f"Error during image analysis: {str(e)}")
        return f"Error analyzing image: {str(e)}"
# ---------------- IMAGE HANDLER ---------------- #

def handle_crop_image(user_msg,chat_id, file_id):
    image_path = None
    try:
        with app.app_context():
            send_message(chat_id, "📸 Image received. Analyzing crop disease, please wait...")

            image_path = download_image(file_id)
            lang = get_language(chat_id)

            analysis = analyze_crop_image(image_path,user_msg,language=lang)
            # print("Analysis Result:", analysis)
            send_message(chat_id, f"🌾 Crop Disease Analysis\n\n{analysis}")
            save_message(chat_id, "user", user_msg)
            save_message(chat_id, "bot", analysis)

    except Exception as e:
        logging.error(f"Error handling crop image: {str(e)}")
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
