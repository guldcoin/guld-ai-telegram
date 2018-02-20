from bot import __version__
from setuptools import setup, find_packages

REQUIREMENTS = [line.strip() for line in open("requirements.txt").readlines()]

setup(name='guldai-telegram-bot',
      version=__version__,
      description='Telegram interface for the guldai bot',
      author='isysd',
      author_email='public@iramiller.com',
      license='MIT',
      url='https://guld.io/',
      py_modules = ['bot'],
    #   packages=find_packages(exclude=['tests', 'tests.*']),
    #   zip_safe=False,
    #   include_package_data=True,
      install_requires=REQUIREMENTS,
      classifiers=[
          'Topic :: Communications :: ChatBot',
          'Development Status :: 4 - Beta',
          'Intended Audience :: End Users/Desktop',
          'License :: OSI Approved :: MIT License',
          'Programming Language :: Python :: 2.7',
          'Programming Language :: Python :: 3.4',
          'Topic :: Internet'
])
