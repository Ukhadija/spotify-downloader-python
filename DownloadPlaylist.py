import tekore as tk
import os
from dotenv import load_dotenv
import yt_dlp as youtube_dl
import eyed3
import urllib.request
import re
import platform
import datetime
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import zipfile
import sys
import uuid
from typing import Dict, Any, Tuple

app = Flask(__name__)
CORS(app)

# Spotify API

load_dotenv('.env.local')
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

# Global variable to track download progress
download_progress = {}

def initialize_spotify_client():
    """Initialize Spotify client with client credentials flow"""
    app_token = tk.request_client_token(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
    return tk.Spotify(app_token)

#############################################################################

def extract_spotify_id(spotify_link: str) -> Tuple[str, str]:
    """Extract ID from various Spotify URL formats (playlist, album, track)"""
    # Handle direct ID (22 characters)
    if re.match(r'^[a-zA-Z0-9]{22}$', spotify_link):
        return spotify_link, 'unknown'
    
    # Extract from URL patterns
    patterns = [
        (r'spotify.com/playlist/([a-zA-Z0-9]{22})', 'playlist'),
        (r'open.spotify.com/playlist/([a-zA-Z0-9]{22})', 'playlist'),
        (r'spotify.com/album/([a-zA-Z0-9]{22})', 'album'),
        (r'open.spotify.com/album/([a-zA-Z0-9]{22})', 'album'),
        (r'spotify.com/track/([a-zA-Z0-9]{22})', 'track'),
        (r'open.spotify.com/track/([a-zA-Z0-9]{22})', 'track'),
    ]
    
    for pattern, type_ in patterns:
        match = re.search(pattern, spotify_link)
        if match:
            return match.group(1), type_
    
    raise ValueError("Invalid Spotify link format. Please provide a valid Spotify playlist, album, or track link.")

def get_playlist_tracks(spotify, playlist_id: str) -> list:
    """Get all tracks from a playlist"""
    tracks = []
    results = spotify.playlist_items(playlist_id)
    
    while results:
        for item in results.items:
            if item.track and item.track.type == 'track':
                track = item.track
                tracks.append(track)  # Return the actual track object, not a dict
        results = spotify.next(results) if results.next else None
    
    return tracks

def get_album_tracks(spotify, album_id: str) -> list:
    """Get all tracks from an album"""
    tracks = []
    results = spotify.album_tracks(album_id)
    
    while results:
        for track in results.items:
            if track.type == 'track':
                tracks.append(track)  # Return the actual track object, not a dict
        results = spotify.next(results) if results.next else None
    
    return tracks

def get_playlist_info(spotify, playlist_id: str) -> Dict[str, Any]:
    """Get playlist information"""
    playlist = spotify.playlist(playlist_id)
    return {
        'id': playlist.id,
        'name': playlist.name,
        'description': playlist.description or '',
        'owner': playlist.owner.display_name if hasattr(playlist.owner, 'display_name') else playlist.owner.id,
        'tracks_total': playlist.tracks.total if hasattr(playlist.tracks, 'total') else 0,
        'type': 'playlist'
    }

def get_album_info(spotify, album_id: str) -> Dict[str, Any]:
    """Get album information"""
    album = spotify.album(album_id)
    return {
        'id': album.id,
        'name': album.name,
        'artists': [artist.name for artist in album.artists],
        'release_date': album.release_date,
        'total_tracks': album.total_tracks,
        'type': 'album'
    }

###########################################################################
# Flask Routes search playlists

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'Spotify API Wrapper'})

