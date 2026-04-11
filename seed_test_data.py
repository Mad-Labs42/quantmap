import sqlite3
import json
import uuid
import datetime

db_path = r"d:\Workspaces\QuantMap\db\lab.sqlite"

def add_campaign_data(conn, campaign_id, configs_data):
    """
    configs_data is a list of tuples:
    (config_id, var_value, status, failure_detail, [list of requests])
    """
    now = datetime.datetime.now().isoformat()
    # Ensure campaign exists in db (not technically required by schema but good practice)
    
    for c_idx, (config_id, value, status, detail, requests) in enumerate(configs_data):
        # Insert config
        conn.execute(
            """INSERT OR REPLACE INTO configs
               (id, campaign_id, variable_name, variable_value, config_values_json,
                resolved_command, runtime_env_json, status, failure_detail, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (config_id, campaign_id, "batch_size", json.dumps(value), "{}",
             "llama-server ...", "{}", status, detail, now)
        )
        
        # If there are requests, we need a cycle
        if requests or status == "running":
            cycle_id = int(uuid.uuid4().int % 1000000)
            conn.execute(
                """INSERT OR REPLACE INTO cycles 
                   (id, config_id, campaign_id, cycle_number, status, server_pid, started_at)
                   VALUES (?, ?, ?, ?, 'complete', 1234, ?)""",
                (cycle_id, config_id, campaign_id, 1, now)
            )
            
            for r_idx, (req_type, ttft, is_cold) in enumerate(requests):
                # insert request
                payload = {"outcome": "success", "ttft_ms": ttft, "is_cold": is_cold, "predicted_per_second": 10.0, "total_duration_s": 1.0}
                if ttft is None:
                    payload["outcome"] = "server_error"
                
                conn.execute(
                    """INSERT INTO requests
                       (cycle_id, campaign_id, config_id, cycle_number, request_index, request_type, is_cold, outcome, ttft_ms, predicted_per_second, cycle_status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'complete')""",
                    (cycle_id, campaign_id, config_id, 1, r_idx+1, req_type, int(is_cold), payload["outcome"], ttft, 10.0)
                )

with sqlite3.connect(db_path) as conn:
    # SCENARIO A: Fatal Startup
    # Config 1: 5 valid warm requests (passing)
    # Config 2: 0 requests, status='oom', failure_detail='OOM during KV allocation'
    add_campaign_data(conn, "A_fatal", [
        ("A_fatal_512", 512, "complete", None, [
            ("speed_short", 100.0, True),
            ("speed_short", 110.0, False),
            ("speed_short", 112.0, False),
            ("speed_short", 109.0, False),
            ("speed_short", 111.0, False),
            ("speed_short", 115.0, False),
        ]),
        ("A_fatal_1000000", 1000000, "oom", "OOM during KV allocation", [])
    ])
    
    # SCENARIO B: Low-Sample Config
    # Config 1: < 3 valid warm
    add_campaign_data(conn, "B_low_sample", [
        ("B_low_128", 128, "complete", None, [
            ("speed_short", 100.0, True),
            ("speed_short", 110.0, False),
            ("speed_short", 112.0, False),
        ])
    ])
    
    # SCENARIO C: All Configs Fail
    # Config 1: 5 requests but very high latency (failed score filter max_warm_ttft_p90_ms=500)
    # Config 2: 5 requests but very low success rate (failed score filter min_success_rate)
    add_campaign_data(conn, "C_all_fail", [
        ("C_fail_ttft", 512, "complete", None, [
            ("speed_short", 1000.0, True),
            ("speed_short", 1100.0, False),
            ("speed_short", 1120.0, False),
            ("speed_short", 1090.0, False),
            ("speed_short", 1110.0, False),
            ("speed_short", 1150.0, False),
        ]),
        ("C_fail_sr", 1000000, "complete", None, [
            ("speed_short", 100.0, True),
            ("speed_short", None, False),
            ("speed_short", None, False),
            ("speed_short", None, False),
            ("speed_short", 111.0, False),
            ("speed_short", 115.0, False),
        ])
    ])
    
    # SCENARIO D: Only One Config Passes
    add_campaign_data(conn, "D_one_passes", [
        ("D_pass_512", 512, "complete", None, [
            ("speed_short", 100.0, True),
            ("speed_short", 110.0, False),
            ("speed_short", 112.0, False),
            ("speed_short", 109.0, False),
            ("speed_short", 111.0, False),
            ("speed_short", 115.0, False),
        ]),
        ("D_fail_1M", 1000000, "oom", "CUDA OOM", []),
        ("D_fail_2M", 2000000, "failed", "Invalid parameter", [])
    ])
    conn.commit()
