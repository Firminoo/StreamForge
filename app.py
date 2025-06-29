import sys
import os
import uuid
import threading
import json
from flask import Flask, request, jsonify, render_template, send_from_directory

import yt_dlp

# --- CONFIGURAÇÃO DA APLICAÇÃO FLASK ---
app = Flask(__name__)

# Define a pasta onde os arquivos baixados serão armazenados
DOWNLOAD_FOLDER = os.path.join(os.getcwd(), "downloads")
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# Dicionário para rastrear o status das tarefas de download em memória.
# Em uma aplicação de produção, seria melhor usar um banco de dados ou Redis.
tasks = {}


# --- LÓGICA DE DOWNLOAD (ADAPTADA DO SEU CÓDIGO) ---

def run_download_task(task_id, url, download_type):
    """
    Esta função executa o download usando yt_dlp em uma thread separada.
    """
    
    # Hook para ser chamado pelo yt-dlp a cada atualização de status
    def progress_hook(d):
        if d['status'] == 'downloading':
            # Extrai o progresso e atualiza o status da tarefa
            progress_str = d.get('_percent_str', '0.0%').replace('%', '')
            try:
                progress = float(progress_str)
                tasks[task_id]['status'] = 'downloading'
                tasks[task_id]['progress'] = progress
                tasks[task_id]['details'] = f"Baixando {d.get('filename', '')}..."
            except ValueError:
                pass # Ignora se não for um número
        elif d['status'] == 'finished':
            tasks[task_id]['status'] = 'processing'
            tasks[task_id]['details'] = 'Processando o arquivo (conversão, etc)...'


    try:
        tasks[task_id] = {'status': 'starting', 'progress': 0, 'details': 'Iniciando download...'}
        
        output_template = os.path.join(DOWNLOAD_FOLDER, '%(title)s [%(id)s].%(ext)s')
        
        ydl_opts = {
            'outtmpl': output_template,
            'progress_hooks': [progress_hook],
            'noplaylist': True, # Por simplicidade, vamos baixar apenas vídeos individuais
        }

        if download_type == 'audio':
            ydl_opts['format'] = 'bestaudio/best'
            # Pós-processador para converter para MP3 e embutir a thumbnail
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }, {
                'key': 'EmbedThumbnail'
            }]
        else: # 'video'
            ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

        # Inicia o download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Prepara o nome do arquivo final
            final_filename = ydl.prepare_filename(info)
            if download_type == 'audio':
                # O pós-processador muda a extensão para mp3
                base, _ = os.path.splitext(final_filename)
                final_filename = base + '.mp3'

            # Pega apenas o nome do arquivo, não o caminho completo
            base_filename = os.path.basename(final_filename)

            # Atualiza a tarefa como concluída
            tasks[task_id]['status'] = 'success'
            tasks[task_id]['filename'] = base_filename
            tasks[task_id]['title'] = info.get('title', 'Título Desconhecido')
            tasks[task_id]['details'] = 'Download concluído com sucesso!'

    except Exception as e:
        print(f"Erro no download: {e}")
        tasks[task_id]['status'] = 'error'
        tasks[task_id]['details'] = f"Ocorreu um erro: {str(e)}"


# --- ROTAS DA API E INTERFACE ---

@app.route('/')
def index():
    """ Rota principal que renderiza a página HTML. """
    return render_template('index.html')

@app.route('/start-download', methods=['POST'])
def start_download():
    """
    Rota para iniciar um novo download. Recebe a URL e o tipo via POST.
    """
    data = request.json
    url = data.get('url')
    download_type = data.get('type', 'audio')

    if not url:
        return jsonify({'status': 'error', 'details': 'URL não fornecida'}), 400

    # Gera um ID único para a tarefa
    task_id = str(uuid.uuid4())
    
    # Cria e inicia uma nova thread para o download
    thread = threading.Thread(target=run_download_task, args=(task_id, url, download_type))
    thread.start()

    # Retorna o ID da tarefa para que o frontend possa verificar o status
    return jsonify({'status': 'queued', 'task_id': task_id})

@app.route('/status/<task_id>')
def task_status(task_id):
    """ Rota para verificar o status de uma tarefa de download. """
    task = tasks.get(task_id)
    if not task:
        return jsonify({'status': 'not_found'}), 404
    return jsonify(task)

@app.route('/download/<path:filename>')
def download_file(filename):
    """ Rota para servir o arquivo finalizado para o usuário. """
    return send_from_directory(DOWNLOAD_FOLDER, filename, as_attachment=True)


if __name__ == "__main__":
    print(f"Arquivos serão salvos em: {DOWNLOAD_FOLDER}")
    # O modo debug NÃO é recomendado para produção!
    app.run(host='0.0.0.0', port=5000, debug=True)