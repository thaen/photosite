"""
Simple photo gallery site generator that processes images only when necessary.
"""
import os
import shutil
import subprocess
import calendar
from datetime import datetime
from glob import glob
from exif import Image
from jinja2 import Environment, FileSystemLoader

def ensure_dir(path):
    """Create directory if it doesn't exist."""
    os.makedirs(path, exist_ok=True)

def get_photo_path(original, type_='site'):
    """Convert content path to site path."""
    if type_ == 'site':
        return original.replace('content/galleries', 'site')
    elif type_ == 'large':
        site_path = original.replace('content/galleries', 'site')
        return os.path.join(os.path.dirname(site_path), 'large', os.path.basename(site_path))
    elif type_ == 'thumb':
        site_path = original.replace('content/galleries', 'site')
        return os.path.join(os.path.dirname(site_path), 'thumbnails', os.path.basename(site_path))
    else:
        raise ValueError(f"Unknown path type: {type_}")

def get_photo_metadata(photo_path):
    """Get photo metadata including capture time and dimensions."""
    metadata = {'capture_time': None, 'width': None, 'height': None}
    
    # Try to get EXIF data
    try:
        with open(photo_path, 'rb') as f:
            image = Image(f)
            if hasattr(image, 'datetime'):
                metadata['capture_time'] = datetime.strptime(image.datetime, '%Y:%m:%d %H:%M:%S')
    except Exception:
        pass  # EXIF data not available
        
    # Get dimensions using ImageMagick's identify
    try:
        result = subprocess.run(['identify', photo_path], capture_output=True, text=True, check=True)
        # Output format: path JPEG WxH ...
        parts = result.stdout.split()
        if len(parts) >= 3:
            width, height = parts[2].split('x')
            metadata['width'] = int(width)
            metadata['height'] = int(height)
    except subprocess.CalledProcessError:
        pass
        
    return metadata

def process_photo(photo_path, force=False):
    """Process a single photo, creating thumbnail and large version if needed."""
    thumb_path = get_photo_path(photo_path, 'thumb')
    large_path = get_photo_path(photo_path, 'large')
    
    # Ensure directories exist
    ensure_dir(os.path.dirname(thumb_path))
    ensure_dir(os.path.dirname(large_path))
    
    needs_processing = force
    if not needs_processing:
        needs_processing = (
            not os.path.exists(thumb_path) or
            not os.path.exists(large_path) or
            os.path.getmtime(photo_path) > os.path.getmtime(thumb_path) or
            os.path.getmtime(photo_path) > os.path.getmtime(large_path)
        )
    
    if needs_processing:
        # Create thumbnail
        subprocess.run(['magick', photo_path, '-geometry', 'x250', thumb_path], check=True)
        # Create large version (just copy for now, could add resizing if needed)
        shutil.copy2(photo_path, large_path)
        
    return get_photo_metadata(photo_path)

def update_orderfile(gallery_path, metadata_dict):
    """Update the order file for a gallery if needed."""
    gallery_name = os.path.basename(gallery_path)
    orderfile_dir = 'orderfiles'
    ensure_dir(orderfile_dir)
    
    orderfile_path = os.path.join(orderfile_dir, f'{gallery_name}_order.txt')
    needs_update = True
    
    if os.path.exists(orderfile_path):
        # Check if any source photo is newer than the orderfile
        orderfile_mtime = os.path.getmtime(orderfile_path)
        needs_update = any(
            os.path.getmtime(photo) > orderfile_mtime
            for photo in glob(os.path.join(gallery_path, '*.jpg'))
        )
    
    if needs_update:
        # Sort photos by capture time, falling back to filename
        photos = []
        for photo_path, metadata in metadata_dict.items():
            photo_name = os.path.basename(photo_path)
            capture_time = metadata.get('capture_time') or datetime.fromtimestamp(0)
            thumb_path = get_photo_path(photo_path, 'thumb')
            # Get thumbnail dimensions
            thumb_metadata = get_photo_metadata(thumb_path)
            photos.append({
                'name': photo_name,
                'capture_time': capture_time,
                'width': thumb_metadata['width'],
                'height': thumb_metadata['height']
            })
        
        photos.sort(key=lambda x: (x['capture_time'], x['name']))
        
        with open(orderfile_path, 'w') as f:
            for photo in photos:
                # Format: name width height
                f.write(f"{photo['name']} {photo['width']} {photo['height']}\n")

def process_gallery(gallery_path, force=False):
    """Process all photos in a gallery."""
    if not os.path.exists(gallery_path):
        raise ValueError(f"Gallery path does not exist: {gallery_path}")
        
    metadata_dict = {}
    for photo_path in glob(os.path.join(gallery_path, '*.jpg')):
        metadata = process_photo(photo_path, force)
        metadata_dict[photo_path] = metadata
        
    update_orderfile(gallery_path, metadata_dict)

