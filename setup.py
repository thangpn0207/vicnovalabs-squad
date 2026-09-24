#!/usr/bin/env python3
from setuptools import setup, find_packages

setup(
    name="VicnovaLabs-squad",
    version="1.0.0",
    description="Multi-IDE Autonomous Specialized Squad Framework",
    author="VicnovaLabs Team",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "squad=squad_engine.cli:main",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
