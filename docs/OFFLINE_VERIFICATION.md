# Offline verification on another Mac

This prepared bundle targets macOS 14 or later on Apple Silicon (arm64). It includes
Python 3.11, locked wheels, local models, native Word rendering and built web assets.
No npm command or Internet package installation is required to run it.

1. Verify the ZIP's SHA-256 against the supplied `.sha256` file. Extract to a fresh
   folder with Finder or `/usr/bin/ditto -x -k bundle.zip destination` to preserve links
   and executable permissions. The application is inside `spr-prescreen/`.
2. Turn off Wi-Fi and disconnect any other Internet connection on the target Mac.
   This is an operator check; the application does not change network settings.
3. From the extracted application, run `./install.sh`. It verifies bundle files,
   creates a fresh local environment, and uses only the vendored, hash-locked wheels.
4. Run `.venv/bin/python scripts/offline_smoke.py --report reports/offline-smoke.json`.
   It creates its own temporary official-phrase/format fixtures and checks upload,
   screening, review, Word/PDF pages and native/report exports. It reads no prior runs
   and no sponsor data. Expect `workflow: passed` and zero blocked workflow calls.
5. Run `./run.sh`, open Offline status, and confirm the guard is active, model files
   are present, and all observed application listeners are loopback addresses. The
   normal app uses `127.0.0.1:8501`. AI is off in a new bundle.
6. Optionally initialize a new local admin with `.venv/bin/python -m backend.admin init`.
   The bundle includes no password or sessions. The current rule baseline is preserved;
   prior scans, decisions, drafts and source-project policy audit history are excluded.
7. For optional AI, first check `./scripts/run_ollama.sh --verify`, then start
   `./scripts/run_ollama.sh` in another terminal before first-time enablement (use
   `--cpu` if Metal is unavailable). Refresh model status and enable the cached model through the admin controls with a suitable deadline. Later `./run.sh` starts
   project-local Ollama if needed and stops only a server it owns. An existing local
   server is reused only if the configured model digest/context match. Use
   `SPR_OLLAMA_CPU=1 ./run.sh` if Metal is unavailable; CPU inference can be slow.

Record the target Mac model, macOS version, network-disconnected state, smoke report,
listener observations and any failures. A restored folder on the development Mac is
useful portability evidence but does not substitute for this second-machine check.

The guard wraps Python socket/DNS calls and includes parser-worker counts. It is not
an OS-wide firewall for other applications or native subprocesses. Word preview refuses
active/external linked resources; Ollama is configured with cloud disabled and cached
local weights. Physical disconnection verifies the complete native workflow independently.

Pre-screen only — a reviewer makes the release decision.
