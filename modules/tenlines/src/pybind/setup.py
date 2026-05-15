import sysconfig

from pybind11 import get_include as pybind11_get_include
from setuptools import setup, Extension

extra_compile_args = ["-O3", "-ffast-math", "-std=c++14"]

ext_modules = [
    Extension(
        "calibration_bind",
        ["calibration_bind.cpp"],
        include_dirs=[
            pybind11_get_include(),
            sysconfig.get_path("include"),
        ],
        extra_compile_args=extra_compile_args,
        language="c++",
    ),
]

setup(
    name="calibration_bind",
    version="1.1.0",
    ext_modules=ext_modules,
    zip_safe=False,
)
