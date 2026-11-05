"""
This material is based upon work supported by the United States Air Force under contract number FA8750-24-S-B079 (Prime Contractor Smart Information Flow Technologies (SIFT)).  Any opinions, findings and conclusions or recommendations expressed in this material are those of the author(s) and do not necessarily reflect the views of the United States Air Force.
 Copyright (c) 2026 RTX BBN Technologies. Licensed to US Government with unlimited rights.

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
This is distributed in the hope that it will be useful, but without any warranty, without even the implied warranty of merchantability or fitness for a particular purpose.  See the GNU General Public License for more details. https://www.gnu.org/licenses/

HLS / ABR API Blueprint

Provides endpoints to:
- Enable/disable ABR transcoding per stream
- Query ABR status
- Serve HLS playlists and segments (static file serving)
"""
import os
import re
import html
import time
import logging
import requests as http_requests
from flask import Blueprint, jsonify, request, send_from_directory, abort, Response

from app.services.abr import abr_manager, HLS_OUTPUT_DIR, HLS_SEGMENT_DURATION, HLS_LIST_SIZE

logger = logging.getLogger(__name__)

hls_bp = Blueprint('hls', __name__)

MEDIAMTX_HLS_URL = os.environ.get('MEDIAMTX_HLS_URL', 'http://127.0.0.1:8888')


def _cors(response):
    """Add CORS headers so external sites can embed our HLS streams."""
    response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
    response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Range, X-API-Key'
    response.headers['Access-Control-Expose-Headers'] = 'Content-Length, Content-Range'
    response.headers['Access-Control-Max-Age'] = '86400'
    return response


def _playlist_response(filepath, check_abr_stream=None):
    """Return a playlist as plain 200 OK, bypassing Flask Range handling.
    If check_abr_stream is set, returns 503 when ABR is not running for that stream,
    so HLS.js stops polling instead of hammering forever on a dead stream.
    Also returns 503 when the playlist file itself is stale (FFmpeg alive but hung).
    """
    # Variant playlists: return 503 when ABR has stopped.
    if check_abr_stream:
        status = abr_manager.status(check_abr_stream)
        if not status.get('running', False):
            resp = Response('Stream not active', status=503,
                            mimetype='application/vnd.apple.mpegurl')
            resp.headers['Retry-After'] = '5'
            resp.headers['Cache-Control'] = 'no-cache, no-store'
            return resp

    if not os.path.isfile(filepath):
        abort(404)

    # Also return 503 if the playlist itself hasn't been updated recently.
    # This catches "FFmpeg alive but frozen" (e.g. partial segment write).
    # Threshold: segment_duration * (list_size + 2) seconds — generous enough
    # that a single slow segment doesn't trigger this.
    try:
        stale_threshold = HLS_SEGMENT_DURATION * (HLS_LIST_SIZE + 2)
        if check_abr_stream and (time.time() - os.path.getmtime(filepath)) > stale_threshold:
            resp = Response('Playlist stale', status=503,
                            mimetype='application/vnd.apple.mpegurl')
            resp.headers['Retry-After'] = '5'
            resp.headers['Cache-Control'] = 'no-cache, no-store'
            return resp
    except OSError:
        pass

    try:
        with open(filepath, 'r') as f:
            content = f.read()
    except OSError:
        abort(404)

    resp = Response(content, status=200, mimetype='application/vnd.apple.mpegurl')
    resp.headers['Cache-Control'] = 'no-cache, no-store'
    resp.headers['Expires'] = '-1'
    return resp


def _valid_stream(name):
    return (
        bool(name)
        and len(name) <= 128
        and re.match(r'^[a-zA-Z0-9_./-]+$', name) is not None
        and '..' not in name
        and not name.startswith('/')
        and not name.endswith('/')
    )


# ------------------------------------------------------------------
# ABR management endpoints
# ------------------------------------------------------------------

