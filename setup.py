from setuptools import setup, find_packages

setup(
    name="hs-battlegrounds-ai",
    version="0.1.0",
    description="Machine learning framework for Hearthstone Battlegrounds AI",
    author="You",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "torch>=2.0.0",
        "numpy>=1.24.0",
        "pandas>=1.5.0",
        "matplotlib>=3.7.0",
        "tensorboard>=2.13.0",
    ],
    extras_require={
        "dev": ["pytest>=7.3.0", "black>=23.0.0", "flake8>=6.0.0"],
    },
)
