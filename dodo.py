'''
This is a build script for a website.  Its job is to populate the
build directory (site/) with the built website, suitable for uploading
to a place where it will be served as web content.

This parallelizes well, since generating thumbnails and copying large
files is highly parallelizabl.

However, there are a lot of dependencies in the artifacts.  I find
this to be a fascinating problem because I see no way out of it:
index.html needs to link to the galleries, meaning an author has to
understand that.  Theoretically you could give the author of
/index.html some level of indirection, like a structure to loop
over, but this incurs logic here (to build the list) and pain on the
author (to understand it).  It seems better overall to me to keep this
file as small as possible.
'''

import calendar
from datetime import datetime
from glob import glob
import json
import os
from pathlib import Path
from shutil import copyfile
import subprocess
import sys

# Third-party imports
from doit import create_after
from exif import Image
from jinja2 import Environment, FileSystemLoader
jenv = Environment(loader=FileSystemLoader('templates'))

# A release build may request a list of successfully rebuilt site targets. Normal
# builds retain doit's standard console reporter.
if os.environ.get('PHOTOSITE_UPLOAD_LIST'):
    from scripts.release_reporter import UploadListReporter
    DOIT_CONFIG = {'reporter': UploadListReporter}

ORDERFILE_LOCATION = "orderfiles"

def _mkdir(targets):
    for target in targets:
        os.makedirs(os.path.dirname(target), exist_ok=True)

def _sitepath(original):
    if "galleries" in original:
        return original.replace('content/galleries', 'site')
    if "static" in original:
        return original.replace('content/static', 'site/static')
    
def _largepath(original):
    # original is like content/galleries/2015_book_photos/foo.jpg
    path = original.replace('content/galleries', 'site')
    return os.path.join(os.path.dirname(path), 'large', os.path.basename(path))

def _thumbpath(original):
    path = original.replace('content/galleries', 'site')
    return os.path.join(os.path.dirname(path), 'thumbnails', os.path.basename(path))

def dirsonly(L):
    return filter(lambda i: os.path.isdir(i), L)

def gallery_dirs():
    selected = os.environ.get('PHOTOSITE_CHANGED_GALLERIES')
    names = set(json.loads(selected)) if selected is not None else None
    return [path for path in sorted(dirsonly(glob('content/galleries/*')))
            if names is None or os.path.basename(path) in names]

def gallery_photos(galdir):
    return sorted(path for path in glob(os.path.join(galdir, '*.jpg')) if os.path.isfile(path))

def _make_thumbnail(original, target):
    subprocess.run(['magick', original, '-geometry', 'x250', target], check=True)

def task_larges():
    '''
    Copy original photos into the corresponding directory in the site/.
    '''
    for original in (photo for folder in gallery_dirs() for photo in gallery_photos(folder)):
        largepath = _largepath(original)
        yield {
            'name': largepath,
            'file_dep': [original],
            'targets': [largepath],
            'actions': [_mkdir, (copyfile, [original, largepath])]}

def task_thumbs():
    '''
    Create thumbnails from originals in the corresponding thumbnail directory.
    '''
    for original in (photo for folder in gallery_dirs() for photo in gallery_photos(folder)):
        thumbpath = _thumbpath(original)
        yield {
            'name': thumbpath,
            'file_dep': [original],
            'targets': [thumbpath],
            'actions': [_mkdir, (_make_thumbnail, [original, thumbpath])]}

def task_create_orderfiles_dir():
    '''Create the orderfiles directory.'''
    return {
        'actions': [(os.makedirs, [ORDERFILE_LOCATION], {'exist_ok': True})],
        'targets': [ORDERFILE_LOCATION]
    }

def task_orderfiles():
    '''
    Read EXIF data from all images and create the order.txt files,
    which are the file names sorted by capture time, and the x/y
    dimenions of the thumbnails.
    '''
    for galdir in gallery_dirs():
        galname = os.path.basename(galdir)
        orderfile = os.path.join(ORDERFILE_LOCATION, '{}_order.txt'.format(galname))
        deps = gallery_photos(galdir)
        reverse = False
        if galname == 'photostream':
            reverse = True
        yield {
            'name': orderfile,
            'targets': [orderfile],
            'task_dep': ['thumbs', 'create_orderfiles_dir'],
            'file_dep': deps,
            'actions': [(make_order_file, [galdir, reverse])]}

