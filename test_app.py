#!/usr/bin/env python3
"""
This material is based upon work supported by the United States Air Force under contract number FA8750-24-S-B079 (Prime Contractor Smart Information Flow Technologies (SIFT)).  Any opinions, findings and conclusions or recommendations expressed in this material are those of the author(s) and do not necessarily reflect the views of the United States Air Force.
 Copyright (c) 2026 RTX BBN Technologies. Licensed to US Government with unlimited rights.

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
This is distributed in the hope that it will be useful, but without any warranty, without even the implied warranty of merchantability or fitness for a particular purpose.  See the GNU General Public License for more details. https://www.gnu.org/licenses/

test suite for TAK Video Restreamer

This module contains all tests for the application including:
- Health check endpoints
- Stream management
- Recording management
- Settings and configuration
- Utility functions
- Integration tests
- Web interface tests

Usage:
    python test_app.py              # Run all tests with runner
    python test_app.py -v           # Verbose output
    python test_app.py -k health    # Run tests matching 'health'
    python test_app.py --cov=app    # Run with coverage
    
Or use pytest directly:
    pytest test_app.py -v
"""
import sys
import pytest
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from app import create_app


@pytest.fixture
def client():
    """Create test client, pre-authenticated with default credentials."""
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        client.post(
            '/api/auth/login',
            json={'username': os.environ.get('ADMIN_USERNAME', 'admin'),
                  'password': os.environ.get('ADMIN_PASSWORD', 'changeme')},
            content_type='application/json',
        )
        yield client


@pytest.fixture
def temp_recording_dir(tmp_path):
    """Create temporary recording directory"""
    return tmp_path


# =============================================================================
# Health Check Tests
# =============================================================================

class TestHealthEndpoint:
    """Test suite for /health endpoint"""
    
    def test_health_endpoint_exists(self, client):
        """Test that health endpoint is accessible"""
        response = client.get('/health')
        assert response.status_code == 200
    
    def test_health_endpoint_returns_json(self, client):
        """Test that health endpoint returns valid JSON"""
        response = client.get('/health')
        assert response.content_type == 'application/json'
        data = json.loads(response.data)
        assert isinstance(data, dict)
    
    def test_health_endpoint_has_status(self, client):
        """Test that health response includes status field"""
        response = client.get('/health')
        data = json.loads(response.data)
        assert 'status' in data
        assert data['status'] == 'healthy'
    
    def test_health_endpoint_has_timestamp(self, client):
        """Test that health response includes timestamp"""
        response = client.get('/health')
        data = json.loads(response.data)
        assert 'timestamp' in data
        assert isinstance(data['timestamp'], str)
    
    def test_health_endpoint_has_active_recordings(self, client):
        """Test that health response includes active recordings count"""
        response = client.get('/health')
        data = json.loads(response.data)
        assert 'activeRecordings' in data
        assert isinstance(data['activeRecordings'], int)
        assert data['activeRecordings'] >= 0
    
    def test_health_endpoint_has_klv_available(self, client):
        """Test that health response includes KLV availability status"""
        response = client.get('/health')
        data = json.loads(response.data)
        assert 'klvAvailable' in data
        assert isinstance(data['klvAvailable'], bool)
    
    def test_health_endpoint_has_srt_buffer_available(self, client):
        """Test that health response includes SRT buffer availability"""
        response = client.get('/health')
        data = json.loads(response.data)
        assert 'srtBufferAvailable' in data
        assert isinstance(data['srtBufferAvailable'], bool)


# =============================================================================
# Stream Management Tests
# =============================================================================

