"""
Ana - Asistent Vocal Restaurant
Backend simplu pentru probe (fara Twilio, fara Supabase)
"""

import os
import json
import asyncio
import base64
import logging
from pathlib import Path

import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ana")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o-realtime-preview-2024-12-17"

ANA_SYSTEM_PROMPT = """Ești Ana, o tânără simpatică de la restaurantul "La Bunica" din România. Vorbești exact ca un om real la telefon - natural, cald, uman, cu mici pauze și expresii autentice.

CUM VORBEȘTI:
- Folosești un ton de conversație reală, nu de robot
- Faci mici pauze naturale între idei
- Folosești expresii ca: "Păi...", "Deci...", "Îhî", "A, înțeleg!", "Super!", "Minunat!"
- Uneori repeți ce a spus clientul pentru confirmare: "Deci vreți o ciorbă de burtă, am înțeles bine?"
- Ești caldă, feminina și familiară, nu formală și rigidă
- Răspunzi SCURT și NATURAL - nu liste lungi, ci conversație reală
- Folosești "voi" și "noi" ca și cum ai fi parte din echipă: "Noi avem...", "Vă pregătim..."

SALUT LA APEL:
"Alo! Restaurant La Bunica, cu Ana. Cu ce vă pot ajuta?"

NU face:
- Nu vorbi în liste robotice
- Nu spune fraze prea formale
- Nu răspunde prea lung la o întrebare simplă

MENIU DISPONIBIL:
- Ciorbe: Ciorbă de burtă (25 lei), Ciorbă de legume (20 lei), Ciorbă de perișoare (22 lei)
- Feluri principale: Sarmale cu mămăligă (35 lei), Mici cu muștar (28 lei), Tochitura moldovenească (40 lei), Friptură de pui (32 lei)
- Garnituri: Mămăligă (8 lei), Cartofi prăjiți (10 lei), Salată de varză (8 lei)
- Deserturi: Papanași (18 lei), Clătite cu gem (15 lei), Cozonac (12 lei)
- Băuturi: Apă plată/minerală (5 lei), Suc natural (12 lei), Bere (10 lei), Vin roșu/alb (15 lei)
- Lapte de pasare (60 lei)
- Laba de urs (120 lei)

SERVICII:
- Livrare la domiciliu (în oraș, raza 5 km, 10 lei livrare, GRATUIT peste 50 lei)
- Timp livrare: ~35 minute
- Timp preparare takeaway: ~20 minute
- Rezervări masă (suni pentru rezervare)
- Program: Luni-Duminică, 10:00-22:00
- Programul artistic este asigurat de artistul Popa Nicolae, ce are un repertoriu foarte bogat, si ofera seri artistice de neuitat

FLUX COMANDĂ LIVRARE:
1. Întreabă ce doresc să comande
2. Confirmă produsele și prețul total
3. Întreabă adresa de livrare (stradă, număr, bloc/scară/apartament dacă e cazul)
4. Întreabă metoda de plată (numerar sau card la livrare)
5. Confirmă comanda cu timp estimat
6. Mulțumește și urează poftă bună!

IMPORTANT:
- Dacă nu înțelegi, cere politicos să repete: "Îmi cer scuze, nu am înțeles bine. Puteți repeta?"
- Dacă nu poți ajuta cu ceva, spune: "Îmi pare rău, pentru asta trebuie să vorbești cu un coleg. Vă transfer imediat."
- Fii CONCISĂ - nu vorbi prea mult odată
- Ascultă pacient clientul înainte să răspunzi
"""

app = FastAPI(title="Ana - Asistent Vocal Restaurant")

# Servim fișierele statice (HTML frontend)
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def homepage():
    """Pagina principală - interfața de test"""
    html_path = static_dir / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/health")
async def health():
    return {"status": "ok", "ana": "gata de lucru"}


