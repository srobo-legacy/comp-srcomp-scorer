from setuptools import find_packages, setup


with open('README.rst') as f:
    long_description = f.read()

setup(
    name='sr.comp.scorer',
    version='1.0.0',
    packages=find_packages(),
    namespace_packages=['sr', 'sr.comp'],
    description='Student Robotics Competition Score Entry Application',
    long_description=long_description,
    include_package_data=True,
    zip_safe=False,
    author='Student Robotics Competition Software SIG',
    author_email='srobo-devel@googlegroups.com',
    install_requires=[
        'PyYAML >=3.11, <4',
        'six >=1.8, <2',
        'Flask >=0.10, <0.11',
        'sr.comp >=1.0, <2'
    ],
    setup_requires=[
        'Sphinx >=1.3, <2'
    ]
)
