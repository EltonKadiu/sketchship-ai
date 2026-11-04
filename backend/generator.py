"""Backend helpers: sketch -> JSON layout -> Streamlit code."""
from __future__ import annotations

import base64
import io
import json
import os
import re

import requests
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

REQUEST_TIMEOUT = 120

LAYOUT_SYSTEM_PROMPT = """You are a UI analyst. Look at the hand-drawn sketch or wireframe and
describe it as JSON ONLY (no prose, no markdown fences) with this schema:
{
  "title": str,
  "layout": "single_column" | "two_columns" | "sidebar_main",
  "components": [
    {"type": "header|text|text_input|number_input|textarea|selectbox|slider|checkbox|button|image|table|chart|divider",
     "label": str,
     "options": [str],            // for selectbox only
     "region": "main|left|right|sidebar"}
  ]
}
Keep components in top-to-bottom visual order."""

CODE_SYSTEM_PROMPT = """You are an expert Streamlit developer. Convert the given JSON UI layout
into a single self-contained Streamlit script.
Rules:
- Only import streamlit (as st), and optionally pandas, numpy, math, random, datetime, time, json.
- Do NOT call st.set_page_config. No file, network, or OS access.
- Make buttons do something visible (e.g. show a result with st.success / st.write).
- Use mock data where data is needed.
- Return ONLY the code inside one ```python fenced block."""


def _api_key() -> str:
    return os.getenv("META_API_KEY", "").strip()


def has_api_key() -> bool:
    return bool(_api_key())


def _chat(model: str, messages: list[dict], temperature: float = 0.2) -> str:
    """Call the Meta Model API (assumed OpenAI-style chat completions; adjust if docs differ)."""
    base = os.getenv("META_API_BASE_URL", "").rstrip("/")
    if not base or "REPLACE_WITH" in base:
        raise RuntimeError("META_API_BASE_URL is not configured in .env")
    resp = requests.post(
        f"{base}/chat/completions",
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
        },
        json={"model": model, "messages": messages, "temperature": temperature},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Meta API error {resp.status_code}: {resp.text[:300]}")
    try:
        return resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as exc:
        raise RuntimeError(f"Unexpected API response format: {resp.text[:300]}") from exc


def _prepare_image(image_bytes: bytes, max_side: int = 1280) -> str:
    """Resize + convert to PNG and return a base64 data URI."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _extract_json(text: str) -> dict:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Model did not return JSON.")
    return json.loads(text[start : end + 1])


# --------------------------------------------------------------------------- #
# Mock mode (no API key)
# --------------------------------------------------------------------------- #
MOCK_LAYOUT = {
    "title": "Expense Tracker",
    "layout": "two_columns",
    "components": [
        {"type": "header", "label": "Expense Tracker", "region": "main"},
        {"type": "text_input", "label": "Description", "region": "left"},
        {"type": "number_input", "label": "Amount", "region": "left"},
        {"type": "selectbox", "label": "Category",
         "options": ["Food", "Travel", "Bills", "Fun"], "region": "left"},
        {"type": "button", "label": "Add expense", "region": "left"},
        {"type": "table", "label": "Recent expenses", "region": "right"},
        {"type": "chart", "label": "Spending by category", "region": "right"},
    ],
}


def _mock_layout() -> dict:
    return json.loads(json.dumps(MOCK_LAYOUT))


def _layout_to_code(layout: dict) -> str:
    """Deterministic offline JSON -> Streamlit converter (fallback)."""
    lines = ["import streamlit as st", "import pandas as pd", "import numpy as np", ""]
    lines.append(f"st.title({layout.get('title', 'App')!r})")
    comps = layout.get("components", [])
    two_cols = layout.get("layout") == "two_columns"
    if two_cols:
        lines.append("left, right = st.columns(2)")

    def target(region: str) -> str:
        if two_cols:
            return "right" if region == "right" else "left"
        if region == "sidebar" or layout.get("layout") == "sidebar_main" and region == "left":
            return "st.sidebar"
        return "st"

    for i, c in enumerate(comps):
        t, label = c.get("type", "text"), c.get("label", "")
        tgt = target(c.get("region", "main"))
        if t == "header" and label == layout.get("title"):
            continue
        pre = f"{tgt}." if tgt != "st" else "st."
        if tgt in ("left", "right"):
            pre = f"{tgt}."
        key = f"k{i}"
        if t == "header":
            lines.append(f"{pre}header({label!r})")
        elif t == "text":
            lines.append(f"{pre}write({label!r})")
        elif t == "text_input":
            lines.append(f"{pre}text_input({label!r}, key={key!r})")
        elif t == "number_input":
            lines.append(f"{pre}number_input({label!r}, min_value=0.0, key={key!r})")
        elif t == "textarea":
            lines.append(f"{pre}text_area({label!r}, key={key!r})")
        elif t == "selectbox":
            lines.append(f"{pre}selectbox({label!r}, {c.get('options') or ['A', 'B']!r}, key={key!r})")
        elif t == "slider":
            lines.append(f"{pre}slider({label!r}, 0, 100, 50, key={key!r})")
        elif t == "checkbox":
            lines.append(f"{pre}checkbox({label!r}, key={key!r})")
        elif t == "button":
            lines.append(f"if {pre}button({label!r}, key={key!r}):")
            lines.append(f"    {pre}success('{label} clicked!')")
        elif t == "table":
            lines.append(f"{pre}subheader({label!r})")
            lines.append(f"{pre}dataframe(pd.DataFrame({{'Item': ['Coffee', 'Taxi', 'Rent'], 'Amount': [4.5, 18.0, 900.0]}}))")
        elif t == "chart":
            lines.append(f"{pre}subheader({label!r})")
            lines.append(f"{pre}bar_chart(pd.DataFrame({{'Food': [30], 'Travel': [45], 'Bills': [120]}}))")
        elif t == "divider":
            lines.append(f"{pre}divider()")
        elif t == "image":
            lines.append(f"{pre}info('Image placeholder: {label}')")
        else:
            lines.append(f"{pre}write({label!r})")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def analyze_sketch(image_bytes: bytes) -> dict:
    """Image bytes -> structured UI layout dict. Falls back to a mock if no API key."""
    if not has_api_key():
        return _mock_layout()

    data_uri = _prepare_image(image_bytes)
    messages = [
        {"role": "system", "content": LAYOUT_SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": "Describe this UI sketch as JSON."},
            {"type": "image_url", "image_url": {"url": data_uri}},
        ]},
    ]
    raw = _chat(os.getenv("META_VISION_MODEL", "muse-spark"), messages)
    layout = _extract_json(raw)
    layout.setdefault("title", "Untitled App")
    layout.setdefault("components", [])
    return layout


def generate_streamlit_code(layout_json: dict) -> str:
    """UI layout dict -> Streamlit source code (no fences). Offline fallback without API key."""
    if not has_api_key():
        return _layout_to_code(layout_json)

    messages = [
        {"role": "system", "content": CODE_SYSTEM_PROMPT},
        {"role": "user", "content": "Layout JSON:\n" + json.dumps(layout_json, indent=2)},
    ]
    raw = _chat(os.getenv("META_CODE_MODEL", "muse-spark"), messages)
    match = re.search(r"```(?:python)?\s*(.*?)```", raw, re.DOTALL)
    code = (match.group(1) if match else raw).strip()
    if not code:
        raise RuntimeError("Model returned empty code.")
    return code + "\n"