def task_photostream_glom_orderfile():
    yield {
        'name': 'photostream_glom_order.txt',
        'targets': [ORDERFILE_LOCATION + '/photostream_glom_order.txt'],
        'task_dep': ['orderfiles'],
        'file_dep': [os.path.join(ORDERFILE_LOCATION, os.path.basename(folder) + '_order.txt')
                     for folder in sorted(dirsonly(glob('content/galleries/*')))],
        'actions': [make_photostream_glom_orderfile] }
        
@create_after(executed='orderfiles')
def task_gallery_html():
    '''
    Generate HTML for directories in galleries/.
    '''
    for galdir in gallery_dirs():
        # we need the image files to exist, and the order files to exist.
        galname = os.path.basename(galdir)
        targetdir = _sitepath(galdir)
        target = os.path.join(targetdir, 'index.html')
        swipetarget = os.path.join(targetdir, 'swipe.html')
        orderfile = os.path.join(ORDERFILE_LOCATION, '{}_order.txt'.format(galname))
        yield {
            'name': target,
            'task_dep': ['orderfiles', 'thumbs', 'larges'],
            'file_dep': [orderfile,
                         'templates/gallery_template.html.tmpl',
                         'templates/foot.html',
                         'templates/head.html',
                         'templates/gallery_content_template.html.tmpl'],
            'targets': [target],
            'actions': [(make_stream_html, [orderfile, target, galname])]
            }
        yield {
            'name': swipetarget,
            'task_dep': ['orderfiles', 'thumbs', 'larges'],
            'file_dep': [orderfile,
                         'templates/swipegallery.html.tmpl',
                         'templates/foot.html',
                         'templates/head.html'],
            'targets': [swipetarget],
            'actions': [(make_swipe_html, [orderfile, swipetarget, galname])]
        }            

def _write_if_changed(content, filename):
    # TODO this task actually only depends on the ones before
    # and after it.  If those don't change, we don't need to
    # redo this.  We may end up cheesing this because the
    # cascading effects will cause us to rewrite all gallery
    # pages if we add one page (p1 changes, so p2 points to
    # p1, so p3 has to change since p2 did, etc.) When in
    # reality we don't usually need to write a new
    # file. Avoiding writing new files is important because
    # uploading thousands of new HTML files every time we add
    # a picture to s3 is silly.
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            if f.read() == content:
                return
    with open(filename, 'w') as f:
        f.write(content)

def make_gallery_html(targetdir, prev, photo_id, next_):
    template = jenv.get_template('galpage.html')
    prevlink = None
    if prev:
        prevlink = os.path.join(prev['name'] + '.html')

    nextlink = None
    if next_:
        nextlink = os.path.join(next_['name'] + '.html')

    _write_if_changed(
        template.render(
            title='see photo run',
            prevlink=prevlink,
            nextlink=nextlink,
            largefile='large/' + photo_id + '.jpg'),
        os.path.join(targetdir, photo_id + '.html')
    )
        

def task_homepage():
    '''
    Generate the homepage HTML.
    '''
    return {
        'task_dep': ['gallery_html', 'photostream_glom_orderfile'],
        'file_dep': [ORDERFILE_LOCATION + '/photostream_glom_order.txt'] + glob('templates/*') + glob('content/galleries/*order.txt'),
        'targets': ['site/index.html'],
        'actions': [make_index_html]}

def task_music_html():
    yield {
        'name': 'music.html',
        'file_dep': ['songs.txt', 'templates/music.html.tmpl'],
        'targets': ['site/music.html'],
        'actions': [make_music_html]}

def task_favicon():
    yield {
        'name': 'favicon.ico',
        'file_dep': ['content/static/favicon.ico'],
        'targets': ['site/favicon.ico'],
        'actions': ['cp content/static/favicon.ico site/favicon.ico']}

def make_music_html():
    class Song():
        def __init__(self, songline):
            self.url, self.title, self.comments = songline.split('|')
    with open('songs.txt') as f:
        songlist = [Song(line) for line in f.readlines()]

    template = jenv.get_template('music.html.tmpl')
    with open ("site/music.html", "w") as fh:
        fh.write(template.render(songs = songlist))

TRIVIA_DIR = 'content/static/trivia'
TRIVIA_ASSETS = os.path.join(TRIVIA_DIR, 'assets')
TRIVIA_BANK_SOURCE = os.path.join(
    'trivia-sources', 'the-trivia-api-family-text-choice.json')