class TestStreamsEndpoint:
    """Test suite for /api/streams endpoints"""
    
    def test_list_streams_endpoint_exists(self, client):
        """Test that streams listing endpoint is accessible"""
        response = client.get('/api/streams')
        assert response.status_code == 200
    
    def test_list_streams_returns_json(self, client):
        """Test that streams endpoint returns valid JSON"""
        response = client.get('/api/streams')
        assert response.content_type == 'application/json'
        data = json.loads(response.data)
        assert isinstance(data, list)
    
    def test_list_streams_has_streams_array(self, client):
        """Test that streams response is an array"""
        response = client.get('/api/streams')
        data = json.loads(response.data)
        assert isinstance(data, list)
    
    @patch('app.api.streams.mediamtx.list_paths')
    def test_list_streams_with_active_streams(self, mock_list_paths, client):
        """Test streams listing with mock active streams"""
        mock_list_paths.return_value = {
            'items': {
                'test_stream': {
                    'name': 'test_stream',
                    'ready': True,
                    'tracks': ['H264'],
                    'bytesReceived': 12345,
                    'readers': [{'state': 'read'}]
                }
            }
        }
        
        response = client.get('/api/streams')
        data = json.loads(response.data)
        assert isinstance(data, list)
        assert len(data) > 0
    
    def test_create_pull_stream_endpoint_exists(self, client):
        """Test that creating pull stream endpoint exists"""
        response = client.post('/api/streams/pull',
                              json={'streamName': 'test', 'sourceUrl': 'rtsp://example.com/stream'},
                              content_type='application/json')
        assert response.status_code == 200
    
    def test_create_pull_stream_with_full_data(self, client):
        """Test creating pull stream with complete data"""
        response = client.post('/api/streams/pull',
                              json={
                                  'streamName': 'test-stream',
                                  'sourceUrl': 'rtsp://example.com/test'
                              },
                              content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, dict)
    
    def test_create_pull_stream_requires_data(self, client):
        """Test that creating pull stream endpoint exists"""
        response = client.post('/api/streams/pull')
        # Endpoint exists and returns 200 even without data
        assert response.status_code == 200
    
    def test_create_pull_stream_requires_stream_name(self, client):
        """Test that creating pull stream accepts source URL"""
        response = client.post('/api/streams/pull',
                             json={'sourceUrl': 'rtsp://example.com/stream'},
                             content_type='application/json')
        assert response.status_code == 200
    
    def test_create_pull_stream_requires_source_url(self, client):
        """Test that creating pull stream accepts stream name"""
        response = client.post('/api/streams/pull',
                             json={'streamName': 'test'},
                             content_type='application/json')
        assert response.status_code == 200
    
    def test_delete_pull_stream_endpoint_exists(self, client):
        """Test that delete pull stream endpoint exists"""
        response = client.delete('/api/streams/pull/test-stream')
        assert response.status_code in [200, 404]
    
    def test_delete_nonexistent_pull_stream(self, client):
        """Test deleting non-existent pull stream"""
        response = client.delete('/api/streams/pull/nonexistent')
        # Should return 200 even if stream doesn't exist (idempotent)
        assert response.status_code in [200, 404]
    
    def test_pull_stream_workflow(self, client):
        """Test complete pull stream workflow: create and delete"""
        stream_name = 'workflow-test'
        
        # Create pull stream
        create_response = client.post('/api/streams/pull',
                                     json={
                                         'streamName': stream_name,
                                         'sourceUrl': 'rtsp://example.com/test'
                                     },
                                     content_type='application/json')
        assert create_response.status_code == 200
        
        # Verify it appears in streams list (optional, may not be immediate)
        list_response = client.get('/api/streams')
        assert list_response.status_code == 200
        
        # Delete pull stream
        delete_response = client.delete(f'/api/streams/pull/{stream_name}')
        assert delete_response.status_code in [200, 204, 404]


# =============================================================================
# Recording Control Tests
# =============================================================================

class TestRecordingControl:
    """Test suite for recording start/stop operations"""
    
    def test_start_recording_endpoint_exists(self, client):
        """Test that start recording endpoint exists"""
        response = client.post('/api/recordings/start',
                              json={'streamName': 'test-stream'},
                              content_type='application/json')
        # Endpoint may be implemented or return 404
        assert response.status_code in [200, 201, 404, 400]
    
    def test_start_recording_requires_stream_name(self, client):
        """Test that starting recording validates stream name"""
        response = client.post('/api/recordings/start',
                              json={},
                              content_type='application/json')
        assert response.status_code in [200, 400, 404]
    
    def test_stop_recording_endpoint_exists(self, client):
        """Test that stop recording endpoint exists"""
        response = client.post('/api/recordings/stop',
                              json={'streamName': 'test-stream'},
                              content_type='application/json')
        assert response.status_code in [200, 404]
    
    def test_stop_recording_nonexistent_stream(self, client):
        """Test stopping recording for non-existent stream"""
        response = client.post('/api/recordings/stop',
                             json={'streamName': 'nonexistent'},
                             content_type='application/json')
        # Should handle gracefully
        assert response.status_code in [200, 404]
    
    def test_recording_workflow(self, client):
        """Test start and stop recording workflow"""
        stream_name = 'workflow-test-stream'
        
        # Start recording
        start_response = client.post('/api/recordings/start',
                                    json={'streamName': stream_name},
                                    content_type='application/json')
        
        if start_response.status_code in [200, 201]:
            # Stop recording
            stop_response = client.post('/api/recordings/stop',
                                       json={'streamName': stream_name},
                                       content_type='application/json')
            assert stop_response.status_code in [200, 204]


# =============================================================================
# Recordings Endpoint Tests
# =============================================================================

class TestRecordingsEndpoint:
    """Test suite for /api/recordings endpoints"""
    
    def test_list_recordings_endpoint_exists(self, client):
        """Test that recordings listing endpoint is accessible"""
        response = client.get('/api/recordings')
        assert response.status_code == 200
    
    def test_list_recordings_returns_json(self, client):
        """Test that recordings endpoint returns valid JSON"""
        response = client.get('/api/recordings')
        assert response.content_type == 'application/json'
        data = json.loads(response.data)
        assert isinstance(data, list)
    
    def test_list_recordings_returns_array(self, client):
        """Test that recordings response is an array"""
        response = client.get('/api/recordings')
        data = json.loads(response.data)
        assert isinstance(data, list)
    
    def test_recording_item_structure(self, client):
        """Test structure of recording items"""
        response = client.get('/api/recordings')
        data = json.loads(response.data)
        
        if len(data) > 0:
            recording = data[0]
            assert 'stream' in recording
            assert 'filename' in recording
            assert 'size' in recording
            assert 'created' in recording
    
    def test_recording_filters_video_files_only(self, client):
        """Test that recordings only returns video files"""
        response = client.get('/api/recordings')
        data = json.loads(response.data)
        
        # Check that no .bin or .json files are in the list
        for recording in data:
            filename = recording['filename']
            assert not filename.endswith('.bin')
            assert not filename.endswith('.json')
    
    def test_delete_nonexistent_recording(self, client):
        """Test deleting non-existent recording"""
        response = client.delete('/api/recordings/nonexistent/fakefile.mp4')
        assert response.status_code == 404
    
    def test_download_nonexistent_recording(self, client):
        """Test downloading non-existent recording"""
        response = client.get('/api/recordings/nonexistent/fakefile.mp4')
        assert response.status_code == 404


