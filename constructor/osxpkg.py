import os
import sys
import shutil
from os.path import dirname, exists, expanduser, join
from subprocess import check_call
import xml.etree.ElementTree as ET

from constructor.install import rm_rf, name_dist



OSX_DIR = join(dirname(__file__), "osx")
CONDA_DIR = expanduser('~/.conda')
PACKAGE_ROOT = join(CONDA_DIR, "package_root")
PACKAGES_DIR = join(CONDA_DIR, "built_pkgs")


def write_readme(path):
    shutil.copy(join(OSX_DIR, 'readme_header.rtf'), path)

    with open(path, 'a') as f:
        for dist in sorted(DISTS):
            if dist.startswith('_'):
                continue
            f.write("{\\listtext\t\n\\f1 \\uc0\\u8259 \n\\f0 \t}%s %s\\\n" %
                    tuple(dist.rsplit('-', 2)[:2]))
        f.write('}')


def modify_xml(xml_path):
    # See
    # http://developer.apple.com/library/mac/#documentation/DeveloperTools/Reference/DistributionDefinitionRef/Chapters/Distribution_XML_Ref.html#//apple_ref/doc/uid/TP40005370-CH100-SW20 for all the options you can put here.

    tree = ET.parse(xml_path)
    root = tree.getroot()

    title = ET.Element('title')
    title.text = NAME
    root.append(title)

    license = ET.Element('license', file=LICENSE_PATH)
    root.append(license)

    background = ET.Element('background',
                            file=join(FILES_DIR, 'MacInstaller.png'),
                            scaling='proportional', alignment='center')
    root.append(background)

    conclusion = ET.Element('conclusion', file=join(OSX_DIR, 'acloud.rtf'),
                            attrib={'mime-type': 'richtext/rtf'})
    root.append(conclusion)

    readme_path = join(PACKAGES_DIR, "readme.rtf")
    write_readme(readme_path)
    readme = ET.Element('readme', file=readme_path,
                        attrib={'mime-type': 'richtext/rtf'})
    root.append(readme)

    [options] = [i for i in root.findall('options')]
    options.set('customize', 'allow')
    options.set('customLocation', '/')

    [default_choice] = [i for i in root.findall('choice')
                        if i.get('id') == 'default']
    default_choice.set('title', NAME)

    [path_choice] = [i for i in root.findall('choice')
                     if 'pathupdate' in i.get('id')]
    path_choice.set('visible', 'true')
    path_choice.set('title', "Modify PATH")
    path_description = """
    Whether to modify the bash profile file to append anaconda to the PATH
    variable.  If you do not do this, you will need to add ~/anaconda/bin
    to your PATH manually to run the commands, or run all anaconda commands
    explicitly from that path.
    """
    path_choice.set('description', ' '.join(path_description.split()))

    domains = ET.Element('domains',
                         enable_anywhere='true',
                         enable_currentUserHome='true',
                         enable_localSystem='false')
    root.append(domains)

    tree.write(xml_path)


def move_script(src, dst):
    with open(src) as fi:
        data = fi.read()

    data = data.replace('__NAME__', NAME)
    data = data.replace('__VERSION__', VERSION)
    data = data.replace('__PYTHON_DIST__', PYTHON_DIST)

    with open(dst, 'w') as fo:
        fo.write(data)
    os.chmod(dst, 0o755)


def fresh_dir(dir_path):
    rm_rf(dir_path)
    assert not exists(dir_path)
    os.mkdir(dir_path)


def pkgbuild(name, scripts=None):
    args = [
        "pkgbuild",
        "--root", PACKAGE_ROOT,
    ]
    if scripts:
        args.extend([
            "--scripts", scripts,
        ])
    args.extend([
        "--identifier", "io.continuum.pkg.%s" % name,
        "--ownership", "preserve",
        "%s/%s.pkg" % (PACKAGES_DIR, name),
    ])
    check_call(args)


def pkgbuild_script(name, src, dst='postinstall'):
    scripts_dir = join(AROOT, "scripts")
    fresh_dir(scripts_dir)
    move_script(join(OSX_DIR, src),
                join(scripts_dir, dst))
    fresh_dir(PACKAGE_ROOT)  # --root <empty dir>
    pkgbuild(name, scripts_dir)


def make_package():
    # See http://stackoverflow.com/a/11487658/161801 for how all this works.

    anaconda_dir = join(PACKAGE_ROOT, "anaconda")
    pkgs_dir = join(anaconda_dir, "pkgs")

    fresh_dir(PACKAGES_DIR)

    fresh_dir(PACKAGE_ROOT)
    preconda.write_files(anaconda_dir)
    pkgbuild('preconda')

    for dist in DISTS:
        fresh_dir(PACKAGE_ROOT)
        os.makedirs(pkgs_dir)
        tar_xf(join(TARS_DIR, dist + '.tar.bz2'), join(pkgs_dir, dist))
        pkgbuild(name_dist(dist))

    # Create special preinstall and postinstall packages to check if Anaconda
    # is already installed, build Anaconda, and to update the shell profile.

    # First the script to build Anaconda (move everything to the prefix and
    # run conda install)
    pkgbuild_script('postextract', 'post_extract.sh')

    # Next, the script to edit bashrc with the PATH.  This is separate so it
    # can be disabled.
    pkgbuild_script('pathupdate', 'update_path.sh')

    # Next, the script to be run before everything, which checks if Anaconda
    # is already installed.
    pkgbuild_script('apreinstall', 'preinstall.sh', 'preinstall')

    # Now build the final package
    names = ['apreinstall', 'preconda']
    names.extend(name_dist(dist) for dist in DISTS)
    names.extend(['postextract', 'pathupdate'])

    xml_path = join(PACKAGES_DIR, 'distribution.xml')
    args = ["productbuild", "--synthesize"]
    for name in names:
        args.extend(['--package', join(PACKAGES_DIR, "%s.pkg" % name)])
    args.append(xml_path)
    check_call(args)

    modify_xml(xml_path)

    check_call([
        "productbuild",
        "--distribution", xml_path,
        "--package-path", PACKAGES_DIR,
        "--identifier", NAME,
        "%s.pkg" % FNROOT,
    ])


if __name__ == '__main__':
    fetch_all()
    make_package()
