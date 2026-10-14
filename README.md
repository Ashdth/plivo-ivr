# Plivo IVR Demo — InspireWorks

A small Flask app that places an outbound call with the Plivo Voice API, authenticates
the caller with a 4-digit OTP, and then runs a two-level IVR menu
(language → play audio / connect to an associate).

## Call flow

```
/call  ──Plivo dials you──▶  /answer   "Enter your 4-digit OTP"
                                 │
                                 ▼
                           /verify-otp ──wrong──▶ re-prompt (loops until correct)
                                 │ correct
                                 ▼
                             /language  "1 English / 2 Spanish"  (invalid → repeat)
                                 │
                                 ▼
                         /language-selected ──▶ action menu in chosen language
                                 │
                                 ▼
                          /action-selected   1 → <Play> MP3 then hang up
                                             2 → <Dial> associate number
                                             other → repeat action menu
```

Every step is a separate Plivo webhook. No state is stored on the server: each
response's XML tells Plivo which URL to call next, and the chosen language is
carried in the URL (`?lang=en`). The IVR routes are only ever reached via the
`<Redirect>` that `/verify-otp` returns after a correct OTP, so there is no way
into the menu without authenticating.

## Setup

```bash
git clone <repo> && cd plivo-ivr
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

| Variable | Value |
|---|---|
| `PLIVO_AUTH_ID` / `PLIVO_AUTH_TOKEN` | From the Plivo console (or the assignment email) |
| `PLIVO_PHONE_NUMBER` | Your Plivo number, e.g. `+9180XXXXXXXX` |
| `RECEIVER_PHONE_NUMBER` | Your own mobile, e.g. `+91XXXXXXXXXX` |
| `ASSOCIATE_PHONE_NUMBER` | Associate / placeholder number, e.g. `+9122XXXXXXXX` |
| `OTP` | Your birthdate as DDMM, e.g. `1503` |
| `BASE_URL` | Your public ngrok URL (set after step 2 below) |

Never commit `.env` — it is in `.gitignore`.

## Run

1. Start Flask:
   ```bash
   python app.py
   ```
2. In a second terminal, expose it:
   ```bash
   ngrok http 5000
   ```
   Copy the `https://....ngrok-free.app` URL into `BASE_URL` in `.env` and restart Flask.
3. Trigger the call — open in a browser (or `curl`):
   ```
   http://localhost:5000/call
   http://localhost:5000/call?to=+91XXXXXXXXXX   # override the destination
   ```
   You get back `Call started to ... Request UUID: ...` or a Plivo error message.

## Test checklist (for the demo video)

1. Answer the call → hear "Welcome to Inspire Works, enter your four digit OTP".
2. Enter a **wrong** OTP → "Incorrect OTP, please try again".
3. Enter the **correct** OTP → "Authentication successful" → language menu.
4. Press 1 (English) or 2 (Spanish) → action menu in that language. Press 9 → menu repeats.
5. Press 1 → short audio plays, call ends. Press 2 → call is forwarded to the associate number.

## Notes

- `OTP` is read as a string so a birthdate like `0203` keeps its leading zero.
- Audio uses Plivo's public sample MP3 (`https://s3.amazonaws.com/plivocloud/music.mp3`);
  change `AUDIO_URL` in `app.py` to any public MP3.
- Plivo XML elements used: `<GetDigits>`, `<Speak>`, `<Play>`, `<Dial>`/`<Number>`,
  `<Redirect>`, `<Hangup>`.
