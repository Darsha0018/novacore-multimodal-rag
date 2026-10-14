# NovaCore multimodal report assistant

This Streamlit app answers questions about the NovaCore FY2026 report using
the existing Pinecone vector index. It retrieves text and visual summaries,
uses Groq for answers, and displays retrieved source pages and available
report images.

## Requirements

- Python 3.11 or newer
- Groq API key
- Pinecone API key
- The existing Pinecone index `novacore-multimodal-rag`, populated in the
  `fy2026-demo` namespace using the `sentence-transformers/all-MiniLM-L6-v2`
  embedding model

The app only queries the index; it does not create, clear, or ingest Pinecone
data on startup. Keep `novacore_extracted_images/` alongside the app so visual
citations in the index can be displayed.

## Run locally

Install dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The app reads `GROQ_API_KEY` and `PINECONE_API_KEY` from environment variables
or a local `.env` file. Alternatively, create
`.streamlit\secrets.toml` with:

```toml
GROQ_API_KEY = "your-groq-api-key"
PINECONE_API_KEY = "your-pinecone-api-key"
```

Run the app:

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

## Deploy to Streamlit Community Cloud

1. Push the app, `requirements.txt`, README, and `novacore_extracted_images/`
   to a GitHub repository. Do not commit `.env`, API keys, or
   `.streamlit\secrets.toml`.
2. In Streamlit Community Cloud, create an app from that repository and select
   `streamlit_app.py` as the entry point.
3. In the app's **Settings → Secrets**, add:

   ```toml
   GROQ_API_KEY = "your-groq-api-key"
   PINECONE_API_KEY = "your-pinecone-api-key"
   ```

4. Deploy and confirm the configured Pinecone index is reachable from the app.

This deployment is intentionally public: anyone with its URL can ask questions
about the indexed report, and requests consume your Groq and Pinecone quotas.
Use provider usage limits and rotate credentials if they are ever exposed.
