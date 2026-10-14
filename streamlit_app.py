import base64
import io
import logging
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from streamlit.errors import StreamlitSecretNotFoundError


APP_DIR = Path(__file__).resolve().parent
load_dotenv(APP_DIR / ".env")
IMAGE_DIR = APP_DIR / "novacore_extracted_images"
TEXT_MODEL = "openai/gpt-oss-20b"
VISION_MODEL = "qwen/qwen3.8-27b"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
PINECONE_INDEX_NAME = "novacore-multimodal-rag"
PINECONE_NAMESPACE = "fy2026-demo"
MAX_QUESTION_LENGTH = 1000
MAX_VISUALS_PER_ANSWER = 3
logger = logging.getLogger(__name__)

st.set_page_config(page_title="NovaCore report assistant", page_icon=":material/auto_awesome:")
st.title("NovaCore report assistant")
st.caption("Ask questions about the NovaCore Systems FY2026 company report.")


def get_secret(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value

    try:
        value = st.secrets[name]
    except (KeyError, StreamlitSecretNotFoundError):
        return None

    return str(value) if value else None


def resolve_image_path(metadata_path: str) -> Path | None:
    image_name = Path(metadata_path.replace("\\", "/")).name
    image_path = IMAGE_DIR / image_name
    return image_path if image_path.is_file() else None


def image_to_data_uri(image_path: Path) -> str:
    from PIL import Image

    with Image.open(image_path) as source_image:
        image = source_image.convert("RGB")
        image.thumbnail((1600, 1600))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)

    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


@st.cache_resource
def get_services(groq_api_key: str, pinecone_api_key: str):
    from groq import Groq
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_pinecone import PineconeVectorStore

    os.environ["PINECONE_API_KEY"] = pinecone_api_key
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        encode_kwargs={"normalize_embeddings": True},
    )
    vectorstore = PineconeVectorStore(
        index_name=PINECONE_INDEX_NAME,
        embedding=embeddings,
        namespace=PINECONE_NAMESPACE,
    )
    return vectorstore, Groq(api_key=groq_api_key)


def format_context(documents: list) -> str:
    return "\n\n".join(
        f"[Page {doc.metadata.get('page')} | "
        f"{str(doc.metadata.get('modality', 'text')).upper()}]\n"
        f"{doc.page_content}"
        for doc in documents
    )


def answer_with_vision(
    groq_client,
    question: str,
    context: str,
    image_paths: list[Path],
) -> str:
    content = [
        {
            "type": "text",
            "text": (
                "You are answering questions about the NovaCore Systems FY2026 "
                "report. Use only the retrieved context and attached visuals. "
                "Answer factually, mention page numbers when possible, and say "
                '"I could not find that information in the report." if the '
                "answer is missing.\n\n"
                f"RETRIEVED CONTEXT:\n{context}\n\nQUESTION:\n{question}"
            ),
        }
    ]
    for image_path in image_paths[:MAX_VISUALS_PER_ANSWER]:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": image_to_data_uri(image_path)},
            }
        )

    response = groq_client.chat.completions.create(
        model=VISION_MODEL,
        messages=[{"role": "user", "content": content}],
        temperature=0,
        max_completion_tokens=900,
    )
    answer = response.choices[0].message.content
    if not answer:
        raise RuntimeError("The vision model returned an empty answer.")
    return answer.strip()


def answer_with_text(groq_client, question: str, context: str) -> str:
    response = groq_client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You answer questions about the NovaCore Systems FY2026 "
                    "company report. Use only the supplied retrieved context. "
                    "If the answer is missing, say "
                    '"I could not find that information in the report." '
                    "Mention page numbers when possible."
                ),
            },
            {
                "role": "user",
                "content": f"RETRIEVED CONTEXT:\n{context}\n\nQUESTION:\n{question}",
            },
        ],
        temperature=0,
        max_completion_tokens=900,
    )
    answer = response.choices[0].message.content
    if not answer:
        raise RuntimeError("The text model returned an empty answer.")
    return answer.strip()


def ask_report(vectorstore, groq_client, question: str) -> dict:
    documents = vectorstore.similarity_search(question, k=5)
    if not documents:
        return {
            "content": "I could not find that information in the report.",
            "sources": [],
            "images": [],
        }

    context = format_context(documents)
    image_paths = []
    for document in documents:
        if document.metadata.get("modality") != "visual":
            continue
        metadata_path = document.metadata.get("image_path")
        if metadata_path:
            image_path = resolve_image_path(str(metadata_path))
            if image_path:
                image_paths.append(image_path)

    if image_paths:
        answer = answer_with_vision(groq_client, question, context, image_paths)
    else:
        answer = answer_with_text(groq_client, question, context)

    return {
        "content": answer,
        "sources": [
            {
                "page": document.metadata.get("page"),
                "modality": document.metadata.get("modality", "text"),
                "preview": document.page_content[:500],
            }
            for document in documents
        ],
        "images": [str(path) for path in image_paths[:MAX_VISUALS_PER_ANSWER]],
    }


def show_sources(sources: list[dict]) -> None:
    if not sources:
        return

    with st.expander(f"Sources ({len(sources)})"):
        for source in sources:
            page = source.get("page", "unknown")
            modality = source.get("modality", "text")
            st.caption(f"Page {page} · {modality}")
            st.write(source["preview"])


def show_images(image_paths: list[str]) -> None:
    available_images = [
        path for path in image_paths if Path(path).is_file()
    ]
    if not available_images:
        return

    with st.expander(f"Retrieved visuals ({len(available_images)})"):
        for image_path in available_images:
            st.image(
                image_path,
                alt=f"Retrieved report visual: {Path(image_path).name}",
            )


groq_api_key = get_secret("GROQ_API_KEY")
pinecone_api_key = get_secret("PINECONE_API_KEY")
missing_secrets = [
    name
    for name, value in (
        ("GROQ_API_KEY", groq_api_key),
        ("PINECONE_API_KEY", pinecone_api_key),
    )
    if not value
]

if missing_secrets:
    st.error(
        "Add the following app secrets before asking questions: "
        + ", ".join(missing_secrets)
    )
    st.stop()

st.sidebar.header("About this assistant")
st.sidebar.write(
    "Answers are grounded in the pre-indexed NovaCore FY2026 report. "
    "Source pages and retrieved visuals are shown with each response."
)
st.sidebar.warning(
    "This app is public. Anyone with the link can query the report and use "
    "your configured Groq and Pinecone services."
)

if "messages" not in st.session_state:
    st.session_state.messages = []

if st.sidebar.button("Clear conversation"):
    st.session_state.messages = []
    st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            show_sources(message.get("sources", []))
            show_images(message.get("images", []))

prompt = st.chat_input("Ask a question about the report")
if prompt:
    if len(prompt) > MAX_QUESTION_LENGTH:
        st.error(f"Keep questions to {MAX_QUESTION_LENGTH} characters or fewer.")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Searching the report..."):
                vectorstore, groq_client = get_services(
                    groq_api_key,
                    pinecone_api_key,
                )
                result = ask_report(vectorstore, groq_client, prompt)
            st.markdown(result["content"])
            show_sources(result["sources"])
            show_images(result["images"])
            st.session_state.messages.append(
                {"role": "assistant", **result}
            )
        except Exception:
            logger.exception("Report question failed.")
            st.error(
                "I could not complete that request. Check the app logs and "
                "verify the configured API keys, Pinecone index, and model access."
            )