@app.route('/api/spotify/item', methods=['GET'])
def get_spotify_item():
    """Main endpoint to get Spotify playlist, album, or track data"""
    try:
        # Get URL from query parameters
        url = request.args.get('url')
        
        if not url:
            return jsonify({
                'success': False,
                'error': 'Missing URL parameter'
            }), 400
        
        # Initialize Spotify client
        spotify = initialize_spotify_client()
        
        # Extract ID and type
        item_id, item_type = extract_spotify_id(url)
        
        result = {}
        
        if item_type == 'playlist':
            # Get playlist info and tracks
            playlist_info = get_playlist_info(spotify, item_id)
            tracks = get_playlist_tracks(spotify, item_id)
            
            # Convert tracks to dict format for JSON response
            tracks_dict = []
            for track in tracks:
                artists = [artist.name for artist in track.artists]
                tracks_dict.append({
                    'id': track.id,
                    'name': track.name,
                    'artists': artists,
                    'artist_names': ', '.join(artists),
                    'album': track.album.name,
                    'duration_ms': track.duration_ms,
                    'track_number': track.track_number,
                    'disc_number': track.disc_number,
                    'explicit': track.explicit,
                    'popularity': track.popularity,
                    'preview_url': track.preview_url,
                    'external_urls': track.external_urls,
                    'uri': track.uri,
                    'type': 'playlist_track'
                })
            
            result = {
                'success': True,
                'item_info': playlist_info,
                'tracks': tracks_dict
            }
        
        elif item_type == 'album':
            # Get album info and tracks
            album_info = get_album_info(spotify, item_id)
            tracks = get_album_tracks(spotify, item_id)
            
            # Convert tracks to dict format for JSON response
            tracks_dict = []
            for track in tracks:
                artists = [artist.name for artist in track.artists]
                tracks_dict.append({
                    'id': track.id,
                    'name': track.name,
                    'artists': artists,
                    'artist_names': ', '.join(artists),
                    'album': album_info['name'],  # Use album name from album info
                    'duration_ms': track.duration_ms,
                    'track_number': track.track_number,
                    'disc_number': track.disc_number,
                    'explicit': track.explicit,
                    'popularity': 0,  # Not available in album tracks response
                    'preview_url': track.preview_url,
                    'external_urls': track.external_urls,
                    'uri': track.uri,
                    'type': 'album_track'
                })
            
            result = {
                'success': True,
                'item_info': album_info,
                'tracks': tracks_dict
            }
        
        elif item_type == 'track':
            # Handle single track
            track = spotify.track(item_id)
            artists = [artist.name for artist in track.artists]
            result = {
                'success': True,
                'item_info': {
                    'type': 'single_track',
                    'id': track.id,
                    'name': track.name,
                    'artists': artists
                },
                'tracks': [{
                    'id': track.id,
                    'name': track.name,
                    'artists': artists,
                    'artist_names': ', '.join(artists),
                    'album': track.album.name,
                    'duration_ms': track.duration_ms,
                    'explicit': track.explicit,
                    'popularity': track.popularity,
                    'preview_url': track.preview_url,
                    'type': 'single_track'
                }]
            }
        else:
            return jsonify({
                'success': False,
                'error': f'Unsupported Spotify item type: {item_type}'
            }), 400
        
        return jsonify(result)
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }), 500

@app.route('/api/spotify/search', methods=['GET'])
def search_spotify():
    """Search for playlists, albums, or tracks"""
    try:
        query = request.args.get('q')
        search_type = request.args.get('type', 'playlist')  # playlist, album, track
        limit = int(request.args.get('limit', 10))
        
        if not query:
            return jsonify({
                'success': False,
                'error': 'Missing search query parameter "q"'
            }), 400
        
        spotify = initialize_spotify_client()
        results = spotify.search(query, types=(search_type,), limit=limit)
        
        return jsonify({
            'success': True,
            'query': query,
            'type': search_type,
            'results': getattr(results, f'{search_type}s').items
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Search failed: {str(e)}'
        }), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Endpoint not found'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500

