# Photo Site Builder

A simple and efficient static site generator for photo galleries using Python.

## Features

- Generates photo galleries with thumbnails and full-size views
- Groups photos by capture date
- Only processes photos when needed (smart incremental builds)
- Supports custom CSS and static files
- Mobile-friendly swipe view for photos

## Requirements

### System Dependencies
- Python 3.9 or higher
- ImageMagick (`convert` command for thumbnail generation)

### Python Dependencies
Install Python dependencies using:
```bash
pip3 install -r requirements.txt
```

## Usage

### Directory Structure
```
├── content/
│   ├── galleries/     # Your photo galleries go here
│   │   ├── gallery1/
│   │   └── gallery2/
│   └── static/        # Static files (CSS, JS, etc.)
└── templates/         # HTML templates
```

### Building and Serving the Site

1. Build and serve the site in one command:
   ```bash
   ./build_site.py --serve
   ```
   Then view at http://localhost:8000

2. Additional options:
   ```bash
   ./build_site.py --force    # Force rebuild all files
   ./build_site.py --port 8080 # Use a different port
   ```

### Development and Testing

1. Create a test gallery:
   ```bash
   mkdir -p test_data/galleries/test_gallery
   ```

2. Add test photos to `test_data/galleries/test_gallery/`

3. Run the tests:
   ```bash
   python3 -m unittest test_new_photosite.py -v
   ```

## How It Works

1. Photo Processing:
   - Creates thumbnails (250px height) for gallery view
   - Preserves full-size photos for detailed view
   - Extracts EXIF data for date-based grouping

2. HTML Generation:
   - Generates gallery index pages with thumbnails
   - Creates swipe view for full-size photos
   - Builds homepage with gallery links

3. Static Files:
   - Copies CSS and other static files
   - Supports custom styling and assets

## Resources
- [CSS Flexbox Guide](https://css-tricks.com/snippets/css/a-guide-to-flexbox/)
- [Browser Image Lazy Loading](https://web.dev/browser-level-image-lazy-loading/)

## GitHub Operations
* There's probably an auth token in your bashrc
* Run `gh auth login` first, then git as normal