def task_trivia_bank():
    '''
    Build the served trivia question bank from the cached API response,
    merging the API categories down to the six the game plays.
    '''
    yield {
        'name': 'bank.js',
        'file_dep': ['scripts/build_trivia_bank.py', TRIVIA_BANK_SOURCE],
        'targets': [os.path.join(TRIVIA_DIR, 'bank.js')],
        'actions': ['{} scripts/build_trivia_bank.py'.format(sys.executable)],
    }

def task_trivia_artwork():
    '''
    Measure the trivia comic artwork and emit the stylesheet that carries
    each frame's image, safe area and colour. Needs Pillow.
    '''
    assets = sorted(glob(os.path.join(TRIVIA_ASSETS, '*.webp')))
    yield {
        'name': 'artwork.css',
        'file_dep': ['scripts/trivia_artwork.py'] + assets,
        'targets': [os.path.join(TRIVIA_DIR, 'artwork.css')],
        'actions': ['{} scripts/trivia_artwork.py'.format(sys.executable)],
    }

def task_trivia():
    '''
    Everything generated into content/static/ before it gets copied out.
    '''
    yield {
        'name': 'generated',
        'actions': None,
        'task_dep': ['trivia_bank', 'trivia_artwork'],
    }

# task_static walks content/static/ to build its file list, so it has to be
# created after anything that generates files in there has run -- otherwise
# a first build copies whatever existed before the generators wrote.
@create_after(executed='trivia')
def task_static():
    '''
    Copy all files from ./static to ./site/static/. Parallelizes with doit -n 8.
    '''
    for path, subdirs, files in os.walk('./content/static/'):
        for name in files:
            filepath = os.path.join(path, name)
            target = _sitepath(filepath)
            yield {
                'name': target,
                'file_dep': [filepath],
                'targets': [target],
                'actions': [_mkdir, 'cp {} {}'.format(filepath, target)]
            }

def make_index_html():
    template = jenv.get_template('index.html.tmpl')

    groups = _get_photo_groups(ORDERFILE_LOCATION + '/photostream_glom_order.txt')

    gallery_dirs = sorted(
        list(
            filter(
                lambda x: os.path.isdir(os.path.join('content/galleries', x)),
                os.listdir('content/galleries'))))

    galleries = [
        {
            'name': d.replace('_', ' '),
            'dir': d
        } for d in gallery_dirs]
    
    output_from_parsed_template = template.render(groups=groups,
                                                  galname='photostream',
                                                  galleries=galleries)

    # to save the results
    with open("site/index.html", "w") as fh:
        fh.write(output_from_parsed_template)

def _get_photo_groups(orderfile):
    of = Orderfile.from_file(orderfile)

    # this isn't super flexible. oh who are we kidding, this *file* isn't super flexible.
    curgroup = {'description': "",
                'photos': []}
    groups = []
    for photo in of.data:
        photo['htmlid'] = 'l' + photo['name'].replace('.', '_')
        desc = "{} {}".format(
            calendar.month_name[photo['capture_time'].month],
            photo['capture_time'].year)
        if curgroup['description'] != desc:
            # make a new group and append existing one to the list
            if curgroup['photos']:
                groups.append(curgroup)
            curgroup = {'description': desc, 'photos': []}
        curgroup['photos'].append(photo)
    groups.append(curgroup)

    return groups
        
def make_stream_html(orderfile, target, galname):
    template = jenv.get_template('gallery_template.html.tmpl')

    output_from_parsed_template = template.render(title=galname,
                                                  galname=galname,
                                                  groups=_get_photo_groups(orderfile))
    
    _write_if_changed(output_from_parsed_template, target)

def make_swipe_html(orderfile, swipetarget, galname):
    template = jenv.get_template('swipegallery.html.tmpl')
    output_from_parsed_template = template.render(title=galname,
                                                  galname=galname,
                                                  groups=_get_photo_groups(orderfile))
    _write_if_changed(output_from_parsed_template, swipetarget)

# *******************************************
# make the order files

def make_order_file(galdir, reverse, dependencies, targets):
    order_path = Path(targets[0])
    galname = os.path.basename(galdir)
    images = {image.name: image for image in map(MyImage, gallery_photos(galdir))}
    of = Orderfile(order_path, reverse=reverse)
    if order_path.exists():
        cached = Orderfile.from_file(order_path, galname).data
        newest = order_path.stat().st_mtime_ns
        for row in cached:
            image = images.get(row['name'])
            if image and row['galname'] == galname and os.stat(image.orig_file_path).st_mtime_ns <= newest:
                of.data.append(row)
                images.pop(row['name'])
    for image in images.values():
        image.fill_in()
        of.add_row(image.name, image.xdim, image.ydim, image.capture_time, galname)
    of.write_file()