@hls_bp.route('/api/streams/<path:stream_name>/abr', methods=['POST'])
def start_abr(stream_name):
    """Enable ABR HLS transcoding for a stream."""
    if not _valid_stream(stream_name):
        return jsonify({'status': 'error', 'error': 'Invalid stream name'}), 400
    result = abr_manager.start(stream_name)
    status_code = 200 if result['status'] in ('started', 'already_running') else 500
    return jsonify(result), status_code


@hls_bp.route('/api/streams/<path:stream_name>/abr', methods=['DELETE'])
def stop_abr(stream_name):
    """Disable ABR HLS transcoding for a stream."""
    if not _valid_stream(stream_name):
        return jsonify({'status': 'error', 'error': 'Invalid stream name'}), 400
    result = abr_manager.stop(stream_name)
    return jsonify(result), 200


@hls_bp.route('/api/streams/<path:stream_name>/abr/status', methods=['GET'])
def abr_status(stream_name):
    """Get ABR status for a stream."""
    if not _valid_stream(stream_name):
        return jsonify({'status': 'error', 'error': 'Invalid stream name'}), 400
    result = abr_manager.status(stream_name)
    return jsonify(result), 200


@hls_bp.route('/api/abr', methods=['GET'])
def list_abr():
    """List all active ABR transcoding processes."""
    return jsonify(abr_manager.list_active()), 200


# ------------------------------------------------------------------
# HLS file serving
# ------------------------------------------------------------------

@hls_bp.route('/hls/<path:stream_name>/master.m3u8')
def serve_master_playlist(stream_name):
    """Serve the ABR master playlist (raw m3u8, always)."""
    if not _valid_stream(stream_name):
        abort(400)
    filepath = os.path.join(HLS_OUTPUT_DIR, stream_name, 'master.m3u8')

    if not os.path.isfile(filepath):
        status = abr_manager.status(stream_name)

        if status.get('running', False) and status.get('process_alive', False):
            resp = Response('Stream starting', status=503,
                            mimetype='text/plain')
            resp.headers['Retry-After'] = '2'
            resp.headers['Cache-Control'] = 'no-cache, no-store'
            return _cors(resp)
    return _cors(_playlist_response(filepath))


@hls_bp.route('/hls/<path:stream_name>/player')
def serve_player(stream_name):
    """Embedded hls.js player page for browser viewing."""
    if not _valid_stream(stream_name):
        abort(400)
    return _serve_player_page(stream_name)


