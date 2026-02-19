from flask import Flask, jsonify, request
import subprocess
import json
import sys

from monitor_api import run_monitor

app = Flask(__name__)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 200


# ---------------------------------------------------------------------------
# MONITOR DE SITES
# ---------------------------------------------------------------------------

@app.route('/run-monitor', methods=['POST'])
def run_monitor_endpoint():
    """
    Recebe lista de sites, executa Selenium e retorna hash + conteúdo de cada um.
    O n8n compara o hash com o Supabase e decide se houve mudança.

    Body:
    {
        "sites": [
            "https://cartaometrocard.com.br/sistema-metropolitano/alteracao-em-linhas/",
            "https://www.urbs.curitiba.pr.gov.br/transporte/boletim-de-transportes"
        ]
    }

    Resposta 200:
    [
      {"url": "...", "name": "SITE", "hash": "abc123", "content": "...", "ok": true,  "error": null},
      {"url": "...", "name": "SITE", "hash": null,     "content": null,  "ok": false, "error": "msg"}
    ]
    """
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


# ---------------------------------------------------------------------------
# OUTROS ENDPOINTS (inalterados)
# ---------------------------------------------------------------------------

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


@app.route('/run-vaipromo', methods=['POST'])
def run_vaipromo():
    try:
        config = request.get_json()
        if not config or 'CONSULTAS' not in config:
            return jsonify({'error': 'Body invalido, esperado {"CONSULTAS": [...]}'}), 400
        result = subprocess.run(
            [sys.executable, 'vai_promo.py'],
            input=json.dumps(config), capture_output=True, text=True, timeout=600
        )
        if result.returncode != 0:
            return jsonify({'error': 'Script failed', 'stderr': result.stderr,
                            'stdout': result.stdout, 'returncode': result.returncode}), 500
        output = result.stdout.strip()
        if not output:
            return jsonify({'error': 'Script returned empty output', 'stderr': result.stderr}), 500
        json_start = output.find('{')
        if json_start == -1:
            return jsonify({'error': 'No JSON found in output', 'output': output[-1000:], 'stderr': result.stderr}), 500
        try:
            return jsonify(json.loads(output[json_start:])), 200
        except json.JSONDecodeError as e:
            return jsonify({'error': 'Invalid JSON in output', 'json_error': str(e)}), 500
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Script timeout (10 min)'}), 504
    except Exception as e:
        return jsonify({'error': 'Unexpected error', 'details': str(e), 'type': type(e).__name__}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
