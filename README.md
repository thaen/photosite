# Photo Site Builder

A static site generator for photo galleries using Python and doit.

## Requirements

### System Dependencies
- Python 3.9 or higher
- ImageMagick (`convert` command for thumbnail generation)

### Python Dependencies
Install Python dependencies using:
```bash
pip3 install -r requirements.txt
```

## Development

### Building and Serving the Site
1. Build the site:
   ```bash
   doit
   ```
2. Start a local web server:
   ```bash
   cd site && python3 -m http.server 8000
   ```
3. View the site at http://localhost:8000

### Setting up a test environment
1. Create a test gallery:
   ```bash
   mkdir -p content/galleries/test_gallery
   ```
2. Add some test photos to `content/galleries/test_gallery/`
3. Add the Python user bin directory to your PATH in your shell's rc file (e.g. `.bashrc`, `.zshrc`):
   ```bash
   export PATH="$PATH:$HOME/Library/Python/3.9/bin"  # For macOS
   export PATH="$PATH:$HOME/.local/bin"             # For Linux
   ```

4. Run the tests (make sure to source your rc file first):
   ```bash
   source ~/.bashrc && python3 -m unittest test_photosite.py -v
   ```

## Resources
- [CSS Flexbox Guide](https://css-tricks.com/snippets/css/a-guide-to-flexbox/)
- [Browser Image Lazy Loading](https://web.dev/browser-level-image-lazy-loading/)

## GitHub Operations
* There's probably an auth token in your bashrc
* Run `gh auth login` first, then git as normal