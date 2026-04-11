import sys
import os

print('Starting deterministic test (waiting for pandas to load...)', flush=True)

try:
    import pandas as pd
    from src.score import rank_overall
except Exception as e:
    print(f"Error importing: {e}", flush=True)
    sys.exit(1)

print('\nImports complete! Testing Tie Breakers for Determinism...', flush=True)

def test_identical(desc, passing_dict):
    df = rank_overall(passing_dict)
    print(f'\n--- {desc} ---', flush=True)
    
    winner = df.index[0] if not df.empty else "None"
    
    # is_highest_tg is a boolean column
    highest_tg = df[df['is_highest_tg']].index[0] if df['is_highest_tg'].any() else "None"
    
    ranks = list(zip(df.index, df['rank_overall']))
    
    print(f'Winner         : {winner}', flush=True)
    print(f'Highest TG     : {highest_tg}', flush=True)
    print(f'Ranks          : {ranks}', flush=True)

# ── Case 1: Identical composite scores, tie broken by config_id ascending ──
base = {
    'config_Z': {
        'warm_tg_median': 100.0,
        'warm_tg_p10': 90.0,
        'warm_ttft_median_ms': 50.0,
        'warm_ttft_p90_ms': 60.0,
        'cold_ttft_median_ms': 100.0,
        'pp_median': 500.0
    },
    'config_A': {
        'warm_tg_median': 100.0,
        'warm_tg_p10': 90.0,
        'warm_ttft_median_ms': 50.0,
        'warm_ttft_p90_ms': 60.0,
        'cold_ttft_median_ms': 100.0,
        'pp_median': 500.0
    }
}

test_identical('Insert Z, then A', base)

reverse_base = {'config_A': base['config_A'], 'config_Z': base['config_Z']}
test_identical('Insert A, then Z', reverse_base)

# ── Case 2: Identical TG, but different composite scores (A has worse composite score) ──
# Because they tie on TG, highest_tg should be explicitly broken by config_id ascending, 
# disregarding who was inserted first!
mixed_base = {
    'config_X': {
        'warm_tg_median': 150.0, # tied
        'warm_tg_p10': 140.0,
        'warm_ttft_median_ms': 50.0,
        'warm_ttft_p90_ms': 60.0,
        'cold_ttft_median_ms': 100.0,
        'pp_median': 600.0
    },
    'config_B': {
        'warm_tg_median': 150.0, # tied
        'warm_tg_p10': 140.0,
        'warm_ttft_median_ms': 999.0, # Worse TTFT = lower composite score
        'warm_ttft_p90_ms': 999.0,
        'cold_ttft_median_ms': 999.0,
        'pp_median': 600.0
    }
}
test_identical('Tied TG, B then X', {'config_B': mixed_base['config_B'], 'config_X': mixed_base['config_X']})
test_identical('Tied TG, X then B', {'config_X': mixed_base['config_X'], 'config_B': mixed_base['config_B']})

print('\nDONE DETERMINISM PROOF', flush=True)
