# Demo workflow on the prepared Mac

Project: `/Users/mpatel/Projects/spr-prescreen`. These steps use its existing Python environment, built UI, cached models, and local runtimes. A fresh GitHub clone contains source code; it does not include these large/local assets.

1. Let any current batch finish. In the terminal running the old app, press **Control+C** so the demo loads the latest backend. Do not start two app processes against the same project.

2. If Ollama is already running, leave it running and skip this step. Otherwise open Terminal A and run:

   ```bash
   cd /Users/mpatel/Projects/spr-prescreen
   ./scripts/run_ollama.sh
   ```

   Leave Terminal A running. This starts the project's cached local Ollama service; it does not start the website or download a model.

3. Open Terminal B and run:

   ```bash
   cd /Users/mpatel/Projects/spr-prescreen
   ./run.sh --port 8510
   ```

   Wait for `SPR local workspace: http://127.0.0.1:8510`. The launcher validates the local assets and starts the app. When its saved AI default is enabled, it reuses an eligible running Ollama service or starts the bundled service itself. Keep this terminal running.

4. Open <http://127.0.0.1:8510>. Refresh an old tab if necessary. If startup says the port is already in use, stop the previous app terminal first; do not run duplicate copies.

5. Open **System status** and confirm the app is ready. Open **Offline status** to see whether the local AI endpoint is reachable. The current saved timeout is **60 seconds per paper**, including AI queue wait; that is a limit, not a promised processing duration.

6. Return to **Batch Upload**. Add your chosen demo PDF/DOCX documents. Add or remove files before starting. The limit is 100 files, 25 MiB each. Answer-key files and unsupported formats are excluded.

7. Select a scan mode, then click **Start scan**:

   - **Python scanner — no Ollama**: rules and local semantic screening check the readable document; no LLM generation. Use this for the quickest first walkthrough.
   - **Selective AI**: Ollama receives baseline-flagged passages and neighboring context in the same section. No candidates means no LLM call. This is the practical live-AI demonstration mode.
   - **Full AI**: all extracted screenable text is selected for Ollama. Context limits or timeouts can prevent completion; it does not silently switch to selective mode.

   To compare modes, upload the same documents as a new batch with the other mode selected. Existing results and decisions remain separate.

8. Open a completed paper. Click a flag to navigate to its source evidence. Word page preview can take additional time the first time it is opened; this is separate from screening. Expand **Scan details → Local AI** to verify `ran`, `skipped`, `timeout`, or `error` rather than judging AI usage by speed.

9. Enter a reviewer name. Demonstrate **Accept flag**, then **Override** with a reason. Both PDF and DOCX saved review copies retain pending/accepted colors and remove overridden highlights. **Undo** restores the prior decision and corresponding highlight. All original findings remain in the audit history.

10. For red/yellow papers, resolve every flag before clicking **Mark source inspected**. For a complete green paper, click **Mark reviewed & approve**. The Not-Reviewed/Reviewed counts update as review is completed.

11. Expand **Batch document folders** and copy its path. In Finder press **Command+Shift+G**, paste the path, and open it. The main directory is:

    ```text
    /Users/mpatel/Projects/spr-prescreen/runs/Batch Documents/
    ```

    Batch folders use date, local time, and uploaded file count. **Approved** contains reviewer-approved green papers; **Flagged** contains red/yellow review copies, including reviewed papers; **Pending Review** holds green papers awaiting approval. Existing copies are upgraded on restart without rescanning. Update batch folders retries a storage problem; modified files are preserved and reported.

12. Demonstrate **Highlighted PDF/DOCX** downloads or **Export CSV/JSON**. Batch exports contain exactly `Paper`, `File format`, `Expected result`, `# triggers`, and `Title`. Despite its template heading, Expected result contains the actual scanner color. Browser downloads normally go to `/Users/mpatel/Downloads`.

13. For an offline demonstration, after the app and cached Ollama are ready, disconnect Wi-Fi and run another chosen demo batch at the same localhost URL. Internet is unnecessary for these prepared local assets. GitHub uploads require reconnecting later.

14. When finished, press **Control+C** in Terminal B. If you started Ollama separately in Terminal A, press **Control+C** there too when you no longer need it.

The tool supports human review; a green result or successful software test does not establish clearance or guarantee detection accuracy.
