# Unified AI Usage Tracker & Dashboard

A local, privacy-safe token usage and cost tracker for developer AI tools. It aggregates and visualizes consumption from **GitHub Copilot**, **Cursor**, **Groq**, **Cline**, **Roo Code**, **Google Gemini**, **Anthropic Claude**, and **OpenAI Codex** inside a modern, glassmorphic dark-mode web interface or directly in your terminal.

---

## 🔒 Privacy Guarantee

- **Zero API calls / network uploads**: All operations occur entirely on your local machine.
- **Strict credential isolation**: The application never touches or reads any API credentials or auth keys.
- **Local SQLite DB**: Aggregated metrics are stored in a private, local SQLite database (`~/.codex/codex_usage.db`).

---

## 🚀 Getting Started

### Method A: One-Click Executable (Zero Setup)

You don't need Python, Node.js, or Git installed.

1. Go to the **Releases** tab in this GitHub repository.
2. Download the `ai-usage-tracker.exe` file.
3. Double-click the file to run it. It will:
   * Scan your machine's logs for active sessions.
   * Launch the database query server.
   * Automatically open the dashboard in your default browser at **[http://localhost:8080](http://localhost:8080)**.

---

### Method B: Developer Setup (Running the Code)

#### 1. Requirements
* Python 3.8+ installed.

#### 2. Run Log Scan
Scans logs for all active AI agents (VS Code, Cursor workspaces, etc.) and saves token counts to the local database.
```bash
python cli.py scan
```

#### 3. Show Today's Stats
Print token usage statistics for the current day:
```bash
python cli.py today
```

#### 4. Show Overall Stats
Displays summary usage of all time, last 5 hours, last 7 days, top projects, and models:
```bash
python cli.py stats
```

#### 5. Start Dashboard Server
Launch the zero-dependency local webserver and auto-open the dashboard page in your browser:
```bash
python cli.py dashboard
```

---

## 💻 Web Dashboard UI

Once the dashboard server is running, navigate to:
👉 **[http://localhost:8080](http://localhost:8080)**

### UI Features:
- **Instant Scan Trigger**: Click the **🔄 Scan Logs** button in the header to run an incremental log scan directly from the web browser.
- **Dynamic Filters**: Shows selection tabs *only* for the AI tools you actually have database logs for (hiding unused agents).
- **Dynamic Chart Legends**: The Daily Consumption stacked bar chart and Hourly Activity (24 Hours) line chart dynamically display legend entries only for active providers.
- **Top Projects & Models**: View ranked token consumption lists by project, folder path, and model.
