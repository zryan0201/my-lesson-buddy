"""Local, review-first interface for the worksheet-to-video prototype.

Run with ``streamlit run streamlit_app.py`` beside the separate Flask API.
Only the Read and Make buttons cause work; ordinary UI reruns never do.
"""
from __future__ import annotations

import copy
import html
from pathlib import Path
import uuid

import streamlit as st

from lesson_video.characters import render_character_image, validate_character
from lesson_video.web_client import LessonApiClient, LessonApiError


PROJECT = Path(__file__).resolve().parent
EXAMPLE = PROJECT / "examples" / "worksheets" / "user_popsicle_addition.png"
ACTIVE_STATUSES = {"queued_read", "reading", "queued", "rendering"}
STATUS_LABELS = {
    "queued_read": ("Your picture is in line", "We will read the worksheet next.", 0.12),
    "reading": ("Looking closely at your picture", "Your friend is finding the question and counting the objects.", 0.28),
    "awaiting_review": ("A quick check together", "Ask a grown-up to check that we read the worksheet correctly.", 0.5),
    "queued": ("Getting your lesson ready", "Your checked question is ready for its story.", 0.65),
    "rendering": ("Making your cartoon lesson", "Adding your friend, the explanation, and the voice. This can take a few minutes.", 0.8),
    "completed": ("Your lesson is ready!", "Watch, count along, and discover the answer.", 1.0),
    "failed": ("Let's try another picture", "We could not finish this lesson.", 0.0),
}


def _style():
    st.markdown("""
    <style>
    .stApp {background:#FFFDF7; color:#233044;}
    .block-container {max-width:1240px; padding-top:4rem; padding-bottom:3rem;}
    h1,h2,h3 {color:#233044; letter-spacing:-.035em;}
    h1 {font-size:2.9rem!important; line-height:1.08!important; max-width:760px;}
    h2 {font-size:1.45rem!important; letter-spacing:-.02em;}
    h3 {font-size:1.15rem!important;}
    [data-testid="stVerticalBlockBorderWrapper"] > div {background:#fff; border-radius:22px;}
    [data-testid="stVerticalBlockBorderWrapper"] {border-radius:22px;}
    .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
      border-radius:12px; min-height:3rem; font-weight:700;}
    .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
      background:#236C63; border-color:#236C63; color:white;}
    .stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {
      background:#18544D; border-color:#18544D; color:white;}
    [data-baseweb="select"] > div {border-radius:10px;}
    [data-testid="stTextInput"] input {border-radius:10px;}
    [data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] p,
    [data-testid="stRadio"] label, [data-testid="stRadio"] label p,
    [data-testid="stCheckbox"] label, [data-testid="stCheckbox"] label p {
      color:#233044!important;}
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {color:#637080!important;}
    [data-testid="stMetric"] {background:#F4F7F8; padding:1rem 1.2rem; border-radius:15px;}
    .eyebrow {font-size:.78rem; letter-spacing:.17em; font-weight:800; color:#236C63; margin-bottom:.7rem;}
    .hero-subtitle {font-size:1.08rem; color:#637080; max-width:700px; line-height:1.65; margin-bottom:1.35rem;}
    .journey {display:flex; flex-wrap:wrap; gap:8px; margin:0 0 1.65rem;}
    .journey span {background:#F2EEDC; padding:7px 13px; border-radius:30px; font-size:.85rem; color:#536052;}
    .character-label {text-align:center; font-size:1.15rem; font-weight:800; margin-top:0; color:#236C63;}
    .review-question {background:#FFF3C4; border-radius:16px; padding:18px 22px;
      margin:12px 0; font-size:1.4rem; font-weight:750; color:#343A33;}
    .footer-note {font-size:.82rem; color:#7D858C; margin-top:1.5rem; text-align:center;}
    @media(max-width:640px) {h1 {font-size:2rem!important;} .block-container {padding-top:3.5rem;}}
    </style>
    """, unsafe_allow_html=True)


def _initialize():
    defaults = {"lesson_job": None, "pending_submission": None, "last_job": None,
                "read_error": None, "generation_requested": False,
                "lesson_assets": {}, "lesson_epoch": 0}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _apply_character_link():
    """A studio link selects a preview; it never submits a worksheet or video."""
    requested = st.query_params.get('character')
    if not requested:
        return
    try:
        from character_studio.assets import get_character
        metadata = get_character(requested)
        st.session_state.friend_kind = 'studio'
        st.session_state.studio_character_id = metadata['id']
        st.session_state.studio_handoff_notice = ('ready', metadata['name'])
    except (ImportError, OSError, ValueError):
        st.session_state.studio_handoff_notice = ('missing', '')
    # IDs are public artwork selections, never lesson access capabilities. A
    # consumed link must not keep resetting later choices on ordinary reruns.
    del st.query_params['character']


