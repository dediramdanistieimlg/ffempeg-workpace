from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import os, subprocess, uuid, shutil

app = Flask(__name__)
CORS(app) # PENTING: Agar Lovable (port 5173) bisa akses API ini (port 5000)

app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'
app.config['AMBIENT_FOLDER'] = 'ambient'
app.config['TEMP_FOLDER'] = 'temp'
app.config['MAX_CONTENT_LENGTH'] = 2000 * 1024 * 1024

for folder in [app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER'], app.config['TEMP_FOLDER']]:
    os.makedirs(folder, exist_ok=True)

def cleanup_temp():
    for f in os.listdir(app.config['TEMP_FOLDER']):
        os.remove(os.path.join(app.config['TEMP_FOLDER'], f))

def get_duration(filepath):
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', filepath]
    try:
        return float(subprocess.run(cmd, capture_output=True, text=True).stdout.strip())
    except:
        return 0

@app.route('/')
def index():
    uploads = []
    for f in sorted(os.listdir(app.config['UPLOAD_FOLDER']), reverse=True):
        path = os.path.join(app.config['UPLOAD_FOLDER'], f)
        if os.path.isfile(path):
            size = os.path.getsize(path) / (1024 * 1024)
            dur = get_duration(path)
            uploads.append({'name': f, 'size': f'{size:.1f} MB', 'duration': f'{int(dur//60):02d}:{int(dur%60):02d}'})
    return jsonify({'uploads': uploads})

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    ext = os.path.splitext(file.filename)[1]
    unique_name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    file.save(path)
    
    size = os.path.getsize(path) / (1024 * 1024)
    duration = get_duration(path)
    return jsonify({
        'success': True, 'name': unique_name, 'original_name': file.filename,
        'size': f'{size:.1f} MB', 'duration': f'{int(duration//60):02d}:{int(duration%60):02d}'
    })

@app.route('/process', methods=['POST'])
def process():
    try:
        data = request.json
        mode = data.get('mode', 'loop')
        input_file = data.get('input_file')
        if not input_file: return jsonify({'error': 'No input file'}), 400
        
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], input_file)
        if not os.path.exists(input_path): return jsonify({'error': 'File not found'}), 400
        
        output_name = f"{uuid.uuid4().hex}.{data.get('output_format', 'mp4')}"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_name)
        cleanup_temp()
        
        # === LOGIKA LOOPING ===
        if mode == 'loop':
            n = int(data.get('loop_count', 3))
            speed = float(data.get('speed', 1.0))
            volume = int(data.get('volume', 100))
            crossfade = float(data.get('crossfade', 0.5))
            
            cmd = ['ffmpeg']
            for _ in range(n): cmd.extend(['-i', input_path])
            
            filters, afilters = [], []
            for i in range(n):
                vf = f'[{i}:v]setpts={1/speed}*PTS[v{i}]' if speed != 1.0 else f'[{i}:v]copy[v{i}]'
                af = f'[{i}:a]atempo={speed}[a{i}]' if speed != 1.0 else f'[{i}:a]copy[a{i}]'
                filters.append(vf); afilters.append(af)
                
            filters.append(f'{"".join([f"[v{i}]" for i in range(n)])}concat=n={n}:v=1:a=0[outv]')
            afilters.append(f'{"".join([f"[a{i}]" for i in range(n)])}concat=n={n}:v=0:a=1[outa]')
            
            af_str = f'volume={volume/100}'
            if crossfade > 0: af_str += f',afade=t=out:st={get_duration(input_path)*n-crossfade}:d={crossfade}'
            
            cmd.extend(['-filter_complex', ';'.join(filters+afilters), '-map', '[outv]', '-map', '[outa]',
                        '-af', af_str, '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', str(data.get('crf', 23)),
                        '-c:a', 'aac', '-b:a', '128k', '-y', output_path])
            
        # === LOGIKA SLEEP FADE ===
        elif mode == 'sleep_fade':
            n = int(data.get('loop_count', 10))
            speed = float(data.get('speed', 1.0))
            volume = int(data.get('volume', 80))
            fade_min = int(data.get('sleep_fade_minutes', 30))
            
            cmd = ['ffmpeg']
            for _ in range(n): cmd.extend(['-i', input_path])
            
            filters, afilters = [], []
            for i in range(n):
                vf = f'[{i}:v]setpts={1/speed}*PTS[v{i}]' if speed != 1.0 else f'[{i}:v]copy[v{i}]'
                af = f'[{i}:a]atempo={speed}[a{i}]' if speed != 1.0 else f'[{i}:a]copy[a{i}]'
                filters.append(vf); afilters.append(af)
                
            filters.append(f'{"".join([f"[v{i}]" for i in range(n)])}concat=n={n}:v=1:a=0[outv]')
            afilters.append(f'{"".join([f"[a{i}]" for i in range(n)])}concat=n={n}:v=0:a=1[outa]')
            
            total_dur = get_duration(input_path) * n
            fade_sec = min(fade_min * 60, total_dur - 1)
            af_str = f'volume={volume/100},afade=t=out:st={total_dur-fade_sec}:d={fade_sec}'
            
            cmd.extend(['-filter_complex', ';'.join(filters+afilters), '-map', '[outv]', '-map', '[outa]',
                        '-af', af_str, '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', str(data.get('crf', 23)),
                        '-c:a', 'aac', '-b:a', '128k', '-y', output_path])

        # === LOGIKA AMBIENT MIX ===
        elif mode == 'ambient_mix':
            amb_type = data.get('ambient_type', 'rain')
            amb_vol = int(data.get('ambient_volume', 30))
            orig_vol = int(data.get('volume', 100))
            n = int(data.get('loop_count', 1))
            
            amb_file = os.path.join(app.config['AMBIENT_FOLDER'], f'{amb_type}.mp3')
            if not os.path.exists(amb_file): return jsonify({'error': 'Ambient not found'}), 400
            
            cmd = ['ffmpeg']
            for _ in range(n): cmd.extend(['-i', input_path])
            cmd.extend(['-stream_loop', '-1', '-i', amb_file])
            
            filters, afilters = [], []
            for i in range(n):
                filters.append(f'[{i}:v]copy[v{i}]')
                afilters.append(f'[{i}:a]volume={orig_vol/100}[a{i}]')
                
            filters.append(f'{"".join([f"[v{i}]" for i in range(n)])}concat=n={n}:v=1:a=0[outv]')
            afilters.append(f'{"".join([f"[a{i}]" for i in range(n)])}concat=n={n}:v=0:a=1[concata]')
            afilters.append(f'[concata]volume={orig_vol/100}[a1]')
            afilters.append(f'[{n}:a]volume={amb_vol/100}[a2]')
            afilters.append(f'[a1][a2]amix=inputs=2:duration=first:dropout_transition=5[outa]')
            
            cmd.extend(['-filter_complex', ';'.join(filters+afilters), '-map', '[outv]', '-map', '[outa]',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', str(data.get('crf', 23)),
                        '-c:a', 'aac', '-b:a', '128k', '-shortest', '-y', output_path])

        # === LOGIKA PRESET ===
        elif mode == 'preset':
            preset = data.get('preset', 'sleep')
            presets = {
                'sleep': {'loop_count': 10, 'volume': 80, 'sleep_fade_minutes': 30, 'speed': 1.0},
                'deep_sleep': {'loop_count': 20, 'volume': 60, 'sleep_fade_minutes': 45, 'speed': 0.9},
                'study': {'loop_count': 5, 'volume': 70, 'ambient_type': 'rain', 'ambient_volume': 40, 'speed': 1.0},
                'focus': {'loop_count': 8, 'volume': 50, 'ambient_type': 'bowl', 'ambient_volume': 30, 'speed': 1.0},
                'relax': {'loop_count': 3, 'volume': 85, 'ambient_type': 'ocean', 'ambient_volume': 25, 'speed': 0.9},
                'meditation': {'loop_count': 5, 'volume': 75, 'ambient_type': 'bowl', 'ambient_volume': 35, 'speed': 0.85}
            }
            data.update(presets.get(preset, presets['sleep']))
            if preset in ['sleep', 'deep_sleep']: mode = 'sleep_fade'
            else: mode = 'ambient_mix'
            return process() # Re-call function with updated mode
        
        # === FALLBACK / BASIC ===
        else:
            cmd = ['ffmpeg', '-i', input_path, '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', str(data.get('crf', 23)), '-c:a', 'aac', '-y', output_path]

        subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        input_size = os.path.getsize(input_path) / (1024 * 1024)
        output_size = os.path.getsize(output_path) / (1024 * 1024)
        output_duration = get_duration(output_path)
        
        return jsonify({
            'success': True, 'output': output_name,
            'input_size': f'{input_size:.1f} MB', 'output_size': f'{output_size:.1f} MB',
            'duration': f'{int(output_duration//60):02d}:{int(output_duration%60):02d}'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<filename>')
def download(filename):
    return send_file(os.path.join(app.config['OUTPUT_FOLDER'], filename), as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
