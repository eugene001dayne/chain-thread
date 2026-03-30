from setuptools import setup, find_packages

setup(
    name="chainthread",
    version="0.1.0",
    description="Open agent handoff protocol and verification infrastructure.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Eugene Dayne Mawuli",
    author_email="bitelance.team@gmail.com",
    url="https://github.com/eugene001dayne/chain-thread",
    packages=find_packages(),
    py_modules=["chainthread"],
    python_requires=">=3.9",
    install_requires=["httpx"],
)