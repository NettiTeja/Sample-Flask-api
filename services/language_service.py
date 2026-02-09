from langdetect import detect, DetectorFactory
DetectorFactory.seed = 0

def detect_language(text):
    try:
        return detect(text)
    except:
        return "en"

def map_to_gtts_lang(code):

    mapping = {
        "en": "en",
        "hi": "hi",
        "te": "te",
        "ta": "ta",
        "bn": "bn",
        "ur": "ur",
        "ml": "ml",
        "kn": "kn",
        "mr": "mr",
        "gu": "gu"
    }

    return mapping.get(code, "en")