#########################################################################################
def log_progress(download_id, message, message_type="info"):
    """Log progress messages with robust Unicode handling and store in global progress"""
    progress_data = {
        "type": message_type,
        "message": message,
        "timestamp": datetime.datetime.now().isoformat()
    }
    
    # Store in global progress
    if download_id not in download_progress:
        download_progress[download_id] = []
    
    download_progress[download_id].append(progress_data)
    
    # Keep only last 100 messages to prevent memory issues
    if len(download_progress[download_id]) > 100:
        download_progress[download_id] = download_progress[download_id][-100:]
    
    # Handle encoding for output - be very permissive with errors
    try:
        # First try to encode with UTF-8 and replace errors
        if isinstance(message, str):
            safe_message = message.encode('utf-8', errors='replace').decode('utf-8')
        else:
            safe_message = str(message).encode('utf-8', errors='replace').decode('utf-8')
    except Exception:
        # If that fails, use a very basic replacement
        try:
            safe_message = str(message).encode('ascii', errors='replace').decode('ascii')
        except Exception:
            safe_message = "Log message contains unreadable characters"
    
    # Final safety check before printing
    try:
        print(f"[{download_id}] {safe_message}", flush=True)
    except Exception as e:
        # If even the safe message fails, use a bare minimum message
        print(f"[{download_id}] Log message: check download folder for download ", flush=True)

class MyLogger(object):
    def __init__(self, download_id):
        self.download_id = download_id
        
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        log_progress(self.download_id, msg, "error")

def get_ydl_opts(download_id, output_template):
    """Get youtube-dl options with progress tracking"""
    return {
        'ffmpeg_location': r"C:\Users\Dell\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-7.1.1-full_build\bin\ffmpeg.exe",
        'format': 'bestaudio/best',
        'extractaudio': True,
        'outtmpl': output_template,
        'addmetadata': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }],
        'logger': MyLogger(download_id),
        
        # Add these options to avoid 403 errors:
        'retries': 3,  # Retry failed downloads
        'fragment_retries': 3,  # Retry fragmented downloads
        'skip_unavailable_fragments': True,
        'extract_flat': False,
        'http_chunk_size': 10485760,  # 10MB chunks
        'continuedl': True,
    }

def check_permissions():
    """Check if we have write permissions in current directory"""
    try:
        test_file = "permission_test.txt"
        with open(test_file, 'w') as f:
            f.write("test")
        #os.remove(test_file)
        return True
    except Exception as e:
        return False
    

def get_default_download_folder():
    """Get the user's default download folder based on their OS"""
    system = platform.system()
    
    if system == "Windows":
        return os.path.join(os.path.expanduser("~"), "Downloads")
    elif system == "Darwin":  # macOS
        return os.path.join(os.path.expanduser("~"), "Downloads")
    elif system == "Linux":
        # Try multiple common locations on Linux
        download_dirs = [
            os.path.join(os.path.expanduser("~"), "Downloads"),
            os.path.join(os.path.expanduser("~"), "downloads"),
        ]
        for dir_path in download_dirs:
            if os.path.exists(dir_path):
                return dir_path
        # Fallback to home directory if no Downloads folder found
        return os.path.expanduser("~")
    else:
        return os.path.expanduser("~")


def sanitize_filename(filename):
    """Sanitize filename with fallback to 'unknown' on Unicode errors"""
    try:
        # Try to keep original name first
        cleaned = filename
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            cleaned = cleaned.replace(char, '')
        cleaned = ''.join(char for char in cleaned if ord(char) >= 32)
        
        # Test if we can encode it (no encoding errors)
        cleaned.encode('utf-8')
        return cleaned.strip()
        
    except (UnicodeEncodeError, UnicodeDecodeError):
        # Fallback to 'unknown' if Unicode fails
        return "unknown"