def _show_api_error(error: LessonApiError):
    st.error(str(error))
    if error.code == "offline":
        # Troubleshooting is for the adult running the prototype, outside the
        # child-facing workflow and only shown when a connection actually fails.
        with st.expander("For the adult: start the lesson service"):
            st.write("In VS Code, open a second terminal in the project folder, activate the same environment, and run:")
            st.code("python -m lesson_video.web_api", language="sh")
            st.write("Keep both terminals open, then try again here.")


def _character_creator() -> dict:
    st.subheader("1 · Make your character")
    st.caption("Pick a friend, or bring one you made in Character Studio.")
    preview, controls = st.columns([0.9, 1.15], gap="medium")
    config = None
    studio_artwork = None
    with controls:
        kind = st.selectbox("Choose a friend", ["robot", "fox", "bear", "studio"],
                            format_func=lambda value: "Studio library" if value == "studio" else value.title(),
                            key="friend_kind")
        if kind == "studio":
            st.link_button("Open Character Studio ↗", "http://127.0.0.1:8601", width="stretch")
            st.caption("Draw, tidy, or build a character there, then save it to your library.")
            with st.expander("For the adult: open the studio"):
                st.caption("If the studio link does not open, run this in another VS Code terminal with the same environment:")
                st.code("python -m character_studio", language="sh")
            st.button("Refresh my character library", key="refresh_studio_library", width="stretch")
            try:
                from character_studio.assets import get_character, list_characters, load_character_image
                saved = list_characters()
                if saved:
                    by_id = {item['id']: item for item in saved}
                    chosen = st.selectbox("Your saved characters", list(by_id),
                                          format_func=lambda key: by_id[key]['name'], key="studio_character_id")
                    metadata = get_character(chosen)
                    config = validate_character({"kind": "studio", "asset_id": chosen, "name": metadata['name']})
                    studio_artwork = load_character_image(chosen)
                    st.session_state.character_valid = True
                    st.caption("Your saved character is ready to join the lesson. Built characters can wave, speak, and celebrate; drawings move as stickers.")
                else:
                    st.info("Your library is ready for its first character. Save a character in the studio, then refresh here.")
            except (ImportError, OSError, ValueError):
                st.warning("We could not open your character library. Refresh after saving your character in the studio.")
            if config is None:
                st.session_state.character_valid = False
                config = validate_character({})
        else:
            name = st.text_input("Your friend's name", value="Buddy", max_chars=24, key="friend_name",
                                 help="Use letters, numbers, spaces, apostrophes, or hyphens.")
            color = st.color_picker("Character color", value="#65B9D8", key="friend_color")
            outfit = st.selectbox("Clothes", ["overalls", "shirt", "none"],
                                  format_func=lambda x: "No clothes" if x == "none" else x.title(), key="friend_outfit")
            outfit_color = st.color_picker("Clothes color", value="#7966CB", key="friend_outfit_color")
            accessory = st.selectbox("An extra touch", ["none", "cap", "glasses", "bow"],
                                     format_func=lambda x: "Just me" if x == "none" else x.title(), key="friend_accessory")
            choices = {"kind": kind, "name": name.strip() or "Buddy", "color": color,
                       "outfit": outfit, "outfit_color": outfit_color, "accessory": accessory}
            try:
                config = validate_character(choices)
                st.session_state.character_valid = True
            except ValueError:
                st.warning("Give your friend a name using letters, numbers, spaces, apostrophes, or hyphens.")
                config = validate_character({**choices, "name": "Buddy"})
                st.session_state.character_valid = False
    with preview:
        if kind == "studio" and studio_artwork is None:
            st.markdown("### Your creation goes here")
            st.caption("Make a character in the studio to star in your next lesson.")
        else:
            st.image(render_character_image(config, width=300, height=400), width="stretch")
            st.markdown(f'<p class="character-label">{html.escape(config["name"])}</p>', unsafe_allow_html=True)
            st.caption("Your very own learning buddy")
    job = st.session_state.lesson_job
    if job and config != job["character"]:
        st.caption("These character changes are ready for your next lesson. Your current lesson keeps the friend you chose when you started.")
    return config