def write_if_changed(content, filename):
    """Write content to file only if it has changed."""
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            if f.read() == content:
                return
    ensure_dir(os.path.dirname(filename))
    with open(filename, 'w') as f:
        f.write(content)

def get_photo_groups(orderfile_path):
    """Group photos by capture time month/year."""
    groups = []
    current_group = {'description': '', 'photos': []}
    
    with open(orderfile_path) as f:
        for line in f:
            # Parse orderfile line: name width height
            name, width, height = line.strip().split()
            photo_path = glob(os.path.join('content/galleries/*/', name))[0]
            metadata = get_photo_metadata(photo_path)
            
            if metadata['capture_time']:
                desc = f"{calendar.month_name[metadata['capture_time'].month]} {metadata['capture_time'].year}"
            else:
                desc = "Unknown Date"
                
            photo = {
                'name': os.path.splitext(name)[0],  # Remove .jpg extension
                'width': width,
                'height': height,
                'capture_time': metadata['capture_time'],
                'htmlid': 'l' + name.replace('.', '_'),
                'galname': os.path.basename(os.path.dirname(photo_path))
            }
            
            if current_group['description'] != desc:
                if current_group['photos']:
                    groups.append(current_group)
                current_group = {'description': desc, 'photos': []}
            current_group['photos'].append(photo)
            
    if current_group['photos']:
        groups.append(current_group)
        
    return groups

def generate_gallery_html(gallery_path, env):
    """Generate HTML files for a gallery."""
    gallery_name = os.path.basename(gallery_path)
    orderfile_path = os.path.join('orderfiles', f'{gallery_name}_order.txt')
    
    if not os.path.exists(orderfile_path):
        return
        
    # Get photo groups
    groups = get_photo_groups(orderfile_path)
    
    # Generate gallery index
    template = env.get_template('gallery_template.html.tmpl')
    content = template.render(
        title=gallery_name.replace('_', ' '),
        galname=gallery_name,
        groups=groups
    )
    target_path = os.path.join('site', gallery_name, 'index.html')
    write_if_changed(content, target_path)
    
    # Generate swipe gallery
    template = env.get_template('swipegallery.html.tmpl')
    content = template.render(
        title=gallery_name.replace('_', ' '),
        galname=gallery_name,
        groups=groups
    )
    target_path = os.path.join('site', gallery_name, 'swipe.html')
    write_if_changed(content, target_path)

def generate_homepage(env):
    """Generate the main index.html."""
    # Get list of galleries
    galleries = []
    for gallery_path in glob('content/galleries/*'):
        if os.path.isdir(gallery_path):
            gallery_name = os.path.basename(gallery_path)
            galleries.append({
                'name': gallery_name.replace('_', ' '),
                'dir': gallery_name
            })
    galleries.sort(key=lambda x: x['name'])
    
    # Get photostream groups if available
    groups = []
    photostream_orderfile = os.path.join('orderfiles', 'photostream_order.txt')
    if os.path.exists(photostream_orderfile):
        groups = get_photo_groups(photostream_orderfile)
    
    # Generate index.html
    template = env.get_template('index.html.tmpl')
    content = template.render(
        groups=groups,
        galname='photostream',
        galleries=galleries
    )
    write_if_changed(content, 'site/index.html')

def copy_static_files():
    """Copy static files to the site directory."""
    static_dir = os.path.join('content', 'static')
    site_static = os.path.join('site', 'static')
    
    if os.path.exists(static_dir):
        # Create site/static if it doesn't exist
        ensure_dir(site_static)
        
        # Copy all files from static to site/static
        for root, _, files in os.walk(static_dir):
            for file in files:
                src = os.path.join(root, file)
                # Get relative path from static_dir
                rel_path = os.path.relpath(src, static_dir)
                dst = os.path.join(site_static, rel_path)
                # Ensure destination directory exists
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                # Copy file if it doesn't exist or is newer
                if not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst):
                    shutil.copy2(src, dst)

def process_all_galleries(content_root='content/galleries', force=False, jinja_env=None):
    """Process all galleries under the content root and generate HTML."""
    # Initialize Jinja2 environment if not provided
    if jinja_env is None:
        jinja_env = Environment(loader=FileSystemLoader('templates'))
        
    # Copy static files
    copy_static_files()
    
    # Process photos and generate orderfiles
    for gallery_path in glob(os.path.join(content_root, '*')):
        if os.path.isdir(gallery_path):
            process_gallery(gallery_path, force)
            generate_gallery_html(gallery_path, jinja_env)
    
    # Generate homepage
    generate_homepage(jinja_env)