@app.websocket("/ws")
async def websocket_bridge(client_ws: WebSocket):
    """
    Bridge WebSocket: Browser/Android <-> OpenAI Realtime API
    """
    await client_ws.accept()
    log.info("Client conectat!")

    if not OPENAI_API_KEY:
        await client_ws.send_text(json.dumps({
            "type": "error",
            "message": "OPENAI_API_KEY lipsește din .env!"
        }))
        await client_ws.close()
        return

    openai_url = f"wss://api.openai.com/v1/realtime?model={OPENAI_MODEL}"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }

    try:
        async with websockets.connect(openai_url, extra_headers=headers) as openai_ws:
            log.info("Conectat la OpenAI Realtime API!")

            # Configurăm sesiunea cu personalitatea Anei
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": ANA_SYSTEM_PROMPT,
                    "voice": "coral",  # voce feminină naturală
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.3,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 1000
                    },
                    "temperature": 0.9
                }
            }
            await openai_ws.send(json.dumps(session_config))
            log.info("Sesiune configurată - Ana e pregătită!")

            # Trimitem salutul inițial
            await asyncio.sleep(0.5)
            initial_greeting = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{
                        "type": "input_text",
                        "text": "Bună ziua!"
                    }]
                }
            }
            await openai_ws.send(json.dumps(initial_greeting))
            await openai_ws.send(json.dumps({"type": "response.create"}))

            # Rulăm bridge-ul bidirectional
            async def client_to_openai():
                """Primim audio de la client și trimitem la OpenAI"""
                try:
                    async for message in client_ws.iter_text():
                        data = json.loads(message)

                        if data.get("type") == "audio":
                            # Audio PCM16 de la browser -> OpenAI
                            audio_event = {
                                "type": "input_audio_buffer.append",
                                "audio": data["audio"]
                            }
                            await openai_ws.send(json.dumps(audio_event))

                        elif data.get("type") == "commit_audio":
                            await openai_ws.send(json.dumps({
                                "type": "input_audio_buffer.commit"
                            }))

                        elif data.get("type") == "ping":
                            await client_ws.send_text(json.dumps({"type": "pong"}))

                except WebSocketDisconnect:
                    log.info("Client deconectat")

            async def openai_to_client():
                """Primim răspunsuri de la OpenAI și le trimitem la client"""
                try:
                    async for message in openai_ws:
                        event = json.loads(message)
                        event_type = event.get("type", "")

                        if event_type == "response.audio.delta":
                            # Audio de la Ana -> client
                            await client_ws.send_text(json.dumps({
                                "type": "audio",
                                "audio": event.get("delta", "")
                            }))

                        elif event_type == "response.audio_transcript.delta":
                            # Textul a ce spune Ana
                            await client_ws.send_text(json.dumps({
                                "type": "transcript_ana",
                                "text": event.get("delta", "")
                            }))

                        elif event_type == "conversation.item.input_audio_transcription.completed":
                            # Ce a spus clientul
                            await client_ws.send_text(json.dumps({
                                "type": "transcript_client",
                                "text": event.get("transcript", "")
                            }))

                        elif event_type == "session.created":
                            await client_ws.send_text(json.dumps({
                                "type": "status",
                                "message": "Ana e conectată și gata!"
                            }))

                        elif event_type == "error":
                            log.error(f"Eroare OpenAI: {event}")
                            await client_ws.send_text(json.dumps({
                                "type": "error",
                                "message": str(event.get("error", {}).get("message", "Eroare necunoscută"))
                            }))

                except Exception as e:
                    log.error(f"Eroare OpenAI stream: {e}")

            # Rulăm ambele direcții simultan
            await asyncio.gather(
                client_to_openai(),
                openai_to_client(),
                return_exceptions=True
            )

    except Exception as e:
        log.error(f"Eroare conexiune OpenAI: {e}")
        try:
            await client_ws.send_text(json.dumps({
                "type": "error",
                "message": f"Nu mă pot conecta la OpenAI: {str(e)}"
            }))
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    import socket

    # Afișăm IP-ul local pentru acces de pe telefon
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "localhost"

    print("\n" + "="*50)
    print("🍽️  ANA - Asistent Vocal Restaurant La Bunica")
    print("="*50)
    print(f"✅ Backend pornit!")
    print(f"📱 Accesează de pe telefon (același WiFi):")
    print(f"   http://{local_ip}:8000")
    print(f"💻 Sau de pe PC:")
    print(f"   http://localhost:8000")
    print("="*50 + "\n")

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
