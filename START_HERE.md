# Start RoboListener

RoboListener runs on your computer. Open it at <http://127.0.0.1:5173> after launch.

1. Install Python 3.10 or newer, Node.js LTS with npm, and FFmpeg. FFmpeg must be available on `PATH` to capture audio. Install yt-dlp only if you want to use supported YouTube, Twitch, or similar platform URLs.
2. Start the app:
   - **macOS:** double-click **Start RoboListener.command**.
   - **Windows:** double-click **Start RoboListener.bat**.
   - **Linux:** open a terminal in this folder and run `./run.sh`.
3. On first launch, the app installs its Python and JavaScript dependencies. This needs an internet connection and can take several minutes.
4. Keep the launcher window open while you use the app. It opens your browser after the backend and frontend are ready. If Linux does not open a browser, open <http://127.0.0.1:5173> yourself.
5. To stop the app, press **Ctrl+C** in the launcher window. On macOS, use **Control-C**.

For setup details, feature instructions, port changes, and troubleshooting, read [README.md](README.md).
