"""
hypothesis_agent.py

Runs structured experiments through the backplayer API.
Each experiment varies ONE parameter to isolate its effect on outcomes.

Supports parallel execution via --workers flag.
Workers submit runs concurrently but respect a rate limit so the
server and yfinance are not flooded.

Usage:
    # Copy to container:
    docker cp hypothesis_agent.py $(docker-compose ps -q api):/app/hypothesis_agent.py

    # Dry run — print plan, no API calls:
    docker-compose exec api python3 /app/hypothesis_agent.py --dry-run

    # Run one experiment:
    docker-compose exec api python3 /app/hypothesis_agent.py --exp A \
      --username admin --password yourpassword

    # Run all experiments, sequential (~9 hours):
    docker-compose exec api python3 /app/hypothesis_agent.py \
      --username admin --password yourpassword

    # Run all experiments, 3 parallel workers (~3 hours):
    docker-compose exec api python3 /app/hypothesis_agent.py \
      --workers 3 --username admin --password yourpassword

    # Print summary of results already collected:
    docker-compose exec api python3 /app/hypothesis_agent.py --summary

    # Copy results out after completion:
    docker cp $(docker-compose ps -q api):/app/hypothesis_results.json .
"""

import argparse
import json
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'requests', '-q'])
    import requests

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

BASE_URL = 'http://localhost:8000'
POLL_INTERVAL = 12
MAX_WAIT = 900
RESULTS_FILE = '/app/hypothesis_results.json'
DB_DSN = os.environ.get(
    'DATABASE_URL',
    'postgresql://postgres:postgres@db:5432/trading_copilot'
)

TICKERS = {
    'quality_trend':     ['SPY','QQQ','AAPL','MSFT','COST','WMT','MCD','TXN','NOW','AVGO','JPM','V'],
    'quality_reversion': ['MU','PYPL','AMD','NFLX','CRM','SHOP'],
    'etf_sector':        ['XLK','XLF','XLE','XLV','XLY','GLD','TLT'],
}
ALL_QUALITY = TICKERS['quality_trend'] + TICKERS['quality_reversion']

DEFAULT = {
    'lookback_years': 3,
    'entry_score_threshold': 70,
    'watch_score_threshold': 55,
    'min_rr_ratio': 1.5,
    'min_support_strength': 'LOW',
    'require_weekly_aligned': True,
}

EXPERIMENTS = {
    'A': {
        'name': 'Weekly alignment impact',
        'hypothesis': 'require_weekly=ON filters bad signals — improves WR at cost of frequency',
        'tickers': ALL_QUALITY,
        'vary_param': 'require_weekly_aligned',
        'vary_values': [True, False],
    },
    'B': {
        'name': 'Lookback window impact',
        'hypothesis': 'Longer lookback covers more regimes — more reliable statistics',
        'tickers': TICKERS['quality_trend'],
        'vary_param': 'lookback_years',
        'vary_values': [1, 2, 3, 5],
    },
    'C': {
        'name': 'Entry score threshold impact',
        'hypothesis': 'Higher entry threshold = fewer but higher quality signals',
        'tickers': TICKERS['quality_trend'],
        'vary_param': 'entry_score_threshold',
        'vary_values': [60, 65, 70, 75, 80],
        'watch_follow': True,
    },
    'D': {
        'name': 'R:R floor impact',
        'hypothesis': 'Higher R:R floor removes poor-payoff signals',
        'tickers': ALL_QUALITY,
        'vary_param': 'min_rr_ratio',
        'vary_values': [1.0, 1.5, 2.0, 2.5],
    },
    'E': {
        'name': 'Support strength filter',
        'hypothesis': 'HIGH support = more reliable stops = better outcomes',
        'tickers': ALL_QUALITY,
        'vary_param': 'min_support_strength',
        'vary_values': ['LOW', 'MEDIUM', 'HIGH'],
    },
    'F': {
        'name': 'Sector ETFs vs individual stocks',
        'hypothesis': 'ETFs have smoother S/R and different signal characteristics',
        'tickers': TICKERS['etf_sector'],
        'vary_param': None,
        'vary_values': [None],
    },
}

_print_lock = threading.Lock()

def tprint(*args, **kwargs):
    with _print_lock:
        print(*args, **kwargs)


def get_token(username, password):
    r = requests.post(f'{BASE_URL}/auth/login',
                      data={'username': username, 'password': password}, timeout=15)
    r.raise_for_status()
    token = r.json().get('access_token')
    if not token:
        raise RuntimeError(f'No token: {r.json()}')
    return token


