import os
import json
import glob
import sqlite3
from datetime import datetime, timezone, timedelta

DB_PATH = os.path.expanduser("~/.codex/codex_usage.db")
CODEX_SESSIONS_DIR = os.path.expanduser("~/.codex/sessions")
CLAUDE_SESSIONS_DIR = os.path.expanduser("~/.claude/projects")
GEMINI_SESSIONS_DIR = os.path.expanduser("~/.gemini/antigravity/brain")

def get_vscode_storage_path(subpath):
    import platform
    home = os.path.expanduser("~")
    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
        return os.path.join(appdata, "Code", "User", subpath)
    elif system == "Darwin":
        return os.path.join(home, "Library", "Application Support", "Code", "User", subpath)
    else:
        return os.path.join(home, ".config", "Code", "User", subpath)

def get_cursor_storage_path(subpath):
    import platform
    home = os.path.expanduser("~")
    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
        return os.path.join(appdata, "Cursor", "User", subpath)
    elif system == "Darwin":
        return os.path.join(home, "Library", "Application Support", "Cursor", "User", subpath)
    else:
        return os.path.join(home, ".config", "Cursor", "User", subpath)

COPILOT_SESSIONS_DIR = get_vscode_storage_path("workspaceStorage")
CURSOR_SESSIONS_DIR = get_cursor_storage_path("workspaceStorage")
GROQ_SESSIONS_DIR = os.path.expanduser("~/.groq/sessions")
CLINE_SESSIONS_DIR = get_vscode_storage_path(os.path.join("globalStorage", "saoudrizwan.claude-dev", "tasks"))
ROOCODE_SESSIONS_DIR = get_vscode_storage_path(os.path.join("globalStorage", "roodev.roo-cline", "tasks"))

