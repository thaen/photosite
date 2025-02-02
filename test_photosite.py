import unittest
import os
import shutil
from glob import glob
import subprocess
import sys
from dodo import _sitepath, _largepath, _thumbpath

# Get the doit executable path
def check_doit_in_path():
    """Check if doit is available in PATH"""
    try:
        subprocess.run(['doit', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError('doit command not found in PATH. Please install doit and ensure it\'s in your PATH.')

class TestPhotoSite(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        check_doit_in_path()
        # Clean up any existing site directory
        if os.path.exists('site'):
            shutil.rmtree('site')
        
        # Ensure we have our test gallery
        self.test_gallery = 'content/galleries/test_gallery'
        self.assertTrue(os.path.exists(self.test_gallery), 
                       f"Test gallery not found at {self.test_gallery}")
        
        # Get list of test photos
        self.test_photos = glob(os.path.join(self.test_gallery, '*.jpg'))
        self.assertGreater(len(self.test_photos), 0, 
                          "No test photos found in test gallery")

    def tearDown(self):
        """Clean up after each test method."""
        # Optionally clean up the site directory
        if os.path.exists('site'):
            shutil.rmtree('site')

    def test_path_conversions(self):
        """Test path conversion functions."""
        test_photo = self.test_photos[0]
        site_path = _sitepath(test_photo)
        large_path = _largepath(test_photo)
        thumb_path = _thumbpath(test_photo)
        
        self.assertTrue(site_path.startswith('site/'))
        self.assertTrue(large_path.endswith('.jpg'))
        self.assertTrue(thumb_path.endswith('.jpg'))
        self.assertIn('thumb', thumb_path)

    def test_large_photo_generation(self):
        """Test generation of large photos."""
        result = subprocess.run(['doit', 'larges'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"Task failed: {result.stderr}")
        
        # Check each test photo has a corresponding large version
        for photo in self.test_photos:
            large_path = _largepath(photo)
            self.assertTrue(os.path.exists(large_path),
                          f"Large photo not generated: {large_path}")
            
            # Verify file size (should be non-zero)
            self.assertGreater(os.path.getsize(large_path), 0,
                             f"Large photo is empty: {large_path}")

    def test_thumbnail_generation(self):
        """Test generation of thumbnails."""
        result = subprocess.run(['doit', 'thumbs'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"Task failed: {result.stderr}")
        
        # Check each test photo has a corresponding thumbnail
        for photo in self.test_photos:
            thumb_path = _thumbpath(photo)
            self.assertTrue(os.path.exists(thumb_path),
                          f"Thumbnail not generated: {thumb_path}")
            
            # Verify file size (should be non-zero)
            self.assertGreater(os.path.getsize(thumb_path), 0,
                             f"Thumbnail is empty: {thumb_path}")

    def test_order_file_generation(self):
        """Test generation of order.txt files."""
        result = subprocess.run(['doit', 'orderfiles'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"Task failed: {result.stderr}")
        
        order_file = os.path.join('orderfiles', 'test_gallery_order.txt')
        self.assertTrue(os.path.exists(order_file),
                       f"Order file not generated: {order_file}")
        
        # Verify order file contains entries
        with open(order_file, 'r') as f:
            lines = f.readlines()
        self.assertGreater(len(lines), 0,
                          "Order file is empty")

    def test_gallery_html_generation(self):
        """Test generation of gallery HTML files."""
        # We need thumbnails and order files before generating HTML
        subprocess.run(['doit', 'thumbs'], check=True)
        subprocess.run(['doit', 'orderfiles'], check=True)
        result = subprocess.run(['doit', 'gallery_html'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"Task failed: {result.stderr}")
        
        # Check for gallery index
        gallery_index = os.path.join('site', 'test_gallery', 'index.html')
        self.assertTrue(os.path.exists(gallery_index),
                       f"Gallery index not generated: {gallery_index}")
        
        # Basic HTML validation
        with open(gallery_index, 'r') as f:
            content = f.read()
            self.assertIn('<!DOCTYPE html>', content)
            self.assertIn('</HTML>', content)
            # Check for at least one photo reference
            self.assertIn('.jpg', content)

    def test_homepage_generation(self):
        """Test generation of main index.html."""
        # Need all prerequisites
        subprocess.run(['doit', 'thumbs'], check=True)
        subprocess.run(['doit', 'orderfiles'], check=True)
        subprocess.run(['doit', 'gallery_html'], check=True)
        result = subprocess.run(['doit', 'homepage'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"Task failed: {result.stderr}")
        
        homepage = os.path.join('site', 'index.html')
        self.assertTrue(os.path.exists(homepage),
                       f"Homepage not generated: {homepage}")
        
        # Basic HTML validation
        with open(homepage, 'r') as f:
            content = f.read()
            self.assertIn('<!DOCTYPE html>', content)
            self.assertIn('</HTML>', content)
            self.assertIn('test_gallery', content)

if __name__ == '__main__':
    unittest.main()
