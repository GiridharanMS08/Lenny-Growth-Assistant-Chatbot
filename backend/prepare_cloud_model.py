"""Download and verify the CPU model at build time; no API credentials required."""

from app.core.config import Settings
from app.rag.cloud import embed_query


def main() -> None:
    settings = Settings(_env_file=None, FASTEMBED_LOCAL_FILES_ONLY=False)
    vector = embed_query(settings, "Verify the Railway embedding model cache.")
    print(f"FastEmbed ready: {settings.cloud_embedding_model}, {len(vector)} dimensions.")


if __name__ == "__main__":
    main()
