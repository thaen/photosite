import unittest
import os
import shutil
import calendar
from glob import glob
from jinja2 import Environment, FileSystemLoader
import photosite

class TestNewPhotoSite(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        # Clean up any existing directories
        for dir_to_clean in ['site', 'orderfiles', 'content']:
            if os.path.exists(dir_to_clean):
                shutil.rmtree(dir_to_clean)

        # Create content directory and copy test data
        self.test_gallery = 'content/galleries/test_gallery'
        os.makedirs(self.test_gallery, exist_ok=True)
        test_data_path = 'test_data/galleries/test_gallery'
        if not os.path.exists(test_data_path):
            raise RuntimeError(f'Test data not found in {test_data_path}')
        
        # Copy test photos
        for photo in glob(os.path.join(test_data_path, '*.jpg')):
            shutil.copy2(photo, self.test_gallery)
        
        # Get list of test photos
        self.test_photos = glob(os.path.join(self.test_gallery, '*.jpg'))
        self.assertGreater(len(self.test_photos), 0, 
                          "No test photos found in test gallery")

    def tearDown(self):
        """Clean up after each test method."""
        # Clean up directories
        for dir_to_clean in ['site', 'orderfiles']:
            if os.path.exists(dir_to_clean):
                shutil.rmtree(dir_to_clean)

    def test_photo_processing(self):
        """Test that photos are processed correctly."""
        # Process the test gallery
        photosite.process_gallery(self.test_gallery)
        
        # Check that thumbnails and large photos were created
        for photo in self.test_photos:
            thumb_path = photosite.get_photo_path(photo, 'thumb')
            large_path = photosite.get_photo_path(photo, 'large')
            self.assertTrue(os.path.exists(thumb_path), f"Thumbnail not created: {thumb_path}")
            self.assertTrue(os.path.exists(large_path), f"Large photo not created: {large_path}")
        
        # Check that orderfile was created
        gallery_name = os.path.basename(self.test_gallery)
        orderfile_path = os.path.join('orderfiles', f'{gallery_name}_order.txt')
        self.assertTrue(os.path.exists(orderfile_path), f"Orderfile not created: {orderfile_path}")
        
        # Check orderfile format
        with open(orderfile_path) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), len(self.test_photos), 
                        "Orderfile should have one line per photo")
        for line in lines:
            parts = line.strip().split()
            self.assertEqual(len(parts), 3, 
                           "Each line should have filename and dimensions")
            self.assertTrue(parts[1].isdigit() and parts[2].isdigit(),
                          "Width and height should be numbers")

    def test_incremental_processing(self):
        """Test that photos are only processed when needed."""
        # First processing
        photosite.process_gallery(self.test_gallery)
        
        # Get initial modification times
        thumb_paths = [photosite.get_photo_path(p, 'thumb') for p in self.test_photos]
        large_paths = [photosite.get_photo_path(p, 'large') for p in self.test_photos]
        initial_thumb_mtimes = [os.path.getmtime(p) for p in thumb_paths]
        initial_large_mtimes = [os.path.getmtime(p) for p in large_paths]
        
        # Process again
        photosite.process_gallery(self.test_gallery)
        
        # Check that files weren't reprocessed
        current_thumb_mtimes = [os.path.getmtime(p) for p in thumb_paths]
        current_large_mtimes = [os.path.getmtime(p) for p in large_paths]
        self.assertEqual(initial_thumb_mtimes, current_thumb_mtimes,
                        "Thumbnails were reprocessed unnecessarily")
        self.assertEqual(initial_large_mtimes, current_large_mtimes,
                        "Large photos were reprocessed unnecessarily")
                        
    def test_html_generation(self):
        """Test that HTML files are generated correctly."""
        # Set up Jinja environment
        env = Environment(loader=FileSystemLoader('templates'))
        
        # Create test static file
        test_static_dir = os.path.join('content', 'static')
        os.makedirs(test_static_dir, exist_ok=True)
        test_css = os.path.join(test_static_dir, 'styles.css')
        with open(test_css, 'w') as f:
            f.write('/* Test CSS */')
            
        # Process gallery and generate HTML
        photosite.process_all_galleries(force=False, jinja_env=env)
        
        # Check that gallery HTML files exist
        gallery_name = os.path.basename(self.test_gallery)
        gallery_index = os.path.join('site', gallery_name, 'index.html')
        gallery_swipe = os.path.join('site', gallery_name, 'swipe.html')
        homepage = 'site/index.html'
        
        self.assertTrue(os.path.exists(gallery_index), 
                       f"Gallery index not created: {gallery_index}")
        self.assertTrue(os.path.exists(gallery_swipe),
                       f"Gallery swipe not created: {gallery_swipe}")
        self.assertTrue(os.path.exists(homepage),
                       f"Homepage not created: {homepage}")
        
        # Check gallery index content
        with open(gallery_index) as f:
            content = f.read()
            # Basic content checks
            # Gallery page should link to swipe gallery and thumbnails
            self.assertIn('swipe.html', content)
            self.assertIn('thumbnails', content)
            
        # Check homepage content
        with open(homepage) as f:
            content = f.read()
            # Basic content checks
            self.assertIn('Photos.', content)
            self.assertIn(f'/{gallery_name}/', content)
            
        # Check that static files were copied
        site_css = os.path.join('site', 'static', 'styles.css')
        self.assertTrue(os.path.exists(site_css), 'Static CSS file not copied')
        with open(site_css) as f:
            self.assertEqual(f.read(), '/* Test CSS */', 'CSS content not copied correctly')

if __name__ == '__main__':
    unittest.main()