def songs_downloader(download_id, folder, tracks):
    """Download songs with progress tracking"""
    if not check_permissions():
        log_progress(download_id, "No write permissions in current directory", "error")
        return
        
    download_folder = get_default_download_folder()
    folder = sanitize_filename(folder)
    playlist_folder = os.path.join(download_folder, folder)
    
    # Create main folder
    os.makedirs(playlist_folder, exist_ok=True)
    
    total_tracks = len(tracks)
    
    for i, track in enumerate(tracks, 1):
        try:
            # Use safe default names initially
            song = "unknown_audio"
            artist = "unknown_artist" 
            album = "unknown_album"
            
            try:
                # Try to get the actual names from track object
                song = track.name
                artist = track.artists[0].name if track.artists else "unknown_artist"
                album = track.album.name if hasattr(track, 'album') and track.album else "unknown_album"
                
                # Log the original track info
                log_progress(download_id, f"Track {i}/{total_tracks}: {song} by {artist}", "info")
                
            except (UnicodeEncodeError, UnicodeDecodeError) as e:
                log_progress(download_id, f"Unicode error reading track metadata, using default names", "warning")
                # Keep the default "unknown" names we set above
            except Exception as e:
                log_progress(download_id, f"Error reading track metadata: {e}, using default names", "warning")
            
            # Sanitize names (this will handle Unicode errors and return "unknown" if needed)
            song_safe = sanitize_filename(song)
            artist_safe = sanitize_filename(artist)
            album_safe = sanitize_filename(album)
            
            # Build the destination path
            file_name = f'{artist_safe} - {song_safe}.mp3'
            full_destination = os.path.join(playlist_folder, file_name)

            # Download song if not already downloaded
            if not os.path.exists(full_destination):
                # Update output template for current download
                current_ydl_opts = get_ydl_opts(download_id, os.path.join(playlist_folder, f'{artist_safe} - {song_safe}.%(ext)s'))
                
                try:
                    with youtube_dl.YoutubeDL(current_ydl_opts) as ydl:
                        # Use safe names for search query too
                        search_query = f'{song_safe} {artist_safe} official audio'
                        ydl.cache.remove()
                        ydl.download([f'ytsearch1:{search_query}'])

                    # Check if file was downloaded to the destination
                    if os.path.exists(full_destination):
                        log_progress(download_id, f'Successfully downloaded: {file_name}', "success")
                        
                        # Add metadata to the downloaded file
                        try:
                            audiofile = eyed3.load(full_destination)
                            if audiofile.tag is None:
                                audiofile.initTag()
                            
                            # Use safe names for metadata too
                            audiofile.tag.artist = artist_safe
                            audiofile.tag.title = song_safe
                            audiofile.tag.album = album_safe
                            
                            if hasattr(track, 'album') and track.album and hasattr(track.album, 'artists') and track.album.artists:
                                try:
                                    album_artist = track.album.artists[0].name
                                    audiofile.tag.album_artist = sanitize_filename(album_artist)
                                except (UnicodeEncodeError, UnicodeDecodeError):
                                    audiofile.tag.album_artist = "unknown_artist"

                            if hasattr(track, 'track_number'):
                                audiofile.tag.track_num = track.track_number

                            # Add album art if available
                            if (hasattr(track, 'album') and track.album and 
                                hasattr(track.album, 'images') and track.album.images):
                                try:
                                    imagedata = urllib.request.urlopen(track.album.images[0].url).read()
                                    audiofile.tag.images.set(3, imagedata, 'image/jpeg')
                                except:
                                    log_progress(download_id, "Could not add album art", "warning")

                            audiofile.tag.save()
                        except Exception as e:
                            log_progress(download_id, f"Error adding metadata: {e}", "error")
                    else:
                        log_progress(download_id, f'Failed to download {file_name}', "error")
                        
                except youtube_dl.utils.DownloadError as e:
                    log_progress(download_id, f"Error downloading track {i}: {e}. Skipping this song.", "error")
                    continue
                except Exception as e:
                    log_progress(download_id, f"An unexpected error occurred while downloading track {i}: {e}. Skipping this song.", "error")
                    continue
            else:
                log_progress(download_id, f'Already downloaded: {file_name}', "info")
                
        except Exception as e:
            log_progress(download_id, f"Error processing track {i}: {e}", "error")
            continue

@app.route('/api/download/progress/<download_id>', methods=['GET'])
def get_download_progress(download_id: str):
    """Get progress for a specific download"""
    progress = download_progress.get(download_id, [])
    return jsonify({
        'success': True,
        'download_id': download_id,
        'progress': progress
    })

@app.route('/api/download/start', methods=['POST'])
def start_download():
    """Start a download and return download ID"""
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing URL in request body'
            }), 400
        
        spotify_input = data['url']
        download_id = str(uuid.uuid4())
        
        # Initialize download progress
        download_progress[download_id] = []
        
        # Start download in background thread
        import threading
        thread = threading.Thread(
            target=download_worker,
            args=(download_id, spotify_input)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'download_id': download_id,
            'message': 'Download started'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to start download: {str(e)}'
        }), 500

