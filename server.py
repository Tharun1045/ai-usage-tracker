import os
import sys
import json
import sqlite3
import urllib.parse
from http.server import SimpleHTTPRequestHandler, HTTPServer
from socketserver import ThreadingTCPServer
from datetime import datetime, timezone, timedelta

PORT = 8080
DB_PATH = os.path.expanduser("~/.codex/codex_usage.db")
if hasattr(sys, "_MEIPASS"):
    WEB_DIR = os.path.join(sys._MEIPASS, "web")
else:
    WEB_DIR = os.path.join(os.path.dirname(__file__), "web")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def calculate_cost(agent_type, input_tok, cached_tok, output_tok):
    if agent_type == "claude" or agent_type == "cursor" or agent_type == "cline" or agent_type == "roocode":
        return ((input_tok - cached_tok) * 3.0 + cached_tok * 1.5 + output_tok * 15.0) / 1_000_000.0
    elif agent_type == "gemini":
        return ((input_tok - cached_tok) * 0.075 + cached_tok * 0.0375 + output_tok * 0.3) / 1_000_000.0
    elif agent_type == "copilot":
        return ((input_tok - cached_tok) * 5.0 + cached_tok * 2.5 + output_tok * 15.0) / 1_000_000.0
    elif agent_type == "groq":
        return ((input_tok - cached_tok) * 0.60 + cached_tok * 0.30 + output_tok * 0.80) / 1_000_000.0
    else: # codex
        return ((input_tok - cached_tok) * 15.0 + cached_tok * 7.5 + output_tok * 60.0) / 1_000_000.0

