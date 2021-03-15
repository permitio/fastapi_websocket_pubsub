from setuptools import setup, find_packages

def get_requirements(env=""):
    if env:
        env = "-{}".format(env)
    with open("requirements{}.txt".format(env)) as fp:
        return [x.strip() for x in fp.read().split("\n") if not x.startswith("#")]

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name='fastapi_websocket_pubsub',
    version='0.1.14',
    author='Or Weis',
    author_email="or@authorizon.com",
    description="A fast and durable PubSub channel over Websockets (using fastapi-websockets-rpc).",
    long_description_content_type="text/markdown",
    long_description=long_description,
    url="https://github.com/authorizon/fastapi_websocket_pubsub",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
        "Topic :: Internet :: WWW/HTTP :: WSGI"
    ],    
    python_requires='>=3.7',
    install_requires=get_requirements(),
)