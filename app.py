import os
import time
import hashlib
import json
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import sounddevice as sd
import speech_recognition as sr
from flask import Flask, Response, request, send_from_directory

app = Flask(__name__)

DURATION = 10
SAMPLE_RATE = 22050

BACKGROUND_EXECUTOR = ThreadPoolExecutor(
    max_workers=3,
    thread_name_prefix="cyber-shield-bg"
)

ENGLISH_PHRASES = {
    "password": 25, "passcode": 25, "verification code": 20,
    "bank": 15, "transfer": 15, "otp": 25, "link": 15
}

ARABIC_PHRASES = {
    "كلمه السر": 25, "كلمه المرور": 25, "رمز التحقق": 20,
    "البنك": 15, "تحويل": 15, "رابط": 15
}

def normalize_text(text):
    text = text.lower()
    text = text.replace("ة", "ه")
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace(".", " ").replace(",", " ").replace("!", " ").replace("?", " ")
    return " ".join(text.split())

def hash_phone_number(phone_number):
    clean_number = phone_number.strip().encode('utf-8')
    return hashlib.sha256(clean_number).hexdigest()

KNOWN_SCAM_HASHES = {hashlib.sha256("+966500000000".encode()).hexdigest()}

@lru_cache(maxsize=128)
def cached_number_lookup(hashed_phone):
    time.sleep(0.5)
    if hashed_phone in KNOWN_SCAM_HASHES:
        return "⚠️ flagged as Known Scam Number"
    return "✅ Clean / Safe Number"

# قراءة صفحة الويب من نفس المجلد
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/run-scan')
def run_scan():
    lang_code = request.args.get('lang', 'en-US')
    phone = request.args.get('phone', '+966500000000')
    phrases_dict = ARABIC_PHRASES if lang_code == 'ar-SA' else ENGLISH_PHRASES

    def generate_events():
        yield f"data: {json.dumps({'message': '🎙️ تم البدء: جاري تشفير رقم المتصل وفحصه في الخلفية...', 'status': 'running'})}\n\n"
        
        hashed_caller = hash_phone_number(phone)
        future_caller_check = BACKGROUND_EXECUTOR.submit(cached_number_lookup, hashed_caller)
        
        yield f"data: {json.dumps({'message': f'🔒 تم التشفير (SHA-256): {hashed_caller[:12]}...', 'status': 'running'})}\n\n"
        yield f"data: {json.dumps({'message': f'🎙️ بدأ التسجيل الصوتي لمدة {DURATION} ثوانٍ...', 'status': 'running'})}\n\n"
        
        try:
            audio = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
            sd.wait()
            audio = audio.flatten()
            yield f"data: {json.dumps({'message': '✅ اكتمل التسجيل الصوتي بنجاح.', 'status': 'running'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'message': f'❌ فشل التسجيل: {str(e)}', 'error': True, 'status': 'error'})}\n\n"
            return

        yield f"data: {json.dumps({'message': '🗣️ جاري تحليل وتحويل الصوت إلى نص عبر جوجل...', 'status': 'running'})}\n\n"
        try:
            audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
            recognizer = sr.Recognizer()
            audio_data = sr.AudioData(audio_int16.tobytes(), SAMPLE_RATE, 2)
            text = recognizer.recognize_google(audio_data, language=lang_code)
            text = normalize_text(text)
            yield f"data: {json.dumps({'message': f'📝 النص المكتشف: &quot;{text}&quot;', 'status': 'running'})}\n\n"
        except Exception:
            text = ""
            yield f"data: {json.dumps({'message': '⚠️ لم يتم التعرف على كلام واضح.', 'status': 'running'})}\n\n"

        score = 0
        found = []
        for phrase, points in phrases_dict.items():
            if phrase in text:
                score += points
                found.append((phrase, points))
        score = min(score, 100)

        caller_status = future_caller_check.result()

        yield f"data: {json.dumps({'message': f'🚨 نسبة الخطر: {score}/100 | حالة الرقم: {caller_status}', 'status': 'finished'})}\n\n"

    return Response(generate_events(), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True, port=5000) 