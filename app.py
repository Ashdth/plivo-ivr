
import os
from flask import Flask, request, Response, jsonify
from dotenv import load_dotenv
import plivo
import plivo.xml

load_dotenv()

app = Flask(__name__)

# Configuration from .env
AUTH_ID = os.getenv("PLIVO_AUTH_ID", "").strip()
AUTH_TOKEN = os.getenv("PLIVO_AUTH_TOKEN", "").strip()
PLIVO_PHONE_NUMBER = os.getenv("PLIVO_PHONE_NUMBER", "").strip()
RECEIVER_PHONE_NUMBER = os.getenv("RECEIVER_PHONE_NUMBER", "").strip()
ASSOCIATE_PHONE_NUMBER = os.getenv("ASSOCIATE_PHONE_NUMBER", "").strip()
OTP = os.getenv("OTP", "1607").strip()
BASE_URL = os.getenv("BASE_URL", "").strip().rstrip("/")

# Sample audio file
AUDIO_URL = "https://s3.amazonaws.com/plivocloud/music.mp3"

# In-memory call state for local testing
CALLS = {}


def xml_response(response):
    xml = response.to_string()
    app.logger.info("Plivo XML response: %s", xml)

    return Response(
        xml,
        status=200,
        mimetype="application/xml"
    )


def say(text, language="en-US"):
    return plivo.xml.SpeakElement(text, language=language)


def get_call_state():
    call_uuid = request.values.get("CallUUID", "")

    if call_uuid not in CALLS:
        CALLS[call_uuid] = {
            "authenticated": False,
            "language": "en"
        }

    return call_uuid, CALLS[call_uuid]


def hangup_response(message, language="en-US"):
    response = plivo.xml.ResponseElement()
    response.add(say(message, language=language))
    response.add(plivo.xml.HangupElement())
    return xml_response(response)


def get_digits(action_url, count, prompt, language="en-US"):
    digits = plivo.xml.GetDigitsElement(
        action=action_url,
        method="POST",
        num_digits=count,
        timeout=10,
        retries=2
    )
    digits.add(say(prompt, language=language))
    return digits


@app.route("/", methods=["GET"])
def home():
    return "Plivo IVR is running", 200


@app.route("/call", methods=["GET", "POST"])
def make_call():
    required = {
        "PLIVO_AUTH_ID": AUTH_ID,
        "PLIVO_AUTH_TOKEN": AUTH_TOKEN,
        "PLIVO_PHONE_NUMBER": PLIVO_PHONE_NUMBER,
        "RECEIVER_PHONE_NUMBER": RECEIVER_PHONE_NUMBER,
        "BASE_URL": BASE_URL
    }

    missing = [key for key, value in required.items() if not value]

    if missing:
        return jsonify({
            "error": "Missing configuration in .env",
            "missing_variables": missing
        }), 500

    try:
        client = plivo.RestClient(AUTH_ID, AUTH_TOKEN)

        result = client.calls.create(
            from_=PLIVO_PHONE_NUMBER,
            to_=RECEIVER_PHONE_NUMBER,
            answer_url=f"{BASE_URL}/answer",
            answer_method="POST"
        )

        return jsonify({
            "message": "Call initiated",
            "call_uuid": getattr(result, "request_uuid", None)
        }), 200

    except Exception as exc:
        app.logger.exception("Plivo call request failed")
        return jsonify({"error": str(exc)}), 502


@app.route("/answer", methods=["GET", "POST"])
def answer():
    get_call_state()

    response = plivo.xml.ResponseElement()

    response.add(get_digits(
        action_url=f"{BASE_URL}/verify-otp",
        count=4,
        prompt="Welcome. Please enter your four digit OTP."
    ))

    response.add(say("We did not receive your OTP. Goodbye."))
    response.add(plivo.xml.HangupElement())

    return xml_response(response)


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    _, state = get_call_state()
    entered_otp = request.values.get("Digits", "").strip()

    response = plivo.xml.ResponseElement()

    if entered_otp != OTP:
        response.add(get_digits(
            action_url=f"{BASE_URL}/verify-otp",
            count=4,
            prompt="Incorrect OTP. Please enter your four digit OTP again."
        ))

        response.add(say("OTP entry failed. Goodbye."))
        response.add(plivo.xml.HangupElement())
        return xml_response(response)

    state["authenticated"] = True
    state["language"] = "en"

    response.add(say("OTP verified successfully."))

    response.add(get_digits(
        action_url=f"{BASE_URL}/language-selected",
        count=1,
        prompt="For English, press 1. For Spanish, press 2."
    ))

    response.add(say("No selection received. Goodbye."))
    response.add(plivo.xml.HangupElement())

    return xml_response(response)


@app.route("/language-selected", methods=["GET", "POST"])
def language_selected():
    _, state = get_call_state()

    if not state["authenticated"]:
        return hangup_response("Please verify your OTP first. Goodbye.")

    digit = request.values.get("Digits", "").strip()

    if digit == "1":
        state["language"] = "en"
        language = "en-US"
        prompt = (
            "You selected English. "
            "To listen to a message, press 1. "
            "To speak to a live associate, press 2."
        )

    elif digit == "2":
        state["language"] = "es"
        language = "es-ES"
        prompt = (
            "Ha seleccionado español. "
            "Para escuchar un mensaje, oprima 1. "
            "Para hablar con un representante, oprima 2."
        )

    else:
        return hangup_response("Invalid selection. Goodbye.")

    response = plivo.xml.ResponseElement()

    response.add(get_digits(
        action_url=f"{BASE_URL}/action-selected",
        count=1,
        prompt=prompt,
        language=language
    ))

    response.add(say(
        "No selection received. Goodbye."
        if state["language"] == "en"
        else "No se recibió ninguna selección. Adiós.",
        language=language
    ))
    response.add(plivo.xml.HangupElement())

    return xml_response(response)


@app.route("/action-selected", methods=["GET", "POST"])
def action_selected():
    _, state = get_call_state()

    if not state["authenticated"]:
        return hangup_response("Please verify your OTP first. Goodbye.")

    digit = request.values.get("Digits", "").strip()
    language = state.get("language", "en")
    voice_language = "es-ES" if language == "es" else "en-US"

    response = plivo.xml.ResponseElement()

    if digit == "1":
        # Play audio once, then speak and hang up.
        response.add(plivo.xml.PlayElement(AUDIO_URL))

        response.add(say(
            "Thank you for calling. Goodbye."
            if language == "en"
            else "Gracias por llamar. Adiós.",
            language=voice_language
        ))

        response.add(plivo.xml.HangupElement())

    elif digit == "2":
        if not ASSOCIATE_PHONE_NUMBER:
            return hangup_response(
                "The associate number is not configured. Goodbye.",
                language=voice_language
            )

        response.add(say(
            "Please wait while we connect you to a live associate."
            if language == "en"
            else "Espere mientras le conectamos con un representante.",
            language=voice_language
        ))

        dial = plivo.xml.DialElement(
            caller_id=PLIVO_PHONE_NUMBER,
            timeout=30
        )
        dial.add(plivo.xml.NumberElement(ASSOCIATE_PHONE_NUMBER))
        response.add(dial)

        response.add(say(
            "The associate is unavailable. Goodbye."
            if language == "en"
            else "El representante no está disponible. Adiós.",
            language=voice_language
        ))
        response.add(plivo.xml.HangupElement())

    else:
        response.add(say(
            "Invalid selection. Goodbye.",
            language=voice_language
        ))
        response.add(plivo.xml.HangupElement())

    return xml_response(response)


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5002,
        debug=False
    )
