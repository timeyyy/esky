import sys
from esky import bdist_esky
from distutils.core import setup
from esky.bdist_esky import Executable
setup(
    name = 'example-app',
    version = '0.1',
    options = {"bdist_esky": {
                "freezer_module":"cxfreeze",
		"includes":['tkinter']
	      }},
    scripts = [Executable('example3.py')],
)