def _picture_picker() -> tuple[bytes, str, str] | None:
    st.subheader("2 · Bring a worksheet")
    st.caption("One clear question at a time. Keep every object and symbol in the picture.")
    source = st.radio("Choose a picture", ["Try an example", "Upload a picture", "Take a photo"],
                      horizontal=True, label_visibility="collapsed", key="picture_source")
    selected = None
    if source == "Try an example":
        st.write("**Popsicle math** · Let's put two groups together.")
        if EXAMPLE.is_file():
            selected = (EXAMPLE.read_bytes(), EXAMPLE.name, "image/png")
        else:
            st.info("Upload your own worksheet picture to begin.")
    elif source == "Upload a picture":
        uploaded = st.file_uploader("Choose a worksheet photo", type=["png", "jpg", "jpeg"], max_upload_size=10,
                                    key=f"worksheet_upload_{st.session_state.lesson_epoch}")
        if uploaded is not None:
            selected = (uploaded.getvalue(), uploaded.name, uploaded.type or "image/png")
    else:
        picture = st.camera_input("Take a clear photo of one question", key=f"worksheet_camera_{st.session_state.lesson_epoch}")
        if picture is not None:
            selected = (picture.getvalue(), picture.name, picture.type or "image/jpeg")
    if selected:
        if len(selected[0]) >= 10 * 1024 * 1024:
            st.error("That picture is too large. Please choose a PNG or JPEG smaller than 10 MB.")
            return None
        try:
            st.image(selected[0], caption="The worksheet we'll read", width="stretch")
        except Exception:
            st.error("We could not open this picture. Please choose another one.")
            return None
    else:
        st.info("Choose a picture above, then your friend can read it.")
    st.caption("For this first version: addition, subtraction, counting, and simple shapes, with quantities through 10.")
    return selected


def _submit_picture(client: LessonApiClient, config: dict, picture):
    """Freeze bytes and character once. Network retries reuse that same nonce."""
    pending = st.session_state.pending_submission
    if pending is None:
        if picture is None:
            return
        pending = {"image": picture[0], "filename": picture[1], "content_type": picture[2],
                   "character": copy.deepcopy(config), "client_request_id": uuid.uuid4().hex}
        st.session_state.pending_submission = pending
    try:
        result = client.create_job(**pending)
        if not result.get("job_id") or not result.get("access_token"):
            raise LessonApiError("The lesson service did not return a lesson. Please try again.", code="invalid_response")
        st.session_state.lesson_job = {"job_id": result["job_id"], "access_token": result["access_token"],
                                      "character": pending["character"], "picture": pending["image"]}
        st.session_state.last_job = result
        st.session_state.pending_submission = None
        st.session_state.read_error = None
    except LessonApiError as error:
        st.session_state.read_error = error


def _clear_lesson():
    st.session_state.lesson_job = None
    st.session_state.last_job = None
    st.session_state.pending_submission = None
    st.session_state.read_error = None
    st.session_state.generation_requested = False
    st.session_state.lesson_assets = {}
    st.session_state.lesson_epoch += 1


def _asset(client: LessonApiClient, asset: str) -> bytes:
    job = st.session_state.lesson_job
    cache = st.session_state.lesson_assets
    cache_key = (job["job_id"], asset)
    if cache_key not in cache:
        cache[cache_key] = client.get_asset(job["job_id"], job["access_token"], asset)
    return cache[cache_key]


def _narration(review: dict) -> list[str]:
    narration = review.get("narration")
    if isinstance(narration, list):
        return [item for item in narration if isinstance(item, str)]
    if isinstance(narration, str):
        return [line for line in narration.splitlines() if line]
    return [step["text"] for step in review.get("steps", []) if isinstance(step, dict) and isinstance(step.get("text"), str)]


def _show_review(client: LessonApiClient, data: dict):
    review = data.get("review") or {}
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.markdown("**Your worksheet**")
        st.image(st.session_state.lesson_job["picture"], width="stretch")
        question = str(review.get("question", "Please check the question in your picture."))
        st.markdown(f'<div class="review-question">{html.escape(question)}</div>', unsafe_allow_html=True)
        st.write("**The calculated answer:**", str(review.get("answer", "—")))
        for warning in review.get("warnings", []):
            if isinstance(warning, str):
                st.warning(warning)
    with right:
        st.markdown("**What your friend will explain**")
        with st.expander("Read the lesson script", expanded=False):
            for text in _narration(review):
                st.write(text)
    with st.form(f"confirm_lesson_{st.session_state.lesson_job['job_id']}"):
        confirmed = st.checkbox("I am the teacher or grown-up. I checked the picture, the question, the counted groups, and the answer.",
                                key=f"review_confirmed_{st.session_state.lesson_job['job_id']}")
        st.caption("If the reading is wrong, start a new lesson with a clearer picture. The model can make mistakes.")
        submitted = st.form_submit_button("Make my video →", type="primary", width="stretch",
                                          disabled=st.session_state.generation_requested)
    if submitted:
        if not confirmed:
            st.warning("A grown-up needs to check the worksheet and tick the box before we make the video.")
        else:
            job = st.session_state.lesson_job
            try:
                result = client.generate(job["job_id"], job["access_token"])
                st.session_state.last_job = result
                st.session_state.generation_requested = True
                st.rerun()
            except LessonApiError as error:
                # The server makes confirmation idempotent. If this response
                # timed out, the next status poll shows whether it was accepted.
                _show_api_error(error)