class Orderfile:
    def __init__(self, filename, reverse=False):
        self.filename = filename
        self.data = []
        self.reverse = reverse

    def add_row(self, name, xdim, ydim, capture_time, galname):
        # always store datetime objects, not strings
        if not isinstance(capture_time, datetime):
            capture_time = spt(capture_time)
        self.data.append(
            {'name': name, 'xdim': xdim, 'ydim':ydim,
             'capture_time': capture_time,
             'galname': galname})

    def write_file(self, numrows=None):
        lines = []
        for item in sorted(self.data,
                           key = lambda r: r['capture_time'],
                           reverse=self.reverse)[:numrows]:
            lines.append("{},{},{},{},{}\n".format(
                item['name'],
                item['xdim'],
                item['ydim'],
                sft(item['capture_time']),
                item['galname']))
        _write_if_changed(''.join(lines), self.filename)
        
    @classmethod
    def from_file(cls, filename, galname=None):
        of = Orderfile(filename)
        with open(filename) as order:
            for line in order:
                row = line.rstrip('\n').split(',')
                if len(row) == 4 and galname:
                    row.append(galname)
                of.add_row(*row)
        return of
                
def make_photostream_glom_orderfile():
    data = []
    for galdir in sorted(dirsonly(glob('content/galleries/*'))):
        galname = os.path.basename(galdir)
        f = os.path.join(ORDERFILE_LOCATION, '{}_order.txt'.format(galname))
        orderfile = Orderfile.from_file(f, galname)
        data.extend(orderfile.data)

    glom_path = Path(ORDERFILE_LOCATION) / 'photostream_glom_order.txt'
    if glom_path.exists():
        previous = Orderfile.from_file(glom_path).data
        positions = {(row['galname'], row['name']): index for index, row in enumerate(previous)}
        data.sort(key=lambda row: positions.get((row['galname'], row['name']), len(positions)))
    glom_orderfile = Orderfile(glom_path, reverse=True)
    for item in data:
        glom_orderfile.add_row(
            item['name'],
            item['xdim'],
            item['ydim'],
            item['capture_time'],
            item['galname'])

    glom_orderfile.write_file(numrows=100)

def sft(s):
    return s.strftime('%Y:%m:%d %H:%M:%S')
def spt(s):
    return datetime.strptime(s.strip(), '%Y:%m:%d %H:%M:%S')

class GalleryGroup():
    def __init__(self, description, photos):
        self.photos = photos
        self.description = description
        
class MyImage():
    def __init__(self, orig_file_path):
        self.orig_file_path = orig_file_path
        self.filename = os.path.basename(self.orig_file_path)
        self.name = Path(self.filename).stem

        self.image = None
        
        self.xdim = None
        self.ydim = None
        self.capture_time = None

    def get_capture_time(self, image):
        try:
            return sft(spt(image.datetime_original))
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        try:
            if '-WA' in self.name:
                return sft(datetime.strptime(self.name.split('-')[1], '%Y%m%d'))
            if 'signal-' in self.name:
                return sft(datetime.strptime(self.name, 'signal-%Y-%m-%d-%H%M%S'))
            if 'WhatsApp_Image' in self.name:
                return sft(datetime.strptime(self.name, 'WhatsApp_Image_%Y-%m-%d_at_%H.%M.%S_%p'))
        except (IndexError, ValueError):
            pass
        return sft(datetime.utcfromtimestamp(os.stat(self.orig_file_path).st_mtime))

    def fill_in(self):
        if not all([self.xdim, self.ydim, self.capture_time]):
            print("Missing some metadata for {}, will grab...".format(self.orig_file_path))
            image = Image(self.orig_file_path)
            try:
                self.capture_time = self.get_capture_time(image).strip()
            except Exception as err:
                raise Exception("couldn't get capture time for {}".format(self.orig_file_path))

            dimensions = subprocess.check_output(['magick', 'identify', '-ping', '-format', '%w %h',
                                                   _thumbpath(self.orig_file_path)], text=True)
            self.xdim, self.ydim = dimensions.split()