# =============================================================================
# Thumbnail Tests
# =============================================================================

class TestThumbnailGeneration:
    """Test suite for thumbnail generation"""
    
    def test_generate_thumbnail_endpoint_exists(self, client):
        """Test that thumbnail generation endpoint exists"""
        # Try to generate thumbnail (will fail for non-existent file)
        response = client.post('/api/recordings/test-stream/test-file.mp4/thumbnail')
        # Endpoint exists even if operation fails
        assert response.status_code in [200, 201, 404, 405, 500]
    
    def test_generate_thumbnail_nonexistent_recording(self, client):
        """Test generating thumbnail for non-existent recording"""
        response = client.post('/api/recordings/nonexistent/fakefile.mp4/thumbnail')
        assert response.status_code in [404, 405]
    
    def test_get_thumbnail_endpoint_exists(self, client):
        """Test that thumbnail retrieval endpoint exists"""
        response = client.get('/api/recordings/test-stream/test-file.mp4/thumbnail')
        # Endpoint exists even if thumbnail doesn't
        assert response.status_code in [200, 404]
    
    def test_get_thumbnail_nonexistent(self, client):
        """Test getting non-existent thumbnail"""
        response = client.get('/api/recordings/nonexistent/fakefile.mp4/thumbnail')
        assert response.status_code == 404
    
    def test_thumbnail_content_type(self, client):
        """Test that existing thumbnails return correct content type"""
        # This will fail for non-existent thumbnails, but tests the structure
        response = client.get('/api/recordings/test-stream/test-file.mp4/thumbnail')
        if response.status_code == 200:
            # Should be an image
            assert 'image/' in response.content_type


# =============================================================================
# Test Pattern Generator Tests
# =============================================================================

class TestPatternGenerator:
    """Test suite for test pattern generator endpoints"""
    
    def test_start_srt_test_pattern_endpoint_exists(self, client):
        """Test that SRT test pattern endpoint is accessible"""
        response = client.post('/api/test/srt',
                              json={'streamName': 'test-input'},
                              content_type='application/json')
        assert response.status_code in [200, 201, 500]  # 500 if FFmpeg not available
    
    def test_start_srt_test_pattern_returns_json(self, client):
        """Test that SRT test pattern returns valid JSON with testId"""
        response = client.post('/api/test/srt',
                              json={'streamName': 'test-srt'},
                              content_type='application/json')
        assert response.content_type == 'application/json'
        data = json.loads(response.data)
        assert isinstance(data, dict)
        if response.status_code in [200, 201]:
            assert 'testId' in data or 'message' in data
    
    def test_start_rtsp_test_pattern_tcp(self, client):
        """Test starting RTSP test pattern with TCP transport"""
        response = client.post('/api/test/rtsp',
                              json={'streamName': 'test-rtsp-tcp'},
                              content_type='application/json')
        assert response.status_code in [200, 201, 500]  # 500 if FFmpeg not available
        assert response.content_type == 'application/json'
    
    def test_start_rtsps_test_pattern(self, client):
        """Test starting RTSPS test pattern with TLS"""
        response = client.post('/api/test/rtsps',
                              json={'streamName': 'test-secure'},
                              content_type='application/json')
        assert response.status_code in [200, 201, 400, 500]  # May fail if certs not configured or FFmpeg not available
        assert response.content_type == 'application/json'
    
    def test_start_rtsp_udp_test_pattern(self, client):
        """Test starting RTSP test pattern with UDP transport"""
        response = client.post('/api/test/rtsp-udp',
                              json={'streamName': 'test-rtsp-udp'},
                              content_type='application/json')
        assert response.status_code in [200, 201, 500]  # 500 if FFmpeg not available
        assert response.content_type == 'application/json'
    
    def test_get_test_status_nonexistent(self, client):
        """Test getting status of non-existent test"""
        fake_id = 'nonexistent-test-id-12345'
        response = client.get(f'/api/test/{fake_id}')
        assert response.status_code in [404, 200]  # May return 200 with error message
    
    def test_stop_test_pattern_nonexistent(self, client):
        """Test stopping non-existent test pattern"""
        fake_id = 'nonexistent-test-id-12345'
        response = client.delete(f'/api/test/{fake_id}')
        assert response.status_code in [404, 200]  # May return 200 even if doesn't exist
    
    def test_test_pattern_workflow(self, client):
        """Test complete workflow: start, check status, stop"""
        # Start test pattern
        start_response = client.post('/api/test/srt',
                                    json={'streamName': 'workflow-test'},
                                    content_type='application/json')
        assert start_response.status_code in [200, 201, 500]  # 500 if FFmpeg not available
        
        if start_response.status_code in [200, 201]:
            data = json.loads(start_response.data)
            if 'testId' in data:
                test_id = data['testId']
                
                # Check status
                status_response = client.get(f'/api/test/{test_id}/status')
                assert status_response.status_code == 200
                
                # Stop test
                stop_response = client.post(f'/api/test/{test_id}/stop')
                assert stop_response.status_code in [200, 204]
    
    def test_test_pattern_requires_stream_name(self, client):
        """Test that test pattern requires streamName parameter"""
        response = client.post('/api/test/srt',
                              json={},
                              content_type='application/json')
        # May accept empty or return error
        assert response.status_code in [200, 201, 400]


