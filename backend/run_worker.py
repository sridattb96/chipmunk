"""Run the embedding worker. Start in a separate terminal from the API."""
import sys

# ChromaDB requires Python 3.10–3.12 (Pydantic v1 incompatible with 3.14+)
if sys.version_info >= (3, 14):
    print(
        "Error: The embedding worker requires Python 3.10–3.12.\n"
        "ChromaDB is not compatible with Python 3.14+.\n\n"
        "Recreate the venv with Python 3.12:\n"
        "  deactivate\n"
        "  rm -rf venv\n"
        "  python3.12 -m venv venv\n"
        "  source venv/bin/activate\n"
        "  pip install -r requirements.txt\n"
    )
    sys.exit(1)

from app.worker import main, run_once

if __name__ == "__main__":
    if "--once" in sys.argv:
        run_once()
    else:
        main()
