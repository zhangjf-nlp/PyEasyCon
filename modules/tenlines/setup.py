"""
Ten Lines Python API - setup.py

Pure Python package with optional pybind11 C++ acceleration.
The pybind11 module is built separately via src/pybind/setup.py.
This setup.py installs the pure Python package and resource files.
"""

from setuptools import setup, find_packages
import os

# Read README
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="tenlines",
    version="1.1.0",
    author="Ten Lines Contributors",
    description="Gen 3 Pokemon RNG manipulation toolkit (Python port)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/lincoln-lm/ten-lines",
    license="GPLv3",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: C++",
        "Topic :: Games/Entertainment",
    ],
    python_requires=">=3.8",
    py_modules=["tenlines", "tenlines_utils"],
    package_data={
        "": ["resources/**/*"],
    },
    include_package_data=True,
    install_requires=[
        "requests>=2.20",
    ],
    extras_require={
        "accelerated": ["pybind11>=2.10"],
        "dev": ["pybind11>=2.10", "numpy>=1.20"],
    },
    entry_points={
        "console_scripts": [],
    },
)
