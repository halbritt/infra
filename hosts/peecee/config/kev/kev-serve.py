"""Serve Kev on peecee bound to all interfaces (kev.serve hard-codes 127.0.0.1).

Same load path and defaults as `python -m kev.serve` (CUDA, bf16, torch backend); only the
uvicorn bind address changes so proximal can reach it over the tailnet. KEV_API_KEY is
unset on purpose: the box is reachable only on the LAN and tailnet, like ollama's :11434.
"""
import os, sys
import uvicorn
import kev.serve as serve

HOST = os.environ.get("KEV_HOST", "0.0.0.0")
_run = uvicorn.run
uvicorn.run = lambda app, host="127.0.0.1", port=8008, **kw: _run(app, host=HOST, port=port, **kw)
sys.argv = [sys.argv[0], "--run", os.environ.get("KEV_RUN", "jaredpalmer/kev-4b"), "--port", os.environ.get("KEV_PORT", "8008")]
serve.main()