def _serve_player_page(stream_name):
    """Return an HTML page with an embedded hls.js player and full error recovery.
    
    Automatically selects the video source:
    - ABR master playlist when ABR transcoding is active
    - MediaMTX native HLS when ABR is not running
    """
    # Decide which HLS source to use
    abr_status = abr_manager.status(stream_name)
    if abr_status.get('running', False):
        m3u8_url = f'/hls/{stream_name}/master.m3u8'
        source_label = 'ABR'
    else:
        # Fall back to MediaMTX native single-bitrate HLS
        m3u8_url = f'/api/hls/proxy/{stream_name}/index.m3u8'
        source_label = 'Native'

    # Escape any user-controlled values before interpolation into HTML/JS.
    # stream_name is validated by _valid_stream() upstream, but defence-in-depth.
    safe_stream_name = html.escape(stream_name, quote=True)
    safe_m3u8_url = html.escape(m3u8_url, quote=True)
    safe_source_label = html.escape(source_label, quote=True)

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <title>HLS Player: {safe_stream_name}</title>
    <script src="/static/hls.min.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ background: #000; display: flex; flex-direction: column; height: 100vh; font-family: Arial, sans-serif; }}
        .player-container {{ flex: 1; display: flex; align-items: center; justify-content: center; position: relative; }}
        video {{ max-width: 100%; max-height: 100%; }}
        .controls {{ background: #111; padding: 8px 12px; display: flex; align-items: center; gap: 12px; color: #ccc; font-size: 13px; }}
        .controls label {{ font-weight: bold; }}
        .controls select {{ background: #222; color: #fff; border: 1px solid #444; padding: 4px 8px; border-radius: 4px; font-size: 13px; }}
        .controls .quality-info {{ margin-left: auto; font-size: 12px; color: #888; }}
        .status {{ position: absolute; top: 10px; right: 10px; padding: 4px 10px; border-radius: 4px; font-size: 12px; color: #fff; background: rgba(0,0,0,0.6); display: none; }}
        .error {{ color: #fff; font-family: Arial; padding: 20px; }}
    </style>
</head>
<body>
    <div class="player-container">
        <video id="video" controls autoplay></video>
        <div class="status" id="status"></div>
    </div>
    <div class="controls">
        <label>Quality:</label>
        <select id="quality-select"><option value="-1" selected>Auto</option></select>
        <span class="quality-info" id="quality-info">{safe_source_label} mode</span>
    </div>
    <div id="error" class="error" style="display: none;"></div>
    <script>
        var video = document.getElementById('video');
        var errorDiv = document.getElementById('error');
        var statusDiv = document.getElementById('status');
        var videoSrc = '{safe_m3u8_url}';

        if (Hls.isSupported()) {{
            var hlsConfig = {{
                debug: false,
                enableWorker: true,
                lowLatencyMode: true,
                backBufferLength: 8,
                liveBackBufferLength: 8
            }};
            var hls = new Hls(hlsConfig);
            var mediaRecoveryAttempts = 0;
            var maxMediaRecovery = 3;

            function initHls() {{
                hls.loadSource(videoSrc);
                hls.attachMedia(video);
            }}
            initHls();

            // Official hls.js workaround (issues #5306, #7127):
            // Stop loading when hidden to prevent Chrome/Firefox from pausing the media
            // element due to background-tab MSE duration updates.
            // On return, restart loading from the live edge and snap the playhead.
            document.addEventListener('visibilitychange', function() {{
                if (!hls) return;
                if (document.hidden) {{
                    hls.stopLoad();
                }} else {{
                    hls.startLoad(-1);
                    // Wait one tick for the manifest reload to register a liveSyncPosition
                    setTimeout(function() {{
                        if (hls && hls.liveSyncPosition != null) {{
                            video.currentTime = hls.liveSyncPosition;
                        }}
                        video.play().catch(function() {{}});
                    }}, 100);
                }}
            }});
            window.addEventListener('focus', function() {{
                if (!hls) return;
                // If loading was stopped (e.g. tab was hidden), restart it
                hls.startLoad(-1);
                setTimeout(function() {{
                    if (hls && hls.liveSyncPosition != null) {{
                        video.currentTime = hls.liveSyncPosition;
                    }}
                    video.play().catch(function() {{}});
                }}, 100);
            }});

            hls.on(Hls.Events.MANIFEST_PARSED, function(event, data) {{
                mediaRecoveryAttempts = 0;
                errorDiv.style.display = 'none';
                video.style.display = '';
                statusDiv.style.display = 'none';
                video.play().catch(function(e) {{ console.error('Autoplay failed:', e); }});

                var select = document.getElementById('quality-select');
                select.innerHTML = '<option value="-1" selected>Auto</option>';
                if (data.levels && data.levels.length > 1) {{
                    data.levels.forEach(function(level, idx) {{
                        var opt = document.createElement('option');
                        opt.value = idx;
                        var h = level.height || '?';
                        var bw = level.bitrate ? Math.round(level.bitrate / 1000) + 'k' : '?';
                        opt.textContent = h + 'p (' + bw + ')';
                        select.appendChild(opt);
                    }});
                    select.addEventListener('change', function() {{
                        hls.currentLevel = parseInt(this.value);
                    }});
                }}
            }});

            hls.on(Hls.Events.LEVEL_SWITCHED, function(event, data) {{
                var infoEl = document.getElementById('quality-info');
                if (infoEl && hls.levels[data.level]) {{
                    var lvl = hls.levels[data.level];
                    infoEl.textContent = 'Playing: ' + (lvl.height || '?') + 'p @ ' + Math.round(lvl.bitrate / 1000) + 'kbps';
                }}
            }});

            hls.on(Hls.Events.ERROR, function(event, data) {{
                console.warn('HLS Error:', data.type, data.details, data.fatal);
                if (data.fatal) {{
                    switch (data.type) {{
                        case Hls.ErrorTypes.NETWORK_ERROR:
                            console.log('Fatal network error, retrying...');
                            statusDiv.textContent = 'Waiting for stream source\u2026';
                            statusDiv.style.display = 'block';
                            setTimeout(function() {{
                                if (hls) hls.startLoad();
                            }}, 3000);
                            break;
                        case Hls.ErrorTypes.MEDIA_ERROR:
                            if (mediaRecoveryAttempts < maxMediaRecovery) {{
                                mediaRecoveryAttempts++;
                                console.log('Fatal media error, recovering (attempt ' + mediaRecoveryAttempts + ')...');
                                hls.recoverMediaError();
                            }} else {{
                                console.log('Media recovery exhausted, reloading stream...');
                                mediaRecoveryAttempts = 0;
                                hls.destroy();
                                hls = new Hls(hlsConfig);
                                initHls();
                            }}
                            break;
                        default:
                            console.log('Unrecoverable error, reloading stream in 3s...');
                            statusDiv.textContent = 'Reloading stream...';
                            statusDiv.style.display = 'block';
                            setTimeout(function() {{
                                hls.destroy();
                                hls = new Hls(hlsConfig);
                                statusDiv.style.display = 'none';
                                initHls();
                            }}, 3000);
                            break;
                    }}
                }}
            }});
        }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
            video.src = videoSrc;
            video.addEventListener('loadedmetadata', function() {{
                video.play().catch(function(e) {{ console.error('Autoplay failed:', e); }});
            }});
        }} else {{
            errorDiv.innerHTML = 'HLS is not supported in this browser';
            errorDiv.style.display = 'block';
            video.style.display = 'none';
        }}
    </script>
</body>
</html>"""
    resp = Response(html_body, status=200, mimetype='text/html')
    resp.headers['Cache-Control'] = 'no-cache'
    return _cors(resp)


@hls_bp.route('/hls/<path:stream_name>/v<int:variant>/index.m3u8')
def serve_variant_playlist(stream_name, variant):
    """Serve a variant (rendition) playlist. Returns 503 when ABR not running."""
    if not _valid_stream(stream_name):
        abort(400)
    filepath = os.path.join(HLS_OUTPUT_DIR, stream_name, f'v{variant}', 'index.m3u8')
    return _cors(_playlist_response(filepath, check_abr_stream=stream_name))


@hls_bp.route('/hls/<path:stream_name>/v<int:variant>/<filename>')
def serve_segment(stream_name, variant, filename):
    """Serve an HLS segment file (.ts)."""
    if not _valid_stream(stream_name):
        abort(400)
    variant_dir = os.path.join(HLS_OUTPUT_DIR, stream_name, f'v{variant}')
    if not os.path.isdir(variant_dir):
        abort(404)
    mimetype = 'video/mp2t' if filename.endswith('.ts') else 'application/octet-stream'
    resp = send_from_directory(variant_dir, filename, mimetype=mimetype)
    resp.headers['Cache-Control'] = 'public, max-age=60'
    return _cors(resp)


# ------------------------------------------------------------------
# MediaMTX HLS proxy with CORS
# ------------------------------------------------------------------
# External systems (e.g. a sensor server UI) can point VideoJS at:
#   http://<host>:3000/api/hls/proxy/<stream>/index.m3u8
# and all segment fetches stay on the same origin with CORS headers.

@hls_bp.route('/api/hls/proxy/<stream_name>/<path:filename>', methods=['GET', 'HEAD', 'OPTIONS'])
def proxy_mediamtx_hls(stream_name, filename):
    """Proxy MediaMTX HLS with CORS headers for cross-origin embedding.
    
    Optional query param: ?videoonly=1  — strips audio renditions from M3U8
    playlists (useful for muted video wall cells to avoid broken audio tracks).
    """
    if not _valid_stream(stream_name):
        return _cors(jsonify({'error': 'Invalid stream name'})), 400
    if not re.match(r'^[a-zA-Z0-9_./-]+\.(m3u8|ts|m4s|mp4)$', filename):
        return _cors(jsonify({'error': 'Invalid filename'})), 400

    # Preflight
    if request.method == 'OPTIONS':
        return _cors(Response('', status=204))

    videoonly = request.args.get('videoonly') == '1'
    upstream = f'{MEDIAMTX_HLS_URL}/{stream_name}/{filename}'
    try:
        up = http_requests.get(upstream, stream=True, timeout=30)
        if up.status_code != 200:
            return _cors(jsonify({'error': 'Stream not available'})), up.status_code

        if filename.endswith('.m3u8'):
            ct = 'application/vnd.apple.mpegurl'
            body = up.text
            rewritten = _rewrite_m3u8(body, stream_name, videoonly=videoonly)
            resp = Response(rewritten, content_type=ct)
        else:
            ct = 'video/mp2t' if filename.endswith('.ts') else 'video/mp4'
            resp = Response(up.iter_content(chunk_size=65536), content_type=ct)

        resp.headers['Cache-Control'] = 'no-cache' if filename.endswith('.m3u8') else 'public, max-age=30'
        return _cors(resp)

    except http_requests.exceptions.ConnectionError:
        return _cors(jsonify({'error': 'MediaMTX HLS not available'})), 502
    except http_requests.exceptions.Timeout:
        return _cors(jsonify({'error': 'MediaMTX HLS timeout'})), 504


def _rewrite_m3u8(body, stream_name, videoonly=False):
    """Rewrite relative/absolute segment and playlist URLs to route through our proxy.
    Handles both plain segment lines and URI= attributes in #EXT-X-MEDIA tags.
    When videoonly=True, strips all audio renditions and cleans the CODECS attribute
    so that browsers with H.265 hardware decode can play back without broken audio tracks.
    """
    def _proxy_url(fname):
        fname = fname.lstrip('/')
        if fname.startswith('http'):
            fname = fname.rsplit('/', 1)[-1]
        return f'/api/hls/proxy/{stream_name}/{fname}'

    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append(line)
            continue

        # Strip audio rendition tags when videoonly is requested
        if videoonly and stripped.startswith('#EXT-X-MEDIA') and 'TYPE=AUDIO' in stripped:
            continue

        if stripped.startswith('#'):
            # Strip AUDIO group reference and non-video codecs from #EXT-X-STREAM-INF
            if videoonly and stripped.startswith('#EXT-X-STREAM-INF'):
                line = re.sub(r',?AUDIO="[^"]+"', '', line)
                # Keep only the first (video) codec in CODECS="a,b,c" → CODECS="a"
                line = re.sub(
                    r'(CODECS=")([^"]+)(")',
                    lambda m: m.group(1) + m.group(2).split(',')[0] + m.group(3),
                    line, flags=re.IGNORECASE
                )
            # Rewrite URI="..." attributes (EXT-X-MEDIA, EXT-X-I-FRAME-STREAM-INF, etc.)
            line = re.sub(
                r'URI="([^"]+)"',
                lambda m: f'URI="{_proxy_url(m.group(1))}"',
                line
            )
            lines.append(line)
        elif stripped.startswith('http'):
            lines.append(_proxy_url(stripped))
        else:
            lines.append(_proxy_url(stripped))
    return '\n'.join(lines) + '\n'
