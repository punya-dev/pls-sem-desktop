"""
Entrypoint for the packaged StatSEM backend server.
Frozen into a standalone sidecar executable via PyInstaller.
"""
import sys
import os
import argparse
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()

    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    parser = argparse.ArgumentParser(description="StatSEM Backend Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8721, help="Port to bind to")
    args = parser.parse_args()

    import uvicorn
    from main import app

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        access_log=False,
    )