def _lesson_panel(client: LessonApiClient):
    job = st.session_state.lesson_job
    if not job:
        return
    try:
        old_status = (st.session_state.last_job or {}).get("status")
        data = client.get_job(job["job_id"], job["access_token"])
        st.session_state.last_job = data
    except LessonApiError as error:
        _show_api_error(error)
        st.button("Refresh lesson status", key="refresh_disconnected")
        return
    status = data.get("status", "reading")
    if old_status in ACTIVE_STATUSES and status not in ACTIVE_STATUSES:
        # Rebuild once at a stage boundary so polling stops during teacher
        # review and after completion, rather than resetting a form every 2s.
        st.rerun()
    if status in {"queued", "rendering", "completed"}:
        st.session_state.generation_requested = True
    title, detail, progress = STATUS_LABELS.get(status, ("Checking your lesson", "Please refresh in a moment.", 0.2))
    st.subheader("3 · " + title)
    st.caption(detail)
    if status != "failed":
        st.progress(progress)
    if status in ACTIVE_STATUSES:
        st.info("You can keep this page open. Your lesson updates here automatically.")
        st.button("Refresh lesson status", key="refresh_active")
    elif status == "awaiting_review":
        _show_review(client, data)
    elif status == "completed":
        try:
            video = _asset(client, "video")
            st.video(video, format="video/mp4")
            st.download_button("Save my lesson", data=video, file_name="my_cartoon_lesson.mp4",
                               mime="video/mp4", width="stretch")
        except LessonApiError as error:
            _show_api_error(error)
            st.button("Try loading the video again", key="retry_video")
    elif status == "failed":
        st.error(data.get("error") or "We could not read this picture clearly. Please try another picture with one complete question.")
    else:
        st.button("Refresh lesson status", key="refresh_unknown")


def main():
    st.set_page_config(page_title="My Lesson Buddy", page_icon="🌟", layout="wide", initial_sidebar_state="collapsed")
    _style()
    _initialize()
    _apply_character_link()
    st.markdown('<div class="eyebrow">MY LESSON BUDDY · K–2 LEARNING LAB</div>', unsafe_allow_html=True)
    st.title("Your friend. Your worksheet.\nA little learning adventure.")
    st.markdown('<p class="hero-subtitle">Turn one math question into a cartoon you can watch, hear, and count along with.</p>', unsafe_allow_html=True)
    st.markdown('<div class="journey"><span>① Make a friend</span><span>② Add a picture</span><span>③ Check together</span><span>④ Watch & discover</span></div>', unsafe_allow_html=True)
    handoff = st.session_state.pop('studio_handoff_notice', None)
    if handoff:
        if handoff[0] == 'ready':
            if st.session_state.lesson_job:
                st.info(f'{handoff[1]} is ready for your next lesson. Your current lesson keeps its original character.')
            else:
                st.success(f'{handoff[1]} is selected. Add a worksheet when you are ready.')
        else:
            st.warning('That saved character could not be opened. Choose one from your Studio library.')
    try:
        client = LessonApiClient()
    except LessonApiError as error:
        _show_api_error(error)
        return
    character_card, picture_card = st.columns([1.05, 1], gap="large")
    with character_card, st.container(border=True):
        config = _character_creator()
    with picture_card, st.container(border=True):
        picture = _picture_picker()
        has_job = bool(st.session_state.lesson_job)
        pending = st.session_state.pending_submission
        if pending and not has_job:
            st.caption("Retry keeps the picture and character from your first attempt. Start a new lesson to change them.")
        label = "Try reading again →" if pending else "Read my picture →"
        if st.button(label, type="primary", width="stretch",
                     disabled=has_job or (pending is None and (picture is None or not st.session_state.character_valid))):
            with st.spinner("Sending your picture…"):
                _submit_picture(client, config, picture)
            st.rerun()
        if st.session_state.read_error:
            _show_api_error(st.session_state.read_error)
        if has_job:
            st.caption("This lesson has its own picture and character. Start a new lesson when you are ready to change them.")
        if has_job or pending:
            if st.button("Start a new lesson", width="stretch"):
                _clear_lesson()
                st.rerun()
    if st.session_state.lesson_job:
        st.divider()
        state = (st.session_state.last_job or {}).get("status")
        # Only status polling repeats. Model reading and generation are tied to
        # explicit button submissions, outside the polling side effects.
        poll = st.fragment(run_every=2 if state in ACTIVE_STATUSES else None)(_lesson_panel)
        with st.container(border=True):
            poll(client)
    else:
        st.caption("A teacher or grown-up checks each reading before a video is made.")
    st.markdown('<div class="footer-note">A supervised learning prototype · Keep pictures focused on the worksheet.</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