def start_run(token, ticker, config):
    r = requests.post(f'{BASE_URL}/player/run',
                      json={'ticker': ticker, **config},
                      headers={'Authorization': f'Bearer {token}'}, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data['run_id'], data['label']


def poll_run(token, ticker, run_id):
    elapsed = 0
    while elapsed < MAX_WAIT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        try:
            r = requests.get(f'{BASE_URL}/player/runs/{ticker}',
                             headers={'Authorization': f'Bearer {token}'}, timeout=15)
            if r.status_code != 200:
                continue
            match = next((x for x in r.json() if str(x.get('run_id')) == run_id), None)
            if not match:
                continue
            status = match.get('status')
            if status == 'complete':
                return match
            elif status == 'error':
                return None
        except Exception:
            pass
    return None


def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def query_conditions(run_id):
    if not HAS_PSYCOPG2:
        return {}
    try:
        conn = psycopg2.connect(DB_DSN)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        results = {}
        for col, key in [('trigger_ok','trigger'), ('rr_label','rr'), ('four_h_confirmed','four_h')]:
            cur.execute(f"""
                SELECT {col}, COUNT(*) as n,
                  ROUND(AVG(CASE WHEN outcome='WIN' THEN 1.0 ELSE 0.0 END)*100,1) as win_rate,
                  ROUND(AVG(return_pct::numeric),3) as avg_return
                FROM backtest_signals
                WHERE run_id = %s AND outcome IS NOT NULL
                GROUP BY {col} ORDER BY {col} DESC NULLS LAST
            """, (run_id,))
            results[key] = [dict(r) for r in cur.fetchall()]
        conn.close()
        return results
    except Exception as e:
        return {'db_error': str(e)}


def run_one(token, ticker, config, run_num, total, label_str, rate_limiter):
    rate_limiter.acquire()
    try:
        run_id, label = start_run(token, ticker, config)
        tprint(f'  [{run_num:3d}/{total}] {ticker:6s} {label_str} → submitted')
    except Exception as e:
        tprint(f'  [{run_num:3d}/{total}] {ticker:6s} {label_str} → submit error: {e}')
        return ticker, None
    finally:
        time.sleep(2)
        rate_limiter.release()

    result = poll_run(token, ticker, run_id)
    if result:
        wr  = safe_float(result.get('win_rate'))
        ev  = safe_float(result.get('expected_value'))
        sig = int(result.get('total_signals') or 0)
        tprint(f'  [{run_num:3d}/{total}] {ticker:6s} {label_str} → '
               f'n={sig:3d} wr={wr:5.1f}% ev={ev:+.3f}')
        return ticker, {
            'run_id': run_id,
            'label': label,
            'total_signals': sig,
            'entry_signals': int(result.get('entry_signals') or 0),
            'win_rate': wr,
            'expected_value': ev,
            'fixed_pnl': safe_float(result.get('fixed_pnl')),
            'win_count': int(result.get('win_count') or 0),
            'loss_count': int(result.get('loss_count') or 0),
            'conditions': query_conditions(run_id),
        }
    else:
        tprint(f'  [{run_num:3d}/{total}] {ticker:6s} {label_str} → FAILED')
        return ticker, None


def run_experiment(exp_id, exp, token, workers=1, dry_run=False):
    tprint(f'\n{"="*60}')
    tprint(f'Exp {exp_id}: {exp["name"]}')
    tprint(f'  {exp["hypothesis"]}')

    jobs = []
    for val in exp['vary_values']:
        config = {**DEFAULT}
        if exp['vary_param']:
            config[exp['vary_param']] = val
            if exp.get('watch_follow') and exp['vary_param'] == 'entry_score_threshold':
                config['watch_score_threshold'] = max(45, val - 15)
        label_str = f'{exp["vary_param"]}={val}' if exp['vary_param'] else 'default'
        for ticker in exp['tickers']:
            jobs.append((ticker, config, val, label_str))

    total = len(jobs)
    tprint(f'  Runs: {total}  Workers: {workers}')

    if dry_run:
        for i, (ticker, _, val, label_str) in enumerate(jobs, 1):
            tprint(f'  [{i:3d}/{total}] {ticker:6s} {label_str}')
        return {}

    results = {}
    for val in exp['vary_values']:
        results[str(val)] = {
            'param_value': val,
            'ticker_results': {},
            'aggregate': {},
        }

    rate_limiter = threading.Semaphore(workers)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(run_one, token, ticker, config, i+1,
                        total, label_str, rate_limiter): (ticker, val)
            for i, (ticker, config, val, label_str) in enumerate(jobs)
        }
        for future in as_completed(futures):
            ticker, val = futures[future]
            try:
                _, data = future.result()
                results[str(val)]['ticker_results'][ticker] = data or {'status': 'error'}
            except Exception as e:
                results[str(val)]['ticker_results'][ticker] = {'status': 'error', 'error': str(e)}

    for val in exp['vary_values']:
        key = str(val)
        tr = results[key]['ticker_results']
        wins    = sum(r.get('win_count', 0)   for r in tr.values() if isinstance(r, dict))
        losses  = sum(r.get('loss_count', 0)  for r in tr.values() if isinstance(r, dict))
        signals = sum(r.get('total_signals',0) for r in tr.values() if isinstance(r, dict))
        evs     = [r['expected_value'] for r in tr.values()
                   if isinstance(r, dict) and r.get('expected_value') is not None]
        pnls    = [r.get('fixed_pnl', 0) for r in tr.values() if isinstance(r, dict)]
        done    = sum(1 for r in tr.values() if isinstance(r, dict) and r.get('run_id'))

        total_resolved = wins + losses
        results[key]['aggregate'] = {
            'total_signals':      signals,
            'total_wins':         wins,
            'total_losses':       losses,
            'win_rate':           round(wins / total_resolved * 100 if total_resolved else 0, 1),
            'avg_expected_value': round(sum(evs) / len(evs) if evs else 0, 4),
            'total_fixed_pnl':    round(sum(pnls), 2),
            'tickers_completed':  done,
        }

    return results


