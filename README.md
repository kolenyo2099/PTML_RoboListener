# RoboListener (RadioWatch)

RoboListener monitors public radio streams for words in live speech. It runs a local web app, captures audio with FFmpeg, transcribes audio with Faster Whisper, and creates an alert when a transcript matches a keyword.

The app has six views: Discovery, Monitor, Keywords, Pipeline, Alerts, and About. It uses the Radio Browser service to find stations. This service does not require an API key. The app needs an internet connection to find stations, install dependencies, download a Whisper model on first use, and access the station streams.

## Requirements

- Python 3.10 or newer
- Node.js LTS, including npm
- FFmpeg available on your `PATH` (required for audio capture)
- Internet access during setup and when the app accesses online services
- Optional: `yt-dlp` for supported YouTube, Twitch, and similar platform URLs

The first use of each Whisper model downloads that model. The download needs disk space. The app's **Pipeline** view shows whether it can find FFmpeg and yt-dlp.

## Install and start

Use the steps for your operating system. Keep the project folder in place. Setup creates `.venv` and `frontend/node_modules` in this folder.

### macOS

1. Install Python 3.10 or newer and Node.js LTS. Install FFmpeg, for example with Homebrew: `brew install ffmpeg`.
2. Double-click **Start RoboListener.command**. If macOS asks, choose **Open**.
3. On first start, the launcher installs the Python and JavaScript dependencies. This can take several minutes.
4. Keep the Terminal window open. The launcher opens the app at <http://127.0.0.1:5173> when both services are ready.
5. To stop the app, press **Control-C** in Terminal.

You can also open Terminal in the project folder and run `./run.sh`.

### Windows

1. Install Python 3.10 or newer. In the Python installer, enable **Add Python to PATH**. Install Node.js LTS and FFmpeg. Make sure `ffmpeg.exe` is on `PATH`.
2. Double-click **Start RoboListener.bat**. The launcher runs PowerShell setup on first start.
3. Keep the command window open. The launcher opens the app at <http://127.0.0.1:5173> when both services are ready.
4. To stop the app, press **Ctrl+C** in the command window.

### Linux

1. Install Python 3.10 or newer, Node.js LTS with npm, and FFmpeg with your distribution's package manager. For Debian or Ubuntu, use `sudo apt install ffmpeg`.
2. Open a terminal in the project folder and run `./run.sh`. If needed, first run `chmod +x run.sh setup.sh`.
3. On first start, the launcher installs the Python and JavaScript dependencies. This can take several minutes.
4. Keep the terminal open. The launcher opens the app at <http://127.0.0.1:5173> when both services are ready. If it does not open a browser, open that address yourself.
5. To stop the app, press **Ctrl+C** in the terminal.

### Ports

The default frontend port is `5173`; the backend port is `8000`. The launcher reports an error if either port is busy. On macOS or Linux, choose free ports when starting from a terminal:

```sh
BACKEND_PORT=8001 FRONTEND_PORT=5174 ./run.sh
```

On Windows PowerShell, set the environment variables before running the launcher:

```powershell
$env:BACKEND_PORT = "8001"
$env:FRONTEND_PORT = "5174"
./run-windows.ps1
```

Then open `http://127.0.0.1:5174`. The app binds to the local computer (`127.0.0.1`).

## Use the app

### 1. Find and select stations

1. Open **Discovery**.
2. Select one or more languages. Use the language search field to find a language.
3. Select **Load stations**. The app groups stations by country.
4. Search by station or city. Filter by language, genre, or country. Select a station card to add or remove it from the selection. A station without a stream cannot be selected.
5. Select **Details** to inspect a station and preview its stream. Select **Load more** in a country section to fetch more stations.
6. To add a stream that is not in the directory, open **Add custom stream URL**. Enter its URL, name, and language code. Country is optional. Select the TV option for a TV stream; the app captures its audio.

### 2. Set keywords

1. Open **Keywords**.
2. Enter one keyword per line, then select **Add**. You can also press Enter to add the entries.
3. Select a match mode:
   - **exact** looks for the same text.
   - **lemma** uses an available spaCy language model to match word forms. The view shows model coverage and install controls. If a model is unavailable, matching falls back to exact matching for that language.
   - **fuzzy** allows approximate matches. Set its threshold with the slider.
4. Optional: enter a preset name and select **Save as preset**. A saved preset is stored in this browser. Select **Load** to add its keywords to the current list.

### 3. Configure capture and transcription

Open **Pipeline** to select the Whisper model, device, compute type, language hint, chunk length, audio buffers, output format, and output directories. Choose WAV, MP3, or OGG for clips. Settings are saved by the app. Use **Use settings for a slower computer** to select the small model with CPU and int8 settings.

The app uses CPU for **auto** device selection. CUDA requires a compatible NVIDIA GPU and CUDA libraries. Apple GPU acceleration is not supported by this backend. Model choice affects speed and transcription results. Start with one station and check whether transcripts keep up.

FFmpeg is required for capture. yt-dlp is optional and is used for supported platform URLs. The generated Python script in this view reflects the current selected stations and settings; use **Copy** or **Download** to save it. The script is a separate local runner.

### 4. Monitor stations

1. Return to **Discovery** and select the stations to monitor.
2. Open **Monitor** and select **Start monitoring**. You can also start, pause, resume, or remove one station on its card. **Stop all** stops all active monitors.
3. Watch each station's status, latest transcript, chunk history, uptime, and alert count. Select **Listen** to play the station stream in your browser.
4. When the app finds a keyword, it waits for the post-buffer audio before it saves the alert and clip. The clip includes the matching chunk and available audio before and after it. Buffer lengths are rounded up to whole chunks. If you stop or pause the station before the post-buffer is complete, the app saves the alert without a clip. A notification appears when the alert is saved.

By default, the app saves clips under `recordings/` and alert records in `recordings/radiowatch.db`. It writes transcript text to `transcripts/` when a keyword matches; it does not save a complete transcript of each stream. Output paths can be changed in **Pipeline**. Keep this folder if you want to retain these files.

### 5. Review alerts

1. Open **Alerts**.
2. Filter alerts by language, station, keyword, review status, or date.
3. Play a clip in the alert card. Select **Clip** to download the audio file, or **ZIP** to export that alert's metadata and available clip.
4. Select one or more checkboxes and use **Export** to download the filtered alerts or selected alerts as a ZIP file.
5. Select **Mark reviewed** to change review status. Select **Delete** to remove an alert record. Deleting an alert does not delete its clip file.

Transcription can miss words or produce incorrect text. Listen to the source audio before you use an alert as evidence. A match may not have an audio clip if clip creation fails.

## Saved settings

The browser stores the current station selection, languages, keywords, pipeline settings, and keyword presets in local browser storage. When you open the app in a new browser session, it can offer to resume the previous selection. **Start fresh** clears the saved session from the browser and restores the default setup. It does not delete clips or transcripts from disk.

## Troubleshooting

- **A port is already in use:** stop the other process or set different `BACKEND_PORT` and `FRONTEND_PORT` values.
- **FFmpeg is not found:** install FFmpeg and ensure its executable is on `PATH`; check the status in **Pipeline**.
- **The app says Backend offline:** keep the launcher window open. If a service stopped, stop and start the launcher again, then read its error output.
- **A platform stream does not start:** install yt-dlp if the URL is from YouTube, Twitch, or a supported platform. Direct audio streams and common broadcast formats use FFmpeg.
- **Transcription is slow:** select fewer stations or a smaller Whisper model. The first use of a model also downloads its files.
- **A saved station stops working:** stream URLs can change. Use **Refresh from API** when the app shows the stale URL notice.