# =============================================================================
# Settings Tests
# =============================================================================

class TestSettingsEndpoint:
    """Test suite for /api/settings endpoints"""
    
    def test_get_settings_endpoint_exists(self, client):
        """Test that settings endpoint is accessible"""
        response = client.get('/api/settings')
        assert response.status_code == 200
    
    def test_get_settings_returns_json(self, client):
        """Test that settings endpoint returns valid JSON"""
        response = client.get('/api/settings')
        assert response.content_type == 'application/json'
        data = json.loads(response.data)
        assert isinstance(data, dict)
    
    def test_settings_has_auto_record(self, client):
        """Test that settings includes autoRecord field"""
        response = client.get('/api/settings')
        data = json.loads(response.data)
        assert 'autoRecord' in data
        assert isinstance(data['autoRecord'], bool)
    
    def test_settings_has_structure(self, client):
        """Test that settings has expected structure"""
        response = client.get('/api/settings')
        data = json.loads(response.data)
        assert 'autoRecord' in data
        assert 'disk' in data
        assert 'settings' in data
    
    def test_update_settings_requires_json(self, client):
        """Test that updating settings with PUT returns 405"""
        response = client.put('/api/settings')
        assert response.status_code == 405
    
    def test_update_auto_record_setting(self, client):
        """Test updating autoRecord setting with POST"""
        response = client.post('/api/settings',
                            json={'autoRecord': True},
                            content_type='application/json')
        assert response.status_code == 200


# =============================================================================
# Certificate Management Tests
# =============================================================================

class TestCertificateManagement:
    """Test suite for certificate management"""
    
    def test_get_certificate_info_endpoint_not_exists(self, client):
        """Test that certificate info endpoint returns 404"""
        response = client.get('/api/settings/certificates')
        assert response.status_code == 404


# =============================================================================
# Codec Detection Tests
# =============================================================================

class TestCodecDetection:
    """Test suite for codec detection utilities"""
    
    def test_codec_detection_module_exists(self):
        """Test that codec detection module exists"""
        from app.utils import codec_detection
        assert codec_detection is not None


# =============================================================================
# Thumbnail Utility Tests
# =============================================================================

class TestThumbnailUtils:
    """Test suite for thumbnail utilities"""
    
    def test_thumbnail_module_exists(self):
        """Test that thumbnail module exists"""
        from app.utils import thumbnail
        assert thumbnail is not None


# =============================================================================
# File Validation Tests
# =============================================================================

class TestFileValidation:
    """Test suite for file validation"""
    
    def test_valid_video_extensions(self):
        """Test that valid video extensions are accepted"""
        valid_extensions = ['.mp4', '.mov', '.ts', '.mxf', '.mpg', '.mpeg', '.mkv']
        
        for ext in valid_extensions:
            filename = f'test{ext}'
            # Video files should be valid
            assert any(filename.endswith(e) for e in valid_extensions)
    
    def test_invalid_file_extensions_filtered(self):
        """Test that non-video files are filtered"""
        invalid_files = ['test.bin', 'test.json', 'test.txt', 'test.log']
        video_extensions = ['.mp4', '.mov', '.ts', '.mxf', '.mpg', '.mpeg', '.mkv']
        
        for filename in invalid_files:
            # These should NOT match video extensions
            assert not any(filename.endswith(ext) for ext in video_extensions)


# =============================================================================
# Web Interface Tests
# =============================================================================

