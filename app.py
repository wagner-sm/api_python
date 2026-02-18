from flask import Flask, jsonify, request
import subprocess
import json
import sys

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok'}), 200


@app.route('/run-discogs', methods=['POST'])
def run_discogs():
    """Executa o script discogs.py e retorna o resultado"""
    try:
        result = subprocess.run(
            [sys.executable, 'discogs.py'],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutos
        )

        if result.returncode != 0:
            return jsonify({
                'error': 'Script failed',
                'stderr': result.stderr
            }), 500

        output = result.stdout.strip()
        json_string = output[output.rfind('{'):]

        return jsonify(json.loads(json_string)), 200

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Script timeout (5 min)'}), 504
    except json.JSONDecodeError as e:
        return jsonify({
            'error': 'Invalid JSON output',
            'details': str(e),
            'output': result.stdout
        }), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/run-setlistfm', methods=['POST'])
def run_setlistfm():
    """Executa o script setlistfm.py e retorna o resultado"""
    try:
        result = subprocess.run(
            [sys.executable, 'setlistfm.py'],
            capture_output=True,
            text=True,
            timeout=900  # 15 minutos
        )

        if result.returncode != 0:
            return jsonify({
                'error': 'Script failed',
                'stderr': result.stderr,
                'stdout': result.stdout,
                'returncode': result.returncode
            }), 500

        output = result.stdout.strip()
        print(f"STDOUT completo: {output[:500]}...")
        print(f"STDERR: {result.stderr}")

        if not output:
            return jsonify({
                'error': 'Script returned empty output',
                'stderr': result.stderr
            }), 500

        json_start = output.rfind('{')
        if json_start == -1:
            return jsonify({
                'error': 'No JSON found in output',
                'output': output[-1000:],
                'stderr': result.stderr
            }), 500

        json_string = output[json_start:]

        try:
            parsed_json = json.loads(json_string)
            return jsonify(parsed_json), 200
        except json.JSONDecodeError as e:
            return jsonify({
                'error': 'Invalid JSON in output',
                'json_error': str(e),
                'json_string': json_string[:500],
                'full_output': output[-1000:]
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Script timeout (15 min)'}), 504
    except Exception as e:
        return jsonify({
            'error': 'Unexpected error',
            'details': str(e),
            'type': type(e).__name__
        }), 500


@app.route('/run-vaipromo', methods=['POST'])
def run_vaipromo():
    """Executa o script vai_promo.py recebendo config via body"""
    try:
        config = request.get_json()
        if not config or 'CONSULTAS' not in config:
            return jsonify({'error': 'Body inválido, esperado {"CONSULTAS": [...]}'}), 400

        result = subprocess.run(
            [sys.executable, 'vai_promo.py'],
            input=json.dumps(config),   # passa o config via stdin
            capture_output=True,
            text=True,
            timeout=600  # 10 minutos
        )

        if result.returncode != 0:
            return jsonify({
                'error': 'Script failed',
                'stderr': result.stderr,
                'stdout': result.stdout,
                'returncode': result.returncode
            }), 500

        output = result.stdout.strip()
        print(f"STDOUT completo: {output[:500]}...")
        print(f"STDERR: {result.stderr}")

        if not output:
            return jsonify({
                'error': 'Script returned empty output',
                'stderr': result.stderr
            }), 500

        json_start = output.find('{')
        if json_start == -1:
            return jsonify({
                'error': 'No JSON found in output',
                'output': output[-1000:],
                'stderr': result.stderr
            }), 500

        json_string = output[json_start:]

        try:
            parsed_json = json.loads(json_string)
            return jsonify(parsed_json), 200
        except json.JSONDecodeError as e:
            return jsonify({
                'error': 'Invalid JSON in output',
                'json_error': str(e),
                'json_string': json_string[:500],
                'full_output': output[-1000:]
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Script timeout (10 min)'}), 504
    except Exception as e:
        return jsonify({
            'error': 'Unexpected error',
            'details': str(e),
            'type': type(e).__name__
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
