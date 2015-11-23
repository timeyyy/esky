#import sys
#from esky import bdist_esky
#from distutils.core import setup
#    
#from esky.bdist_esky import Executable
#setup(
#    name = 'example-app',
#    version = '0.1',
#    options = {"bdist_esky": {
#                "freezer_module":"cxfreeze",
#		"includes":["future"],
#	      }},
#    scripts = [Executable('script1.py')],
#)

from cx_Freeze import setup, Executable
setup(
        name = 'example-app',
	version = '0.0',
	executables=[Executable('script1.py')],
    )
   
