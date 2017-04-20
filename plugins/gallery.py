import os
import glob
import hashlib
import json
import shutil
import functools
import copy
from urllib.parse import urljoin

import yaml
from yapsy.IPlugin import IPlugin

from PIL import Image
from thumbnails import get_thumbnail

class MyPointPlugin(IPlugin):
    def activate(self, settings):
        self.settings = settings
        super().activate()

    def generate_sha1(self, fp, block_size=65536):
        hasher = hashlib.sha1()
        buf = fp.read(block_size)
        while len(buf) > 0:
            hasher.update(buf)
            buf = fp.read(block_size)
        return hasher.hexdigest()

    def generate_sha1_for_file(self, path):
        with open(path, 'rb') as afile:
            return self.generate_sha1(afile)

    def get_custom_data_for_file(self, file_path, suffix='.yaml'):
        data_path = '{file_path}{suffix}'.format(
            file_path=file_path,
            suffix=suffix
        )
        if os.path.isfile(data_path):
            with open(data_path) as f:
                return yaml.load(f)
        return {}

    def get_file_paths(self, file_selectors):
        for s in file_selectors:
            for file_path in glob.glob(os.path.join(self.settings['from_dir'], s)):
                yield file_path

    def make_path_relative(self, path):
        return os.path.relpath(path, self.settings['output_dir'])

    def form_obj_url(self, path):
        relative_path = self.make_path_relative(path)
        base_url = self.settings.get('base_url')
        if not base_url:
            return relative_path
        url = urljoin(self.settings['base_url'], relative_path)
        return url

    def get_objects(self, file_paths, sort_by, reverse=False):
        def get_object_data(path):
            data = {
                'path': path,
                'filename': os.path.split(path)[-1],
                'mtime': os.path.getmtime(path),
                'ctime': os.path.getctime(path),
            }
            data.update(self.get_custom_data_for_file(path))
            return data
        objs = [get_object_data(p) for p in file_paths]
        if sort_by:
            objs.sort(key=lambda x: x[sort_by], reverse=reverse)
        return objs

    def filter_fields(self, item, fields):
        return {k: v for k, v in item.items() if k in fields}

    def pre_save_actions(self):
        return []

    def post_save_actions(self):
        return []

    def format_detail_json(self, fields, **kwargs):
        kwargs = self.filter_fields(kwargs, fields)
        return kwargs

    def format_list_json(self, fields, *objs):
        objs = [self.filter_fields(o, fields) for o in objs]
        return objs

    def generate(self, **kwargs):
        name = kwargs.pop('name')
        file_selectors = kwargs.pop('file_selectors')
        list_attributes = kwargs.pop('list_attributes')
        detail_attributes = kwargs.pop('detail_attributes')
        order = kwargs.pop('order')

        objs = self.get_objects(self.get_file_paths(file_selectors), **order)
        base_path = os.path.join(self.settings['output_dir'], self.settings['api_namespace'], name)
        for i, obj in enumerate(objs, 1):
            obj['id'] = i
            obj_dir = os.path.join(base_path, str(i))
            obj_detail_json_path = os.path.join(obj_dir, 'index.json')
            obj['obj_dir'] = obj_dir
            obj['url'] = self.form_obj_url(obj_dir)
            obj['obj_detail_json_path'] = obj_detail_json_path

            # Create directory for object
            try:
                os.makedirs(obj_dir)
            except FileExistsError:
                pass #TODO: log that file already exists.

            # Run pre save actions
            for f in self.pre_save_actions():
                obj.update(f(copy.deepcopy(obj), **copy.deepcopy(kwargs)))

            # Write details
            with open(obj_detail_json_path, 'w') as fp:
                json.dump(self.format_detail_json(detail_attributes, **obj), fp)
            shutil.copy2(obj['path'], obj_dir)
            print(obj)

            # Run post save actions
            for f in self.post_save_actions():
                f(copy.deepcopy(obj), **copy.deepcopy(kwargs))

        # Write index json.
        with open(os.path.join(base_path, 'index.json'), 'w') as fp:
            json.dump(self.format_list_json(list_attributes, *objs), fp)

class Gallery(MyPointPlugin):
    def pre_save_actions(self):
        return [self.set_attributes, self.image_transpose_exif, self.generate_thumbnail]

    def post_save_actions(self):
        return []

    def set_attributes(self, obj, **kwargs):
        return {
            'image': self.form_obj_url(os.path.join(obj['obj_dir'], obj['filename']))
        }

    def generate_thumbnail(self, obj, thumbnail=None):
        if not thumbnail:
            return {}
        #TODO: support multiple thumbnail sizes
        thumbnail_size = thumbnail.pop('size')
        obj_path = obj['path']
        thumbnail_file_path = get_thumbnail(obj_path, thumbnail_size, **thumbnail).path
        _, extension = os.path.splitext(obj_path)
        thumbnail_path = os.path.join(obj['obj_dir'], 'thumbnail{extension}'.format(extension=extension))
        shutil.copyfile(thumbnail_file_path, thumbnail_path)
        return {'thumbnail': self.form_obj_url(thumbnail_path)}

    def image_transpose_exif(self, obj, **kwargs):
        img = Image.open(obj['path'])

        exif_orientation_tag = 0x0112 # contains an integer, 1 through 8
        exif_transpose_sequences = [  # corresponding to the following
            [],
            [Image.FLIP_LEFT_RIGHT],
            [Image.ROTATE_180],
            [Image.FLIP_TOP_BOTTOM],
            [Image.FLIP_LEFT_RIGHT, Image.ROTATE_90],
            [Image.ROTATE_270],
            [Image.FLIP_TOP_BOTTOM, Image.ROTATE_90],
            [Image.ROTATE_90],
        ]
        try:
            seq = exif_transpose_sequences[img._getexif()[exif_orientation_tag] - 1]
        except Exception:
            pass
        else:
            functools.reduce(lambda im, op: img.transpose(op), seq, img)
        img.save(obj['path'])
        return {}