def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if we need to migrate schema (add agent_type column)
    cursor.execute("PRAGMA table_info(token_events)")
    columns = [row[1] for row in cursor.fetchall()]
    if columns and "agent_type" not in columns:
        print("Schema out of date. Recreating tables...")
        cursor.execute("DROP TABLE IF EXISTS token_events")
        cursor.execute("DROP TABLE IF EXISTS scanned_files")
        
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scanned_files (
        file_path TEXT PRIMARY KEY,
        last_modified REAL,
        file_size INTEGER
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS token_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_type TEXT,
        file_path TEXT,
        timestamp TEXT,
        session_id TEXT,
        project_path TEXT,
        project_name TEXT,
        model TEXT,
        input_tokens INTEGER,
        cached_input_tokens INTEGER,
        output_tokens INTEGER,
        reasoning_tokens INTEGER,
        total_tokens INTEGER
    )
    """)
    
    conn.commit()
    conn.close()

def parse_session_id_from_filename(filename):
    base = os.path.basename(filename)
    name, _ = os.path.splitext(base)
    parts = name.split("-")
    if len(parts) >= 6:
        uuid_parts = parts[-5:]
        if len(uuid_parts[0]) == 8 and len(uuid_parts[1]) == 4 and len(uuid_parts[2]) == 4 and len(uuid_parts[3]) == 4 and len(uuid_parts[4]) == 12:
            return "-".join(uuid_parts)
    return name

def clean_path(p):
    if not p:
        return ""
    # Strip quotes, backslashes and surrounding whitespace
    return p.strip().strip('"').strip("'").strip()

def get_project_name(cwd):
    if not cwd:
        return "Unknown Project"
    cwd = clean_path(cwd)
    
    # Normalize slashes (handling potential double backslashes)
    normalized = cwd.replace("\\\\", "/").replace("\\", "/").strip("/")
    if not normalized:
        return "Unknown Project"
        
    parts = [p for p in normalized.split("/") if p]
    
    # Strip file extensions if it looks like a file
    if parts:
        last_part = parts[-1]
        if "." in last_part and len(last_part.split(".")[-1]) <= 4:
            parts.pop()
        
    if not parts:
        return "Unknown Project"
        
    # Try to find folder directly under common personal project directories
    project_idx = -1
    for i, part in enumerate(parts):
        if part in ["Tharun_personal_projects", "Documents", "projects", "scratch"]:
            if i + 1 < len(parts):
                project_idx = i + 1
                break
                
    if project_idx != -1:
        proj = parts[project_idx]
        if proj == "gravity-games":
            return "Games"
        return proj
        
    # Fallback to last directory name, skipping common subdirectories
    ignored_dirs = {"src", "web", "scripts", "builtin", "systems", "components", "services", "assets", "public", "dist", "build"}
    for part in reversed(parts):
        if part.lower() not in ignored_dirs:
            if part.lower() == "gravity-games":
                return "Games"
            return part
            
    return parts[-1]

# --- CODE SCANNER ---
def scan_codex_file(file_path):
    fallback_session_id = parse_session_id_from_filename(file_path)
    
    session_id = fallback_session_id
    session_cwd = None
    current_cwd = None
    current_model = "unknown"
    
    events = []
    
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                event_type = data.get("type")
                payload = data.get("payload")
                timestamp = data.get("timestamp")
                
                if not isinstance(payload, dict):
                    continue
                
                if event_type == "session_meta":
                    session_id = payload.get("session_id") or payload.get("id") or session_id
                    session_cwd = payload.get("cwd")
                    if not current_cwd:
                        current_cwd = session_cwd
                    if "model" in payload:
                        current_model = payload.get("model")
                
                elif event_type == "turn_context":
                    if "cwd" in payload:
                        current_cwd = payload.get("cwd")
                    if "model" in payload:
                        current_model = payload.get("model")
                
                elif event_type == "event_msg" and payload.get("type") == "token_count":
                    info = payload.get("info")
                    if not isinstance(info, dict):
                        continue
                    
                    last_usage = info.get("last_token_usage")
                    if not isinstance(last_usage, dict):
                        continue
                    
                    reasoning = last_usage.get("reasoning_output_tokens", 0)
                    if not reasoning:
                        reasoning = last_usage.get("reasoning_tokens", 0)
                        
                    input_tok = last_usage.get("input_tokens", 0)
                    cached_tok = last_usage.get("cached_input_tokens", 0)
                    output_tok = last_usage.get("output_tokens", 0)
                    total_tok = last_usage.get("total_tokens", 0)
                    
                    if not total_tok:
                        total_tok = input_tok + output_tok
                    
                    cwd = current_cwd or session_cwd
                    proj_name = get_project_name(cwd)
                    
                    events.append((
                        "codex",
                        file_path,
                        timestamp,
                        session_id,
                        clean_path(cwd),
                        proj_name,
                        current_model,
                        input_tok,
                        cached_tok,
                        output_tok,
                        reasoning,
                        total_tok
                    ))
            except Exception:
                pass
    return events

# --- CLAUDE SCANNER ---
def scan_claude_file(file_path):
    session_id, _ = os.path.splitext(os.path.basename(file_path))
    
    events = []
    
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                timestamp = data.get("timestamp")
                cwd = data.get("cwd")
                sess_id = data.get("sessionId") or session_id
                
                message = data.get("message")
                if not isinstance(message, dict):
                    continue
                
                usage = message.get("usage")
                if not isinstance(usage, dict):
                    continue
                
                input_tok = usage.get("input_tokens", 0)
                output_tok = usage.get("output_tokens", 0)
                cached_tok = usage.get("cache_read_input_tokens", 0)
                
                total_tok = input_tok + output_tok
                model = message.get("model", "claude-3-5-sonnet")
                proj_name = get_project_name(cwd)
                
                events.append((
                    "claude",
                    file_path,
                    timestamp,
                    sess_id,
                    clean_path(cwd),
                    proj_name,
                    model,
                    input_tok,
                    cached_tok,
                    output_tok,
                    0,
                    total_tok
                ))
            except Exception:
                pass
    return events

# --- GEMINI / ANTIGRAVITY SCANNER ---
def scan_gemini_file(file_path):
    parent_dirs = file_path.replace("\\", "/").split("/")
    session_id = "unknown"
    for i, p in enumerate(parent_dirs):
        if p == ".system_generated" and i > 0:
            session_id = parent_dirs[i-1]
            break
            
    events = []
    current_cwd = r"C:\Users\tharu\.gemini\antigravity\scratch"
    current_model = "gemini-3.5-pro"
    
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                event_type = data.get("type")
                timestamp = data.get("created_at") or data.get("timestamp")
                content = data.get("content")
                
                tool_calls = data.get("tool_calls")
                if isinstance(tool_calls, list):
                    for call in tool_calls:
                        args = call.get("args")
                        if isinstance(args, dict):
                            # Search for path inputs across all possible tool arguments
                            cwd = args.get("Cwd") or args.get("DirectoryPath") or args.get("SearchPath") or args.get("TargetFile") or args.get("AbsolutePath")
                            if cwd:
                                current_cwd = clean_path(cwd)
                
                if event_type == "USER_INPUT" and content:
                    input_tok = int(len(content) / 3.5)
                    events.append((
                        "gemini",
                        file_path,
                        timestamp,
                        session_id,
                        current_cwd,
                        get_project_name(current_cwd),
                        current_model,
                        input_tok,
                        0,
                        0,
                        0,
                        input_tok
                    ))
                elif event_type == "PLANNER_RESPONSE" and content:
                    output_tok = int(len(content) / 3.5)
                    events.append((
                        "gemini",
                        file_path,
                        timestamp,
                        session_id,
                        current_cwd,
                        get_project_name(current_cwd),
                        current_model,
                        0,
                        0,
                        output_tok,
                        0,
                        output_tok
                    ))
            except Exception:
                pass
    return events

def scan_copilot_file(file_path):
    events = []
    parts = file_path.replace("\\", "/").split("/")
    workspace_hash = "unknown"
    for i, part in enumerate(parts):
        if part == "workspaceStorage" and i + 1 < len(parts):
            workspace_hash = parts[i+1]
            break
            
    project_name = "VS Code Workspace"
    workspace_dir = ""
    if workspace_hash != "unknown":
        idx = parts.index(workspace_hash)
        workspace_dir = "/".join(parts[:idx+1])
        workspace_json_path = os.path.join(workspace_dir, "workspace.json")
        if os.path.exists(workspace_json_path):
            try:
                with open(workspace_json_path, 'r', encoding='utf-8') as f:
                    w_data = json.load(f)
                    folder_uri = w_data.get("folder")
                    if folder_uri:
                        project_name = get_project_name(folder_uri)
            except:
                pass
                
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            data = json.load(f)
            v = data.get("v", {})
            session_id = v.get("sessionId") or os.path.splitext(os.path.basename(file_path))[0]
            requests = v.get("requests", [])
            for req in requests:
                req_msg = req.get("message")
                req_text = ""
                if isinstance(req_msg, dict):
                    req_text = req_msg.get("text", "")
                elif isinstance(req_msg, str):
                    req_text = req_msg
                    
                resp_text = ""
                response = req.get("response", [])
                if isinstance(response, list):
                    for resp_item in response:
                        if isinstance(resp_item, dict):
                            resp_text += resp_item.get("value", "") + "\n"
                        elif isinstance(resp_item, str):
                            resp_text += resp_item + "\n"
                elif isinstance(response, dict):
                    resp_text = response.get("value", "")
                elif isinstance(response, str):
                    resp_text = response
                    
                ts_ms = req.get("creationDate") or v.get("creationDate") or os.path.getmtime(file_path) * 1000
                dt = datetime.fromtimestamp(ts_ms / 1000.0, timezone.utc)
                timestamp = dt.isoformat().replace("+00:00", "Z")
                
                input_tok = int(len(req_text) / 3.5) if req_text else 0
                output_tok = int(len(resp_text) / 3.5) if resp_text else 0
                
                model = req.get("model") or "copilot-default"
                
                events.append((
                    "copilot",
                    file_path,
                    timestamp,
                    session_id,
                    workspace_dir,
                    project_name,
                    model,
                    input_tok,
                    0,
                    output_tok,
                    0,
                    input_tok + output_tok
                ))
    except Exception:
        pass
        
    return events

def scan_cursor_db(db_path):
    import sqlite3
    import tempfile
    import shutil
    
    events = []
    workspace_dir = os.path.dirname(db_path)
    session_id = os.path.basename(workspace_dir)
    
    project_name = "Cursor Workspace"
    workspace_json_path = os.path.join(workspace_dir, "workspace.json")
    if os.path.exists(workspace_json_path):
        try:
            with open(workspace_json_path, 'r', encoding='utf-8') as f:
                w_data = json.load(f)
                folder_uri = w_data.get("folder")
                if folder_uri:
                    project_name = get_project_name(folder_uri)
        except:
            pass
            
    temp_dir = tempfile.gettempdir()
    temp_db_path = os.path.join(temp_dir, f"cursor_state_{session_id}.db")
    try:
        shutil.copy2(db_path, temp_db_path)
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM ItemTable WHERE key = 'workbench.panel.aichat.view.aichat.chatdata'")
        row = cursor.fetchone()
        conn.close()
        try:
            os.remove(temp_db_path)
        except:
            pass
            
        if row and row[0]:
            chat_data = json.loads(row[0])
            tabs = chat_data.get("tabs", [])
            for tab in tabs:
                tab_id = tab.get("id") or session_id
                ts_ms = tab.get("timestamp") or os.path.getmtime(db_path) * 1000
                dt = datetime.fromtimestamp(ts_ms / 1000.0, timezone.utc)
                timestamp = dt.isoformat().replace("+00:00", "Z")
                
                bubbles = tab.get("bubbles", [])
                for bubble in bubbles:
                    b_type = bubble.get("type")
                    text = bubble.get("text", "")
                    if not text:
                        continue
                        
                    tokens = int(len(text) / 3.5)
                    input_tok = tokens if b_type == "user" else 0
                    output_tok = tokens if b_type in ("ai", "assistant") else 0
                    
                    model = tab.get("model") or "cursor-default"
                    
                    events.append((
                        "cursor",
                        db_path,
                        timestamp,
                        tab_id,
                        workspace_dir,
                        project_name,
                        model,
                        input_tok,
                        0,
                        output_tok,
                        0,
                        input_tok + output_tok
                    ))
    except Exception:
        pass
        
    return events

def scan_groq_file(file_path):
    events = []
    session_id, _ = os.path.splitext(os.path.basename(file_path))
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    timestamp = data.get("timestamp") or datetime.now(timezone.utc).isoformat()
                    model = data.get("model") or "llama3-70b-8192"
                    
                    input_tok = data.get("input_tokens") or data.get("prompt_tokens") or 0
                    output_tok = data.get("output_tokens") or data.get("completion_tokens") or 0
                    cached_tok = data.get("cached_tokens") or data.get("prompt_tokens_details", {}).get("cached_tokens", 0) or 0
                    
                    prompt = data.get("prompt") or data.get("input") or ""
                    response = data.get("response") or data.get("output") or ""
                    if not input_tok and prompt:
                        input_tok = int(len(prompt) / 3.5)
                    if not output_tok and response:
                        output_tok = int(len(response) / 3.5)
                        
                    total_tok = data.get("total_tokens") or (input_tok + output_tok)
                    
                    events.append((
                        "groq",
                        file_path,
                        timestamp,
                        session_id,
                        "",
                        "Groq Workspace",
                        model,
                        input_tok,
                        cached_tok,
                        output_tok,
                        0,
                        total_tok
                    ))
                except:
                    pass
    except Exception:
        pass
    return events

def scan_cline_file(file_path):
    events = []
    parts = file_path.replace("\\", "/").split("/")
    task_id = "unknown"
    agent_type = "cline"
    
    for i, part in enumerate(parts):
        if part == "tasks" and i > 0:
            task_id = parts[i+1] if i + 1 < len(parts) else "unknown"
        if "roo-cline" in part.lower():
            agent_type = "roocode"
            
    project_name = "Cline Task" if agent_type == "cline" else "Roo Code Task"
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            messages = json.load(f)
            if not isinstance(messages, list):
                return []
                
            for msg in messages:
                ts_ms = msg.get("ts") or os.path.getmtime(file_path) * 1000
                dt = datetime.fromtimestamp(ts_ms / 1000.0, timezone.utc)
                timestamp = dt.isoformat().replace("+00:00", "Z")
                
                text = msg.get("text") or ""
                if not text and isinstance(msg.get("value"), str):
                    text = msg.get("value")
                    
                if not text:
                    continue
                    
                tokens = int(len(text) / 3.5)
                m_type = msg.get("type")
                input_tok = tokens if m_type == "ask" else 0
                output_tok = tokens if m_type == "say" else 0
                
                events.append((
                    agent_type,
                    file_path,
                    timestamp,
                    task_id,
                    "",
                    project_name,
                    "claude-3-5-sonnet",
                    input_tok,
                    0,
                    output_tok,
                    0,
                    input_tok + output_tok
                ))
    except Exception:
        pass
        
    return events

# --- SCAN ORCHESTRATOR ---
def run_scan(verbose=False):
    init_db()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT file_path, last_modified, file_size FROM scanned_files")
    scanned_state = {row["file_path"]: (row["last_modified"], row["file_size"]) for row in cursor.fetchall()}
    
    codex_files = glob.glob(os.path.join(CODEX_SESSIONS_DIR, "**/*.jsonl"), recursive=True) if os.path.exists(CODEX_SESSIONS_DIR) else []
    claude_files = glob.glob(os.path.join(CLAUDE_SESSIONS_DIR, "**/*.jsonl"), recursive=True) if os.path.exists(CLAUDE_SESSIONS_DIR) else []
    
    gemini_files = []
    if os.path.exists(GEMINI_SESSIONS_DIR):
        for root, dirs, files in os.walk(os.path.normpath(GEMINI_SESSIONS_DIR)):
            for f in files:
                if f == "transcript.jsonl":
                    gemini_files.append(os.path.join(root, f))
                    
    copilot_files = glob.glob(os.path.join(COPILOT_SESSIONS_DIR, "**/chatSessions/*.jsonl"), recursive=True) if os.path.exists(COPILOT_SESSIONS_DIR) else []
    cursor_files = glob.glob(os.path.join(CURSOR_SESSIONS_DIR, "**/state.vscdb"), recursive=True) if os.path.exists(CURSOR_SESSIONS_DIR) else []
    groq_files = glob.glob(os.path.join(GROQ_SESSIONS_DIR, "**/*.jsonl"), recursive=True) if os.path.exists(GROQ_SESSIONS_DIR) else []
    cline_files = glob.glob(os.path.join(CLINE_SESSIONS_DIR, "**/ui_messages.json"), recursive=True) if os.path.exists(CLINE_SESSIONS_DIR) else []
    roocode_files = glob.glob(os.path.join(ROOCODE_SESSIONS_DIR, "**/ui_messages.json"), recursive=True) if os.path.exists(ROOCODE_SESSIONS_DIR) else []
        
    all_scan_targets = []
    for f in codex_files:
        if "auth.json" not in f:
            all_scan_targets.append((f, "codex"))
    for f in claude_files:
        all_scan_targets.append((f, "claude"))
    for f in gemini_files:
        all_scan_targets.append((f, "gemini"))
    for f in copilot_files:
        all_scan_targets.append((f, "copilot"))
    for f in cursor_files:
        all_scan_targets.append((f, "cursor"))
    for f in groq_files:
        all_scan_targets.append((f, "groq"))
    for f in cline_files:
        all_scan_targets.append((f, "cline"))
    for f in roocode_files:
        all_scan_targets.append((f, "roocode"))
        
    new_files_count = 0
    updated_files_count = 0
    skipped_files_count = 0
    total_events_added = 0
    
    for file_path, agent_type in all_scan_targets:
        try:
            mtime = os.path.getmtime(file_path)
            size = os.path.getsize(file_path)
        except OSError:
            continue
            
        if file_path in scanned_state:
            old_mtime, old_size = scanned_state[file_path]
            if old_mtime == mtime and old_size == size:
                skipped_files_count += 1
                continue
            else:
                updated_files_count += 1
                cursor.execute("DELETE FROM token_events WHERE file_path = ?", (file_path,))
        else:
            new_files_count += 1
            
        if verbose:
            print(f"Scanning [{agent_type}]: {file_path}")
            
        if agent_type == "codex":
            events = scan_codex_file(file_path)
        elif agent_type == "claude":
            events = scan_claude_file(file_path)
        elif agent_type == "gemini":
            events = scan_gemini_file(file_path)
        elif agent_type == "copilot":
            events = scan_copilot_file(file_path)
        elif agent_type == "cursor":
            events = scan_cursor_db(file_path)
        elif agent_type == "groq":
            events = scan_groq_file(file_path)
        elif agent_type in ("cline", "roocode"):
            events = scan_cline_file(file_path)
        else:
            events = []
            
        if events:
            cursor.executemany("""
            INSERT INTO token_events (
                agent_type, file_path, timestamp, session_id, project_path, project_name,
                model, input_tokens, cached_input_tokens, output_tokens, reasoning_tokens, total_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, events)
            total_events_added += len(events)
            
        cursor.execute("""
        INSERT OR REPLACE INTO scanned_files (file_path, last_modified, file_size)
        VALUES (?, ?, ?)
        """, (file_path, mtime, size))
        
        conn.commit()
        
    conn.close()
    
    return {
        "new": new_files_count,
        "updated": updated_files_count,
        "skipped": skipped_files_count,
        "events_added": total_events_added
    }

if __name__ == "__main__":
    print("Running Unified Scan...")
    stats = run_scan(verbose=True)
    print(f"Scan complete: {stats}")
