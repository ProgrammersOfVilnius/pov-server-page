#!/usr/bin/env python
import os
from setuptools import setup, find_packages

here = os.path.dirname(__file__)
with open(os.path.join(here, 'README.rst')) as f:
    long_description = f.read()

setup(
    name='pov-server-page',
    version='0.9',
    author='Marius Gedminas',
    author_email='marius@pov.lt',
    url='https://github.com/ProgrammersOfVilnius/pov-server-page',
    description='PoV server page',
    long_description=long_description,
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
    license='GPL',

    packages=find_packages('src'),
    package_dir={'': 'src'},
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'mako',
    ],
    extras_require={
        'test': [
            'mock',
        ],
    },
)
