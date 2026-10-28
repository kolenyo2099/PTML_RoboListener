# RoboListener (RadioWatch)

RoboListener monitors public radio streams for words in live speech. It runs a local web app, captures audio with FFmpeg, transcribes audio with Faster Whisper, and creates an alert when a transcript matches a keyword.

The app has six views: Discovery, Monitor, Keywords, Pipeline, Alerts, and About. It uses the Radio Browser service to find stations. This service does not require an API key. The app needs an internet connection to find stations, install dependencies, download a Whisper model on first use, and access the station streams.

## Get RoboListener

1. Open the [RoboListener GitHub page](https://github.com/kolenyo2099/PTML_RoboListener).
2. Select **Code**, then **Download ZIP**.
3. Open your Downloads folder. Extract the ZIP file. Keep the extracted RoboListener folder in a place you can find again.
4. Follow the steps below for your computer.

You need an internet connection for setup, station searches, and live streams. The first use of a transcription model also downloads the model. Allow enough free disk space for the model and recordings.

## Install and start

RoboListener needs Python, Node.js, and FFmpeg. You install these tools once. The launcher then installs RoboListener's own dependencies the first time you start it. This can take several minutes. Keep the launcher window open until you finish using the app.

For this version, use a standard 64-bit Python 3.10 to 3.13 installation. The app has been tested with Python 3.11 and 3.13. Do not use Python 3.14 or newer for this version: its required packages may not install. You can check your version with the commands below. Python 3.13.17 is the last python.org installer for this series; Python 3.13.18 is a newer source-only security release. If you need the latest security fixes, use an updated Python 3.13 from a trusted package provider.

### macOS

1. Install [Python 3.13](https://www.python.org/downloads/release/python-31317/). Under **Files**, select the macOS installer. Open the downloaded file and follow the installer steps.
2. Install [Node.js LTS](https://nodejs.org/en/download/). Select the macOS installer, open it, and follow its steps.
3. Install [Homebrew](https://brew.sh/) if you do not already have it. Open the Homebrew page, copy its install command, and paste it into Terminal. Press **Return**. Follow the instructions in Terminal, including any steps to add Homebrew to your PATH. Your Mac may ask for your password; the password does not appear as you type.
4. Close and reopen Terminal. Enter the following command and press **Return** to install FFmpeg:

   ```sh
   brew install ffmpeg
   ```

5. Check the tools. Enter each command in Terminal:

   ```sh
   python3 --version
   node --version
   npm --version
   ffmpeg -version
   ```

   Each command should show a version. If a command is not found, close and reopen Terminal and try again. Check that `python3` reports a supported version between 3.10 and 3.13.
6. Open the extracted RoboListener folder. Double-click **Start RoboListener.command**. If macOS asks whether to open it, choose **Open**. Leave the Terminal window open.
7. The first start installs the app's dependencies and then opens your browser. If the browser does not open, go to <http://127.0.0.1:5173>.
8. To stop RoboListener, select the Terminal window and press **Control-C**.

If the launcher cannot run because of file permissions, open Terminal in the RoboListener folder, enter `chmod +x "Start RoboListener.command" run.sh setup.sh`, and try again. You can also run `./run.sh` in that folder.

### Windows 10 or 11

1. Install [Python 3.13](https://www.python.org/downloads/release/python-31317/). Under **Files**, select **Windows installer (64-bit)** for most computers. Open the installer. Select **Add Python to PATH** before you select **Install Now**. Complete the installation.
2. Install [Node.js LTS](https://nodejs.org/en/download/). Choose the Windows installer and follow its steps.
3. Open **Command Prompt**: open the Start menu, type `Command Prompt`, and select it. Enter this command to install FFmpeg with Windows Package Manager:

   ```bat
   winget install --id Gyan.FFmpeg --exact
   ```

   Follow any prompts. If `winget` is not found, install or update [App Installer](https://learn.microsoft.com/en-us/windows/package-manager/winget/), then open a new Command Prompt and try again.
4. Close and reopen Command Prompt so it can find the new tools. Enter each command:

   ```bat
   python --version
   node --version
   npm --version
   ffmpeg -version
   ```

   Each command should show a version. Check that `python` reports a supported version between 3.10 and 3.13. If a command is not found, restart Windows and check again. For Python, check that **Add Python to PATH** was selected during installation.
5. Open the extracted RoboListener folder. Double-click **Start RoboListener.bat**. Leave the command window open.
6. The first start installs the app's dependencies and then opens your browser. If the browser does not open, go to <http://127.0.0.1:5173>.
7. To stop RoboListener, select the command window and press **Ctrl+C**.

### Linux

1. Install Python 3.10 to 3.13, its `venv` support, Node.js LTS with npm, and FFmpeg. On Ubuntu or Debian, open a terminal and enter:

   ```sh
   sudo apt update
   sudo apt install python3 python3-venv python3-pip ffmpeg
   ```

   Install [Node.js LTS](https://nodejs.org/en/download/) using the instructions for your distribution. Other Linux distributions use different package managers.
2. In the terminal, check the tools:

   ```sh
   python3 --version
   node --version
   npm --version
   ffmpeg -version
   ```

   Each command should show a version. Check that `python3` reports a version between 3.10 and 3.13.
3. Open a terminal in the extracted RoboListener folder. If your file manager has **Open in Terminal**, use that option. Otherwise, type `cd `, drag the folder into the terminal, and press **Enter**.
4. Enter the following command:

   ```sh
   chmod +x run.sh setup.sh
   ./run.sh
   ```

5. The first start installs the app's dependencies. Keep the terminal open. If a browser does not open, go to <http://127.0.0.1:5173>.
6. To stop RoboListener, select the terminal and press **Ctrl+C**.

### Optional: install yt-dlp

Install `yt-dlp` only if you want to monitor a supported YouTube, Twitch, or similar platform URL. Direct radio streams do not require it. See the [yt-dlp installation guide](https://github.com/yt-dlp/yt-dlp#installation). After installation, restart RoboListener. In **Pipeline**, check that yt-dlp shows **Installed**.


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