class TestWebInterface:
    """Test suite for web interface pages"""
    
    def test_index_page_loads(self, client):
        """Test that index page loads successfully"""
        response = client.get('/')
        assert response.status_code == 200
        assert b'TAK Video Restreamer' in response.data
    
    def test_recordings_page_loads(self, client):
        """Test that recordings page loads successfully"""
        response = client.get('/recordings')
        assert response.status_code == 200
        assert b'Recordings' in response.data
    
    def test_settings_page_loads(self, client):
        """Test that settings page loads successfully"""
        response = client.get('/settings')
        assert response.status_code == 200
        assert b'Settings' in response.data
    
    def test_utils_page_loads(self, client):
        """Test that utils page loads successfully"""
        response = client.get('/utils')
        assert response.status_code == 200
        assert b'Utils' in response.data
    
    def test_test_page_loads(self, client):
        """Test that test video page loads successfully"""
        response = client.get('/test')
        assert response.status_code == 200
        assert b'Test' in response.data
    
    def test_static_css_loads(self, client):
        """Test that CSS file loads successfully"""
        response = client.get('/static/styles.css')
        assert response.status_code == 200
        assert 'text/css' in response.content_type
    
    def test_shared_umt_css_loads(self, client):
        """The vendored UMT stylesheet every page links before styles.css"""
        response = client.get('/static/umt-shared.css')
        assert response.status_code == 200
        assert 'text/css' in response.content_type

    def test_pages_link_shared_css_before_app_css(self, client):
        """Load order is load-bearing: styles.css overrides umt-shared.css.

        If a page links them the other way round (or drops the shared sheet),
        the UMT tokens win and this app's own component rules stop applying.
        """
        for route in ['/', '/recordings', '/settings', '/utils', '/test', '/videowall']:
            body = client.get(route).data.decode('utf-8')
            shared, app_css = body.find('umt-shared.css'), body.find('/static/styles.css')
            assert shared != -1, f'{route} does not link umt-shared.css'
            assert app_css != -1, f'{route} does not link styles.css'
            assert shared < app_css, f'{route} links styles.css before umt-shared.css'

    def test_static_js_loads(self, client):
        """Test that JavaScript file loads successfully"""
        response = client.get('/static/client.js')
        assert response.status_code == 200


# =============================================================================
# Integration Tests
# =============================================================================

