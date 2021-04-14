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
/index.html something a level of indirection, like a structure to loop
over, but this incurs logic here (to build the list) and pain on the
author (to understand it).  It seems better overall to me to keep this
file as small as possible.
'''

from glob import glob
import os
import sys

from doit import create_after

from datetime import datetime
from exif import Image
import subprocess

from jinja2 import Environment, FileSystemLoader
jenv = Environment(loader=FileSystemLoader('templates'))

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

def task_larges():
    '''
    Copy original photos into the corresponding directory in the site/.
    '''
    for original in glob('content/galleries/*/*jpg'):
        largepath = _largepath(original)
        yield {
            'name': largepath,
            'file_dep': [original],
            'targets': [largepath],
            'actions': [_mkdir, "cp '{}' '{}'".format(original, largepath)]}

def task_thumbs():
    '''
    Create thumbnails from originals in the corresponding thumbnail directory.
    '''
    for original in glob('content/galleries/*/*jpg'):
        thumbpath = _thumbpath(original)
        yield {
            'name': thumbpath,
            'file_dep': [original],
            'targets': [thumbpath],
            'actions': [
                _mkdir,
                "magick convert -geometry x250 '{}' '{}'".format(original, thumbpath)]}

def task_orderfiles():
    '''
    Read EXIF data from all images and create the order.txt files,
    which are the file names sorted by capture time, and the x/y
    dimenions of the thumbnails.
    '''
    for galdir in dirsonly(glob('content/galleries/*')):
        galname = os.path.basename(galdir)
        orderfile = os.path.join('content/galleries', '{}_order.txt'.format(galname))
        deps = glob(os.path.join(galdir, '*'))
        reverse = False
        if galname == 'photostream':
            reverse = True
        yield {
            'name': orderfile,
            'targets': [orderfile],
            'task_dep': ['thumbs'],
            'file_dep': deps,
            'actions': [(make_order_file, [galdir, reverse])]}

@create_after(executed='orderfiles')
def task_gallery_html():
    '''
    Generate HTML for directories in galleries/.
    '''
    for galdir in dirsonly(glob('content/galleries/*')):
        # we need the image files to exist, and the order files to exist.
        galname = os.path.basename(galdir)
        targetdir = _sitepath(galdir)
        target = os.path.join(targetdir, 'index.html')
        orderfile = os.path.join('content/galleries', '{}_order.txt'.format(galname))
        yield {
            'name': target,
            'task_dep': ['orderfiles', 'thumbs', 'larges'],
            'file_dep': [orderfile,
                         'templates/gallery_template.html.tmpl',
                         'templates/foot.html', 'templates/head.html'],
            'targets': [target],
            'actions': [(make_stream_html, [orderfile, target, galname])]
            }

        # TODO: This doesn't run at task execution time. It runs at
        # task definition time. Therefore, if the order files change
        # DURING task execution, the previous/next things could be
        # INCORRECT because they were set before the order files were
        # changed.
        #
        # SOLUTION: https://pydoit.org/task_creation.html#delayed-task-creation
        with open(orderfile) as f:
            orderdata = f.readlines()

        prevdata = orderdata[:][:-1]
        prevdata.insert(0, None)
        nextdata = orderdata[1:]
        nextdata.append(None)
        for prev, cur, next_ in zip(prevdata, orderdata, nextdata):
            photo_id = cur.split(',')[0]
            filename = os.path.join(targetdir, photo_id + '.html')

            yield {
                'name': filename,
                'targets': [filename],
                'task_dep': ['orderfiles', 'thumbs', 'larges'],
                'file_dep': [orderfile, 'templates/galpage.html', 'templates/foot.html', 'templates/head.html'],
                'actions': [(make_gallery_html,
                             [targetdir, prev, photo_id, next_])]
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
        prevlink = os.path.join(prev.split(',')[0] + '.html')

    nextlink = None
    if next_:
        nextlink = os.path.join(next_.split(',')[0] + '.html')

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
        'task_dep': ['gallery_html'],
        'file_dep': ['content/galleries/photostream_order.txt'] + glob('templates/*'),
        'targets': ['site/index.html'],
        'actions': [make_index_html]}

def task_music_html():
    yield {
        'name': 'music.html',
        'file_dep': ['songs.txt', 'templates/music.html.tmpl'],
        'targets': ['site/music.html'],
        'actions': [make_music_html]}
def make_music_html():
    class Song():
        def __init__(self, songline):
            self.url, self.title, self.comments = songline.split('|')
    with open('songs.txt') as f:
        songlist = [Song(line) for line in f.readlines()]

    template = jenv.get_template('music.html.tmpl')
    with open ("site/music.html", "w") as fh:
        fh.write(template.render(songs = songlist))

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

    with open('content/galleries/photostream_order.txt') as f:
        stream_photos = [d.split(',') for d in f.readlines()[:20]]

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
    
    photos = [
        {"name":data[0],
         "width":data[1],
         "height":data[2]} for data in stream_photos
    ]

    output_from_parsed_template = template.render(photos=photos, galleries=galleries)

    # to save the results
    with open("site/index.html", "w") as fh:
        fh.write(output_from_parsed_template)

def make_stream_html(orderfile, target, galname):
    template = jenv.get_template('gallery_template.html.tmpl')

    with open(orderfile) as order:
        data = []
        for line in order.readlines():
            name, xdim, ydim, capture_time = line.split(',')
            data.append({'name': name, 'xdim': xdim, 'ydim':ydim})
    
    output_from_parsed_template = template.render(title=galname, photos=data)
    
    with open(os.path.join(target), 'w') as fh:
        fh.write(output_from_parsed_template)

# *******************************************
# render photostream HTML

# *******************************************
# make the order files

def make_order_file(galdir, reverse, dependencies, targets):
    # dependencies is only a list of files that are updated, not all the files. grab all the files.
    ORDER_FILE = targets[0]
    
    existing_order = []
    if os.path.exists(ORDER_FILE):
        with open(ORDER_FILE) as orderfile:
            existing_order = orderfile.readlines()
    def get_for_image(image):
        for line in existing_order:
            if line.startswith(image.name):
                return line.strip()
        return None
        
    image_files = [MyImage(i) for i in glob(os.path.join(galdir, '*'))]
    print("reading exif from {} files".format(len(image_files)))
    for my_image in image_files:
        my_image.add_order(get_for_image(my_image))

    [my_image.fill_in() for my_image in image_files]

    names = []
    for item in sorted(image_files,
                       key=lambda i: i.capture_time,
                       reverse=reverse):
        names.append("{},{},{},{}\n".format(
            item.name,
            item.xdim,
            item.ydim,
            item.capture_time))

    with open(ORDER_FILE, 'w') as f:
        f.writelines(names)

class MyImage():
    def __init__(self, orig_file_path):
        self.orig_file_path = orig_file_path
        self.filename = os.path.basename(self.orig_file_path)
        self.name = self.filename.replace('.jpg', '')

        self.image = None
        
        self.xdim = None
        self.ydim = None
        self.capture_time = None

    def add_order(self, orderline):
        if not orderline:
            return

        data = orderline.split(',')
        if len(data) != 4:
            return None

        if data[0] != self.name:
            raise Exception('collision: {} {}'.format(data, self.name))

        self.xdim = data[1]
        self.ydim = data[2]
        self.capture_time = data[3]

    def get_capture_time(self, image):
        try:
            d = image.datetime_original
            return d
        except AttributeError as err:
            # maybe this is a WA image with the date in the filename?
            if '-WA' in self.name:
                maybe_dt = self.name.split('-')[1]
                dt = datetime.strptime(maybe_dt, '%Y%m%d')
                if dt:
                    return dt.strftime('%Y:%m:%d %H:%M:%S')
            print("Image at {} has no EXIF for datetime.".format(self.orig_file_path))
            return None
        
    def fill_in(self):
        if not all([self.xdim, self.ydim, self.capture_time]):
            print("Missing some metadata for {}, will grab...".format(self.orig_file_path))
            image = Image(self.orig_file_path)
            self.capture_time = self.get_capture_time(image).strip()

            dimen_cmd = "magick identify '{}'"
            out = subprocess.check_output(dimen_cmd.format(_thumbpath(self.orig_file_path)),
                                          shell=True).decode('UTF-8')
            print(out.split()[2].split('x'))
            self.xdim, self.ydim = out.split()[2].split('x')
                
