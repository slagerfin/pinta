import os
import shutil

import yaml
import click
from yapsy.PluginManager import PluginManager


def load_mypoint(dir, filename='root.yaml'):
    try:
        with open(os.path.join(dir, filename)) as f:
            return yaml.load(f)
    except IOError:
        #TODO: Must have root file, raise exception
        return

def copy_static_dir(from_dir, output_dir):
    for root, dirs, files in os.walk(os.path.join(from_dir, 'static')):
        for f in files:
            path_file = os.path.join(root, f)
            shutil.copy2(path_file, output_dir)

def create_output_dir(output_dir):
    try:
        os.mkdir(output_dir)
    except FileExistsError:
        pass


@click.command()
@click.argument('from-dir', type=click.Path(exists=True))
@click.argument('output-dir', type=click.Path())
def generate(from_dir, output_dir):
    from_dir = os.path.abspath(from_dir)
    output_dir = os.path.abspath(output_dir)

    create_output_dir(output_dir)
    copy_static_dir(from_dir, output_dir)

    # Load settings
    site = load_mypoint(from_dir)
    settings = site.pop('settings')
    #TODO: rename to from_dir
    settings['from_dir'] = from_dir
    settings['output_dir'] = output_dir

    manager = PluginManager()
    manager.setPluginPlaces(["plugins"])
    manager.collectPlugins()

    for plugin in manager.getAllPlugins():
        plugin.plugin_object.activate(settings)

    for a in site.pop('apis'):
        plugin = manager.getPluginByName(a.pop('plugin')).plugin_object
        click.echo(plugin.generate(**a))

if __name__ == '__main__':
    generate()
