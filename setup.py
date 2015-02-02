from setuptools import find_packages, setup


with open('README.rst') as f:
    long_description = f.read()


setup(name='sr.comp.scorer',
      version='1.0.0',
      packages=find_packages(),
      namespace_packages=['sr', 'sr.comp'],
      description='srcomp score entry app',
      long_description=long_description,
      author='Student Robotics Competition Software SIG',
      author_email='srobo-devel@googlegroups.com',
      install_requires=['PyYAML >=3.11, <4',
                        'sr.comp >=1.0, <2'])
