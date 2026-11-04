"""SketchShip AI - napkin sketch -> live Streamlit app."""
import ast
import builtins
import io
import re
import traceback

import streamlit as st
from PIL import Image, ImageDraw

from backend.generator import analyze_sketch, generate_streamlit_code, has_api_key

st.set_page_config(page_title="SketchShip AI", page_icon="🚀", layout="wide")

st.markdown(
    """
    <style>
    .hero {padding: 1.2rem 1.5rem; border-radius: 14px;
           background: linear-gradient(135deg,#0866ff 0%,#7b3fe4 100%); color:#fff; margin-bottom:1rem;}
    .hero h1 {margin:0; font-size:2rem; color:#fff;}
    .hero p {margin:.2rem 0 0; opacity:.9;}
    div.stButton > button[kind="primary"] {width:100%; font-weight:700; border-radius:10px;}
    </style>
    <div class="hero"><h1>🚀 SketchShip AI</h1>
    <p>Draw it on a napkin. Ship it as a running Streamlit app.</p></div>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Safe-ish execution of generated code
# --------------------------------------------------------------------------- #
ALLOWED_IMPORTS = {"streamlit", "pandas", "numpy", "math", "random", "datetime", "time", "json"}
BLOCKED_CALLS = {"eval", "exec", "compile", "open", "__import__", "input", "globals", "locals",
                 "getattr", "setattr", "delattr", "vars", "breakpoint"}


def validate_code(code: str) -> None:
    """Static check. Raises ValueError for anything suspicious."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORTS:
                    raise ValueError(f"Import not allowed: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                raise ValueError(f"Import not allowed: {node.module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in BLOCKED_CALLS:
                raise ValueError(f"Call not allowed: {node.func.id}()")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError(f"Dunder attribute not allowed: {node.attr}")


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name.split(".")[0] not in ALLOWED_IMPORTS:
        raise ImportError(f"Import blocked: {name}")
    return builtins.__import__(name, globals, locals, fromlist, level)


def run_generated_code(code: str) -> None:
    """Validate, then exec in a restricted namespace. Not a true sandbox: for demos only."""
    code = re.sub(r"^\s*st\.set_page_config\(.*?\)\s*$", "", code, flags=re.MULTILINE | re.DOTALL)
    validate_code(code)
    safe_builtins = {k: getattr(builtins, k) for k in dir(builtins)
                     if k not in BLOCKED_CALLS and not k.startswith("_")}
    safe_builtins["__import__"] = _safe_import
    exec(compile(code, "<generated>", "exec"), {"__builtins__": safe_builtins, "st": st, "__name__": "generated"})


# --------------------------------------------------------------------------- #
# Sample sketch
# --------------------------------------------------------------------------- #
def make_sample_sketch() -> bytes:
    img = Image.new("RGB", (800, 560), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 780, 540], outline="black", width=4)
    d.text((40, 40), "EXPENSE TRACKER", fill="black")
    d.rectangle([40, 90, 380, 130], outline="black", width=3); d.text((50, 102), "Description", fill="black")
    d.rectangle([40, 150, 380, 190], outline="black", width=3); d.text((50, 162), "Amount", fill="black")
    d.rectangle([40, 210, 380, 250], outline="black", width=3); d.text((50, 222), "Category [v]", fill="black")
    d.rounded_rectangle([40, 280, 220, 330], radius=10, outline="black", width=3); d.text((70, 298), "ADD", fill="black")
    d.rectangle([420, 90, 760, 300], outline="black", width=3); d.text((430, 100), "TABLE: recent expenses", fill="black")
    d.rectangle([420, 330, 760, 520], outline="black", width=3); d.text((430, 340), "BAR CHART", fill="black")
    for i, h in enumerate([60, 110, 40, 90]):
        d.rectangle([450 + i * 70, 510 - h, 490 + i * 70, 510], outline="black", width=3)
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
for key in ("image_bytes", "layout", "code"):
    st.session_state.setdefault(key, None)

left, right = st.columns([1, 1.2], gap="large")

with left:
    st.subheader("1 · Your sketch")
    if not has_api_key():
        st.warning("No `META_API_KEY` found: running in **offline mock mode**.")

    uploaded = st.file_uploader("Upload a wireframe or napkin sketch", type=["png", "jpg", "jpeg"])
    if uploaded is not None:
        st.session_state.image_bytes = uploaded.getvalue()

    if st.button("🎨 Load sample sketch"):
        st.session_state.image_bytes = make_sample_sketch()

    if st.session_state.image_bytes:
        st.image(st.session_state.image_bytes, caption="Input sketch", use_container_width=True)

    ship = st.button("🚀 Ship Code", type="primary", disabled=not st.session_state.image_bytes)

    if ship:
        try:
            with st.spinner("Reading your sketch with Meta Muse..."):
                st.session_state.layout = analyze_sketch(st.session_state.image_bytes)
            with st.spinner("Writing Streamlit code..."):
                st.session_state.code = generate_streamlit_code(st.session_state.layout)
            st.success("Shipped! Check the preview →")
        except Exception as exc:  # noqa: BLE001
            st.session_state.code = None
            st.error(f"Something went wrong: {exc}")

    if st.session_state.layout:
        with st.expander("Detected layout (JSON)"):
            st.json(st.session_state.layout)

with right:
    st.subheader("2 · Result")
    tab_preview, tab_code = st.tabs(["Live Preview", "Generated Python Code"])

    with tab_preview:
        if st.session_state.code:
            with st.container(border=True):
                try:
                    run_generated_code(st.session_state.code)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Preview failed: {exc}")
                    with st.expander("Traceback"):
                        st.code(traceback.format_exc())
        else:
            st.info("Upload a sketch and press **Ship Code** to see your app here.")

    with tab_code:
        if st.session_state.code:
            st.code(st.session_state.code, language="python")  # built-in copy icon, top right
            st.download_button("⬇️ Download app.py", st.session_state.code, file_name="generated_app.py")
        else:
            st.info("Generated code will appear here.")