def get_stats_data(agent_filter="all", date_filter=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Query absolute min/max timestamps for the calendar limits
    cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM token_events")
    min_ts, max_ts = cursor.fetchone()
    min_date_limit = min_ts[:10] if min_ts else datetime.now().strftime("%Y-%m-%d")
    max_date_limit = max_ts[:10] if max_ts else datetime.now().strftime("%Y-%m-%d")
    
    # Query token events based on agent filter
    if agent_filter and agent_filter != "all":
        cursor.execute("""
            SELECT agent_type, timestamp, session_id, project_name, model,
                   input_tokens, cached_input_tokens, output_tokens, reasoning_tokens, total_tokens
            FROM token_events
            WHERE agent_type = ?
        """, (agent_filter,))
    else:
        cursor.execute("""
            SELECT agent_type, timestamp, session_id, project_name, model,
                   input_tokens, cached_input_tokens, output_tokens, reasoning_tokens, total_tokens
            FROM token_events
        """)
        
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    now = datetime.now(timezone.utc)
    local_today = datetime.now().strftime("%Y-%m-%d")
    
    # Check if we are in "Overall / All Time" mode
    is_all_time = not date_filter or date_filter.strip() == ""
    
    # Set target date context
    if is_all_time:
        target_date_str = max_date_limit
    else:
        target_date_str = date_filter
        
    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
    except ValueError:
        target_date_str = local_today
        target_date = datetime.strptime(local_today, "%Y-%m-%d")
        
    agents_list = ["codex", "claude", "gemini", "copilot", "cursor", "groq", "cline", "roocode"]

    # Build daily history trends (storing agent splits)
    daily_7d = {}
    for i in range(6, -1, -1):
        d = (target_date - timedelta(days=i)).strftime("%Y-%m-%d")
        daily_7d[d] = {**{a: 0 for a in agents_list}, "total": 0, "input": 0, "output": 0}
        
    daily_30d = {}
    for i in range(29, -1, -1):
        d = (target_date - timedelta(days=i)).strftime("%Y-%m-%d")
        daily_30d[d] = {**{a: 0 for a in agents_list}, "total": 0, "input": 0, "output": 0}
        
    # Build Monthly buckets (3M, 6M, 12M/1Y)
    def get_month_buckets(end_date, num_months):
        buckets = {}
        curr = end_date
        for _ in range(num_months):
            key = curr.strftime("%Y-%m")
            buckets[key] = {**{a: 0 for a in agents_list}, "total": 0, "input": 0, "output": 0}
            first_of_month = curr.replace(day=1)
            curr = first_of_month - timedelta(days=1)
        return buckets

    monthly_3m = get_month_buckets(target_date, 3)
    monthly_6m = get_month_buckets(target_date, 6)
    monthly_1y = get_month_buckets(target_date, 12)
    
    # Build hourly history for target_date
    hourly_hist = {}
    for i in range(24):
        h = f"{i:02d}:00"
        hourly_hist[h] = {**{a: 0 for a in agents_list}, "total": 0}
        
    # Aggregated metrics for selected date / overall
    selected_summary = {"input": 0, "cached": 0, "output": 0, "reasoning": 0, "total": 0, "cost": 0.0, "count": 0}
    
    # Cumulative stats
    all_time = {"input": 0, "cached": 0, "output": 0, "reasoning": 0, "total": 0, "cost": 0.0}
    today = {"input": 0, "cached": 0, "output": 0, "reasoning": 0, "total": 0, "count": 0, "cost": 0.0}
    last_5h = {"input": 0, "cached": 0, "output": 0, "reasoning": 0, "total": 0, "count": 0, "cost": 0.0}
    last_7d = {"input": 0, "cached": 0, "output": 0, "reasoning": 0, "total": 0, "count": 0, "cost": 0.0}
    
    projects_map = {}
    sessions_map = {}
    models_map = {}
    
    # Total breakdown counters by agent
    agent_breakdown = {a: 0 for a in agents_list}
    
    for row in rows:
        agent = row["agent_type"]
        ts_str = row["timestamp"]
        in_t = row["input_tokens"]
        cach_t = row["cached_input_tokens"]
        out_t = row["output_tokens"]
        reas_t = row["reasoning_tokens"]
        tot_t = row["total_tokens"]
        model = row["model"]
        proj = row["project_name"] or "Unknown Project"
        sess = row["session_id"] or "unknown"
        
        try:
            ts_utc = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            ts_local = ts_utc.astimezone()
            local_date_str = ts_local.strftime("%Y-%m-%d")
            
            row_cost = calculate_cost(agent, in_t, cach_t, out_t)
            
            # 1. Update general timeframes
            all_time["input"] += in_t
            all_time["cached"] += cach_t
            all_time["output"] += out_t
            all_time["reasoning"] += reas_t
            all_time["total"] += tot_t
            all_time["cost"] += row_cost
            
            delta = now - ts_utc
            seconds_ago = delta.total_seconds()
            
            if local_date_str == local_today:
                today["input"] += in_t
                today["cached"] += cach_t
                today["output"] += out_t
                today["reasoning"] += reas_t
                today["total"] += tot_t
                today["cost"] += row_cost
                today["count"] += 1
                
            if seconds_ago <= 5 * 3600:
                last_5h["input"] += in_t
                last_5h["cached"] += cach_t
                last_5h["output"] += out_t
                last_5h["reasoning"] += reas_t
                last_5h["total"] += tot_t
                last_5h["cost"] += row_cost
                last_5h["count"] += 1
                
            if seconds_ago <= 7 * 24 * 3600:
                last_7d["input"] += in_t
                last_7d["cached"] += cach_t
                last_7d["output"] += out_t
                last_7d["reasoning"] += reas_t
                last_7d["total"] += tot_t
                last_7d["cost"] += row_cost
                last_7d["count"] += 1
                
            # 2. Update selected date data & groupers
            is_matching_date = is_all_time or (local_date_str == target_date_str)
            
            if is_matching_date:
                selected_summary["input"] += in_t
                selected_summary["cached"] += cach_t
                selected_summary["output"] += out_t
                selected_summary["reasoning"] += reas_t
                selected_summary["total"] += tot_t
                selected_summary["cost"] += row_cost
                selected_summary["count"] += 1
                
                # Breakdown
                if agent in agent_breakdown:
                    agent_breakdown[agent] += tot_t
                
                # Projects aggregation
                if proj not in projects_map:
                    projects_map[proj] = {
                        "input": 0, "cached": 0, "output": 0, "reasoning": 0, "total": 0, "cost": 0.0,
                        "agent_counts": {a: 0 for a in agents_list}
                    }
                projects_map[proj]["input"] += in_t
                projects_map[proj]["cached"] += cach_t
                projects_map[proj]["output"] += out_t
                projects_map[proj]["reasoning"] += reas_t
                projects_map[proj]["total"] += tot_t
                projects_map[proj]["cost"] += row_cost
                projects_map[proj]["agent_counts"][agent] += tot_t
                
                # Sessions aggregation
                if sess not in sessions_map:
                    sessions_map[sess] = {"input": 0, "cached": 0, "output": 0, "reasoning": 0, "total": 0, "project": proj, "last_active": ts_str, "cost": 0.0}
                sessions_map[sess]["input"] += in_t
                sessions_map[sess]["cached"] += cach_t
                sessions_map[sess]["output"] += out_t
                sessions_map[sess]["reasoning"] += reas_t
                sessions_map[sess]["total"] += tot_t
                sessions_map[sess]["cost"] += row_cost
                if ts_str > sessions_map[sess]["last_active"]:
                    sessions_map[sess]["last_active"] = ts_str
                    
                # Models aggregation
                if model not in models_map:
                    models_map[model] = {"input": 0, "cached": 0, "output": 0, "reasoning": 0, "total": 0, "cost": 0.0}
                models_map[model]["input"] += in_t
                models_map[model]["cached"] += cach_t
                models_map[model]["output"] += out_t
                models_map[model]["reasoning"] += reas_t
                models_map[model]["total"] += tot_t
                models_map[model]["cost"] += row_cost
                
                # Hourly stats for matching date
                hour_str = ts_local.strftime("%H:00")
                if not is_all_time:
                    if hour_str in hourly_hist:
                        hourly_hist[hour_str][agent] += tot_t
                        hourly_hist[hour_str]["total"] += tot_t
                        
            # Daily trends
            if local_date_str in daily_7d:
                daily_7d[local_date_str][agent] += tot_t
                daily_7d[local_date_str]["total"] += tot_t
                daily_7d[local_date_str]["input"] += in_t
                daily_7d[local_date_str]["output"] += out_t
            if local_date_str in daily_30d:
                daily_30d[local_date_str][agent] += tot_t
                daily_30d[local_date_str]["total"] += tot_t
                daily_30d[local_date_str]["input"] += in_t
                daily_30d[local_date_str]["output"] += out_t
                
            # Monthly trends
            local_month_str = local_date_str[:7]
            if local_month_str in monthly_3m:
                monthly_3m[local_month_str][agent] += tot_t
                monthly_3m[local_month_str]["total"] += tot_t
                monthly_3m[local_month_str]["input"] += in_t
                monthly_3m[local_month_str]["output"] += out_t
            if local_month_str in monthly_6m:
                monthly_6m[local_month_str][agent] += tot_t
                monthly_6m[local_month_str]["total"] += tot_t
                monthly_6m[local_month_str]["input"] += in_t
                monthly_6m[local_month_str]["output"] += out_t
            if local_month_str in monthly_1y:
                monthly_1y[local_month_str][agent] += tot_t
                monthly_1y[local_month_str]["total"] += tot_t
                monthly_1y[local_month_str]["input"] += in_t
                monthly_1y[local_month_str]["output"] += out_t
                
        except Exception:
            pass

    # Timeframe comparison calculations (only for All AI filter)
    today_pct = 0.0
    last_5h_pct = 0.0
    last_7d_pct = 0.0
    
    if agent_filter == "all":
        prev_day_str = (target_date - timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_tokens = 0
        prev_5h_tokens = 0
        prev_7d_tokens = 0
        
        for row in rows:
            ts_str = row["timestamp"]
            tot_t = row["total_tokens"]
            try:
                ts_utc = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                ts_local = ts_utc.astimezone()
                local_date = ts_local.strftime("%Y-%m-%d")
                
                # Yesterday's token aggregation
                if local_date == prev_day_str:
                    yesterday_tokens += tot_t
                    
                delta = now - ts_utc
                seconds_ago = delta.total_seconds()
                
                # Previous intervals aggregation
                if 5 * 3600 < seconds_ago <= 10 * 3600:
                    prev_5h_tokens += tot_t
                if 7 * 24 * 3600 < seconds_ago <= 14 * 24 * 3600:
                    prev_7d_tokens += tot_t
            except Exception:
                pass
                
        def get_pct_change(current, previous):
            if previous == 0:
                return 0.0
            return ((current - previous) / previous) * 100.0
            
        today_pct = get_pct_change(selected_summary["total"] if not is_all_time else today["total"], yesterday_tokens)
        last_5h_pct = get_pct_change(last_5h["total"], prev_5h_tokens)
        last_7d_pct = get_pct_change(last_7d["total"], prev_7d_tokens)

    # Format lists
    projects_list = []
    for name, p_data in projects_map.items():
        # Find dominant agent for project and format name
        dominant_agent = max(p_data["agent_counts"], key=p_data["agent_counts"].get)
        agent_display_names = {
            "codex": "Codex", 
            "claude": "Claude", 
            "gemini": "Gemini",
            "copilot": "Copilot",
            "cursor": "Cursor",
            "groq": "Groq",
            "cline": "Cline",
            "roocode": "Roo Code"
        }
        dominant_agent_name = agent_display_names.get(dominant_agent, "Codex")
        
        # Format name as "Project Name (Agent Name)" if in "All AIs" view (except for "ollama")
        if name.lower() == "ollama":
            display_name = name
        else:
            display_name = f"{name} ({dominant_agent_name})" if agent_filter == "all" else name
        
        projects_list.append({
            "project_name": display_name,
            "total_tokens": p_data["total"],
            "input_tokens": p_data["input"],
            "cached_input_tokens": p_data["cached"],
            "output_tokens": p_data["output"],
            "reasoning_tokens": p_data["reasoning"],
            "estimated_cost": p_data["cost"]
        })
    projects_list.sort(key=lambda x: x["total_tokens"], reverse=True)
    
    sessions_list = []
    for s_id, s_data in sessions_map.items():
        sessions_list.append({
            "session_id": s_id,
            "project_name": s_data["project"],
            "total_tokens": s_data["total"],
            "input_tokens": s_data["input"],
            "cached_input_tokens": s_data["cached"],
            "output_tokens": s_data["output"],
            "reasoning_tokens": s_data["reasoning"],
            "last_active": s_data["last_active"],
            "estimated_cost": s_data["cost"]
        })
    sessions_list.sort(key=lambda x: x["total_tokens"], reverse=True)
    
    models_list = []
    for m_name, m_data in models_map.items():
        models_list.append({
            "model": m_name,
            "total_tokens": m_data["total"],
            "input_tokens": m_data["input"],
            "cached_input_tokens": m_data["cached"],
            "output_tokens": m_data["output"],
            "reasoning_tokens": m_data["reasoning"],
            "estimated_cost": m_data["cost"]
        })
    models_list.sort(key=lambda x: x["total_tokens"], reverse=True)
    
    # Sort dynamic trends list
    def format_trend_sorted(trend_dict):
        res = []
        for k in sorted(trend_dict.keys()):
            item = {
                "date": k,
                "total_tokens": trend_dict[k]["total"],
                "input_tokens": trend_dict[k]["input"],
                "output_tokens": trend_dict[k]["output"]
            }
            for agent in agents_list:
                item[f"{agent}_tokens"] = trend_dict[k].get(agent, 0)
            res.append(item)
        return res

    daily_7d_sorted = format_trend_sorted(daily_7d)
    daily_30d_sorted = format_trend_sorted(daily_30d)
    monthly_3m_sorted = format_trend_sorted(monthly_3m)
    monthly_6m_sorted = format_trend_sorted(monthly_6m)
    monthly_1y_sorted = format_trend_sorted(monthly_1y)
    
    # Hourly calculation
    if is_all_time:
        hourly_keys = []
        for i in range(23, -1, -1):
            hourly_keys.append((now - timedelta(hours=i)).strftime("%H:00"))
        
        hourly_hist = {k: {**{a: 0 for a in agents_list}, "total": 0} for k in hourly_keys}
        for row in rows:
            ts_str = row["timestamp"]
            tot_t = row["total_tokens"]
            agent = row["agent_type"]
            try:
                ts_utc = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                ts_local = ts_utc.astimezone()
                delta = now - ts_utc
                if delta.total_seconds() <= 24 * 3600:
                    hour_str = ts_local.strftime("%H:00")
                    if hour_str in hourly_hist:
                        hourly_hist[hour_str][agent] += tot_t
                        hourly_hist[hour_str]["total"] += tot_t
            except Exception:
                pass
        hourly_hist_sorted = []
        for k in hourly_keys:
            item = {
                "hour": k,
                "total_tokens": hourly_hist[k]["total"]
            }
            for agent in agents_list:
                item[f"{agent}_tokens"] = hourly_hist[k].get(agent, 0)
            hourly_hist_sorted.append(item)
    else:
        hourly_hist_sorted = []
        for i in range(24):
            k = f"{i:02d}:00"
            item = {
                "hour": k,
                "total_tokens": hourly_hist[k]["total"]
            }
            for agent in agents_list:
                item[f"{agent}_tokens"] = hourly_hist[k].get(agent, 0)
            hourly_hist_sorted.append(item)

    # Dynamic selected date label
    selected_date_label = "Overall (All Time)" if is_all_time else target_date.strftime("%B %d, %Y")

    return {
        "config": {
            "min_date": min_date_limit,
            "max_date": max_date_limit,
            "selected_date": "" if is_all_time else date_filter,
            "is_all_time": is_all_time
        },
        "summary": {
            "total_tokens": all_time["total"],
            "input_tokens": all_time["input"],
            "cached_input_tokens": all_time["cached"],
            "output_tokens": all_time["output"],
            "reasoning_tokens": all_time["reasoning"],
            "estimated_cost": all_time["cost"]
        },
        "timeframes": {
            "today": {
                **today,
                "pct_change": today_pct
            },
            "last_5h": {
                **last_5h,
                "pct_change": last_5h_pct
            },
            "last_7d": {
                **last_7d,
                "pct_change": last_7d_pct
            },
            "selected_date": {
                **selected_summary,
                "label": selected_date_label,
                "is_all_time": is_all_time
            }
        },
        "projects": projects_list[:15],
        "sessions": sessions_list[:15],
        "models": models_list,
        "history_7d": daily_7d_sorted,
        "history_30d": daily_30d_sorted,
        "history_3m": monthly_3m_sorted,
        "history_6m": monthly_6m_sorted,
        "history_1y": monthly_1y_sorted,
        "history_24h": hourly_hist_sorted,
        "agent_breakdown": agent_breakdown
    }

class DashboardRequestHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = SimpleHTTPRequestHandler.translate_path(self, path)
        rel_path = os.path.relpath(path, os.getcwd())
        return os.path.join(WEB_DIR, rel_path)
        
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()
        
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == "/api/stats":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                query_params = urllib.parse.parse_qs(parsed_url.query)
                agent_filter = query_params.get("agent", ["all"])[0]
                date_filter = query_params.get("date", [""])[0]
                stats = get_stats_data(agent_filter, date_filter)
                self.wfile.write(json.dumps(stats).encode("utf-8"))
            except Exception as e:
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        elif parsed_url.path == "/api/scan":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                import scanner
                scan_res = scanner.run_scan()
                self.wfile.write(json.dumps({"status": "success", "results": scan_res}).encode("utf-8"))
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
        else:
            if parsed_url.path == "/":
                self.path = "/index.html"
            super().do_GET()

def start_server():
    os.makedirs(WEB_DIR, exist_ok=True)
    server_address = ("", PORT)
    
    class ThreadedHTTPServer(ThreadingTCPServer):
        allow_reuse_address = True
        
    httpd = ThreadedHTTPServer(server_address, DashboardRequestHandler)
    print(f"Unified AI Usage Dashboard running at http://localhost:{PORT}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

if __name__ == "__main__":
    start_server()
