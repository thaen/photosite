#!/usr/bin/env python3
"""
Simple CLI tool to build the photo site.
"""
import argparse
import http.server
import os
import shutil
import socketserver
import sys
from jinja2 import Environment, FileSystemLoader

import photosite

def serve_site(port=8000):
    """Serve the site directory on localhost."""
    os.chdir('site')
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Serving site at http://localhost:{port}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            httpd.shutdown()

def copy_static_files():
    """Copy static files to the site directory."""
    os.makedirs('site/static', exist_ok=True)
    
    # First try content/static
    content_static = 'content/static'
    if os.path.exists(content_static):
        for root, _, files in os.walk(content_static):
            for file in files:
                src = os.path.join(root, file)
                rel_path = os.path.relpath(src, content_static)
                dst = os.path.join('site/static', rel_path)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
    
    # Fallback to test_data/static
    test_static = 'test_data/static'
    if os.path.exists(test_static):
        for root, _, files in os.walk(test_static):
            for file in files:
                src = os.path.join(root, file)
                rel_path = os.path.relpath(src, test_static)
                dst = os.path.join('site/static', rel_path)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)

def main():
    parser = argparse.ArgumentParser(description='Build and serve the photo site.')
    parser.add_argument('--force', '-f', action='store_true',
                      help='Force rebuild all files')
    parser.add_argument('--serve', '-s', action='store_true',
                      help='Serve the site after building')
    parser.add_argument('--port', '-p', type=int, default=8000,
                      help='Port to serve on (default: 8000)')
    args = parser.parse_args()
    
    # Check that we're in the right directory
    if not os.path.exists('templates') or not os.path.exists('content'):
        print("Error: Must run from photosite root directory (containing 'templates' and 'content')")
        sys.exit(1)
    
    # Set up Jinja environment
    env = Environment(loader=FileSystemLoader('templates'))
    
    try:
        # Process galleries and generate site
        print("Building site...")
        photosite.process_all_galleries(force=args.force, jinja_env=env)
        
        # Copy static files
        print("Copying static files...")
        copy_static_files()
        
        print("Site built successfully!")
        
        if args.serve:
            serve_site(args.port)
            
    except Exception as e:
        print(f"Error building site: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
