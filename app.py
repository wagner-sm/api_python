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
    """
    Executa o script discogs.py e retorna o resultado
    """
    try:
        # Executar o script Python
        result = subprocess.run(
            [sys.executable, 'discogs.py'],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutos de timeout
        )
        
        if result.returncode != 0:
            return jsonify({
                'error': 'Script failed',
                'stderr': result.stderr
            }), 500
        
        # Extrair JSON do output (última linha)
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
    """
    Executa o script setlistfm.py e retorna o resultado
    Espera receber JSON com parâmetros necessários
    """
    try:
        # Executar o script Python
        result = subprocess.run(
            [sys.executable, 'setlistfm.py'],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutos de timeout
        )
        
        if result.returncode != 0:
            return jsonify({
                'error': 'Script failed',
                'stderr': result.stderr
            }), 500
        
        # Extrair JSON do output (última linha)
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