def print_summary(exp_id, exp, results):
    tprint(f'\n{"─"*60}')
    tprint(f'Exp {exp_id} summary: {exp["name"]}')
    tprint(f'{"Value":16s}  {"Signals":8s}  {"WR%":7s}  {"Avg EV":9s}  {"P&L":8s}')
    tprint(f'{"─"*60}')
    best_ev, best_val = float('-inf'), None
    for val in exp['vary_values']:
        agg = results.get(str(val), {}).get('aggregate', {})
        ev = agg.get('avg_expected_value', float('-inf'))
        tprint(f'{str(val):16s}  {agg.get("total_signals",0):8d}  '
               f'{agg.get("win_rate",0):7.1f}  {ev:9.4f}  '
               f'${agg.get("total_fixed_pnl",0):7.0f}')
        if ev > best_ev:
            best_ev, best_val = ev, val
    if best_val is not None:
        tprint(f'\n  Best: {exp["vary_param"]}={best_val}  EV={best_ev:.4f}')


def print_cross_summary(all_results):
    tprint(f'\n{"="*60}')
    tprint('CROSS-EXPERIMENT RECOMMENDATIONS')
    tprint(f'{"="*60}')
    for exp_id, exp_data in sorted(all_results.get('experiments', {}).items()):
        if 'results' not in exp_data:
            continue
        exp = EXPERIMENTS.get(exp_id, {})
        results = exp_data['results']
        best_val, best_ev = None, float('-inf')
        for val_key, val_data in results.items():
            ev = val_data.get('aggregate', {}).get('avg_expected_value', float('-inf'))
            if ev > best_ev:
                best_ev, best_val = ev, val_key
        if best_val is not None:
            agg = results[best_val].get('aggregate', {})
            tprint(f'\n  {exp_id}: {exp.get("vary_param",""):30s} '
                   f'best={best_val}  WR={agg.get("win_rate",0):.1f}%  EV={best_ev:.4f}')


def load_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            return json.load(f)
    return {'experiments': {}, 'metadata': {}}


def save_results(data):
    data['metadata']['last_updated'] = datetime.now().isoformat()
    with open(RESULTS_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    tprint(f'Saved → {RESULTS_FILE}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://localhost:8000')
    parser.add_argument('--username', default='admin')
    parser.add_argument('--password', default='changeme')
    parser.add_argument('--exp', nargs='+', choices=list(EXPERIMENTS.keys()))
    parser.add_argument('--workers', type=int, default=1,
                        help='Parallel workers 1–4. Default 1.')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--summary', action='store_true')
    args = parser.parse_args()

    global BASE_URL
    BASE_URL = args.base_url

    if args.summary:
        print_cross_summary(load_results())
        return

    exp_ids = args.exp or list(EXPERIMENTS.keys())
    workers = max(1, min(args.workers, 4))
    total_runs = sum(len(EXPERIMENTS[e]['tickers']) * len(EXPERIMENTS[e]['vary_values'])
                     for e in exp_ids)
    est = max(1, total_runs * 2 // workers)

    tprint(f'\nHypothesis agent — {len(exp_ids)} experiments, '
           f'{total_runs} runs, {workers} workers, ~{est//60}h{est%60:02d}m')

    if args.dry_run:
        for e in exp_ids:
            run_experiment(e, EXPERIMENTS[e], None, workers=workers, dry_run=True)
        return

    tprint(f'Authenticating...')
    try:
        token = get_token(args.username, args.password)
        tprint('OK\n')
    except Exception as e:
        tprint(f'Auth failed: {e}')
        sys.exit(1)

    all_results = load_results()

    for exp_id in exp_ids:
        exp = EXPERIMENTS[exp_id]
        results = run_experiment(exp_id, exp, token, workers=workers)
        print_summary(exp_id, exp, results)
        all_results['experiments'][exp_id] = {
            'name': exp['name'],
            'hypothesis': exp['hypothesis'],
            'vary_param': exp['vary_param'],
            'workers_used': workers,
            'completed_at': datetime.now().isoformat(),
            'results': results,
        }
        save_results(all_results)

    print_cross_summary(all_results)
    tprint(f'\nDone. Copy results:')
    tprint(f'  docker cp $(docker-compose ps -q api):/app/hypothesis_results.json .')


if __name__ == '__main__':
    main()
