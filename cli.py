import sys
import os
import sqlite3
from datetime import datetime, timezone, timedelta
import scanner

DB_PATH = scanner.DB_PATH

def get_connection():
    return sqlite3.connect(DB_PATH)

def format_tokens(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    elif n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)

def get_agent_pricing(agent):
    if agent == "claude":
        return 3.0, 1.5, 15.0
    elif agent == "gemini":
        return 0.075, 0.0375, 0.30
    else: # codex
        return 15.0, 7.5, 60.0

def calculate_row_cost(agent, input_tok, cached_tok, output_tok):
    in_p, cach_p, out_p = get_agent_pricing(agent)
    return ((input_tok - cached_tok) * in_p + cached_tok * cach_p + output_tok * out_p) / 1_000_000.0

def print_usage_row(title, input_tok, cached_tok, output_tok, reasoning_tok, total_tok, cost=0.0):
    print(f"{title:20} Input: {format_tokens(input_tok):<8} Cached: {format_tokens(cached_tok):<8} Output: {format_tokens(output_tok):<8} Reasoning: {format_tokens(reasoning_tok):<8} Total: {format_tokens(total_tok):<8} Est. Cost: ${cost:.4f}")

def query_stats_for_timeframe(hours=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT agent_type, timestamp, input_tokens, cached_input_tokens, output_tokens, reasoning_tokens, total_tokens FROM token_events")
    rows = cursor.fetchall()
    conn.close()
    
    total_input = 0
    total_cached = 0
    total_output = 0
    total_reasoning = 0
    total_total = 0
    total_cost = 0.0
    
    now = datetime.now(timezone.utc)
    
    for row in rows:
        agent, ts_str, in_t, cach_t, out_t, reas_t, tot_t = row
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if hours is not None:
                delta = now - ts
                if delta.total_seconds() > hours * 3600:
                    continue
            
            total_input += in_t
            total_cached += cach_t
            total_output += out_t
            total_reasoning += reas_t
            total_total += tot_t
            total_cost += calculate_row_cost(agent, in_t, cach_t, out_t)
        except Exception:
            pass
            
    return total_input, total_cached, total_output, total_reasoning, total_total, total_cost

def show_today():
    local_today = datetime.now().strftime("%Y-%m-%d")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT agent_type, timestamp, input_tokens, cached_input_tokens, output_tokens, reasoning_tokens, total_tokens FROM token_events")
    rows = cursor.fetchall()
    conn.close()
    
    in_t = cach_t = out_t = reas_t = tot_t = 0
    cost = 0.0
    count = 0
    
    for row in rows:
        agent, ts_str, i, c, o, r, t = row
        try:
            ts_utc = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            ts_local = ts_utc.astimezone()
            if ts_local.strftime("%Y-%m-%d") == local_today:
                in_t += i
                cach_t += c
                out_t += o
                reas_t += r
                tot_t += t
                cost += calculate_row_cost(agent, i, c, o)
                count += 1
        except Exception:
            pass
            
    print(f"=== Unified Token Usage for Today ({local_today}) ===")
    print(f"Total prompt interactions: {count}")
    print_usage_row("Today's Usage", in_t, cach_t, out_t, reas_t, tot_t, cost)

def show_stats():
    print("=== Unified Token Usage Statistics ===")
    
    # 1. Quota timeframes
    in_5h, cach_5h, out_5h, reas_5h, tot_5h, cost_5h = query_stats_for_timeframe(hours=5)
    print_usage_row("Last 5 Hours", in_5h, cach_5h, out_5h, reas_5h, tot_5h, cost_5h)
    
    in_7d, cach_7d, out_7d, reas_7d, tot_7d, cost_7d = query_stats_for_timeframe(hours=24*7)
    print_usage_row("Last 7 Days", in_7d, cach_7d, out_7d, reas_7d, tot_7d, cost_7d)
    
    in_all, cach_all, out_all, reas_all, tot_all, cost_all = query_stats_for_timeframe(hours=None)
    print_usage_row("All Time", in_all, cach_all, out_all, reas_all, tot_all, cost_all)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # 2. Consumption by Agent
    print("\n--- Consumption by AI Agent ---")
    cursor.execute("""
        SELECT agent_type, SUM(total_tokens) as total, COUNT(*) as count
        FROM token_events
        GROUP BY agent_type
        ORDER BY total DESC
    """)
    for row in cursor.fetchall():
        agent = row[0]
        # Query total costs specifically for this agent to show in list
        cursor.execute("SELECT input_tokens, cached_input_tokens, output_tokens FROM token_events WHERE agent_type = ?", (agent,))
        agent_rows = cursor.fetchall()
        agent_cost = sum(calculate_row_cost(agent, r[0], r[1], r[2]) for r in agent_rows)
        
        print(f"  - {agent.upper():<12} Sessions: {row[2]:<6} Total Tokens: {format_tokens(row[1]):<8} Est. Cost: ${agent_cost:.2f}")
        
    # 3. Biggest Consuming Projects
    print("\n--- Top 5 Consuming Projects ---")
    cursor.execute("""
        SELECT project_name, SUM(total_tokens) as total
        FROM token_events
        GROUP BY project_name
        ORDER BY total DESC
        LIMIT 5
    """)
    for i, row in enumerate(cursor.fetchall(), 1):
        print(f"  {i}. {row[0]:<30} Total Tokens: {format_tokens(row[1])}")
        
    # 4. Biggest Consuming Sessions
    print("\n--- Top 5 Consuming Sessions ---")
    cursor.execute("""
        SELECT session_id, SUM(total_tokens) as total, project_name, agent_type
        FROM token_events
        GROUP BY session_id
        ORDER BY total DESC
        LIMIT 5
    """)
    for i, row in enumerate(cursor.fetchall(), 1):
        sess_name = row[0][:8] + "..." if row[0] else "unknown"
        print(f"  {i}. Session: {sess_name:<12} Agent: {row[3].upper():<8} Project: {row[2]:<20} Total Tokens: {format_tokens(row[1])}")
        
    # 5. Usage by Model
    print("\n--- Usage by Model ---")
    cursor.execute("""
        SELECT model, SUM(total_tokens) as total
        FROM token_events
        GROUP BY model
        ORDER BY total DESC
    """)
    for i, row in enumerate(cursor.fetchall(), 1):
        print(f"  - {row[0]:<25} Total Tokens: {format_tokens(row[1])}")
        
    conn.close()

def main():
    if len(sys.argv) < 2:
        print("Usage: python cli.py [scan|today|stats|dashboard]")
        sys.exit(1)
        
    cmd = sys.argv[1].lower()
    
    if cmd == "scan":
        print("Scanning multi-agent log sessions...")
        stats = scanner.run_scan(verbose=True)
        print(f"Scan Finished: {stats['new']} new files, {stats['updated']} updated, {stats['skipped']} skipped. Added {stats['events_added']} events.")
        
    elif cmd == "today":
        show_today()
        
    elif cmd == "stats":
        show_stats()
        
    elif cmd == "dashboard":
        print("Starting local Unified AI Usage Dashboard microserver...")
        import server
        server.start_server()
        
    else:
        print(f"Unknown command: {cmd}")
        print("Available commands: scan, today, stats, dashboard")
        sys.exit(1)

if __name__ == "__main__":
    main()
