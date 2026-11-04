# 🚀 SketchShip AI

Upload a hand-drawn sketch or wireframe and get a working Streamlit app with a live preview.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then fill in META_API_KEY, META_API_BASE_URL, model names
streamlit run app.py
```

No API key? The app runs in offline mock mode so you can try the full flow.

## How it uses Meta's models

SketchShip AI sends the uploaded sketch to a Muse multimodal model through the Meta Model API, which returns a structured JSON description of the UI (title, inputs, buttons, tables, layout). That JSON is then passed to a Muse model that writes clean Streamlit code, which is statically validated (import allow-list, blocked calls) and rendered live in the app. All inference runs on Meta's hosted endpoints over HTTP, so no local GPU is needed.

## Security note

Generated code is validated and run with restricted builtins, but `exec()` is not a true sandbox. Use for demos only, not untrusted public deployments.

## Built during the Meta Global AI Developer Hackathon