def download_worker(download_id, spotify_input):
    """Worker function to handle download in background"""
    try:
        # Initialize Spotify client
        spotify = initialize_spotify_client()
        
        # Extract ID and type
        item_id, item_type = extract_spotify_id(spotify_input)
        
        tracks = []
        folder_name = ""
        
        if item_type == 'playlist':
            # Get playlist info and tracks
            playlist_info = get_playlist_info(spotify, item_id)
            tracks = get_playlist_tracks(spotify, item_id)  # Returns track objects
            folder_name = f"Playlist - {playlist_info['name']}"
            
            log_progress(download_id, f"Downloading playlist: {playlist_info['name']} ({len(tracks)} tracks)", "info")
            
        elif item_type == 'album':
            # Get album info and tracks
            album_info = get_album_info(spotify, item_id)
            tracks = get_album_tracks(spotify, item_id)  # Returns track objects
            folder_name = f"Album - {album_info['name']} - {', '.join(album_info['artists'])}"
            log_progress(download_id, f"Downloading album: {album_info['name']} by {', '.join(album_info['artists'])} ({len(tracks)} tracks)", "info")
            
        elif item_type == 'track':
            # Handle single track
            track = spotify.track(item_id)
            tracks = [track]  # Single track object
            folder_name = f"Single - {track.name} - {track.artists[0].name}"
            log_progress(download_id, f"Downloading single track: {track.name} by {track.artists[0].name}", "info")
        
        else:
            log_progress(download_id, "Unknown item type", "error")
            return
        
        if tracks:
            # Log download confirmation
            log_progress(download_id, f"Found {len(tracks)} tracks to download", "info")
            log_progress(download_id, f"Ready to download {len(tracks)} tracks to folder: {folder_name}", "info")
            folder_name = sanitize_filename(folder_name)
            songs_downloader(download_id, folder_name, tracks)
            log_progress(download_id, f"Download completed! Check the '{folder_name}' folder.", "success")
        
        else:
            log_progress(download_id, "No tracks found to download.", "warning")
            
    except Exception as e:
        log_progress(download_id, f"Fatal error: {str(e)}", "error")

@app.route('/api/spotify/info', methods=['GET'])
def get_spotify_info():
    """Get Spotify item information without downloading"""
    try:
        url = request.args.get('url')
        
        if not url:
            return jsonify({
                'success': False,
                'error': 'Missing URL parameter'
            }), 400
        
        spotify = initialize_spotify_client()
        item_id, item_type = extract_spotify_id(url)
        
        result = {}
        
        if item_type == 'playlist':
            playlist_info = get_playlist_info(spotify, item_id)
            tracks = get_playlist_tracks(spotify, item_id)
            result = {
                'item_info': {**playlist_info, 'type': 'playlist'},
                'tracks_count': len(tracks),
                'tracks_preview': [{
                    'name': track.name,
                    'artists': [artist.name for artist in track.artists],
                    'duration_ms': getattr(track, 'duration_ms', None)
                } for track in tracks[:5]]  # First 5 tracks as preview
            }
            
        elif item_type == 'album':
            album_info = get_album_info(spotify, item_id)
            tracks = get_album_tracks(spotify, item_id)
            result = {
                'item_info': {**album_info, 'type': 'album'},
                'tracks_count': len(tracks),
                'tracks_preview': [{
                    'name': track.name,
                    'artists': [artist.name for artist in track.artists],
                    'duration_ms': getattr(track, 'duration_ms', None)
                } for track in tracks[:5]]
            }
            
        elif item_type == 'track':
            track = spotify.track(item_id)
            result = {
                'item_info': {
                    'type': 'track',
                    'name': track.name,
                    'artists': [artist.name for artist in track.artists],
                    'duration_ms': track.duration_ms
                },
                'tracks_count': 1
            }
        
        return jsonify({
            'success': True,
            'data': result
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)