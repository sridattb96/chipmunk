import os
import threading
import uvicorn


def start_worker():
    from app.worker import main
    main()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