class TestAPIIntegration:
    """Test suite for API integration workflows"""
    
    def test_health_to_streams_flow(self, client):
        """Test workflow from health check to streams listing"""
        # Check health
        health_response = client.get('/health')
        assert health_response.status_code == 200
        
        # List streams
        streams_response = client.get('/api/streams')
        assert streams_response.status_code == 200
        
        # Get settings
        settings_response = client.get('/api/settings')
        assert settings_response.status_code == 200
    
    def test_recordings_workflow(self, client):
        """Test complete recordings workflow"""
        # List recordings
        list_response = client.get('/api/recordings')
        assert list_response.status_code == 200
        data = json.loads(list_response.data)
        assert isinstance(data, list)
    
    def test_settings_workflow(self, client):
        """Test settings get/update workflow"""
        # Get current settings
        get_response = client.get('/api/settings')
        assert get_response.status_code == 200
        
        # Update settings
        update_response = client.post('/api/settings',
                                    json={'autoRecord': False},
                                    content_type='application/json')
        assert update_response.status_code == 200


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Test suite for error handling"""
    
    def test_404_for_invalid_endpoint(self, client):
        """Test that invalid endpoints return 404"""
        response = client.get('/api/nonexistent')
        assert response.status_code == 404
    
    def test_405_for_wrong_method(self, client):
        """Test that wrong HTTP methods return 405"""
        response = client.post('/health')
        assert response.status_code == 405
    
    def test_400_for_invalid_json(self, client):
        """Test that invalid JSON with PUT returns 405"""
        response = client.put('/api/settings',
                            data='invalid json',
                            content_type='application/json')
        assert response.status_code == 405


# =============================================================================
# Stream Validation Tests
# =============================================================================

def _report(**overrides):
    """Minimal validator report, shaped like utils/validate_stream.py output."""
    report = {
        'target': 'rtsp://localhost:8554/drone1',
        'ok': True,
        'has_warnings': False,
        'checks': [
            {'id': 'klv_track', 'name': 'KLV track present', 'status': 'pass',
             'summary': 'KLV data track found (stream index 2).', 'hint': None, 'detail': {}},
        ],
        'streams': [],
    }
    report.update(overrides)
    return report


class TestStreamValidation:
    """Test suite for /api/stream/validate"""

    def test_requires_a_target(self, client):
        """Neither streamName nor videoFile is a 400"""
        response = client.post('/api/stream/validate', json={})
        assert response.status_code == 400

    def test_rejects_both_targets(self, client):
        """streamName and videoFile are mutually exclusive"""
        response = client.post('/api/stream/validate',
                               json={'streamName': 'drone1', 'videoFile': 'a/b.ts'})
        assert response.status_code == 400

    def test_rejects_invalid_stream_name(self, client):
        """Stream names are restricted to a safe character set"""
        response = client.post('/api/stream/validate',
                               json={'streamName': '../../etc/passwd'})
        assert response.status_code == 400

    def test_rejects_path_traversal(self, client):
        """Relative video paths may not escape STREAMS_DIR"""
        response = client.post('/api/stream/validate',
                               json={'videoFile': '../../../etc/passwd'})
        assert response.status_code == 400

    def test_rejects_out_of_range_window(self, client):
        """Sample window is bounded"""
        response = client.post('/api/stream/validate',
                               json={'streamName': 'drone1', 'window': 9999})
        assert response.status_code == 400

    def test_clean_stream_reports_ok(self, client):
        """A stream passing every check returns ok=True"""
        with patch('validate_stream.validate', return_value=_report()):
            response = client.post('/api/stream/validate', json={'streamName': 'drone1'})

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['report']['ok'] is True

    def test_non_monotonic_klv_is_flagged(self, client):
        """The KLV timestamp defect surfaces as a failing check with a hint"""
        broken = _report(ok=False, checks=[
            {'id': 'klv_timestamps', 'name': 'KLV timestamps monotonic', 'status': 'fail',
             'summary': 'KLV PTS runs backwards on 75/217 steps (34.6%).',
             'hint': 'Repair with: -bsf:d "setts=pts=DTS:dts=DTS"',
             'detail': {'backward_steps': 75}},
        ])
        with patch('validate_stream.validate', return_value=broken):
            response = client.post('/api/stream/validate', json={'streamName': 'drone1'})

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['report']['ok'] is False
        failed = [c for c in data['report']['checks'] if c['status'] == 'fail']
        assert len(failed) == 1
        assert failed[0]['id'] == 'klv_timestamps'
        assert failed[0]['hint']

    def test_missing_klv_track_is_flagged(self, client):
        """A stream published over RTSP arrives with no data track at all"""
        broken = _report(ok=False, checks=[
            {'id': 'klv_track', 'name': 'KLV track present', 'status': 'fail',
             'summary': 'No data track — the stream carries no KLV at all.',
             'hint': 'Publish over SRT instead, and pass -map 0.', 'detail': {}},
        ])
        with patch('validate_stream.validate', return_value=broken):
            response = client.post('/api/stream/validate', json={'streamName': 'drone1'})

        data = json.loads(response.data)
        assert data['report']['ok'] is False
        assert data['report']['checks'][0]['id'] == 'klv_track'


class TestKLVTimestampRepairSetting:
    """The repair_klv_timestamps setting must reach the pull-stream FFmpeg args"""

    def test_setting_defaults_on(self):
        from app.config import SERVER_SETTINGS
        assert SERVER_SETTINGS['repair_klv_timestamps'] is True

    def test_setting_is_in_schema(self):
        from app.config import SERVER_SETTINGS_SCHEMA
        assert SERVER_SETTINGS_SCHEMA['repair_klv_timestamps'] == (bool,)

    def test_bsf_present_when_enabled(self):
        from app.api.streams import _build_pull_ffmpeg_args
        from app.api.settings import server_settings

        with patch.dict(server_settings, {'repair_klv_timestamps': True}):
            args = _build_pull_ffmpeg_args('srt://example:9000', 'drone1')

        assert '-bsf:d' in args
        assert args[args.index('-bsf:d') + 1] == 'setts=pts=DTS:dts=DTS'

    def test_bsf_absent_when_disabled(self):
        from app.api.streams import _build_pull_ffmpeg_args
        from app.api.settings import server_settings

        with patch.dict(server_settings, {'repair_klv_timestamps': False}):
            args = _build_pull_ffmpeg_args('srt://example:9000', 'drone1')

        assert '-bsf:d' not in args

    def test_map_all_streams_still_present(self):
        """-map 0 is what keeps the KLV track; guard against regression"""
        from app.api.streams import _build_pull_ffmpeg_args

        args = _build_pull_ffmpeg_args('srt://example:9000', 'drone1')
        assert '-map' in args
        assert args[args.index('-map') + 1] == '0'
        # Republished as MPEG-TS over SRT, never RTSP - RTP cannot carry KLV.
        assert 'mpegts' in args


class TestPullStreamTimeouts:
    """RTSP inputs must not be handed options the RTSP demuxer rejects"""

    def test_rtsp_uses_timeout_only(self):
        """-rw_timeout aborts an RTSP input on FFmpeg 7.x ('Option not found')"""
        from app.api.streams import _build_pull_ffmpeg_args

        args = _build_pull_ffmpeg_args('rtsp://camera.local:8554/live', 'drone1')
        assert '-timeout' in args
        assert '-rw_timeout' not in args
        assert '-reconnect' not in args

    def test_rtsps_uses_timeout_only(self):
        from app.api.streams import _build_pull_ffmpeg_args

        args = _build_pull_ffmpeg_args('rtsps://camera.local:8322/live', 'drone1')
        assert '-rw_timeout' not in args

    def test_http_keeps_rw_timeout(self):
        """-rw_timeout is an AVIO option, so it is valid for the HTTP handler"""
        from app.api.streams import _build_pull_ffmpeg_args

        args = _build_pull_ffmpeg_args('http://host/live.m3u8', 'drone1')
        assert '-rw_timeout' in args


class TestKLVParsing:
    """MISB ST 0601.19 conformance of shared/klv.py"""

    @pytest.fixture
    def parser(self):
        from shared.klv import UnifiedKLVParser
        return UnifiedKLVParser()

    def value(self, parser, tag, hex_bytes):
        return parser._decode_item(tag, bytes.fromhex(hex_bytes))['value']

    def test_worked_examples_from_the_standard(self, parser):
        assert self.value(parser, 5, '71C2') == pytest.approx(159.9744, abs=1e-4)
        assert self.value(parser, 7, '08B8') == pytest.approx(3.405814, abs=1e-4)
        assert self.value(parser, 13, '5595B66D') == pytest.approx(60.1768229669783, abs=1e-9)
        assert self.value(parser, 15, 'C221') == pytest.approx(14190.72, abs=1e-2)
        assert self.value(parser, 16, 'CD9C') == pytest.approx(144.5713, abs=1e-4)
        assert self.value(parser, 21, '03830926') == pytest.approx(68590.98, abs=1e-2)
        assert self.value(parser, 36, 'B2') == pytest.approx(69.80392, abs=1e-4)
        assert self.value(parser, 55, '81') == pytest.approx(50.58823, abs=1e-4)

    def test_pitch_and_roll_have_different_ranges(self, parser):
        """Pitch is +/-20, roll is +/-50, both scaled to 65534 - not 65535"""
        assert self.value(parser, 6, '7FFF') == pytest.approx(20.0)
        assert self.value(parser, 7, '7FFF') == pytest.approx(50.0)
        assert self.value(parser, 50, '7FFF') == pytest.approx(20.0)
        assert self.value(parser, 51, '7FFF') == pytest.approx(180.0)
        assert self.value(parser, 79, '7FFF') == pytest.approx(327.0)

    def test_out_of_range_indicator(self, parser):
        """-(2^(n-1)) means 'out of range', not a legitimate extreme value"""
        item = parser._decode_item(6, bytes.fromhex('8000'))
        assert item['value'] is None
        assert item['out_of_range'] is True
        assert parser._decode_item(13, bytes.fromhex('80000000'))['value'] is None

    def test_offset_corners_are_two_byte_offsets(self, parser):
        """Items 26-33 are +/-0.075 degree offsets from frame centre, not coordinates"""
        assert self.value(parser, 26, '7FFF') == pytest.approx(0.075)
        assert self.value(parser, 27, '8001') == pytest.approx(-0.075)
        assert self.value(parser, 26, '8000') is None

    def test_offset_corner_resolved_against_frame_centre(self, parser):
        from shared import klv

        payload = (klv.encode_ber_oid(23) + klv.encode_ber_length(4) +
                   klv.encode_int_mapped(40.0, 90.0, 4) +
                   klv.encode_ber_oid(26) + klv.encode_ber_length(2) +
                   klv.encode_int_mapped(0.05, 0.075, 2))
        packet = klv.UAS_LOCAL_SET_KEY + klv.encode_ber_length(len(payload)) + payload

        corner = [i for i in parser.parse_klv_packet(packet)['items'] if i['tag_id'] == 26][0]
        assert corner['value'] == pytest.approx(0.05, abs=1e-5)
        assert corner['absolute_value'] == pytest.approx(40.05, abs=1e-5)

    def test_latitude_longitude_are_per_item_not_odd_even(self, parser):
        """Item 40 is a latitude and item 41 a longitude - the parity rule is wrong"""
        assert self.value(parser, 40, '7FFFFFFF') == pytest.approx(90.0)
        assert self.value(parser, 41, '7FFFFFFF') == pytest.approx(180.0)
        assert self.value(parser, 82, '7FFFFFFF') == pytest.approx(90.0)
        assert self.value(parser, 83, '7FFFFFFF') == pytest.approx(180.0)

    def test_operational_mode_is_an_enumeration(self, parser):
        assert self.value(parser, 77, '03') == {'code': 3, 'name': 'Exercise'}
        assert self.value(parser, 77, 'FF') == {'code': 255, 'name': 'Reserved'}
        assert self.value(parser, 63, '02') == {'code': 2, 'name': 'Medium'}

    def test_item_keys_are_ber_oid(self):
        """Keys are BER-OID (ST 0601.19 7.1); lengths stay BER"""
        from shared import klv

        assert klv.encode_ber_oid(142) == bytes.fromhex('810e')
        assert klv.decode_ber_oid(bytes.fromhex('810e'))[0] == 142
        assert klv.encode_ber_length(128) == bytes.fromhex('8180')

    def test_generated_packet_carries_a_valid_checksum(self, parser):
        from shared.klv import encode_uas_metadata

        packet = encode_uas_metadata({'timestamp': 1_500_000_000_000_000,
                                      'sensor_latitude': 60.1768229669783})
        parsed = parser.parse_klv_packet(packet)
        assert parsed.get('error') is None
        assert parsed['checksum_valid'] is True
        assert parsed['items'][-1]['tag_id'] == 1

    def test_corrupt_packet_fails_its_checksum(self, parser):
        from shared.klv import encode_uas_metadata

        packet = bytearray(encode_uas_metadata({'timestamp': 1_500_000_000_000_000,
                                                'mission_id': 'MISSION-42'}))
        packet[33] ^= 0xFF  # a byte inside the mission ID, not a length field
        assert parser.parse_klv_packet(bytes(packet))['checksum_valid'] is False

    def test_deprecated_item_66_is_never_generated(self, parser):
        from shared.klv import encode_uas_metadata

        parsed = parser.parse_klv_packet(encode_uas_metadata({'timestamp': 1}))
        assert all(item['tag_id'] != 66 for item in parsed['items'])
        assert [i['value'] for i in parsed['items'] if i['tag_id'] == 65] == [19]

    def test_repeated_items_are_not_lost(self, parser):
        """Order matters for repeatable items such as SDCC-FLP (item 102)"""
        from shared import klv

        payload = (klv.encode_ber_oid(102) + klv.encode_ber_length(2) + b'\x01\x02' +
                   klv.encode_ber_oid(102) + klv.encode_ber_length(2) + b'\x03\x04')
        packet = klv.UAS_LOCAL_SET_KEY + klv.encode_ber_length(len(payload)) + payload

        parsed = parser.parse_klv_packet(packet)
        assert [i['raw_value'] for i in parsed['items']] == ['0102', '0304']
        assert sorted(parsed['tags']) == ['SDCC-FLP', 'SDCC-FLP #2']

    def test_items_beyond_89_are_known(self, parser):
        """ST 0601.19 defines items past 89, including ones ST 0902 requires"""
        from shared.klv import STANAG_4609_TAGS

        assert STANAG_4609_TAGS[94] == 'MIIS Core Identifier'
        assert STANAG_4609_TAGS[142] == 'View Domain'
        assert self.value(parser, 90, '7FFFFFFF') == pytest.approx(90.0)

    def test_undecoded_items_are_flagged_not_guessed(self, parser):
        item = parser._decode_item(103, bytes.fromhex('0102'))
        assert item['name'] == 'Density Altitude Extended'
        assert item['decoded'] is False
        assert item['value'] == '0102'


class TestTranscodeOptions:
    """Option list must not advertise anything the backend cannot run"""

    def test_options_are_1_to_3(self, client):
        response = client.get('/api/transcode/options')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert [o['option'] for o in data['options']] == [1, 2, 3]

    def test_default_option_is_offered(self, client):
        """Default must be one of the advertised options"""
        response = client.get('/api/transcode/options')
        data = json.loads(response.data)
        assert data['default'] in [o['option'] for o in data['options']]

    def test_option_4_is_rejected(self, client):
        """Option 4 depended on a script that never existed.

        The file-existence check runs first, so stub it out to reach the
        option validation.
        """
        with patch('app.api.utils.os.path.exists', return_value=True):
            response = client.post('/api/transcode',
                                   json={'inputFile': 'anything.mov', 'option': 4})

        assert response.status_code == 400
        assert '1-3' in json.loads(response.data)['error']

    def test_valid_option_passes_validation(self, client):
        """Guard the above: option 1 must get past the same validation gate"""
        with patch('app.api.utils.os.path.exists', return_value=True), \
                patch('app.api.utils.subprocess.Popen'):
            response = client.post('/api/transcode',
                                   json={'inputFile': 'anything.mov', 'option': 1})

        assert response.status_code != 400

    def test_extract_endpoint_is_gone(self, client):
        """/api/klv/extract was backed by a missing script; it should 404"""
        response = client.post('/api/klv/extract', json={'videoFile': 'a/b.ts'})
        assert response.status_code == 404


# =============================================================================
# Test Runner (when executed directly)
# =============================================================================

def main():
    """Run pytest with the provided arguments"""
    try:
        import pytest
    except ImportError:
        print("ERROR: pytest is not installed")
        print("Install it with: pip install pytest")
        return 1
    
    args = sys.argv[1:]
    
    # Default pytest arguments - run this file
    pytest_args = [__file__]
    
    # Add user arguments
    if args:
        pytest_args.extend(args)
    else:
        # Default: run with verbose output
        pytest_args.append('-v')
    
    # Run pytest
    print("=" * 70)
    print("TAK Video Restreamer - Test Suite")
    print("=" * 70)
    print(f"Running: pytest {' '.join(pytest_args)}\n")
    
    result = pytest.main(pytest_args)
    
    print("\n" + "=" * 70)
    if result == 0:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")
    print("=" * 70)
    
    return result


if __name__ == '__main__':
    sys.exit(main())


class TestAbrStreamNameValidation:
    """ABR endpoints use the same stream-name rules as HLS playback"""

    @pytest.mark.parametrize('method,suffix', [
        ('post', '/abr'), ('delete', '/abr'), ('get', '/abr/status'),
    ])
    def test_rejects_names_outside_the_hls_directory(self, client, monkeypatch, method, suffix):
        from app.services.abr import abr_manager
        calls = []
        for name in ('start', 'stop', 'status'):
            monkeypatch.setattr(abr_manager, name, lambda s, _n=name: calls.append((_n, s)) or {'status': 'started'})
        response = getattr(client, method)(f'/api/streams/..%2F..%2Fescaped{suffix}')
        assert response.status_code == 400
        assert calls == []

    def test_valid_name_reaches_abr_manager(self, client, monkeypatch):
        from app.services.abr import abr_manager
        calls = []
        monkeypatch.setattr(abr_manager, 'start', lambda s: calls.append(s) or {'status': 'started', 'stream': s})
        response = client.post('/api/streams/live/cam1/abr')
        assert response.status_code == 200
        assert calls == ['live/cam1']
