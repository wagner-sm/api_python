from flask import Flask, jsonify, request
import subprocess
import json
import sys
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
print("Iniciando aplicação Flask...", flush=True)

from monitor import run_monitor

app = Flask(__name__)

API_TOKEN = os.getenv("API_TOKEN")


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 200


@app.before_request
def authenticate():
    # libera healthcheck
    if request.path == "/health":
        return

    auth_header = request.headers.get("Authorization")

    if not auth_header:
        return jsonify({"error": "Missing token"}), 401

    if auth_header != f"Bearer {API_TOKEN}":
        return jsonify({"error": "Invalid token"}), 401


@app.route('/run-monitor', methods=['POST'])
def run_monitor_endpoint():
    try:
        body = request.get_json()
        if not body or 'sites' not in body or not isinstance(body['sites'], list):
            return jsonify({'error': 'Body invalido. Esperado: {"sites": ["url1", "url2"]}'}), 400

        sites = [s.strip() for s in body['sites'] if isinstance(s, str) and s.strip()]
        if not sites:
            return jsonify({'error': 'Lista de sites vazia'}), 400

        results = run_monitor(sites)
        return jsonify(results), 200

    except Exception as e:
        return jsonify({'error': 'Erro interno', 'details': str(e)}), 500


@app.route('/run-discogs', methods=['POST'])
def run_discogs():
    try:
        result = subprocess.run(
            [sys.executable, 'discogs.py'],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            return jsonify({'error': 'Script failed', 'stderr': result.stderr}), 500
        output = result.stdout.strip()
        json_string = output[output.rfind('{'):]
        return jsonify(json.loads(json_string)), 200
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Script timeout (5 min)'}), 504
    except json.JSONDecodeError as e:
        return jsonify({'error': 'Invalid JSON output', 'details': str(e), 'output': result.stdout}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/run-setlistfm', methods=['POST'])
def run_setlistfm():
    try:
        result = subprocess.run(
            [sys.executable, 'setlistfm.py'],
            capture_output=True, text=True, timeout=900
        )
        if result.returncode != 0:
            return jsonify({'error': 'Script failed', 'stderr': result.stderr,
                            'stdout': result.stdout, 'returncode': result.returncode}), 500
        output = result.stdout.strip()
        if not output:
            return jsonify({'error': 'Script returned empty output', 'stderr': result.stderr}), 500
        json_start = output.rfind('{')
        if json_start == -1:
            return jsonify({'error': 'No JSON found in output', 'output': output[-1000:], 'stderr': result.stderr}), 500
        try:
            return jsonify(json.loads(output[json_start:])), 200
        except json.JSONDecodeError as e:
            return jsonify({'error': 'Invalid JSON in output', 'json_error': str(e)}), 500
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Script timeout (15 min)'}), 504
    except Exception as e:
        return jsonify({'error': 'Unexpected error', 'details': str(e), 'type': type(e).__name__}), 500


@app.route('/run-bluesky', methods=['POST'])
def run_bluesky():
    try:
        body = request.get_json() or {}

        handle = body.get("handle", "").strip()
        if not handle:
            return jsonify({"error": "Campo 'handle' obrigatorio"}), 400

        cmd = [sys.executable, "bluesky.py", handle]

        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=120
        )

        if result.returncode != 0:
            return jsonify({
                "error": "Script failed",
                "stderr": result.stderr,
                "stdout": result.stdout,
                "returncode": result.returncode
            }), 500

        output = result.stdout.strip()
        if not output:
            return jsonify({"error": "Script returned empty output", "stderr": result.stderr}), 500

        return jsonify(json.loads(output)), 200

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Script timeout (2 min)"}), 504
    except json.JSONDecodeError as e:
        return jsonify({"error": "Invalid JSON in output", "json_error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "Unexpected error", "details": str(e), "type": type(e).__name__}), 500


@app.route('/run-monitorflip', methods=['POST'])
def run_monitorflip():
    try:
        body = request.get_json() or {}

        date = body.get("date", "").strip()
        origin = body.get("origin", "").strip()
        destiny = body.get("destiny", "").strip()

        if not date or not origin or not destiny:
            return jsonify({"error": "Missing required fields: date, origin, destiny"}), 400

        payload = json.dumps({"date": date, "origin": origin, "destiny": destiny})
        result = subprocess.run(
            [sys.executable, "monitorflip.py"],
            input=payload,
            capture_output=True, text=True, timeout=120
        )

        if result.returncode != 0:
            return jsonify({
                "error": "Script failed",
                "stderr": result.stderr,
                "stdout": result.stdout,
                "returncode": result.returncode
            }), 500

        output = result.stdout.strip()
        if not output:
            return jsonify({"error": "Script returned empty output", "stderr": result.stderr}), 500

        return jsonify(json.loads(output)), 200

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Script timeout (2 min)"}), 504
    except json.JSONDecodeError as e:
        return jsonify({"error": "Invalid JSON in output", "json_error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "Unexpected error", "details": str(e), "type": type(e).__name__}), 500


@app.route('/run-cmc', methods=['POST'])
def run_cmc():
    try:
        result = subprocess.run(
            [sys.executable, 'cmc.py'],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            return jsonify({'error': 'Script failed', 'stderr': result.stderr,
                           'stdout': result.stdout, 'returncode': result.returncode}), 500
        output = result.stdout.strip()
        if not output:
            return jsonify({'error': 'Script returned empty output', 'stderr': result.stderr}), 500
        json_start = output.rfind('{')
        if json_start == -1:
            return jsonify({'error': 'No JSON found in output', 'output': output[-1000:], 'stderr': result.stderr}), 500
        try:
            return jsonify(json.loads(output[json_start:])), 200
        except json.JSONDecodeError as e:
            return jsonify({'error': 'Invalid JSON in output', 'json_error': str(e)}), 500
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Script timeout (5 min)'}), 504
    except Exception as e:
        return jsonify({'error': 'Unexpected error', 'details': str(e), 'type': type(e).__name__}), 500


if __name__ == '__main__':
    print("Chamando app.run() na porta 5000...", flush=True)
    app.run(host='0.0.0.0', port=5000, debug=False)