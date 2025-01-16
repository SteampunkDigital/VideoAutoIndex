from setuptools import setup, find_packages

setup(
    name="video-auto-index",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "ffmpeg-python",
        "flask",
        "anthropic",
        "beautifulsoup4",
    ],
    python_requires=">=3.11",
)
