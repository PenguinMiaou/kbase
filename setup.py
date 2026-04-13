from setuptools import setup, find_packages

setup(
    name="kbase",
    version="0.5.0",
    author="PenguinMiaou",
    license="MIT",
    packages=find_packages(),
    install_requires=[
        "chromadb>=0.5.0",
        "sentence-transformers>=2.2.0",
        "python-pptx>=0.6.21",
        "python-docx>=1.0.0",
        "openpyxl>=3.1.0",
        "PyMuPDF>=1.23.0",
        "click>=8.0.0",
        "watchdog>=3.0.0",
        "rich>=13.0.0",
        "fastapi>=0.100.0",
        "uvicorn>=0.23.0",
        "python-multipart>=0.0.6",
    ],
    entry_points={
        "console_scripts": [
            "kbase=kbase.cli:main",
        ],
    },
    python_requires=">=3.9",
)
